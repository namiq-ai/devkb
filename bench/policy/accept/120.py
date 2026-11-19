"""#120 (SPEC-DKB-004 F4, F5) on a finished checkout: C++ member calls resolve through receiver types read off the page,
TEST_F fixtures and argument counts; an undecidable receiver gets no edge.

With the checkout's own devkb (`devkb build`), read from the built graph's CALLS edges, on a fixture (src/w.h, src/w.cc,
src/w_test.cc, and a second repository for arity):
- `auto_and_smart`: `auto w = Widget()`, `auto w = new Widget()`, `auto w = std::make_unique<Widget>()`,
  `std::shared_ptr<Widget> w`, `Widget& w`: each `w.Draw()` / `w->Draw()` links to Widget::Draw;
- `header_members`: `owned_->Draw()` (`std::unique_ptr<Widget> owned_;`) and `gadget_->Spin()` (`Gadget* gadget_;`) in
  Holder::Use link to Widget::Draw and Gadget::Spin;
- `one_chain`: `h.Get().Draw()` (Get returns `Widget&`) and `w->Self()->Draw()` link to Widget::Draw;
- `test_f`: `Add(1)` in `TEST_F(WidgetTest, Small)` links to WidgetTest::Add;
- `undecidable`: `thing.Draw()` (`auto&& thing`) and `auto w = Factory(); w.Draw()` get no edge;
- `arity`: `spin_free(1, 2)` with `a::spin_free(int)` and `b::spin_free(int, int)` links to b::spin_free.
"""
import json, os, subprocess, sys, tempfile
from pathlib import Path

W = Path(sys.argv[1]).resolve()
PY = str(W / ".venv" / "bin" / "python")
ENV = dict(os.environ, PYTHONPATH=str(W), PYTHONWARNINGS="ignore")
HDR = '#include <memory>\nnamespace app {\nclass Widget {\n public:\n  int Draw(int x);\n  Widget* Self();\n};\nclass Gadget {\n public:\n  int Spin(int x);\n  int Spin(int x, int y) const;\n};\nclass Other {\n public:\n  int Spin(int x, int y, int z);\n};\nclass Holder {\n public:\n  int Use();\n  Widget& Get();\n private:\n  std::unique_ptr<Widget> owned_;\n  Gadget* gadget_;\n};\n}  // namespace app\n'
SRC = '#include "w.h"\nnamespace app {\nint Widget::Draw(int x) { return x; }\nWidget* Widget::Self() { return this; }\nint Gadget::Spin(int x) { return x; }\nint Gadget::Spin(int x, int y) const { return x + y; }\nint Other::Spin(int x, int y, int z) { return x + y + z; }\nWidget& Holder::Get() { return *owned_; }\nint Holder::Use() { return owned_->Draw(1) + gadget_->Spin(1); }\nint use_auto_ctor() { auto w = Widget(); return w.Draw(2); }\nint use_auto_new() { auto w = new Widget(); return w->Draw(3); }\nint use_make() { auto w = std::make_unique<Widget>(); return w->Draw(4); }\nint use_smart(std::shared_ptr<Widget> w) { return w->Draw(5); }\nint use_ref(Widget& w) { return w.Draw(6); }\nint use_chain(Holder& h) { return h.Get().Draw(7); }\nint use_chain_self(Widget* w) { return w->Self()->Draw(8); }\nint use_unknown(auto&& thing) { return thing.Draw(9); }\nint use_auto_unknown() { auto w = Factory(); return w.Draw(10); }\n}  // namespace app\n'
TEST = '#include "w.h"\nnamespace app {\nclass WidgetTest : public testing::Test {\n public:\n  void Add(int x) { n_ += x; }\n  int n_ = 0;\n};\nTEST_F(WidgetTest, Small) {\n  Add(1);\n  Add(2);\n}\n}  // namespace app\n'
ARITY = {"src/t.cc": "namespace a { int spin_free(int x) { return x; } }\nnamespace b { int spin_free(int x, int y) { return x; } }\n",
         "src/u.cc": "int spin_free(int, int);\nint drive2() { return spin_free(1, 2); }\n"}


def build(root, files):
    for rel, text in files.items():
        (root / rel).parent.mkdir(parents=True, exist_ok=True)
        (root / rel).write_text(text)
    subprocess.run("git init -q . && git add -A && git -c user.email=a@example.com -c user.name=a commit -qm i", shell=True, cwd=root, check=True)
    subprocess.run([PY, "-P", "-m", "devkb.cli", "build", "--project", str(root)], cwd=W, env=ENV, capture_output=True, timeout=600)
    name, edges = {}, set()
    store = root / ".devkb"
    for line in ((store / "nodes.jsonl").read_text().splitlines() if (store / "nodes.jsonl").exists() else []):
        n = json.loads(line)
        name[n["uid"]] = n["natural_key"].split("::", 1)[-1]
    for line in ((store / "edges.jsonl").read_text().splitlines() if (store / "edges.jsonl").exists() else []):
        e = json.loads(line)
        if e.get("verb") == "CALLS":
            edges.add((name.get(e["from_uid"], ""), name.get(e["to_uid"], "")))
    return edges


def has(edges, caller, callee):
    return any(a.endswith(caller) and b.endswith(callee) for a, b in edges)


out = {}
with tempfile.TemporaryDirectory() as td:
    e = build(Path(td) / "a", {"src/w.h": HDR, "src/w.cc": SRC, "src/w_test.cc": TEST})
    out["auto_and_smart"] = all(has(e, c, "Widget.Draw") for c in ("use_auto_ctor", "use_auto_new", "use_make", "use_smart", "use_ref"))
    out["header_members"] = has(e, "Holder.Use", "Widget.Draw") and has(e, "Holder.Use", "Gadget.Spin")
    out["one_chain"] = has(e, "use_chain", "Widget.Draw") and has(e, "use_chain_self", "Widget.Draw")
    out["test_f"] = any("Small" in a and b.endswith("WidgetTest.Add") for a, b in e)
    out["undecidable"] = not any(a.endswith(("use_unknown", "use_auto_unknown")) for a, _b in e)
    e2 = build(Path(td) / "b", ARITY)
    out["arity"] = has(e2, "drive2", "b.spin_free")
out["pass"] = all(out.values())
print(json.dumps(out))
