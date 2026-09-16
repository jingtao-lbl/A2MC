"""The QUATERNARY surface: EcoSIM's site/soil-profile grid file (`grid_file_in`).

The defect this closes is an absence rather than a bug: A2MC declared three parameter surfaces and
the soil lived in a fourth it could not touch. R1b cycle 15 moved ground albedo anyway, by
hand-editing a per-case copy, and that hand-built file is the ground truth several tests below
check against.

THE AXIS IS THE TRAP. The layered variables are dimensioned (ntopou, nlevs), so axis 0 is the
topographic unit and the soil LAYER is axis 1. The primary writer indexes axis 0. Reusing it would
have edited the wrong dimension and reported success, so the tests that pin the axis are the
load-bearing ones ([[feedback_pft_column_is_an_axis_alias]]).
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
for p in (str(REPO), str(REPO / "scripts")):
    if p not in sys.path:
        sys.path.insert(0, p)

nc = pytest.importorskip("netCDF4")
import numpy as np                                             # noqa: E402
from models.ecosim.backend import EcoSIMBackend                # noqa: E402
from models.ecosim.spec import ECOSIM_SPEC                     # noqa: E402

BUNDLE = REPO / "use_cases/EcoSIM_Lusignan/reports/20260909b_R1b_FINAL_CONFIGURATION"
GRID = BUNDLE / "inputs/case/grid-input.nc"
RANK6 = BUNDLE / "calibrated_parameterizations/rank06_c15_2.grid.nc"
pytestmark = pytest.mark.skipif(not GRID.is_file(), reason="R1b bundle not in this checkout")


@pytest.fixture
def be():
    return EcoSIMBackend()


# --------------------------------------------------------------------------- the declaration
def test_the_spec_declares_a_fourth_surface_and_names_its_axis():
    assert ECOSIM_SPEC.quaternary_namelist_var == "grid_file_in"
    assert ECOSIM_SPEC.quaternary_axis == "soil_layer", \
        "the axis must be NAMED; an unnamed axis alias is how a layer gets read as a PFT"


def test_the_four_surfaces_are_distinct():
    slots = [ECOSIM_SPEC.secondary_namelist_var, ECOSIM_SPEC.tertiary_namelist_var,
             ECOSIM_SPEC.quaternary_namelist_var]
    assert len(set(slots)) == len(slots) and all(slots)


# ------------------------------------------------------- ground truth: the hand-built variant
def test_the_slot_REPRODUCES_the_hand_built_cycle15_variant(be, tmp_path):
    """THE test. Cycle 15 changed ALBS 0.15 -> 0.05 by hand because no slot existed. Going
    through the slot must produce that exact file, or the slot is not what the round did."""
    if not RANK6.is_file():
        pytest.skip("rank06 grid variant not in this checkout")
    out = tmp_path / "g.nc"
    be.write_parameter_file(GRID, {"ALBS": 0.05}, out, surface="quaternary")
    got, want = nc.Dataset(out), nc.Dataset(RANK6)
    differing = [k for k in want.variables
                 if not np.array_equal(np.asarray(got[k][:]), np.asarray(want[k][:]))]
    assert differing == [], f"differs from the hand-built file in {differing}"


# --------------------------------------------------------------------------- the layer axis
def test_a_layer_edit_writes_the_LAYER_axis_not_the_topo_axis(be, tmp_path):
    out = tmp_path / "g.nc"
    be.write_parameter_file(GRID, {"PH_5": 7.7}, out, surface="quaternary")
    before, after = nc.Dataset(GRID)["PH"][:], nc.Dataset(out)["PH"][:]
    assert float(after[0, 4]) == pytest.approx(7.7), "layer 5 (axis 1, 0-based 4) was not written"
    assert np.array_equal(np.delete(before, 4, axis=1), np.delete(after, 4, axis=1)), \
        "a layer edit disturbed other layers"


def test_the_axis_is_ONE_BASED_like_every_other_surface(be, tmp_path):
    out = tmp_path / "g.nc"
    be.write_parameter_file(GRID, {"PH_1": 4.4}, out, surface="quaternary")
    assert float(nc.Dataset(out)["PH"][0, 0]) == pytest.approx(4.4)


def test_a_layer_beyond_the_profile_is_REFUSED(be, tmp_path):
    with pytest.raises(IndexError):
        be.write_parameter_file(GRID, {"PH_99": 7.0}, tmp_path / "g.nc", surface="quaternary")


def test_an_axis_suffix_on_a_variable_with_NO_layer_axis_is_REFUSED(be, tmp_path):
    """ALBS is (ntopou,). Accepting `ALBS_3` would write the topographic-unit dimension while the
    parameter list said layer 3 -- a value edited that the list never named."""
    with pytest.raises(ValueError, match="no soil-layer axis"):
        be.write_parameter_file(GRID, {"ALBS_3": 0.1}, tmp_path / "g.nc", surface="quaternary")


def test_a_bare_name_broadcasts_to_every_layer(be, tmp_path):
    out = tmp_path / "g.nc"
    be.write_parameter_file(GRID, {"PH": 6.0}, out, surface="quaternary")
    assert np.allclose(np.asarray(nc.Dataset(out)["PH"][:]), 6.0)


def test_an_unknown_variable_is_REFUSED_not_silently_dropped(be, tmp_path):
    with pytest.raises(KeyError):
        be.write_parameter_file(GRID, {"NOTAVAR": 1.0}, tmp_path / "g.nc", surface="quaternary")


def test_untouched_variables_are_bit_identical(be, tmp_path):
    """113 of 114 must survive an edit unchanged; a writer that rewrites the file wholesale can
    silently change precision or fill values."""
    out = tmp_path / "g.nc"
    be.write_parameter_file(GRID, {"PH_5": 7.7}, out, surface="quaternary")
    a, b = nc.Dataset(GRID), nc.Dataset(out)
    changed = [k for k in a.variables
               if not np.array_equal(np.asarray(a[k][:]), np.asarray(b[k][:]))]
    assert changed == ["PH"], f"expected only PH to change, got {changed}"


# --------------------------------------------------------------------------- surface routing
def test_a_grid_variable_routes_to_the_quaternary_surface():
    from create_adapter_parameter_sample import route_surfaces
    r = route_surfaces(["VCMX", "PH_5", "ALBS"], {"VCMX"}, set(), False,
                       quaternary_vars={"PH", "ALBS"}, quaternary_given=True)
    assert r == {"VCMX": "primary", "PH_5": "quaternary", "ALBS": "quaternary"}


def test_a_grid_variable_with_NO_base_file_is_REFUSED(route=None):
    """Routing it to 'primary' would edit the wrong file; dropping it would stage the surface
    unchanged and silently discard a sampled value."""
    from create_adapter_parameter_sample import route_surfaces
    with pytest.raises(ValueError):
        route_surfaces(["PH_5"], {"VCMX"}, set(), False)


def test_a_name_in_TWO_surfaces_is_REFUSED():
    from create_adapter_parameter_sample import route_surfaces
    with pytest.raises(ValueError, match="MORE THAN ONE"):
        route_surfaces(["PH"], {"PH"}, set(), False,
                       quaternary_vars={"PH"}, quaternary_given=True)


# --------------------------------------------------------------------------- case staging
def test_create_case_stages_the_grid_file_and_repoints_the_namelist(be, tmp_path):
    nml = tmp_path / "base.nml"
    nml.write_text("&run\n  pft_file_in = '/x/p.nc'\n  grid_file_in = '/x/grid-input.nc'\n/\n")
    case = be.create_case(
        "c0", GRID.parent / "grass_clova_pftpar.nc",
        {"A2MC_OUTPUT_DIR": str(tmp_path / "runs"),
         "A2MC_ECOSIM_BASE_NAMELIST": str(nml),
         "A2MC_ECOSIM_BINARY": "/bin/true"},
        quaternary_param_file=GRID,
    )
    staged = Path(case) / GRID.name
    assert staged.is_file(), "the grid file was not staged into the case"
    text = (Path(case) / "runfile.nml").read_text()
    assert str(staged) in text, "grid_file_in was not repointed at the staged copy"


def test_a_namelist_with_no_grid_line_RAISES_rather_than_staging_a_file_nothing_reads(be, tmp_path):
    nml = tmp_path / "base.nml"
    nml.write_text("&run\n  pft_file_in = '/x/p.nc'\n/\n")
    with pytest.raises(KeyError, match="grid_file_in"):
        be.create_case(
            "c1", GRID.parent / "grass_clova_pftpar.nc",
            {"A2MC_OUTPUT_DIR": str(tmp_path / "runs"),
             "A2MC_ECOSIM_BASE_NAMELIST": str(nml),
             "A2MC_ECOSIM_BINARY": "/bin/true"},
            quaternary_param_file=GRID,
        )


# --------------------------------------------------------------------- the other surfaces
def test_the_other_surfaces_still_reject_an_unknown_name(be, tmp_path):
    with pytest.raises(ValueError, match="quaternary"):
        be.write_parameter_file(GRID, {}, tmp_path / "g.nc", surface="quinary")


# ====================================================================================
# The secondary surface answers to TWO env names, and only one used to work here
# ====================================================================================

def _load(script):
    """Every one of these scripts now IMPORTS the rule, so resolve through the module each of
    them imports rather than through the script -- which is the property under test."""
    import importlib.util
    spec = importlib.util.spec_from_file_location(
        "caps_shared", REPO / "scripts/create_adapter_parameter_sample.py")
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    assert "secondary_base_default" in (REPO / script).read_text(), \
        f"{script} does not reference the shared resolver"
    m._secondary_default = m.secondary_base_default
    return m


SECONDARY_SCRIPTS = ["scripts/materialize_adapter_ensemble.py",
                     "scripts/validate_adapter_ensemble.py",
                     "scripts/materialize_adapter_crossed.py"]


def test_ONE_definition_of_the_resolution_rule_not_one_per_script():
    """Three copies of the fix would be the original defect with better intentions. Every script
    must import the rule, not restate it."""
    canon = (REPO / "scripts/create_adapter_parameter_sample.py").read_text()
    assert "def secondary_base_default(" in canon
    for script in SECONDARY_SCRIPTS:
        body = (REPO / script).read_text()
        assert "def secondary_base_default(" not in body, f"{script} defines its own copy"
        assert "secondary_base_default" in body, f"{script} does not use the shared rule"


@pytest.mark.parametrize("script", SECONDARY_SCRIPTS)
def test_the_LEGACY_secondary_name_resolves(script, monkeypatch):
    """EcoSIM_BioCON's R2 config sets A2MC_BASE_PARAM_FILE_2; R3 and TeRaCON set the current
    name. Before this, a config written for the crossed path ran through these scripts with its
    secondary surface staged UNCHANGED -- sampled values written nowhere, no warning."""
    monkeypatch.delenv("A2MC_SECONDARY_PARAM_FILE", raising=False)
    monkeypatch.setenv("A2MC_BASE_PARAM_FILE_2", "/legacy.nc")
    assert _load(script).secondary_base_default() == ("/legacy.nc", "A2MC_BASE_PARAM_FILE_2")


@pytest.mark.parametrize("script", SECONDARY_SCRIPTS)
def test_the_CURRENT_name_wins_when_both_are_set(script, monkeypatch):
    """A fallback that outranked the current name would make the legacy one authoritative,
    which is the opposite of retiring it."""
    monkeypatch.setenv("A2MC_SECONDARY_PARAM_FILE", "/cur.nc")
    monkeypatch.setenv("A2MC_BASE_PARAM_FILE_2", "/legacy.nc")
    assert _load(script).secondary_base_default() == ("/cur.nc", "A2MC_SECONDARY_PARAM_FILE")


@pytest.mark.parametrize("script", SECONDARY_SCRIPTS)
def test_neither_set_stays_None_rather_than_inventing_a_path(script, monkeypatch):
    for k in ("A2MC_SECONDARY_PARAM_FILE", "A2MC_BASE_PARAM_FILE_2"):
        monkeypatch.delenv(k, raising=False)
    assert _load(script).secondary_base_default() == (None, None)


# ====================================================================================
# The shipped R1b deliverable must be unaffected
# ====================================================================================

def test_the_LUSIGNAN_config_leaves_the_quaternary_slot_OFF():
    """R1b ran with the grid file as a shared, unperturbed site input. If this config ever
    exports the slot, every reproduction of R1b starts staging a per-case grid file and the
    delivered results stop being what the config produces."""
    cfg = (REPO / "use_cases/EcoSIM_Lusignan/config/ecosim_lusignan_config.sh").read_text()
    live = [l for l in cfg.split("\n")
            if l.strip().startswith("export A2MC_BASE_PARAM_FILE_4")]
    assert live == [], f"the quaternary slot is live in the Lusignan config: {live}"


def test_the_LUSIGNAN_config_uses_no_secondary_surface():
    """So the legacy-name fallback cannot change anything about this case either."""
    cfg = (REPO / "use_cases/EcoSIM_Lusignan/config/ecosim_lusignan_config.sh").read_text()
    live = [l for l in cfg.split("\n") if l.strip().startswith(
        ("export A2MC_SECONDARY_PARAM_FILE", "export A2MC_BASE_PARAM_FILE_2"))]
    assert live == []
