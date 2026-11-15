#!/bin/bash
# run_arm.sh ARM   (plain | devkb): one headless Claude Code agent implementing ADR-DEVKB-007 in its worktree.
X=<exercise>
ARM=$1; W=$X/$ARM; OUT=$X/eval/run-$ARM
mkdir -p $OUT
if [ "$ARM" = devkb ]; then MCP=$W/.mcp.json; EXTRA="mcp__devkb"; else MCP=$X/eval/no-mcp.json; EXTRA=""; fi
cd $W
date -u +%FT%TZ > $OUT/start
PATH=$W/.venv/bin:$PATH timeout 14400 claude -p "$(cat $X/eval/prompt.md)" --model sonnet \
  --output-format stream-json --verbose --max-turns 400 --permission-mode acceptEdits \
  --strict-mcp-config --mcp-config $MCP \
  --allowedTools Read Edit Write Glob Grep TodoWrite $EXTRA \
    "Bash(git:*)" "Bash(.venv/bin/python:*)" "Bash(.venv/bin/devkb:*)" "Bash(devkb:*)" "Bash(python3:*)" "Bash(gh api:*)" \
    "Bash(ls:*)" "Bash(cat:*)" "Bash(head:*)" "Bash(tail:*)" "Bash(wc:*)" "Bash(find:*)" "Bash(grep:*)" "Bash(diff:*)" "Bash(mkdir:*)" "Bash(rm -rf /tmp/*)" \
  --disallowedTools "Bash(git push:*)" Task \
  > $OUT/stream.jsonl 2> $OUT/stderr.log
echo "exit=$?" > $OUT/end; date -u +%FT%TZ >> $OUT/end
