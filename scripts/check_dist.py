"""Refuse to publish a distribution that carries internal names or local paths.

devkb grew inside a private factory; its comments still name the factory's projects. PyPI is public and permanent, so
the PyPI job runs this on the built wheel and sdist and stops on any match. Patterns are in .release-denylist (one
regular expression per line, `#` comments).

  python3 scripts/check_dist.py dist/*
"""
from __future__ import annotations

import re
import sys
import tarfile
import zipfile
from pathlib import Path


def members(path: Path):
    if path.suffix == ".whl":
        with zipfile.ZipFile(path) as z:
            for n in z.namelist():
                yield n, z.read(n)
    elif path.name.endswith(".tar.gz"):
        with tarfile.open(path) as t:
            for m in t.getmembers():
                if m.isfile():
                    yield m.name, t.extractfile(m).read()


def main() -> int:
    rules = [re.compile(x) for x in (Path(__file__).resolve().parents[1] / ".release-denylist").read_text().splitlines()
             if x.strip() and not x.lstrip().startswith("#")]
    hits: dict[str, int] = {}
    for arg in sys.argv[1:]:
        for name, data in members(Path(arg)):
            text = data.decode("utf-8", "ignore")
            n = sum(len(r.findall(text)) for r in rules)
            if n:
                hits[f"{Path(arg).name}:{name}"] = n
    for k, n in sorted(hits.items(), key=lambda kv: -kv[1])[:40]:
        print(f"{n:5d}  {k}")
    if hits:
        print(f"{sum(hits.values())} matches in {len(hits)} files: not publishable", file=sys.stderr)
        return 1
    print("no internal names or local paths")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
