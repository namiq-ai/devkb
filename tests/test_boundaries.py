"""SPEC-DKB-002 epic 2: a call that crosses a language is a graph edge, and an exported symbol says who may still call it."""
from __future__ import annotations

import profile_support as P
import pytest

from devkb import boundaries, cpp_graph

CROSS = ("extern-c", "ctypes", "cffi", "pyc-api", "pybind11")


def cross(g) -> dict[tuple[str, str], object]:
    return {(e.src, e.dst): e for e in g.edges("CALLS") if e.source in CROSS}


def reasons(g, key: str) -> list[str]:
    return P.props(g, key).get("incomplete_reasons", [])


# ── story 2.1: an exported or JNI-named function stops claiming the strong Complete ───────────────────────────
def test_a_jni_named_function_is_exported_and_its_pack_is_qualified(tmp_path, monkeypatch):
    api, packer = P.api(tmp_path, "boundaries/defect", monkeypatch)
    p = P.props(api_graph(tmp_path / "g", "boundaries/defect"), "calc.c::Java_demo_Calc_nativeAdd")
    assert p["abi_exported"] is True and p["boundary_kind"] == "jni"
    for pack in (packer.file("calc.c"), packer.refactor("Java_demo_Calc_nativeAdd")):
        assert "**Complete for the languages read** (c, python)" in pack
        assert "Callers may exist in languages not read" in pack
        assert "**Complete.**" not in pack


def api_graph(tmp_path, name, extra=None):
    return P.build(tmp_path, name, extra)


def test_a_non_static_c_function_and_a_pyinit_function_are_exported(tmp_path, monkeypatch):
    g = P.build(tmp_path, "boundaries/defect")
    assert P.props(g, "calc.c::add_ints")["boundary_kind"] == "c-abi"
    assert P.props(g, "calc.c::PyInit_calc")["boundary_kind"] == "pyinit"
    api, packer = P.api(tmp_path / "api", "boundaries/defect", monkeypatch)
    for name in ("add_ints", "PyInit_calc"):
        assert "Callers may exist in languages not read" in packer.refactor(name), name


def test_a_static_function_keeps_the_strong_complete(tmp_path, monkeypatch):
    g = P.build(tmp_path, "boundaries/defect")
    assert not P.props(g, "calc.c::local_sum").get("abi_exported")
    api, packer = P.api(tmp_path / "api", "boundaries/defect", monkeypatch)
    pack = packer.refactor("local_sum")
    assert "**Complete.**" in pack and "languages read" not in pack


def test_c_linkage_inside_a_cpp_file_is_exported_and_a_method_is_not(tmp_path):
    g = P.build(tmp_path, "boundaries/defect_cpp")
    wrap = P.props(g, "wrap.cpp::wrap_add")
    assert (wrap["language"], wrap["linkage"], wrap["abi_exported"]) == ("cpp", "c", True)
    method = P.props(g, "wrap.cpp::Calc.add")
    assert "abi_exported" not in method


def test_the_reply_carries_the_qualifier_as_data(tmp_path, monkeypatch):
    api, _ = P.api(tmp_path, "boundaries/defect", monkeypatch)
    cov = api.callers("add_ints")["coverage"]
    assert cov["complete"] is True and cov["qualified"] is True
    assert cov["languages_read"] == ["c", "python"] and cov["boundary_kind"] == "c-abi"


def test_the_defect_fixture_shows_the_old_claim_is_gone(tmp_path, monkeypatch):
    """The owner's defect: a JNI-named and a ctypes-called function both said the strong Complete with the foreign callers missing."""
    api, packer = P.api(tmp_path, "boundaries/defect", monkeypatch)
    for name in ("Java_demo_Calc_nativeAdd", "add_ints"):
        assert "Every call site" not in packer.refactor(name).split("## Coverage")[1].split("C limits")[0], name


# ── story 2.2: extern "C" between C++ and C is linked once, with its mechanism named ──────────────────────────
def test_a_cpp_call_into_a_c_function_links_with_source_extern_c(tmp_path):
    g = P.build(tmp_path, "boundaries/extern_c")
    pair = [e for e in g.edges("CALLS") if (e.src, e.dst) == ("app.cpp::app_main", "lib.c::lib_add")]
    assert len(pair) == 1, "no second edge from an older rule for the same pair"
    assert (pair[0].source, pair[0].confidence, pair[0].evidence_ref) == ("extern-c", 0.9, "app.cpp:2")


