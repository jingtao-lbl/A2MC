"""The committed EcoSIM graph must carry every curated relation whose endpoints exist.

WHY THIS TEST EXISTS. `models/ecosim/curated_seed.yaml` states relations in five places and until 2026-09-08
`scripts/build_ecosim_rag.py` read three. The outputs block's `direct_drivers` /
`indirect_drivers` (73 edges, among them `RSMX -> ECO_ET_col`, the driver of the scored target a
live calibration round was stuck on) and `categories.*.key_outputs` (22 edges) were consumed by
the chunk text and by `tools/validate_curated_yaml.py`, which passed them, and by nothing that
builds anything. No count guard could see it: counts do not fall when an edge is never created,
and both fields were found by hand, one after the other, in the same audit.

The test asserts an IMPLICATION rather than a count, so it stays true as the seed grows: for every
curated relation whose two endpoints both exist as nodes, the edge is in the graph. It therefore
fails on two different regressions with one assertion, and both have happened here:

  * a builder pass removed or never written  (the 2026-09-08 defect)
  * the seed edited and the graph not rebuilt (a `--graph-only` run skipped, or forgotten)

Endpoints that do NOT resolve are reported, not failed: an unresolved driver name is a seed defect
for a human to fix, and minting a node for it is what put three phantom outputs in this graph in
2026-09-06. `CNWL` in `outputs.ECO_ET_col.indirect_drivers` is one such name today.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest
import yaml

REPO = Path(__file__).resolve().parent.parent
SEED = REPO / "models/ecosim/curated_seed.yaml"
GRAPH = REPO / "rag/graphs/ecosim-2dea74d9.json"

pytestmark = pytest.mark.skipif(not (SEED.exists() and GRAPH.exists()),
                                reason="EcoSIM seed or graph not present in this checkout")


def _load():
    seed = yaml.safe_load(SEED.read_text())
    g = json.load(GRAPH.open())
    nodes = {n["id"] for n in g["nodes"]}
    edges = {(e["source"], e["target"], e["relation_type"]) for e in g["links"]}
    return seed, nodes, edges


def _expected(seed):
    """-> list of (source_id, target_id, relation, where) for every curated relation."""
    out = []
    for cname, c in (seed.get("categories") or {}).items():
        for m in (c.get("mechanisms") or []):
            out.append((f"category:{cname}", f"mechanism:{m}", "contains",
                        f"categories.{cname}.mechanisms"))
        for o in (c.get("key_outputs") or []):
            out.append((f"category:{cname}", f"output:{o}", "affects",
                        f"categories.{cname}.key_outputs"))
    for mname, m in (seed.get("mechanisms") or {}).items():
        for p in (m.get("parameters") or []):
            out.append((f"parameter:{p.split('#')[0].strip()}", f"mechanism:{mname}", "controls",
                        f"mechanisms.{mname}.parameters"))
        for o in (m.get("affects") or []):
            out.append((f"mechanism:{mname}", f"output:{o}", "affects",
                        f"mechanisms.{mname}.affects"))
    for pname, p in (seed.get("parameters") or {}).items():
        for m in (p.get("controls") or []):
            out.append((f"parameter:{pname}", f"mechanism:{m}", "controls",
                        f"parameters.{pname}.controls"))
        for o in (p.get("affects") or []):
            out.append((f"parameter:{pname}", f"output:{o}", "affects",
                        f"parameters.{pname}.affects"))
    for oname, o in (seed.get("outputs") or {}).items():
        for field in ("direct_drivers", "indirect_drivers"):
            for p in (o.get(field) or []):
                out.append((f"parameter:{p}", f"output:{oname}", "affects",
                            f"outputs.{oname}.{field}"))
    return out


def test_every_resolvable_curated_relation_is_an_edge():
    seed, nodes, edges = _load()
    missing = [
        f"{where}: {s} -{r}-> {t}"
        for s, t, r, where in _expected(seed)
        if s in nodes and t in nodes and (s, t, r) not in edges
    ]
    assert not missing, (
        f"{len(missing)} curated relation(s) have both endpoints in the graph but no edge. "
        f"Rebuild with `python scripts/build_ecosim_rag.py --graph-only`, or fix the builder "
        f"if a whole seed block is being skipped:\n  " + "\n  ".join(missing[:25]))


def test_the_outputs_block_specifically_is_wired():
    """The 2026-09-08 defect, pinned on its own so a regression names itself.

    Without it the general test above still fails, but its message is a list of 73 lines that
    reads like a stale graph rather than like a missing builder pass.
    """
    seed, nodes, edges = _load()
    drivers = [(s, t, r, w) for s, t, r, w in _expected(seed) if ".direct_drivers" in w
               or ".indirect_drivers" in w]
    resolvable = [(s, t, r) for s, t, r, _ in drivers if s in nodes and t in nodes]
    assert resolvable, "no output-block driver resolves; the seed or the graph is not the expected one"
    absent = [e for e in resolvable if e not in edges]
    assert not absent, (
        f"{len(absent)} of {len(resolvable)} output-block driver edges are missing. The builder's "
        f"`outputs -> {{direct,indirect}}_drivers` pass in scripts/build_ecosim_rag.py is the one "
        f"that creates these; PFLOTRAN's builder has the equivalent pass.")


def test_unresolved_driver_names_are_reported_not_minted():
    """A curated driver name must either resolve to a REAL parsed parameter or not exist at all.

    The failure this pins is minting: creating a bare node for a name that is in no parameter
    surface, so the graph answers queries about something the model does not have. Three phantom
    OUTPUTS entered this graph that way and were removed on 2026-09-06. A parsed parameter node
    carries a description or units from its NetCDF surface; a minted one carries neither.
    """
    seed, nodes, _ = _load()
    attrs = {n["id"]: n for n in json.load(GRAPH.open())["nodes"]}
    driver_names = {s[10:] for s, t, r, where in _expected(seed)
                    if ".direct_drivers" in where or ".indirect_drivers" in where}

    bare = sorted(n for n in driver_names
                  if f"parameter:{n}" in nodes
                  and not (attrs[f"parameter:{n}"].get("description")
                           or attrs[f"parameter:{n}"].get("units")))
    assert not bare, (
        f"{len(bare)} output-block driver name(s) exist as nodes with no description and no units, "
        f"which is what a minted node looks like: {bare}. The builder should SKIP an unresolved "
        f"name, not create it.")

    unresolved = sorted(n for n in driver_names if f"parameter:{n}" not in nodes)
    # Not a build failure: this is the seed's own defect list, asserted only to stay small and
    # visible. `CNWL` (outputs.ECO_ET_col.indirect_drivers) is the one entry today; it matches no
    # parameter in either parsed surface and needs a human to say what it should have been.
    assert len(unresolved) <= 1, (
        f"unresolved output-block driver names grew to {len(unresolved)}: {unresolved}. Each is a "
        f"name in the seed matching no parameter in any parsed surface. Fix the seed; do not let "
        f"the builder mint a node for it.")
