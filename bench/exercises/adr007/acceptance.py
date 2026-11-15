#!/usr/bin/env python3
"""Acceptance check for ADR-DEVKB-007, written before either implementation run and applied unchanged to both.

  python3 acceptance.py BRANCH_DIR OUT.json

It judges only what the ADR specifies (node types, verbs, natural keys, flags, files written), never an
implementation's internal names, so two different designs are measured by the same rule. Ground truth for pull
requests and issues comes from the GitHub API (`gh api`), which neither implementation's offline layer may read.

  A tests        the branch's full test suite
  B schema       PullRequest in NODE_TYPES; MERGES and CLOSES in VERBS
  C offline      builds lattice-scan, Mealie, Dispatch at their pinned commits with no network allowed (strace counts
                 connect() calls); PR-<n> keys; MERGES precision against the API on a seeded sample of 25 pull
                 requests per repository; recall of merged pull requests on lattice-scan
  D privacy      no e-mail address, pull request author login or description text anywhere in .devkb/
  E online       the opt-in GitHub layer on lattice-scan and Mealie: GH-<n> issue tickets, CLOSES precision against
                 GitHub's closing record, and a cached second build
  F pack         `devkb pack pr N` exists and names the pull request's commit
  G regression   the benchmark registry's pack check still scores 1.0 (lattice-scan, Mealie, Dispatch, lnbits)
"""
from __future__ import annotations

import json
import os
import random
import re
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

WORK = Path("bench-work")
REPOS = {"lattice-scan": "namiq-ai/lattice-scan", "mealie": "mealie-recipes/mealie", "dispatch": "Netflix/dispatch"}
SAMPLE = 25
EMAIL = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")


def sh(cmd, cwd=None, env=None, timeout=3600):
    return subprocess.run(cmd, cwd=cwd, env=env, capture_output=True, text=True, timeout=timeout)


def gh(path: str):
    r = sh(["gh", "api", path])
    return json.loads(r.stdout) if r.returncode == 0 else None


def load(graph: Path):
    nodes = [json.loads(x) for x in (graph / "nodes.jsonl").read_text().splitlines() if x.strip()]
    edges = [json.loads(x) for x in (graph / "edges.jsonl").read_text().splitlines() if x.strip()]
    return nodes, edges


def offline_env(tmp: Path) -> dict:
    env = {k: v for k, v in os.environ.items() if k not in ("GITHUB_TOKEN", "GH_TOKEN")}
    env.update({"GH_CONFIG_DIR": str(tmp / "no-gh"), "HTTPS_PROXY": "http://127.0.0.1:9", "HTTP_PROXY": "http://127.0.0.1:9",
                "ALL_PROXY": "http://127.0.0.1:9"})
    return env


def build(branch: Path, checkout: Path, out: Path, env: dict, extra: list[str] = (), trace: Path | None = None):
    py = branch / ".venv" / "bin" / "python"
    cmd = [str(py), "-m", "devkb.cli", "build", "--project", str(checkout), *extra]
    if trace:
        cmd = ["strace", "-f", "-qq", "-e", "trace=connect", "-o", str(trace), *cmd]
    t0 = time.time()
    r = sh(cmd, cwd=branch, env={**env, "DEVKB_DIR": str(out)})
    return r.returncode, round(time.time() - t0, 1), (r.stderr or r.stdout)[-1500:]


def net_connects(trace: Path) -> int:
    if not trace.exists():
        return -1
    n = 0
    for line in trace.read_text().splitlines():
        if "AF_INET" in line and "127.0.0.1" not in line and "::1" not in line:
            n += 1  # includes DNS to the local resolver stub (127.0.0.53): an attempt to reach the network
    return n


def pr_nodes(nodes):
    return {n["natural_key"]: n for n in nodes if n["type"] == "PullRequest"}


def keyed(nodes):
    return {n["uid"]: n for n in nodes}


def merges(nodes, edges):
    by = keyed(nodes)
    out: dict[str, set[str]] = {}
    for e in edges:
        if e["verb"] == "MERGES" and e["from_uid"] in by and e["to_uid"] in by:
            out.setdefault(by[e["from_uid"]]["natural_key"], set()).add(by[e["to_uid"]]["natural_key"])
    return out


