I implemented the Decision section of ADR-DEVKB-007 and committed it on `exercise/adr007-plain` as `761e164`. I did not push. The full suite passes (`.venv/bin/python -m pytest tests -q`: 247 passed). The new tests use fixture git repositories and a fake GitHub transport, with socket connections blocked so any network use fails the test.

**What's in:**
- **Graph model:** `PullRequest` (`PR-<n>`) and the `MERGES` and `CLOSES` verbs are in `devkb/model.py` and `devkb/ontology.md`.
- **Offline layer (always on):** `devkb/extractors/pull_requests.py` reads merge-commit and squash subjects.
  - `MERGES` is 0.9. A merge commit links to itself and to the commits it brought in.
  - A closing keyword gives `CLOSES` at 0.7 with `unverified: true`.
  - A bare `#N` gives no edge.
- **Online layer (opt-in):** `devkb/github.py` is enabled by `devkb build --github` or `{"github": {"enabled": true}}`.
  - It reads issues, pull requests, commit lists, closing links and sub-issues.
  - Online links are 1.0, and offline links GitHub contradicts are removed.
  - Issues become `GH-<n>` tickets with `ticket_type`, `CHILD_OF` for sub-issues, and `REFERENCES` at 0.8 from commit mentions.
  - Responses are cached in `.devkb/github/cache.json`, keyed by `updated_at`, so a rebuild fetches only what changed.
  - If GitHub is unreachable or rate-limited, the build finishes offline. It records what failed in the manifest and prints it. Answers carry the same note in `coverage`.
- **Privacy:** descriptions, review text and emails are never stored. Author logins are stored only with `github.authors` on, and turning it off clears them from the cache.
- **Tools and packs:** `trace`, `lineage`, `sdlc_context`, `history` and `review_pack` follow the new edges. There is a new `pull_request` MCP tool, `devkb pack pr N`, and `devkb pack ticket GH-n`. I updated the README, the CLI help and the review skill, since an existing test requires every MCP tool to appear in a skill.
- **Open questions:** both use the draft's defaults (author logins opt-in, online layer only on request).

**Checks on real checkouts:**
- lattice-scan, offline: 70 merge-style and 55 squash pull requests, matching the ADR's counts.
- A 12-pull-request sample compared with `gh api` commit lists: all 18 offline `MERGES` edges were in GitHub's lists (precision 1.0).

**Not done or different from the ADR:**
- I did not run the ADR's full validation. That means precision on Mealie and Dispatch, per-style recall, `CLOSES` checks on Mealie and click, and the `pr_code` benchmark tasks.
- I never ran the online layer against real GitHub, only against the fake transport.
- `merge_style` is only `merge` or `squash`. Online-only pull requests, including rebase merges, get no style, because I found no reliable signal for it.
- Closing links need a token (`GITHUB_TOKEN` or a `gh` login), because they come from GraphQL. Without one, the REST data is still fetched and the closing links stay offline and unverified.
- `GITHUB_TOKEN` is sent only to github.com. Other hosts use their `gh` login.
- The offline layer works even with no `origin` remote, so a "(#N)" subject in a non-GitHub repository would create a `PullRequest`. The ADR's "no hosting remote gets no new nodes" line could be read as ruling that out.
- When several commits share a squash number, such as backports, only the earliest links to the pull request.
- Existing `Commit` nodes still carry git author names. That is existing behaviour, not a GitHub login, and I left it alone.
