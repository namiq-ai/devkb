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


# ── round 4 (SPEC-DEVKB-CSHARP-4, #40) ────────────────────────────────────────────────────────────────────────

def _sites(tmp_path, name, text, caller="Go"):
    """{source line: callees resolved on it} for every call site in `caller` (extract() keeps one edge per pair)."""
    (tmp_path / name).write_text(text)
    sc = csharp_symbols.scan_file(name, text)
    for x in sc["symbols"]:
        x["rel"], x["key"] = name, name + "::" + ".".join(x["qparts"])
    index = csharp_symbols._Index(sc["symbols"])
    go = next(x for x in sc["symbols"] if x["name"] == caller)
    lines = text.splitlines()
    got = {}
    for callee, _c, line, _t, why in csharp_symbols._calls_in(go, sc["masked"], sc["nl"], index, {}, sc["raw"],
                                                               sc.get("aliases")):
        key = lines[line - 1].split("//")[0].strip()
        got.setdefault(key, set()).add(".".join(callee["qparts"]) if callee else "-" + why)
    return got


def test_f6_static_calls_on_generic_types(tmp_path):
    got = _sites(tmp_path, "G6.cs", '''namespace G6;
public class Ctx<T> { public static Ctx<T> FromOther(object o) => null; public void Run() { } }
public class Use
{
    public void Go(object o)
    {
        Ctx<int>.FromOther(o);
        var p = System.IO.Path.GetExtension("a.b");
        Path.GetExtension("x");
    }
}
public static class Ext { public static string GetExtension(this string s) => s; }
''')
    assert got["Ctx<int>.FromOther(o);"] == {"G6.Ctx.FromOther"}
    assert "G6.Ext.GetExtension" not in got.get('Path.GetExtension("x");', set()), ".NET's Path.GetExtension"


def test_f7_element_access(tmp_path):
    got = _sites(tmp_path, "G7.cs", '''namespace G7;
using System.Collections.Generic;
public class Failure { public string Name; public void Show() { } }
public class Result { public List<Failure> Errors { get; } }
public class Use
{
    public void Go(Result result, Dictionary<string, Failure> byName, Failure[] all)
    {
        result.Errors[0].Show();
        byName["a"].Show();
        all[1].Show();
    }
}
''')
    for line in ("result.Errors[0].Show();", 'byName["a"].Show();', "all[1].Show();"):
        assert got[line] == {"G7.Failure.Show"}, line


def test_f8_casts_and_patterns(tmp_path):
    got = _sites(tmp_path, "G8.cs", '''namespace G8;
public class Builder { public void AddComponent(int c) { } }
public class Shape { }
public class Circle : Shape { public void Roll() { } }
public class Use
{
    public void Go(object o, Shape s)
    {
        var rb = (Builder)o;
        rb.AddComponent(1);
        var c = s as Circle;
        c.Roll();
        if (s is Circle round) { round.Roll(); }
        ((Builder)o).AddComponent(2);
    }
}
''')
    assert got["rb.AddComponent(1);"] == {"G8.Builder.AddComponent"}
    assert got["c.Roll();"] == {"G8.Circle.Roll"}
    assert got["if (s is Circle round) { round.Roll(); }"] == {"G8.Circle.Roll"}
    assert got["((Builder)o).AddComponent(2);"] == {"G8.Builder.AddComponent"}


