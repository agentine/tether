"""SSHSession — SSH session management built on Spawn."""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

from tether._errors import EOF as EOFExc
from tether._errors import Timeout as TimeoutExc
from tether._spawn import Spawn

if TYPE_CHECKING:
    from types import TracebackType


class SSHSession:
    """SSH session helper built on :class:`Spawn`.

    Manages SSH connection, login, and command execution.

    Example::

        with SSHSession("server.example.com", username="admin") as ssh:
            ssh.login(password="secret")
            output = ssh.run("uname -a")
    """

    def __init__(
        self,
        server: str,
        *,
        username: str | None = None,
        port: int = 22,
        password: str | None = None,
        timeout: float = 30,
        ssh_options: dict[str, str] | None = None,
    ) -> None:
        self.server = server
        self.username = username
        self.port = port
        self.password = password
        self.timeout = timeout
        self._prompt_re: re.Pattern[str] = re.compile(r"[\$#>]\s*$")
        self._spawn: Spawn | None = None

        # Build SSH command.
        cmd_parts = ["ssh"]
        if ssh_options:
            for key, val in ssh_options.items():
                cmd_parts.extend(["-o", f"{key}={val}"])
        cmd_parts.extend(["-p", str(port)])
        if username:
            cmd_parts.append(f"{username}@{server}")
        else:
            cmd_parts.append(server)
        self._ssh_command = cmd_parts

    def __enter__(self) -> SSHSession:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None:
        self.logout()

    def login(
        self,
        *,
        original_prompt: str = r"[\$#>]\s*$",
        login_timeout: float = 10,
        password: str | None = None,
        auto_prompt_reset: bool = True,
    ) -> None:
        """Connect via SSH and log in.

        Handles password prompts and waits for the shell prompt.
        """
        self._spawn = Spawn(
            self._ssh_command,
            timeout=self.timeout,
        )
        pw = password or self.password

        # Wait for password prompt or shell prompt.
        prompt_pat = re.compile(original_prompt)
        idx = self._spawn.expect(
            [re.compile(r"[Pp]assword:\s*"), prompt_pat],
            timeout=login_timeout,
        )

        if idx == 0:
            # Password prompt.
            if pw is None:
                raise ValueError("Password required but not provided")
            self._spawn.sendline(pw)
            self._spawn.expect(prompt_pat, timeout=login_timeout)

        if auto_prompt_reset:
            self._prompt_re = re.compile(original_prompt)

    def prompt(self, timeout: float = -1) -> bool:
        """Wait for the shell prompt. Returns True if found."""
        if self._spawn is None:
            raise RuntimeError("Not connected. Call login() first.")
        t = timeout if timeout >= 0 else self.timeout
        try:
            self._spawn.expect(self._prompt_re, timeout=t)
            return True
        except (TimeoutExc, EOFExc):
            return False

    def run(self, command: str, *, timeout: float = -1) -> str:
        """Execute a command and return its output.

        Sends the command, waits for the prompt, and returns
        everything between the command echo and the prompt.
        """
        if self._spawn is None:
            raise RuntimeError("Not connected. Call login() first.")
        self._spawn.sendline(command)
        t = timeout if timeout >= 0 else self.timeout
        self._spawn.expect(self._prompt_re, timeout=t)
        return self._spawn.before

    def logout(self) -> None:
        """Close the SSH session."""
        if self._spawn is not None:
            try:
                self._spawn.sendline("exit")
            except OSError:
                pass
            self._spawn.close()
            self._spawn = None
