#!/usr/bin/env python3
"""QB5: from an error message, does `pack error` name the functions that raise it, and only those?  (#399)

Items: the fixed text of the messages devkb's own code raises (`raise X("text ...")`, `raise X(f"text {v}")`: the literal parts of the
string, at least three words). The truth for an item is the function(s) whose source contains that raise. The query is the text
an agent would paste: the first literal run of the message (the part before the first variable). Negative items are made-up messages that
no code raises: the right answer is that no function holds the text.

Metrics (per item, then averaged): recall (the raiser is listed), precision (listed functions whose own source holds the text), the number
of functions listed, and for the negative items whether the pack lists any function at all (it should list none).

  python bench/quality/qb5_error.py [--project .] [--limit N]"""
from __future__ import annotations

import ast
import re
import statistics as st
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
NEGATIVE = ["quantum flux capacitor misaligned during warp", "the frobnicator refused to initialise today",
            "unexpected zeppelin in the data pipeline", "cannot reticulate splines for this tenant", "orbital banana overflow in the cache layer"]


def literal_runs(node: ast.AST) -> list[str]:
    """The literal text runs of an exception message, in order (an f-string's variable parts split them)."""
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return [node.value]
    if isinstance(node, ast.JoinedStr):
        return [v.value for v in node.values if isinstance(v, ast.Constant) and isinstance(v.value, str)]
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Add):
        return literal_runs(node.left) + literal_runs(node.right)
    return []


def items(project: Path, limit: int | None) -> list[dict]:
    out, seen = [], set()
    for f in sorted((project / "devkb").glob("*.py")):
        try:
            tree = ast.parse(f.read_text())
        except SyntaxError:
            continue
        for fn in ast.walk(tree):
            if not isinstance(fn, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            for n in ast.walk(fn):
                if isinstance(n, ast.Raise) and isinstance(n.exc, ast.Call) and n.exc.args:
                    runs = [r.strip() for r in literal_runs(n.exc.args[0]) if r.strip()]
                    text = runs[0] if runs else ""
                    if len(text.split()) >= 3 and text.lower() not in seen:
                        seen.add(text.lower())
                        out.append({"text": text[:90], "file": f"devkb/{f.name}", "fn": fn.name})
    return out[:limit] if limit else out


def listed(project: Path, text: str) -> list[tuple[str, str]]:
    """[(file, function)] under `## Raised by` in `pack error TEXT`."""
    p = subprocess.run([sys.executable, "-c", "import sys; from devkb.cli import main; sys.argv[0]='devkb'; sys.exit(main())", "pack", "--project", str(project), "error", text],
                       capture_output=True, text=True, cwd=ROOT, timeout=120)
    sec = p.stdout.split("## Raised by", 1)[-1].split("\n## ", 1)[0] if "## Raised by" in p.stdout else ""
    return [(m[1], m[2]) for m in re.finditer(r"^- `([^`:]+)::([^`]+)`", sec, re.M)]


def holds(project: Path, rel: str, qual: str, text: str) -> bool:
    """Does the function's own source contain the message text (as literal words)?"""
    try:
        tree = ast.parse((project / rel).read_text())
    except (OSError, SyntaxError):
        return False
    want = " ".join(re.findall(r"[a-z0-9']+", text.lower()))
    parts = qual.split(".")
    for fn in ast.walk(tree):
        if isinstance(fn, (ast.FunctionDef, ast.AsyncFunctionDef)) and fn.name == parts[-1]:
            src = " ".join(re.findall(r"[a-z0-9']+", (ast.get_source_segment((project / rel).read_text(), fn) or "").lower()))
            if want in src:
                return True
    return False


def main(a: list[str]) -> None:
    project = Path(a[a.index("--project") + 1]).resolve() if "--project" in a else ROOT
    its = items(project, int(a[a.index("--limit") + 1]) if "--limit" in a else None)
    rec, prec, size, perfect = [], [], [], 0
    for it in its:
        got = listed(project, it["text"])
        hit = any(f == it["file"] and q.split(".")[-1] == it["fn"] for f, q in got)
        ok = [holds(project, f, q, it["text"]) for f, q in got]
        rec.append(1.0 if hit else 0.0)
        prec.append(sum(ok) / len(ok) if ok else 1.0)           # silence is not a wrong answer here; recall counts it
        size.append(len(got))
        perfect += bool(hit and all(ok))
    neg = [len(listed(project, t)) for t in NEGATIVE]
    n = len(its)
    print(f"{n} messages from devkb's own raise sites; {len(NEGATIVE)} made-up ones\n")
    print("| measure | value |\n|---|---|")
    print(f"| the raiser is listed (recall) | {st.mean(rec):.2f} ({int(sum(rec))}/{n}) |")
    print(f"| listed functions that hold the text (precision) | {st.mean(prec):.2f} |")
    print(f"| items answered exactly (raiser listed, nothing else) | {perfect}/{n} |")
    print(f"| functions listed per message, median / max | {st.median(size):.0f} / {max(size)} |")
    print(f"| made-up messages with at least one function listed (should be 0) | {sum(1 for x in neg if x)}/{len(NEGATIVE)} (listed {neg}) |")


if __name__ == "__main__":
    main(sys.argv[1:])
