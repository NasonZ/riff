"""One owner for reservation, observations and guarded terminal commit."""

from __future__ import annotations

import uuid
from dataclasses import dataclass, replace
from pathlib import Path
from .evidence import (
    file_position,
    native_episode,
    native_position,
    native_rows,
    native_transcript,
    checkout_fingerprint,
)
from .models import (
    DEFAULT_TIMEOUT_SECONDS,
    ParticipantSpec,
    SettledTurn,
    TurnRequest,
    ValidationError,
)
from .process import group_state, identity, native_launch_model
from .adapters.base import HarnessAdapter
from .snapshot import capture
from .state import sha256_file, sha256_text, utc_now
from .views import ACTIVE_PHASES, attempts_for, check_budget, recovery_error


def current_attempt(
    control: dict, participant_id: str, attempt_id: str, token: str
) -> dict | None:
    attempts = attempts_for(control, participant_id)
    if not attempts:
        return None
    attempt = attempts[-1]
    if (
        attempt["id"] != attempt_id
        or attempt.get("owner_token") != token
        or attempt["phase"] not in {"reserved", "running"}
    ):
        return None
    return attempt


def observe(
    store,
    run_id: str,
    participant_id: str,
    attempt_id: str,
    token: str,
    *,
    child: dict | None = None,
    session_id: str | None = None,
    session_ref: str | None = None,
    baseline: dict | None = None,
) -> None:
    with store.mutation(run_id) as control:
        attempt = current_attempt(control, participant_id, attempt_id, token)
        if attempt is None:
            raise RuntimeError(
                "attempt ownership changed; refusing late observation or launch"
            )
        if child is not None:
            if attempt["phase"] != "reserved":
                raise RuntimeError("attempt already launched")
            attempt.update(phase="running", child=child)
        if baseline is not None:
            attempt["baseline"] = baseline
        participant = control["participant_specs"][participant_id]
        if (
            session_id is not None
            and session_id != participant.get("native_session_id")
            and session_ref is None
        ):
            participant["native_session_ref"] = None
            attempt["native_session_ref"] = None
        for field, value in (
            ("native_session_id", session_id),
            ("native_session_ref", session_ref),
        ):
            if value is not None:
                participant[field] = value
                attempt[field] = value


def terminal_record(
    store,
    turn: TurnRequest,
    result: SettledTurn,
    attempt: dict | None,
    native_evidence: dict | None = None,
) -> Path:
    artifact, log = Path(turn.artifact_path), Path(turn.log_path)
    if (
        Path(result.artifact_file).resolve() != artifact.resolve()
        or Path(result.log_file).resolve() != log.resolve()
    ):
        raise ValidationError(
            "adapter returned an artifact or log outside its assigned path"
        )
    if not artifact.exists():
        artifact.write_text("")
    if not log.exists():
        log.write_text(result.error or "")
    return store.write_turn(
        turn.run_id,
        turn.turn_id,
        {
            "schema_version": 2,
            "run_id": turn.run_id,
            "turn_id": turn.turn_id,
            "attempt_id": turn.turn_id if attempt else None,
            "participant_id": turn.participant.id,
            "harness": turn.participant.harness,
            "continued": turn.is_reply,
            "started_at": (attempt or {}).get("started_at"),
            "settled_at": utc_now(),
            "driver_session": (attempt or {}).get("driver_session"),
            "native_transcript": native_evidence,
            "request": {
                "prompt_digest": sha256_text(turn.prompt),
                "cwd": turn.participant.cwd,
                "tools": turn.participant.tools,
                "checkout_at_settle": checkout_fingerprint(turn.participant.cwd),
            },
            "execution": result.to_dict(),
            "artifact_sha256": sha256_file(artifact),
            "recorded_at": utc_now(),
        },
    )


@dataclass
class Reservation:
    turn: TurnRequest
    token: str
    attempt: dict
    adapter: HarnessAdapter


