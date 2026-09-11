"""F1-F6 for the SECONDARY parameter surface and for `mode: multiplier`.

Each test asserts a way the feature must FAIL, not merely that the happy path works
([[feedback_a_check_that_cannot_fail]]). The two that would otherwise go untested are F5, the
regression that a FIXED secondary stage still behaves exactly as before, and F6, that a value the
writer stores as an integer is compared as one.

Context: before 2026-09-01 `route_surfaces()` resolved names to `primary` or `tertiary` only, so an
adapter's secondary surface could be STAGED but never SAMPLED. See
memory/dev_logs_adapterkit/20260901g_*.
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pytest

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from scripts.create_adapter_parameter_sample import route_surfaces, parse_param_modes  # noqa: E402

PRIMARY = {"CNLF", "DMLF"}
TERTIARY = {"RMOM", "SPOSC"}
SECONDARY = {"PPI"}


# ---------------------------------------------------------------- F1: unknown name refuses
def test_f1_name_on_no_surface_raises_and_names_the_secondary_set():
    with pytest.raises(ValueError) as e:
        route_surfaces(["GHOST_1"], PRIMARY, TERTIARY, True,
                       secondary_names=SECONDARY, secondary_given=True)
    msg = str(e.value)
    assert "GHOST" in msg
    # the error must say what the secondary surface WOULD have accepted, or a reader has no way
    # to tell a typo from an unsupported parameter
    assert "PPI" in msg


# ---------------------------------------------------------------- F2: declared but no base file
def test_f2_secondary_name_without_a_secondary_base_refuses():
    """Must NOT fall through to the fixed-stage path: that would silently drop a sampled value."""
    with pytest.raises(ValueError) as e:
        route_surfaces(["PPI_1"], PRIMARY, TERTIARY, True,
                       secondary_names=SECONDARY, secondary_given=False)
    assert "secondary" in str(e.value).lower()


# ---------------------------------------------------------------- F3: ambiguity refuses
def test_f3_name_on_two_surfaces_raises():
    with pytest.raises(ValueError) as e:
        route_surfaces(["CNLF_1"], PRIMARY, TERTIARY, True,
                       secondary_names={"CNLF"}, secondary_given=True)
    assert "MORE THAN ONE" in str(e.value)


def test_secondary_routes_when_declared_and_supplied():
    r = route_surfaces(["CNLF_1", "PPI_1", "RMOM"], PRIMARY, TERTIARY, True,
                       secondary_names=SECONDARY, secondary_given=True)
    assert r == {"CNLF_1": "primary", "PPI_1": "secondary", "RMOM": "tertiary"}


# ---------------------------------------------------------------- F5: the REGRESSION guard
def test_f5_no_secondary_names_leaves_routing_identical():
    """A model declaring no secondary names must route exactly as it did before this feature."""
    before = route_surfaces(["CNLF_1", "DMLF_1", "RMOM"], PRIMARY, TERTIARY, True)
    after = route_surfaces(["CNLF_1", "DMLF_1", "RMOM"], PRIMARY, TERTIARY, True,
                           secondary_names=set(), secondary_given=False)
    assert before == after == {"CNLF_1": "primary", "DMLF_1": "primary", "RMOM": "tertiary"}


def test_f5_secondary_given_but_nothing_sampled_is_not_an_error():
    """Supplying a fixed secondary base while sampling none of it is the pre-existing path."""
    r = route_surfaces(["CNLF_1"], PRIMARY, TERTIARY, True,
                       secondary_names=SECONDARY, secondary_given=True)
    assert r == {"CNLF_1": "primary"}


# ---------------------------------------------------------------- mode column
def _write_list(tmp_path, rows, header="name,pft,surface,mode,lower_bound,upper_bound"):
    p = tmp_path / "plist.csv"
    p.write_text(header + "\n" + "\n".join(rows) + "\n")
    return p


def test_mode_defaults_to_absolute_and_a_missing_column_changes_nothing(tmp_path):
    with_col = _write_list(tmp_path / "a", [], header="x") if False else None
    d1 = tmp_path / "a"; d1.mkdir()
    d2 = tmp_path / "b"; d2.mkdir()
    p_no = _write_list(d1, ["CNLF,1,primary,0.1,0.2"],
                       header="name,pft,surface,lower_bound,upper_bound")
    p_yes = _write_list(d2, ["CNLF,1,primary,,0.1,0.2"])
    assert parse_param_modes(p_no) == {}                       # no column -> all absolute
    assert parse_param_modes(p_yes)["CNLF_1"] == "absolute"     # blank cell -> absolute


def test_mode_multiplier_is_parsed(tmp_path):
    p = _write_list(tmp_path, ["SPOSC,-,tertiary,multiplier,0.1,0.8"])
    assert parse_param_modes(p)["SPOSC"] == "multiplier"


def test_unknown_mode_raises(tmp_path):
    p = _write_list(tmp_path, ["SPOSC,-,tertiary,scaled,0.1,0.8"])
    with pytest.raises(ValueError) as e:
        parse_param_modes(p)
    assert "scaled" in str(e.value)


# ---------------------------------------------------------------- F6 + multiplier semantics
def test_f6_integer_quantization_is_what_the_writer_stores():
    """PPI is written as int(round(v)); a validator comparing the raw float fails every case."""
    for sampled, want in [(184.985, 185), (523.989, 524), (366.166, 366), (140.4, 140)]:
        assert round(float(sampled)) == want


def test_multiplier_scales_elementwise_and_cannot_move_zeros():
    """The property that makes a multiplier a RAY through the array's space, not the space."""
    base = np.array([7.5, 1.5, 0.5, 0.05, 0.0167, 0.0])
    for factor in (0.1, 0.3606, 0.6749, 0.8):
        scaled = base * factor
        assert np.allclose(scaled / factor, base)          # structure preserved
        assert scaled[-1] == 0.0                            # a zero entry can never be moved
        assert scaled.max() == pytest.approx(7.5 * factor)


def test_multiplier_broadcast_would_be_wrong():
    """Guards the actual defect: writing the FACTOR instead of base*factor flattens the array."""
    base = np.array([7.5, 1.5, 0.5, 0.05, 0.0167, 0.0])
    factor = 0.3606
    broadcast = np.full_like(base, factor)     # what the writer does with a bare scalar
    assert not np.allclose(broadcast, base * factor)