def test_f1_generic_arguments_are_carried_through(tmp_path):
    got = _sites(tmp_path, "G1.cs", '''namespace G1;
using System;
using System.Collections.Generic;
public class Person { public decimal CalculateSalary() => 0; }
public class Blog { public void Publish() { } }
public class Order { public void Ship() { } }
public class Reporter { public void ReportAsync() { } }
public class Builder<TEntity> { public PropBuilder<TEntity> Property(int x) => null; public TEntity Entity => default; }
public class PropBuilder<TP> { public PropBuilder<TP> HasMax(int n) => this; }
public class ModelBuilder { public ModelBuilder Entity<TEntity>(Action<Builder<TEntity>> configure) => this; }
public abstract class AbstractValidator<T>
{
    public void RuleFor<TProperty>(Func<T, TProperty> pick) { }
}
public class Repository<T> { public T Get(int id) => default; public List<T> All() => null; }
public static class Seq { public static T FirstItem<T>(this IEnumerable<T> xs) => default; }
public class PersonValidator : AbstractValidator<Person>
{
    public void Go(ModelBuilder mb, Repository<Order> orders, Lazy<Reporter> reporter, List<Blog> blogs)
    {
        RuleFor(x => x.CalculateSalary());
        mb.Entity<Blog>(b => b.Property(1).HasMax(10));
        mb.Entity<Blog>(b => b.Entity.Publish());
        orders.Get(1).Ship();
        orders.All()[0].Ship();
        reporter.Value.ReportAsync();
        blogs.FirstItem().Publish();
    }
}
''')
    assert "G1.Person.CalculateSalary" in got["RuleFor(x => x.CalculateSalary());"], "T from the base list"
    assert "G1.PropBuilder.HasMax" in got["mb.Entity<Blog>(b => b.Property(1).HasMax(10));"]
    assert "G1.Blog.Publish" in got["mb.Entity<Blog>(b => b.Entity.Publish());"], "explicit <Blog> into the lambda"
    assert "G1.Order.Ship" in got["orders.Get(1).Ship();"], "the receiver's argument binds T"
    assert "G1.Order.Ship" in got["orders.All()[0].Ship();"]
    assert "G1.Reporter.ReportAsync" in got["reporter.Value.ReportAsync();"], "Lazy<T>.Value"
    assert "G1.Blog.Publish" in got["blogs.FirstItem().Publish();"], "T inferred from the receiver"


def test_f2_overload_betterness_across_keys(tmp_path):
    got = _sites(tmp_path, "G2.cs", '''namespace G2;
public class Animal { }
public class Dog : Animal { }
public static class AnimalExt { public static void Feed(this Animal a, int n) { } }
public static class DogExt { public static void Feed(this Dog d, int n) { } }
public static class ObjExt { public static void Tag(this object o, string s) { } }
public static class StrExt { public static void Tag(this object o, int n) { } }
public class Use
{
    public void Go(Dog dog, Animal cat)
    {
        dog.Feed(1);
        cat.Feed(1);
        dog.Tag("x");
    }
}
''')
    assert got["dog.Feed(1);"] == {"G2.DogExt.Feed"}, "the more specific `this` type wins"
    assert got["cat.Feed(1);"] == {"G2.AnimalExt.Feed"}, "a Dog extension cannot take an Animal"
    assert got['dog.Tag("x");'] == {"G2.ObjExt.Tag"}, "the string literal rules the int overload out"


def test_f3_dynamic_receivers_bind_at_run_time(tmp_path):
    got = _sites(tmp_path, "G3.cs", '''namespace G3;
public class Thing { public void Run() { } }
public class Use { public void Go(dynamic d) { d.Run(); } }
''')
    assert got["public class Use { public void Go(dynamic d) { d.Run(); } }"] == {"-external"}


def test_f4_linq_query_syntax(tmp_path):
    got = _sites(tmp_path, "G4.cs", '''namespace G4;
using System.Collections.Generic;
using System.Linq;
public class Order { public bool IsLate() => true; public Customer Buyer; }
public class Customer { public string Name() => ""; }
public class Use
{
    public void Go(List<Order> orders, List<Customer> customers)
    {
        var late = from o in orders
                   where o.IsLate()
                   select o;
        var names = from Customer c in customers select c.Name();
    }
}
''')
    assert got["where o.IsLate()"] == {"G4.Order.IsLate"}
    assert got["var names = from Customer c in customers select c.Name();"] == {"G4.Customer.Name"}


def test_f5_third_party_bases_and_f9_expression_receivers(tmp_path):
    got = _sites(tmp_path, "G5.cs", '''namespace G5;
using System;
using System.Linq.Expressions;
using Microsoft.AspNetCore.Mvc;
public static class ExprExt { public static bool IsParameterExpression(this LambdaExpression e) => true; }
public class ItemsController : ControllerBase
{
    public object Ok(int x) => null;
    public void Go(Expression<Func<int, int>> expression)
    {
        NotFound();
        expression.IsParameterExpression();
    }
}
''')
    assert got["NotFound();"] == {"-external"}, "MVC's NotFound, inherited from ControllerBase"
    assert got["expression.IsParameterExpression();"] == {"G5.ExprExt.IsParameterExpression"}


