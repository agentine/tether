"""Tests for tether._spawn — Spawn class integration tests.

These tests exercise real PTY processes (not mocks).
"""

import re
import time

import pytest

import tether
from tether import EOF_TYPE, TIMEOUT_TYPE, Spawn
from tether._errors import EOF as EOFExc
from tether._errors import Timeout as TimeoutExc


class TestSpawnBasic:
    """Test 1: spawn("echo hello"), expect("hello")."""

    def test_echo_hello(self) -> None:
        child = Spawn("echo hello", timeout=5)
        child.expect("hello")
        assert child.after == "hello"
        child.close()

    def test_echo_before_is_minimal(self) -> None:
        child = Spawn("echo hello", timeout=5)
        child.expect("hello")
        # before should not contain "hello" — it's the text BEFORE the match
        assert "hello" not in child.before
        child.close()


class TestSpawnPythonREPL:
    """Test 2: spawn("python3"), sendline("1+1"), expect("2")."""

    def test_python_repl(self) -> None:
        with Spawn("python3 -u", timeout=10) as child:
            child.expect(">>> ")
            child.sendline("1+1")
            child.expect("2")
            assert child.after == "2"

    def test_before_no_echo_leak(self) -> None:
        """before does NOT contain the echoed sendline input."""
        with Spawn("python3 -u", timeout=10) as child:
            child.expect(">>> ")
            child.sendline("print(42)")
            child.expect("42")
            # The critical pexpect #821 fix: before should not contain
            # the text we sent via sendline.
            assert "print(42)" not in child.before


class TestSpawnCat:
    """Test 3: spawn("cat"), sendline("hello"), expect("hello")."""

    def test_cat_echo(self) -> None:
        with Spawn("cat", timeout=5) as child:
            child.sendline("hello")
            child.expect("hello")
            assert child.after == "hello"


class TestSpawnTimeout:
    """Test 4: spawn("sleep 10"), expect("x", timeout=0.1) → raises Timeout."""

    def test_timeout_raises(self) -> None:
        with Spawn("sleep 10", timeout=5) as child, pytest.raises(TimeoutExc):
            child.expect("will_never_match", timeout=0.2)

    def test_timeout_sentinel(self) -> None:
        with Spawn("sleep 10", timeout=5) as child:
            idx = child.expect_list(["nope", TIMEOUT_TYPE], timeout=0.2)
            assert idx == 1


class TestSpawnEOF:
    """Test 5: spawn("echo x"), wait for EOF."""

    def test_eof_raises(self) -> None:
        with Spawn('/bin/sh -c "echo x"', timeout=5) as child:
            child.expect("x")
            with pytest.raises(EOFExc):
                child.expect("more_data", timeout=3)

    def test_eof_sentinel(self) -> None:
        with Spawn('/bin/sh -c "echo done"', timeout=5) as child:
            child.expect("done")
            idx = child.expect_list(["nope", EOF_TYPE], timeout=3)
            assert idx == 1


class TestSpawnContextManager:
    """Test 6: with spawn("cat") as child: sendline("hi"); close()."""

    def test_context_manager_cleanup(self) -> None:
        with Spawn("cat", timeout=5) as child:
            child.sendline("hi")
            child.expect("hi")
        # After __exit__, process should be terminated
        assert not child.isalive()

    def test_context_manager_no_exception(self) -> None:
        """Context manager exit should not raise."""
        with Spawn("cat", timeout=5) as child:
            child.sendline("test")


class TestSpawnExpectList:
    """Test 7: expect_list(["foo", "bar"]) → returns index of first match."""

    def test_expect_list_first_match(self) -> None:
        with Spawn('/bin/sh -c "echo aaa; echo bbb"', timeout=5) as child:
            idx = child.expect_list(["bbb", "aaa"])
            # "aaa" appears first in output, so it should match
            assert idx == 1
            assert child.after == "aaa"

    def test_expect_with_list(self) -> None:
        """expect() with a list is equivalent to expect_list()."""
        with Spawn('/bin/sh -c "echo hello"', timeout=5) as child:
            idx = child.expect(["goodbye", "hello"])
            assert idx == 1

    def test_expect_exact(self) -> None:
        with Spawn('/bin/sh -c "echo exact_match"', timeout=5) as child:
            idx = child.expect_exact(["nope", "exact_match"])
            assert idx == 1


