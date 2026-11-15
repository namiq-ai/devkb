"""An independent check of each refactor task's truth: the files with a direct caller, found by a second implementation
that shares no code with the graph (`devkb/build_symbols.py`) or the task generators' truth (`module_truth.py`).

The pack check compares a pack with the truth; when both are built with the same import rules, a blind spot they share
scores 1.0 (lnbits `get_wallet`, 2026-11-15: both missed every caller that imported the function through its package's
`__init__.py`). This check resolves each import to the file that defines the name, following re-exports, and counts a
call wherever it is made, inside a function or at import time. A file it finds that the truth lacks is reported as
`missing`: it is proven by an import chain. A file the truth has that it does not find is `unconfirmed`, weaker
evidence, since this check does not follow calls through objects.

  python3 devkb/bench/truth_check.py CHECKOUT TASKS.json
"""
from __future__ import annotations

import ast
import collections
import json
import re
import subprocess
import sys
from pathlib import Path

PROMPT = re.compile(r"`([^`]+)` \(defined in ([^)]+)\)")


class _Repo:
    def __init__(self, root: Path) -> None:
        listed = subprocess.run(["git", "ls-files", "--", "*.py"], cwd=root, capture_output=True, text=True).stdout.split()
        self.trees: dict[str, ast.Module] = {}
        for rel in listed:
            try:
                self.trees[rel] = ast.parse((root / rel).read_text(errors="replace"))
            except (SyntaxError, ValueError, OSError, RecursionError):
                continue
        # dotted module -> files whose path ends that way, so `src/` layouts and nested services resolve
        self.by_suffix: dict[str, list[str]] = collections.defaultdict(list)
        for rel in self.trees:
            parts = rel[:-3].split("/")
            if parts[-1] == "__init__":
                parts = parts[:-1]
            for i in range(len(parts)):
                self.by_suffix[".".join(parts[i:])].append(rel)
        self.defined = {rel: {n.name for n in t.body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))}
                        for rel, t in self.trees.items()}
        self.imports = {rel: self._imports(rel, t) for rel, t in self.trees.items()}

    def module(self, dotted: str) -> str | None:
        hits = self.by_suffix.get(dotted, [])
        return hits[0] if len(hits) == 1 else None

    @staticmethod
    def _imports(rel: str, tree: ast.Module) -> tuple[dict[str, tuple[str, str]], dict[str, str]]:
        """({local: (module, name)} from `from m import name`, {local: module} from `import m` / `import m as x`)."""
        names, modules = {}, {}
        pkg = rel[:-3].split("/")[:-1]
        for n in ast.walk(tree):
            if isinstance(n, ast.ImportFrom):
                base = (".".join(pkg[: len(pkg) - n.level + 1] + ([n.module] if n.module else [])) if n.level
                        else n.module or "")
                for a in n.names:
                    if a.name != "*":
                        names[a.asname or a.name] = (base, a.name)
            elif isinstance(n, ast.Import):
                for a in n.names:
                    modules[a.asname or a.name] = a.name
        return names, modules

    def origin(self, dotted: str, name: str, depth: int = 0) -> tuple[str, str] | None:
        """The (file, name) that `name` looked up in module `dotted` is: defined there, or re-exported from elsewhere."""
        rel = self.module(dotted)
        if rel is None:  # the package path may be ambiguous while the submodule it names is not
            return ("<module>", f"{dotted}.{name}") if self.module(f"{dotted}.{name}") else None
        if name in self.defined[rel]:
            return rel, name
        via = self.imports[rel][0].get(name)
        if via and depth < 6:
            return self.origin(via[0], via[1], depth + 1)
        sub = f"{dotted}.{name}"  # `from pkg import mod`: a module, not a name
        return ("<module>", sub) if self.module(sub) else None

    def caller_files(self, path: str, name: str) -> set[str]:
        want = (path, name)
        out: set[str] = set()
        for rel, tree in self.trees.items():
            if rel == path:  # the defining file calls it by its bare name, from another function
                if any(isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name != name and any(
                        isinstance(c, ast.Call) and isinstance(c.func, ast.Name) and c.func.id == name for c in ast.walk(n))
                       for n in ast.walk(tree)):
                    out.add(rel)
                continue
            names, modules = self.imports[rel]
            local = {k for k, (m, n) in names.items() if self.origin(m, n) == want}
            mods: set[str] = set()  # local names bound to a module whose `name` is the target
            for k, (m, n) in names.items():
                o = self.origin(m, n)
                if o and o[0] == "<module>" and self.origin(o[1], name) == want:
                    mods.add(k)
            for k, m in modules.items():
                if self.origin(m, name) == want:
                    mods.add(k)
            for n in ast.walk(tree):
                if not isinstance(n, ast.Call):
                    continue
                f = n.func
                if isinstance(f, ast.Name) and f.id in local:
                    out.add(rel)
                elif isinstance(f, ast.Attribute) and f.attr == name:
                    v, chain = f.value, []
                    while isinstance(v, ast.Attribute):
                        chain.insert(0, v.attr)
                        v = v.value
                    if not isinstance(v, ast.Name):
                        continue
                    if ".".join([v.id, *chain]) in mods:
                        out.add(rel)
                        continue
                    # `models.flow_runs.read_flow_run()`: the root is a module, the rest a path below it
                    root = names.get(v.id)
                    base = (self.origin(*root) or (None, None)) if root else (None, None)
                    dotted = base[1] if base[0] == "<module>" else modules.get(v.id)
                    if dotted and chain and self.origin(".".join([dotted, *chain]), name) == want:
                        out.add(rel)
        return out


def check(root: Path, tasks: list[dict]) -> list[dict]:
    repo = _Repo(root)
    rows = []
    for t in tasks:
        m = PROMPT.search(t.get("prompt", ""))
        if t.get("kind") != "refactor" or not m or "." in m.group(1):
            continue
        found = repo.caller_files(m.group(2), m.group(1))
        truth = set(t["truth"]["caller_files"])
        rows.append({"task": t["id"], "truth": len(truth), "found": len(found),
                     "missing": sorted(found - truth), "unconfirmed": sorted(truth - found)})
    return rows


def main() -> int:
    root, tasks = Path(sys.argv[1]), json.loads(Path(sys.argv[2]).read_text())
    rows = check(root, tasks)
    print(json.dumps(rows, indent=1))
    return 1 if any(r["missing"] for r in rows) else 0


if __name__ == "__main__":
    raise SystemExit(main())
