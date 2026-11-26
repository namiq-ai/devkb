#!/usr/bin/env python3
"""devkb-sdlc: the software-engineering-process API as an MCP server (ODSF-307).

Read-only tools over one project's devkb graph, one per question a development
stage asks. Tool descriptions are kept to a sentence on purpose: an MCP
server's tool list is paid for in every model turn, so a long description is a
recurring token cost, not a one-off.

  uv run --python ">=3.10" --no-project --with "mcp>=1.23,<2" python devkb/mcp_server.py --project ODSF

Environment: DEVKB_PROJECT (default project), DEVKB_TOOLSET (core, workflow or all), DEVKB_DIR (a pinned graph snapshot
instead of the live `.devkb/`).
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from mcp.server.fastmcp import FastMCP  # noqa: E402
from mcp.types import ToolAnnotations  # noqa: E402

from devkb.process_api import ProcessAPI, project_for  # noqa: E402
from devkb.service import GraphNotBuilt  # noqa: E402


class _LazyAPI:
    """The process API, loaded on first use. A plugin starts the server before any graph exists (its session-start
    hook builds one in the background); until then every tool says how to get one instead of the server failing."""

    def __init__(self, project: str, devkb_dir: Path | None) -> None:
        self._args, self._api = (project, devkb_dir), None

    def get(self) -> ProcessAPI:
        if self._api is None:
            self._api = ProcessAPI(self._args[0], devkb_dir=self._args[1])
        return self._api

    def call(self, name: str, /, **kw) -> dict:
        try:
            return self.get().call(name, **kw)
        except GraphNotBuilt as e:
            return {"error": "no graph yet", "detail": str(e),
                    "next": "the graph is being built in the background on first use; ask again in a minute, or run "
                            "`devkb build --project .` and wait for it"}

READ_ONLY = ToolAnnotations(readOnlyHint=True, idempotentHint=True, destructiveHint=False, openWorldHint=False)
CORE = ["sdlc_context", "trace", "find_docs", "callers", "tests_for", "tests_to_run", "impact", "owner", "review_pack",
        "lineage", "graph_status", "config"]
WORKFLOW = ["feature_brief", "bug_brief", "rca_trace", "refactor_scope", "explain_area", "find_code", "history"]
DOCS = ["design_brief", "flow_sequence", "test_items", "review_doc", "role_brief"]
# SPEC-DKB-003: what agents otherwise grep for (a definition and its body, a file's outline, where a name is used, what the docs say).
READ = ["symbol", "outline", "uses", "search_docs"]
# `core`: single-question tools. `workflow`: one tool per kind of development work, plus the few core tools those
# workflows still need. `docs`: writing and reviewing designs and test specifications, and starting a role's session
# (ODSF-311). `all`: every tool. A smaller set costs fewer tokens to load, so the choice is a deployment decision.
TOOLSETS = {"core": CORE, "workflow": WORKFLOW + ["review_pack", "tests_to_run", "impact", "sdlc_context", "find_docs"],
            "docs": DOCS + ["find_docs", "explain_area", "find_code", "sdlc_context", "history"],
            # ODSF-313: only the tools the benchmarks showed earn their place (chains and joins), so each turn loads fewer
            # tool definitions. Their list answers all carry `coverage`.
            "lean": ["rca_trace", "impact", "callers", "tests_for", "tests_to_run", "review_pack", "config"],
            # `devkb init`'s default: lean, plus orienting in an area before writing new code there. Lean alone left an
            # agent implementing a feature with nothing to ask (it read whole files instead); lean stays as measured.
            # Packs over MCP: one call returns a whole answer (the measured "pack" arm put it in the prompt; here the
            # agent asks for it). `lean-pack` is the arm that measures that; `lean` stays as measured.
            "lean-pack": ["rca_trace", "impact", "callers", "tests_for", "tests_to_run", "review_pack", "config", "pack"] + READ,
            # Navigation only: definitions, file outlines and whole-answer packs. Three tool definitions instead of fourteen.
            "nav": ["symbol", "outline", "pack"],
            "dev": ["rca_trace", "impact", "callers", "tests_for", "tests_to_run", "review_pack", "config",
                    "explain_area", "feature_brief", "find_code", "pack"] + READ,
            "all": CORE + WORKFLOW + DOCS + READ + ["pack"]}
INSTRUCTIONS = ("Dev-process graph for this repository: tickets, specs, commits, symbols, calls, tests, owners. "
                "Ask it first, then read only the files it names. Every reply says if the graph is stale.")


def _compact(reply: dict) -> str:
    """Compact JSON text. FastMCP pretty-prints a dict return with indentation, which
    costs the model tokens on every call for no reader."""
    return json.dumps(reply, separators=(",", ":"))


# Claude Code defers MCP tools behind a ToolSearch call, which costs the agent a turn before its first lookup (measured: 15 of 16
# runs began with ToolSearch). A tool that carries this annotation is loaded with the prompt instead. Only the tools agents reach for
# first are marked, so the prompt grows by four definitions, not by the whole set. `uses` is one of them (#448): the block `devkb init`
# writes names it to "find who calls a function", and in all 5 default runs of the structural probe (#447) the agent spent a ToolSearch
# call loading it, asking for `callers` in the same call and then never calling that. `callers` stays deferred: when both were loaded,
# in a server cut down to `symbol`, `outline`, `pack`, `uses` and `callers`, it was called 2 times to `uses`' 14.
ALWAYS_LOAD = {"symbol", "outline", "pack", "uses"}
ALWAYS_LOAD_META = {"anthropic/alwaysLoad": True}


def build(api: ProcessAPI, toolset: str = "all") -> FastMCP:
    mcp = FastMCP("devkb-sdlc", instructions=INSTRUCTIONS)
    enabled = set(TOOLSETS[toolset])

    def tool(fn):
        if fn.__name__ not in enabled:
            return fn
        meta = ALWAYS_LOAD_META if fn.__name__ in ALWAYS_LOAD else None
        return mcp.tool(annotations=READ_ONLY, structured_output=False, meta=meta)(fn)

    @tool
    def sdlc_context(ticket: str) -> str:
        """Brief for a ticket: status, owner role, epic, spec and requirement chain, related docs, similar tickets, commit and file counts."""
        return _compact(api.call("sdlc_context", ticket=ticket))

    @tool
    def trace(ticket: str) -> str:
        """Requirement-to-ticket chain with status, and the Gate 0 readiness verdict for a story."""
        return _compact(api.call("trace", ticket=ticket))

    @tool
    def find_docs(topic: str, kinds: list[str] | None = None, limit: int = 8) -> str:
        """Ranked specs, ADRs and design docs on a topic. kinds: specification, adr, design."""
        return _compact(api.call("find_docs", topic=topic, kinds=kinds, limit=limit))

    @tool
    def callers(symbol: str, depth: int = 1) -> str:
        """Who calls this function (name or path::name), directly and up to depth 3; tests are listed last."""
        return _compact(api.call("callers", symbol=symbol, depth=depth))

    @tool
    def tests_for(ref: str) -> str:
        """Tests linked to a function or file, with a runnable pytest line."""
        return _compact(api.call("tests_for", ref=ref))

    @tool
    def tests_to_run(files: list[str]) -> str:
        """Which tests to run for these changed files, ranked, with a runnable pytest line."""
        return _compact(api.call("tests_to_run", files=files))

    @tool
    def impact(files: list[str], depth: int = 2) -> str:
        """Blast radius of changing these files: affected callers, endpoints, flows, tests to run, owning roles."""
        return _compact(api.call("impact", files=files, depth=depth))

    @tool
    def owner(path: str) -> str:
        """Which role owns a path and which roles must not touch it."""
        return _compact(api.call("owner", path=path))

    @tool
    def pack(kind: str, subject: str, path: str = "", role: str = "") -> str:
        """Whole answer in one call, with proof lines and coverage. kind: file (subject=path), refactor or change (a function), error (message), pr, ticket."""
        from devkb.packs import Packer  # noqa: PLC0415
        try:
            p = Packer(api.get() if isinstance(api, _LazyAPI) else api)
        except GraphNotBuilt:
            return "No devkb graph yet: it is being built in the background; ask again in a minute."
        from devkb.packs import logged_pack  # noqa: PLC0415
        return logged_pack(p, kind, subject, path, role)

    def _read(tool_name: str, **kw) -> str:
        from devkb.read_tools import RENDER  # noqa: PLC0415
        reply = api.call(tool_name, **kw)
        if "error" in reply and "detail" in reply:           # no graph yet
            return f"{reply['error']}: {reply['detail']} {reply.get('next', '')}"
        return RENDER[tool_name](reply)

    @tool
    def symbol(query: str, source: bool = False, kind: str = "", under: str = "", limit: int = 8, lines: int = 80) -> str:
        """Where names are defined (name, A.b, path::name, glob, re:regex; typos tolerated; several names comma-separated in one call): exact lines and signature; source=True prints bodies."""
        return _read("symbol", query=query, source=source, kind=kind, under=under, limit=limit, lines=lines)

    @tool
    def outline(path: str, offset: int = 0) -> str:
        """A file's symbols in order with nesting and line ranges, plus its imports; a directory lists its files with symbol counts. offset=N skips N symbols (the next page of a large file)."""
        return _read("outline", path=path, offset=offset)

    @tool
    def uses(name: str, under: str = "", docs: bool = False) -> str:
        """Where a name, constant, module or key appears in code (text matches), grouped by file and by the symbol containing each use."""
        return _read("uses", name=name, under=under, docs=docs)

    @tool
    def search_docs(query: str, under: str = "") -> str:
        """Search documentation (md, rst, txt, adoc) for words or a re:regex; best files first, each hit with its heading."""
        return _read("search_docs", query=query, under=under)

    @tool
    def review_pack(rev: str) -> str:
        """Review context for a commit or range (a..b): changed symbols, callers outside the diff, tests, untested symbols, docs, warnings, owners."""
        return _compact(api.call("review_pack", rev=rev))

    @tool
    def lineage(ticket: str) -> str:
        """Bug lineage, duplicates, blockers, commits and spec of a ticket."""
        return _compact(api.call("lineage", ticket=ticket))

    @tool
    def feature_brief(goal: str, ticket: str = "") -> str:
        """Build a feature: similar code, governing docs, similar past work, owner and forbidden paths, tests to copy and run."""
        return _compact(api.call("feature_brief", goal=goal, ticket=ticket))

    @tool
    def bug_brief(ticket: str = "", text: str = "") -> str:
        """Fix a bug from a ticket id or symptom text: suspects, entry points, recent commits, similar past bugs and their fixes, tests."""
        return _compact(api.call("bug_brief", ticket=ticket, text=text))

    @tool
    def rca_trace(symptom: str, depth: int = 3) -> str:
        """Root cause: an error message or name to the raising code, callers up to the entry points, recent commits on that path, tests."""
        return _compact(api.call("rca_trace", symptom=symptom, depth=depth))

    @tool
    def refactor_scope(target: str, role: str = "") -> str:
        """Before a refactor: callers by file, test files, endpoints, tests to run, and caller files your role code may not edit."""
        return _compact(api.call("refactor_scope", target=target, role=role))

    @tool
    def explain_area(path: str) -> str:
        """Understand a directory or file: key symbols by dependents, entry points, owners, governing docs, tests, recent commits."""
        return _compact(api.call("explain_area", path=path))

    @tool
    def find_code(query: str, under: str = "") -> str:
        """Find code by plain words matched against symbol names, paths and docstrings; optionally under a path prefix."""
        return _compact(api.call("find_code", query=query, under=under))

    @tool
    def history(files: list[str]) -> str:
        """The latest commits that touched these files, with dates and ticket ids."""
        return _compact(api.call("history", files=files))

    @tool
    def design_brief(kind: str, topic: str) -> str:
        """Before writing a functional, architecture, detailed or sequence design or a test_spec: outline, facts to cite, related docs, next spec id."""
        return _compact(api.call("design_brief", kind=kind, topic=topic))

    @tool
    def flow_sequence(entry: str) -> str:
        """Recorded call order from an endpoint, function or flow id, as numbered messages and Mermaid sequence-diagram text."""
        return _compact(api.call("flow_sequence", entry=entry))

    @tool
    def test_items(area: str) -> str:
        """Test items for a path or function from what it raises, the endpoints it serves and untested branches, marked covered or not."""
        return _compact(api.call("test_items", area=area))

    @tool
    def review_doc(path: str, kind: str = "") -> str:
        """Review a design or test-spec document against the repo: broken references, drift since written, unmentioned code, missing sections."""
        return _compact(api.call("review_doc", path=path, kind=kind))

    @tool
    def role_brief(role: str) -> str:
        """Session start for a role code (QA, BE, TL, OPS, DSA, DE...): territory, waiting tickets, key code, tests, docs, role-specific facts."""
        return _compact(api.call("role_brief", role=role))

    @tool
    def config(query: str = "") -> str:
        """A setting (env var) or service: code reading it, files declaring it, services deploying it, repos; empty for an overview."""
        return _compact(api.call("config", query=query))

    @tool
    def graph_status() -> str:
        """Size of the graph and whether it is stale against the repository."""
        return _compact(api.call("graph_status"))

    return mcp


def main() -> int:
    ap = argparse.ArgumentParser(description="devkb-sdlc MCP server (stdio)")
    ap.add_argument("--project", default=os.environ.get("DEVKB_PROJECT"))
    ap.add_argument("--devkb-dir", default=os.environ.get("DEVKB_DIR"))
    ap.add_argument("--toolset", default=os.environ.get("DEVKB_TOOLSET", "lean-pack"), choices=sorted(TOOLSETS))
    ns = ap.parse_args()
    if not ns.project:
        ns.project = project_for(Path.cwd())
    if not ns.project:
        ap.error("--project or DEVKB_PROJECT is required (and the working directory is in no registered project)")
    api = _LazyAPI(ns.project, Path(ns.devkb_dir) if ns.devkb_dir else None)
    build(api, ns.toolset).run(transport="stdio")
    return 0


if __name__ == "__main__":
    sys.exit(main())
