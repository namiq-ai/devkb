ADR-DEVKB-007's Decision section is implemented and committed on `exercise3/adr007-devkb` as 793202d. The full suite passes (246 tests, `.venv/bin/python -m pytest tests -q`). I did not push.

**What I implemented**
- **Graph vocabulary:** the `PullRequest` node (`PR-<n>`) and the `MERGES` and `CLOSES` verbs, with the ADR's properties, sources and confidences.
- **Offline layer (always on):**
  - `devkb/extractors/pull_requests.py` reads `Merge pull request #N from …` commits and `(#N)` squash subjects, giving `MERGES` at 0.9.
  - A closing keyword in those commits gives `CLOSES` at 0.7 with `unverified: true` on the edge and on a stub `GH-N` ticket.
  - A bare `#N` produces no `REFERENCES` edge offline.
- **Online layer (opt-in):**
  - `devkb/github_api.py` is the client and cache, switched on by `devkb build --github` or `{"github": {"enabled": true}}`.
  - Hosted issues become `Ticket` nodes `GH-<n>` with `ticket_type` and sub-issue `CHILD_OF`.
  - API commit lists give `MERGES` at 1.0, GitHub's closing references give `CLOSES` at 1.0, and `#N` mentions that resolve to issues give `REFERENCES` at 0.8.
  - For a pull request whose closing references the API returned, they replace the offline `CLOSES` guess. When the API's commit list is complete, it also drops any offline `MERGES` edge it doesn't contain.
  - The cache lives in `.devkb/github/`, keyed by `updated_at`, so a rebuild stops at the first unchanged item.
- **When GitHub is unreachable or rate-limited:** the build still completes from the offline layer plus the cache. The failures go to stderr and `manifest.json`, and answers say so in a `hosting` line or the pack's Coverage section.
- **Privacy:** only an allow-listed set of fields is cached or stored. Descriptions, review text and emails never are. Author logins are stored only with `"github": {"authors": true}`, and a cache written with them is scrubbed on the next build without it. Branch names drop the owner.
- **Tools and packs:**
  - `trace`, `lineage`, `sdlc_context`, `history` and `review_pack` follow `MERGES` and `CLOSES`.
  - There is a new `pull_request` tool, in the `core` and `all` toolsets (the MCP test now expects 25 tools).
  - `devkb pack pr N` is new, and `devkb pack ticket GH-n` now works from the command line and goes through the closing pull requests.
  - The `epics` query alias also matches issues that have sub-issues.
- **Docs and tests:**
  - `ontology.md` is updated, and so are the `devkb-sdlc` skill line and the `devkb build` and `devkb pack` help text in `cli.py`.
  - The new tests are in `tests/test_devkb_pull_requests_adr007.py`: a fixture git repo, a mocked API, and sockets blocked in every test. They cover offline recovery, the online layer, caching, failure modes, privacy, the tools and the packs.

**Not done or worth knowing**
- **Manual checks on the pinned checkouts:** I did not run them. The command to run the extractor on lattice-scan and dispatch needed approval and wasn't granted, and I made no `gh api` calls.
- **Validation items 1–3 and 6:** these need real API data (offline precision and recall against the API, issue-link checks on Mealie and click), so they are not done. The benchmark `pr_code` tasks are also not added; the ADR lists them under validation, not Decision.
- **Closing references need a token:** commit lists and closing references use GraphQL, which requires `GITHUB_TOKEN` or a `gh` login. Without one, only issue and pull request records are fetched, and the manifest says so.
- **Rebase merges:** `merge_style` is set only to `merge` or `squash`, never `rebase`, because rebase merges can't be told apart offline.
- **Pre-existing commit subjects:** existing `Commit.subject` values (from earlier extractors) still contain the owner in a merge subject. I left that behaviour alone; the new PR and issue nodes and edges don't.
- **MCP tool sets:** I did not add `pull_request` to `lean` or `dev`, which were measured sets. The pack covers that case.
