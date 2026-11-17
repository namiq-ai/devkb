"""Configuration as first-class graph knowledge (ADR-SDP-DEVKB-005 §4-5, ODSF-312).

  ConfigKey  one named setting: an environment variable, or a top-level key of the root pms.config.json
  READS      Symbol -> ConfigKey (File -> ConfigKey for a read at module level): os.environ[...], os.environ.get,
             os.environ.setdefault, os.getenv, `"X" in os.environ`, and the same through `from os import environ`
  DECLARES   File -> ConfigKey: *.env.example / .env.template / .env.sample, compose `environment:` and `${VAR}`
             references, systemd `Environment=`, Dockerfile `ENV` and `ARG`, pms.config.json top-level keys
  Component  each compose service, systemd unit and Dockerfile (a second source beside discovery's Services)
  DEPLOYS    File -> Component, from the file that defines it

Only names are recorded. A value can be a secret, so no value is read into the graph, and an untracked `.env` file
is never opened: the file list is `git ls-files`, and among env files only example/template/sample ones are read.
"""
from __future__ import annotations

import ast
import json
import re
import subprocess
from pathlib import Path

from devkb.model import DevKBGraph

try:  # compose files are YAML; without PyYAML the rest of the extractor still runs
    import yaml
except ImportError:  # pragma: no cover - PyYAML is present wherever the factory runs
    yaml = None

SOURCE = "configuration"
_NAME = re.compile(r"^[A-Z][A-Z0-9_]{1,63}$")
_ENV_LINE = re.compile(r"^\s*(?:export\s+)?([A-Z][A-Z0-9_]{1,63})\s*=")
_INTERP = re.compile(r"\$\{([A-Z][A-Z0-9_]{1,63})(?::?[-?][^}]*)?\}")
_ENV_EXAMPLE = re.compile(r"(^|/)(\.env\.(example|template|sample|tmpl)|[^/]+\.env\.(example|template|sample|tmpl)|"
                          r"\.env\.dist|env\.example)$")
_COMPOSE = re.compile(r"(^|/)(docker-)?compose[^/]*\.ya?ml$")
_UNIT = re.compile(r"\.(service|timer|socket)$")
_DOCKERFILE = re.compile(r"(^|/)(Dockerfile([.-][^/]*)?|[^/]+\.Dockerfile)$")
_TEST = re.compile(r"(^|/)(tests?/|test_[^/]*\.py$|[^/]*_test\.py$|conftest\.py$)")


def tracked_files(repo_root: Path) -> list[str]:
    out = subprocess.run(["git", "ls-files", "--recurse-submodules"], cwd=repo_root, capture_output=True, text=True,
                         check=False).stdout
    return [f for f in out.splitlines() if f.strip()]


# ── code that reads a setting ────────────────────────────────────────────────
class _Reads(ast.NodeVisitor):
    """(qualified function name or "", setting name) for each literal environment read."""

    def __init__(self) -> None:
        self.stack: list[str] = []
        self.fn_depth = 0
        self.environ_names = {"environ"}  # `from os import environ` binds it bare
        self.found: list[tuple[str, str]] = []

    def _scope(self) -> str:
        return ".".join(self.stack) if self.fn_depth else ""

    def visit_ClassDef(self, node):
        self.stack.append(node.name)
        self.generic_visit(node)
        self.stack.pop()

    def _fn(self, node):
        self.stack.append(node.name)
        self.fn_depth += 1
        self.generic_visit(node)
        self.fn_depth -= 1
        self.stack.pop()

    visit_FunctionDef = visit_AsyncFunctionDef = _fn

    def _is_environ(self, node) -> bool:
        return (isinstance(node, ast.Attribute) and node.attr == "environ" and isinstance(node.value, ast.Name)
                and node.value.id == "os") or (isinstance(node, ast.Name) and node.id in self.environ_names)

    def _add(self, arg) -> None:
        if isinstance(arg, ast.Constant) and isinstance(arg.value, str) and _NAME.match(arg.value):
            self.found.append((self._scope(), arg.value))

    def visit_Subscript(self, node):
        if self._is_environ(node.value):
            self._add(node.slice)
        self.generic_visit(node)

    def visit_Call(self, node):
        f = node.func
        if node.args and isinstance(f, ast.Attribute):
            if f.attr in ("get", "setdefault", "pop") and self._is_environ(f.value):
                self._add(node.args[0])
            elif f.attr == "getenv" and isinstance(f.value, ast.Name) and f.value.id == "os":
                self._add(node.args[0])
        elif node.args and isinstance(f, ast.Name) and f.id == "getenv":
            self._add(node.args[0])
        self.generic_visit(node)

    def visit_Compare(self, node):
        if (len(node.ops) == 1 and isinstance(node.ops[0], (ast.In, ast.NotIn)) and self._is_environ(node.comparators[0])):
            self._add(node.left)
        self.generic_visit(node)


