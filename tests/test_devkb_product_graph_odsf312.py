"""ODSF-312, ADR-SDP-DEVKB-005: settings and services are graph knowledge, and a product's graph folds in its members.

The fixture is a product with a compose file, a systemd unit, a Dockerfile, an example env file and code reading
settings, plus a member repository with its own built graph that calls one of the product's routes by URL."""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from devkb import process_api  # noqa: E402
from devkb.extractors import configuration, members  # noqa: E402
from devkb.model import DevKBGraph, uid_for  # noqa: E402
from devkb.project_context import ProjectContext  # noqa: E402

pytest.importorskip("yaml")


def _git_repo(root: Path, files: dict[str, str]) -> None:
    for rel, text in files.items():
        (root / rel).parent.mkdir(parents=True, exist_ok=True)
        (root / rel).write_text(text)
    for cmd in (["init", "-q"], ["add", "-A"]):
        subprocess.run(["git", *cmd], cwd=root, check=True, capture_output=True)


def _ctx(code: str, root: Path) -> ProjectContext:
    return ProjectContext(code=code, repo_root=root, ticket_prefix=code, issues_dir=root / "issues", tests_dir=root / "tests",
                          sprint_dir=root / "h", devkb_dir=root / ".devkb", board_file=root / "b.md", wp_map_file=root / "w.json")


PRODUCT = {
    "app/settings.py": "import os\nMODE = os.environ.get('APP_MODE', 'dev')\n\ndef model_name():\n    return os.environ['LLM_MODEL']\n",
    "app/api.py": "import os\n\ndef secret():\n    return os.getenv('ONLY_IN_CODE')\n",
    "tests/test_settings.py": "import os\n\ndef test_x():\n    os.environ['TEST_ONLY'] = '1'\n",
    "deploy/compose.yml": "services:\n  api:\n    image: product/api:1\n    ports: ['8020:8020']\n    environment:\n      - LLM_MODEL=gemma\n      - DB_URL=${DATABASE_URL}\n",
    "deploy/systemd/product-api.service": "[Service]\nEnvironment=APP_MODE=prod\nExecStart=/usr/bin/python3 -m app\n",
    "deploy/Dockerfile": "FROM python:3.12-slim\nENV APP_MODE=prod\nEXPOSE 8020\n",
    ".env.example": "LLM_MODEL=\nUNUSED_SETTING=\n",
    ".env": "LLM_MODEL=a-real-secret-value\n",
    "pms.config.json": json.dumps({"_comment": "x", "ai_policy": {}, "graph": {"members": [{"code": "MEM", "role": "client"}]}}),
}


def test_settings_services_and_their_files_are_extracted_without_values(tmp_path):
    _git_repo(tmp_path, {k: v for k, v in PRODUCT.items() if k != ".env"})
    (tmp_path / ".env").write_text(PRODUCT[".env"])  # untracked, as a real one is: never opened
    g = configuration.extract(_ctx("PRD", tmp_path))
    reads = {(e.src_type, e.src, e.dst) for e in g.edges("READS")}
    assert reads == {("File", "app/settings.py", "APP_MODE"), ("Symbol", "app/settings.py::model_name", "LLM_MODEL"),
                     ("Symbol", "app/api.py::secret", "ONLY_IN_CODE")}, "module reads go to the File, tests are excluded"
    declares = {(e.src, e.dst) for e in g.edges("DECLARES")}
    assert {("deploy/compose.yml", "LLM_MODEL"), ("deploy/compose.yml", "DATABASE_URL"), (".env.example", "UNUSED_SETTING"),
            ("deploy/systemd/product-api.service", "APP_MODE"), ("deploy/Dockerfile", "APP_MODE"),
            ("pms.config.json", "pms.config.json:graph")} <= declares
    assert ("pms.config.json", "pms.config.json:_comment") not in declares
    comps = {n.natural_key: n.props for n in g.nodes("Component")}
    assert comps["deploy/compose.yml#api"]["ports"] == ["8020:8020"] and comps["systemd:product-api.service"]["exec"] == "python3"
    assert comps["deploy/Dockerfile"]["image"] == "python:3.12-slim"
    assert "a-real-secret-value" not in json.dumps(g.to_dict()), "a value is never stored"


def _member(tmp_path: Path) -> Path:
    root = tmp_path / "member"
    _git_repo(root, {"src/client.py": "KEY_API = 'https://example.org/api/v1/keys/abc'\n\ndef renew():\n    return KEY_API\n"})
    g = DevKBGraph()
    g.add_node("File", "src/client.py", "t")
    g.add_node("Symbol", "src/client.py::renew", "t", kind="function")
    g.add_node("ConfigKey", "LLM_MODEL", "t", kind="env")
    g.add_edge("DEFINED_IN", "Symbol", "src/client.py::renew", "File", "src/client.py", "t")
    g.add_edge("READS", "Symbol", "src/client.py::renew", "ConfigKey", "LLM_MODEL", "t")
    (root / ".devkb").mkdir()
    d = g.to_dict()
    (root / ".devkb" / "nodes.jsonl").write_text("\n".join(json.dumps(n) for n in d["nodes"]) + "\n")
    (root / ".devkb" / "edges.jsonl").write_text("\n".join(json.dumps(e) for e in d["edges"]) + "\n")
    return root


