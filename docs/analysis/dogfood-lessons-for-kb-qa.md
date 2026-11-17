# What dogfooding devkb taught, for a QA knowledge base (#36)

#36 proposes a QA knowledge base (QAKB): a graph that answers QA questions for an AI assistant (what tests cover
this, what to re-test after this change, which requirement is untested) so that QA with AI costs less. devkb was built
by using it on its own code and on real repositories at every step. This note collects what that showed, as rules a
QAKB should start with rather than rediscover.

Sources: `docs/specs/csharp-4-dogfood-log.md` (C# round 4, D1–D9), `bench/exercises/cpp/REPORT.md` (C/C++
dogfooding), `bench/exercises/csharp/truth-corrections.md` and `DEVKB-VALUE-0.2.7.md` (the benchmark-truth
correction), and the 0.2.5 → 0.2.8 quality audit (this note, §Audit), all from 2026-11-16/17.

## 1. The oracle is wrong more often than the product

The largest error of the whole C# programme was not in devkb but in the benchmark that judged it. The compiler truth
recorded calls only, not property reads, so on EF Core 29 methods that reach the target were scored wrong; it also
merged two Polly classes of the same name from different assemblies. Together they produced a published "precision
fell to 0.82, criterion not met" that was false (fixed truth: 0.93, unchanged from the previous release). Earlier the
truth also counted .NET static names and explicit interface implementations as callers (round-4 B1), and the committed
question file lacked the filter the published numbers were scored with, so they could not be reproduced.

**For QAKB:** expected results, requirement links and "known defects" lists are an oracle and will have gaps of the same
kind. Before believing a regression, read a sample of the answers the oracle calls wrong against the source; keep the
oracle versioned beside every result; publish scores with the oracle they were computed against; make every score
reproducible from committed inputs (the scorer, its filters, the truth) by one command.

## 2. "Complete" is the most dangerous word a tool can say

A complete-looking list makes an agent stop searching, so a false "Complete" costs more than a missing answer. It has
happened three times:
- `pack refactor _moved_files` (this audit): 0 callers, **Complete**; the method is passed to `pool.submit(...)`, a
  reference the graph does not record as a call.
- The C/C++ error pack matched unrelated symbols and said **Complete** (no C++ error extraction).
- The Incomplete line once counted functions as "call sites" (D2): the honest marker was itself inaccurate.

**For QAKB:** "these are all the tests for X" and "nothing else needs re-testing" are the product's most valuable and
most dangerous answers. Derive completeness from what the extractor can see, and say which kinds of link it cannot:
for tests, fixtures and parametrised data, dependency-injection wiring, configuration-selected suites, tests reached
through helpers, end-to-end tests that call over HTTP. Test the "Complete" claim directly: for a sample of complete
answers, search for the missing link by hand.

## 3. The links that matter are often not calls

Every recall gap that survived four C# rounds was a link that is not a direct call: a property read (EF Core), a method
group registered as a callback (Polly `CloseAsync`), a lambda run later (credited to the member that creates it), a
method passed as a value (`pool.submit(self._moved_files)`), interface and virtual dispatch, reflection.

**For QAKB:** most test-to-code links are indirect (a fixture builds the object, a page object wraps the UI, a test
calls an API that reaches the code). Decide per link kind whether it counts, store the kind on the edge, and score each
kind separately; a single "covered" flag hides which kind is missing.

## 4. Noise comes from copies and data

- `uses` spent its budget on lines of JSON benchmark transcripts (D4); fixed by keeping data files out of code search.
- EF Core keeps fixture copies of production classes under `eng/**/fixtures/`, so a name defined once had two symbols
  and `callers` refused it as ambiguous (D8).
- A repository's own `class List` shadowed .NET's `List<T>` until arity was checked.

**For QAKB:** test repositories are full of copies: golden files, snapshots, recorded responses, vendored fixtures,
generated clients. Classify files (code, test, fixture, data, generated) before linking anything, and never let a
fixture's copy of a class stand for the class.

## 5. Failures must not look like empty answers

- A `devkb` on PATH from an old release built a graph of **0** symbols for leveldb, and every answer was "nothing".
- `search_docs` with a pattern git grep rejects returns "no document matches" (this audit, finding 5).
- Paths under dot-directories cannot be resolved (`lstrip("./")`), so `outline(".github/x.py")` says "no file".

**For QAKB:** "no test covers this" is an alarming answer; make sure it is never produced by a failure. A zero-symbol
build, a parse error, a timeout or a rejected query is an error with its cause, not an empty result. Check the tool's
own version and the graph's size at start.

## 6. Averages hide the answer, and two runs prove little

EF Core's agent answers came in two sizes (14–17 names or 33–39); the mean moved with which mode two runs happened to
draw. With two runs per question one question moved ±0.15 between arms that differed in nothing the agent used. The
first explanation of the drop (the read tools) was wrong, and only an ablation showed it.

**For QAKB:** report per question and per run, not only means; run enough repetitions to see the spread (about 8 per
question for a 0.03 difference here); attribute a change only after an ablation that removes the suspected cause.

## 7. Where the graph pays, and where it does not

Agents used the graph in 88% of runs that followed a call chain and in none of the requirement, solution or review
runs; savings came from chains and joins (callers, code to tests, root cause), and the instructions in `AGENTS.md`
were part of what was measured. On the C# chain questions the graph cut median cost by 40–53% at higher precision.

**For QAKB:** start with the QA questions that are joins: change → affected tests, failure → recent changes and
owners, requirement → tests → last result. Questions one search answers ("find the test named X") will not save
anything. Ship instructions that say when to ask the graph, and measure with them in place.

