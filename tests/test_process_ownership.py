"""Ownership pins, safe platform hints and threaded descriptor lifetimes."""

from __future__ import annotations

import os
import signal
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

from scripts.riff_core import process
from scripts.riff_core.models import ParticipantSpec, TurnRequest
from scripts.riff_core.pipe_io import PipeIO


@unittest.skipUnless(sys.platform == "linux", "real POSIX ownership tests")
class ProcessOwnershipTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)

    def test_group_signals_keep_the_child_waitable_and_cleanup_is_idempotent(self):
        marker = self.root / "grandchild"
        code = (
            "import pathlib,subprocess,sys; "
            "child=subprocess.Popen([sys.executable,'-c','import time;time.sleep(30)']); "
            "pathlib.Path(sys.argv[1]).write_text(str(child.pid))"
        )
        child = process.spawn_gated(
            [sys.executable, "-c", code, str(marker)],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        child.stdin.close()
        try:
            deadline = time.monotonic() + 3
            while (
                not process.observe_child_exit(child).exited
                and time.monotonic() < deadline
            ):
                time.sleep(0.01)
            self.assertTrue(process.observe_child_exit(child).exited)
            grandchild = process.identity(int(marker.read_text()))
            self.assertEqual(process.process_state(grandchild), "alive")
            real_killpg = os.killpg
            signals = []

            def pinned_signal(pgid, sig):
                # The kernel, rather than a cached returncode, must still know
                # this child as ours at each signal. WNOWAIT leaves it pinned.
                waited = os.waitid(
                    os.P_PID, child.pid, os.WEXITED | os.WNOHANG | os.WNOWAIT
                )
                self.assertIsNotNone(waited)
                signals.append(sig)
                return real_killpg(pgid, sig)

            with patch.object(process.os, "killpg", side_effect=pinned_signal):
                result = process.terminate_group(child)
            self.assertEqual(signals, [signal.SIGTERM, signal.SIGKILL])
            self.assertEqual(child.returncode, 0)
            deadline = time.monotonic() + 3
            while (
                process.process_state(grandchild) != "gone"
                and time.monotonic() < deadline
            ):
                time.sleep(0.01)
            self.assertEqual(process.process_state(grandchild), "gone")
            with (
                patch.object(
                    process.os,
                    "killpg",
                    side_effect=AssertionError("late group signal"),
                ),
                patch.object(
                    process.os, "kill", side_effect=AssertionError("late PID signal")
                ),
            ):
                self.assertEqual(process.terminate_group(child), result)
        finally:
            if child.returncode is None:
                process.terminate_group(child, grace_seconds=0.1)
            child.stdout.close()
            child.stderr.close()

    def test_direct_launch_observes_actual_pid_input_and_exit_status(self):
        observed = []
        turn = TurnRequest(
            "synthetic",
            "turn",
            ParticipantSpec("peer", "codex", str(self.root)),
            "prompt",
            3,
            str(self.root / "artifact"),
            str(self.root / "log"),
            str(self.root),
            0,
            launch_model="direct",
            observe_process=observed.append,
        )
        with patch.object(process, "native_launch_model", return_value="direct"):
            completed, _, error = process.run_process(
                [
                    sys.executable,
                    "-c",
                    "import os,sys; print(os.getpid()); print(sys.stdin.read()); raise SystemExit(7)",
                ],
                turn,
                input_text="native input",
            )
        self.assertIsNone(error)
        self.assertEqual(completed.returncode, 7)
        lines = completed.stdout.splitlines()
        self.assertEqual(int(lines[0]), observed[0]["pid"])
        self.assertEqual(lines[1], "native input")

    def test_already_reaped_child_never_authorises_a_group_signal(self):
        child = process.spawn_gated(
            [sys.executable, "-c", "pass"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        child.communicate(timeout=3)
        with (
            patch.object(
                process.os, "killpg", side_effect=AssertionError("recycled group")
            ),
            patch.object(
                process.os, "kill", side_effect=AssertionError("recycled PID")
            ),
        ):
            result = process.terminate_group(child)
        self.assertFalse(result.signalled)
        self.assertEqual(result.group_proof, "unknown")

    def test_retry_after_interrupted_cleanup_does_not_signal_after_reap(self):
        ready = self.root / "ready"
        child = process.spawn_gated(
            [
                sys.executable,
                "-c",
                "import pathlib,signal,sys,time; signal.signal(signal.SIGTERM,signal.SIG_IGN); pathlib.Path(sys.argv[1]).touch(); time.sleep(30)",
                str(ready),
            ],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        child.stdin.close()
        try:
            deadline = time.monotonic() + 3
            while not ready.exists() and time.monotonic() < deadline:
                time.sleep(0.01)
            self.assertTrue(ready.exists())
            with patch.object(process.time, "sleep", side_effect=KeyboardInterrupt):
                with self.assertRaises(KeyboardInterrupt):
                    process.terminate_group(child)
            child.kill()
            child.wait(timeout=3)
            with patch.object(
                process.os, "killpg", side_effect=AssertionError("pin lost")
            ):
                self.assertEqual(process.terminate_group(child).group_proof, "unknown")
        finally:
            if child.returncode is None:
                process.terminate_group(child, grace_seconds=0.1)

    def test_threaded_pipe_owners_close_only_after_their_syscalls_unblock(self):
        marker = self.root / "escaped"
        code = (
            "import pathlib,subprocess,sys,time; "
            "p=subprocess.Popen([sys.executable,'-c','import time;time.sleep(30)'],start_new_session=True); "
            "pathlib.Path(sys.argv[1]).write_text(str(p.pid)); print('captured',flush=True); time.sleep(30)"
        )
        transports = []

        def transport(*args, **kwargs):
            value = PipeIO(*args, **kwargs, threaded=True)
            transports.append(value)
            return value

        turn = TurnRequest(
            "synthetic",
            "turn",
            ParticipantSpec("peer", "codex", str(self.root)),
            "prompt",
            1,
            str(self.root / "artifact"),
            str(self.root / "log"),
            str(self.root),
            0,
        )
        escaped = None
        try:
            with patch.object(process, "PipeIO", side_effect=transport):
                result, _, error = process.run_process(
                    [sys.executable, "-c", code, str(marker)], turn
                )
            escaped = process.identity(int(marker.read_text()))
            self.assertIn("timed out", error)
            self.assertTrue(result.output_truncated)
            io = transports[0]
            self.assertEqual(process.process_state(escaped), "alive")
            self.assertFalse(io.process.stdout.closed)
            self.assertFalse(io.process.stderr.closed)
            os.kill(escaped["pid"], signal.SIGKILL)
            for thread in io.threads:
                thread.join(timeout=3)
            self.assertTrue(all(not thread.is_alive() for thread in io.threads))
            self.assertTrue(io.process.stdout.closed)
            self.assertTrue(io.process.stderr.closed)
        finally:
            if escaped and process.process_state(escaped) == "alive":
                os.kill(escaped["pid"], signal.SIGKILL)


class PlatformHintTests(unittest.TestCase):
    def test_non_linux_posix_has_alive_only_hints_and_keeps_foreign_linux_unknown(self):
        with patch.object(process.sys, "platform", "darwin"):
            self.assertEqual(process.process_state({"pid": os.getpid()}), "alive")
            with patch.object(process.os, "kill", side_effect=ProcessLookupError):
                self.assertEqual(process.process_state({"pid": 12345}), "unknown")
            with patch.object(
                process.os, "kill", side_effect=AssertionError("foreign Linux identity")
            ):
                self.assertEqual(
                    process.process_state({"pid": os.getpid(), "boot_id": "synthetic"}),
                    "unknown",
                )

    def test_windows_alive_handle_query_closes_handles_for_both_outcomes(self):
        import ctypes
        from unittest.mock import Mock

        kernel = Mock()
        handle = 0x123456789
        kernel.OpenProcess.return_value = handle
        with patch.object(ctypes, "WinDLL", return_value=kernel, create=True):
            for waited, expected in ((258, "alive"), (0, "unknown")):
                kernel.WaitForSingleObject.return_value = waited
                self.assertEqual(process._windows_alive(12345), expected)
                kernel.OpenProcess.assert_called_with(0x100000, False, 12345)
                kernel.WaitForSingleObject.assert_called_with(handle, 0)
                kernel.CloseHandle.assert_called_with(handle)
        self.assertEqual(kernel.CloseHandle.call_count, 2)

    def test_windows_hints_never_use_kill_as_a_probe(self):
        with (
            patch.object(process.sys, "platform", "win32"),
            patch.object(process.os, "kill", side_effect=AssertionError("Windows TerminateProcess")),
            patch.object(process, "_windows_alive", return_value="unknown"),
        ):
            self.assertEqual(process.process_state({"pid": 12345}), "unknown")
            with patch.object(process, "_windows_alive", return_value="alive"):
                self.assertEqual(process.process_state({"pid": 12345}), "alive")
