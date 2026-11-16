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


# ── round 3 (SPEC-DEVKB-CSHARP-3): typed expressions ─────────────────────────────────────────────────────────

ROUND3 = '''namespace R3;

using System;
using System.Collections.Generic;
using System.IO;
using System.Linq.Expressions;
using System.Threading;
using System.Threading.Tasks;

public class Order { public void Ship() { } public Customer Owner { get; set; } }
public class Customer { public void Notify() { } }
public class Builder
{
    public Builder Named(string n) => this;
    public Order Build() => new Order();
}
public class Repo
{
    public Builder Start() => new Builder();
    public Task<Order> LoadAsync(int id) => null;
    public IReadOnlyList<Order> All() => null;
    public Order Find(int id) => null;
}
public class Config { public void Enable() { } }
public class Model { public string Name { get; set; } }
public static class Setup
{
    public static void Configure(this Repo repo, Action<Config> configure) { }
    public static void Map(this Repo repo, Expression<Func<Model, string>> pick) { }
    public static string Head(this TextReader reader) => null;
    public static int IndexOf(this IReadOnlyList<Order> orders, Order o) => 0;
}
public class Finder { public Order Find(string key) => null; }
public class Token { public void Run(CancellationToken ct) { } }
public static class TokenExt { public static void Run(this Token t, Action work) { } }

public class Use
{
    private readonly Repo _repo = new Repo();

    public async Task Go(Repo repo, StreamReader reader, List<Order> list, Finder finder, Token tok)
    {
        repo.Start()
            .Named("x")
            .Build()
            .Ship();                                     // chained over lines: Start -> Named -> Build -> Ship
        (await repo.LoadAsync(1)).Ship();                // awaited result
        var o = repo.Find(2);
        o.Ship();                                        // var from a call
        var later = await repo.LoadAsync(3).ConfigureAwait(false);
        later.Ship();                                    // var from an awaited call
        foreach (var each in repo.All()) { each.Ship(); }  // foreach element
        o.Owner.Notify();                                // property chain
        _repo.Find(4).Owner.Notify();                    // call result, then a property
        repo.Configure(c => c.Enable());                 // lambda parameter from Action<Config>
        repo.Map(m => m.Name);                           // Expression<Func<Model, string>>
        reader.Head();                                   // StreamReader is a TextReader (.NET table)
        list.IndexOf(o);                                 // List<T> has its own IndexOf: never the extension
        finder.Find("k");                                // a string literal: Finder.Find(string)
        tok.Run(() => { });                              // a lambda cannot be a CancellationToken: the extension
    }
}
'''


def _round3(tmp_path):
    """{source line: callees resolved on it}, per call site (extract() keeps one edge per caller and callee)."""
    sc = csharp_symbols.scan_file("R3.cs", ROUND3)
    for x in sc["symbols"]:
        x["rel"], x["key"] = "R3.cs", "R3.cs::" + ".".join(x["qparts"])
    index = csharp_symbols._Index(sc["symbols"])
    go = next(x for x in sc["symbols"] if x["name"] == "Go")
    lines = ROUND3.splitlines()
    got = {}
    for callee, _conf, line, _text, _why in csharp_symbols._calls_in(go, sc["masked"], sc["nl"], index, {}, sc["raw"]):
        if callee is not None:
            got.setdefault(lines[line - 1].split("//")[0].strip(), set()).add(".".join(callee["qparts"]))
    return got


def test_calls_on_call_results_are_typed(tmp_path):
    got = _round3(tmp_path)
    assert got['.Named("x")'] == {"R3.Builder.Named"}
    assert got[".Build()"] == {"R3.Builder.Build"}
    assert got[".Ship();"] == {"R3.Order.Ship"}
    assert "R3.Order.Ship" in got["(await repo.LoadAsync(1)).Ship();"]
    assert "R3.Order.Ship" in got["o.Ship();"]
    assert "R3.Order.Ship" in got["later.Ship();"]
    assert "R3.Order.Ship" in got["foreach (var each in repo.All()) { each.Ship(); }"]


def test_property_chains_and_lambda_parameters_are_typed(tmp_path):
    got = _round3(tmp_path)
    assert "R3.Customer.Notify" in got["o.Owner.Notify();"]
    assert "R3.Customer.Notify" in got["_repo.Find(4).Owner.Notify();"]
    assert "R3.Config.Enable" in got["repo.Configure(c => c.Enable());"]


