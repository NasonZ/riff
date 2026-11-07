"""Pi JSONL-RPC adapter."""

from __future__ import annotations

import json
from dataclasses import asdict
import os
import shutil
import subprocess
import time
import uuid
from pathlib import Path
from typing import Any

from ..evidence import pi_progress, pi_rpc_progress
from ..process import (
    child_environment,
    group_state,
    observe_child_exit,
    spawn_gated,
    terminate_group,
)
from ..pipe_io import PipeIO, close_process_pipes
from ..models import SettledTurn, TurnRequest, ValidationError
from .base import (
    PEER_SYSTEM_NOTE,
    HarnessAdapter,
    classify_error_text,
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

    def native_transcript(
        self, session_id: str | None, session_ref: str | None
    ) -> Path | None:
        return (
            Path(session_ref) if session_ref and Path(session_ref).is_file() else None
        )

    def live_progress(
        self,
        state_path: Path,
        log_dir: Path,
        *,
        participant_id: str,
        active_log: str | None,
        session_ref: str | None,
        include_previews: bool,
    ) -> dict[str, Any]:
        item: dict[str, Any] = {}
        log_files = (
            [Path(active_log)]
            if active_log and Path(active_log).is_file()
            else sorted(
                log_dir.glob(f"{participant_id}-*.log"),
                key=lambda path: path.stat().st_mtime,
            )
        )
        if log_files and log_files[-1].is_file():
            item["live_rpc"] = pi_rpc_progress(
                log_files[-1], include_previews=include_previews
            )
        if not session_ref:
            native_root = state_path / "sessions"
            sessions = sorted(
                native_root.glob("*.jsonl"),
                key=lambda path: path.stat().st_mtime,
            )
            session_ref = str(sessions[-1]) if sessions else None
        if session_ref and Path(session_ref).is_file():
            item["live_trace"] = pi_progress(
                Path(session_ref), include_previews=include_previews
            )
        return item

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
        if turn.participant.provider and not turn.participant.model:
            raise ValidationError(
                "pi provider requires model; Pi refuses --provider without --model"
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

    def execute(self, turn: TurnRequest) -> SettledTurn:
        command, environment, session_id = self.build_command(turn)
        if turn.observe_session:
            turn.observe_session(session_id, turn.native_session_ref)
        started = time.monotonic()
        final_message: dict[str, Any] = {}
        error: str | None = None
        error_type: str | None = None
        settled = False
        process = spawn_gated(
            command,
            observe=turn.observe_process,
            launch_model=turn.launch_model,
            cwd=turn.participant.cwd,
            env=environment,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        cleanup = None
        drained = True
        try:
            assert process.stdin is not None
            assert process.stdout is not None
            assert process.stderr is not None
            payload = (
                json.dumps(
                    {"id": turn.turn_id, "type": "prompt", "message": turn.prompt}
                )
                + "\n"
            ).encode("utf-8")
            # Split raw chunks explicitly: message_end and agent_settled can
            # arrive together while Pi keeps the process alive for more RPC.
            io = PipeIO(process, payload, keep_stdin=True)
            pending = {"stdout": b"", "stderr": b""}
            deadline = started + turn.timeout_seconds
            stderr_lines: list[str] = []
            log_path = Path(turn.log_path)
            log_path.parent.mkdir(parents=True, exist_ok=True)
            log_stream = log_path.open("w", encoding="utf-8", buffering=1)

            def read_records(stream_name: str, chunk: bytes) -> list[str]:
                *lines, pending[stream_name] = (pending[stream_name] + chunk).split(
                    b"\n"
                )
                return [line.decode("utf-8", errors="replace") for line in lines]

            def log_stderr(line: str) -> None:
                stderr_lines.append(line)
                log_stream.write(f"[stderr] {line}\n")

            finished_loop = False
            try:
                while not settled and not error and time.monotonic() < deadline:
                    chunks = io.read(min(0.25, max(0, deadline - time.monotonic())))
                    if not chunks:
                        if observe_child_exit(process).exited:
                            break
                        continue
                    for stream_name, chunk in chunks:
                        lines = read_records(stream_name, chunk)
                        if stream_name == "stdout":
                            # Retain every captured line even if parsing an
                            # earlier record in this same chunk raises.
                            log_stream.write("".join(line + "\n" for line in lines))
                        for line in lines:
                            if stream_name == "stderr":
                                log_stderr(line)
                                continue
                            if settled or error:
                                continue
                            try:
                                event = json.loads(line)
                            except json.JSONDecodeError:
                                continue
                            if (
                                event.get("type") == "response"
                                and event.get("command") == "prompt"
                            ):
                                # No run follows a rejected or handled prompt, so
                                # agent_settled will never arrive.
                                if not event.get("success"):
                                    error = str(
                                        event.get("error") or "Pi rejected the prompt"
                                    )
                                    error_type = "transport"
                                elif (event.get("data") or {}).get(
                                    "disposition"
                                ) == "handled":
                                    error = (
                                        "Pi handled the prompt without starting a run"
                                    )
                                    error_type = "transport"
                            if event.get("type") == "message_end":
                                message = event.get("message") or {}
                                if message.get("role") == "assistant":
                                    final_message = message
                            if event.get("type") == "agent_settled":
                                settled = True
                finished_loop = True
            finally:
                # Close stdin first, allowing a settled session to flush itself.
                # Drain concurrently with that grace period so shutdown output
                # cannot fill a pipe and turn an orderly exit into a forced one.
                remaining = {name: bytearray(tail) for name, tail in pending.items()}

                def retain(name, chunk):
                    remaining[name].extend(chunk)

                try:
                    io.finish_input()
                    orderly = (
                        finished_loop
                        and settled
                        and not error
                        and not final_message.get("errorMessage")
                        and bool(_assistant_text(final_message))
                    )
                    if orderly:
                        shutdown_deadline = time.monotonic() + 5
                        while time.monotonic() < shutdown_deadline:
                            if observe_child_exit(process).exited:
                                break
                            interval = min(
                                0.05, max(0, shutdown_deadline - time.monotonic())
                            )
                            if io.outputs:
                                for name, chunk in io.read(interval):
                                    retain(name, chunk)
                            else:
                                time.sleep(interval)
                    observed_exit = observe_child_exit(process)
                    if (
                        orderly
                        and observed_exit.exited
                        and observed_exit.returncode in {0, None}
                    ):
                        # Reap only the successful orderly path. A fallback that
                        # cannot observe the exit code before reaping cannot
                        # subsequently authorise group signals after an error.
                        process.wait(timeout=5)
                        if process.returncode != 0:
                            cleanup = terminate_group(process)
                    elif orderly and observed_exit.exited is None:
                        try:
                            process.wait(timeout=0)
                        except subprocess.TimeoutExpired:
                            cleanup = terminate_group(process)
                        else:
                            if process.returncode != 0:
                                cleanup = terminate_group(process)
                    else:
                        cleanup = terminate_group(process)
                    drained = io.drain(retain)
                    if remaining["stdout"]:
                        log_stream.write(
                            remaining["stdout"].decode("utf-8", errors="replace")
                        )
                    for line in (
                        remaining["stderr"]
                        .decode("utf-8", errors="replace")
                        .splitlines()
                    ):
                        log_stderr(line)
                    if not drained:
                        log_stream.write(
                            "\n[riff] pipe capture stopped at the drain deadline; inherited pipes remain open.\n"
                        )
                finally:
                    io.close()
                    log_stream.close()
            elapsed_ms = round((time.monotonic() - started) * 1000)
            if not settled and not error:
                if time.monotonic() >= deadline:
                    error = (
                        f"Pi turn did not settle within {turn.timeout_seconds} seconds"
                    )
                    error_type = "timeout"
                else:
                    error = f"Pi exited with status {process.returncode} before agent_settled"
                    last_stderr = next(
                        (line for line in reversed(stderr_lines) if line.strip()), ""
                    )
                    if last_stderr:
                        error += f": {last_stderr.strip()}"
                    error_type = classify_error_text(last_stderr) or "process"
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
                    "output_truncated": not drained,
                    "descendants": group_state(process.riff_identity),
                    "cleanup": asdict(cleanup) if cleanup is not None else None,
                    "cleanup_unproven": cleanup is not None
                    and cleanup.group_proof == "unknown"
                    and group_state(process.riff_identity) != "gone",
                    "settlement": "agent_settled" if settled else None,
                    "stop_reason": final_message.get("stopReason"),
                },
            )

        except BaseException:
            terminate_group(process)
            close_process_pipes(process)
            raise


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
