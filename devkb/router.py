"""`devkb hook prompt`: the workflow router. It pushes a compact graph bundle into the prompt, once, at the right stage.

Agents given devkb as a tool almost never call it (docs/analysis/why-agents-do-not-query-devkb.md: 0 of 63 runs). The
cause that held up was not a missing tool but a missing moment: with a location in hand, a read is the shortest path,
and advice at the point of need is not followed. So the router does not advise. At UserPromptSubmit it reads the prompt,
decides which SDLC stage it is, and either answers from the graph in the same turn or says nothing.

Routes (docs/specs/workflow-router.md):

  located   the prompt names `path.ext:LINE`: the agent already knows where to look, so the graph is skipped
            (the pre-edit hook still gives the file's pack at the first edit).
  error     a traceback, `Error:` line or quoted message: `pack error`.
  ticket    `#123` or `TICKET-123`: `pack ticket`, the commits, functions and tests of earlier work on it.
  change    a change request on an open branch ("per review feedback", "CR", "change request"): the blast radius
            of the branch's own diff, `pack file` of the changed source files.
  release   "release", "changelog", "bump", "tag": the commits since the last tag, grouped for a SemVer decision.
  navigate  the prompt names code (backticked or snake/Camel identifiers) the graph resolves: where each is defined.
  none      nothing to add. Most prompts are this, and costing them nothing is the point.

Rules, from the specification this implements: a bundle is at most BUDGET characters (about 1,000 tokens); it carries
`path:line` and never a file body; it says when the graph is stale; it never blocks and never fails the prompt; and
every decision, including `none`, is logged to `.devkb/router.jsonl` so the next measurement counts what was pushed.
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path

BUDGET = 3000          # characters, under 800 tokens (the reference architecture's cap)
PER_PART = 1500        # characters one pack may take of the bundle
MAX_SYMBOLS = 4
MAX_FILES = 3
MIN_PROMPT = 12        # "ok", "yes", "continue": nothing to route
SRC = r"(?:py|pyi|ts|tsx|js|jsx|mjs|c|cc|cpp|cxx|h|hh|hpp|hxx|java|go|rs|cs)"
LOCATED = re.compile(rf"(?<![\w./-])((?:[\w.-]+/)*[\w.-]+\.{SRC})(?::|#L|\s+(?:line|lines|L)\s*)(\d+)")
TRACE = re.compile(r"Traceback \(most recent call last\)|^\s+at \S+ \(.+:\d+:\d+\)|^\w*(?:Error|Exception)\b.*:", re.M)
ERROR_LINE = re.compile(r"\b(?:\w+\.)*\w*(?:Error|Exception|Panic)\s*:\s*(.{6,200})$", re.M)
QUOTED_ERROR = re.compile(r"[\"'`]([^\"'`\n]{12,160})[\"'`]")
TICKET = re.compile(r"(?i:(?<![\w/&])(?:#|(?:issue|ticket|PR)\s+#?)(\d{1,6})\b)|(?<![\w-])([A-Z]{2,10}-\d{1,6})\b")
CHANGE = re.compile(r"\b(change request|CR\b|review feedback|reviewer (?:asked|said|wants)|address(?:ing)? (?:the )?(?:review|comments)|"
                    r"per (?:the )?(?:feedback|review|new spec)|spec (?:changed|update))", re.I)
RELEASE = re.compile(r"\b((?:prepare|cut|draft|ship|plan|do|make|start)\s+(?:the\s+|a\s+|our\s+)?(?:next\s+)?release|release\s+(?:notes|candidate|checklist|readiness|audit)|"
                     r"changelog|bump\s+(?:the\s+)?version|semver|tag\s+v?\d+\.\d+|publish\s+v?\d+\.\d+)", re.I)
BACKTICKED = re.compile(r"`([A-Za-z_][\w.:]{2,80})`")
CODEISH = re.compile(r"(?<![\w])(_{0,2}[a-z]+(?:_[a-z0-9]+)+|_[a-z][a-z0-9]{3,}|[A-Z][a-z0-9]+(?:[A-Z][a-z0-9]+)+|[a-z]+[A-Z][A-Za-z0-9]+|(?<=[a-z,;] )[A-Z][a-z]{4,})\b")
STOP = {"pytest", "github", "javascript", "typescript", "claude_code", "pre_commit"}


@dataclass
class Route:
    name: str
    why: str
    subjects: list[str] = field(default_factory=list)


def tracked(project: Path, path: str) -> bool:
    """Whether `path` (as a ticket writes it, maybe only a file name) is a file of this repository. A fixture path in a
    reproduction (`src/a.cpp L8-10`) or a corpus file is not where the agent has to work, so it is not a location."""
    if (project / path).is_file():
        return True
    return bool(_git(project, "ls-files", "--", f"*/{path}", path))


def classify(prompt: str, branch_has_diff: bool = False, known=None) -> Route:
    """Which stage a prompt belongs to. Pure: no graph, no git. The order is the order of cost: a located ticket is free,
    an error or ticket id is exact, a change request needs the branch's diff, and a bare name is the weakest signal."""
    text = (prompt or "").strip()
    if len(text) < MIN_PROMPT:
        return Route("none", "too short to route")
    located = next((m for m in LOCATED.finditer(text) if known is None or known(m.group(1))), None)   # a tracked file only
    if located:
        return Route("located", f"names {located.group(1)}:{located.group(2)}", [located.group(1)])
    if TRACE.search(text) or ERROR_LINE.search(text):
        msg = ERROR_LINE.search(text)
        return Route("error", "a traceback or error line", [msg.group(1).strip() if msg else _first_error_text(text)])
    t = TICKET.search(text)
    if t and not CHANGE.search(text):
        return Route("ticket", "names a ticket", [t.group(1) or t.group(2)])
    if CHANGE.search(text) and branch_has_diff:
        return Route("change", "a change request on a branch with a diff")
    if RELEASE.search(text):
        return Route("release", "a release request")
    names = _names(text)
    if names:
        return Route("navigate", "names code", names[:MAX_SYMBOLS])
    return Route("none", "names nothing the graph could resolve")


