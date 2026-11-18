import re, sys; sys.path.insert(0, __file__.rsplit("/", 1)[0])
from _common import devkb, emit
out = devkb("uses", "decimal_point_impl", repo="fmt")
calls = all(re.search(rf"format\.h:{n}\b", out) for n in (1364, 1367))
wrong = [l for l in out.splitlines() if re.search(r"format\.h:(1362|1376|1377)\b", l) and "count_digits" in l]
calls_first = calls and out.find("format.h:1364") < min([out.find(f"format.h:{n}") for n in (1362, 1376, 1377) if out.find(f"format.h:{n}") >= 0] or [10**9])
emit(calls_shown=calls, wrong_enclosure=len(wrong), calls_before_declarations=calls_first, **{"pass": calls and not wrong and calls_first})
