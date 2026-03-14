"""Pattern matching engine for the expect loop."""

from __future__ import annotations

import re
import select
import time
from collections import deque
from typing import Callable

from tether._errors import EOF as EOFExc
from tether._errors import Timeout as TimeoutExc
from tether._types import EOF_TYPE, TIMEOUT_TYPE, CompiledPattern, Pattern

# Result type from expect_loop.
ExpectResult = tuple[int, str, str, re.Match[str] | str | None]


def compile_pattern(pattern: Pattern) -> CompiledPattern:
    """Compile a single pattern into a ``CompiledPattern``.

    Accepts both the sentinel types (``EOF_TYPE``, ``TIMEOUT_TYPE``) and
    the exception classes (``tether._errors.EOF``, ``tether._errors.Timeout``)
    so that ``import tether.compat as pexpect; child.expect(pexpect.EOF)``
    works correctly.
    """
    if pattern is EOF_TYPE or pattern is EOFExc:
        return CompiledPattern(raw=pattern, regex=None, is_eof=True, is_timeout=False)
    if pattern is TIMEOUT_TYPE or pattern is TimeoutExc:
        return CompiledPattern(raw=pattern, regex=None, is_eof=False, is_timeout=True)
    if isinstance(pattern, re.Pattern):
        return CompiledPattern(raw=pattern, regex=pattern, is_eof=False, is_timeout=False)
    if isinstance(pattern, str):
        return CompiledPattern(
            raw=pattern,
            regex=re.compile(re.escape(pattern)),
            is_eof=False,
            is_timeout=False,
        )
    raise TypeError(f"Unsupported pattern type: {type(pattern)}")


def compile_patterns(patterns: list[Pattern]) -> list[CompiledPattern]:
    """Compile a list of patterns."""
    return [compile_pattern(p) for p in patterns]


def expect_loop(
    fd: int,
    buffer: deque[str],
    patterns: list[CompiledPattern],
    timeout: float,
    read_fn: Callable[[int], str],
) -> ExpectResult:
    """Run the expect loop: read from *fd* and match against *patterns*.

    Args:
        fd: File descriptor to read from (master PTY).
        buffer: Shared str buffer (deque used as accumulator).
        patterns: Compiled patterns to match against.
        timeout: Maximum seconds to wait. Negative means no timeout.
        read_fn: Callable ``(fd) -> str`` that reads decoded text.
            Should raise ``EOFError`` when the slave side closes.

    Returns:
        ``(pattern_index, before, after, match)``
    """
    # Flatten buffer into a single working string.
    incoming = "".join(buffer)
    buffer.clear()

    end_time = time.monotonic() + timeout if timeout >= 0 else None

    while True:
        # --- Try to match regex/exact patterns in current buffer ---
        result = _search_patterns(incoming, patterns)
        if result is not None:
            idx, before, after, match_obj = result
            remainder = incoming[len(before) + len(after):]
            if remainder:
                buffer.append(remainder)
            return (idx, before, after, match_obj)

        # --- Check timeout ---
        if end_time is not None:
            remaining = end_time - time.monotonic()
            if remaining <= 0:
                return _on_timeout(incoming, patterns, buffer)
            wait: float | None = remaining
        else:
            wait = None

        # --- Wait for data ---
        try:
            readable, _, _ = select.select([fd], [], [], wait)
        except (ValueError, OSError):
            readable = []

        if readable:
            try:
                chunk = read_fn(fd)
                if chunk:
                    incoming += chunk
                    continue
            except EOFError:
                pass
            # Fall through: EOF on fd.
            return _on_eof(incoming, patterns, buffer)
        else:
            # No data — timeout or fd error.
            if end_time is not None and time.monotonic() >= end_time:
                return _on_timeout(incoming, patterns, buffer)
            # Infinite wait + no readable → fd likely closed.
            try:
                chunk = read_fn(fd)
                if chunk:
                    incoming += chunk
                    continue
            except EOFError:
                pass
            return _on_eof(incoming, patterns, buffer)


def _search_patterns(
    text: str,
    patterns: list[CompiledPattern],
) -> tuple[int, str, str, re.Match[str] | str | None] | None:
    """Find the earliest matching pattern in *text*.

    Picks the match closest to the start; ties broken by pattern list order.
    """
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


def _on_eof(
    incoming: str,
    patterns: list[CompiledPattern],
    buffer: deque[str],
) -> ExpectResult:
    """Handle EOF. Return EOF pattern result or raise ``tether.EOF``."""
    for i, pat in enumerate(patterns):
        if pat.is_eof:
            if incoming:
                buffer.append(incoming)
            return (i, incoming, "EOF", None)
    raise EOFExc(before=incoming)


def _on_timeout(
    incoming: str,
    patterns: list[CompiledPattern],
    buffer: deque[str],
) -> ExpectResult:
    """Handle timeout. Return TIMEOUT pattern result or raise ``tether.Timeout``."""
    for i, pat in enumerate(patterns):
        if pat.is_timeout:
            if incoming:
                buffer.append(incoming)
            return (i, incoming, "TIMEOUT", None)
    raise TimeoutExc(pattern=repr([p.raw for p in patterns]))
