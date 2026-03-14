# Changelog

> **Note:** This package was previously published as **tether**. It was renamed to **ptylink** after v0.1.0.
> If you were using `tether`, update your dependency to `ptylink` and replace any `TetherError` references with `PtylinkError`.

## v0.1.0 (2026-03-13)

Initial release as `tether` — modern drop-in replacement for pexpect. Renamed to `ptylink` post-release.

### Features

- `Spawn` class with PTY-based process interaction
- `AsyncSpawn`: native `async/await` (not `async_=True` hack)
- `PopenSpawn`: pipe-based spawn for environments without PTY
- `SSHSession`: SSH login/command helper built on Spawn
- `run()` high-level function with events support
- Pattern matching: regex, exact string, EOF, TIMEOUT sentinels
- `strip_ansi()` and `has_ansi()` ANSI escape handling
- `interact()` standalone function with input/output filters
- pexpect compatibility shim (`ptylink.compat`)
- Zero dependencies
- Full type annotations — `mypy --strict` + `pyright strict` clean
- Python 3.10+

### Bug fixes vs pexpect

- `before` attribute no longer contains leaked `sendline()` echo (#821)
- No Python 3.12+ `ResourceWarning` on fork (#817)
- No deprecated `asyncio.coroutine` usage (#677)

### Performance

- 3.6–95× faster than pexpect across all benchmarked operations