def _reserve(
    store,
    adapters,
    run_id,
    participant_id,
    prompt,
    *,
    depth,
    timeout_seconds,
    is_reply,
    extend_rounds,
    driver_session,
) -> Reservation:
    with store.mutation(run_id) as control:
        snapshot = capture(control)
        if participant_id not in control["participant_specs"]:
            raise ValidationError(
                f"participant {participant_id!r} is not in run {run_id}"
            )
        state = snapshot.view["participant_state"][participant_id]
        participant = ParticipantSpec.from_dict(
            state["spec"], default_cwd=state["spec"]["cwd"]
        )
        adapter = adapters.get(participant.harness)
        if adapter is None:
            raise ValidationError(
                f"adapter for harness {participant.harness!r} is unavailable"
            )
        previous = attempts_for(control, participant_id)
        latest = previous[-1] if previous else None
        if latest and latest["phase"] in ACTIVE_PHASES:
            problem = recovery_error(latest, snapshot.observations)
            if problem:
                raise ValidationError(
                    f"participant {participant_id} still has a running turn or interrupted owner: {problem}"
                )
        if is_reply and not state.get("native_session_id"):
            raise ValidationError(
                f"participant {participant_id} has no resumable native session"
            )
        maximum = control["coordination"]["max_rounds"]
        if is_reply and state["settled_turns"] >= maximum and extend_rounds:
            new_max = min(20, maximum + extend_rounds)
            control["coordination"]["max_rounds"] = new_max
            control.setdefault("round_extensions", []).append(
                {
                    "participant": participant_id,
                    "from": maximum,
                    "to": new_max,
                    "at": utc_now(),
                }
            )
            maximum = new_max
        check_budget(state, maximum)
        if latest and latest["phase"] in ACTIVE_PHASES:
            latest.update(
                phase="finished",
                outcome={
                    "status": "interrupted",
                    "error_type": "interrupted",
                    "error": "owner exited before terminal commit",
                },
                settled_at=utc_now(),
            )
        turn_id = (
            f"{participant_id}-{state['turn_count'] + 1:03d}-{uuid.uuid4().hex[:8]}"
        )
        token = uuid.uuid4().hex
        bound = (
            timeout_seconds
            if timeout_seconds is not None
            else state.get("timeout_seconds", DEFAULT_TIMEOUT_SECONDS)
        )
        attempt = {
            "id": turn_id,
            "participant_id": participant_id,
            "ordinal": state["turn_count"] + 1,
            "owner_token": token,
            "owner": identity(),
            "phase": "reserved",
            "launch_model": native_launch_model(),
            "continued": is_reply,
            "prompt_digest": sha256_text(prompt),
            "started_at": utc_now(),
            "native_session_id": state.get("native_session_id"),
            "native_session_ref": state.get("native_session_ref"),
            "driver_session": driver_session,
            "timeout_seconds": bound,
            "artifact_file": str(store.artifact_path(run_id, turn_id)),
            "log_file": str(store.log_path(run_id, turn_id)),
            "baseline": {},
        }
        control["attempts"].append(attempt)
        if not is_reply:
            control["dispatch"]["participants"][participant_id] = {
                "kind": "attempted",
                "attempt_id": turn_id,
            }
    turn = TurnRequest(
        run_id=run_id,
        turn_id=turn_id,
        participant=participant,
        prompt=prompt,
        timeout_seconds=bound,
        artifact_path=attempt["artifact_file"],
        log_path=attempt["log_file"],
        state_path=str(store.native_state_path(run_id, participant_id)),
        depth=depth,
        is_reply=is_reply,
        launch_model=attempt["launch_model"],
        native_session_id=attempt.get("native_session_id"),
        native_session_ref=attempt.get("native_session_ref"),
        observe_process=lambda child: observe(
            store, run_id, participant_id, turn_id, token, child=child
        ),
        observe_session=lambda sid, ref: observe(
            store,
            run_id,
            participant_id,
            turn_id,
            token,
            session_id=sid,
            session_ref=ref,
        ),
    )
    return Reservation(turn, token, attempt, adapter)


