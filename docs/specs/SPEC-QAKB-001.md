---
id: SPEC-QAKB-001
title: "A QA knowledge base on the devkb graph: traceable, measured, honest about what it cannot see"
type: spec
status: proposed
created: 2026-11-18
story: "#36"
builds_on: [devkb 0.2.9, docs/analysis/devkb-for-auditing.md, docs/analysis/bugfix-benchmark.md, docs/analysis/dogfood-lessons-for-kb-qa.md]
---

# SPEC-QAKB-001: QA knowledge base (QAKB)

BMAD roles: decision record of the QA manager (§0), brief (§1), requirements (§2), architecture (§3), quantitative
management (§4), stories (§5), readiness (§6), evaluation plan (§7). Written from the position of the quality-assurance
function of a CMMI maturity level 5 organisation. **devkb was used to write it** (every question about devkb's code and
documents went to devkb first; log and verdicts in §8).

## 0. Decision record: which frameworks, and why

A QA function at maturity level 5 does not ask "is the product tested?" but "is the process that produces quality under
statistical control, and do we know the cause of every deviation?". QAKB must serve that question, so the frameworks are
chosen for what each contributes, not stacked for coverage.

| Need | Framework chosen | What it gives QAKB | Not chosen as the frame, and why |
|---|---|---|---|
| The process model QA audits against | **CMMI V2.0** practice areas PQA (Process Quality Assurance), PR (Peer Reviews), VV (Verification and Validation), MPM (Managing Performance and Measurement), CAR (Causal Analysis and Resolution), with high-maturity practices (process performance baselines and models, statistical management) | the questions QAKB must answer, the evidence an appraisal asks for, and the quantitative expectations of levels 4–5 | TMMi alone: test-process only, says nothing of reviews or causal analysis; ISO 9001 alone: a management-system standard, not a software-process model. Both map onto CMMI and are recorded as cross-references only |
| What "quality" is measured as | **ISO/IEC 25010:2023** quality model, measures from **ISO/IEC 25023** | a fixed vocabulary of characteristics (functional suitability, reliability, maintainability, security, …) to tag requirements, tests and defects with | ad-hoc "severity" scales: not comparable across projects |
| How tests are specified and reported | **ISO/IEC/IEEE 29119-2/-3** (test processes, test documentation; risk-based testing) | the record types: test plan, test design/case, test result, incident report | tool-specific formats: kept as import sources, not as the model |
| How reviews and audits are run and recorded | **IEEE 1028-2008** (management/technical reviews, inspections, walkthroughs, audits) and **ISO 19011:2018** (audit principles: evidence-based approach, objectivity) | review and audit records with objective evidence; every finding traceable to the evidence it rests on | informal checklists: no evidence trail |
| How defects are classified for causal analysis | **Orthogonal Defect Classification (ODC)**: defect type, trigger, impact, source, age, qualifier | attributes stable enough for trend and causal analysis across projects (the basis of CAR) | free-text root-cause fields: not analysable |
| How progress and convergence are judged | **reliability growth (Gompertz) curves**, **test density and defect density per KLOC with target ranges** (the measurement practice of large Japanese system integrators, benchmarked by IPA/SEC data), **defect removal efficiency** per phase | the quantitative signals a level-5 QA function manages by: is the bug curve converging, is a component under- or over-tested against its baseline | pass rate alone: says nothing about convergence or test sufficiency |
| How a deviation is explained | **statistical process control** (XmR and u-charts on review and test sub-processes), **why-why analysis** (なぜなぜ分析) recorded per ODC class | a special-cause signal, then a recorded causal chain to a process change | anecdotal post-mortems |

**Principle:** QAKB records and links; it does not judge. The judgement (is this defect a requirements error, is this
process out of control) stays with people and, where an AI suggests, the suggestion is recorded as one, with its basis.

## 1. Brief (analyst)

**Problem.** QA work with an AI assistant spends its cost on finding things: which tests cover a change, which
requirement a test verifies, which past defects resemble this one, what evidence an audit finding rests on. Today those
answers live in five places (code, test results, tracker, reviews, spreadsheets) and are re-assembled by hand or by an
agent reading files.

