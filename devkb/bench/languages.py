"""Dogfood check for every language beyond Python (bench/languages.yaml).

  python -m devkb.bench.languages list
  python -m devkb.bench.languages check [LANGUAGE] [--work DIR]

For each repository: a shallow fetch of the pinned commit, `devkb build` into a scratch graph, then counts of the
language's Symbol nodes (by their `source`), CALLS edges between them, and TestCase nodes in its test files, against
the minimums in the file. Exit 1 if any falls short, so CI catches a regression in a language's extractor.
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
REGISTRY = ROOT / "bench" / "languages.yaml"


def counts(graph: Path, source: str) -> dict[str, int]:
    nodes = [json.loads(line) for line in (graph / "nodes.jsonl").read_text().splitlines() if line.strip()]
    lang = {n["uid"] for n in nodes if n["type"] == "Symbol" and n.get("source") == source}
    edges = [json.loads(line) for line in (graph / "edges.jsonl").read_text().splitlines() if line.strip()]
    return {"symbols": len(lang),
            "calls": sum(1 for e in edges if e["verb"] == "CALLS" and e["from_uid"] in lang and e["to_uid"] in lang),
            "tests": sum(1 for n in nodes if n["type"] == "TestCase")}


def check_repo(lang: str, cfg: dict, repo: dict, work: Path) -> tuple[bool, dict]:
    checkout = work / lang / repo["id"]
    if not (checkout / ".git").exists():
        checkout.mkdir(parents=True, exist_ok=True)
        subprocess.run(["git", "init", "-q", str(checkout)], check=True)
        subprocess.run(["git", "remote", "add", "origin", repo["url"]], cwd=checkout, check=True)
    subprocess.run(["git", "fetch", "-q", "--depth", "1", "origin", repo["commit"]], cwd=checkout, check=True)
    subprocess.run(["git", "checkout", "-q", "--force", repo["commit"]], cwd=checkout, check=True)
    graph = work / lang / f"{repo['id']}-graph"
    env = {**os.environ, "DEVKB_DIR": str(graph)}
    subprocess.run([sys.executable, "-m", "devkb.cli", "build", "--project", str(checkout)], env=env, check=True,
                   cwd=ROOT, stdout=subprocess.DEVNULL)
    got = counts(graph, cfg["source"])
    ok = all(got[k] >= repo[f"min_{k}"] for k in ("symbols", "calls", "tests"))
    return ok, got


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("command", choices=("list", "check"))
    ap.add_argument("language", nargs="?")
    ap.add_argument("--work", default=os.environ.get("BENCH_WORK", "bench-work/languages"))
    a = ap.parse_args()
    reg = yaml.safe_load(REGISTRY.read_text())["languages"]
    langs = {a.language: reg[a.language]} if a.language else reg
    failed = False
    for lang, cfg in langs.items():
        if len(cfg["repos"]) < 3:
            print(f"{lang}: {len(cfg['repos'])} repositories; the rule is at least 3", file=sys.stderr)
            failed = True
        for repo in cfg["repos"]:
            if a.command == "list":
                print(f"{lang:8s} {repo['id']:18s} {repo['commit'][:10]} {repo['url']}")
                continue
            ok, got = check_repo(lang, cfg, repo, Path(a.work).resolve())
            mins = {k: repo[f"min_{k}"] for k in ("symbols", "calls", "tests")}
            print(f"{'ok  ' if ok else 'FAIL'} {lang} {repo['id']}: {got} (minimum {mins})")
            failed |= not ok
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
