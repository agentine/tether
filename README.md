# tether

Modern process interaction library for Python — expect-style automation with PTY support.

Drop-in replacement for [pexpect](https://github.com/pexpect/pexpect) with full type annotations, native async/await, and zero dependencies.

## Installation

```bash
pip install tether
```

## Quick Start

```python
import tether

with tether.spawn("python3") as child:
    child.expect(">>> ")
    child.sendline("print('hello')")
    child.expect("hello")
    print(child.before)
```

## License

ISC
