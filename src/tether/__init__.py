"""tether — Modern process interaction library with PTY support."""

from __future__ import annotations

__version__ = "0.1.0"
__all__ = [
    "Spawn",
    "AsyncSpawn",
    "PopenSpawn",
    "SSHSession",
    "EOF",
    "TIMEOUT",
    "run",
    "spawn",
    "TetherError",
    "Timeout",
]


# Stubs — replaced as phases are implemented.

class TetherError(Exception):
    """Base exception for tether. Stub — replaced by _errors.py."""


class Timeout(TetherError):
    """Expect timeout. Stub — replaced by _errors.py."""


class Spawn:
    """Process interaction via PTY. Stub — see Phase 1."""


class AsyncSpawn:
    """Async process interaction via PTY. Stub — see Phase 3."""


class PopenSpawn:
    """Non-PTY process interaction via pipes. Stub — see Phase 3."""


class SSHSession:
    """SSH session helper. Stub — see Phase 3."""


# Sentinel stubs
class _SentinelType:
    _instance: _SentinelType | None = None
    def __new__(cls) -> _SentinelType:
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance


class EOF_TYPE(_SentinelType):
    """EOF sentinel type."""
    def __repr__(self) -> str:
        return "EOF"


class TIMEOUT_TYPE(_SentinelType):
    """TIMEOUT sentinel type."""
    def __repr__(self) -> str:
        return "TIMEOUT"


EOF: EOF_TYPE = EOF_TYPE()
TIMEOUT: TIMEOUT_TYPE = TIMEOUT_TYPE()


def run(command: str, *, timeout: float = 30) -> str:
    """Run a command and return its output. Stub — see Phase 2."""
    raise NotImplementedError("tether.run() not yet implemented")


def spawn(
    command: str | list[str],
    *,
    timeout: float = 30,
    encoding: str = "utf-8",
) -> Spawn:
    """Spawn a process with PTY. Stub — see Phase 1."""
    raise NotImplementedError("tether.spawn() not yet implemented")
