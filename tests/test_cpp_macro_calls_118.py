"""#118 (SPEC-DKB-004 F2): a call through a repository macro links the invoking function to the repository functions the
macro's body calls, with source `cpp-macro`.

Fixture code is synthetic."""
from __future__ import annotations

import cpp_support as S

LIB = ("#include <assert.h>\n"
       "static int grow(int n) { return n * 2; }\n"
       "int item_free(int x) { return x; }\n"
       "int log_it(int x) { return x; }\n"
       "#define GROW(n) grow(n)\n"
       "#define FREE_ITEM(p) do { item_free(p); log_it(p); } while (0)\n"
       "#define L1(x) L2(x)\n#define L2(x) L3(x)\n#define L3(x) L4(x)\n#define L4(x) L5(x)\n#define L5(x) deep(x)\n"
       "int deep(int x) { return x; }\n"
       "#define CALL_ARG(f, x) f(x)\n"
       "#ifdef FAST\n#define PICK(x) grow(x)\n#else\n#define PICK(x) item_free(x)\n#endif\n"
       "#ifdef FAST\n#define PICK2(x) (grow(x) + log_it(x))\n#else\n#define PICK2(x) (item_free(x) + log_it(x))\n#endif\n"
       "int use_grow(int n) { return GROW(n); }\n"
       "void use_free(int p) { FREE_ITEM(p); }\n"
       "int use_deep(int x) { return L1(x); }\n"
       "int use_deep3(int x) { return L2(x); }\n"
       "int use_assert(int x) { assert(x); return x; }\n"
       "int use_arg(int x) { return CALL_ARG(log_it, x); }\n"
       "int use_pick(int x) { return PICK(x); }\n"
       "int use_pick2(int x) { return PICK2(x); }\n")


def _edges(tmp_path):
    g = S.build(tmp_path, {"src/lib.c": LIB})
    return {(e.src.split("::")[-1], e.dst.split("::")[-1]): e for e in g.edges("CALLS") if e.source == "cpp-macro"}


def test_a_repository_macro_links_its_invokers_to_the_functions_it_calls(tmp_path):
    e = _edges(tmp_path)
    assert ("use_grow", "grow") in e
    assert ("use_free", "item_free") in e and ("use_free", "log_it") in e
    assert e[("use_grow", "grow")].confidence < 0.8 and "GROW" in e[("use_grow", "grow")].evidence_ref


def test_nesting_stops_at_depth_four(tmp_path):
    e = _edges(tmp_path)
    assert ("use_deep", "deep") not in e          # L1 -> L2 -> L3 -> L4 -> L5 -> deep: five macro levels
    assert ("use_deep3", "deep") in e             # L2 -> L3 -> L4 -> L5 -> deep: four


def test_a_macro_the_repository_does_not_define_is_not_expanded(tmp_path):
    assert not [k for k in _edges(tmp_path) if k[0] == "use_assert"]


def test_a_macro_parameter_is_not_a_call_target(tmp_path):
    assert not [k for k in _edges(tmp_path) if k[0] == "use_arg"]


def test_a_call_only_some_if_variants_make_is_not_linked(tmp_path):
    """0.2.15: the union of `#if` variants was linked and marked `variant`; adjudicated, 19 of 29 `cpp-macro` edges of autoas were such calls (a macro
    that is empty without `USE_DET`, a timer macro that calls `Std_TimerInit` only with `OSEKNM_USE_STD_TIMER`). A call every variant makes is linked."""
    e = _edges(tmp_path)
    assert not [k for k in e if k[0] == "use_pick"], "PICK calls grow or item_free depending on FAST: neither is linked"
    assert ("use_pick2", "log_it") in e, "both variants of PICK2 call log_it"
    assert not [k for k in e if k[0] == "use_pick2" and k[1] in ("grow", "item_free")]
    assert ("use_grow", "grow") in e and not e[("use_grow", "grow")].extra


def test_a_macro_of_the_same_name_in_a_file_the_caller_does_not_see_is_not_expanded(tmp_path):
    files = {"a.c": "int a_fn(int x) { return x; }\n#define STEP(x) a_fn(x)\nint use_a(int x) { return STEP(x); }\n",
             "b.c": "int b_fn(int x) { return x; }\n#define STEP(x) b_fn(x)\nint use_b(int x) { return STEP(x); }\n"}
    g = S.build(tmp_path, files)
    e = {(x.src.split("::")[-1], x.dst.split("::")[-1]) for x in g.edges("CALLS") if x.source == "cpp-macro"}
    assert ("use_a", "a_fn") in e and ("use_b", "b_fn") in e
    assert ("use_a", "b_fn") not in e and ("use_b", "a_fn") not in e, "each file expands its own definition only"


def test_a_header_macro_is_seen_by_the_file_that_includes_it_and_by_nobody_else(tmp_path):
    files = {"m.h": "#define RUN(x) helper(x)\n", "helper.c": "int helper(int x) { return x; }\n",
             "with.c": '#include "m.h"\nint with_inc(int x) { return RUN(x); }\n', "without.c": "int without_inc(int x) { return RUN(x); }\n"}
    g = S.build(tmp_path, files)
    e = {(x.src.split("::")[-1], x.dst.split("::")[-1]) for x in g.edges("CALLS") if x.source == "cpp-macro"}
    assert ("with_inc", "helper") in e and not [k for k in e if k[0] == "without_inc"]
