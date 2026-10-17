"""`tools/graph_gaps.py` must refuse a gap candidate nobody can check, and promote only what a human accepted.

visibility: public

A knowledge-graph gap candidate is staged in a cycle report's folder and promoted to
`models/<model>/` only after a human reviews it (`memory/dev_logs_adapterkit/20261017d_*`). The graph holds source-code
relationships, so a candidate without a source line, of a shape the graph cannot hold, or already in
the graph is not a gap; and promotion must never move an entry still pending review.

**Every test here is a way the tool must FAIL or refuse** (`feedback_a_check_that_cannot_fail`),
plus one positive control that a well-formed file passes.

Author: Jing Tao with Claude on Perlmutter
"""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]


def _mod(name, rel):
    sp = importlib.util.spec_from_file_location(name, ROOT / rel)
    m = importlib.util.module_from_spec(sp)
    sp.loader.exec_module(m)
    return m


GG = _mod("gg_under_test", "tools/graph_gaps.py")
KN = _mod("kn_under_test", "tools/kb_network.py")


@pytest.fixture
def graph(tmp_path):
    """A four-node graph: parameter:A -controls-> mechanism:M -affects-> output:O, and parameter:B."""
    nodes = [dict(id=i, node_type=i.split(":")[0].title(), name=i.split(":")[1])
             for i in ("parameter:A", "parameter:B", "mechanism:M", "output:O")]
    links = [dict(source="parameter:A", target="mechanism:M", relation_type="controls", weight=1.0),
             dict(source="mechanism:M", target="output:O", relation_type="affects", weight=1.0)]
    p = tmp_path / "g.json"
    p.write_text(json.dumps(dict(directed=True, multigraph=False, graph={}, nodes=nodes, links=links)))
    return KN.Graph(p)


def cand(**over):
    c = dict(id="G1", **{"from": "parameter:B"}, relation="controls", to="mechanism:M",
             source="f90src/Plant_bgc/X.F90:10", claim="B sets M's rate", prompted_by="a run",
             found="2026-10-17", review="pending")
    c.update(over)
    return c


def write(tmp_path, candidates, new_nodes=None, name="graph_gap_candidates.yaml"):
    p = tmp_path / name
    p.write_text(yaml.safe_dump(dict(schema=1, model="toy", profile="toy-1", source_commit="abc1234",
                                     new_nodes=new_nodes or {}, candidates=candidates), sort_keys=False))
    return p


def test_a_well_formed_file_passes(tmp_path, graph):
    errs, _ = GG.check(write(tmp_path, [cand()]), graph)
    assert errs == []


def test_an_empty_candidate_list_passes(tmp_path, graph):
    errs, _ = GG.check(write(tmp_path, []), graph)
    assert errs == []


@pytest.mark.parametrize("source", ["", "f90src/X.F90", "see the code", "X.F90:abc"])
def test_a_candidate_without_a_source_line_fails(tmp_path, graph, source):
    errs, _ = GG.check(write(tmp_path, [cand(source=source)]), graph)
    assert errs, f"source {source!r} was accepted"


def test_a_chain_of_citations_is_accepted_and_each_is_checked(tmp_path, graph):
    ok, _ = GG.check(write(tmp_path, [cand(source=["a/X.F90:1", "a/Y.F90:2-9"])]), graph)
    bad, _ = GG.check(write(tmp_path, [cand(source=["a/X.F90:1", "not a cite"])]), graph)
    assert ok == [] and bad


def test_a_shape_the_graph_cannot_hold_fails(tmp_path, graph):
    errs, _ = GG.check(write(tmp_path, [cand(**{"from": "mechanism:M"}, relation="affects", to="mechanism:N")],
                             new_nodes={"mechanism:N": "a second mechanism"}), graph)
    assert any("shape" in e for e in errs)


def test_an_edge_already_in_the_graph_is_not_a_gap(tmp_path, graph):
    errs, _ = GG.check(write(tmp_path, [cand(**{"from": "parameter:A"})]), graph)
    assert any("not a gap" in e for e in errs)


def test_an_unknown_endpoint_must_be_declared_as_a_new_node(tmp_path, graph):
    bad, _ = GG.check(write(tmp_path, [cand(to="mechanism:Unknown")]), graph)
    ok, _ = GG.check(write(tmp_path, [cand(to="mechanism:Unknown")], new_nodes={"mechanism:Unknown": "what it is"}), graph)
    assert bad and ok == []


def test_duplicate_ids_and_bad_review_states_fail(tmp_path, graph):
    dup, _ = GG.check(write(tmp_path, [cand(), cand(to="output:O", relation="affects")]), graph)
    rev, _ = GG.check(write(tmp_path, [cand(review="approved")]), graph)
    assert any("duplicate" in e for e in dup) and any("review" in e for e in rev)


def test_promote_moves_only_accepted_entries_and_never_twice(tmp_path, graph):
    src = write(tmp_path, [cand(id="G1", review="accepted"),
                           cand(id="G2", **{"from": "parameter:B"}, relation="affects", to="output:O", review="pending"),
                           cand(id="G3", relation="depends_on", to="parameter:A", review="rejected")])
    models = tmp_path / "models"
    assert GG.promote(src, g=graph, models_root=models) == 0
    dst = yaml.safe_load((models / "toy" / "graph_gap_candidates.yaml").read_text())
    assert [c["promoted_from"].split("#")[1] for c in dst["candidates"]] == ["G1"]
    assert GG.promote(src, g=graph, models_root=models) == 0
    again = yaml.safe_load((models / "toy" / "graph_gap_candidates.yaml").read_text())
    assert len(again["candidates"]) == 1


def test_promote_refuses_a_file_that_fails_check(tmp_path, graph):
    src = write(tmp_path, [cand(source="no line", review="accepted")])
    models = tmp_path / "models"
    assert GG.promote(src, g=graph, models_root=models) == 1
    assert not (models / "toy").exists()
