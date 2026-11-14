---
id: ADR-DEVKB-007
title: "ADR-DEVKB-007: pull requests and hosted issues join the graph"
type: adr
status: proposed
created: 2026-11-14
updated: 2026-11-14
owner: Hung T. Le
supersedes: []
superseded_by: null
---

# ADR-DEVKB-007: pull requests and hosted issues join the graph

**Status**: Proposed, awaiting a decision by the owner. It adds one node type and two verbs to `devkb/ontology.md`
and gives two existing verbs a new source. ADR-SDP-DEVKB-001 allows such a change only through an Accepted ADR.
Numbering continues ADR-SDP-DEVKB-001 to 006, recorded before devkb became a standalone component; ADR-SDP-DEVKB-006
is still Proposed and independent of this one.

## Context

devkb's process layer (tickets, epics, specifications, and the commits that implement them) reads tickets from
files in the repository: an `issues/` folder whose ticket ids appear in commit messages, and a `## Trace` table per
ticket. That is how the factory projects work. Almost no other repository works that way: their issues and the
pull requests that implement them live on GitHub, and git history carries only the pull request numbers.

Measured on the benchmark registry (`bench/repos.yaml`, the pinned commits, 2026-11-14):

| Repository | Commits | "Merge pull request #N" subjects | Squash subjects ending "(#N)" | Closing keywords in commit messages ("Fixes #N") | `REFERENCES` edges today |
|---|---|---|---|---|---|
| lattice-scan | 229 | 70 | 55 | 0 | 0 |
| click | 3,413 | 597 | 496 | 152 | 0 |
| lnbits | 7,401 | 548 | 1,888 | 31 | 0 |
| Prefect | 22,492 | 290 | 9,355 | 22 | 0 |
| Netflix Dispatch | 5,279 | 21 | 5,179 | 3 | 0 |
| Mealie | 5,937 | 131 | 4,710 | 147 | 0 |

Three consequences:

1. On every public repository the graph answers no process question: which change a commit belongs to, which issue
   it fixed, which commits a fix consisted of, what else changed with it. The tools that answer them (`trace`,
   `lineage`, `review_pack`, `history`, the ticket pack) return nothing.
2. The paper's process-layer study (pre-registered hypothesis H6, ticket → commits → code → tests) could only use
   the two internal repositories, and its threats to validity say so: "the public ones keep their tickets outside the
   repository". A replication on public repositories needs this ADR.
3. Most of the missing link is already in git. A squash merge or a merge commit names its pull request: 42% of
   Prefect's commits, 79% of Mealie's and 98% of Dispatch's carry the number. The link from a pull request to the
   issue it closes is not: closing keywords appear in few commit messages because they are written in the pull
   request's description.

## Decision

1. **New node type `PullRequest`**: one pull request (GitHub) or merge request (GitLab, later).
   - Natural key `PR-<number>`; a member repository's key is prefixed `<CODE>:` as for files (ADR-SDP-DEVKB-005).
     GitHub numbers issues and pull requests from one sequence per repository, so `PR-137` and an issue `GH-137`
     never both exist.
   - Properties: `number`, `title`, `state` (`open`, `merged`, `closed`), `merged_at`, `base`, `head` (branch names),
     `labels`, `url`, `merge_style` (`merge`, `squash`, `rebase` when known).
   - Not stored: the description text, review comments, and the author. The description is parsed for references
     and dropped, because it can hold personal data or secrets. The author's login is stored only when the repository
     opts in (`"github": {"authors": true}` in `devkb.json`).
2. **Hosted issues are `Ticket` nodes**, not a new type, so every ticket query, tool and pack keeps working.
   - Natural key `GH-<number>` (member-prefixed as above); `source` `github-issues`.
   - `ticket_type` comes from the issue's type where the repository uses issue types, else from labels (`bug` → `BUG`,
     `epic` → `EPIC`, `enhancement`/`feature` → `FEATURE`), else `ISSUE`.
   - Properties: `title`, `state`, `state_reason`, `labels`, `milestone`, `url`, `created_at`, `closed_at`; no body,
     no author (as for pull requests).
   - An epic is an issue whose `ticket_type` is `EPIC` or which has sub-issues; a sub-issue gets `CHILD_OF` to its
     parent, which reuses the existing verb with a new source (`github-sub-issues`).
3. **New verb `MERGES`**, PullRequest → Commit: the commits the pull request brought in.
   - Offline, from git alone: a merge commit whose subject is `Merge pull request #N from <owner>/<branch>`
     (`MERGES` to the merge commit and to the commits it brought in: `git rev-list <merge>^1..<merge>^2`), and a
     squash commit whose subject ends `(#N)`. `source` `git-merge-subject` / `git-squash-subject`, confidence 0.9: a
     subject is text a person can edit.
   - Online (opt-in, item 6): the pull request's commit list from the API, confidence 1.0. This also covers rebase
     merges, which leave no trace in git.
