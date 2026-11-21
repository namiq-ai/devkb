"""#369: which command forms the benchmark's permission settings refuse. One headless `claude -p` per form, with the
benchmark's own --allowedTools/--disallowedTools, permission mode and setting sources, in a scratch checkout.

  python bench/policy/probes/permission_probe.py SCRATCH_CHECKOUT [FORMS.json]   # one JSON line per form (costs money)
"""
import json, subprocess, sys, concurrent.futures as cf
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import storybench as sb
W = Path(sys.argv[1]).resolve()                       # a scratch git checkout with `.venv` linked in
# one form per probe: the forms the 0.2.14 and 0.2.15 runs were refused for, and their allowed neighbours (#369)
FORMS = {
    "cd-abs-and": f"cd {W} && ls", "cd-rel-and": "cd sub && ls", "compound": "ls; ls sub", "pipe": "ls | head -3",
    "heredoc-python": "python3 - <<'E'\nprint(1)\nE", "heredoc-brace-string": "cat > sub/f.py <<'E'\nd = {\"a\": 1}\nE",
    "heredoc-brace-int": "cat > sub/k.py <<'E'\nd = {1: 2}\nE", "echo-redirect": "echo hi > sub/y.txt",
    "sed-i": "sed -i 's/x/y/' sub/z.txt", "var-assign": "R=$PWD; ls $R", "cmd-subst": "ls $(pwd)/sub",
    "subshell": "(cd sub && ls)", "for-loop": "for f in a b; do echo $f; done", "echo-brace": "echo {a,b}",
    "abs-venv": f"{W}/.venv/bin/python -c 'print(1)'", "venv-pipe": ".venv/bin/python -c 'print(1)' 2>&1 | tail -1",
    "ls-parent": "ls ..", "outside-abs": "ls /tmp",
}
if len(sys.argv) > 2:                                 # or a JSON file of {name: command} (e.g. denied commands verbatim)
    FORMS = json.load(open(sys.argv[2]))
PROMPT = ("Run exactly this shell command with the Bash tool, once, unchanged, and then stop. Do not run anything "
          "else and do not explain.\n\n```\n{cmd}\n```")

def one(item):
    name, cmd = item
    p = subprocess.run(["claude", "-p", PROMPT.format(cmd=cmd), "--model", sb.MODEL, "--setting-sources", "project,local",
                        "--output-format", "json", "--max-turns", "3", "--permission-mode", "acceptEdits",
                        "--strict-mcp-config", "--mcp-config", json.dumps({"mcpServers": {}}),
                        "--allowedTools", *sb.ALLOW, "--disallowedTools", *sb.DENY],
                       cwd=W, capture_output=True, text=True, timeout=600)
    try:
        r = json.loads(p.stdout)
    except ValueError:
        return {"form": name, "cmd": cmd, "error": (p.stderr or p.stdout)[-200:]}
    den = r.get("permission_denials", [])
    return {"form": name, "cmd": cmd, "denied": len(den), "denied_cmds": [(d.get("tool_input") or {}).get("command") for d in den],
            "cost": r.get("total_cost_usd")}

if __name__ == "__main__":
    with cf.ThreadPoolExecutor(6) as ex:
        for row in ex.map(one, FORMS.items()):
            print(json.dumps(row), flush=True)
