"""DKB-003: calls are linked only when provable, and a pack says Incomplete when the graph could not follow one."""
from __future__ import annotations

import cpp_support as S

TABLE = {
    "src/table.h": "class Table {\n public:\n  void Add(int v);\n  int end() const;\n};\nclass Other {\n public:\n  void Add(int v);\n};\n",
    "src/table.cc": "#include \"table.h\"\nvoid Table::Add(int v) {}\nint Table::end() const { return 0; }\nvoid Other::Add(int v) {}\n",
    "src/user.cc": "#include \"table.h\"\nvoid typed(int x) {\n  Table* t = 0;\n  t->Add(x);\n}\n",
    "src/other.cc": ("void unknown(Thing* p) {\n  p->Add(1);\n}\n"
                    "void inferred() {\n  auto q = make();\n  q->Add(2);\n}\n"
                    "void stdlib() {\n  file_map_.end();\n}\n"),
}


def test_untyped_pointer_call_is_unresolved_and_the_pack_is_incomplete(tmp_path, monkeypatch):
    api, packer = S.api(tmp_path, TABLE, monkeypatch)
    r = api.callers("src/table.cc::Table.Add")
    cov = r["coverage"]
    assert cov["complete"] is False and cov["unresolved_calls"] >= 1
    assert "src/other.cc" in cov["search_files"]
    assert r["direct"] == ["src/user.cc::typed"]
    text = packer.refactor("Table.Add", path="src/table.cc")
    assert "Incomplete" in text and "Complete." not in text


def test_typed_local_links_and_untyped_or_inferred_receivers_do_not(tmp_path):
    g = S.build(tmp_path, TABLE)
    into = {src for src, dst in S.calls(g) if dst == "src/table.cc::Table.Add"}
    assert into == {"src/user.cc::typed"}
    assert not any(dst == "src/table.cc::Other.Add" for _s, dst in S.calls(g))
    srcs = {e.source for e in g.edges("CALLS") if e.dst == "src/table.cc::Table.Add"}
    assert srcs == {"cpp-typed-receiver"}


def test_std_method_on_an_unseen_type_is_not_linked_to_a_repo_method_of_that_name(tmp_path):
    g = S.build(tmp_path, TABLE)
    assert not any(dst == "src/table.cc::Table.end" for _s, dst in S.calls(g))
    node = S.symbols(g)["src/table.cc::Table.end"]
    assert node.props["unresolved_calls"] >= 1, "counted, not guessed"


def test_bare_call_never_links_to_another_classs_method(tmp_path):
    files = {
        "a.cc": "class A { public: void run(); };\nclass B { public: void Add(int); };\nvoid A::run() { Add(1); }\nvoid B::Add(int) {}\n",
    }
    g = S.build(tmp_path, files)
    assert ("a.cc::A.run", "a.cc::B.Add") not in S.calls(g)
    assert S.symbols(g)["a.cc::B.Add"].props["unresolved_calls"] == 1


def test_c_library_names_are_never_linked_across_files(tmp_path):
    files = {
        "lib/shim.c": "void exit(int c) {}\nvoid *memcpy(void *d, const void *s, int n) { return d; }\nint printf(const char *f) { return 0; }\n",
        "app/main.c": "int main(void) {\n  exit(1);\n  memcpy(0, 0, 1);\n  printf(\"192.0.2.1\");\n  return 0;\n}\n",
    }
    g = S.build(tmp_path, files)
    assert not [e for e in S.calls(g) if e[0] == "app/main.c::main"]


def test_c_static_function_links_within_its_file_among_ten_same_named(tmp_path):
    files = {f"mod{i}.c": f"static int log_it(void) {{ return {i}; }}\nint use{i}(void) {{ return log_it(); }}\n" for i in range(10)}
    files["extra.c"] = "static int log_it(void) { return 99; }\n"
    g = S.build(tmp_path, files)
    calls = S.calls(g)
    for i in range(10):
        assert (f"mod{i}.c::use{i}", f"mod{i}.c::log_it") in calls
    assert sum(1 for e in g.edges("CALLS") if e.source == "cpp-same-file") == 10


