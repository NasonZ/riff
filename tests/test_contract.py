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

    def test_provided_position_requires_text(self) -> None:
        with self.assertRaisesRegex(ValidationError, "driver_position_text"):
            RunRequest.from_dict(self.request(driver_position="provided"))

    def test_provided_position_turns_off_independent_first(self) -> None:
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

    def test_participant_timeout_points_to_the_request_field(self) -> None:
        with self.assertRaisesRegex(ValidationError, "timeout_seconds is a request-level field"):
            RunRequest.from_dict(
                self.request(
                    participants=[
                        {"id": "pi-a", "harness": "pi", "cwd": self.cwd, "timeout_seconds": 60}
                    ]
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

    def test_well_formed_consult_has_no_warnings(self) -> None:
        self.assertEqual(self.codes(), [])

    def test_delegate_without_contract_is_flagged(self) -> None:
        self.assertEqual(
            self.codes(mode="delegate", task="Refactor the parser."),
            ["delegate-without-acceptance-criteria", "delegate-without-out-of-scope"],
        )
        self.assertEqual(
            self.codes(
                mode="delegate",
                task="Refactor the parser.",
                acceptance_criteria=["python -m unittest passes"],
                out_of_scope=["Do not change the public API"],
            ),
            [],
        )

    def test_persona_wording_is_flagged_but_focused_attention_is_not(self) -> None:
        self.assertIn("persona-cue", self.codes(task="Act as Aristotle and judge this plan."))
        self.assertIn(
            "persona-cue", self.codes(task="You are a world-class engineer. Review this.")
        )
        self.assertNotIn(
            "persona-cue", self.codes(task="Check specifically for lost-update races.")
        )

    def test_driver_view_inside_a_withheld_task_is_flagged(self) -> None:
        self.assertIn(
            "position-in-withheld-task",
            self.codes(task="I think option B is right. Which option is best?"),
        )
        self.assertNotIn(
            "position-in-withheld-task",
            self.codes(
                task="I think option B is right. Critique that.",
                driver_position="provided",
                driver_position_text="Option B, because it keeps one writer.",
            ),
        )

    def test_independent_first_run_asks_for_a_prediction(self) -> None:
        self.assertIn("no-driver-prediction", self.codes(driver_prediction=None))

    def test_claude_context_ref_outside_cwd_is_flagged_unless_added(self) -> None:
        outside = Path(self.cwd).parent / f"{Path(self.cwd).name}-shared"
        outside.mkdir()
        self.addCleanup(outside.rmdir)
        reference = str(outside / "spec.md")
        claude = {"id": "claude-a", "harness": "claude", "cwd": self.cwd, "tools": "read"}
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
        relative = f"../{outside.name}/spec.md"
        self.assertIn(
            "context-ref-outside-cwd",
            self.codes(participants=[claude], context_refs=[relative]),
        )
        self.assertNotIn(
            "context-ref-outside-cwd",
            self.codes(participants=[claude], context_refs=["docs/design.md"]),
        )

    def test_write_peer_in_a_main_checkout_is_flagged(self) -> None:
        (Path(self.cwd) / ".git").mkdir()
        writer = {"id": "codex-w", "harness": "codex", "cwd": self.cwd, "tools": "write"}
        codes = self.codes(
            mode="delegate",
            participants=[writer],
            acceptance_criteria=["tests pass"],
            out_of_scope=["no API changes"],
        )
        self.assertEqual(codes, ["write-in-main-checkout"])

    def test_web_verification_task_without_web_scope_is_flagged(self) -> None:
        task = "Verify the cited URLs in docs/telem_refresh.md support its claims."
        self.assertIn("scope-lacks-web", self.codes(task=task))
        web_peer = {"id": "claude-w", "harness": "claude", "cwd": self.cwd, "tools": "read+web"}
        self.assertNotIn("scope-lacks-web", self.codes(task=task, participants=[web_peer]))

    def test_wide_fan_out_is_flagged(self) -> None:
        participants = [
            {"id": f"pi-{index}", "harness": "pi", "cwd": self.cwd} for index in range(6)
        ]
        self.assertIn(
            "wide-fan-out",
            self.codes(participants=participants, coordination={"dispatch": "broadcast"}),
        )


if __name__ == "__main__":
    unittest.main()
