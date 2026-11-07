"""Owned process launch, streaming and conservative Linux recovery observations."""

from __future__ import annotations

import os
import signal
import subprocess
import sys
import threading
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Callable

from .models import ProcessIdentity, TurnRequest
from .pipe_io import PipeIO, close_process_pipes

# Read exactly one byte: a buffered read could consume part of the native prompt.
GATE_SOURCE = 'import os,sys; release=os.read(0,1); sys.exit(125) if release != b"R" else os.execvpe(sys.argv[1],sys.argv[1:],os.environ)'


def _stat(pid: int) -> tuple[str, int, int]:
    tail = Path(f"/proc/{pid}/stat").read_text().rsplit(")", 1)[1].split()
    return tail[0], int(tail[2]), int(tail[19])


def identity(pid: int | None = None) -> ProcessIdentity:
    pid = os.getpid() if pid is None else pid
    result: ProcessIdentity = {"pid": pid}
    if sys.platform != "linux":
        return result
    try:
        _, pgid, ticks = _stat(pid)
        result.update(
            start_ticks=ticks,
            pgid=pgid,
            boot_id=Path("/proc/sys/kernel/random/boot_id").read_text().strip(),
            pid_namespace=os.readlink(f"/proc/{pid}/ns/pid"),
        )
    except (OSError, ValueError, IndexError):
        pass
    return result


def _local(record: dict[str, Any] | None) -> bool:
    if sys.platform != "linux" or not record:
        return False
    if (
        not isinstance(record.get("pid"), int)
        or isinstance(record.get("pid"), bool)
        or record["pid"] <= 0
        or not isinstance(record.get("start_ticks"), int)
        or record["start_ticks"] <= 0
        or not all(
            isinstance(record.get(key), str) and record[key]
            for key in ("boot_id", "pid_namespace")
        )
    ):
        return False
    try:
        return (
            record["pid_namespace"] == os.readlink("/proc/self/ns/pid")
            and record["boot_id"]
            == Path("/proc/sys/kernel/random/boot_id").read_text().strip()
        )
    except OSError:
        return False


def _windows_alive(pid: int) -> str:
    """An alive-only handle query; os.kill(pid, 0) is destructive on Windows."""
    if not 0 < pid <= 0xFFFFFFFF:
        return "unknown"
    try:
        import ctypes
        from ctypes import wintypes

        kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
        kernel.OpenProcess.restype = wintypes.HANDLE
        kernel.WaitForSingleObject.argtypes = [wintypes.HANDLE, wintypes.DWORD]
        kernel.WaitForSingleObject.restype = wintypes.DWORD
        kernel.CloseHandle.argtypes = [wintypes.HANDLE]
        kernel.CloseHandle.restype = wintypes.BOOL
        handle = kernel.OpenProcess(0x100000, False, pid)  # SYNCHRONIZE
        if not handle:
            return "unknown"
        try:
            if kernel.WaitForSingleObject(handle, 0) == 258:  # WAIT_TIMEOUT
                return "alive"
        finally:
            kernel.CloseHandle(handle)
    except (AttributeError, OSError, OverflowError):
        pass
    return "unknown"


def pid_alive_hint(pid: object) -> str:
    """A live-PID hint can delay work, but can never authorise recovery."""
    if not isinstance(pid, int) or isinstance(pid, bool) or pid <= 0:
        return "unknown"
    if sys.platform == "win32" or os.name == "nt":
        return _windows_alive(pid)
    if os.name == "posix":
        try:
            os.kill(pid, 0)
            return "alive"
        except (OSError, OverflowError):
            pass
    return "unknown"


def process_state(record: dict[str, Any] | None) -> str:
    if sys.platform != "linux":
        if not record or any(
            key in record for key in ("boot_id", "pid_namespace", "start_ticks")
        ):
            return "unknown"
        return pid_alive_hint(record.get("pid"))
    if not _local(record):
        return "unknown"
    try:
        state, _, ticks = _stat(record["pid"])
    except FileNotFoundError:
        return "gone"
    except (OSError, ValueError, IndexError):
        return "unknown"
    return "gone" if state == "Z" or ticks != record["start_ticks"] else "alive"


