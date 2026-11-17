#!/usr/bin/env python3
"""Behaviour checks for a C/C++ build, independent of naming conventions: the owner's constraints (REQ) and the
specification's decisions (SPEC/ADR). Runs WORKTREE's own devkb through its CLI on small fixture repositories.

  behavior.py WORKTREE   ->  JSON {"req": {...}, "spec": {...}}
Each check is True/False. The REQ group applies to every arm; the SPEC group is what the accepted specification adds.
"""
import json, os, re, subprocess, sys, tempfile
from pathlib import Path

W = Path(sys.argv[1]).resolve()
ENV = dict(os.environ, PYTHONPATH=str(W), PYTHONWARNINGS="ignore")


def cli(args, cwd):
    return subprocess.run([sys.executable, "-P", "-W", "ignore", "-m", "devkb.cli", *args], cwd=cwd, env=ENV,
                          capture_output=True, text=True, timeout=300)


def repo(files):
    d = Path(tempfile.mkdtemp())
    for name, body in files.items():
        (d / name).parent.mkdir(parents=True, exist_ok=True)
        (d / name).write_text(body)
    for c in (["init", "-q"], ["add", "."], ["-c", "user.name=a", "-c", "user.email=a@example.com", "commit", "-qm", "x"]):
        subprocess.run(["git", *c], cwd=d, check=True, capture_output=True)
    cli(["build", "--project", "."], d)
    return d


def nodes_edges(d):
    nodes = [json.loads(l) for l in (d / ".devkb" / "nodes.jsonl").read_text().splitlines() if l.strip()] if (d / ".devkb" / "nodes.jsonl").exists() else []
    edges = [json.loads(l) for l in (d / ".devkb" / "edges.jsonl").read_text().splitlines() if l.strip()] if (d / ".devkb" / "edges.jsonl").exists() else []
    return nodes, edges


req, spec, detail = {}, {}, {}

# R1 / D2: a call through a pointer to a method. A pack for `add` must either list the caller `use`, or not say Complete.
d = repo({"store.h": "class Store { public: void add(int x); int v; };\n", "store.cpp": '#include "store.h"\nvoid Store::add(int x) { v = x; }\n',
          "user.cpp": '#include "store.h"\nvoid use(Store* s) { s->add(1); }\n'})
pack = cli(["pack", "--project", ".", "refactor", "add"], d).stdout + cli(["pack", "--project", ".", "change", "add", "--path", "store.cpp"], d).stdout
lists_caller = bool(re.search(r"\buse\b", pack))
says_complete = bool(re.search(r"\*\*Complete\.?\*\*", pack)) and "Incomplete" not in pack
req["R1_pack_never_says_Complete_while_missing_a_pointer_caller"] = lists_caller or not says_complete
detail["R1"] = {"lists_caller": lists_caller, "says_complete": says_complete}
spec["D2_pointer_receiver_with_declared_type_is_linked"] = lists_caller

# R2: an ambiguous receiver must not be guessed. Two classes have `add`; `o` is an Other*.
d = repo({"a.h": "struct Store { void add(int x) { } };\nstruct Other { void add(int x) { } };\n",
          "f.cpp": '#include "a.h"\nvoid g(Other* o) { o->add(2); }\nvoid h(Store* s) { s->add(3); }\n'})
n, e = nodes_edges(d)
uid = {x["uid"]: x["natural_key"] for x in n if x.get("type") == "Symbol"}
calls = {(uid.get(x["from_uid"]), uid.get(x["to_uid"])) for x in e if x.get("verb") == "CALLS"}
def has(a, b): return any(a in (x or "") and b in (y or "") for x, y in calls)
req["R2_ambiguous_receiver_not_guessed"] = not has("::g", "Store") and not has("::h", "Other")
spec["D2_typed_receivers_resolve_to_their_own_class"] = has("::g", "Other") and has("::h", "Store")
detail["R2"] = sorted(f"{a.split('::')[-1]}->{b.split('::')[-1]}" for a, b in calls if a and b)

# R5: honesty with a receiver whose type the graph cannot know (`auto x = make<Store>(); x.add(1)`). The graph is built by
# the arm's own code; the pack is rendered by the checkout this benchmark ships in (it resolves `Store.add`, which the
# arms' own pack code cannot when two classes define `add`). A pack for Store::add must list the caller `k` or not say Complete.
d = repo({"a.h": "struct Store { void add(int x) { } };\nstruct Other { void add(int x) { } };\ntemplate <class T> T make();\n",
          "k.cpp": '#include "a.h"\nvoid k() { auto x = make<Store>(); x.add(1); }\n'})
