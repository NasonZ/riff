"""Shared request and result contracts for Riff."""

from __future__ import annotations

import re
import uuid
from dataclasses import asdict, dataclass, field, replace
from pathlib import Path
from typing import Any, Literal

Json = None | bool | int | float | str | list["Json"] | dict[str, "Json"]
Mode = Literal["consult", "discuss", "delegate"]
Tools = Literal["none", "read", "read+web", "write"]
Dispatch = Literal["single", "broadcast", "split", "pipeline"]
DriverPosition = Literal["withheld", "provided", "none"]


class ValidationError(ValueError):
    """Raised when a Riff request would be ambiguous or unsafe to execute."""


PARTICIPANT_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")
# Allow long peer analyses; a recoverable timeout still costs a round trip.
DEFAULT_TIMEOUT_SECONDS = 1800


def _nonempty_string(value: Any, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValidationError(f"{field_name} must be a non-empty string")
    return value.strip()


def _string_list(value: Any, field_name: str) -> list[str]:
    if value is None:
        return []
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        raise ValidationError(f"{field_name} must be an array of strings")
    return [item for item in value if item.strip()]


def _canonical_uuid(value: Any, field_name: str) -> str:
    if not isinstance(value, str):
        raise ValidationError(f"{field_name} must be a canonical UUID string")
    try:
        parsed = uuid.UUID(value)
    except ValueError as error:
        raise ValidationError(f"{field_name} must be a canonical UUID string") from error
    if str(parsed) != value.lower():
        raise ValidationError(f"{field_name} must be a canonical UUID string")
    return value.lower()


@dataclass(frozen=True)
class ParticipantSpec:
    """One independently addressable harness instance."""

    id: str
    harness: str
    cwd: str
    tools: Tools = "none"
    model: str | None = None
    provider: str | None = None
    params: dict[str, Json] = field(default_factory=dict)
    task: str | None = None
    focus: str | None = None

    @classmethod
    def from_dict(cls, value: Any, *, default_cwd: str) -> ParticipantSpec:
        if not isinstance(value, dict):
            raise ValidationError("each participant must be an object")
        allowed = {
            "id",
            "harness",
            "cwd",
            "tools",
            "model",
            "provider",
            "params",
            "task",
            "focus",
        }
        unknown = sorted(set(value) - allowed)
        if unknown:
            hint = (
                "; timeout_seconds is a request-level field"
                if "timeout_seconds" in unknown
                else ""
            )
            raise ValidationError(
                "unknown participant fields: "
                + ", ".join(unknown)
                + f" (allowed: {', '.join(sorted(allowed))}){hint}"
            )
        participant_id = _nonempty_string(value.get("id"), "participant.id")
        if not PARTICIPANT_ID.fullmatch(participant_id):
            raise ValidationError(
                "participant.id must start with an alphanumeric character and contain "
                "only alphanumerics, dot, underscore, or hyphen (maximum 64 characters)"
            )
        harness = _nonempty_string(value.get("harness"), f"participant {participant_id}.harness")
        tools = value.get("tools", "none")
        if tools not in {"none", "read", "read+web", "write"}:
            raise ValidationError(
                f"participant {participant_id}.tools must be none, read, read+web, or write"
            )
        raw_cwd = value.get("cwd")
        if raw_cwd is not None and not isinstance(raw_cwd, str):
            raise ValidationError(f"participant {participant_id}.cwd must be a string")
        cwd = str(Path(raw_cwd or default_cwd).expanduser().resolve())
        if not Path(cwd).is_dir():
            raise ValidationError(f"participant {participant_id} cwd does not exist: {cwd}")
        params = value.get("params") or {}
        if not isinstance(params, dict):
            raise ValidationError(f"participant {participant_id}.params must be an object")
        model = value.get("model")
        provider = value.get("provider")
        task = value.get("task")
        focus = value.get("focus")
        for field_name, optional in (
            ("model", model),
            ("provider", provider),
            ("task", task),
            ("focus", focus),
        ):
            if optional is not None and not isinstance(optional, str):
                raise ValidationError(
                    f"participant {participant_id}.{field_name} must be a string or null"
                )
            if field_name in {"model", "provider"} and optional is not None and not optional.strip():
                raise ValidationError(
                    f"participant {participant_id}.{field_name} must not be empty"
                )
        return cls(
            id=participant_id,
            harness=harness.lower(),
            cwd=cwd,
            tools=tools,
            model=model.strip() if model is not None else None,
            provider=provider.strip() if provider is not None else None,
            params=params,
            task=(task or "").strip() or None,
            focus=(focus or "").strip() or None,
        )


@dataclass(frozen=True)
class CoordinationSpec:
    """Driver-mediated scheduling rules for a run."""

    dispatch: Dispatch = "single"
    independent_first: bool = True
    max_rounds: int = 3
    max_depth: int = 1
    concurrency: int = 4

    @classmethod
    def from_dict(cls, value: Any, *, participant_count: int) -> CoordinationSpec:
        if value is None:
            value = {}
        if not isinstance(value, dict):
            raise ValidationError("coordination must be an object")
        allowed = {
            "dispatch",
            "independent_first",
            "max_rounds",
            "max_depth",
            "concurrency",
        }
        unknown = sorted(set(value) - allowed)
        if unknown:
            raise ValidationError(
                "unknown coordination fields: " + ", ".join(unknown)
            )
        default_dispatch = "single" if participant_count == 1 else "broadcast"
        dispatch = value.get("dispatch", default_dispatch)
        if dispatch not in {"single", "broadcast", "split", "pipeline"}:
            raise ValidationError(
                "coordination.dispatch must be single, broadcast, split, or pipeline"
            )
        if participant_count > 1 and dispatch == "single":
            raise ValidationError("single dispatch requires exactly one participant")
        if participant_count == 1 and dispatch != "single":
            raise ValidationError(f"{dispatch} dispatch requires at least two participants")
        max_rounds = value.get("max_rounds", 3)
        max_depth = value.get("max_depth", 1)
        concurrency = value.get("concurrency", min(4, max(1, participant_count)))
        independent_first = value.get("independent_first", True)
        if not isinstance(independent_first, bool):
            raise ValidationError("coordination.independent_first must be a boolean")
        for name, number, minimum, maximum in (
            ("max_rounds", max_rounds, 1, 20),
            ("max_depth", max_depth, 0, 8),
            ("concurrency", concurrency, 1, 16),
        ):
            if not isinstance(number, int) or isinstance(number, bool):
                raise ValidationError(f"coordination.{name} must be an integer")
            if not minimum <= number <= maximum:
                raise ValidationError(
                    f"coordination.{name} must be between {minimum} and {maximum}"
                )
        return cls(
            dispatch=dispatch,
            independent_first=independent_first,
            max_rounds=max_rounds,
            max_depth=max_depth,
            concurrency=concurrency,
        )


@dataclass(frozen=True)
class RunRequest:
    """Validated, versioned request accepted by the Riff coordinator."""

    version: int
    mode: Mode
    task: str
    origin_harness: str
    participants: tuple[ParticipantSpec, ...]
    coordination: CoordinationSpec
    driver_position: DriverPosition = "withheld"
    driver_position_text: str | None = None
    driver_prediction: str | None = None
    context_refs: tuple[str, ...] = ()
    constraints: tuple[str, ...] = ()
    out_of_scope: tuple[str, ...] = ()
    acceptance_criteria: tuple[str, ...] = ()
    timeout_seconds: int = DEFAULT_TIMEOUT_SECONDS
    parent_run_id: str | None = None
    depth: int = 0

    @classmethod
    def from_dict(cls, value: Any, *, default_cwd: str | None = None) -> RunRequest:
        if not isinstance(value, dict):
            raise ValidationError("request must be a JSON object")
        allowed = {
            "version",
            "mode",
            "task",
            "origin_harness",
            "participants",
            "coordination",
            "driver_position",
            "driver_position_text",
            "driver_prediction",
            "context_refs",
            "constraints",
            "out_of_scope",
            "acceptance_criteria",
            "timeout_seconds",
            "parent_run_id",
            "depth",
        }
        unknown = sorted(set(value) - allowed)
        if unknown:
            raise ValidationError("unknown request fields: " + ", ".join(unknown))
        version = value.get("version", 1)
        if not isinstance(version, int) or isinstance(version, bool) or version != 1:
            raise ValidationError(f"unsupported request version: {version!r}")
        mode = value.get("mode")
        if mode not in {"consult", "discuss", "delegate"}:
            raise ValidationError("mode must be consult, discuss, or delegate")
        task = _nonempty_string(value.get("task"), "task")
        origin_harness = _nonempty_string(
            value.get("origin_harness", "unknown"), "origin_harness"
        ).lower()
        raw_participants = value.get("participants")
        if not isinstance(raw_participants, list) or not raw_participants:
            raise ValidationError("participants must be a non-empty array")
        cwd = default_cwd or str(Path.cwd())
        participants = tuple(
            ParticipantSpec.from_dict(item, default_cwd=cwd) for item in raw_participants
        )
        ids = [participant.id for participant in participants]
        if len(ids) != len(set(ids)):
            raise ValidationError("participant ids must be unique")
        coordination = CoordinationSpec.from_dict(
            value.get("coordination"), participant_count=len(participants)
        )
        if coordination.dispatch == "split":
            missing = [participant.id for participant in participants if not participant.task]
            if missing:
                raise ValidationError(
                    "split dispatch requires participant.task for: " + ", ".join(missing)
                )
        if coordination.dispatch == "broadcast" and any(
            participant.tools == "write" for participant in participants
        ):
            raise ValidationError("broadcast dispatch is read-only; use split or pipeline for writes")
        if coordination.dispatch != "pipeline":
            write_cwds = [
                (participant.id, Path(participant.cwd))
                for participant in participants
                if participant.tools == "write"
            ]
            for index, (left_id, left) in enumerate(write_cwds):
                for right_id, right in write_cwds[index + 1 :]:
                    if (
                        left == right
                        or left.is_relative_to(right)
                        or right.is_relative_to(left)
                    ):
                        raise ValidationError(
                            "concurrent write participants must use non-overlapping "
                            f"working directories: {left_id} and {right_id}"
                        )
        driver_position = value.get(
            "driver_position", "withheld" if coordination.independent_first else "none"
        )
        if driver_position not in {"withheld", "provided", "none"}:
            raise ValidationError("driver_position must be withheld, provided, or none")
        driver_position_text = value.get("driver_position_text")
        if driver_position_text is not None and not isinstance(driver_position_text, str):
            raise ValidationError("driver_position_text must be a string or null")
        if driver_position == "provided" and not (driver_position_text or "").strip():
            raise ValidationError(
                "driver_position_text is required when driver_position is provided: put "
                "the driver's current view there, or use driver_position=withheld for an "
                "independent read"
            )
        if driver_position == "provided" and coordination.independent_first:
            explicit = isinstance(value.get("coordination"), dict) and (
                "independent_first" in value["coordination"]
            )
            if explicit:
                raise ValidationError(
                    "coordination.independent_first=true contradicts driver_position=provided; "
                    "drop one of them"
                )
            coordination = replace(coordination, independent_first=False)
        driver_prediction = value.get("driver_prediction")
        if driver_prediction is not None and not isinstance(driver_prediction, str):
            raise ValidationError("driver_prediction must be a string or null")
        timeout_seconds = value.get("timeout_seconds", DEFAULT_TIMEOUT_SECONDS)
        if not isinstance(timeout_seconds, int) or isinstance(timeout_seconds, bool):
            raise ValidationError("timeout_seconds must be an integer")
        if not 1 <= timeout_seconds <= 86400:
            raise ValidationError("timeout_seconds must be between 1 and 86400")
        depth = value.get("depth", 0)
        if not isinstance(depth, int) or isinstance(depth, bool) or depth < 0:
            raise ValidationError("depth must be a non-negative integer")
        parent_run_id = value.get("parent_run_id")
        if parent_run_id is not None:
            parent_run_id = _canonical_uuid(parent_run_id, "parent_run_id")
        if parent_run_id is None and depth != 0:
            raise ValidationError("top-level requests must use depth 0")
        if parent_run_id is not None and depth == 0:
            raise ValidationError("nested requests must use a positive depth")
        if parent_run_id is not None and depth >= coordination.max_depth:
            raise ValidationError(
                f"nested run depth {depth} reaches max_depth {coordination.max_depth}"
            )
        return cls(
            version=version,
            mode=mode,
            task=task,
            origin_harness=origin_harness,
            participants=participants,
            coordination=coordination,
            driver_position=driver_position,
            driver_position_text=driver_position_text,
            driver_prediction=(driver_prediction or "").strip() or None,
            context_refs=tuple(_string_list(value.get("context_refs"), "context_refs")),
            constraints=tuple(_string_list(value.get("constraints"), "constraints")),
            out_of_scope=tuple(_string_list(value.get("out_of_scope"), "out_of_scope")),
            acceptance_criteria=tuple(
                _string_list(value.get("acceptance_criteria"), "acceptance_criteria")
            ),
            timeout_seconds=timeout_seconds,
            parent_run_id=parent_run_id,
            depth=depth,
        )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


# Heuristic request lints. They warn rather than reject: each pattern has honest
# false positives, and the driver may have a stated reason to proceed.
PERSONA_CUE = re.compile(
    r"\b(?:act(?:ing)? as|pretend(?:ing)? (?:to be|you are)|role-?play|"
    r"you are an? (?:legendary|world[- ]class|renowned|famous|brilliant|seasoned|"
    r"veteran|senior|expert)\b)",
    re.IGNORECASE,
)
POSITION_CUE = re.compile(
    r"\b(?:I think|I believe|I suspect|I propose|I recommend|I(?:'m| am) leaning|"
    r"my (?:view|position|answer|proposal|recommendation|hypothesis|take)\b)",
    re.IGNORECASE,
)
WEB_CUE = re.compile(
    r"https?://|\b(?:web ?search|on the web|online sources?|external (?:sources?|claims?)|"
    r"cited (?:urls?|links?|sources?)|upstream (?:docs|issues?))\b",
    re.IGNORECASE,
)
FAN_OUT_LIMIT = 5


def request_warnings(request: RunRequest) -> list[dict[str, str]]:
    """Return lint findings for a valid request that is likely to underperform."""
    warnings: list[dict[str, str]] = []

    def warn(code: str, message: str) -> None:
        warnings.append({"code": code, "message": message})

    if request.mode == "delegate" and not request.acceptance_criteria:
        warn(
            "delegate-without-acceptance-criteria",
            "delegate request has no acceptance_criteria; add observable checks the "
            "driver will run, or consult first if the output cannot yet be specified",
        )
    if request.mode == "delegate" and not request.out_of_scope:
        warn(
            "delegate-without-out-of-scope",
            "delegate request has no out_of_scope; name the tempting adjacent work the "
            "worker must not do",
        )
    texts = [("task", request.task)]
    for participant in request.participants:
        if participant.task:
            texts.append((f"participant {participant.id}.task", participant.task))
        if participant.focus:
            texts.append((f"participant {participant.id}.focus", participant.focus))
    for label, text in texts:
        match = PERSONA_CUE.search(text)
        if match:
            warn(
                "persona-cue",
                f"{label} contains persona wording {match.group(0)!r}; state the object of "
                "attention instead (for example 'check specifically for lost-update races')",
            )
    if request.driver_position == "withheld":
        for label, text in texts:
            match = POSITION_CUE.search(text)
            if match:
                warn(
                    "position-in-withheld-task",
                    f"driver_position is withheld but {label} contains {match.group(0)!r}; "
                    "remove the driver's view from the task, or declare it with "
                    "driver_position=provided",
                )
        if request.mode != "delegate" and not request.driver_prediction:
            warn(
                "no-driver-prediction",
                "independent-first run has no driver_prediction; record the starting "
                "expectation or uncertainty when useful. If there is no prior position "
                "to withhold, use driver_position=none; do not invent a prediction",
            )
    for participant in request.participants:
        if participant.harness != "claude" or participant.tools == "none":
            continue
        readable = [Path(participant.cwd)] + [
            Path(item).expanduser().resolve()
            for item in participant.params.get("add_dirs") or []
            if isinstance(item, str)
        ]
        for reference in request.context_refs:
            # A relative ref reaches the peer as-is, so it resolves against its cwd.
            path = Path(reference).expanduser()
            resolved = (path if path.is_absolute() else Path(participant.cwd) / path).resolve()
            if not any(resolved.is_relative_to(root) for root in readable):
                warn(
                    "context-ref-outside-cwd",
                    f"{participant.id} cannot read {reference}: it is outside {participant.cwd}; "
                    "add its directory to params.add_dirs or copy the file into the cwd",
                )
    web_text = " ".join([request.task, *request.acceptance_criteria, *request.constraints])
    if WEB_CUE.search(web_text):
        for participant in request.participants:
            if participant.tools in {"none", "read"}:
                warn(
                    "scope-lacks-web",
                    f"the task mentions web or external sources but {participant.id} has "
                    f"tools={participant.tools}; use read+web on a Claude or Codex peer, or "
                    "state that external claims will stay unverified",
                )
    for participant in request.participants:
        if participant.tools == "write" and _is_main_checkout(Path(participant.cwd)):
            warn(
                "write-in-main-checkout",
                f"{participant.id} writes in a main git checkout ({participant.cwd}); use a "
                "linked worktree so the driver can review the diff before integrating",
            )
    if len(request.participants) > FAN_OUT_LIMIT:
        warn(
            "wide-fan-out",
            f"{len(request.participants)} participants exceed {FAN_OUT_LIMIT}; synthesis "
            "usually costs more than the extra samples return, so batch or narrow the question",
        )
    return warnings


def _is_main_checkout(directory: Path) -> bool:
    """True inside a repository's primary checkout; a linked worktree has a .git file."""
    for candidate in (directory, *directory.parents):
        marker = candidate / ".git"
        if marker.exists():
            return marker.is_dir()
    return False


@dataclass(frozen=True)
class TurnRequest:
    """Adapter-ready prompt and execution boundary."""

    run_id: str
    turn_id: str
    participant: ParticipantSpec
    prompt: str
    timeout_seconds: int
    artifact_path: str
    log_path: str
    state_path: str
    depth: int
    is_reply: bool = False
    native_session_id: str | None = None
    native_session_ref: str | None = None


@dataclass
class SettledTurn:
    """Normalized result returned by every harness adapter."""

    participant_id: str
    harness: str
    status: str
    artifact_file: str
    log_file: str
    native_session_id: str | None = None
    native_session_ref: str | None = None
    model: str | None = None
    provider: str | None = None
    elapsed_ms: int = 0
    usage: dict[str, Any] = field(default_factory=dict)
    error_type: str | None = None
    error: str | None = None
    authority_enforcement: str = "native"
    adapter_metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def ok(self) -> bool:
        return self.status == "settled" and self.error is None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
