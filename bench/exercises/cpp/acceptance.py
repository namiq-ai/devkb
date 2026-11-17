#!/usr/bin/env python3
"""Acceptance check for the C/C++ exercise. Fixed and hashed (acceptance.sha256) before any run.

  python3 acceptance.py WORKTREE CHECKOUTS_DIR [--skip-suite]  ->  JSON on stdout

Runs the worktree's own code (PYTHONPATH=WORKTREE). The fixture's expected symbols and edges were written by hand from
the C++ source, not from any implementation."""
import json, os, subprocess, sys, tempfile, textwrap, time
from pathlib import Path

W, CK = Path(sys.argv[1]).resolve(), Path(sys.argv[2]).resolve()
SKIP = "--skip-suite" in sys.argv
PY = sys.executable

FIXTURE = {
"geo.h": r'''
#pragma once
#include <vector>
namespace geo {
class Shape {
 public:
  Shape(int id) : id_(id), tags_{1, 2} { reset(); }
  virtual ~Shape() {}
  int id() const { return id_; }
  bool operator==(const Shape& o) const { return id_ == o.id_; }
  void reset();
  double area() const;
 private:
  int id_;
  std::vector<int> tags_;
};
struct Point {
  double x, y;
  double norm() const { return helper(x) + helper(y); }
};
enum class Color { Red, Green };
double helper(double v);
struct Other { void reset() { } };
}  // namespace geo
''',
"geo.cpp": r'''
#include "geo.h"
// double ghost() { return 1; }
/* int ghost2() { return 2; } */
namespace geo {
static const char* kMsg = "void fake() { }";
#define BROKEN(x) int macro_fn() { return x; }
double helper(double v) { return v * v; }
void Shape::reset() { id_ = 0; }
double Shape::area() const { return helper(id_); }
namespace detail {
int twice(int x) { return x * 2; }
}
template <typename T>
T clampv(T v, T lo, T hi) { return v < lo ? lo : v > hi ? hi : v; }
}  // namespace geo
extern "C" {
int c_entry(int x) { return geo::detail::twice(x); }
}
int main() {
  geo::Shape s(1);
  s.reset();
  return c_entry(2) + static_cast<int>(geo::helper(2));
}
''',
"geo_test.cc": r'''
#include <gtest/gtest.h>
TEST(GeoSuite, AreaIsZero) { }
TEST_F(GeoFixture, Resets) { }
TEST_CASE("clamps values") { }
''',
"util.c": r'''
static int add(int a, int b) { return a + b; }
int plus_one(int x) { return add(x, 1); }
''',
}
SYMS = {  # key -> kind
 "geo.h::geo.Shape": "class", "geo.h::geo.Shape.Shape": "method", "geo.h::geo.Shape.~Shape": "method",
 "geo.h::geo.Shape.id": "method", "geo.h::geo.Shape.operator==": "method", "geo.h::geo.Point": "class",
 "geo.h::geo.Point.norm": "method", "geo.h::geo.Color": "enum", "geo.h::geo.Other": "class",
 "geo.h::geo.Other.reset": "method",
 "geo.cpp::geo.helper": "function", "geo.cpp::geo.Shape.reset": "method", "geo.cpp::geo.Shape.area": "method",
 "geo.cpp::geo.detail.twice": "function", "geo.cpp::geo.clampv": "function",
 "geo.cpp::c_entry": "function", "geo.cpp::main": "function",
 "util.c::add": "function", "util.c::plus_one": "function",
}
FORBID_SYM = ("ghost", "ghost2", "fake", "macro_fn", "kMsg", "GeoSuite", "TEST")
REQ_EDGES = [
 ("geo.h::geo.Shape.Shape", "geo.cpp::geo.Shape.reset"),      # bare call from a constructor, definition in another file
 ("geo.cpp::geo.Shape.area", "geo.cpp::geo.helper"),
 ("geo.h::geo.Point.norm", "geo.cpp::geo.helper"),            # a header method calling a function defined in a .cpp
 ("geo.cpp::c_entry", "geo.cpp::geo.detail.twice"),           # qualified call
 ("geo.cpp::main", "geo.cpp::c_entry"),
 ("geo.cpp::main", "geo.cpp::geo.helper"),
 ("util.c::plus_one", "util.c::add"),
]
FORBID_EDGES = [  # `reset` exists on Shape and Other: a call on an object of unknown type must not pick Other
 ("geo.cpp::main", "geo.h::geo.Other.reset"), ("geo.cpp::geo.Shape.area", "geo.h::geo.Other.reset"),
]
RESULT = {"checks": {}, "detail": {}}