HERE = Path(__file__).resolve().parents[3]
pk = subprocess.run([sys.executable, "-P", "-W", "ignore", "-m", "devkb.cli", "pack", "--project", ".", "refactor", "Store.add"], cwd=d,
                    env=dict(os.environ, PYTHONPATH=str(HERE)), capture_output=True, text=True).stdout
lists_k = bool(re.search(r"\bk\b", pk.split("## Coverage")[0])); complete = bool(re.search(r"\*\*Complete\.?\*\*", pk)) and "Incomplete" not in pk
req["R5_untyped_receiver_pack_is_Incomplete_or_lists_the_caller"] = lists_k or not complete
detail["R5"] = {"lists_k": lists_k, "says_complete": complete, "pack_head": pk[:120]}

# R3: dependencies unchanged
py = (W / "pyproject.toml").read_text()
req["R3_dependencies_unchanged"] = bool(re.search(r'^dependencies = \["pyyaml>=6"\]', py, re.M))

# R4: the limits are stated to the user (README)
readme = (W / "README.md").read_text().lower()
req["R4_limits_stated_in_readme"] = all(w in readme for w in ("preprocessor", "overload")) and ("c++" in readme)

# D3: test frameworks, seen through the graph (`devkb build`), not through any one module's API
tdir = repo({"a_test.cc": '#include <gtest/gtest.h>\nTEST(Suite, GtestCase) { }\nTEST_F(Fx, FixtureCase) { }\n',
             "b_test.cpp": '#include <catch2/catch_test_macros.hpp>\nTEST_CASE("doctest or catch title") { }\n',
             "c_test.cc": "#include <boost/test/unit_test.hpp>\nBOOST_AUTO_TEST_CASE(boost_case) { }\n",
             "t/test_z.c": "#include <zephyr/ztest.h>\nZTEST(zsuite, ztest_case) { }\n"})
n, _ = nodes_edges(tdir)
names = " ".join(str(x.get("properties", {}).get("function", "")) for x in n if x.get("type") == "TestCase")
frameworks = {str(x.get("properties", {}).get("framework", "")) for x in n if x.get("type") == "TestCase" and not x["natural_key"].endswith(".py:1")}
spec["D3_gtest_catch_doctest_boost_cases_found"] = all(s in names for s in ("GtestCase", "doctest or catch title", "boost_case"))
spec["D3_zephyr_ztest_found"] = "ztest_case" in names
spec["D3_each_case_records_its_framework"] = len(frameworks - {"", "None", "pytest", "js"}) >= 2
detail["D3"] = {"names": names[:300], "frameworks": sorted(frameworks)}

# D4: errors (the message does not contain the function's name)
d = repo({"e.cpp": '#include <stdexcept>\nvoid fail_here(int x) { if (x) throw std::runtime_error("boom happened badly"); }\nvoid ok() { fail_here(0); }\n'})
pk = cli(["pack", "--project", ".", "error", "boom happened badly"], d).stdout
spec["D4_throw_message_traces_to_its_function"] = "fail_here" in pk
detail["D4"] = pk[:300]

# D5: overloads and macro-wrapped return type
d = repo({"o.cpp": 'int pick(int a) { return a; }\nint pick(double a) { return 1; }\n#define API(t) t\nAPI(int) wrapped_name(const char* s) { return 0; }\n'})
n, _ = nodes_edges(d)
syms = {x["natural_key"].split("::", 1)[-1]: x.get("properties", {}) for x in n if x.get("type") == "Symbol" and x["natural_key"].startswith("o.cpp::")}
spec["D5_overloads_carry_overload_count"] = any(k.endswith("pick") and str(v.get("overload_count", "")) in ("2",) for k, v in syms.items())
spec["D5_macro_wrapped_return_type_found"] = any(k.endswith("wrapped_name") for k in syms)
detail["D5"] = sorted(syms)

# Complete / Incomplete: the machinery exists for C/C++ (a symbol with an unresolved call carries the count)
print(json.dumps({"req": req, "spec": spec, "detail": detail}))
