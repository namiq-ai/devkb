"""#132: `pack change` / `pack refactor` resolve the C++ `Class::method` spelling that `symbol` accepts."""
import re, sys; sys.path.insert(0, __file__.rsplit("/", 1)[0])
from _common import devkb, emit
res = {}
for kind in ("change", "refactor"):
    for name in ("Footer::DecodeFrom", "leveldb::Footer::DecodeFrom", "Footer.DecodeFrom"):
        out = devkb("pack", kind, name, repo="leveldb")
        ok = "cannot resolve" not in out and bool(re.search(r"reach it, at any depth \((\d+)\)|direct caller \((\d+)", out))
        n = re.search(r"reach it, at any depth \((\d+)\)", out)
        res[f"{kind} {name}"] = (ok, int(n.group(1)) if n else None)
emit(results={k: v for k, v in res.items()}, **{"pass": all(ok for ok, _ in res.values())})