def test_a_partial_types_members_are_seen_from_every_file(tmp_path):
    (tmp_path / "P1.cs").write_text('''namespace PP;
public abstract partial class Pool { public static Pool Shared { get; } = null; public Ctx Get(int t) => null; }
public class Ctx { }
''')
    (tmp_path / "P2.cs").write_text('''namespace PP;
public abstract partial class Pool { private sealed class SharedPool : Pool { } }
public class Use { public void Go() { Pool.Shared.Get(1); } }
''')
    _, calls = csharp_symbols.extract(_repo(tmp_path))
    assert ("PP.Use.Go", "PP.Pool.Get") in {(_short(c["caller"]), _short(c["callee"])) for c in calls}


def test_overloads_that_agree_on_the_result_type_keep_it(tmp_path):
    got = _sites(tmp_path, "OV.cs", '''namespace OV;
using System;
public class Builder<TResult> { public Builder<TResult> Or<TException>() => this; }
public class Policy
{
    public static Builder<TResult> HandleResult<TResult>(TResult result) => null;
    public static Builder<TResult> HandleResult<TResult>(Func<TResult, bool> pick) => null;
}
public class Use { public void Go(int failure) { Policy.HandleResult(failure).Or<Exception>(); } }
''')
    line = "public class Use { public void Go(int failure) { Policy.HandleResult(failure).Or<Exception>(); } }"
    assert {"OV.Policy.HandleResult", "OV.Builder.Or"} <= got[line]


def test_var_from_a_call_chain_ending_in_a_property_and_switch_arm_patterns(tmp_path):
    got = _sites(tmp_path, "VP.cs", '''namespace VP;
public class Complex { public void Touch() { } }
public class Prop { public Complex ComplexType { get; } }
public class Model { public Prop Single() => null; }
public class Expr { }
public class ArrayExpr : Expr { }
public class Use
{
    public void Visit(ArrayExpr e) { }
    public object Go(Model model, Expr x)
    {
        var complexType = model.Single().ComplexType;
        complexType.Touch();
        return x switch
        {
            ArrayExpr a => Pick(a),
            _ => null
        };
    }
    public object Pick(ArrayExpr a) => a;
}
''')
    assert got["complexType.Touch();"] == {"VP.Complex.Touch"}
    assert got["ArrayExpr a => Pick(a),"] == {"VP.Use.Pick"}


def test_dotnet_names_shadowed_by_repo_types_array_casts_and_collection_arguments(tmp_path):
    got = _sites(tmp_path, "SH.cs", '''namespace SH;
using System.Collections.Generic;
public class List { }                                        // a repository type named like .NET's List<T>
public static class TupleExt { public static string FormatTables(this IEnumerable<(string T, string S)> t) => ""; }
public static class Coll { public static Queue<T> Enqueue<T>(this Queue<T> q, IEnumerable<T> items) => q; }
public class Bytes { public static string ToHex(byte[] b) => ""; }
public class Data { public List<(string T, string S)> Tables { get; } }
public class Use
{
    public void Go(Data d, object v, Queue<bool> failures)
    {
        d.Tables.FormatTables();
        var raw = (byte[])v;
        Bytes.ToHex(raw);
        failures.Enqueue([true]);
    }
}
''')
    assert got["d.Tables.FormatTables();"] == {"SH.TupleExt.FormatTables"}
    assert got["Bytes.ToHex(raw);"] == {"SH.Bytes.ToHex"}
    assert got["failures.Enqueue([true]);"] == {"SH.Coll.Enqueue"}


def test_generic_types_sharing_a_name_with_different_arity_are_both_repository_types(tmp_path):
    got = _sites(tmp_path, "AR.cs", '''namespace AR;
public interface IRule<T> { }
public interface IRule<T, TProperty> : IRule<T> { void AddValidator(int v); }
public class Builder<T, TProperty> { public IRule<T, TProperty> Rule { get; } public void Go() { Rule.AddValidator(1); } }
''', caller="Go")
    assert got["public class Builder<T, TProperty> { public IRule<T, TProperty> Rule { get; } public void Go() { Rule.AddValidator(1); } }"] == {"AR.IRule.AddValidator"}


