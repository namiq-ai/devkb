I implemented the ADR's Decision section and committed it on `exercise2/adr007-devkb` as `15473a1`; nothing is pushed. The full suite passes (`.venv/bin/python -m pytest tests -q`: 255 passed, including 37 new tests). The online layer has only run against the mocked API in tests, never against live GitHub.

**What is in**
- **Graph model:** the `PullRequest` node (`PR-<n>`) and the `MERGES` and `CLOSES` verbs, with the properties, sources and confidences the ADR gives. Hosted issues are `Ticket` nodes (`GH-<n>`), with `ticket_type` from the issue type, then labels, then `ISSUE`. Sub-issues give `CHILD_OF` (`github-sub-issues`), and `REFERENCES` gains `git-hash-mention` at 0.8.
- **Offline layer:** it parses merge-commit and squash subjects. It reads closing keywords as `CLOSES` at 0.7 with `unverified` set, and bare `#N` mentions make no edge.
- **Online layer (opt-in):** `devkb build --github` or `{"github": {"enabled": true}}` turns it on. Token comes from `GITHUB_TOKEN` or `gh`.
  - **Cache:** responses are cached in `.devkb/github/` keyed by `updated_at`, so a rebuild fetches only what changed. The cache is discarded if the repository or the `authors` setting changes.
  - **Reconciliation:** online data confirms offline `MERGES` edges at 1.0 and removes offline `CLOSES` edges that the API contradicts.
  - **Failure handling:** if GitHub is unreachable or rate-limited, the build completes offline. It prints what failed, writes it to `manifest.json`, and the affected answers carry a `coverage` note.
- **Privacy:** descriptions, review text, commit authors' emails and author logins are never written. Logins are stored only with `{"github": {"authors": true}}`.
- **Tools and packs:** `trace`, `lineage`, `history` and `review_pack` follow `MERGES` and `CLOSES`. `devkb pack pr N` and `devkb pack ticket GH-N` are new CLI commands. `devkb/ontology.md` and the README are updated.
- **Open questions:** I used the draft's defaults (author logins opt-in, online layer only on request).
- **Real-repo check:** an offline build of the pinned lattice-scan checkout, written to a directory outside it, gave 125 pull requests (70 merge-commit plus 55 squash), matching the ADR's table.

**Choices the ADR left open**
- The offline layer only runs when the repository has a hosting remote. I took this from the ADR's line that a repository without one gets no new nodes. A local-path remote does not count.
- Hosted tickets also carry an upper-case `status` property so the existing ticket tools keep working. A `GH-` issue with sub-issues counts under the `epics` alias.
- `merge_style` is `rebase` only when the merge commit's subject equals the pull request's last API commit subject. Otherwise it stays unset.

**Not done**
- The ADR's six validation measurements (offline precision and recall, issue links against GitHub's record, `pr_code` benchmark tasks) are not run, so the ADR status stays `proposed`.
- I did not run the online layer against live GitHub. I checked the response shapes it parses with a read-only `gh api` call on lattice-scan; they match what the code expects.
- GitLab and Jira sources are out of scope, as the ADR says.
- I did not add a new MCP tool for pull requests; the existing tools carry the new fields.
