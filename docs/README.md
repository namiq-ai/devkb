# devkb documentation

| Folder | What is in it |
|---|---|
| [`adr/`](adr/) | Architecture decision records, one per decision (`ADR-DEVKB-NNN`). |
| [`specs/`](specs/) | Specifications: what a capability must do and how it is accepted (`SPEC-DKB-NNN`, `SPEC-DEVKB-CSHARP*`), with the packs used while building the C# work. |
| [`stories/`](stories/) | The work items each spec produced: `language-profiles/`, `read-tools/`, and `spikes/` for questions to answer before building. |
| [`analysis/`](analysis/) | Measurements behind a decision, and `graph-baseline.md`, the reference graph size and build time of twelve repositories to compare a release against; also: `read-tools-analysis.md` (what agents grep for, range accuracy, name matching), `read-tools-benchmark.md` (the benchmarks and the cost breakdown) and `performance-v0.2.6-to-main.md` (build and query cost, and the tool-search fix). |
| [`evaluations/`](evaluations/) | End-to-end evaluations of a language or feature: C/C++ support, language profiles, and the C/C++ final report. |
| [`BENCHMARK.md`](BENCHMARK.md) | The benchmark protocol and results behind the README numbers. |
| [`RELEASING.md`](RELEASING.md) | How a release is cut and checked. |
| [`TRIAGE.md`](TRIAGE.md) | The daemons that triage and handle outside issues and pull requests every 4 hours. |
| `img/` | Images used by the README. |

Tooling that produced the numbers lives in `bench/` (`bench/readtools/`, `bench/exercises/cpp/`).
