"""Advanced tests for Spawn: expect_list ordering, sendcontrol, setwinsize."""

from __future__ import annotations

import re
import time

from tether._spawn import Spawn
from tether._types import EOF_TYPE


class TestExpectListOrdering:
    def test_first_match_wins(self) -> None:
        """expect_list returns the index of the earliest match in the buffer."""
        with Spawn("echo 'aXXXbYYY'") as child:
            idx = child.expect_list(["b", "a"])
            # 'a' appears first in the output, so index 1 should match
            # (since 'a' is pattern index 1 in the list)
            assert idx == 1  # 'a' matched first by position

    def test_expect_list_eof_sentinel(self) -> None:
        """EOF sentinel in pattern list should match when process exits."""
        with Spawn("echo done") as child:
            child.expect("done")
            idx = child.expect([EOF_TYPE])
            assert idx == 0


class TestSendcontrol:
    def test_sendcontrol_c(self) -> None:
        """Ctrl-C should terminate a running process."""
        with Spawn("cat") as child:
            # cat blocks on stdin — give it a moment to start, then Ctrl-C.
            time.sleep(0.2)
            child.sendcontrol("c")
            # Drain any output so the PTY processes the signal.
            try:
                child.expect(re.compile(r"."), timeout=2)
            except Exception:
                pass
            deadline = time.monotonic() + 5
            while child.isalive() and time.monotonic() < deadline:
                time.sleep(0.1)
            assert not child.isalive()


class TestSetwinsize:
    def test_setwinsize_changes_dimensions(self) -> None:
        """setwinsize should change the PTY dimensions visible to the child."""
        with Spawn("sh") as child:
            child.expect(re.compile(r"[\$#] "))
            child.setwinsize(50, 120)
            child.sendline("stty size")
            child.expect(re.compile(r"\d+ \d+"))
            # The output should contain "50 120"
            assert "50 120" in child.before + child.after


class TestInteractModule:
    def test_interact_import(self) -> None:
        """interact function should be importable."""
        from tether._interact import interact

        assert callable(interact)
