"""#119 (SPEC-DKB-004 F3): constructor calls link to the class's constructor: `T x(args)`, `T x{args}`, `T(args)`, `new T(args)`,
`std::make_unique<T>` / `make_shared<T>`, and base and member initialisers. Several constructors fitting the argument count: left unresolved
and counted. Fixture code is synthetic."""
from __future__ import annotations

import cpp_support as S

T = ("class Widget {\n public:\n  Widget(int a);\n  Widget(int a, int b);\n  int size() const;\n};\n"
     "Widget::Widget(int a) {}\nWidget::Widget(int a, int b) {}\n")
ONE = "Widget::Widget(int a)"


def _targets(g, caller):
    return {dst for src, dst in S.calls(g) if src == caller}


def _build(tmp_path, body, extra=""):
    return S.build(tmp_path, {"w.cc": T + extra + "void user() {\n" + body + "\n}\n"})


def test_a_local_declaration_with_parentheses_or_braces_links_by_argument_count(tmp_path):
    g = _build(tmp_path, "  Widget a(1);\n  Widget b{1, 2};")
    assert {s for s in _targets(g, "w.cc::user")} == {"w.cc::Widget.Widget"}, _targets(g, "w.cc::user")


def test_new_and_make_unique_link_to_the_constructor(tmp_path):
    g = _build(tmp_path, "  Widget* p = new Widget(1);\n  auto q = std::make_unique<Widget>(1, 2);\n  auto r = std::make_shared<Widget>(3);")
    assert "w.cc::Widget.Widget" in _targets(g, "w.cc::user")


def test_the_constructor_edge_has_its_own_source(tmp_path):
    g = _build(tmp_path, "  Widget a(1);")
    es = [e for e in g.edges("CALLS") if e.src == "w.cc::user"]
    assert es and es[0].source == "cpp-constructor", [(e.dst, e.source) for e in es]


def test_a_member_initialiser_of_a_repository_class_type_builds_it_with_its_constructor(tmp_path):
    extra = "class Holder {\n public:\n  Holder() : w_(1) {}\n  Widget w_;\n};\n"
    g = S.build(tmp_path, {"w.cc": T + extra})
    assert "w.cc::Widget.Widget" in _targets(g, "w.cc::Holder.Holder")


def test_constructors_of_one_arity_share_their_node_as_overloads_do(tmp_path):
    files = {"a.cc": ("class Twin {\n public:\n  Twin(int a);\n  Twin(const char* s);\n};\nTwin::Twin(int a) {}\nTwin::Twin(const char* s) {}\n"
                      "void user() { Twin t(1); }\n")}
    g = S.build(tmp_path, files)
    assert _targets(g, "a.cc::user") == {"a.cc::Twin.Twin"}, "the graph keeps one node for the overloads, so the edge is to it (#291)"


def test_two_classes_of_one_name_are_left_unresolved_and_counted(tmp_path):
    files = {"a.cc": "namespace x { class Twin { public: Twin(int a); }; Twin::Twin(int a) {} }\n"
                     "namespace y { class Twin { public: Twin(int a); }; Twin::Twin(int a) {} }\n"
                     "void user() { Twin t(1); }\n"}
    g = S.build(tmp_path, files)
    assert not _targets(g, "a.cc::user"), "no guess between two classes"
    assert any(n.props.get("unresolved_calls") for n in S.symbols(g).values() if n.props["qualified_name"].endswith("Twin.Twin")), \
        "but the pack must not say Complete"


def test_a_type_that_is_not_a_repository_class_is_not_linked_or_counted(tmp_path):
    g = S.build(tmp_path, {"a.cc": "void helper(int) {}\nvoid user() { std::string s(3); int n(4); helper(n); }\n"})
    assert _targets(g, "a.cc::user") == {"a.cc::helper"}


def test_a_copy_or_move_is_not_linked_to_a_declared_constructor_it_does_not_call(tmp_path):
    files = {"a.cc": ("class Opt {\n public:\n  Opt();\n};\nOpt::Opt() {}\nOpt make() { Opt o; return o; }\n"
                      "void user(const Opt& other) { Opt a(other); }\n")}
    g = S.build(tmp_path, files)
    # `Opt a(other)` passes one argument and Opt declares only a default constructor: an implicit copy, not Opt::Opt()
    assert _targets(g, "a.cc::user") == set(), _targets(g, "a.cc::user")


def test_a_copy_or_move_of_the_same_type_is_not_a_call_to_a_one_argument_constructor(tmp_path):
    files = {"a.cc": ("class T {\n public:\n  T(int v);\n};\nT::T(int v) {}\n"
                      "void user(const T& other, T* p) { T copy(other); T moved(std::move(other)); T real(3); }\n")}
    es = [e for e in S.build(tmp_path, files).edges("CALLS") if e.src == "a.cc::user"]
    assert len(es) == 1 and es[0].source == "cpp-constructor", [(e.dst, e.source) for e in es]      # only `T real(3)`


def test_a_member_copied_or_moved_from_a_same_typed_argument_is_not_a_constructor_call(tmp_path):
    files = {"a.cc": ("class Cmp {\n public:\n  Cmp(const char* name);\n};\nCmp::Cmp(const char* name) {}\n"
                      "class A {\n public:\n  A(const Cmp& c) : cmp_(c) {}\n  A(const Cmp* p) : cmp_(*p) {}\n  A(Cmp&& m) : cmp_(std::move(m)) {}\n"
                      "  A(const char* n) : cmp_(n) {}\n  Cmp cmp_;\n};\n")}
    g = S.build(tmp_path, files)
    es = {(e.src, e.dst) for e in g.edges("CALLS") if e.source == "cpp-constructor"}
    assert es == {("a.cc::A.A", "a.cc::Cmp.Cmp")}, es      # only `cmp_(n)`; one node A.A stands for the four constructors
    assert len([1 for e in g.edges("CALLS") if e.source == "cpp-constructor"]) == 1


def test_a_default_initialised_local_links_to_a_declared_default_constructor_only(tmp_path):
    files = {"a.cc": ("class D {\n public:\n  D();\n  D(int v);\n};\nD::D() {}\nD::D(int v) {}\n"
                      "class OnlyArg {\n public:\n  OnlyArg(int v);\n};\nOnlyArg::OnlyArg(int v) {}\n"
                      "void user() { D d; extern D shared; }\nvoid user2() { OnlyArg a(1); }\n")}
    g = S.build(tmp_path, files)
    assert _targets(g, "a.cc::user") == {"a.cc::D.D"}, _targets(g, "a.cc::user")
    assert _targets(g, "a.cc::user2") == {"a.cc::OnlyArg.OnlyArg"}
