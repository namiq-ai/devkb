# Releasing devkb, and the workflows that guard it

Three GitHub Actions workflows, from every change to a public package:

| Workflow | Runs | What it does | Costs |
|---|---|---|---|
| [`ci`](../.github/workflows/ci.yml) | every push and pull request | the test suite | free |
| [`bench`](../.github/workflows/bench.yml) | pull requests touching `devkb/` or the registry; **every night** at 07:17 UTC; by hand | the free benchmark stage on every registry repository; agent runs only when enabled | free; agent runs about $0.05–0.16 each |
| [`release`](../.github/workflows/release.yml) | a `v*` tag; by hand (no publishing) | dependency audit, tests, build, GitHub release; PyPI only when enabled | free |

## Nightly benchmark

Every night `bench` checks, for each repository in [`bench/repos.yaml`](../bench/repos.yaml), at its pinned commit and
at the current devkb code: the graph builds, the task generators find tasks, every pack scores against the truth from
source, and an independent implementation finds no caller the truth misses (`bench/truth_check.py`). A regression in
extraction shows up the next morning, at no model cost.

Agent runs at night are off. To turn them on, set repository variables (Settings → Secrets and variables → Actions →
Variables) and the `ANTHROPIC_API_KEY` secret:

| Variable | Meaning | Default |
|---|---|---|
| `BENCH_NIGHTLY_AGENTS` | `true` runs the agent arms at night | off |
| `BENCH_NIGHTLY_IDS` | repositories, comma-separated | `lattice-scan` |
| `BENCH_NIGHTLY_REPS` | repetitions per task and arm | `1` |
| `BENCH_NIGHTLY_MAX_RUNS` | per repository, refuse when tasks × arms × reps exceeds it | `60` |

With the defaults, a night is 12 tasks × 4 arms × 1 rep = 48 runs on lattice-scan, about $2.50. All seven repositories
at 5 repetitions is about $70 a night. A nightly run is a smoke test of the pipeline, not a result to publish: published
results keep the protocol in [`BENCHMARK.md`](BENCHMARK.md) (5 repetitions, every arm of a repository in one session).
A run whose tool arms never reached the graph fails (`pipeline report`), so a broken graph server cannot pass as a
result.

## A release

1. Set `version` in `pyproject.toml`, merge to `main`.
2. `git tag v0.2.0 && git push origin v0.2.0`.
3. `release` then runs, in order, each step needing the one before:
   - **audit**: every dependency with all extras, pinned with hashes, checked by pip-audit 2.7.3 on Python 3.10 and 3.12
     against the PyPI and OSV advisory databases; any known vulnerability stops the release. pip-audit checks
     dependencies, not devkb's own code.
   - **test**: the test suite.
   - **build**: the tag must equal the version; wheel and sdist; `twine check --strict`.
   - **release**: a GitHub release with the wheel, the sdist and both audit reports.
   - **pypi**: only when enabled (below).

Run `release` by hand from the Actions tab to rehearse: it audits, tests and builds, and publishes nothing.

## Publishing to PyPI

Publishing is public and permanent: PyPI never accepts the same version twice, and a package once downloaded cannot
be recalled. The `pypi` job is therefore off, and when on, it stops unless all of these hold.

**Before the first upload**

1. The decisions only the owner can make: a licence (the package metadata has none yet), and the timing check with
   patent counsel that the disclosure freeze asks for before devkb is made public.
2. No internal names or local paths in the package. `scripts/check_dist.py dist/*` scans the built wheel and sdist
   against [`.release-denylist`](../.release-denylist) and the `pypi` job runs it first. At the time of writing it finds
   1,307 matches in 113 files, mostly internal project names and ticket ids in comments; clean them and the check passes.
3. Package metadata for a public page: `license`, `project.urls` (repository, issues), `classifiers`, `keywords` in
   `pyproject.toml`.

**One-time setup**

1. On PyPI, add a *pending trusted publisher* (Account → Publishing): owner `namiq-ai`, repository `devkb`, workflow
   `release.yml`, environment `pypi`. No token is created or stored; PyPI trusts this workflow's OIDC identity for
   that one project. The name `devkb` was free on PyPI and TestPyPI on 2026-11-15; it is reserved only by the first
   upload.
2. In the GitHub repository, create the environment `pypi` (Settings → Environments) with required reviewers, so every
   upload waits for a person's approval, and restrict it to tags `v*`.
3. Set the repository variable `PYPI_PUBLISH` to `true`.

After that, a tag publishes to PyPI once a reviewer approves the `pypi` job. `pip install devkb[mcp]` then replaces
the `git+https` install in the README.
