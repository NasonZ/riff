"""Capture control once and observe its referenced processes and evidence."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from .assessment import assessment_snapshot, verification_scope
from .models import SettledTurn
from .process import group_state, process_state
from .state import read_json
from .views import ACTIVE_PHASES, run_view


@dataclass
class Snapshot:
    control: dict
    observations: dict
    records: dict
    view: dict
    assessment: dict

    @property
    def scope(self) -> dict:
        return verification_scope(self.control, self.assessment)


def observe(control: dict) -> dict:
    result = {
        "dispatch": {
            "owner": process_state(control["dispatch"].get("owner")),
            "child": process_state(control["dispatch"].get("child")),
        }
    }
    for attempt in control["attempts"]:
        if attempt["phase"] in ACTIVE_PHASES:
            result[attempt["id"]] = {
                "owner": process_state(attempt.get("owner")),
                "child": group_state(attempt.get("child")),
            }
    return result


def _evidence_bindings(control: dict) -> dict:
    """Bind exports to the execution facts in the captured control document."""
    bindings = {}
    for participant_id, participant in control["participant_specs"].items():
        identity = {
            "run_id": control["run_id"],
            "participant_id": participant_id,
            "harness": (participant.get("spec") or {}).get("harness"),
        }
        for attempt in control["attempts"]:
            if attempt["participant_id"] == participant_id and attempt.get("turn_file"):
                bindings[attempt["turn_file"]] = (
                    {**identity, "turn_id": attempt["id"]},
                    attempt.get("outcome") or {},
                )
        disposition = control["dispatch"]["participants"].get(participant_id, {})
        if disposition.get("kind") == "blocked" and disposition.get("turn_file"):
            path = disposition["turn_file"]
            bindings[path] = (
                {**identity, "turn_id": Path(path).stem},
                {"status": "failed", "error_type": "dependency"},
            )
    return bindings


def _validate_evidence(record: dict, binding: tuple[dict, dict]) -> dict:
    identity, outcome = binding
    if any(record.get(key) != value for key, value in identity.items()):
        raise ValueError("turn evidence belongs to another execution")
    execution = record.get("execution")
    if not isinstance(execution, dict):
        raise ValueError("invalid execution evidence")
    # Ensure the export can actually be reconstructed by the public result reader.
    SettledTurn(**execution)
    if any(
        not isinstance(execution.get(key), str)
        for key in ("participant_id", "harness", "status", "artifact_file", "log_file")
    ) or any(
        not isinstance(execution.get(key, {}), dict)
        for key in ("usage", "adapter_metadata")
    ):
        raise ValueError("invalid execution evidence fields")
    if any(execution[key] != identity[key] for key in ("participant_id", "harness")):
        raise ValueError("execution evidence belongs to another participant")
    if any(
        execution.get(key) != outcome[key]
        for key in ("status", "error_type", "error")
        if key in outcome
    ):
        raise ValueError("turn evidence contradicts the recorded outcome")
    return execution


def capture(control: dict) -> Snapshot:
    observations = observe(control)
    view = run_view(control, observations)
    bindings = _evidence_bindings(control)
    records = {}
    for state in view["participant_state"].values():
        for path in state["turns"]:
            try:
                record = read_json(Path(path))
                execution = _validate_evidence(record, bindings[path])
                artifact = execution.get("artifact_file")
                record["_artifact_readable"] = False
                if artifact and Path(artifact).is_file():
                    with Path(artifact).open("rb"):
                        record["_artifact_readable"] = True
                records[path] = record
            except (OSError, ValueError, TypeError, KeyError):
                records[path] = None
    assessment = assessment_snapshot(control, view["participant_state"], records)
    return Snapshot(control, observations, records, view, assessment)
