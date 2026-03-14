"""AsyncSpawn — native async/await process interaction via PTY."""

from __future__ import annotations

import asyncio
import re
import shlex
from collections import deque
from typing import TYPE_CHECKING

from tether._errors import EOF as EOFExc
from tether._errors import ExitStatus
from tether._errors import Timeout as TimeoutExc
from tether._expect import compile_patterns
from tether._pty import PtyProcess
from tether._types import CompiledPattern, Pattern

if TYPE_CHECKING:
    from types import TracebackType


class AsyncSpawn:
    """Async process interaction via a pseudo-terminal.

    Pure ``async def`` throughout — no deprecated ``@asyncio.coroutine``.

    Example::

        async with AsyncSpawn("python3") as child:
            await child.expect(">>> ")
            await child.sendline("print(42)")
            await child.expect("42")
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
        self._last_sendline: str | None = None
        self._closed = False

    # ---- Async context manager ----

    async def __aenter__(self) -> AsyncSpawn:
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None:
        await self.close()

    # ---- Expect methods ----

    async def expect(
        self,
        pattern: Pattern | list[Pattern],
        *,
        timeout: float = -1,
    ) -> int:
        """Wait for pattern(s) in process output."""
        if isinstance(pattern, list):
            return await self.expect_list(pattern, timeout=timeout)
        return await self.expect_list([pattern], timeout=timeout)

    async def expect_exact(
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
        return await self.expect_list(patterns, timeout=timeout)

    async def expect_list(
        self,
        patterns: list[Pattern],
        *,
        timeout: float = -1,
    ) -> int:
        """Wait for any of the given patterns. Returns matched index."""
        if timeout < 0:
            timeout = self.timeout

        compiled = compile_patterns(patterns)

        # Strip echoed sendline input.
        await self._strip_echo()

        idx, before, after, match_obj = await self._async_expect_loop(
            compiled, timeout
        )

        self.before = before
        self.after = after
        self.match = match_obj
        return idx

    # ---- Send methods ----

    async def send(self, s: str) -> int:
        """Send string *s* to the process."""
        data = s.encode(self.encoding)
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, self._proc.write, data)

    async def sendline(self, s: str = "") -> int:
        """Send string *s* followed by a newline."""
        self._last_sendline = s
        return await self.send(s + "\n")

    async def sendcontrol(self, char: str) -> int:
        """Send a control character (e.g. ``'c'`` for Ctrl-C)."""
        char = char.lower()
        code = ord(char) - ord("a") + 1
        if not 1 <= code <= 26:
            raise ValueError(f"Invalid control character: {char!r}")
        return await self.send(chr(code))

    async def sendeof(self) -> None:
        """Send EOF (Ctrl-D) to the process."""
        await self.send("\x04")

    async def sendintr(self) -> None:
        """Send interrupt (Ctrl-C) to the process."""
        await self.send("\x03")

    # ---- Read methods ----

    async def read(self, size: int = -1) -> str:
        """Read up to *size* characters from process output."""
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

        if size < 0:
            chunks = [buffered]
            while True:
                try:
                    chunk = await self._async_read(timeout=0.1)
                    if chunk:
                        chunks.append(chunk)
                    else:
                        break
                except (EOFError, asyncio.TimeoutError):
                    break
            return "".join(chunks)
        else:
            needed = size - len(buffered)
            if needed <= 0:
                return buffered[:size]
            try:
                chunk = await self._async_read(timeout=self.timeout)
                data = buffered + chunk
            except EOFError:
                data = buffered
            if len(data) > size:
                self._buffer.append(data[size:])
                return data[:size]
            return data

    async def readline(self) -> str:
        """Read a single line from process output."""
        compiled = compile_patterns(["\r\n", "\n"])
        _, before, after, _ = await self._async_expect_loop(compiled, self.timeout)
        return before + after

    # ---- Process control ----

    async def isalive(self) -> bool:
        """Return True if the child process is still running."""
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, self._proc.isalive)

    async def wait(self) -> int:
        """Wait for the child to exit and return the exit code."""
        while self._proc.isalive():
            await asyncio.sleep(0.05)
        self._proc.waitpid()
        if self._proc.exitstatus is not None and self._proc.exitstatus != 0:
            raise ExitStatus(
                self._proc.exitstatus,
                signal=self._proc.signalstatus,
            )
        return self._proc.exitstatus or 0

    async def close(self, force: bool = True) -> None:
        """Close the child process and PTY."""
        if self._closed:
            return
        self._closed = True
        self._proc.terminate(force=force)
        self._proc.close()

    async def terminate(self, force: bool = False) -> bool:
        """Terminate the child process."""
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, self._proc.terminate, force)

    async def setwinsize(self, rows: int, cols: int) -> None:
        """Set the terminal window size."""
        loop = asyncio.get_running_loop()
        await loop.run_in_executor(None, self._proc.setwinsize, rows, cols)

    # ---- Internal helpers ----

    async def _async_read(self, timeout: float = 0) -> str:
        """Read from PTY fd asynchronously using the event loop."""
        loop = asyncio.get_running_loop()
        fut: asyncio.Future[str] = loop.create_future()

        def _on_readable() -> None:
            loop.remove_reader(self._proc.fd)
            if fut.done():
                return
            try:
                data = self._proc.read(4096)
                if not data:
                    fut.set_exception(EOFError())
                else:
                    fut.set_result(data.decode(self.encoding, errors="replace"))
            except (OSError, EOFError) as e:
                if not fut.done():
                    fut.set_exception(EOFError(str(e)))

        loop.add_reader(self._proc.fd, _on_readable)
        try:
            if timeout > 0:
                return await asyncio.wait_for(asyncio.shield(fut), timeout=timeout)
            else:
                return await fut
        except asyncio.TimeoutError:
            loop.remove_reader(self._proc.fd)
            if not fut.done():
                fut.cancel()
            raise
        except (asyncio.CancelledError, EOFError):
            loop.remove_reader(self._proc.fd)
            raise

    async def _async_expect_loop(
        self,
        patterns: list[CompiledPattern],
        timeout: float,
    ) -> tuple[int, str, str, re.Match[str] | str | None]:
        """Async version of the expect loop."""
        incoming = "".join(self._buffer)
        self._buffer.clear()

        deadline = asyncio.get_running_loop().time() + timeout if timeout >= 0 else None

        while True:
            # Try to match patterns in current buffer.
            result = self._search_patterns(incoming, patterns)
            if result is not None:
                idx, before, after, match_obj = result
                remainder = incoming[len(before) + len(after):]
                if remainder:
                    self._buffer.append(remainder)
                return (idx, before, after, match_obj)

            # Check timeout.
            if deadline is not None:
                remaining = deadline - asyncio.get_running_loop().time()
                if remaining <= 0:
                    return self._on_timeout(incoming, patterns)
            else:
                remaining = 30.0  # Large default for infinite wait.

            # Wait for data.
            try:
                chunk = await self._async_read(timeout=min(remaining, 1.0))
                if chunk:
                    incoming += chunk
                    continue
            except asyncio.TimeoutError:
                if deadline is not None and asyncio.get_running_loop().time() >= deadline:
                    return self._on_timeout(incoming, patterns)
                continue
            except EOFError:
                pass

            # EOF — check for EOF pattern.
            return self._on_eof(incoming, patterns)

    @staticmethod
    def _search_patterns(
        text: str,
        patterns: list[CompiledPattern],
    ) -> tuple[int, str, str, re.Match[str] | str | None] | None:
        """Find the earliest matching pattern in *text*."""
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
    def _on_eof(
        incoming: str,
        patterns: list[CompiledPattern],
    ) -> tuple[int, str, str, re.Match[str] | str | None]:
        """Handle EOF."""
        for i, pat in enumerate(patterns):
            if pat.is_eof:
                return (i, incoming, "EOF", None)
        raise EOFExc(before=incoming)

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

    async def _strip_echo(self) -> None:
        """Strip echoed sendline input from the buffer."""
        if self._last_sendline is None:
            return

        sent = self._last_sendline
        self._last_sendline = None

        if not sent and not self._buffer:
            return

        echo_patterns = [sent + "\r\n", sent + "\n"]

        deadline = asyncio.get_running_loop().time() + 0.5
        while asyncio.get_running_loop().time() < deadline:
            buf_text = "".join(self._buffer)
            for echo in echo_patterns:
                if buf_text.startswith(echo):
                    self._buffer.clear()
                    remainder = buf_text[len(echo):]
                    if remainder:
                        self._buffer.append(remainder)
                    return

            if len(buf_text) > len(echo_patterns[0]) + 10:
                return

            remaining = deadline - asyncio.get_running_loop().time()
            try:
                chunk = await self._async_read(timeout=min(0.05, remaining))
                if chunk:
                    self._buffer.append(chunk)
            except (asyncio.TimeoutError, EOFError):
                return
