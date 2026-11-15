I implemented the ADR-DEVKB-007 Decision section and committed it as `f106349` on `exercise3/adr007-plain`; nothing was pushed. The full suite passes (252 tests, 33 of them new) with no network use. I did not run the manual checks on the public checkouts, so the ADR's Validation section is still open.

**What's in**
- **Node type and verbs:**
  - `PullRequest` (`PR-<n>`) is a new node type, and `MERGES` and `CLOSES` are new verbs. The confidences are as the ADR gives them: 0.9 for git subjects, 0.7 for offline closing keywords marked `unverified`, 1.0 online.
  - Members' keys are prefixed with the member code automatically.
- **Hosted issues:** they are `GH-<n>` Tickets with `ticket_type` taken from the issue type, then labels, then `ISSUE`. An issue with sub-issues and no other type becomes `EPIC`. Sub-issues get `CHILD_OF` with source `github-sub-issues`. Online, a `#N` in a commit message that resolves to an issue gives `REFERENCES` at 0.8.
- **Offline layer:** `devkb/extractors/pull_requests.py` reads merge-commit and squash subjects and closing keywords. A repository with no pull requests gets no new nodes.
- **Online layer:**
  - `devkb/github.py` and `devkb build --github` (or `devkb.json` `github.enabled`) turn it on. It is never on by default.
  - Credentials come from `GITHUB_TOKEN` or the `gh` login.
  - The cache in `.devkb/github/` is keyed by `updated_at`, so a rebuild fetches only what changed. A test confirms `devkb init`'s gitignore covers it.
  - If GitHub can't be reached or rate-limits, the build keeps the offline layer, prints what it couldn't fetch, and records it in the manifest. The `coverage.pull_requests` of affected answers and packs says so.
- **Privacy:**
  - No descriptions, review text or emails are stored, and a test scans `.devkb/` for them.
  - Author logins appear only with `"github": {"authors": true}`.
  - A cache written without logins is discarded when that setting is turned on.
- **Tools and packs:**
  - `trace`, `lineage`, `history`, `review_pack` and `sdlc_context` follow the new edges, and `trace PR-7` and `lineage PR-7` describe a pull request.
  - `devkb pack pr N` is new. The `ticket` pack now lists pull requests and their commits, and `ticket` is now selectable from the CLI.
  - `devkb/ontology.md` and the README are updated.
- **Open questions:** I used the draft's defaults (author logins opt-in, online layer only on explicit request).

**Not done**
- The ADR's Validation section needs live API checks, so I did not mark it implemented and left its status as Proposed. That covers offline precision and recall, `CLOSES` against GitHub's closing record on Mealie and click, and the `pr_code` benchmark tasks.
- I didn't run any build against the lattice-scan, mealie or dispatch checkouts, because those commands needed approval I didn't have. The code is therefore only tested on fixture repositories and the mocked API.
- The mock follows GitHub's REST and GraphQL shapes as I know them. The `parent_issue_url` and `sub_issues_summary` fields in particular are unconfirmed against the real API.
- Rebase merges are only recovered through the pull request's `merge_commit_sha` (the tip commit). The rebased copies of the other commits are not matched to the pull request's original commits.
- I did not add the GitLab or Jira sources, which the ADR puts out of scope.
