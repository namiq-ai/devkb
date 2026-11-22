"""SPEC-DKB-002 epic 1: C and C++ are separate rule profiles that each report their own Complete (ADR-DEVKB-009 D7)."""
from __future__ import annotations

import re
import tomllib
from pathlib import Path

import cpp_support as S
import profile_support as P
import pytest

from devkb import cpp_resolve, cpp_symbols
from devkb.packs import Packer

ROOT = Path(__file__).resolve().parents[1]


# ── story 1.1: language and linkage on every File and Symbol ──────────────────────────────────────────────
def missing_language(g) -> list[str]:
    """C/C++ File and Symbol nodes without `language`."""
    return [n.natural_key for t in ("File", "Symbol") for n in g.nodes(t) if n.source == "cpp-symbols" and "language" not in n.props]


def test_a_c_a_cpp_and_a_plain_header_file_each_carry_their_language(tmp_path):
    g = P.build(tmp_path, "profiles/basic")
    langs = {n.natural_key: n.props["language"] for n in g.nodes("File") if n.source == "cpp-symbols"}
    assert langs == {"a.c": "c", "b.cpp": "cpp", "c.h": "c"}
    for n in S.symbols(g).values():
        assert n.props["language"] == langs[n.natural_key.split("::")[0]]
    assert P.props(g, "a.c::hidden")["linkage"] == "internal"
    assert P.props(g, "a.c::visible")["linkage"] == "c"
    assert P.props(g, "b.cpp::cxx_fn")["linkage"] == "cpp"


def test_language_on_every_node(tmp_path):
    g = P.build(tmp_path, "profiles/basic")
    assert missing_language(g) == []
    # seeded: an extractor that drops the property for one file is caught
    victim = next(n for n in g.nodes("Symbol") if n.natural_key.startswith("b.cpp::"))
    del victim.props["language"]
    assert missing_language(g) == [victim.natural_key]


def test_a_repository_with_no_c_or_cpp_file_builds_the_same_graph(tmp_path):
    """Python and TypeScript nodes get no `language`, and the graph equals the one the code built before ADR-DEVKB-009."""
    g = P.build(tmp_path, "profiles/python_ts")
    golden = (P.FIXTURES / "profiles" / "python_ts.golden.json").read_text()
    import json
    assert P.graph_dict(g) == json.loads(golden)
    assert all("language" not in n.props for n in g.nodes())


def test_the_ontology_names_the_new_properties_and_the_adr_is_accepted():
    onto = (ROOT / "devkb" / "ontology.md").read_text()
    for prop in ("language", "linkage", "abi_exported", "boundary_kind", "consumed_by_cpp"):
        assert f"`{prop}`" in onto, prop
    adr = (ROOT / "docs" / "adr" / "ADR-DEVKB-009_language-profiles-and-boundaries.md").read_text()
    assert re.search(r"^status: accepted", adr, re.M)


# ── story 1.2: a .h file is read by what it contains and what includes it ───────────────────────────────────
def test_header_language_rules(tmp_path):
    g = P.build(tmp_path, "profiles/headers")
    files = {n.natural_key: n for n in g.nodes("File") if n.source == "cpp-symbols"}
    lang = {k: n.props["language"] for k, n in files.items()}
    assert lang["ns.h"] == lang["tpl.h"] == lang["cls.h"] == "cpp"                    # constructs outside a guard
    assert lang["guarded.h"] == "c" and files["guarded.h"].props["consumed_by_cpp"] is True
    assert lang["only_cpp.h"] == "cpp"                                                  # only C++ includers
    assert lang["mixed.h"] == "c" and lang["lonely.h"] == "c"
    assert lang["words.h"] == "c" and lang["colons.h"] == "c"                           # words in comments and a lone `::`
    assert "consumed_by_cpp" not in files["cls.h"].props and "consumed_by_cpp" not in files["lonely.h"].props


def test_the_header_rule_is_one_function_of_text_and_includers():
    m = cpp_symbols.mask_source('#ifdef __cplusplus\nextern "C" {\n#endif\nint f(void);\n#ifdef __cplusplus\n}\n#endif\n')
    assert cpp_symbols.header_facts(m) == (False, True)
    assert cpp_symbols.header_language((False, False), ["cpp", "cpp"]) == ("cpp", False)
    assert cpp_symbols.header_language((False, False), ["cpp", "c"]) == ("c", False)
    assert cpp_symbols.header_language((True, True), []) == ("cpp", False)


