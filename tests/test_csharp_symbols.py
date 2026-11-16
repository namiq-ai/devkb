"""C# support (#32, SPEC-DEVKB-CSHARP): definitions, calls and tests from `.cs` files, standard library only."""
from __future__ import annotations

import json
import subprocess
from pathlib import Path

from devkb import build_symbols, csharp_symbols, process_api, test_discovery
from devkb.packs import Packer
from devkb.project_context import ProjectContext

SHAPES = '''\ufeffnamespace Shop.Core;

public interface IStore
{
    Order Load(int id);
}

public record Money(decimal Amount, string Currency);

public enum Status { Open, Closed }

public struct Point { public int X; public int Y; }

public class Order
{
    public int Id { get; set; }
    public string Label => $"order {{ {Id} }}";          // braces inside an interpolated string
    private const string Raw = """ { not a scope } """;
    private static readonly string Path = @"C:\\temp\\{x}";
    public Order(int id) : this(id, "none") { }
    public Order(int id, string note) { Id = id; Validate(); }
    public void Validate() { var t = Total(); }
    public decimal Total() => Sum(1) + Sum(1, 2);
    public decimal Sum(int a) => a;
    public decimal Sum(int a, int b) => a + b;
    private static (int Count, decimal Total) Totals(int n) => (n, Sum(n));
    public string Describe()
    {
        string Format(int n) => n.ToString();               // a local function: its declaration is not a call
        return Format(Id) + Helpers.Shout("x");
    }
}

public class Box<T> where T : class
{
    public T Item { get { return Make(); } }
    private T Make() => default;
    public class Inner { public void Touch() { } }
}
'''

SERVICES = '''namespace Shop.Services
{
    using Shop.Core;

    public static class Helpers
    {
        public static string Shout(string s) => s.ToUpper();
        public static int Double(this int n) => n * 2;
    }

    public class OrderService
    {
        private readonly IStore _store;
        public OrderService(IStore store) { _store = store; }

        public Order Get(int id)
        {
            var order = _store.Load(id);
            order.Validate();
            var fresh = new Order(id);
            fresh.Validate();
            this.Audit();
            int twice = id.Double();
            return order;
        }

        private void Audit() { }
    }
}
'''

XUNIT = '''namespace Shop.Tests;

using Shop.Core;
using Shop.Services;
using Xunit;

public class OrderServiceTests
{
    [Fact]
    public void Get_validates()
    {
        var service = new OrderService(null);
        service.Get(1);
    }

    [Theory]
    [InlineData(1)]
    public void Total_adds(int n)
    {
        var o = new Order(n);
        o.Total();
    }

    public class Ping { }                                  // a type nested in the test class shadows any other Ping

    [Fact]
    public void Uses_nested_ping() { var p = new Ping(); }
}
'''

NUNIT_MSTEST = '''namespace Shop.Tests.Other
{
    using NUnit.Framework;
    using Microsoft.VisualStudio.TestTools.UnitTesting;

    public class NUnitStyle
    {
        [Test] public void One() { }
        [TestCase(2)] public void Two(int x) { }
    }

    [TestClass]
    public class MsTestStyle
    {
        [TestMethod] public void Three() { }
        [DataTestMethod] public void Four() { }
        public void NotATest() { }
    }
}
'''

OTHER_PING = '''namespace Elsewhere;

public class Ping { }
'''


def _repo(tmp_path: Path) -> Path:
    files = {"src/Shop.Core/Order.cs": SHAPES, "src/Shop.Services/OrderService.cs": SERVICES,
             "tests/Shop.Tests/OrderServiceTests.cs": XUNIT, "tests/Shop.Tests/OtherFrameworks.cs": NUNIT_MSTEST,
             "src/Elsewhere/Ping.cs": OTHER_PING, "src/Shop.Core/obj/Debug/Gen.g.cs": "class Generated { }"}
    for rel, text in files.items():
        (tmp_path / rel).parent.mkdir(parents=True, exist_ok=True)
        (tmp_path / rel).write_text(text)
    for cmd in (["init", "-q"], ["add", "-A", "-f"], ["-c", "user.email=t@example.com", "-c", "user.name=T", "commit", "-qm", "x"]):
        subprocess.run(["git", *cmd], cwd=tmp_path, check=True)
    return tmp_path


def _short(key: str) -> str:
    return key.split("::", 1)[1]