def check_offline(branch: Path, tmp: Path, res: dict):
    res["offline"] = {}
    rnd = random.Random(7)
    for rid, slug in REPOS.items():
        r: dict = {}
        res["offline"][rid] = r
        out, trace = tmp / f"off-{rid}", tmp / f"strace-{rid}.txt"
        code, secs, log = build(branch, WORK / rid / "checkout", out, offline_env(tmp), trace=trace)
        r.update({"exit": code, "secs": secs, "network_connects": net_connects(trace)})
        if code != 0:
            r["log"] = log
            continue
        nodes, edges = load(out)
        prs, m = pr_nodes(nodes), merges(nodes, edges)
        r["pull_requests"] = len(prs)
        r["merges_edges"] = sum(len(v) for v in m.values())
        r["keys_ok"] = all(re.fullmatch(r"(?:[A-Z]+:)?PR-\d+", k) for k in prs)
        r["closes_edges"] = sum(1 for e in edges if e["verb"] == "CLOSES")
        sample = rnd.sample(sorted(m), min(SAMPLE, len(m)))
        good = total = 0
        wrong = []
        for key in sample:
            num = int(key.rsplit("-", 1)[1])
            pr = gh(f"repos/{slug}/pulls/{num}")
            if pr:
                res.setdefault("_pr_meta", []).append({"login": (pr.get("user") or {}).get("login"), "body": (pr.get("body") or "")[:60]})
            commits = gh(f"repos/{slug}/pulls/{num}/commits?per_page=100") or []
            truth = {c["sha"] for c in commits} | ({pr["merge_commit_sha"]} if pr and pr.get("merge_commit_sha") else set())
            for sha in m[key]:
                total += 1
                if sha in truth:
                    good += 1
                else:
                    wrong.append(f"{key}->{sha[:10]}")
        r["merges_precision"] = round(good / total, 4) if total else None
        r["merges_checked"] = total
        r["merges_wrong"] = wrong[:10]
        if rid == "lattice-scan":
            head = sh(["git", "rev-parse", "HEAD"], cwd=WORK / rid / "checkout").stdout.strip()
            merged = []
            for page in range(1, 6):
                batch = gh(f"repos/{slug}/pulls?state=closed&per_page=100&page={page}") or []
                merged += [p for p in batch if p.get("merged_at") and p.get("merge_commit_sha")]
                if len(batch) < 100:
                    break
            inside = [p for p in merged if sh(["git", "merge-base", "--is-ancestor", p["merge_commit_sha"], head],
                                              cwd=WORK / rid / "checkout").returncode == 0]
            found = [p for p in inside if any(k.endswith(f"PR-{p['number']}") for k in m)]
            r["recall_merged_prs"] = round(len(found) / len(inside), 4) if inside else None
            r["recall_denominator"] = len(inside)
            res.setdefault("_pr_meta", []).extend({"login": (p.get("user") or {}).get("login"),
                                                   "body": (p.get("body") or "")[:60]} for p in inside)


PRE_EXISTING = {"nodes.jsonl", "edges.jsonl", "symbols-nodes.jsonl", "symbols-edges.jsonl", "symbols-manifest.json",
                "manifest.json"}


def check_privacy(graphs: list[Path], res: dict):
    """Only what ADR-DEVKB-007 adds is judged: PullRequest nodes, GH-<n> issue tickets, MERGES/CLOSES edges, and any
    file the graph folder did not have before (a GitHub cache). Commit subjects and source text were in the graph
    before the ADR and are out of its scope."""
    meta = res.get("_pr_meta", [])
    logins = {p["login"] for p in meta if p.get("login")}
    bodies = [p["body"].strip() for p in meta if len(p["body"].strip()) >= 30]
    found = {"emails": [], "logins": [], "bodies": []}

    def scan(label: str, text: str):
        found["emails"] += [f"{label}: {x}" for x in EMAIL.findall(text)][:3]
        found["logins"] += [f"{label}: {x}" for x in logins if f'"{x}"' in text][:3]
        found["bodies"] += [f"{label}: {b[:30]}" for b in bodies if b[:30] in text][:3]

    for g in graphs:
        if not (g / "nodes.jsonl").exists():
            continue
        nodes, edges = load(g)
        new = [n for n in nodes if n["type"] == "PullRequest"
               or (n["type"] == "Ticket" and re.fullmatch(r"(?:[A-Z]+:)?GH-\d+", n["natural_key"]))]
        scan(f"{g.name}/new-nodes", json.dumps(new))
        scan(f"{g.name}/new-edges", json.dumps([e for e in edges if e["verb"] in ("MERGES", "CLOSES")]))
        for f in g.rglob("*"):
            if f.is_file() and f.relative_to(g).as_posix() not in PRE_EXISTING:
                scan(f"{g.name}/{f.relative_to(g)}", f.read_text(errors="replace"))
    res["privacy"] = {k: v[:10] for k, v in found.items()}
    res["privacy"]["ok"] = not any(found.values())
    res["privacy"]["checked_logins"], res["privacy"]["checked_bodies"] = len(logins), len(bodies)


