"""tools/check_kg_html_current.py: a knowledge graph's HTML view describes the graph it was rendered from.

visibility: public

The first tests are positive controls: a page rendered before an edge, a node or an attribute changed
must be reported, or every pass below is vacuous. The last uses a real stale page, the one recorded in
memory/dev_logs_adapterkit/20261016j_A_Graph_And_Its_HTML_View_Are_Checked_Against_Each_Other.md.
"""
import json
import subprocess
from pathlib import Path

import pytest

from tools.check_kg_html_current import compare, embedded_data
from tools.render_kg_html import graph_from_json, page

ROOT = Path(__file__).resolve().parent.parent

GRAPH = {
    "nodes": [{"id": "parameter:A", "node_type": "Parameter", "name": "A", "description": "a"},
              {"id": "mechanism:M", "node_type": "Mechanism", "name": "M", "description": "m"},
              {"id": "output:O", "node_type": "Output", "name": "O", "description": "o"},
              {"id": "output:ISOLATED", "node_type": "Output", "name": "ISOLATED", "description": ""}],
    "links": [{"source": "parameter:A", "target": "mechanism:M", "relation": "controls"},
              {"source": "mechanism:M", "target": "output:O", "relation": "affects"}],
}


def render(graph):
    nodes, links = graph_from_json(graph)
    keep = {l["source"] for l in links} | {l["target"] for l in links}
    return page("p", nodes, links, keep, [], [], "", "h", "s", "", ["Category"])


def test_new_edge_and_node_are_reported():
    newer = json.loads(json.dumps(GRAPH))
    newer["nodes"].append({"id": "mechanism:N", "node_type": "Mechanism", "name": "N", "description": ""})
    newer["links"].append({"source": "mechanism:N", "target": "output:O", "relation": "affects"})
    out = compare(newer, render(GRAPH), "page")
    assert out and "STALE" in out[0]
    assert any("mechanism:N" in line and "missing" in line for line in out)


def test_changed_attribute_is_reported():
    newer = json.loads(json.dumps(GRAPH))
    newer["nodes"][1]["description"] = "rewritten"
    out = compare(newer, render(GRAPH), "page")
    assert out and "attributes differ" in out[-1]


def test_removed_edge_is_reported():
    newer = json.loads(json.dumps(GRAPH))
    newer["links"].pop()
    out = compare(newer, render(GRAPH), "page")
    assert any("no longer in the graph" in line for line in out)


def test_in_step_page_passes_and_isolated_nodes_are_not_expected():
    html = render(GRAPH)
    assert compare(GRAPH, html, "page") == []
    assert "output:ISOLATED" not in {n["id"] for n in embedded_data(html)["nodes"]}


def test_render_is_deterministic():
    assert render(GRAPH) == render(json.loads(json.dumps(GRAPH)))


def test_a_page_with_no_data_is_reported():
    assert compare(GRAPH, "<html></html>", "page")


def test_the_real_stale_page_of_2026_10_16_is_caught():
    rel = "docs/ecosim-knowledge-base/graph_html/ecosim-cb243228_knowledge_graph.html"
    r = subprocess.run(["git", "-C", str(ROOT), "show", f"08690063:{rel}"], stdout=subprocess.PIPE,
                       stderr=subprocess.PIPE, universal_newlines=True)
    if r.returncode != 0:
        pytest.skip("history not available in this clone")
    graph = json.loads((ROOT / "rag/graphs/ecosim-cb243228.json").read_text())
    out = compare(graph, r.stdout, rel)
    assert any("Plant_Death_Root_Litterfall_And_Replanting" in line for line in out)
