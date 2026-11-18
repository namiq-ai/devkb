import re, sys; sys.path.insert(0, __file__.rsplit("/", 1)[0])
from _common import devkb, emit
out = devkb("pack", "change", "BloomTest.Add", repo="leveldb")
reach = re.search(r"## Functions that reach it[^\n]*\((\d+)\)\n(.*?)(?=\n## |\Z)", out, re.S)
linked = bool(reach and int(reach.group(1)) > 0 and "bloom_test.cc" in reach.group(2))
hint = [l for l in out.splitlines() if "search only these files" in l.lower()]
in_hint = any("util/bloom_test.cc" in l for l in hint)
emit(hint_has_own_file=in_hint, callers_linked=linked, hint_lines=len(hint), **{"pass": in_hint or linked})
