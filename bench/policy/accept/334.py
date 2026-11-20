"""#334: no arm's agent environment leaves the Bash tool's 120 s default timeout in force: BASH_DEFAULT_TIMEOUT_MS and BASH_MAX_TIMEOUT_MS are set (at least 300000) for every arm. Black box on policybench._run_one."""
import importlib, json, os, re, subprocess, sys, tempfile
from pathlib import Path

W = Path(sys.argv[1]).resolve()
sys.path.insert(0, str(W / "bench" / "policy"))
pb = importlib.import_module("policybench")
sb = pb.sb
cap = {}


def capture(arm, body="The ticket body.", keep_b=False):
    """_run_one with the setup, gh, claude and scoring stubbed; returns (what claude was given, the message, the end file)."""
    td = tempfile.mkdtemp()
    if not keep_b:
        pb.B = Path(td)
    tag = f"p9999-{arm}-r1"
    def fake_from_template(t, w):
        Path(w).mkdir(parents=True, exist_ok=True)
        (Path(w) / ".bench-arm.json").write_text("{}")
    real_run, real_sh = subprocess.run, sb.sh
    pb.template_for = lambda a: Path(td) / "t"
    pb.from_template = fake_from_template
    pb.toolenv.build = lambda ref: {"bin": str(Path(td) / "bin" / "devkb"), "commit": "x", "hook_sha": "x"}
    pb.score_run = lambda *a, **k: None
    sb.sh = lambda cmd, **kw: subprocess.CompletedProcess(cmd, 0, json.dumps({"title": "T", "body": body}), "") if cmd[:2] == ["gh", "issue"] else real_sh(cmd, **kw)
    got = {}
    def fake_run(cmd, *a, **k):
        if cmd and cmd[0] == "claude":
            got.update(cmd=cmd, env=k.get("env") or {}, cwd=k.get("cwd"))
            return subprocess.CompletedProcess(cmd, 0)
        return real_run(cmd, *a, **k)
    pb.subprocess.run = fake_run
    try:
        msg = pb._run_one("9999", arm, 1)
    finally:
        pb.subprocess.run, sb.sh = real_run, real_sh
    end = (pb.B / "runs" / tag / "end")
    return got, msg, end.read_text() if end.exists() else ""


def flag(cmd, name):
    """The values after --name up to the next --option."""
    i = cmd.index(name); out = []
    for x in cmd[i + 1:]:
        if x.startswith("--"):
            break
        out.append(x)
    return out

res = {}
for arm in ("none", "main"):
    got, msg, end = capture(arm)
    env = got.get("env", {})
    d, m = env.get("BASH_DEFAULT_TIMEOUT_MS", ""), env.get("BASH_MAX_TIMEOUT_MS", "")
    res[f"{arm}_default_timeout_raised"] = d.isdigit() and int(d) >= 300000
    res[f"{arm}_max_not_below_default"] = m.isdigit() and d.isdigit() and int(m) >= int(d)
res["pass"] = all(res.values())
print(json.dumps(res))