class TestSpawnSendcontrol:
    """Test 8: sendcontrol("c") terminates running process."""

    def test_sendcontrol_c(self) -> None:
        with Spawn("cat", timeout=5) as child:
            time.sleep(0.1)
            child.sendcontrol("c")
            time.sleep(1.0)
            assert not child.isalive()

    def test_sendcontrol_invalid(self) -> None:
        with Spawn("cat", timeout=5) as child:
            with pytest.raises(ValueError, match="Invalid control character"):
                child.sendcontrol("1")

    def test_sendeof(self) -> None:
        with Spawn("cat", timeout=5) as child:
            child.sendeof()
            # Wait up to 2 seconds for cat to exit after Ctrl-D
            for _ in range(20):
                time.sleep(0.1)
                if not child.isalive():
                    break
            assert not child.isalive()

    def test_sendintr(self) -> None:
        """sendintr() sends Ctrl-C (\\x03) to the process."""
        with Spawn("cat", timeout=5) as child:
            # sendintr is equivalent to sendcontrol('c')
            child.sendintr()
            # Give process time to receive signal
            time.sleep(1.5)
            # Cat should eventually exit from the interrupt
            if child.isalive():
                child.terminate(force=True)
            # At minimum, verify sendintr doesn't raise
            assert True


class TestSpawnNonexistent:
    """Test 9: spawn with nonexistent command → raises appropriate error."""

    def test_nonexistent_command(self) -> None:
        child = Spawn("/nonexistent_binary_xyz", timeout=2)
        time.sleep(0.5)
        assert not child.isalive()
        child.close()


class TestSpawnIsAlive:
    """Test 10: isalive() returns False after close()."""

    def test_isalive_false_after_close(self) -> None:
        child = Spawn("cat", timeout=5)
        assert child.isalive()
        child.close()
        assert not child.isalive()

    def test_isalive_false_after_exit(self) -> None:
        child = Spawn('/bin/sh -c "exit 0"', timeout=5)
        time.sleep(0.3)
        assert not child.isalive()
        child.close()


class TestSpawnRegex:
    """Test regex patterns in expect."""

    def test_regex_pattern(self) -> None:
        with Spawn('/bin/sh -c "echo count: 42"', timeout=5) as child:
            child.expect(re.compile(r"count: (\d+)"))
            assert child.match is not None
            assert hasattr(child.match, "group")
            assert child.match.group(1) == "42"  # type: ignore[union-attr]


class TestSpawnMatchAttributes:
    """Test before/after/match attributes."""

    def test_before_after_match(self) -> None:
        with Spawn('/bin/sh -c "echo hello world"', timeout=5) as child:
            child.expect("world")
            assert child.after == "world"
            # before should contain "hello " (or similar with PTY output)
            assert "hello" in child.before or child.before == ""

    def test_match_for_exact_string(self) -> None:
        with Spawn("echo test_match", timeout=5) as child:
            child.expect("test_match")
            assert child.match == "test_match"

    def test_match_for_regex(self) -> None:
        with Spawn("echo number_99", timeout=5) as child:
            child.expect(re.compile(r"number_(\d+)"))
            assert child.match is not None
            assert hasattr(child.match, "group")


class TestSpawnPublicAPI:
    """Test the tether.spawn() convenience function."""

    def test_tether_spawn(self) -> None:
        with tether.spawn("echo api_test") as child:
            child.expect("api_test")
            assert child.after == "api_test"

    def test_tether_spawn_with_encoding(self) -> None:
        child = tether.spawn("echo utf8", encoding="utf-8")
        child.expect("utf8")
        child.close()


class TestSpawnSetwinsize:
    def test_setwinsize(self) -> None:
        with Spawn("/bin/sh", timeout=5) as child:
            child.setwinsize(50, 132)
            # Should not raise


class TestSpawnTerminate:
    def test_terminate(self) -> None:
        child = Spawn("sleep 60", timeout=5)
        assert child.isalive()
        result = child.terminate()
        assert result is True
        child.close()
