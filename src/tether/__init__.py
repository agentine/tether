"""tether — Modern process interaction library with PTY support."""

from __future__ import annotations

__version__ = "0.1.0"
__all__ = [
    "Spawn",
    "AsyncSpawn",
    "PopenSpawn",
    "SSHSession",
    "EOF",
    "EOFError",
    "TIMEOUT",
    "EOF_TYPE",
    "TIMEOUT_TYPE",
    "run",
    "spawn",
    "TetherError",
    "Timeout",
    "ExitStatus",
    "Pattern",
    "strip_ansi",
    "has_ansi",
]

# Foundational types
from tether._errors import EOF as EOFError
from tether._errors import ExitStatus, TetherError, Timeout
from tether._types import EOF, TIMEOUT, EOF_TYPE, TIMEOUT_TYPE, Pattern

# Phase 1 — Spawn
from tether._spawn import Spawn


# Phase 2 — run, screen, interact
from tether._run import run
from tether._screen import has_ansi, strip_ansi


# Phase 3 — async, popen, ssh
from tether._async import AsyncSpawn
from tether._popen import PopenSpawn
from tether._ssh import SSHSession


def spawn(
    command: str | list[str],
    *,
    timeout: float = 30,
    encoding: str = "utf-8",
) -> Spawn:
    """Spawn a process with PTY."""
    return Spawn(command, timeout=timeout, encoding=encoding)