# ── 0.2.8 quality audit (#57-#61) ─────────────────────────────────────────────────────────────────────────────

def _edges_of(tmp_path, files: dict[str, str]):
    """(symbol names, {(caller, callee)}) from extract() over a repository of `files`."""
    for rel, text in files.items():
        (tmp_path / rel).write_text(text)
    for cmd in (["init", "-q"], ["add", "-A", "-f"], ["-c", "user.email=t@example.com", "-c", "user.name=T", "commit", "-qm", "x"]):
        subprocess.run(["git", *cmd], cwd=tmp_path, check=True)
    symbols, calls = csharp_symbols.extract(tmp_path)
    return {_short(s["key"]) for s in symbols}, {(_short(c["caller"]), _short(c["callee"])) for c in calls}


def test_a_verbatim_string_of_one_quote_is_not_a_raw_string(tmp_path):
    # #57: `@` and four quotes is a verbatim string holding one quote; read as a raw string it blanked the file
    names, edges = _edges_of(tmp_path, {"V.cs": '''namespace V { class A {
  void M() { var q = @""""; Helper(); }
  void Helper() { }
  void Other() { Helper(); }
} }
'''})
    assert {"V.A.M", "V.A.Helper", "V.A.Other"} <= names
    assert {("V.A.M", "V.A.Helper"), ("V.A.Other", "V.A.Helper")} <= edges
    assert csharp_symbols.mask('x = @"""" + @"a""b"; y();').endswith("y();")


def test_a_local_function_calls_its_sibling_local_function(tmp_path):
    """#58: a call from one local function to a sibling (or to one of an enclosing local function) binds to it,
    not to the type's method of the same name."""
    _, edges = _edges_of(tmp_path, {"L.cs": '''namespace L { class A {
  void M() {
    int B() => 1;
    int C() { return B(); }
    int D() { int E() => B() + C(); return E(); }
    C();
  }
  int B() => 2;
  void N() { B(); }
} }
'''})
    assert ("L.A.M.C", "L.A.M.B") in edges and ("L.A.M.C", "L.A.B") not in edges
    assert {("L.A.M.D.E", "L.A.M.B"), ("L.A.M.D.E", "L.A.M.C"), ("L.A.M.D", "L.A.M.D.E"), ("L.A.M", "L.A.M.C")} <= edges
    assert ("L.A.N", "L.A.B") in edges and not any(callee == "L.A.B" for caller, callee in edges if caller != "L.A.N")


def test_identifiers_starting_with_a_non_ascii_letter_keep_it(tmp_path):
    """#59: `Älpha` and `Ölpha` are two names; read as `[A-Za-z_]\\w*` both were keyed `lpha`."""
    names, edges = _edges_of(tmp_path, {"U.cs": '''namespace U { class Ärger {
  void Älpha() { }
  void Ölpha() { }
  void Go() { Älpha(); var é = new Ärger(); é.Ölpha(); }
} }
'''})
    assert {"U.Ärger", "U.Ärger.Älpha", "U.Ärger.Ölpha"} <= names and "U.Ärger.lpha" not in names
    assert {("U.Ärger.Go", "U.Ärger.Älpha"), ("U.Ärger.Go", "U.Ärger.Ölpha")} <= edges


def test_extraction_stays_linear_in_unresolved_calls_to_a_common_name(tmp_path):
    """#60: N types each define `Get()` and call `x.Get()` on receivers it cannot type. Per-file counts were rebuilt
    per definition, and `_why` built a set of every `Get` per call site: N=3000 took ~8 s; linear, well under 1 s."""
    import time
    n = 3000
    for i in range(n):
        (tmp_path / f"C{i}.cs").write_text(f"namespace N{i} {{ class C{i} {{ public int Get() => 1; "
                                           f"void Use(dynamic_ x) {{ x.Get(); y.Get(); z.Get(); }} }} }}\n")
    for cmd in (["init", "-q"], ["add", "-A", "-f"], ["-c", "user.email=t@example.com", "-c", "user.name=T", "commit", "-qm", "x"]):
        subprocess.run(["git", *cmd], cwd=tmp_path, check=True)
    t = time.perf_counter()
    symbols, _ = csharp_symbols.extract(tmp_path)
    took = time.perf_counter() - t
    gets = [s for s in symbols if s["name"] == "Get"]
    assert len(gets) == n and all(s["unresolved_calls"] == n and s["unresolved_file_count"] == n for s in gets)
    assert gets[0]["unresolved_files"] == sorted(f"C{i}.cs" for i in range(n))[:20]
    assert took < 3.0, f"{took:.1f} s for {n} files: quadratic again"