def test_unique_free_function_links_across_files_and_qualified_calls_resolve(tmp_path):
    files = {
        "core.c": "int core_init(void) { return 0; }\n",
        "ns.cc": "namespace util { int twice(int x) { return x * 2; } }\nclass Box { public: static int make(); };\nint Box::make() { return 1; }\n",
        "main.cc": "int run() { core_init(); util::twice(2); Box::make(); std::move(1); return 0; }\n",
    }
    g = S.build(tmp_path, files)
    got = {(e.dst, e.source) for e in g.edges("CALLS") if e.src == "main.cc::run"}
    assert got == {("core.c::core_init", "cpp-unique-free"), ("ns.cc::twice", "cpp-qualified"), ("ns.cc::Box.make", "cpp-qualified")}


def test_this_and_same_class_and_base_calls_resolve(tmp_path):
    files = {
        "k.cc": ("class Base { public: void save(); };\nclass K : public Base {\n public:\n  void go();\n  void step();\n};\n"
                 "void Base::save() {}\nvoid K::step() {}\nvoid K::go() { step(); this->step(); save(); }\n"),
    }
    g = S.build(tmp_path, files)
    got = {(e.dst, e.source) for e in g.edges("CALLS") if e.src == "k.cc::K.go"}
    assert got == {("k.cc::K.step", "cpp-same-class"), ("k.cc::Base.save", "cpp-same-class-base")}


def test_each_incomplete_reason_has_a_fixture(tmp_path):
    files = {
        "v.cc": ("class Shape { public: virtual double Area() const; };\nclass Sq : public Shape { public: double Area() const; };\n"
                 "double Shape::Area() const { return 0; }\ndouble Sq::Area() const { return 1; }\n"
                 "class Plain { public: Plain(); ~Plain(); bool operator==(const Plain&) const; int calm() const; };\n"
                 "Plain::Plain() {}\nPlain::~Plain() {}\nbool Plain::operator==(const Plain&) const { return true; }\nint Plain::calm() const { return 1; }\n"),
    }
    syms = S.symbols(S.build(tmp_path, files))
    assert syms["v.cc::Shape.Area"].props["incomplete_reasons"] == ["dynamic-dispatch"]
    assert syms["v.cc::Sq.Area"].props["incomplete_reasons"] == ["dynamic-dispatch"]
    for name in ("Plain.Plain", "Plain.~Plain", "Plain.operator=="):
        assert syms[f"v.cc::{name}"].props["incomplete_reasons"] == ["implicit-call"]
    assert "incomplete_reasons" not in syms["v.cc::Plain.calm"].props


def test_unread_file_marks_every_symbol(tmp_path):
    files = {"big.c": "int big_fn(void) { return 0; }\n" + "/* " + "x" * (2 * 1024 * 1024) + " */\n", "small.c": "int small_fn(void) { return 1; }\n"}
    g = S.build(tmp_path, files)
    assert S.symbols(g)["small.c::small_fn"].props["incomplete_reasons"] == ["unread-file"]
    assert "big.c::big_fn" not in S.symbols(g)
    assert g.meta["cpp"]["skipped"] == ["big.c"]


def test_indirect_reference_makes_the_function_incomplete(tmp_path, monkeypatch):
    files = {
        "h.c": "int on_event(int x) { return x; }\nint plain(int x) { return x; }\n",
        "reg.c": "struct ops { int (*cb)(int); };\nstatic struct ops table = { .cb = on_event };\nint call_plain(void) { return plain(1); }\n",
    }
    api, packer = S.api(tmp_path, files, monkeypatch)
    assert api.callers("on_event")["coverage"]["complete"] is False
    assert api.callers("plain")["coverage"]["complete"] is True
    assert "Complete." in packer.refactor("plain")
    assert "Incomplete" in packer.refactor("on_event")


def test_a_define_d_name_is_a_macro_use_not_a_call(tmp_path):
    files = {"m.c": "#define twice(x) ((x) * 2)\nint twice_impl(int x) { return x; }\nint user(void) { return twice(3); }\n"}
    g = S.build(tmp_path, files)
    assert not S.calls(g)


def test_a_name_that_is_both_a_macro_and_a_function_is_counted_not_ignored(tmp_path):
    files = {
        "net.c": "#if defined(CONFIG_NET)\nvoid mon_register(int x) {}\n#else\n#define mon_register(...)\n#endif\n",
        "drv.c": "void init(void) {\n  mon_register(1);\n}\n",
    }
    g = S.build(tmp_path, files)
    assert not S.calls(g), "a macro use is never an edge"
    assert S.symbols(g)["net.c::mon_register"].props["unresolved_calls"] == 1, "but the pack must not say Complete"