def _first_error_text(text: str) -> str:
    for line in text.splitlines():
        s = line.strip()
        if s and not s.startswith(("File ", "Traceback", "at ")):
            return s[:160]
    return text.strip()[:160]


def _names(text: str) -> list[str]:
    seen: dict[str, None] = {}
    for m in BACKTICKED.finditer(text):
        w = m.group(1).strip(".:")
        if len(w) >= 5 or re.search(r"[_A-Z]", w[1:]):       # `add` and `run` are words before they are names
            seen.setdefault(w, None)
    for m in CODEISH.finditer(text):
        w = m.group(1)
        if w.lower() not in STOP and len(w) > 4:
            seen.setdefault(w, None)
    return [n for n in seen if not LOCATED.search(n) and "/" not in n]


# ── the bundle ─────────────────────────────────────────────────────────────────────────────────────────────────────────
def _git(project: Path, *args: str) -> str:
    out = subprocess.run(["git", *args], cwd=project, capture_output=True, text=True, timeout=10, check=False)
    return out.stdout.strip() if out.returncode == 0 else ""


def trunk(project: Path) -> str:
    for ref in ("origin/main", "main", "origin/master", "master"):
        if _git(project, "rev-parse", "--verify", "-q", ref):
            return ref
    return ""


def branch_files(project: Path) -> list[str]:
    """Source files the current branch changed against the trunk, plus uncommitted ones."""
    base = trunk(project)
    names = set(_git(project, "diff", "--name-only", f"{base}...HEAD").splitlines()) if base else set()
    names |= set(_git(project, "diff", "--name-only", "HEAD").splitlines())
    return sorted(n for n in names if re.search(rf"\.{SRC}$", n) and (project / n).is_file())


