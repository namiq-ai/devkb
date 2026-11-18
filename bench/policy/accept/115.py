import re, sys; sys.path.insert(0, __file__.rsplit("/", 1)[0])
from _common import devkb, emit
out = devkb("uses", "compute_delta", repo="fmt")
merged = bool(re.search(r"L339-1116", out))
both = bool(re.search(r"L339\b", out)) and bool(re.search(r"L1113\b", out))
emit(merged_span=merged, both_ranges=both, **{"pass": both and not merged})
