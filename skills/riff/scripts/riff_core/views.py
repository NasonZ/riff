"""Pure lifecycle views and reservation policy over a captured control snapshot."""

from __future__ import annotations

from typing import Any
from .models import DEFAULT_TIMEOUT_SECONDS, ValidationError

ATTEMPT_FACTOR = 2
ACTIVE_PHASES = {"reserved", "running"}


def attempts_for(control: dict, participant_id: str) -> list[dict]:
    return [a for a in control["attempts"] if a["participant_id"] == participant_id]


def attempt_status(attempt: dict, observations: dict) -> str:
    if attempt["phase"] not in ACTIVE_PHASES:
        outcome = attempt.get("outcome") or {}
        status = outcome.get("status", "unknown")
        return (
            "failed"
            if status == "settled" and outcome.get("error") is not None
            else status
        )
    owner = observations.get(attempt["id"], {}).get("owner", "unknown")
    if owner == "alive":
        return "running"
    if owner == "gone":
        return "interrupted"
    return "unknown"


def dispatch_status(control: dict, observations: dict) -> str:
    dispatch = control["dispatch"]
    phase = dispatch["phase"]
    if phase == "complete":
        return "settled"
    if phase == "launch_failed":
        return "failed-to-start"
    dispatched = all(
        item.get("kind") in {"attempted", "blocked"}
        for item in dispatch["participants"].values()
    )
    if phase in {"failed", "interrupted"}:
        return "settled" if dispatched else "interrupted"
    observed = observations.get("dispatch", {})
    if phase == "launching":
        if dispatch.get("child"):
            child = observed.get("child", "unknown")
            if child == "alive":
                return "starting"
            if child == "unknown":
                return "unknown"
            if child == "gone":
                return "failed-to-start"
        owner = observed.get("owner", "unknown")
        return {"alive": "starting", "gone": "failed-to-start"}.get(owner, "unknown")
    return {"alive": "running", "gone": "settled" if dispatched else "interrupted"}.get(
        observed.get("owner"), "unknown"
    )


def participant_views(control: dict, observations: dict) -> dict[str, dict[str, Any]]:
    result = {}
    for key in control["participants"]:
        participant = control["participant_specs"][key]
        attempts = attempts_for(control, key)
        latest = attempts[-1] if attempts else None
        disposition = control["dispatch"]["participants"].get(key, {})
        status = (
            attempt_status(latest, observations)
            if latest
            else (
                "failed"
                if disposition.get("kind") == "blocked"
                else "pending"
            )
        )
        turns = [a["turn_file"] for a in attempts if a.get("turn_file")]
        if not attempts and disposition.get("turn_file"):
            turns.append(disposition["turn_file"])
        state = {
            "schema_version": 2,
            "run_id": control["run_id"],
            "participant_id": key,
            "spec": participant["spec"],
            "native_session_id": participant.get("native_session_id"),
            "native_session_ref": participant.get("native_session_ref"),
            "status": status,
            "turn_count": len(attempts),
            "settled_turns": sum(
                (a.get("outcome") or {}).get("status") == "settled"
                and (a.get("outcome") or {}).get("error") is None
                for a in attempts
            ),
            "turns": turns,
            "timeout_seconds": latest.get("timeout_seconds", DEFAULT_TIMEOUT_SECONDS)
            if latest
            else DEFAULT_TIMEOUT_SECONDS,
        }
        if latest and latest["phase"] in ACTIVE_PHASES:
            state["active_turn"] = {
                "turn_id": latest["id"],
                "attempt_id": latest["id"],
                "phase": latest["phase"],
                "continued": latest.get("continued", False),
                "log_file": latest.get("log_file"),
                "started_at": latest.get("started_at"),
                "coordinator_pid": (latest.get("owner") or {}).get("pid"),
                "owner": latest.get("owner"),
                "child": latest.get("child"),
                "owner_state": observations.get(latest["id"], {}).get(
                    "owner", "unknown"
                ),
                "child_state": observations.get(latest["id"], {}).get(
                    "child", "unknown"
                ),
                "driver_session": latest.get("driver_session"),
            }
        result[key] = state
    return result


def run_view(control: dict, observations: dict) -> dict:
    states = participant_views(control, observations)
    values = [s["status"] for s in states.values()]
    dispatch = dispatch_status(control, observations)
    # Active work takes priority while any participant or initial dispatcher can
    # still advance. Then uncertainty outranks interruption. Only completed
    # dispatch with terminal participant outcomes can produce a settled result;
    # queued pipeline work remains interrupted after its dispatcher exits.
    if "running" in values:
        status = "running"
    elif dispatch in {"running", "starting"}:
        status = dispatch
    elif "unknown" in values or dispatch == "unknown":
        status = "unknown"
    elif dispatch == "failed-to-start":
        status = dispatch
    elif "interrupted" in values or dispatch == "interrupted" or "pending" in values:
        status = "interrupted"
    else:
        status = "settled"
    successes = values.count("settled")
    if status == "settled":
        outcome = (
            "success"
            if successes == len(values) and values
            else "partial"
            if successes
            else "failed"
        )
    elif status in {"unknown", "interrupted"}:
        outcome = status
    elif status == "failed-to-start":
        outcome = "failed"
    else:
        outcome = "partial" if successes else "pending"
    manifest = {
        k: v
        for k, v in control.items()
        if k not in {"attempts", "participant_specs", "assessments"}
    }
    manifest["dispatch"] = {
        key: value for key, value in control["dispatch"].items() if key != "token"
    }
    assessments = control.get("assessments", [])
    manifest.update(
        status=status,
        result=outcome,
        verification=assessments[-1]
        if assessments
        else {
            "performed": False,
            "verifier": None,
            "checks": [],
            "result": "pending",
            "integrated": False,
            "view_changed": None,
        },
        verification_history=assessments[:-1],
    )
    return {
        "manifest": manifest,
        "participant_state": states,
    }


def recovery_error(attempt: dict, observations: dict) -> str | None:
    if attempt["phase"] not in ACTIVE_PHASES:
        return None
    observed = observations.get(attempt["id"], {})
    owner = observed.get("owner", "unknown")
    if owner != "gone":
        return f"owner is {owner}; inspect status/progress and wait for a confirmed dead owner"
    if attempt["phase"] == "reserved" and attempt.get("launch_model") == "exec-gated":
        return None
    child = observed.get("child", "unknown")
    if child != "gone":
        return f"child/process group is {child} ({attempt.get('child')}); wait for confirmed exit; no automatic orphan killing"
    return None


def check_budget(state: dict, max_rounds: int) -> None:
    if state["settled_turns"] >= max_rounds:
        raise ValidationError(
            f"participant {state['participant_id']} reached max_rounds={max_rounds} settled turns; synthesize, reply with --extend-rounds N to keep this session, or start a new run"
        )
    if state["turn_count"] >= ATTEMPT_FACTOR * max_rounds:
        raise ValidationError(
            f"participant {state['participant_id']} reached {state['turn_count']} attempts ({ATTEMPT_FACTOR} x max_rounds); fix the failure cause before retrying"
        )
