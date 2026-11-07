"""Fault boundaries exercised with synthetic harnesses and real process ownership."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import textwrap
import threading
import time
import unittest
import uuid
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest.mock import patch

from scripts.riff_core.coordinator import Coordinator
from scripts.riff_core.models import RunRequest, ValidationError
from scripts.riff_core.process import (
    group_state,
    identity,
    process_state,
    spawn_gated,
    spawn_coordinator,
    terminate_group,
)
from scripts.riff_core.state import RunStore, read_json
from .test_coordinator import FakeAdapter

ROOT = Path(__file__).resolve().parent.parent


@unittest.skipUnless(
    sys.platform == "linux", "Linux identity and POSIX process integration"
)
class LifecycleTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.cwd = self.root / "repo"
        self.cwd.mkdir()
        self.store = RunStore(self.root / "state")
        self.adapter = FakeAdapter("fake")
        self.coordinator = Coordinator(
            store=self.store, adapters={"fake": self.adapter}
        )
        self.environment = {
            **os.environ,
            "PYTHONPATH": os.pathsep.join([str(ROOT), str(ROOT / "skills/riff")]),
            "RIFF_STATE_DIR": str(self.store.root),
            "CODEX_HOME": str(self.root / "codex"),
        }
        self.environment.pop("RIFF_DEPTH", None)
        self.environment.pop("RIFF_RUN_ID", None)
        self.environment["CLAUDE_CONFIG_DIR"] = str(self.root / "claude")
        self.environment["HERMES_HOME"] = str(self.root / "hermes")
        isolation = patch.dict(
            os.environ,
            {
                "CLAUDE_CONFIG_DIR": str(self.root / "claude"),
                "HERMES_HOME": str(self.root / "hermes"),
            },
        )
        isolation.start()
        self.addCleanup(isolation.stop)

    def request(
        self,
        *,
        harness="fake",
        participants=1,
        rounds=3,
        dispatch=None,
        participant_id=None,
    ):
        return RunRequest.from_dict(
            {
                "version": 1,
                "mode": "discuss",
                "task": "Review synthetic input.",
                "origin_harness": "codex",
                "participants": [
                    {
                        "id": participant_id or f"peer-{i}",
                        "harness": harness,
                        "cwd": str(self.cwd),
                        "tools": "read",
                    }
                    for i in range(participants)
                ],
                "coordination": {
                    "dispatch": dispatch
                    or ("single" if participants == 1 else "broadcast"),
                    "max_rounds": rounds,
                },
            }
        )

    def worker(self, source, *args, environment=None):
        process = subprocess.Popen(
            [sys.executable, "-c", textwrap.dedent(source), *map(str, args)],
            env=environment or self.environment,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
        )
        self.addCleanup(
            lambda: process.poll() is None and (process.kill(), process.wait(timeout=5))
        )
        return process

    def eventually(self, predicate, timeout=5):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            try:
                value = predicate()
                if value:
                    return value
            except (OSError, ValueError, KeyError):
                pass
            time.sleep(0.02)
        self.fail("synthetic process did not reach the expected boundary")

    def executable(self, name, source):
        path = self.root / name
        path.write_text("#!/usr/bin/env python3\n" + textwrap.dedent(source))
        path.chmod(0o755)
        return str(path)

    def test_parent_death_before_gate_release_cannot_execute_target(self):
        gate_file, effect = self.root / "gate.json", self.root / "effect"
        worker = self.worker(
            """
            import json, pathlib, sys, time
            from scripts.riff_core.process import spawn_gated
            def publish(child):
                pathlib.Path(sys.argv[1]).write_text(json.dumps(child))
                time.sleep(60)
            spawn_gated([sys.executable, '-c', "import pathlib,sys; pathlib.Path(sys.argv[1]).touch()", sys.argv[2]], observe=publish)
        """,
            gate_file,
            effect,
        )
        child = self.eventually(lambda: read_json(gate_file))
        self.assertEqual(process_state(child), "alive")
        worker.kill()
        worker.wait(timeout=5)
        self.eventually(lambda: process_state(child) == "gone")
        self.assertFalse(effect.exists())

    def test_gate_release_preserves_identity_and_prompt_bytes(self):
        observed = []
        process = spawn_gated(
            [
                sys.executable,
                "-c",
                "import json,sys; from scripts.riff_core.process import identity; print(json.dumps(identity())); print(sys.stdin.read())",
            ],
            observe=observed.append,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env=self.environment,
        )
        stdout, stderr = process.communicate(b"prompt starts immediately", timeout=5)
        self.assertEqual(process.returncode, 0, stderr)
        lines = stdout.decode().splitlines()
        self.assertEqual(json.loads(lines[0]), observed[0])
        self.assertEqual(lines[1], "prompt starts immediately")
        self.assertEqual(process_state(observed[0]), "gone")

    def test_recycled_pid_and_foreign_or_incomplete_identity_are_distinct(self):
        process = spawn_gated(
            [sys.executable, "-c", "import time; time.sleep(30)"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        process.stdin.close()
        try:
            observed = identity(process.pid)
            self.assertEqual(process_state(observed), "alive")
            recycled = {**observed, "start_ticks": observed["start_ticks"] + 1}
            self.assertEqual(process_state(recycled), "gone")
            self.assertEqual(group_state(recycled), "gone")
            foreign = {**observed, "pid_namespace": "pid:[0]"}
            self.assertEqual(process_state(foreign), "unknown")
            self.assertEqual(group_state(foreign), "unknown")
            self.assertEqual(process_state({"pid": process.pid}), "unknown")
        finally:
            terminate_group(process)

    def test_failed_publication_reaps_unreleased_gate(self):
        observed = []
        effect = self.root / "effect"

        def reject(child):
            observed.append(child)
            raise OSError("synthetic persistence failure")

        with self.assertRaisesRegex(OSError, "persistence"):
            spawn_gated(
                [
                    sys.executable,
                    "-c",
                    "import pathlib,sys; pathlib.Path(sys.argv[1]).touch()",
                    str(effect),
                ],
                observe=reject,
            )
        self.assertEqual(group_state(observed[0]), "gone")
        self.assertFalse(effect.exists())

    def test_reservation_survives_owner_death_and_recovery_counts_it(self):
        request = self.request(rounds=1)
        run_id = str(uuid.uuid4())
        worker = self.worker(
            """
            import json, os, sys
            from tests.test_coordinator import FakeAdapter
            from scripts.riff_core.coordinator import Coordinator
            from scripts.riff_core.models import RunRequest
            class ExitAdapter(FakeAdapter):
                def execute(self, turn):
                    turn.observe_session('reserved-session', None)
                    os._exit(23)
            Coordinator(adapters={'fake': ExitAdapter('fake')}).run(RunRequest.from_dict(json.loads(sys.argv[1])), run_id=sys.argv[2])
        """,
            json.dumps(request.to_dict()),
            run_id,
        )
        self.assertEqual(worker.wait(timeout=5), 23)
        status = self.coordinator.status(run_id)
        self.assertEqual(status["manifest"]["status"], "interrupted")
        self.assertEqual(status["participant_state"]["peer-0"]["turn_count"], 1)
        self.assertEqual(status["participant_state"]["peer-0"]["settled_turns"], 0)
        self.assertEqual(
            self.coordinator.wait(run_id, timeout_seconds=1)["status"], "interrupted"
        )
        self.coordinator.verify(
            run_id,
            verifier="driver",
            result="not_performed",
            checks=[],
            integrated=False,
        )
        self.assertTrue(
            self.coordinator.status(run_id)["verification_scope"]["current"]
        )
        resumed = self.coordinator.reply(
            run_id, "peer-0", "Resume the observed session."
        )
        self.assertTrue(resumed["ok"])
        self.assertEqual(resumed["status"], "settled")
        self.assertEqual(self.adapter.turns[-1].native_session_id, "reserved-session")
        control = self.store.read_control(run_id)
        self.assertEqual(
            [a["outcome"]["status"] for a in control["attempts"]],
            ["interrupted", "settled"],
        )
        self.assertFalse(
            self.coordinator.status(run_id)["verification_scope"]["current"]
        )

    def test_terminal_export_without_control_commit_does_not_promote_success(self):
        request = self.request()
        run_id = str(uuid.uuid4())
        worker = self.worker(
            """
            import json, os, sys
            from tests.test_coordinator import FakeAdapter
            from scripts.riff_core.coordinator import Coordinator
            from scripts.riff_core.models import RunRequest
            from scripts.riff_core.state import RunStore
            class ExitStore(RunStore):
                def write_turn(self, run_id, turn_id, value):
                    path = super().write_turn(run_id, turn_id, value)
                    os._exit(24)
            class Observing(FakeAdapter):
                def execute(self, turn):
                    turn.observe_session('session-peer-0', None)
                    return super().execute(turn)
            Coordinator(store=ExitStore(), adapters={'fake': Observing('fake')}).run(RunRequest.from_dict(json.loads(sys.argv[1])), run_id=sys.argv[2])
        """,
            json.dumps(request.to_dict()),
            run_id,
        )
        self.assertEqual(worker.wait(timeout=5), 24)
        self.assertEqual(
            len(list((self.store.run_dir(run_id) / "turns").glob("*.json"))), 1
        )
        status = self.coordinator.status(run_id)
        self.assertEqual(status["manifest"]["status"], "interrupted")
        self.assertEqual(status["participant_state"]["peer-0"]["settled_turns"], 0)
        self.assertEqual(status["participant_state"]["peer-0"]["turns"], [])
        self.assertTrue(
            self.coordinator.reply(run_id, "peer-0", "Recover the uncommitted turn.")[
                "ok"
            ]
        )
        self.assertEqual(self.adapter.turns[-1].native_session_id, "session-peer-0")

    def test_null_terminal_identity_retains_the_observed_handle(self):
        class NullIdentity(FakeAdapter):
            def execute(self, turn):
                turn.observe_session("observed-session", "observed-session-file")
                result = super().execute(turn)
                result.native_session_id = result.native_session_ref = None
                return result

        coordinator = Coordinator(
            store=self.store, adapters={"fake": NullIdentity("fake")}
        )
        result = coordinator.run(self.request())
        self.assertEqual(result["participants"][0]["session_id"], "observed-session")
        status = coordinator.status(result["run_id"])["participant_state"]["peer-0"]
        self.assertEqual(status["native_session_id"], "observed-session")
        self.assertEqual(status["native_session_ref"], "observed-session-file")
        coordinator.reply(
            result["run_id"], "peer-0", "Continue with the retained handle."
        )
        self.assertEqual(
            coordinator.adapters["fake"].turns[-1].native_session_id, "observed-session"
        )

    def test_dead_owner_with_live_tool_group_blocks_then_resumes_exact_session(self):
        ready, release = self.root / "tool-ready", self.root / "release-tool"
        fake = self.executable(
            "orphan-claude",
            """
            import pathlib, subprocess, sys
            sys.stdin.read()
            subprocess.Popen([sys.executable, '-c',
                'import pathlib,sys,time; pathlib.Path(sys.argv[1]).touch(); '\
                'exec("while not pathlib.Path(sys.argv[2]).exists(): time.sleep(0.02)")',
                __READY__, __RELEASE__])
        """.replace("__READY__", repr(str(ready))).replace(
                "__RELEASE__", repr(str(release))
            ),
        )
        request = self.request(harness="claude")
        run_id = str(uuid.uuid4())
        environment = {**self.environment, "RIFF_CLAUDE_BIN": fake}
        worker = self.worker(
            """
            import json, sys
            from scripts.riff_core.coordinator import Coordinator
            from scripts.riff_core.models import RunRequest
            Coordinator().run(RunRequest.from_dict(json.loads(sys.argv[1])), run_id=sys.argv[2])
        """,
            json.dumps(request.to_dict()),
            run_id,
            environment=environment,
        )
        try:
            self.eventually(ready.exists)
            control = self.store.read_control(run_id)
            attempt = control["attempts"][0]
            child = attempt["child"]
            session_id = control["participant_specs"]["peer-0"]["native_session_id"]
            self.assertTrue(session_id)
            self.eventually(lambda: process_state(child) == "gone")
            self.assertEqual(group_state(child), "alive")
            worker.kill()
            worker.wait(timeout=5)
            coordinator = Coordinator(store=self.store)
            state = coordinator.status(run_id)
            self.assertEqual(state["manifest"]["status"], "interrupted")
            self.assertEqual(
                state["participant_state"]["peer-0"]["active_turn"]["child_state"],
                "alive",
            )
            with self.assertRaisesRegex(ValidationError, "process group is alive"):
                coordinator.reply(run_id, "peer-0", "Unsafe concurrent resume.")
            with self.assertRaisesRegex(ValidationError, "settled run"):
                coordinator.verify(
                    run_id,
                    verifier="driver",
                    result=None,
                    checks=[],
                    commands=["exit 0"],
                    integrated=False,
                )
            coordinator.verify(
                run_id,
                verifier="driver",
                result="not_performed",
                checks=[],
                integrated=False,
            )
            self.assertTrue(coordinator.status(run_id)["verification_scope"]["current"])
            with self.store.mutation(run_id) as updated:
                updated["attempts"][0]["child"]["pid_namespace"] = "pid:[0]"
            with self.assertRaisesRegex(ValidationError, "process group is unknown"):
                coordinator.reply(run_id, "peer-0", "Unprovable resume.")
            with self.store.mutation(run_id) as updated:
                updated["attempts"][0]["child"] = child
            release.touch()
            self.eventually(lambda: group_state(child) == "gone")
            resumed = self.executable(
                "resume-claude",
                """
                import json, sys
                args = sys.argv[1:]
                sys.stdin.read()
                session = args[args.index('--resume') + 1]
                print(json.dumps({'result': 'resumed artifact', 'session_id': session}))
            """,
            )
            with patch.dict(os.environ, {"RIFF_CLAUDE_BIN": resumed}):
                result = coordinator.reply(
                    run_id, "peer-0", "Resume after confirmed group exit."
                )
            self.assertTrue(result["ok"])
            self.assertEqual(result["participants"][0]["session_id"], session_id)
            self.assertEqual(result["status"], "settled")
        finally:
            release.touch()

    def test_initial_completion_cannot_overwrite_active_or_failed_reply(self):
        for active_at_completion in (True, False):
            with self.subTest(active_at_completion=active_at_completion):
                slow_initial, initial_release = threading.Event(), threading.Event()
                reply_entered, reply_release = threading.Event(), threading.Event()

                class Interleaved(FakeAdapter):
                    def execute(self, turn):
                        if turn.participant.id == "peer-1":
                            slow_initial.set()
                            initial_release.wait(5)
                        if turn.is_reply:
                            reply_entered.set()
                            reply_release.wait(5)
                            self.fail_ids.add("peer-0")
                        return super().execute(turn)

                adapter = Interleaved("fake")
                coordinator = Coordinator(store=self.store, adapters={"fake": adapter})
                run_id = str(uuid.uuid4())
                with ThreadPoolExecutor(max_workers=2) as pool:
                    initial = pool.submit(
                        coordinator.run, self.request(participants=2), run_id=run_id
                    )
                    try:
                        self.assertTrue(slow_initial.wait(5))
                        self.eventually(
                            lambda: (
                                coordinator.status(run_id)["participant_state"][
                                    "peer-0"
                                ]["status"]
                                == "settled"
                            )
                        )
                        reply = pool.submit(
                            coordinator.reply, run_id, "peer-0", "A later attempt."
                        )
                        self.assertTrue(reply_entered.wait(5))
                        if not active_at_completion:
                            reply_release.set()
                            self.assertFalse(reply.result(timeout=5)["ok"])
                        initial_release.set()
                        finished_initial = initial.result(timeout=5)
                        self.assertEqual(
                            finished_initial["status"],
                            "running" if active_at_completion else "settled",
                        )
                        self.assertNotEqual(finished_initial["result"], "success")
                    finally:
                        reply_release.set()
                        initial_release.set()
                    self.assertFalse(reply.result(timeout=5)["ok"])
                self.assertEqual(
                    coordinator.status(run_id)["manifest"]["result"], "partial"
                )

    def test_active_reservation_during_checks_invalidates_assessment_before_terminal_export(
        self,
    ):
        entered, release = threading.Event(), threading.Event()

        class ActiveAdapter(FakeAdapter):
            def execute(self, turn):
                if turn.is_reply:
                    entered.set()
                    release.wait(5)
                return super().execute(turn)

        coordinator = Coordinator(
            store=self.store, adapters={"fake": ActiveAdapter("fake")}
        )
        run_id = coordinator.run(self.request())["run_id"]
        with ThreadPoolExecutor(max_workers=1) as pool:
            original = coordinator._execute_check
            reply = None

            def check(*args):
                nonlocal reply
                reply = pool.submit(
                    coordinator.reply, run_id, "peer-0", "Remain active during checks."
                )
                self.assertTrue(entered.wait(5))
                return original(*args)

            try:
                with patch.object(coordinator, "_execute_check", side_effect=check):
                    verified = coordinator.verify(
                        run_id,
                        verifier="driver",
                        result=None,
                        checks=[],
                        commands=["exit 0"],
                        integrated=False,
                    )
                self.assertFalse(verified["verification_scope"]["current"])
                self.assertTrue(verified["verification_scope"]["changed_during_checks"])
                self.assertEqual(
                    verified["verification_scope"]["participants"]["peer-0"], "running"
                )
                self.assertEqual(len(self.store.read_control(run_id)["attempts"]), 2)
                self.assertEqual(
                    len(
                        coordinator.status(run_id)["participant_state"]["peer-0"][
                            "turns"
                        ]
                    ),
                    1,
                )
            finally:
                release.set()
                if reply:
                    reply.result(timeout=5)
        self.assertFalse(coordinator.status(run_id)["verification_scope"]["current"])

    def test_pipeline_pending_and_blocked_work_are_not_launched_attempts(self):
        entered, release = threading.Event(), threading.Event()

        class FailingFirst(FakeAdapter):
            def execute(self, turn):
                entered.set()
                release.wait(5)
                return super().execute(turn)

        coordinator = Coordinator(
            store=self.store,
            adapters={"fake": FailingFirst("fake", fail_ids={"peer-0"})},
        )
        run_id = str(uuid.uuid4())
        with ThreadPoolExecutor(max_workers=1) as pool:
            future = pool.submit(
                coordinator.run,
                self.request(participants=2, dispatch="pipeline"),
                run_id=run_id,
            )
            try:
                self.assertTrue(entered.wait(5))
                status = coordinator.status(run_id)
                self.assertEqual(status["manifest"]["status"], "running")
                self.assertEqual(
                    status["participant_state"]["peer-1"]["status"], "pending"
                )
                self.assertEqual(status["participant_state"]["peer-1"]["turn_count"], 0)
            finally:
                release.set()
            self.assertEqual(future.result(timeout=5)["result"], "failed")
        status = coordinator.status(run_id)
        self.assertEqual(len(self.store.read_control(run_id)["attempts"]), 1)
        self.assertEqual(status["participant_state"]["peer-1"]["turn_count"], 0)
        path = status["participant_state"]["peer-1"]["turns"][0]
        self.assertEqual(read_json(Path(path))["execution"]["error_type"], "dependency")
        self.assertIsNone(read_json(Path(path))["attempt_id"])

    def test_pipeline_recovery_does_not_launch_queued_participants(self):
        request = self.request(participants=2, dispatch="pipeline")
        run_id = str(uuid.uuid4())
        worker = self.worker(
            """
            import json, os, sys
            from tests.test_coordinator import FakeAdapter
            from scripts.riff_core.coordinator import Coordinator
            from scripts.riff_core.models import RunRequest
            class ExitAdapter(FakeAdapter):
                def execute(self, turn):
                    turn.observe_session('pipeline-session', None)
                    os._exit(23)
            Coordinator(adapters={'fake': ExitAdapter('fake')}).run(RunRequest.from_dict(json.loads(sys.argv[1])), run_id=sys.argv[2])
        """,
            json.dumps(request.to_dict()),
            run_id,
        )
        self.assertEqual(worker.wait(timeout=5), 23)
        result = self.coordinator.reply(
            run_id, "peer-0", "Recover this participant only."
        )
        self.assertEqual(result["turn_result"], "success")
        self.assertEqual(result["status"], "interrupted")
        self.assertEqual([t.participant.id for t in self.adapter.turns], ["peer-0"])
        self.assertEqual(
            self.coordinator.status(run_id)["participant_state"]["peer-1"]["status"],
            "pending",
        )

    def test_corrupt_or_missing_terminal_evidence_remains_unknown(self):
        run_id = self.coordinator.run(self.request())["run_id"]
        path = Path(
            self.coordinator.status(run_id)["participant_state"]["peer-0"]["turns"][-1]
        )
        original = path.read_text()
        inconsistent_records = []
        for key in ("run_id", "participant_id", "turn_id"):
            record = json.loads(original)
            record[key] = "another-execution"
            inconsistent_records.append(json.dumps(record))
        record = json.loads(original)
        record["execution"].update(status="failed", error="changed export")
        inconsistent_records.append(json.dumps(record))
        for content in [
            "[]",
            '{"execution": []}',
            '{"execution":{"status":"settled"}}',
            *inconsistent_records,
        ]:
            with self.subTest(content=content):
                path.write_text(content)
                self.assertIsNone(
                    self.coordinator.status(run_id)["verification_scope"]["current"]
                )
                self.assertEqual(
                    self.coordinator.status(run_id)["verification_scope"][
                        "participants"
                    ]["peer-0"],
                    "unknown",
                )
                self.assertFalse(self.coordinator.wait(run_id, timeout_seconds=1)["ok"])
        path.write_text(original)
        artifact = Path(read_json(path)["execution"]["artifact_file"])
        artifact.unlink()
        self.assertIsNone(
            self.coordinator.status(run_id)["verification_scope"]["current"]
        )
        with self.assertRaisesRegex(ValidationError, "readable"):
            self.coordinator.verify(
                run_id,
                verifier="driver",
                result="passed",
                checks=["Cannot read artifact."],
                integrated=False,
            )

        # A well-formed export cannot promote a canonical failure to success.
        self.adapter.fail_ids.add("peer-0")
        failed_run = self.coordinator.run(self.request())["run_id"]
        failed_path = Path(
            self.coordinator.status(failed_run)["participant_state"]["peer-0"]["turns"][-1]
        )
        record = read_json(failed_path)
        record["execution"].update(status="settled", error=None, error_type=None)
        failed_path.write_text(json.dumps(record))
        result = self.coordinator.result(failed_run)
        self.assertEqual(result["result"], "failed")
        self.assertFalse(result["ok"])
        self.assertEqual(result["verification_scope"]["participants"]["peer-0"], "unknown")

    def test_non_linux_posix_alive_hint_keeps_wait_bounded_and_running(self):
        entered, release = threading.Event(), threading.Event()

        class Blocking(FakeAdapter):
            def execute(self, turn):
                entered.set()
                release.wait(5)
                return super().execute(turn)

        coordinator = Coordinator(store=self.store, adapters={"fake": Blocking("fake")})
        run_id = str(uuid.uuid4())
        with patch("scripts.riff_core.process.sys.platform", "darwin"):
            with ThreadPoolExecutor(max_workers=1) as pool:
                future = pool.submit(coordinator.run, self.request(), run_id=run_id)
                try:
                    self.assertTrue(entered.wait(3))
                    started = time.monotonic()
                    result = coordinator.wait(
                        run_id, timeout_seconds=1, poll_seconds=0.02
                    )
                    self.assertEqual(result["status"], "running")
                    self.assertGreaterEqual(time.monotonic() - started, 0.8)
                finally:
                    release.set()
                self.assertTrue(future.result(timeout=3)["ok"])

    def test_missing_reply_adapter_does_not_reserve_an_attempt(self):
        run_id = self.coordinator.run(self.request())["run_id"]
        before = self.store.manifest_path(run_id).read_bytes()
        unavailable = Coordinator(
            store=self.store, adapters={"other": FakeAdapter("other")}
        )
        with self.assertRaisesRegex(ValidationError, "adapter.*unavailable"):
            unavailable.reply(run_id, "peer-0", "Unavailable harness.")
        self.assertEqual(self.store.manifest_path(run_id).read_bytes(), before)
        self.assertEqual(len(self.store.read_control(run_id)["attempts"]), 1)

    def test_busy_reply_fails_fast_before_budget_or_native_execution(self):
        entered, release = threading.Event(), threading.Event()

        class Blocking(FakeAdapter):
            def execute(self, turn):
                if turn.is_reply:
                    entered.set()
                    release.wait(5)
                return super().execute(turn)

        adapter = Blocking("fake")
        coordinator = Coordinator(store=self.store, adapters={"fake": adapter})
        run_id = coordinator.run(self.request())["run_id"]
        with ThreadPoolExecutor(max_workers=1) as pool:
            first = pool.submit(coordinator.reply, run_id, "peer-0", "Hold this reply.")
            try:
                self.assertTrue(entered.wait(3))
                started = time.monotonic()
                with self.assertRaisesRegex(ValidationError, "participant is busy"):
                    coordinator.reply(run_id, "peer-0", "Must not execute.")
                self.assertLess(time.monotonic() - started, 0.5)
                self.assertEqual(len(self.store.read_control(run_id)["attempts"]), 2)
            finally:
                release.set()
            self.assertTrue(first.result(timeout=3)["ok"])
        self.assertEqual(len(adapter.turns), 2)

    def test_supervisor_failure_retains_partial_artifact_and_hides_claim_token(self):
        class Partial(FakeAdapter):
            def execute(self, turn):
                Path(turn.artifact_path).write_text("partial synthetic artifact")
                raise RuntimeError("synthetic supervisor failure")

        coordinator = Coordinator(store=self.store, adapters={"fake": Partial("fake")})
        result = coordinator.run(self.request())
        self.assertFalse(result["ok"])
        self.assertEqual(
            Path(result["participants"][0]["artifact_file"]).read_text(),
            "partial synthetic artifact",
        )
        self.assertNotIn(
            "token", coordinator.status(result["run_id"])["manifest"]["dispatch"]
        )
        self.assertIn("token", self.store.read_control(result["run_id"])["dispatch"])

    def test_direct_observer_failure_without_published_child_stays_unproven(self):
        run_id = str(uuid.uuid4())
        worker = self.worker(
            """
            import json, sys
            from dataclasses import replace
            from pathlib import Path
            from unittest.mock import patch
            from tests.test_coordinator import FakeAdapter
            from scripts.riff_core.coordinator import Coordinator
            from scripts.riff_core.models import RunRequest
            from scripts.riff_core.process import run_process
            class DirectFailure(FakeAdapter):
                def execute(self, turn):
                    turn.observe_session('direct-session', None)
                    Path(turn.artifact_path).write_text('partial direct artifact')
                    def reject(child):
                        raise OSError('synthetic child publication failure')
                    run_process([sys.executable, '-c', 'import time;time.sleep(30)'], replace(turn, observe_process=reject))
            with patch('scripts.riff_core.lifecycle.native_launch_model', return_value='direct'), patch('scripts.riff_core.process.native_launch_model', return_value='direct'):
                Coordinator(adapters={'fake': DirectFailure('fake')}).run(RunRequest.from_dict(json.loads(sys.argv[1])), run_id=sys.argv[2])
        """,
            json.dumps(self.request().to_dict()),
            run_id,
        )
        self.assertEqual(worker.wait(timeout=5), 0)
        attempt = self.store.read_control(run_id)["attempts"][0]
        self.assertEqual(attempt["launch_model"], "direct")
        self.assertEqual(attempt["phase"], "reserved")
        self.assertNotIn("child", attempt)
        self.assertTrue(attempt["diagnostics"][0]["cleanup_unproven"])
        self.assertEqual(
            Path(attempt["artifact_file"]).read_text(), "partial direct artifact"
        )
        with self.assertRaisesRegex(ValidationError, "process group is unknown"):
            self.coordinator.reply(
                run_id, "peer-0", "Cannot infer a direct launch never ran."
            )
        self.assertEqual(len(self.store.read_control(run_id)["attempts"]), 1)

    def test_reaped_supervisor_failure_retains_unproven_group_diagnostics(self):
        release = self.root / "release-background"
        child_file = self.root / "background-pid"
        # Use a separate file so the generated Python string remains ordinary
        # launch input rather than nesting quoted task content.
        child_script = self.root / "background.py"
        child_script.write_text(
            "import pathlib,time\nwhile not pathlib.Path("
            + repr(str(release))
            + ").exists(): time.sleep(0.01)\n"
        )
        parent_code = "import pathlib,subprocess,sys; child=subprocess.Popen([sys.executable,sys.argv[1]]); pathlib.Path(sys.argv[2]).write_text(str(child.pid))"

        class ReapedFailure(FakeAdapter):
            def execute(self, turn):
                child = spawn_gated(
                    [
                        sys.executable,
                        "-c",
                        parent_code,
                        str(child_script),
                        str(child_file),
                    ],
                    observe=turn.observe_process,
                    launch_model=turn.launch_model,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
                child.stdin.close()
                child.wait(timeout=3)
                self.cleanup = terminate_group(child)
                raise RuntimeError("synthetic failure after native reap")

        adapter = ReapedFailure("fake")
        coordinator = Coordinator(store=self.store, adapters={"fake": adapter})
        try:
            result = coordinator.run(self.request())
            self.assertEqual(adapter.cleanup.group_proof, "unknown")
            self.assertEqual(result["status"], "running")
            attempt = self.store.read_control(result["run_id"])["attempts"][0]
            self.assertTrue(attempt["diagnostics"][0]["cleanup_unproven"])
            background = identity(int(child_file.read_text()))
            self.assertEqual(process_state(background), "alive")
        finally:
            release.touch()
            if child_file.exists():
                background = identity(int(child_file.read_text()))
                self.eventually(lambda: process_state(background) == "gone")

    def test_direct_native_failed_completion_can_finish_normally(self):
        from scripts.riff_core.models import SettledTurn
        from scripts.riff_core.process import run_process

        class DirectFailure(FakeAdapter):
            def execute(self, turn):
                completed, elapsed, error = run_process(
                    [sys.executable, "-c", "raise SystemExit(2)"], turn
                )
                self.turns.append(turn)
                return SettledTurn(
                    turn.participant.id,
                    "fake",
                    "failed",
                    turn.artifact_path,
                    turn.log_path,
                    native_session_id="direct-session",
                    error_type="process",
                    error="synthetic exit 2",
                    elapsed_ms=elapsed,
                    adapter_metadata=completed.metadata,
                )

        coordinator = Coordinator(
            store=self.store, adapters={"fake": DirectFailure("fake")}
        )
        with (
            patch(
                "scripts.riff_core.lifecycle.native_launch_model", return_value="direct"
            ),
            patch(
                "scripts.riff_core.process.native_launch_model", return_value="direct"
            ),
        ):
            result = coordinator.run(self.request())
        self.assertFalse(result["ok"])
        self.assertEqual(result["status"], "settled")
        self.assertEqual(
            self.store.read_control(result["run_id"])["attempts"][0]["phase"],
            "finished",
        )

    def test_domain_keys_survive_redaction_through_verify_status_and_reply(self):
        class MetadataAdapter(FakeAdapter):
            def execute(self, turn):
                result = super().execute(turn)
                result.usage = {"input_tokens": 9, "api_key": "synthetic-credential"}
                return result

        coordinator = Coordinator(
            store=self.store, adapters={"fake": MetadataAdapter("fake")}
        )
        request = self.request(participant_id="secret-scan")
        request = RunRequest.from_dict(
            {
                **json.loads(json.dumps(request.to_dict())),
                "participants": [
                    {
                        **request.to_dict()["participants"][0],
                        "params": {"refresh_token": "synthetic-credential"},
                    }
                ],
            }
        )
        result = coordinator.run(request)
        run_id = result["run_id"]
        coordinator.verify(
            run_id,
            verifier="driver",
            result="passed",
            checks=["Inspected synthetic output."],
            integrated=False,
        )
        status = coordinator.status(run_id)
        self.assertEqual(
            status["verification_scope"]["participants"], {"secret-scan": "covered"}
        )
        self.assertTrue(status["verification_scope"]["current"])
        reply = coordinator.reply(run_id, "secret-scan", "Continue.")
        self.assertEqual(
            reply["participants"][0]["usage"],
            {"input_tokens": 9, "api_key": "<redacted>"},
        )
        self.assertNotIn("synthetic-credential", json.dumps(coordinator.status(run_id)))
        self.assertNotIn(
            "synthetic-credential", self.store.manifest_path(run_id).read_text()
        )

    def test_public_readers_are_truly_read_only(self):
        run_id = self.coordinator.run(self.request())["run_id"]
        directory = self.store.run_dir(run_id)
        before = {
            str(p): (p.read_bytes(), p.stat().st_mode)
            for p in directory.rglob("*")
            if p.is_file()
        }
        original_open = Path.open

        def readonly_open(path, mode="r", *args, **kwargs):
            if any(flag in mode for flag in "wa+"):
                raise AssertionError(f"reader tried to write {path.name}")
            return original_open(path, mode, *args, **kwargs)

        with (
            patch.object(
                Path, "mkdir", side_effect=AssertionError("reader mkdir")
            ),
            patch.object(
                Path, "chmod", side_effect=AssertionError("reader chmod")
            ),
            patch.object(Path, "open", readonly_open),
        ):
            coordinator = Coordinator(
                store=RunStore(self.store.root), adapters={"fake": self.adapter}
            )
            status = coordinator.status(run_id)
            self.assertEqual(status["manifest"]["status"], "settled")
            self.assertEqual(coordinator.progress(run_id)["status"], "settled")
            self.assertEqual(
                coordinator.wait(run_id, timeout_seconds=1)["status"], "settled"
            )
            self.assertEqual(coordinator.result(run_id)["result"], "success")
        after = {
            str(p): (p.read_bytes(), p.stat().st_mode)
            for p in directory.rglob("*")
            if p.is_file()
        }
        self.assertEqual(before, after)

        manifest = self.store.manifest_path(run_id)
        original = json.loads(manifest.read_text())
        for unsupported in (
            {"schema_version": 1},
            {"history": {"incomplete": True, "source_schema_version": 1}},
        ):
            with self.subTest(unsupported=unsupported):
                manifest.write_text(json.dumps({**original, **unsupported}))
                before = {p: p.read_bytes() for p in directory.rglob("*") if p.is_file()}
                for reader in (
                    coordinator.status, coordinator.progress,
                    coordinator.result, coordinator.wait,
                ):
                    with self.assertRaisesRegex(ValidationError, "unsupported run history"):
                        reader(run_id)
                with self.assertRaisesRegex(ValidationError, "unsupported run history"):
                    with self.store.mutation(run_id):
                        self.fail("unsupported history accepted for mutation")
                after = {p: p.read_bytes() for p in directory.rglob("*") if p.is_file()}
                self.assertEqual(before, after)

    def test_detached_startup_failure_reports_captured_stderr(self):
        coordinator = Coordinator(store=self.store)
        broken = self.root / "broken-worker.py"
        broken.write_text(
            "import sys; sys.stderr.write('synthetic startup failure'); sys.exit(3)"
        )
        run_id = str(uuid.uuid4())
        with patch("scripts.riff_core.coordinator.RIFF_SCRIPT", broken):
            result = coordinator.detach(self.request(harness="claude"), run_id)
        self.assertEqual(result["status"], "starting")
        self.eventually(
            lambda: (
                coordinator.status(run_id)["manifest"]["status"] == "failed-to-start"
            )
        )
        with self.assertRaisesRegex(ValidationError, "synthetic startup failure"):
            coordinator.wait(run_id, timeout_seconds=1)
        self.assertEqual(self.store.read_control(run_id)["attempts"], [])

    def test_dead_detached_parent_before_publication_is_failed_to_start(self):
        run_id = str(uuid.uuid4())
        worker = self.worker(
            """
            import json, os, sys
            from scripts.riff_core.coordinator import Coordinator
            from scripts.riff_core.models import RunRequest
            Coordinator().prepare(RunRequest.from_dict(json.loads(sys.argv[1])), sys.argv[2], detached=True)
            os._exit(25)
        """,
            json.dumps(self.request(harness="claude").to_dict()),
            run_id,
        )
        self.assertEqual(worker.wait(timeout=5), 25)
        self.assertEqual(
            self.coordinator.status(run_id)["manifest"]["status"], "failed-to-start"
        )
        self.assertEqual(self.store.read_control(run_id)["attempts"], [])

    def test_actual_detached_worker_cannot_mutate_control_without_release(self):
        request = self.request(harness="claude")
        run_id = str(uuid.uuid4())
        token = Coordinator(store=self.store).prepare(request, run_id, detached=True)
        request_file = self.root / "launch-input.json"
        request_file.write_text(json.dumps(request.to_dict()))
        command = [
            sys.executable,
            str(ROOT / "skills/riff/scripts/riff.py"),
            "--state-dir",
            str(self.store.root),
            "_execute",
            "--request",
            str(request_file),
            "--run-id",
            run_id,
            "--launch-token",
            token,
        ]
        child = subprocess.Popen(
            command,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env=self.environment,
        )
        try:
            with self.store.mutation(run_id) as control:
                control["dispatch"]["child"] = identity(child.pid)
            before = self.store.manifest_path(run_id).read_bytes()
            stdout, stderr = child.communicate(timeout=3)
            self.assertNotEqual(child.returncode, 0)
            self.assertIn("was not released", stderr.decode())
            self.assertEqual(self.store.manifest_path(run_id).read_bytes(), before)
            self.assertEqual(self.store.read_control(run_id)["attempts"], [])
        finally:
            if child.poll() is None:
                child.kill()
                child.wait()

    def test_detached_launch_input_cannot_change_reserved_control(self):
        request = self.request(harness="claude")
        run_id = str(uuid.uuid4())
        coordinator = Coordinator(store=self.store)
        token = coordinator.prepare(request, run_id, detached=True)
        changed = request.to_dict()
        changed["coordination"]["max_rounds"] = 20
        source = """
