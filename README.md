# ptylink

[![CI](https://github.com/agentine/ptylink/actions/workflows/ci.yml/badge.svg)](https://github.com/agentine/ptylink/actions/workflows/ci.yml)
[![PyPI](https://img.shields.io/pypi/v/ptylink)](https://pypi.org/project/ptylink/)
[![Python](https://img.shields.io/pypi/pyversions/ptylink)](https://pypi.org/project/ptylink/)

Modern process interaction library for Python — expect-style automation with PTY support.

Drop-in replacement for [pexpect](https://github.com/pexpect/pexpect) with full type annotations, native async/await, and zero dependencies.

## Why ptylink?

| | pexpect | ptylink |
|---|---|---|
| **Type annotations** | No | Full (`mypy --strict` + `pyright strict`) |
| **Async support** | Deprecated `@asyncio.coroutine` | Native `async/await` via `AsyncSpawn` |
| **Python 3.12+ fork warning** | Yes (#817) | Fixed |
| **`before` leaks sendline echo** | Yes (#821) | Fixed |
| **Dependencies** | `ptyprocess` | Zero |
| **Performance** | Baseline | 3.6–95× faster |

## Installation

```bash
pip install ptylink
```

Requires Python 3.10+.

## Quick Start

```python
import ptylink

with ptylink.spawn("python3") as child:
    child.expect(">>> ")
    child.sendline("print(42)")
    child.expect("42")
    print(child.before)  # text before the match
```

## Context Manager

```python
from ptylink import Spawn

with Spawn("ssh user@host") as child:
    child.expect("password:")
    child.sendline("secret")
    child.expect(r"\$ ")
    child.sendline("ls")
    child.expect(r"\$ ")
    print(child.before)
```

## Async Usage

```python
import asyncio
from ptylink import AsyncSpawn

async def main():
    async with AsyncSpawn("python3") as child:
        await child.expect(">>> ")
        await child.sendline("1 + 1")
        await child.expect("2")

asyncio.run(main())
```

## Pipe-Based (No PTY)

For environments without PTY support (e.g. Windows):

```python
from ptylink import PopenSpawn

with PopenSpawn("echo hello") as child:
    child.expect("hello")
```

## High-Level `run()`

```python
from ptylink import run

# Simple command
output = run("ls -la")

# With exit status
output, status = run("make test", withexitstatus=True)

# Interactive with events
output = run(
    "sudo apt install foo",
    events={"password:": "secret\n"},
)
```

## SSH Sessions

```python
from ptylink import SSHSession

with SSHSession("server.example.com", username="admin") as ssh:
    ssh.login(password="secret")
    output = ssh.run("uname -a")
    print(output)
```

## Pattern Matching

```python
import re
from ptylink import Spawn, EOF_TYPE, TIMEOUT_TYPE

with Spawn("some_program") as child:
    # String patterns (auto-escaped)
    child.expect("login:")

    # Regex patterns
    child.expect(re.compile(r"[\$#] "))

    # Multiple patterns — returns index of match
    idx = child.expect_list(["error", "success", EOF_TYPE])
    if idx == 0:
        print("Error:", child.after)
    elif idx == 1:
        print("Success!")
    elif idx == 2:
        print("Process ended")
```

## API Reference

### Classes and Functions

- **`Spawn(command, *, timeout=30, encoding='utf-8', env=None, cwd=None)`** — PTY-based process interaction
- **`spawn(command, *, timeout=30, encoding='utf-8')`** — Factory function; returns a `Spawn` instance
- **`AsyncSpawn(command, ...)`** — Async version of Spawn
- **`PopenSpawn(command, ...)`** — Pipe-based (no PTY) process interaction
- **`SSHSession(server, *, username=None, port=22, password=None)`** — SSH session helper

### Spawn Methods

| Method | Description |
|--------|-------------|
| `expect(pattern, *, timeout=-1)` | Wait for pattern in output |
| `expect_exact(pattern, *, timeout=-1)` | Wait for exact string |
| `expect_list(patterns, *, timeout=-1)` | Wait for any pattern, return index |
| `send(s)` | Send string to process |
| `sendline(s='')` | Send string + newline |
| `sendcontrol(char)` | Send control character (e.g. `'c'` for Ctrl-C) |
| `sendeof()` | Send EOF (Ctrl-D) |
| `read(size=-1)` | Read from process output |
| `readline()` | Read a single line |
| `isalive()` | Check if process is running |
| `wait()` | Wait for exit, return exit code |
| `close(force=True)` | Close process and PTY |
| `setwinsize(rows, cols)` | Set terminal dimensions |
| `interact()` | Interactive passthrough mode |

### Attributes

- `before` — Text before the last match
- `after` — Text of the last match
- `match` — Match object or string from last expect

### Exceptions

- `PtylinkError` — Base exception
- `Timeout` — Expect timed out
- `EOF` — Process closed output
- `ExitStatus` — Process exited with non-zero status

### Sentinels

- `EOF_TYPE` — Use in pattern lists to match EOF without raising
- `TIMEOUT_TYPE` — Use in pattern lists to match timeout without raising

## ANSI Utilities

```python
from ptylink import strip_ansi, has_ansi

clean = strip_ansi("\x1b[31mred text\x1b[0m")  # "red text"
has_ansi("\x1b[1mbold\x1b[0m")  # True
```

## Migrating from tether

This package was previously named **tether**. To upgrade:

```bash
pip uninstall tether
pip install ptylink
```

Then update your imports and any exception references:

```python
# Before
import tether
from tether import TetherError

# After
import ptylink
from ptylink import PtylinkError
```

All other APIs are identical.

## pexpect Migration Guide

### Zero-Change Migration

```python
# Before
import pexpect

# After — just change the import
import ptylink.compat as pexpect
```

All pexpect names are available: `spawn`, `run`, `EOF`, `TIMEOUT`, `pxssh`.

### Manual Migration

| pexpect | ptylink |
|---------|--------|
| `pexpect.spawn(cmd)` | `ptylink.Spawn(cmd)` |
| `pexpect.run(cmd)` | `ptylink.run(cmd)` |
| `pexpect.EOF` | `ptylink.EOF_TYPE` |
| `pexpect.TIMEOUT` | `ptylink.TIMEOUT_TYPE` |
| `pexpect.pxssh.pxssh()` | `ptylink.SSHSession()` |
| `pexpect.spawn(cmd, async_=True)` | `ptylink.AsyncSpawn(cmd)` |

### Breaking Changes

- `EOF` and `TIMEOUT` are sentinel types, not exception classes. Use `EOF_TYPE` and `TIMEOUT_TYPE` in pattern lists.
- `async_=True` parameter is removed. Use `AsyncSpawn` instead.
- `before` attribute no longer contains leaked `sendline()` echo text.

## Fixes from pexpect

- **#821** — `before` attribute no longer contains echoed `sendline()` input
- **#817** — No `ResourceWarning` from `os.fork()` on Python 3.12+
- **#677** — No deprecated `@asyncio.coroutine` usage; native `async def` throughout

## Benchmarks

| Operation | ptylink (us/op) | pexpect (us/op) | Speedup |
|-----------|---------------:|----------------:|--------:|
| spawn+expect (echo) | 3,002 | 285,821 | 95x |
| spawn+expect (python) | 84,312 | 307,303 | 3.6x |
| run (echo) | 3,352 | 163,946 | 49x |

## License

ISC