def test_definitions_of_every_shape(tmp_path):
    symbols, _ = csharp_symbols.extract(_repo(tmp_path))
    found = {(_short(s["key"]), s["kind"]) for s in symbols}
    for expected in [("Shop.Core.IStore", "class"), ("Shop.Core.IStore.Load", "method"), ("Shop.Core.Money", "class"),
                     ("Shop.Core.Status", "enum"), ("Shop.Core.Point", "class"), ("Shop.Core.Order", "class"),
                     ("Shop.Core.Order.Id", "method"), ("Shop.Core.Order.Label", "method"),
                     ("Shop.Core.Order.ctor", "method"), ("Shop.Core.Order.Sum", "method"), ("Shop.Core.Order.Totals", "method"),
                     ("Shop.Core.Order.Describe.Format", "function"), ("Shop.Core.Box", "class"),
                     ("Shop.Core.Box.Item", "method"), ("Shop.Core.Box.Inner.Touch", "method"),
                     ("Shop.Services.Helpers.Double", "method"), ("Shop.Services.OrderService.Get", "method")]:
        assert expected in found, expected
    assert not any("Generated" in s["key"] for s in symbols), "generated files under obj/ are skipped"
    assert not any(_short(s["key"]).startswith("Shop.Core.Order.Raw") for s in symbols)
    assert not any(s["name"] in ("static", "private", "public") for s in symbols), "a tuple return type is not a name"


def test_calls_resolve_only_where_one_target_fits(tmp_path):
    _, calls = csharp_symbols.extract(_repo(tmp_path))
    pairs = {(_short(c["caller"]), _short(c["callee"])) for c in calls}
    expected = {
        ("Shop.Core.Order.ctor", "Shop.Core.Order.Validate"),                 # bare call in the same type
        ("Shop.Core.Order.Validate", "Shop.Core.Order.Total"),
        ("Shop.Core.Order.Total", "Shop.Core.Order.Sum"),                     # overloads share one key
        ("Shop.Core.Order.Describe", "Shop.Core.Order.Describe.Format"),     # a local function
        ("Shop.Core.Order.Describe", "Shop.Services.Helpers.Shout"),          # `Type.Member(...)`, a static call
        ("Shop.Core.Box.Item", "Shop.Core.Box.Make"),                         # inside a property accessor
        ("Shop.Services.OrderService.Get", "Shop.Core.IStore.Load"),          # receiver typed by a field
        ("Shop.Services.OrderService.Get", "Shop.Core.Order.Validate"),       # `var x = _store.Load()` unknown, `new` known
        ("Shop.Services.OrderService.Get", "Shop.Core.Order.ctor"),           # `new Order(...)`
        ("Shop.Services.OrderService.Get", "Shop.Services.OrderService.Audit"),  # `this.Audit()`
        ("Shop.Services.OrderService.Get", "Shop.Services.Helpers.Double"),   # the only extension method so named
        ("Shop.Tests.OrderServiceTests.Get_validates", "Shop.Services.OrderService.Get"),
        ("Shop.Tests.OrderServiceTests.Total_adds", "Shop.Core.Order.Total"),
        ("Shop.Tests.OrderServiceTests.Uses_nested_ping", "Shop.Tests.OrderServiceTests.Ping"),
    }
    missing = expected - pairs
    assert not missing, missing
    assert ("Shop.Tests.OrderServiceTests.Uses_nested_ping", "Elsewhere.Ping") not in pairs, "the nested Ping wins"
    format_calls = [c for c in calls if _short(c["callee"]) == "Shop.Core.Order.Describe.Format"]
    assert all(":31:" not in f"{c['rel']}:{c['line']}:" for c in format_calls), "the declaration line is not a call"


def test_strings_with_braces_do_not_break_the_scope(tmp_path):
    root = _repo(tmp_path)
    masked = csharp_symbols.mask((root / "src/Shop.Core/Order.cs").read_text())
    assert "not a scope" not in masked and "order" not in masked.split("Label", 1)[1].split(";", 1)[0]
    assert masked.count("{") == masked.count("}")


def test_tests_are_found_by_attribute_and_project(tmp_path):
    root = _repo(tmp_path)
    files = test_discovery.list_test_files(root)
    assert "tests/Shop.Tests/OrderServiceTests.cs" in files and "src/Shop.Core/Order.cs" not in files
    names = {n for n, _ in test_discovery.tests_in_file(root, "tests/Shop.Tests/OrderServiceTests.cs")}
    assert names == {"Get_validates", "Total_adds", "Uses_nested_ping"}
    other = {n for n, _ in test_discovery.tests_in_file(root, "tests/Shop.Tests/OtherFrameworks.cs")}
    assert other == {"One", "Two", "Three", "Four"}
    assert process_api.is_test_path("tests/Shop.Tests/OrderServiceTests.cs")
    assert process_api.is_test_path("src/Shop.Tests/Anything.cs") and process_api.is_test_path("src/Core/OrderTests.cs")
    assert not process_api.is_test_path("src/Shop.Core/Order.cs")


