"""#205-#208 on a finished checkout: the checkout's own ops/triage/triage.py, driven with GitHub and the model faked.
- `malformed_triage`: a verdict with a list type, an int questions or no JSON fails its item; the next item is triaged;
- `malformed_plan`: a plan answer without text marks that item handler-failed and the next item is handled;
- `comment_fails`: a failed triage comment leaves that item without labels and the next item is still triaged;
- `feedback_once`: a failed reply after a filed ticket never files it again;
- `branch_retry`: a draft retry resets its branch (`checkout -B`), never fails on an existing one;
- `dry_once`: three dry runs judge each unchanged item once; a changed item is judged again;
- `same_repo`: with TRIAGE_REPO set to a fork, the review fetch and the draft's base and push use the fork, never origin.
"""
import importlib.util, json, sys, tempfile
from pathlib import Path

w = Path(sys.argv[1]).resolve()
spec = importlib.util.spec_from_file_location("triage_acc", w / "ops" / "triage" / "triage.py")
T = importlib.util.module_from_spec(spec)
spec.loader.exec_module(T)
out = {}
GOOD = '{"validity": "valid", "type": "bug", "priority": "low", "summary": "s", "comment": "c"}'


def item(n, **kw):
    return {"number": n, "title": "pack crashes on empty file", "body": "b", "author": "x", "bot": False, "assoc": "NONE",
            "pr": False, "labels": [], "comments": 0, "updated": "2026-11-19T00:00:00Z", **kw}


def setup(home, items, answers, runf=None):
    T.HOME = home
    home.mkdir(parents=True, exist_ok=True)
    T.update_tree = lambda: None
    T.ensure_labels = lambda a: None
    T.items = lambda: items
    T.log = lambda k, r: None
    it = iter(answers)
    T.claude = lambda *a: (next(it), 0.0)
    T.run = runf or (lambda cmd, **kw: "")


def quiet(f):
    import contextlib, io
    with contextlib.redirect_stdout(io.StringIO()) as b:
        try:
            f()
        except Exception as e:  # noqa: BLE001  an escaping error is the failure being checked
            return f"RAISED {type(e).__name__}: {e}"
    return b.getvalue()


fp = T.feedback_pass
with tempfile.TemporaryDirectory() as td:
    td = Path(td)
    ok = True
    for i, bad in enumerate(['{"validity": "valid", "type": ["bug"], "priority": "low"}',
                             '{"validity": "needs_info", "type": "bug", "priority": "low", "questions": 3}', "no json"]):
        setup(td / f"m{i}", [item(1), item(2)], [bad, GOOD])
        T.feedback_pass = lambda a, e: None
        o = quiet(lambda: T.cmd_triage(False, None))
        ok &= "#1: no verdict" in o and "#2 " in o and "RAISED" not in o
    out["malformed_triage"] = ok

    setup(td / "p", [item(1), item(2)], ['{"plan": {"a": 1}}', '{"plan": "do it"}'])
    T.wants_handling = lambda it: "plan"
    marks = []
    T.mark = lambda n, apply, add, remove=None: marks.append((n, add))
    o = quiet(lambda: T.cmd_handle(True, None))          # the real post: gh is faked by setup's run
    out["malformed_plan"] = marks == [(1, "handler-failed"), (2, "handled")]

    calls = []
    def r206(cmd, **kw):
        calls.append(cmd)
        if cmd[:3] == ["gh", "issue", "comment"] and cmd[3] == "69":
            raise RuntimeError("HTTP 502: Bad Gateway")
        return ""
    setup(td / "c", [item(69), item(70)], [GOOD, GOOD], r206)
    o = quiet(lambda: T.cmd_triage(True, None))
    edits = [c[3] for c in calls if c[:3] == ["gh", "issue", "edit"]]
    out["comment_fails"] = "RAISED" not in o and "69" not in edits and "70" in edits

    created = []
    def r206b(cmd, **kw):
        if cmd[:3] == ["gh", "issue", "create"]:
            created.append(1)
            return "https://github.com/o/r/issues/5\n"
        raise RuntimeError("comment failed")
    thread = {"number": 4, "title": "feedback", "labels": [T.FEEDBACK_LABEL], "pr": False}
    c = {"id": 77, "url": "u", "author": "a", "bot": False, "assoc": "NONE", "body": "it broke", "ours": False}
    tk = '{"action": "ticket", "type": "bug", "priority": "low", "ticket": {"title": "t", "body": "' + "b" * 90 + '"}, "reply": "ok"}'
    setup(td / "f", [], [tk, tk], r206b)
    T.feedback_pass = fp
    T.comments = lambda n: [c]
    quiet(lambda: T.feedback_pass(True, [thread]))
    quiet(lambda: T.feedback_pass(True, [thread]))
    out["feedback_once"] = created == [1]

    cmds = []
    setup(td / "b", [], [], lambda cmd, **kw: cmds.append(cmd) or "")
    T.worktree_for = lambda name, ref: cmds.append(["worktree", ref]) or td
    T.worktree_gitdir = lambda wk: (td / "g", "gitdir: x")
    def stop(*a):
        raise RuntimeError("stop after checkout")
    T.claude = stop
    quiet(lambda: T.handle_draft_pr(item(42), [], False))
    co = [x for x in cmds if "checkout" in x]
    out["branch_retry"] = bool(co) and "-B" in co[0] and "-b" not in co[0]

    n = []
    items = [item(1), item(2)]
    setup(td / "d", items, [])
    T.feedback_pass = lambda a, e: None
    T.claude = lambda *a: (n.append(1), (GOOD, 0.1))[1]
    for _ in range(3):
        quiet(lambda: T.cmd_triage(False, None))
    first = len(n)
    items[0]["updated"] = "2026-11-20T00:00:00Z"
    quiet(lambda: T.cmd_triage(False, None))
    out["dry_once"] = first == 2 and len(n) == 3

    fork = "https://github.com/someone/devkb-fork.git"
    T.REPO = "someone/devkb-fork"
    if hasattr(T, "REPO_URL"):
        T.REPO_URL = fork
    cmds = []
    setup(td / "r", [], ['{"review": "fine"}'], lambda cmd, **kw: cmds.append(cmd) or "")
    T.worktree_for = lambda name, ref: cmds.append(["worktree", ref]) or td
    T.post = lambda *a: None
    quiet(lambda: T.handle_review(item(7, pr=True), [], False))
    review_ok = any("fetch" in x and fork in x for x in cmds) and not any("fetch" in x and "origin" in x for x in cmds)
    cmds.clear()
    T.claude = stop
    quiet(lambda: T.handle_draft_pr(item(8), [], False))
    base = [x[1] for x in cmds if x[0] == "worktree"]
    draft_ok = any("fetch" in x and fork in x for x in cmds) and base and "origin" not in base[0]
    src = (w / "ops" / "triage" / "triage.py").read_text()
    out["same_repo"] = bool(review_ok and draft_ok and '"push", "-q", "origin"' not in src)
out["pass"] = all(v for k, v in out.items())
print(json.dumps(out))