**Evidence from building devkb** (2026-11-16/18):
- On audits, an agent told to ask the graph first sent 31–39% of its navigation through it and read 33–78k characters
  of files instead of 108–153k; but every one of 36 defects was found by reading code and a repro, not by the graph
  (`docs/analysis/devkb-for-auditing.md`).
- On bug fixing in devkb's own repository (102 runs over four task sets: tickets with and without a pointer to the code,
  tickets in a user's words, cross-file renames), agents almost never asked the graph (3 queries in the 60 runs where it
  was offered, a pre-edit hook included) and fixed as well without it: a precise ticket, a small well-named repository,
  Python's qualified call sites and a test suite make grep sufficient (`docs/analysis/bugfix-benchmark.md`). The
  large-repository task set (sympy) is the open question (§6, §7).
- The most harmful answers were not wrong locations but wrong claims of **completeness**, **kind** ("is a test") and
  **absence** ("no caller"), and failures shown as empty answers (`docs/analysis/dogfood-lessons-for-kb-qa.md`).
- The **oracle** (benchmark truth) was wrong more often than the tool, and a class of cases removed from the oracle hid
  the same gap in the product.

**Users and what they ask.**

| User | Question QAKB must answer |
|---|---|
| QA engineer | what must be re-tested after this change, and why; which requirement does this failing test verify |
| Developer | is this change covered; have we seen a defect like this before, and how was it fixed |
| QA manager / SEPG | is test and review effort within baseline per component; is the defect curve converging; which ODC classes dominate and why |
| Auditor (internal, appraisal) | for practice X on project Y, the objective evidence, its date and its source |
| AI agent | all of the above in one call each, with a coverage statement it can act on |

**Goal.** Cut the cost of those questions for people and agents, without ever making a wrong claim of completeness.

**Non-goals.** Running tests; writing tests; judging correctness; replacing the issue tracker or the test management
tool; any processing of client-confidential data outside the local network.

## 2. Requirements (PM)

**Functional**

| # | Requirement |
|---|---|
| F1 | **Traceability matrix**: requirement ↔ test case ↔ code symbol ↔ defect ↔ change, each link with its source and its kind (declared in a test, inferred from calls, inferred from a ticket) and a confidence |
| F2 | **Change impact for QA**: for a change (diff, commit range or pull request), the tests to run, the requirements touched, the past defects in the changed code, and the risk class; with a coverage statement naming what could not be traced |
| F3 | **Defect records with ODC**: imported defects carry ODC attributes; where a person has not classified, an AI suggestion is stored as a suggestion with its basis, never as the classification |
| F4 | **Test results as history**: test runs and results (JUnit XML and equivalents) per commit, so a test's history, flakiness and the first failing change are queries |
| F5 | **Review and audit records** (IEEE 1028, ISO 19011): review/audit, its findings, the objective evidence for each, and the finding's status through to closure |
| F6 | **Measures and baselines**: per project and component, test density, defect density, review coverage and review rate, defect removal efficiency, escape rate, reliability-growth fit; baselines and control limits from history (§4) |
| F7 | **Causal analysis records** (CAR): a special-cause signal or a defect class, its why-why chain, the process change decided and its measured effect |
| F8 | **Audit evidence pack**: for a CMMI practice and a project, the evidence QAKB holds, its age and its source, and the gaps |
| F9 | **Similar past defects**: for a new defect or a failing test, past defects with the same ODC type and trigger in the same code, with their fixes |
| F10 | **Extraction health**: per source file and imported record, parsed / partly parsed / skipped with the reason, shown beside every answer that depends on it |

**Non-functional**

