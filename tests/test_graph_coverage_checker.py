"""`tools/check_graph_coverage.py` must FAIL on an unread relation field and PASS on a wired one.

The checker exists because a curated field no builder reads is invisible to every other mechanism:
it passes the YAML validator, emits no skip line, and moves no count. A checker for that class is
worth nothing unless it demonstrably fires, so both directions are asserted here on synthetic
artifacts rather than on the repo's live ones, which change under it.
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
CHECKER = REPO / "tools/check_graph_coverage.py"

pytestmark = pytest.mark.skipif(not CHECKER.exists(), reason="checker not present")


def _fixture(tmp_path: Path, wired: bool):
    """A one-profile registry whose seed states two relations; `wired` decides if one is an edge."""
    seed = tmp_path / "seed.yaml"
    seed.write_text(
        "parameters:\n"
        "  ALPHA:\n"
        "    affects: [OUT_ONE]\n"
        "categories:\n"
        "  physics:\n"
        "    key_outputs: [OUT_ONE]\n"
    )
    links = [{"source": "parameter:ALPHA", "target": "output:OUT_ONE", "relation_type": "affects"}]
    if wired:
        links.append({"source": "category:physics", "target": "output:OUT_ONE",
                      "relation_type": "affects"})
    graph = {"directed": True, "multigraph": False, "graph": {},
             "nodes": [{"id": "parameter:ALPHA", "node_type": "Parameter"},
                       {"id": "output:OUT_ONE", "node_type": "Output"},
                       {"id": "category:physics", "node_type": "Category"}],
             "links": links}
    root = tmp_path / "repo"
    (root / "rag/graphs").mkdir(parents=True)
    (root / "tools").mkdir(parents=True)
    (root / "rag/graphs/fixture.json").write_text(json.dumps(graph))
    (root / "rag/milestones.json").write_text(json.dumps(
        {"milestones": {"fixture": {"curated_yaml_path": "seed.yaml"}}}))
    (root / "seed.yaml").write_text(seed.read_text())
    (root / "tools/check_graph_coverage.py").write_text(CHECKER.read_text())
    return root


def _run(root: Path):
    return subprocess.run([sys.executable, str(root / "tools/check_graph_coverage.py")],
                          capture_output=True, text=True)


def test_wired_field_passes(tmp_path):
    r = _run(_fixture(tmp_path, wired=True))
    assert r.returncode == 0, f"expected clean, got {r.returncode}\n{r.stdout}\n{r.stderr}"
    assert "categories.key_outputs" in r.stdout and "wired" in r.stdout


def test_unread_field_fails_and_names_itself(tmp_path):
    """The negative control. Remove the one edge and the checker must go red and say which field."""
    r = _run(_fixture(tmp_path, wired=False))
    assert r.returncode == 1, f"expected failure, got {r.returncode}\n{r.stdout}\n{r.stderr}"
    assert "UNREAD" in r.stdout
    assert "categories.key_outputs" in r.stderr, "the failure must NAME the field, not just count it"
    assert "parameters.affects" not in r.stderr, "the wired field must not be reported"
