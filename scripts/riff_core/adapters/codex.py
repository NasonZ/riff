"""OpenAI Codex CLI adapter."""

from __future__ import annotations

import json
import os
import re
import shutil
import tomllib
from pathlib import Path
from typing import Any

from ..models import SettledTurn, TurnRequest, ValidationError
from ..state import default_state_root, private_directory
from .base import (
    HarnessAdapter,
    child_environment,
    classify_error_text,
    executable,
    require_bool_param,
    require_string_param,
    require_supported_params,
    run_process,
)

MCP_TABLE = re.compile(r"\s*\[mcp_servers[.\]]")


def _without_mcp_servers(config: str) -> str:
    """The user's Codex config with every MCP server table removed."""
    kept: list[str] = []
    inside = False
    for line in config.splitlines(keepends=True):
        if MCP_TABLE.match(line):
            inside = True
            continue
        if inside and line.lstrip().startswith("["):
            inside = False
        if not inside:
            kept.append(line)
    filtered = "".join(kept)
    try:
        remaining = tomllib.loads(filtered)
    except tomllib.TOMLDecodeError as error:
        raise ValidationError("Codex configuration could not be safely filtered") from error
    if remaining.get("mcp_servers"):
        raise ValidationError(
            "Codex MCP configuration uses a form Riff cannot safely remove; "
            "use [mcp_servers.<name>] tables or a separate MCP-free CODEX_HOME"
        )
    return filtered


def codex_home(turn: TurnRequest) -> Path:
    """A Codex home whose config declares no MCP servers.

    The scope names a peer's authority and MCP is in no scope, but Codex offers
    no per-run way to drop a configured server: `-c mcp_servers={}` merges and
    is ignored, `-c mcp.enabled=false` is unrecognized, and
    `-c mcp_servers.<id>.enabled=false` replaces the server's table and breaks
    config loading outright ("invalid transport"). `CODEX_HOME` is the supported
    control, so Riff keeps a sanitized copy of the user's config beside its own
    state and points the turn at it. Auth and the model cache are linked, so
    credentials and model resolution are unchanged; it must not live under a
    temporary directory, which Codex refuses.
    """
    real = Path(os.environ.get("CODEX_HOME") or Path.home() / ".codex")
    home = default_state_root() / "codex-home"
    private_directory(home)
    source = real / "config.toml"
    wanted = _without_mcp_servers(source.read_text()) if source.exists() else ""
    target = home / "config.toml"
    if not target.exists() or target.read_text() != wanted:
        target.write_text(wanted)
    for name in ("auth.json", "cache"):
        link = home / name
        if not link.exists() and (real / name).exists():
            try:
                link.symlink_to(real / name)
            except OSError:
                pass
    return home


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
            "tool_scopes": ["none", "read", "read+web", "write"],
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
        # codex-cli enables web search by default, and `[features].web_search` is
        # deprecated in 0.160.0, so the top-level setting is pinned in both
        # directions. Without this, `read` silently grants outbound network and
        # the reported scope overstates nothing but understates the authority.
        command.extend(
            [
                "-c",
                'web_search="live"'
                if turn.participant.tools == "read+web"
                else 'web_search="disabled"',
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
        environment = child_environment(turn)
        environment["CODEX_HOME"] = str(codex_home(turn))
        completed, elapsed_ms, timeout_error = run_process(
            command, turn, input_text=turn.prompt, environment=environment
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
        # Codex also emits top-level `error` events for transient failures it is
        # about to retry ("Reconnecting... 2/5"); only turn.failed or a non-zero
        # exit fails the turn. Those messages still explain a turn that never settles.
        turn_failure = _last_event_message(events, {"turn.failed"})
        error_events = [
            message
            for event in events
            if event.get("type") == "error" and (message := _event_message(event))
        ]
        settled = any(event.get("type") == "turn.completed" for event in events)
        if completed.returncode != 0:
            error = (
                turn_failure
                or (error_events[-1] if error_events else None)
                or completed.stderr.strip()
                or f"codex exited with status {completed.returncode}"
            )
            error_type = classify_error_text(error) or "process"
        elif turn_failure:
            error = turn_failure
            error_type = classify_error_text(error) or "model"
        elif parse_errors and not events:
            error = parse_errors[0]
            error_type = "parse"
        elif not session_id:
            error = "Codex did not emit an explicit thread_id"
            error_type = "parse"
        elif not settled:
            error = "Codex did not emit turn.completed"
            if error_events:
                error += f": {error_events[-1]}"
            error_type = classify_error_text(error) or "transport"
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
                else "native-sandbox-and-config"
                if turn.participant.tools == "read+web"
                else "native-sandbox"
            ),
            adapter_metadata={
                "mcp_servers_suppressed": True,
                "event_count": len(events),
                "parse_errors": parse_errors,
                "settlement": "turn.completed" if settled else None,
                "error_events": error_events,
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


def _last_event_message(events: list[dict[str, Any]], types: set[str]) -> str | None:
    for event in reversed(events):
        if event.get("type") in types:
            return _event_message(event) or "Codex reported an error"
    return None


def _event_message(event: dict[str, Any]) -> str | None:
    """Text of an error event; turn.failed nests it as {"error": {"message": ...}}."""
    value = event.get("error") or event.get("message")
    if isinstance(value, dict):
        value = value.get("message") or json.dumps(value)
    return str(value) if value else None


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
