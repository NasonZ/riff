"""Pipe lifetime and portable transport checks using real synthetic processes."""

from __future__ import annotations

import json
import os
import signal
import subprocess
import sys
import tempfile
import textwrap
import time
import unittest
from pathlib import Path

from scripts.riff_core.process import process_state, terminate_process

ROOT = Path(__file__).resolve().parent.parent

WORKER = r"""
import json, sys, time
from pathlib import Path
from scripts.riff_core import process
from scripts.riff_core.models import ParticipantSpec, TurnRequest
from scripts.riff_core.adapters.pi import PiAdapter
root, mode = Path(sys.argv[1]), sys.argv[2]
if mode == 'incomplete-identity':
    import os
    process.identity = lambda pid=None: {'pid': os.getpid() if pid is None else pid}
if mode.endswith('-threaded'):
    original = process.PipeIO
    process.PipeIO = lambda *args, **kwargs: original(*args, **kwargs, threaded=True)
turn = TurnRequest('synthetic-run', 'synthetic-turn', ParticipantSpec('peer', 'pi' if mode.startswith('pi-') else 'codex', str(root)),
                   'synthetic prompt', 1, str(root / 'artifact'), str(root / 'log'), str(root / 'state'), 0,
                   observe_process=lambda info: (root / 'owner-child.json').write_text(json.dumps(info)))
started = time.monotonic()
try:
    if mode.startswith('pi-'):
        result = PiAdapter().execute(turn)
        value = {'ok': result.ok, 'error_type': result.error_type, 'artifact': Path(result.artifact_file).read_text(), 'metadata': result.adapter_metadata}
    else:
        def observe(stream, line):
            if line == 'ready':
                if mode.startswith('exception'):
                    raise ValueError('synthetic observer failure')
                (root / 'release-input').touch()
        result, elapsed, error = process.run_process([sys.executable, '-c', (root / 'native.py').read_text()], turn,
                                input_text='x' * 2000000 if mode.startswith('duplex') else None, on_line=observe)
        value = {'error': error, 'stdout': result.stdout, 'stderr_bytes': len(result.stderr), 'returncode': result.returncode, 'metadata': result.metadata}
except Exception as error:
    value = {'exception': str(error)}
value['elapsed'] = time.monotonic() - started
print(json.dumps(value))
"""