def test_a_c_call_into_a_cpp_function_with_c_linkage_links_the_same_way(tmp_path):
    e = cross(P.build(tmp_path, "boundaries/extern_c"))[("main.c::c_main", "cb.cpp::cb_run")]
    assert e.source == "extern-c"


def test_a_name_that_is_not_unique_links_nothing(tmp_path, monkeypatch):
    g = P.build(tmp_path, "boundaries/extern_c")
    assert not [k for k in P.edges(g) if k[0] == "dupcaller.c::use_dup"]
    assert "ambiguous-abi-name" in reasons(g, "dup_a.cpp::dup") and "ambiguous-abi-name" in reasons(g, "dup_b.cpp::dup")
    api, _ = P.api(tmp_path / "api", "boundaries/extern_c", monkeypatch)
    assert api.callers("dup_a.cpp::dup")["coverage"]["complete"] is False


def test_a_cpp_name_does_not_match_a_c_name(tmp_path):
    g = P.build(tmp_path, "boundaries/extern_c")
    assert not [k for k in cross(g) if k[0] == "app2.cpp::probe"]


def test_a_name_defined_outside_the_repository_is_not_a_boundary(tmp_path):
    g = P.build(tmp_path, "boundaries/extern_c")
    assert not [e for e in g.edges("CALLS") if e.src == "app2.cpp::probe" and not e.dst.endswith("::foo")]
    assert not [u for u in g.meta["boundaries"]["unresolved"] if u["abi_name"] in ("strlen", "vendor_fn")]
    assert not P.props(g, "app2.cpp::probe").get("incomplete_reasons")


def test_a_dynamic_lookup_is_unresolved_and_counted(tmp_path, monkeypatch):
    g = P.build(tmp_path, "boundaries/extern_c")
    for fn in ("by_variable", "by_literal"):
        assert "dynamic-import" in reasons(g, f"plug.c::{fn}")
        assert not [k for k in P.edges(g) if k[0] == f"plug.c::{fn}"]
    assert g.meta["boundaries"]["dynamic_lookups"] == 2
    api, packer = P.api(tmp_path / "api", "boundaries/extern_c", monkeypatch)
    assert "2 dynamic lookup(s)" in packer.refactor("lib_add")
    assert api.callers("lib_add")["coverage"]["dynamic_lookups"] == 2


def test_a_repository_without_a_boundary_has_none(tmp_path):
    g = P.build(tmp_path, "profiles/basic")
    assert not cross(g)
    assert g.meta["boundaries"] == {"links": 0, "dynamic_lookups": 0, "unresolved": []}


def test_the_resolver_alone_takes_the_first_export_when_uniqueness_is_off():
    recs = [boundaries.Record("export", "f", "extern-c", "a.c", 1, "a.c::f", language="c"),
            boundaries.Record("export", "f", "extern-c", "b.c", 1, "b.c::f", language="c"),
            boundaries.Record("import", "f", "extern-c", "m.cpp", 3, "m.cpp::g", language="cpp")]
    assert boundaries.resolve(recs).links == []
    assert [lk.callee for lk in boundaries.resolve(recs, unique=False).links] == ["a.c::f"]


# ── story 2.4: ctypes and cffi ──────────────────────────────────────────────────────────────────────────────
def test_a_ctypes_call_links_with_source_ctypes(tmp_path, monkeypatch):
    e = cross(P.build(tmp_path, "boundaries/ctypes"))[("use.py::go", "calc.c::add_ints")]
    assert (e.source, e.confidence) == ("ctypes", 0.8)
    api, packer = P.api(tmp_path / "api", "boundaries/ctypes", monkeypatch)
    assert api.callers("calc.c::add_ints")["direct"] == ["use.py::go", "use_cffi.py::go_cffi"]


def test_cffi_links_the_same_way(tmp_path):
    assert cross(P.build(tmp_path, "boundaries/ctypes"))[("use_cffi.py::go_cffi", "calc.c::add_ints")].source == "cffi"


