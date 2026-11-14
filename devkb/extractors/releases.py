"""Release-tag extractor (devkb BL-2, body/legs model).

The one process-log sub-signal that's actually recoverable without a ticket
system: `git tag` already records "this commit was a release," for real,
cheaply, independent of tickets/commits-clustering/everything else in this
package. Real data throughout -- source="git-tag", no inference involved.
"""
from __future__ import annotations

from pathlib import Path

from devkb.extractors.tickets_git import _run
from devkb.model import DevKBGraph
from devkb.project_context import ProjectContext


def _list_tags(repo_root: Path) -> list[str]:
    out = _run(["git", "tag", "--list"], repo_root)
    return [t for t in out.splitlines() if t.strip()]


def _tag_commit(tag: str, repo_root: Path) -> str | None:
    out = _run(["git", "rev-list", "-n", "1", tag], repo_root)
    sha = out.strip()
    return sha or None


def _tag_date(tag: str, repo_root: Path) -> str:
    # %(creatordate:short) covers both annotated and lightweight tags --
    # `git log -1 <tag> --format=%ad` would report the TAGGED COMMIT's own
    # date, not when the tag itself was created, which is the wrong question
    # for "when was this released."
    out = _run(["git", "for-each-ref", f"refs/tags/{tag}", "--format=%(creatordate:short)"], repo_root)
    return out.strip()


def extract(ctx: ProjectContext) -> DevKBGraph:
    g = DevKBGraph()
    for tag in _list_tags(ctx.repo_root):
        commit = _tag_commit(tag, ctx.repo_root)
        if commit is None:
            continue  # a tag git itself can't resolve -- skip, don't guess
        g.add_node("Release", tag, source="git-tag", tagged_at=_tag_date(tag, ctx.repo_root))
        g.add_node("Commit", commit, source="git-tag")
        g.add_edge(
            "TAGS", "Release", tag, "Commit", commit,
            source="git-tag", confidence=1.0, evidence_ref=f"git tag {tag}",
        )
    return g
