"""Work, not time, for the linearity tests (#377, #371's form): the Python lines a module executes while a function runs, counted with `sys.settrace`.

A wall-clock ratio flakes on a loaded machine (the benchmarks run agents in parallel). A line count is the same on every run and separates linear from
quadratic: 4x the input is about 4x the lines when linear, about 16x when quadratic.

One blind spot: a line count does not see quadratic work inside a single C-level call, such as a regex scanning a growing string. Where the regression a
test guards against is of that kind, the test must say how it still sees it (or keep a timing check for that case alone)."""
from __future__ import annotations

import sys


def lines_executed(fn, *files: str):
    """(lines executed in `files` while fn() ran, fn's result). A tracer already installed (coverage) is restored afterwards.

    The count is exact, so a bound can sit close above the linear ratio: on #194 the linear ratio for 3x the files is 2.99 and the same code with its fix
    reverted reads 3.82, so that test's bound is 3.4, not a loose "less than quadratic"."""
    n = [0]
    mine = set(files)

    def local(frame, event, arg):
        if event == "line":
            n[0] += 1
        return local

    old = sys.gettrace()
    sys.settrace(lambda frame, event, arg: local if frame.f_code.co_filename in mine else None)
    try:
        result = fn()
    finally:
        sys.settrace(old)
    return n[0], result
