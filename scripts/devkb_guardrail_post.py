#!/usr/bin/env python3
"""devkb guardrail, PostToolUse companion (#133): adds what the search found to the verdict the PreToolUse hook kept
for the same tool_use_id. When devkb could not answer (or only partly) and grep found code, one line is appended to
`<repo>/.devkb/graph-misses.jsonl`. Read it with `devkb misses --project .`. Never prints, never blocks.
`DEVKB_MISSLOG=0` turns it off.
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
PENDING = Path.home() / ".claude" / "hooks" / ".devkb-guardrail-pending"


def response_text(resp) -> tuple[str, list[str]]:
    if isinstance(resp, str):
        return resp, []
    if not isinstance(resp, dict):
        return "", []
    text = "\n".join(str(resp[k]) for k in ("stdout", "content", "output") if isinstance(resp.get(k), str))
    files = [f for f in resp.get("filenames") or [] if isinstance(f, str)]
    return text, files


def main() -> int:
    from devkb import misses
    try:
        ev = json.load(sys.stdin)
    except ValueError:
        return 0
    key = "".join(c for c in str(ev.get("tool_use_id") or "") if c.isalnum() or c in "-_")[:80]
    f = PENDING / key
    if not misses.enabled() or not key or not f.is_file():
        return 0
    try:
        pending = json.loads(f.read_text())
        f.unlink()
    except (OSError, ValueError):
        return 0
    text, files = response_text(ev.get("tool_response"))
    misses.record(pending, misses.parse_grep(text, files, names=pending.get("names"), repo=Path(pending["repo"])))
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception:  # noqa: BLE001
        sys.exit(0)
