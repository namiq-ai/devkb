#!/usr/bin/env bash
# devkb plugin, session start: make sure a graph of this repository exists and is current, without blocking the
# session. The build runs in the background; the MCP server answers "ask again in a minute" until it is done.
d="${CLAUDE_PROJECT_DIR:-$PWD}"
git -C "$d" rev-parse --git-dir >/dev/null 2>&1 || exit 0          # not a git repository: nothing to do
# Keep .devkb/ out of `git status` without touching any tracked file: git's local exclude list.
ex="$(git -C "$d" rev-parse --git-path info/exclude)"; case "$ex" in /*) ;; *) ex="$d/$ex" ;; esac
mkdir -p "$(dirname "$ex")" && { grep -qx '.devkb/' "$ex" 2>/dev/null || echo '.devkb/' >> "$ex"; }
head="$(git -C "$d" rev-parse HEAD 2>/dev/null)"
built="$(sed -n 's/.*"git_head": *"\([0-9a-f]*\)".*/\1/p' "$d/.devkb/manifest.json" 2>/dev/null)"
if [ ! -f "$d/.devkb/nodes.jsonl" ] || [ -n "$head" -a "$head" != "$built" ]; then
  mkdir -p "$d/.devkb"
  lock="$d/.devkb/.building"
  if [ ! -e "$lock" ] || [ -n "$(find "$lock" -mmin +30 2>/dev/null)" ]; then
    touch "$lock"
    (nohup sh -c "uvx --from 'devkb[mcp]>=0.2.1' devkb build --project '$d' >'$d/.devkb/build.log' 2>&1; rm -f '$lock'" >/dev/null 2>&1 &)
  fi
fi
exit 0
