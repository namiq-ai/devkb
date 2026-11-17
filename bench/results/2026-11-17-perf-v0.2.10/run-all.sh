#!/bin/bash
# The run behind docs/analysis/performance-v0.2.6-to-v0.2.10.md: v0.2.10 (picks targets) -> v0.2.6 -> v0.2.8 -> v0.2.10
# again (noise), one at a time. Needs code-<version>/ (`git archive v<version> | tar -x -C code-<version>`) and
# repos/<name> clones beside this script, and PERF_PYTHON: an interpreter with devkb's dependencies.
set -u
P=$(cd "$(dirname "$0")" && pwd); cd "$P"
PERF="$(git rev-parse --show-toplevel)/bench/perf.py"
R=""; for r in click mealie prefect leveldb fmt zephyr; do R="$R $r=$P/repos/$r"; done
run() { echo "=== $2 $(date +%T) load $(cut -d' ' -f1-3 /proc/loadavg)"; python3 "$PERF" "$P/code-$1" "$2" "$2.json" $R --targets targets.json $3; }
run 0.2.10 v0.2.10-a --pick
run 0.2.6 v0.2.6 ""
run 0.2.8 v0.2.8 ""
run 0.2.10 v0.2.10-b ""
echo "=== done $(date +%T) load $(cut -d' ' -f1-3 /proc/loadavg)"