def test_a_receiver_that_is_not_a_library_handle_is_not_a_boundary(tmp_path):
    g = P.build(tmp_path, "boundaries/ctypes")
    assert not [k for k in cross(g) if k[0] == "use.py::not_a_handle"]
    assert not reasons(g, "use.py::not_a_handle") if "incomplete_reasons" in P.props(g, "use.py::not_a_handle") else True


def test_a_name_held_in_a_variable_is_unresolved(tmp_path, monkeypatch):
    g = P.build(tmp_path, "boundaries/ctypes")
    assert not [k for k in P.edges(g) if k[0] == "use.py::dynamic" and k[1].startswith("calc.c")]
    assert reasons(g, "use.py::dynamic") == ["dynamic-import"]
    assert g.meta["boundaries"]["dynamic_lookups"] == 1
    api, _ = P.api(tmp_path / "api", "boundaries/ctypes", monkeypatch)
    assert api.callers("calc.c::add_ints")["coverage"]["dynamic_lookups"] == 1


def test_a_static_c_function_and_a_duplicated_name_are_never_targets(tmp_path):
    g = P.build(tmp_path, "boundaries/ctypes")
    assert not [k for k in cross(g) if k[0] in ("use.py::hidden", "use.py::twice")]


def test_the_note_lists_the_python_caller_with_its_mechanism(tmp_path, monkeypatch):
    api, packer = P.api(tmp_path, "boundaries/defect", monkeypatch)
    pack = packer.refactor("add_ints")
    assert "`use.py`" in pack and "(via ctypes)" in pack and "Callers may exist in languages not read" in pack


# ── story 2.5: PyMethodDef ──────────────────────────────────────────────────────────────────────────────────
def test_a_table_entry_is_an_export_under_its_python_name(tmp_path):
    g = P.build(tmp_path, "boundaries/pyc_api")
    p = P.props(g, "calc.c::py_add")
    assert (p["linkage"], p["abi_exported"], p["boundary_kind"]) == ("internal", True, "pyc-method")
    assert cross(g)[("use.py::go", "calc.c::py_add")].source == "pyc-api"


def test_the_table_reference_is_explained_and_another_reference_still_counts(tmp_path, monkeypatch):
    api, packer = P.api(tmp_path, "boundaries/pyc_api", monkeypatch)
    cov = api.callers("py_add")["coverage"]
    assert cov["complete"] is True and cov["qualified"] is True and "indirect-reference" not in cov.get("reasons", [])
    assert "Complete for the languages read" in packer.refactor("py_add")
    api2, _ = P.api(tmp_path / "again", "boundaries/pyc_api", monkeypatch,
                    extra={"extra.c": "extern int py_add(void);\nstatic int (*cb)(void) = py_add;\n"})
    assert api2.callers("py_add")["coverage"]["complete"] is False


def test_aliases_resolve_and_unknown_modules_do_not(tmp_path):
    g = P.build(tmp_path, "boundaries/pyc_api")
    e = cross(g)
    assert ("alias.py::go_alias", "calc.c::py_add") in e and ("from_import.py::go_from", "calc.c::py_add") in e
    assert not [k for k in e if k[0] == "other.py::go_other"]
    assert not [u for u in g.meta["boundaries"]["unresolved"] if u["file"] == "other.py"]


def test_two_entries_under_one_name_link_nothing(tmp_path):
    g = P.build(tmp_path, "boundaries/pyc_api")
    assert not [k for k in cross(g) if k[0] == "twice.py::go_twice"]
    assert {"file": "twice.py", "line": 5, "abi_name": "dbl.add", "mechanism": "pyc-api", "reason": "ambiguous-abi-name"} \
        in g.meta["boundaries"]["unresolved"]
    assert "ambiguous-abi-name" in reasons(g, "dbl.c::dbl_one")


# ── story 2.6: pybind11 ─────────────────────────────────────────────────────────────────────────────────────
def test_a_m_def_of_a_function_address_links_its_python_caller(tmp_path):
    g = P.build(tmp_path, "boundaries/pybind11")
    e = cross(g)[("use.py::go", "bind.cpp::add_ints")]
    assert (e.source, e.confidence) == ("pybind11", 0.8)
    assert P.props(g, "bind.cpp::add_ints")["boundary_kind"] == "pybind11"


