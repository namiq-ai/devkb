"""#315: the release workflow builds devkb's own graph at the tag, with the GitHub layer, fails when the build or its manifest is not at the tag, and
publishes the graph as a release asset. The workflow is YAML read as data; running it is the `workflow_dispatch` rehearsal."""
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
WF = yaml.safe_load((ROOT / ".github" / "workflows" / "release.yml").read_text())
JOBS = WF["jobs"]


def steps_text(job):
    return "\n".join(str(s.get("run", "")) + " " + str(s.get("uses", "")) + " " + str(s.get("name", "")) for s in JOBS[job]["steps"])


def test_a_graph_job_builds_the_graph_with_the_github_layer_after_the_tests():
    assert "graph" in JOBS and JOBS["graph"]["needs"] == "test"
    assert "devkb.cli build --project . --github" in steps_text("graph")
    env = [s.get("env", {}) for s in JOBS["graph"]["steps"] if "build --project" in str(s.get("run", ""))]
    assert env and env[0].get("GITHUB_TOKEN"), "the GitHub layer needs the workflow's token"


def test_the_graph_job_is_read_only_and_reads_history():
    perms = JOBS["graph"]["permissions"]
    assert all(v == "read" for v in perms.values()), perms
    assert any(s.get("with", {}).get("fetch-depth") == 0 for s in JOBS["graph"]["steps"] if "checkout" in str(s.get("uses", ""))), "the graph reads the history"


def test_a_manifest_that_is_not_at_the_commit_fails_the_release():
    text = steps_text("graph")
    assert "manifest.json" in text and "git_head" in text and "git rev-parse HEAD" in text and "exit 1" in text


def test_the_graph_is_packed_and_published_with_the_release():
    assert "devkb-graph-" in steps_text("graph") and any(s.get("uses", "").startswith("actions/upload-artifact") for s in JOBS["graph"]["steps"])
    assert set(JOBS["release"]["needs"]) >= {"build", "graph"}, "no release without the graph"
    assert "devkb-graph-" in JOBS["release"]["steps"][1]["run"]


def test_releasing_lists_the_graph_step_and_the_local_rebuild():
    doc = (ROOT / "docs" / "RELEASING.md").read_text()
    assert "**graph**" in doc and "devkb-graph-<tag>.tar.gz" in doc
    assert "build --project . --github" in doc.split("After tagging")[1]
