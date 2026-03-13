"""Spawn class — core process interaction via PTY."""

from __future__ import annotations

import os
import re
import select
import shlex
import sys
import tty
import termios
from collections import deque
from typing import TYPE_CHECKING

from tether._errors import ExitStatus
from tether._expect import compile_pattern, compile_patterns, expect_loop
from tether._pty import PtyProcess
from tether._types import Pattern

if TYPE_CHECKING:
    from types import TracebackType


class Spawn:
    """Control an interactive process via a pseudo-terminal.

    The primary user-facing API for tether. Spawns a child process in a PTY
    and provides expect-style pattern matching on its output.

    Example::

        with Spawn("python3") as child:
            child.expect(">>> ")
            child.sendline("print('hello')")
            child.expect("hello")

    **pexpect fix (#821):** ``before`` never contains leaked ``sendline`` echo.
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
        dimensions: tuple[int, int] = (24, 80),
    ) -> None:
        if isinstance(command, str):
            argv = shlex.split(command)
        else:
            argv = list(command)

        self._proc = PtyProcess.spawn(argv, env=env, cwd=cwd, dimensions=dimensions)
        self.timeout = timeout
        self.encoding = encoding
        self.before = ""
        self.after = ""
        self.match = None
        self._buffer: deque[str] = deque()
        self._last_sendline: str | None = None  # For echo stripping (#821)
        self._closed = False

    @property
    def proc(self) -> PtyProcess:
        """The underlying PtyProcess."""
        return self._proc

    # ---- Context manager ----

    def __enter__(self) -> Spawn:
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
        """Wait for pattern(s) in process output.

        Args:
            pattern: A single pattern or list of patterns.
            timeout: Seconds to wait. ``-1`` uses ``self.timeout``.

        Returns:
            Index of the matched pattern (0 for a single pattern).
        """
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
        """Wait for any of the given patterns.

        Returns the index of the first pattern that matches.
        """
        if timeout < 0:
            timeout = self.timeout

        compiled = compile_patterns(patterns)

        # Strip echoed sendline input before matching (pexpect fix #821).
        self._strip_echo()

        idx, before, after, match_obj = expect_loop(
            self._proc.fd,
            self._buffer,
            compiled,
            timeout,
            self._read_str,
        )

        self.before = before
        self.after = after
        self.match = match_obj
        return idx

    # ---- Send methods ----

    def send(self, s: str) -> int:
        """Send string *s* to the process. Returns number of bytes written."""
        data = s.encode(self.encoding)
        return self._proc.write(data)

    def sendline(self, s: str = "") -> int:
        """Send string *s* followed by a newline to the process."""
        self._last_sendline = s
        return self.send(s + "\n")

    def sendcontrol(self, char: str) -> int:
        """Send a control character (e.g. ``'c'`` for Ctrl-C)."""
        char = char.lower()
        code = ord(char) - ord("a") + 1
        if not 1 <= code <= 26:
            raise ValueError(f"Invalid control character: {char!r}")
        return self.send(chr(code))

    def sendeof(self) -> None:
        """Send EOF (Ctrl-D) to the process."""
        self.send("\x04")

    def sendintr(self) -> None:
        """Send interrupt (Ctrl-C) to the process."""
        self.send("\x03")

    # ---- Read methods ----

    def read(self, size: int = -1) -> str:
        """Read up to *size* characters from process output.

        If *size* is -1, read all available data.
        """
        # Drain buffer first.
        if self._buffer:
            buffered = "".join(self._buffer)
            self._buffer.clear()
            if size >= 0 and len(buffered) >= size:
                result = buffered[:size]
                remainder = buffered[size:]
                if remainder:
                    self._buffer.append(remainder)
                return result
        else:
            buffered = ""

        # Read more from PTY.
        if size < 0:
            # Read all available.
            chunks = [buffered]
            while True:
                r, _, _ = select.select([self._proc.fd], [], [], 0.1)
                if not r:
                    break
                try:
                    chunk = self._read_str(self._proc.fd)
                    if chunk:
                        chunks.append(chunk)
                    else:
                        break
                except EOFError:
                    break
            return "".join(chunks)
        else:
            needed = size - len(buffered)
            if needed <= 0:
                return buffered[:size]
            try:
                chunk = self._read_str(self._proc.fd)
                data = buffered + chunk
            except EOFError:
                data = buffered
            if len(data) > size:
                self._buffer.append(data[size:])
                return data[:size]
            return data

    def readline(self) -> str:
        """Read a single line from process output."""
        compiled = [compile_pattern("\r\n"), compile_pattern("\n")]
        _, before, after, _match = expect_loop(
            self._proc.fd,
            self._buffer,
            compiled,
            self.timeout,
            self._read_str,
        )
        return before + after

    # ---- Process control ----

    def isalive(self) -> bool:
        """Return True if the child process is still running."""
        return self._proc.isalive()

    def wait(self) -> int:
        """Wait for the child to exit and return the exit code."""
        self._proc.waitpid()
        if self._proc.exitstatus is not None and self._proc.exitstatus != 0:
            raise ExitStatus(
                self._proc.exitstatus,
                signal=self._proc.signalstatus,
            )
        return self._proc.exitstatus or 0

    def close(self, force: bool = True) -> None:
        """Close the child process and PTY."""
        if self._closed:
            return
        self._closed = True
        self._proc.terminate(force=force)
        self._proc.close()

    def terminate(self, force: bool = False) -> bool:
        """Terminate the child process."""
        return self._proc.terminate(force=force)

    def setwinsize(self, rows: int, cols: int) -> None:
        """Set the terminal window size."""
        self._proc.setwinsize(rows, cols)

    def interact(self, escape_character: str = chr(29)) -> None:
        """Interactive passthrough mode.

        Passes stdin to the child and child output to stdout.
        Press *escape_character* (default: Ctrl-]) to exit.
        """
        escape_byte = escape_character.encode(self.encoding)
        stdin_fd = sys.stdin.fileno()
        old_settings = termios.tcgetattr(stdin_fd)
        try:
            tty.setraw(stdin_fd)
            while self.isalive():
                r, _, _ = select.select([stdin_fd, self._proc.fd], [], [], 0.1)
                if stdin_fd in r:
                    data = os.read(stdin_fd, 1024)
                    if escape_byte in data:
                        break
                    self._proc.write(data)
                if self._proc.fd in r:
                    try:
                        data = self._proc.read(1024)
                        if data:
                            os.write(sys.stdout.fileno(), data)
                    except EOFError:
                        break
        finally:
            termios.tcsetattr(stdin_fd, termios.TCSADRAIN, old_settings)

    # ---- Internal helpers ----

    def _read_str(self, fd: int) -> str:
        """Read bytes from *fd* and decode to str. Raises EOFError on EOF."""
        data = self._proc.read(4096)
        if not data:
            raise EOFError
        return data.decode(self.encoding, errors="replace")

    def _strip_echo(self) -> None:
        """Strip echoed sendline input from the front of the buffer.

        PTYs echo input back. When we call sendline("foo"), the PTY echoes
        "foo\\r\\n" into the output stream. We strip this so that ``before``
        never contains the sent text (pexpect issue #821).
        """
        if self._last_sendline is None:
            return

        sent = self._last_sendline
        self._last_sendline = None

        if not sent and not self._buffer:
            return

        # Build possible echo patterns: "sent\r\n" or "sent\n".
        echo_patterns = [
            sent + "\r\n",
            sent + "\n",
        ]

        # Wait briefly for the echo to arrive.
        import time
        deadline = time.monotonic() + 0.5
        while time.monotonic() < deadline:
            buf_text = "".join(self._buffer)
            # Check if any echo pattern is at the start.
            for echo in echo_patterns:
                if buf_text.startswith(echo):
                    self._buffer.clear()
                    remainder = buf_text[len(echo):]
                    if remainder:
                        self._buffer.append(remainder)
                    return

            # If buffer is already longer than the echo, and doesn't start with it, bail.
            if len(buf_text) > len(echo_patterns[0]) + 10:
                return

            # Try to read more data.
            r, _, _ = select.select([self._proc.fd], [], [], min(0.05, deadline - time.monotonic()))
            if r:
                try:
                    chunk = self._read_str(self._proc.fd)
                    if chunk:
                        self._buffer.append(chunk)
                except EOFError:
                    return
