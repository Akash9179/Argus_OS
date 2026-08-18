"""The Engineering Knowledge Graph consistency gate (laws 17 and 18).

The graph in architecture/graph/*.yaml is the machine-readable truth about
what exists and how mature it is. These tests make architecture drift a CI
failure: a dangling reference, a deleted module the graph still claims, a
maturity promotion without evidence, or a stale STATUS.md all fail the build.
"""

import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "scripts"))

import argus_graph  # noqa: E402


def test_graph_is_internally_consistent():
    graph = argus_graph.load_graph()
    errors = argus_graph.validate(graph)
    assert not errors, "\n".join(errors)


def test_status_md_matches_the_graph():
    graph = argus_graph.load_graph()
    expected = argus_graph.render_status(graph)
    actual = (REPO / "STATUS.md").read_text(encoding="utf-8")
    assert actual == expected, (
        "STATUS.md has drifted from the engineering graph. Regenerate it: "
        ".venv/bin/python scripts/argus_graph.py status --write"
    )


def test_hardware_claims_require_hardware_evidence():
    """Law 17 directly: nothing may claim hardware maturity without a run."""
    graph = argus_graph.load_graph()
    for c in graph["components"]:
        if c["status"] in argus_graph.NEEDS_HARDWARE_EVIDENCE:
            runs = (c.get("evidence") or {}).get("hardware_runs") or []
            assert runs, f"{c['id']} claims {c['status']} with no hardware evidence"


def test_planned_components_claim_no_code():
    graph = argus_graph.load_graph()
    for c in graph["components"]:
        if c["status"] == "planned":
            assert c.get("path") is None, (
                f"{c['id']} is planned but claims a path; if code exists it is "
                "at least scaffolded, if not the path is a lie"
            )


def test_cli_runs():
    """The query CLI must at least answer validate and status."""
    out = subprocess.run(
        [sys.executable, str(REPO / "scripts" / "argus_graph.py"), "validate"],
        capture_output=True, text=True,
    )
    assert out.returncode == 0, out.stdout + out.stderr