def check(name, ok, detail=None):
    RESULT["checks"][name] = bool(ok)
    if detail is not None:
        RESULT["detail"][name] = detail


def run(cmd, cwd, timeout=1800, env_extra=None):
    env = dict(os.environ, PYTHONPATH=str(W), PYTHONWARNINGS="ignore", **(env_extra or {}))
    return subprocess.run(cmd, cwd=cwd, env=env, capture_output=True, text=True, timeout=timeout)


EXTRACT = textwrap.dedent('''
    import json, sys, time
    from pathlib import Path
    from devkb import build_symbols
    t = time.time(); g = build_symbols.extract(Path(sys.argv[1])); dt = time.time() - t
    nodes = [{"key": n.natural_key, "kind": n.props.get("kind"), "ls": n.props.get("line_start"), "le": n.props.get("line_end"),
              "source": n.source} for n in g.nodes("Symbol")]
    uid = {n.uid: n.natural_key for n in g.nodes("Symbol")}
    edges = [{"from": uid.get(e.from_uid), "to": uid.get(e.to_uid), "conf": e.confidence, "ev": e.evidence_ref}
             for e in g.edges("CALLS")]
    defined = [(e.src, e.dst) for e in g.edges("DEFINED_IN")]
    print(json.dumps({"secs": dt, "nodes": nodes, "edges": edges, "defined": defined}))
''')


def extract(path):
    p = run([PY, "-c", EXTRACT, str(path)], cwd=str(W), timeout=900)
    if p.returncode:
        return None, p.stderr[-600:]
    return json.loads(p.stdout.splitlines()[-1]), None


# 1. the repository's own suite
if not SKIP:
    p = run([PY, "-m", "pytest", "tests", "-q", "-x", "-p", "no:cacheprovider"], cwd=str(W))
    tail = p.stdout.strip().splitlines()[-1] if p.stdout.strip() else p.stderr[-200:]
    check("suite_passes", p.returncode == 0, tail)

# 2. the hand-written fixture
with tempfile.TemporaryDirectory() as d:
    d = Path(d)
    for name, body in FIXTURE.items():
        (d / name).write_text(body.lstrip())
    for c in (["init", "-q"], ["add", "."], ["-c", "user.name=a", "-c", "user.email=a@example.com", "commit", "-qm", "x"]):
        subprocess.run(["git", *c], cwd=d, check=True, capture_output=True)
    out, err = extract(d)
    check("fixture_extracts", out is not None, err)
    if out:
        by_key = {n["key"]: n for n in out["nodes"]}
        got = {k for k in by_key}
        missing = sorted(set(SYMS) - got)
        check("fixture_symbols_complete", not missing, {"missing": missing})
        check("fixture_kinds", all(by_key.get(k, {}).get("kind") == v for k, v in SYMS.items()),
              {k: by_key.get(k, {}).get("kind") for k, v in SYMS.items() if by_key.get(k, {}).get("kind") != v})
        extra = sorted(k for k in got if k not in SYMS)
        check("fixture_no_forbidden_or_extra_symbols",
              not any(f in k.split("::", 1)[-1] for k in got for f in FORBID_SYM) and not extra, {"extra": extra})
        lines = (d / "geo.cpp").read_text().splitlines()
        sh = by_key.get("geo.cpp::geo.Shape.area", {})
        check("fixture_lines", sh.get("ls") == 9 and sh.get("le") == 9 and by_key.get("geo.h::geo.Shape", {}).get("le", 0) > by_key.get("geo.h::geo.Shape", {}).get("ls", 0),
              {"area": [sh.get("ls"), sh.get("le")], "geo_cpp_line9": lines[8] if len(lines) > 8 else None})
        edges = {(e["from"], e["to"]) for e in out["edges"]}
        miss_e = [e for e in REQ_EDGES if e not in edges]
        check("fixture_required_edges", not miss_e, {"missing": miss_e})
        check("fixture_forbidden_edges_absent", not [e for e in FORBID_EDGES if e in edges], {"present": [e for e in FORBID_EDGES if e in edges]})
        check("fixture_edges_have_confidence_below_1_and_evidence", all(e["conf"] < 1 and e["ev"] for e in out["edges"] if e["from"] and e["from"].split("::")[0] in FIXTURE))
        check("fixture_defined_in", all(any(s == k and f == k.split("::")[0] for s, f in out["defined"]) for k in SYMS))
    # test discovery
    code = textwrap.dedent('''
        import json, sys
        from pathlib import Path
        from devkb import test_discovery as t
        r = Path(sys.argv[1])
        print(json.dumps({"files": t.list_test_files(r), "cases": t.tests_in_file(r, "geo_test.cc")}))
    ''')
    p = run([PY, "-c", code, str(d)], cwd=str(W))
    try:
        td = json.loads(p.stdout.splitlines()[-1])
        names = [c[0] for c in td["cases"]]
        check("test_discovery", "geo_test.cc" in td["files"] and "GeoSuite.AreaIsZero" in names and "GeoFixture.Resets" in names
              and "clamps values" in names and all(isinstance(c[1], int) for c in td["cases"]), td)
    except Exception:
        check("test_discovery", False, p.stderr[-300:])