def _run_reserved(
    store, reservation: Reservation
) -> tuple[SettledTurn, Exception | None]:
    turn, attempt, token = reservation.turn, reservation.attempt, reservation.token
    run_id, participant = turn.run_id, turn.participant
    participant_id, turn_id = participant.id, turn.turn_id
    adapter = reservation.adapter
    execution_error = None
    try:
        baseline = {
            "transcript": file_position(
                native_transcript(
                    adapter, turn.native_session_id, turn.native_session_ref
                )
            ),
            "position": native_position(
                adapter, turn.native_session_id, turn.native_session_ref
            ),
        }
        observe(store, run_id, participant_id, turn_id, token, baseline=baseline)
        attempt["baseline"] = baseline
        result = adapter.execute(turn)
    except Exception as error:
        execution_error = error
        if not Path(turn.artifact_path).exists():
            Path(turn.artifact_path).write_text("")
        with Path(turn.log_path).open("a") as log:
            log.write(f"\n{type(error).__name__}: {error}")
        result = SettledTurn(
            participant_id,
            participant.harness,
            "failed",
            turn.artifact_path,
            turn.log_path,
            native_session_id=turn.native_session_id,
            native_session_ref=turn.native_session_ref,
            model=participant.model,
            provider=participant.provider,
            error_type="adapter",
            error=str(error),
        )
    return result, execution_error


def _finish(
    store,
    reservation: Reservation,
    result: SettledTurn,
    execution_error: Exception | None,
) -> SettledTurn:
    turn, attempt, token = reservation.turn, reservation.attempt, reservation.token
    run_id, participant = turn.run_id, turn.participant
    participant_id, turn_id = participant.id, turn.turn_id
    adapter = reservation.adapter
    observed_control = store.read_control(run_id)
    known = next(
        (a for a in observed_control["attempts"] if a["id"] == turn_id), attempt
    )
    result = replace(
        result,
        native_session_id=result.native_session_id or known.get("native_session_id"),
        native_session_ref=result.native_session_ref
        or (
            known.get("native_session_ref")
            if result.native_session_id in {None, known.get("native_session_id")}
            else None
        ),
    )
    native_evidence = native_episode(
        adapter, turn, result, attempt["baseline"].get("transcript")
    ) or native_rows(adapter, turn, result, attempt["baseline"].get("position"))
    path = terminal_record(store, turn, result, attempt, native_evidence)
    # Evidence export precedes the guarded control commit. A crash here leaves
    # the attempt interrupted rather than promoting an uncommitted success.
    with store.mutation(run_id) as control:
        current = current_attempt(control, participant_id, turn_id, token)
        if current is None:
            for own in control["attempts"]:
                if own["id"] == turn_id:
                    own.setdefault("diagnostics", []).append(
                        {"late_terminal_file": str(path), "at": utc_now()}
                    )
                    break
        elif result.adapter_metadata.get("cleanup_unproven", False) or (
            execution_error is not None
            and (
                current.get("launch_model") != "exec-gated"
                or (current.get("child") and group_state(current["child"]) != "gone")
            )
        ):
            # A supervisor failure cannot certify that its child/tools ended.
            # Keep ownership active; after this process exits, recovery must
            # still prove that the recorded process group has gone.
            current.setdefault("diagnostics", []).append(
                {
                    "terminal_file": str(path),
                    "cleanup_unproven": True,
                    "error": str(execution_error),
                    "at": utc_now(),
                }
            )
        else:
            current.update(
                phase="finished",
                outcome={
                    "status": result.status,
                    "error_type": result.error_type,
                    "error": result.error,
                },
                turn_file=str(path),
                settled_at=utc_now(),
            )
            participant_state = control["participant_specs"][participant_id]
            if result.native_session_id is not None:
                if (
                    result.native_session_id
                    != participant_state.get("native_session_id")
                    and result.native_session_ref is None
                ):
                    participant_state["native_session_ref"] = None
                participant_state["native_session_id"] = result.native_session_id
            if result.native_session_ref is not None:
                participant_state["native_session_ref"] = result.native_session_ref
    return result


def execute(
    store,
    adapters: dict,
    run_id: str,
    participant_id: str,
    prompt: str,
    *,
    depth: int,
    timeout_seconds: int | None = None,
    is_reply: bool = False,
    extend_rounds: int | None = None,
    driver_session: dict | None = None,
) -> SettledTurn:
    """The sole execution entry point; participant ownership spans the whole turn."""
    with store.participant_lock(run_id, participant_id):
        reservation = _reserve(
            store,
            adapters,
            run_id,
            participant_id,
            prompt,
            depth=depth,
            timeout_seconds=timeout_seconds,
            is_reply=is_reply,
            extend_rounds=extend_rounds,
            driver_session=driver_session,
        )
        result, error = _run_reserved(store, reservation)
        return _finish(store, reservation, result, error)
