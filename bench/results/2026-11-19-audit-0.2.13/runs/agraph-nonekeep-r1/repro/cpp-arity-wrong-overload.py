import os, sys, json
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _h

d = _h.make({
 "a.h": "struct Foo { int bar(int x); int bar(int x, int y); };\n",
 "a.cc": '#include "a.h"\nint Foo::bar(int x) {\n  return x;\n}\n\nint Foo::bar(int x, int y) {\n  return x + y;\n}\n',
 "b.cc": '#include "a.h"\nvoid use1() { Foo f; f.bar(1); }\nvoid use2() { Foo f; f.bar(1, 2); }\n',
})
_h.build(d)
nodes = {}
for l in open(d + "/.devkb/nodes.jsonl"):
    n = json.loads(l)
    nodes[n["uid"]] = n
edges = [json.loads(l) for l in open(d + "/.devkb/edges.jsonl")]
calls = {}
for e in edges:
    if e["verb"] == "CALLS":
        src = nodes[e["from_uid"]]
        dst = nodes[e["to_uid"]]
        calls[e["evidence_ref"] if "evidence_ref" in e else e["properties"]["evidence_ref"]] = dst
for k, v in calls.items():
    print(k, "->", {x: v.get(x) for x in ("uid", "start_line", "line", "name") if x in v} or v)
rc, out = _h.dk("pack", "--project", d, "change", "a.cc::Foo.bar")
print(out.split("## Coverage")[0])
two_arg_node_has_caller = any(("L6" in str(v) or v.get("start_line") == 6 or v.get("line") == 6) for v in calls.values())
bad = "use2" in out.split("## Test files")[0] or not two_arg_node_has_caller
print("expected: use2 (2 args) calls the 2-parameter overload (a.cc:6) only; use1 calls a.cc:2 only")
print("actual: use2 reaches the 1-parameter overload; the 2-parameter overload has caller edge:", two_arg_node_has_caller)
sys.exit(1 if bad else 0)
