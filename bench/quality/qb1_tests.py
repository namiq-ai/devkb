#!/usr/bin/env python3
"""QB1 (docs/specs/quality-benchmarks.md): for a change, which tests does each method name, against the tests that really
cover the changed code? Offline, no model runs.

  snapshot SHA     worktree of the commit, its graph built by that commit's own devkb, and one coverage run with a context
                   per test: which test executed which line
  items SHA        the next commits that change devkb functions which exist at the snapshot, with the functions changed
  score SHA...     for every item: what `devkb pack file`, `devkb pack refactor` and three baselines name, against the truth

Truth: the test files whose coverage context executed a body line of a changed function at the snapshot. `specific` leaves out
the wide tests (a test file that executes more than WIDE of all covered lines: integration tests touch everything).
Arms: devkb-file (pack file: its "Test files to run"), devkb-fn (pack refactor per changed function), devkb (their union),
import (tests that import the module), name (tests named after it), grep (tests that mention a changed function's name).

  QB1_PY=<python with pytest, pytest-cov, pytest-xdist, pyyaml, mcp, scipy>  QB1_CACHE=<dir>  (defaults: see below)
"""
from __future__ import annotations

import ast
import json
import os
import random
import re
import statistics as st
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CACHE = Path(os.environ.get("QB1_CACHE") or Path.home() / ".cache" / "devkb" / "qb1")
PY = os.environ.get("QB1_PY") or sys.executable
WIDE = 0.30
AHEAD = 12
MIN_NAME = 4


def sh(*a, cwd=None, env=None, check=False, timeout=None):
    p = subprocess.run(a, cwd=cwd, env={**os.environ, **(env or {})}, capture_output=True, text=True, timeout=timeout)
    if check and p.returncode:
        raise SystemExit(f"{' '.join(a)[:100]} failed:\n{p.stderr[-600:]}")
    return p.stdout


def tree(sha: str) -> Path:
    return CACHE / sha / "tree"


def devkb(sha: str, *args: str) -> str:
    """The commit's own devkb, on the commit's own tree: what an agent working at that commit had."""
    t = tree(sha)
    code = "import sys; sys.path.insert(0, %r); from devkb.cli import main; sys.argv[0]='devkb'; sys.exit(main())" % str(t)
    return sh(PY, "-c", code, *args, cwd=t, timeout=300)


def snapshot(sha: str, force: bool = False) -> None:
    d = CACHE / sha
    d.mkdir(parents=True, exist_ok=True)
    if force:
        for n in ("cov.json", "health.json", "junit.xml", ".coverage"):
            (d / n).unlink(missing_ok=True)
    if not tree(sha).exists():
        sh("git", "-C", str(ROOT), "worktree", "add", "--detach", str(tree(sha)), sha, check=True)
    if not (tree(sha) / ".devkb" / "nodes.jsonl").exists():
        sh(PY, "-c", "import sys; sys.path.insert(0, %r); from devkb.cli import main; sys.argv[0]='devkb'; sys.exit(main())" % str(tree(sha)),
           "build", "--project", str(tree(sha)), "--allow-foreign-checkout", cwd=tree(sha), timeout=600)
    if not (d / "cov.json").exists():
        env = {"COVERAGE_FILE": str(d / ".coverage"), "PYTHONPATH": str(tree(sha))}
        p = subprocess.run([PY, "-m", "pytest", "-q", "-n", "8", "-p", "no:cacheprovider", "--cov=devkb", "--cov-context=test", "--cov-report=",
                            f"--junitxml={d / 'junit.xml'}", "--ignore=tests/test_bench_user_policy_366.py"], cwd=tree(sha),
                           env={**os.environ, **env}, capture_output=True, text=True, timeout=3600)
        (d / "pytest-tail.txt").write_text(p.stdout[-3000:])
        sh(PY, "-m", "coverage", "json", "--show-contexts", "-o", str(d / "cov.json"), cwd=tree(sha), env=env, check=True)
        health(sha, p.returncode)
    print("snapshot", sha, "ready")


