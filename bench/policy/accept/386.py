"""#386: `without_location` (the location-withheld benchmark arms) never passes a ticket's "where to start" on silently: an inline or unbolded
"Where to start" is withheld, and a body that says it in a form no section catches is refused or warned about. Black box: the checkout's own
`bench/policy/policybench.py`; prints one JSON line."""
import json, subprocess, sys, tempfile
from pathlib import Path

W = Path(sys.argv[1]).resolve()
SHARED = Path("/home/namiq/orchestra/devkb/.venv/bin/python")
py = str(W / ".venv/bin/python") if (W / ".venv/bin/python").exists() else (str(SHARED) if SHARED.exists() else sys.executable)
CASES = {
    "plain_line": "**Expected:** it works.\n\nWhere to start: `foo_bar` in `devkb/x.py`.\n\n**Done when:** the test passes.\n",
    "inline_bold": "**Expected:** ok. **Where to start:** `foo_bar` in `devkb/x.py`.\n\n**Done when:** the test passes.\n",
    "unrecognised_form": "**Expected:** it works.\n\nWHERE TO START - look at foo_bar in devkb/x.py first.\n\n**Done when:** the test passes.\n",
    "normal_section": "**Expected:** it works.\n\n**Where to start:** `foo_bar` in `devkb/x.py`.\n\n**Done when:** the test passes.\n",
}
CODE = r'''
import sys, json
sys.path.insert(0, sys.argv[1] + "/bench/policy")
import policybench as pb
body = sys.stdin.read()
try:
    t, b = pb.without_location("t", body)
    print(json.dumps({"ok": True, "body": b}))
except BaseException as e:
    print(json.dumps({"ok": False, "error": type(e).__name__ + ": " + str(e)[:200]}))
'''
res, detail = {}, {}
for name, body in CASES.items():
    p = subprocess.run([py, "-P", "-c", CODE, str(W)], input=body, capture_output=True, text=True, cwd=tempfile.gettempdir(), timeout=120)
    try:
        r = json.loads(p.stdout.strip().splitlines()[-1])
    except Exception:
        r = {"ok": False, "error": "no result: " + p.stderr[-200:]}
    r["stderr"] = p.stderr
    detail[name] = {k: (v[:200] if isinstance(v, str) else v) for k, v in r.items()}
    leaked = r["ok"] and ("foo_bar" in r["body"] or "devkb/x.py" in r["body"])
    refused = not r["ok"]
    warned = r["ok"] and "where to start" in p.stderr.lower()
    if name == "normal_section":
        res[name] = r["ok"] and not leaked and "**Where to start:** (withheld for this benchmark run)" in r["body"] and "**Done when:** the test passes." in r["body"]
    elif name == "unrecognised_form":
        res[name] = refused or warned or not leaked          # refused, warned about, or the names are gone from the body
        res[name] = refused or warned
    elif name == "plain_line":
        res[name] = (not refused) and not leaked and "(withheld" in r["body"]          # "treated as a section": withheld, not refused
    else:
        res[name] = refused or (not leaked and "(withheld" in r["body"])
print(json.dumps({"results": res, "pass": all(res.values())}))
