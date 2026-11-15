I implemented the ADR-DEVKB-007 Decision section and committed it on `exercise2/adr007-plain` (`5662eb6`, not pushed). `.venv/bin/python -m pytest tests -q` gives 252 passed: the 218 that were already there plus 34 new ones. The new tests use fixture git repositories and a fake GitHub transport, and they fail if anything reaches the network.

**What's in**
- **Model:** the `PullRequest` node and the `MERGES` and `CLOSES` verbs, as the ADR specifies. `devkb/ontology.md` documents them, and `README.md` has a short note.
- **Offline layer (always on):**
  - One `git log` pass finds pull requests from `Merge pull request #N` and `(#N)` squash subjects. They produce `MERGES` edges at 0.9, including the commits a merge brought in.
  - A closing keyword (`Fixes #N` and similar) in those commits gives `CLOSES` at 0.7. The edge and the target `GH-N` ticket are marked `unverified`.
  - A bare `#N` gives no edge.
- **Online layer (opt-in):**
  - It is switched on by `devkb build --github` or `{"github": {"enabled": true}}`, and it uses `GITHUB_TOKEN` or the `gh` login. It reads pull requests and issues through GitHub's GraphQL API and caches them in `.devkb/github/`, keyed by `updated_at`.
  - For each pull request it covers, GitHub's data replaces the offline edges, so an offline `CLOSES` that GitHub does not confirm disappears. Rebase merges become visible.
  - If GitHub can't be reached or is rate-limited, the build still completes from git alone. The failure is written to `manifest.json` and shown in the `coverage` of affected answers.
- **Issues as tickets:** `GH-<n>` `Ticket` nodes with `ticket_type` from the issue type, then labels, then `ISSUE`. A parent with sub-issues becomes `EPIC`, and sub-issues get `CHILD_OF`. Commit messages that mention `#N` for a known issue give `REFERENCES` at 0.8.
- **Privacy:** descriptions, reviews and comments are never requested from the API. Author logins are requested and stored only with `"github": {"authors": true}`. Turning that setting off discards the cached copy.
- **Tools and packs:**
  - `trace`, `lineage`, `sdlc_context`, `history` and `review_pack` now follow `MERGES` and `CLOSES`.
  - The ticket pack lists the pull requests.
  - `devkb pack pr N` is new, and `devkb pack ticket ID` is now reachable from the command line.
  - `devkb pack` now defaults `--project` to `.`.
- **Open questions:** author logins stay opt-in, and the online layer runs only on explicit request, as the draft says.

**Manual checks, read-only**
- On lattice-scan, I built offline and then with `--github`. All 217 offline `MERGES` edges were confirmed by GitHub's commit lists, and the offline layer found 125 of the 126 pull requests GitHub reports (PR-91 was missed).
- Dispatch built offline in 15 seconds and found 1,838 pull requests.
- The pinned checkouts were not modified.

**Not done**
- Validation items 1–3 are only partly run. I did the offline precision and recall check on lattice-scan. I did not do Mealie or Dispatch against the API, the click and Mealie `CLOSES` check, or the per-merge-style breakdown.
- Validation item 6 is not done. I did not add `pr_code` tasks to the benchmark registry.
- The ADR's status is still `proposed`.
- I added no new MCP tool for pull requests. The existing tools carry the data, and the pack is the new entry point.
- `merge_style: rebase` is never set, because git and the API don't reveal it reliably.
- The ADR says online fetching costs about one request per 100 items. Pull requests with more than 100 commits cost an extra request each.
