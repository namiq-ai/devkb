"""DKB-004: test cases of the approved C/C++ frameworks are inventoried with their framework and reach `tests_to_run`."""
from __future__ import annotations

import json
import subprocess

import cpp_support as S
from devkb.extractors import test_inventory
from devkb.project_context import ProjectContext

LIB = {"src/calc.h": "int add(int a, int b);\n", "src/calc.cc": "int add(int a, int b) { return a + b; }\n"}

FRAMEWORK_FILES = {
    "tests/gtest_calc.cc": '#include <gtest/gtest.h>\n#include "../src/calc.h"\nTEST(CalcSuite, Adds) { EXPECT_EQ(add(1, 2), 3); }\n',
    "tests/catch_calc.cc": '#include <catch2/catch_test_macros.hpp>\nTEST_CASE("adds two numbers", "[calc]") { REQUIRE(add(1, 2) == 3); }\n',
    "tests/doctest_calc.cc": '#include "doctest/doctest.h"\nTEST_CASE("doctest adds") { CHECK(add(1, 2) == 3); }\n',
    "tests/boost_calc.cc": '#include <boost/test/unit_test.hpp>\nBOOST_AUTO_TEST_CASE(boost_adds) { BOOST_CHECK(add(1, 2) == 3); }\n',
    "tests/test_unity.c": '#include "unity.h"\nvoid test_adds(void) { add(1, 2); }\nint main(void) { RUN_TEST(test_adds); return 0; }\n',
    "tests/ztest_calc.c": '#include <zephyr/ztest.h>\nZTEST(calc_suite, test_add) { zassert_equal(add(1, 2), 3); }\n',
}
WANT = {
    "tests/gtest_calc.cc": ("CalcSuite.Adds", 3, "gtest"), "tests/catch_calc.cc": ("adds two numbers", 2, "catch2"),
    "tests/doctest_calc.cc": ("doctest adds", 2, "doctest"), "tests/boost_calc.cc": ("boost_adds", 2, "boost-test"),
    "tests/test_unity.c": ("test_adds", 2, "unity"), "tests/ztest_calc.c": ("calc_suite.test_add", 2, "ztest"),
}


def _ctx(root):
    return ProjectContext(code="TST", repo_root=root, ticket_prefix="TST", issues_dir=root / "issues", tests_dir=root / "tests",
                          sprint_dir=root / "h", devkb_dir=root / ".devkb", board_file=root / "b.md", wp_map_file=root / "w.json")


def test_one_case_per_framework_with_file_line_function_and_framework(tmp_path):
    root = S.make_repo(tmp_path, {**LIB, **FRAMEWORK_FILES})
    g = test_inventory.extract(_ctx(root))
    got = {n.props["file"]: (n.props["function"], n.props["line"], n.props["framework"]) for n in g.nodes("TestCase")}
    assert got == WANT
    assert {(e.src, e.dst) for e in g.edges("DEFINED_IN")} == {(f"{f}:{w[1]}", f) for f, w in WANT.items()}


def test_tests_to_run_returns_the_test_file_that_calls_into_a_changed_source_file(tmp_path, monkeypatch):
    api, _packer = S.api(tmp_path, {**LIB, **FRAMEWORK_FILES}, monkeypatch)
    r = api.tests_to_run(files=["src/calc.cc"])
    assert "tests/gtest_calc.cc" in r["tests"] and "tests/catch_calc.cc" not in r["tests"] or "tests/catch_calc.cc" in r["tests"]
    assert "tests/gtest_calc.cc" in r["tests"], r
    assert r["run"] == "", "no build-system integration: files only"
    assert api.tests_to_run(files=["src/calc.cc"])["n"] >= 1


def test_macro_in_a_comment_string_or_if_0_is_not_a_test(tmp_path):
    root = S.make_repo(tmp_path, {
        "src/notes.cc": ('// TEST(Fake, Comment) { }\n/* TEST_CASE("fake") { } */\nconst char *s = "TEST(Fake, String) { }";\n'
                         '#if 0\nTEST(Fake, Disabled) { }\n#endif\nint real(void) { return 0; }\n'),
    })
    assert not list(test_inventory.extract(_ctx(root)).nodes("TestCase"))


def test_ambiguous_test_case_without_an_include_is_skipped_and_counted(tmp_path):
    root = S.make_repo(tmp_path, {"tests/mystery.cc": 'TEST_CASE("who owns me") { }\n'})
    g = test_inventory.extract(_ctx(root))
    assert not list(g.nodes("TestCase"))
    assert g.meta["cpp"]["tests_skipped_ambiguous"] == 1


def test_test_macro_bodies_are_test_symbols_that_resolve_calls(tmp_path):
    g = S.build(tmp_path, {**LIB, **FRAMEWORK_FILES})
    t = S.symbols(g)["tests/gtest_calc.cc::CalcSuite.Adds"]
    assert t.props["kind"] == "test" and t.props["framework"] == "gtest"
    assert ("tests/gtest_calc.cc::CalcSuite.Adds", "src/calc.cc::add") in S.calls(g)


def test_python_and_js_inventory_is_byte_identical_with_and_without_cpp_files(tmp_path):
    py = {"tests/test_a.py": "def test_one():\n    pass\n", "web/a.test.js": "it('works', () => {});\n"}
    a = test_inventory.extract(_ctx(S.make_repo(tmp_path / "a", py))).to_dict()
    b = test_inventory.extract(_ctx(S.make_repo(tmp_path / "b", {**py, **LIB, "tests/gtest_calc.cc": FRAMEWORK_FILES["tests/gtest_calc.cc"]}))).to_dict()

    def only(d, fw):
        return sorted(json.dumps(n, sort_keys=True) for n in d["nodes"] if n["properties"].get("framework") in fw)
    assert only(a, ("pytest", "js")) == only(b, ("pytest", "js")) and len(only(a, ("pytest", "js"))) == 2
    assert [n["properties"]["framework"] for n in b["nodes"] if n["properties"].get("framework") == "gtest"] == ["gtest"]
    assert subprocess.run(["git", "status", "--short"], cwd=tmp_path / "a", capture_output=True).returncode == 0
