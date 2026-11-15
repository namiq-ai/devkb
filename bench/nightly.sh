#!/usr/bin/env bash
# Nightly benchmark on this machine, with the signed-in Claude Code CLI (no API key).
#
#   bench/nightly.sh install     install and start the user systemd timer (02:00 local time)
#   bench/nightly.sh run         one night: update, free stage on every repository, agent runs, report
#   bench/nightly.sh dry-run     the same without agent runs (no model cost)
#   bench/nightly.sh status      the timer and the last night's summary
#
# It runs from its own worktree, detached at origin/main and updated each night, never from a working copy someone
# edits: switching a branch under a running benchmark changes the code its graph servers load.
#
# Settings, in ~/.config/devkb-nightly.env (all optional):
#   NIGHTLY_IDS=lattice-scan      repositories for the agent arms, comma-separated (the free stage covers all)
#   NIGHTLY_REPS=1                repetitions per task and arm
#   NIGHTLY_ARMS=plain,core,lean,pack
#   NIGHTLY_MODEL=sonnet
#   NIGHTLY_MAX_RUNS=60           per repository: refuse when tasks x arms x reps exceeds it
#   NIGHTLY_HOME=~/devkb-nightly  worktree, clones, results, logs
#   NIGHTLY_KEEP_DAYS=30          results older than this are deleted
#
# Results stay on this machine (NIGHTLY_HOME/runs/YYYY-MM-DD/); nothing is committed or pushed. A night is a smoke test
# of the pipeline at the current code, not a result to publish (docs/BENCHMARK.md).
set -euo pipefail

CONF="${XDG_CONFIG_HOME:-$HOME/.config}/devkb-nightly.env"
[ -f "$CONF" ] && . "$CONF"
IDS="${NIGHTLY_IDS:-lattice-scan}"
REPS="${NIGHTLY_REPS:-1}"
ARMS="${NIGHTLY_ARMS:-plain,core,lean,pack}"
MODEL="${NIGHTLY_MODEL:-sonnet}"
MAX_RUNS="${NIGHTLY_MAX_RUNS:-60}"
HOME_DIR="${NIGHTLY_HOME:-$HOME/devkb-nightly}"
KEEP_DAYS="${NIGHTLY_KEEP_DAYS:-30}"
SRC="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"   # the repository this script came from
TREE="$HOME_DIR/devkb"                                    # the nightly's own worktree
WORK="$HOME_DIR/work"                                     # pinned clones and graphs, kept between nights
export PATH="$HOME/.local/bin:$PATH"                      # claude and uv, also under systemd

install() {
  local units="${XDG_CONFIG_HOME:-$HOME/.config}/systemd/user"
  mkdir -p "$units"
  update_tree   # the timer runs the nightly worktree's own copy, never a working copy someone switches branches in
  sed "s|@SCRIPT@|$TREE/bench/nightly.sh|" "$SRC/bench/systemd/devkb-nightly.service" > "$units/devkb-nightly.service"
  cp "$SRC/bench/systemd/devkb-nightly.timer" "$units/devkb-nightly.timer"
  systemctl --user daemon-reload
  systemctl --user enable --now devkb-nightly.timer
  systemctl --user list-timers devkb-nightly.timer --no-pager
}

update_tree() {
  git -C "$SRC" fetch -q origin
  if [ ! -e "$TREE/.git" ]; then
    mkdir -p "$HOME_DIR"
    git -C "$SRC" worktree add -q --detach "$TREE" origin/main
  fi
  git -C "$TREE" checkout -q --detach origin/main
  git -C "$TREE" clean -qfdx -e .venv
  [ -x "$TREE/.venv/bin/python" ] || uv venv -q --python 3.12 "$TREE/.venv"
  uv pip install -q --python "$TREE/.venv/bin/python" -e "$TREE[dev]"
}

