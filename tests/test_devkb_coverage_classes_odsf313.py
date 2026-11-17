"""ODSF-313: base-class and self. resolution, answer coverage, exact error matching, and packs.

ADR-SDP-DEVKB-006 (CONTAINS/EXTENDS) is Proposed, so no new verb is emitted; calls resolved through a base are
ordinary CALLS tagged ast-typed-receiver-base."""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from devkb import build_symbols, process_api  # noqa: E402
from devkb.model import VERBS  # noqa: E402
from devkb.packs import Packer  # noqa: E402
from devkb.project_context import ProjectContext  # noqa: E402

FILES = {
    "app/__init__.py": "",
    "app/base.py": "class Store:\n    def save(self, x):\n        raise ValueError('a record without a name cannot be saved')\n",
    "app/store.py": ("from app.base import Store\n\n\nclass RuntimeStore(Store):\n    def add_edge(self, a, b):\n"
                     "        self.save(a)\n\n    def flush(self):\n        self.add_edge(1, 2)\n"),
    "app/routes.py": ("from app.store import RuntimeStore\n\n\n@router.post('/records')\ndef post_record(store: RuntimeStore):\n"
                      "    store.add_edge(1, 2)\n\n\ndef untyped(thing):\n    thing.add_edge(3, 4)\n"),
    "tests/test_store.py": "from app.store import RuntimeStore\n\n\ndef test_add():\n    RuntimeStore().add_edge(1, 2)\n",
    "package-lock.json": "{}\n",
}


def _repo(tmp_path: Path) -> Path:
    for rel, text in FILES.items():
        (tmp_path / rel).parent.mkdir(parents=True, exist_ok=True)
        (tmp_path / rel).write_text(text)
    for cmd in (["init", "-q"], ["add", "-A"], ["-c", "user.email=t@example.com", "-c", "user.name=T", "commit", "-qm", "x"]):
        subprocess.run(["git", *cmd], cwd=tmp_path, check=True, capture_output=True)
    return tmp_path


def test_methods_resolve_through_bases_and_self_and_classes_are_structured(tmp_path):
    g = build_symbols.extract(_repo(tmp_path))
    calls = {(e.src, e.dst) for e in g.edges("CALLS")}
    assert ("app/store.py::RuntimeStore.add_edge", "app/base.py::Store.save") in calls, "self.save() resolves on the base"
    assert ("app/store.py::RuntimeStore.flush", "app/store.py::RuntimeStore.add_edge") in calls
    assert ("app/routes.py::post_record", "app/store.py::RuntimeStore.add_edge") in calls
    via_base = {(e.src, e.dst) for e in g.edges("CALLS") if e.source == "ast-typed-receiver-base"}
    assert via_base == {("app/store.py::RuntimeStore.add_edge", "app/base.py::Store.save")}, "tagged so the audit can count it"
    assert "EXTENDS" not in VERBS and "CONTAINS" not in VERBS, "no new verb while ADR-SDP-DEVKB-006 is Proposed"
    node = next(n for n in g.nodes("Symbol") if n.natural_key == "app/store.py::RuntimeStore.add_edge")
    assert node.props["unresolved_calls"] == 1 and node.props["unresolved_files"] == ["app/routes.py"], "thing.add_edge() is unattributable"


def _api(tmp_path, monkeypatch):
    root = _repo(tmp_path)
    g = build_symbols.extract(root)
    store = root / ".devkb"
    store.mkdir()
    d = g.to_dict()
    (store / "nodes.jsonl").write_text("\n".join(json.dumps(n) for n in d["nodes"]) + "\n")
    (store / "edges.jsonl").write_text("\n".join(json.dumps(e) for e in d["edges"]) + "\n")
    head = subprocess.run(["git", "rev-parse", "HEAD"], cwd=root, capture_output=True, text=True).stdout.strip()
    (store / "manifest.json").write_text(json.dumps({"built_at": "2026-11-14T00:00:00+00:00", "git_head": head}))
    ctx = ProjectContext(code="TST", repo_root=root, ticket_prefix="TST", issues_dir=root / "issues", tests_dir=root / "tests",
                         sprint_dir=root / "h", devkb_dir=store, board_file=root / "b.md", wp_map_file=root / "w.json")
    monkeypatch.setattr(process_api, "resolve", lambda code: ctx)
    return process_api.ProcessAPI("TST", telemetry=False)


