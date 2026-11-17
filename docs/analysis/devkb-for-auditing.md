# devkb as an auditing tool: what it saved, where it stopped (input for the QAKB specification, #36)

Two code audits of devkb itself (2026-11-17), each by independent reviewer agents told to ask devkb before searching
or reading, on a graph of the repository built by the code under audit. The questions an audit asks are the questions
a QA knowledge base (#36) will be asked, so the measurements below are its starting requirements.

| Audit | Scope | Reviewers | Defects confirmed, ticketed |
|---|---|---|---|
| 1 | changes v0.2.5 → main (≈6,600 lines: C/C++, C#, read tools, hook, init, packs) | 3 (devkb-first added mid-run) | 22 (#50–#71) |
| 2 | code from v0.2.0 → v0.2.5 still on main (plugin hooks/config, init, bench; 825 surviving C# lines) | 2 (devkb-first from the start, every query logged with a verdict) | 14 (#72–#85) |

Every finding was reproduced by a script before it was reported; the high ones were reproduced a second time
independently. Measured from the reviewers' transcripts (`toolmix.py`: tool calls by kind and the characters each
returned to the model) and from their query logs (44 devkb queries in audit 2, each checked against the source).

## 1. Efficiency

Tool mix from the transcripts (`bench/audit/toolmix.py`; all rows in `bench/audit/toolmix-results.md`): navigation calls are devkb, search (grep/find/ls) and read
(file and git reads); "run" is writing and running repro scripts and tests.

| Agent | devkb queries | devkb share of navigation calls | devkb share of navigation text | text read from files/diffs | run calls |
|---|---|---|---|---|---|
| audit 1, C/C++ (devkb asked mid-run) | 2 | 8% | 1% | 150k chars | 8 |
| audit 1, C# (mid-run) | 8 | 24% | 5% | 153k | 4 |
| audit 1, tools (mid-run) | 6 | 12% | 3% | 108k | 3 |
| **audit 2, plugin (devkb-first)** | 23 | **39%** | **32%** | 33k | 3 |
| **audit 2, C# (devkb-first)** | 19 | **31%** | **22%** | 78k | 9 |
| fix, Python (devkb-first) | 29 | 27% | 18% | 123k | 32 |
| fix, C# (devkb-first) | 18 | 18% | 16% | 76k | 25 |
| fix, C/C++ (devkb-first) | 13 | 7% | 7% | 67k | 42 |
| fix 2, plugin/init/read tools (devkb-first) | 15 | 24% | 22% | 18k | 20 |
| fix 2, C# (devkb-first) | 12 | 10% | 9% | 121k | 31 |
| fix 2, C/C++ (devkb-first) | 12 | 8% | 8% | 73k | 34 |

- **Asked first, devkb carries a third of an audit's navigation, and file reading falls.** Audit 2 reviewers sent
  31–39% of navigation calls and 22–32% of the navigation text through devkb and read 33k–78k characters from files,
  against 108k–153k in audit 1. Different scopes, so a direction, not a controlled comparison.
- **Fixing uses it less than auditing.** The fixers' work is dominated by running tests and repros (25–42 runs each)
  and by reading whole functions they change; devkb's share falls to 7–27%, and to 8–10% for the extractor fixers. The C/C++ fixer, working inside one
  2,000-line file whose behaviour it had to test, used it least.
- **19 of 44 audit-2 answers settled the question** with no grep or read after them.
- **The defect-finding work itself stays outside the graph.** Every one of the 36 audit defects was found by reading
  code and confirmed by a scratch repro; devkb located the code, listed callers and showed what is tested, but did not
  and cannot judge correctness ("answered worst: the actual audit questions", audit 2 reviewer). This agrees with the
  earlier study (agents used the graph in 0% of review runs, 88% of call-chain runs).

**Accuracy (every answer checked against the source):**

| Agent | devkb answers checked | right |
|---|---|---|
| audit 1 (3 reviewers and the lead) | 25 | 21 (84%) |
| audit 2, plugin | 23 | 15 (65%) |
| audit 2, C# | 21 | 11 (52%) |
| fix, Python | 21 | 15 (71%) |
| fix, C# | 9 | 5 (56%) |
| fix, C/C++ | 10 | 7 (70%) |
| fix 2, plugin/init/read tools | 13 | 9 (69%) |
| fix 2, C# | 11 | 6 (55%) |
| fix 2, C/C++ | 8 | 6 (75%) |
| **total** | **141** | **95 (67%)** |

None of the 46 other answers gave a wrong location or a wrong body. They were claims about absence or kind (no other
caller, Complete, "is a test"), honest or silent incompleteness, noise, or questions it has no tool for.

**Defects in devkb found by using devkb**, ticketed: #69 (false Complete for a method passed as a value), #70 (a
self-call counted as a caller), #71 (a `test_*.py` module classed as a test), #87 (caller count silently partial),
#88 (function-local imports in `outline`), #89 (`uses` cap keeps comments before call sites), #90 (`uses --under` a
file finds nothing), #91 (`outline` cap with no paging). #69–#71 and #87–#91 are fixed for 0.2.8 except #88 (low).

