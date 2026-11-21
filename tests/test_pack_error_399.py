"""#399: `pack error MESSAGE` names the functions that raise the message, not functions that share a word with it."""
import subprocess

from devkb.cli import main


def repo(tmp_path):
    (tmp_path / "pkg").mkdir()
    (tmp_path / "pkg" / "rx.py").write_text(
        "def compile_pattern(q):\n    try:\n        return q\n    except ValueError as e:\n        raise ValueError(f\"bad regular expression: {e}\")\n")
    # raise sites that share words with the message but are not it
    (tmp_path / "pkg" / "other.py").write_text(
        "def check_a(x):\n    raise ValueError('expression is too long for this regular tenant')\n\n\n"
        "def check_b(x):\n    raise KeyError(f'regular users cannot edit this expression {x}')\n\n\n"
        "def check_c(x):\n    raise RuntimeError('a bad day for regular maintenance of the expression cache')\n")
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    subprocess.run(["git", "add", "."], cwd=tmp_path, check=True)
    subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@e.x", "commit", "-qm", "x"], cwd=tmp_path, check=True)
    assert main(["build", "--project", str(tmp_path)]) == 0


def pack(tmp_path, capsys, text):
    capsys.readouterr()
    assert main(["pack", "--project", str(tmp_path), "error", text]) == 0
    return capsys.readouterr().out


def raised_by(out):
    sec = out.split("## Raised by", 1)[-1].split("\n## ", 1)[0] if "## Raised by" in out else ""
    return [ln.split("`")[1] for ln in sec.splitlines() if ln.startswith("- `")]


def test_a_message_typed_without_its_variable_part_names_only_its_raiser(tmp_path, capsys):
    repo(tmp_path)
    assert raised_by(pack(tmp_path, capsys, "bad regular expression")) == ["pkg/rx.py::compile_pattern"]      # the message minus `: {e}`
    assert raised_by(pack(tmp_path, capsys, "bad regular expression: unterminated group")) == ["pkg/rx.py::compile_pattern"]


def test_a_message_that_no_code_raises_says_so_and_lists_no_function(tmp_path, capsys):
    repo(tmp_path)
    out = pack(tmp_path, capsys, "quantum flux capacitor misaligned during warp")
    assert raised_by(out) == [] and "No function in the graph raises or logs this text" in out
    assert "devkb docs" in out                                                                                # it points at the searches that can still find a text
    out = pack(tmp_path, capsys, "regular expression cache layer warms slowly")                                  # two words in common with three raise sites, the message of none
    assert raised_by(out) == [] and "No function in the graph raises or logs this text" in out
