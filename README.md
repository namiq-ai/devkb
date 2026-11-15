# devkb: a software-process knowledge graph for coding agents

Coding agents pay to rediscover what a repository already records: who calls a function, which tests exercise it,
which ticket and specification a change belongs to. devkb extracts that into a graph and hands it to an agent in as
few turns as possible.

In a pre-registered study on 30 held-out tasks in four repositories (1,020 runs, same model in every arm),
devkb's pre-computed **packs cost 41% less** than plain search (95% CI 34–48%) and its **lean tool set 35% less**, at
equal or better quality, for two model sizes. Task-shaped tools saved nothing. See [`study/`](study/) and
[`SCOPE.md`](SCOPE.md).

## Use it on your repository

```bash
pip install "devkb[mcp] @ git+https://github.com/namiq-ai/devkb"
cd your-repo
devkb init --hooks      # AGENTS.md + CLAUDE.md instructions, .mcp.json server, .gitignore, rebuild hooks; builds the graph
devkb init --remove     # takes all of it out again, leaving your files as they were
```

`devkb init` writes marked blocks, never whole files, so your own `AGENTS.md`, `CLAUDE.md`, `.mcp.json` and
`.gitignore` keep their content and a re-run only refreshes the block. The instructions matter: in the study, agents
left to choose used the graph for call chains but not for other work, and the savings were measured with these
instructions in place. Codex and most agents read `AGENTS.md`; Claude Code reads it through `CLAUDE.md`'s
`@AGENTS.md`. For Codex, add the server to `~/.codex/config.toml`: `[mcp_servers.devkb]`, `command = "devkb"`,
`args = ["mcp", "--project", ".", "--toolset", "dev"]`.

Or by hand:

```bash
devkb build --project .                       # writes .devkb/ (add it to .gitignore)
devkb pack  --project . file path/to/file.py  # before editing: what depends on it, tests that reach it
devkb pack  --project . refactor my_function  # who calls it, which tests, with evidence lines and coverage
devkb pack  --project . error "message text"  # which route handlers reach the code that raises it
devkb pack  --project . change path/to/file.py
devkb pack  --project . pr 123                 # a pull request: commits, changed functions, tests to run, issues it closes
devkb pack  --project . ticket GH-45           # a hosted issue: its pull requests, commits, functions, tests
devkb build --project . --github               # opt in to GitHub pull requests and issues (ADR-DEVKB-007); cached in .devkb/github/
```

Serve the graph to an agent over MCP (stdio), for example in Claude Code's `.mcp.json`:

```json
{"mcpServers": {"devkb": {"command": "devkb", "args": ["mcp", "--project", ".", "--toolset", "dev"]}}}
```

`devkb init` configures `--toolset dev` (10 tools: lean plus `explain_area`, `feature_brief`, `find_code` for orienting before new
code); `--toolset lean` exposes the 7 the benchmark measured; the server default exposes 24 (callers, tests_for, tests_to_run, impact, rca_trace,
refactor_scope, review_pack, lineage, trace, config, ...). Every list answer carries a **coverage** statement: the
call sites the resolver could not attribute, so an agent searches only where the graph is blind. The `skills/`
folder maps developer tasks to tools for agents that load skills.

Nothing to configure for a plain repository. An optional `devkb.json` at the repository root declares what devkb
cannot guess:

```json
{"code": "APP", "ticket_prefix": "APP",
 "paths": {"issues_dir": "issues", "spec_dirs": ["docs", "docs/adr"], "frontend_src": "web/src"}}
```

devkb reads the repository and runs `git`; it never executes the repository's own code unless `devkb.json` sets
`"run_repo_scripts": true`.

## What is in the graph

20 node types (Ticket, Commit, File, Symbol, TestCase, Endpoint, Flow, ErrorSignature, Spec, Requirement, ConfigKey,
...) and 30 relations (CALLS, TESTED_BY, RAISES, STEP, TOUCHES, REFERENCES, IMPLEMENTS, READS, DECLARES, ...); see
[`devkb/ontology.md`](devkb/ontology.md). Calls are resolved through imports, aliases, package re-exports, dotted
module paths, typed receivers and base classes; nothing is attributed by a bare name. Calls made at import time are
kept on the function they call, so a refactor pack lists those files too. `devkb audit --project .` reports each
relation's size, fan-out and cost, so you can check what your graph actually contains.

Languages: **Python** in full (functions, classes, methods, calls, imports, routes, raised and logged errors,
environment reads); **TypeScript and JavaScript** (`.ts`, `.tsx`, `.js`, `.mjs`) for functions, components, classes and
the HTTP calls a frontend makes to backend routes, by pattern matching rather than a parser; **Odoo XML** templates
and menus. The git layer (commits, files, pull requests, tickets) works for any language; call chains, error traces
and packs need Python.

## Benchmark it on more repositories

The benchmark runs on every repository in [`bench/repos.yaml`](bench/repos.yaml); adding one is a pull request.
See [`docs/BENCHMARK.md`](docs/BENCHMARK.md).

On all seven registry repositories (55 tasks, 1,100 runs, Sonnet; exploratory, not pre-registered), packs cost 56%
less than plain search [51, 60] with quality up 0.051, the lean tools 28% less, the full tool set 9% less; the saving
is on call chains (68–78% on route-handler tasks), not on one-hop refactors, where the full tool set costs 17% more
([`bench/results/2026-11-15-registry/`](bench/results/2026-11-15-registry/)). Four of those 55 tasks had a truth that
missed callers the graph also missed; `prepare` now checks every truth against an independent implementation before
any run is paid for, and the addendum there reruns those four.

## Reproduce the paper

```bash
make dev        # a virtual environment with the test and analysis dependencies
make test       # the component's test suite
make verify     # recompute every result in study/results from the raw runs and compare byte for byte
make paper      # build study/paper/paper.pdf (needs a TeX installation)
```

## Releases

Pushing a version tag (`v0.2.0`, matching `pyproject.toml`) runs [`release.yml`](.github/workflows/release.yml): it
audits every dependency with all extras, pinned with hashes, using pip-audit on Python 3.10 and 3.12, and stops on any
known vulnerability. It then runs the tests, builds the wheel and sdist, and publishes a GitHub release with them and
the audit reports. Running it by hand from the Actions tab does everything except publish. PyPI publishing and the
nightly benchmark are described in [`docs/RELEASING.md`](docs/RELEASING.md); both stay off until enabled.

## Status

Private pre-release. Licence to be chosen before the repository is made public; until then, all rights reserved.

## Cite

Hung T. Le. *Fewer Turns, Not a Better Graph: A Pre-Registered Study of Process Graphs for Coding Agents.* 2026.
