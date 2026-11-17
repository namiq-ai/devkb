"""#99: the devkb command prints a subcommand's error message instead of exiting silently."""
from __future__ import annotations

from devkb import cli


def test_a_subcommand_error_message_reaches_stderr(tmp_path, capsys):
    rc = cli.main(["init", "--project", str(tmp_path), "--no-build"])  # not a git repository
    err = capsys.readouterr().err
    assert rc == 1
    assert "is not a git repository" in err, err


def test_a_numeric_exit_code_still_passes_through_silently(monkeypatch, capsys):
    import runpy

    def fake(module, run_name, alter_sys):
        raise SystemExit(3)
    monkeypatch.setattr(runpy, "run_module", fake)
    assert cli._run("devkb.anything", []) == 3
    assert capsys.readouterr().err == ""