def release_bundle(project: Path) -> str:
    tag = _git(project, "describe", "--tags", "--abbrev=0")
    rng = f"{tag}..HEAD" if tag else "HEAD"
    subjects = _git(project, "log", rng, "--no-merges", "--pretty=%s", "-n", "200").splitlines()
    if not subjects:
        return ""
    groups: dict[str, list[str]] = {"breaking": [], "feat": [], "fix": [], "other": []}
    areas: dict[str, int] = {}
    for s in subjects:
        kind = re.match(r"(\w+)(\([^)]*\))?(!)?:", s)
        key = "breaking" if kind and kind.group(3) or "BREAKING" in s else (kind.group(1) if kind and kind.group(1) in groups else "other")
        groups[key].append(s)
        if kind:
            areas[kind.group(1)] = areas.get(kind.group(1), 0) + 1
    if not (groups["breaking"] or groups["feat"] or groups["fix"]):
        # No conventional-commit types here: a bump would be a guess, so give the shape of the range and no verdict.
        top = ", ".join(f"{k} {n}" for k, n in sorted(areas.items(), key=lambda kv: -kv[1])[:6])
        return (f"Since {tag or 'the first commit'}: {len(subjects)} commits, none typed feat/fix/breaking, so no SemVer verdict "
                f"(by area: {top or 'untyped'}). Read the diff of a public contract, then decide.")
    bump = "major" if groups["breaking"] else "minor" if groups["feat"] else "patch"
    lines = [f"Since {tag or 'the first commit'}: {len(subjects)} commits; SemVer suggests a **{bump}** bump "
             f"({len(groups['breaking'])} breaking, {len(groups['feat'])} feat, {len(groups['fix'])} fix, {len(groups['other'])} other)."]
    for key in ("breaking", "feat"):
        lines += [f"- {key}: {x[:110]}" for x in groups[key][:5]]
    return "\n".join(lines) + "\nThe commit prefixes are a guess; read the diff of a public contract before you decide."


def stale_note(project: Path) -> str:
    """One line when the graph was built at another commit than HEAD: a stale lead is worse than none (spec rule)."""
    try:
        built = json.loads((project / ".devkb" / "manifest.json").read_text()).get("git_head") or ""
    except (OSError, ValueError):
        return ""
    head = _git(project, "rev-parse", "HEAD")
    if not built or not head or built == head:
        return ""
    behind = _git(project, "rev-list", "--count", f"{built}..HEAD")
    return f"\n(graph built {behind + ' commits' if behind.isdigit() else 'at another commit'} before HEAD: re-check anything that decides a change; `devkb build --project .` refreshes it)"


def _grams(message: str, window: int = 4) -> set[str]:
    words = re.findall(r"[a-z0-9']+", message.lower())
    return {" ".join(words[i:i + window]) for i in range(max(1, len(words) - window + 1))}


def proven_raisers(project: Path, message: str, pack_text: str) -> tuple[list[str], int]:
    """(the "Raised by" lines whose file holds a run of the message as literal text, how many the pack listed).

    `pack error` matches loosely and does not say so: a message that is returned, not raised, got three unrelated raisers,
    and a real one got two extra. The router pushes only what it can see in the source."""
    grams = _grams(message)
    section = pack_text.split("## Raised by", 1)[-1].split("\n## ", 1)[0]
    lines = [x for x in section.splitlines() if x.startswith("- `")]
    kept = []
    for line in lines:
        m = re.match(r"- `([^`:]+)::", line)
        try:
            body = " ".join(re.findall(r"[a-z0-9']+", (project / m.group(1)).read_text(errors="replace").lower())) if m else ""
        except OSError:
            body = ""
        if any(g in body for g in grams):
            kept.append(line)
    return kept, len(lines)


