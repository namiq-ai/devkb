"""#135: a Python call is counted against a function only when it could reach it.

A name that several symbols share (a function, a same-named method, an attribute, a keyword argument) used to make every
one of them Incomplete: every unattributed call under the short name, anywhere, was charged to each symbol."""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from devkb import build_symbols  # noqa: E402

FILES = {
    "app/__init__.py": "",
    "app/paths.py": "def repo_path(p):\n    return p.strip('/')\n\n\ndef clean(p):\n    return repo_path(p)\n",
    "app/other.py": ("class Config:\n    repo_path = 'x'\n\n    def repo_path_of(self, root, kind):\n        return root\n\n"
                     "class Tools:\n    def repo_path(self, root, kind):\n        return root\n"),
    "app/use.py": ("from app.paths import clean, repo_path\nfrom app.other import Config, Tools\n\n\n"
                   "def run(ctx, thing):\n"
                   "    value = ctx.repo_path          # an attribute read\n"
                   "    show(repo_path=value)          # a keyword argument\n"
                   "    a = Config().repo_path\n"
                   "    b = Tools().repo_path('a', 'b')  # a receiver of a known class\n"
                   "    c = thing.repo_path('a', 'b')    # unknown receiver: may be Tools.repo_path, never the function\n"
                   "    return clean(value), repo_path(value), a, b, c\n\n\n"
                   "def show(**kw):\n    return kw\n"),
    "app/elsewhere.py": "def go(s, t):\n    return s.repo_path(1, 2, 3, 4)\n",
}


def _graph(tmp_path: Path):
    for rel, text in FILES.items():
        (tmp_path / rel).parent.mkdir(parents=True, exist_ok=True)
        (tmp_path / rel).write_text(text)
    for cmd in (["init", "-q"], ["add", "-A"], ["-c", "user.email=t@example.com", "-c", "user.name=T", "commit", "-qm", "x"]):
        subprocess.run(["git", *cmd], cwd=tmp_path, check=True, capture_output=True)
    return {n.natural_key: n.props for n in build_symbols.extract(tmp_path).nodes("Symbol")}


def test_a_shared_name_used_as_attribute_keyword_and_method_does_not_make_the_function_incomplete(tmp_path):
    nodes = _graph(tmp_path)
    fn = nodes["app/paths.py::repo_path"]
    assert not fn.get("unresolved_calls"), "no call that could reach the function is unattributed"
    assert not fn.get("unresolved_files")


def test_the_method_keeps_the_call_on_an_unknown_receiver_that_fits_it(tmp_path):
    nodes = _graph(tmp_path)
    method = nodes["app/other.py::Tools.repo_path"]
    assert method["unresolved_calls"] == 1 and method["unresolved_files"] == ["app/use.py"], \
        "`thing.repo_path('a', 'b')` may be this method; the 4-argument call cannot bind to it; the known `Tools()` is resolved"
