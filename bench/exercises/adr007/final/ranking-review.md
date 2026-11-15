# Final blind ranking of the four implementations that passed the acceptance check

Key (revealed after the review): **P = round 3 devkb arm, Q = round 1 devkb arm, R = round 2 plain, S = round 3
plain.** The reviewer saw the ADR and four anonymous diffs, and was told all four had passed the measured acceptance
check, so it should judge what the check cannot see. Line numbers are diff lines.

**Ranking: Q, S, P, R** (about 60% confident in Q first, 70% in R last; S and P close). Decided mainly by what happens
when a fetch fails part-way and a later build resumes from the cache.

## Deviations found

- **P**: a partial fetch is never finished (paging stops at the first unchanged item, the cache is saved after an
  error, and the next build reports `complete: true`); open or closed pull requests get MERGES at 1.0 with no merged
  check; the API's CLOSES are dropped when the issue is not in the issue cache; `PR-N`/`GH-N` can coexist; a
  repository with no remote still gets PullRequest nodes; `history` carries no coverage statement.
- **Q**: closing references from other repositories are not filtered; a stub `GH-n` is created with source
  `github-issues`; a number that is both an offline PR and a fetched issue keeps the false PR; a Bug with sub-issues
  becomes EPIC; `GITHUB_TOKEN` is ignored on Enterprise.
- **R**: the same resume flaw as P, worse: the next build treats the listing as complete and deletes real offline pull
  requests the cache never received; cross-repository closing references not filtered; a pull request with more than
  250 commits loses its offline edges; a GraphQL schema error fails the whole issue fetch.
- **S**: open and closed-unmerged pull requests get MERGES at 1.0; one REST request per pull request for commit lists
  (resumes correctly, and has a request budget); the `PR-N`/`GH-N` collision; offline nodes without a remote check.

## Robustness, tests, maintainability

- Resume after a partial fetch: S correct; Q safe but makes no progress (saves only after a full walk); P silently
  wrong; R wrong and deletes data.
- Tests: Q has the strongest network exclusion (socket, `urlopen`, transport and token patched; its fake returns
  descriptions, logins and e-mails, and it checks the queries never ask for them). Weak tests: P greps source text;
  Q's CLI test asserts `argparse` and one assertion accepts either title; R's assertions use `or`. None tests a
  rebuild after a partial fetch.
- Maintainability: P smallest and closest to the surrounding code; Q largest, touches two existing extractors, has
  dead code and an unverifiable ADR note; R changes an unrelated default; S clean.

## Must fix in Q before merging (all done in the merge, with a test each)

1. Filter closing references to this repository (`repository { nameWithOwner }`).
2. No `github-issues` stub for an issue the listing did not return (now `github-closing-reference`, `fetched: false`).
3. When a number is a fetched issue, drop the offline-only `PR-N`.
4. Catch `GitHubError` per pull request in the commit continuation; save progress per page so a large first build
   resumes.
5. Delete the dead `report.setdefault("status", "failed")`.
6. Replace the grep-style CLI test and the either-title assertion (the latter hid a fixture bug).
7. Remove the unverifiable implementation note from the ADR.
8. (possible) Keep an issue's own type; record `has_sub_issues` for the `epics` alias.
9. (possible) Accept `GITHUB_TOKEN` on Enterprise where CI names that host.
10. (possible) Report merges with more than 1,000 commits instead of linking nothing silently.
11. (possible) A test of a rebuild after a partial fetch.
