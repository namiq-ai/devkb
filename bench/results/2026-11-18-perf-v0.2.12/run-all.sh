#!/bin/bash
# Release check of v0.2.12 against v0.2.11 (same clones, same targets as the 2026-11-18 check). One build at a time.
set -u
W=$(cd "$(dirname "$0")" && pwd); cd "$W"; R=$W/repos
export PERF_PYTHON=/home/namiq/orchestra/ip/devkb-cs4/.venv/bin/python
P="click=$R/click mealie=$R/mealie prefect=$R/prefect leveldb=$R/leveldb fmt=$R/fmt zephyr=$R/zephyr"
run() { echo "=== perf $2 $(date +%T) load $(cut -d' ' -f1-3 /proc/loadavg)"; /home/namiq/orchestra/ip/devkb-cs4/.venv/bin/python $W/code-v0.2.12/bench/perf.py $W/code-$1 $2 $2.json $P --targets targets.json; }
run v0.2.12 v0.2.12-a
run v0.2.11 v0.2.11
run v0.2.12 v0.2.12-b
echo "=== graph_info $(date +%T)"
/home/namiq/orchestra/ip/devkb-cs4/.venv/bin/python $W/code-v0.2.12/bench/graph_info.py $W/code-v0.2.12 v0.2.12 graphs-0.2.12.json click=$R/click mealie=$R/mealie prefect=$R/prefect leveldb=$R/leveldb fmt=$R/fmt zephyr=$R/zephyr
echo "=== done $(date +%T)"
