"""PFLOTRAN write_parameter_file: the 16-knob calibration deck writer.

Line-surgical: parses the base deck to find each modified card's exact line
and original token, then replaces only that token, leaving every untouched
card byte-identical. Covers the two footguns the param list itself calls
out — the M/LIQUID_RESIDUAL_SATURATION "all3" triple-address write, and
PERM_ISO's log10-in-the-param-list-but-linear-in-the-deck convention — plus
the address-resolution error paths (unknown leaf, unknown sub-address,
unsupported surface).

Gated on a real miniLEO deck (A2MC_PFLOTRAN_DECK), same pattern as
tests/test_pflotran_e2e.py, since the deck lives on CFS and is not committed.

Run:  ~/a2mc_env/bin/python -m pytest tests/test_pflotran_write_parameter_file.py -v

Author: Jing Tao with Claude
"""
from __future__ import annotations

import math
import os
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
_DECK = Path(os.environ.get("A2MC_PFLOTRAN_DECK", "")) if os.environ.get("A2MC_PFLOTRAN_DECK") else None
_needs_deck = pytest.mark.skipif(
    not (_DECK and _DECK.is_file()),
    reason="miniLEO deck not staged (set A2MC_PFLOTRAN_DECK)")

DEFAULTS = {
    "RATE_CONSTANT_Glass_FB": -12.6349,
    "RATE_CONSTANT_Proto-Imogolite": -10.0557,
    "RATE_CONSTANT_Ferrihydrite": -5.8636,
    "RATE_CONSTANT_Montmor-Mg": -4.4353,
    "RATE_CONSTANT_Hydroxylapatite": -11.8358,
    "RATE_CONSTANT_Calcite": -11.8979,
    "surface_area_Glass_FB": 32000,
    "surface_area_Ferrihydrite": 2.0e8,
    "surface_area_Proto-Imogolite": 9.0e6,
    "M_all3": 0.4505494,
    "ALPHA_sf": 0.000267,
    "LIQUID_RESIDUAL_SATURATION_all3": 0.02,
    "PERM_ISO_Bolitic": -10.9252,          # log10; deck wants linear
    "PERMEABILITY_POWER_Bolitic": 3.0,
    "PERMEABILITY_CRITICAL_POROSITY_Bolitic": 0.09,
    "LONGITUDINAL_DISPERSIVITY_Bolitic": 0.0458,
    "LIQUID_SATURATION_initial": 0.10,
}


def _backend():
    from models.pflotran.backend import PFLOTRANBackend
    return PFLOTRANBackend()


def _parser():
    from models.pflotran.parameter_parser import PFLOTRANParameterParser
    return PFLOTRANParameterParser()


@_needs_deck
def test_default_values_round_trip(tmp_path):
    """Writing the param list's OWN defaults must reproduce identical values
    and must not disturb the deck's parameter COUNT or introduce parse errors."""
    out = tmp_path / "roundtrip.in"
    _backend().write_parameter_file(_DECK, DEFAULTS, out)

    orig = _parser().parse(_DECK)
    p2 = _parser()
    reparsed = p2.parse(out)
    assert p2.errors == []
    assert len(reparsed) == len(orig) == 121

    checks = {
        "CHEMISTRY/MINERAL_KINETICS/Glass_FB/RATE_CONSTANT": -12.6349,
        "CONSTRAINT[initial]/MINERALS/Glass_FB#surface_area": 32000.0,
        "MATERIAL_PROPERTY[Bolitic]/PERMEABILITY/PERM_ISO": 10 ** -10.9252,
        "CHARACTERISTIC_CURVES[sf1]/SATURATION_FUNCTION[VAN_GENUCHTEN]/M": 0.4505494,
        "CHARACTERISTIC_CURVES[sf1]/PERMEABILITY_FUNCTION[MUALEM_VG_LIQ]/M": 0.4505494,
        "CHARACTERISTIC_CURVES[sf1]/PERMEABILITY_FUNCTION[MUALEM_VG_GAS]/M": 0.4505494,
        "FLOW_CONDITION[initial]/LIQUID_SATURATION": 0.1,
    }
    for addr, expect in checks.items():
        assert math.isclose(reparsed[addr].value, expect, rel_tol=1e-6), addr


