"""Remaining acceptance checks for the plain branch: the same functions from acceptance.py (sha256 9f03c5ab...),
unchanged, with the online step limited to lattice-scan because the full check timed out on Mealie's online build."""
import json, random, re, shutil, sys, tempfile
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
import acceptance as A

def online_lattice_only(branch, tmp, res):
    src = A.check_online.__code__
    res["online"] = {"mealie": {"exit": "timeout", "note": "the full acceptance run timed out (50 min) in this build; REST rate limit consumed"}}
    saved = A.REPOS
    A.REPOS = {"lattice-scan": saved["lattice-scan"], "mealie": saved["mealie"]}
    # run the original function body for lattice-scan only by temporarily narrowing its loop input
    code = src.co_consts
    orig = A.check_online
    def patched(branch, tmp, res):
        r0 = res.get("online", {})
        exec(compile(open(A.__file__).read().split("def check_online")[1].split("def check_pack")[0]
                     .replace('for rid in ("lattice-scan", "mealie"):', 'for rid in ("lattice-scan",):'), "x", "exec") if False else "", {})
    # simpler: copy of check_online with the loop narrowed, built from the source text
    text = open(A.__file__).read()
    body = "def check_online" + text.split("def check_online")[1].split("\ndef check_pack")[0]
    body = body.replace('for rid in ("lattice-scan", "mealie"):', 'for rid in ("lattice-scan",):')
    ns = dict(vars(A)); exec(body, ns)
    keep = res["online"]["mealie"]
    ns["check_online"](branch, tmp, res)
    res["online"]["mealie"] = keep
    A.REPOS = saved

branch, out = Path(sys.argv[1]).resolve(), Path(sys.argv[2])
res = {"branch": str(branch), "commit": A.sh(["git", "rev-parse", "HEAD"], cwd=branch).stdout.strip()}
tmp = Path(tempfile.mkdtemp(prefix="adr007-eval-"))
py = branch / ".venv" / "bin" / "python"
t = A.sh([str(py), "-m", "pytest", "tests", "-q", "-p", "no:cacheprovider"], cwd=branch)
res["tests"] = {"exit": t.returncode, "summary": (t.stdout.strip().splitlines() or [""])[-1]}
s = A.sh([str(py), "-c", "from devkb.model import NODE_TYPES, VERBS; import json; print(json.dumps(['PullRequest' in NODE_TYPES, 'MERGES' in VERBS, 'CLOSES' in VERBS]))"], cwd=branch)
res["schema"] = json.loads(s.stdout) if s.returncode == 0 else s.stderr[-300:]
for name, fn in (("offline", A.check_offline), ("online", online_lattice_only), ("pack", A.check_pack), ("regression", A.check_regression)):
    try:
        fn(branch, tmp, res)
    except Exception as exc:
        res[f"{name}_error"] = f"{type(exc).__name__}: {exc}"
A.check_privacy([tmp / f"off-{r}" for r in A.REPOS] + [Path(p) for p in res.pop("_online_graphs", [])], res)
res.pop("_pr_meta", None)
res["diff"] = A.sh(["git", "diff", "--shortstat", "53ebb83", "HEAD"], cwd=branch).stdout.strip()
Path(out).write_text(json.dumps(res, indent=1)); shutil.rmtree(tmp, ignore_errors=True)
