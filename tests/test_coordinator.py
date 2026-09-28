from __future__ import annotations

import os
import subprocess
import tempfile
import threading
import unittest
import uuid
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest.mock import patch

from scripts.riff_core.adapters.base import HarnessAdapter
from scripts.riff_core.coordinator import Coordinator
from scripts.riff_core.models import RunRequest, SettledTurn, TurnRequest, ValidationError
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

    def test_independent_first_does_not_include_a_driver_answer(self) -> None:
        request = self.request(participants=1)
        self.coordinator.run(request)
        prompt = self.fake.turns[0].prompt
        self.assertIn("deliberately withheld", prompt)
        self.assertNotIn("Driver's current position", prompt)

    def test_reply_uses_the_exact_native_session(self) -> None:
        started = self.coordinator.run(self.request(participants=1))
        replied = self.coordinator.reply(
            started["run_id"],
            "peer-0",
            "Compare with option B.",
            timeout_seconds=1200,
        )
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
            self.assertIsNotNone(progress["participants"]["peer-0"]["active_turn"])
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

    def test_recursive_child_is_rejected_at_the_depth_bound(self) -> None:
        with patch.dict(
            os.environ,
            {
                "RIFF_RUN_ID": "00000000-0000-0000-0000-000000000001",
                "RIFF_DEPTH": "1",
            },
            clear=False,
        ):
            with self.assertRaisesRegex(ValidationError, "recursive Riff invocation"):
                self.coordinator.run(self.request(participants=1))

    def test_verification_is_recorded_without_fabricated_checks(self) -> None:
        started = self.coordinator.run(self.request(participants=1))
        result = self.coordinator.verify(
            started["run_id"],
            verifier="codex-driver",
            result="not_performed",
            checks=[],
            integrated=False,
            note="Planning-only consult",
        )
        self.assertTrue(result["ok"])
        manifest = self.coordinator.status(started["run_id"])["manifest"]
        self.assertEqual(manifest["verification"]["checks"], [])
        self.assertEqual(manifest["verification"]["result"], "not_performed")
        self.assertFalse(manifest["verification"]["performed"])

    def test_executed_checks_derive_the_result_and_record_exit_codes(self) -> None:
        started = self.coordinator.run(self.request(participants=1))
        result = self.coordinator.verify(
            started["run_id"],
            verifier="driver",
            result=None,
            checks=["Read the diff"],
            integrated=True,
            commands=["echo suite ok", "exit 3"],
        )
        self.assertEqual(result["result"], "partial")
        checks = self.coordinator.status(started["run_id"])["manifest"]["verification"]["checks"]
        self.assertEqual([check["kind"] for check in checks], ["asserted", "executed", "executed"])
        self.assertEqual(checks[0]["text"], "Read the diff")
        self.assertEqual([check["exit_code"] for check in checks[1:]], [0, 3])
        self.assertEqual(checks[1]["cwd"], str(self.cwd.resolve()))
        self.assertIn("suite ok", Path(checks[1]["output_file"]).read_text())
        self.assertTrue(checks[1]["output_sha256"])

    def test_passed_cannot_contradict_a_failing_executed_check(self) -> None:
        started = self.coordinator.run(self.request(participants=1))
        with self.assertRaisesRegex(ValidationError, "contradicts executed check 'exit 1'"):
            self.coordinator.verify(
                started["run_id"],
                verifier="driver",
                result="passed",
                checks=[],
                integrated=True,
                commands=["exit 1"],
            )
        manifest = self.coordinator.status(started["run_id"])["manifest"]
        self.assertEqual(manifest["verification"]["result"], "pending")

    def test_timed_out_check_fails_and_records_view_change(self) -> None:
        started = self.coordinator.run(self.request(participants=1))
        result = self.coordinator.verify(
            started["run_id"],
            verifier="driver",
            result=None,
            checks=[],
            integrated=False,
            commands=["sleep 5"],
            command_timeout_seconds=1,
            view_changed=True,
        )
        self.assertEqual(result["result"], "failed")
        verification = self.coordinator.status(started["run_id"])["manifest"]["verification"]
        self.assertTrue(verification["checks"][0]["timed_out"])
        self.assertIsNone(verification["checks"][0]["exit_code"])
        self.assertTrue(verification["view_changed"])

    def test_result_is_required_without_an_executed_check(self) -> None:
        started = self.coordinator.run(self.request(participants=1))
        with self.assertRaisesRegex(ValidationError, "result is required"):
            self.coordinator.verify(
                started["run_id"],
                verifier="driver",
                result=None,
                checks=["Looked fine"],
                integrated=False,
            )

    def test_prompt_demands_evidence_and_never_carries_the_prediction(self) -> None:
        request = RunRequest.from_dict(
            {
                "version": 1,
                "mode": "consult",
                "task": "Choose an approach.",
                "origin_harness": "codex",
                "participants": [{"id": "peer-0", "harness": "fake", "cwd": str(self.cwd)}],
                "driver_prediction": "Option B wins unless the cache is shared.",
            }
        )
        started = self.coordinator.run(request)
        prompt = self.fake.turns[0].prompt
        self.assertIn("evidence (file:line", prompt)
        self.assertNotIn("Option B wins", prompt)
        manifest = self.coordinator.status(started["run_id"])["manifest"]
        self.assertEqual(
            manifest["request"]["driver_prediction"],
            "Option B wins unless the cache is shared.",
        )
        self.assertEqual(started["warnings"], [])

    def test_failed_turns_do_not_spend_rounds_but_attempts_are_capped(self) -> None:
        flaky = FakeAdapter("fake", fail_ids={"peer-0"})
        coordinator = Coordinator(store=self.coordinator.store, adapters={"fake": flaky})
        started = coordinator.run(self.request(participants=1, max_rounds=1))
        self.assertEqual(started["result"], "failed")
        # the failed first turn left the single round unspent
        failed_again = coordinator.reply(started["run_id"], "peer-0", "Try again.")
        self.assertFalse(failed_again["ok"])
        with self.assertRaisesRegex(ValidationError, "attempts"):
            coordinator.reply(started["run_id"], "peer-0", "Third try.")

    def test_recovered_turn_spends_the_round(self) -> None:
        flaky = FakeAdapter("fake", fail_ids={"peer-0"})
        coordinator = Coordinator(store=self.coordinator.store, adapters={"fake": flaky})
        started = coordinator.run(self.request(participants=1, max_rounds=1))
        flaky.fail_ids.clear()
        self.assertTrue(coordinator.reply(started["run_id"], "peer-0", "Recover.")["ok"])
        with self.assertRaisesRegex(ValidationError, "max_rounds=1 settled turns"):
            coordinator.reply(started["run_id"], "peer-0", "One more.")

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

    def test_output_carries_next_steps_and_unverified_runs(self) -> None:
        earlier = self.coordinator.run(self.request(participants=1))
        later = self.coordinator.run(self.request(participants=1))
        self.assertIn(earlier["run_id"], later["unverified_runs"])
        self.assertNotIn(later["run_id"], later["unverified_runs"])
        steps = " ".join(later["next_steps"])
        self.assertIn(f"verify --run-id {later['run_id']}", steps)
        self.assertIn("riff.py", steps)
        self.assertIn(f'--state-dir "{self.coordinator.store.root}"', steps)

    def test_timeout_next_step_names_the_exact_session_reply(self) -> None:
        class TimingOut(FakeAdapter):
            def _settle(self, turn: TurnRequest) -> SettledTurn:
                settled = super()._settle(turn)
                settled.status, settled.error_type, settled.error = (
                    "failed",
                    "timeout",
                    "timed out after 1 seconds",
                )
                return settled

        coordinator = Coordinator(
            store=self.coordinator.store, adapters={"fake": TimingOut("fake")}
        )
        result = coordinator.run(self.request(participants=1))
        steps = " ".join(result["next_steps"])
        self.assertIn(f"reply --run-id {result['run_id']} --participant peer-0", steps)

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

    def test_timeout_recovery_suggests_a_longer_bound(self) -> None:
        class TimingOut(FakeAdapter):
            def _settle(self, turn: TurnRequest) -> SettledTurn:
                settled = super()._settle(turn)
                settled.status, settled.error_type = "failed", "timeout"
                settled.error = "timed out after 8 seconds"
                return settled

        coordinator = Coordinator(store=self.coordinator.store, adapters={"fake": TimingOut("fake")})
        steps = " ".join(coordinator.run(self.request(participants=1))["next_steps"])
        self.assertIn("--timeout-seconds 1800", steps)

    def test_peer_is_told_the_exact_commands_it_may_run(self) -> None:
        request = RunRequest.from_dict(
            {
                "version": 1,
                "mode": "delegate",
                "task": "Fix it.",
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
            }
        )
        self.coordinator.run(request)
        self.assertIn("`python3 -m unittest`", self.fake.turns[0].prompt)

    def test_reverification_keeps_history(self) -> None:
        started = self.coordinator.run(self.request(participants=1))
        for outcome in ("partial", "passed"):
            self.coordinator.verify(
                started["run_id"],
                verifier="driver",
                result=outcome,
                checks=[f"pass {outcome}"],
                integrated=outcome == "passed",
            )
        manifest = self.coordinator.status(started["run_id"])["manifest"]
        self.assertEqual(manifest["verification"]["result"], "passed")
        self.assertEqual(
            [entry["result"] for entry in manifest["verification_history"]], ["partial"]
        )

    def test_verification_pass_requires_evidence(self) -> None:
        started = self.coordinator.run(self.request(participants=1))
        with self.assertRaisesRegex(ValidationError, "requires at least one check"):
            self.coordinator.verify(
                started["run_id"],
                verifier="driver",
                result="passed",
                checks=[],
                integrated=True,
            )

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
