"""#121 (SPEC-DKB-004 F6): definitions behind a project's namespace, export and attribute macros are symbols. A namespace-opening macro written
before `namespace` (`FMT_BEGIN_NAMESPACE namespace detail {`) once turned the whole head into one unknown construct and everything inside it
was lost (fmt's args.h had no symbols). Each fixture fails on 3d11db7 where it names a head shape. Fixture code is synthetic."""
from __future__ import annotations

import cpp_support as S


def _names(tmp_path, text):
    return sorted(k.split("::")[-1] for k in S.symbols(S.build(tmp_path, {"a.h": text})))


def test_a_namespace_macro_before_namespace_does_not_hide_what_is_inside(tmp_path):
    names = _names(tmp_path, "FMT_BEGIN_NAMESPACE\nnamespace detail {\nint f() { return 1; }\n}\nFMT_END_NAMESPACE\n")
    assert names == ["f"], names


def test_an_export_macro_before_a_class_or_template_keeps_its_members(tmp_path):
    names = _names(tmp_path, "FMT_EXPORT class K {\n public:\n  int g() { return 1; }\n};\n"
                             "FMT_BEGIN_EXPORT\ntemplate <typename T> struct node { int h() { return 1; } };\nFMT_END_EXPORT\n")
    assert {"K", "K.g", "node", "node.h"} <= set(names), names


def test_attribute_macros_inside_declaration_specifiers_and_parameter_lists(tmp_path):
    text = ("struct V {\n  constexpr FMT_INLINE V() : n_() {}\n  FMT_INLINE V(int x FMT_BUILTIN) : n_(x) {}\n"
            "  FMT_DEPRECATED operator int() const { return 1; }\n  FMT_CONSTEXPR auto operator++(int) -> V& { return *this; }\n  int n_;\n};\n"
            "MY_INLINE MY_CONSTEXPR20 int shown(int a) { return a; }\nint MYLIB_CALL later(int a) { return a; }\n")
    names = set(_names(tmp_path, text))
    assert {"V.V", "V.operator int", "V.operator++", "shown", "later"} <= names, names


def test_a_lower_case_word_is_never_blanked_as_a_macro(tmp_path):
    names = _names(tmp_path, "namespace detail {\nclass inline_holder {\n public:\n  int get() { return 1; }\n};\n}\n")
    assert "inline_holder.get" in names, names
