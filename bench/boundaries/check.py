#!/usr/bin/env python3
"""Python-and-C (and C++-and-C) boundary check against a labelled truth (SPEC-DKB-002 story 7). Standard library only.

  check.py FIXTURES_DIR [--built DIR]

`FIXTURES_DIR/truth.json` labels every boundary fixture: each true edge `{caller, callee, mechanism}` and each negative
case (`ambiguous`, `not-a-handle`, `static`, `not-in-repository`, `lambda`, `overload`: no edge may leave the caller;
`dynamic`: the symbol must carry the reason `dynamic-import`). For each fixture the check builds the graph in a scratch
repository through `devkb build` (or reads `DIR/<fixture>/.devkb` when `--built DIR` is given) and reads only
`nodes.jsonl` and `edges.jsonl`: it shares no code with the extractors. It prints precision and recall per mechanism.
Exit 0 only if precision is 1.0 for every mechanism, every negative produced no edge and every dynamic case is counted.
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

MECHANISMS = ("extern-c", "ctypes", "cffi", "pyc-api", "pybind11")
ROOT = Path(__file__).resolve().parents[2]


def build(fixture: Path, scratch: Path) -> Path:
    repo = scratch / fixture.name
    shutil.copytree(fixture, repo)
    for cmd in (["init", "-q"], ["add", "-A"], ["-c", "user.email=t@example.com", "-c", "user.name=T", "commit", "-qm", "x"]):
        subprocess.run(["git", *cmd], cwd=repo, check=True, capture_output=True)
    env = {**os.environ, "PYTHONPATH": str(ROOT)}
    done = subprocess.run([sys.executable, "-m", "devkb.cli", "build", "--project", str(repo)], env=env, capture_output=True, text=True)
    if done.returncode != 0 or not (repo / ".devkb" / "edges.jsonl").exists():
        raise SystemExit(f"build of {fixture.name} failed: {done.stderr[-300:]}")
    return repo / ".devkb"


def read(store: Path):
    keys, reasons = {}, {}
    for line in (store / "nodes.jsonl").read_text().splitlines():
        n = json.loads(line)
        keys[n["uid"]] = n["natural_key"]
        if n["type"] == "Symbol":
            reasons[n["natural_key"]] = n["properties"].get("incomplete_reasons") or []
    edges = set()
    for line in (store / "edges.jsonl").read_text().splitlines():
        e = json.loads(line)
        if e["verb"] == "CALLS" and e["properties"].get("source") in MECHANISMS:
            edges.add((keys.get(e["from_uid"]), keys.get(e["to_uid"]), e["properties"]["source"]))
    return edges, reasons


def main(argv: list[str]) -> int:
    fixtures = Path(argv[0]).resolve()
    built = Path(argv[argv.index("--built") + 1]).resolve() if "--built" in argv else None
    truth = json.loads((fixtures / "truth.json").read_text())["fixtures"]
    tp = {m: 0 for m in MECHANISMS}
    fp = {m: 0 for m in MECHANISMS}
    fn = {m: 0 for m in MECHANISMS}
    problems: list[str] = []
    with tempfile.TemporaryDirectory() as tmp:
        for name, labels in sorted(truth.items()):
            store = (built / name / ".devkb") if built else build(fixtures / name, Path(tmp))
            edges, reasons = read(store)
            want = {(e["caller"], e["callee"], e["mechanism"]) for e in labels.get("edges", [])}
            for e in sorted(edges - want):
                fp[e[2]] += 1
                problems.append(f"FALSE EDGE {name}: {e[0]} -> {e[1]} via {e[2]} is not in the truth")
            for e in sorted(want - edges):
                fn[e[2]] += 1
                problems.append(f"MISSED EDGE {name}: {e[0]} -> {e[1]} via {e[2]}")
            for e in want & edges:
                tp[e[2]] += 1
            for neg in labels.get("negatives", []):
                if neg["kind"] == "dynamic":
                    if "dynamic-import" not in reasons.get(neg["symbol"], []):
                        problems.append(f"DYNAMIC NOT COUNTED {name}: {neg['symbol']} has no dynamic-import reason")
                elif any(e[0] == neg["caller"] for e in edges - want):
                    problems.append(f"NEGATIVE LINKED {name}: {neg['caller']} ({neg['kind']}) produced an edge")
    for m in MECHANISMS:
        precision = tp[m] / (tp[m] + fp[m]) if tp[m] + fp[m] else 1.0
        recall = tp[m] / (tp[m] + fn[m]) if tp[m] + fn[m] else 1.0
        print(f"{m}: precision {precision:.2f} recall {recall:.2f} ({tp[m]} true, {fp[m]} false, {fn[m]} missed)")
    wrong = [p for p in problems if not p.startswith("MISSED")]
    for p in problems:
        print(p)
    return 1 if wrong or any(fp.values()) else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
