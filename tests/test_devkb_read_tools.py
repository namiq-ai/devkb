"""SPEC-DKB-003 / ADR-DEVKB-010: the read tools (symbol, outline, uses, search_docs) over a fixture repository in
Python, TypeScript, C and C#. One repository is built once; tests that change a file restore it."""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from devkb import process_api, read_tools  # noqa: E402

LONG_BODY = "\n".join(f"    step_{n} = {n}" for n in range(1, 261))
FILES = {
    "pkg/models.py": '"""Models."""\nimport json\nfrom pathlib import Path\n\n\nclass Store:\n    """Holds records."""\n\n'
                     '    def add(self, item):\n        """Add an item."""\n        return item\n\n'
                     '    def get(self, key):\n        return key\n\n\n'
                     'def parse_json_string(text):\n    """Parse a JSON string."""\n    return json.loads(text)\n\n\n'
                     f'def long_function(x):\n{LONG_BODY}\n    return x\n',
    "pkg/other.py": "class Cache:\n    def add(self, item):\n        return item\n\n\ndef uses_store():\n    from pkg.models import Store\n    return Store()\n",
    "pkg/many.py": "\n".join(f"v{n} = needle_token  # {n}" for n in range(60)) + "\n",
    "tests/test_models.py": "from pkg.models import Store\n\n\ndef add(x):\n    return x\n\n\ndef test_add():\n    assert Store().add(1) == 1\n",
    "web/api.ts": 'import axios from "axios";\n\nexport function getRequests(c: number): number {\n  return c + 1;\n}\n\n'
                  "export const fetchAll = (u: string) => {\n  return u;\n};\n",
    "lib/util.c": "int add_numbers(int a, int b) { return a + b; }\n\nint scaled(int a, int k)\n{\n    int r = a * k;\n    return r;\n}\n",
    "lib/util.h": "int add_numbers(int a, int b);\nint scaled(int a, int k);\n",
    "src/Calc.cs": "namespace Demo\n{\n    public class Calc\n    {\n        public int Add(int a, int b)\n        {\n            return a + b;\n        }\n    }\n}\n",
    "README.md": "# Demo\n\nSee the guide.\n",
    "docs/guide.md": "# Guide\n\n## Retention policy\n\nRecords keep for 30 days. The retention policy is per store. GuideOnlyToken.\n\n## Other\n\nnothing here\n",
    "docs/adr/ADR-001_retention.md": "# ADR-001 Retention\n\n## Decision\n\nThe retention policy is 30 days.\n",
}


@pytest.fixture(scope="module")
def repo(tmp_path_factory):
    root = tmp_path_factory.mktemp("readtools")
    subprocess.run(["git", "init", "-q", str(root)], check=True)
    for rel, text in FILES.items():
        (root / rel).parent.mkdir(parents=True, exist_ok=True)
        (root / rel).write_text(text)
    subprocess.run(["git", "add", "."], cwd=root, check=True)
    subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@example.com", "commit", "-qm", "fixture"], cwd=root, check=True)
    env = dict(os.environ, PYTHONPATH=str(ROOT), PYTHONWARNINGS="ignore")
    subprocess.run([sys.executable, "-P", "-m", "devkb.cli", "build", "--project", str(root)], cwd=root, env=env, check=True, capture_output=True)
    return root


@pytest.fixture(scope="module")
def api(repo):
    return process_api.ProcessAPI(str(repo), telemetry=False)


def line_of(rel: str, needle: str) -> int:
    return next(n for n, t in enumerate(FILES[rel].splitlines(), 1) if needle in t)


PJS = line_of("pkg/models.py", "def parse_json_string")


def sym(api, q, **kw):
    return api.call("symbol", query=q, **kw)


def keys(r):
    return [m["k"] for m in r["matches"]]


