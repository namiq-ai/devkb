"""The words of the task break a tie between equally good names (session_context, ReadTools._rank_key, `devkb hook context`)."""
import json
import subprocess
import time
from pathlib import Path

from devkb import router, session_context
from devkb.process_api import ProcessAPI

PROMPT = ("Fix the C++ macro call edges: a call through a macro is dropped by cpp_resolve. Where to start: the resolve step. "
          "Done when: the regression test passes.")


def project(tmp_path: Path) -> Path:
    (tmp_path / "devkb").mkdir()
    (tmp_path / "devkb" / "cpp_resolve.py").write_text('def resolve(units):\n    """Link a C++ call to its definition."""\n    return units\n')
    (tmp_path / "devkb" / "project_context.py").write_text("def resolve(code):\n    return code\n\n\ndef a():\n    resolve(1)\n\n\ndef b():\n    resolve(2)\n")
    (tmp_path / "devkb" / "boundaries.py").write_text("def resolve(records):\n    return records\n\n\ndef c():\n    resolve(3)\n")
    (tmp_path / ".git").mkdir()
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    subprocess.run(["git", "add", "devkb"], cwd=tmp_path, check=True)
    subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@e.x", "commit", "-qm", "x"], cwd=tmp_path, check=True)
    from devkb.cli import main  # noqa: PLC0415
    assert main(["build", "--project", str(tmp_path)]) == 0
    return tmp_path


def order(tmp_path: Path, capsys) -> list[str]:
    from devkb.cli import main  # noqa: PLC0415
    capsys.readouterr()
    assert main(["symbol", "resolve", "--project", str(tmp_path)]) == 0
    return [ln.split()[1] for ln in capsys.readouterr().out.splitlines() if ln[:1].isdigit()]


def test_words_are_task_words_not_noise():
    w = session_context.words(PROMPT)
    assert {"macro", "cpp", "resolve", "regression"} <= set(w) and "the" not in w and "this" not in w
    assert "cppresolve" in w and "cpp_resolve" not in w                      # an identifier: its parts and the joined form
    assert len(session_context.words("word " * 5000 + " ".join(f"w{i}abc" for i in range(500)))) <= session_context.MAX_WORDS


def test_without_a_record_the_busiest_definition_leads_and_with_one_the_task_does(tmp_path, capsys):
    p = project(tmp_path)
    assert order(p, capsys)[0] == "devkb/project_context.py"                          # most callers: the old order, unchanged
    session_context.record(p, PROMPT)
    assert order(p, capsys)[0] == "devkb/cpp_resolve.py"                              # the task is about cpp
    (p / ".devkb" / session_context.NAME).write_text(json.dumps({"at": time.time() - 13 * 3600, "words": ["cpp"]}))
    assert order(p, capsys)[0] == "devkb/project_context.py"                          # aged out: the hint is gone
    (p / ".devkb" / session_context.NAME).write_text("{not json")
    assert order(p, capsys)[0] == "devkb/project_context.py"                          # unreadable: the old order, no error


def test_a_hint_never_removes_a_match(tmp_path, capsys):
    p = project(tmp_path)
    session_context.record(p, PROMPT)
    assert sorted(order(p, capsys)) == ["devkb/boundaries.py", "devkb/cpp_resolve.py", "devkb/project_context.py"]


def test_the_context_hook_records_and_pushes_nothing(tmp_path, monkeypatch, capsys):
    p = project(tmp_path)
    capsys.readouterr()
    monkeypatch.setenv("CLAUDE_PROJECT_DIR", str(p))
    assert router.main_context({"prompt": PROMPT, "cwd": str(p)}) == 0
    assert capsys.readouterr().out == "" and "cpp" in session_context.load(p)
    monkeypatch.setenv("DEVKB_CONTEXT", "0")
    (p / ".devkb" / session_context.NAME).unlink()
    router.main_context({"prompt": PROMPT, "cwd": str(p)})
    assert not (p / ".devkb" / session_context.NAME).exists()


def test_the_prompt_router_records_too_even_when_it_pushes_nothing(tmp_path, monkeypatch):
    p = project(tmp_path)
    monkeypatch.setenv("CLAUDE_PROJECT_DIR", str(p))
    router.on_prompt({"prompt": "thanks, that works" + " fine" * 3, "cwd": str(p)})
    assert "fine" in session_context.load(p)
    monkeypatch.setenv("DEVKB_ROUTER", "0")
    router.on_prompt({"prompt": PROMPT, "cwd": str(p)})
    assert "macro" in session_context.load(p)                                 # the router's own off switch leaves the ranking on


def test_hook_dispatch_knows_context(monkeypatch, capsys):
    from devkb import hook
    monkeypatch.setattr(router, "main_context", lambda event=None: 0)
    assert hook.main(["context"]) == 0
    assert hook.main(["nonsense"]) == 2 and "pre-edit|prompt|context" in capsys.readouterr().err
