"""DKB-005: literal messages in throw, assert and log macros become ErrorSignatures; error-return codes do not (ADR D4)."""
from __future__ import annotations

import subprocess
from pathlib import Path

import cpp_support as S

FILES = {
    "src/block.cc": ('#include <stdexcept>\nvoid ReadBlock(int n) {\n  if (n < 0) throw std::runtime_error("block checksum mismatch");\n}\n'
                     'Status Verify(int n) {\n  return Status::Corruption("block checksum mismatch");\n}\n'
                     'void Check(int n) {\n  assert(n > 0 && "block length must be positive");\n}\n'
                     'void Dynamic(const std::string &msg) {\n  throw Err(msg);\n}\n'
                     'void Rethrow() {\n  try { Check(1); } catch (...) { throw; }\n}\n'
                     'void Quiet() {\n  static_assert(sizeof(int) == 4, "int width");\n}\n'
                     'void Log() {\n  LOG_ERR("device 192.0.2.7 unreachable: %d", 5);\n  return -EINVAL;\n}\n'),
    "src/other.cc": "void Unrelated() {\n  int x = 1;\n}\n",
}


def _edges(g, verb):
    return {(e.src, e.source) for e in g.edges(verb)}


def test_throw_assert_and_log_macro_literals_become_signatures_and_return_codes_do_not(tmp_path):
    g = S.build(tmp_path, FILES)
    assert _edges(g, "RAISES") == {("src/block.cc::ReadBlock", "cpp-throw"), ("src/block.cc::Check", "cpp-assert")}
    assert _edges(g, "LOGS") == {("src/block.cc::Log", "cpp-log-macro")}
    sigs = {n.props["message_template"]: n.props for n in g.nodes("ErrorSignature")}
    assert sigs["block checksum mismatch"]["label"] == "std::runtime_error" and sigs["block checksum mismatch"]["kind"] == "raised"
    assert sigs["block length must be positive"]["label"] == "assert"
    assert sigs["device 192.0.2.7 unreachable: %d"]["kind"] == "logged", "placeholders stay verbatim"
    assert "src/block.cc::Verify" not in {e.src for e in g.edges("RAISES")}, "Status::Corruption(...) is an error-return, excluded"
    assert not [n for n in g.nodes("ErrorSignature") if n.props["message_template"] in (None, "int width")]


def test_dynamic_message_creates_no_signature_and_is_counted(tmp_path):
    g = S.build(tmp_path, FILES)
    dyn = S.symbols(g)["src/block.cc::Dynamic"]
    assert dyn.props["unattributed_errors"] == 1
    assert "src/block.cc::Dynamic" not in {e.src for e in g.edges("RAISES")}
    assert "unattributed_errors" not in S.symbols(g)["src/block.cc::Rethrow"].props, "bare `throw;` is ignored"
    assert "unattributed_errors" not in S.symbols(g)["src/block.cc::Quiet"].props, "static_assert is ignored"


def test_error_pack_ranks_the_raiser_first_and_says_what_it_cannot_attribute(tmp_path, monkeypatch):
    _api, packer = S.api(tmp_path, FILES, monkeypatch)
    text = packer.error("block checksum mismatch")
    assert "ReadBlock" in text
    assert "Verify" not in text and "Unrelated" not in text, "no symbol that does not hold the string"
    first = text.index("ReadBlock")
    assert all(text.find(x) in (-1,) or text.index(x) > first for x in ("Check", "Log"))
    dyn = packer.error("device 192.0.2.7 unreachable: 5")
    assert "Log" in dyn
    coverage = _api.rca_trace("block checksum mismatch")["coverage"]
    assert coverage["complete"] in (True, False)


def test_pack_coverage_text_counts_unattributed_messages(tmp_path, monkeypatch):
    api, packer = S.api(tmp_path, FILES, monkeypatch)
    i, _ = api._resolve("src/block.cc::Dynamic")
    text = packer.coverage([i], set())
    assert "1 `throw` or `assert` site(s)" in text and "not a literal" in text
    assert api._coverage([i])["unattributed_errors"] == 1


def test_ontology_changes_only_the_raises_description_and_the_symbol_properties():
    root = Path(__file__).resolve().parents[1]
    from devkb.model import NODE_TYPES, VERBS
    ontology = (root / "devkb/ontology.md").read_text()
    raises = next(ln for ln in ontology.splitlines() if ln.startswith("| `RAISES`"))
    assert "throw" in raises and "assert" in raises and "error-return" in raises
    assert not {"Function", "Class", "Enum", "Namespace", "Include"} & set(NODE_TYPES), "no node type added (ADR-SDP-DEVKB-001)"
    assert not {"THROWS", "INCLUDES", "INHERITS", "EXTENDS", "CONTAINS", "OVERRIDES"} & set(VERBS), "no edge verb added"
    for prop in ("incomplete_reasons", "unattributed_errors", "overload_count", "framework"):
        assert f"`{prop}`" in ontology
