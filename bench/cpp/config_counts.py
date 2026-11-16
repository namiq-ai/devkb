#!/usr/bin/env python3
"""Independent `CONFIG_*` counts (SPEC-DKB-002 story 8): a regex count that imports nothing from devkb.

  config_counts.py REPO [--graph DIR]

Over the tracked `.c` files of REPO: the share that mention a `CONFIG_*` option outside comments, strings and
`#if 0` blocks. With `--graph DIR` (a `.devkb` directory) it also prints the share of `.c` files that devkb gives a
`READS` edge to a `kconfig:` ConfigKey, and exits 1 when the two shares differ by more than two points.
"""
import json
import re
import subprocess
import sys
from pathlib import Path

STRIP = re.compile(r'//[^\n]*|/\*.*?\*/|"(?:[^"\\\n]|\\.)*"|\'(?:[^\'\\\n]|\\.)*\'', re.S)
TOKEN = re.compile(r"\bCONFIG_[A-Za-z0-9_]+")
IF0 = re.compile(r"^[ \t]*#[ \t]*if[ \t]+0[ \t]*$.*?^[ \t]*#[ \t]*(?:else|elif|endif)\b", re.M | re.S)
DEFINE = re.compile(r"^[ \t]*#[ \t]*define\b(?:[^\n]*\\\n)*[^\n]*", re.M)


def reads_config(text: str) -> bool:
    text = STRIP.sub(lambda m: re.sub(r"[^\n]", " ", m.group(0)), text)
    text = IF0.sub("", text)
    text = DEFINE.sub("", text)          # a macro body is not a use; devkb reads uses
    return bool(TOKEN.search(text))


def main(argv: list[str]) -> int:
    repo = Path(argv[0]).resolve()
    graph = Path(argv[argv.index("--graph") + 1]) if "--graph" in argv else None
    cfiles = [f for f in subprocess.run(["git", "ls-files", "--recurse-submodules", "--", "*.c"], cwd=repo, capture_output=True, text=True).stdout.split("\n")
              if f and not any(s in f.split("/")[:-1] for s in ("third_party", "thirdparty", "vendor", "external", "build"))]
    mine = {f for f in cfiles if reads_config((repo / f).read_text(errors="replace"))}
    out = {"c_files": len(cfiles), "reading_config": len(mine), "share": round(len(mine) / max(1, len(cfiles)), 4)}
    code = 0
    if graph is not None:
        uid_path, keys = {}, set()
        for line in (graph / "nodes.jsonl").read_text().splitlines():
            n = json.loads(line)
            if n["type"] in ("File", "Symbol"):
                uid_path[n["uid"]] = n["natural_key"].split("::", 1)[0]
            elif n["type"] == "ConfigKey" and n["natural_key"].startswith("kconfig:"):
                keys.add(n["uid"])
        theirs = set()
        for line in (graph / "edges.jsonl").read_text().splitlines():
            e = json.loads(line)
            if e["verb"] == "READS" and e["to_uid"] in keys and uid_path.get(e["from_uid"], "").endswith(".c"):
                theirs.add(uid_path[e["from_uid"]])
        out["devkb_reading_config"] = len(theirs)
        out["devkb_share"] = round(len(theirs) / max(1, len(cfiles)), 4)
        out["share_difference_points"] = round(abs(out["share"] - out["devkb_share"]) * 100, 2)
        out["only_independent"] = sorted(mine - theirs)[:10]
        out["only_devkb"] = sorted(theirs - mine)[:10]
        code = 1 if out["share_difference_points"] > 2 else 0
    print(json.dumps(out))
    return code


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
