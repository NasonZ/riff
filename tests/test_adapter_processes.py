from __future__ import annotations

import json
import os
import tempfile
import textwrap
import unittest
from pathlib import Path
from unittest.mock import patch

from scripts.riff_core.adapters.claude import ClaudeAdapter
from scripts.riff_core.adapters.codex import CodexAdapter
from scripts.riff_core.adapters.hermes import HermesAdapter
from scripts.riff_core.adapters.pi import PiAdapter
from scripts.riff_core.models import ParticipantSpec, TurnRequest


class AdapterProcessTests(unittest.TestCase):
    """Exercise process parsing and native-session continuation without model calls."""

    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.cwd = self.root / "repo"
        self.cwd.mkdir()
        environment = patch.dict(
            os.environ,
            {
                "RIFF_STATE_DIR": str(self.root / "state"),
                "CODEX_HOME": str(self.root / "codex"),
            },
        )
        environment.start()
        self.addCleanup(environment.stop)

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def executable(self, name: str, source: str) -> str:
        path = self.root / name
        path.write_text("#!/usr/bin/env python3\n" + textwrap.dedent(source))
        path.chmod(0o755)
        return str(path)

    def turn(
        self,
        harness: str,
        *,
        suffix: str,
        reply: bool = False,
        session_id: str | None = None,
        session_ref: str | None = None,
    ) -> TurnRequest:
        return TurnRequest(
            run_id="run",
            turn_id=f"turn-{suffix}",
            participant=ParticipantSpec(
                id=f"{harness}-a", harness=harness, cwd=str(self.cwd)
            ),
            prompt="Give an independent answer.",
            timeout_seconds=5,
            artifact_path=str(self.root / f"{suffix}.md"),
            log_path=str(self.root / f"{suffix}.log"),
            state_path=str(self.root / "native" / harness),
            depth=0,
            is_reply=reply,
            native_session_id=session_id,
            native_session_ref=session_ref,
        )

    def test_claude_start_and_reply_preserve_session(self) -> None:
        fake = self.executable(
            "claude",
            """
            import json, sys
            args = sys.argv[1:]
            flag = '--resume' if '--resume' in args else '--session-id'
            session_id = args[args.index(flag) + 1]
            print(json.dumps({'result': 'claude artifact', 'session_id': session_id,
                              'model': 'fake-claude', 'usage': {'output_tokens': 3}}))
            """,
        )
        adapter = ClaudeAdapter()
        with patch.dict(os.environ, {"RIFF_CLAUDE_BIN": fake}):
            started = adapter.start(self.turn("claude", suffix="claude-start"))
            replied = adapter.reply(
                self.turn(
                    "claude",
                    suffix="claude-reply",
                    reply=True,
                    session_id=started.native_session_id,
                )
            )
        self.assertTrue(started.ok)
        self.assertTrue(replied.ok)
        self.assertEqual(replied.native_session_id, started.native_session_id)

    def test_claude_timeout_preserves_preallocated_session_id(self) -> None:
        fake = self.executable(
            "slow-claude",
            """
            import time
            time.sleep(5)
            """,
        )
        turn = self.turn("claude", suffix="claude-timeout")
        turn = TurnRequest(**{**turn.__dict__, "timeout_seconds": 1})
        with patch.dict(os.environ, {"RIFF_CLAUDE_BIN": fake}):
            result = ClaudeAdapter().start(turn)
        self.assertFalse(result.ok)
        self.assertEqual(result.error_type, "timeout")
        self.assertIsNotNone(result.native_session_id)

    def test_claude_is_error_payload_is_not_reported_as_success(self) -> None:
        fake = self.executable(
            "error-claude",
            """
            import json, sys
            args = sys.argv[1:]
            flag = '--resume' if '--resume' in args else '--session-id'
            print(json.dumps({'is_error': True, 'subtype': 'error_during_execution',
                              'result': 'seeded Claude failure',
                              'session_id': args[args.index(flag) + 1]}))
            """,
        )
        with patch.dict(os.environ, {"RIFF_CLAUDE_BIN": fake}):
            result = ClaudeAdapter().start(self.turn("claude", suffix="claude-error"))
        self.assertFalse(result.ok)
        self.assertEqual(result.error_type, "model")
        self.assertEqual(result.error, "seeded Claude failure")

    def test_claude_usage_limit_is_classified_from_the_json_payload(self) -> None:
        # Shape of the field failure: exit 1 with the reason only inside the payload.
        fake = self.executable(
            "limited-claude",
            """
            import json, sys
            args = sys.argv[1:]
            print(json.dumps({'type': 'result', 'is_error': True, 'api_error_status': 429,
                              'result': "You've hit your session limit · resets 2:50am",
                              'total_cost_usd': 0,
                              'session_id': args[args.index('--session-id') + 1]}))
            sys.exit(1)
            """,
        )
        with patch.dict(os.environ, {"RIFF_CLAUDE_BIN": fake}):
            result = ClaudeAdapter().start(self.turn("claude", suffix="claude-limit"))
        self.assertFalse(result.ok)
        self.assertEqual(result.error_type, "rate_limit")
        self.assertIn("session limit", result.error)
        self.assertEqual(Path(result.artifact_file).read_text(), "")
        self.assertEqual(result.adapter_metadata["cost_usd"], 0)

    def test_cli_detach_then_wait_follows_a_real_process(self) -> None:
        import json
        import subprocess
        import sys

        fake = self.executable(
            "slow-claude",
            """
            import json, sys, time
            args = sys.argv[1:]
            sys.stdin.read()
            time.sleep(2)
            print(json.dumps({'result': 'detached artifact',
                              'session_id': args[args.index('--session-id') + 1]}))
            """,
        )
        script = str(Path(__file__).resolve().parent.parent / "scripts" / "riff.py")
        request = self.root / "request.json"
        request.write_text(json.dumps({
            "version": 1, "mode": "consult", "task": "Review.", "origin_harness": "codex",
            "participants": [{"id": "claude-a", "harness": "claude", "cwd": str(self.cwd), "tools": "read"}],
            "driver_prediction": "Nothing surprising.",
        }))
        env = {**os.environ, "RIFF_CLAUDE_BIN": fake}
        state = str(self.root / "state")
        # Exercise upgrades from directories created with a permissive umask.
        for name in ("runs", "detached"):
            directory = Path(state) / name
            directory.mkdir(parents=True, exist_ok=True)
            directory.chmod(0o755)

        def riff(*args):
            done = subprocess.run([sys.executable, script, "--state-dir", state, *args],
                                  capture_output=True, text=True, env=env, timeout=60, check=False)
            self.assertEqual(done.returncode, 0, done.stderr)
            return json.loads(done.stdout)

        invalid = subprocess.run(
            [sys.executable, script, "--state-dir", state, "run", "--request", str(request),
             "--run-id", "../escaped", "--detach"],
            capture_output=True, text=True, env=env, timeout=10, check=False,
        )
        self.assertNotEqual(invalid.returncode, 0)
        self.assertFalse((Path(state) / "escaped.request.json").exists())

        detached = riff("run", "--request", str(request), "--detach")
        self.assertEqual(detached["status"], "running")
        waited = riff("wait", "--run-id", detached["run_id"], "--timeout-seconds", "30")
        self.assertEqual(waited["status"], "settled")
        self.assertEqual(Path(waited["participants"][0]["artifact_file"]).read_text(), "detached artifact")
        if os.name == "posix":
            for name in ("runs", "detached"):
                self.assertEqual((Path(state) / name).stat().st_mode & 0o077, 0)

    def test_codex_auth_failure_is_classified(self) -> None:
        fake = self.executable(
            "unauthorized-codex",
            """
            import json, sys
            print(json.dumps({'type': 'thread.started', 'thread_id': 'auth-thread'}))
            print(json.dumps({'type': 'error', 'message': 'Reconnecting... 1/5'}))
            print(json.dumps({'type': 'turn.failed', 'error': {'message':
                'unexpected status 401 Unauthorized: Incorrect API key provided'}}))
            sys.exit(1)
            """,
        )
        with patch.dict(os.environ, {"RIFF_CODEX_BIN": fake}):
            result = CodexAdapter().start(self.turn("codex", suffix="codex-auth"))
        self.assertFalse(result.ok)
        self.assertEqual(result.error_type, "auth")
        self.assertEqual(
            result.error, "unexpected status 401 Unauthorized: Incorrect API key provided"
        )

    def test_codex_start_and_reply_parse_jsonl_and_artifact(self) -> None:
        fake = self.executable(
            "codex",
            """
            import json, pathlib, sys
            args = sys.argv[1:]
            output = pathlib.Path(args[args.index('-o') + 1])
            output.write_text('codex artifact')
            print(json.dumps({'type': 'thread.started', 'thread_id': 'codex-session'}))
            # A transient error Codex retried does not fail a completed turn.
            print(json.dumps({'type': 'error', 'message': 'Reconnecting... 1/5 (stream closed)'}))
            print(json.dumps({'type': 'turn.completed', 'usage': {'output_tokens': 7}}))
            """,
        )
        adapter = CodexAdapter()
        with patch.dict(os.environ, {"RIFF_CODEX_BIN": fake}):
            started = adapter.start(self.turn("codex", suffix="codex-start"))
            replied = adapter.reply(
                self.turn(
                    "codex",
                    suffix="codex-reply",
                    reply=True,
                    session_id=started.native_session_id,
                )
            )
        self.assertTrue(started.ok)
        self.assertTrue(replied.ok)
        self.assertEqual(started.native_session_id, "codex-session")
        self.assertEqual(started.usage["output_tokens"], 7)

    def test_codex_requires_settlement_and_preserves_a_timed_out_thread(self) -> None:
        incomplete = self.executable(
            "incomplete-codex",
            """
            import json, pathlib, sys
            args = sys.argv[1:]
            pathlib.Path(args[args.index('-o') + 1]).write_text('partial artifact')
            print(json.dumps({'type': 'thread.started', 'thread_id': 'incomplete-thread'}))
            """,
        )
        with patch.dict(os.environ, {"RIFF_CODEX_BIN": incomplete}):
            result = CodexAdapter().start(self.turn("codex", suffix="codex-incomplete"))
        self.assertFalse(result.ok)
        self.assertEqual(result.error_type, "transport")
        self.assertEqual(result.native_session_id, "incomplete-thread")

        timed = self.executable(
            "timed-codex",
            """
            import json, pathlib, sys, time
            args = sys.argv[1:]
            pathlib.Path(args[args.index('-o') + 1]).write_text('partial artifact')
            print(json.dumps({'type': 'thread.started', 'thread_id': 'timed-thread'}),
                  flush=True)
            time.sleep(5)
            """,
        )
        turn = self.turn("codex", suffix="codex-timeout")
        turn = TurnRequest(**{**turn.__dict__, "timeout_seconds": 1})
        with patch.dict(os.environ, {"RIFF_CODEX_BIN": timed}):
            result = CodexAdapter().start(turn)
        self.assertFalse(result.ok)
        self.assertEqual(result.error_type, "timeout")
        self.assertEqual(result.native_session_id, "timed-thread")

    def test_pi_waits_for_agent_settled_and_resumes_session_file(self) -> None:
        fake = self.executable(
            "pi",
            """
            import json, pathlib, sys
            args = sys.argv[1:]
            sessions = pathlib.Path(args[args.index('--session-dir') + 1])
            sessions.mkdir(parents=True, exist_ok=True)
            if '--session-id' in args:
                session_id = args[args.index('--session-id') + 1]
                (sessions / f'fake_{session_id}.jsonl').write_text('{}\\n')
            else:
                session = pathlib.Path(args[args.index('--session') + 1])
                session_id = session.stem.split('_')[-1]
            json.loads(sys.stdin.readline())
            # Like real Pi: the closing events can share one pipe write, and the
            # process stays alive for further commands until stdin closes.
            sys.stdout.write(json.dumps({'type': 'message_end', 'message': {
                'role': 'assistant', 'content': [{'type': 'text', 'text': 'pi artifact'}],
                'responseModel': 'fake-pi', 'usage': {'output': 4}}}) + '\\n'
                + json.dumps({'type': 'agent_settled'}) + '\\n')
            sys.stdout.flush()
            sys.stdin.read()
            """,
        )
        adapter = PiAdapter()
        with patch.dict(os.environ, {"RIFF_PI_BIN": fake}):
            started = adapter.start(self.turn("pi", suffix="pi-start"))
            replied = adapter.reply(
                self.turn(
                    "pi",
                    suffix="pi-reply",
                    reply=True,
                    session_id=started.native_session_id,
                    session_ref=started.native_session_ref,
                )
            )
        self.assertTrue(started.ok)
        self.assertEqual(started.adapter_metadata["settlement"], "agent_settled")
        self.assertTrue(replied.ok)
        self.assertEqual(replied.native_session_id, started.native_session_id)

    def test_pi_drains_large_stderr_while_waiting_for_settlement(self) -> None:
        fake = self.executable(
            "noisy-pi",
            """
            import json, pathlib, sys
            args = sys.argv[1:]
            sessions = pathlib.Path(args[args.index('--session-dir') + 1])
            sessions.mkdir(parents=True, exist_ok=True)
            session_id = args[args.index('--session-id') + 1]
            (sessions / f'fake_{session_id}.jsonl').write_text('{}\\n')
            json.loads(sys.stdin.readline())
            for index in range(12000):
                print(f'noise-{index}', file=sys.stderr)
            print(json.dumps({'type': 'message_end', 'message': {
                'role': 'assistant', 'content': [{'type': 'text', 'text': 'settled'}]}}),
                flush=True)
            print(json.dumps({'type': 'agent_settled'}), flush=True)
            """,
        )
        with patch.dict(os.environ, {"RIFF_PI_BIN": fake}):
            result = PiAdapter().start(self.turn("pi", suffix="pi-noisy"))
        self.assertTrue(result.ok)

    def test_pi_prompt_that_starts_no_run_fails_without_waiting_for_timeout(self) -> None:
        # Pi stays alive after either response, and agent_settled never follows.
        fake = self.executable(
            "idle-pi",
            """
            import json, os, sys
            json.loads(sys.stdin.readline())
            response = json.loads(os.environ['FAKE_PI_RESPONSE'])
            print(json.dumps({'type': 'response', 'command': 'prompt', **response}),
                  flush=True)
            sys.stdin.read()
            """,
        )
        responses = {
            "rejected": {"success": False, "error": "Model not found: fake/missing"},
            "handled": {"success": True, "data": {"disposition": "handled"}},
        }
        for name, response in responses.items():
            with self.subTest(name), patch.dict(
                os.environ, {"RIFF_PI_BIN": fake, "FAKE_PI_RESPONSE": json.dumps(response)}
            ):
                result = PiAdapter().start(self.turn("pi", suffix=f"pi-{name}"))
                self.assertEqual(result.error_type, "transport")
                self.assertLess(result.elapsed_ms, 3000)  # the turn timeout is 5 s

    def test_hermes_start_and_reply_parse_stderr_session(self) -> None:
        fake = self.executable(
            "hermes",
            """
            import sys
            args = sys.argv[1:]
            session_id = args[args.index('--resume') + 1] if '--resume' in args else 'hermes-session'
            print('hermes artifact')
            print(f'session_id: {session_id}', file=sys.stderr)
            """,
        )
        adapter = HermesAdapter()
        with patch.dict(os.environ, {"RIFF_HERMES_BIN": fake}):
            started = adapter.start(self.turn("hermes", suffix="hermes-start"))
            replied = adapter.reply(
                self.turn(
                    "hermes",
                    suffix="hermes-reply",
                    reply=True,
                    session_id=started.native_session_id,
                )
            )
        self.assertTrue(started.ok)
        self.assertTrue(replied.ok)
        self.assertEqual(replied.native_session_id, "hermes-session")


if __name__ == "__main__":
    unittest.main()