def python_reads(text: str) -> list[tuple[str, str]]:
    try:
        tree = ast.parse(text)
    except (SyntaxError, ValueError, RecursionError):
        return []
    v = _Reads()
    try:
        v.visit(tree)
    except RecursionError:      # a file nested deeper than the walk can follow: no reads from it (#106)
        return []
    return v.found


# ── files that declare a setting or define a service ─────────────────────────
def env_example_names(text: str) -> list[str]:
    return [m.group(1) for line in text.splitlines() if (m := _ENV_LINE.match(line)) and not line.lstrip().startswith("#")]


def compose_services(text: str) -> list[dict]:
    """[{"name", "image", "ports", "settings"}] for each service; names in `environment:` and `${VAR}` references."""
    if yaml is None:
        return []
    try:
        doc = yaml.safe_load(text)
    except yaml.YAMLError:
        return []
    out = []
    services = (doc or {}).get("services") if isinstance(doc, dict) else None
    for name, svc in (services or {}).items() if isinstance(services, dict) else []:
        svc = svc if isinstance(svc, dict) else {}
        env = svc.get("environment") or {}
        keys = list(env) if isinstance(env, dict) else [str(e).split("=", 1)[0] for e in env if isinstance(e, str)]
        ports = [str(p) if not isinstance(p, dict) else f"{p.get('published', '')}:{p.get('target', '')}" for p in svc.get("ports") or []]
        out.append({"name": str(name), "image": str(svc.get("image") or ""), "ports": ports,
                    "settings": sorted({k for k in keys if _NAME.match(k)} | set(_INTERP.findall(json.dumps(svc))))})
    return out


def unit_settings(text: str) -> tuple[list[str], str]:
    """Environment= names and the ExecStart program of a systemd unit."""
    names, exec_start = [], ""
    for line in text.splitlines():
        line = line.strip()
        if line.startswith("Environment="):
            for part in re.findall(r'"([^"]*)"|(\S+)', line[len("Environment="):]):
                name = (part[0] or part[1]).split("=", 1)[0]
                if _NAME.match(name):
                    names.append(name)
        elif line.startswith("ExecStart=") and not exec_start:
            exec_start = line[len("ExecStart="):].lstrip("-@+!").split()[0] if line[len("ExecStart="):].split() else ""
    return names, exec_start


def dockerfile_facts(text: str) -> tuple[list[str], str, list[str]]:
    """ENV and ARG names, the first FROM image, EXPOSE ports."""
    names, base, ports = [], "", []
    for line in text.splitlines():
        words = line.strip().split()
        if not words:
            continue
        op = words[0].upper()
        if op == "FROM" and not base and len(words) > 1:
            base = words[1]
        elif op in ("ENV", "ARG"):
            for w in words[1:]:
                name = w.split("=", 1)[0]
                if _NAME.match(name):
                    names.append(name)
                if op == "ENV" and "=" not in w:
                    break  # `ENV KEY value` form: one name, the rest is its value
        elif op == "EXPOSE":
            ports += words[1:]
    return names, base, ports


