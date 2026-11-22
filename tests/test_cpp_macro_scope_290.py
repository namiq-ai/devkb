"""#290: a repository macro is expanded only in files that see it (define it, or include a header that does, at any depth), and not after an `#undef`.
Each negative fixture fails on 3d11db7 and passes after the fix. Fixture code is synthetic."""
from __future__ import annotations

import cpp_support as S


def _from(g, caller):
    return {dst for src, dst in S.calls(g) if src == caller}


def test_a_macro_does_not_leak_into_a_file_that_never_includes_its_header(tmp_path):
    files = {"legacy.h": "#define run(x) legacy_helper(x)\nvoid legacy_helper(int);\n",
             "legacy.cc": '#include "legacy.h"\nvoid legacy_helper(int) {}\nvoid old_user() { run(1); }\n',
             "modern.cc": "void run(int x) {}\nvoid new_user() { run(2); }\n"}
    g = S.build(tmp_path, files)
    assert "legacy.cc::legacy_helper" not in _from(g, "modern.cc::new_user")
    assert "modern.cc::run" in _from(g, "modern.cc::new_user"), "its own run() is a plain call"


def test_a_macro_stops_at_undef(tmp_path):
    files = {"a.h": "#define DEBUGONLY(x) dbg(x)\n", "fa.cc": "void dbg(int){}\n",
             "c.cc": '#include "a.h"\n#undef DEBUGONLY\nvoid DEBUGONLY(int);\nvoid use3() { DEBUGONLY(2); }\n',
             "e.cc": "void DEBUGONLY(int);\nvoid use5() { DEBUGONLY(2); }\n"}
    g = S.build(tmp_path, files)
    assert "fa.cc::dbg" not in _from(g, "c.cc::use3") and "fa.cc::dbg" not in _from(g, "e.cc::use5")


def test_a_macro_is_still_expanded_where_it_is_visible(tmp_path):
    files = {"m.h": "#define go(x) target(x)\n", "mid.h": '#include "m.h"\n', "t.cc": "void target(int) {}\n",
             "direct.cc": '#include "m.h"\nvoid a() { go(1); }\n',
             "deep.cc": '#include "mid.h"\nvoid b() { go(2); }\n',
             "own.cc": "#define own(x) target(x)\nvoid c() { own(3); }\n",
             "before.cc": '#include "m.h"\nvoid d() { go(4); }\n#undef go\nvoid e() { go(5); }\n'}
    g = S.build(tmp_path, files)
    for caller in ("direct.cc::a", "deep.cc::b", "own.cc::c", "before.cc::d"):
        assert "t.cc::target" in _from(g, caller), caller
    assert "t.cc::target" not in _from(g, "before.cc::e"), "after the #undef"