def online_build(branch: Path, checkout: Path, out: Path):
    """The ADR names two switches: `devkb build --github`, or `{"github": {"enabled": true}}` in devkb.json."""
    env = {**os.environ, "GITHUB_TOKEN": sh(["gh", "auth", "token"]).stdout.strip()}
    code, secs, log = build(branch, checkout, out, env, extra=["--github"])
    how = "--github"
    if code != 0:
        cfg = checkout / "devkb.json"
        had = cfg.exists()
        old = cfg.read_text() if had else None
        cfg.write_text(json.dumps({"github": {"enabled": True}}))
        try:
            code, secs, log = build(branch, checkout, out, env)
            how = "devkb.json"
        finally:
            cfg.write_text(old) if had else cfg.unlink()
    return code, secs, log, how


def check_online(branch: Path, tmp: Path, res: dict):
    res["online"] = {}
    for rid in ("lattice-scan", "mealie"):
        slug = REPOS[rid]
        r: dict = {}
        res["online"][rid] = r
        src = WORK / rid / "checkout"
        checkout = tmp / f"co-{rid}"
        sh(["git", "clone", "-q", "--shared", str(src), str(checkout)])
        sh(["git", "checkout", "-q", sh(["git", "rev-parse", "HEAD"], cwd=src).stdout.strip()], cwd=checkout)
        sh(["git", "remote", "set-url", "origin", f"https://github.com/{slug}.git"], cwd=checkout)
        out = tmp / f"on-{rid}"
        code, secs, log, how = online_build(branch, checkout, out)
        r.update({"exit": code, "secs": secs, "switch": how})
        if code != 0:
            r["log"] = log
            continue
        code2, secs2, _l, _h = online_build(branch, checkout, out)
        r["second_build_secs"] = secs2
        nodes, edges = load(out)
        by = keyed(nodes)
        tickets = [n for n in nodes if n["type"] == "Ticket" and re.fullmatch(r"(?:[A-Z]+:)?GH-\d+", n["natural_key"])]
        r["issue_tickets"] = len(tickets)
        r["ticket_types"] = sorted({(n["properties"].get("ticket_type") or "") for n in tickets})[:10]
        closes = [(by[e["from_uid"]]["natural_key"], by[e["to_uid"]]["natural_key"]) for e in edges
                  if e["verb"] == "CLOSES" and e["from_uid"] in by and e["to_uid"] in by]
        r["closes_edges"] = len(closes)
        r["pull_requests"] = len(pr_nodes(nodes))
        owner, name = slug.split("/")
        good = total = 0
        wrong = []
        for pr_key, issue_key in random.Random(7).sample(closes, min(SAMPLE, len(closes))):
            num, iss = int(pr_key.rsplit("-", 1)[1]), int(issue_key.rsplit("-", 1)[1])
            q = ('query{repository(owner:"%s",name:"%s"){pullRequest(number:%d){closingIssuesReferences(first:50)'
                 '{nodes{number}}}}}' % (owner, name, num))
            data = json.loads(sh(["gh", "api", "graphql", "-f", f"query={q}"]).stdout or "{}")
            refs = {n["number"] for n in ((((data.get("data") or {}).get("repository") or {}).get("pullRequest") or {})
                                          .get("closingIssuesReferences") or {}).get("nodes", [])}
            total += 1
            if iss in refs:
                good += 1
            else:
                wrong.append(f"{pr_key}->{issue_key}")
        r["closes_precision"] = round(good / total, 4) if total else None
        r["closes_checked"] = total
        r["closes_wrong"] = wrong[:10]
        res.setdefault("_online_graphs", []).append(str(out))


