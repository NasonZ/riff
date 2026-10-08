"""Durable, privacy-conscious state and trace helpers for Riff."""

from __future__ import annotations

import hashlib
import json
import os
import re
import tempfile
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

SECRET_KEY = re.compile(
    r"(?:api[_-]?key|secret|password|authorization|bearer|"
    r"(?:access|refresh|oauth|auth)[_-]?token)",
    re.IGNORECASE,
)


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def default_state_root() -> Path:
    configured = os.environ.get("RIFF_STATE_DIR")
    if configured:
        return Path(configured).expanduser().resolve()
    xdg = os.environ.get("XDG_STATE_HOME")
    base = Path(xdg).expanduser() if xdg else Path.home() / ".local" / "state"
    return (base / "riff").resolve()


def private_directory(path: Path) -> None:
    """Restrict a Riff-owned data directory, including existing installations."""
    path.mkdir(mode=0o700, parents=True, exist_ok=True)
    path.chmod(0o700)


def atomic_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.", suffix=".tmp", dir=path.parent
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
            stream.write(json.dumps(value, indent=2, ensure_ascii=False) + "\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text())
    if not isinstance(value, dict):
        # Well-formed JSON of the wrong shape is a bad value.
        raise ValueError(f"expected JSON object in {path}")  # noqa: TRY004
    return value


def sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def sha256_file(path: Path) -> str | None:
    if not path.is_file():
        return None
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def redact(value: Any) -> Any:
    """Redact secret-shaped keys before writing metadata to durable state."""
    if isinstance(value, dict):
        return {
            str(key): "<redacted>" if SECRET_KEY.search(str(key)) else redact(item)
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [redact(item) for item in value]
    if isinstance(value, tuple):
        return [redact(item) for item in value]
    return value


class RunStore:
    """Filesystem layout for one or more Riff runs."""

    def __init__(self, root: Path | None = None) -> None:
        self.root = (root or default_state_root()).expanduser().resolve()
        self.runs = self.root / "runs"
        private_directory(self.runs)

    def run_dir(self, run_id: str) -> Path:
        try:
            parsed = uuid.UUID(run_id)
        except (ValueError, AttributeError, TypeError) as error:
            raise ValueError(f"invalid run id: {run_id!r}") from error
        if str(parsed) != run_id.lower():
            raise ValueError(f"run id must be a canonical UUID: {run_id!r}")
        return self.runs / run_id

    @contextmanager
    def run_lock(self, run_id: str):
        with _file_lock(self.run_dir(run_id) / ".run.lock"):
            yield

    @contextmanager
    def participant_lock(self, run_id: str, participant_id: str):
        _validate_participant_id(participant_id)
        with _file_lock(self.run_dir(run_id) / "participants" / f".{participant_id}.lock"):
            yield

    def create(self, run_id: str, manifest: dict[str, Any]) -> Path:
        directory = self.run_dir(run_id)
        try:
            directory.mkdir()
        except FileExistsError as error:
            raise ValueError(f"run already exists: {run_id}") from error
        for child in ("artifacts", "logs", "turns", "participants"):
            (directory / child).mkdir()
        self.write_manifest(run_id, manifest)
        return directory

    def manifest_path(self, run_id: str) -> Path:
        return self.run_dir(run_id) / "run.json"

    def read_manifest(self, run_id: str) -> dict[str, Any]:
        path = self.manifest_path(run_id)
        if not path.is_file():
            raise ValueError(f"unknown run id: {run_id}")
        return read_json(path)

    def write_manifest(self, run_id: str, manifest: dict[str, Any]) -> None:
        atomic_json(self.manifest_path(run_id), redact(manifest))

    def participant_path(self, run_id: str, participant_id: str) -> Path:
        _validate_participant_id(participant_id)
        return self.run_dir(run_id) / "participants" / f"{participant_id}.json"

    def read_participant(self, run_id: str, participant_id: str) -> dict[str, Any]:
        path = self.participant_path(run_id, participant_id)
        if not path.is_file():
            raise ValueError(f"participant {participant_id!r} is not in run {run_id}")
        return read_json(path)

    def write_participant(
        self, run_id: str, participant_id: str, value: dict[str, Any]
    ) -> None:
        atomic_json(self.participant_path(run_id, participant_id), redact(value))

    def write_turn(self, run_id: str, turn_id: str, value: dict[str, Any]) -> Path:
        path = self.run_dir(run_id) / "turns" / f"{turn_id}.json"
        atomic_json(path, redact(value))
        return path

    def artifact_path(self, run_id: str, turn_id: str) -> Path:
        return self.run_dir(run_id) / "artifacts" / f"{turn_id}.md"

    def log_path(self, run_id: str, turn_id: str) -> Path:
        return self.run_dir(run_id) / "logs" / f"{turn_id}.log"

    def native_state_path(self, run_id: str, participant_id: str) -> Path:
        _validate_participant_id(participant_id)
        path = self.run_dir(run_id) / "participants" / participant_id
        path.mkdir(parents=True, exist_ok=True)
        return path


@contextmanager
def _file_lock(path: Path):
    """Hold an inter-process advisory lock for a state mutation."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a+") as stream:
        try:
            import fcntl
        except ImportError:  # pragma: no cover - exercised on Windows
            import msvcrt

            stream.seek(0)
            if stream.read(1) == "":
                stream.write("\0")
                stream.flush()
            stream.seek(0)
            msvcrt.locking(stream.fileno(), msvcrt.LK_LOCK, 1)
            try:
                yield
            finally:
                stream.seek(0)
                msvcrt.locking(stream.fileno(), msvcrt.LK_UNLCK, 1)
        else:
            fcntl.flock(stream.fileno(), fcntl.LOCK_EX)
            try:
                yield
            finally:
                fcntl.flock(stream.fileno(), fcntl.LOCK_UN)


def _validate_participant_id(participant_id: str) -> None:
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,63}", participant_id):
        raise ValueError(f"invalid participant id: {participant_id!r}")