def group_state(record: dict[str, Any] | None) -> str:
    """A missing leader does not prove its tools have exited."""
    if not _local(record) or record.get("pgid") != record.get("pid"):
        return "unknown"
    try:
        _, _, current_ticks = _stat(record["pid"])
        if current_ticks != record["start_ticks"]:
            # Linux retains a process-group ID while any group member exists;
            # reusing its leader PID therefore proves this old group has gone.
            return "gone"
    except FileNotFoundError:
        pass
    except (OSError, ValueError, IndexError):
        return "unknown"
    leader = process_state(record)
    if leader == "alive":
        return "alive"
    try:
        for mount in Path("/proc/mounts").read_text().splitlines():
            fields = mount.split()
            if len(fields) >= 4 and fields[1] == "/proc":
                if any(
                    option.startswith("hidepid=") and option != "hidepid=0"
                    for option in fields[3].split(",")
                ):
                    return "unknown"
    except OSError:
        return "unknown"

    def members():
        observed = {}
        uncertain = False
        try:
            entries = list(Path("/proc").iterdir())
        except OSError:
            return observed, True
        for entry in entries:
            if not entry.name.isdigit():
                continue
            try:
                state, pgid, ticks = _stat(int(entry.name))
                if pgid == record["pgid"]:
                    observed[int(entry.name)] = (state, ticks)
            except (OSError, ValueError, IndexError):
                # A disappearing process could have forked another group member
                # after enumeration. Do not turn that race into proof of exit.
                uncertain = True
        return observed, uncertain

    first, uncertain = members()
    if any(state != "Z" for state, _ in first.values()):
        return "alive"
    try:
        os.killpg(record["pgid"], 0)
    except ProcessLookupError:
        return "gone"
    except PermissionError:
        return "unknown"
    second, changed = members()
    if any(state != "Z" for state, _ in second.values()):
        return "alive"
    # A stable, readable set of zombies cannot fork. A group that exists but has
    # no visible members, or changes during enumeration, is not proven gone.
    if uncertain or changed or first != second or not second:
        return "unknown"
    return "gone"


@dataclass(frozen=True)
class ChildExit:
    exited: bool | None
    returncode: int | None = None


@dataclass(frozen=True)
class CleanupResult:
    signalled: bool
    group_proof: str


class ProcessCompletion(subprocess.CompletedProcess[str]):
    output_truncated: bool = False
    cleanup: CleanupResult | None = None

    @property
    def metadata(self) -> dict[str, Any]:
        value: dict[str, Any] = {"output_truncated": self.output_truncated}
        if self.cleanup is not None:
            value["cleanup"] = asdict(self.cleanup)
        return value


def native_launch_model() -> str:
    return "exec-gated" if os.name == "posix" else "direct"


def observe_child_exit(process: subprocess.Popen) -> ChildExit:
    """Observe without releasing a POSIX child PID/PGID pin."""
    if process.returncode is not None:
        return ChildExit(True, process.returncode)
    if os.name != "posix":
        code = process.poll()  # the real native Windows process handle
        return ChildExit(code is not None, code)
    if all(hasattr(os, key) for key in ("waitid", "WNOWAIT", "P_PID")):
        try:
            result = os.waitid(
                os.P_PID, process.pid, os.WEXITED | os.WNOHANG | os.WNOWAIT
            )
        except ChildProcessError:
            process.riff_pin_lost = True
            return ChildExit(None)
        except OSError:
            return ChildExit(None)
        if result is None:
            return ChildExit(False)
        code = (
            result.si_status if result.si_code == os.CLD_EXITED else -result.si_status
        )
        return ChildExit(True, code)
    if sys.platform == "linux":
        try:
            return ChildExit(_stat(process.pid)[0] == "Z")
        except (OSError, ValueError, IndexError):
            pass
    return ChildExit(None)