def test_dotnet_hierarchies_and_members(tmp_path):
    got = _round3(tmp_path)
    assert got["reader.Head();"] == {"R3.Setup.Head"}, "StreamReader derives from TextReader"
    assert "list.IndexOf(o);" not in got, "List<T>.IndexOf is List's own"


def test_argument_types_rule_candidates_out(tmp_path):
    got = _round3(tmp_path)
    assert got['finder.Find("k");'] == {"R3.Finder.Find"}
    assert got["tok.Run(() => { });"] == {"R3.TokenExt.Run"}, "a lambda is not a CancellationToken"


def test_an_expression_bodied_member_with_braces_in_its_expression_is_a_member(tmp_path):
    (tmp_path / "E.cs").write_text('''namespace E;
public class Opts { public int A { get; set; } }
public static class Ext
{
    public static Opts Make(this string s, int a) => Build(new Opts
    {
        A = a
    });
    public static Opts Build(Opts o) => o;
    public static int After() => 1;                       // the type-level scan continues normally after it
}
''')
    syms, calls = csharp_symbols.extract(_repo(tmp_path))
    names = {_short(s["key"]) for s in syms}
    assert {"E.Ext.Make", "E.Ext.Build", "E.Ext.After"} <= names
    make = next(s for s in syms if s["name"] == "Make")
    assert make["ext"] and (make["line_start"], make["line_end"]) == (5, 8)
    assert ("E.Ext.Make", "E.Ext.Build") in {(_short(c["caller"]), _short(c["callee"])) for c in calls}


def test_using_aliases_lambda_shadowing_and_invisible_receivers(tmp_path):
    (tmp_path / "A.cs").write_text('''namespace A;
using Dto = A.Item;
using System.Linq;
public class Item { }
public class Movie : Item { }
public class Service { public void Save(Dto item) { } }
public static class Q { public static int Pick<T>(this System.Linq.IQueryable<T> q, int n) => n; }
public class Use
{
    public void Go(Service svc, Microsoft.EntityFrameworkCore.DbSet<Item> set, int[] xs)
    {
        svc.Save(new Movie());                       // `Dto` is an alias of Item; a Movie is an Item
        int i = 0;
        xs.Select(i => Twice(i)).ToList();          // the lambda's `i` is not the outer int
        set.Pick(1);                                 // DbSet<T> is an IQueryable<T> (table)
    }
    private int Twice(object o) => 0;
}
''')
    _, calls = csharp_symbols.extract(_repo(tmp_path))
    pairs = {(_short(c["caller"]), _short(c["callee"])) for c in calls}
    assert ("A.Use.Go", "A.Service.Save") in pairs, "alias resolved before the type check"
    assert ("A.Use.Go", "A.Use.Twice") in pairs
    assert ("A.Use.Go", "A.Q.Pick") in pairs


def test_arrays_take_list_extensions_and_spans_accept_arrays(tmp_path):
    (tmp_path / "S.cs").write_text('''namespace S;
using System;
using System.Collections.Generic;
public static class L { public static int IndexOf<T>(this IReadOnlyList<T> xs, T x) => 0; }
public static class W { internal static int Write(Span<byte> buffer, int n) => n; }
public class Use
{
    public void Go(string[] names, List<string> list)
    {
        names.IndexOf("a");                         // arrays implement IList.IndexOf explicitly: the extension
        list.IndexOf("a");                          // List<T>.IndexOf is List's own
        byte[] buffer = new byte[8];
        W.Write(buffer, 1);                         // byte[] converts to Span<byte>
    }
}
''')
    _, calls = csharp_symbols.extract(_repo(tmp_path))
    hits = [(_short(c["callee"]), c["line"]) for c in calls if c["rel"] == "S.cs"]
    assert ("S.L.IndexOf", 10) in hits and not [h for h in hits if h == ("S.L.IndexOf", 11)]
    assert any(h[0] == "S.W.Write" for h in hits)


def test_tuple_typed_fields_are_not_methods_named_after_a_modifier(tmp_path):
    (tmp_path / "T.cs").write_text('''namespace T;
public class C
{
    private (string A, int B) _key;
    public (int X, int Y)? Pair { get; set; }
    private static (string Command, int Id) _q;
    public (int, int) Make() => (1, 2);
}
''')
    syms, _ = csharp_symbols.extract(_repo(tmp_path))
    names = {s["name"] for s in syms}
    assert not names & {"private", "public", "static"} and "Make" in names


