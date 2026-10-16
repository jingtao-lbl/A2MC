"""The EcoSIM graph must carry branch guards, and must not lose live physics to the dead-variable filter.

Author: Jing Tao with Claude on Perlmutter

WHY. A `CHL` analysis cited `StomatesMod.F90:556` (`C4Photosynthesis`) while every record at the
site is `ICTYP = 3`, so the live line is `:415` (`C3Photosynthesis`), which carries no `fCHLMESO`
term. Nothing in the graph could have said so: all 192 `Parameter` nodes had `code_location: null`
and no node or edge encoded a condition. These tests pin the two halves of the fix, and the second
is the one that guards against MY OWN first attempt at the first.

`wire-knowledge-graph` Step 4: assert the IMPLICATION, not a count, so the assertions survive the
seed growing.
"""
from __future__ import annotations
import json
import re
import pathlib
import pytest
import yaml

REPO = pathlib.Path(__file__).resolve().parents[1]
SEED = REPO / "models/ecosim/curated_seed.yaml"

def _active_ecosim_profile() -> str:
    """The single non-legacy EcoSIM milestone: the graph these assertions are about is the one the
    builder produces now, not a pinned name (ecosim-2dea74d9 became legacy on 2026-10-15)."""
    m = json.loads((REPO / "rag/milestones.json").read_text())["milestones"]
    live = [k for k, v in m.items() if v.get("adapter") == "ecosim" and not v.get("legacy")]
    assert len(live) == 1, live
    return live[0]

PROFILE = _active_ecosim_profile()
GRAPH = REPO / "rag/graphs" / f"{PROFILE}.json"


@pytest.fixture(scope="module")
def nodes():
    g = json.loads(GRAPH.read_text())
    return {n["name"]: n for n in g["nodes"] if n.get("node_type") == "Parameter"}


@pytest.fixture(scope="module")
def seed_params():
    return yaml.safe_load(SEED.read_text())["parameters"]


def test_every_guarded_seed_parameter_reaches_the_graph(nodes, seed_params):
    """The implication: a seed `guard` that no builder pass reads is inert and silent."""
    guarded = {k: v for k, v in seed_params.items() if v.get("guard")}
    assert guarded, "the seed declares no guards -- the fix has been reverted"
    for name, spec in guarded.items():
        assert name in nodes, f"{name} is guarded in the seed but absent from the graph"
        assert nodes[name].get("guard") == spec["guard"], (
            f"{name}'s guard did not reach the node verbatim")


def test_guard_names_the_selecting_flag_and_both_pathways(nodes, seed_params):
    """A guard that does not say WHICH VALUE selects WHICH ROUTINE cannot resolve a citation."""
    for name, spec in seed_params.items():
        g = spec.get("guard")
        if not g:
            continue
        assert g.get("flag"), f"{name}: guard has no selecting flag"
        assert len(g.get("selects") or {}) >= 2, (
            f"{name}: a guard with fewer than two branches is not a guard")
        assert g.get("dispatch"), f"{name}: guard does not cite the dispatch site"


def test_chl_guard_points_at_the_c3_line_not_the_c4_line(nodes):
    """The specific error, pinned by ROUTINE rather than by line number. ICTYP=3 selects the line in
    `C3Photosynthesis`, NOT the one in `C4Photosynthesis` (`:415` against `:556` at 2dea74d9, `:423`
    against `:564` at cb243228). Line numbers move with every commit the profile is re-pinned to,
    and `tools/check_ecosim_seed_citations.py` already holds each one to the source; what this test
    owns is that the FIRST citation, the one a reader acts on, is the C3 one."""
    chl = nodes["CHL"]
    first = chl["code_location"].split(";")[0]
    assert "C3Photosynthesis" in first, f"CHL's first citation is not the C3 line: {first!r}"
    line = re.search(r":(\d+)", first).group(1)
    selects = chl["guard"]["selects"]
    assert "C3Photosynthesis" in selects["3"] and f":{line}" in selects["3"], (
        "the C3 branch must name the same line code_location leads with")
    assert "C4Photosynthesis" in selects["4"], "the C4 branch must name C4Photosynthesis"
    c4_lines = set(re.findall(r":(\d+)", selects["4"]))
    assert line not in c4_lines, "code_location leads with a C4 line -- this is the original defect"


def test_dead_file_variable_is_not_a_node(nodes):
    """`CHL4` is in the shipped sample pft file and in ZERO .F90 files.

    It is ecosys's parameterization: the F77 ancestor split C3/C4 chlorophyll across CHL and CHL4,
    while EcoSIM's F90 uses one CHL partitioned by fCHLMESO. A dead knob carrying the FILE's own
    long_name as its description is worse than no node, because it answers queries.
    """
    assert "CHL4" not in nodes


@pytest.mark.parametrize("name", ["H2KI", "OAKI"])
def test_live_but_not_file_backed_parameters_survive(nodes, name):
    """NEGATIVE CONTROL for the dead-variable filter, and it caught a real regression.

    The first cut of `_source_status()` returned only the `ncd_getvar` set and dropped everything
    else, which would have deleted H2KI and OAKI. They are LIVE -- compiled-in constants set in
    `initNitroPars` (NitroPars.F90:144-145) and used in the Gibbs free-energy terms
    (MicBGCFGMod.F90:2597, MicAutoCplxFGMod.F90:1677). Deleting live physics to tidy one dead
    variable would have been a far worse bug than the one being fixed.

    They keep a node AND carry `file_backed: False`, because the second fact matters on its own: the
    value in `MicrobePars.nc` is never read back, so a calibration slot pointing at either is a
    SILENT NO-OP.
    """
    assert name in nodes, f"{name} is live physics and must not be dropped as a dead variable"
    assert nodes[name].get("file_backed") is False
    assert "no-op" in nodes[name].get("file_backed_note", "").lower()


def test_file_backed_flag_is_not_applied_to_ordinary_parameters(nodes):
    """A flag that ends up on everything says nothing. CHL is read from the file; it must be unflagged.

    `RSRA` joined the set with the cb243228 profile (2026-10-15): its only `ncd_getvar` is in
    `ReadPlantTraitsNC`, which nothing calls, so no run reads it; the variable it names is computed
    from ARSRA in STARTQ. A name-literal grep counted that dead read as file-backed until the
    builder learned to ask whether the reading routine is ever called.

    `NCNG` joined with the grid surface (2026-10-15): the grid file carries it, but the model takes
    the lateral-connection mode from the `grid_mode` namelist key and `NCNG` survives in source only
    as a dummy-argument name (`readimod.F90:130`, `GridConectionMode`). The grid extents NHW, NHE,
    NVN and NVS must NOT be in the set: `SetMesh` reads them with `check_var` + `nf90_get_var`
    rather than `ncd_getvar`, and the first grid build called them inert until the scanner learned
    that pattern."""
    assert "file_backed" not in nodes["CHL"]
    assert "file_backed" not in nodes["ARSRA"], "ARSRA is read by the LIVE table reader"
    for name in ("NHW", "NHE", "NVN", "NVS"):
        assert "file_backed" not in nodes[name], f"{name} is read in SetMesh (GridMod.F90)"
    assert nodes["fAeroDOM"].get("read_if_present") is True, (
        "the bioaerosol fractions are read through read_aerosol_vars, if present")
    flagged = [n for n, v in nodes.items() if v.get("file_backed") is False]
    assert set(flagged) == {"H2KI", "OAKI", "RSRA", "NCNG"}, f"unexpected inert set: {sorted(flagged)}"
