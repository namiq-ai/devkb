# devkb ontology (ADR-SDP-DEVKB-001)

Governed node types and edge verbs for the dev-process knowledge graph. Changing
this file (add/remove/rename a node type or edge verb) requires an Accepted ADR
(amendment to `ADR-SDP-DEVKB-001`, or a new `ADR-SDP-DEVKB-NNN`) filed **before**
the implementing PR is merged — see `CLAUDE.md`'s Forbidden Actions.

This is a deliberately small, dev-process-specific vocabulary — not a fork of
OCO's 55-type/21-verb cyber-threat-intel ontology (`ADR-SDP-FACTORY-EXTRACTION-001`
judged that graph domain-coupled and non-reusable), and not an extension of
`discovery/`'s 5-type component-architecture graph (`discovery/ontology.md` scopes
itself to source structure only, by design non-goal to extend).

## Node types

| Type | Meaning | Natural key | Primary source | Phase |
|---|---|---|---|---|
| `Ticket` | one issue; a hosted GitHub issue is also a `Ticket` (ADR-DEVKB-007) | ticket id, e.g. `ODSF-021`; hosted: `GH-<number>` (member: `<CODE>:GH-<number>`) | `issues/*.md` filename + body; hosted: the GitHub issues API (opt-in), `source` `github-issues` | 1 |
| `Commit` | one git commit | full 40-char sha | `git log` | 1 |
| `WorkPackage` | one work package | WP id | `PROJECT_BOARD.md` + `wp-map.json` | 1 |
| `Milestone` | one milestone | milestone name | `PROJECT_BOARD.md` milestone summary | 1 |
| `File` | one repo-relative path | path | `git diff-tree`, compliance evidence | 2 |
| `TestCase` | one test function (ADR-SDP-DEVKB-003; was: only a test referencing a ticket); carries `ticket` when marked | `path:line` | `@pytest.mark.ticket`/grep | 2 |
| `Warning` | one compliance/gate finding (open or resolved -- see `status`/`resolved_at` properties) | `sha256(rule+detail+evidence)` (widened from `rule+evidence` alone -- some rules' `evidence` is fixed boilerplate, `detail` is what actually varies per violation) | `dev_compliance_monitor.py --json-report` | 3 |
| `Symbol` | one function/class/method, below `File` granularity | `path::qualified_name` | `ast` decomposition (`devkb/build_symbols.py`, standalone refresh) | BL-3 |
| `Release` | one git tag | tag name | `git tag --list` | BL-2 |
| `WorkUnit` | a probable unit of work inferred from same-day/same-author/file-overlap commit clustering -- **never a `Ticket`**, always `source="commit-cluster-inference"`, `confidence=0.5` | `sha256` of member commit shas | `extractors/work_units.py` | BL-6 |
| `Endpoint` | one API route | `METHOD path` (matches `discovery/`'s own convention) | FastAPI and Odoo `@http.route` decorator AST capture (`devkb/build_symbols.py`; Odoo: ADR-SDP-DEVKB-003) | BL-7 |
| `Component` | one deployable service, per `12-sys-arch.pdf`'s definition ("implementation of" a Subsystem) | `Service.natural_key`, identical to `discovery/`'s own | mirrors `discovery/`'s already-built `Service` nodes (`.onboarding/graph.json`) | BL-8 |
| `Subsystem` | one logical grouping a Component realizes | `pms.config.json`'s own `subsystems[].key` | `pms.config.json` directly | BL-8 |
| `Flow` | one fully-automated call chain from a detected touch point (`endpoint`/`ui_handler`/`scheduled`/`daemon_entry`, see `devkb/SOT.md` Part 5.4) | `flow:<kind>:<start_symbol>` | mechanical BFS over real `CALLS`/`CALLS_API` edges (`extractors/flows.py`) -- never curated | BL-12 |
| `ErrorSignature` | one statically-detectable error a Symbol's own body can raise or log (**not** the same as `Warning`, which is process/compliance, not source-derived) | `sha256(kind+label+message_template)` | `ast.Raise` and recognized `logger.<level>(...)` calls (`devkb/build_symbols.py`) | BL-9 |
| `Spec` | one design doc / ADR / onboarding artifact | path | `docs/adr/`, `design/`, `.onboarding/*.md` | BL-13 |
| `Requirement` | one PMS requirement | `REQ-NNN` | PMS requirements store; ticket `## Trace` `Requirement` row | BL-14 (ADR-SDP-DEVKB-002) |
| `Evidence` | one evidence record (REA `ev_…` or ODSF `of_…`), `confidence` as recorded, never upgraded | `evidence_id` | evidence packs `.onboarding/evidence/<EVP>/` | BL-14 (ADR-SDP-DEVKB-002) |
| `Repository` | one registered project's repository, the product's own or a declared member's (ADR-SDP-DEVKB-005) | project code, e.g. `OCO`, `LTCS` | `projects.json` + the product's `pms.config.json` `graph.members` | ODSF-312 |
| `ConfigKey` | one named setting: an environment variable, or a root `pms.config.json` top-level key (`pms.config.json:<key>`); **its value is never stored**; never prefixed with a member's code | the name | `extractors/configuration.py` | ODSF-312 |
| `PullRequest` | one pull request (GitHub; GitLab merge requests later). A member repository's key is prefixed `<CODE>:`. Properties: `number`, `title`, `state` (`open`/`merged`/`closed`), `merged_at`, `base`, `head` (branch names, no owner), `labels`, `url`, `merge_style` (`merge`/`squash`, `rebase` when known), and `merges_source`/`closes_source` (what its links rest on). **Not stored:** description, review comments, author — the author's login only with `"github": {"authors": true}` in `devkb.json` | `PR-<number>` | offline: `Merge pull request #N from …` and `… (#N)` commit subjects (`git log`); online (opt-in): the GitHub API | ADR-DEVKB-007 |

`Epic` and `Story` are **not** separate types: they are `Ticket` nodes with `ticket_type` `EPIC` /
`STORY`, and the names are query aliases for them (ADR-SDP-DEVKB-002 §2), so every existing
`Ticket` query keeps working.

Properties that carry BL-14 (ODSF-230; properties, not types or verbs, so no schema change):
`Ticket.ticket_type` is the filename type upper-cased (`STORY`, `EPIC`, `BUG`, …) and is what the
Epic/Story aliases filter on (`devkb/query.py "stories implementing SPEC-ODSF-003"`); a ticket
without it (a pre-BL-14 graph) answers only to `tickets`. `Spec.spec_id` is the document's
front-matter `id`, else its filename stem before the first `_`; a Trace `Specification` row
resolves against it (or the Spec path) and an id shared by two Spec nodes is ambiguous, so it is
not linked. A Trace `Epic` row yields `CHILD_OF` only from a `STORY` to an `EPIC`. Every BL-14
reference that does not resolve (unknown epic, spec or evidence id, an `Epic` row that is not
STORY → EPIC, malformed evidence pack, one evidence id recorded with two confidences) is
**reported on stderr at build** and produces no edge — never a guess.

**Hosted issues and pull requests (ADR-DEVKB-007).** A hosted issue is a `Ticket` with `source` `github-issues`, so every ticket
query, tool and pack keeps working. Its properties are `title`, `state` (also in `status`), `state_reason`, `labels`,
`milestone`, `url`, `created_at`, `closed_at`, `has_sub_issues` and, only with `authors`, `author`; never the body. `ticket_type`
is the issue's type where the repository uses issue types (`Bug` → `BUG`), else its labels (`bug` → `BUG`, `epic` → `EPIC`,
`enhancement`/`feature` → `FEATURE`), else `ISSUE`. An epic is an issue whose `ticket_type` is `EPIC` or which has sub-issues
(`has_sub_issues`); the `epics` query alias covers both. A `Ticket` created offline from a closing keyword (`GH-N` named by a
`Fixes #N` in a pull request's commit message) carries `unverified: true` and no title, because `#N` may be a pull request:
the online layer replaces it with the issue, or removes the edge when `#N` is a pull request.

**Two layers, one graph.** The *offline* layer is always on and reads git only. The *online* layer is opt-in
(`devkb build --github`, or `{"github": {"enabled": true}}` in `devkb.json`); a build never touches the network otherwise. It
takes the host and repository from the `origin` remote, authenticates with `GITHUB_TOKEN` or the `gh` login (commit lists and
closing references use GraphQL and need a token), and caches what it reads in `.devkb/github/` keyed by each item's
`updated_at` (gitignored by `devkb init` with the rest of `.devkb/`). If GitHub cannot be reached or rate-limits, the build
completes with the offline layer and the cache, lists what it could not fetch on stderr and in `manifest.json`'s `github`
entry, and every affected answer's `hosting` / Coverage line says so. Only an allow-listed projection of each API item is cached
or stored: descriptions, review text, e-mail addresses and author logins are dropped before anything is written.

## Edge verbs

| Verb | From → To | Source | Phase |
|---|---|---|---|
| `REFERENCES` | Commit → Ticket | `git log --grep=<ticket>`; hosted (online only): a `#N` in a commit message that the API resolves to an issue, `source` `git-hash-mention`, 0.8 — offline a bare `#N` makes no edge, because it cannot be told from a pull request | 1, ADR-DEVKB-007 |
| `CAUSED_BY` | Ticket → Ticket | Bug Lineage `caused_by` | 1 |
| `REGRESSION_OF` | Ticket → Ticket | Bug Lineage `regression_of` | 1 |
| `DUPLICATE_OF` | Ticket → Ticket | Bug Lineage `duplicate_of` | 1 |
| `BLOCKS` | Ticket → Ticket | Bug Lineage `blocks` | 1 |
| `PART_OF` | Ticket → WorkPackage | `wp-map.json` | 1 |
| `BELONGS_TO` | WorkPackage → Milestone | `PROJECT_BOARD.md` grouping | 1 |
| `TOUCHES` | Commit → File | `git diff-tree --name-only` | 2 |
| `TESTED_BY` | File → TestCase | pytest ticket-marker grep | 2 |
| `FLAGGED_BY` | File → Warning | compliance `evidence` field, only when a real on-disk path is parseable from it (most violations are process-level, not file-level -- see `extractors/warnings.py`) | 3 |
| `DEFINED_IN` | Symbol → File, or TestCase → File (ADR-SDP-DEVKB-003) | `ast` decomposition | BL-3 |
| `CALLS` | Symbol → Symbol | `ast.Call`, same-file (0.8) or cross-file via the caller's own import (0.7) -- resolved relative to the repo root first, then to each ancestor directory of the caller's own file (a real per-service src-root import convention, confirmed live against OCO's own `from app.middleware.auth import ...` inside `webapp/backend/`) | BL-3 / BL-3b |
| `TAGS` | Release → Commit | `git log -1 <tag>` | BL-2 |
| `GROUPS` | WorkUnit → Commit | `extractors/work_units.py` clustering, `confidence=0.5` | BL-6 |
| `CALLS_API` | Symbol (frontend, TS) → Symbol (backend route handler) | a frontend route-call site (incl. object-literal methods, e.g. `const api = { x: () => get(...) }`) resolved against a real backend `Endpoint`'s route | BL-4b |
| `PART_OF` *(new usage)* | File → Component | `discovery/`'s own `Module.service` property, promoted to a real edge | BL-8 |
| `REALIZES` | Component → Subsystem | `pms.config.json`'s `subsystems[].path`, longest-prefix match against the Component's own path -- skipped, not guessed, when nothing matches | BL-8 |
| `RAISES` | Symbol → ErrorSignature | `ast.Raise`; `HTTPException(status_code=N, ...)` gets `N` extracted onto `ErrorSignature.status_code` when literal, skipped when dynamic | BL-9 |
| `LOGS` | Symbol → ErrorSignature | `logger.error/warning/critical/exception(...)` calls | BL-9 |
| `REGISTERED_ON` | Symbol (middleware) → Endpoint (wildcard marker, `* <router_prefix>`) | `app.add_middleware(X)`/`router.add_middleware(X)` call-site detection | BL-10 |
| `SIMILAR_TO` | Ticket ↔ Ticket | any nonzero overlap of **evidence-bearing** touched files, carrying `shared_file_count`/`overlap_score`/`weighted_score` (`Edge.extra`) -- still no significance threshold at build time; ranking and capping are query-time concerns and `devkb/query.py` now performs them. A file touched by >10% of tickets is bookkeeping rather than subject matter and is excluded from evidence entirely (computed, reported at build; see `ticket_similarity.hub_files`) | BL-11 |
| `STEP` | Flow → Symbol, `sequence`/weakest-link `confidence` via `Edge.extra` | mechanical BFS over `CALLS`/`CALLS_API` from a detected touch point | BL-12 |
| `DOCUMENTS` | Spec → Ticket | ADR `Related:` line / bare ticket-id mentions in spec body, only when the ticket is confirmed to exist in the graph. **Narrowed from an earlier `Spec → File\|Ticket` draft** -- `Symbol`/`File` reach a `Spec` via the existing multi-hop path (`Symbol→File→Commit→Ticket→Spec`) instead of a second, more speculative direct edge | BL-13 |
| `CHILD_OF` | Story (Ticket) → Epic (Ticket); hosted: sub-issue → parent issue | ticket `## Trace` `Epic` row; hosted: the issue's parent (`source` `github-sub-issues`, 1.0) | BL-14, ADR-DEVKB-007 |
| `DERIVED_FROM` | Ticket → Requirement | ticket `## Trace` `Requirement` row | BL-14 |
| `IMPLEMENTS` | Ticket → Spec | ticket `## Trace` `Specification` row, resolved to the spec file | BL-14 |
| `EVIDENCED_BY` | Ticket \| Spec → Evidence | `References` `evidence — <pack>/bundle.json#<id>` or an `## Open Unknowns` evidence id; only when both ends exist | BL-14 |
| `IN_REPO` | File → Repository | every File of the product and of each member; a member's keys are prefixed `<CODE>:` | ODSF-312 |
| `READS` | Symbol → ConfigKey, or File → ConfigKey at module level | literal `os.environ[...]`, `os.environ.get/setdefault/pop`, `os.getenv`, `"X" in os.environ`; test files excluded; `confidence=0.9` | ODSF-312 |
| `DECLARES` | File → ConfigKey | `*.env.example`/`.env.template`/`.env.sample` `KEY=` lines, compose `environment:` and `${VAR}`, systemd `Environment=`, Dockerfile `ENV`/`ARG`, root `pms.config.json` keys | ODSF-312 |
| `DEPLOYS` | File → Component | a compose service (`<file>#<service>`), a systemd unit (`systemd:<unit>`), a Dockerfile (its path); `kind`, `image`, `ports`, `exec` as properties | ODSF-312 |
| `MERGES` | PullRequest → Commit | the commits the pull request brought in. Offline: a merge commit `Merge pull request #N from <owner>/<branch>` (to the merge commit and to `git rev-list <merge>^1..<merge>^2`, `source` `git-merge-subject`) and a squash commit whose subject ends `(#N)` (`git-squash-subject`), confidence 0.9 because a subject is editable text. Online: the API's commit list, `github-api`, 1.0 (also finds rebase merges, which leave no trace in git); for a pull request whose list the API gave completely, an offline edge it does not contain is dropped | ADR-DEVKB-007 |
| `CLOSES` | PullRequest → Ticket | the issues a pull request closes. Online: GitHub's closing references, `github-closing-references`, 1.0, replacing every offline edge of a pull request it was read for. Offline: a closing keyword (`Fixes`/`Closes`/`Resolves #N`) in a commit message of the pull request, `git-closing-keyword`, 0.7, with `unverified: true` on the edge and the target | ADR-DEVKB-007 |

## Envelope shapes

Node (as written to `.devkb/nodes.jsonl`):
```json
{"uid": "devkb:ticket:<sha256(\"Ticket:ODSF-021\")[:16]>",
 "type": "Ticket", "natural_key": "ODSF-021", "source": "tickets",
 "properties": {"...": "..."}}
```

Edge (as written to `.devkb/edges.jsonl`):
```json
{"from_uid": "...", "to_uid": "...", "verb": "CAUSED_BY",
 "properties": {"source": "bug-lineage", "confidence": 1.0,
                "evidence_ref": "issues/ODSF-021...md#Bug-Lineage"}}
```

Every edge carries `source`/`confidence`/`evidence_ref`; some verbs also
carry verb-specific structured data (`Edge.extra`, e.g. `SIMILAR_TO`'s
`shared_file_count`/`overlap_score`, `STEP`'s `sequence`) merged into the
same `properties` bag rather than a separate field — a consumer reads
`properties` generically either way:
```json
{"from_uid": "...", "to_uid": "...", "verb": "SIMILAR_TO",
 "properties": {"source": "file-overlap-inference", "confidence": 1.0,
                "evidence_ref": "2 shared touched files (...)",
                "shared_file_count": 2, "overlap_score": 0.5}}
```

`uid` is deterministic (`sha256(f"{type}:{natural_key}")[:16]`, prefixed
`devkb:<type>:`) — see `devkb/model.py::uid_for`. Rebuilds are idempotent and
never duplicate nodes.

## Not governed here: `Symbol.security_signals`

A property, not a new node type or edge verb, so it isn't a table row
above — but worth naming since it's a real, load-bearing concept (BL-14,
`devkb/SOT.md` Part 5.1a / Part 8 OQ2): a fully-automated `list[str]` of which
policy/criticality detector fired (`path-keyword:<word>`,
`registered-as-middleware`, `enforces-authz-boundary`), no hand-maintained
field anywhere. Computed in the same `devkb/build_symbols.py` pass as
`RAISES`/`REGISTERED_ON`, since both are its own inputs.
