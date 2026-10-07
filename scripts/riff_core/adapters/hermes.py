"""Hermes Agent quiet-CLI adapter."""

from __future__ import annotations

import os
import re
import shutil
from pathlib import Path
from typing import Any

from ..models import SettledTurn, TurnRequest, ValidationError
from .base import (
    PEER_SYSTEM_NOTE,
    HarnessAdapter,
    classify_error_text,
    executable,
    require_positive_int_param,
    require_supported_params,
    run_process,
)

SESSION_PATTERN = re.compile(r"^\s*session_id:\s*(\S+)\s*$", re.MULTILINE)
# The prompt travels as one --query argument, and Linux caps a single argument at
# 128 KiB. Refuse clearly rather than fail at launch with "Argument list too long".
QUERY_ARGUMENT_LIMIT = 128 * 1024


class HermesAdapter(HarnessAdapter):
    name = "hermes"

    def capability(self) -> dict[str, Any]:
        configured = os.environ.get("RIFF_HERMES_BIN") or "hermes"
        available = bool(
            shutil.which(configured)
            if os.sep not in configured
            else Path(configured).is_file()
        )
        return {
            "harness": self.name,
            "available": available,
            "persistent_sessions": True,
            "tool_scopes": ["none", "read"],
            "parameters": ["max_turns"],
            "authority_note": "read scope is prompt-enforced on the installed CLI",
        }

    def validate(self, turn: TurnRequest) -> None:
        super().validate(turn)
        require_supported_params(self.name, turn.participant.params, {"max_turns"})
        require_positive_int_param(self.name, turn.participant.params, "max_turns")
        if turn.participant.tools == "write":
            raise ValidationError(
                "Hermes write delegation is disabled until a native permission-enforced adapter is used"
            )
        if turn.participant.tools == "read+web":
            raise ValidationError(
                "hermes does not support the read+web tool scope; use read or none"
            )
        if len(_query(turn).encode("utf-8")) >= QUERY_ARGUMENT_LIMIT:
            raise ValidationError(
                "hermes receives the prompt as one command-line argument, limited to "
                "128 KiB; reference large inputs through context_refs instead of "
                "pasting them"
            )

    def build_command(self, turn: TurnRequest) -> list[str]:
        self.validate(turn)
        command = [
            executable("hermes", "RIFF_HERMES_BIN"),
            "chat",
            "--quiet",
            "--source",
            "riff",
            "--ignore-rules",
        ]
        if turn.is_reply:
            if not turn.native_session_id:
                raise ValidationError("hermes reply requires a native session id")
            command.extend(["--resume", turn.native_session_id, "--no-restore-cwd"])
        if turn.participant.model:
            command.extend(["--model", turn.participant.model])
        if turn.participant.provider:
            command.extend(["--provider", turn.participant.provider])
        max_turns = turn.participant.params.get("max_turns")
        if max_turns:
            command.extend(["--max-turns", str(max_turns)])
        # `todo` supplies no workspace or network capability. Hermes' `file`
        # toolset currently combines reads and writes, so read authority is also
        # stated in the prompt and recorded as prompt-enforced.
        command.extend(
            ["--toolsets", "todo" if turn.participant.tools == "none" else "file"]
        )
        command.extend(["--query", _query(turn)])
        return command

    def start(self, turn: TurnRequest) -> SettledTurn:
        return self._run(turn)

    def reply(self, turn: TurnRequest) -> SettledTurn:
        return self._run(turn)

    def _run(self, turn: TurnRequest) -> SettledTurn:
        completed, elapsed_ms, timeout_error = run_process(self.build_command(turn), turn)
        if timeout_error:
            assert completed is not None
            combined = completed.stderr + "\n" + completed.stdout
            match = SESSION_PATTERN.search(combined)
            return _failed(
                turn,
                elapsed_ms,
                "timeout",
                timeout_error,
                native_session_id=match.group(1) if match else None,
            )
        assert completed is not None
        combined = completed.stderr + "\n" + completed.stdout
        match = SESSION_PATTERN.search(combined)
        session_id = match.group(1) if match else turn.native_session_id
        artifact = SESSION_PATTERN.sub("", completed.stdout).strip()
        Path(turn.artifact_path).write_text(artifact)
        error: str | None = None
        error_type: str | None = None
        if completed.returncode != 0:
            error = completed.stderr.strip() or (
                f"hermes exited with status {completed.returncode}"
            )
            error_type = classify_error_text(error) or "process"
        elif not session_id:
            error = "Hermes did not emit an explicit session_id"
            error_type = "parse"
        elif not artifact:
            error = "Hermes produced no final artifact"
            error_type = "parse"
        return SettledTurn(
            participant_id=turn.participant.id,
            harness=self.name,
            status="settled" if not error else "failed",
            artifact_file=turn.artifact_path,
            log_file=turn.log_path,
            native_session_id=session_id,
            model=turn.participant.model,
            provider=turn.participant.provider,
            elapsed_ms=elapsed_ms,
            error_type=error_type,
            error=error,
            authority_enforcement=(
                "native-toolset" if turn.participant.tools == "none" else "prompt"
            ),
        )


def _query(turn: TurnRequest) -> str:
    return f"{PEER_SYSTEM_NOTE}\n\n{turn.prompt}"


def _failed(
    turn: TurnRequest,
    elapsed_ms: int,
    error_type: str,
    error: str,
    *,
    native_session_id: str | None = None,
) -> SettledTurn:
    return SettledTurn(
        participant_id=turn.participant.id,
        harness="hermes",
        status="failed",
        artifact_file=turn.artifact_path,
        log_file=turn.log_path,
        native_session_id=native_session_id or turn.native_session_id,
        model=turn.participant.model,
        provider=turn.participant.provider,
        elapsed_ms=elapsed_ms,
        error_type=error_type,
        error=error,
        authority_enforcement="prompt",
    )
