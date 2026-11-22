"""#400: a call on a name bound by unpacking a helper's tuple of constructed objects is attributed to the method."""
import subprocess
from devkb.cli import main


def test_calls_through_unpacked_helper_results_are_resolved(tmp_path, capsys):
    (tmp_path / "pkg").mkdir()
    (tmp_path / "pkg" / "m.py").write_text("class Api:\n    def go(self):\n        return 1\n\n\nclass Packer:\n    def run(self):\n        return 2\n")
    (tmp_path / "pkg" / "t.py").write_text(
        "from pkg.m import Api, Packer\n\n\ndef make():\n    a = Api()\n    return a, Packer()\n\n\ndef use():\n    api, packer = make()\n    api.go()\n    packer.run()\n")
    for c in (["init", "-q"], ["add", "."], ["-c", "user.name=t", "-c", "user.email=t@e.x", "commit", "-qm", "x"]):
        subprocess.run(["git", *c], cwd=tmp_path, check=True, capture_output=True)
    assert main(["build", "--project", str(tmp_path)]) == 0
    import json
    edges = [json.loads(l) for l in (tmp_path / ".devkb" / "edges.jsonl").read_text().splitlines()]
    refs = {e["properties"].get("evidence_ref", "") for e in edges if e.get("verb") == "CALLS"}
    assert any(r.startswith("pkg/t.py::use calls go") for r in refs) and any(r.startswith("pkg/t.py::use calls run") for r in refs), sorted(refs)


def test_a_helper_in_another_file_is_followed(tmp_path):
    import json
    (tmp_path / "pkg").mkdir()
    (tmp_path / "pkg" / "m.py").write_text("class Api:\n    def go(self):\n        return 1\n\n\nclass Packer:\n    def run(self):\n        return 2\n")
    (tmp_path / "pkg" / "h.py").write_text("from pkg.m import Api, Packer\n\n\ndef make():\n    a = Api()\n    return a, Packer()\n")
    (tmp_path / "pkg" / "t.py").write_text("import pkg.h as H\nfrom pkg.h import make\n\n\ndef use():\n    api, packer = H.make()\n    api.go()\n\n\ndef use_bare():\n    api, packer = make()\n    packer.run()\n")
    for c in (["init", "-q"], ["add", "."], ["-c", "user.name=t", "-c", "user.email=t@e.x", "commit", "-qm", "x"]):
        subprocess.run(["git", *c], cwd=tmp_path, check=True, capture_output=True)
    assert main(["build", "--project", str(tmp_path)]) == 0
    refs = {json.loads(l)["properties"].get("evidence_ref", "") for l in (tmp_path / ".devkb" / "edges.jsonl").read_text().splitlines()
            if json.loads(l).get("verb") == "CALLS"}
    assert any(r.startswith("pkg/t.py::use calls go") for r in refs) and any(r.startswith("pkg/t.py::use_bare calls run") for r in refs), sorted(refs)


def test_a_method_named_like_the_helper_does_not_replace_it(tmp_path):
    import json
    (tmp_path / "pkg").mkdir()
    (tmp_path / "pkg" / "m.py").write_text("class Api:\n    def go(self):\n        return 1\n\n\nclass Other:\n    pass\n")
    (tmp_path / "pkg" / "h.py").write_text(
        "from pkg.m import Api, Other\n\n\nclass K:\n    def make(self):\n        return Other(), Other()\n\n\n"
        "def make():\n    return Api(), Api()\n\n\ndef use():\n    a, b = make()\n    a.go()\n")
    for c in (["init", "-q"], ["add", "."], ["-c", "user.name=t", "-c", "user.email=t@e.x", "commit", "-qm", "x"]):
        subprocess.run(["git", *c], cwd=tmp_path, check=True, capture_output=True)
    assert main(["build", "--project", str(tmp_path)]) == 0
    refs = {json.loads(l)["properties"].get("evidence_ref", "") for l in (tmp_path / ".devkb" / "edges.jsonl").read_text().splitlines()
            if json.loads(l).get("verb") == "CALLS"}
    assert any(r.startswith("pkg/h.py::use calls go on a Api") for r in refs), sorted(refs)
