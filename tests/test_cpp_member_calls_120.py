"""#120 (SPEC-DKB-004 F4, F5): C++ member calls resolve through the receiver types an agent reads off the page, TEST_F
fixtures and argument counts; an undecidable receiver gets no edge.

Fixture code is synthetic."""
from __future__ import annotations

import cpp_support as S

HDR = ("#include <memory>\n"
       "namespace app {\n"
       "class Widget {\n public:\n  int Draw(int x);\n  Widget* Self();\n};\n"
       "class Gadget {\n public:\n  int Spin(int x);\n  int Spin(int x, int y) const;\n};\n"
       "class Other {\n public:\n  int Spin(int x, int y, int z);\n};\n"
       "class Holder {\n public:\n  int Use();\n  Widget& Get();\n private:\n  std::unique_ptr<Widget> owned_;\n  Gadget* gadget_;\n};\n"
       "}  // namespace app\n")
SRC = ("#include \"w.h\"\n"
       "namespace app {\n"
       "int Widget::Draw(int x) { return x; }\n"
       "Widget* Widget::Self() { return this; }\n"
       "int Gadget::Spin(int x) { return x; }\n"
       "int Gadget::Spin(int x, int y) const { return x + y; }\n"
       "int Other::Spin(int x, int y, int z) { return x + y + z; }\n"
       "Widget& Holder::Get() { return *owned_; }\n"
       "int Holder::Use() { return owned_->Draw(1) + gadget_->Spin(1); }\n"
       "int use_auto_ctor() { auto w = Widget(); return w.Draw(2); }\n"
       "int use_auto_new() { auto w = new Widget(); return w->Draw(3); }\n"
       "int use_make() { auto w = std::make_unique<Widget>(); return w->Draw(4); }\n"
       "int use_smart(std::shared_ptr<Widget> w) { return w->Draw(5); }\n"
       "int use_ref(Widget& w) { return w.Draw(6); }\n"
       "int use_chain(Holder& h) { return h.Get().Draw(7); }\n"
       "int use_chain_self(Widget* w) { return w->Self()->Draw(8); }\n"
       "int use_unknown(auto&& thing) { return thing.Draw(9); }\n"
       "int use_auto_unknown() { auto w = Factory(); return w.Draw(10); }\n"
       "}  // namespace app\n")
TEST = ("#include \"w.h\"\n"
        "namespace app {\n"
        "class WidgetTest : public testing::Test {\n public:\n  void Add(int x) { n_ += x; }\n  int n_ = 0;\n};\n"
        "TEST_F(WidgetTest, Small) {\n  Add(1);\n  Add(2);\n}\n"
        "}  // namespace app\n")


def _calls(tmp_path):
    g = S.build(tmp_path, {"src/w.h": HDR, "src/w.cc": SRC, "src/w_test.cc": TEST})
    return {(e.src.split("::")[-1], e.dst.split("::")[-1]) for e in g.edges("CALLS") if e.source.startswith("cpp-")}


def test_auto_new_make_unique_and_smart_pointers_give_the_receiver_type(tmp_path):
    c = _calls(tmp_path)
    for caller in ("use_auto_ctor", "use_auto_new", "use_make", "use_smart", "use_ref"):
        assert (f"app.{caller}", "app.Widget.Draw") in c or (caller, "Widget.Draw") in c or any(
            a.endswith(caller) and b.endswith("Widget.Draw") for a, b in c), (caller, sorted(c))


def test_members_declared_in_the_class_header_give_the_receiver_type(tmp_path):
    c = _calls(tmp_path)
    assert any(a.endswith("Holder.Use") and b.endswith("Widget.Draw") for a, b in c)       # std::unique_ptr<Widget> owned_
    assert any(a.endswith("Holder.Use") and b.endswith("Gadget.Spin") for a, b in c)       # Gadget* gadget_


def test_one_level_of_chaining_through_a_declared_return_type(tmp_path):
    c = _calls(tmp_path)
    assert any(a.endswith("use_chain") and b.endswith("Widget.Draw") for a, b in c)
    assert any(a.endswith("use_chain_self") and b.endswith("Widget.Draw") for a, b in c)


def test_a_test_f_body_calls_its_fixtures_methods(tmp_path):
    c = _calls(tmp_path)
    assert any("Small" in a and b.endswith("WidgetTest.Add") for a, b in c), sorted(c)


def test_an_undecidable_receiver_gets_no_edge(tmp_path):
    c = _calls(tmp_path)
    assert not any(a.endswith(("use_unknown", "use_auto_unknown")) for a, _b in c)


def test_same_named_free_functions_are_narrowed_by_argument_count(tmp_path):
    # one name in two namespaces with two arities; a bare call with two arguments from another file picks b::spin_free
    files = {"src/t.cc": ("namespace a { int spin_free(int x) { return x; } }\nnamespace b { int spin_free(int x, int y) { return x; } }\n"),
             "src/u.cc": "int spin_free(int, int);\nint drive2() { return spin_free(1, 2); }\n"}
    g = S.build(tmp_path, files)
    c = {(e.src.split("::")[-1], e.dst) for e in g.edges("CALLS") if e.source.startswith("cpp-")}
    assert any(a == "drive2" and d.endswith("b.spin_free") for a, d in c), sorted(c)


def test_a_member_of_a_typed_receiver_and_an_annotated_member_give_the_type(tmp_path):
    files = {"src/k.h": ("class Widget {\n public:\n  int Draw(int x);\n};\n"
                         "struct Box {\n  Widget inner;\n  Widget* ptr;\n};\n"
                         "class Owner {\n public:\n  int Run();\n private:\n  Widget* const w_ GUARDED_BY(mu_);\n  int mu_;\n};\n"),
             "src/k.cc": ("#include \"k.h\"\nint Widget::Draw(int x) { return x; }\n"
                          "int use_field(Box& b) { return b.inner.Draw(1); }\n"
                          "int use_field_ptr(Box* b) { return b->ptr->Draw(2); }\n"
                          "int Owner::Run() { return w_->Draw(3); }\n")}
    g = S.build(tmp_path, files)
    c = {(e.src.split("::")[-1], e.dst.split("::")[-1]) for e in g.edges("CALLS") if e.source.startswith("cpp-")}
    for caller in ("use_field", "use_field_ptr", "Owner.Run"):
        assert (caller, "Widget.Draw") in c, (caller, sorted(c))
