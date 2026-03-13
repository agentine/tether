"""PTY process management — replaces ptyprocess dependency."""

from __future__ import annotations

import errno
import fcntl
import os
import pty
import signal
import struct
import sys
import termios
import time


class PtyProcess:
    """Manage a child process running in a pseudo-terminal.

    This replaces ptyprocess with built-in PTY handling using
    ``pty.openpty()`` + ``os.fork()`` on Unix.
    """

    __slots__ = ("pid", "fd", "_exitstatus", "_signalstatus", "_closed")

    def __init__(self, pid: int, fd: int) -> None:
        self.pid = pid
        self.fd = fd
        self._exitstatus: int | None = None
        self._signalstatus: int | None = None
        self._closed = False

    @classmethod
    def spawn(
        cls,
        argv: list[str],
        *,
        env: dict[str, str] | None = None,
        cwd: str | None = None,
        dimensions: tuple[int, int] = (24, 80),
    ) -> PtyProcess:
        """Fork a child process in a new PTY.

        Args:
            argv: Command and arguments (e.g. ``["/bin/sh", "-c", "echo hi"]``).
            env: Environment variables for the child. ``None`` inherits parent.
            cwd: Working directory for the child.
            dimensions: Terminal size as ``(rows, cols)``.

        Returns:
            A ``PtyProcess`` wrapping the master PTY fd and child pid.
        """
        if not argv:
            raise ValueError("argv must not be empty")

        # Allocate a PTY pair.
        master_fd, slave_fd = pty.openpty()

        # Set initial window size on the slave.
        _setwinsize(slave_fd, dimensions[0], dimensions[1])

        pid = os.fork()

        if pid == 0:
            # ---- Child process ----
            try:
                os.close(master_fd)

                # Create a new session and set the slave as controlling terminal.
                if sys.version_info >= (3, 13):
                    os.login_tty(slave_fd)
                else:
                    os.setsid()
                    # Set controlling terminal via ioctl.
                    fcntl.ioctl(slave_fd, termios.TIOCSCTTY, 0)
                    # Redirect std fds to the slave PTY.
                    os.dup2(slave_fd, 0)
                    os.dup2(slave_fd, 1)
                    os.dup2(slave_fd, 2)
                    if slave_fd > 2:
                        os.close(slave_fd)

                if cwd is not None:
                    os.chdir(cwd)

                if env is not None:
                    os.execvpe(argv[0], argv, env)
                else:
                    os.execvp(argv[0], argv)
            except Exception:
                os._exit(127)
        else:
            # ---- Parent process ----
            os.close(slave_fd)

            # Set master fd to non-blocking.
            flags = fcntl.fcntl(master_fd, fcntl.F_GETFL)
            fcntl.fcntl(master_fd, fcntl.F_SETFL, flags | os.O_NONBLOCK)

            return cls(pid, master_fd)

        # Should never reach here but satisfies type checker.
        raise RuntimeError("unreachable")  # pragma: no cover

    def read(self, size: int = 1024) -> bytes:
        """Read up to *size* bytes from the PTY master fd.

        Returns an empty ``bytes`` on EAGAIN (non-blocking, no data ready).
        Raises ``EOFError`` when the slave side is closed.
        """
        try:
            data = os.read(self.fd, size)
        except OSError as e:
            if e.errno == errno.EAGAIN:
                return b""
            if e.errno == errno.EIO:
                # EIO means the slave side is closed.
                raise EOFError("PTY slave closed") from e
            raise
        if not data:
            raise EOFError("PTY slave closed")
        return data

    def write(self, data: bytes) -> int:
        """Write *data* to the PTY master fd. Handles EINTR."""
        while True:
            try:
                return os.write(self.fd, data)
            except OSError as e:
                if e.errno == errno.EINTR:
                    continue
                raise

    def setwinsize(self, rows: int, cols: int) -> None:
        """Set the terminal window size."""
        _setwinsize(self.fd, rows, cols)

    def waitpid(self) -> tuple[int, int]:
        """Wait for the child to exit. Returns ``(pid, status)``."""
        if self._exitstatus is not None:
            return (self.pid, self._exitstatus)
        while True:
            try:
                wpid, status = os.waitpid(self.pid, 0)
            except ChildProcessError:
                # Already reaped.
                return (self.pid, self._exitstatus or 0)
            if wpid == self.pid:
                self._decode_status(status)
                return (wpid, status)

    def terminate(self, force: bool = False) -> bool:
        """Terminate the child process.

        Sends SIGHUP first. If *force* is True and the process is still alive
        after a short wait, sends SIGKILL.

        Returns True if the process was successfully terminated.
        """
        if not self.isalive():
            return True

        try:
            os.kill(self.pid, signal.SIGHUP)
        except OSError:
            return not self.isalive()

        # Give it a moment to exit.
        for _ in range(10):
            time.sleep(0.05)
            if not self.isalive():
                return True

        if force:
            try:
                os.kill(self.pid, signal.SIGKILL)
            except OSError:
                pass
            time.sleep(0.05)
            return not self.isalive()

        return not self.isalive()

    def isalive(self) -> bool:
        """Return True if the child process is still running."""
        if self._exitstatus is not None:
            return False
        try:
            wpid, status = os.waitpid(self.pid, os.WNOHANG)
        except ChildProcessError:
            self._exitstatus = 0
            return False
        if wpid == 0:
            return True
        self._decode_status(status)
        return False

    @property
    def exitstatus(self) -> int | None:
        """Exit status of the child, or None if still running."""
        return self._exitstatus

    @property
    def signalstatus(self) -> int | None:
        """Signal that killed the child, or None."""
        return self._signalstatus

    def fileno(self) -> int:
        """Return the master PTY file descriptor."""
        return self.fd

    def close(self) -> None:
        """Close the master PTY fd."""
        if not self._closed:
            self._closed = True
            try:
                os.close(self.fd)
            except OSError:
                pass

    def _decode_status(self, status: int) -> None:
        """Decode a raw waitpid status into exit code / signal."""
        if os.WIFEXITED(status):
            self._exitstatus = os.WEXITSTATUS(status)
        elif os.WIFSIGNALED(status):
            self._signalstatus = os.WTERMSIG(status)
            self._exitstatus = -self._signalstatus

    def __del__(self) -> None:
        self.close()


def _setwinsize(fd: int, rows: int, cols: int) -> None:
    """Set terminal window size on the given fd."""
    s = struct.pack("HHHH", rows, cols, 0, 0)
    fcntl.ioctl(fd, termios.TIOCSWINSZ, s)