def health(sha: str, rc: int | None = None) -> dict:
    """Did the coverage run run the suite? The exit status, the outcomes per test file from the JUnit file, and the test files that
    left no coverage of devkb/ with what happened to them: a file that passed and covered nothing runs other code (bench/, scripts/);
    a file that errored, failed to collect or was skipped is a hole in the truth."""
    import xml.etree.ElementTree as ET
    d = CACHE / sha
    out = {"pytest_exit": rc, "files": {}}
    try:
        for tc in ET.parse(d / "junit.xml").getroot().iter("testcase"):
            parts = (tc.get("classname") or "").split(".")
            k = next((i for i, x in enumerate(parts) if x.startswith("test_")), None)
            if k is None:
                continue
            f = "/".join(parts[:k + 1]) + ".py"                  # `tests.test_x.TestY` -> tests/test_x.py
            o = out["files"].setdefault(f, {"passed": 0, "failed": 0, "error": 0, "skipped": 0})
            kind = "failed" if tc.find("failure") is not None else "error" if tc.find("error") is not None else "skipped" if tc.find("skipped") is not None else "passed"
            o[kind] += 1
    except (OSError, ET.ParseError):
        out["junit"] = "missing"
    seen: set[str] = set()
    cov = json.loads((d / "cov.json").read_text()) if (d / "cov.json").exists() else {"files": {}}
    for f, info in cov["files"].items():
        for ctxs in (info.get("contexts") or {}).values():
            seen |= {c.split("::")[0] for c in ctxs if c.startswith("tests/")}
    allf = set(test_texts(sha))
    out["no_coverage"] = {f: out["files"].get(f, "not in the JUnit file (not collected)") for f in sorted(allf - seen)}
    out["holes"] = {f: v for f, v in out["no_coverage"].items() if not isinstance(v, dict) or v["failed"] or v["error"] or (v["skipped"] and not v["passed"])}
    (d / "health.json").write_text(json.dumps(out, indent=1))
    return out


def functions(src: str) -> dict[str, tuple[int, int, int, str]]:
    """qualified name -> (first body line, last line, def line, source) for every function and method."""
    try:
        mod = ast.parse(src)
    except SyntaxError:
        return {}
    out = {}

    def walk(node, prefix):
        for n in ast.iter_child_nodes(node):
            if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)):
                q = prefix + n.name
                out[q] = (n.body[0].lineno, n.end_lineno, n.lineno, ast.get_source_segment(src, n) or "")
                walk(n, q + ".")
            elif isinstance(n, ast.ClassDef):
                walk(n, prefix + n.name + ".")
    walk(mod, "")
    return out


def show(sha: str, path: str) -> str | None:
    p = subprocess.run(["git", "-C", str(ROOT), "show", f"{sha}:{path}"], capture_output=True, text=True)
    return p.stdout if p.returncode == 0 else None


def after(sha: str) -> list[str]:
    """The first-parent commits after `sha` on origin/main, oldest first."""
    ids = sh("git", "-C", str(ROOT), "rev-list", "--first-parent", "--reverse", f"{sha}..origin/main").split()
    return ids[:AHEAD]


def items(sha: str) -> list[dict]:
    snap = {p: functions(show(sha, p) or "") for p in sh("git", "-C", str(ROOT), "ls-tree", "-r", "--name-only", sha, "devkb").split()
            if p.endswith(".py")}
    out = []
    for c in after(sha):
        changed = []
        for line in sh("git", "-C", str(ROOT), "diff", "--name-status", f"{c}^", c, "--", "devkb").splitlines():
            st_, _, path = line.partition("\t")
            if st_ != "M" or not path.endswith(".py") or path not in snap:
                continue
            old, new = functions(show(f"{c}^", path) or ""), functions(show(c, path) or "")
            for q, (_a, _b, _d, body) in new.items():
                if q in old and old[q][3] != body and q in snap[path]:
                    a, b, d, _ = snap[path][q]
                    changed.append({"file": path, "qual": q, "body": [a, b]})
        if changed:
            out.append({"commit": c, "subject": sh("git", "-C", str(ROOT), "log", "-1", "--pretty=%s", c).strip()[:80], "changed": changed})
    return out


def coverage_tables(sha: str):
    cov = json.loads((CACHE / sha / "cov.json").read_text())
    by_line: dict[tuple[str, int], set[str]] = {}
    per_test: dict[str, set] = {}
    for f, info in cov["files"].items():
        if not f.startswith("devkb/"):
            continue
        for ln, ctxs in (info.get("contexts") or {}).items():
            for c in ctxs:
                t = c.split("::")[0]
                if not t.startswith("tests/"):
                    continue
                by_line.setdefault((f, int(ln)), set()).add(t)
                per_test.setdefault(t, set()).add((f, int(ln)))
    total = len({k for k in by_line}) or 1
    wide = {t for t, s in per_test.items() if len(s) / total > WIDE}
    return by_line, wide


def mod_of(path: str) -> str:
    return Path(path).stem


def test_texts(sha: str) -> dict[str, str]:
    return {str(p.relative_to(tree(sha))): p.read_text(errors="replace") for p in sorted((tree(sha) / "tests").glob("test_*.py"))}


def section_tests(out: str) -> set[str]:
    m = re.search(r"## (?:Test files to run|Tests that exercise it|Test files among them)[^\n]*\n(.*?)(?:\n## |\n---|\Z)", out, re.S)   # file pack / change and refactor packs
    return set(re.findall(r"tests/[\w./-]+\.py", m[1])) if m else set()


