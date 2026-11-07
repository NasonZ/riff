"""Assessment identity and coverage; success is distinct from currency."""

from __future__ import annotations

from typing import Any

from .views import attempts_for


def assessment_snapshot(control: dict, states: dict, records: dict) -> dict:
    snapshot = {}
    for key, state in states.items():
        attempts = attempts_for(control, key)
        latest = attempts[-1] if attempts else None
        successful = None
        status = state["status"]
        readable = True
        for path in state["turns"]:
            record = records.get(path)
            if (
                not record
                or "execution" not in record
                or "turn_id" not in record
                or "artifact_sha256" not in record
            ):
                readable = False
                continue
            if (
                record["execution"].get("status") == "settled"
                and record["execution"].get("error") is None
            ):
                successful = {
                    "turn_id": record["turn_id"],
                    "artifact_sha256": record["artifact_sha256"],
                }
            if not record.get("_artifact_readable", True):
                readable = False
        if not readable:
            status = "unknown"
        snapshot[key] = {
            "status": status,
            "latest_turn": state["turns"][-1] if state["turns"] else None,
            "active_turn": (state.get("active_turn") or {}).get("turn_id"),
            "latest_attempt": latest["id"] if latest else None,
            "phase": latest["phase"] if latest else None,
            "evidence_readable": readable,
            "successful_turn": successful,
        }
    return snapshot


def snapshots_match(recorded: object, current: dict) -> bool | None:
    """Incomplete evidence cannot establish assessment currency."""
    if not isinstance(recorded, dict) or recorded.keys() != current.keys():
        return None
    if any(
        not isinstance(recorded[key], dict) or recorded[key].keys() != value.keys()
        for key, value in current.items()
    ):
        return None
    return recorded == current


def verification_scope(control: dict, snapshot: dict) -> dict:
    record = (control.get("assessments") or [{}])[-1]
    covers = record.get("covers")
    if not isinstance(covers, dict):
        covers = None
    participants, covered_turns = {}, {}
    for key, value in snapshot.items():
        covered = (covers or {}).get(key)
        covered_turns[key] = (
            covered
            if covered is not None and covered == value["successful_turn"]
            else None
        )
        if value["status"] in {"running", "unknown"}:
            scope = value["status"]
        elif value["status"] != "settled":
            scope = "failed"
        elif not record.get("verified_at"):
            scope = "unassessed"
        elif covers is None:
            scope = "unknown"
        elif covered_turns[key] is not None:
            scope = "covered"
        else:
            scope = "uncovered"
        participants[key] = scope
    changed = record.get("changed_during_checks", False)
    if any(v["status"] == "unknown" for v in snapshot.values()):
        current = None
    elif not record.get("verified_at"):
        current = False
    elif covers is None:
        current = None
    else:
        matches = snapshots_match(record.get("snapshot"), snapshot)
        current = None if matches is None else not changed and matches
    return {
        "participants": participants,
        "covered_turns": covered_turns,
        "current": current,
        "changed_during_checks": changed,
    }


def derive_verification(executed: list[dict[str, Any]]) -> str | None:
    if not executed:
        return None
    passed = sum(check["passed"] for check in executed)
    if passed == len(executed):
        return "passed"
    return "partial" if passed else "failed"
