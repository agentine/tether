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

# Sentinels — pexpect.EOF / pexpect.TIMEOUT
from tether._types import EOF_TYPE as EOF
from tether._types import TIMEOUT_TYPE as TIMEOUT

# Exceptions — pexpect exception names
from tether._errors import EOF as ExceptionEOF
from tether._errors import TetherError as ExceptionPexpect
from tether._errors import Timeout as ExceptionTimeout

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