## 2. What it answered well (44 checked queries, audit 2)

| Tool | Queries | Right | Other |
|---|---|---|---|
| `uses` (where a name occurs, with the enclosing function) | 14 | 11 | 1 silently incomplete (JSON not scanned), 1 honest incomplete, 1 misleading |
| `symbol` (definition and body) | 9 | 7 | 2 misleading |
| `outline` (a file's members and ranges) | 9 | 6 | 3 unsupported (shell, JSON, markdown) |
| `pack refactor` / `pack change` (callers, completeness) | 5 | 2 | 2 silently incomplete, 1 noisy |
| `docs` (documentation search) | 3 | 0 | 3 noisy |
| no tool for the question | 4 | | history/blame, the ticket list, regex behaviour |

Best: "where is X defined", "what is in this file", "where is this name used, and is it tested"
(`uses --under tests` was reliable even when the answer was no). These matched git grep exactly and added the
enclosing function, which grep does not.

## 3. Limitations, by kind (each is a requirement for QAKB)

**L1. False completeness (the most harmful).** Four answers claimed "Complete" and were not:
- a caller reached through a string-keyed dispatch table (`"init": "devkb.init"`) was missing;
- a method passed as a value (`pool.submit(self._moved_files)`) had 0 callers (#69);
- a refactor pack listed one call site of a caller with four (a signature change needs all four);
- `uses` did not scan JSON and only the generic "not complete" banner hinted at it.
*QAKB requirement:* a completeness claim must name what the extractor cannot see (dispatch tables, callbacks,
reflection, configuration files, data-driven tests) and must be checked by sampling; per-site, not per-function,
completeness when the question is about sites.

**L2. Kind and identity errors.** A source module named `test_discovery.py` listed as a test (#71); a recursive
self-call counted as a caller, hiding dead code (#70); `uses Finalize` reported the definition of a different,
lower-case `finalize`; `symbol` offered a near name but not the exact `path::name` that exists.
*QAKB requirement:* classify tests by what the runner collects, not by file name; identity is case-sensitive and
path-qualified; never present a fuzzy match as the answer.

**L3. Blind to non-code artefacts.** The plugin is shell, JSON and markdown; `outline` had nothing to say about any
of them and `docs` returned README table rows for behaviour documented in shell comments.
*QAKB requirement:* QA lives in non-code files (test plans, CI YAML, fixtures, feature files, configuration); index
them as first-class nodes with their own structure, not as text.

**L4. No history.** "Which lines came from v0.2.0..v0.2.5", "when did this rule land", "what changed in this function"
are core audit and regression questions and have no tool (the graph has commits, but no blame or per-function
history).
*QAKB requirement:* change → affected tests and "what changed since the last green run" need history as data.

**L5. No reasoning about behaviour.** Whether a regex mis-parses a literal, or a hook breaks on a quote, is found only
by running a repro. *QAKB requirement:* store reproductions and their results as data (finding → repro → test →
fix), so the knowledge base remembers what was proven, rather than trying to infer behaviour.

**L6. Silent extraction gaps look like answers.** UTF-16 C# files yield nothing with no warning (#83); attributes
with braces, explicit interface implementations and `#if` branches made methods disappear (#78–#80). An agent sees
"no callers" or "no test", not "this file was not understood".
*QAKB requirement:* per-file extraction health (parsed, partly parsed, skipped and why) shown beside every answer
that depends on the file.

**L7. The oracle can be blind in the same place.** Round 4 removed explicit interface implementations from the
benchmark truth as "truth noise"; the audit then found the extractor drops them entirely (#79). Removing a class of
cases from the oracle hid the product's gap in that class.
*QAKB requirement:* when the oracle is corrected, record each excluded class and test the product on it separately.

## 4. What to carry into the QAKB specification

1. Ask-first instructions measurably change behaviour (devkb share of navigation 8–24% → 31–39%); ship them.
2. The saving is in navigation and joins, not in judging; scope QAKB's promise to "find, link and remember", and
   measure it on navigation and joins.
3. Every list answer carries a coverage statement that names the invisible link kinds (L1) and the files not
   understood (L6).
4. Non-code QA artefacts and history are first-class (L3, L4).
5. Findings, repros and their tests are nodes (L5): the audit trail itself is the most reusable QA knowledge.
6. Measure with the method used here: tool-mix from transcripts, and a per-query verdict log (right, wrong,
   incomplete-honest, incomplete-silent, noisy, misleading, unsupported) checked against the source.

Raw data: `bench/audit/` holds the measurement script and the audit-2 query logs (redacted paths). The defects are in
issues #50–#93 with their repros.
