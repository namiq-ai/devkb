"""What truth_clang.py, quality.py and adjudicate.py share: the vendored-path list and the interval."""
import json, math
from pathlib import Path

CORPUS = Path(__file__).resolve().parents[2] / "devkb" / "bench" / "cpp_corpus.json"


def vendored_prefixes(repo_name, corpus=CORPUS):
    """Vendored directory prefixes of `repo_name` from the corpus file (SPEC-DKB-004 F1); [] when the file or the entry is absent."""
    if not Path(corpus).exists():
        return []
    return list(json.loads(Path(corpus).read_text()).get("vendored", {}).get(repo_name, []))


def is_vendored(rel, prefixes):
    """`rel` (repo-relative, '/'-separated) equals a prefix or lies below it, by whole path components."""
    rel = rel.replace("\\", "/")
    if rel.startswith("./"):
        rel = rel[2:]
    return any(rel == p.strip("/") or rel.startswith(p.strip("/") + "/") for p in prefixes)


def wilson(k, n, z=1.96):
    """95% Wilson score interval for k successes of n: (low, high). (0, 1) for n == 0."""
    if n == 0:
        return (0.0, 1.0)
    p = k / n
    d = 1 + z * z / n
    centre = (p + z * z / (2 * n)) / d
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return (max(0.0, centre - half), min(1.0, centre + half))
