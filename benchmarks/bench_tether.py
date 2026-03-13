"""Benchmarks: tether vs pexpect performance comparison."""

from __future__ import annotations

import time


def bench(name: str, fn: object, iterations: int) -> float:
    """Time a function over *iterations* and return µs/op."""
    # Warm up
    fn()  # type: ignore[operator]

    start = time.perf_counter()
    for _ in range(iterations):
        fn()  # type: ignore[operator]
    elapsed = time.perf_counter() - start
    us_per_op = (elapsed / iterations) * 1_000_000
    print(f"  {name}: {us_per_op:.0f} µs/op ({iterations} iterations)")
    return us_per_op


def bench_tether_echo() -> None:
    from tether import Spawn

    with Spawn("echo hello") as child:
        child.expect("hello")


def bench_pexpect_echo() -> None:
    import pexpect

    child = pexpect.spawn("echo hello")
    child.expect("hello")
    child.close()


def bench_tether_python() -> None:
    from tether import Spawn

    with Spawn("python3 -c \"print(1+1)\"") as child:
        child.expect("2")


def bench_pexpect_python() -> None:
    import pexpect

    child = pexpect.spawn("python3 -c \"print(1+1)\"")
    child.expect("2")
    child.close()


def bench_tether_run() -> None:
    from tether import run

    run("echo hello")


def bench_pexpect_run() -> None:
    import pexpect

    pexpect.run("echo hello")


def main() -> None:
    iterations_fast = 100
    iterations_slow = 50

    print("=== Spawn + expect (echo hello) ===")
    t_echo = bench("tether", bench_tether_echo, iterations_fast)
    p_echo = bench("pexpect", bench_pexpect_echo, iterations_fast)
    ratio_echo = p_echo / t_echo if t_echo > 0 else 0

    print(f"\n=== Spawn + expect (python3 print) ===")
    t_py = bench("tether", bench_tether_python, iterations_slow)
    p_py = bench("pexpect", bench_pexpect_python, iterations_slow)
    ratio_py = p_py / t_py if t_py > 0 else 0

    print(f"\n=== run('echo hello') ===")
    t_run = bench("tether", bench_tether_run, iterations_fast)
    p_run = bench("pexpect", bench_pexpect_run, iterations_fast)
    ratio_run = p_run / t_run if t_run > 0 else 0

    print(f"\n=== Summary ===")
    print(f"  echo: tether {t_echo:.0f} µs vs pexpect {p_echo:.0f} µs ({ratio_echo:.2f}x)")
    print(f"  python: tether {t_py:.0f} µs vs pexpect {p_py:.0f} µs ({ratio_py:.2f}x)")
    print(f"  run: tether {t_run:.0f} µs vs pexpect {p_run:.0f} µs ({ratio_run:.2f}x)")

    # Write results
    with open("benchmarks/RESULTS.md", "w") as f:
        f.write("# Benchmark Results\n\n")
        f.write("**Environment:** Python 3.14, macOS Darwin 25.3.0\n")
        f.write(f"**Date:** {time.strftime('%Y-%m-%d')}\n\n")
        f.write("## tether vs pexpect\n\n")
        f.write("| Operation | tether (µs/op) | pexpect (µs/op) | Ratio |\n")
        f.write("|-----------|---------------:|----------------:|------:|\n")
        f.write(f"| spawn+expect (echo) | {t_echo:.0f} | {p_echo:.0f} | {ratio_echo:.2f}x |\n")
        f.write(f"| spawn+expect (python) | {t_py:.0f} | {p_py:.0f} | {ratio_py:.2f}x |\n")
        f.write(f"| run (echo) | {t_run:.0f} | {p_run:.0f} | {ratio_run:.2f}x |\n")
        f.write(f"\ntether is **{min(ratio_echo, ratio_py, ratio_run):.1f}×–{max(ratio_echo, ratio_py, ratio_run):.1f}×** ")
        if min(ratio_echo, ratio_py, ratio_run) >= 1.0:
            f.write("faster than pexpect across all operations.\n")
        else:
            f.write("compared to pexpect (ratio = pexpect/tether).\n")


if __name__ == "__main__":
    main()