# ── story 1.3: the C profile resolves through linkage ───────────────────────────────────────────────────────
def test_a_static_function_resolves_only_inside_its_own_file(tmp_path):
    e = P.edges(P.build(tmp_path, "profiles/c_linkage"))
    assert ("a.c::run_a", "a.c::helper") in e and ("b.c::run_b", "b.c::helper") in e
    assert not [k for k in e if k[0] == "c.c::run_c"], "c.c has no helper: the call is unresolved"


def test_an_extern_function_resolves_repository_wide_only_when_unique(tmp_path, monkeypatch):
    g = P.build(tmp_path, "profiles/c_linkage")
    e = P.edges(g)
    assert ("main.c::main", "a.c::init") in e
    assert not [k for k in e if k[0] == "main.c::main" and k[1].endswith("dup")]
    api, packer = P.api(tmp_path / "second", "profiles/c_linkage", monkeypatch)
    assert api.callers("a.c::dup")["coverage"]["complete"] is False


def test_function_pointer_tables_are_unresolved_indirect_references(tmp_path, monkeypatch):
    api, packer = P.api(tmp_path, "profiles/c_linkage", monkeypatch)
    for fn in ("my_read", "on_a", "on_b"):
        cov = api.callers(fn)["coverage"]
        assert cov["complete"] is False and "indirect-reference" in cov["reasons"], fn
        assert "ops.c" in cov["search_files"], fn
    assert "indirect-reference" in packer.refactor("on_a")


def test_c_has_no_receivers(tmp_path):
    g = P.build(tmp_path, "profiles/c_linkage")
    assert not [e for e in g.edges("CALLS") if e.source == "cpp-typed-receiver"]
    assert not [k for k in P.edges(g) if k[0] == "recv.c::use"]
    assert P.props(g, "recv.c::fetch")["unresolved_calls"] == 1


def test_a_seeded_wrong_c_rule_is_caught(tmp_path, monkeypatch):
    """A C profile that treats `static` as `extern` links `c.c`'s call to a static helper: the fixture's truth says it must not."""
    orig = cpp_resolve.Repo.__init__

    def init(self, units):
        orig(self, units)
        for u in units:
            for s in u.syms.values():
                if s.kind == "function" and s.linkage == "internal":
                    s.linkage = "c"
                    self.c_linkage.setdefault(s.short, []).append((u.path, s))

    monkeypatch.setattr(cpp_resolve.Repo, "__init__", init)
    g = P.build(tmp_path, "profiles/c_linkage")
    assert [k for k in P.edges(g) if k[0] == "c.c::run_c"] == [], "the seeded fault must be visible as a false edge"


# ── story 1.4: Complete by the rules of the symbol's own language ───────────────────────────────────────────
def test_c_and_cpp_packs_state_different_limits(tmp_path, monkeypatch):
    api, packer = P.api(tmp_path, "profiles/coverage", monkeypatch)
    c_pack = packer.refactor("api_c")
    cpp_pack = packer.refactor("get", )
    py_pack = packer.refactor("py_fn")
    assert cpp_symbols.C_LIMITS_TEXT in c_pack and cpp_symbols.CXX_LIMITS_TEXT not in c_pack
    for word in ("overload", "receiver"):
        assert word not in c_pack.lower()
    for word in ("macro generates", "function pointer", "ops table"):
        assert word in c_pack
    assert cpp_symbols.CXX_LIMITS_TEXT in cpp_pack and cpp_symbols.C_LIMITS_TEXT not in cpp_pack
    assert cpp_symbols.CXX_LIMITS_TEXT not in py_pack and cpp_symbols.C_LIMITS_TEXT not in py_pack


def test_the_reply_says_which_profile_judged_it(tmp_path, monkeypatch):
    api, _ = P.api(tmp_path, "profiles/coverage", monkeypatch)
    cov = api.callers("cb")["coverage"]
    assert cov["complete"] is False and cov["profile"] == "c" and "indirect-reference" in cov["reasons"]
    assert api.callers("get")["coverage"]["profile"] == "cpp"
    assert "profile" not in api.callers("py_fn")["coverage"]