# ── symbol: name resolution, tier by tier ─────────────────────────────────
def test_an_exact_name_returns_its_exact_range_signature_and_docstring(api):
    r = sym(api, "parse_json_string")
    m = r["matches"][0]
    assert r["how"] == "exact" and m["k"] == "pkg/models.py::parse_json_string"
    assert (m["ls"], m["le"], m["range"]) == (PJS, PJS + 2, "exact")
    assert m["sig"] == "def parse_json_string(text):" and m["doc"].startswith("Parse a JSON")


def test_qualified_names_accept_dot_double_colon_and_a_file_prefix(api):
    for q in ("Store.add", "Store::add", "pkg/models.py::Store.add", "models.py::Store.add", "Store#add"):
        assert keys(sym(api, q))[0] == "pkg/models.py::Store.add", q


def test_a_name_shared_by_several_symbols_ranks_production_before_tests(api):
    r = sym(api, "add")
    assert r["n"] >= 4 and keys(r)[-1].startswith("tests/") and not any(k.startswith("tests/") for k in keys(r)[:-1])


def test_glob_regex_prefix_and_words_find_the_same_function(api):
    for q, how in (("parse_*", "glob"), ("re:^parse_.*string$", "regex"), ("^parse_js", "regex"), ("parse_js", "prefix"), ("parse json", "words")):
        r = sym(api, q)
        assert r["how"] == how and "pkg/models.py::parse_json_string" in keys(r), q


def test_a_typo_is_matched_by_similarity_and_labelled(api):
    r = sym(api, "parse_jsn_string")
    assert r["how"] == "similar" and keys(r)[0] == "pkg/models.py::parse_json_string" and r["matches"][0]["how"].startswith("similar ")


def test_a_name_that_does_not_exist_is_not_matched_and_gets_suggestions_at_most(api):
    r = sym(api, "zzzqqqwww")
    assert r["n"] == 0 and r["matches"] == [] and "suggestions" in r
    r = sym(api, "parse_something_else_entirely")
    assert r["how"] != "similar"          # below the confidence floor: not presented as a match


def test_a_bad_regular_expression_is_an_error_not_a_crash(api):
    assert "bad regular expression" in sym(api, "re:(")["error"]


def test_filters_by_kind_and_path(api):
    assert all(m["kind"] == "class" for m in sym(api, "re:Store|Cache", kind="class")["matches"])
    assert all(m["k"].startswith("pkg/") for m in sym(api, "add", under="pkg/")["matches"])


# ── symbol: source, ranges and honesty per language ───────────────────────
def test_source_is_bounded_by_the_graphs_own_range(api):
    s = sym(api, "parse_json_string", source=True)["matches"][0]["source"]
    assert [x.split(None, 1)[0] for x in s["lines"]] == [str(PJS), str(PJS + 1), str(PJS + 2)] and s["more"] == 0 and not s["approx"]


def test_a_long_body_is_cut_with_the_remainder_counted(api):
    s = sym(api, "long_function", source=True, lines=10)["matches"][0]["source"]
    assert len(s["lines"]) == 10 and s["more"] > 200
    s = sym(api, "long_function", source=True, lines=10_000)["matches"][0]["source"]
    assert len(s["lines"]) == read_tools.HARD_SOURCE and s["more"] > 50


def test_a_class_too_long_to_print_lists_its_members_instead(api):
    s = sym(api, "Store", source=True, lines=3)["matches"][0]["source"]
    assert s["too_long"] > 3 and {"pkg/models.py::Store.add", "pkg/models.py::Store.get"} <= {m["k"] for m in s["members"]}


def test_a_typescript_symbol_says_its_end_is_unknown_and_shows_a_window_not_a_range(api):
    m = sym(api, "getRequests", source=True)["matches"][0]
    assert m["range"] == "end unknown" and m["source"]["approx"] is True and len(m["source"]["lines"]) <= read_tools.APPROX_WINDOW + 1
    assert "(end unknown)" in read_tools.render_symbol(sym(api, "getRequests", source=True))