def test_the_graph_and_a_pack_answer_for_csharp(tmp_path, monkeypatch):
    root = _repo(tmp_path)
    g = build_symbols.extract(root)
    store = root / ".devkb"
    store.mkdir()
    d = g.to_dict()
    (store / "nodes.jsonl").write_text("\n".join(json.dumps(n) for n in d["nodes"]) + "\n")
    (store / "edges.jsonl").write_text("\n".join(json.dumps(e) for e in d["edges"]) + "\n")
    head = subprocess.run(["git", "rev-parse", "HEAD"], cwd=root, capture_output=True, text=True).stdout.strip()
    (store / "manifest.json").write_text(json.dumps({"built_at": "2026-11-16T00:00:00+00:00", "git_head": head}))
    ctx = ProjectContext(code="CS", repo_root=root, ticket_prefix="CS", issues_dir=root / "issues", tests_dir=root / "tests",
                         sprint_dir=root / "h", devkb_dir=store, board_file=root / "b.md", wp_map_file=root / "w.json")
    monkeypatch.setattr(process_api, "resolve", lambda code: ctx)
    pack = Packer(process_api.ProcessAPI("CS", telemetry=False)).refactor("Get", path="src/Shop.Services/OrderService.cs")
    assert "tests/Shop.Tests/OrderServiceTests.cs" in pack.split("## Test files among them")[1]
    assert "OrderServiceTests.cs:13:" in pack, "each caller carries its proof line"


def test_a_chained_call_split_over_lines_carries_the_line_of_its_name(tmp_path):
    (tmp_path / "A.cs").write_text("namespace N;\npublic static class P { public static P Handle() => null; }\n"
                                   "public class C {\n  void M() {\n    var x = P\n        .Handle();\n  }\n}\n")
    _, calls = csharp_symbols.extract(_repo(tmp_path))
    hit = [c for c in calls if c["callee"].endswith("N.P.Handle")]
    assert hit and hit[0]["line"] == 6


# ── round 2 (SPEC-DEVKB-CSHARP-2): a call goes only to a method that can accept it ─────────────────────────────

ROUND2 = '''namespace R2;

using System;
using System.Collections.Generic;

public interface IProp { Type ClrType { get; } }
public interface IEntity { void FindProperty(int id); }
public class TypeBase { public virtual void FindProperty(string name) { } }
public class Entity : TypeBase, IEntity { }                        // class base first: TypeBase.FindProperty wins

public static class PropExtensions
{
    public static object Default(this IProp property) => null;
}

public static class TypeExtensions
{
    public static object Default(
        [Marker(typeof(int))]
        this Type type) => null;                                   // an attribute before `this`: still an extension
}

public static class ListExtensions
{
    public static T First<T>(this IReadOnlyList<T> source) => default;   // no predicate
}

public class Store
{
    public void Put(int a, int b) { }
}

public class Use
{
    public void Run(IProp prop, Entity entity, IReadOnlyList<int> list, Store store, Type t)
    {
        prop.Default();                                            // -> PropExtensions.Default (this IProp)
        t.Default();                                               // -> TypeExtensions.Default (this Type)
        entity.FindProperty("x");                                  // -> TypeBase.FindProperty
        list.First();                                              // -> ListExtensions.First
        list.First(x => x > 1);                                    // LINQ's First(predicate): no edge
        store.Put(1);                                              // no overload takes one argument: no edge
        store.Put(1, 2);                                           // -> Store.Put
    }
}
'''


def _round2(tmp_path):
    (tmp_path / "R2.cs").write_text(ROUND2)
    syms, calls = csharp_symbols.extract(_repo(tmp_path))
    lines = ROUND2.splitlines()
    by_line = {}
    for c in calls:
        if c["rel"] == "R2.cs":
            by_line.setdefault(lines[c["line"] - 1].strip().split(";")[0], set()).add(_short(c["callee"]))
    return syms, by_line


def test_an_attribute_before_this_does_not_hide_an_extension(tmp_path):
    syms, _ = _round2(tmp_path)
    td = [s for s in syms if s["key"].endswith("R2.TypeExtensions.Default")]
    assert td and td[0]["ext"] and td[0]["this_type"] == "Type"


def test_extensions_are_chosen_by_receiver_type(tmp_path):
    _, by_line = _round2(tmp_path)
    assert by_line["prop.Default()"] == {"R2.PropExtensions.Default"}
    assert by_line["t.Default()"] == {"R2.TypeExtensions.Default"}


def test_the_class_base_is_searched_before_an_interface(tmp_path):
    _, by_line = _round2(tmp_path)
    assert by_line['entity.FindProperty("x")'] == {"R2.TypeBase.FindProperty"}