def test_lambda_parameter_lookup_stays_linear_in_a_long_fluent_method(tmp_path):
    """#61: one method of `b.Property(x => x.P).HasColumn(y => y.Q);` lines (an EF Core model snapshot's shape). Every
    lambda parameter went on one list scanned whole per lookup: quadratic. The measure is the number of Python lines
    csharp_symbols executes, which is the same on every run: a wall clock or CPU time fails under load (#371; CPU time
    too, when another process shares the core). 4x the lines: 4.05x the work now, 10.9x for the code before #61."""
    import sys

    def repo(n: int) -> Path:
        d = tmp_path / f"r{n}"
        d.mkdir()
        lines = "\n".join(f"    b.Property(x => x.P{i}).HasColumn(y => y.Q{i});" for i in range(n))
        (d / "A.cs").write_text("namespace N { class B { public B Property(System.Func<int,int> f) => this; "
                                "public B HasColumn(System.Func<int,int> f) => this; }\nclass A { void M(B b) {\n" + lines + "\n} } }\n")
        for cmd in (["init", "-q"], ["add", "-A", "-f"], ["-c", "user.email=t@example.com", "-c", "user.name=T", "commit", "-qm", "x"]):
            subprocess.run(["git", *cmd], cwd=d, check=True)
        return d

    def work(d: Path):
        """(lines executed in csharp_symbols, calls found) for one extract()."""
        n, mine = [0], csharp_symbols.__file__

        def local(frame, event, arg):
            if event == "line":
                n[0] += 1
            return local

        old = sys.gettrace()
        sys.settrace(lambda frame, event, arg: local if frame.f_code.co_filename == mine else None)
        try:
            _, calls = csharp_symbols.extract(d)
        finally:
            sys.settrace(old)
        return n[0], calls

    small, _ = work(repo(500))
    big, calls = work(repo(2000))
    assert {(_short(c["caller"]), _short(c["callee"])) for c in calls} == {("N.A.M", "N.B.Property"), ("N.A.M", "N.B.HasColumn")}
    assert big / small < 6, f"4x the lines took {big / small:.1f}x the work ({small} and {big} lines executed): quadratic again"


def test_a_lambda_parameter_shadows_only_within_its_lambda(tmp_path):
    """#61 kept the lookup's meaning: the innermost (latest) lambda parameter whose span holds the position wins, and
    outside every span the local of the same name is seen again."""
    got = _sites(tmp_path, "S61.cs", '''namespace S61;
public class P { public void Pm() { } }
public class Q { public void Qm() { } }
public class R { public void Rm() { } }
public static class Run { public static void With(System.Action<Q> a) { } public static void Wide(System.Action<R> a) { } }
public class Use
{
    public void Go(P x)
    {
        Run.Wide(x => { Run.With(x => x.Qm()); x.Rm(); });
        x.Pm();
    }
}
''')
    assert got["Run.Wide(x => { Run.With(x => x.Qm()); x.Rm(); });"] >= {"S61.Q.Qm", "S61.R.Rm"}
    assert "S61.P.Pm" not in got["Run.Wide(x => { Run.With(x => x.Qm()); x.Rm(); });"]
    assert got["x.Pm();"] == {"S61.P.Pm"}



