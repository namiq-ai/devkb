"""#448: `uses` loads with the prompt in every toolset that serves it, no other tool gains the mark, and the toolsets without `uses` are as before.
Black box: the checkout's own MCP server over stdio (`devkb mcp --toolset T`, initialize, tools/list); prints one JSON line."""
import json, os, subprocess, sys, tempfile
from pathlib import Path

W = Path(sys.argv[1]).resolve()
SHARED = Path("/home/namiq/orchestra/devkb/.venv/bin/python")
py = str(W / ".venv/bin/python") if (W / ".venv/bin/python").exists() else (str(SHARED) if SHARED.exists() else sys.executable)
MARK = "anthropic/alwaysLoad"
LEAN = {"rca_trace", "impact", "callers", "tests_for", "tests_to_run", "review_pack", "config"}
NAV = {"symbol", "outline", "pack"}
READ = {"symbol", "outline", "uses", "search_docs"}
ALL_FOUR = {"symbol", "outline", "pack", "uses"}


def tools(toolset: str, project: str) -> dict:
    """name -> tool definition, as a client receives it."""
    env = dict(os.environ, PYTHONPATH=str(W), PYTHONWARNINGS="ignore")
    p = subprocess.Popen([py, "-m", "devkb.cli", "mcp", "--project", project, "--toolset", toolset], cwd=project, env=env,
                         stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)

    def send(msg):
        p.stdin.write(json.dumps(msg) + "\n")
        p.stdin.flush()

    def reply(i):
        for line in p.stdout:
            if line.startswith("{"):
                d = json.loads(line)
                if d.get("id") == i:
                    return d
        raise RuntimeError("server closed: " + p.stderr.read()[-400:])

    try:
        send({"jsonrpc": "2.0", "id": 1, "method": "initialize",
              "params": {"protocolVersion": "2025-06-18", "capabilities": {}, "clientInfo": {"name": "accept", "version": "1"}}})
        reply(1)
        send({"jsonrpc": "2.0", "method": "notifications/initialized"})
        send({"jsonrpc": "2.0", "id": 2, "method": "tools/list"})
        return {t["name"]: t for t in reply(2)["result"]["tools"]}
    finally:
        p.kill()
        p.wait()


res, detail = {}, {}
with tempfile.TemporaryDirectory() as td:
    try:
        got = {s: tools(s, td) for s in ("lean-pack", "dev", "all", "nav", "lean", "core", "workflow", "docs")}
        marked = {s: {n for n, t in ts.items() if (t.get("_meta") or {}).get(MARK) is True} for s, ts in got.items()}
        for s in ("lean-pack", "dev", "all"):
            res[f"{s}: uses served and marked"] = "uses" in got[s] and "uses" in marked[s]
        for s, ts in got.items():
            res[f"{s}: marks are exactly the four served"] = marked[s] == ALL_FOUR & set(ts)
        res["callers is not marked"] = not any("callers" in m for m in marked.values())
        res["nav serves the same tools"] = set(got["nav"]) == NAV
        res["lean serves the same tools"] = set(got["lean"]) == LEAN
        res["lean-pack serves the same tools"] = set(got["lean-pack"]) == LEAN | {"pack"} | READ
        detail = {s: sorted(m) for s, m in marked.items()}
    except Exception as e:  # noqa: BLE001
        res["server"] = False
        detail = {"error": f"{type(e).__name__}: {e}"[-600:]}
print(json.dumps({"pass": bool(res) and all(res.values()), "checks": res, "detail": detail}))
