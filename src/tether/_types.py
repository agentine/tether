"""Sentinel types and type aliases for tether."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import TYPE_CHECKING, Union

if TYPE_CHECKING:
    from tether._errors import EOF as EOFExc
    from tether._errors import Timeout as TimeoutExc


class EOF_TYPE:
    """Singleton sentinel for EOF in pattern lists.

    Distinct from the EOF *exception* in _errors.py. Use ``tether.EOF`` (the
    singleton instance) in expect pattern lists to match end-of-file without
    raising an exception.
    """

    _instance: EOF_TYPE | None = None

    def __new__(cls) -> EOF_TYPE:
        if cls._instance is None:
            cls._instance = object.__new__(cls)
        return cls._instance

    def __repr__(self) -> str:
        return "EOF"

    def __bool__(self) -> bool:
        return True


class TIMEOUT_TYPE:
    """Singleton sentinel for TIMEOUT in pattern lists.

    Distinct from the Timeout *exception* in _errors.py. Use
    ``tether.TIMEOUT`` in expect pattern lists to match timeout without
    raising an exception.
    """

    _instance: TIMEOUT_TYPE | None = None

    def __new__(cls) -> TIMEOUT_TYPE:
        if cls._instance is None:
            cls._instance = object.__new__(cls)
        return cls._instance

    def __repr__(self) -> str:
        return "TIMEOUT"

    def __bool__(self) -> bool:
        return True


# Singleton instances.
EOF: EOF_TYPE = EOF_TYPE()
TIMEOUT: TIMEOUT_TYPE = TIMEOUT_TYPE()

# Pattern type accepted by expect methods.
# Includes both sentinel types and exception classes for compat support.
Pattern = Union[
    str, re.Pattern[str], type[EOF_TYPE], type[TIMEOUT_TYPE], "type[EOFExc]", "type[TimeoutExc]"
]


@dataclass(frozen=True, slots=True)
class CompiledPattern:
    """A compiled expect pattern ready for matching."""

    raw: Pattern
    regex: re.Pattern[str] | None  # None for EOF/TIMEOUT sentinels
    is_eof: bool
    is_timeout: bool
