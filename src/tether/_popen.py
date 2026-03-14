"""PopenSpawn — non-PTY process interaction via pipes."""

from __future__ import annotations

import os
import re
import select
import shlex
import subprocess
import time
from collections import deque
from typing import TYPE_CHECKING

from tether._errors import EOF as EOFExc
from tether._errors import Timeout as TimeoutExc
from tether._expect import compile_patterns
from tether._types import CompiledPattern, Pattern

if TYPE_CHECKING:
    from types import TracebackType


class PopenSpawn:
    """Spawn a process using pipes instead of a PTY.

    Works on systems without PTY support (e.g. Windows).
    No echo stripping needed since pipes don't echo input.

    Example::

        with PopenSpawn("echo hello") as child:
            child.expect("hello")
    """

    before: str
    after: str
    match: re.Match[str] | str | None
    timeout: float
    encoding: str

    def __init__(
        self,
        command: str | list[str],
        *,
        timeout: float = 30,
        encoding: str = "utf-8",
        env: dict[str, str] | None = None,
        cwd: str | None = None,
    ) -> None:
        if isinstance(command, str):
            argv = shlex.split(command)
        else:
            argv = list(command)

        self._proc = subprocess.Popen(
            argv,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            env=env,
            cwd=cwd,
        )
        self.timeout = timeout
        self.encoding = encoding
        self.before = ""
        self.after = ""
        self.match = None
        self._buffer: deque[str] = deque()
        self._eof = False

    # ---- Context manager ----

    def __enter__(self) -> PopenSpawn:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None:
        self.close()

    # ---- Expect methods ----

    def expect(
        self,
        pattern: Pattern | list[Pattern],
        *,
        timeout: float = -1,
    ) -> int:
        """Wait for pattern(s) in process output."""
        if isinstance(pattern, list):
            return self.expect_list(pattern, timeout=timeout)
        return self.expect_list([pattern], timeout=timeout)

    def expect_exact(
        self,
        pattern: str | list[str],
        *,
        timeout: float = -1,
    ) -> int:
        """Wait for exact string(s) in process output."""
        if isinstance(pattern, str):
            patterns: list[Pattern] = [pattern]
        else:
            patterns = list(pattern)
        return self.expect_list(patterns, timeout=timeout)

    def expect_list(
        self,
        patterns: list[Pattern],
        *,
        timeout: float = -1,
    ) -> int:
        """Wait for any of the given patterns. Returns matched index."""
        if timeout < 0:
            timeout = self.timeout

        compiled = compile_patterns(patterns)
        idx, before, after, match_obj = self._expect_loop(compiled, timeout)
        self.before = before
        self.after = after
        self.match = match_obj
        return idx

    # ---- Send methods ----

    def send(self, s: str) -> int:
        """Send string *s* to the process stdin."""
        if self._proc.stdin is None:
            raise OSError("stdin pipe is closed")
        data = s.encode(self.encoding)
        self._proc.stdin.write(data)
        self._proc.stdin.flush()
        return len(data)

    def sendline(self, s: str = "") -> int:
        """Send string *s* followed by a newline."""
        return self.send(s + "\n")

    def sendeof(self) -> None:
        """Close stdin pipe (send EOF)."""
        if self._proc.stdin is not None:
            self._proc.stdin.close()

    def sendcontrol(self, char: str) -> int:
        """Send a control character."""
        char = char.lower()
        code = ord(char) - ord("a") + 1
        if not 1 <= code <= 26:
            raise ValueError(f"Invalid control character: {char!r}")
        return self.send(chr(code))

    # ---- Process control ----

    def isalive(self) -> bool:
        """Return True if the child process is still running."""
        return self._proc.poll() is None

    def wait(self) -> int:
        """Wait for the child to exit and return the exit code."""
        return self._proc.wait()

    def close(self) -> None:
        """Close pipes and terminate the process."""
        if self._proc.stdin is not None:
            try:
                self._proc.stdin.close()
            except OSError:
                pass
        if self._proc.stdout is not None:
            try:
                self._proc.stdout.close()
            except OSError:
                pass
        try:
            self._proc.terminate()
        except OSError:
            pass
        try:
            self._proc.wait(timeout=3)
        except subprocess.TimeoutExpired:
            self._proc.kill()

    # ---- Internal helpers ----

    def _read(self, timeout: float = 0) -> str:
        """Read available data from stdout.

        Uses ``select()`` so the call respects *timeout* instead of
        blocking indefinitely when the child produces no output.

        Returns an empty string when no data is available within *timeout*.
        Raises ``EOFError`` when the child's stdout is closed.
        """
        if self._eof or self._proc.stdout is None:
            raise EOFError
        fd = self._proc.stdout.fileno()
        ready, _, _ = select.select([fd], [], [], timeout)
        if not ready:
            return ""
        data = os.read(fd, 4096)
        if not data:
            self._eof = True
            raise EOFError
        return data.decode(self.encoding, errors="replace")

    def _expect_loop(
        self,
        patterns: list[CompiledPattern],
        timeout: float,
    ) -> tuple[int, str, str, re.Match[str] | str | None]:
        """Read from stdout and match against patterns."""
        incoming = "".join(self._buffer)
        self._buffer.clear()

        end_time = time.monotonic() + timeout if timeout >= 0 else None

        while True:
            result = self._search_patterns(incoming, patterns)
            if result is not None:
                idx, before, after, match_obj = result
                remainder = incoming[len(before) + len(after):]
                if remainder:
                    self._buffer.append(remainder)
                return (idx, before, after, match_obj)

            if end_time is not None:
                remaining = end_time - time.monotonic()
                if remaining <= 0:
                    return self._on_timeout(incoming, patterns)
            else:
                remaining = 30.0

            try:
                chunk = self._read(timeout=min(remaining, 1.0))
                if chunk:
                    incoming += chunk
                    continue
                # No data within poll interval — loop back to re-check timeout.
                continue
            except EOFError:
                pass

            # EOF — check for EOF pattern.
            for i, pat in enumerate(patterns):
                if pat.is_eof:
                    if incoming:
                        self._buffer.append(incoming)
                    return (i, incoming, "EOF", None)
            raise EOFExc(before=incoming)

    @staticmethod
    def _search_patterns(
        text: str,
        patterns: list[CompiledPattern],
    ) -> tuple[int, str, str, re.Match[str] | str | None] | None:
        """Find the earliest matching pattern."""
        best: tuple[int, int, int, re.Match[str] | str | None] | None = None

        for i, pat in enumerate(patterns):
            if pat.regex is None:
                continue
            m = pat.regex.search(text)
            if m is not None:
                start, end = m.start(), m.end()
                if best is None or start < best[1] or (start == best[1] and i < best[0]):
                    if isinstance(pat.raw, str):
                        best = (i, start, end, m.group())
                    else:
                        best = (i, start, end, m)

        if best is not None:
            idx, start, end, match_obj = best
            return (idx, text[:start], text[start:end], match_obj)
        return None

    @staticmethod
    def _on_timeout(
        incoming: str,
        patterns: list[CompiledPattern],
    ) -> tuple[int, str, str, re.Match[str] | str | None]:
        """Handle timeout."""
        for i, pat in enumerate(patterns):
            if pat.is_timeout:
                return (i, incoming, "TIMEOUT", None)
        raise TimeoutExc(pattern=repr([p.raw for p in patterns]))
