I implemented the Decision section of ADR-DEVKB-007 and committed it on `exercise/adr007-devkb` (`c136e5a`, not pushed). `.venv/bin/python -m pytest tests -q` gives 250 passed. All GitHub calls in the tests go through a fake transport.

I did not run the ADR's Validation items 1–3 and 6 in full: the offline precision and recall report, `CLOSES` against GitHub's closing record, and the `pr_code` benchmark tasks. The only real-API check was a read-only spot check on lattice-scan. All 19 offline `MERGES` edges from the first 12 pull requests were in GitHub's commit lists. A scan of the lattice-scan checkout found 125 pull requests, matching the ADR's table (70 merge plus 55 squash).

What now exists:
- **Node type and verbs:** `PullRequest` (`PR-<n>`) with the ADR's properties, plus `MERGES` and `CLOSES`. Confidences are 0.9 for git subjects, 0.7 and `unverified` for offline closing keywords, and 1.0 from GitHub. I also store `merge_commit` on the pull request, which the ADR does not list.
- **Offline layer:** always on, from one `git log` pass. It only applies when `origin` is a GitHub host, and it uses the same 3-year window as the commit baseline.
- **Online layer:** opt-in via `devkb build --github` or `{"github": {"enabled": true}}`; I added `--no-github` to override the config. It uses GitHub's GraphQL API, with a cache in `.devkb/github/` keyed by `updated_at`. A token-less, unreachable, rate-limited or unauthorized build still finishes with the offline links and the cache, prints what it missed, and records it in the manifest.
- **Issues:** `Ticket` `GH-<n>` with `ticket_type` from the issue type, then labels, then `ISSUE`, and sub-issue `CHILD_OF`. Online, a commit message `#N` that resolves to an issue gives a `REFERENCES` edge at 0.8.
- **Privacy:** only a whitelist of fields is stored, and author logins only with `"github": {"authors": true}`.
- **Tools and packs:** `trace`, `lineage`, `history` and `review_pack` follow the new verbs and add a `coverage` saying what was not verified. `devkb pack pr N` is new, and `devkb pack ticket ID` is now reachable from the CLI. There is also a `pull_request` method on `ProcessAPI`, but I did not add it as an MCP tool.
- **Docs:** `devkb/ontology.md` and the README are updated, and the ADR has an implementation-notes section.

Choices the ADR did not spell out:
- Commit subjects of the form `Merge pull request #N from owner/branch` are now stored without the owner, unless `authors` is on. The owner is a login, and the existing commit extractors would otherwise have written it into `.devkb/`. This changes stored subjects for any repository with such merges.
- Commit `author` fields still hold the git author name, as before.
- The ADR does not name the API. I used GraphQL because it gives about one request per 100 items and is the only place GitHub exposes its closing references.

I could not delete `<exercise>/manual-out`, which my manual check left behind, because the shell asked for approval. It sits outside the repo, so please remove it.
