from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from scripts.riff_core.models import RunRequest, ValidationError, request_warnings


class RunRequestTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.cwd = self.temporary.name

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def request(self, **updates):
        value = {
            "version": 1,
            "mode": "consult",
            "task": "Find the strongest flaw in this design.",
            "origin_harness": "codex",
            "participants": [
                {"id": "pi-a", "harness": "pi", "cwd": self.cwd, "tools": "read"}
            ],
        }
        value.update(updates)
        return value

    def test_accepts_same_harness_as_distinct_instances(self) -> None:
        parsed = RunRequest.from_dict(
            self.request(
                participants=[
                    {"id": "pi-a", "harness": "pi", "cwd": self.cwd},
                    {"id": "pi-b", "harness": "pi", "cwd": self.cwd},
                ],
                coordination={"dispatch": "broadcast"},
            )
        )
        self.assertEqual([participant.id for participant in parsed.participants], ["pi-a", "pi-b"])

    def test_rejects_duplicate_participant_ids(self) -> None:
        with self.assertRaisesRegex(ValidationError, "ids must be unique"):
            RunRequest.from_dict(
                self.request(
                    participants=[
                        {"id": "same", "harness": "pi", "cwd": self.cwd},
                        {"id": "same", "harness": "codex", "cwd": self.cwd},
                    ],
                    coordination={"dispatch": "broadcast"},
                )
            )

    def test_split_requires_a_task_per_participant(self) -> None:
        with self.assertRaisesRegex(ValidationError, "split dispatch requires"):
            RunRequest.from_dict(
                self.request(
                    participants=[
                        {"id": "a", "harness": "pi", "cwd": self.cwd, "task": "A"},
                        {"id": "b", "harness": "codex", "cwd": self.cwd},
                    ],
                    coordination={"dispatch": "split"},
                )
            )

    def test_rejects_shared_concurrent_write_directory(self) -> None:
        with self.assertRaisesRegex(ValidationError, "non-overlapping working directories"):
            RunRequest.from_dict(
                self.request(
                    mode="delegate",
                    participants=[
                        {
                            "id": "a",
                            "harness": "pi",
                            "cwd": self.cwd,
                            "tools": "write",
                            "task": "Edit A",
                        },
                        {
                            "id": "b",
                            "harness": "codex",
                            "cwd": self.cwd,
                            "tools": "write",
                            "task": "Edit B",
                        },
                    ],
                    coordination={"dispatch": "split"},
                )
            )

        nested = Path(self.cwd) / "nested"
        nested.mkdir()
        with self.assertRaisesRegex(ValidationError, "non-overlapping working directories"):
            RunRequest.from_dict(
                self.request(
                    mode="delegate",
                    participants=[
                        {
                            "id": "a",
                            "harness": "pi",
                            "cwd": self.cwd,
                            "tools": "write",
                            "task": "Edit A",
                        },
                        {
                            "id": "b",
                            "harness": "codex",
                            "cwd": str(nested),
                            "tools": "write",
                            "task": "Edit B",
                        },
                    ],
                    coordination={"dispatch": "split"},
                )
            )

    def test_rejects_write_broadcast(self) -> None:
        other = Path(self.cwd) / "other"
        other.mkdir()
        with self.assertRaisesRegex(ValidationError, "broadcast dispatch is read-only"):
            RunRequest.from_dict(
                self.request(
                    mode="delegate",
                    participants=[
                        {"id": "a", "harness": "pi", "cwd": self.cwd, "tools": "write"},
                        {"id": "b", "harness": "codex", "cwd": str(other), "tools": "write"},
                    ],
                    coordination={"dispatch": "broadcast"},
                )
            )

    def test_provided_position_requires_text_and_is_not_independent(self) -> None:
        with self.assertRaisesRegex(ValidationError, "driver_position_text"):
            RunRequest.from_dict(self.request(driver_position="provided"))
        parsed = RunRequest.from_dict(
            self.request(driver_position="provided", driver_position_text="Use B.")
        )
        self.assertFalse(parsed.coordination.independent_first)
        with self.assertRaisesRegex(ValidationError, "contradicts driver_position=provided"):
            RunRequest.from_dict(
                self.request(
                    driver_position="provided",
                    driver_position_text="Use B.",
                    coordination={"independent_first": True},
                )
            )

    def test_participant_id_cannot_escape_state_directory(self) -> None:
        with self.assertRaisesRegex(ValidationError, "participant.id"):
            RunRequest.from_dict(
                self.request(
                    participants=[
                        {"id": "../../escape", "harness": "pi", "cwd": self.cwd}
                    ]
                )
            )

    def test_unknown_fields_fail_instead_of_becoming_dead_configuration(self) -> None:
        with self.assertRaisesRegex(ValidationError, "unknown coordination fields"):
            RunRequest.from_dict(
                self.request(coordination={"cross_review": True})
            )

        with self.assertRaisesRegex(ValidationError, "unknown participant fields"):
            RunRequest.from_dict(
                self.request(
                    participants=[
                        {
                            "id": "pi-a",
                            "harness": "pi",
                            "cwd": self.cwd,
                            "profile": "hidden-magic",
                        }
                    ]
                )
            )

        # A misplaced field names where it belongs: a driver that deleted it instead
        # inherited the default timeout and lost a turn.
        with self.assertRaisesRegex(ValidationError, "timeout_seconds is a request-level field"):
            RunRequest.from_dict(
                self.request(
                    participants=[
                        {"id": "pi-a", "harness": "pi", "cwd": self.cwd, "timeout_seconds": 60}
                    ]
                )
            )

    def test_boolean_and_version_fields_are_not_coerced(self) -> None:
        with self.assertRaisesRegex(ValidationError, "must be a boolean"):
            RunRequest.from_dict(
                self.request(coordination={"independent_first": "false"})
            )
        with self.assertRaisesRegex(ValidationError, "unsupported request version"):
            RunRequest.from_dict(self.request(version=True))
        with self.assertRaisesRegex(ValidationError, "cwd must be a string"):
            RunRequest.from_dict(
                self.request(
                    participants=[{"id": "pi-a", "harness": "pi", "cwd": 42}]
                )
            )
        with self.assertRaisesRegex(ValidationError, "canonical UUID"):
            RunRequest.from_dict(
                self.request(parent_run_id="not-a-uuid", depth=1)
            )


class RequestWarningTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.cwd = self.temporary.name

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def codes(self, **updates) -> list[str]:
        value = {
            "version": 1,
            "mode": "consult",
            "task": "Find the strongest flaw in this design.",
            "origin_harness": "claude",
            "participants": [{"id": "codex-a", "harness": "codex", "cwd": self.cwd}],
            "driver_prediction": "The cache invalidation path is the weak point.",
        }
        value.update(updates)
        return [warning["code"] for warning in request_warnings(RunRequest.from_dict(value))]

    def test_each_lint_fires_on_its_pattern_and_clears_with_its_remedy(self) -> None:
        pis = [{"id": f"pi-{index}", "harness": "pi", "cwd": self.cwd} for index in range(6)]
        web_task = "Verify the cited URLs in docs/design.md support its claims."
        cases = [
            # (lint, request that triggers it, the same request after its remedy)
            (
                "delegate-without-acceptance-criteria",
                {"mode": "delegate", "out_of_scope": ["No API changes"]},
                {"mode": "delegate", "out_of_scope": ["No API changes"],
                 "acceptance_criteria": ["unittest passes"]},
            ),
            (
                "delegate-without-out-of-scope",
                {"mode": "delegate", "acceptance_criteria": ["unittest passes"]},
                {"mode": "delegate", "acceptance_criteria": ["unittest passes"],
                 "out_of_scope": ["No API changes"]},
            ),
            (
                "persona-cue",
                {"task": "You are a world-class engineer. Review this."},
                {"task": "Check specifically for lost-update races."},
            ),
            (
                "position-in-withheld-task",
                {"task": "I think option B is right. Which option is best?"},
                {"task": "I think option B is right. Critique that.",
                 "driver_position": "provided", "driver_position_text": "Option B."},
            ),
            ("no-driver-prediction", {"driver_prediction": None}, {}),
            (
                "scope-lacks-web",
                {"task": web_task},
                {"task": web_task, "participants": [
                    {"id": "claude-w", "harness": "claude", "cwd": self.cwd, "tools": "read+web"}]},
            ),
            (
                "wide-fan-out",
                {"participants": pis, "coordination": {"dispatch": "broadcast"}},
                {"participants": pis[:5], "coordination": {"dispatch": "broadcast"}},
            ),
        ]
        self.assertEqual(self.codes(), [], "the well-formed base request must be clean")
        for code, triggering, remedied in cases:
            with self.subTest(code):
                self.assertIn(code, self.codes(**triggering))
                self.assertNotIn(code, self.codes(**remedied))

    def test_filesystem_lints_follow_what_the_peer_can_actually_reach(self) -> None:
        outside = Path(self.cwd).parent / f"{Path(self.cwd).name}-shared"
        outside.mkdir()
        self.addCleanup(outside.rmdir)
        claude = {"id": "claude-a", "harness": "claude", "cwd": self.cwd, "tools": "read"}
        for reference in (str(outside / "spec.md"), f"../{outside.name}/spec.md"):
            with self.subTest(reference):
                self.assertIn(
                    "context-ref-outside-cwd",
                    self.codes(participants=[claude], context_refs=[reference]),
                )
                self.assertNotIn(
                    "context-ref-outside-cwd",
                    self.codes(
                        participants=[claude | {"params": {"add_dirs": [str(outside)]}}],
                        context_refs=[reference],
                    ),
                )
        self.assertNotIn(
            "context-ref-outside-cwd",
            self.codes(participants=[claude], context_refs=["docs/design.md"]),
        )

        (Path(self.cwd) / ".git").mkdir()
        writer = {"id": "codex-w", "harness": "codex", "cwd": self.cwd, "tools": "write"}
        contract = {"acceptance_criteria": ["tests pass"], "out_of_scope": ["no API changes"]}
        self.assertEqual(
            self.codes(mode="delegate", participants=[writer], **contract),
            ["write-in-main-checkout"],
        )
        (Path(self.cwd) / ".git").rmdir()
        (Path(self.cwd) / ".git").write_text("gitdir: /elsewhere/.git/worktrees/w\n")
        self.assertEqual(self.codes(mode="delegate", participants=[writer], **contract), [])

if __name__ == "__main__":
    unittest.main()