4. **New verb `CLOSES`**, PullRequest → Ticket: the issues a pull request closes.
   - Online only: GitHub's own record of the issues a pull request closes (closing keywords in its description or
     commits, and manual links), confidence 1.0.
   - Offline: a closing keyword in a commit message of a pull request (`Fixes #N`, `Closes #N`, `Resolves #N`) gives
     `CLOSES` at confidence 0.7 with the target marked `unverified: true`, because offline `#N` might be a pull
     request, not an issue. Online confirmation replaces it.
5. **`REFERENCES` gains a source**: a commit message mentioning `#N` that the online layer resolves to an issue
   gives Commit → Ticket (`source` `git-hash-mention`, confidence 0.8). Offline, a bare `#N` produces no edge: it
   cannot be told apart from a pull request, and a wrong ticket link is worse than none.
6. **The online layer is opt-in and local.**
   - `devkb build --github` (or `"github": {"enabled": true}` in `devkb.json`). Never on by default: building a graph
     never touches the network unless asked to.
   - Authentication from `GITHUB_TOKEN` or the `gh` command-line tool's login; the host and repository from the
     `origin` remote.
   - Responses are cached in `.devkb/github/` keyed by each item's `updated_at`, so a rebuild fetches only what
     changed. The cache, like the graph, never leaves the machine and is gitignored by `devkb init`.
   - If the API is unreachable or rate-limited, the build completes with the offline layer, reports what it could not
     fetch, and every affected answer's `coverage` says so.
7. **Tools and packs.** `trace`, `lineage`, `history` and `review_pack` follow `MERGES` and `CLOSES`; the ticket pack
   (`devkb pack ticket GH-123`) lists the pull requests, their commits, the functions they changed and the tests
   that call them. A new pack, `devkb pack pr N`, gives a pull request's commits, changed functions, tests to run and
   the issues it closes. Each states its coverage, including links the offline layer could not verify.

## Alternatives considered

- **Issues as a new node type `Issue`.** Rejected: every ticket tool, query alias and pack would need a second
  code path for the same concept, and the factory's own projects would then have two kinds of ticket.
- **Pull requests as `Ticket` nodes** (`ticket_type` `PR`). Rejected: a pull request is a change set, not a unit of
  intent; it merges commits and closes tickets, and folding it into `Ticket` would make "the tickets this commit
  implements" return change sets.
- **Offline only.** Rejected as the whole answer, kept as the default: it recovers pull requests for most commits but
  almost no issues (the closing keywords are in descriptions, not commits).
- **Online only.** Rejected: a graph must build without network access (air-gapped and client sites), and git
  already holds most of the pull request links.
- **Store descriptions and authors for search.** Rejected by default for the privacy reason in item 1; titles carry
  most of the search value.

## Consequences

- One node type (`PullRequest`) and two verbs (`MERGES`, `CLOSES`) are added; `Ticket`, `CHILD_OF` and `REFERENCES`
  gain sources. Existing graphs, keys and queries are unchanged: a repository without a hosting remote gets no new
  nodes.
- Build time grows with history: offline parsing is one `git log` pass (already done for `TOUCHES`); online
  fetching costs about one API request per 100 pull requests or issues, cached after the first build.
- The process-layer benchmark can run on public repositories: `ticket_code` tasks from closed issues and
  `pr_code` tasks (which functions did pull request N change, which tests call them), with truth from git and the
  API, reported separately from the graph-only truth because the graph reads the same API.
- A new failure mode: a repository that rewrites merge subjects or uses rebase merges gets fewer offline links. The
  coverage statement makes this visible rather than silent.

## Validation (before the ADR is marked implemented)

1. **Offline precision**: on lattice-scan, Mealie and Dispatch, every offline `MERGES` edge is checked against the
   API's commit lists; precision at least 0.98, and the misses listed.
2. **Offline recall**: share of the API's merged pull requests that the offline layer finds, reported per repository
   and merge style; no floor, because rebase merges are invisible offline by design.
3. **Issue links**: on Mealie and click (the registry repositories with the most closing keywords), every online
   `CLOSES` edge matches GitHub's own closing record; every offline `CLOSES` edge that the API contradicts is
   removed on the next online build.
4. **No network by default**: a test builds a repository with a GitHub remote and no flag, with the network
   disabled, and asserts that the build succeeds and makes no request.
5. **Privacy**: a test asserts that no description text, review text, author login or email is written to
   `.devkb/` unless `authors` is enabled.
6. **Pack check**: the benchmark registry gains `pr_code` tasks and their packs score against git truth, as the
   existing kinds do.

## Out of scope

GitLab merge requests and Jira issues (the same node type and verbs would carry them; a separate ADR names their
sources), reviews and review comments, CI check results, and people as nodes (ownership, reviewers), which needs its
own privacy decision.

## Open questions for the decider

1. Should the author login be stored by default for public repositories, where it is already public, or stay
   opt-in everywhere? This draft keeps it opt-in.
2. Should `devkb init` turn the online layer on when it finds a GitHub remote and a `gh` login, or leave it to an
   explicit flag? This draft leaves it explicit.
