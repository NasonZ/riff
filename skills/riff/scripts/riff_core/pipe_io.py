"""Duplex pipe transport with a bounded final drain.

POSIX uses raw, nonblocking descriptors. The portable backend uses independent
readers and a writer, since Windows selectors cannot wait on anonymous pipes.
"""

from __future__ import annotations

import os
import queue
import selectors
import subprocess
import threading
import time
from typing import Callable

DRAIN_SECONDS = 0.5


class PipeIO:
    def __init__(
        self,
        process: subprocess.Popen,
        payload: bytes = b"",
        *,
        keep_stdin: bool = False,
        threaded: bool | None = None,
    ):
        self.process = process
        self.payload = payload
        self.keep_stdin = keep_stdin
        self.threaded = os.name != "posix" if threaded is None else threaded
        self.outputs = {"stdout", "stderr"}
        self.stop = threading.Event()
        self.input_done = threading.Event()
        self.input_close_requested = threading.Event()
        self.threads = []
        self.thread_owned = set()
        process.riff_pipe_io = self
        self.selector = None
        self.events = queue.Queue(maxsize=16)
        if self.threaded:
            try:
                for name in (*self.outputs, "stdin"):
                    target = self._writer if name == "stdin" else self._reader
                    args = () if name == "stdin" else (name, getattr(process, name))
                    thread = threading.Thread(
                        target=target, args=args, name=f"riff-{name}", daemon=True
                    )
                    self.thread_owned.add(name)
                    try:
                        thread.start()
                    except BaseException:
                        self.thread_owned.remove(name)
                        raise
                    self.threads.append(thread)
            except BaseException:
                self.close()
                raise
        else:
            self.selector = selectors.DefaultSelector()
            try:
                for name in self.outputs:
                    self.selector.register(
                        getattr(process, name), selectors.EVENT_READ, name
                    )
                os.set_blocking(process.stdin.fileno(), False)
                if payload:
                    self.selector.register(
                        process.stdin, selectors.EVENT_WRITE, "stdin"
                    )
                else:
                    self.input_done.set()
                    if not keep_stdin:
                        self.finish_input()
            except BaseException:
                self.close()
                raise

    def _emit(self, name, value):
        while not self.stop.is_set():
            try:
                self.events.put((name, value), timeout=0.05)
                return
            except queue.Full:
                pass

    def _reader(self, name, stream):
        try:
            fd = stream.fileno()
            while not self.stop.is_set():
                chunk = os.read(fd, 65536)
                if self.stop.is_set():
                    return
                self._emit(name, chunk)
                if not chunk:
                    return
        except OSError as error:
            if not self.stop.is_set():
                self._emit(name, error)
        finally:
            stream.close()

    def _writer(self):
        try:
            fd = self.process.stdin.fileno()
            while self.payload and not self.stop.is_set():
                try:
                    count = os.write(fd, self.payload[:65536])
                    self.payload = self.payload[count:]
                except BlockingIOError:
                    self.stop.wait(0.01)
            self.input_done.set()
            if self.keep_stdin and not self.stop.is_set():
                self.input_close_requested.wait()
        except BrokenPipeError:
            pass
        except (OSError, ValueError) as error:
            if not self.stop.is_set():
                self._emit("stdin", error)
        finally:
            self.process.stdin.close()
            self.input_done.set()

    def read(self, timeout: float) -> list[tuple[str, bytes]]:
        chunks = []
        if self.threaded:
            try:
                name, value = self.events.get(timeout=max(0, timeout))
            except queue.Empty:
                return chunks
            if isinstance(value, BaseException):
                raise value
            if value:
                chunks.append((name, value))
            else:
                self.outputs.discard(name)
            return chunks
        for key, _ in self.selector.select(max(0, timeout)):
            if key.data == "stdin":
                try:
                    count = os.write(key.fd, self.payload[:65536])
                    self.payload = self.payload[count:]
                except BlockingIOError:
                    continue
                except BrokenPipeError:
                    self.payload = b""
                if not self.payload:
                    self.input_done.set()
                    self.selector.unregister(key.fileobj)
                    if not self.keep_stdin:
                        self.process.stdin.close()
                continue
            chunk = os.read(key.fd, 65536)
            if chunk:
                chunks.append((key.data, chunk))
            else:
                self.selector.unregister(key.fileobj)
                self.outputs.discard(key.data)
        return chunks

    def finish_input(self):
        self.payload = b""
        self.input_done.set()
        if self.threaded:
            self.input_close_requested.set()
            return
        if self.selector is not None:
            try:
                self.selector.unregister(self.process.stdin)
            except (KeyError, ValueError):
                pass
        if not self.process.stdin.closed:
            self.process.stdin.close()

    def drain(
        self, consume: Callable[[str, bytes], None], seconds: float = DRAIN_SECONDS
    ) -> bool:
        deadline = time.monotonic() + seconds
        while self.outputs and time.monotonic() < deadline:
            for name, chunk in self.read(
                min(0.05, max(0, deadline - time.monotonic()))
            ):
                consume(name, chunk)
        return not self.outputs

    def close(self):
        self.stop.set()
        self.input_close_requested.set()
        if self.threaded:
            # Each OS reader/writer owns its descriptor until its syscall returns.
            # Main-thread CRT close is not assumed to be nonblocking or safe.
            deadline = time.monotonic() + 0.1
            for thread in self.threads:
                thread.join(timeout=max(0, deadline - time.monotonic()))
            for name in ("stdin", "stdout", "stderr"):
                stream = getattr(self.process, name)
                if (
                    name not in self.thread_owned
                    and stream is not None
                    and not stream.closed
                ):
                    stream.close()
            return
        if self.selector is not None:
            self.selector.close()
        for stream in (self.process.stdin, self.process.stdout, self.process.stderr):
            if stream is not None and not stream.closed:
                stream.close()


def close_process_pipes(process: subprocess.Popen) -> None:
    transport = getattr(process, "riff_pipe_io", None)
    if transport is not None:
        transport.close()
    else:
        for stream in (process.stdin, process.stdout, process.stderr):
            if stream is not None and not stream.closed:
                stream.close()
