from __future__ import annotations

import hashlib
import json
import os
import re
import shlex
import subprocess
import sys
import tempfile
import threading
import unittest
import uuid
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch

from scripts.riff_core.adapters.base import HarnessAdapter
from scripts.riff_core.coordinator import Coordinator
from scripts.riff_core.models import (
    RunRequest,
    SettledTurn,
    TurnRequest,
    ValidationError,
)
from scripts.riff_core.state import RunStore, read_json, redact


class FakeAdapter(HarnessAdapter):
    def __init__(self, name: str, *, fail_ids: set[str] | None = None) -> None:
        self.name = name
        self.fail_ids = fail_ids or set()
        self.turns: list[TurnRequest] = []

    def capability(self):
        return {"harness": self.name, "available": True, "persistent_sessions": True}

    def start(self, turn: TurnRequest) -> SettledTurn:
        return self._settle(turn)

    def reply(self, turn: TurnRequest) -> SettledTurn:
        return self._settle(turn)

    def _settle(self, turn: TurnRequest) -> SettledTurn:
        self.turns.append(turn)
        failed = turn.participant.id in self.fail_ids
        artifact = Path(turn.artifact_path)
        artifact.write_text("" if failed else f"answer from {turn.participant.id}")
        Path(turn.log_path).write_text("fake log")
        return SettledTurn(
            participant_id=turn.participant.id,
            harness=self.name,
            status="failed" if failed else "settled",
            artifact_file=turn.artifact_path,
            log_file=turn.log_path,
            native_session_id=turn.native_session_id or f"session-{turn.participant.id}",
            elapsed_ms=1,
            error_type="model" if failed else None,
            error="seeded failure" if failed else None,
        )


class CoordinatorTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        root = Path(self.temporary.name)
        self.cwd = root / "repo"
        self.cwd.mkdir()
        self.fake = FakeAdapter("fake")
        self.coordinator = Coordinator(
            store=RunStore(root / "state"), adapters={"fake": self.fake}
        )

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def request(self, *, participants=2, max_rounds=3) -> RunRequest:
        return RunRequest.from_dict(
            {
                "version": 1,
                "mode": "discuss",
                "task": "Choose an approach.",
                "origin_harness": "codex",
                "participants": [
                    {
                        "id": f"peer-{index}",
                        "harness": "fake",
                        "cwd": str(self.cwd),
                    }
                    for index in range(participants)
                ],
                "coordination": {
                    "dispatch": "single" if participants == 1 else "broadcast",
                    "max_rounds": max_rounds,
                },
                "driver_position": "withheld",
            }
        )

    def test_multi_participant_run_isolates_sessions_and_emits_turns(self) -> None:
        result = self.coordinator.run(self.request())
        self.assertTrue(result["ok"])
        self.assertEqual(
            [item["session_id"] for item in result["participants"]],
            ["session-peer-0", "session-peer-1"],
        )
        status = self.coordinator.status(result["run_id"])
        self.assertEqual(status["manifest"]["result"], "success")
        for state in status["participant_state"].values():
            self.assertEqual(state["turn_count"], 1)
            turn = read_json(Path(state["turns"][0]))
            self.assertNotIn("prompt", turn["request"])
            self.assertTrue(turn["artifact_sha256"])

    def test_peer_prompt_carries_the_contract_but_never_the_driver_view(self) -> None:
        request = RunRequest.from_dict(
            {
                "version": 1,
                "mode": "delegate",
                "task": "Fix the failing test.",
                "origin_harness": "codex",
                "participants": [
                    {
                        "id": "peer-0",
                        "harness": "fake",
                        "cwd": str(self.cwd),
                        "tools": "write",
                        "params": {"allowed_commands": ["python3 -m unittest"]},
                    }
                ],
                "driver_position": "withheld",
                "driver_prediction": "Option B wins unless the cache is shared.",
            }
        )
        started = self.coordinator.run(request)
        prompt = self.fake.turns[0].prompt
        self.assertIn("deliberately withheld", prompt)
        self.assertNotIn("Driver's current position", prompt)
        # The prediction is the driver's private baseline; the peer must never see it.
        self.assertNotIn("Option B wins", prompt)
        # Permission rules match by prefix, so the peer needs the exact spelling.
        self.assertIn("`python3 -m unittest`", prompt)
        manifest = self.coordinator.status(started["run_id"])["manifest"]
        self.assertEqual(manifest["request"]["driver_prediction"], "Option B wins unless the cache is shared.")

    def test_reply_uses_the_exact_native_session(self) -> None:
        with patch("scripts.riff_core.coordinator.utc_now", return_value="2026-01-01T00:00:00Z"):
            started = self.coordinator.run(self.request(participants=1))
        with patch("scripts.riff_core.coordinator.utc_now", return_value="2026-01-02T00:00:00Z"):
            replied = self.coordinator.reply(
                started["run_id"],
                "peer-0",
                "Compare with option B.",
                timeout_seconds=1200,
            )
        state = self.coordinator.status(started["run_id"])["participant_state"]["peer-0"]
        records = [read_json(Path(path)) for path in state["turns"]]
        self.assertEqual([r["started_at"] for r in records], ["2026-01-01T00:00:00Z", "2026-01-02T00:00:00Z"])
        self.assertEqual(records[1]["settled_at"], "2026-01-02T00:00:00Z")
        self.assertTrue(replied["ok"])
        self.assertTrue(self.fake.turns[-1].is_reply)
        self.assertEqual(self.fake.turns[-1].native_session_id, "session-peer-0")
        self.assertEqual(self.fake.turns[-1].timeout_seconds, 1200)

    def test_round_bound_is_enforced(self) -> None:
        started = self.coordinator.run(self.request(participants=1, max_rounds=1))
        with self.assertRaisesRegex(ValidationError, "reached max_rounds"):
            self.coordinator.reply(started["run_id"], "peer-0", "One more round")

    def test_partial_failure_remains_visible(self) -> None:
        failing = FakeAdapter("fake", fail_ids={"peer-1"})
        coordinator = Coordinator(store=self.coordinator.store, adapters={"fake": failing})
        result = coordinator.run(self.request())
        self.assertFalse(result["ok"])
        self.assertEqual(result["result"], "partial")
        self.assertEqual(result["participants"][1]["error"], "seeded failure")

    def test_replies_recompute_the_whole_run_result(self) -> None:
        recovering = FakeAdapter("fake", fail_ids={"peer-1"})
        coordinator = Coordinator(store=self.coordinator.store, adapters={"fake": recovering})
        started = coordinator.run(self.request())
        self.assertEqual(started["result"], "partial")

        peer_zero = coordinator.reply(started["run_id"], "peer-0", "Recheck.")
        self.assertTrue(peer_zero["ok"])
        self.assertEqual(peer_zero["turn_result"], "success")
        self.assertEqual(peer_zero["result"], "partial")

        recovering.fail_ids.clear()
        peer_one = coordinator.reply(started["run_id"], "peer-1", "Recover.")
        self.assertEqual(peer_one["result"], "success")

    def test_pipeline_adapter_failure_is_contained_and_dependents_are_recorded(self) -> None:
        class RaisingAdapter(FakeAdapter):
            def start(self, turn: TurnRequest) -> SettledTurn:
                if turn.participant.id == "peer-0":
                    raise RuntimeError("seeded adapter crash")
                return super().start(turn)

        request = RunRequest.from_dict(
            {
                "version": 1,
                "mode": "delegate",
                "task": "Produce a two-stage artifact.",
                "origin_harness": "codex",
                "participants": [
                    {"id": "peer-0", "harness": "fake", "cwd": str(self.cwd)},
                    {
                        "id": "peer-1",
                        "harness": "fake",
                        "cwd": str(self.cwd),
                        "tools": "read",
                    },
                ],
                "coordination": {"dispatch": "pipeline"},
            }
        )
        coordinator = Coordinator(
            store=self.coordinator.store, adapters={"fake": RaisingAdapter("fake")}
        )
        result = coordinator.run(request)
        self.assertEqual(result["result"], "failed")
        states = coordinator.status(result["run_id"])["participant_state"]
        first = read_json(Path(states["peer-0"]["turns"][0]))
        second = read_json(Path(states["peer-1"]["turns"][0]))
        self.assertEqual(first["execution"]["error_type"], "adapter")
        self.assertEqual(second["execution"]["error_type"], "dependency")
        self.assertIsNotNone(first["started_at"])
        self.assertIsNone(second["started_at"])
        self.assertIsNotNone(first["settled_at"])
        self.assertIsNotNone(second["settled_at"])

    def test_same_participant_replies_are_serialized_at_the_round_limit(self) -> None:
        started = self.coordinator.run(self.request(participants=1, max_rounds=2))

        def reply(prompt: str):
            try:
                return self.coordinator.reply(started["run_id"], "peer-0", prompt)
            except ValidationError as error:
                return error

        with ThreadPoolExecutor(max_workers=2) as executor:
            outcomes = list(executor.map(reply, ("A", "B")))
        self.assertEqual(sum(isinstance(item, ValidationError) for item in outcomes), 1)
        state = self.coordinator.status(started["run_id"])["participant_state"]["peer-0"]
        self.assertEqual(state["turn_count"], 2)

    def test_progress_reads_pi_trace_without_revealing_content_by_default(self) -> None:
        pi = FakeAdapter("pi")
        coordinator = Coordinator(store=self.coordinator.store, adapters={"pi": pi})
        request = RunRequest.from_dict(
            {
                "version": 1,
                "mode": "consult",
                "task": "Inspect this.",
                "origin_harness": "codex",
                "participants": [
                    {"id": "qwen", "harness": "pi", "cwd": str(self.cwd)}
                ],
            }
        )
        started = coordinator.run(request)
        sessions = coordinator.store.native_state_path(started["run_id"], "qwen") / "sessions"
        sessions.mkdir()
        trace = sessions / "active.jsonl"
        trace.write_text(
            '{"type":"session"}\n'
            '{"type":"message","timestamp":"now","message":{"role":"assistant",'
            '"content":[{"type":"thinking","thinking":"private analysis"},'
            '{"type":"toolCall","name":"read"}]}}\n'
        )
        rpc_log = coordinator.store.log_path(started["run_id"], "qwen-live-001")
        rpc_log.write_text(
            '{"type":"message_update","assistantMessageEvent":'
            '{"type":"thinking_delta","delta":"private "}}\n'
            '{"type":"message_update","assistantMessageEvent":'
            '{"type":"thinking_delta","delta":"analysis"}}\n'
            '{"type":"tool_execution_start","toolName":"read"}\n'
        )
        progress = coordinator.progress(started["run_id"])["participants"]["qwen"]
        metadata = progress["live_trace"]
        self.assertEqual(metadata["latest_message"]["blocks"][0]["characters"], 16)
        self.assertNotIn("preview", metadata["latest_message"]["blocks"][0])
        self.assertEqual(progress["live_rpc"]["delta_characters"]["thinking"], 16)
        self.assertNotIn("previews", progress["live_rpc"])
        preview_progress = coordinator.progress(
            started["run_id"], participant_id="qwen", include_previews=True
        )["participants"]["qwen"]
        preview = preview_progress["live_trace"]
        self.assertEqual(preview["latest_message"]["blocks"][0]["preview"], "private analysis")
        self.assertEqual(
            preview_progress["live_rpc"]["previews"]["thinking"], "private analysis"
        )

    def test_preallocated_run_id_is_used_exactly(self) -> None:
        run_id = str(uuid.uuid4())
        result = self.coordinator.run(self.request(participants=1), run_id=run_id)
        self.assertEqual(result["run_id"], run_id)

    def test_progress_marks_an_inflight_turn_as_running(self) -> None:
        entered = threading.Event()
        release = threading.Event()

        class BlockingAdapter(FakeAdapter):
            def start(self, turn: TurnRequest) -> SettledTurn:
                entered.set()
                release.wait(timeout=5)
                return super().start(turn)

        coordinator = Coordinator(
            store=self.coordinator.store, adapters={"fake": BlockingAdapter("fake")}
        )
        run_id = str(uuid.uuid4())
        with ThreadPoolExecutor(max_workers=1) as executor:
            future = executor.submit(
                coordinator.run, self.request(participants=1), run_id=run_id
            )
            self.assertTrue(entered.wait(timeout=2))
            progress = coordinator.progress(run_id)
            self.assertEqual(progress["status"], "running")
            self.assertEqual(progress["participants"]["peer-0"]["status"], "running")
            active = progress["participants"]["peer-0"]["active_turn"]
            self.assertIsNotNone(active)
            with self.assertRaisesRegex(ValidationError, "requires a settled run"):
                coordinator.verify(
                    run_id,
                    verifier="driver",
                    result="passed",
                    checks=["premature"],
                    integrated=False,
                )
            release.set()
            future.result(timeout=2)
        state = coordinator.status(run_id)["participant_state"]["peer-0"]
        recorded = read_json(Path(state["turns"][0]))
        self.assertEqual(recorded["started_at"], active["started_at"])
        self.assertEqual(recorded["turn_id"], active["turn_id"])
        self.assertIsNotNone(recorded["settled_at"])
        self.assertNotIn("active_turn", state)

    def test_turn_records_bound_each_episode_in_the_native_session(self) -> None:
        native = Path(self.temporary.name) / "native"
        native.mkdir()

        class NativeAdapter(FakeAdapter):
            def native_transcript(self, session_id, session_ref):
                path = native / f"{session_id}.jsonl"
                return path if session_id and path.is_file() else None

            def _settle(self, turn: TurnRequest) -> SettledTurn:
                settled = super()._settle(turn)
                with (native / f"{settled.native_session_id}.jsonl").open("a") as stream:
                    stream.write(json.dumps({"id": f"entry-{len(self.turns)}"}) + "\n")
                return settled

        coordinator = Coordinator(
            store=self.coordinator.store, adapters={"fake": NativeAdapter("fake")}
        )
        session_file = native / "session-peer-0.jsonl"
        with patch.dict(os.environ, {"CODEX_THREAD_ID": "driver-thread"}):
            run_id = coordinator.run(self.request(participants=1))["run_id"]
            first_end = session_file.stat().st_size
            coordinator.reply(run_id, "peer-0", "Continue.")
            # A resumed episode whose start was never observed stays unbounded
            # instead of claiming everything the file holds.
            session_file.unlink()
            coordinator.reply(run_id, "peer-0", "Once more.")
        state = coordinator.status(run_id)["participant_state"]["peer-0"]
        first, second, third = (read_json(Path(path))["native_transcript"] for path in state["turns"])
        self.assertEqual((first["start_offset"], first["end_offset"]), (0, first_end))
        self.assertEqual(second["start_offset"], first_end)
        self.assertEqual(second["last_entry_id"], "entry-2")
        self.assertIsNone(third["start_offset"])
        self.assertEqual(third["sha256"], hashlib.sha256(session_file.read_bytes()).hexdigest())

        driver = {"harness": "codex", "session_id": "driver-thread", "session_file": None}
        self.assertEqual(coordinator.status(run_id)["manifest"]["driver_session"], driver)
        self.assertEqual(read_json(Path(state["turns"][1]))["driver_session"], driver)

    def test_stale_active_turn_does_not_supply_another_turns_start(self) -> None:
        store = self.coordinator.store

        class StaleAdapter(FakeAdapter):
            def start(self, turn: TurnRequest) -> SettledTurn:
                state = store.read_participant(turn.run_id, turn.participant.id)
                state["active_turn"]["turn_id"] = "unrelated-turn"
                state["active_turn"]["started_at"] = "2020-01-01T00:00:00Z"
                store.write_participant(turn.run_id, turn.participant.id, state)
                return super().start(turn)

        coordinator = Coordinator(store=store, adapters={"fake": StaleAdapter("fake")})
        result = coordinator.run(self.request(participants=1))
        state = coordinator.status(result["run_id"])["participant_state"]["peer-0"]
        recorded = read_json(Path(state["turns"][0]))
        self.assertIsNone(recorded["started_at"])
        self.assertIsNotNone(recorded["settled_at"])

    def test_recursive_child_is_rejected_at_the_depth_bound(self) -> None:
        with patch.dict(
            os.environ,
            {
                "RIFF_RUN_ID": "00000000-0000-0000-0000-000000000001",
                "RIFF_DEPTH": "1",
            },
            clear=False,
        ), self.assertRaisesRegex(ValidationError, "recursive Riff invocation"):
            self.coordinator.run(self.request(participants=1))

    def test_verification_refuses_records_it_cannot_stand_behind(self) -> None:
        run_id = self.coordinator.run(self.request(participants=1))["run_id"]
        refusals = [
            ("not_performed verification cannot include checks",
             {"result": "not_performed", "checks": ["looked fine"]}),
            ("passed verification requires at least one check", {"result": "passed", "checks": []}),
            ("result is required", {"result": None, "checks": ["looked fine"]}),
            ("contradicts executed check 'exit 1'",
             {"result": "passed", "checks": [], "commands": ["exit 1"]}),
        ]
        for message, arguments in refusals:
            with self.subTest(message), self.assertRaisesRegex(ValidationError, message):
                self.coordinator.verify(run_id, verifier="driver", integrated=False, **arguments)
        verification = self.coordinator.status(run_id)["manifest"]["verification"]
        self.assertEqual(verification["result"], "pending")

        self.coordinator.verify(
            run_id, verifier="driver", result="not_performed", checks=[], integrated=False
        )
        verification = self.coordinator.status(run_id)["manifest"]["verification"]
        self.assertEqual((verification["result"], verification["performed"]), ("not_performed", False))

    def test_executed_checks_decide_the_result_and_earlier_records_survive(self) -> None:
        run_id = self.coordinator.run(self.request(participants=1))["run_id"]
        first = self.coordinator.verify(
            run_id,
            verifier="driver",
            result=None,
            checks=["Read the diff"],
            integrated=False,
            commands=["echo suite ok", "exit 3"],
        )
        self.assertEqual(first["result"], "partial")
        checks = self.coordinator.status(run_id)["manifest"]["verification"]["checks"]
        self.assertEqual([check["kind"] for check in checks], ["asserted", "executed", "executed"])
        self.assertEqual([check["exit_code"] for check in checks[1:]], [0, 3])
        self.assertEqual(checks[1]["cwd"], str(self.cwd.resolve()))
        self.assertIn("suite ok", Path(checks[1]["output_file"]).read_text())

        second = self.coordinator.verify(
            run_id,
            verifier="driver",
            result=None,
            checks=[],
            integrated=False,
            commands=["sleep 5"],
            command_timeout_seconds=1,
        )
        self.assertEqual(second["result"], "failed")
        manifest = self.coordinator.status(run_id)["manifest"]
        self.assertTrue(manifest["verification"]["checks"][0]["timed_out"])
        self.assertEqual([entry["result"] for entry in manifest["verification_history"]], ["partial"])

    def test_only_settled_turns_spend_rounds_and_attempts_are_capped(self) -> None:
        flaky = FakeAdapter("fake", fail_ids={"peer-0"})
        coordinator = Coordinator(store=self.coordinator.store, adapters={"fake": flaky})
        failing = coordinator.run(self.request(participants=1, max_rounds=1))
        self.assertEqual(failing["result"], "failed")
        # the failed first turn left the single round unspent, so a retry is allowed
        self.assertFalse(coordinator.reply(failing["run_id"], "peer-0", "Try again.")["ok"])
        with self.assertRaisesRegex(ValidationError, "attempts"):
            coordinator.reply(failing["run_id"], "peer-0", "Third try.")

        recovering = coordinator.run(self.request(participants=1, max_rounds=1))
        flaky.fail_ids.clear()
        self.assertTrue(coordinator.reply(recovering["run_id"], "peer-0", "Recover.")["ok"])
        with self.assertRaisesRegex(ValidationError, "max_rounds=1 settled turns"):
            coordinator.reply(recovering["run_id"], "peer-0", "One more.")

    def test_reply_refuses_a_live_running_turn_but_recovers_a_dead_one(self) -> None:
        started = self.coordinator.run(self.request(participants=1))
        store = self.coordinator.store
        state = store.read_participant(started["run_id"], "peer-0")
        state["status"] = "running"
        state["active_turn"] = {"started_at": "now", "coordinator_pid": os.getpid()}
        store.write_participant(started["run_id"], "peer-0", state)
        with self.assertRaisesRegex(ValidationError, "still has a running turn"):
            self.coordinator.reply(started["run_id"], "peer-0", "Anything new?")
        state["active_turn"]["coordinator_pid"] = 2**22 + 12345  # beyond pid_max
        store.write_participant(started["run_id"], "peer-0", state)
        self.assertTrue(self.coordinator.reply(started["run_id"], "peer-0", "Resume.")["ok"])

    def test_next_steps_fit_the_run_and_survive_without_the_skill(self) -> None:
        earlier = self.coordinator.run(self.request(participants=1))
        later = self.coordinator.run(self.request(participants=1))
        self.assertIn(earlier["run_id"], later["unverified_runs"])
        self.assertNotIn(later["run_id"], later["unverified_runs"])

        cases = [
            ("consult", False, {"passed", "not_performed"}),
            ("discuss", False, {"passed", "not_performed"}),
            ("delegate", False, {"passed"}),
            ("consult", True, {"not_performed"}),
        ]
        for mode, failing, expected_outcomes in cases:
            with self.subTest(mode=mode, failing=failing):
                adapter = FakeAdapter("fake", fail_ids={"peer-0"} if failing else set())
                coordinator = Coordinator(store=self.coordinator.store, adapters={"fake": adapter})
                request = RunRequest.from_dict({
                    "mode": mode, "task": "Look at this.", "origin_harness": "codex",
                    "participants": [{"id": "peer-0", "harness": "fake", "cwd": str(self.cwd)}],
                    "driver_position": "none",
                })
                started = coordinator.run(request)
                outcomes = set()
                for step in started["next_steps"]:
                    # Extract the suggested command, not its surrounding explanation.
                    # Only fill user inputs; let the real CLI reject incomplete commands.
                    match = re.search(r"python3 .*?(?:--note '[^']*'|--integrated)", step)
                    if not match:
                        continue
                    command = match.group().replace("<acceptance command>", "exit 0")
                    arguments = [
                        re.sub(r"<[^>]+>", "test input", token)
                        for token in shlex.split(command)
                    ]
                    completed = subprocess.run(
                        [sys.executable, *arguments[1:]],
                        capture_output=True, text=True, check=False,
                    )
                    self.assertEqual(completed.returncode, 0, completed.stderr)
                    record = coordinator.status(started["run_id"])["manifest"]["verification"]
                    outcomes.add(record["result"])
                    self.assertIsNone(record["view_changed"])
                    self.assertEqual(record["integrated"], mode == "delegate")
                    if record["result"] == "passed":
                        expected_kind = "executed" if mode == "delegate" else "asserted"
                        self.assertIn(expected_kind, [check["kind"] for check in record["checks"]])
                    else:
                        self.assertFalse(record["performed"])
                        self.assertEqual(record["checks"], [])
                    if mode != "delegate":
                        self.assertEqual(record["note"], "test input")
                self.assertEqual(outcomes, expected_outcomes)

    def test_timeout_next_step_resumes_the_same_session_with_a_longer_bound(self) -> None:
        class TimingOut(FakeAdapter):
            def _settle(self, turn: TurnRequest) -> SettledTurn:
                settled = super()._settle(turn)
                settled.status, settled.error_type = "failed", "timeout"
                settled.error = "Pi turn did not settle within 7200 seconds"
                return settled

        coordinator = Coordinator(store=self.coordinator.store, adapters={"fake": TimingOut("fake")})
        result = coordinator.run(replace(self.request(participants=1), timeout_seconds=7200))
        steps = " ".join(result["next_steps"])
        self.assertIn(f"reply --run-id {result['run_id']} --participant peer-0", steps)
        # a reply inherits the expired bound unless the step raises it, whatever the
        # harness's wording of the timeout
        self.assertIn("--timeout-seconds 14400", steps)

    def test_documented_inspection_and_exploration_records_run_through_the_cli(self) -> None:
        root = Path(__file__).resolve().parent.parent
        examples = 0
        for name in ("README.md", "SKILL.md", "references/PROTOCOLS.md"):
            for block in re.findall(r"```bash\n(.*?)\n```", (root / name).read_text(), re.DOTALL):
                if " verify --run-id " not in block or "--run " in block:
                    continue
                with self.subTest(document=name, block=block):
                    examples += 1
                    started = self.coordinator.run(self.request(participants=1))
                    command = block.replace('"$RIFF_ROOT/scripts/riff.py"', '"' + str(root / "scripts/riff.py") + '"')
                    command = command.replace("<uuid>", started["run_id"]).replace("<run-id>", started["run_id"])
                    command = command.replace("<you>", "test-driver").replace("\\\n", "")
                    completed = subprocess.run(
                        [sys.executable, *shlex.split(command)[1:],
                         "--state-dir", str(self.coordinator.store.root)],
                        cwd=root, capture_output=True, text=True, check=False,
                    )
                    self.assertEqual(completed.returncode, 0, completed.stderr)
                    record = self.coordinator.status(started["run_id"])["manifest"]["verification"]
                    self.assertNotEqual(record["result"], "pending")
        self.assertGreater(examples, 0, "No executable verification examples found")

    def test_checkout_fingerprint_is_recorded_at_dispatch_and_settle(self) -> None:
        git = ["git", "-C", str(self.cwd)]
        subprocess.run(git + ["init", "-q"], check=True)
        (self.cwd / "a.txt").write_text("one")
        subprocess.run(git + ["add", "a.txt"], check=True)
        subprocess.run(
            git + ["-c", "user.name=t", "-c", "user.email=t@t", "commit", "-qm", "init"],
            check=True,
        )
        (self.cwd / "a.txt").write_text("two")
        started = self.coordinator.run(self.request(participants=1))
        manifest = self.coordinator.status(started["run_id"])["manifest"]
        at_dispatch = manifest["checkouts_at_dispatch"]["peer-0"]
        self.assertEqual(len(at_dispatch["head"]), 40)
        self.assertEqual(at_dispatch["dirty_files"], 1)
        state = self.coordinator.status(started["run_id"])["participant_state"]["peer-0"]
        turn = read_json(Path(state["turns"][0]))
        self.assertEqual(turn["request"]["checkout_at_settle"]["head"], at_dispatch["head"])

    def test_wait_returns_the_settled_result_or_reports_running(self) -> None:
        started = self.coordinator.run(self.request(participants=1))
        waited = self.coordinator.wait(started["run_id"], timeout_seconds=1)
        self.assertEqual(waited["status"], "settled")
        self.assertEqual(waited["participants"][0]["artifact_file"], started["participants"][0]["artifact_file"])
        self.assertTrue(waited["next_steps"])

        store = self.coordinator.store
        manifest = store.read_manifest(started["run_id"])
        manifest["status"] = "running"
        store.write_manifest(started["run_id"], manifest)
        running = self.coordinator.wait(started["run_id"], timeout_seconds=1, poll_seconds=0.2)
        self.assertEqual(running["status"], "running")
        self.assertIn("wait --run-id", running["next_steps"][0])
        with self.assertRaisesRegex(ValidationError, "unknown run id"):
            self.coordinator.wait(str(uuid.uuid4()), timeout_seconds=1)

    def test_run_id_cannot_escape_state_directory(self) -> None:
        with self.assertRaisesRegex(ValueError, "invalid run id"):
            self.coordinator.status("../../escape")

    def test_redaction_preserves_usage_counts_but_removes_credentials(self) -> None:
        value = redact(
            {
                "totalTokens": 42,
                "input_tokens": 12,
                "api_key": "secret-value",
                "refresh_token": "secret-value",
            }
        )
        self.assertEqual(value["totalTokens"], 42)
        self.assertEqual(value["input_tokens"], 12)
        self.assertEqual(value["api_key"], "<redacted>")
        self.assertEqual(value["refresh_token"], "<redacted>")


if __name__ == "__main__":
    unittest.main()
