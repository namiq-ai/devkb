"""The benchmark's source truth: calls between methods of one class, handlers reached through other handlers, and
messages raised as keyword arguments."""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "devkb" / "bench"))
import module_truth as mt  # noqa: E402

FILES = {
    "app/__init__.py": "",
    "app/events.py": "def publish(items):\n    return items\n",
    "app/routes.py": (
        "from app.events import publish\n\n\n"
        "class ItemController:\n"
        "    @router.post('/bulk')\n"
        "    def create_many(self, items):\n"
        "        publish(items)\n\n"
        "    @router.post('')\n"
        "    def create_one(self, item):\n"
        "        return self.create_many([item])\n\n"
        "    def helper(self):\n"
        "        return self.create_many([])\n\n\n"
        "@router.get('/history')\n"
        "def history(interval):\n"
        "    if interval < 1:\n"
        "        raise HTTPException(422, detail='History interval must not be less than 1 second.')\n"
        "    return interval\n"
    ),
    "tests/test_events.py": "from app.events import publish\n\n\ndef test_publish():\n    publish([])\n",
}


def _truth(tmp_path: Path) -> mt.Truth:
    for rel, text in FILES.items():
        (tmp_path / rel).parent.mkdir(parents=True, exist_ok=True)
        (tmp_path / rel).write_text(text)
    for cmd in (["init", "-q"], ["add", "-A"], ["-c", "user.email=t@example.com", "-c", "user.name=T", "commit", "-qm", "x"]):
        subprocess.run(["git", *cmd], cwd=tmp_path, check=True, capture_output=True)
    return mt.Truth(tmp_path)


def test_a_handler_reaching_the_function_through_another_handler_of_its_class_is_found(tmp_path):
    T = _truth(tmp_path)
    prod, tests, clean = T.up(("app/events.py", "publish"))
    handlers = {mt.short(k) for k in prod if T.is_route(k)}
    assert handlers == {"app/routes.py::create_many", "app/routes.py::create_one"}
    assert {k[0] for k in tests} == {"tests/test_events.py"}
    assert not clean, "a non-route method (helper) is on a path: outside objects may call it, so not complete"


def test_a_message_raised_as_a_detail_keyword_is_a_raise(tmp_path):
    T = _truth(tmp_path)
    assert ("history", "History interval must not be less than 1 second.") in T.files["app/routes.py"].raises


def test_files_in_a_tests_tree_are_test_code_for_the_tools():
    from devkb.process_api import is_test_path
    assert is_test_path("tests/fixtures/fixture_users.py") and is_test_path("pkg/tests/conftest.py")
    assert is_test_path("test/helpers.py") and not is_test_path("app/testing_utils.py")