## 8. Tools that edit a user's files must preserve them byte for byte

The audit found three ways `devkb init` damages a user's own `AGENTS.md`/`CLAUDE.md`: a block whose end marker was lost
makes the next run delete the user's text after it; a `CLAUDE.md` symlinked to `AGENTS.md` overwrites the block;
CRLF files are rewritten as LF. A non-UTF-8 file crashes it.

**For QAKB:** a QA tool will write test plans, checklists and instructions into repositories it does not own. Edit by
markers that fail closed (refuse when a marker is unpaired), resolve symlinks, keep encodings and line endings, and
test the round trip (add, update, remove) on files with content around the block.

## 9. The dogfood loop itself

What worked: every navigation question during the work went to the tool first, the answer was checked against the
source, and each failure was written down as (question, the tool's answer, what the source shows, cause, fixed or not)
with a regression test that fails on the old code. Seven limitations came out of one round (five fixed: private classes
not typing receivers, the wrong Incomplete count, recursive evidence lines, data files in `uses`, nested functions),
and the owner's rule for each new language is at least three real repositories plus a sampled precision check.

**For QAKB:** use it on its own test suite from the first week; log every answer that was wrong, incomplete, noisy or
misleading in the same five columns; one regression test per entry.

## Audit (0.2.5 → 0.2.8, 2026-11-17)

Dogfood during the audit: devkb's own graph (built by the code under audit, 3,375 nodes) answered the navigation
questions first.

| Query | Answer | Checked against | Verdict |
|---|---|---|---|
| `uses` for `shell=True`, `eval/exec`, `pickle.load`, `os.system` | 0, 0, 1, 0 hits | git grep | right (4/4) |
| `symbol load_index --source`, `docs dogfood` | the function; 7 documents | the file; git grep | right |
| graph: private functions with no caller in changed files | 2 (`_moved_files`, `_bmad_unknown_cached`) | git grep | **both used**: passed as values, not called |
| `pack refactor _moved_files` | 0 callers, **Complete** | `pool.submit(self._moved_files, ...)` | **wrong** (false Complete) |
| reviewer, tools layer: `symbol`, `outline`, `uses`, `pack refactor` ×2, `symbol --source` | 6 answers | grep, source | right (6/6); `uses` truncates at 3 hits per file without naming the cap |
| reviewer, C#: 8 queries (`symbol`, `uses`, `outline`, `pack refactor` ×3) | | grep, source | 7 right (one Incomplete, honestly, naming the file to search); **`symbol field_type` says `callers 1`: the only call is the method calling itself**, so dead code looks used |
| reviewer, C/C++: 6 queries | | grep, source | 5 right; **`pack refactor _match_close` lists `devkb/test_discovery.py` as a test file** (a source module named `test_*`); `pack refactor locals_of` missed a call through a receiver typed `object` but said Incomplete |

Totals: 25 queries, 21 right, 1 honestly incomplete, 3 wrong or misleading, all three a *claim about absence or kind*
(no other caller, Complete, "is a test"), none a wrong location or body.

Audit findings (each reproduced; repro scripts kept with the audit): `devkb init` 3 ways to damage a user's file and
1 crash; read tools 3 wrong answers (dot-directory paths, a rejected regex reported as no match, non-ASCII paths); C#
5 (a verbatim string `@""""` blanks the rest of the file, sibling local functions, non-ASCII identifiers, two
quadratic paths); C/C++ 7 (a name split into a fake type and local, a brace-initialised member read as the body,
unbalanced braces across `#ifdef`, template declarations read as calls, a quadratic path, unguarded recursion, a
memory release that frees nothing).

## 10. Two more, from the audit's dogfood

- **A self-call is not a caller.** `symbol field_type` counted the method's call to itself and showed `callers 1`; the
  method is dead code. For QAKB: "this test is used by 1 suite" must not count the suite's reference to itself.
- **A name is not a kind.** `devkb/test_discovery.py` was listed as a test because it starts with `test_`. For QAKB:
  classify tests by what the runner collects (the framework's own discovery, markers, configuration), never by
  filename alone; a wrong "this is a test" inflates coverage.

## Status in 0.2.8

- Issues filed from the two audits and the fixing that followed: #50–#95 (one per defect, before any fix).
- Fixed in 0.2.8 (each with a test that fails on 0.2.7): #50–#52, #54, #55, #57–#66, #69–#74, #78–#83, #86, #87,
  #89–#93. Known and open (low severity, or found last): #53, #56, #67, #68, #75–#77, #84, #85, #88, #94, #95.
- Lessons 2, 3, 5 and 10 above are partly built into 0.2.8: a function passed as a value makes a pack Incomplete and
  names the line (#69), a self-call is not a caller (#70), a `test_*.py` outside the project's test paths is source
  (#71), a caller count says when it is partial (#87), a rejected search pattern is an error, not "no match" (#55).

0.2.9 (final review of 0.2.8 installed from PyPI): the `devkb` command now prints a subcommand's error message, so
#50's refusal reaches the user instead of a silent exit status 1 (#99, present since 0.1.0: a fix that only its unit
test saw); `symbol` accepts `module.name` (#100, found twice by dogfooding). Lesson: **review the installed release
through its real entry point**, not only through the functions the tests call.

Companion reports: `devkb-for-auditing.md` (how much of an audit devkb carried, measured from transcripts, and its
limits as QAKB requirements) and `bugfix-benchmark.md` (plain against devkb on six of these fixes).
