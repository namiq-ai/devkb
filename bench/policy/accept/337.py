"""#337: an option withholds a ticket's location from the prompt. Black box on the checkout's harness (bench/policy):
- hidden_prompt_has_no_location_names: #286's prompt with the location withheld names neither `_resolve_cross_file_symbol` nor
  `_star_modules` (what its "Where to start" gave), and has no "Where to start" text of its own;
- rest_of_ticket_kept: its "Expected" and "Reproduce" text is still there;
- filed_prompt_unchanged: without the option, the prompt holds the ticket as filed, names included;
- hidden_arms_set_up_as_base: a hidden-location arm exists for the no-devkb and the devkb arm, mapped to those arms.
- (revised after the review of PR #385) no_leak_193 / no_leak_132: the same for #193 (its Scope file and `file:line` repeated
  in Reproduce) and #132 (`_resolve` repeated as `Packer._resolve`), two tickets the first version leaked;
- option_maps_score_too: POLICY_HIDE_START=1 maps arms the same way for scoring as for running (`arms_for`).
The tickets' text is a snapshot (2026-11-20), so the check needs no network. Prints one JSON line."""
import importlib, json, os, sys, tempfile
from pathlib import Path

W = Path(sys.argv[1]).resolve()
TITLE = 'A call through a star re-export (`from .sub import *`) is attributed, or the pack says Incomplete'
BODY = "**Found by** the 0.2.13 release audit (2026-11-19), a bi-arm benchmark of three reviewers with and without devkb (`bench/results/2026-11-19-audit-0.2.13/`). Found in 3 of the 12 runs: agraph-main-r2, agraph-nonekeep-r1, agraph-nonekeep-r2; arms: devkb 0.2.13, no devkb. Every reproduction exits 1 twice on a clean checkout of main 3f56ece.\n\n**Who is affected and why it matters (high):** agents changing a function re-exported by `from .sub import *` in a package `__init__`: its callers through the package are not attributed and `pack change`/`refactor` say Complete with no caller and no test. #192 fixed named re-exports only.\n\n**Reproduce** (from the root of a checkout of main 3f56ece; each run's scripts expect to sit in `audit/`, where the reviewer wrote them):\n```\nrm -rf audit && cp -r bench/results/2026-11-19-audit-0.2.13/runs/agraph-main-r2 audit && PYTHONPATH=audit .venv/bin/python audit/repro/star-reexport-callers-missing.py\n## Coverage\n**Complete.** Every call site under these names was attributed to its target; nothing else calls them.\n---\nThis pack was extracted from the source by the dev-process graph; each item carries the line that proves it. Treat it as the answer: re-read a file only if it is listed as changed, and search only where Coverage says the\nDEFECT: callers reached through a star re-export are missing, and the pack still says Complete: ['app.py::direct', 'app.py::via_pkg']\nEXPECTED: both callers and tests/test_app.py listed, or Incomplete\n```\n```\nrm -rf audit && cp -r bench/results/2026-11-19-audit-0.2.13/runs/agraph-nonekeep-r1 audit && PYTHONPATH=audit .venv/bin/python audit/repro/star-reexport-call-unattributed.py\n- none the graph resolves\n## Test files to run (0): every test calling it or a function on those paths\n- none in the graph\n## Coverage\n**Complete.** Every call site under these names was attributed to its target; nothing else calls them.\nexpected: use.py::a (and tests/test_u.py) listed, or Coverage Incomplete; actual: caller listed = False Complete = True\n```\n```\nrm -rf audit && cp -r bench/results/2026-11-19-audit-0.2.13/runs/agraph-nonekeep-r2 audit && PYTHONPATH=audit .venv/bin/python audit/repro/star_reexport_complete.py\n(The defining file `pkg/sub.py` is not counted as a caller.)\n## Coverage\n**Complete.** Every call site under these names was attributed to its target; nothing else calls them.\nrefactor -> callers found: False | says Complete: True\nBAD: starfn is called from user.py (c, g), reached through `from .sub import *`, yet the pack says Complete with no caller and no test\nexpected: the two callers (and tests/test_u.py), or Incomplete naming pkg/user.py\n```\n\n**Expected:**\n- the callers and their tests are listed, or the pack says Incomplete and names the files\n\n**Scope:** `devkb/build_symbols.py` cross-file resolution; tests.\n\n**Where to start:** `_resolve_cross_file_symbol` re-export following (#192) and `_star_modules`.\n\n**Done when:** each reproduction above exits 0, a regression test for each case fails on main 3f56ece and passes after the fix, and the full suite is green.\n"
res = {}
sys.path.insert(0, str(W / "bench" / "policy"))
os.environ.setdefault("POLICY_TEMPLATES_DIR", tempfile.mkdtemp())
try:
    pb = importlib.import_module("policybench")
except Exception as e:  # noqa: BLE001
    print(json.dumps({"import": f"{type(e).__name__}: {e}"[:200], "pass": False}))
    sys.exit(0)

def prompt(hide):
    fn = getattr(pb, "prompt_for", None)
    if fn is None:
        return None
    try:
        return fn("286", TITLE, BODY, W, hide)
    except TypeError:
        return fn("286", TITLE, BODY, W, hide=hide)