def _spawn(command: list[str], *, observe, release: bool, **kwargs) -> subprocess.Popen:
    process = subprocess.Popen(
        command, stdin=subprocess.PIPE, start_new_session=os.name == "posix", **kwargs
    )
    process.riff_owned_new_session = os.name == "posix"
    process.riff_cleanup_lock = threading.Lock()
    process.riff_pin_lost = False
    try:
        process.riff_identity = identity(process.pid)
        if observe:
            observe(process.riff_identity)
        if release:
            os.write(process.stdin.fileno(), b"R")
    except BaseException:
        process.stdin.close()
        try:
            terminate_group(process)
        finally:
            close_process_pipes(process)
        raise
    return process


def spawn_gated(
    command: list[str], *, observe=None, launch_model: str | None = None, **kwargs
) -> subprocess.Popen:
    """Gate native POSIX exec; Windows owns the actual native Popen handle."""
    model = launch_model or native_launch_model()
    if model != native_launch_model():
        raise RuntimeError("native launch model differs from its reservation")
    gated = model == "exec-gated"
    target = [sys.executable, "-I", "-c", GATE_SOURCE, *command] if gated else command
    return _spawn(target, observe=observe, release=gated, **kwargs)


def spawn_coordinator(
    command: list[str], *, observe=None, **kwargs
) -> subprocess.Popen:
    """The actual Python worker consumes its release byte before claiming state."""
    return _spawn(command, observe=observe, release=True, **kwargs)


def await_coordinator_release() -> None:
    if os.read(sys.stdin.fileno(), 1) != b"R":
        raise RuntimeError("detached coordinator was not released")


def reap_detached(process: subprocess.Popen) -> None:
    threading.Thread(target=process.wait, name="riff-child-reaper", daemon=True).start()


def terminate_process(process: subprocess.Popen, *, grace_seconds: float = 5) -> bool:
    """Portable leader cleanup using its actual Popen handle."""
    signalled = False
    if process.poll() is None:
        process.terminate()
        signalled = True
    try:
        process.wait(timeout=grace_seconds)
    except subprocess.TimeoutExpired:
        process.kill()
        signalled = True
        process.wait(timeout=grace_seconds)
    return signalled


def terminate_group(
    process: subprocess.Popen, *, grace_seconds: float = 5
) -> CleanupResult:
    """Signal an owned new-session group only while its leader is unreaped.

    Embedding hosts must not install external SIGCHLD/wait(-1) reapers. No poll,
    wait or Popen.send_signal can occur between the two group signals. A reaped
    child's numeric group ID never authorises another signal, even after a proc
    identity check. Cleanup results are cached to make repeated calls harmless.
    """
    lock = getattr(process, "riff_cleanup_lock", None)
    if lock is None:
        lock = process.riff_cleanup_lock = threading.Lock()
    with lock:
        cached = getattr(process, "riff_cleanup", None)
        if cached is not None:
            return cached
        if process.returncode is not None or getattr(process, "riff_pin_lost", False):
            result = CleanupResult(False, "unknown")
        elif os.name != "posix" or not getattr(
            process, "riff_owned_new_session", False
        ):
            signalled = terminate_process(process, grace_seconds=grace_seconds)
            result = CleanupResult(signalled, "unknown")
        else:
            observe_child_exit(process)
            if process.returncode is not None or getattr(
                process, "riff_pin_lost", False
            ):
                result = CleanupResult(False, "unknown")
            else:
                try:
                    os.killpg(process.pid, signal.SIGTERM)
                except ProcessLookupError:
                    pass
                deadline = time.monotonic() + grace_seconds
                while time.monotonic() < deadline:
                    if observe_child_exit(process).exited:
                        break
                    time.sleep(min(0.05, max(0, deadline - time.monotonic())))
                if process.returncode is not None or getattr(
                    process, "riff_pin_lost", False
                ):
                    result = CleanupResult(True, "unknown")
                else:
                    # A zombie leader still pins the group: always KILL before
                    # reaping, including when TERM made just the leader exit.
                    try:
                        os.killpg(process.pid, signal.SIGKILL)
                    except ProcessLookupError:
                        pass
                    process.wait(timeout=5)
                    result = CleanupResult(True, "terminated")
        process.riff_cleanup = result
        return result


