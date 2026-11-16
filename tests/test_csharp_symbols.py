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