def test_list_answers_say_what_they_cannot_see(tmp_path, monkeypatch):
    api = _api(tmp_path, monkeypatch)
    r = api.call("callers", symbol="app/store.py::RuntimeStore.add_edge")
    assert r["coverage"] == {"complete": False, "unresolved_calls": 1, "search_files": [], "in_listed_files": True}, \
        "routes.py is already listed"
    s = api.call("refactor_scope", target="app/store.py::RuntimeStore.add_edge")
    assert s["coverage"]["complete"] is False
    assert api.call("callers", symbol="app/base.py::Store.save")["coverage"] == {"complete": True}
    assert process_api.is_generated_path("webapp/frontend/package-lock.json") and not process_api.is_generated_path("app/store.py")


def test_an_exact_message_names_only_its_raiser(tmp_path, monkeypatch):
    api = _api(tmp_path, monkeypatch)
    r = api.call("rca_trace", symptom="Saving fails: a record without a name cannot be saved")
    assert r["raisers"] == ["app/base.py::Store.save"] and "coverage" in r


def test_a_pack_carries_evidence_lines_coverage_and_freshness(tmp_path, monkeypatch):
    api = _api(tmp_path, monkeypatch)
    p = Packer(api)
    text = p.change("add_edge", "app/store.py")
    assert "`app/routes.py:6: store.add_edge(1, 2)`" in text, "each item carries the line that proves it"
    assert "app/routes.py::post_record" in text and "tests/test_store.py" in text
    assert "**Incomplete: calls under this name from 1 function(s)" in text and "None of the files below has changed since" in text
    (tmp_path / "app" / "routes.py").write_text(FILES["app/routes.py"] + "\n# edited\n")
    assert "Changed since, re-read these:" in Packer(api).change("add_edge", "app/store.py")
    err = p.error("a record without a name cannot be saved")
    assert "`app/base.py::Store.save`" in err and "## Route handlers that reach it (1)" in err


def test_a_pack_names_every_function_on_the_path_with_the_call_that_proves_it(tmp_path, monkeypatch):
    """A command-line tool has no route handlers; "what reaches it" is the list of functions on the call paths."""
    p = Packer(_api(tmp_path, monkeypatch))
    err = p.error("a record without a name cannot be saved")
    assert "## Functions that reach it, at any depth (3)" in err
    assert "- `app/store.py::RuntimeStore.add_edge` — `app/store.py:6: self.save(a)`" in err
    assert "`app/routes.py::post_record`" in err and "`app/store.py::RuntimeStore.flush`" in err


def test_a_repository_without_routes_gets_no_route_section(tmp_path, monkeypatch):
    monkeypatch.setitem(globals(), "FILES", {k: v for k, v in FILES.items() if k != "app/routes.py"})
    text = Packer(_api(tmp_path, monkeypatch)).change("add_edge", "app/store.py")
    assert "Route handlers" not in text and "## Functions that reach it, at any depth (1)" in text


def test_a_router_named_for_what_it_serves_still_declares_routes():
    import ast as _ast
    from devkb.build_symbols import _decorator_route
    dec = lambda src: _ast.parse(src).body[0].value  # noqa: E731
    assert _decorator_route(dec('public_router.post("/token")')) == ("POST", "/token")
    assert _decorator_route(dec('user_router.get("/me")')) == ("GET", "/me")
    assert _decorator_route(dec('bp.get("/x")')) == ("GET", "/x")
    assert _decorator_route(dec('cache.get("key")')) is None, "not a router"
    assert _decorator_route(dec('router.get(path)')) is None, "a route needs a literal path"