def test_a_c_symbol_with_no_unresolved_call_is_complete_under_the_c_profile(tmp_path, monkeypatch):
    api, packer = P.api(tmp_path, "profiles/coverage", monkeypatch)
    pack = packer.refactor("helper")
    assert "**Complete.**" in pack and cpp_symbols.C_LIMITS_TEXT in pack
    assert api.callers("helper")["coverage"]["complete"] is True


# ── story 1.5: dialect keywords, never a compiler ───────────────────────────────────────────────────────────
def test_definitions_with_dialect_keywords_are_found_with_their_proving_line(tmp_path):
    g = P.build(tmp_path, "profiles/dialect")
    text = P.files_of("profiles/dialect")["dialect.c"].splitlines()
    names = {"ram_fn", "isr_a", "isr_b", "fast_fn", "kept_fn", "weak_fn", "svc_fn", "asm_fn"}
    found = {n.props["qualified_name"]: n.props for n in S.symbols(g).values() if n.props["kind"] == "function"}
    assert names <= set(found)
    for name in names:
        assert name in text[found[name]["line_start"] - 1], name


def test_dialect_text_is_not_a_call_or_a_definition(tmp_path):
    g = P.build(tmp_path, "profiles/dialect")
    assert not {"aligned", "__attribute__", "__asm__", "section", "__svc"} & {n.props["qualified_name"] for n in S.symbols(g).values()}


def test_the_tolerated_keywords_live_in_one_table_and_each_is_used_by_the_fixture():
    text = P.files_of("profiles/dialect")["dialect.c"]
    for kw in cpp_symbols.DIALECT_KEYWORDS + cpp_symbols.DIALECT_PAREN:
        assert re.search(r"\b" + re.escape(kw) + r"\b", text), f"{kw} is in the table but no fixture line uses it"


def test_no_compiler_is_ever_invoked_by_the_scanner():
    pattern = re.compile(r"subprocess\.\w+\(\s*\[?\s*[\"'](?:gcc|g\+\+|clang|clang\+\+|cc|c\+\+|armcc|iccarm)[\"']")
    offenders = [str(p) for p in (ROOT / "devkb").rglob("*.py") if pattern.search(p.read_text())]
    assert offenders == []
    assert tomllib.loads((ROOT / "pyproject.toml").read_text())["project"]["dependencies"] == ["pyyaml>=6"]


def test_the_compiler_appears_only_as_verification_flags():
    import importlib.util
    spec = importlib.util.spec_from_file_location("truth_clang", ROOT / "bench" / "cpp" / "truth_clang.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)          # imports without libclang: the import is lazy
    opts = mod.parse_args(["repo", "out.json", "-D__interrupt=", "-D", "__ramfunc=", "-Iinc", "--std", "c++14"])
    assert opts["defs"] == ["__interrupt=", "__ramfunc="] and opts["incs"] == ["inc"] and opts["std"] == "c++14"
    assert not re.search(r"^\s*(?:from|import)\s+devkb", (ROOT / "bench" / "cpp" / "truth_clang.py").read_text(), re.M)


def test_the_readme_names_each_c_limit_and_each_is_demonstrated():
    row = next(ln for ln in (ROOT / "README.md").read_text().splitlines() if ln.startswith("| C, C++"))
    assert "ops table" in row and "ops table" in cpp_symbols.C_LIMITS_TEXT          # demonstrated: the ops-table tests above
    assert "a definition a macro generates is not seen" in row and "a definition a macro generates is not seen" in cpp_symbols.C_LIMITS_TEXT
    assert "Complete only for the languages read" in row


def test_this_repositorys_own_python_gets_none_of_the_c_properties(tmp_path):
    """The Python source of this repository, built as a repository of its own: no C/C++ property and no C/C++ node appears."""
    files = {f"devkb/{p.name}": p.read_text() for p in sorted((ROOT / "devkb").glob("*.py"))}
    g = S.build(tmp_path, files)
    new = {"language", "linkage", "abi_exported", "boundary_kind", "consumed_by_cpp"}
    assert not [n.natural_key for n in g.nodes() if new & set(n.props)]
    assert not [n for n in g.nodes() if n.source in ("cpp-symbols", "cpp-config")]
    assert not [e for e in g.edges() if e.source.startswith("cpp-") or e.source in ("extern-c", "ctypes", "cffi", "pyc-api", "pybind11")]
