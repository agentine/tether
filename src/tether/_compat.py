"""pexpect compatibility shim.

Use ``import tether._compat as pexpect`` or
``import tether.compat as pexpect`` for a drop-in replacement.

Example::

    import tether.compat as pexpect
    child = pexpect.spawn("echo hello")
    child.expect("hello")
"""

from __future__ import annotations

# Core classes — pexpect.spawn ↔ tether.Spawn
from tether._spawn import Spawn as spawn  # noqa: N811 (pexpect names are lowercase)
from tether._spawn import Spawn

# High-level run — pexpect.run ↔ tether.run
from tether._run import run

# EOF / TIMEOUT — pexpect exports these as exception classes that also serve
# as sentinels in expect() pattern lists.  Mapping to tether's exception
# classes lets ``except pexpect.EOF:`` work correctly.
from tether._errors import EOF as EOF  # noqa: PLC0414
from tether._errors import Timeout as TIMEOUT  # noqa: PLC0414

# Explicit exception aliases (pexpect compat names).
from tether._errors import EOF as ExceptionEOF  # noqa: PLC0414
from tether._errors import TetherError as ExceptionPexpect  # noqa: PLC0414
from tether._errors import Timeout as ExceptionTimeout  # noqa: PLC0414

# SSH — pexpect.pxssh ↔ tether.SSHSession
from tether._ssh import SSHSession as pxssh

__all__ = [
    "spawn",
    "Spawn",
    "run",
    "EOF",
    "TIMEOUT",
    "ExceptionPexpect",
    "ExceptionEOF",
    "ExceptionTimeout",
    "pxssh",
]
