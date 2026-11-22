"""#317: a search that reaches a Makefile, Dockerfile, .env, .properties, .tf, .jsonc or lockfile is never replaced by the graph's code-only answer."""
import importlib.util
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
_spec = importlib.util.spec_from_file_location("devkb_guardrail", ROOT / "scripts" / "devkb_guardrail.py")
g = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(g)

CONFIG = ["Makefile", "sub/Makefile", "GNUmakefile", "Dockerfile", "Dockerfile.dev", "app.dockerfile", "Containerfile", ".env", ".env.local",
          "app.properties", "main.tf", "prod.tfvars", "tsconfig.jsonc", "poetry.lock", "package.lock", "rules.mk", "x.cmake", "build.gradle",
          "Jenkinsfile", "Gemfile", "Procfile"]
CODE = ["pkg/a.py", "src/a.c", "lib/x.rb", "main.go", "app.ts", "environment.py", "envelope.cc", "dockerfile_parser.py", "lockfile.py"]


@pytest.mark.parametrize("path", CONFIG)
def test_each_configuration_file_kind_is_non_code(path):
    assert g.is_non_code(path), path


@pytest.mark.parametrize("path", CODE)
def test_code_that_merely_resembles_a_config_name_is_still_code(path):
    assert not g.is_non_code(path), path


def test_a_named_configuration_path_stops_a_replacement(tmp_path):
    for p in ("Makefile", "deploy/Dockerfile", ".env"):
        assert g.names_non_code([tmp_path / p], tmp_path), p
    assert not g.names_non_code([tmp_path / "pkg" / "a.py"], tmp_path)


def test_a_name_found_in_a_makefile_stops_the_replacement_of_a_repository_wide_search(tmp_path):
    (tmp_path / "pkg").mkdir()
    (tmp_path / "pkg" / "a.py").write_text("def build_image():\n    return 1\n")
    (tmp_path / "Makefile").write_text("image:\n\t./run build_image\n")
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)
    subprocess.run(["git", "add", "-A"], cwd=tmp_path, check=True)
    assert g.names_non_code(None, tmp_path, ["build_image"], None), "grep prints the Makefile line too: the graph's code-only answer would hide it"
