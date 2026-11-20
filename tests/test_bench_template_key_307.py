"""#307: every setting that changes a checkout's content is part of its template key: the suite (#331) and the pre-registered PostToolUse hook."""
import importlib
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HERE / "bench" / "policy"))
pb = importlib.import_module("policybench")
sb = importlib.import_module("storybench")


def _key(tmp_path, monkeypatch, **env):
    for k in ("POLICY_PREREGISTER_POST", "POLICY_EQUAL_SUITE"):
        monkeypatch.delenv(k, raising=False)
    for k, v in env.items():
        monkeypatch.setenv(k, v)
    monkeypatch.setattr(pb, "TEMPLATES", tmp_path)
    monkeypatch.setattr(sb, "REPO", HERE)
    monkeypatch.setitem(pb.BASES, "climain", "HEAD")
    built = []
    monkeypatch.setattr(pb, "checkout", lambda t, arm: (built.append(Path(t).name), Path(t).mkdir(parents=True, exist_ok=True))[0])
    return pb.template_for("climain"), built


def test_the_preregister_flag_gets_its_own_template(tmp_path, monkeypatch):
    plain, built = _key(tmp_path, monkeypatch)
    post, built = _key(tmp_path, monkeypatch, POLICY_PREREGISTER_POST="1")
    assert plain != post and post.name.endswith("-post") and not plain.name.endswith("-post") and built == [post.name]


def test_the_same_settings_reuse_the_template_and_other_values_of_the_flag_do_not_count(tmp_path, monkeypatch):
    a, built = _key(tmp_path, monkeypatch, POLICY_PREREGISTER_POST="1")
    b, built = _key(tmp_path, monkeypatch, POLICY_PREREGISTER_POST="1")
    c, built = _key(tmp_path, monkeypatch, POLICY_PREREGISTER_POST="0")
    assert a == b and len(built) == 1               # only "1" turns the hook on (the code's own test)
    assert c != a


def test_the_suite_setting_and_the_flag_make_four_distinct_templates(tmp_path, monkeypatch):
    names = {_key(tmp_path, monkeypatch, **e)[0].name for e in
             ({}, {"POLICY_EQUAL_SUITE": "0"}, {"POLICY_PREREGISTER_POST": "1"}, {"POLICY_EQUAL_SUITE": "0", "POLICY_PREREGISTER_POST": "1"})}
    assert len(names) == 4
