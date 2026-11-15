# Round 2 blind review

Key (revealed after the review): **A = plain arm, B = devkb arm** (the labels were swapped from round 1). The reviewer
saw only the ADR and two anonymous diffs. Line numbers are diff line numbers.

## Decision items

| Item | A | B |
|---|---|---|
| 1 PullRequest node | complete: properties 339–341, 356–357; author only on opt-in (561); member prefix (1779); `merge_style` is never set to `rebase` (336–338) | complete: properties 359–360, 388–393; rebase inferred (303–315); author only on opt-in (645) |
| 2 Hosted issues as Ticket | complete with a small gap: key GH-N, source `github-issues`, `ticket_type` rules (313–316, 569–577); CHILD_OF (320); only an `ISSUE` with sub-issues becomes EPIC (311), so a BUG with sub-issues is not an epic | complete: a `has_sub_issues` flag (292) feeds the epics alias (1257); CHILD_OF (427) |
| 3 MERGES | complete: merge commit plus `rev-list ^1..^2` (246–251), squash (252), 0.9; online 1.0 (342–345); the API replaces offline edges for the pull requests it covers | complete: offline 245–267, online 394–398; offline edges the API does not confirm stay at 0.9 |
| 4 CLOSES | complete: online 347–351; offline 0.7 `unverified` (361–369); the keyword regex handles lists such as `#8, #9` (186) | partial: the offline regex captures one number per keyword (175); contradicted links are removed (379–384, 399–400) |
| 5 REFERENCES | complete: only when the online layer has issue numbers (372–379) | complete (404–409, 429–433) |
| 6 Opt-in, local online layer | partial: opt-in (76–79, 470–474), cached and self-gitignored (655), failure degrades to offline (80–84); the cache cannot resume after a partial fetch (A1) | partial: opt-in (322–323, 347); the request pattern does not finish on a large repository (B1) |
| 7 Tools and packs | complete: trace, lineage, history, review_pack, sdlc_context, ticket and pr packs (865–966, 1084–1179); coverage stated in each | complete: trace, lineage, history, review_pack, both packs (978–1049, 1134–1213) |
| Privacy | complete: the GraphQL query never asks for body, comments or reviews (514–533); the cache is discarded when `authors` changes (647) | complete: responses reduced on arrival (638–661); the cache is checked against the repository and the `authors` setting (685) |
| No network by default | complete (77–79) | complete (347–348) |

## Defects in A

- A1 (certain, 699 with 298): on a rebuild, paging stops at the first page in which nothing changed. If an earlier
  build was rate-limited at page k, the next sees page 1 unchanged and stops, reports `prs_complete = True`, and drops
  every offline pull request missing from the incomplete cache. The cache has no "listing finished" marker.
- A2 (possible, 347): CLOSES is created for open, unmerged pull requests (the test at 1507 asserts an open PR closes
  an issue): "will close", not "closes".
- A3 (possible, 515–524): `issueType`, `parent` and `subIssues` are in one query; on a GitHub Enterprise instance
  without those fields the whole issues layer fails.
- A4 (certain, tests 1477, 1658): both assertions use an `or` fallback that makes them near-tautologies.

## Defects in B

- B1 (certain, 734, 742, 751): one REST request per pull request for its commits; 10,000 pull requests need more than
  10,000 requests against a 5,000/hour limit. When the commit loop fails, `closing_issues` is skipped for the whole
  batch, every pull request fetched in that build is dropped from the cache, and the next build repeats the work: on a
  large repository the cache never fills.
- B2 (certain, 714, 764): the full pull-request and issue lists are fetched on every build with no early stop; the
  `/issues` list also returns pull requests, roughly doubling its pages.
- B3 (certain, 175): "Closes #8, #9" yields only #8.
- B4 (possible, 807): with no token the client goes ahead unauthenticated (60 requests/hour) instead of reporting
  missing credentials.
- B5 (possible, 230, 418, 430): B creates its own Commit nodes, with `author`, from `git log --all` with no `--since`
  window; A links only to commits already in the graph (325).
- B6 (certain, 835–843): `discard_edges` and `discard_node` are never used.
- B7 (possible, 1139, 1170, 1213): `out["coverage"] = {dict}` replaces any existing coverage value and changes its type.
- B8 (possible, 623): the GraphQL query interpolates owner and repository instead of using variables.

## Tests and code

- **A** covers merge, squash, rebase and issue-number-as-subject fixtures, paging two at a time, the incremental fetch
  with a request count (1541), commit pagination beyond 100, partial, unreachable and no-credential failures, privacy
  across all of `.devkb` including the query text (1622), the authors opt-out purging the cache, every tool and pack,
  and the CLI. Its network guard replaces `make_transport`, `urlopen` and `find_token` but does not block sockets.
  Missing: a rebuild after a partial fetch, where A1 lives. Keeps the extractor and the client separate, reuses the
  build's Commit nodes, small changes to existing code, a bulk GraphQL query (about one request per 100 pull requests).
- **B** has the stronger network guard (`socket.connect` blocked; the no-flag test spies on `subprocess` to prove `gh`
  is never run) and tests privacy including commit text and e-mail (1491), removal of contradicted CLOSES and stub
  tickets, a stale cache standing in when the API is down, and rebase inference. Missing: a multi-number closing list,
  pagination beyond one page, any request-volume check; the mid-build rate-limit test (1723) misses B1. Readable, with
  a cleaner `github_config` and the epic alias, but dead code, a per-PR REST design and its own Commit nodes.

## Judgement

A satisfies the ADR better, at about 75% confidence: A fetches 100 pull requests per GraphQL request with commits,
labels and closing references inline, while B issues one REST request per pull request and cannot make progress once
rate-limited (B1); A parses closing lists, B drops every number after the first (B3). B is stronger on the test
network guard, rebase inference and epic handling. A's resume defect (A1) appears only after a partial fetch; B's
failure is structural on any large repository.
