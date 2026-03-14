"""Interactive passthrough mode for a Spawn child."""

from __future__ import annotations

import os
import select
import sys
import termios
import tty
from collections.abc import Callable
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from tether._spawn import Spawn


def interact(
    spawn: Spawn,
    escape_character: str = chr(29),
    input_filter: Callable[[bytes], bytes] | None = None,
    output_filter: Callable[[bytes], bytes] | None = None,
) -> None:
    """Pass control of the PTY to the user interactively.

    Reads from stdin and writes to the process; reads from the process
    and writes to stdout.  Exits when *escape_character* is received or
    the process closes.

    Args:
        spawn: The Spawn instance to interact with.
        escape_character: Character that exits interact mode (default Ctrl-]).
        input_filter: Optional function applied to bytes read from stdin
            before forwarding to the process.
        output_filter: Optional function applied to bytes read from the
            process before writing to stdout.
    """
    escape_byte = escape_character.encode(spawn.encoding)
    stdin_fd = sys.stdin.fileno()
    pty_fd = spawn.proc.fd
    stdout_fd = sys.stdout.fileno()

    old_settings = termios.tcgetattr(stdin_fd)
    try:
        tty.setraw(stdin_fd)
        while spawn.isalive():
            r, _, _ = select.select([stdin_fd, pty_fd], [], [], 0.1)
            if stdin_fd in r:
                data = os.read(stdin_fd, 1024)
                if escape_byte in data:
                    break
                if input_filter is not None:
                    data = input_filter(data)
                spawn.proc.write(data)
            if pty_fd in r:
                try:
                    data = spawn.proc.read(1024)
                    if data:
                        if output_filter is not None:
                            data = output_filter(data)
                        os.write(stdout_fd, data)
                except EOFError:
                    break
    finally:
        termios.tcsetattr(stdin_fd, termios.TCSADRAIN, old_settings)
