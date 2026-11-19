"""#198: reads of a constant a function declares `global` are attributed, and `X += 1` reads X. #199: a class-body
name that shadows a module constant is not a use of it. #200: names assigned by tuple unpacking are constants."""
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def repo(root: Path, files: dict) -> Path:
    for rel, t in files.items():
        (root / rel).parent.mkdir(parents=True, exist_ok=True)
        (root / rel).write_text(t)
    subprocess.run("git init -q . && git add -A && git -c user.name=t -c user.email=t@example.com commit -qm x", shell=True, cwd=root, check=True)
    env = dict(os.environ, PYTHONPATH=str(ROOT), PYTHONWARNINGS="ignore")
    subprocess.run([sys.executable, "-P", "-m", "devkb.cli", "build", "--project", str(root)], cwd=root, env=env, check=True, capture_output=True)
    return root


def cli(root, *a):
    env = dict(os.environ, PYTHONPATH=str(ROOT), PYTHONWARNINGS="ignore")
    return subprocess.run([sys.executable, "-P", "-m", "devkb.cli", *a, "--project", str(root)], cwd=root, env=env,
                          capture_output=True, text=True).stdout


def test_global_declared_reads_and_augmented_reads_are_uses(tmp_path):
    r = repo(tmp_path, {"app.py": "_CACHE = None\nLIMIT = 10\n\n\ndef get_cache():\n    global _CACHE\n    if _CACHE is None:\n"
                                  "        _CACHE = {}\n    return _CACHE\n\n\ndef bump():\n    global LIMIT\n    LIMIT += 1\n"
                                  "    return LIMIT\n\n\ndef plain():\n    return _CACHE\n"})
    cache = cli(r, "pack", "change", "_CACHE")
    for site in ("app.py:7", "app.py:9", "app.py:19"):
        assert f"`{site}`" in cache, site
    limit = cli(r, "pack", "change", "LIMIT")
    assert "`app.py:14`" in limit and "`app.py:15`" in limit


def test_a_class_body_name_is_not_a_use_of_the_module_constant(tmp_path):
    r = repo(tmp_path, {"pkg/__init__.py": "", "pkg/settings.py": "RETRIES = 3\n\n\nclass Client:\n    RETRIES = 5\n    attempts = RETRIES\n",
                        "pkg/use.py": "from pkg.settings import RETRIES\n\n\ndef f():\n    return RETRIES + 1\n"})
    p = cli(r, "pack", "change", "pkg/settings.py::RETRIES")
    assert "`pkg/use.py:5`" in p and "`pkg/settings.py:6`" not in p


def test_names_assigned_by_tuple_unpacking_are_constants(tmp_path):
    r = repo(tmp_path, {"cfg.py": "HOST, PORT = 'h', 80\n[USER, *GROUP] = ['u', 'g']\n\n\ndef url():\n    return f'{HOST}:{PORT}'\n"})
    for name in ("HOST", "PORT", "USER", "GROUP"):
        assert "no symbol named" not in cli(r, "symbol", name), name
    assert "`cfg.py:6`" in cli(r, "pack", "change", "PORT")
