# Releasing devkb, and the workflows that guard it

Three GitHub Actions workflows, from every change to a public package:

| Workflow | Runs | What it does | Costs |
|---|---|---|---|
| [`ci`](../.github/workflows/ci.yml) | every push and pull request | the test suite | free |
| [`bench`](../.github/workflows/bench.yml) | pull requests touching `devkb/` or the registry; **every night** at 2 AM CST (08:00 UTC); by hand | the free benchmark stage on every registry repository; agent runs only when enabled | free; agent runs about $0.05–0.16 each |
| [`release`](../.github/workflows/release.yml) | a `v*` tag; by hand (no publishing) | dependency audit, tests, build, GitHub release; PyPI only when enabled | free |

## Nightly benchmark

Every night `bench` checks, for each repository in [`bench/repos.yaml`](../bench/repos.yaml), at its pinned commit and
at the current devkb code: the graph builds, the task generators find tasks, every pack scores against the truth from
source, and an independent implementation finds no caller the truth misses (`bench/truth_check.py`). A regression in
extraction shows up the next morning, at no model cost.

**Agent runs at night run on the owner's machine**, not in GitHub Actions: a user systemd timer starts
[`bench/nightly.sh`](../bench/nightly.sh) at 2 AM Central time, which drives the signed-in Claude Code CLI, so no API
key is stored anywhere. Each night it updates its own worktree to `origin/main` (never a working copy someone edits),
runs the free stage on every registry repository, then the agent arms on the chosen repositories, and writes
`~/devkb-nightly/runs/YYYY-MM-DD/` (summary, logs, pack checks, runs, reports; kept 30 days, never committed).

```bash
bench/nightly.sh install    # install and start the timer (once)
bench/nightly.sh dry-run    # one night without agent runs, no model cost
bench/nightly.sh run        # one night now
bench/nightly.sh status     # the timer and the last night's summary
journalctl --user -u devkb-nightly    # its log
```

Settings, in `~/.config/devkb-nightly.env`:

| Setting | Meaning | Default |
|---|---|---|
| `NIGHTLY_IDS` | repositories for the agent arms, comma-separated | `lattice-scan` |
| `NIGHTLY_REPS` | repetitions per task and arm | `1` |
| `NIGHTLY_ARMS` | arms | `plain,core,lean,pack` |
| `NIGHTLY_MAX_RUNS` | per repository, refuse when tasks × arms × reps exceeds it | `60` |
| `NIGHTLY_KEEP_DAYS` | days of results kept | `30` |

The GitHub `bench` workflow still runs the free stage every night at the same hour, in a clean CI environment; its
own agent option (`BENCH_NIGHTLY_AGENTS`, needs an API key secret) is off.