import json, sys
from scripts.riff_core.coordinator import Coordinator
from scripts.riff_core.models import RunRequest
Coordinator().execute_detached(RunRequest.from_dict(json.loads(sys.argv[1])), sys.argv[2], sys.argv[3])
"""

        def publish(child):
            with self.store.mutation(run_id) as control:
                control["dispatch"]["child"] = child

        process = spawn_coordinator(
            [sys.executable, "-c", source, json.dumps(changed), run_id, token],
            observe=publish,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
            env=self.environment,
        )
        _, stderr = process.communicate(timeout=5)
        self.assertNotEqual(process.returncode, 0)
        self.assertIn("does not match its reserved run", stderr.decode())
        self.assertEqual(self.store.read_control(run_id)["attempts"], [])
        self.assertEqual(
            self.store.read_control(run_id)["coordination"]["max_rounds"], 3
        )

    def test_slow_published_detached_worker_remains_starting_until_claim(self):
        request = self.request(harness="claude")
        run_id = str(uuid.uuid4())
        coordinator = Coordinator(store=self.store)
        token = coordinator.prepare(request, run_id, detached=True)
        fake = self.executable(
            "claude",
            """
            import json, sys
            args=sys.argv[1:]; sys.stdin.read()
            print(json.dumps({'result':'synthetic artifact','session_id':args[args.index('--session-id')+1]}))
        """,
        )
        source = """
import json, sys, time
from scripts.riff_core.coordinator import Coordinator
from scripts.riff_core.models import RunRequest
time.sleep(1.5)
Coordinator().execute_detached(RunRequest.from_dict(json.loads(sys.argv[1])), sys.argv[2], sys.argv[3])
"""

        def publish(child):
            with self.store.mutation(run_id) as control:
                control["dispatch"]["child"] = child

        process = spawn_coordinator(
            [
                sys.executable,
                "-c",
                source,
                json.dumps(request.to_dict()),
                run_id,
                token,
            ],
            observe=publish,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
            env={**self.environment, "RIFF_CLAUDE_BIN": fake},
        )
        process.stdin.close()
        try:
            self.assertEqual(
                coordinator.status(run_id)["manifest"]["status"], "starting"
            )
            self.assertEqual(
                coordinator.wait(run_id, timeout_seconds=1, poll_seconds=0.05)[
                    "status"
                ],
                "starting",
            )
            process.wait(timeout=5)
            self.assertEqual(process.returncode, 0, process.stderr.read().decode())
            self.assertEqual(coordinator.result(run_id)["result"], "success")
        finally:
            terminate_group(process)
            process.stderr.close()
