#!/usr/bin/env bash
# devkb plugin, UserPromptSubmit: record the task's words so `symbol` breaks a tie by the task (devkb/session_context.py). Pushes
# nothing. The prompt router (devkb/router.py, `hook prompt`) is opt-in: it showed no effect on cost or turns in 72 benchmark runs.
# Never blocks and never fails the prompt. DEVKB_CMD overrides the released package (for testing a checkout);
# DEVKB_CONTEXT=0 turns the recording off.
exec ${DEVKB_CMD:-uvx --from 'devkb[mcp]>=0.2.15' devkb} hook context 2>/dev/null || exit 0
