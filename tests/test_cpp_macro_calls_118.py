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
       "int use_grow(int n) { return GROW(n); }\n"
       "void use_free(int p) { FREE_ITEM(p); }\n"
       "int use_deep(int x) { return L1(x); }\n"
       "int use_deep3(int x) { return L2(x); }\n"
       "int use_assert(int x) { assert(x); return x; }\n"
       "int use_arg(int x) { return CALL_ARG(log_it, x); }\n"
       "int use_pick(int x) { return PICK(x); }\n")


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


def test_if_variants_give_the_union_and_are_marked(tmp_path):
    e = _edges(tmp_path)
    assert ("use_pick", "grow") in e and ("use_pick", "item_free") in e
    assert e[("use_pick", "grow")].extra.get("variant") is True
    assert not e[("use_grow", "grow")].extra.get("variant")