def error_bundle(project: Path, message: str, pack_text: str) -> str:
    kept, listed = proven_raisers(project, message, pack_text)
    if not kept:
        return ""
    if len(kept) == listed:
        return "devkb, what raises this error and who reaches it:\n\n" + _clip(_lean(pack_text), BUDGET)
    names = " ".join(re.match(r"- `[^`]*::([^`]+)`", k).group(1) for k in kept[:1])
    return (f"devkb, what raises this error (the graph listed {listed} raisers; {len(kept)} contain the message, the rest are dropped):\n"
            + "\n".join(kept) + f"\nWho reaches it: `devkb pack --project . refactor {names}`.")


def _lean(pack: str) -> str:
    """A pack without its closing instructions (the router's own header says how to use it) and its title line."""
    pack = pack.split("\n---\n", 1)[0]
    return "\n".join(x for x in pack.splitlines() if not x.startswith("# Graph pack:")).strip()


def _clip(text: str, n: int) -> str:
    return text if len(text) <= n else text[:n].rsplit("\n", 1)[0] + "\n... (cut)"


class Backend:
    """The graph, bound to one project. Built only when a route needs it, so a `none` route never loads the graph."""

    def __init__(self, project: Path) -> None:
        from devkb.packs import Packer  # noqa: PLC0415
        from devkb.process_api import ProcessAPI  # noqa: PLC0415
        from devkb.read_tools import ReadTools  # noqa: PLC0415
        self.api = ProcessAPI(str(project), telemetry_source="router")
        self.packer, self.reader = Packer(self.api), ReadTools(self.api)

    def pack(self, kind: str, subject: str) -> str:
        from devkb.packs import logged_pack  # noqa: PLC0415
        return logged_pack(self.packer, kind, subject)

    def symbol(self, name: str) -> dict:
        return self.api.call("symbol", query=name, limit=3)

    def tests(self, key: str) -> dict:
        return self.api.call("tests_for", ref=key, limit=3)


def _symbol_row(reply: dict) -> dict | None:
    """The best exact row for a name the graph defines. A fuzzy match is not one: a wrong lead costs more than none."""
    rows = reply.get("matches") or []
    if reply.get("error") or not rows or reply.get("how") in (None, "similar") or not rows[0].get("ls") or "::" not in (rows[0].get("k") or ""):
        return None
    # a name that resolves only into tests or fixtures is not the code the prompt is about (#120: `add` led to a TS fixture)
    rows = [r for r in rows if not re.search(r"(^|/)(tests?|fixtures?|corpus)/", (r.get("k") or "").split("::")[0])]
    if not rows:
        return None
    return {**rows[0], "n": reply.get("n", 1)}


def _symbol_line(r: dict, tests: dict | None) -> str:
    path, _, qual = r["k"].partition("::")
    callers = f", {r['callers']} caller(s)" if r.get("callers") else ""
    more = f" (+{r['n'] - 1} more with this name)" if r["n"] > 1 else ""
    line = f"- `{qual}` at `{path}:{r['ls']}`{callers}{more}"
    files = (tests or {}).get("files") or []
    if files:
        shown = ", ".join(f"`{f['f']}`" for f in files[:2])
        gap = "" if (tests.get("coverage") or {}).get("complete", True) else " (list may be incomplete)"
        extra = f" (+{tests['n_files'] - 2} more files)" if tests.get("n_files", 0) > 2 else ""
        line += f"; tests: {shown}{extra}{gap}"
    elif tests is not None and not tests.get("error"):
        line += "; no test calls it directly (check its callers' tests)"
    return line


