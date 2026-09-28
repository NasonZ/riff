"""Driver-mediated orchestration for Riff runs."""

from __future__ import annotations

import json
import os
import re
import subprocess
import time
import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import asdict, replace
from pathlib import Path
from typing import Any

from .adapters import adapter_registry
from .adapters.base import HarnessAdapter
from .models import (
    DEFAULT_TIMEOUT_SECONDS,
    ParticipantSpec,
    RunRequest,
    SettledTurn,
    TurnRequest,
    ValidationError,
    request_warnings,
)
from .state import RunStore, default_state_root, sha256_file, sha256_text, utc_now

RIFF_SCRIPT = Path(__file__).resolve().parent.parent / "riff.py"
UNVERIFIED_LOOKBACK_SECONDS = 7 * 24 * 3600
UNVERIFIED_LIMIT = 5
VERIFY_OUTPUT_TAIL_CHARS = 2000  # enough to show a failing assertion without copying a whole log
DEFAULT_WAIT_SECONDS = 540  # under the ~10 min per-call limit common to agent shells
ATTEMPT_FACTOR = 2  # failed turns allowed per round before a participant is considered broken


class Coordinator:
    """Coordinate peer sessions while keeping the current harness as driver."""

    def __init__(
        self,
        *,
        store: RunStore | None = None,
        adapters: dict[str, HarnessAdapter] | None = None,
    ) -> None:
        self.store = store or RunStore()
        self.adapters = adapters or adapter_registry()

    def capabilities(self) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for name, adapter in self.adapters.items():
            try:
                result[name] = adapter.capability()
            except (OSError, RuntimeError, ValueError) as error:
                result[name] = {"harness": name, "available": False, "error": str(error)}
        return {"schema_version": 1, "harnesses": result}

    def validate(self, request: RunRequest) -> RunRequest:
        """Validate shared and adapter-specific request semantics without launching."""
        self._validate_request_capabilities(request)
        for participant in request.participants:
            probe = TurnRequest(
                run_id="00000000-0000-0000-0000-000000000000",
                turn_id=f"{participant.id}-validation",
                participant=participant,
                prompt=request.task,
                timeout_seconds=request.timeout_seconds,
                artifact_path="",
                log_path="",
                state_path="",
                depth=request.depth,
            )
            self.adapters[participant.harness].validate(probe)
        return request

    def warnings(self, request: RunRequest) -> list[dict[str, str]]:
        """Lint a valid request for patterns that tend to waste or bias a run."""
        return request_warnings(request)

    def run(self, request: RunRequest, *, run_id: str | None = None) -> dict[str, Any]:
        request = self._apply_parent_environment(request)
        self.validate(request)
        warnings = self.warnings(request)
        run_id = run_id or str(uuid.uuid4())
        created_at = utc_now()
        manifest = {
            "schema_version": 1,
            "run_id": run_id,
            "parent_run_id": request.parent_run_id,
            "depth": request.depth,
            "origin_harness": request.origin_harness,
            "mode": request.mode,
            "coordination": asdict(request.coordination),
            "request": {
                "task_digest": sha256_text(request.task),
                "driver_position": request.driver_position,
                "driver_prediction": request.driver_prediction,
                "context_refs": list(request.context_refs),
                "constraints": list(request.constraints),
                "out_of_scope": list(request.out_of_scope),
                "acceptance_criteria": list(request.acceptance_criteria),
            },
            "participants": [participant.id for participant in request.participants],
            "checkouts_at_dispatch": {
                participant.id: _checkout_fingerprint(participant.cwd)
                for participant in request.participants
            },
            "warnings": warnings,
            "created_at": created_at,
            "updated_at": created_at,
            "status": "running",
            "result": "pending",
            "verification": {
                "performed": False,
                "verifier": None,
                "checks": [],
                "result": "pending",
                "integrated": False,
                "view_changed": None,
            },
        }
        self.store.create(run_id, manifest)
        for participant in request.participants:
            self.store.write_participant(
                run_id,
                participant.id,
                {
                    "schema_version": 1,
                    "run_id": run_id,
                    "participant_id": participant.id,
                    "spec": asdict(participant),
                    "native_session_id": None,
                    "native_session_ref": None,
                    "turn_count": 0,
                    "turns": [],
                    "status": "pending",
                },
            )
        try:
            if request.coordination.dispatch == "pipeline":
                results = self._run_pipeline(run_id, request)
            else:
                results = self._run_parallel(run_id, request)
        except BaseException as error:
            with self.store.run_lock(run_id):
                manifest = self.store.read_manifest(run_id)
                manifest["updated_at"] = utc_now()
                manifest["status"] = "failed"
                manifest["result"] = "failed"
                manifest["fatal_error"] = {
                    "type": type(error).__name__,
                    "message": str(error),
                }
                self.store.write_manifest(run_id, manifest)
            raise
        with self.store.run_lock(run_id):
            manifest = self.store.read_manifest(run_id)
            manifest["updated_at"] = utc_now()
            manifest["status"] = "settled"
            manifest["result"] = _aggregate_result(results)
            self.store.write_manifest(run_id, manifest)
        public = self._public_result(run_id, results)
        public["warnings"] = warnings
        public["unverified_runs"] = self._unverified_runs(
            request.origin_harness, exclude=run_id
        )
        return public

    def reply(
        self,
        run_id: str,
        participant_id: str,
        prompt: str,
        *,
        timeout_seconds: int | None = None,
    ) -> dict[str, Any]:
        if not prompt.strip():
            raise ValidationError("reply prompt must not be empty")
        if timeout_seconds is not None and (
            not isinstance(timeout_seconds, int)
            or isinstance(timeout_seconds, bool)
            or not 1 <= timeout_seconds <= 86400
        ):
            raise ValidationError("reply timeout_seconds must be between 1 and 86400")
        with self.store.participant_lock(run_id, participant_id):
            manifest = self.store.read_manifest(run_id)
            participant_state = self.store.read_participant(run_id, participant_id)
            participant = ParticipantSpec.from_dict(
                participant_state["spec"], default_cwd=participant_state["spec"]["cwd"]
            )
            max_rounds = int(manifest["coordination"]["max_rounds"])
            turn_count = int(participant_state.get("turn_count", 0))
            # Rounds budget the conversation, so only settled turns spend one; a
            # timed-out or quota-failed turn being recovered does not. Attempts are
            # still capped so a broken peer cannot loop forever.
            settled_turns = int(participant_state.get("settled_turns", turn_count))
            if settled_turns >= max_rounds:
                raise ValidationError(
                    f"participant {participant_id} reached max_rounds={max_rounds} "
                    "settled turns; synthesize, or start a new run if more rounds are needed"
                )
            if turn_count >= ATTEMPT_FACTOR * max_rounds:
                raise ValidationError(
                    f"participant {participant_id} reached {turn_count} attempts "
                    f"({ATTEMPT_FACTOR} x max_rounds); fix the failure cause before retrying"
                )
            active = participant_state.get("active_turn") or {}
            if participant_state.get("status") == "running" and _process_alive(
                active.get("coordinator_pid")
            ):
                started = active.get("started_at")
                raise ValidationError(
                    f"participant {participant_id} still has a running turn (started {started}); "
                    "wait for run to return, or inspect it with riff.py progress"
                )
            native_session_id = participant_state.get("native_session_id")
            if not native_session_id:
                raise ValidationError(
                    f"participant {participant_id} has no resumable native session"
                )
            turn = self._turn_request(
                run_id,
                participant,
                prompt,
                timeout_seconds=(
                    timeout_seconds
                    if timeout_seconds is not None
                    else int(participant_state.get("timeout_seconds", DEFAULT_TIMEOUT_SECONDS))
                ),
                turn_number=turn_count + 1,
                depth=int(manifest.get("depth", 0)),
                is_reply=True,
                native_session_id=str(native_session_id),
                native_session_ref=participant_state.get("native_session_ref"),
            )
            self._mark_turn_running(run_id, participant, turn)
            try:
                result = self._execute_turn(turn)
            except Exception as error:
                result = self._adapter_failure(participant, turn, error)
            self._record_turn(run_id, participant, turn, result)
        with self.store.run_lock(run_id):
            manifest = self.store.read_manifest(run_id)
            manifest["updated_at"] = utc_now()
            participant_statuses = self._participant_statuses(run_id, manifest)
            if "running" in participant_statuses:
                manifest["status"] = "running"
            else:
                manifest["status"] = "settled"
                manifest["result"] = _aggregate_statuses(participant_statuses)
            self.store.write_manifest(run_id, manifest)
        return self._public_result(run_id, [result])

    def status(self, run_id: str) -> dict[str, Any]:
        manifest = self.store.read_manifest(run_id)
        participants = {
            participant_id: self.store.read_participant(run_id, participant_id)
            for participant_id in manifest["participants"]
        }
        return {"manifest": manifest, "participant_state": participants}

    def wait(
        self,
        run_id: str,
        *,
        timeout_seconds: int = DEFAULT_WAIT_SECONDS,
        poll_seconds: float = 5.0,
    ) -> dict[str, Any]:
        """Block until a run settles or the bound passes, whichever is first.

        The bound sits under common agent tool-call limits, so a driver that cannot
        keep a background task alive (a non-interactive session) can follow a long
        run through repeated bounded calls instead of losing it."""
        if not 1 <= timeout_seconds <= 3600:
            raise ValidationError("wait timeout must be between 1 and 3600 seconds")
        deadline = time.monotonic() + timeout_seconds
        while True:
            state = self._settled_state(run_id)
            if state == "settled":
                return self.result(run_id)
            if state == "failed-to-start" or time.monotonic() >= deadline:
                break
            time.sleep(poll_seconds)
        if state == "failed-to-start":
            detached = self.store.root / "detached" / f"{run_id}.err"
            raise ValidationError(
                f"run {run_id} never started: "
                + (detached.read_text()[-2000:] if detached.is_file() else "no run record")
            )
        return {
            "ok": False,
            "run_id": run_id,
            "status": "running",
            "next_steps": [
                f"Still running; call {self.script_invocation()} wait --run-id {run_id} again."
            ],
        }

    def result(self, run_id: str) -> dict[str, Any]:
        """Rebuild the public result of a settled run from its latest turn records."""
        manifest = self.store.read_manifest(run_id)
        latest: list[SettledTurn] = []
        for participant_id in manifest["participants"]:
            turns = self.store.read_participant(run_id, participant_id).get("turns") or []
            if turns:
                execution = json.loads(Path(turns[-1]).read_text())["execution"]
                latest.append(SettledTurn(**execution))
        public = self._public_result(run_id, latest)
        public["status"] = manifest.get("status")
        public["warnings"] = manifest.get("warnings") or []
        return public

    def _settled_state(self, run_id: str) -> str:
        if not self.store.manifest_path(run_id).is_file():
            detached = self.store.root / "detached" / f"{run_id}.err"
            pid_file = self.store.root / "detached" / f"{run_id}.pid"
            if pid_file.is_file() and not _process_alive(int(pid_file.read_text() or 0)):
                return "failed-to-start"
            if not pid_file.is_file() and not detached.is_file():
                raise ValidationError(f"unknown run id: {run_id}")
            return "starting"
        manifest = self.store.read_manifest(run_id)
        return "settled" if manifest.get("status") in {"settled", "failed"} else "running"

    def progress(
        self,
        run_id: str,
        *,
        participant_id: str | None = None,
        include_previews: bool = False,
    ) -> dict[str, Any]:
        manifest = self.store.read_manifest(run_id)
        selected = [participant_id] if participant_id else list(manifest["participants"])
        progress: dict[str, Any] = {}
        for current_id in selected:
            state = self.store.read_participant(run_id, current_id)
            item: dict[str, Any] = {
                "status": state.get("status"),
                "turn_count": state.get("turn_count", 0),
                "native_session_id": state.get("native_session_id"),
                "active_turn": state.get("active_turn"),
                "turns": state.get("turns", []),
            }
            spec = state.get("spec") or {}
            if spec.get("harness") == "pi":
                active_log = (state.get("active_turn") or {}).get("log_file")
                log_files = (
                    [Path(active_log)]
                    if active_log and Path(active_log).is_file()
                    else sorted(
                        (self.store.run_dir(run_id) / "logs").glob(
                            f"{current_id}-*.log"
                        ),
                        key=lambda path: path.stat().st_mtime,
                    )
                )
                if log_files and log_files[-1].is_file():
                    item["live_rpc"] = _pi_rpc_progress(
                        log_files[-1], include_previews=include_previews
                    )
                session_ref = state.get("native_session_ref")
                if not session_ref:
                    native_root = (
                        self.store.run_dir(run_id) / "participants" / current_id / "sessions"
                    )
                    sessions = sorted(
                        native_root.glob("*.jsonl"),
                        key=lambda path: path.stat().st_mtime,
                    )
                    session_ref = str(sessions[-1]) if sessions else None
                if session_ref and Path(session_ref).is_file():
                    item["live_trace"] = _pi_progress(
                        Path(session_ref), include_previews=include_previews
                    )
            progress[current_id] = item
        return {
            "run_id": run_id,
            "status": manifest["status"],
            "result": manifest["result"],
            "participants": progress,
        }

    def verify(
        self,
        run_id: str,
        *,
        verifier: str,
        result: str | None,
        checks: list[str],
        integrated: bool,
        note: str | None = None,
        commands: list[str] | None = None,
        cwd: str | None = None,
        command_timeout_seconds: int = 600,
        view_changed: bool | None = None,
    ) -> dict[str, Any]:
        """Record verification. Commands are executed and their exit codes recorded;
        free-text checks are recorded as asserted, never as executed."""
        commands = [command for command in (commands or []) if command.strip()]
        if result is not None and result not in {
            "passed",
            "partial",
            "failed",
            "not_performed",
        }:
            raise ValidationError(
                "verification result must be passed, partial, failed, or not_performed"
            )
        if result is None and not commands:
            raise ValidationError(
                "result is required without an executed check; pass --run <command> to "
                "derive it, or --result not_performed if nothing was checked"
            )
        if result == "not_performed" and (checks or commands):
            raise ValidationError("not_performed verification cannot include checks")
        if result not in {None, "not_performed"} and not (checks or commands):
            raise ValidationError(f"{result} verification requires at least one check")
        if not 1 <= command_timeout_seconds <= 86400:
            raise ValidationError("command timeout must be between 1 and 86400 seconds")
        manifest = self.store.read_manifest(run_id)
        if manifest.get("status") != "settled":
            raise ValidationError("verification requires a settled run")
        if commands:
            if cwd is None:
                first = self.store.read_participant(run_id, manifest["participants"][0])
                cwd = first["spec"]["cwd"]
            cwd = str(Path(cwd).expanduser().resolve())
            if not Path(cwd).is_dir():
                raise ValidationError(f"verification cwd does not exist: {cwd}")
        executed = [
            self._execute_check(run_id, index, command, cwd, command_timeout_seconds)
            for index, command in enumerate(commands, start=1)
        ]
        derived = _derive_verification(executed)
        if result is None:
            result = derived
        elif result == "passed" and derived in {"failed", "partial"}:
            failing = next(check for check in executed if not check["passed"])
            raise ValidationError(
                f"result passed contradicts executed check {failing['command']!r} "
                f"({_describe_exit(failing)}); record failed or partial, or fix and rerun"
            )
        recorded = [{"kind": "asserted", "text": text} for text in checks] + executed
        with self.store.run_lock(run_id):
            manifest = self.store.read_manifest(run_id)
            prior = manifest.get("verification") or {}
            if prior.get("verified_at"):
                manifest.setdefault("verification_history", []).append(prior)
            manifest["verification"] = {
                "performed": result != "not_performed",
                "verifier": verifier,
                "checks": recorded,
                "result": result,
                "integrated": integrated,
                "view_changed": view_changed,
                "note": note,
                "verified_at": utc_now(),
            }
            manifest["updated_at"] = utc_now()
            self.store.write_manifest(run_id, manifest)
        return {
            "ok": True,
            "run_id": run_id,
            "result": result,
            "checks": recorded,
            "manifest_file": str(self.store.manifest_path(run_id)),
        }

    def _execute_check(
        self, run_id: str, index: int, command: str, cwd: str, timeout_seconds: int
    ) -> dict[str, Any]:
        output_file = self.store.run_dir(run_id) / "verification" / f"check-{index:02d}.log"
        output_file.parent.mkdir(parents=True, exist_ok=True)
        started = time.monotonic()
        try:
            completed = subprocess.run(
                ["/bin/sh", "-c", command],
                cwd=cwd,
                capture_output=True,
                text=True,
                timeout=timeout_seconds,
                stdin=subprocess.DEVNULL,
            )
            exit_code: int | None = completed.returncode
            output = "\n".join(part for part in (completed.stdout, completed.stderr) if part)
            timed_out = False
        except subprocess.TimeoutExpired as error:
            exit_code = None
            output = "\n".join(
                part.decode() if isinstance(part, bytes) else part
                for part in (error.stdout, error.stderr)
                if part
            )
            timed_out = True
        output_file.write_text(output)
        return {
            "kind": "executed",
            "command": command,
            "cwd": cwd,
            "exit_code": exit_code,
            "timed_out": timed_out,
            "passed": exit_code == 0,
            "elapsed_ms": round((time.monotonic() - started) * 1000),
            "output_file": str(output_file),
            "output_sha256": sha256_file(output_file),
            "output_tail": output[-VERIFY_OUTPUT_TAIL_CHARS:],
        }

    def _apply_parent_environment(self, request: RunRequest) -> RunRequest:
        parent = os.environ.get("RIFF_RUN_ID")
        inherited_depth = os.environ.get("RIFF_DEPTH")
        if not parent:
            return request
        try:
            parsed_parent = uuid.UUID(parent)
        except ValueError as error:
            raise ValidationError("RIFF_RUN_ID must be a canonical UUID") from error
        if str(parsed_parent) != parent.lower():
            raise ValidationError("RIFF_RUN_ID must be a canonical UUID")
        try:
            depth = int(inherited_depth or request.depth + 1)
        except ValueError as error:
            raise ValidationError("RIFF_DEPTH must be an integer") from error
        if depth < 1:
            raise ValidationError("nested RIFF_DEPTH must be positive")
        if depth >= request.coordination.max_depth:
            raise ValidationError(
                f"recursive Riff invocation depth {depth} reaches max_depth "
                f"{request.coordination.max_depth}"
            )
        return replace(request, parent_run_id=parent.lower(), depth=depth)

    def _validate_request_capabilities(self, request: RunRequest) -> None:
        unknown = sorted(
            {participant.harness for participant in request.participants} - set(self.adapters)
        )
        if unknown:
            raise ValidationError("unsupported harnesses: " + ", ".join(unknown))
        if request.coordination.dispatch == "pipeline":
            for participant in request.participants[1:]:
                if participant.tools == "none":
                    raise ValidationError(
                        "pipeline participants after the first need read or write tools "
                        "to consume the prior artifact"
                    )

    def _run_parallel(self, run_id: str, request: RunRequest) -> list[SettledTurn]:
        results: list[SettledTurn] = []
        with ThreadPoolExecutor(max_workers=request.coordination.concurrency) as executor:
            futures = {}
            for participant in request.participants:
                prompt = self._initial_prompt(request, participant)
                turn = self._turn_request(
                    run_id,
                    participant,
                    prompt,
                    timeout_seconds=request.timeout_seconds,
                    turn_number=1,
                    depth=request.depth,
                )
                future = executor.submit(
                    self._execute_marked_turn, run_id, participant, turn
                )
                futures[future] = (participant, turn)
            for future in as_completed(futures):
                participant, turn = futures[future]
                try:
                    result = future.result()
                except Exception as error:  # adapter failures must remain visible
                    result = self._adapter_failure(participant, turn, error)
                self._record_turn(run_id, participant, turn, result)
                results.append(result)
        order = {participant.id: index for index, participant in enumerate(request.participants)}
        results.sort(key=lambda result: order[result.participant_id])
        return results

    def _run_pipeline(self, run_id: str, request: RunRequest) -> list[SettledTurn]:
        results: list[SettledTurn] = []
        previous: SettledTurn | None = None
        for participant in request.participants:
            prompt = self._initial_prompt(request, participant)
            turn = self._turn_request(
                run_id,
                participant,
                prompt,
                timeout_seconds=request.timeout_seconds,
                turn_number=1,
                depth=request.depth,
            )
            if previous is not None:
                if not previous.ok:
                    result = SettledTurn(
                        participant_id=participant.id,
                        harness=participant.harness,
                        status="failed",
                        artifact_file=turn.artifact_path,
                        log_file=turn.log_path,
                        error_type="dependency",
                        error=f"prior pipeline participant {previous.participant_id} failed",
                    )
                    Path(turn.artifact_path).write_text("")
                    Path(turn.log_path).write_text(result.error or "pipeline dependency failed")
                    self._record_turn(run_id, participant, turn, result)
                    results.append(result)
                    previous = result
                    continue
                prompt += (
                    "\n\nPipeline input\n"
                    f"The previous participant's artifact is at {previous.artifact_file}. "
                    "Read and use that artifact as declared by your task."
                )
                turn = replace(turn, prompt=prompt)
            try:
                self._mark_turn_running(run_id, participant, turn)
                result = self._execute_turn(turn)
            except Exception as error:
                result = self._adapter_failure(participant, turn, error)
            self._record_turn(run_id, participant, turn, result)
            results.append(result)
            previous = result
        return results

    def _adapter_failure(
        self, participant: ParticipantSpec, turn: TurnRequest, error: Exception
    ) -> SettledTurn:
        Path(turn.artifact_path).write_text("")
        Path(turn.log_path).write_text(f"{type(error).__name__}: {error}")
        return SettledTurn(
            participant_id=participant.id,
            harness=participant.harness,
            status="failed",
            artifact_file=turn.artifact_path,
            log_file=turn.log_path,
            native_session_id=turn.native_session_id,
            native_session_ref=turn.native_session_ref,
            model=participant.model,
            provider=participant.provider,
            error_type="adapter",
            error=str(error),
        )

    def _participant_statuses(
        self, run_id: str, manifest: dict[str, Any]
    ) -> list[str | None]:
        return [
            self.store.read_participant(run_id, participant_id).get("status")
            for participant_id in manifest["participants"]
        ]

    def _mark_turn_running(
        self, run_id: str, participant: ParticipantSpec, turn: TurnRequest
    ) -> None:
        state = self.store.read_participant(run_id, participant.id)
        state["status"] = "running"
        state["active_turn"] = {
            "turn_id": turn.turn_id,
            "continued": turn.is_reply,
            "log_file": turn.log_path,
            "started_at": utc_now(),
            "coordinator_pid": os.getpid(),
        }
        self.store.write_participant(run_id, participant.id, state)
        with self.store.run_lock(run_id):
            manifest = self.store.read_manifest(run_id)
            manifest["status"] = "running"
            manifest["updated_at"] = utc_now()
            self.store.write_manifest(run_id, manifest)

    def _execute_turn(self, turn: TurnRequest) -> SettledTurn:
        adapter = self.adapters[turn.participant.harness]
        return adapter.reply(turn) if turn.is_reply else adapter.start(turn)

    def _execute_marked_turn(
        self, run_id: str, participant: ParticipantSpec, turn: TurnRequest
    ) -> SettledTurn:
        self._mark_turn_running(run_id, participant, turn)
        return self._execute_turn(turn)

    def _turn_request(
        self,
        run_id: str,
        participant: ParticipantSpec,
        prompt: str,
        *,
        timeout_seconds: int,
        turn_number: int,
        depth: int,
        is_reply: bool = False,
        native_session_id: str | None = None,
        native_session_ref: str | None = None,
    ) -> TurnRequest:
        turn_id = f"{participant.id}-{turn_number:03d}-{uuid.uuid4().hex[:8]}"
        return TurnRequest(
            run_id=run_id,
            turn_id=turn_id,
            participant=participant,
            prompt=prompt,
            timeout_seconds=timeout_seconds,
            artifact_path=str(self.store.artifact_path(run_id, turn_id)),
            log_path=str(self.store.log_path(run_id, turn_id)),
            state_path=str(self.store.native_state_path(run_id, participant.id)),
            depth=depth,
            is_reply=is_reply,
            native_session_id=native_session_id,
            native_session_ref=native_session_ref,
        )

    def _initial_prompt(self, request: RunRequest, participant: ParticipantSpec) -> str:
        task = participant.task or request.task
        parts = [f"Mode: {request.mode}", f"Task\n{task}"]
        if participant.focus:
            parts.append(f"Focused attention\n{participant.focus}")
        if request.context_refs:
            parts.append("Context references\n" + "\n".join(f"- {item}" for item in request.context_refs))
        if request.driver_position == "provided" and request.driver_position_text:
            parts.append("Driver's current position\n" + request.driver_position_text)
        elif request.driver_position == "withheld":
            parts.append(
                "Independence\nThe driver has deliberately withheld its proposed answer. "
                "Form your view before comparison."
            )
        if request.constraints:
            parts.append("Constraints\n" + "\n".join(f"- {item}" for item in request.constraints))
        if request.out_of_scope:
            parts.append("Out of scope\n" + "\n".join(f"- {item}" for item in request.out_of_scope))
        if request.acceptance_criteria:
            parts.append(
                "Acceptance criteria\n"
                + "\n".join(f"- {item}" for item in request.acceptance_criteria)
            )
        authority = (
            f"Tool scope is {participant.tools}. Do not exceed it. "
            "Do not invoke Riff or another agent."
        )
        commands = participant.params.get("allowed_commands") or []
        if commands:
            # The permission rule matches by prefix, so the peer must know the exact
            # spelling (field: a peer ran python3 where python was allowed).
            authority += (
                " The only shell commands you may run are those beginning with: "
                + "; ".join(f"`{command}`" for command in commands)
                + ". Run them exactly as written, without cd, pipes, or chaining."
            )
        parts.append("Authority\n" + authority)
        parts.append(
            "Response\nReturn a self-contained artifact. Give each material claim its "
            "evidence (file:line, command and result, or source URL), or label it "
            "unverified. Surface assumptions and known gaps. If the framing is wrong, say "
            "so and propose the better question."
        )
        return "\n\n".join(parts)

    def _record_turn(
        self,
        run_id: str,
        participant: ParticipantSpec,
        turn: TurnRequest,
        result: SettledTurn,
    ) -> None:
        artifact_path = Path(turn.artifact_path)
        log_path = Path(turn.log_path)
        if Path(result.artifact_file).resolve() != artifact_path.resolve():
            raise ValidationError("adapter returned an artifact outside its assigned path")
        if Path(result.log_file).resolve() != log_path.resolve():
            raise ValidationError("adapter returned a log outside its assigned path")
        if not artifact_path.exists():
            artifact_path.write_text("")
        if not log_path.exists():
            log_path.write_text(result.error or "")
        turn_record = {
            "schema_version": 1,
            "run_id": run_id,
            "turn_id": turn.turn_id,
            "participant_id": participant.id,
            "harness": participant.harness,
            "continued": turn.is_reply,
            "request": {
                "prompt_digest": sha256_text(turn.prompt),
                "cwd": participant.cwd,
                "tools": participant.tools,
                "checkout_at_settle": _checkout_fingerprint(participant.cwd),
            },
            "execution": result.to_dict(),
            "artifact_sha256": sha256_file(artifact_path),
            "recorded_at": utc_now(),
        }
        turn_file = self.store.write_turn(run_id, turn.turn_id, turn_record)
        state = self.store.read_participant(run_id, participant.id)
        state["native_session_id"] = result.native_session_id
        state["native_session_ref"] = result.native_session_ref
        previous_turns = int(state.get("turn_count", 0))
        state["turn_count"] = previous_turns + 1
        state["settled_turns"] = int(state.get("settled_turns", previous_turns)) + int(result.ok)
        state["timeout_seconds"] = turn.timeout_seconds
        state["status"] = result.status
        state.pop("active_turn", None)
        state.setdefault("turns", []).append(str(turn_file))
        self.store.write_participant(run_id, participant.id, state)

    def _public_result(
        self, run_id: str, results: list[SettledTurn]
    ) -> dict[str, Any]:
        overall = self.store.read_manifest(run_id)["result"]
        participants = []
        notices = []
        for result in results:
            denied = sorted(
                {
                    str(item.get("tool_name") if isinstance(item, dict) else item)
                    for item in result.adapter_metadata.get("permission_denials") or []
                }
            )
            if denied:
                notices.append(
                    {
                        "code": "peer-tool-denied",
                        "message": (
                            f"{result.participant_id} was denied {', '.join(denied)}; its "
                            "artifact may lack that evidence. Check the artifact for the gap "
                            "and tell the user what the peer could not access."
                        ),
                    }
                )
            participants.append(
                {
                    "id": result.participant_id,
                    "harness": result.harness,
                    "ok": result.ok,
                    "status": result.status,
                    "session_id": result.native_session_id,
                    "artifact_file": result.artifact_file,
                    "elapsed_ms": result.elapsed_ms,
                    "cost_usd": result.adapter_metadata.get("cost_usd"),
                    "denied_tools": denied,
                    "error_type": result.error_type,
                    "error": result.error,
                    "authority_enforcement": result.authority_enforcement,
                }
            )
        return {
            "ok": bool(results) and all(result.ok for result in results),
            "run_id": run_id,
            "result": overall,
            "turn_result": _aggregate_result(results),
            "manifest_file": str(self.store.manifest_path(run_id)),
            "notices": notices,
            "participants": participants,
            "next_steps": _next_steps(run_id, results, notices, self.script_invocation()),
        }

    def script_invocation(self) -> str:
        """The riff.py command a driver can paste, pinned to this store's root."""
        command = f'python3 "{RIFF_SCRIPT}"'
        if self.store.root != default_state_root():
            command += f' --state-dir "{self.store.root}"'
        return command

    def _unverified_runs(self, origin: str, *, exclude: str) -> list[str]:
        """Recent settled runs from this driver harness with no verification record."""
        cutoff = time.time() - UNVERIFIED_LOOKBACK_SECONDS
        found: list[tuple[float, str]] = []
        for path in self.store.runs.glob("*/run.json"):
            if path.parent.name == exclude or path.stat().st_mtime < cutoff:
                continue
            try:
                manifest = json.loads(path.read_text())
            except (OSError, json.JSONDecodeError):
                continue
            if (
                manifest.get("origin_harness") == origin
                and manifest.get("status") == "settled"
                and (manifest.get("verification") or {}).get("result") == "pending"
            ):
                found.append((path.stat().st_mtime, path.parent.name))
        return [run_id for _, run_id in sorted(found, reverse=True)[:UNVERIFIED_LIMIT]]