def predict(sha: str, item: dict, texts: dict[str, str]) -> dict[str, set]:
    files = sorted({c["file"] for c in item["changed"]})
    pf = set().union(*[section_tests(devkb(sha, "pack", "--project", str(tree(sha)), "file", f)) for f in files])
    pn = set()
    for c in item["changed"]:
        subj = c["qual"].replace(".", "::", 1) if "." in c["qual"] else c["qual"]
        pn |= section_tests(devkb(sha, "pack", "--project", str(tree(sha)), "refactor", subj))
    imp, nam, grp = set(), set(), set()
    for f in files:
        m = mod_of(f)
        pat = re.compile(rf"(devkb\.{m}\b|from devkb import [^\n]*\b{m}\b|\"{m}\"|'{m}')")
        imp |= {t for t, x in texts.items() if pat.search(x)}
        nam |= {t for t in texts if m in Path(t).stem}
    for c in item["changed"]:
        n = c["qual"].split(".")[-1]
        if len(n) >= MIN_NAME:
            grp |= {t for t, x in texts.items() if re.search(rf"\b{re.escape(n)}\b", x)}
    real = set(texts)                                   # `tests/conftest.py` and helper modules can never be in the truth
    return {"devkb-file": pf & real, "devkb-fn": pn & real, "devkb": (pf | pn) & real, "import": imp, "name": nam, "grep": grp}


def truth(item: dict, by_line, wide) -> tuple[set, set]:
    allt = set()
    for c in item["changed"]:
        for ln in range(c["body"][0], c["body"][1] + 1):
            allt |= by_line.get((c["file"], ln), set())
    return allt, allt - wide


def score(shas: list[str]) -> None:
    rows = []
    for sha in shas:
        by_line, wide = coverage_tables(sha)
        texts = test_texts(sha)
        for it in items(sha):
            ta, ts = truth(it, by_line, wide)
            if not ta:
                rows.append({"snapshot": sha, "commit": it["commit"], "covered": False})
                continue
            pr = predict(sha, it, texts)
            rows.append({"snapshot": sha, "commit": it["commit"], "subject": it["subject"], "covered": True, "truth": len(ta), "specific": len(ts),
                         "wide_removed": len(ta) - len(ts), "functions": len(it["changed"]),
                         **{f"{a}": {"n": len(p), "rec_all": len(p & ta) / len(ta), "rec_spec": (len(p & ts) / len(ts)) if ts else None,
                                     "prec": (len(p & ta) / len(p)) if p else None} for a, p in pr.items()}})
    out = CACHE / "qb1-results.json"
    out.write_text(json.dumps(rows, indent=1))
    report(rows)


def boot(xs: list[float], n=3000, seed=5) -> tuple[float, float]:
    rnd = random.Random(seed)
    m = sorted(st.mean(rnd.choices(xs, k=len(xs))) for _ in range(n))
    return m[int(.05 * n)], m[int(.95 * n) - 1]


def report(rows: list[dict]) -> None:
    cov = [r for r in rows if r["covered"]]
    print(f"{len(rows)} items; {len(rows) - len(cov)} changed functions no test covers at the snapshot; {len(cov)} scored")
    print(f"truth per item: median {st.median(r['truth'] for r in cov)} test files; {st.median(r['specific'] for r in cov)} after dropping wide tests")
    print("\n| arm | files named | recall (all) | recall (specific) | missed-guard | precision |\n|---|---|---|---|---|---|")
    for a in ("devkb-file", "devkb-fn", "devkb", "import", "name", "grep"):
        ra = [r[a]["rec_all"] for r in cov]
        rs = [r[a]["rec_spec"] for r in cov if r[a]["rec_spec"] is not None]
        miss = sum(1 for r in cov if r[a]["rec_spec"] == 0)
        pr = [r[a]["prec"] for r in cov if r[a]["prec"] is not None]
        lo, hi = boot(ra)
        print(f"| {a} | {st.median(r[a]['n'] for r in cov):.0f} | {st.mean(ra):.2f} ({lo:.2f}-{hi:.2f}) | {st.mean(rs):.2f} | {miss}/{len(rs)} | {st.mean(pr) if pr else 0:.2f} |")


if __name__ == "__main__":
    a = sys.argv[1:]
    if not a or a[0] not in ("snapshot", "items", "score", "health"):
        raise SystemExit(__doc__)
    if a[0] == "snapshot":
        [snapshot(s, "--force" in a) for s in a[1:] if not s.startswith("--")]
    elif a[0] == "health":
        for sha in a[1:]:
            h = health(sha)
            print(sha, "pytest exit", h["pytest_exit"], "|", len(h["files"]), "test files in the JUnit file |", len(h["no_coverage"]), "left no coverage of devkb/ |",
                  len(h["holes"]), "of those are holes (failed, errored, skipped or not collected)")
            for f, v in h["holes"].items():
                print("   ", f, v)
    elif a[0] == "items":
        for it in items(a[1]):
            print(it["commit"], it["subject"], len(it["changed"]), "functions")
    else:
        score(a[1:])
