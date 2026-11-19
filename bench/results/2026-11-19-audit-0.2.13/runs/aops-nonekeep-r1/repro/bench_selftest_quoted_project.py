"""A devkb query against a fixture outside the checkout is a self-test (#258) whether or not its --project path is quoted."""
import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "bench" / "policy"))
import storybench as sb

cases = {
    "devkb symbol foo --project /tmp/fx": (0, 1),
    'devkb symbol foo --project "/tmp/fx"': (0, 1),
    "devkb symbol foo --project '/tmp/fx'": (0, 1),
}
bad = False
for cmd, want in cases.items():
    got = sb.devkb_commands(cmd)
    print(f"{cmd!r}: (nav, self-test) = {got}, expected {want}")
    bad |= got != want
sys.exit(1 if bad else 0)
