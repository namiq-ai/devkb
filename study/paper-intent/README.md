# Beyond Grep: intent-aware interception and at-the-moment teaching for coding agents

An **exploratory** study (not pre-registered) of devkb's search hook as of release 0.2.13:
- intent-preserving interception of the agent's own searches;
- the teach line (D1);
- a cost model for agent exploration (turns and the fixed load).

It follows the pre-registered study in `../paper/` (doi:10.5281/zenodo.24267143) and pre-specifies the confirmatory
study it calls for (its Section VIII).

**Build:** `pdflatex paper && bibtex paper && pdflatex paper && pdflatex paper`.

**Data:**
- every number in the paper is in `bench/results/2026-11-19-release-0.2.13/` and `docs/analysis/release-0.2.13.md`;
- the per-run results are the recounted ones (#258, #263);
- the analysis script is `stories.py` there.
