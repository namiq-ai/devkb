# devkb

[![PyPI](https://img.shields.io/pypi/v/devkb)](https://pypi.org/project/devkb/)
[![License: Apache-2.0](https://img.shields.io/badge/license-Apache--2.0-blue)](LICENSE)
[![DOI](https://zenodo.org/badge/DOI/10.5281/zenodo.24267143.svg)](https://doi.org/10.5281/zenodo.24267143)

**A knowledge graph of your repository for software development agents.** Agents answer "what calls this, what breaks, which tests"
in one step instead of searching file by file: 55% cheaper, with better answers, in our benchmark.

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="docs/img/benchmark-dark.svg">
  <img alt="Median cost per task: plain search $0.070 (quality 0.931); devkb 12 tools $0.059, 18% cheaper (0.955); devkb 7 tools $0.040, 38% cheaper (0.963); devkb pack $0.025, 55% cheaper (0.981)" src="docs/img/benchmark-light.svg">
</picture>

## 1. What devkb is

- **A graph** built from your source and git history: functions, calls, tests, routes, errors, configuration,
  commits, pull requests, tickets ([ontology](devkb/ontology.md)).
- **Packs**: one command answers a whole question (who calls this, what breaks, which tests to run), each item with
  the source line that proves it, and a statement of what the graph could not see.
- **An MCP server** giving agents the same answers as tools, for Claude Code, Codex and any MCP client.

Everything runs locally: devkb reads files and runs `git`, never your code (unless `devkb.json` opts in), and the graph never leaves your machine.

### Languages

| Language | Status | What devkb understands |
|---|---|---|
| Python | ✅ Supported | functions, classes, calls (through imports, re-exports, typed objects, base classes), tests, FastAPI/Flask routes, raised and logged errors, environment variables; every pack |
| TypeScript, TSX | 🟡 Partial | functions, components, classes, and the HTTP calls they make to backend routes; not calls between them |
| JavaScript (`.js`, `.mjs`) | 🟡 Partial | as TypeScript |
| C# | ✅ Supported | classes, structs, interfaces, records, methods, constructors, properties, local and extension methods; calls through typed receivers, call results (`a.B().C()`, `await`, `var`, `foreach`), property chains, lambda parameters (builder lambdas, LINQ), static calls and `new T()`; extension methods and overloads chosen by receiver type and by argument count and declared types; a table of .NET's common types (bases, members, conversions); xUnit/NUnit/MSTest tests; every pack. Checked against the compiler on MediatR, FluentValidation, Polly, Jellyfin and EF Core. Not: generic type inference, overload betterness, `dynamic`, LINQ query syntax, third-party types' hierarchies |
| Odoo XML | 🟡 Partial | templates and menus |
| Bash / shell | ⬜ Not yet | files and history only |
| C, C++ | 🟡 Partial | definitions, calls, tests, `throw`/`assert`/log-macro messages. Limits: no preprocessor expansion, no overload resolution, no type inference; an answer says Incomplete where a call could not be attributed. C and C++ are separate profiles: C resolves through linkage and treats a function-pointer or ops table as an unresolved indirect reference; a call across languages is linked only through `extern "C"`, `ctypes`/`cffi`, a `PyMethodDef` table or pybind11 `m.def`, and the pack of an exported function is Complete only for the languages read |
| Java, Rust, Go, others | ⬜ Not yet | files and history only |

"Files and history" is the language-independent layer every repository gets: files, commits, pull requests and
tickets.

## 2. How much it saves

Latest benchmark: the 7 open-source repositories in [`bench/repos.yaml`](bench/repos.yaml), 57 tasks, 1,138 agent
runs, the same model (Sonnet) in every arm, answers scored against truth computed from the source. Cost, turns and
tokens are the median run; saving is per task against plain search, averaged over tasks; quality is the mean score:

| | Plain search | devkb, 12 tools | devkb, 7 tools | devkb pack |
|---|---|---|---|---|
| **Cost per task** | $0.070 | $0.059 | $0.040 | **$0.025** |
| **Saving** | — | 18% | 38% | **55%** |
| **Quality** (0–1) | 0.931 | 0.955 (+0.024) | 0.963 (+0.032) | **0.981 (+0.050)** |
| Turns | 4 | 6 | 5 | **3** |
| Context processed (tokens) | 126k | 169k | 147k | **75k** |
| of which cache reads | 123k | 163k | 141k | 74k |
| of which new input and cache writes | 8.3k | 4.1k | 2.0k | 1.3k |
| Output tokens | 1.4k | 1.8k | 1.3k | 0.9k |

Saving and quality gain by repository (95% intervals in the results):

| Repository | Tasks | 7 tools: saving / quality | pack: saving / quality |
|---|---|---|---|
| lnbits | 10 | 53% / +0.032 | **66%** / +0.049 |
| Netflix Dispatch | 8 | 45% / +0.040 | **61%** / +0.081 |
| Prefect | 9 | 41% / −0.017 | **59%** / +0.047 |
| lattice-scan | 12 | 36% / +0.052 | **51%** / +0.058 |
| Mealie | 6 | 18% / +0.095 | **42%** / +0.062 |
| devkb | 4 | 1% / +0.004 | **40%** / +0.004 |
| click | 8 | 6% / +0.016 | 15% / +0.023 |

The saving is in call chains (66–77% on tasks that trace an error or a change to the route handlers that reach it);
on one-hop questions, as in click, plain search is already good. An earlier pre-registered study (30 held-out tasks,
1,020 runs, two model sizes) found packs 41% cheaper and the lean tools 35% ([`study/`](study/); `make verify`
recomputes it). Details and corrections: [`bench/results/2026-11-15-registry`](bench/results/2026-11-15-registry/);
add a repository: [`docs/BENCHMARK.md`](docs/BENCHMARK.md).

## 3. Set up

```bash
uv tool install "devkb[mcp]"      # or: pipx install "devkb[mcp]"
cd your-repo
devkb init --hooks
```

This builds the graph into `.devkb/`, adds a short devkb section to `AGENTS.md` and `CLAUDE.md`, registers the MCP
server in `.mcp.json`, and rebuilds the graph after each commit. Your own content in those files is kept;
`devkb init --remove` undoes it.

Install devkb as a tool, as above, so the `devkb` command is on your PATH: agents start the server from there, and a
devkb installed only inside a virtual environment never starts (`devkb init` warns if that is the case).

Ask it directly:

```bash
devkb pack --project . refactor my_function     # who calls it, which tests
devkb pack --project . error "message text"     # which route handlers reach it
devkb pack --project . file path/to/file.py     # before editing a file
```

### Your agent

**Claude Code**: `devkb init` registered the server in `.mcp.json` and pointed `CLAUDE.md` at the instructions, which
say which tool to use at which step. Start `claude` in the repository, approve the `devkb` server when asked, and check
it with `/mcp`. Agents told to run a pack before editing mostly do not, so add the hook that does it for them: run
`devkb init --claude-hook`, and when the agent is about to Edit or Write a file the graph knows, it receives that file's
pack (the functions other files call, the dependent files, the tests to run) once per session. It never blocks an edit.
Or skip the install and `devkb init` and use the plugin, which brings the server, its instructions, that hook and a hook
that builds the graph in the background (needs [uv](https://docs.astral.sh/uv/)):

```
/plugin install devkb --marketplace namiq-ai/devkb
```

**Cursor**: add `.cursor/mcp.json` to the repository, then enable `devkb` under Settings → MCP:

```json
{"mcpServers": {"devkb": {"command": "devkb", "args": ["mcp", "--project", ".", "--toolset", "lean-pack"]}}}
```

**Codex**: add to `~/.codex/config.toml`:

```toml
[mcp_servers.devkb]
command = "devkb"
args = ["mcp", "--project", ".", "--toolset", "lean-pack"]
```

Codex and Cursor read the instructions in `AGENTS.md`; Claude Code reads them through `CLAUDE.md`.

What agents get by default (`--toolset lean-pack`): a `pack` tool that returns a whole answer in one call, and the
seven single-question tools. The instructions tell them to ask for a pack when a question follows a chain (a file
before editing, a change, an error) and to search as usual for a one-hop lookup, which is where the benchmark found
the saving and where it did not. Measured with agents asking for the pack themselves (lnbits and Dispatch, 400 runs):
53% cheaper than plain search with the highest quality of any arm, against 42% for the seven tools alone
([`bench/results/2026-11-15-lean-pack`](bench/results/2026-11-15-lean-pack/)).

Tried it on your repository? Tell us what happened, good or bad, in
[issue #25](https://github.com/namiq-ai/devkb/issues/25).

## 4. Licence and citation

Code: [Apache-2.0](LICENSE). The study in [`study/`](study/) (paper, figures, pre-registration, data):
[CC BY 4.0](study/LICENSE). Benchmark results quote third-party code under its own licences
([`bench/results/NOTICE`](bench/results/NOTICE)). Releases: [`docs/RELEASING.md`](docs/RELEASING.md).

> Hung T. Le. *Precomputed Context, Not More Tools: A Pre-Registered Study of Process Graphs for Coding Agents.* 2026.
