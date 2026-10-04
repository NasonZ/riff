"""Claude Code CLI adapter."""

from __future__ import annotations

import json
import os
import uuid
from pathlib import Path
from typing import Any

from ..models import SettledTurn, TurnRequest, ValidationError
from .base import (
    PEER_SYSTEM_NOTE,
    HarnessAdapter,
    child_environment,
    executable,
    require_string_param,
    require_supported_params,
    run_process,
)


class ClaudeAdapter(HarnessAdapter):
    name = "claude"

    def capability(self) -> dict[str, Any]:
        path = os.environ.get("RIFF_CLAUDE_BIN") or "claude"
        return {
            "harness": self.name,
            "available": bool(executable(path, "RIFF_CLAUDE_BIN")) if _which(path) else False,
            "persistent_sessions": True,
            "tool_scopes": ["none", "read", "read+web", "write"],
            "parameters": ["effort", "permission_mode", "add_dirs", "allowed_commands"],
        }

    def validate(self, turn: TurnRequest) -> None:
        super().validate(turn)
        params = turn.participant.params
        require_supported_params(
            self.name,
            params,
            {"effort", "permission_mode", "add_dirs", "allowed_commands"},
        )
        require_string_param(self.name, params, "effort")
        require_string_param(self.name, params, "permission_mode")
        if params.get("permission_mode") not in {None, "dontAsk", "acceptEdits"}:
            raise ValidationError(
                "claude permission_mode must be dontAsk or acceptEdits; "
                "permission bypasses are not supported"
            )
        for directory in _string_list_param(params, "add_dirs"):
            if not Path(directory).expanduser().is_dir():
                raise ValidationError(f"claude param add_dirs entry does not exist: {directory}")
        commands = _string_list_param(params, "allowed_commands")
        if commands and turn.participant.tools != "write":
            raise ValidationError(
                "claude param allowed_commands requires tools=write; read scopes have no shell"
            )
        for command in commands:
            if any(character in command for character in "()*\n"):
                raise ValidationError(
                    f"claude allowed_commands entries are plain command prefixes such as "
                    f"'uv run pytest'; received {command!r}"
                )
        if turn.participant.provider not in {
            None,
            "anthropic",
            "bedrock",
            "vertex",
            "foundry",
        }:
            raise ValidationError(
                "claude provider must be anthropic, bedrock, vertex, foundry, or null"
            )

    def build_command(self, turn: TurnRequest) -> tuple[list[str], dict[str, str], str]:
        self.validate(turn)
        command = [
            executable("claude", "RIFF_CLAUDE_BIN"),
            "--print",
            "--output-format",
            "json",
            "--disable-slash-commands",
            "--append-system-prompt",
            PEER_SYSTEM_NOTE,
        ]
        if turn.is_reply:
            if not turn.native_session_id:
                raise ValidationError("claude reply requires a native session id")
            command.extend(["--resume", turn.native_session_id])
        else:
            command.extend(["--session-id", str(uuid.uuid4())])
        if turn.participant.model:
            command.extend(["--model", turn.participant.model])
        effort = turn.participant.params.get("effort")
        if effort:
            command.extend(["--effort", str(effort)])
        permission_mode = turn.participant.params.get("permission_mode")
        if permission_mode:
            command.extend(["--permission-mode", str(permission_mode)])
        elif turn.participant.tools == "write":
            command.extend(["--permission-mode", "acceptEdits"])
        else:
            command.extend(["--permission-mode", "dontAsk"])
        # --tools makes a tool available; under dontAsk/acceptEdits a tool that needs
        # approval is still denied unless --allowedTools pre-approves it (field
        # evidence: every read+web WebFetch/WebSearch call was denied before this).
        if turn.participant.tools == "none":
            command.extend(["--tools", ""])
        elif turn.participant.tools == "read":
            command.extend(["--tools", "Read,Grep,Glob"])
        elif turn.participant.tools == "read+web":
            command.extend(["--tools", "Read,Grep,Glob,WebSearch,WebFetch"])
            command.extend(["--allowedTools", "WebSearch,WebFetch"])
        else:
            command.extend(["--tools", "Read,Grep,Glob,Edit,Write,Bash"])
            commands = _string_list_param(turn.participant.params, "allowed_commands")
            if commands:
                command.extend(
                    ["--allowedTools", ",".join(f"Bash({prefix}:*)" for prefix in commands)]
                )
        for directory in _string_list_param(turn.participant.params, "add_dirs"):
            command.extend(["--add-dir", str(Path(directory).expanduser().resolve())])
        # The scope names the peer's authority, and MCP is in no scope. Without
        # this, a configured MCP server adds tools --tools never mentioned.
        command.append("--strict-mcp-config")
        environment = child_environment(turn)
        provider = turn.participant.provider
        if provider is not None:
            for variable in (
                "CLAUDE_CODE_USE_BEDROCK",
                "CLAUDE_CODE_USE_VERTEX",
                "CLAUDE_CODE_USE_FOUNDRY",
            ):
                environment.pop(variable, None)
        if provider == "bedrock":
            environment["CLAUDE_CODE_USE_BEDROCK"] = "1"
        elif provider == "vertex":
            environment["CLAUDE_CODE_USE_VERTEX"] = "1"
        elif provider == "foundry":
            environment["CLAUDE_CODE_USE_FOUNDRY"] = "1"
        return command, environment, turn.prompt

    def start(self, turn: TurnRequest) -> SettledTurn:
        return self._run(turn)

    def reply(self, turn: TurnRequest) -> SettledTurn:
        return self._run(turn)

    def _run(self, turn: TurnRequest) -> SettledTurn:
        command, environment, prompt = self.build_command(turn)
        completed, elapsed_ms, timeout_error = run_process(
            command, turn, input_text=prompt, environment=environment
        )
        if timeout_error:
            return _failed(
                turn,
                elapsed_ms,
                "timeout",
                timeout_error,
                native_session_id=turn.native_session_id or _session_id_from_command(command),
            )
        assert completed is not None
        payload: dict[str, Any] = {}
        parse_error: str | None = None
        try:
            decoded = json.loads(completed.stdout)
            if isinstance(decoded, dict):
                payload = decoded
            else:
                parse_error = "Claude JSON output was not an object"
        except json.JSONDecodeError as error:
            parse_error = f"could not parse Claude JSON output: {error}"
        failed = completed.returncode != 0 or bool(payload.get("is_error"))
        artifact = "" if failed else str(payload.get("result") or "")
        Path(turn.artifact_path).write_text(artifact)
        error = parse_error
        error_type = "parse" if parse_error else None
        if failed:
            # Claude reports quota and auth failures inside the JSON result even when
            # it exits non-zero; keep that text instead of a bare exit status.
            error = (
                payload.get("error")
                or (payload.get("result") if payload.get("is_error") else None)
                or completed.stderr.strip()
                or f"claude exited with status {completed.returncode}"
            )
            error_type = _classify_api_error(payload.get("api_error_status")) or (
                "process" if completed.returncode != 0 else "model"
            )
        if not artifact and not error:
            error = "Claude produced no final result"
            error_type = "parse"
        return SettledTurn(
            participant_id=turn.participant.id,
            harness=self.name,
            status="settled" if not error else "failed",
            artifact_file=turn.artifact_path,
            log_file=turn.log_path,
            native_session_id=payload.get("session_id") or (
                turn.native_session_id if turn.is_reply else _session_id_from_command(command)
            ),
            model=payload.get("model") or turn.participant.model,
            provider=turn.participant.provider,
            elapsed_ms=elapsed_ms,
            usage=payload.get("usage") or {},
            error_type=error_type,
            error=str(error) if error else None,
            authority_enforcement=(
                "native-tool-allowlist-and-prompt"
                if turn.participant.tools == "write"
                else "native-tool-allowlist"
            ),
            adapter_metadata={
                "subtype": payload.get("subtype"),
                "num_turns": payload.get("num_turns"),
                "permission_denials": payload.get("permission_denials") or [],
                "api_error_status": payload.get("api_error_status"),
                "cost_usd": payload.get("total_cost_usd"),
            },
        )


def _string_list_param(params: dict[str, Any], name: str) -> list[str]:
    value = params.get(name)
    if value is None:
        return []
    if not isinstance(value, list) or not all(isinstance(item, str) and item.strip() for item in value):
        raise ValidationError(f"claude param {name} must be a list of non-empty strings")
    return [item.strip() for item in value]


def _classify_api_error(status: Any) -> str | None:
    try:
        code = int(status)
    except (TypeError, ValueError):
        return None
    if code == 429:
        return "rate_limit"
    if code in {401, 403}:
        return "auth"
    return None


def _session_id_from_command(command: list[str]) -> str | None:
    try:
        return command[command.index("--session-id") + 1]
    except (ValueError, IndexError):
        return None


def _which(value: str) -> str | None:
    import shutil

    return shutil.which(value) if os.sep not in value else value if Path(value).is_file() else None


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
        harness="claude",
        status="failed",
        artifact_file=turn.artifact_path,
        log_file=turn.log_path,
        native_session_id=native_session_id or turn.native_session_id,
        model=turn.participant.model,
        provider=turn.participant.provider,
        elapsed_ms=elapsed_ms,
        error_type=error_type,
        error=error,
    )
