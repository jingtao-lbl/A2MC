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
2026-09-06. `CNWL` in `outputs.ECO_ET_col.indirect_drivers` was the one such name until 2026-09-11,
and the way it was fixed is the second thing this file now pins. It was never a seed defect: the
name is real and the INDEXED surface was wrong. The profile parsed only
`ds_input__pft_test__ex1.nc` (104 variables), the sample deck, while the surface a Lusignan run
actually reads carries 121 and has `CNWL` among them. Registering the evolved surface in
`rag/milestones.json` resolved it, and the output-block pass then delivered the 73 edges it had
always predicted rather than 72.
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
    # Held at ZERO since 2026-09-11. It stood at one (`CNWL`) while the profile indexed only the
    # 104-variable sample surface; registering the 121-variable evolved surface resolved it. The
    # count is asserted rather than the names, so the next dangling reference fails on its own
    # instead of joining a tolerated crowd -- but read the diagnosis before editing the seed: a
    # name that resolves in the model and not in the graph is an INDEXED-SURFACE question first.
    assert not unresolved, (
        f"{len(unresolved)} output-block driver name(s) match no parameter in any parsed surface: "
        f"{unresolved}. Before calling this a seed typo, check whether the name exists in a "
        f"parameter surface this profile does not index -- `param_files_extra` in "
        f"rag/milestones.json is where a real-but-unindexed name is fixed. Never mint a node.")


def test_the_indexed_parameter_surfaces_cover_the_names_the_seed_uses():
    """The 2026-09-11 fix, pinned on the axis it actually failed on: WHICH SURFACES ARE INDEXED.

    `CNWL` and `CHL` were both missing from the graph for reasons that look alike from a query and
    are not alike at all. `CNWL` had no node because the profile parsed the 104-variable sample
    deck and the name lives only in the 121-variable surface a real run reads -- a registry gap,
    fixed in `rag/milestones.json`. `CHL` had a node and no outgoing edge because it was not a key
    in `parameters:`, so the builder's parameter pass never visited it -- a seed gap, fixed in
    `models/ecosim/curated_seed.yaml`.

    A test that only asserted "both edges exist" would pass again if either fix were reverted and
    the other widened to cover for it, so each is asserted at its own layer.
    """
    seed, nodes, edges = _load()
    milestones = json.loads((REPO / "rag/milestones.json").read_text())
    entry = milestones["milestones"]["ecosim-2dea74d9"]
    surfaces = [entry["param_file"], *entry.get("param_files_extra", [])]

    evolved = [s for s in surfaces if "evolved" in s]
    assert evolved, (
        "the profile no longer indexes an evolved parameter surface, so any name present only "
        f"there is unresolvable again. Indexed surfaces: {surfaces}")

    assert "parameter:CNWL" in nodes, (
        "CNWL is absent from the graph. It is a real parameter of the surface a Lusignan run "
        f"reads; if it vanished, the evolved surface stopped being parsed. Indexed: {surfaces}")

    assert ("parameter:CHL", "output:CAN_GPP_pft", "affects") in edges, (
        "CHL has no outgoing affects edge. The builder's parameter pass iterates the KEYS of "
        "`parameters:` in the seed, so a parameter described only inside a mechanism's list is "
        "visited by nothing and fails silently -- it is a node with no edge, not an error.")


def test_the_leaf_protein_min_carries_all_four_of_its_parameters():
    """The 2026-09-11 mis-wiring: a mechanism whose own citation refuted its parameter list.

    `Leaf_Protein_Colimitation` cited `PlantBranchMod.F90:3548`,

        LeafProteinC_node += AMIN1(GrowthElms(ielmn)*rProteinC2LeafN_pft,
                                   GrowthElms(ielmp)*rProteinC2LeafP_pft)

    and listed `parameters: [CNLF, CPLF]` -- neither of which is in that line. `rProteinC2LeafN_pft`
    is CNWL (`PlantInfoMod.F90:619`) and `rProteinC2LeafP_pft` is CPWL (`:620`); CNLF is
    `rNCLeaf_pft` (`:623`), a different variable. CNLF and CPLF are not wrong to be there -- they
    set the nutrient SUPPLY that each branch multiplies -- but CNWL and CPWL, the coefficients, were
    absent from the seed's `parameters:` block entirely and so reached no pass.

    The visible consequence was that `CNWL`, rank 1 for GPP in EcoSIM_Lusignan R1b, carried one
    outgoing edge in the whole graph and it went to `ECO_ET_col`. It now reaches `CAN_GPP_pft`
    through the chain the mechanism describes.

    All four are asserted, and the GPP edge separately, so that restoring any single half of the
    fix still fails.
    """
    seed, nodes, edges = _load()
    mech = seed["mechanisms"]["Leaf_Protein_Colimitation"]
    for pname in ("CNWL", "CPWL", "CNLF", "CPLF"):
        assert pname in mech["parameters"], (
            f"{pname} is not on Leaf_Protein_Colimitation. The min() at PlantBranchMod.F90:3548 is "
            f"a nutrient SUPPLY (CNLF/CPLF) times a protein-per-nutrient COEFFICIENT (CNWL/CPWL) on "
            f"each branch; all four meet in it.")
        assert (f"parameter:{pname}", "mechanism:Leaf_Protein_Colimitation", "controls") in edges, (
            f"{pname} is listed on the mechanism but has no controls edge -- rebuild the graph.")

    assert ("parameter:CNWL", "output:CAN_GPP_pft", "affects") in edges, (
        "CNWL no longer reaches CAN_GPP_pft. It is the coefficient on the nitrogen branch of the "
        "leaf-protein min(), and leaf protein sets Rubisco surface density hence Vmax "
        "(StomatesMod.F90:414, 433, 435) -- which is why it ranks first for GPP.")
