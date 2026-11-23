"""#123, #124: defects the adjudicated precision sample (bench/cpp/samples) found in 0.2.15, each a call linked to something it does not mean."""
from __future__ import annotations

import cpp_support as S


def _calls(tmp_path, files):
    g = S.build(tmp_path, files)
    return {(e.src.split("::")[-1], e.dst.split("::")[-1], e.source) for e in g.edges("CALLS")}


def test_a_call_through_a_local_lambda_is_not_a_call_of_a_function_of_that_name(tmp_path):
    src = ("int write(int x) { return x; }\\n"
           "int use(int v) { auto write = [=](int i) { return i + v; }; return write(1); }\\n"
           "int plain(int v) { return write(v); }\\n")
    got = _calls(tmp_path, {"a.cpp": src})
    assert ("plain", "write", "cpp-same-file") in got
    assert not [k for k in got if k[0] == "use" and k[1] == "write"], "`write(1)` calls the local lambda"


def test_a_name_the_file_also_brings_in_by_using_is_not_linked_to_its_own_fallback(tmp_path):
    src = ("namespace std { template <class F> F use_facet(int) { return F(); } }\\n"
           "namespace d {\\n#if 1\\nusing std::use_facet;\\n#else\\ntemplate <class F> F use_facet(int) { return F(); }\\n#endif\\n"
           "int point() { return use_facet<int>(1); }\\n}\\n")
    got = _calls(tmp_path, {"a.cpp": src})
    assert not [k for k in got if k[0] == "point" and k[1] == "use_facet"], got


def test_a_copy_of_this_is_not_a_constructor_call(tmp_path):
    src = ("class Iter {\\n public:\\n  Iter() : cur_(0) {}\\n  explicit Iter(int c) : cur_(c) {}\\n"
           "  Iter dec() const { Iter pre(*this); return pre; }\\n  Iter make() const { return Iter(3); }\\n private:\\n  int cur_;\\n};\\n")
    got = _calls(tmp_path, {"a.cpp": src})
    assert [k for k in got if k[0] == "Iter.make" and k[1] == "Iter.Iter"], "a constructor call with an argument of another type still links"
    assert not [k for k in got if k[0] == "Iter.dec" and k[1] == "Iter.Iter"], "`Iter pre(*this)` copies"


def test_a_defaulted_destructor_is_a_symbol_in_the_class_and_outside_it(tmp_path):
    src = ("namespace N {\nclass A {\n public:\n  virtual ~A() = default;\n};\nclass B { public: ~B(); };\n"
           "B::~B() noexcept = default;\n}\n")
    g = S.build(tmp_path, {"a.cpp": src})
    names = {n.props.get("qualified_name") for n in g.nodes("Symbol")}
    assert {"A.~A", "B.~B"} <= names, names


def test_a_c_library_name_the_repository_defines_once_is_linked_to_that_definition(tmp_path):
    files = {"misclib.c": "void *memset(void *s, int c, unsigned n) { return s; }\n",
             "use.c": "void *memset(void *s, int c, unsigned n);\nvoid clear(char *p) { memset(p, 0, 4); }\n"}
    got = _calls(tmp_path, files)
    assert ("clear", "memset", "cpp-unique-free") in got, got
    none = _calls(tmp_path / "x", {"use.c": files["use.c"]})
    assert not [k for k in none if k[1] == "memset"], none


def test_a_host_side_program_calls_the_system_c_library_not_the_repositorys_own(tmp_path):
    files = {"fw/misclib.c": "void *memset(void *s, int c, unsigned n) { return s; }\n",
             "fw/use.c": "void *memset(void *s, int c, unsigned n);\nvoid clear(char *p) { memset(p, 0, 4); }\n",
             "tools/send.c": "void *memset(void *s, int c, unsigned n);\nvoid wipe(char *p) { memset(p, 0, 4); }\n"}
    got = _calls(tmp_path, files)
    assert ("clear", "memset", "cpp-unique-free") in got, got
    assert not [k for k in got if k[0] == "wipe"], got