@_needs_deck
def test_perturbation_hits_all3_addresses_and_exponentiates_perm_iso(tmp_path):
    """A real (non-default) sample must land on ALL THREE M/LIQUID_RESIDUAL_SATURATION
    addresses together, and PERM_ISO's log10 param-list value must be exponentiated
    before it reaches the deck (the deck reads it linearly, unlike RATE_CONSTANT)."""
    out = tmp_path / "perturbed.in"
    perturbed = {
        "RATE_CONSTANT_Glass_FB": -13.6349,
        "surface_area_Glass_FB": 64000,
        "M_all3": 0.30,
        "LIQUID_RESIDUAL_SATURATION_all3": 0.10,
        "PERM_ISO_Bolitic": -11.5,
        "LIQUID_SATURATION_initial": 0.40,
    }
    _backend().write_parameter_file(_DECK, perturbed, out)

    p = _parser()
    reparsed = p.parse(out)
    assert p.errors == []
    assert len(reparsed) == 121

    for addr in (
        "CHARACTERISTIC_CURVES[sf1]/SATURATION_FUNCTION[VAN_GENUCHTEN]/M",
        "CHARACTERISTIC_CURVES[sf1]/PERMEABILITY_FUNCTION[MUALEM_VG_LIQ]/M",
        "CHARACTERISTIC_CURVES[sf1]/PERMEABILITY_FUNCTION[MUALEM_VG_GAS]/M",
    ):
        assert math.isclose(reparsed[addr].value, 0.30, rel_tol=1e-6), addr
    for addr in (
        "CHARACTERISTIC_CURVES[sf1]/SATURATION_FUNCTION[VAN_GENUCHTEN]/LIQUID_RESIDUAL_SATURATION",
        "CHARACTERISTIC_CURVES[sf1]/PERMEABILITY_FUNCTION[MUALEM_VG_LIQ]/LIQUID_RESIDUAL_SATURATION",
        "CHARACTERISTIC_CURVES[sf1]/PERMEABILITY_FUNCTION[MUALEM_VG_GAS]/LIQUID_RESIDUAL_SATURATION",
    ):
        assert math.isclose(reparsed[addr].value, 0.10, rel_tol=1e-6), addr

    perm_iso = reparsed["MATERIAL_PROPERTY[Bolitic]/PERMEABILITY/PERM_ISO"].value
    assert math.isclose(perm_iso, 10 ** -11.5, rel_tol=1e-6), (
        "PERM_ISO must be EXPONENTIATED: the param list samples log10(k), the deck "
        "reads k linearly")

    # untouched knobs must be exactly unchanged
    assert reparsed["CHEMISTRY/MINERAL_KINETICS/Labradorite/RATE_CONSTANT"].value == -15.8535
    assert reparsed["CHEMISTRY/MINERAL_KINETICS/Calcite/RATE_CONSTANT"].value == -11.8979
    assert reparsed["MATERIAL_PROPERTY[Bolitic]/PERMEABILITY_POWER"].value == 3.0


@_needs_deck
def test_only_intended_lines_change(tmp_path):
    """Every line the resolver does not address must be byte-identical to the source
    deck -- the point of a line-surgical writer over a full re-serialization."""
    out = tmp_path / "touch_check.in"
    _backend().write_parameter_file(_DECK, DEFAULTS, out)

    orig_lines = _DECK.read_text().splitlines()
    new_lines = out.read_text().splitlines()
    assert len(orig_lines) == len(new_lines)

    # lines the 16-param DEFAULTS set is allowed to touch (some no-op because the
    # formatted default matches the deck's own token exactly; others reformat
    # a value-identical token, e.g. "3.d0" -> "3")
    allowed = {237, 267, 275, 298, 305, 291, 435, 441, 438,
               568, 573, 580, 569, 570, 574, 578, 552, 557, 556, 554, 498}
    changed = {i + 1 for i, (a, b) in enumerate(zip(orig_lines, new_lines)) if a != b}
    assert changed <= allowed, f"unexpected changed lines: {changed - allowed}"


@_needs_deck
def test_unknown_leaf_name_raises(tmp_path):
    with pytest.raises(KeyError, match="does not start with a known"):
        _backend().write_parameter_file(
            _DECK, {"NOT_A_REAL_NAME_Glass_FB": 1.0}, tmp_path / "out.in")


@_needs_deck
def test_unknown_sub_address_raises(tmp_path):
    with pytest.raises(KeyError, match="resolved to no address"):
        _backend().write_parameter_file(
            _DECK, {"RATE_CONSTANT_NotAMineral": -12.0}, tmp_path / "out.in")


@_needs_deck
def test_database_surface_not_implemented(tmp_path):
    with pytest.raises(NotImplementedError, match="surface='database'"):
        _backend().write_parameter_file(_DECK, {}, tmp_path / "out.in", surface="database")


def test_split_canonical_id_handles_underscored_mineral_names():
    """The RIGHTMOST-underscore split EcoSIM uses (_MOD_PFT_RE) would break here:
    several sub-addresses are themselves mineral names containing underscores."""
    from models.pflotran.backend import PFLOTRANBackend
    split = PFLOTRANBackend._split_canonical_id
    assert split("RATE_CONSTANT_Glass_FB") == ("RATE_CONSTANT", "Glass_FB")
    assert split("surface_area_Proto-Imogolite") == ("surface_area", "Proto-Imogolite")
    assert split("M_all3") == ("M", "all3")
    assert split("PERMEABILITY_CRITICAL_POROSITY_Bolitic") == (
        "PERMEABILITY_CRITICAL_POROSITY", "Bolitic")
    with pytest.raises(KeyError):
        split("totally_unknown_thing")
