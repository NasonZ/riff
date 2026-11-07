"""Native evidence capture and live Pi progress views.

Adapters locate native sources; these functions describe the evidence available
without changing session identity or persisting coordinator state.
"""

from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path
from typing import TYPE_CHECKING, Any

from .models import SettledTurn, TurnRequest

if TYPE_CHECKING:
    from .adapters.base import HarnessAdapter


def native_transcript(
    adapter: HarnessAdapter, session_id: str | None, session_ref: str | None
) -> Path | None:
    try:
        return adapter.native_transcript(session_id, session_ref)
    except OSError:
        return None


def native_position(
    adapter: HarnessAdapter, session_id: str | None, session_ref: str | None
) -> dict[str, Any] | None:
    try:
        return adapter.native_position(session_id, session_ref)
    except OSError:
        return None


def native_rows(
    adapter: HarnessAdapter,
    turn: TurnRequest,
    result: SettledTurn,
    before: dict[str, Any] | None,
) -> dict[str, Any] | None:
    """Where this turn sits in a database-backed session: the message ids it added."""
    after = native_position(
        adapter, result.native_session_id, result.native_session_ref
    )
    if after is None:
        return None
    if before is not None and before.get("session_id") == after["session_id"]:
        start: int | None = before["last_message_id"]
    else:
        start = None if turn.is_reply else 0
    return {
        "path": after["path"],
        "session_id": after["session_id"],
        "start_message_id": start,
        "end_message_id": after["last_message_id"],
    }


def native_episode(
    adapter: HarnessAdapter,
    turn: TurnRequest,
    result: SettledTurn,
    before: dict[str, Any] | None,
) -> dict[str, Any] | None:
    """Where this turn sits in the harness's own session file: the byte range
    it appended, a digest of the file at settle, and its last entry's id."""
    path = native_transcript(
        adapter, result.native_session_id, result.native_session_ref
    )
    if path is None:
        return None
    if before is not None and before["path"] == str(path):
        start: int | None = before["size"]
    else:
        # A new session starts empty; a resumed one with no recorded start is
        # unbounded, and must say so rather than claim the whole file.
        start = None if turn.is_reply else 0
    digest = hashlib.sha256()
    last = b""
    try:
        with path.open("rb") as stream:
            for line in stream:
                digest.update(line)
                if line.strip():
                    last = line
            size = stream.tell()
    except OSError:
        return None
    if start is not None and start > size:
        start = None  # the file was rewritten during the turn, not appended to
    try:
        entry = json.loads(last) if last else {}
    except json.JSONDecodeError:
        entry = {}
    entry_id = (
        (entry.get("id") or entry.get("uuid")) if isinstance(entry, dict) else None
    )
    return {
        "path": str(path),
        "start_offset": start,
        "end_offset": size,
        "sha256": digest.hexdigest(),
        "last_entry_id": entry_id if isinstance(entry_id, str) else None,
    }


def file_position(path: Path | None) -> dict[str, Any] | None:
    try:
        return {"path": str(path), "size": path.stat().st_size} if path else None
    except OSError:
        return None


def pi_progress(path: Path, *, include_previews: bool) -> dict[str, Any]:
    counts: dict[str, int] = {}
    latest: dict[str, Any] | None = None
    record_count = 0
    for line in path.read_text().splitlines():
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        event_type = str(event.get("type") or "unknown")
        counts[event_type] = counts.get(event_type, 0) + 1
        if event_type != "message" or not isinstance(event.get("message"), dict):
            continue
        record_count += 1
        message = event["message"]
        blocks: list[dict[str, Any]] = []
        for block in message.get("content") or []:
            if not isinstance(block, dict):
                continue
            block_type = block.get("type")
            summary: dict[str, Any] = {"type": block_type}
            if block_type in {"thinking", "text"}:
                text = str(block.get("thinking") or block.get("text") or "")
                summary["characters"] = len(text)
                if include_previews:
                    summary["preview"] = text[:400]
            elif block_type in {"toolCall", "tool_use"}:
                summary["name"] = block.get("name")
            blocks.append(summary)
        latest = {
            "timestamp": event.get("timestamp"),
            "role": message.get("role"),
            "blocks": blocks,
        }
    return {
        "session_file": str(path),
        "bytes": path.stat().st_size,
        "event_counts": counts,
        "message_records": record_count,
        "latest_message": latest,
    }


def pi_rpc_progress(path: Path, *, include_previews: bool) -> dict[str, Any]:
    event_counts: dict[str, int] = {}
    update_counts: dict[str, int] = {}
    delta_characters = {"thinking": 0, "text": 0, "toolcall": 0}
    previews = {"thinking": "", "text": "", "toolcall": ""}
    tool_names: list[str] = []
    last_event: str | None = None
    last_update: str | None = None
    with path.open(encoding="utf-8", errors="replace") as stream:
        for line in stream:
            if line.startswith("[stderr] "):
                event_counts["stderr"] = event_counts.get("stderr", 0) + 1
                continue
            try:
                event = json.loads(line)
            except json.JSONDecodeError:
                continue
            event_type = str(event.get("type") or "unknown")
            event_counts[event_type] = event_counts.get(event_type, 0) + 1
            last_event = event_type
            if event_type in {"tool_execution_start", "tool_execution_end"}:
                tool_name = event.get("toolName")
                if isinstance(tool_name, str) and tool_name not in tool_names:
                    tool_names.append(tool_name)
            if event_type != "message_update":
                continue
            update = event.get("assistantMessageEvent") or {}
            update_type = str(update.get("type") or "unknown")
            update_counts[update_type] = update_counts.get(update_type, 0) + 1
            last_update = update_type
            delta = update.get("delta")
            if not isinstance(delta, str):
                continue
            kind = update_type.removesuffix("_delta")
            if kind not in delta_characters:
                continue
            delta_characters[kind] += len(delta)
            if include_previews:
                previews[kind] = (previews[kind] + delta)[-400:]
    result: dict[str, Any] = {
        "log_file": str(path),
        "bytes": path.stat().st_size,
        "event_counts": event_counts,
        "update_counts": update_counts,
        "delta_characters": delta_characters,
        "tool_names": tool_names,
        "last_event": last_event,
        "last_update": last_update,
        "settled": bool(event_counts.get("agent_settled")),
    }
    if include_previews:
        result["previews"] = {key: value for key, value in previews.items() if value}
    return result


def checkout_fingerprint(cwd: str) -> dict[str, Any] | None:
    """Coarse checkout observations, not a content fingerprint or isolation proof.

    Equal HEAD and dirty-file counts can conceal edits. None outside git.
    """
    try:
        head = subprocess.run(
            ["git", "-C", cwd, "rev-parse", "HEAD"],
            check=False,
            capture_output=True,
            text=True,
            timeout=10,
        )
        if head.returncode != 0:
            return None
        status = subprocess.run(
            ["git", "-C", cwd, "status", "--porcelain"],
            check=False,
            capture_output=True,
            text=True,
            timeout=30,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    return {
        "head": head.stdout.strip(),
        "dirty_files": len(
            [line for line in status.stdout.splitlines() if line.strip()]
        ),
    }
