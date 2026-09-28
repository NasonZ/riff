"""OpenAI Codex CLI adapter."""

from __future__ import annotations

import json
import os
import shutil
from pathlib import Path
from typing import Any

from ..models import SettledTurn, TurnRequest, ValidationError
from .base import (
    HarnessAdapter,
    classify_error_text,
    executable,
    require_bool_param,
    require_string_param,
    require_supported_params,
    run_process,
)


class CodexAdapter(HarnessAdapter):
    name = "codex"

    def capability(self) -> dict[str, Any]:
        configured = os.environ.get("RIFF_CODEX_BIN") or "codex"
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
            "parameters": ["reasoning_effort", "skip_git_repo_check"],
        }

    def validate(self, turn: TurnRequest) -> None:
        super().validate(turn)
        require_supported_params(
            self.name,
            turn.participant.params,
            {"reasoning_effort", "skip_git_repo_check"},
        )
        require_string_param(self.name, turn.participant.params, "reasoning_effort")
        require_bool_param(self.name, turn.participant.params, "skip_git_repo_check")
        if turn.participant.tools == "read+web":
            raise ValidationError(
                "codex does not support the read+web tool scope; use read or write"
            )
        if turn.participant.provider not in {None, "openai", "oss", "ollama", "lmstudio"}:
            raise ValidationError(
                "codex provider must be openai, oss, ollama, lmstudio, or null"
            )

    def build_command(self, turn: TurnRequest) -> list[str]:
        self.validate(turn)
        codex = executable("codex", "RIFF_CODEX_BIN")
        command = [codex, "exec"]
        if turn.is_reply:
            if not turn.native_session_id:
                raise ValidationError("codex reply requires a native session id")
            command.extend(
                ["resume", "--json", "-o", turn.artifact_path]
            )
        else:
            command.extend(
                [
                    "--json",
                    "-o",
                    turn.artifact_path,
                    "-C",
                    turn.participant.cwd,
                    "--sandbox",
                    "workspace-write" if turn.participant.tools == "write" else "read-only",
                ]
            )
        if turn.participant.model:
            command.extend(["--model", turn.participant.model])
        provider = turn.participant.provider
        if not turn.is_reply and provider in {"oss", "ollama", "lmstudio"}:
            command.append("--oss")
            if provider in {"ollama", "lmstudio"}:
                command.extend(["--local-provider", provider])
        effort = turn.participant.params.get("reasoning_effort")
        if effort:
            command.extend(["-c", f'model_reasoning_effort="{effort}"'])
        if turn.participant.params.get("skip_git_repo_check"):
            command.append("--skip-git-repo-check")
        if turn.is_reply:
            command.extend([turn.native_session_id, "-"])
        else:
            command.append("-")
        return command

    def start(self, turn: TurnRequest) -> SettledTurn:
        return self._run(turn)

    def reply(self, turn: TurnRequest) -> SettledTurn:
        return self._run(turn)

    def _run(self, turn: TurnRequest) -> SettledTurn:
        command = self.build_command(turn)
        completed, elapsed_ms, timeout_error = run_process(
            command, turn, input_text=turn.prompt
        )
        assert completed is not None
        events, parse_errors = _parse_events(completed.stdout)
        session_id = turn.native_session_id or _find_key(events, "thread_id")
        artifact_path = Path(turn.artifact_path)
        artifact = artifact_path.read_text() if artifact_path.is_file() else _last_text(events)
        if artifact and not artifact_path.is_file():
            artifact_path.write_text(artifact)
        if timeout_error:
            return _failed(
                turn,
                elapsed_ms,
                "timeout",
                timeout_error,
                native_session_id=str(session_id) if session_id else None,
            )
        error: str | None = None
        error_type: str | None = None
        reported_error = _find_error(events)
        settled = any(event.get("type") == "turn.completed" for event in events)
        if completed.returncode != 0:
            error = reported_error or completed.stderr.strip() or (
                f"codex exited with status {completed.returncode}"
            )
            error_type = classify_error_text(error) or "process"
        elif reported_error:
            error = reported_error
            error_type = classify_error_text(error) or "model"
        elif parse_errors and not events:
            error = parse_errors[0]
            error_type = "parse"
        elif not session_id:
            error = "Codex did not emit an explicit thread_id"
            error_type = "parse"
        elif not settled:
            error = "Codex did not emit turn.completed"
            error_type = "transport"
        elif not artifact:
            error = "Codex produced no final artifact"
            error_type = "parse"
        return SettledTurn(
            participant_id=turn.participant.id,
            harness=self.name,
            status="settled" if not error else "failed",
            artifact_file=turn.artifact_path,
            log_file=turn.log_path,
            native_session_id=str(session_id) if session_id else None,
            model=turn.participant.model,
            provider=turn.participant.provider or "openai",
            elapsed_ms=elapsed_ms,
            usage=_last_usage(events),
            error_type=error_type,
            error=error,
            authority_enforcement=(
                "sandbox-and-prompt"
                if turn.participant.tools == "none"
                else "native-sandbox-and-prompt"
                if turn.participant.tools == "write"
                else "native-sandbox"
            ),
            adapter_metadata={
                "event_count": len(events),
                "parse_errors": parse_errors,
                "settlement": "turn.completed" if settled else None,
            },
        )


def _parse_events(output: str) -> tuple[list[dict[str, Any]], list[str]]:
    events: list[dict[str, Any]] = []
    errors: list[str] = []
    for line in output.splitlines():
        if not line.strip():
            continue
        try:
            value = json.loads(line)
        except json.JSONDecodeError as error:
            errors.append(f"invalid Codex JSONL event: {error}")
            continue
        if isinstance(value, dict):
            events.append(value)
    return events, errors


def _find_key(value: Any, key: str) -> Any:
    if isinstance(value, dict):
        if key in value:
            return value[key]
        for child in value.values():
            found = _find_key(child, key)
            if found is not None:
                return found
    elif isinstance(value, list):
        for child in value:
            found = _find_key(child, key)
            if found is not None:
                return found
    return None


def _last_text(events: list[dict[str, Any]]) -> str:
    candidates: list[str] = []
    for event in events:
        item = event.get("item")
        if isinstance(item, dict) and item.get("type") in {"agent_message", "message"}:
            text = item.get("text") or item.get("content")
            if isinstance(text, str):
                candidates.append(text)
    return candidates[-1] if candidates else ""


def _find_error(events: list[dict[str, Any]]) -> str | None:
    for event in reversed(events):
        if event.get("type") in {"error", "turn.failed"}:
            value = event.get("error") or event.get("message")
            return str(value) if value else "Codex reported an error"
    return None


def _last_usage(events: list[dict[str, Any]]) -> dict[str, Any]:
    for event in reversed(events):
        usage = event.get("usage")
        if isinstance(usage, dict):
            return usage
    return {}


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
        harness="codex",
        status="failed",
        artifact_file=turn.artifact_path,
        log_file=turn.log_path,
        native_session_id=native_session_id or turn.native_session_id,
        model=turn.participant.model,
        provider=turn.participant.provider or "openai",
        elapsed_ms=elapsed_ms,
        error_type=error_type,
        error=error,
    )