def test_c_and_csharp_symbols_carry_real_ranges_and_a_one_line_function_says_so(api):
    assert sym(api, "scaled")["matches"][0]["range"] == "exact"
    assert sym(api, "add_numbers")["matches"][0]["range"] == "one line"
    m = sym(api, "Calc.Add")["matches"][0]
    assert m["k"].endswith("Calc.Add") and m["range"] == "exact"


def test_a_file_edited_after_the_build_is_re_anchored_and_flagged(api, repo):
    path = repo / "pkg/models.py"; original = path.read_text()
    try:
        path.write_text("# a\n# b\n# c\n" + original)
        api._read_tools = None
        m = sym(api, "parse_json_string", source=True)["matches"][0]
        assert m["moved"] == 3 and m["ls"] == PJS + 3 and m["sig"] == "def parse_json_string(text):"
        assert m["source"]["lines"][0].split(None, 1)[1].startswith("def parse_json_string")
    finally:
        path.write_text(original); api._read_tools = None


# ── outline ───────────────────────────────────────────────────────────────
def test_outline_nests_symbols_lists_ranges_and_imports(api):
    r = api.call("outline", path="pkg/models.py")
    by = {s["q"]: s for s in r["symbols"]}
    assert by["Store"]["depth"] == 0 and by["Store.add"]["depth"] == 1 and by["Store.add"]["ls"] == line_of("pkg/models.py", "def add")
    assert any("import json" in i for i in r["imports"]) and r["n"] >= 5
    text = read_tools.render_outline(r)
    assert "class Store" in text and "  method add" in text


def test_outline_resolves_a_unique_suffix_and_lists_a_directory(api):
    assert api.call("outline", path="models.py")["path"] == "pkg/models.py"
    d = api.call("outline", path="pkg")
    assert d["directory"] and {f["f"] for f in d["files"]} >= {"pkg/models.py", "pkg/other.py"}
    assert "error" in api.call("outline", path="nowhere.py")


def test_outline_of_a_file_without_symbols_says_so(api):
    r = api.call("outline", path="README.md")
    assert r.get("note") or r.get("error")


# ── uses ──────────────────────────────────────────────────────────────────
def test_uses_groups_hits_by_file_and_enclosing_symbol_production_first(api):
    r = api.call("uses", name="Store")
    assert r["mode"] == "word" and [d["k"] for d in r["definitions"]] == ["pkg/models.py::Store"]
    files = [f["f"] for f in r["files"]]
    assert files.index("pkg/other.py") < files.index("tests/test_models.py")
    other = next(f for f in r["files"] if f["f"] == "pkg/other.py")
    assert any(h["in"] == "uses_store" for h in other["hits"])
    assert next(f for f in r["files"] if f["f"] == "tests/test_models.py")["test"] is True


def test_uses_caps_what_it_shows_and_says_what_it_cut(api):
    r = api.call("uses", name="needle_token")
    f = next(x for x in r["files"] if x["f"] == "pkg/many.py")
    assert r["n_hits"] >= 60 and f["n"] >= 60 and len(f["hits"]) == 3


def test_uses_skips_documentation_unless_asked_and_supports_regex(api):
    assert api.call("uses", name="GuideOnlyToken")["n_hits"] == 0
    assert api.call("uses", name="GuideOnlyToken", docs=True)["n_hits"] == 1
    r = api.call("uses", name="re:def (add|get)\\(")
    assert r["mode"] == "regex" and r["n_hits"] >= 3


def test_uses_is_honest_about_what_it_is(api):
    text = read_tools.render_uses(api.call("uses", name="Store"))
    assert "text matches, not resolved references" in text


# ── search_docs ───────────────────────────────────────────────────────────
def test_search_docs_needs_every_word_and_names_the_heading_of_each_hit(api):
    r = api.call("search_docs", query="retention policy")
    assert [f["f"] for f in r["files"]][0] == "docs/adr/ADR-001_retention.md"          # decisions first
    guide = next(f for f in r["files"] if f["f"] == "docs/guide.md")
    assert any(h["under"] == "Retention policy" for h in guide["hits"])
    assert api.call("search_docs", query="retention nonexistentword")["files"] == []
    assert api.call("search_docs", query="re:30 days")["mode"] == "regex"