def test_any_router_constructor_gives_its_prefix_and_same_routes_in_two_modules_both_survive(tmp_path):
    files = {
        "api/__init__.py": "",
        "api/flows.py": ("from app.routing import ProjectRouter\nrouter = ProjectRouter(prefix='/flows')\n\n"
                         "@router.post('/history')\ndef flow_history():\n    pass\n\n@router.post('/')\ndef create_flow():\n    pass\n"),
        "api/tasks.py": ("from app.routing import ProjectRouter\nrouter = ProjectRouter(prefix='/tasks')\n\n"
                         "@router.post('/history')\ndef task_history():\n    pass\n"),
        "api/plain.py": "router = make()\n\n@router.post('/')\ndef create_plain():\n    pass\n",
        "api/other.py": "router = make()\n\n@router.post('/')\ndef create_other():\n    pass\n",
    }
    for rel, text in files.items():
        (tmp_path / rel).parent.mkdir(parents=True, exist_ok=True)
        (tmp_path / rel).write_text(text)
    for cmd in (["init", "-q"], ["add", "-A"], ["-c", "user.email=t@example.com", "-c", "user.name=T", "commit", "-qm", "x"]):
        subprocess.run(["git", *cmd], cwd=tmp_path, check=True, capture_output=True)
    g = build_symbols.extract(tmp_path)
    owners = {n.props["owner_symbol"]: (n.natural_key, n.props["path"]) for n in g.nodes("Endpoint") if n.props.get("owner_symbol")}
    assert owners["api/flows.py::flow_history"] == ("POST /flows/history", "/flows/history")
    assert owners["api/tasks.py::task_history"] == ("POST /tasks/history", "/tasks/history")
    assert {"api/plain.py::create_plain", "api/other.py::create_other"} <= set(owners), "POST / in two modules: both kept"
    assert all(path == "/" for k, (key, path) in owners.items() if k.endswith(("create_plain", "create_other")))


def test_a_call_through_an_imported_module_never_resolves_to_a_same_named_local_function(tmp_path):
    files = {
        "app/__init__.py": "", "app/models/__init__.py": "",
        "app/models/items.py": "def create_item(x):\n    return x\n",
        "app/api.py": ("from app.models import items as items_models\n\n@router.post('/items')\n"
                       "def create_item(x):\n    return items_models.create_item(x)\n"),
    }
    for rel, text in files.items():
        (tmp_path / rel).parent.mkdir(parents=True, exist_ok=True)
        (tmp_path / rel).write_text(text)
    for cmd in (["init", "-q"], ["add", "-A"], ["-c", "user.email=t@example.com", "-c", "user.name=T", "commit", "-qm", "x"]):
        subprocess.run(["git", *cmd], cwd=tmp_path, check=True, capture_output=True)
    calls = {(e.src, e.dst) for e in build_symbols.extract(tmp_path).edges("CALLS")}
    assert ("app/api.py::create_item", "app/models/items.py::create_item") in calls
    assert ("app/api.py::create_item", "app/api.py::create_item") not in calls, "not a call to itself"


def test_a_bare_call_inside_a_method_never_means_a_method_of_the_same_name(tmp_path):
    """Inside `def secret(self)`, a bare `secret()` is the imported function: a class body does not enclose names."""
    files = {
        "app/__init__.py": "",
        "app/crypto.py": "def secret(n):\n    return n\n",
        "app/api.py": ("from app.crypto import secret\n\n\nclass Host:\n    def secret(self, n):\n        return secret(n)\n"),
    }
    for rel, text in files.items():
        (tmp_path / rel).parent.mkdir(parents=True, exist_ok=True)
        (tmp_path / rel).write_text(text)
    for cmd in (["init", "-q"], ["add", "-A"], ["-c", "user.email=t@example.com", "-c", "user.name=T", "commit", "-qm", "x"]):
        subprocess.run(["git", *cmd], cwd=tmp_path, check=True, capture_output=True)
    calls = {(e.src, e.dst) for e in build_symbols.extract(tmp_path).edges("CALLS")}
    assert ("app/api.py::Host.secret", "app/crypto.py::secret") in calls
    assert ("app/api.py::Host.secret", "app/api.py::Host.secret") not in calls


def test_a_method_call_on_an_expression_is_not_a_call_to_a_same_named_function(tmp_path):
    files = {"app/__init__.py": "",
             "app/paths.py": ("from pathlib import Path\n\n\ndef resolve(code):\n    return code\n\n\n"
                              "def external(p):\n    return Path(p).resolve()\n")}
    for rel, text in files.items():
        (tmp_path / rel).parent.mkdir(parents=True, exist_ok=True)
        (tmp_path / rel).write_text(text)
    for cmd in (["init", "-q"], ["add", "-A"], ["-c", "user.email=t@example.com", "-c", "user.name=T", "commit", "-qm", "x"]):
        subprocess.run(["git", *cmd], cwd=tmp_path, check=True, capture_output=True)
    calls = {(e.src, e.dst) for e in build_symbols.extract(tmp_path).edges("CALLS")}
    assert ("app/paths.py::external", "app/paths.py::resolve") not in calls
