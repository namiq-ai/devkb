"""#288: environment reads and writes in every form are not a record's string-key uses; a plain dict's are still."""
import ast

from devkb import build_symbols


def keys(src):
    return sorted((k, kind) for _w, k, kind, _l in build_symbols._uses_in_tree(ast.parse(src))[1])


def test_every_environment_form_is_excluded():
    src = ('import os\n\n\ndef f():\n    a = os.environ["ZZ1"]\n    b = "ZZ2" in os.environ\n    c = "ZZ3" not in os.environ\n'
           '    os.environ["ZZ4"] = "x"\n    os.environ["ZZ5"] += "y"\n    d = os.environ.get("ZZ6")\n    e = os.environ.setdefault("ZZ7", "1")\n'
           '    del os.environ["ZZ8"]\n    g = os.getenv("ZZ9")\n')
    assert keys(src) == [], keys(src)


def test_a_record_of_the_same_shape_is_still_a_key_use():
    src = ('def f(rec):\n    a = rec["status"]\n    b = "owner" in rec\n    rec["count"] += 1\n    rec["new"] = 1\n')
    assert keys(src) == [("count", "read"), ("count", "write"), ("new", "write"), ("owner", "read"), ("status", "read")], keys(src)   # `+= 1` reads, then writes (#202)


def test_an_environ_imported_by_name_is_excluded_too():
    assert keys('from os import environ\n\n\ndef f():\n    return environ["ZZ1"], "ZZ2" in environ\n') == []
