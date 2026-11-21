"""#335: a devkb-arm agent may run .venv/bin/devkb (the command the checkout's policy prescribes) and the no-devkb arm may not.
Black box on the allowed and disallowed tool lists policybench._run_one gives claude."""
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
    pb.template_for = lambda a, issue=None: Path(td) / "t"
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

def covers(patterns, command):
    for p in patterns:
        m = re.fullmatch(r"Bash\((.*?)(:\*|\s\*|)\)", p)
        if m and command.startswith(m.group(1)):
            return True
    return False


res = {}
cmd = ".venv/bin/devkb pack --project . file x.py"
got, _, _ = capture("main")
res["devkb_arm_may_run_venv_devkb"] = covers(flag(got["cmd"], "--allowedTools"), cmd) and not covers(flag(got["cmd"], "--disallowedTools"), cmd)
res["devkb_arm_may_still_run_path_devkb"] = covers(flag(got["cmd"], "--allowedTools"), "devkb pack --project . file x.py")
got, _, _ = capture("none")
res["none_arm_may_not_run_venv_devkb"] = covers(flag(got["cmd"], "--disallowedTools"), cmd) or not covers(flag(got["cmd"], "--allowedTools"), cmd)
res["none_arm_may_not_run_path_devkb"] = covers(flag(got["cmd"], "--disallowedTools"), "devkb pack --project . file x.py")
res["pass"] = all(res.values())
print(json.dumps(res))
