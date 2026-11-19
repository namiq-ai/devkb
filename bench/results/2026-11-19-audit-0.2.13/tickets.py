"""The 0.2.13 audit's findings, grouped by root cause, as tickets in the repository's ticket standard.
Usage: tickets.py render OUTDIR   (one .md per ticket, plus index.json) | tickets.py file OUTDIR (gh issue create)"""
import json, subprocess, sys
from pathlib import Path

A = Path(__file__).resolve().parent
REL = "bench/results/2026-11-19-audit-0.2.13"
V = {(r["run"], r["id"]): r for r in map(json.loads, open(A / "verified.jsonl"))}

# key, title, priority, labels, who/why, expected (list), scope, where, members [(run, id)]
T = [
 ("g-replace-not-grep", "A search the hook replaces gets every line grep would print: no capped call sites, substring matches, definition lines, comments or docs dropped", "high", ["bug"],
  "agents whose search is replaced (denied) by the graph's answer. SPEC-DKB-005 replaces a search only when the answer is the search's result, but the call-site answer is built from resolved uses, so it caps call sites and drops what grep matches as text: longer identifiers containing the name, the definition line, comments, strings, and lines in docs or config folders. The agent never sees those lines unless it repeats the search, which the answer's first line asks but does not force.",
  ["a replacement is given only when its lines are the lines grep prints for that command (same files and lines); otherwise the answer goes alongside", "the test compares the replacement with grep's real output on fixtures with substring matches, comments, docs folders and more call sites than the cap"],
  "`scripts/devkb_guardrail.py` (`shaped_answer`, the substitute decision); tests", "the substitute branch (`shaped_answer`/substitute, around L815 and L1043-1052) and `uses` capping",
  [("aguardrail-main-r2", "replace-hides-lines"), ("aguardrail-main-r2", "replace-hides-substring-matches"), ("aguardrail-main-r1", "replace-hides-comment-mentions"),
   ("aguardrail-nonekeep-r1", "replace_hides_uses"), ("aguardrail-nonekeep-r2", "uses-cap-hides-callers"), ("aguardrail-nonekeep-r2", "deny-hides-substring-matches"), ("aguardrail-nonekeep-r2", "deny-hides-doc-matches")]),
 ("g-def-prefix", "A definition search is not replaced when grep also prints definitions of longer names that start with the same text", "high", ["bug"],
  "agents searching `def resolve`: grep also prints `def resolve_file`, `def resolve_all`; the hook denies the search with the one definition named exactly, so the agent loses the others.",
  ["a definition pattern that is a prefix of other defined names (no word boundary) is answered alongside, or with every definition grep would print", "a pattern with `\\b`, `(` or `-w` keeps today's exact-name answer"],
  "`scripts/devkb_guardrail.py` definition answer; tests", "the definition branch around L1013 (`definition:one-definition`)",
  [("aguardrail-main-r1", "def-prefix-hides-lines"), ("aguardrail-nonekeep-r1", "definition_prefix_hides")]),
 ("g-names-cut-3", "A search for four or more names is never replaced by an answer for the first three", "high", ["bug"],
  "agents searching for several names at once: `misses.navigation_names` returns `names[:3]`, the hook answers those three, calls it Complete and replaces the search, so every line for the fourth and later names disappears.",
  ["a search with more names than the hook answers is never replaced; the names it did not ask about are listed or the answer goes alongside", "the log records every name the search asks about"],
  "`devkb/misses.py` `navigation_names`, `scripts/devkb_guardrail.py`; tests", "`devkb/misses.py:59` (`return names[:3]`), used at `scripts/devkb_guardrail.py:973`",
  [("aguardrail-nonekeep-r2", "four-names-answered-for-three")]),
 ("g-stale-rename", "A graph built before a file was renamed never replaces a search", "medium", ["bug"],
  "agents in a checkout where a code file was renamed (git mv) after the build: `graph_stale` does not treat the rename as a change, so the hook replaces grep with an answer that has none of the renamed file's lines. Related to #273 (another way the stale rule misses).",
  ["a renamed, added or deleted code file in the searched scope makes the graph stale for that search, as a modified one does"],
  "`scripts/devkb_guardrail.py` `graph_stale`; tests", "`graph_stale` (L942-962): the porcelain parsing of `R  old -> new` and `changed_since_build`",
  [("aguardrail-nonekeep-r2", "stale-rename-still-replaces-grep")]),
 ("g-def-shapes", "A definition search is answered in the shape its grep options ask for: a location for a plain search, the asked-for lines for -A/-B, the body in every defining file", "medium", ["bug"],
  "agents reading or locating definitions. Five shapes are wrong today: a plain `grep -n 'def f'` (locate, SPEC-DKB-007 §3.3: one location line) gets the whole body, far larger than grep's one line; `-A10` on a function over 80 lines is replaced with no body lines at all; a definition in the second file that defines the name gets no body and the false reason 'its end is not known'; `-B N` loses the lines above the definition; a call-site name with `-A/-C` is answered with the definition's body instead of the call site.",
  ["locate (no context options) is answered with location lines only", "a replacement for `-A/-B/-C` carries the lines those options ask for, or the search is not replaced", "every defining file gets its body, with a true reason when one is cut", "a name that is not a definition pattern is not answered with a body"],
  "`scripts/devkb_guardrail.py` (`definition_answer`, the read-body/locate branches); tests", "`definition_answer` (L760-771) and the definition branch (L995-1035)",
  [("aguardrail-main-r1", "def-answer-larger-than-grep"), ("aguardrail-main-r2", "locate-gets-body"), ("aguardrail-nonekeep-r1", "locate_answers_whole_body"),
   ("aguardrail-main-r2", "long-def-denied-without-body"), ("aguardrail-nonekeep-r2", "deny-long-body-no-lines"), ("aguardrail-main-r2", "scoped-definition-no-body"),
   ("aguardrail-nonekeep-r1", "definition_second_has_no_body"), ("aguardrail-nonekeep-r1", "before_context_hidden"), ("aguardrail-nonekeep-r2", "deny-before-context-hides-decorator"),
   ("aguardrail-nonekeep-r1", "context_callsite_gets_body")]),
 ("g-head", "An answer to a search cut by `| head -N` or Grep `head_limit` is never larger than the cut output", "medium", ["bug"],
  "agents that limit a search's output: the hook ignores a trailing `| head -N` / `| tail -N` and Grep's `head_limit`, so a replacement or an alongside answer carries more lines than the command prints (SPEC-DKB-007 R5).",
  ["a trailing head/tail or head_limit caps the answer at that many lines, or the answer is left out"],
  "`scripts/devkb_guardrail.py` (pipe parsing, `capped`); tests", "the pipe-filter parsing near L259 and the size budget",
  [("aguardrail-main-r2", "answer-larger-than-head"), ("aguardrail-nonekeep-r1", "head_trim_ignored"), ("aguardrail-nonekeep-r2", "deny-larger-than-trimmed-output")]),
 ("g-outline-shape", "A listing of one kind of definition gets only that kind, never a whole outline or another language's definitions", "low", ["bug"],
  "agents listing `^class ` or `^def ` lines, or searching a keyword as text: the hook adds the file's whole outline (constants, methods, functions), larger than grep's output; a keyword search (`async`, `static`) is answered with an outline; `^def alpha` lists a JavaScript `function alpha`.",
  ["`^class `/`^def ` listings get only that kind's symbols, within grep's size", "a keyword searched as text gets nothing", "a language-specific pattern lists only that language's definitions"],
  "`scripts/devkb_guardrail.py` (`outline_answer`, intent rules); tests", "`outline_answer` (L869-883), the keyword rule near L492, the definition answer near L1013",
  [("aguardrail-main-r2", "outline-wider-than-grep"), ("aguardrail-nonekeep-r1", "list_symbols_wrong_kinds"), ("aguardrail-nonekeep-r2", "list-symbols-answer-larger-than-grep"),
   ("aguardrail-main-r2", "keyword-literal-gets-outline"), ("aguardrail-main-r1", "def-pattern-lists-other-language")]),
 ("g-teach", "The teach line's command runs as written, from the search's directory, for the answer it follows", "medium", ["bug"],
  "every agent since D1 is on by default (#267): the suggested `devkb … --project .` fails when the search ran in a subdirectory ('no devkb graph at …/pkg/.devkb'); it can name another name than the one answered (a string-key answer for `beta_key` followed by `devkb uses alpha_sym`); a path with a space is not quoted.",
  ["the suggested command works when pasted in the directory the search ran in (`--project` names the repository root)", "it names the command for the answer it follows", "paths are shell-quoted"],
  "`scripts/devkb_guardrail.py` `teach_command` and its caller; tests", "`teach_command` (L695-705) and where it is chosen (L1057-1065)",
  [("aguardrail-main-r2", "teach-command-wrong-dir"), ("aguardrail-nonekeep-r1", "teach_line_other_name"), ("aguardrail-nonekeep-r2", "teach-line-unquoted-path")]),
 ("g-log-stats", "The guardrail log names the graph question an answer came from, and guardrail-stats counts every decision kind", "medium", ["bug"],
  "maintainers reading `devkb guardrail-stats` and the decision log (the evidence SPEC-DKB-007 §3.5 names for changing the intent table): a call-site answer built from `uses` is logged with question `pack refactor`, an outline answer with `none`; `outline-on-open` decisions are left out of the counts.",
  ["`question` is the query the answer was built from", "guardrail-stats counts every action the hook logs, including outline-on-open"],
  "`scripts/devkb_guardrail.py` (`question_of`, `log_decision`), `devkb/outcomes.py`; tests", "`question_of` (L639-645), `log_decision` (L708-720), `devkb/outcomes.py:113`",
  [("aguardrail-nonekeep-r1", "logged_question_wrong"), ("aguardrail-main-r2", "stats-omit-outline-on-open"), ("aguardrail-nonekeep-r1", "stats_omits_outline_on_open")]),
 ("g-misslog", "A one-file grep with a pipe, a redirection or a leading cd is logged as a graph miss, and a miss names its Allman-style C/C++ function", "medium", ["bug", "graph-miss"],
  "maintainers using `devkb misses` (AGENTS.md rule 7): #137 handled `grep -n NAME file`, but `… | head -5`, `2>&1`, `2>/dev/null` and `cd lib && grep -n NAME x.rb` still log nothing; #138's text scan names no function when the brace is on its own line.",
  ["each of those forms writes the miss with `file:line`", "a match inside `int Foo::bar(int x)\\n{` names `Foo::bar`"],
  "`scripts/devkb_guardrail.py` `single_bash_file`, `devkb/misses.py` enclosing scan; tests", "`single_bash_file` (L147-166), `devkb/misses.py:199`",
  [("aguardrail-main-r2", "miss-single-file-forms"), ("aguardrail-main-r2", "miss-enclosing-allman")]),
 ("r-star-reexport", "A call through a star re-export (`from .sub import *`) is attributed, or the pack says Incomplete", "high", ["bug"],
  "agents changing a function re-exported by `from .sub import *` in a package `__init__`: its callers through the package are not attributed and `pack change`/`refactor` say Complete with no caller and no test. #192 fixed named re-exports only.",
  ["the callers and their tests are listed, or the pack says Incomplete and names the files"],
  "`devkb/build_symbols.py` cross-file resolution; tests", "`_resolve_cross_file_symbol` re-export following (#192) and `_star_modules`",
  [("agraph-main-r2", "star-reexport-callers-missing"), ("agraph-nonekeep-r1", "star-reexport-call-unattributed"), ("agraph-nonekeep-r2", "star-reexport-complete")]),
 ("r-const-reads", "A module constant's reads are attributed exactly: local bindings that shadow it are not reads, and a read through a dotted module path is", "medium", ["bug"],
  "agents changing a module constant (#143, #198): a lambda parameter, an `except … as NAME`, a `case [NAME, _]` capture or a method default in a class that defines the name is attributed as a read of the module constant; `pkg.mod.LIMIT` is not attributed and the pack still says Complete.",
  ["those local bindings are not reads of the module constant", "a dotted-path read is attributed, or the pack says Incomplete"],
  "`devkb/build_symbols.py` (`_bound_names`, `_uses_in_tree`, the Attribute branch); tests", "`_bound_names` (L318), `_uses_in_tree` (L388-413)",
  [("agraph-main-r1", "constant-shadowed-locals"), ("agraph-main-r2", "lambda-param-shadows-constant"), ("agraph-main-r2", "class-default-arg-shadow"),
   ("agraph-nonekeep-r2", "const-lambda-param"), ("agraph-nonekeep-r2", "const-except-match-binding"), ("agraph-nonekeep-r1", "constant-dotted-read-unattributed"), ("agraph-nonekeep-r2", "const-dotted-module-read")]),
 ("r-environ-key", "`os.environ['K']` and `'K' in os.environ` are not counted as a record's string-key reads", "low", ["bug"],
  "agents asking `symbol K` for a key: #202 excluded `os.environ.get('K')`, but the subscript and membership forms are still reported as record key reads.",
  ["environment reads in every form are excluded from record keys (or reported as environment reads)"],
  "`devkb/build_symbols.py` key-use extraction; tests", "the Subscript branch (L408-410) lacks the `_is_environ` check the Call branch has (L421)",
  [("agraph-main-r1", "environ-subscript-counted-as-key"), ("agraph-nonekeep-r2", "key-environ-subscript")]),
 ("r-quadratic-names", "Build time stays linear when many symbols share a name and many calls to it are unresolved", "medium", ["bug"],
  "repositories with many same-named functions (`run`, `main`): 800 files each defining `run()` and 800 unresolved callers make `_could_reach` run 640,000 times. #194 fixed the typed-receiver case only.",
  ["work grows with the number of unresolved calls plus definitions, not their product"],
  "`devkb/build_symbols.py`; a timing test like #194's", "`_could_reach` per symbol over `by_target[short]` (L1684)",
  [("agraph-main-r1", "build-quadratic-same-name-defs")]),
 ("r-macro-scope", "A repository macro is expanded only where it is visible: in files that include its header, and not after `#undef` or a redeclaration", "medium", ["bug"],
  "agents reading C/C++ callers since #118: a function-like macro is expanded by name across the repository, so `new_user()` in a file that never includes `legacy.h` is said to reach `legacy_helper`; a name `#undef`'d or redeclared as a function still expands. This adds wrong edges on top of the union rule the owner kept for `#if` variants.",
  ["a macro applies in the files that define it or include its header, and stops at `#undef` or a redeclaration", "the union rule for `#if` variants is unchanged"],
  "`devkb/cpp_resolve.py`, `devkb/cpp_graph.py` macro expansion; tests", "macro expansion in `cpp_resolve.py` (#118)",
  [("agraph-main-r1", "macro-after-undef"), ("agraph-main-r2", "cpp-macro-leaks-into-unrelated-file")]),
 ("r-cpp-overload-pack", "A pack for an overloaded C++ method offers choices an agent can tell apart, or covers every overload", "medium", ["bug"],
  "agents asking `pack change W::draw` for overloads: the ambiguity list prints identical names (`w.cc::W.draw` twice) and asks to 'pass one as path::name', which cannot be done.",
  ["each choice carries its line or signature and can be passed back", "or the pack covers all overloads and says so"],
  "`devkb/packs.py` candidate listing; tests", "`devkb/packs.py:297`",
  [("agraph-main-r1", "cpp-overload-ambiguity-identical"), ("agraph-main-r2", "cpp-overload-candidates-indistinguishable"), ("agraph-nonekeep-r1", "cpp-overload-pack-ambiguous"), ("agraph-nonekeep-r2", "cpp-overload-ambiguous-choices")]),
 ("r-cpp-footer", "A C/C++ pack's notes are true: the limits footer says macros are expanded, and a Run line is a runnable command or absent", "low", ["bug"],
  "agents reading C/C++ packs: the footer still says 'no preprocessor expansion' after #118; a pack listing a C++ test prints an empty `Run: ```.",
  ["the footer states what the resolver does and does not see today", "no empty Run line"],
  "`devkb/cpp_symbols.py` footer text, `devkb/packs.py` Run line; tests", "`devkb/cpp_symbols.py:31` and `:39`; the tests section of packs",
  [("agraph-main-r1", "cpp-pack-stale-limits"), ("agraph-nonekeep-r2", "cpp-pack-stale-macro-footer"), ("agraph-main-r2", "cpp-pack-empty-run-command")]),
 ("r-nograph-commands", "`devkb audit`, `coverage` and `query` on a repository with no graph print one line naming `devkb build --project PATH`", "low", ["bug"],
  "users who run these before building: #212 fixed the read commands, but `audit`, `coverage` and `query` print a traceback or point at `python3 devkb/build.py --project CODE`.",
  ["every query command prints the same one line as #212 and exits 2"],
  "`devkb/cli.py` routes for audit, coverage, query; tests", "`devkb/cli.py:37` and the coverage entry point",
  [("agraph-main-r1", "audit-no-graph-traceback"), ("agraph-main-r2", "audit-no-graph-traceback"), ("agraph-nonekeep-r1", "audit-no-graph-traceback"), ("agraph-nonekeep-r2", "nograph-audit-query-coverage")]),
 ("o-malformed-starves", "An item whose model answer is malformed is backed off, not judged and paid for again on every run ahead of the others", "medium", ["bug"],
  "the triage daemon's owner: #205 made a malformed answer fail only its item, but the item stays first in line and is judged again on every run, so it costs a model call each time and starves later items (30 model calls over 3 runs, item #5 never judged).",
  ["a failed item is retried with a back-off (or after N failures needs a maintainer)", "other items are judged in the meantime"],
  "`ops/triage/triage.py` (`cmd_triage`, `feedback_pass`); tests", "`cmd_triage` (~L513) and `feedback_pass` (~L389)",
  [("aops-main-r1", "triage-malformed-starves"), ("aops-main-r2", "triage-malformed-answer-starves-queue"), ("aops-nonekeep-r1", "triage_failed_items_starve_queue"), ("aops-nonekeep-r2", "triage-failed-item-retried-every-run")]),
 ("o-label-recomment", "A failed label edit after the triage comment does not make the next run comment on the same item again", "medium", ["bug"],
  "outside contributors and maintainers: since #206 the comment is posted before the label; when the label edit then fails, the next run sees an unlabelled item and comments (and pays) again.",
  ["an item that has the daemon's comment is not commented again; the label is retried alone"],
  "`ops/triage/triage.py` triage apply; tests", "`ops/triage/triage.py:503-504`",
  [("aops-main-r1", "triage-label-failure-recomments"), ("aops-main-r2", "triage-label-failure-repeats-comment"), ("aops-nonekeep-r1", "triage_label_failure_duplicate_comment")]),
 ("o-feedback-lost", "A transient GitHub error while filing a feedback ticket leaves the comment to be handled on the next run", "medium", ["bug"],
  "maintainers commenting on the daemon's work: #206 marks the comment seen before posting so nothing is filed twice, but when `gh issue create` fails the comment is never handled (0 tickets, 0 replies).",
  ["a comment whose ticket was not created is retried on the next run; one that was created is never filed twice"],
  "`ops/triage/triage.py` `feedback_pass`; tests", "`ops/triage/triage.py:426-432`",
  [("aops-main-r1", "feedback-ticket-failure-loses-comment"), ("aops-main-r2", "feedback-create-failure-loses-comment")]),
 ("o-draft-retry-push", "A draft-pr issue can be retried after an earlier attempt pushed its branch but did not open the PR", "medium", ["bug"],
  "maintainers clearing handler-failed: #207 resets the local branch, but the retry's push is rejected (non-fast-forward) by the branch the first attempt pushed.",
  ["the retry pushes over its own earlier auto branch (or uses a new one) and opens the PR"],
  "`ops/triage/triage.py` `handle_draft_pr`; tests", "the push in `handle_draft_pr` (~L717)",
  [("aops-main-r1", "draft-pr-retry-remote-branch"), ("aops-main-r2", "draft-pr-retry-push-rejected"), ("aops-nonekeep-r1", "triage_push_retry"), ("aops-nonekeep-r2", "triage-draft-pr-retry-push-rejected")]),
 ("o-sandbox-timeout", "A hanging test in the sandbox fails its item instead of aborting the whole handle run", "medium", ["bug"],
  "the daemon's owner: a draft fix whose tests hang raises `TimeoutExpired` out of the handle run, so later items are not handled and the hung item is retried and paid for again.",
  ["the item is marked handler-failed and the run goes on"],
  "`ops/triage/triage.py` handle loop; tests", "`ops/triage/triage.py:538-539` and `:736`",
  [("aops-main-r1", "handle-sandbox-timeout-aborts-run"), ("aops-nonekeep-r1", "triage_handle_timeout")]),
 ("o-read-tree-origin", "With TRIAGE_REPO set, the tree the triage, plan and feedback agents read is that repository's main", "low", ["bug"],
  "owners running the daemon for another repository: #208 moved the review fetch, the draft base and the push to TRIAGE_REPO, but the daemon's own read tree is still updated from `origin`.",
  ["`update_tree` fetches TRIAGE_REPO's main"],
  "`ops/triage/triage.py` `update_tree`; tests", "`update_tree` (~L292)",
  [("aops-main-r1", "triage-repo-override-reads-origin"), ("aops-nonekeep-r2", "triage-read-tree-from-origin")]),
 ("o-verdict-text", "A verdict is validated and posted text carries no closing keyword in any form GitHub honours", "low", ["bug"],
  "maintainers and outside contributors: a verdict with `duplicate_of: true` is posted as 'a duplicate of #True'; titles and summaries keep `Fixes GH-5`, which GitHub honours as a closing keyword.",
  ["a non-integer duplicate_of is refused", "every closing-keyword form (#N, GH-N, owner/repo#N) is neutralised"],
  "`ops/triage/triage.py` verdict checks and the CLOSING rule; tests", "`ops/triage/triage.py:234-237` and `:608`",
  [("aops-main-r1", "triage-duplicate-of-true"), ("aops-nonekeep-r2", "triage-duplicate-of-boolean"), ("aops-nonekeep-r1", "triage_closing_keyword_gh_form")]),
 ("b-flaky-order", "A suite that fails the same way on every full run is red, even when the failed test passes on its own", "high", ["bug"],
  "every benchmark result: #260 re-runs a red suite's failed tests on their own and calls those that pass flaky. A test that fails only after another test (order dependence, which an agent's new test can cause) passes alone, so a change that breaks the suite is scored green.",
  ["a run counts as flaky only if the full suite passes when run again; failed tests that pass alone but fail again in a second full run make the suite red"],
  "`bench/policy/policybench.py` `run_suite`; tests", "`run_suite` (L290-309)",
  [("aops-main-r1", "flaky-rule-hides-order-dependence"), ("aops-main-r2", "suite-order-failure-scored-green")]),
 ("b-nav-rule", "A devkb query is a self-test only after an edit of the checkout's own devkb code, and a quoted fixture path counts as a fixture", "medium", ["bug"],
  "the release table's devkb navigation column (#258, #263): the edit rule matches `devkb/` anywhere in an absolute path, so a checkout under a folder named `devkb` makes every query after any edit a self-test; `--project \"/tmp/fixture\"` with quotes counts as navigation.",
  ["the rule looks at the path relative to the checkout root", "quoted and unquoted fixture paths are treated alike"],
  "`bench/policy/storybench.py` (`devkb_commands`, the edit rule), `bench/policy/release_table.py`; tests", "`storybench.py:231` and `release_table.py:50` (`re.search(r\"(^|/)(devkb|scripts)/\", file_path)`), `devkb_commands` (~L139)",
  [("aops-nonekeep-r1", "bench_edit_rule_matches_parent_dir"), ("aops-nonekeep-r1", "bench_selftest_quoted_project"), ("aops-nonekeep-r2", "bench-quoted-fixture-project-counted-as-navigation")]),
 ("b-timeout-free", "A run cut off by the timeout is not recorded with zero cost and zero context", "medium", ["bug"],
  "release tables: a timed-out run has no final result message, so `transcript()` records cost 0 and context 0, and the arm looks cheaper.",
  ["a cut-off run's cost and context are estimated from the messages' usage, or the run is flagged and left out of the means"],
  "`bench/policy/storybench.py` `transcript`; tests", "`storybench.py:194-205`",
  [("aops-main-r1", "timeout-run-scored-as-free")]),
 ("b-table-nav-stored", "The release table uses the stored devkb navigation counts when the transcript is not in the harness folder", "medium", ["bug"],
  "anyone rebuilding a release table from saved results (as the 0.2.13 report does): `counts()` reads the transcript from `bench/policy/runs/` and returns 0 when it is elsewhere, ignoring the row's `devkb_nav`/`devkb_selftest`.",
  ["the row's stored counts are used when the transcript is not found"],
  "`bench/policy/release_table.py`; tests", "`release_table.py:29-34` and `:83`",
  [("aops-main-r1", "release-table-nav-from-missing-transcript")]),
 ("b-setup-retry", "A run whose setup failed by accident, or whose base was red, is set up again in the next batch", "medium", ["bug"],
  "benchmark batches: a setup error (network, uv) is recorded as `base-red` and skipped forever; a run refused for a red base is never retried after the base is fixed.",
  ["a setup error is recorded as an error and retried", "a red-base run is retried when its base commit's suite is green"],
  "`bench/policy/policybench.py` `run_one`/`_run_one`; tests", "`policybench.py:224` and `:236-238`",
  [("aops-main-r1", "base-red-run-never-rerun"), ("aops-main-r2", "bench-setup-failure-recorded-as-base-red"), ("aops-nonekeep-r1", "bench_base_red_run_never_retried")]),
 ("b-score-arms", "Scoring one arm keeps the other arms' rows in results-ISSUE.jsonl", "medium", ["bug"],
  "anyone re-scoring an arm with `POLICY_ARMS`: `score` rewrites results-ISSUE.jsonl with only that arm's rows, and the release table loses its baseline.",
  ["re-scoring an arm replaces only that arm's rows"],
  "`bench/policy/policybench.py` `score`; tests", "`score` (~L340)",
  [("aops-main-r1", "score-arms-filter-overwrites-results"), ("aops-nonekeep-r2", "bench-score-arm-filter-truncates-results")]),
 ("b-template-key", "A checkout template is keyed on everything that changes its content", "medium", ["bug"],
  "benchmark batches using `POLICY_PREREGISTER_POST`: the template key is arm, base commit and devkb commit only, so a batch that sets the variable reuses a template built without the post hook.",
  ["every setting that changes a checkout's content is part of the template key"],
  "`bench/policy/policybench.py` `template_for`; tests", "`template_for` (~L175)",
  [("aops-main-r2", "template-key-ignores-preregister-post"), ("aops-nonekeep-r1", "bench_template_key_ignores_preregister"), ("aops-nonekeep-r2", "bench-template-ignores-preregister-post")]),
 ("b-storybench-rules", "storybench runs are scored with the same rules as policybench runs", "medium", ["bug"],
  "anyone using storybench results: its rows lack the check hash, the failed and flaky test lists and the green-base record (#221, #223, #260).",
  ["storybench's score uses the shared scoring (score_run, run_suite) and carries the same fields"],
  "`bench/policy/storybench.py` score and checkout; tests", "`storybench.py` score (~L228), checkout (~L72)",
  [("aops-nonekeep-r2", "bench-storybench-score-old-rules")]),
 ("b-counters-text", "toolmix and listing_then_read count only what agents ran: no devkb use from quoted text, no reads outside the listed folder", "low", ["bug"],
  "the tool-mix and listing studies: a commit message or comment mentioning `devkb symbol` counts as devkb use; reads after a bare `ls` count files outside the listed folder.",
  ["quoted text and comments are not commands", "only reads inside the listed folder count"],
  "`bench/audit/toolmix.py`, `bench/exploration/listing_then_read.py`; tests", "`toolmix.py:17-22`, `listing_then_read.py:44-49, 113`",
  [("aops-main-r2", "toolmix-counts-quoted-text-as-devkb"), ("aops-main-r2", "listing-then-read-counts-files-outside-cwd")]),
]


