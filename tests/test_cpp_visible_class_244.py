"""#244: when several classes bear one name (alternate platform headers, a documentation header), a call resolves to the one the calling file
includes. Fixture code is synthetic."""
from __future__ import annotations

import cpp_support as S

FILES = {
    "port_real.h": "class Mutex {\n public:\n  void Lock();\n};\n",
    "port_example.h": "class Mutex {\n public:\n  void Lock();\n};\n",
    "real.cc": '#include "port_real.h"\nvoid Mutex::Lock() {}\n',
    "example.cc": '#include "port_example.h"\nvoid Mutex::Lock() {}\n',
    "db.h": '#include "port_real.h"\nclass Db {\n public:\n  void Open();\n  Mutex mu_;\n};\n',
    "db.cc": '#include "db.h"\nvoid Db::Open() { mu_.Lock(); }\n',
}


def test_a_member_of_an_ambiguously_named_class_resolves_to_the_included_one(tmp_path):
    g = S.build(tmp_path, FILES)
    targets = {dst for src, dst in S.calls(g) if src == "db.cc::Db.Open"}
    assert targets == {"real.cc::Mutex.Lock"}, targets


def test_with_no_include_to_tell_them_apart_it_stays_unresolved(tmp_path):
    files = dict(FILES)
    files["db.h"] = "class Db {\n public:\n  void Open();\n  Mutex mu_;\n};\n"       # includes neither header
    g = S.build(tmp_path, files)
    assert not {dst for src, dst in S.calls(g) if src == "db.cc::Db.Open"}
