#!/usr/bin/env bash
# devkb plugin, PreToolUse on Edit/Write: give the agent the pack of the file it is about to edit, once per session.
# Never blocks and never fails the tool call. DEVKB_CMD overrides the released package (for testing a checkout).
exec ${DEVKB_CMD:-uvx --from 'devkb[mcp]>=0.2.4' devkb} hook pre-edit 2>/dev/null || exit 0