def test_an_attribute_holding_braces_does_not_hide_the_member_after_it(tmp_path):
    """#78: `[InlineData(new int[] { 1, 2 }, 3)]`: the attribute's `{` was read as a block at type level, so the test
    method after it was neither a symbol nor a test and its calls were lost."""
    text = '''namespace T78 {
public static class Calc { public static int Sum(int[] a) => 0; }
public class CalcTests {
  [Theory][InlineData(new int[] { 1, 2 }, 3)] public void Sums(int[] a, int s) { Calc.Sum(a); }
  [Fact] public void After() { Calc.Sum(null); }
}
[Obsolete(nameof(X), new[] { "a" })] public class Marked { public void M() { Calc.Sum(null); } }
}
'''
    names, edges = _edges_of(tmp_path, {"T78.cs": text})
    assert {"T78.CalcTests.Sums", "T78.CalcTests.After", "T78.Marked", "T78.Marked.M"} <= names
    assert {("T78.CalcTests.Sums", "T78.Calc.Sum"), ("T78.CalcTests.After", "T78.Calc.Sum"),
            ("T78.Marked.M", "T78.Calc.Sum")} <= edges
    assert [n for n, _ in csharp_symbols.tests_in_text(text)] == ["After", "Sums"]



def test_explicit_interface_implementations_are_recorded_with_their_calls(tmp_path):
    """#79: `void IRunner.Run()` was rejected (a name after `.`), so the member and every call inside it were lost.
    The member keeps its interface name (`A.IRunner.Run`); a call `Run()` never binds to it, as in C#."""
    names, edges = _edges_of(tmp_path, {"I79.cs": '''namespace I79 {
interface IRunner { void Run(); }
class A : IRunner, System.IDisposable, System.Collections.Generic.IEnumerable<int> {
  void IRunner.Run(){ Helper(); }
  void IDisposable.Dispose(){ Cleanup(); }
  public void Dispose() { }
  IEnumerator<int> IEnumerable<int>.GetEnumerator() { return Make(); }
  int IRunner.Count { get { return Helper2(); } }
  void Helper(){} void Cleanup(){} IEnumerator<int> Make() => null; int Helper2() => 1;
  void Go() { Run(); Dispose(); }
  void Run() { }
}
}
'''})
    assert {"I79.A.IRunner.Run", "I79.A.IDisposable.Dispose", "I79.A.IEnumerable.GetEnumerator",
            "I79.A.IRunner.Count"} <= names
    assert {("I79.A.IRunner.Run", "I79.A.Helper"), ("I79.A.IDisposable.Dispose", "I79.A.Cleanup"),
            ("I79.A.IEnumerable.GetEnumerator", "I79.A.Make"), ("I79.A.IRunner.Count", "I79.A.Helper2")} <= edges
    assert ("I79.A.Go", "I79.A.Run") in edges and ("I79.A.Go", "I79.A.Dispose") in edges
    assert not any(callee.startswith(("I79.A.IRunner.", "I79.A.IDisposable.")) for _, callee in edges)



def test_if_else_branches_with_unbalanced_braces_do_not_nest_the_rest_of_the_class(tmp_path):
    """#80: two signature variants under `#if`/`#else` open one `{` each but share one `}`; the rest of the class was
    nested in the first method (`A.M.Foo`). Read as one configuration would: the first branch alone."""
    names, edges = _edges_of(tmp_path, {"P80.cs": '''namespace P80 { class A {
#if X
void M(int a) {
#else
void M(int a, int b) {
#endif
  Foo();
}
void Foo(){} void Bar(){ Foo(); }
#if Y
void Kept() { Foo(); }
#else
void Also() { Bar(); }
#endif
} }
'''})
    assert {"P80.A.M", "P80.A.Foo", "P80.A.Bar", "P80.A.Kept", "P80.A.Also"} <= names
    assert not any(n.startswith("P80.A.M.") for n in names)
    assert {("P80.A.Bar", "P80.A.Foo"), ("P80.A.M", "P80.A.Foo"), ("P80.A.Kept", "P80.A.Foo"),
            ("P80.A.Also", "P80.A.Bar")} <= edges