| # | Requirement |
|---|---|
| N1 | **Honest completeness** (from devkb's lessons): a list answer is Complete only when every link kind that could add an item was readable; otherwise it says Incomplete and names the link kinds not seen (fixtures, dependency injection, data-driven tests, end-to-end calls over HTTP, configuration-selected suites, callbacks, reflection) |
| N2 | **Kind by the runner, not by the name**: a test is what the project's runner collects (configuration, markers), never a file name pattern alone |
| N3 | **A failure is never an empty answer**: a rejected query, a parse failure, a missing import, a stale source is an error with its cause |
| N4 | **Data sovereignty**: QA data is client-confidential by default; any model call goes to the local endpoint only, logged; no public AI API |
| N5 | **Determinism and provenance**: the same inputs give the same graph; every node and link records its source, extractor version and time |
| N6 | **Byte-preserving writes**: QAKB writes into repositories only through marked blocks that fail closed (refuse an unpaired marker), keep encodings and line endings, and survive add/update/remove round trips |
| N7 | **Reproducible measures**: every measure and baseline is recomputable from committed inputs by one command, with the oracle it was computed against |
| N8 | **No real personal data** in any fixture, example or test |

## 3. Architecture (architect)

**Build on devkb, do not fork it.** devkb already holds `Ticket`, `Commit`, `File`, `Symbol`, `TestCase`, `Requirement`,
`Spec`, `Evidence`, `Warning`, `ErrorSignature`, `PullRequest` and the relations `REFERENCES`, `TOUCHES`, `CALLS`,
`TESTED_BY`, `RAISES`, `IMPLEMENTS`, `DOCUMENTS`, `CLOSES`, `MERGES` (`devkb/ontology.md`). QAKB is a layer on that graph.

**Schema additions** (each requires an Accepted ADR before code: `devkb/ontology.md` governance; proposed as
ADR-DEVKB-0xx "QA layer"):

| Node | Key | Source |
|---|---|---|
| `Defect` | tracker id | issue tracker; ODC attributes as properties (`odc_type`, `odc_trigger`, `odc_impact`, `odc_source`, `odc_age`, each with `classified_by: person/suggested`) |
| `TestRun` | CI run id + commit | JUnit XML / test reports |
| `TestResult` | run + TestCase | same; `outcome`, `duration` |
| `Review` | review id | pull-request reviews, inspection records (IEEE 1028 type as property) |
| `Audit` | audit id | audit plan/report (ISO 19011) |
| `Finding` | audit/review + n | the record; `status`, `practice` (CMMI practice id) |
| `Measure` | project + component + measure + period | computed (§4) |
| `CausalAnalysis` | id | CAR record: signal, why-why chain, decided change |

| Relation | From → To | Meaning |
|---|---|---|
| `VERIFIES` | TestCase → Requirement | a test verifies a requirement; `kind`: declared (marker/tag) or inferred |
| `DETECTED_BY` | Defect → TestCase / Review / Audit | where it was found (ODC trigger context) |
| `LOCATED_IN` | Defect → Symbol / File | where the fault was; from the fixing commit's diff |
| `FIXED_BY` | Defect → Commit | the fix |
| `RESULTED_IN` | TestRun → TestResult; TestResult → TestCase | test history |
| `EVIDENCED_BY` | Finding → Evidence / Commit / TestRun / Review | the objective evidence |
| `EXPLAINS` | CausalAnalysis → Defect / Measure | what the analysis is about |

**Link kinds are first-class.** Every `TESTED_BY`/`VERIFIES` link carries `kind` (direct call, through fixture, through
HTTP, declared by marker, inferred from ticket) so N1's coverage statement can name exactly which kinds were not
readable, and §7 can score each kind separately.

**Tools** (MCP and CLI, one question per call, each with a coverage statement): `rtm` (F1), `qa_impact` (F2),
`defect_pack` (F3, F9), `test_history` (F4), `audit_pack` (F5, F8), `measures` (F6, with control limits), `car_log`
(F7), `health` (F10). Packs follow devkb's pack contract: evidence line per item, Complete/Incomplete with reasons.

**Model use.** Optional, and only for suggestions (ODC class from defect text, requirement–test link candidates):
through the local endpoint (N4), stored as suggestions, never as facts.

## 4. Quantitative management (high maturity)

| Measure | Definition | Baseline and limits |
|---|---|---|
| Test density | test cases (or test points) per KLOC changed, per component | per-component baseline from the organisation's history; XmR limits |
| Defect density | defects found per KLOC, per phase (review, unit, integration, system) | per phase; u-chart with limits from the baseline period |
| Review coverage / rate | reviewed LOC share; LOC per review hour | IEEE 1028 inspection norms adjusted by baseline |
| Defect removal efficiency | defects removed in phase / (removed in phase + found later) | per phase target from the process performance baseline |
| Escape rate | defects found after release / total | per release |
| Reliability growth | Gompertz fit to cumulative defects over test effort; convergence = predicted remaining below target | fit residuals reported; a non-converging fit is a signal |
| ODC distribution | share of defect types per trigger and phase | chi-square against baseline distribution; a shift is a special-cause candidate for CAR |

**Rules.** A point outside the control limits, or a run rule violation, creates a candidate `CausalAnalysis` record; a
person decides whether it is a special cause. Baselines are recomputed only by an explicit, logged decision, never
silently. A measure computed from incomplete links (N1) is marked so and is not plotted against the baseline.

## 5. Stories

1. **QA impact.** As a QA engineer I give a pull request and get the tests to run, the requirements touched and the
   past defects in the changed code, each with its evidence line and a coverage statement. *AC:* on three repositories,
   tests-to-run recall ≥ 0.95 against the compiler/runner truth (tests that fail when the change is reverted into a
   mutation), precision ≥ 0.9; every Incomplete names the unreadable link kinds; a Complete claim checked on 20 sampled
   answers is never wrong.
2. **Traceability matrix.** As an auditor I ask for project Y's RTM and get requirement ↔ test ↔ code ↔ defect with link
   kinds and gaps. *AC:* every declared link from the test framework's markers present; inferred links labelled; RTM
   reproducible from committed inputs by one command.
3. **Defects with ODC.** As a QA manager I import a tracker export and see ODC classes, with suggestions separated from
   classifications. *AC:* no suggestion is ever stored as a classification; suggestions come only from the local model;
   agreement of suggestions with two human classifiers measured (Cohen's κ reported, not assumed).
4. **Test history.** As a developer I ask which change first broke a test and whether it is flaky. *AC:* from JUnit XML
   of ≥ 100 runs, first failing commit correct on a labelled sample of 20; flakiness = outcome changes without a code
   change.
5. **Audit evidence pack.** As an auditor I ask for the evidence of PQA practice on project Y. *AC:* each item has
   source, date and link to the record; the pack lists the practices with no evidence; no evidence older than the
   audit period presented as current.
6. **Measures and SPC.** As a QA manager I see defect density and DRE per component against baseline with control
   limits. *AC:* every number recomputable by one command; a measure from incomplete links is flagged and not plotted.
7. **Causal analysis.** As SEPG I record a why-why chain for a signal and later see the measured effect of the process
   change. *AC:* the chain links signal → causes → decision → measure after; nothing in the chain without a source.
8. **Health and honesty.** As any user I see, beside every answer, which inputs were not understood. *AC:* a corpus with
   injected unreadable files (encoding, nesting, a failed import) yields answers that name them; none returns an empty
   list as if nothing existed.

## 6. Readiness (G0)

| Check | State |
|---|---|
| Traces to a need | #36; the three analyses in `docs/analysis/` |
| Falsifiable criteria | every story has numeric or sampled acceptance |
| Scope boundary | §1 non-goals; N4 |
| Schema change governed | §3: ADR before code |
| Evaluation designed before build | §7 |
| Open risk | the large-repository bug-fix benchmark (T2, sympy) is still running; its outcome decides how much of F2/F9 is navigation the graph must carry versus search an agent already does well |

## 7. Evaluation plan (from what devkb's benchmarks taught)

- **Arms:** plain; QAKB as shipped (instructions + tools); QAKB pushed (a hook that supplies the pack without being
  asked). Measure use as well as outcome: a tool never called cannot be credited or blamed.
- **Tasks where the knowledge base should matter,** not only where it is easy to build: symptom-only reports in a
  large unfamiliar repository; change impact where call sites are not textually qualified; "every place that computes X"
  changes; audit questions across code, tests, tracker and reviews.
- **Oracle discipline:** acceptance matched to the ticket's scope (two of devkb's task tickets were narrowed in a
  rewrite while their tests were not, which inverted a result until rescored); every "wrong" answer sampled against
  the source before a regression is believed; classes excluded from the oracle tested separately.
- **Enough repetitions** to see the spread (≥ 8 per question for a 0.03 difference); per-question and per-run results
  published, not only means.
- **Dogfood from week one:** QAKB answers QA questions about its own repository; every wrong, incomplete, noisy or
  misleading answer is logged with a regression test.

## 8. How devkb was used to write this specification

Every question about devkb's code and documents went to devkb first and was checked against the source; the log is
`docs/specs/qakb-spec-dogfood.jsonl` (with the queries made while preparing the benchmarks that feed §1).

**17 queries: 10 right, 2 honestly incomplete, 2 silently incomplete, 1 misleading,
1 noisy, 1 with no tool for the question.** None gave a wrong location or a wrong body.

| Phase | Query | Purpose | Verdict | What the source showed |
|---|---|---|---|---|
| research | `docs "node types relations ontology"` | find the schema doc QAKB must extend | incomplete-silent | no match although devkb/ontology.md answers it; word search has no plural matching: the doc says 'node type', 'relation' |
| research | `docs "schema change requires ADR"` | rule for adding node types/verbs | right | ontology.md L4-5: Accepted ADR before a schema change |
| research | `symbol tests_for` | existing QA-facing tool | right | mcp_server.py L124 and process_api.py L453 |
| research | `uses TESTED_BY --under devkb` | where test links are produced and read | right | files_tests (ticket markers), symbol_tests, process_api._tests_of; edge_truth measures it |
| research | `outline devkb/packs.py` | which pack kinds exist | right | Packer L51-522 with its methods (my grep filter hid them) |
| research | `symbol tests_to_run|rca_trace|review_pack|impact` | QA-facing tools QAKB builds on | right | four tools located; caller counts say partial (#87) |
| research | `uses Ticket --under devkb/extractors` | how tickets enter the graph | misleading | hits right (github issues, closing refs, lifecycle); header 'defined: packs.py L434-460 method' is a case-insensitive match of a method, not the node  |
| readme | `docs "language support"` | find README language table | noisy | 13 docs (specs/ADRs) ranked above; README not among top results |
| readme | `docs "language support" --under README.md` | find README language table | incomplete-silent | no match: README says 'Languages' and 'Supported' (no plural/stem matching, same as the ontology query) |
| benchmark | `symbol project_context.resolve --source` | current behaviour before writing a benchmark ticket | right | body and docstring; caller count 7+ with 'named without a call' (0.2.9 #69/#87 visible); it corrected my wrong assumption about a silent fallback |
| benchmark | `pack refactor build_symbols.extract (and project_context.resolve, tick` | callers of a module function for a refactor | incomplete-honest | 'cannot resolve unambiguously. Search the code' although symbol resolves module.name since 0.2.9 (#100): pack and symbol disagree |
| benchmark | `pack refactor DevKBGraph.edges` | callers of a method for a rename | incomplete-honest | 6 caller files with lines; Incomplete names 82 unattributed functions in 27 files (other edges/attributes) |
| benchmark | `pack refactor devkb/build_symbols.py::extract` | callers for a rename | right | 14 caller files, 12 tests; Incomplete says 21 symbols share the name |
| spec | `docs "TestCase"` | how a test is modelled | right | ADR-DEVKB-008 §5: TestCase key path:line, file/line/function/framework |
| spec | `outline devkb/coverage.py` | what 'coverage' means in devkb | right | layout right; the module docstring is not shown by outline |
| spec | `symbol audit.main` | the graph audit entry point | right | resolved by module name (#100) |
| spec | `(read devkb/ontology.md whole)` | the full node-type and relation list | unsupported | docs returns matching lines only; there is no tool to read a document or a section of one |

**What this says about devkb as a specification tool.** It answered "where is X, what does it do, who calls it" quickly
and correctly, including a correction of the author's own wrong assumption about `project_context.resolve` while writing a
benchmark ticket. It failed on documents: word search without stemming missed `ontology.md` and the README for plural and
inflected wording, and there is no way to read a document or a section of one, so the ontology had to be read
directly. Three findings became issues during the work: `pack refactor` rejected `module.name` while `symbol` accepted it
(#104), and devkb could not build sympy at all (#105, #106).

**Requirements this adds to QAKB:** N3 (failures as errors), F10 (health), and a document tool with stemming and
section reads, because a QA knowledge base is mostly documents (plans, reports, standards).
