"""#340: an agent's checkout is not inside the repository that holds the harness, and a change to that repository during a run is flagged contaminated. Black box on policybench._run_one."""
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

root = Path(pb.__file__).resolve().parents[2]
res = {}
import shutil
got, msg, end = capture("main", keep_b=True)          # the harness's own work directory, not a temporary one
cwd = Path(got["cwd"]).resolve()
for junk in list((pb.B / "runs").glob("p9999-*")) + list((pb.B / "work").glob("p9999-*")):
    shutil.rmtree(junk, ignore_errors=True)
res["checkout_outside_the_harness_repository"] = root not in cwd.parents and cwd != root
# a stray write into the harness repository during the run (what three agents did)
marker = root / "bench" / "policy" / ".stray-write-by-the-agent-340"
def run_that_writes(cmd, *a, **k):
    if cmd and cmd[0] == "claude":
        marker.write_text("x")
        return subprocess.CompletedProcess(cmd, 0)
    return real(cmd, *a, **k)
real = subprocess.run
try:
    pb_run = subprocess.run
    td = tempfile.mkdtemp(); pb.B = Path(td)
    def fake_from_template(t, w):
        Path(w).mkdir(parents=True, exist_ok=True); (Path(w) / ".bench-arm.json").write_text("{}")
    pb.template_for = lambda a: Path(td) / "t"; pb.from_template = fake_from_template; pb.score_run = lambda *a, **k: None
    pb.toolenv.build = lambda ref: {"bin": str(Path(td) / "bin" / "devkb"), "commit": "x", "hook_sha": "x"}
    sb.sh = lambda cmd, **kw: subprocess.CompletedProcess(cmd, 0, json.dumps({"title": "T", "body": "b"}), "") if cmd[:2] == ["gh", "issue"] else subprocess.run(cmd, check=True, capture_output=True, text=True, **kw)
    pb.subprocess.run = run_that_writes
    msg2 = pb._run_one("9999", "main", 1)
    end2 = (pb.B / "runs" / "p9999-main-r1" / "end")
    text = (msg2 + (end2.read_text() if end2.exists() else "")).lower()
    res["a_stray_write_is_flagged"] = "contaminat" in text
finally:
    pb.subprocess.run = real
    marker.unlink(missing_ok=True)
res["pass"] = all(res.values())
print(json.dumps(res))
