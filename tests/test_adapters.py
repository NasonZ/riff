from __future__ import annotations

import os
import sqlite3
import tempfile
import tomllib
import unittest
from pathlib import Path
from unittest import mock

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
        # Command construction must not depend on which harnesses are installed.
        environment = mock.patch.dict(
            os.environ,
            {
                f"RIFF_{harness.upper()}_BIN": str(self.root / "bin" / harness)
                for harness in ("claude", "codex", "pi", "hermes")
            },
        )
        environment.start()
        self.addCleanup(environment.stop)

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
        with self.assertRaises(ValidationError):
            ClaudeAdapter().build_command(
                self.turn("claude", tools="write", params={
                    "permission_mode": "bypassPermissions", "allowed_commands": ["pytest"],
                })
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
        for harness in ("pi", "hermes"):
            with self.assertRaisesRegex(ValidationError, "read\\+web"):
                {
                    "pi": PiAdapter,
                    "hermes": HermesAdapter,
                }[harness]().build_command(self.turn(harness, tools="read+web"))

    def test_adapters_locate_only_an_unambiguous_native_session_file(self) -> None:
        session = "0f8e1d2c-3b4a-4c5d-8e6f-7a8b9c0d1e2f"
        claude_home = self.root / "claude-config"
        claude_file = claude_home / "projects" / "-repo" / f"{session}.jsonl"
        state = self.root / "state"
        rollout = state / "codex-home" / "sessions" / "2026" / "10" / "08"
        rollout = rollout / f"rollout-2026-10-08T01-02-03-{session}.jsonl"
        for path in (claude_file, rollout):
            path.parent.mkdir(parents=True)
            path.write_text("{}\n")
        with mock.patch.dict(
            os.environ, {"CLAUDE_CONFIG_DIR": str(claude_home), "RIFF_STATE_DIR": str(state)}
        ):
            self.assertEqual(ClaudeAdapter().native_transcript(session, None), claude_file)
            self.assertEqual(
                CodexAdapter().native_transcript(session, None).resolve(), rollout.resolve()
            )
            # The same session under two project directories is ambiguous, not a guess.
            duplicate = claude_home / "projects" / "-other" / f"{session}.jsonl"
            duplicate.parent.mkdir()
            duplicate.write_text("{}\n")
            self.assertIsNone(ClaudeAdapter().native_transcript(session, None))
        self.assertEqual(PiAdapter().native_transcript(session, str(rollout)), rollout)
        self.assertIsNone(HermesAdapter().native_transcript(session, None))

        hermes_home = self.root / "hermes"
        hermes_home.mkdir()
        with sqlite3.connect(hermes_home / "state.db") as database:
            database.execute("CREATE TABLE messages (id INTEGER PRIMARY KEY, session_id TEXT)")
            database.executemany(
                "INSERT INTO messages (session_id) VALUES (?)", [("h1",), ("other",), ("h1",)]
            )
        with mock.patch.dict(os.environ, {"HERMES_HOME": str(hermes_home)}):
            position = HermesAdapter().native_position("h1", None)
            self.assertEqual((position["session_id"], position["last_message_id"]), ("h1", 3))
            self.assertEqual(HermesAdapter().native_position("new", None)["last_message_id"], 0)

    def test_codex_turn_runs_against_a_home_without_mcp_servers(self) -> None:
        # No per-run flag drops a configured server, so the sanitized CODEX_HOME
        # is what makes the scope bound the peer's tools. Verified live: with it,
        # the peer answers ABSENT for an MCP tool it otherwise calls.
        from scripts.riff_core.adapters import codex as codex_module

        real = self.root / "codex-real"
        real.mkdir(parents=True, exist_ok=True)
        (real / "config.toml").write_text(
            'model = "gpt-6-astra"\n'
            "\n[mcp_servers.firecrawl-local]\n"
            'command = "npx"\n'
            "\n[mcp_servers.firecrawl-local.env]\n"
            'KEY = "x"\n'
            "\n[projects.\"/tmp\"]\n"
            'trust_level = "trusted"\n'
        )
        (real / "auth.json").write_text("{}")
        state = self.root / "state"
        (state / "codex-home").mkdir(parents=True)
        (state / "codex-home").chmod(0o755)
        with mock.patch.dict(
            os.environ, {"CODEX_HOME": str(real), "RIFF_STATE_DIR": str(state)}
        ):
            home = codex_module.codex_home(self.turn("codex"))
            config = (home / "config.toml").read_text()
        self.assertNotIn("mcp_servers", tomllib.loads(config))
        # everything that is not an MCP server survives, including later tables
        self.assertIn('model = "gpt-6-astra"', config)
        self.assertIn('trust_level = "trusted"', config)
        self.assertTrue((home / "auth.json").exists(), "auth must still resolve")
        self.assertEqual(home.parent, state.resolve(), "the home lives beside riff state")
        if os.name == "posix":
            self.assertEqual(home.stat().st_mode & 0o077, 0)

        for source in (
            'mcp_servers = { example = { command = "unused" } }\n',
            '["mcp_servers"."example"]\ncommand = "unused"\n',
        ):
            with self.subTest(config=source), mock.patch.dict(
                os.environ, {"CODEX_HOME": str(real), "RIFF_STATE_DIR": str(state)}
            ):
                (real / "config.toml").write_text(source)
                with self.assertRaises(ValidationError):
                    codex_module.codex_home(self.turn("codex"))
                self.assertEqual((home / "config.toml").read_text(), config)

    def test_codex_pins_web_search_in_both_directions(self) -> None:
        # codex-cli 0.160.0 enables web search by default, so a scope that does
        # not name the web has to turn it off explicitly; otherwise `read`
        # silently grants outbound network and the scope misreports authority.
        def web_setting(tools: str) -> str:
            command = CodexAdapter().build_command(self.turn("codex", tools=tools))
            return command[command.index("-c") + 1] if "-c" in command else ""

        self.assertEqual(web_setting("read+web"), 'web_search="live"')
        for scope in ("none", "read", "write"):
            self.assertEqual(web_setting(scope), 'web_search="disabled"')
        self.assertIn(
            "read+web", CodexAdapter().capability()["tool_scopes"]
        )
        # read+web grants no write authority: the sandbox stays read-only
        command = CodexAdapter().build_command(self.turn("codex", tools="read+web"))
        self.assertEqual(command[command.index("--sandbox") + 1], "read-only")

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
        with self.assertRaisesRegex(ValidationError, "provider requires model"):
            PiAdapter().build_command(self.turn("pi", provider="llama.cpp"))

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
