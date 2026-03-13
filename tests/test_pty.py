"""Tests for tether._pty — PtyProcess class."""

import os
import select
import time

import pytest
from tether._pty import PtyProcess


class TestPtyProcessSpawn:
    def test_spawn_echo(self) -> None:
        proc = PtyProcess.spawn(["/bin/echo", "hello world"])
        time.sleep(0.2)
        output = b""
        while select.select([proc.fd], [], [], 0.5)[0]:
            try:
                output += proc.read(4096)
            except EOFError:
                break
        assert b"hello world" in output
        proc.waitpid()
        proc.close()

    def test_spawn_sh(self) -> None:
        proc = PtyProcess.spawn(["/bin/sh"])
        time.sleep(0.2)
        # Drain prompt
        while select.select([proc.fd], [], [], 0.2)[0]:
            try:
                proc.read(4096)
            except EOFError:
                break
        proc.write(b"echo testing_pty\n")
        time.sleep(0.3)
        output = b""
        while select.select([proc.fd], [], [], 0.3)[0]:
            try:
                output += proc.read(4096)
            except EOFError:
                break
        assert b"testing_pty" in output
        proc.terminate()
        proc.close()

    def test_spawn_empty_argv_raises(self) -> None:
        with pytest.raises(ValueError, match="argv must not be empty"):
            PtyProcess.spawn([])

    def test_spawn_with_env(self) -> None:
        env = dict(os.environ)
        env["TETHER_TEST_VAR"] = "hello123"
        proc = PtyProcess.spawn(
            ["/bin/sh", "-c", "echo $TETHER_TEST_VAR"],
            env=env,
        )
        time.sleep(0.3)
        output = b""
        while select.select([proc.fd], [], [], 0.5)[0]:
            try:
                output += proc.read(4096)
            except EOFError:
                break
        assert b"hello123" in output
        proc.waitpid()
        proc.close()


class TestPtyProcessReadWrite:
    def test_write_and_read(self) -> None:
        proc = PtyProcess.spawn(["/bin/cat"])
        time.sleep(0.1)
        proc.write(b"ping\n")
        time.sleep(0.2)
        output = b""
        while select.select([proc.fd], [], [], 0.3)[0]:
            try:
                output += proc.read(4096)
            except EOFError:
                break
        assert b"ping" in output
        proc.terminate()
        proc.close()

    def test_read_nonblocking_no_data(self) -> None:
        proc = PtyProcess.spawn(["/bin/sleep", "5"])
        # Drain any initial output
        time.sleep(0.1)
        while select.select([proc.fd], [], [], 0.1)[0]:
            try:
                proc.read(4096)
            except EOFError:
                break
        # Now read should return empty (non-blocking)
        data = proc.read(4096)
        assert data == b""
        proc.terminate(force=True)
        proc.close()


class TestPtyProcessLifecycle:
    def test_isalive_running(self) -> None:
        proc = PtyProcess.spawn(["/bin/sleep", "10"])
        assert proc.isalive()
        proc.terminate(force=True)
        proc.close()

    def test_isalive_after_exit(self) -> None:
        proc = PtyProcess.spawn(["/bin/sh", "-c", "exit 0"])
        time.sleep(0.3)
        assert not proc.isalive()
        proc.close()

    def test_terminate(self) -> None:
        proc = PtyProcess.spawn(["/bin/sleep", "60"])
        assert proc.isalive()
        result = proc.terminate()
        assert result is True
        assert not proc.isalive()
        proc.close()

    def test_terminate_force(self) -> None:
        # trap SIGHUP so the first signal doesn't kill it
        proc = PtyProcess.spawn(["/bin/sh", "-c", "trap '' HUP; sleep 60"])
        time.sleep(0.2)
        assert proc.isalive()
        result = proc.terminate(force=True)
        assert result is True
        assert not proc.isalive()
        proc.close()

    def test_waitpid(self) -> None:
        proc = PtyProcess.spawn(["/bin/sh", "-c", "exit 42"])
        pid, status = proc.waitpid()
        assert pid == proc.pid
        proc.close()

    def test_fileno(self) -> None:
        proc = PtyProcess.spawn(["/bin/echo", "test"])
        assert proc.fileno() == proc.fd
        assert isinstance(proc.fileno(), int)
        proc.waitpid()
        proc.close()

    def test_setwinsize(self) -> None:
        proc = PtyProcess.spawn(["/bin/sh"])
        # Should not raise
        proc.setwinsize(40, 120)
        proc.terminate()
        proc.close()

    def test_close_idempotent(self) -> None:
        proc = PtyProcess.spawn(["/bin/echo", "x"])
        proc.waitpid()
        proc.close()
        proc.close()  # Should not raise
