# devkb

**A knowledge graph of your repository for software development agents.** Agents answer "what calls this, what breaks, which tests"
in one step instead of searching file by file: 56% cheaper, with better answers, in our benchmark.

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="docs/img/benchmark-dark.svg">
  <img alt="Median cost per task: plain search $0.075 (quality 0.928); devkb 12 tools $0.060, 19% cheaper (0.951); devkb 7 tools $0.042, 39% cheaper (0.961); devkb pack $0.026, 56% cheaper (0.979)" src="docs/img/benchmark-light.svg">
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
| Odoo XML | 🟡 Partial | templates and menus |
| Bash / shell | ⬜ Not yet | files and history only |
| C, C++, Java, Rust, Go, C#, others | ⬜ Not yet | files and history only |

"Files and history" is the language-independent layer every repository gets: files, commits, pull requests and
tickets.

## 2. How much it saves

Latest benchmark: the 7 open-source repositories in [`bench/repos.yaml`](bench/repos.yaml), 52 tasks, 1,038 agent
runs, the same model (Sonnet) in every arm, answers scored against truth computed from the source. Cost, turns and
tokens are the median run; saving is per task against plain search, averaged over tasks; quality is the mean score:

| | Plain search | devkb, 12 tools | devkb, 7 tools | devkb pack |
|---|---|---|---|---|
| **Cost per task** | $0.075 | $0.060 | $0.042 | **$0.026** |
| **Saving** | — | 19% | 39% | **56%** |
| **Quality** (0–1) | 0.928 | 0.951 (+0.023) | 0.961 (+0.033) | **0.979 (+0.051)** |
| Turns | 5.5 | 7 | 6 | **3** |
| Context processed (tokens) | 164k | 187k | 156k | **77k** |
| of which cache reads | 155k | 173k | 146k | 76k |
| of which new input and cache writes | 9.2k | 4.7k | 2.2k | 1.4k |
| Output tokens | 1.6k | 1.8k | 1.3k | 0.9k |

Saving and quality gain by repository (95% intervals in the results):

| Repository | Tasks | 7 tools: saving / quality | pack: saving / quality |
|---|---|---|---|
| lnbits | 10 | 53% / +0.032 | **66%** / +0.049 |
| Netflix Dispatch | 8 | 45% / +0.040 | **61%** / +0.081 |
| Prefect | 9 | 41% / −0.017 | **59%** / +0.047 |
| lattice-scan | 12 | 36% / +0.052 | **51%** / +0.058 |
| Mealie | 6 | 18% / +0.095 | **42%** / +0.062 |
| devkb | 4 | 1% / +0.004 | **40%** / +0.004 |
| click | 3 | −3% / 0 | −19% / 0 |

The saving is in call chains (66–77% on tasks that trace an error or a change to the route handlers that reach it);
on one-hop questions, as in click, plain search is already good. An earlier pre-registered study (30 held-out tasks,
1,020 runs, two model sizes) found packs 41% cheaper and the lean tools 35% ([`study/`](study/); `make verify`
recomputes it). Details and corrections: [`bench/results/2026-11-15-registry`](bench/results/2026-11-15-registry/);
add a repository: [`docs/BENCHMARK.md`](docs/BENCHMARK.md).

## 3. Set up

```bash
pip install "devkb[mcp] @ git+https://github.com/namiq-ai/devkb"
cd your-repo
devkb init --hooks
```

This builds the graph into `.devkb/`, adds a short devkb section to `AGENTS.md` and `CLAUDE.md`, registers the MCP
server in `.mcp.json`, and rebuilds the graph after each commit. Your own content in those files is kept;
`devkb init --remove` undoes it.

Ask it directly:

```bash
devkb pack --project . refactor my_function     # who calls it, which tests
devkb pack --project . error "message text"     # which route handlers reach it
devkb pack --project . file path/to/file.py     # before editing a file
```

For Codex, add to `~/.codex/config.toml`:

```toml
[mcp_servers.devkb]
command = "devkb"
args = ["mcp", "--project", ".", "--toolset", "dev"]
```

## 4. Licence and citation

Code: [Apache-2.0](LICENSE). The study in [`study/`](study/) (paper, figures, pre-registration, data):
[CC BY 4.0](study/LICENSE). Benchmark results quote third-party code under its own licences
([`bench/results/NOTICE`](bench/results/NOTICE)). Releases: [`docs/RELEASING.md`](docs/RELEASING.md).

> Hung T. Le. *Precomputed Context, Not More Tools: A Pre-Registered Study of Process Graphs for Coding Agents.* 2026.
