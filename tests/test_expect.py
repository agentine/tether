"""Tests for tether._expect — pattern matching engine."""

import re
from collections import deque

import pytest

from tether._errors import EOF as EOFExc
from tether._errors import Timeout as TimeoutExc
from tether._expect import (
    compile_pattern,
    compile_patterns,
    expect_loop,
)
from tether._types import EOF_TYPE, TIMEOUT_TYPE


class TestCompilePattern:
    def test_string_pattern(self) -> None:
        cp = compile_pattern("hello")
        assert cp.regex is not None
        assert cp.is_eof is False
        assert cp.is_timeout is False
        assert cp.raw == "hello"
        # Should match exact string
        assert cp.regex.search("say hello world") is not None

    def test_string_with_special_chars(self) -> None:
        cp = compile_pattern("foo.*bar")
        assert cp.regex is not None
        # Should be escaped — should NOT match "fooXbar"
        assert cp.regex.search("fooXbar") is None
        assert cp.regex.search("foo.*bar") is not None

    def test_regex_pattern(self) -> None:
        pat = re.compile(r"\d+")
        cp = compile_pattern(pat)
        assert cp.regex is pat
        assert cp.is_eof is False
        assert cp.is_timeout is False

    def test_eof_sentinel(self) -> None:
        cp = compile_pattern(EOF_TYPE)
        assert cp.is_eof is True
        assert cp.regex is None

    def test_timeout_sentinel(self) -> None:
        cp = compile_pattern(TIMEOUT_TYPE)
        assert cp.is_timeout is True
        assert cp.regex is None

    def test_invalid_type_raises(self) -> None:
        with pytest.raises(TypeError, match="Unsupported pattern type"):
            compile_pattern(42)  # type: ignore[arg-type]


class TestCompilePatterns:
    def test_multiple(self) -> None:
        patterns = compile_patterns(["foo", re.compile(r"\d+"), EOF_TYPE])
        assert len(patterns) == 3
        assert patterns[0].raw == "foo"
        assert patterns[1].is_eof is False
        assert patterns[2].is_eof is True


