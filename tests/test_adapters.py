from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from scripts.riff_core.adapters.claude import ClaudeAdapter
from scripts.riff_core.adapters.codex import CodexAdapter
from scripts.riff_core.adapters.hermes import HermesAdapter
from scripts.riff_core.adapters.pi import PiAdapter
from scripts.riff_core.models import ParticipantSpec, TurnRequest, ValidationError


class AdapterCommandTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.cwd = self.root / "repo"
        self.cwd.mkdir()

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def turn(
        self,
        harness: str,
        *,
        tools="none",
        model=None,
        provider=None,
        params=None,
        reply=False,
    ) -> TurnRequest:
        participant = ParticipantSpec(
            id=f"{harness}-a",
            harness=harness,
            cwd=str(self.cwd),
            tools=tools,
            model=model,
            provider=provider,
            params=params or {},
        )
        return TurnRequest(
            run_id="run",
            turn_id="turn",
            participant=participant,
            prompt="Inspect independently.",
            timeout_seconds=10,
            artifact_path=str(self.root / "artifact.md"),
            log_path=str(self.root / "turn.log"),
            state_path=str(self.root / "native"),
            depth=0,
            is_reply=reply,
            native_session_id="native-session" if reply else None,
        )

    def test_claude_maps_model_effort_and_read_tools(self) -> None:
        command, _, _ = ClaudeAdapter().build_command(
            self.turn(
                "claude",
                tools="read",
                model="sonnet",
                provider="bedrock",
                params={"effort": "high"},
            )
        )
        self.assertIn("--session-id", command)
        self.assertEqual(command[command.index("--model") + 1], "sonnet")
        self.assertEqual(command[command.index("--effort") + 1], "high")
        self.assertEqual(command[command.index("--tools") + 1], "Read,Grep,Glob")
        self.assertNotIn("--allowedTools", command)  # read tools need no pre-approval

    def test_claude_read_plus_web_scope_adds_and_preapproves_web_tools_only(self) -> None:
        command, _, _ = ClaudeAdapter().build_command(
            self.turn("claude", tools="read+web")
        )
        self.assertEqual(
            command[command.index("--tools") + 1],
            "Read,Grep,Glob,WebSearch,WebFetch",
        )
        self.assertEqual(command[command.index("--permission-mode") + 1], "dontAsk")
        # dontAsk denies an available tool unless it is pre-approved.
        self.assertEqual(command[command.index("--allowedTools") + 1], "WebSearch,WebFetch")

    def test_claude_write_peer_may_run_only_listed_command_prefixes(self) -> None:
        command, _, _ = ClaudeAdapter().build_command(
            self.turn(
                "claude",
                tools="write",
                params={"allowed_commands": ["uv run pytest", "ruff check"]},
            )
        )
        self.assertEqual(
            command[command.index("--allowedTools") + 1],
            "Bash(uv run pytest:*),Bash(ruff check:*)",
        )
        with self.assertRaisesRegex(ValidationError, "requires tools=write"):
            ClaudeAdapter().build_command(
                self.turn("claude", tools="read", params={"allowed_commands": ["pytest"]})
            )
        with self.assertRaisesRegex(ValidationError, "plain command prefixes"):
            ClaudeAdapter().build_command(
                self.turn("claude", tools="write", params={"allowed_commands": ["rm *"]})
            )

    def test_claude_add_dirs_extends_readable_roots(self) -> None:
        shared = self.root / "shared"
        shared.mkdir()
        command, _, _ = ClaudeAdapter().build_command(
            self.turn("claude", tools="read", params={"add_dirs": [str(shared)]})
        )
        self.assertEqual(command[command.index("--add-dir") + 1], str(shared.resolve()))
        with self.assertRaisesRegex(ValidationError, "does not exist"):
            ClaudeAdapter().build_command(
                self.turn("claude", tools="read", params={"add_dirs": [str(self.root / "no")]})
            )

    def test_unsupported_harnesses_reject_read_plus_web(self) -> None:
        for harness in ("codex", "pi", "hermes"):
            with self.assertRaisesRegex(ValidationError, "read\\+web"):
                {
                    "codex": CodexAdapter,
                    "pi": PiAdapter,
                    "hermes": HermesAdapter,
                }[harness]().build_command(self.turn(harness, tools="read+web"))

    def test_codex_uses_explicit_resume_and_reasoning_effort(self) -> None:
        command = CodexAdapter().build_command(
            self.turn(
                "codex",
                model="gpt-5",
                params={"reasoning_effort": "xhigh"},
                reply=True,
            )
        )
        self.assertIn("native-session", command)
        self.assertNotIn("--last", command)
        self.assertIn('model_reasoning_effort="xhigh"', command)
        self.assertEqual(command[command.index("--model") + 1], "gpt-5")

    def test_pi_uses_rpc_settlement_and_explicit_session(self) -> None:
        command, _, session_id = PiAdapter().build_command(
            self.turn(
                "pi",
                tools="read",
                model="qwen",
                provider="llama.cpp",
                params={"thinking": "high"},
            )
        )
        self.assertEqual(command[command.index("--mode") + 1], "rpc")
        self.assertEqual(command[command.index("--session-id") + 1], session_id)
        self.assertEqual(command[command.index("--thinking") + 1], "high")
        self.assertEqual(command[command.index("--tools") + 1], "read,grep,find,ls")
        self.assertEqual(command[command.index("--model") + 1], "qwen")
        self.assertEqual(command[command.index("--provider") + 1], "llama.cpp")

    def test_hermes_maps_model_and_rejects_write_until_enforceable(self) -> None:
        command = HermesAdapter().build_command(
            self.turn("hermes", tools="read", model="qwen", provider="custom")
        )
        self.assertEqual(command[command.index("--model") + 1], "qwen")
        self.assertEqual(command[command.index("--provider") + 1], "custom")
        with self.assertRaisesRegex(ValidationError, "write delegation is disabled"):
            HermesAdapter().build_command(self.turn("hermes", tools="write"))

    def test_unknown_adapter_params_fail_closed(self) -> None:
        with self.assertRaisesRegex(ValidationError, "does not support"):
            PiAdapter().build_command(self.turn("pi", params={"mystery": True}))

    def test_adapter_param_types_fail_closed(self) -> None:
        cases = (
            (ClaudeAdapter(), self.turn("claude", params={"effort": 4})),
            (CodexAdapter(), self.turn("codex", params={"skip_git_repo_check": "yes"})),
            (PiAdapter(), self.turn("pi", params={"context_files": "false"})),
            (HermesAdapter(), self.turn("hermes", params={"max_turns": True})),
        )
        for adapter, turn in cases:
            with self.subTest(adapter=adapter.name), self.assertRaises(ValidationError):
                adapter.validate(turn)


if __name__ == "__main__":
    unittest.main()