def bundle(route: Route, project: Path, backend: Backend | None = None) -> tuple[str, dict]:
    """(text, detail) for a route; text is empty when there is nothing worth the tokens."""
    detail: dict = {}
    if route.name in ("none", "located"):
        return "", detail
    if route.name == "release":
        text = release_bundle(project)
        return (f"devkb, release scope (from git, no graph needed):\n{text}" if text else ""), detail
    if route.name == "change":
        files = branch_files(project)[:MAX_FILES]
        if not files:
            return "", detail
        backend = backend or Backend(project)
        parts = [f"### `{f}`\n" + _clip(_lean(backend.pack("file", f)), PER_PART) for f in files]
        detail["files"] = files
        return "devkb, blast radius of this branch's changes (callers outside the diff, tests to run):\n\n" + "\n\n".join(parts), detail
    backend = backend or Backend(project)
    if route.name == "error":
        text = backend.pack("error", route.subjects[0])
        if "has no error matching" in text:
            return "", detail
        out = error_bundle(project, route.subjects[0], text)
        if not out:
            detail["refused"] = "no listed raiser contains the message"   # the pack matched loosely: a wrong lead is worse than none
        return out, detail
    if route.name == "ticket":
        for key in (route.subjects[0], f"GH-{route.subjects[0]}"):      # a bare number is a GitHub issue in the graph
            text = backend.pack("ticket", key)
            if "has no ticket" not in text:
                return "devkb, earlier work on this ticket:\n\n" + _clip(_lean(text), BUDGET), detail
        return "", detail
    if route.name == "navigate":
        rows = [(n, _symbol_row(backend.symbol(n))) for n in route.subjects]
        rows = [(n, r) for n, r in rows if r]
        seen: set[str] = set()
        lines = []
        for n, r in rows:
            if r["k"] in seen:
                continue
            seen.add(r["k"])
            lines.append(_symbol_line(r, backend.tests(r["k"]) if len(lines) < 2 else None))
        detail["resolved"] = [n for n, _ in rows]
        if not lines:
            return "", detail
        head = ("devkb, where the code this prompt names is defined, with the tests that call it "
                "(`devkb pack --project . refactor NAME` lists the callers):\n")
        return head + "\n".join(lines), detail
    return "", detail


def log_decision(project: Path, event: dict, route: Route, text: str, detail: dict, ms: float) -> None:
    try:
        path = project / ".devkb" / "router.jsonl"
        path.parent.mkdir(parents=True, exist_ok=True)
        row = {"ts": time.strftime("%Y-%m-%dT%H:%M:%S%z"), "session": event.get("session_id", ""), "route": route.name,
               "why": route.why, "subjects": route.subjects[:4], "chars": len(text), "ms": round(ms, 1), **detail}
        with path.open("a") as fh:
            fh.write(json.dumps(row) + "\n")
    except OSError:
        pass


def on_prompt(event: dict, backend: Backend | None = None) -> dict | None:
    """The UserPromptSubmit hook's JSON answer for one event; None when there is nothing to add."""
    project = Path(os.environ.get("CLAUDE_PROJECT_DIR") or event.get("cwd") or ".").resolve()
    if os.environ.get("DEVKB_ROUTER") == "0":
        return None
    has_graph = (project / ".devkb" / "nodes.jsonl").exists()
    t0 = time.perf_counter()
    prompt = event.get("prompt") or ""
    route = classify(prompt, branch_has_diff=bool(branch_files(project)) if CHANGE.search(prompt) else False,
                     known=lambda p: tracked(project, p))
    needs_graph = route.name not in ("none", "located", "release")
    if needs_graph and not has_graph:
        log_decision(project, event, Route("none", f"{route.name}: no graph built"), "", {}, 0.0)
        return None
    text, detail = bundle(route, project, backend)
    text = _clip(text, BUDGET - 200) + (stale_note(project) if text and route.name != "release" else "")
    log_decision(project, event, route, text, detail, (time.perf_counter() - t0) * 1000)
    if not text:
        return None
    return {"hookSpecificOutput": {"hookEventName": "UserPromptSubmit", "additionalContext": text}}


def main(event: dict | None = None) -> int:
    try:
        out = on_prompt(event if event is not None else json.loads(sys.stdin.read() or "{}"))
        if out:
            print(json.dumps(out))
    except Exception as exc:  # a hook must never break the prompt  # noqa: BLE001
        print(f"devkb router: {exc}", file=sys.stderr)
    return 0
