#!/usr/bin/env bash
# devkb plugin, UserPromptSubmit: route the prompt to the graph's answer for its SDLC stage (devkb/router.py).
# Never blocks and never fails the prompt. DEVKB_CMD overrides the released package (for testing a checkout);
# DEVKB_ROUTER=0 turns the router off.
exec ${DEVKB_CMD:-uvx --from 'devkb[mcp]>=0.2.15' devkb} hook prompt 2>/dev/null || exit 0
