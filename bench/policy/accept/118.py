"""#118 (SPEC-DKB-004 F2) on a finished checkout: a call through a repository C macro links the invoking function to the
repository functions the macro's body calls.

With the checkout's own devkb (`devkb build`), on a C fixture (src/lib.c), read from the built graph's CALLS edges:
- `through_macro`: `use_grow` -> `grow` through `#define GROW(n) grow(n)`; `use_free` -> `item_free` and `log_it`
  through a `do { ... } while (0)` macro;
- `lower_confidence`: those edges are below a direct call's confidence (0.8);
- `system_macro_not_expanded`: `assert(x)` (from <assert.h>, not defined in the repository) adds no edge from `use_assert`;
- `depth_four`: a chain of 4 repository macros reaching `deep` links `use_deep3`; a chain of 5 does not link `use_deep`;
- `variants`: a macro with an `#ifdef`/`#else` definition each gives both targets, and those edges carry `variant: true`.
"""
import json, os, subprocess, sys, tempfile
from pathlib import Path

W = Path(sys.argv[1]).resolve()
PY = str(W / ".venv" / "bin" / "python")
ENV = dict(os.environ, PYTHONPATH=str(W), PYTHONWARNINGS="ignore")
LIB = ("#include <assert.h>\n"
       "static int grow(int n) { return n * 2; }\n"
       "int item_free(int x) { return x; }\n"
       "int log_it(int x) { return x; }\n"
       "#define GROW(n) grow(n)\n"
       "#define FREE_ITEM(p) do { item_free(p); log_it(p); } while (0)\n"
       "#define L1(x) L2(x)\n#define L2(x) L3(x)\n#define L3(x) L4(x)\n#define L4(x) L5(x)\n#define L5(x) deep(x)\n"
       "int deep(int x) { return x; }\n"
       "#ifdef FAST\n#define PICK(x) grow(x)\n#else\n#define PICK(x) item_free(x)\n#endif\n"
       "int use_grow(int n) { return GROW(n); }\n"
       "void use_free(int p) { FREE_ITEM(p); }\n"
       "int use_deep(int x) { return L1(x); }\n"
       "int use_deep3(int x) { return L2(x); }\n"
       "int use_assert(int x) { assert(x); return x; }\n"
       "int use_pick(int x) { return PICK(x); }\n")
out = {}
with tempfile.TemporaryDirectory() as td:
    r = Path(td) / "a"
    (r / "src").mkdir(parents=True)
    (r / "src" / "lib.c").write_text(LIB)
    subprocess.run("git init -q . && git add -A && git -c user.email=a@example.com -c user.name=a commit -qm i", shell=True, cwd=r, check=True)
    subprocess.run([PY, "-P", "-m", "devkb.cli", "build", "--project", str(r)], cwd=W, env=ENV, capture_output=True, timeout=600)
    edges, name = {}, {}
    store = r / ".devkb"
    for line in ((store / "nodes.jsonl").read_text().splitlines() if (store / "nodes.jsonl").exists() else []):
        n = json.loads(line)
        name[n["uid"]] = n["natural_key"].split("::")[-1]
    for line in ((store / "edges.jsonl").read_text().splitlines() if (store / "edges.jsonl").exists() else []):
        e = json.loads(line)
        if e.get("verb") == "CALLS":
            edges[(name.get(e["from_uid"], ""), name.get(e["to_uid"], ""))] = e.get("properties") or {}
    def has(a, b):
        return (a, b) in edges
    out["through_macro"] = has("use_grow", "grow") and has("use_free", "item_free") and has("use_free", "log_it")
    out["lower_confidence"] = out["through_macro"] and all(edges[k].get("confidence", 1) < 0.8 for k in
                                                           [("use_grow", "grow"), ("use_free", "item_free")])
    out["system_macro_not_expanded"] = not any(a == "use_assert" for a, _b in edges)
    out["depth_four"] = has("use_deep3", "deep") and not has("use_deep", "deep")
    v = [edges.get(("use_pick", "grow")), edges.get(("use_pick", "item_free"))]
    out["variants"] = all(v) and all(((x.get("extra") or {}).get("variant") or x.get("variant")) is True for x in v)
    out["edges"] = sorted(f"{a}->{b}" for a, b in edges)[:30]
out["pass"] = all(out[k] for k in ("through_macro", "lower_confidence", "system_macro_not_expanded", "depth_four", "variants"))
print(json.dumps(out))