def check_pack(branch: Path, tmp: Path, res: dict):
    py = branch / ".venv" / "bin" / "python"
    graph = tmp / "off-lattice-scan"
    nodes, edges = load(graph) if graph.exists() else ([], [])
    m = merges(nodes, edges)
    if not m:
        res["pack"] = {"ok": False, "why": "no MERGES edges to pick a pull request from"}
        return
    key = sorted(m, key=lambda k: int(k.rsplit("-", 1)[1]))[-1]
    num = key.rsplit("-", 1)[1]
    r = sh([str(py), "-m", "devkb.cli", "pack", "--project", str(WORK / "lattice-scan" / "checkout"), "pr", num],
           cwd=branch, env={**offline_env(tmp), "DEVKB_DIR": str(graph)})
    text = r.stdout
    res["pack"] = {"exit": r.returncode, "pr": key, "words": len(text.split()),
                   "names_a_commit": any(sha[:7] in text for sha in m[key]), "head": text[:400]}
    res["pack"]["ok"] = r.returncode == 0 and res["pack"]["names_a_commit"]


def check_regression(branch: Path, tmp: Path, res: dict):
    """The registry's free stage with the branch's code, on local clones of the pinned checkouts (no network)."""
    py = branch / ".venv" / "bin" / "python"
    res["regression"] = {}
    for rid in ("lattice-scan", "mealie", "dispatch", "lnbits"):
        co = tmp / "bench" / rid / "checkout"
        sh(["git", "clone", "-q", "--shared", "--no-checkout", str(WORK / rid / "checkout"), str(co)])
        r = sh([str(py), "-m", "devkb.bench.pipeline", "prepare", rid, "--work", str(tmp / "bench")], cwd=branch,
               env=offline_env(tmp), timeout=3600)
        f = tmp / "bench" / rid / "pack-check.json"
        res["regression"][rid] = json.loads(f.read_text())["summary"]["mean_score"] if f.exists() else f"failed: {r.stderr[-300:]}"


def main() -> int:
    branch, out = Path(sys.argv[1]).resolve(), Path(sys.argv[2])
    res: dict = {"branch": str(branch), "commit": sh(["git", "rev-parse", "HEAD"], cwd=branch).stdout.strip()}
    tmp = Path(tempfile.mkdtemp(prefix="adr007-eval-"))
    py = branch / ".venv" / "bin" / "python"
    t = sh([str(py), "-m", "pytest", "tests", "-q", "-p", "no:cacheprovider"], cwd=branch, timeout=3600)
    tail = (t.stdout.strip().splitlines() or [""])[-1]
    res["tests"] = {"exit": t.returncode, "summary": tail}
    s = sh([str(py), "-c", "from devkb.model import NODE_TYPES, VERBS; import json; "
            "print(json.dumps(['PullRequest' in NODE_TYPES, 'MERGES' in VERBS, 'CLOSES' in VERBS]))"], cwd=branch)
    res["schema"] = json.loads(s.stdout) if s.returncode == 0 else s.stderr[-300:]
    for name, fn in (("offline", check_offline), ("online", check_online), ("pack", check_pack),
                     ("regression", check_regression)):
        try:
            fn(branch, tmp, res)
        except Exception as exc:  # a failing check is a result, not a crash
            res[f"{name}_error"] = f"{type(exc).__name__}: {exc}"
    check_privacy([tmp / f"off-{r}" for r in REPOS] + [Path(p) for p in res.pop("_online_graphs", [])], res)
    res.pop("_pr_meta", None)
    diff = sh(["git", "diff", "--shortstat", "c772e17" if "devkb" in branch.name else "53ebb83", "HEAD", "--", ".",
               ":(exclude)AGENTS.md", ":(exclude)CLAUDE.md", ":(exclude).mcp.json", ":(exclude).gitignore"], cwd=branch)
    res["diff"] = diff.stdout.strip()
    Path(out).write_text(json.dumps(res, indent=1))
    shutil.rmtree(tmp, ignore_errors=True)
    print(json.dumps(res, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