@unittest.skipUnless(sys.platform == "linux", "real process-group fixtures on Linux")
class PipeProcessTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.environment = {
            **os.environ,
            "PYTHONPATH": str(ROOT / "skills/riff"),
            "RIFF_PI_BIN": str(self.root / "pi"),
        }
        self.addCleanup(self.cleanup_children)

    def cleanup_children(self):
        for path in self.root.glob("*child.json"):
            record = json.loads(path.read_text())
            if process_state(record) == "alive":
                try:
                    os.kill(record["pid"], signal.SIGKILL)
                except ProcessLookupError:
                    pass

    def worker(self, mode):
        worker = subprocess.Popen(
            [sys.executable, "-c", WORKER, str(self.root), mode],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env=self.environment,
        )
        try:
            stdout, stderr = worker.communicate(timeout=5)
        except subprocess.TimeoutExpired:
            worker.kill()
            worker.communicate(timeout=2)
            self.fail("pipe supervision exceeded its cleanup bound")
        self.assertEqual(worker.returncode, 0, stderr.decode())
        return json.loads(stdout)

    def escaped_native(self):
        (self.root / "native.py").write_text(
            textwrap.dedent("""
            import json, pathlib, subprocess, sys, time
            from scripts.riff_core.process import identity
            child = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(30)'], start_new_session=True)
            pathlib.Path('escaped-child.json').write_text(json.dumps(identity(child.pid)))
            print('ready', flush=True)
            time.sleep(30)
        """)
        )

    def test_timeout_and_observer_exception_bound_escaped_pipe_capture(self):
        for mode in ("timeout", "exception", "timeout-threaded", "exception-threaded"):
            with self.subTest(mode=mode):
                self.escaped_native()
                try:
                    result = self.worker(mode)
                    self.assertLess(result["elapsed"], 4)
                    self.assertIn("ready", (self.root / "log").read_text())
                    self.assertIn("drain deadline", (self.root / "log").read_text())
                    if mode.startswith("exception"):
                        self.assertEqual(
                            result["exception"], "synthetic observer failure"
                        )
                    else:
                        self.assertIn("timed out", result["error"])
                    escaped = json.loads((self.root / "escaped-child.json").read_text())
                    self.assertEqual(process_state(escaped), "alive")
                finally:
                    self.cleanup_children()

    def test_threaded_transport_streams_identity_and_large_duplex_input(self):
        (self.root / "native.py").write_text(
            textwrap.dedent("""
            import pathlib, sys, time
            print('ready', flush=True)
            while not pathlib.Path('release-input').exists():
                time.sleep(0.01)
            payload = sys.stdin.read()
            sys.stderr.write('e' * 300000)
            print(len(payload), flush=True)
        """)
        )
        result = self.worker("duplex-threaded")
        self.assertIsNone(result["error"])
        self.assertEqual(result["returncode"], 0)
        self.assertEqual(result["stdout"].splitlines(), ["ready", "2000000"])
        self.assertEqual(result["stderr_bytes"], 300000)

    def test_closed_output_pipes_still_deliver_input_for_both_transports(self):
        (self.root / "native.py").write_text(
            textwrap.dedent("""
            import os, pathlib, sys
            os.close(1)
            os.close(2)
            payload = sys.stdin.buffer.read()
            pathlib.Path('input-size').write_text(str(len(payload)))
        """)
        )
        for mode in ("duplex", "duplex-threaded"):
            with self.subTest(mode=mode):
                result = self.worker(mode)
                self.assertIsNone(result["error"])
                self.assertEqual(result["returncode"], 0)
                self.assertEqual((self.root / "input-size").read_text(), "2000000")

    def pi_executable(self, source):
        path = self.root / "pi"
        path.write_text("#!/usr/bin/env python3\n" + textwrap.dedent(source))
        path.chmod(0o755)

    def test_settled_pi_preserves_background_group_and_flushes_session(self):
        self.pi_executable("""
            import json, pathlib, subprocess, sys
            from scripts.riff_core.process import identity
            json.loads(sys.stdin.readline())
            child_code = "import pathlib,time; exec('while not pathlib.Path(\\\"release-background\\\").exists(): time.sleep(0.01)'); pathlib.Path('background-completed').touch()"
            child = subprocess.Popen([sys.executable, '-c', child_code])
            pathlib.Path('background-child.json').write_text(json.dumps(identity(child.pid)))
            sys.stdout.write(json.dumps({'type':'message_end','message':{'role':'assistant','content':[{'type':'text','text':'settled artifact'}]}}) + '\\n' + json.dumps({'type':'agent_settled'}) + '\\n')
            sys.stdout.flush()
            sys.stdin.read()
            pathlib.Path('session-flushed').touch()
        """)
        result = self.worker("pi-settled")
        self.assertTrue(result["ok"])
        self.assertEqual(result["artifact"], "settled artifact")
        self.assertLess(result["elapsed"], 3)
        self.assertTrue((self.root / "session-flushed").exists())
        self.assertEqual(result["metadata"]["descendants"], "alive")
        self.assertTrue(result["metadata"]["output_truncated"])
        child = json.loads((self.root / "background-child.json").read_text())
        self.assertEqual(process_state(child), "alive")
        self.assertIn("drain deadline", (self.root / "log").read_text())
        (self.root / "release-background").touch()
        deadline = time.monotonic() + 3
        while (
            not (self.root / "background-completed").exists()
            and time.monotonic() < deadline
        ):
            time.sleep(0.02)
        self.assertTrue((self.root / "background-completed").exists())

    def test_pi_timeout_and_parse_exception_bound_escaped_pipe_capture(self):
        for mode in ("timeout", "exception"):
            with self.subTest(mode=mode):
                self.pi_executable(
                    """
                    import json, pathlib, subprocess, sys, time
                    from scripts.riff_core.process import identity
                    json.loads(sys.stdin.readline())
                    child = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(30)'], start_new_session=True)
                    pathlib.Path('escaped-child.json').write_text(json.dumps(identity(child.pid)))
                    print(__EVENT__, flush=True)
                    time.sleep(30)
                """.replace(
                        "__EVENT__",
                        repr(
                            '[]\n{"type":"captured-after-malformed"}'
                            if mode == "exception"
                            else '{"type":"synthetic-progress"}'
                        ),
                    )
                )
                try:
                    result = self.worker("pi-" + mode)
                    self.assertLess(result["elapsed"], 4)
                    if mode == "timeout":
                        self.assertEqual(result["error_type"], "timeout")
                    else:
                        self.assertIn("exception", result)
                        self.assertIn(
                            "captured-after-malformed", (self.root / "log").read_text()
                        )
                    self.assertIn("drain deadline", (self.root / "log").read_text())
                    self.assertEqual(
                        process_state(
                            json.loads((self.root / "escaped-child.json").read_text())
                        ),
                        "alive",
                    )
                finally:
                    self.cleanup_children()

    def test_timeout_cleans_a_group_after_its_unreaped_leader_exits(self):
        (self.root / "native.py").write_text(
            textwrap.dedent("""
            import json, pathlib, subprocess, sys
            from scripts.riff_core.process import identity
            child = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(30)'])
            pathlib.Path('grandchild.json').write_text(json.dumps(identity(child.pid)))
            print('ready', flush=True)
        """)
        )
        result = self.worker("timeout")
        self.assertIn("timed out", result["error"])
        self.assertEqual(result["returncode"], 0)
        self.assertEqual(result["metadata"]["cleanup"]["group_proof"], "terminated")
        self.assertEqual(
            process_state(json.loads((self.root / "grandchild.json").read_text())),
            "gone",
        )

    def test_incomplete_identity_does_not_prevent_owned_timeout_cleanup(self):
        (self.root / "native.py").write_text(
            textwrap.dedent("""
            import json, os, pathlib, time
            from scripts.riff_core.process import identity
            pathlib.Path('actual-child.json').write_text(json.dumps(identity()))
            print('ready', flush=True)
            time.sleep(30)
        """)
        )
        result = self.worker("incomplete-identity")
        self.assertIn("timed out", result["error"])
        self.assertEqual(result["metadata"]["cleanup"]["group_proof"], "terminated")
        self.assertEqual(
            process_state(json.loads((self.root / "actual-child.json").read_text())),
            "gone",
        )

    def test_pi_missing_final_artifact_cleans_its_owned_background_group(self):
        self.pi_executable("""
            import json, pathlib, subprocess, sys
            from scripts.riff_core.process import identity
            json.loads(sys.stdin.readline())
            child = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(30)'])
            pathlib.Path('grandchild.json').write_text(json.dumps(identity(child.pid)))
            print(json.dumps({'type':'message_end','message':{'role':'assistant','content':[]}}), flush=True)
            print(json.dumps({'type':'agent_settled'}), flush=True)
            sys.stdin.read()
        """)
        result = self.worker("pi-empty-artifact")
        self.assertEqual(result["error_type"], "parse")
        self.assertEqual(result["metadata"]["cleanup"]["group_proof"], "terminated")
        self.assertEqual(
            process_state(json.loads((self.root / "grandchild.json").read_text())),
            "gone",
        )

    def test_pi_early_exit_cleans_grandchild_without_waiting_for_turn_timeout(self):
        self.pi_executable("""
            import json, pathlib, subprocess, sys
            from scripts.riff_core.process import identity
            json.loads(sys.stdin.readline())
            child = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(30)'])
            pathlib.Path('grandchild.json').write_text(json.dumps(identity(child.pid)))
            print('{"type":"synthetic-progress"}', flush=True)
        """)
        result = self.worker("pi-early-exit")
        self.assertEqual(result["error_type"], "process")
        self.assertLess(result["elapsed"], 2)
        self.assertEqual(result["metadata"]["cleanup"]["group_proof"], "terminated")
        self.assertEqual(
            process_state(json.loads((self.root / "grandchild.json").read_text())),
            "gone",
        )

    def test_portable_termination_escalates_when_terminate_is_ignored(self):
        ready = self.root / "ready"
        process = subprocess.Popen(
            [
                sys.executable,
                "-c",
                "import pathlib,signal,sys,time; signal.signal(signal.SIGTERM,signal.SIG_IGN); pathlib.Path(sys.argv[1]).touch(); time.sleep(30)",
                str(ready),
            ]
        )
        try:
            deadline = time.monotonic() + 3
            while not ready.exists() and time.monotonic() < deadline:
                time.sleep(0.01)
            self.assertTrue(ready.exists())
            terminate_process(process, grace_seconds=0.1)
            self.assertEqual(process.returncode, -signal.SIGKILL)
        finally:
            if process.poll() is None:
                process.kill()
                process.wait()
