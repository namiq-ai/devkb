"""Where C# call sites go: resolved, or why not (python bench/cs_stats.py REPO...). Reads source, writes nothing."""
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from devkb import csharp_symbols  # noqa: E402

out = {}
for repo in sys.argv[1:]:
    stats: dict[str, int] = {}
    t = time.time()
    symbols, calls = csharp_symbols.extract(Path(repo), stats)
    named = sum(v for k, v in stats.items() if k != "external")
    out[Path(repo).name] = {"seconds": round(time.time() - t, 1), "symbols": len(symbols), "edges": len(calls),
                            "call_sites": sum(stats.values()), "to_repo_names": named,
                            **{k: stats[k] for k in sorted(stats)}}
    row = out[Path(repo).name]
    print(Path(repo).name, f"{row['seconds']}s", "call sites to repo names:", named, "resolved:",
          f"{stats.get('resolved', 0) / named:.0%}" if named else "-",
          {k: f"{v / named:.1%}" for k, v in sorted(stats.items(), key=lambda kv: -kv[1]) if k not in ("external", "resolved")})
print(json.dumps(out))