night() {
  local agents="$1" day out py status=0
  day="$(date +%F)"
  out="$HOME_DIR/runs/$day"
  mkdir -p "$out" "$WORK"
  exec > >(tee -a "$out/nightly.log") 2>&1
  echo "== devkb nightly $day $(date +%T), agents=$agents ids=$IDS reps=$REPS arms=$ARMS model=$MODEL"
  update_tree
  py="$TREE/.venv/bin/python"
  cd "$TREE"
  echo "devkb $(git rev-parse --short HEAD) ($(git log -1 --format=%s | cut -c1-80))" | tee "$out/summary.md"
  local all
  all="$("$py" -m devkb.bench.pipeline list | awk '{print $1}')"
  echo -e "\n## Free stage (every repository)\n" >> "$out/summary.md"
  for id in $all; do
    if "$py" -m devkb.bench.pipeline prepare "$id" --work "$WORK" > "$out/prepare-$id.log" 2>&1; then r=pass; else r=FAIL; status=1; fi
    cp -f "$WORK/$id/pack-check.json" "$out/pack-check-$id.json" 2>/dev/null || true
    echo "- $id: $r $(python3 -c "import json,sys; c=json.load(open(sys.argv[1]))['summary']; print(c['tasks'], 'tasks, pack score', c['mean_score'], 'complete-but-wrong', c['complete_but_wrong'] or 'none', 'truth missing', list(c.get('truth_missing_callers') or {}) or 'none')" "$WORK/$id/pack-check.json" 2>/dev/null)" | tee -a "$out/summary.md"
  done
  if [ "$agents" = yes ]; then
    echo -e "\n## Agent runs ($ARMS, $REPS rep, $MODEL)\n" >> "$out/summary.md"
    for id in ${IDS//,/ }; do
      [ -f "$WORK/$id/tasks.packs.json" ] || { echo "- $id: not prepared" | tee -a "$out/summary.md"; status=1; continue; }
      n=$(python3 -c "import json,sys; print(len(json.load(open(sys.argv[1]))))" "$WORK/$id/tasks.packs.json")
      total=$(( n * $(echo "$ARMS" | tr ',' '\n' | wc -l) * REPS ))
      if [ "$total" -gt "$MAX_RUNS" ]; then echo "- $id: $total runs exceeds NIGHTLY_MAX_RUNS=$MAX_RUNS, skipped" | tee -a "$out/summary.md"; status=1; continue; fi
      rm -f "$WORK/$id/$id.jsonl"   # one night's runs, never appended to an earlier night's
      if "$py" -m devkb.bench.pipeline run "$id" --work "$WORK" --arms "$ARMS" --reps "$REPS" --model "$MODEL" > "$out/run-$id.log" 2>&1 \
         && "$py" -m devkb.bench.pipeline report "$id" --work "$WORK" --model "$MODEL" > "$out/report-$id.md" 2>&1; then r=pass; else r=FAIL; status=1; fi
      cp -f "$WORK/$id/$id.jsonl" "$out/runs-$id.jsonl" 2>/dev/null || true
      cp -f "$WORK/$id/report.json" "$out/report-$id.json" 2>/dev/null || true
      echo "- $id: $r, $total runs $(python3 -c "
import json,sys
rs=[json.loads(l) for l in open(sys.argv[1])]
print('cost \$%.2f, invalid %d' % (sum(r.get('cost') or 0 for r in rs), sum(1 for r in rs if not r['valid'])))" "$out/runs-$id.jsonl" 2>/dev/null)" | tee -a "$out/summary.md"
      sed -n '/saved/p' "$out/report-$id.md" >> "$out/summary.md" || true
    done
  fi
  find "$HOME_DIR/runs" -mindepth 1 -maxdepth 1 -type d -mtime +"$KEEP_DAYS" -exec rm -rf {} + 2>/dev/null || true
  echo -e "\nfinished $(date +%T), status $status" | tee -a "$out/summary.md"
  return $status
}

main() {
  case "${1:-}" in
    install) install ;;
    run|dry-run)
      exec 9>"${XDG_RUNTIME_DIR:-/tmp}/devkb-nightly.lock"
      flock -n 9 || { echo "a night is already running"; return 0; }
      if [ "$1" = run ]; then night yes; else night no; fi ;;
    status) systemctl --user list-timers devkb-nightly.timer --no-pager
            last=$(ls -1d "$HOME_DIR"/runs/*/ 2>/dev/null | tail -1); [ -z "$last" ] || cat "$last/summary.md" ;;
    *) sed -n '2,8p' "$0"; return 2 ;;
  esac
}

# One line, so bash has read all of it before a night updates this file in the worktree it runs from.
main "$@"; exit $?
