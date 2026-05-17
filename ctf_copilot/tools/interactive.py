"""Interactive, stateful tools — the research-identified #1 lever (EnIGMA).

Two long-lived primitives the agent drives across turns:
  * ``InteractiveProc`` — a child process (gdb/REPL/local binary) over pipes
    with a background reader thread. No pty, so it works on Windows too.
  * ``TcpTube`` — a raw TCP connection (remote pwn / misc services).

Both keep a *bounded* rolling buffer and ``read()`` drains only the bytes
seen since the last read, so per-turn token cost stays flat regardless of how
chatty the program/service is. The caller (solver) further truncates for the
LLM and persists nothing huge.
"""
from __future__ import annotations

import socket
import subprocess
import threading
import time

from ..core.proc import NO_WINDOW

MAX_BUFFER = 256 * 1024  # ring cap per session (bytes kept in memory)


class _Pump:
    """Shared bounded reader: a background thread appends to a capped buffer;
    read() returns and clears what's accumulated."""

    def __init__(self) -> None:
        self._buf = bytearray()
        self._lock = threading.Lock()
        self._closed = False
        self._err = ""

    def _feed(self, chunk: bytes) -> None:
        if not chunk:
            return
        with self._lock:
            self._buf.extend(chunk)
            if len(self._buf) > MAX_BUFFER:
                del self._buf[:-MAX_BUFFER]

    def read(self, wait: float = 0.4, cap: int = 8192) -> str:
        """Brief settle wait, then drain the buffer (newest `cap` bytes)."""
        if wait > 0:
            time.sleep(min(wait, 3.0))
        with self._lock:
            data = bytes(self._buf[-cap:])
            self._buf.clear()
        return data.decode("utf-8", "replace")

    @property
    def closed(self) -> bool:
        return self._closed

    @property
    def error(self) -> str:
        return self._err


class InteractiveProc(_Pump):
    def __init__(self, argv: list[str], cwd: str) -> None:
        super().__init__()
        self.argv = argv
        self._p = subprocess.Popen(
            argv, cwd=cwd, stdin=subprocess.PIPE,
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            bufsize=0, shell=False, **NO_WINDOW,
        )
        self._t = threading.Thread(target=self._reader, daemon=True)
        self._t.start()

    def _reader(self) -> None:
        try:
            assert self._p.stdout is not None
            while True:
                chunk = self._p.stdout.read(4096)
                if not chunk:
                    break
                self._feed(chunk)
        except Exception as e:  # noqa: BLE001
            self._err = str(e)
        finally:
            self._closed = True

    def send(self, data: str, newline: bool = True) -> None:
        if self._p.stdin is None:
            raise RuntimeError("process stdin closed")
        payload = data.encode("utf-8", "replace")
        if newline and not payload.endswith(b"\n"):
            payload += b"\n"
        self._p.stdin.write(payload)
        self._p.stdin.flush()

    def close(self) -> None:
        try:
            self._p.kill()
        except Exception:  # noqa: BLE001
            pass
        self._closed = True


class TcpTube(_Pump):
    def __init__(self, host: str, port: int, connect_timeout: float = 10.0):
        super().__init__()
        self.host, self.port = host, port
        self._s = socket.create_connection((host, port), connect_timeout)
        self._s.settimeout(0.5)
        self._t = threading.Thread(target=self._reader, daemon=True)
        self._t.start()

    def _reader(self) -> None:
        try:
            while True:
                try:
                    chunk = self._s.recv(4096)
                except socket.timeout:
                    continue
                except OSError:
                    break
                if not chunk:
                    break
                self._feed(chunk)
        except Exception as e:  # noqa: BLE001
            self._err = str(e)
        finally:
            self._closed = True

    def send(self, data: str, newline: bool = True) -> None:
        payload = data.encode("utf-8", "replace")
        if newline and not payload.endswith(b"\n"):
            payload += b"\n"
        self._s.sendall(payload)

    def close(self) -> None:
        try:
            self._s.close()
        except Exception:  # noqa: BLE001
            pass
        self._closed = True