def body(t):
    key, title, pri, labels, who, expected, scope, where, members = t
    runs = sorted({r for r, _ in members})
    arms = sorted({r.split("-")[1] for r in runs})
    L = [f"**Found by** the 0.2.13 release audit (2026-11-19), a bi-arm benchmark of three reviewers with and without devkb "
         f"(`{REL}/`). Found in {len(runs)} of the 12 runs: {', '.join(runs)}; arms: {', '.join('no devkb' if a == 'nonekeep' else 'devkb 0.2.13' for a in arms)}. "
         f"Every reproduction exits 1 twice on a clean checkout of main 3f56ece.", "",
         f"**Who is affected and why it matters ({pri}):** {who}", "", "**Reproduce** (from the root of a checkout of main 3f56ece; each run's scripts expect to sit in `audit/`, where the reviewer wrote them):"]
    for run, fid in members[:3]:
        v = V.get((run, fid))
        if not v:
            continue
        L += ["```", f"rm -rf audit && cp -r {REL}/runs/{run} audit && PYTHONPATH=audit .venv/bin/python {v['repro']}"]
        out = [l for l in v["output"].strip().splitlines() if l.strip()][-6:]
        L += [l[:220] for l in out] + ["```"]
    if len(members) > 3:
        L.append(f"Also: {', '.join(f'`{run}/{fid}`' for run, fid in members[3:])}.")
    L += ["", "**Expected:**"] + [f"- {e}" for e in expected]
    L += ["", f"**Scope:** {scope}.", "", f"**Where to start:** {where}.", "",
          "**Done when:** each reproduction above exits 0, a regression test for each case fails on main 3f56ece and passes "
          "after the fix, and the full suite is green."]
    return "\n".join(L) + "\n"


