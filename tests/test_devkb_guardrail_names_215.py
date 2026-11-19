"""#215 (SPEC-DKB-007 S2), with #184 and #186: a keyword or a word in another case is never answered as a symbol,
alternation is read per grep dialect, and option values are never the pattern."""
import importlib.util
from pathlib import Path

import pytest

from devkb import misses

ROOT = Path(__file__).resolve().parents[1]
_spec = importlib.util.spec_from_file_location("guardrail", ROOT / "scripts" / "devkb_guardrail.py")
g = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(g)


@pytest.mark.parametrize("pattern,dialect,names", [
    ("^def ", "both", []), ('    def ', "bre", []), ("class", "ere", []),
    ("compute|helper", "bre", []), ("compute\\|helper", "bre", ["compute", "helper"]),
    ("compute|helper", "ere", ["compute", "helper"]), ("compute\\|helper", "fixed", []), ("compute|helper", "fixed", []),
    ("def extract", "bre", ["extract"]), ("Def", "bre", ["Def"]),
])
def test_names_are_read_per_dialect_and_keywords_are_not_names(pattern, dialect, names):
    assert misses.navigation_names(pattern, dialect) == names


@pytest.mark.parametrize("cmd,dialect,nocase", [
    ("grep -rn x .", "bre", False), ("grep -rnE x .", "ere", False), ("egrep x .", "ere", False), ("rg x", "ere", False),
    ("grep -rnF x .", "fixed", False), ("fgrep x .", "fixed", False), ("grep -rni x .", "bre", True),
    ("rg -i x", "ere", True), ("git grep -n x", "bre", False),
])
def test_the_dialect_and_case_come_from_the_command(cmd, dialect, nocase):
    assert g.dialect_of("Bash", {"command": cmd}) == (dialect, nocase)
    assert g.dialect_of("Grep", {"pattern": "x", "-i": True}) == ("ere", True)


@pytest.mark.parametrize("cmd", ["grep -n -A 30 compute f.py", "grep -m 5 -rn compute .", "rg -t py compute",
                                 "grep -rn --include '*.py' compute .", "grep -rnA 3 compute .", "rg -g '*.py' compute"])
def test_an_option_value_is_never_the_pattern(cmd):
    assert g.bash_pattern(cmd) == "compute"


def test_a_pack_for_a_name_in_another_case_does_not_answer():
    pack = "# Graph pack: changing the signature of `pkg/core.py::compute`\n..."
    assert g.same_case("compute", pack) and g.same_case("core.compute", pack)
    assert not g.same_case("Compute", pack) and not g.same_case("COMPUTE", pack)
    assert not g.same_case("def", "# Graph pack: changing the signature of `devkb/cpp_symbols.py::Def`")
