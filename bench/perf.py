#!/usr/bin/env python3
"""Performance of one devkb checkout: graph build (wall time, peak memory, size on disk) and the latency of the command-line
queries, so two versions can be compared on the same repositories for degradation.

  perf.py CODE_DIR LABEL OUT.json NAME=PATH [NAME=PATH ...] [--reps 3] [--queries 5] [--targets targets.json] [--pick]

`--pick` chooses each repository's targets (its most-called function, its largest source file) from the graph this checkout builds
and writes them to --targets; a later run on another version reads the same file, so both measure identical queries.
Run versions one after another, never at the same time: wall times are only comparable on a quiet machine."""
import argparse, json, os, shutil, statistics as st, subprocess, sys, time
from pathlib import Path

PY = os.environ.get("PERF_PYTHON", sys.executable)


def run(code: str, args: list[str], cwd: str | None = None, timeout: int = 1800):
    env = dict(os.environ, PYTHONPATH=code, PYTHONWARNINGS="ignore")
    t0 = time.perf_counter()
    p = subprocess.run(["/usr/bin/time", "-f", "TIME %e %M", PY, "-P", "-m", "devkb.cli", *args], cwd=cwd, env=env,
                       capture_output=True, text=True, timeout=timeout)
    wall = time.perf_counter() - t0
    rss = 0
    for line in p.stderr.splitlines()[::-1]:
        if line.startswith("TIME "):
            rss = int(line.split()[2]); break
    return p.returncode, wall, rss / 1024, p.stdout


def du(path: Path) -> int:
    return sum(f.stat().st_size for f in path.rglob("*") if f.is_file())


def pick(code: str, repo: str) -> dict:
    sys.path.insert(0, code)
    from devkb.process_api import ProcessAPI  # noqa: PLC0415
    import inspect  # noqa: PLC0415
    api = ProcessAPI(repo) if "project" not in inspect.signature(ProcessAPI.__init__).parameters else ProcessAPI(project=repo)
    best = (-1, None)
    for i, k in enumerate(api.idx.keys if hasattr(api, "idx") else []):
        p = api.idx.props[i]
        if p.get("kind") in ("function", "method"):
            n = api._caller_count(i)
            if n > best[0]:
                best = (n, k)
    f, q = best[1].split("::", 1)
    big = max((x for x in subprocess.run(["git", "ls-files"], cwd=repo, capture_output=True, text=True).stdout.split() if x.endswith((".py", ".c", ".cc", ".cpp", ".cs", ".ts", ".js"))),
              key=lambda x: (Path(repo) / x).stat().st_size if (Path(repo) / x).is_file() else 0)
    return {"function": q, "function_file": f, "file": big, "callers": best[0]}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("code"); ap.add_argument("label"); ap.add_argument("out"); ap.add_argument("repos", nargs="+")
    ap.add_argument("--reps", type=int, default=3); ap.add_argument("--queries", type=int, default=5)
    ap.add_argument("--targets", default="targets.json"); ap.add_argument("--pick", action="store_true")
    a = ap.parse_args()
    targets = json.load(open(a.targets)) if Path(a.targets).exists() else {}
    res = {"label": a.label, "code": a.code, "repos": {}}
    for spec in a.repos:
        name, path = spec.split("=", 1); r = {"build": [], "files": int(subprocess.run(["git", "ls-files"], cwd=path, capture_output=True, text=True).stdout.count("\n"))}
        for rep in range(a.reps):
            shutil.rmtree(Path(path) / ".devkb", ignore_errors=True)
            rc, wall, mb, _ = run(a.code, ["build", "--project", path], timeout=3600)
            r["build"].append({"secs": round(wall, 2), "peak_mb": round(mb), "rc": rc})
        r["graph_mb"] = round(du(Path(path) / ".devkb") / 1e6, 1)
        if a.pick or name not in targets:
            targets[name] = pick(a.code, path); json.dump(targets, open(a.targets, "w"), indent=1)
        t = targets[name]; r["targets"] = t; r["queries"] = {}
        qs = {"pack file": ["pack", "--project", path, "file", t["file"]], "pack change": ["pack", "--project", path, "change", t["function"], "--path", t["function_file"]],
              "query about": ["query", "--project", path, "--about", t["function_file"] + "::" + t["function"]]}
        if (Path(a.code) / "devkb" / "read_tools.py").exists():
            qs.update({"symbol": ["symbol", t["function"].rsplit(".", 1)[-1], "--project", path], "outline": ["outline", t["file"], "--project", path],
                       "uses": ["uses", t["function"].rsplit(".", 1)[-1], "--project", path]})
        for qn, args in qs.items():
            ts = []
            for _ in range(a.queries):
                rc, wall, mb, out = run(a.code, args)
                ts.append(wall)
            r["queries"][qn] = {"median_s": round(st.median(ts), 3), "min_s": round(min(ts), 3), "rc": rc, "bytes": len(out), "answered": "cannot resolve" not in out and "\"found\": false" not in out and rc == 0}
        shutil.rmtree(Path(path) / ".devkb", ignore_errors=True)
        res["repos"][name] = r
        json.dump(res, open(a.out, "w"), indent=1)
        print(name, [b["secs"] for b in r["build"]], r["graph_mb"], "MB", {k: v["median_s"] for k, v in r["queries"].items()}, flush=True)


main()