def test_a_call_no_overload_accepts_gets_no_edge(tmp_path):
    _, by_line = _round2(tmp_path)
    assert by_line["list.First()"] == {"R2.ListExtensions.First"}
    assert "list.First(x => x > 1)" not in by_line, "a predicate means LINQ, not the parameterless extension"
    assert "store.Put(1)" not in by_line and by_line["store.Put(1, 2)"] == {"R2.Store.Put"}


def test_argument_counting():
    cases = {"f()": 0, "f(a)": 1, "f((a))": 1, 'f("x")': 1, 'f(a, "x,y")': 2, "f(x => { g(1, 2); })": 1,
             "f(new[] { a, b }, c)": 2, "f(a < b, c)": None, "f(new List<int>(), 1)": None, "f(/*c*/)": 0}
    for text, n in cases.items():
        assert csharp_symbols._arg_count(csharp_symbols.mask(text), text, 1) == n, text
    assert csharp_symbols._arity("int a, int b = 2, params object[] rest", False) == (1, None)
    assert csharp_symbols._arity("this IFoo x, int a", True) == (1, 1)


ROUND2B = '''namespace R2b;

public interface IHasIds { }
public class A0 : IHasIds { }
''' + "".join(f"public class A{i} : A{i - 1}, IX{i} {{ }}\npublic interface IX{i} {{ }}\n" for i in range(1, 40)) + '''
public static class IdExtensions
{
    public static void SetId(this IHasIds item, string v) { }
    public static string Twice(this string s) => s + s;
    public static string Twice(this string s, int times) => s;
}

public static class Paths
{
    public static string Attr(this string s, string a) => s;
    public static string Use(string p) => Attr(p, "x");          // an extension called by name: `this` passed
}

public class Painter
{
    public void Paint(A39 deep, string p)
    {
        deep.SetId("x");                                          // 40 levels up to IHasIds
        Paths.Attr(p, "y");                                       // an extension called statically
        using var w = new Painter();
        w.Paint(deep, p);
    }
    public void Dispose() { }
}
'''


def test_wide_hierarchies_static_extension_calls_and_using_var(tmp_path):
    (tmp_path / "R2b.cs").write_text(ROUND2B)
    _, calls = csharp_symbols.extract(_repo(tmp_path))
    pairs = {(_short(c["caller"]), _short(c["callee"])) for c in calls}
    assert ("R2b.Painter.Paint", "R2b.IdExtensions.SetId") in pairs
    assert ("R2b.Painter.Paint", "R2b.Paths.Attr") in pairs
    assert ("R2b.Paths.Use", "R2b.Paths.Attr") in pairs
    assert csharp_symbols._locals("using var w = new Painter();") == {"w": "Painter"}


def test_this_object_extensions_and_this_dot_field(tmp_path):
    (tmp_path / "R2c.cs").write_text('''namespace R2c;
public static class Should { public static void ShouldEqual(this object actual, object expected) { } }
public class V { public void Check(int x) { } }
public class T
{
    private V v;
    public void Run(string s, V w) { w.ShouldEqual("a"); this.v.Check(1); }
    public void Outside(string s) { s.ShouldEqual("a"); }
}
''')
    _, calls = csharp_symbols.extract(_repo(tmp_path))
    pairs = {(_short(c["caller"]), _short(c["callee"])) for c in calls}
    assert ("R2c.T.Run", "R2c.Should.ShouldEqual") in pairs, "a repository receiver without that member: the extension"
    assert ("R2c.T.Outside", "R2c.Should.ShouldEqual") in pairs, "no repository method is named ShouldEqual"
    assert ("R2c.T.Run", "R2c.V.Check") in pairs


def test_a_member_that_fits_ambiguously_is_not_replaced_by_an_extension(tmp_path):
    (tmp_path / "P1.cs").write_text("namespace P;\npublic partial class Pol { public void Run(int a) { } }\n")
    (tmp_path / "P2.cs").write_text("namespace P;\npublic partial class Pol { public void Run(string a) { } }\n")
    (tmp_path / "H.cs").write_text('''namespace P;
public static class Helper { public static void Run(this object o, int v) { } }
public class Bench { public static Pol Pol { get; } = new Pol(); public void Go(System.Net.Http.HttpClient c) { Pol.Run(1); c.Run(2); } }
''')
    _, calls = csharp_symbols.extract(_repo(tmp_path))
    assert not [c for c in calls if c["callee"].endswith("P.Helper.Run")], (
        "Pol.Run fits a member: never the extension; c.Run on an outside type: `Run` is also a repository method")