hidden, filed = prompt(True), prompt(False)
names = ("_resolve_cross_file_symbol", "_star_modules")
res["hidden_prompt_has_no_location_names"] = bool(hidden) and not any(n in hidden for n in names) and "re-export following (#192)" not in hidden
res["rest_of_ticket_kept"] = bool(hidden) and "**Expected" in hidden and "**Reproduce" in hidden and "star re-export" in hidden.lower()
res["filed_prompt_unchanged"] = bool(filed) and all(n in filed for n in names)
hl = getattr(pb, "HIDE_LOCATION", {}) or {}
res["hidden_arms_set_up_as_base"] = sorted(hl.values()) == ["main", "none"]   # each hidden arm names the arm it is set up as
T193, B193 = ('A dataclass field named like a function makes calls to that function unresolved (same file and cross-file), losing CALLS edges and the tests they lead to', '**Follow-up of #148.** Found by the 0.2.12 release audit (2026-11-18), reproduced twice (by the reviewer and again before filing).\n\n**Who is affected and why it matters (high):** #148 adds `field` (and #143 `constant`) Symbols to per_file_symbols. Pass 2 puts every non-method symbol into bare_by_short by its short name, so `Job.run` (a field) and `def run()` give two local targets and `run()` resolves to nothing. Cross-file, _resolve_cross_file_symbol._match (L636) also matches by short name and finds two hits. v0.2.11: `run` callers 1; v0.2.12: callers 0+, and `pack refactor run` cannot resolve. Through a re-export (combined with the finding above) the pack loses the caller and the test entirely and says Complete.\n\n**Reproduce** (`devkb/build_symbols.py:1471` at `v0.2.12`; the fixture script is `audit-0.2.12/graph/r01c_field_shadow_reexport.py` in the audit workspace, summarised here):\n```\nr01 v0.2.11: run   callers 1 / Files with a direct caller (1) pkg/records.py:15: return run()\nr01 v0.2.12: run   callers 0+ (... 2 symbols share the name) / 2. pkg/records.py  field  L7  run: int = 0 / pack refactor: cannot resolve `run` unambiguously\nr01c v0.2.11: Functions that reach it (1) app/user.py::caller; Test files to run (1) tests/test_user.py\nr01c v0.2.12: Functions that reach it (0); Test files to run (0); **Complete.**\n```\n\n**Expected:** A field or constant is never a call target: `run()` resolves to the function, as in v0.2.11.\n\n**Scope:** the code at `devkb/build_symbols.py:1471` and a regression test; nothing else.\n\n**Where to start:** build_symbols.extract pass 2 (L1467-1471, and the middleware table at L1400): skip kind field/constant when building bare_by_short/local_by_short; _resolve_cross_file_symbol._match: ignore field (nested) symbols, or match qualified_name == short_name for bare imports.\n\n**Done when:** a fixture test reproduces the case above and fails on `v0.2.12`, and passes after the fix with the full suite green.\n')
T132, B132 = ('`pack change` / `pack refactor` accept the C++ `Class::method` spelling that `symbol` accepts', '**Severity:** high for C/C++ users. It is the most common way a C++ agent names a method, and the failure sends the agent back to grep.\n\n**Who is affected and why it matters:** every agent asking devkb about a C++ method\'s callers. In the #130 benchmark (`Footer::DecodeFrom`, leveldb), 4 of the 16 `pack` calls agents made returned "cannot resolve" for exactly this spelling. Each of those runs then walked the call chain by hand with grep, and drew 9 of the 54 guardrail refusals (#131).\n\n**Reproduce (devkb 0.2.11, leveldb at the corpus pin):**\n```\ndevkb pack change Footer::DecodeFrom --project ~/.cache/devkb/cpp-corpus/leveldb   # The graph cannot resolve `Footer::DecodeFrom`. Search the code.\ndevkb pack change Footer.DecodeFrom  --project ~/.cache/devkb/cpp-corpus/leveldb   # Functions that reach it, at any depth (24) ...\ndevkb symbol Footer::DecodeFrom      --project ~/.cache/devkb/cpp-corpus/leveldb   # 1 match (qualified): table/format.cc L43-67\n```\n\n**Actual:** `pack` resolves `Class.method` but not `Class::method` (nor `ns::Class::method`), while `symbol` resolves all of them.\n\n**Expected:** `pack change`, `pack refactor` and the MCP `pack` tool resolve a name exactly as `symbol` does: `::` is accepted as a qualifier separator. When a name is ambiguous, the answer lists the candidates instead of "cannot resolve".\n\n**Scope:** name resolution in `devkb/packs.py` (`Packer._resolve` / `_by_module_name`); reuse `ReadTools.resolve`\'s rules rather than a second resolver.\n\n**Where to start:** `devkb/packs.py` `_resolve` (the "cannot resolve" path) and `devkb/read_tools.py` `resolve` (the tiers `symbol` uses).\n\n**Done when:**\n- a C++ fixture resolves `pack change A::f`, `ns::A::f` and `A.f` to the same symbol;\n- the leveldb reproduction returns the 24 callers for `Footer::DecodeFrom`;\n- an ambiguous bare name lists its candidates.')
def hidden_of(issue, t, b):
    fn = getattr(pb, "prompt_for", None)
    return fn(issue, t, b, W, True) if fn else ""
h193, h132 = hidden_of("193", T193, B193), hidden_of("132", T132, B132)
res["no_leak_193"] = bool(h193) and "build_symbols" not in h193 and ":1471" not in h193 and "_resolve_cross_file_symbol" not in h193
res["no_leak_132"] = bool(h132) and "_resolve" not in h132 and "packs.py" not in h132 and "read_tools" not in h132
af = getattr(pb, "arms_for", None)
os.environ["POLICY_HIDE_START"] = "1"
try:
    res["option_maps_score_too"] = bool(af) and af(["none", "main"]) == ["nonehid", "mainhid"]
finally:
    os.environ.pop("POLICY_HIDE_START", None)
res["pass"] = all(res.values())
print(json.dumps(res))