def test_a_finalizer_is_not_the_constructor(tmp_path):
    """#81: `~Res()` was recorded as `Res.ctor`, so `new Res()` linked to the finalizer."""
    names, edges = _edges_of(tmp_path, {"F81.cs": '''namespace F81 {
class Res { ~Res(){ Release(); } void Release(){} }
class User { void Go(){ new Res(); } }
class Both { public Both() { Init(); } ~Both() { Release(); } void Init(){} void Release(){} }
class Make { void Go(){ new Both(); } }
}
'''})
    assert "F81.Res.~Res" in names and "F81.Res.ctor" not in names
    assert ("F81.Res.~Res", "F81.Res.Release") in edges
    assert not any(callee.endswith(("~Res", "~Both")) for caller, callee in edges if caller != callee)
    assert ("F81.User.Go", "F81.Res.ctor") not in edges
    assert {("F81.Both.ctor", "F81.Both.Init"), ("F81.Both.~Both", "F81.Both.Release"),
            ("F81.Make.Go", "F81.Both.ctor")} <= edges
    assert ("F81.Both.ctor", "F81.Both.Release") not in edges



def test_overloads_do_not_share_their_local_functions(tmp_path):
    """#82: local functions were looked up by the owner's qualified name, which overloads share: `M(string)`'s
    `Validate()` bound to the local function of `M(int)`."""
    names, edges = _edges_of(tmp_path, {"O82.cs": '''namespace O82 { class A {
  void M(int a){ void Validate(){ Check(); } Validate(); }
  void M(string s){ Validate(); }
  void Validate(){}
  void Check(){}
} }
'''})
    calls = csharp_symbols.extract(tmp_path)[1]
    m_calls = {(c["line"], _short(c["callee"])) for c in calls if _short(c["caller"]) == "O82.A.M"}
    assert (2, "O82.A.M.Validate") in m_calls and (3, "O82.A.Validate") in m_calls
    assert ("O82.A.M.Validate", "O82.A.Check") in edges



def test_a_utf16_file_is_read(tmp_path):
    """#83: a file saved as UTF-16 (Visual Studio's "Unicode") with a byte-order mark yielded nothing, silently."""
    src = 'namespace U83 { class A { void Go() { Helper(); } void Helper() { } } }\n'
    (tmp_path / "Le.cs").write_bytes(src.encode("utf-16"))                 # little-endian with a BOM
    (tmp_path / "Be.cs").write_bytes(b"\xfe\xff" + src.replace("U83", "B83").encode("utf-16-be"))
    (tmp_path / "U8.cs").write_bytes(b"\xef\xbb\xbf" + src.replace("U83", "E83").encode("utf-8"))
    names, edges = _edges_of(tmp_path, {})
    for ns in ("U83", "B83", "E83"):
        assert {f"{ns}.A.Go", f"{ns}.A.Helper"} <= names
        assert (f"{ns}.A.Go", f"{ns}.A.Helper") in edges
    tests = '[Fact] public void Works() { }'.join(("namespace U83 { class T { ", " } }\n"))
    (tmp_path / "T.cs").write_bytes(tests.encode("utf-16"))
    assert test_discovery.tests_in_file(tmp_path, "T.cs") == [("Works", 1)]


def test_an_explicit_implementation_after_an_attribute_does_not_call_itself(tmp_path):
    """#79, measured on EF Core: an expression body's start was counted from the header with its attributes removed,
    so it began that many characters early, inside the header; `IG.Get(` there read as a call to the interface."""
    names, edges = _edges_of(tmp_path, {"E79.cs": '''namespace E79 {
interface IG { int Get(int a); int Put(int a); }
class B { public virtual int Get(int a) => 0; public virtual int Put(int a) => 0; }
class A : B, IG {
  [System.Diagnostics.DebuggerStepThrough]
  int IG.Get(int a) => base.Get(a);
  [System.Diagnostics.DebuggerStepThrough]
  int IG.Put(int a) => new System.Func<int>(() => { return base.Put(a); })();
}
}
'''})
    assert {"E79.A.IG.Get", "E79.A.IG.Put"} <= names
    assert not any(callee.startswith("E79.IG.") for _, callee in edges)
    sc = csharp_symbols.scan_file("E79.cs", (tmp_path / "E79.cs").read_text())
    for s in sc["symbols"]:
        if s["name"] in ("IG.Get", "IG.Put"):
            assert [sc["masked"][a:a + 2] for a, _ in s["body"]] == ["=>"], s["name"]
