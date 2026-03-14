"""Tests for _ssh.py: SSHSession — no network needed."""

from __future__ import annotations

import pytest

from tether._ssh import SSHSession


class TestSSHSessionAPI:
    def test_instantiation(self) -> None:
        """SSHSession should instantiate with basic params."""
        ssh = SSHSession("example.com", username="admin", port=22)
        assert ssh.server == "example.com"
        assert ssh.username == "admin"
        assert ssh.port == 22

    def test_default_port(self) -> None:
        """Default port should be 22."""
        ssh = SSHSession("example.com")
        assert ssh.port == 22

    def test_password_stored(self) -> None:
        """Password should be stored for login()."""
        ssh = SSHSession("example.com", password="secret")
        assert ssh.password == "secret"

    def test_ssh_command_construction(self) -> None:
        """SSH command should include user, port."""
        ssh = SSHSession("example.com", username="admin", port=2222)
        assert "-p" in ssh._ssh_command
        assert "2222" in ssh._ssh_command
        assert "admin@example.com" in ssh._ssh_command

    def test_ssh_options(self) -> None:
        """SSH options should be passed as -o flags."""
        ssh = SSHSession(
            "example.com",
            ssh_options={"StrictHostKeyChecking": "no"},
        )
        assert "-o" in ssh._ssh_command
        assert "StrictHostKeyChecking=no" in ssh._ssh_command

    def test_prompt_regex(self) -> None:
        """Default prompt regex should match common prompts."""
        ssh = SSHSession("example.com")
        assert ssh._prompt_re.search("user@host:~$ ") is not None
        assert ssh._prompt_re.search("root@host:~# ") is not None
        assert ssh._prompt_re.search("prompt> ") is not None

    def test_run_without_login_raises(self) -> None:
        """run() should raise if not connected."""
        ssh = SSHSession("example.com")
        with pytest.raises(RuntimeError, match="Not connected"):
            ssh.run("whoami")

    def test_prompt_without_login_raises(self) -> None:
        """prompt() should raise if not connected."""
        ssh = SSHSession("example.com")
        with pytest.raises(RuntimeError, match="Not connected"):
            ssh.prompt()

    def test_context_manager(self) -> None:
        """Context manager should work without crashing (no-op logout)."""
        with SSHSession("example.com") as ssh:
            assert ssh.server == "example.com"

    def test_logout_when_not_connected(self) -> None:
        """logout() should be safe when not connected."""
        ssh = SSHSession("example.com")
        ssh.logout()  # Should not raise
