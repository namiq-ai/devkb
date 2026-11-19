"""#214 (SPEC-DKB-007 S1): every search is given its intent from the whole command, and the log says which graph
question the hook asked. The answers do not change."""
import importlib.util
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
_spec = importlib.util.spec_from_file_location("guardrail", ROOT / "scripts" / "devkb_guardrail.py")
g = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(g)


def bash(cmd, tmp):
    return g.classify("Bash", {"command": cmd}, g.bash_pattern(cmd), g.bash_search(cmd, tmp)[1], g.bash_search(cmd, tmp)[0])


@pytest.fixture
def tree(tmp_path):
    for rel in ("pkg/core.py", "pkg/app.py", "docs/guide.md", ".gitignore"):
        p = tmp_path / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text("x\n")
    return tmp_path


@pytest.mark.parametrize("cmd,intent", [
    ("grep -rn compute . --include=*.md", "non-code"),
    ("grep -n devkb .gitignore", "non-code"),
    ("grep -rc compute .", "count"),
    ("grep -rn compute . | wc -l", "count"),
    ("grep -rl compute .", "list-files"),
    ("grep -rnv compute pkg/app.py", "invert"),
    ('grep -n "^def " pkg/core.py', "list-symbols"),
    ('grep -n "    def \\|^class " pkg/core.py', "list-symbols"),
    ('grep -n compute pkg/core.py | grep "def \\|class "', "list-symbols"),
    ('grep -n "class Def" -A22 pkg/core.py', "read-body"),
    ('grep -n "def compute" -A20 pkg/core.py', "read-body"),
    ('grep -n "Telemetry" -A60 pkg/core.py', "read-body"),
    ('grep -n "^def \\(run_all\\|go_on\\)" -A28 pkg/core.py', "read-body"),
    ('grep -rn "def compute" pkg/', "locate"),
    ('grep -n "def a_one\\|def b_two" pkg/core.py', "locate"),
    ('grep -n "^NOT_CODE\\|^REGEXY" pkg/core.py', "locate"),
    ('grep -rn compute pkg/ | grep "def compute"', "locate"),
    ("grep -n compute pkg/app.py", "in-file"),
    ("grep -rn compute . | grep -v tests", "call-sites-filtered"),
    ('grep -rn compute . | grep -v "def "', "call-sites-filtered"),
    ("grep -rn compute pkg/", "call-sites"),
    ("grep -rn compute pkg/ | head -5", "call-sites"),
    ('grep -rn "could not read" .', "literal"),
])
def test_each_search_gets_its_intent(tree, cmd, intent):
    assert bash(cmd, tree) == intent


def test_the_grep_tool_is_classified_from_its_own_options(tree):
    def tool(inp):
        paths, why = g.grep_tool_search(inp, tree)
        return g.classify("Grep", inp, inp["pattern"], why, paths)
    assert tool({"pattern": "def compute", "path": "pkg", "output_mode": "content", "-A": 10}) == "read-body"
    assert tool({"pattern": "compute"}) == "list-files"
    assert tool({"pattern": "compute", "output_mode": "count"}) == "count"
    assert tool({"pattern": "compute", "output_mode": "content", "path": "pkg"}) == "call-sites"


def test_the_question_names_the_graph_query():
    assert g.question_of("read-answer", []) == "symbol --source"
    assert g.question_of("span-hint", []) == "outline"
    assert g.question_of("pass-through", []) == "none"
    assert g.question_of("alongside", [{"verdict": "complete"}]) == "pack refactor"