DRIVER_SESSION_VARIABLES = (
    "CLAUDE_CODE_SESSION_ID",
    "CODEX_THREAD_ID",
    "CODEX_SESSION_ID",
    "PI_SESSION_ID",
    "PI_SESSION_FILE",
    "HERMES_SESSION_ID",
)


def child_environment(turn: TurnRequest) -> dict[str, str]:
    environment = os.environ.copy()
    for variable in DRIVER_SESSION_VARIABLES:
        environment.pop(variable, None)
    environment.update(
        RIFF_RUN_ID=turn.run_id,
        RIFF_DEPTH=str(turn.depth + 1),
        RIFF_PARTICIPANT_ID=turn.participant.id,
    )
    return environment


def run_process(
    command: list[str],
    turn: TurnRequest,
    *,
    input_text: str | None = None,
    environment: dict[str, str] | None = None,
    on_line: Callable[[str, str], None] | None = None,
) -> tuple[ProcessCompletion, int, str | None]:
    started = time.monotonic()
    output = {"stdout": bytearray(), "stderr": bytearray()}
    pending = {"stdout": b"", "stderr": b""}
    error = None
    drained = True
    cleanup = None
    io = None
    process = None
    log_stream = Path(turn.log_path).open("wb", buffering=0)

    def capture(name, chunk):
        output[name].extend(chunk)
        log_stream.write(chunk)

    def consume(name, chunk):
        capture(name, chunk)
        *lines, pending[name] = (pending[name] + chunk).split(b"\n")
        if on_line:
            for line in lines:
                on_line(name, line.decode("utf-8", errors="replace"))

    try:
        process = spawn_gated(
            command,
            observe=turn.observe_process,
            launch_model=turn.launch_model,
            cwd=turn.participant.cwd,
            env=environment or child_environment(turn),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        io = PipeIO(process, (input_text or "").encode())
        deadline = started + turn.timeout_seconds
        while (
            io.outputs or not io.input_done.is_set()
        ) and time.monotonic() < deadline:
            for name, chunk in io.read(min(0.1, max(0, deadline - time.monotonic()))):
                consume(name, chunk)
        # EOF on both pipes does not establish that the native process exited.
        if not io.outputs:
            try:
                process.wait(timeout=max(0.01, deadline - time.monotonic()))
            except subprocess.TimeoutExpired:
                error = f"timed out after {turn.timeout_seconds} seconds"
        else:
            error = f"timed out after {turn.timeout_seconds} seconds"
        if error:
            cleanup = terminate_group(process)
        drained = io.drain(consume)
        if on_line:
            for name, tail in pending.items():
                if tail:
                    on_line(name, tail.decode("utf-8", errors="replace"))
    except BaseException:
        if process is not None:
            try:
                cleanup = terminate_group(process)
            finally:
                if io is not None:
                    # A failed observer must not be called again during cleanup.
                    drained = io.drain(capture)
        raise
    finally:
        if process is not None:
            close_process_pipes(process)
        log_stream.close()
        text = "\n".join(
            bytes(output[name]).decode("utf-8", errors="replace")
            for name in ("stdout", "stderr")
            if output[name]
        )
        if not drained:
            text += "\n[riff] pipe capture stopped at the drain deadline; inherited pipes remain open.\n"
        Path(turn.log_path).write_text(text)
    completed = ProcessCompletion(
        command,
        process.returncode,
        output["stdout"].decode("utf-8", errors="replace"),
        output["stderr"].decode("utf-8", errors="replace"),
    )
    completed.output_truncated = not drained
    completed.cleanup = cleanup
    return completed, round((time.monotonic() - started) * 1000), error
