# Draft tickets: two graph defects (not posted; filing needs the owner's approval)

Written to the ticket standard (outcome title, who is affected, a reproduction command, expected, scope, where to start, done when).
Reproduced on `ccbf847` on 2026-11-21.

## 1. `pack error "MESSAGE"` names the files that raise the message, not files that merely contain a function by that name

**Who is affected and why it matters.** An agent that starts from an error text and runs `devkb pack error "..."` is told which
functions raise it. When the list is wrong the agent reads the wrong files and, because the pack carries a Coverage line, takes the
list as the answer. The router's `error` route had to add its own check for exactly this.

**Reproduce.**
```
.venv/bin/devkb pack --project . error "bad regular expression"
grep -rln "bad regular expression" --include=*.py devkb tests bench
```
**Actual.** "Raised by" lists six functions (`bench/cpp/adjudicate.py::judge`, `bench/policy/accept/205-group.py::r206`,
`devkb/bench/pipeline.py::registry`, two in `tests/test_triage_robustness.py`, one under `bench/results/`). None of those files contains
the text. `devkb/read_tools.py` (the raiser: `f"bad regular expression: {e}"`, line 175) and the test that checks it are not listed. The
Coverage line says "Incomplete: calls under this name from 429 function(s) could not be attributed", which is about a different name.

**Expected.** Every function listed contains the message (as a literal, or a format string whose literal part is searchable) in its own
source; one that raises it through a computed message is listed apart as "message not searchable"; when no function contains the text,
the pack says so and points at `devkb docs` or a text search instead of listing near matches.

**Scope.** `pack error`'s matching of the message to raising functions (`devkb/packs.py`, the error pack, and the index it reads).
Not the router.

**Where to start.** `Packer.error` in `devkb/packs.py`; check how the message is matched (it appears to match on words or a short
fragment, not the whole literal). `devkb/router.py::error_bundle` already filters raisers by whether the file holds the message: that
check belongs in the pack.

**Done when.** The reproduction lists `devkb/read_tools.py::ReadTools.resolve` and no function from a file without the text; a
message that appears nowhere gets an explicit "no function raises this text" answer; a test covers a message that is a prefix of another.

## 2. The tests a change endangers are under-listed when a test reaches the function through a variable the graph cannot type

**Who is affected and why it matters.** `pack refactor` and `pack file` are the tools for "which tests to run". On 13 recent
changes, `pack file` named 0.73 of the test files that actually execute the changed functions and `pack refactor` 0.12 (a plain search
for the function name gets 0.72). A pack that omits a covering test is read as complete.

**Reproduce.**
```
.venv/bin/python bench/quality/qb1_tests.py score 632f8d0 ea9d037 215c505   # needs QB1_PY, see the script
.venv/bin/devkb pack --project . refactor Packer::refactor
grep -n "packer.refactor" tests/test_boundaries.py
```
**Actual.** "Test files among them" lists five files; `tests/test_boundaries.py` calls `packer.refactor(...)` (line 25) with
`api, packer = P.api(...)`, a tuple unpacked from a helper, and is not among them. Other shapes: a name passed as a string
(`api.call("symbol", ...)`), a module loaded by `importlib`. In the benchmark about 8 distinct (test, function) pairs were of this kind.

**Expected.** A call on a variable bound by tuple-unpacking a function whose return statement builds constructed objects is attributed
(the typed-receiver forms the Python extractor already handles, extended to tuple targets and to returns of helpers in the same
repository). Where the graph cannot attribute, the pack names the test files that call or quote the name, as it now does for
`refactor`, and says Incomplete.

**Scope.** `_typed_calls` and the return-type table in `devkb/build_symbols.py`; the `pack file` test section. Not the guardrail.

**Where to start.** `visit_function` in `_typed_calls` (the `ast.Assign` branch handles one name target only); `docs/analysis/qb1-baseline.md`.

**Done when.** The reproduction lists `tests/test_boundaries.py`; the QB1 benchmark's recall for `pack file` rises on the three
snapshots and on the held-out ones, with precision not below 0.6.