def test_linq_lambdas_and_fluent_builders(tmp_path):
    (tmp_path / "Q.cs").write_text('''namespace Q;
using System.Collections.Generic;
using System.Linq;
using Microsoft.Extensions.DependencyInjection;
public class Person { public bool IsActor() => true; public void Greet() { } }
public static class Reg { public static IServiceCollection RegisterMine(this IServiceCollection s) => s; }
public class Use
{
    public void Go(List<Person> people, IServiceCollection services)
    {
        var actors = people.Where(i => i.IsActor()).ToList();
        actors.First().Greet();
        people.FirstOrDefault(p => p.IsActor())?.Greet();
        services.AddSingleton<Person>().RegisterMine();
    }
}
''')
    _, calls = csharp_symbols.extract(_repo(tmp_path))
    hits = {(_short(c["callee"]), c["line"]) for c in calls if c["rel"] == "Q.cs"}
    assert ("Q.Person.IsActor", 11) in hits, "the Where lambda's parameter is a Person"
    assert ("Q.Person.Greet", 12) in hits, "ToList() then First() is a Person"
    assert ("Q.Reg.RegisterMine", 14) in hits, "AddSingleton returns the IServiceCollection"


def test_foreach_over_a_typed_local_and_color_color_properties(tmp_path):
    (tmp_path / "F.cs").write_text('''namespace F;
using System.Collections.Generic;
public class Item { public void Touch() { } }
public class Tracker { public bool HasChanges() => true; }
public class Ctx { public Tracker Tracker { get; } }
public class Use<TContext> where TContext : Ctx
{
    public void Go(List<Item> items, TContext context)
    {
        foreach (var it in items) { it.Touch(); }       // a foreach over a typed local
        context.Tracker.HasChanges();                   // a generic receiver: the property named like its type
    }
}
''')
    _, calls = csharp_symbols.extract(_repo(tmp_path))
    pairs = {(_short(c["caller"]), _short(c["callee"])) for c in calls}
    assert ("F.Use.Go", "F.Item.Touch") in pairs
    assert ("F.Use.Go", "F.Tracker.HasChanges") in pairs


def test_generic_parameters_are_their_constraint(tmp_path):
    (tmp_path / "G.cs").write_text('''namespace G;
public class Facade { }
public class Database { }                                   // a type named like the property: must not win
public class Context { public Facade Database { get; } }
public static class Ext { public static int Client(this Facade f) => 0; }
public class Use<TContext> where TContext : Context
{
    public void Go(TContext context) { context.Database.Client(); }
}
''')
    _, calls = csharp_symbols.extract(_repo(tmp_path))
    assert ("G.Use.Go", "G.Ext.Client") in {(_short(c["caller"]), _short(c["callee"])) for c in calls}


def test_a_new_expression_followed_by_a_member_is_not_the_locals_type():
    loc = csharp_symbols._locals("var s = new Builder { A = 1 }.ToString(); var b = new Builder { A = 1 }; "
                                 "var c = new Builder(2); var d = new Builder(1).Build();")
    assert "s" not in loc and "d" not in loc and loc["b"] == "Builder" and loc["c"] == "Builder"


def test_a_call_chained_on_an_object_initializer_is_typed(tmp_path):
    (tmp_path / "I.cs").write_text('''namespace I;
public class Options { public int A { get; set; } public bool Has(int x) => true; }
public static class Ext { public static Options AddMore(this Options o, int x) => o; }
public class Use
{
    public void Go(int f)
    {
        var o = new Options { A = f }
            .AddMore(2);
        o.Has(1);
        new Options(){ A = 2 }.Has(3);
    }
}
''')
    _, calls = csharp_symbols.extract(_repo(tmp_path))
    hits = {(_short(c["callee"]), c["line"]) for c in calls if c["rel"] == "I.cs"}
    assert ("I.Ext.AddMore", 9) in hits and ("I.Options.Has", 10) in hits


def test_linq_beats_an_extension_on_the_non_generic_ienumerable(tmp_path):
    (tmp_path / "L.cs").write_text('''namespace L;
using System.Collections;
using System.Collections.Generic;
using System.Linq;
public static class E
{
    public static List<object> ToList(this IEnumerable source) => null;           // non-generic: loses to LINQ
    public static int FindIndex<T>(this IReadOnlyList<T> source, System.Predicate<T> m) => 0;   // more specific: wins
}
public class Use
{
    public void Go(IQueryable<int> q, IReadOnlyList<int> xs)
    {
        q.ToList();
        xs.FindIndex(x => x > 1);
    }
}
''')
    _, calls = csharp_symbols.extract(_repo(tmp_path))
    callees = {_short(c["callee"]) for c in calls if c["rel"] == "L.cs"}
    assert "L.E.ToList" not in callees and "L.E.FindIndex" in callees
