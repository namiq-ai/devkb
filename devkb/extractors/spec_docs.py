"""Spec + DOCUMENTS (devkb BL-13, promoted from `devkb/ROADMAP.md`'s own
Phase 4 step 1 -- KNOWLEDGE_SPEC.md Section 4/5).

Deterministic, regex-derived, no LLM call -- the cheap half of Phase 4
(`devkb/answer.py`'s LLM-synthesis half stays out of scope, Section 9).
Closes the audit's "no node descriptions from specification documents"
finding: every ADR/design/onboarding markdown file becomes a real `Spec`
node, `DOCUMENTS` linking it to any `Ticket` it actually mentions.

Needs the FULL merged graph (real `Ticket` nodes from Phase 1) so a
`DOCUMENTS` edge only ever points at a ticket confirmed to exist -- a
stale/renamed/typo'd ticket-id mention in an old doc gets skipped, not
guessed into a dangling edge. Post-merge, same shape as BL-4/BL-6/BL-11.
"""
from __future__ import annotations

import hashlib
import re

from devkb.model import DevKBGraph
from devkb.project_context import DEFAULT_SPEC_DIRS, ProjectContext

_HEADING_RE = re.compile(r"^#\s+(.+)$", re.MULTILINE)
_RELATED_LINE_RE = re.compile(r"^\*?\*?Related.*?:\*?\*?\s*(.+)$", re.MULTILINE | re.IGNORECASE)

# The two closed vocabularies ADR-SDP-SPEC-001 Section 3 defines. Closed on
# purpose: an open one is how the sibling OCO checkout ended up carrying
# `Accepted`, `Proposed`, `PROPOSED`, `DRAFT` and nine lines of prose in the
# same field. A declared value outside these sets is not honoured -- it falls
# back to the path rule below rather than inventing a fifth state.
_DOC_TYPES = frozenset({"specification", "adr", "design", "onboarding", "index"})
_STATUSES = frozenset({"draft", "review", "accepted", "superseded"})

# The front-matter block, only when it opens the file. The schema is
# deliberately flat -- scalars, `null`, and inline lists -- so this is parsed
# here rather than with PyYAML: yaml is present in this dev environment but
# absent from `pms-backend/requirements.txt`, and `scripts/deployment.sh`
# installs a fresh clone from that file. An extractor that works on this
# machine and dies on a clean checkout is worse than one with no front-matter.
_FRONT_MATTER_RE = re.compile(r"\A---[ \t]*\r?\n(.*?)\r?\n---[ \t]*\r?\n", re.DOTALL)
_FM_KEY_RE = re.compile(r"^([A-Za-z_][A-Za-z0-9_-]*):[ \t]*(.*)$")
# A `#` opens a comment only at the start of the value or after whitespace,
# so a title containing one (`# 3 of 9 journeys`) survives.
_FM_COMMENT_RE = re.compile(r"(?:^|\s)#.*$")


def _scalar(raw: str) -> str | list[str] | None:
    value = raw.strip()
    # A quoted scalar is taken whole: inside quotes a `#` is literal, not a
    # comment. Stripping comments first truncated any title that contained one
    # ("Only 1 of 9 journeys reach #done" became "Only 1 of 9 journeys reach").
    if value[:1] in ("'", '"'):
        closing = value.find(value[0], 1)
        if closing != -1:
            return value[1:closing]
    value = _FM_COMMENT_RE.sub("", value).strip()
    if value in ("", "null", "~"):
        return None
    if value.startswith("[") and value.endswith("]"):
        inner = value[1:-1].strip()
        return [p.strip().strip("'\"") for p in inner.split(",") if p.strip()] if inner else []
    return value.strip("'\"")


def parse_front_matter(text: str) -> tuple[dict[str, str | list[str] | None], str]:
    """Split a document into its declared front-matter and its body.

    Returns `({}, text)` unchanged when there is no block, which is the common
    case and must stay the cheap one: most of the corpus will carry no
    front-matter for a long time, and such a document has to remain a
    first-class member rather than quietly dropping out of the index.

    Only top-level `key: value` lines are read. Anything indented belongs to a
    nested structure this schema does not have, and is skipped rather than
    guessed at.
    """
    match = _FRONT_MATTER_RE.match(text)
    if not match:
        return {}, text
    fields: dict[str, str | list[str] | None] = {}
    for line in match.group(1).splitlines():
        if not line.strip() or line[:1] in (" ", "\t", "#", "-"):
            continue
        key_match = _FM_KEY_RE.match(line)
        if key_match:
            fields[key_match.group(1).strip().lower()] = _scalar(key_match.group(2))
    return fields, text[match.end():]


def _declared(fields: dict[str, str | list[str] | None], key: str, allowed: frozenset[str]) -> str:
    value = fields.get(key)
    if isinstance(value, str) and value.strip().lower() in allowed:
        return value.strip().lower()
    return ""


