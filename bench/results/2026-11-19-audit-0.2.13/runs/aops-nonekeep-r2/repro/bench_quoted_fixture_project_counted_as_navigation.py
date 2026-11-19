"""devkb_commands() blanks quoted strings before reading --project, so a quoted /tmp fixture path is counted as
navigation instead of a self-test (#258)."""
import sys
from pathlib import Path
root = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(root / "bench" / "policy"))
import storybench as sb  # noqa: E402

bad = False
for cmd in ("devkb uses foo --project /tmp/fixture", 'devkb uses foo --project "/tmp/fixture"',
            "devkb uses foo --project '/tmp/fixture'"):
    nav, own = sb.devkb_commands(cmd)
    print(f"{cmd!r}: navigation={nav} self-test={own}")
    bad |= (nav, own) != (0, 1)
print("expected: navigation=0 self-test=1 whether or not the path is quoted")
sys.exit(1 if bad else 0)
