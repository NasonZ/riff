"""Pi JSONL-RPC adapter."""

from __future__ import annotations

import json
import os
import selectors
import shutil
import signal
import subprocess
import time
import uuid
from pathlib import Path
from typing import Any

from ..models import SettledTurn, TurnRequest, ValidationError
from .base import (
    PEER_SYSTEM_NOTE,
    HarnessAdapter,
    child_environment,
    executable,
    require_bool_param,
    require_string_param,
    require_supported_params,
)

READ_TOOLS = "read,grep,find,ls"


class PiAdapter(HarnessAdapter):
    name = "pi"

    def capability(self) -> dict[str, Any]:
        configured = os.environ.get("RIFF_PI_BIN") or "pi"
        available = bool(
            shutil.which(configured)
            if os.sep not in configured
            else Path(configured).is_file()
        )
        return {
            "harness": self.name,
            "available": available,
            "persistent_sessions": True,
            "tool_scopes": ["none", "read", "write"],
            "parameters": ["thinking", "context_files"],
            "settlement": "agent_settled",
        }

    def validate(self, turn: TurnRequest) -> None:
        super().validate(turn)
        require_supported_params(
            self.name, turn.participant.params, {"thinking", "context_files"}
        )
        require_string_param(self.name, turn.participant.params, "thinking")
        require_bool_param(self.name, turn.participant.params, "context_files")
        if turn.participant.tools == "read+web":
            raise ValidationError(
                "pi does not support the read+web tool scope; use read or write"
            )

    def build_command(self, turn: TurnRequest) -> tuple[list[str], dict[str, str], str]:
        self.validate(turn)
        state_path = Path(turn.state_path)
        sessions_dir = state_path / "sessions"
        sessions_dir.mkdir(parents=True, exist_ok=True)
        command = [
            executable("pi", "RIFF_PI_BIN"),
            "--mode",
            "rpc",
            "--session-dir",
            str(sessions_dir),
            "--append-system-prompt",
            PEER_SYSTEM_NOTE,
            "--no-skills",
            "--no-extensions",
            "--no-prompt-templates",
            "--approve",
        ]
        if turn.is_reply:
            if not turn.native_session_id:
                raise ValidationError("pi reply requires a native session id")
            session_ref = turn.native_session_ref or _session_file(
                sessions_dir, turn.native_session_id
            )
            if not session_ref:
                raise ValidationError(
                    f"Pi session not found for {turn.native_session_id}"
                )
            command.extend(["--session", str(session_ref)])
            session_id = turn.native_session_id
        else:
            session_id = str(uuid.uuid4())
            command.extend(["--session-id", session_id, "--name", turn.participant.id])
        if turn.participant.provider:
            command.extend(["--provider", turn.participant.provider])
        if turn.participant.model:
            command.extend(["--model", turn.participant.model])
        thinking = turn.participant.params.get("thinking")
        if thinking:
            command.extend(["--thinking", str(thinking)])
        if turn.participant.params.get("context_files") is False:
            command.append("--no-context-files")
        if turn.participant.tools == "none":
            command.append("--no-tools")
        elif turn.participant.tools == "read":
            command.extend(["--tools", READ_TOOLS])
        else:
            command.extend(["--tools", "read,grep,find,ls,bash,edit,write"])
        environment = child_environment(turn)
        environment["PI_CODING_AGENT_SESSION_DIR"] = str(sessions_dir)
        return command, environment, session_id

    def start(self, turn: TurnRequest) -> SettledTurn:
        return self._run(turn)

    def reply(self, turn: TurnRequest) -> SettledTurn:
        return self._run(turn)

    def _run(self, turn: TurnRequest) -> SettledTurn:
        command, environment, session_id = self.build_command(turn)
        started = time.monotonic()
        final_message: dict[str, Any] = {}
        error: str | None = None
        error_type: str | None = None
        settled = False
        process = subprocess.Popen(
            command,
            cwd=turn.participant.cwd,
            env=environment,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1,
            start_new_session=True,
        )
        assert process.stdin is not None
        assert process.stdout is not None
        assert process.stderr is not None
        process.stdin.write(
            json.dumps({"id": turn.turn_id, "type": "prompt", "message": turn.prompt})
            + "\n"
        )
        process.stdin.flush()
        selector = selectors.DefaultSelector()
        selector.register(process.stdout, selectors.EVENT_READ)
        selector.register(process.stderr, selectors.EVENT_READ)
        deadline = started + turn.timeout_seconds
        stderr_lines: list[str] = []
        log_path = Path(turn.log_path)
        log_path.parent.mkdir(parents=True, exist_ok=True)
        log_stream = log_path.open("w", encoding="utf-8", buffering=1)
        try:
            while time.monotonic() < deadline:
                events = selector.select(timeout=0.25)
                if not events:
                    if process.poll() is not None:
                        break
                    continue
                for key, _ in events:
                    stream = key.fileobj
                    line = stream.readline()
                    if not line:
                        selector.unregister(stream)
                        continue
                    if stream is process.stderr:
                        stderr_line = line.rstrip("\n")
                        stderr_lines.append(stderr_line)
                        log_stream.write(f"[stderr] {stderr_line}\n")
                        continue
                    log_stream.write(line)
                    try:
                        event = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    if (
                        event.get("type") == "response"
                        and event.get("command") == "prompt"
                        and not event.get("success")
                    ):
                        error = str(event.get("error") or "Pi rejected the prompt")
                        error_type = "transport"
                    if event.get("type") == "message_end":
                        message = event.get("message") or {}
                        if message.get("role") == "assistant":
                            final_message = message
                    if event.get("type") == "agent_settled":
                        settled = True
                        break
                if settled:
                    break
        finally:
            selector.close()
            _terminate(process)
            remaining_stdout = process.stdout.read()
            if remaining_stdout:
                log_stream.write(remaining_stdout)
            remaining_stderr = process.stderr.read()
            if remaining_stderr:
                for stderr_line in remaining_stderr.splitlines():
                    stderr_lines.append(stderr_line)
                    log_stream.write(f"[stderr] {stderr_line}\n")
            for stream in (process.stdin, process.stdout, process.stderr):
                if stream is not None:
                    stream.close()
            log_stream.close()
        elapsed_ms = round((time.monotonic() - started) * 1000)
        if not settled and not error:
            if time.monotonic() >= deadline:
                error = f"Pi turn did not settle within {turn.timeout_seconds} seconds"
                error_type = "timeout"
            else:
                error = f"Pi exited with status {process.returncode} before agent_settled"
                error_type = "process"
        message_error = final_message.get("errorMessage")
        if message_error and not error:
            error = str(message_error)
            error_type = "model"
        artifact = _assistant_text(final_message)
        Path(turn.artifact_path).write_text(artifact)
        if not artifact and not error:
            error = "Pi produced no final assistant artifact"
            error_type = "parse"
        sessions_dir = Path(turn.state_path) / "sessions"
        session_ref = _session_file(sessions_dir, session_id)
        return SettledTurn(
            participant_id=turn.participant.id,
            harness=self.name,
            status="settled" if not error else "failed",
            artifact_file=turn.artifact_path,
            log_file=turn.log_path,
            native_session_id=session_id,
            native_session_ref=str(session_ref) if session_ref else None,
            model=final_message.get("responseModel") or turn.participant.model,
            provider=turn.participant.provider,
            elapsed_ms=elapsed_ms,
            usage=final_message.get("usage") or {},
            error_type=error_type,
            error=error,
            authority_enforcement=(
                "native-tool-allowlist-and-prompt"
                if turn.participant.tools == "write"
                else "native-tool-allowlist"
            ),
            adapter_metadata={
                "settlement": "agent_settled" if settled else None,
                "stop_reason": final_message.get("stopReason"),
            },
        )


def _assistant_text(message: dict[str, Any]) -> str:
    content = message.get("content") or []
    if isinstance(content, str):
        return content
    return "".join(
        str(block.get("text") or "")
        for block in content
        if isinstance(block, dict) and block.get("type") == "text"
    )


def _session_file(sessions_dir: Path, session_id: str) -> Path | None:
    matches = sorted(sessions_dir.glob(f"*_{session_id}.jsonl"))
    if matches:
        return matches[-1]
    matches = sorted(sessions_dir.glob(f"*{session_id}*.jsonl"))
    return matches[-1] if matches else None


def _terminate(process: subprocess.Popen[str]) -> None:
    if process.poll() is not None:
        process.wait()
        return
    try:
        os.killpg(process.pid, signal.SIGTERM)
    except (OSError, ProcessLookupError):
        process.terminate()
    try:
        process.wait(timeout=5)
    except subprocess.TimeoutExpired:
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except (OSError, ProcessLookupError):
            process.kill()
        process.wait(timeout=5)
