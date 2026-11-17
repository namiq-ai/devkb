<!-- devkb:begin (managed by `devkb init`; edit outside this block) -->
## devkb: ask the graph before you read or change code

This repository has a graph of its code in `.devkb/`: calls, tests, raised errors, commits, configuration. One call
returns what would take a dozen searches and file reads, and every item carries the line of code that proves it. The
graph does not hold *how the code is written*: to copy a pattern or learn a style, read the file.

**Choose by what you are about to do:**

**Instead of grep, to read code**: the graph holds every definition with its exact lines, so ask it rather than guess
`grep -A25`:
- `symbol(query)` (shell: `devkb symbol QUERY --source`): where a name is defined, with exact lines and the signature;
  `source=True` prints the body. A query can be a name, `Class.method`, `path::name`, a glob `parse_*`, `re:regex`, a
  prefix or a few words; a typo is tolerated, and below the confidence floor it says there is no match and suggests names.
- `outline(path)` (shell: `devkb outline PATH`): a file's symbols in order with line ranges, and its imports: look before you read.
- `uses(name)` (shell: `devkb uses NAME`): where a name, constant, module or key appears, grouped by the symbol that
  contains each use. Text matches, not resolved references.
- `search_docs(query)` (shell: `devkb docs QUERY`): what the documentation says, with the heading of each hit.
A symbol in a language that stores no end line (TypeScript, JavaScript) is reported as "end unknown": read from its start.


| You are about to... | Use | You get |
|---|---|---|
| open a file to see what depends on it, or edit it | `pack(kind="file", subject=PATH)` (shell: `devkb pack --project . file PATH`) | the functions other files call, the files that depend on it, the tests to run |
| change a function's behaviour or signature | `pack(kind="change", subject=NAME, path=PATH)` (shell: `devkb pack --project . refactor NAME`) | callers at any depth, tests among them |
| start from an error message or a failing request | `pack(kind="error", subject="MESSAGE")` | what raises it, the handlers that reach it |
| find who calls one function directly | search with grep | one hop: a pack adds a step and saves nothing |
| learn how a pattern is written, to copy it | read the file | the graph does not store this |
| decide which tests to run | `tests_to_run` or `tests_for` | the tests, ranked |
| review a commit or a diff | `review_pack` | changed functions, outside callers, untested changes |
| find a setting or a service | `config` | where it is declared and read |

**How to work:**
1. Ask first, read second. Run the pack for a file before you read it to judge impact and before your first edit of it.
   In Claude Code the devkb hook also adds that pack to your first Edit or Write of each file; read it, then continue.
2. A pack marked **Complete** is the whole answer: do not search again to check it. If it is Incomplete, search only the
   files it names. If it says files changed since the graph was built, re-read those files.
3. After editing, run the tests the pack named first, then the full suite. If you edited many files, rebuild first:
   `devkb build --project .` (a few seconds on most repositories).
<!-- devkb:end -->

## Developing devkb: devkb first, logged (#126)

This repository is devkb itself, so every session that works on it is also a test of it.

1. **Ask devkb before searching by text.** For "where is X defined", "who calls / uses X", "what is in this file",
   "what does changing X touch" and "which tests cover X", use the devkb tools above (the MCP server in `.mcp.json`,
   or the released `devkb` on your PATH: `devkb symbol|outline|uses|docs|pack ... --project .`). The same applies to
   the C/C++ corpus (`~/.cache/devkb/cpp-corpus/<repo>`, `--project` that path). Rebuild with
   `devkb build --project .` when the graph is older than the code you are reading.
2. **Check the answer against the source** before relying on it. grep, sed and Read remain right for filtering
   command output, literal strings, confirming an edit, and questions devkb has no tool for.
3. **Log every devkb query** in a JSONL beside the deliverable (spec, report, PR), one row per query: `phase`,
   `query`, `purpose`, `verdict` (`right` / `incomplete-honest` / `incomplete-silent` / `misleading` / `noisy` /
   `wrong` / `unsupported`), `source_showed`, `devkb` version. Example: `docs/specs/cpp-supported-dogfood.jsonl`.
   Summarise it in the deliverable under "How devkb was used".
4. **A wrong, misleading or silently incomplete answer is a defect.** File one issue per defect (reproduce
   command, actual, expected, where to start, done when) before anyone fixes it.
5. **The guardrail stays on.** `.claude/settings.json` runs `scripts/devkb_guardrail.py` before every Grep and every
   grep / rg / git grep search: it adds a reminder (it never blocks) and appends the firing to
   `~/.claude/hooks/devkb-guardrail.log`. `DEVKB_GUARDRAIL=0` turns it off for the control arm of a benchmark only.

Why: SPEC-DKB-004 was first written with grep; redone through devkb, the same questions found three devkb defects
(#114–#116). Use on real work is how devkb's gaps are found, and the log makes that use measurable.
