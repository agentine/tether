"""High-level run() function for simple command execution."""

from __future__ import annotations

from tether._errors import EOF, Timeout
from tether._spawn import Spawn
from tether._types import EOF_TYPE


def run(
    command: str,
    *,
    timeout: float = 30,
    withexitstatus: bool = False,
    events: dict[str, str] | None = None,
    encoding: str = "utf-8",
    env: dict[str, str] | None = None,
    cwd: str | None = None,
) -> str | tuple[str, int]:
    """Run a command and return its output.

    If *events* is provided, it maps patterns to responses::

        run("sudo apt install foo", events={"password:": "mypassword\\n"})

    If *withexitstatus* is True, returns ``(output, exitstatus)`` tuple.
    Otherwise returns the output string.
    """
    child = Spawn(command, timeout=timeout, encoding=encoding, env=env, cwd=cwd)
    output_parts: list[str] = []

    try:
        if events:
            # Build pattern list: event keys + EOF sentinel.
            event_keys = list(events.keys())

            while True:
                try:
                    idx = child.expect([*event_keys, EOF_TYPE], timeout=timeout)
                except EOF:
                    output_parts.append(child.before)
                    break
                except Timeout:
                    output_parts.append(child.before)
                    break

                output_parts.append(child.before)

                if idx == len(events):
                    # EOF sentinel matched.
                    break

                # Send the corresponding response.
                pattern_key = list(events.keys())[idx]
                output_parts.append(child.after)
                child.send(events[pattern_key])
        else:
            # No events — just read until EOF.
            try:
                child.expect(EOF_TYPE, timeout=timeout)
                output_parts.append(child.before)
            except EOF:
                output_parts.append(child.before)
            except Timeout:
                output_parts.append(child.before)

        output = "".join(output_parts)

        # Get exit status.
        exitstatus = 0
        try:
            if child.isalive():
                child.close(force=False)
            child.proc.waitpid()
            exitstatus = child.proc.exitstatus or 0
        except Exception:
            pass

    except Exception:
        output = "".join(output_parts)
        exitstatus = -1
        child.close()

    if withexitstatus:
        return output, exitstatus
    return output
