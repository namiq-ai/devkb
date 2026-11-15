# Round 1 blind review

Key (revealed after the review): **A = devkb arm, B = plain arm.** The reviewer saw only the ADR and two anonymous
diffs. Line numbers are diff line numbers.

## Implementation A

| Item | Verdict | Evidence |
|---|---|---|
| 1 PullRequest node | complete | key, properties and source 289–303; the merge subject's owner is dropped (231); authors stored only on opt-in (684, 298); a closing-keyword target that is a pull request is skipped (337), so `PR-n` and `GH-n` stay disjoint; member prefixing tested (2006–2008) |
| 2 Issues as Tickets | complete | tickets 275–281, ticket type 689–703 (sub-issues give EPIC), CHILD_OF from `github-sub-issues` 282–286 |
| 3 MERGES | complete | merge subjects plus `rev-list ^1..^2` (226–232), squash (233–238), confidence 0.9; online edges at 1.0 (308–318); the API's complete list removes contradicted offline edges (321) |
| 4 CLOSES | complete | online 329–334; offline at 0.7 with `unverified` (335–346) |
| 5 REFERENCES | complete | online only, 0.8, pull-request numbers excluded (349–355) |
| 6 Online layer | complete | opt-in (500–506, 374), `--no-github` (96); token from `GITHUB_TOKEN` or `gh` (566–577); cache keyed by `updated_at` (791–814); failures reported in the manifest and in coverage (829–904, 1203–1222) |
| 7 Tools and packs | mostly complete | trace, lineage, history, review_pack, ticket pack, pr pack (1274–1363, 1080–1149); the `pull_request` tool is in TOOL_ARGS only (1372), not in the MCP server |
| No network by default | complete | 374–375, test 1663–1677 |
| Privacy | complete | the queries never request bodies (614–651); the cache holds only a whitelist (673–686) |

Defects:
- 1981 (certain): the "offline" ticket-pack check reuses the graph just built online, so it never tests offline.
- 1992–1997 (certain): the CLI "test" only searches the source for `--github`; it never parses arguments.
- 623, 330–333 (possible): `closingIssuesReferences` asks only for `number`, so a cross-repository closing reference
  becomes this repository's `GH-n`.
- 213 (possible): a merge bringing in more than 1,000 commits silently loses them all; coverage does not say so.
- 299–302 (possible): a pull request seen only online never gets a `squash` or `rebase` merge_style.
- 551 (possible): any host containing "github" counts as GitHub.

## Implementation B

| Item | Verdict | Evidence |
|---|---|---|
| 1 PullRequest node | partial | properties 315–337, authors opt-in (574–576); but offline a `Fixes #N` naming a pull request still creates `GH-N` (310–313, 379–382; the test at 1456 asserts it); the raw merge subject, including the owner's login, is stored (374) |
| 2 Issues as Tickets | complete | tickets 384–389, ticket type 286–293, CHILD_OF 393–396; an issue with sub-issues is flagged `epic: true` and the `epics` alias widened (1228) |
| 3 MERGES | complete | offline 251–282, online 339–346 with contradicted edges removed; rebase merges tested (1604) |
| 4 CLOSES | complete | online 347–353 (needs a token, 732–735); offline 0.7 `unverified` (310–313) |
| 5 REFERENCES | complete | 363–366 |
| 6 Online layer | partial | opt-in 768–771, cache 606–627, failure report 714–759; no `--no-github`; one REST request per merged pull request (678–688), against the ADR's "about one request per 100" |
| 7 Tools and packs | complete | 1058–1205, 929–966, plus a registered MCP tool (781, 793–796); the `pr` pack computes changed functions over the pull request's net range (1129–1143) |
| No network by default | complete | 323, test 1693–1704 |
| Privacy | mostly complete | reduces what it stores (579–597) but not what it requests: REST replies carry bodies |

Defects:
- 310–313 and 1456 (certain): `PR-5` and `GH-5` can both exist offline, which item 1 forbids.
- 299–302 and 1447–1450 (certain): a repository with no remote still gets PullRequest nodes; the ADR says it gets none.
- 678–688 (certain): one request per pull request; Prefect's ~9,600 pull requests exceed the 5,000/hour limit on the
  first build.
- 340–344 (possible): the API returns at most 250 commits per pull request; a truncated list is treated as complete,
  which deletes valid offline edges.
- 374 (possible): the login in `Merge pull request #N from owner/branch` is stored.
- 580–581 (possible): `parent_issue_url` is matched on the number only, so a parent in another repository can produce
  a wrong CHILD_OF.
- 538 (possible): query parameters are not URL-encoded.

## Tests and code

- **A** fakes the transport in every online test and blocks the socket, `urlopen` and the token lookup in the
  default-build test, but not in every test. Its privacy test is stronger: the queries never ask for body, login or
  e-mail (1872), and the fork owner is not stored. It covers the schema fallback, partial failure, a stale cache and
  member prefixes. Weak: the tests at 1981 and 1992. Larger (`github.py` 477 lines); a GraphQL design that is harder
  to follow but efficient (commits, labels and closing references in one paginated query, with a schema fallback);
  touches two existing extractors.
- **B** blocks the socket for every test (1342–1348), runs both CLI `main()` functions (1731–1736), and tests rebase
  merges, rate-limit retry, cross-repository closing filters and a backport. No member-prefix test; one test enshrines
  the GH/PR collision (1456). Cleaner and a better fit with the surrounding code (MCP tool, query alias, skill note,
  `graph_status`, `review_pack` over the pull request's range), but its REST-per-PR design does not scale.

## Judgement

A fits the ADR better, at about 65% confidence: B breaks item 1's rule that `PR-n` and `GH-n` never both exist
offline (a test asserts the violation; A enforces it at 337); B's online layer needs one request per pull request and
breaks on large repositories, while A needs about one per 100; A holds the privacy line more tightly and keeps
repositories without a GitHub remote free of new nodes. B is ahead on MCP integration, the every-test network block
and cross-repository filtering.