def extract(ctx) -> DevKBGraph:
    g = DevKBGraph()
    root = ctx.repo_root

    def setting(name: str, kind: str = "env") -> str:
        g.add_node("ConfigKey", name, source=SOURCE, kind=kind)
        return name

    for rel in tracked_files(root):
        path = root / rel
        if rel.endswith(".py"):
            if _TEST.search(rel):
                continue  # a test setting an env var for itself is not the product reading a setting
            try:
                reads = python_reads(path.read_text(errors="replace"))
            except OSError:
                continue
            for scope, name in reads:
                setting(name)
                if scope:
                    g.add_edge("READS", "Symbol", f"{rel}::{scope}", "ConfigKey", name, source=SOURCE, confidence=0.9,
                               evidence_ref=f"{rel}: environment read")
                else:
                    g.add_edge("READS", "File", rel, "ConfigKey", name, source=SOURCE, confidence=0.9,
                               evidence_ref=f"{rel}: module-level environment read")
            continue
        try:
            if _ENV_EXAMPLE.search(rel):
                names = env_example_names(path.read_text(errors="replace"))
                if names:
                    g.add_node("File", rel, source=SOURCE)
                for name in names:
                    g.add_edge("DECLARES", "File", rel, "ConfigKey", setting(name), source=SOURCE, evidence_ref=f"{rel}: KEY=")
            elif _COMPOSE.search(rel):
                for svc in compose_services(path.read_text(errors="replace")):
                    comp = f"{rel}#{svc['name']}"
                    g.add_node("File", rel, source=SOURCE)
                    g.add_node("Component", comp, source=SOURCE, kind="compose", label=svc["name"], file=rel,
                               image=svc["image"] or None, ports=svc["ports"] or None)
                    g.add_edge("DEPLOYS", "File", rel, "Component", comp, source=SOURCE, evidence_ref=f"{rel}: services.{svc['name']}")
                    for name in svc["settings"]:
                        g.add_edge("DECLARES", "File", rel, "ConfigKey", setting(name), source=SOURCE,
                                   evidence_ref=f"{rel}: services.{svc['name']}.environment")
            elif _UNIT.search(rel):
                names, exec_start = unit_settings(path.read_text(errors="replace"))
                comp = f"systemd:{Path(rel).name}"
                g.add_node("File", rel, source=SOURCE)
                g.add_node("Component", comp, source=SOURCE, kind="systemd", label=Path(rel).name, file=rel,
                           exec=Path(exec_start).name if exec_start else None)
                g.add_edge("DEPLOYS", "File", rel, "Component", comp, source=SOURCE, evidence_ref=f"{rel}: unit")
                for name in names:
                    g.add_edge("DECLARES", "File", rel, "ConfigKey", setting(name), source=SOURCE, evidence_ref=f"{rel}: Environment=")
            elif _DOCKERFILE.search(rel):
                names, base, ports = dockerfile_facts(path.read_text(errors="replace"))
                g.add_node("File", rel, source=SOURCE)
                g.add_node("Component", rel, source=SOURCE, kind="docker", label=rel, file=rel, image=base or None,
                           ports=ports or None)
                g.add_edge("DEPLOYS", "File", rel, "Component", rel, source=SOURCE, evidence_ref=f"{rel}: FROM {base}")
                for name in names:
                    g.add_edge("DECLARES", "File", rel, "ConfigKey", setting(name), source=SOURCE, evidence_ref=f"{rel}: ENV/ARG")
        except OSError:
            continue

    cfg_path = root / "pms.config.json"
    try:
        cfg = json.loads(cfg_path.read_text())
    except (OSError, ValueError):
        cfg = {}
    for key in cfg if isinstance(cfg, dict) else []:
        if not key.startswith("_"):  # `_comment` keys are prose, not settings
            g.add_node("File", "pms.config.json", source=SOURCE)
            name = setting(f"pms.config.json:{key}", kind="config_file")
            g.add_edge("DECLARES", "File", "pms.config.json", "ConfigKey", name, source=SOURCE, evidence_ref="pms.config.json top-level key")
    return g


def settle(graph: DevKBGraph) -> int:
    """Run after the merge: a READS from a function the symbol extractor did not index is re-attached to its file, so a
    read is never dropped because two extractors name one function differently. Returns how many were re-attached."""
    symbols = {n.natural_key for n in graph.nodes("Symbol")}
    files = {n.natural_key for n in graph.nodes("File")}
    moved = 0
    for e in [e for e in graph.edges("READS") if e.src_type == "Symbol" and e.src not in symbols]:
        graph._edges.discard(e)
        rel = e.src.split("::", 1)[0]
        if rel not in files:
            graph.add_node("File", rel, source=SOURCE)
            files.add(rel)
        graph.add_edge("READS", "File", rel, "ConfigKey", e.dst, source=SOURCE, confidence=e.confidence,
                       evidence_ref=e.evidence_ref + " (function not indexed; attributed to its file)")
        moved += 1
    return moved
