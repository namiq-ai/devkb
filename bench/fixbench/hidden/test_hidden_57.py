from __future__ import annotations
# Hidden acceptance for #57 (from 4b9325c).
"""C# support (#32, SPEC-DEVKB-CSHARP): definitions, calls and tests from `.cs` files, standard library only."""




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