class TestExpectLoop:
    """Test expect_loop with a synthetic read function and pipe fd."""

    @staticmethod
    def _make_pipe_reader(data_chunks: list[str]) -> tuple[int, object]:
        """Create a pipe fd and a read function that yields chunks."""
        r_fd, w_fd = os.pipe()
        import fcntl as _fcntl
        import os as _os

        # Set read end to non-blocking
        flags = _fcntl.fcntl(r_fd, _fcntl.F_GETFL)
        _fcntl.fcntl(r_fd, _fcntl.F_SETFL, flags | _os.O_NONBLOCK)

        # Write all data to the pipe, then close write end
        for chunk in data_chunks:
            _os.write(w_fd, chunk.encode())
        _os.close(w_fd)

        def read_fn(fd: int) -> str:
            try:
                raw = _os.read(fd, 4096)
            except OSError:
                raise EOFError
            if not raw:
                raise EOFError
            return raw.decode()

        return r_fd, read_fn

    def test_simple_match(self) -> None:
        import os

        r_fd, w_fd = os.pipe()
        os.write(w_fd, b"hello world")
        os.close(w_fd)

        buf: deque[str] = deque()

        def read_fn(fd: int) -> str:
            data = os.read(fd, 4096)
            if not data:
                raise EOFError
            return data.decode()

        patterns = compile_patterns(["world"])
        idx, before, after, match = expect_loop(r_fd, buf, patterns, 5.0, read_fn)
        os.close(r_fd)

        assert idx == 0
        assert before == "hello "
        assert after == "world"
        assert match == "world"  # Exact string pattern

    def test_regex_match(self) -> None:
        import os

        r_fd, w_fd = os.pipe()
        os.write(w_fd, b"result: 42 ok")
        os.close(w_fd)

        buf: deque[str] = deque()

        def read_fn(fd: int) -> str:
            data = os.read(fd, 4096)
            if not data:
                raise EOFError
            return data.decode()

        patterns = compile_patterns([re.compile(r"\d+")])
        idx, before, after, match = expect_loop(r_fd, buf, patterns, 5.0, read_fn)
        os.close(r_fd)

        assert idx == 0
        assert before == "result: "
        assert after == "42"
        assert hasattr(match, "group")  # re.Match

    def test_timeout_raises(self) -> None:
        import os

        r_fd, w_fd = os.pipe()
        # Don't write anything, don't close — simulates a long-running process.

        buf: deque[str] = deque()

        def read_fn(fd: int) -> str:
            data = os.read(fd, 4096)
            if not data:
                raise EOFError
            return data.decode()

        patterns = compile_patterns(["never_match"])
        with pytest.raises(TimeoutExc):
            expect_loop(r_fd, buf, patterns, 0.1, read_fn)

        os.close(r_fd)
        os.close(w_fd)

    def test_timeout_sentinel(self) -> None:
        import os

        r_fd, w_fd = os.pipe()

        buf: deque[str] = deque()

        def read_fn(fd: int) -> str:
            data = os.read(fd, 4096)
            if not data:
                raise EOFError
            return data.decode()

        patterns = compile_patterns(["never", TIMEOUT_TYPE])
        idx, before, after, match = expect_loop(r_fd, buf, patterns, 0.1, read_fn)

        os.close(r_fd)
        os.close(w_fd)

        assert idx == 1
        assert after == "TIMEOUT"
        assert match is None

    def test_eof_raises(self) -> None:
        import os

        r_fd, w_fd = os.pipe()
        os.write(w_fd, b"partial data")
        os.close(w_fd)

        buf: deque[str] = deque()

        def read_fn(fd: int) -> str:
            data = os.read(fd, 4096)
            if not data:
                raise EOFError
            return data.decode()

        patterns = compile_patterns(["never_match"])
        with pytest.raises(EOFExc) as exc_info:
            expect_loop(r_fd, buf, patterns, 5.0, read_fn)

        os.close(r_fd)
        assert "partial data" in exc_info.value.before

    def test_eof_sentinel(self) -> None:
        import os

        r_fd, w_fd = os.pipe()
        os.write(w_fd, b"some data")
        os.close(w_fd)

        buf: deque[str] = deque()

        def read_fn(fd: int) -> str:
            data = os.read(fd, 4096)
            if not data:
                raise EOFError
            return data.decode()

        patterns = compile_patterns(["no_match", EOF_TYPE])
        idx, before, after, match = expect_loop(r_fd, buf, patterns, 5.0, read_fn)
        os.close(r_fd)

        assert idx == 1
        assert "some data" in before
        assert after == "EOF"
        assert match is None

    def test_earliest_match_wins(self) -> None:
        """When multiple patterns match, the one at the earliest position wins."""
        import os

        r_fd, w_fd = os.pipe()
        os.write(w_fd, b"aaa bbb ccc")
        os.close(w_fd)

        buf: deque[str] = deque()

        def read_fn(fd: int) -> str:
            data = os.read(fd, 4096)
            if not data:
                raise EOFError
            return data.decode()

        patterns = compile_patterns(["ccc", "bbb", "aaa"])
        idx, before, after, match = expect_loop(r_fd, buf, patterns, 5.0, read_fn)
        os.close(r_fd)

        # "aaa" appears first in the text
        assert idx == 2
        assert after == "aaa"

    def test_buffered_data(self) -> None:
        """Data already in the buffer should be matched before reading."""
        import os

        r_fd, w_fd = os.pipe()
        os.close(w_fd)

        buf: deque[str] = deque(["hello world"])

        def read_fn(fd: int) -> str:
            raise EOFError

        patterns = compile_patterns(["world"])
        idx, before, after, match = expect_loop(r_fd, buf, patterns, 5.0, read_fn)
        os.close(r_fd)

        assert idx == 0
        assert before == "hello "
        assert after == "world"


# Need this import at the module level for _make_pipe_reader
import os  # noqa: E402