def test_a_lambda_or_an_overload_set_is_not_guessed(tmp_path):
    g = P.build(tmp_path, "boundaries/pybind11")
    assert not [k for k in cross(g) if k[0] in ("use.py::go_sub", "use.py::go_mul")]
    unresolved = {(u["abi_name"], u["reason"]) for u in g.meta["boundaries"]["unresolved"]}
    assert ("demo.sub", "lambda-binding") in unresolved and ("demo.mul", "ambiguous-abi-name") in unresolved


def test_two_m_def_of_one_python_name_link_nothing(tmp_path):
    g = P.build(tmp_path, "boundaries/pybind11")
    assert not [k for k in cross(g) if k[0] == "use.py::go_twin"]
    assert ("twin.add", "ambiguous-abi-name") in {(u["abi_name"], u["reason"]) for u in g.meta["boundaries"]["unresolved"]}


def test_class_bindings_are_out_and_said_so(tmp_path, monkeypatch):
    g = P.build(tmp_path, "boundaries/pybind11")
    assert not P.props(g, "bind.cpp::K.go").get("abi_exported")
    api, packer = P.api(tmp_path / "api", "boundaries/pybind11", monkeypatch)
    pack = packer.refactor("K.go", path="bind.cpp")
    assert "py::class_" in pack and "not read" in pack


# ── story 2.8: Kconfig and devicetree as ConfigKey ──────────────────────────────────────────────────────────
def test_a_c_file_read_and_a_kconfig_declaration_meet_at_one_config_key(tmp_path):
    g = P.build(tmp_path, "boundaries/kconfig")
    reads = {(e.src_type, e.src, e.dst): e.evidence_ref for e in g.edges("READS")}
    assert reads[("File", "drivers/foo.c", "kconfig:CONFIG_FOO")].startswith("drivers/foo.c:")
    assert reads[("Symbol", "drivers/foo.c::foo_init", "kconfig:CONFIG_FOO")].startswith("drivers/foo.c:")
    assert ("Symbol", "drivers/foo.c::foo_init", "kconfig:CONFIG_FOO_BUF_SIZE") in reads
    decl = {(e.src, e.dst): e.evidence_ref for e in g.edges("DECLARES")}
    assert decl[("Kconfig", "kconfig:CONFIG_FOO")] == "Kconfig:1" and decl[("Kconfig", "kconfig:CONFIG_FOO_BUF_SIZE")] == "Kconfig:4"
    assert len([n for n in g.nodes("ConfigKey") if n.natural_key == "kconfig:CONFIG_FOO"]) == 1


def test_an_undeclared_option_is_still_a_read(tmp_path, monkeypatch):
    g = P.build(tmp_path, "boundaries/kconfig")
    assert ("Symbol", "drivers/foo.c::foo_init", "kconfig:CONFIG_BAR") in {(e.src_type, e.src, e.dst) for e in g.edges("READS")}
    assert not [e for e in g.edges("DECLARES") if e.dst == "kconfig:CONFIG_BAR"]
    api, packer = P.api(tmp_path / "api", "boundaries/kconfig", monkeypatch)
    pack = packer.file("drivers/foo.c")
    assert "`kconfig:CONFIG_BAR` — not declared in the repository" in pack
    assert "`kconfig:CONFIG_FOO` — declared in `Kconfig`" in pack


def test_comments_strings_and_if_zero_read_nothing(tmp_path):
    g = P.build(tmp_path, "boundaries/kconfig")
    assert "kconfig:CONFIG_BAZ" not in {n.natural_key for n in g.nodes("ConfigKey")}


def test_a_devicetree_label_meets_its_reader(tmp_path):
    g = P.build(tmp_path, "boundaries/kconfig")
    assert ("board.dts", "devicetree:foo") in {(e.src, e.dst) for e in g.edges("DECLARES")}
    assert ("Symbol", "drivers/foo.c::foo_dev", "devicetree:foo") in {(e.src_type, e.src, e.dst) for e in g.edges("READS")}