def _doc_type(rel_path: str, fields: dict[str, str | list[str] | None] | None = None) -> str:
    """What a document *is*, preferring its own declaration over its location.

    ODSF-128: the path rule below is a fallthrough, not a classification --
    `design` is what anything outside `docs/` and `.onboarding/` gets by
    default. That made `backlogs/PMS-NEXT-ERA-SPECIFICATION.md`, this project's
    actual product specification, sort last in the BA's injection ranking and
    be the first thing dropped at the cap. A document can now say what it is.

    The fallthrough is kept exactly as it was for every document that declares
    nothing, so this change cannot shrink an existing corpus.
    """
    declared = _declared(fields or {}, "type", _DOC_TYPES)
    if declared:
        return declared
    if rel_path.startswith("docs/adr/"):
        return "adr"
    if rel_path.startswith(".onboarding/"):
        return "onboarding"
    if rel_path.startswith("docs/"):
        # A top-level `docs/*.md` is the project's read-facing specification
        # set -- requirement/technical/test documents and the cross-cutting
        # references beside them. Typed apart from `design` because they are a
        # different altitude: `design/` is per-screen and per-sprint working
        # material, these consolidate it. Both are Spec nodes; only the
        # `doc_type` property distinguishes them, so this adds no node type and
        # no edge verb (ADR-SDP-DEVKB-001's schema gate does not apply).
        return "specification"
    return "design"


def _spec_id(rel_path: str, fields: dict[str, str | list[str] | None]) -> str:
    """The id a ticket's `## Trace` `Specification` row names this document by
    (ODSF-230, ADR-SDP-DEVKB-002 §3 `IMPLEMENTS`).

    The front-matter `id` when the document declares one (`SPEC-ODSF-003`),
    else the filename stem before its first `_` -- the ADR-SDP-SPEC-001 naming
    convention (`SPEC-ODSF-003_<slug>.md`, `ADR-SDP-DEVKB-002_<slug>.md`). A
    property, not a key: the natural key stays the path, so no existing uid moves.
    """
    declared = fields.get("id")
    if isinstance(declared, str) and declared.strip():
        return declared.strip()
    return rel_path.rsplit("/", 1)[-1].removesuffix(".md").split("_", 1)[0]


def _title(text: str) -> str | None:
    m = _HEADING_RE.search(text)
    return m.group(1).strip() if m else None


def _spec_files(ctx: ProjectContext) -> list[str]:
    """The markdown this project calls its specifications.

    ODSF-102: the roots come from the project rather than from this file. They
    used to be three hardcoded globs, which meant a project keeping its specs
    anywhere else was invisible to its own BA -- ODSF's whole specification set
    is under `backlogs/`, so its graph held 2 Spec nodes while OCO, whose layout
    happens to match those globs, held 187.

    A root ending in `/**` is scanned recursively; without it, top level only.
    That distinction is not decoration: `design` was recursive and `docs/adr`
    deliberately was not (its siblings under `docs/` are per-owner working
    areas, not specifications of the system), and a project that declares
    nothing must behave exactly as it did before.

    A declared root that does not exist is skipped, so a config naming a
    directory the project has not created yet does not break the build.
    """
    out: set[str] = set()
    for root in (ctx.spec_dirs or DEFAULT_SPEC_DIRS):
        recursive = root.endswith("/**")
        base = ctx.repo_root / (root[:-3] if recursive else root)
        if not base.is_dir():
            continue
        for path in (base.rglob("*.md") if recursive else base.glob("*.md")):
            if path.is_file():
                out.add(str(path.relative_to(ctx.repo_root)))
    return sorted(out)


def extract(ctx: ProjectContext, graph: DevKBGraph) -> DevKBGraph:
    g = DevKBGraph()
    real_tickets = {t.natural_key for t in graph.nodes("Ticket")}
    ticket_re = re.compile(rf"{re.escape(ctx.ticket_prefix)}-\d+")

    for rel_path in _spec_files(ctx):
        try:
            text = (ctx.repo_root / rel_path).read_text(errors="replace")
        except OSError:
            continue

        fields, body = parse_front_matter(text)
        title = _title(text) or rel_path
        # Hashed over the BODY, not the whole file, so that editing front-matter
        # -- appending a ticket id to `tickets:`, bumping `updated:` -- is not
        # reported as the document's content having drifted. Those edits are
        # bookkeeping about the document; only the body is the document.
        content_sha = hashlib.sha256(body.encode("utf-8", "replace")).hexdigest()[:16]
        g.add_node(
            "Spec", rel_path, source="spec-scan", title=title,
            doc_type=_doc_type(rel_path, fields),
            # "" means the document declares no status, which is not the same
            # as declaring `draft`. Only an explicit `superseded` withdraws a
            # document from the BA's corpus, so silence never excludes anything.
            status=_declared(fields, "status", _STATUSES),
            content_sha=content_sha,
            spec_id=_spec_id(rel_path, fields),
        )

        mentioned: set[str] = set()
        for related_line in _RELATED_LINE_RE.findall(text):
            mentioned.update(ticket_re.findall(related_line))
        mentioned.update(ticket_re.findall(text))

        for ticket_id in mentioned:
            if ticket_id not in real_tickets:
                continue  # a stale/typo'd/renamed mention -- skip, don't guess
            g.add_edge(
                "DOCUMENTS", "Spec", rel_path, "Ticket", ticket_id,
                source="spec-scan", confidence=0.85,
                evidence_ref=f"{rel_path} mentions {ticket_id}",
            )
    return g