# ── wiring: MCP tools, toolsets, CLI ──────────────────────────────────────
def test_the_four_tools_are_in_the_default_toolsets_and_render_text(repo):
    pytest.importorskip("mcp.server.fastmcp")
    import asyncio
    import importlib.util
    spec = importlib.util.spec_from_file_location("devkb_mcp_server", ROOT / "devkb" / "mcp_server.py")
    module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
    for ts in ("lean-pack", "dev", "all"):
        assert {"symbol", "outline", "uses", "search_docs"} <= set(module.TOOLSETS[ts]), ts
    server = module.build(module._LazyAPI(str(repo), None), "lean-pack")
    def call(name, args):
        out = asyncio.run(server.call_tool(name, args))
        return (out[0] if isinstance(out, tuple) else out)[0].text
    assert f"L{PJS}-{PJS + 2}" in call("symbol", {"query": "parse_json_string"})
    assert "class Store" in call("outline", {"path": "pkg/models.py"})
    assert "pkg/other.py" in call("uses", {"name": "Store"})
    assert "ADR-001_retention.md" in call("search_docs", {"query": "retention policy"})


def test_the_shell_commands_print_the_same_answers(repo):
    env = dict(os.environ, PYTHONPATH=str(ROOT), PYTHONWARNINGS="ignore")
    run = lambda *a: subprocess.run([sys.executable, "-P", "-m", "devkb.cli", *a, "--project", str(repo)], cwd=repo, env=env, capture_output=True, text=True).stdout
    assert f"L{PJS}-{PJS + 2}" in run("symbol", "parse_json_string")
    assert f"{PJS:>5}  def parse_json_string" in run("symbol", "parse_json_string", "--source")
    assert "method add" in run("outline", "pkg/models.py")
    assert "pkg/other.py" in run("uses", "Store")
    assert "Retention policy" in run("docs", "retention policy")


def test_a_stale_graph_is_said_in_every_reply():
    for fn, reply in ((read_tools.render_symbol, {"query": "x", "n": 0, "matches": [], "_meta": {"stale": True, "head": "abc12345", "behind": 2}}),
                      (read_tools.render_uses, {"name": "x", "mode": "word", "definitions": [], "n_hits": 0, "n_files": 0, "files": [],
                                                "omitted_files": 0, "note": "n", "_meta": {"stale": True, "head": "abc12345", "behind": 2}})):
        assert "graph stale: built at" in fn(reply)


def test_a_dotted_query_is_labelled_qualified_and_a_miss_suggests_names_with_path_and_score(api):
    assert sym(api, "Store.add")["how"] == "qualified"
    r = sym(api, "parse_jsn_strin_x")
    if r["n"] == 0:
        assert all({"name", "path", "score"} <= set(s) for s in r["suggestions"])


def test_no_reply_exceeds_the_byte_budget_and_the_cut_is_counted(api):
    text = read_tools.render_symbol(sym(api, "long_function", source=True, lines=200))
    assert len(text.encode()) <= read_tools.BUDGET + 120 and ("output cut" in text or len(text.encode()) <= read_tools.BUDGET)
    assert read_tools.fit_text("x\n" * 4000).endswith("narrow with under=PATH)")


def test_symbol_batch_and_nav_toolset():
    from devkb.mcp_server import TOOLSETS
    from devkb.read_tools import render_symbol
    assert TOOLSETS["nav"] == ["symbol", "outline", "pack"]
    text = render_symbol({"batch": [{"query": "a", "matches": [], "n": 0, "how": None}, {"query": "b", "matches": [], "n": 0, "how": None}]})
    assert 'no symbol named "a"' in text and 'no symbol named "b"' in text