def test_a_member_is_folded_in_with_prefixed_keys_shared_settings_and_a_cross_repository_call(tmp_path):
    product = tmp_path / "product"
    _git_repo(product, {k: v for k, v in PRODUCT.items() if k != ".env"})
    member_root = _member(tmp_path)
    graph = configuration.extract(_ctx("PRD", product))
    graph.add_node("File", "app/keys.py", "t")
    graph.add_node("Symbol", "app/keys.py::get_key", "t", kind="function")
    graph.add_node("Endpoint", "GET /api/v1/keys/{key_id}", "t", path="/api/v1/keys/{key_id}", owner_symbol="app/keys.py::get_key")
    rows = members.merge_members(_ctx("PRD", product), graph, lambda code: _ctx(code, member_root))
    members.link_repository(graph, "PRD")
    assert rows == [{"code": "MEM", "role": "client", "nodes": 3, "edges": 2, "calls_api": 1}]
    keys = {(n.type, n.natural_key) for n in graph.nodes()}
    assert ("Symbol", "MEM:src/client.py::renew") in keys and ("Symbol", "src/client.py::renew") not in keys
    assert ("ConfigKey", "LLM_MODEL") in keys and ("ConfigKey", "MEM:LLM_MODEL") not in keys, "one setting across repos"
    assert {(e.src, e.dst) for e in graph.edges("CALLS_API")} == {("MEM:src/client.py::renew", "app/keys.py::get_key")}
    repo = {(e.src, e.dst) for e in graph.edges("IN_REPO")}
    assert ("MEM:src/client.py", "MEM") in repo and ("MEM:src/client.py", "PRD") not in repo
    assert not any(dst == "PRD" for _src, dst in repo), "the product's own files need no IN_REPO: an unprefixed key says it (ODSF-314)"
    assert ("Repository", "PRD") in keys


def test_a_declared_member_without_a_graph_fails_the_build_loudly(tmp_path):
    product = tmp_path / "product"
    _git_repo(product, {"pms.config.json": PRODUCT["pms.config.json"]})
    with pytest.raises(ValueError, match="declared member graph not built"):
        members.merge_members(_ctx("PRD", product), DevKBGraph(), lambda code: _ctx(code, tmp_path / "nowhere"))


def test_config_tool_answers_a_setting_a_service_and_the_overview(tmp_path, monkeypatch):
    product = tmp_path / "product"
    _git_repo(product, {k: v for k, v in PRODUCT.items() if k != ".env"})
    subprocess.run(["git", "-c", "user.email=t@example.com", "-c", "user.name=T", "commit", "-qm", "x"], cwd=product, check=True)
    graph = configuration.extract(_ctx("PRD", product))
    graph.add_node("Symbol", "app/settings.py::model_name", "t", kind="function")
    members.link_repository(graph, "PRD")
    assert configuration.settle(graph) == 1, "app/api.py::secret has no Symbol node here: its read moves to the file"
    store = product / ".devkb"
    store.mkdir()
    d = graph.to_dict()
    (store / "nodes.jsonl").write_text("\n".join(json.dumps(n) for n in d["nodes"]) + "\n")
    (store / "edges.jsonl").write_text("\n".join(json.dumps(e) for e in d["edges"]) + "\n")
    head = subprocess.run(["git", "rev-parse", "HEAD"], cwd=product, capture_output=True, text=True).stdout.strip()
    (store / "manifest.json").write_text(json.dumps({"built_at": "2026-11-14T00:00:00+00:00", "git_head": head}))
    monkeypatch.setattr(process_api, "resolve", lambda code: _ctx("PRD", product))
    api = process_api.ProcessAPI("PRD", telemetry=False)
    s = api.call("config", query="LLM_MODEL")
    assert s["read_by"] == ["app/settings.py::model_name"] and set(s["declared_in"]) == {".env.example", "deploy/compose.yml"}
    assert s["deployed_by"] == ["deploy/compose.yml#api"] and s["repositories"] == ["PRD"]
    only = api.call("config", query="ONLY_IN_CODE")
    assert only["read_by"] == ["app/api.py"] and "note" in only, "read in code, declared nowhere"
    c = api.call("config", query="api")
    assert c["component"] == "deploy/compose.yml#api" and {x["k"] for x in c["settings"]} == {"LLM_MODEL", "DB_URL", "DATABASE_URL"}
    o = api.call("config")
    assert o["components"] == {"compose": 1, "systemd": 1, "docker": 1} and o["repositories"] == ["PRD"]
    assert "ONLY_IN_CODE" in o["read_not_declared"] and "UNUSED_SETTING" in o["declared_not_read"]
    assert "error" in api.call("config", query="zebra")
    assert uid_for("ConfigKey", "LLM_MODEL") in (store / "nodes.jsonl").read_text()
