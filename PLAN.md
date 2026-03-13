# tether — Implementation Plan

**Target:** Replace `pexpect` (pexpect/pexpect)
**Package name:** `tether` (verified available on PyPI 2026-03-13)
**License:** ISC
**Python:** >= 3.10
**Dependencies:** Zero (pure Python, PTY handling built-in)

---

## Problem Statement

`pexpect` is the dominant Python library for controlling interactive programs in a pseudo-terminal with **149M downloads/month** (PyPI #152). It has:

- **Two primary maintainers** (takluyver: 432 commits, jquast: 320 commits) — high bus factor risk
- **Stale releases** — last release v4.9 on November 25, 2023 (2+ years ago); previous release v4.8 was January 2020
- **165 open issues** including deprecated asyncio.coroutine usage (#677), Python 3.12 fork warnings (#817), ANSI leaks on macOS 3.14 (#824), bare except clauses (#826)
- **Stale pull requests** — PRs from 2024-2026 unmerged (e.g., #826 basic cleanup, #822 dependency bump)
- **No type annotations** — no py.typed, no mypy/pyright support
- **Weak async support** — only `async_=True` parameter hack, uses deprecated `@asyncio.coroutine`
- **Separate ptyprocess dependency** — also stale (last release v0.7.0, December 2020)
- **Poor Windows support** — popen_spawn fallback only, no ConPTY
- **No funding** — not on Tidelift, no GitHub Sponsors, no corporate backing
- **No well-known replacement** — wexpect is Windows-only; no modern async-first expect library exists

## Scope

Modern process interaction library for controlling interactive CLI programs:

1. **Process spawning** — PTY allocation (Unix), ConPTY (Windows 10+), Popen fallback
2. **Pattern matching** — expect patterns on process output (regex, literal, EOF, TIMEOUT)
3. **Input sending** — send, sendline, sendcontrol, sendeof, sendintr
4. **Timeout handling** — per-operation and default timeouts
5. **Session state** — before/after/match attributes for matched content
6. **Interactive mode** — passthrough for manual interaction
7. **High-level API** — run() for simple command execution with expect
8. **SSH helper** — SSH session management (login, command execution)
9. **Async support** — native async/await for all operations
10. **pexpect compatibility** — drop-in shim for existing code

## Architecture Overview

```
src/tether/
├── __init__.py          # Public API exports
├── py.typed             # PEP 561 marker
├── _types.py            # Type aliases, protocols, sentinel types
├── _errors.py           # Exception hierarchy (Timeout, EOF, ExitStatus)
├── _pty.py              # PTY allocation and management (replaces ptyprocess)
├── _spawn.py            # Spawn class — core process interaction
├── _expect.py           # Pattern matching engine (compile, search, match)
├── _interact.py         # Interactive passthrough mode
├── _run.py              # High-level run() function
├── _popen.py            # PopenSpawn — non-PTY spawn (Windows, pipes)
├── _ssh.py              # SSH session helper (login, prompts, commands)
├── _screen.py           # ANSI escape sequence handling
├── _async.py            # AsyncSpawn — native async/await spawn
└── _compat.py           # pexpect drop-in compatibility shim
```

### Key Design Decisions

- **Private modules, public API via `__init__.py`** — all internal modules prefixed with `_`, public surface is `tether.spawn()`, `tether.run()`, `tether.Spawn`, etc.
- **Async-first internals** — core I/O uses asyncio; sync API wraps async with `asyncio.run()` / event loop
- **Built-in PTY** — PTY handling built directly into the library (no ptyprocess dependency)
- **Context manager support** — `with tether.spawn("cmd") as child:` for automatic cleanup
- **Compiled patterns** — expect patterns compiled once and reused
- **Sentinel types** — `EOF` and `TIMEOUT` are proper singleton types, not magic integers
- **Modern Python** — 3.10+ required; uses match statements, `|` union types, slots

## Major Components

### 1. Exception Hierarchy (`_errors.py`)

```python
class TetherError(Exception): ...          # Base
class Timeout(TetherError): ...            # Expect timeout
class EOF(TetherError): ...                # Process closed output
class ExitStatus(TetherError):             # Process exited with error
    status: int
    signal: int | None
```

**Fix over pexpect:** Clear exception types with proper attributes. pexpect EOF/TIMEOUT are exception classes AND sentinel values — tether separates these concerns.

### 2. PTY Management (`_pty.py`)

```python
class PtyProcess:
    pid: int
    fd: int

    @classmethod
    def spawn(cls, argv: list[str], ...) -> PtyProcess: ...
    def read(self, size: int = 1024) -> bytes: ...
    def write(self, data: bytes) -> int: ...
    def setwinsize(self, rows: int, cols: int) -> None: ...
    def waitpid(self) -> tuple[int, int]: ...
    def terminate(self, force: bool = False) -> bool: ...
    def isalive(self) -> bool: ...
```

Replaces ptyprocess with built-in PTY handling. Uses `pty.openpty()` + `os.fork()` on Unix with proper signal handling.

**Fix over pexpect/ptyprocess:** Handles Python 3.12+ fork-with-threads warning (#817). Uses `os.login_tty()` on Python 3.13+.

### 3. Spawn Class (`_spawn.py`)

```python
class Spawn:
    before: str           # Text before last match
    after: str            # Text that matched
    match: re.Match | str | None

    def __init__(self, command: str, *, timeout: float = 30, encoding: str = "utf-8", ...) -> None: ...
    def __enter__(self) -> Spawn: ...
    def __exit__(self, ...) -> None: ...
    def expect(self, pattern: Pattern, *, timeout: float = -1) -> int: ...
    def expect_exact(self, pattern: str | list[str], ...) -> int: ...
    def expect_list(self, patterns: list[Pattern], ...) -> int: ...
    def send(self, s: str) -> int: ...
    def sendline(self, s: str = "") -> int: ...
    def sendcontrol(self, char: str) -> int: ...
    def sendeof(self) -> None: ...
    def sendintr(self) -> None: ...
    def read(self, size: int = -1) -> str: ...
    def readline(self) -> str: ...
    def isalive(self) -> bool: ...
    def wait(self) -> int: ...
    def close(self, force: bool = True) -> None: ...
    def terminate(self, force: bool = False) -> bool: ...
    def interact(self, ...) -> None: ...
```

**Fixes over pexpect:**
- Context manager for automatic cleanup
- `before` never contains input from `sendline` (#821)
- No bare except clauses (#826)
- Proper typing on all methods

### 4. Pattern Matching (`_expect.py`)

```python
Pattern = str | re.Pattern[str] | type[EOF_TYPE] | type[TIMEOUT_TYPE]

def compile_pattern(pattern: Pattern) -> CompiledPattern: ...
def expect_loop(spawn: Spawn, patterns: list[CompiledPattern], timeout: float) -> int: ...
```

Patterns are compiled once. The expect loop uses `select.select()` (Unix) or polling for non-blocking reads.

### 5. Async Spawn (`_async.py`)

```python
class AsyncSpawn:
    async def expect(self, pattern: Pattern, *, timeout: float = -1) -> int: ...
    async def send(self, s: str) -> int: ...
    async def sendline(self, s: str = "") -> int: ...
    async def read(self, size: int = -1) -> str: ...
    async def __aenter__(self) -> AsyncSpawn: ...
    async def __aexit__(self, ...) -> None: ...
```

**Fix over pexpect:** Native async/await, not retrofitted `async_=True` parameter. Uses `asyncio.get_event_loop().add_reader()` for non-blocking PTY reads. No deprecated `@asyncio.coroutine`.

### 6. SSH Helper (`_ssh.py`)

```python
class SSHSession:
    def __init__(self, server: str, *, username: str | None = None, port: int = 22, ...) -> None: ...
    def login(self, ...) -> None: ...
    def prompt(self, timeout: float = -1) -> bool: ...
    def run(self, command: str, *, timeout: float = -1) -> str: ...
    def logout(self) -> None: ...
```

Wraps Spawn for SSH connections with login automation and prompt detection.

### 7. Popen Spawn (`_popen.py`)

```python
class PopenSpawn:
    """Non-PTY spawn using subprocess.Popen. Works on Windows."""
    # Same interface as Spawn but uses pipes instead of PTY
```

### 8. Compatibility Shim (`_compat.py`)

Drop-in replacement for code using `import pexpect`:

```python
# tether.compat provides all pexpect public names
from tether.compat import spawn, run, EOF, TIMEOUT
from tether.compat import pxssh  # maps to tether.SSHSession
```

## Phases

### Phase 1: Core — PTY, Spawn, Expect (Priority: highest)
- Exception hierarchy
- PTY process management (fork, pty, signals)
- Spawn class with send/sendline/expect/expect_exact
- Pattern matching engine (regex, literal, EOF, TIMEOUT)
- Timeout handling
- Context manager (with/as)
- before/after/match state
- isalive/wait/close/terminate
- Unit tests for all core functionality

### Phase 2: Advanced Features
- expect_list (multiple pattern matching)
- sendcontrol/sendeof/sendintr
- interact() mode
- run() high-level function
- Logging/debugging support
- Window size management (setwinsize)
- ANSI escape sequence handling
- Unit tests for advanced features

### Phase 3: Extensions
- AsyncSpawn — native async/await
- PopenSpawn — non-PTY (pipes, Windows support)
- SSHSession — SSH login/command helper
- Unit tests for extensions

### Phase 4: Quality & Compatibility
- pexpect compatibility shim
- Cross-verification tests (run same scenarios with pexpect and tether)
- mypy --strict and pyright clean
- Benchmarks vs pexpect
- CI (GitHub Actions: Python 3.10, 3.11, 3.12, 3.13, ubuntu + macos)
- pyproject.toml with full metadata

### Phase 5: Documentation & Release
- README.md with migration guide from pexpect
- CHANGELOG.md
- API reference (docstrings, all public functions)
- Release v0.1.0 to PyPI

## Deliverables

- `projects/tether/` — complete Python package
- Process spawning with PTY allocation
- Expect-style pattern matching on process output
- Native async/await support
- SSH session helper
- PopenSpawn for Windows/pipe-based operation
- pexpect compatibility shim
- 100% type-annotated, mypy/pyright strict clean
- Comprehensive test suite with cross-verification
- Benchmarks vs pexpect
- CI pipeline
- README with pexpect migration guide

## Success Criteria

- `tether.spawn("python3")` spawns process with PTY, expect/send works
- `child.expect(r">>> ")` matches Python REPL prompt
- `child.sendline("print('hello')")` sends input correctly
- `child.before` contains output without leaked input (#821 fix)
- `async with tether.AsyncSpawn("cmd") as child:` works with native async
- `with tether.spawn("cmd") as child:` auto-cleans up on exit
- No Python 3.12+ fork warnings (#817)
- mypy --strict passes with zero errors
- pytest passes on Python 3.10, 3.11, 3.12, 3.13
- Benchmark within 2x of pexpect performance (targeting parity)
