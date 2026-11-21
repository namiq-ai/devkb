"""#336: a ticket whose Reproduce section names data absent from the checkout does not send the agent to it unannounced: the prompt either leaves the path out or says the data is not in the checkout; a ticket without such a path is passed unchanged. Black box on the prompt policybench._run_one gives claude."""
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

PATH_ = "bench/results/2026-11-19-audit-0.2.13/runs/aops-main-r1"
body = "**Reproduce:**\n```\nrm -rf audit && cp -r " + PATH_ + " audit && PYTHONPATH=audit .venv/bin/python audit/repro/x.py\n```\n**Expected:**\n- the fix\n"
res = {}
got, _, _ = capture("main", body)
prompt = got["cmd"][2]
says_absent = bool(re.search(r"(not|isn't|is not|aren't) (in this checkout|in the checkout|available|present|included)|absent|missing from", prompt, re.I))
res["path_left_out_or_announced"] = ("audit-0.2.13" not in prompt) or says_absent
res["the_fix_is_still_asked_for"] = "the fix" in prompt
plain = "**Expected:**\n- plain ticket with no data path, keep me verbatim\n"
got, _, _ = capture("none", plain)
res["a_plain_ticket_is_unchanged"] = "plain ticket with no data path, keep me verbatim" in got["cmd"][2]
res["pass"] = all(res.values())
print(json.dumps(res))
