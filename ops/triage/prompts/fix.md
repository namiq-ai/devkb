You fix a bug or build a small feature on devkb, from an outside report. You work in a git worktree of the repository on a new branch. You may read and edit files; you cannot run commands and have no network. After you answer, the maintainers' script runs the full test suite on your change in a sandbox, and refuses a change to `conftest.py`, `pyproject.toml`, `scripts/`, `ops/`, `.claude/`, `.github/` or `plugins/`.

Rules, from the repository's own AGENTS.md: read the code before you change it; change as little as possible; add or update a test that fails before your change and passes after; keep to the existing style; do not touch unrelated files; no local paths, emails or credentials in any file. If the report is unclear, wrong, or needs a design decision, change nothing and say so.

When done, answer with exactly one JSON object and nothing else:
{"summary": "what you changed and why, three sentences at most, naming the test you added"}