def _aggregate_result(results: list[SettledTurn]) -> str:
    successes = sum(result.ok for result in results)
    if successes == len(results) and results:
        return "success"
    if successes:
        return "partial"
    return "failed"


def _checkout_fingerprint(cwd: str) -> dict[str, Any] | None:
    """HEAD and dirty-file count of a git checkout, so a reader of a peer's line
    citations can tell whether the files moved under it (field: reviews ran while the
    driver edited the same checkout). None outside git."""
    try:
        head = subprocess.run(
            ["git", "-C", cwd, "rev-parse", "HEAD"],
            capture_output=True, text=True, timeout=10,
        )
        if head.returncode != 0:
            return None
        status = subprocess.run(
            ["git", "-C", cwd, "status", "--porcelain"],
            capture_output=True, text=True, timeout=30,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    return {
        "head": head.stdout.strip(),
        "dirty_files": len([line for line in status.stdout.splitlines() if line.strip()]),
    }


def _process_alive(pid: Any) -> bool:
    """A turn marked running by a coordinator that has since died is interrupted,
    not running; it must not block recovery of the native session."""
    if not isinstance(pid, int):
        return True  # records from before the pid was stored: stay conservative
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def _next_steps(
    run_id: str, results: list[SettledTurn], notices: list[dict[str, str]], script: str
) -> list[str]:
    """Driver obligations carried in the tool output itself, because the skill text
    can fall out of a driver's context after compaction (field evidence: recorded
    verification went from 3 of 5 runs to 0 of 45 after one compaction)."""
    steps = ["Read each artifact_file in full; this summary is not the peer's answer."]
    steps.extend(notice["message"] for notice in notices)
    for result in results:
        if result.error_type == "timeout" and result.native_session_id:
            # A reply inherits the previous timeout; recovering under the same bound
            # that just expired fails again (field: two 8 s replies after an 8 s timeout).
            match = re.search(r"after (\d+) seconds", result.error or "")
            previous = int(match.group(1)) if match else DEFAULT_TIMEOUT_SECONDS
            longer = max(DEFAULT_TIMEOUT_SECONDS, 2 * previous)
            steps.append(
                f"{result.participant_id} timed out but its session survives: {script} reply "
                f"--run-id {run_id} --participant {result.participant_id} "
                f"--timeout-seconds {min(longer, 86400)} --prompt "
                "'Stop exploring and write your final answer now.' (failed turns do not "
                "spend max_rounds)"
            )
        elif result.error_type == "rate_limit":
            steps.append(
                f"{result.participant_id} hit a usage limit ({result.error}); wait for the "
                "stated reset or choose another peer. Retrying now will fail the same way."
            )
        elif result.error_type == "auth":
            steps.append(
                f"{result.participant_id} failed authentication; fix that harness's "
                "credentials or model configuration before retrying, and tell the user."
            )
    steps.append(
        "Verify decisive claims before relying on them, then record it: "
        f"{script} verify --run-id {run_id} --verifier <driver> --run '<test command>' "
        "--check '<what you inspected>' [--view-changed yes|no] [--integrated]; "
        "or --result not_performed if you checked nothing. Never report a check you did "
        "not run."
    )
    return steps


def _derive_verification(executed: list[dict[str, Any]]) -> str | None:
    if not executed:
        return None
    passed = sum(check["passed"] for check in executed)
    if passed == len(executed):
        return "passed"
    return "partial" if passed else "failed"


def _describe_exit(check: dict[str, Any]) -> str:
    if check["timed_out"]:
        return "timed out"
    return f"exit {check['exit_code']}"


def _aggregate_statuses(statuses: list[str | None]) -> str:
    successes = sum(status == "settled" for status in statuses)
    if successes == len(statuses) and statuses:
        return "success"
    if successes:
        return "partial"
    return "failed"


def _pi_progress(path: Path, *, include_previews: bool) -> dict[str, Any]:
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


def _pi_rpc_progress(path: Path, *, include_previews: bool) -> dict[str, Any]:
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