if __name__ == "__main__":
    out = Path(sys.argv[2]); out.mkdir(parents=True, exist_ok=True)
    idx = []
    for t in T:
        (out / f"{t[0]}.md").write_text(body(t))
        idx.append({"key": t[0], "title": t[1], "priority": t[2], "labels": t[3], "members": t[8]})
    (out / "index.json").write_text(json.dumps(idx, indent=1))
    missing = [(k, m) for k, *_, ms in T for m in ms if m not in V]
    print(len(T), "tickets;", sum(len(t[8]) for t in T), "findings grouped; missing from verified:", missing)
    if sys.argv[1] == "file":
        for t in T:
            r = subprocess.run(["gh", "issue", "create", "-R", "namiq-ai/devkb", "--title", t[1], "--body-file", str(out / f"{t[0]}.md"),
                                "--assignee", "hungle-namiq", *sum((["--label", l] for l in t[3] + [f"priority: {t[2]}"]), [])],
                               capture_output=True, text=True)
            url = r.stdout.strip().splitlines()[-1] if r.stdout.strip() else "ERROR " + r.stderr[-200:]
            print(t[0], url, flush=True)
            for i in idx:
                if i["key"] == t[0]:
                    i["issue"] = url
        (out / "index.json").write_text(json.dumps(idx, indent=1))