With the defaults, a night is 12 tasks × 4 arms × 1 rep = 48 runs on lattice-scan (about $2.50 at API prices,
counted against the CLI's subscription usage instead). All seven repositories
at 5 repetitions is about $70 a night. A nightly run is a smoke test of the pipeline, not a result to publish: published
results keep the protocol in [`BENCHMARK.md`](BENCHMARK.md) (5 repetitions, every arm of a repository in one session).
A run whose tool arms never reached the graph fails (`pipeline report`), so a broken graph server cannot pass as a
result.

## A release

0. **Before tagging, run the performance check** (free, about 25 minutes on an idle machine): `python bench/perf_release.py PREVIOUS_TAG HEAD click=... prefect=... leveldb=... fmt=... zephyr=... mediatr=... mealie=...`
   on the repositories and pins of `docs/analysis/performance-0.2.14-build.md` (which lists them), and compare with that baseline. Proposed rule (the release owner confirms it): no
   build time, peak memory or query median beyond the noise pass, except where a ticket says why; a change beyond it gets its own ticket before the tag (#370). Record the run
   as a section of that note.
1. Set `version` in `pyproject.toml`, merge to `main`.
2. `git tag v0.2.0 && git push origin v0.2.0`.
3. `release` then runs, in order, each step needing the one before:
   - **audit**: every dependency with all extras, pinned with hashes, checked by pip-audit 2.7.3 on Python 3.10 and 3.12
     against the PyPI and OSV advisory databases; any known vulnerability stops the release. pip-audit checks
     dependencies, not devkb's own code.
   - **test**: the test suite.
   - **graph**: devkb's own graph at the tag, built by the code being released, with the GitHub layer
     (`python -m devkb.cli build --project . --github`, the workflow's read-only token). A build that fails, or whose
     `.devkb/manifest.json` does not name the tag's commit in `git_head`, fails the release (#315).
   - **build**: the tag must equal the version; wheel and sdist; `twine check --strict`.
   - **release**: a GitHub release with the wheel, the sdist, `devkb-graph-<tag>.tar.gz` (the `.devkb/` store, manifest
     included: anyone can start from the release's exact graph) and both audit reports.
   - **pypi**: only when enabled (below).

4. After tagging, rebuild your own checkout's graph with the checkout's own devkb and the GitHub layer, as the hooks of #158
   do on every merge: `git switch main && git pull && .venv/bin/devkb build --project . --github`. A graph that sits at an
   older commit gives wrong hook answers (#273).

Run `release` by hand from the Actions tab to rehearse: it audits, tests, builds the graph and the package, and publishes nothing.
Its `graph` job shows the manifest's `git_head` equal to the run's commit when it passes.

## DOI (Zenodo)

Every published GitHub release is archived by Zenodo, which mints a DOI for that version and a concept DOI for all
versions. The record's title, authors, licence and keywords come from [`.zenodo.json`](../.zenodo.json); GitHub's
"Cite this repository" button reads [`CITATION.cff`](../CITATION.cff). Keep both, and `version` in `CITATION.cff`,
in step with `pyproject.toml` at each release. One-time setup: sign in to zenodo.org with GitHub, Settings → GitHub,
switch on `namiq-ai/devkb`.

## Publishing to PyPI

Publishing is public and permanent: PyPI never accepts the same version twice, and a package once downloaded cannot
be recalled. The `pypi` job runs only when the repository variable `PYPI_PUBLISH` is `true`, and it stops unless all of these hold.

**Before the first upload**

1. Licence: decided 2026-11-15, Apache-2.0 for the code, CC BY 4.0 for the study (`LICENSE`, `study/LICENSE`, `NOTICE`).
   The owner decided devkb is published as a paper, not patented; it is outside the subjects the disclosure freeze
   holds.
2. No local paths, email addresses or credentials in the package: `scripts/check_dist.py dist/*` scans the built wheel
   and sdist against [`.release-denylist`](../.release-denylist), and the `pypi` job runs it first. Project names in
   comments are no longer blocked: the repository is public (decided 2026-11-15).
3. Done: `license = "Apache-2.0"` and the licence files in `pyproject.toml`; URLs, classifiers and keywords.

**Configured (2026-11-15)**

- Package metadata: URLs, keywords, classifiers (`pyproject.toml`); `twine check --strict` passes.
- GitHub environment `pypi`, deployable only from tags `v*`.
- Repository variable `PYPI_PUBLISH` = `true` (checked 2026-11-20): the switch is **on**. The `pypi` environment has a tag policy (`v*`) and
  **no required reviewer**, so a tag publishes to PyPI as soon as audit, test, build and the scan pass, without a person's approval.
  (Step 2 under "Still to do" below, required reviewers, is not done.)
- PyPI's latest version was 0.2.12 on 2026-11-20: **v0.2.13's upload was refused by the scan below** (a private-key marker in a test
  fixture; #364), so v0.2.13 exists as a GitHub release only. `tests/test_sdist_denylist_364.py` now runs the scan on the files the
  sdist is made of, so the next such fixture fails in CI and not at the tag.
- The `pypi` job: trusted publishing, the internal-name scan before upload.

**Still to do, when going public**

1. On PyPI, add a *pending trusted publisher* (Account → Publishing): owner `namiq-ai`, repository `devkb`, workflow
   `release.yml`, environment `pypi`. This needs the owner's PyPI account. No token is created or stored; PyPI trusts
   this workflow's OIDC identity for that one project. The name `devkb` was free on PyPI and TestPyPI on 2026-11-15; it
   is reserved only by the first upload (or by the pending publisher).
2. Add required reviewers to the `pypi` environment (Settings → Environments → pypi), so every upload waits for a
   person's approval. GitHub offers them on private repositories only on paid plans; on a public repository they are
   free.
3. Set `PYPI_PUBLISH` to `true`.

After that, a tag publishes to PyPI once a reviewer approves the `pypi` job. `pip install devkb[mcp]` then replaces
the `git+https` install in the README.
