"""#276, #278: a search is replaced only by an answer that holds every line grep prints. Not when `uses` left lines out
(a cap), the search names docs or configuration, or the search names more names than the hook asked about."""
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
PRE = ROOT / "scripts" / "devkb_guardrail.py"
MANY = "".join(f"\n\ndef caller{i}():\n    return helper({i})\n" for i in range(80))   # more call sites than uses shows
FILES = {"pkg/__init__.py": "", "pkg/a.py": "def helper(x):\n    return x\n" + MANY,
         "pkg/lib.py": "def alpha_one():\n    return 1\n\n\ndef beta_two():\n    return 2\n\n\ndef gamma_three():\n    return 3\n\n\n"
                       "def delta_four():\n    return 4\n",
         "pkg/use.py": "from pkg.lib import alpha_one, beta_two, gamma_three, delta_four\nfrom pkg.mod import handler\n\n\n"
                       "def go():\n    return alpha_one() + beta_two() + gamma_three() + delta_four() + handler(1)\n",
         "pkg/mod.py": "def handler(x):\n    return x\n", "docs/guide.md": "call handler(1) to run\n"}


@pytest.fixture(scope="module")
def repo(tmp_path_factory):
    root = tmp_path_factory.mktemp("r276")
    for rel, t in FILES.items():
        (root / rel).parent.mkdir(parents=True, exist_ok=True)
        (root / rel).write_text(t)
    for c in (["init", "-q"], ["add", "."], ["-c", "user.name=t", "-c", "user.email=t@example.com", "commit", "-qm", "x"]):
        subprocess.run(["git", *c], cwd=root, check=True)
    env = dict(os.environ, PYTHONPATH=str(ROOT), PYTHONWARNINGS="ignore")
    subprocess.run([sys.executable, "-P", "-m", "devkb.cli", "build", "--project", str(root)], cwd=root, env=env, check=True,
                   capture_output=True)
    return root


_n = [0]


def decide(repo, home, cmd):
    _n[0] += 1
    env = {k: v for k, v in os.environ.items() if not k.startswith("DEVKB_")}
    env.update(HOME=str(home), PYTHONPATH=str(ROOT))
    out = ""
    for j, c in enumerate(("ls", cmd)):
        ev = {"tool_name": "Bash", "cwd": str(repo), "session_id": f"s276-{_n[0]}", "tool_use_id": f"t{_n[0]}-{j}",
              "tool_input": {"command": c}}
        out = subprocess.run([sys.executable, str(PRE)], input=json.dumps(ev), capture_output=True, text=True, env=env).stdout
    log = home / ".claude" / "hooks" / "devkb-guardrail.log"
    rows = [json.loads(l) for l in log.read_text().splitlines() if f'"s276-{_n[0]}"' in l and '"remind"' not in l]
    return (json.loads(out).get("hookSpecificOutput", {}) if out.strip() else {}), rows[-1]


def test_a_capped_call_site_list_never_replaces_the_search(repo, tmp_path):
    h, row = decide(repo, tmp_path, "grep -rn helper pkg/")
    assert h.get("permissionDecision") != "deny" and row["reason"] == "cut"


def test_a_search_naming_a_docs_folder_is_never_replaced(repo, tmp_path):
    h, row = decide(repo, tmp_path, "grep -rn handler pkg/ docs/")
    assert h.get("permissionDecision") != "deny"


def test_a_search_for_four_names_is_never_replaced_and_logs_every_name(repo, tmp_path):
    h, row = decide(repo, tmp_path, "grep -rn 'alpha_one\\|beta_two\\|gamma_three\\|delta_four' pkg/")
    assert h.get("permissionDecision") != "deny"
    assert row["names"] == ["alpha_one", "beta_two", "gamma_three", "delta_four"]


def test_a_complete_short_list_still_replaces(repo, tmp_path):
    h, row = decide(repo, tmp_path, "grep -rn handler pkg/")       # one definition, one call: nothing left out
    assert h.get("permissionDecision") == "deny" and row["action"] == "substitute"


@pytest.mark.parametrize("cmd", ["grep -rn handler .", "grep -rn handler"])
def test_a_repository_wide_search_reaching_docs_is_never_replaced(repo, tmp_path, cmd):
    h, row = decide(repo, tmp_path, cmd)                  # docs/guide.md mentions handler: grep prints that line
    assert h.get("permissionDecision") != "deny" and row["reason"] == "non-code-path"
