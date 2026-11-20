"""#337: an option withholds a ticket's location from the prompt. Black box on the checkout's harness (bench/policy):
- hidden_prompt_has_no_location_names: #286's prompt with the location withheld names neither `_resolve_cross_file_symbol` nor
  `_star_modules` (what its "Where to start" gave), and has no "Where to start" text of its own;
- rest_of_ticket_kept: its "Expected" and "Reproduce" text is still there;
- filed_prompt_unchanged: without the option, the prompt holds the ticket as filed, names included;
- hidden_arms_set_up_as_base: a hidden-location arm exists for the no-devkb and the devkb arm, mapped to those arms.
#286's text is a snapshot (2026-11-20), so the check needs no network. Prints one JSON line."""
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
res["pass"] = all(res.values())
print(json.dumps(res))
