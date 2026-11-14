#!/usr/bin/env python3
"""Write a role's session-start brief from the graph (ODSF-311).

An agent starting a session as a tester, a developer, a DevOps engineer, a data engineer, an architect or a tech lead
needs different things first. This renders the process API's `role_brief` as a short markdown file, so the facts are
in the context from the first turn without a single tool call.

  python3 devkb/startup.py --project ODSF --role QA        # .devkb/startup/QA.md
  python3 devkb/startup.py --project ODSF --all            # one file per declared role
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from devkb.process_api import ProcessAPI  # noqa: E402


def _paths(paths: list[str], cap: int = 12) -> str:
    if not paths:
        return "nothing declared"
    shown = ", ".join(f"`{p}`" for p in paths[:cap])
    return shown + (f", and {len(paths) - cap} more in the profile" if len(paths) > cap else "")


def render(brief: dict) -> str:
    meta = brief.get("_meta", {})
    p = brief.get("profile", {})
    lines = [f"# Session start: {brief['role']}", "",
             f"Generated from the dev-process graph built {meta.get('built', '?')} at {meta.get('head', '?')}"
             + (" (the repository has moved on: re-check anything that decides a change)." if meta.get("stale") else "."),
             f"Your role profile is `{p.get('file', '?')}`; read it when a rule below is not enough.", ""]
    for key, label in (("mission", "Mission"), ("decides", "You decide"), ("not_decide", "You do not decide")):
        if p.get(key):
            lines.append(f"- **{label}**: {p[key]}")
    t = brief.get("territory", {})
    lines += ["", "## Territory", f"- **You own**: {_paths(t.get('own', []))}", f"- **Never touch**: {_paths(t.get('forbidden', []))}"]
    w = brief.get("work", {})
    lines += ["", "## Work waiting", "Tickets by status: " + (", ".join(f"{k} {v}" for k, v in sorted(w.get("counts", {}).items())) or "none") + "."]
    for it in w.get("open", []):
        lines.append(f"- `{it['t']}` {it['p']} {it['s']}: {it['title']}")
    a = brief.get("area", {})
    if a.get("files"):
        lines += ["", "## Your code", f"{a['files']} files, {a.get('symbols', 0)} functions and classes. Most depended on:"]
        lines += [f"- `{s['k']}` ({s['prod_callers']} callers outside tests)" for s in a.get("key_symbols", [])]
    else:
        lines += ["", "## Your code", "Your territory holds documents and configuration, not indexed code."]
    if a.get("endpoints"):
        lines.append("- Endpoints: " + ", ".join(f"`{e}`" for e in a["endpoints"]))
    if a.get("run"):
        lines += ["", "Run your tests with:", "", f"    {a['run']}"]
    if brief.get("docs"):
        lines += ["", "## Read first"] + [f"- `{d['p']}`: {d['t']}" for d in brief["docs"]]
    extras = brief.get("extras") or {}
    if extras:
        lines += ["", "## For this role"]
        for k, v in extras.items():
            if isinstance(v, list):
                lines.append(f"- **{k.replace('_', ' ')}**: " + ("; ".join(str(x) for x in v) if v else "none"))
            elif isinstance(v, dict):
                lines.append(f"- **{k.replace('_', ' ')}**: " + (", ".join(f"{a2} {b2}" for a2, b2 in v.items()) or "none"))
            elif v is not None:
                lines.append(f"- **{k.replace('_', ' ')}**: {v}")
    lines += ["", "## Ask the graph",
              "Before reading the repository, use the devkb-sdlc tools through these skills: "
              + ", ".join(f"`{s}`" for s in brief.get("ask", [])) + ". Check `_meta.stale` on every answer.", ""]
    return "\n".join(lines)


def write(api: ProcessAPI, role: str, out_dir: Path) -> Path | None:
    brief = api.call("role_brief", role=role)
    if "error" in brief:
        print(brief["error"], file=sys.stderr)
        return None
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"{brief['role']}.md"
    path.write_text(render(brief))
    return path


def main() -> int:
    ap = argparse.ArgumentParser(description="write role session-start briefs from the dev-process graph")
    ap.add_argument("--project", required=True)
    ap.add_argument("--role")
    ap.add_argument("--all", action="store_true")
    ns = ap.parse_args()
    api = ProcessAPI(ns.project)
    out_dir = api.ctx.devkb_dir / "startup"
    roles = sorted(api._role_table()) if ns.all else [ns.role] if ns.role else []
    if not roles:
        ap.error("--role CODE or --all")
    for role in roles:
        path = write(api, role, out_dir)
        if path:
            print(f"{path}  {len(path.read_text().split())} words")
    return 0


if __name__ == "__main__":
    sys.exit(main())
