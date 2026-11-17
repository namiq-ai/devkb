#!/usr/bin/env bash
# Usage: validate.sh [bug-id ...]   (run from anywhere; restores the clean tree after each bug)
H="$(cd "$(dirname "$0")" && pwd)"; cd "$H/src" || exit 1
PY="$H/.venv/bin/python"
ids=("$@"); [ ${#ids[@]} -eq 0 ] && ids=($(ls "$H/bugs"))
for id in "${ids[@]}"; do
  d="$H/bugs/$id"; mapfile -t acc < "$d/acceptance.txt"
  git checkout -q . ; git diff --quiet || { echo "tree not clean"; exit 1; }
  echo "=== $id"
  echo "--- clean: snippet"; "$PY" "$d/snippet.py" 2>&1 | cut -c1-300
  t0=$(date +%s.%N); out=$("$PY" -m pytest -q -p no:cacheprovider "${acc[@]}" 2>&1 | tail -1); t1=$(date +%s.%N)
  echo "--- clean: acceptance: $out  [wall $(printf '%.1f' "$(echo "$t1-$t0"|bc)")s]"
  git apply "$d/mutation.patch" || { echo "PATCH FAILED"; exit 1; }
  echo "--- patched: snippet"; "$PY" "$d/snippet.py" 2>&1 | cut -c1-300
  t0=$(date +%s.%N); out=$("$PY" -m pytest -q -p no:cacheprovider "${acc[@]}" 2>&1 | grep -E "^FAILED|passed|failed" | sed 's/ - .*//'); t1=$(date +%s.%N)
  echo "--- patched: acceptance:"; echo "$out"; echo "[wall $(printf '%.1f' "$(echo "$t1-$t0"|bc)")s]"
  git checkout -q .
done
