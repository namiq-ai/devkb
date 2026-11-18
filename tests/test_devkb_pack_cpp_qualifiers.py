"""#132: `pack change` / `pack refactor` accept `Class::method` and `ns::Class::method`, as `symbol` does."""
from __future__ import annotations

import pytest

from tests import cpp_support as cs

FILES = {
    "a.h": "namespace ns {\nclass A {\n public:\n  int f(int x);\n  int g(int x);\n};\nclass B {\n public:\n  int g(int x);\n};\n}\n",
    "a.cc": '#include "a.h"\nnamespace ns {\nint A::f(int x) { return x + 1; }\nint A::g(int x) { return x; }\nint B::g(int x) { return x; }\n}\n',
    "use.cc": '#include "a.h"\nint use(ns::A& a) { return a.f(2); }\n',
}


@pytest.fixture
def packer(tmp_path, monkeypatch):
    return cs.api(tmp_path, FILES, monkeypatch)[1]


@pytest.mark.parametrize("name", ["A::f", "ns::A::f", "A.f"])
def test_change_resolves_every_spelling_to_one_symbol(packer, name):
    text = packer.change(name)
    assert "cannot resolve" not in text, text
    assert text.splitlines()[0] == packer.change("A.f").splitlines()[0]
    assert "use" in text


@pytest.mark.parametrize("name", ["A::f", "ns::A::f"])
def test_refactor_resolves_the_cpp_spelling(packer, name):
    text = packer.refactor(name)
    assert "cannot resolve" not in text and "use.cc" in text, text


def test_an_ambiguous_name_lists_its_candidates(packer):
    for text in (packer.change("g"), packer.refactor("g")):
        assert "cannot resolve" in text and "A.g" in text and "B.g" in text, text