# 3. the three public checkouts
SPOT = {
 "cJSON": ["cJSON.c::cJSON_Parse", "cJSON.c::cJSON_Delete"],
 "leveldb": ["table/format.cc::leveldb.ReadBlock", "db/db_impl.cc::leveldb.DBImpl.Get", "table/table_builder.cc::leveldb.TableBuilder.Add"],
 "fmt": [],
}
FLOOR = {"cJSON": 500, "fmt": 1000, "leveldb": 900}
for name in ("cJSON", "fmt", "leveldb"):
    out, err = extract(CK / name)
    check(f"{name}_builds", out is not None, err)
    if not out:
        continue
    cpp = [n for n in out["nodes"] if n["key"].split("::")[0].lower().endswith((".c", ".cc", ".cpp", ".h", ".hpp", ".hh", ".cxx", ".hxx", ".inl"))]
    keys = {n["key"] for n in cpp}
    check(f"{name}_symbol_floor", len(cpp) >= FLOOR[name], {"symbols": len(cpp), "floor": FLOOR[name]})
    check(f"{name}_under_20s", out["secs"] < 20, {"secs": round(out["secs"], 1)})
    check(f"{name}_spot_symbols", all(k in keys for k in SPOT[name]), [k for k in SPOT[name] if k not in keys])
    cedges = [e for e in out["edges"] if e["from"] in keys and e["to"] in keys]
    check(f"{name}_has_calls", len(cedges) >= {"cJSON": 100, "fmt": 300, "leveldb": 500}[name], {"edges": len(cedges)})
    # soundness: the callee's short name appears in the caller's own file (overloads share one node, so a line range
    # is not a reliable boundary)
    bad = 0
    sample = cedges[::max(1, len(cedges) // 400)]
    node = {n["key"]: n for n in cpp}
    for e in sample:
        f, q = e["from"].split("::", 1)
        try:
            src = (CK / name / f).read_text(errors="replace").splitlines()
        except OSError:
            continue
        body = "\n".join(src)
        short = e["to"].split("::", 1)[1].rsplit(".", 1)[-1]
        if short not in body:
            bad += 1
    check(f"{name}_edges_sound", bad == 0, {"sampled": len(sample), "unsound": bad, "edges": len(cedges)})
    if name == "leveldb":
        check("leveldb_known_chain", ("table/table.cc::leveldb.Table.Open", "table/format.cc::leveldb.ReadBlock") in {(e["from"], e["to"]) for e in cedges})
RESULT["passed"] = sum(RESULT["checks"].values())
RESULT["total"] = len(RESULT["checks"])
print(json.dumps(RESULT, indent=1))
