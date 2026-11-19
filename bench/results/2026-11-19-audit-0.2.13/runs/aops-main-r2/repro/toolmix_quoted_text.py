"""toolmix counts quoted text mentioning a devkb command as devkb use (and hides a grep from the search class)."""
import sys
from pathlib import Path
R = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(R / "bench" / "audit"))
import toolmix  # noqa: E402

bad = 0
cases = [('git commit -m "docs: explain devkb symbol output"', "other"),
         ('grep -rn --include=*.md -e "text" docs # see devkb uses', "search")]
for cmd, want in cases:
    got = toolmix.classify("Bash", {"command": cmd})
    n = toolmix.devkb_queries(cmd)
    print(f"{cmd!r}: class={got} devkb_queries={n}; expected class={want} devkb_queries=0")
    if got == "devkb" or n:
        bad = 1
sys.exit(bad)
