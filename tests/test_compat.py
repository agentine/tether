"""Tests for _compat.py: pexpect compatibility shim and cross-verification."""

from __future__ import annotations

import pytest

pexpect = pytest.importorskip("pexpect")

import tether.compat as tether_compat  # noqa: E402
from tether._spawn import Spawn  # noqa: E402


class TestCompatImports:
    """Verify that pexpect-style imports work."""

    def test_import_spawn(self) -> None:
        assert tether_compat.spawn is Spawn

    def test_import_run(self) -> None:
        assert callable(tether_compat.run)

    def test_import_eof(self) -> None:
        assert tether_compat.EOF is not None

    def test_import_timeout(self) -> None:
        assert tether_compat.TIMEOUT is not None

    def test_import_exception_pexpect(self) -> None:
        assert issubclass(tether_compat.ExceptionPexpect, Exception)

    def test_import_pxssh(self) -> None:
        assert tether_compat.pxssh is not None

    def test_compat_spawn_works(self) -> None:
        """spawn from compat module should work like Spawn."""
        with tether_compat.spawn("echo hello") as child:
            child.expect("hello")
            assert "hello" in child.after

    def test_compat_run_works(self) -> None:
        """run from compat module should work."""
        result = tether_compat.run("echo hello")
        assert "hello" in result


class TestCrossVerification:
    """Cross-verify tether vs pexpect for identical scenarios."""

    def test_echo_expect(self) -> None:
        """Both should match 'hello' from echo."""
        # pexpect
        p_child = pexpect.spawn("echo hello")
        p_child.expect("hello")
        p_after = p_child.after.decode() if isinstance(p_child.after, bytes) else p_child.after
        p_child.close()

        # tether
        with Spawn("echo hello") as t_child:
            t_child.expect("hello")
            t_after = t_child.after

        assert "hello" in p_after
        assert "hello" in t_after

    def test_sendline_expect(self) -> None:
        """Both should handle sendline/expect."""
        # pexpect
        p_child = pexpect.spawn("python3 -c \"x=input(); print('got:',x)\"")
        p_child.sendline("hello")
        p_child.expect("got: hello")
        p_child.close()

        # tether
        with Spawn("python3 -c \"x=input(); print('got:',x)\"") as t_child:
            t_child.sendline("hello")
            t_child.expect("got: hello")

    def test_run_basic(self) -> None:
        """Both run() should return output containing the echoed text."""
        p_result = pexpect.run("echo crosscheck").decode()
        t_result = tether_compat.run("echo crosscheck")
        assert "crosscheck" in p_result
        assert "crosscheck" in t_result

    def test_run_exit_status(self) -> None:
        """Both should return exit status when requested."""
        p_output, p_status = pexpect.run("sh -c 'exit 3'", withexitstatus=True)
        t_output, t_status = tether_compat.run("sh -c 'exit 3'", withexitstatus=True)  # type: ignore[misc]
        assert p_status == 3
        assert t_status == 3

    def test_expect_multiple_patterns(self) -> None:
        """Both should match the first occurring pattern."""
        # pexpect
        p_child = pexpect.spawn("echo 'aXXXbYYY'")
        p_idx = p_child.expect(["b", "a"])
        p_child.close()

        # tether
        with Spawn("echo 'aXXXbYYY'") as t_child:
            t_idx = t_child.expect_list(["b", "a"])

        # Both should match 'a' first (index 1)
        assert p_idx == 1
        assert t_idx == 1

    def test_before_attribute(self) -> None:
        """Both should set before to text preceding the match."""
        # pexpect
        p_child = pexpect.spawn("echo 'before_text:match_text'")
        p_child.expect("match_text")
        p_before = p_child.before.decode() if isinstance(p_child.before, bytes) else p_child.before
        p_child.close()

        # tether
        with Spawn("echo 'before_text:match_text'") as t_child:
            t_child.expect("match_text")
            t_before = t_child.before

        assert "before_text:" in p_before
        assert "before_text:" in t_before

    def test_sendcontrol(self) -> None:
        """Both should support sendcontrol."""
        import time

        # pexpect
        p_child = pexpect.spawn("cat")
        time.sleep(0.2)
        p_child.sendcontrol("c")
        time.sleep(1)
        assert not p_child.isalive()
        p_child.close()

        # tether
        with Spawn("cat") as t_child:
            time.sleep(0.2)
            t_child.sendcontrol("c")
            deadline = time.monotonic() + 5
            while t_child.isalive() and time.monotonic() < deadline:
                time.sleep(0.1)
            assert not t_child.isalive()

    def test_expect_eof(self) -> None:
        """Both should support EOF in pattern lists."""
        # pexpect
        p_child = pexpect.spawn("echo done")
        p_child.expect("done")
        p_idx = p_child.expect([pexpect.EOF])
        p_child.close()

        # tether
        from tether._types import EOF_TYPE

        with Spawn("echo done") as t_child:
            t_child.expect("done")
            t_idx = t_child.expect([EOF_TYPE])

        assert p_idx == 0
        assert t_idx == 0

    def test_context_manager(self) -> None:
        """Both should support context managers."""
        # pexpect doesn't have native context manager, but spawn works with try/finally
        p_child = pexpect.spawn("echo ctx")
        p_child.expect("ctx")
        p_child.close()

        # tether
        with Spawn("echo ctx") as t_child:
            t_child.expect("ctx")

    def test_run_with_events(self) -> None:
        """tether.run with events should work like pexpect.run."""
        t_result = tether_compat.run(
            "sh -c 'echo Question?; read ans; echo Answer: $ans'",
            events={"Question?": "yes\n"},
        )
        assert "Answer: yes" in t_result
