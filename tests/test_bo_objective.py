"""The normalized-violation objective `V` (docs/42 stage S0).

The property that matters is not that `V` computes a number. It is that `V` **cannot be gamed by
compensation** the way the existing composite can, and that a case with no result is treated as
ABSENT rather than as very bad. Both are asserted below against the real R3 ensemble, so a test
cannot pass by agreeing with a fixture built to agree with it.

Every test is written so that it FAILS if the behaviour it names is removed.
"""
import csv
import sys
from pathlib import Path

import numpy as np
import pytest

REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from tools.cost_functions import aggregate_costs  # noqa: E402
from tools.bayesian_optimization.objective import (  # noqa: E402
    Target,
    composite_rmsre,
    load_targets,
    violation,
    violation_matrix,
)

R3_Y = (REPO / "use_cases/EcoSIM_BioCON/memory/phase_results"
        / "20260820a_phase0_design_r03_r3_sobol_ensemble_designed_and_validated_held_at_the_submiss"
        / "R3_Y_matrix_full.csv")
BIOCON_TARGETS = REPO / "use_cases/EcoSIM_BioCON/validation/targets.yaml"

COLS = ["NPP", "plant_C", "Fs"]


def _targets():
    return [Target("NPP", 389.0, 0.36), Target("plant_C", 651.7, 0.35), Target("Fs", 6.2, 0.28)]


def _r3():
    if not R3_Y.is_file():
        pytest.skip("R3 Y matrix absent")
    rows = list(csv.DictReader(R3_Y.open()))
    cases = np.array([int(r["case"]) for r in rows])
    Y = np.array([[float(r[c]) if r[c] not in ("", "nan") else np.nan for c in COLS]
                  for r in rows])
    return cases, Y


# =============================================================================
# The band arithmetic
# =============================================================================

def test_v_equals_one_exactly_at_the_band_edge():
    """The whole objective hangs on `v_i <= 1 <=> in band`. Off-by-one here is silent."""
    t = Target("x", 100.0, 0.25)
    assert t.lo == 75.0 and t.hi == 125.0
    for edge in (t.lo, t.hi):
        V, v, _ = violation({"x": edge}, [t])
        assert v["x"] == pytest.approx(1.0)
    assert violation({"x": 100.0}, [t])[0] == pytest.approx(0.0)


def test_V_le_1_iff_EVERY_target_is_in_band():
    ts = _targets()
    inside = {"NPP": 389.0, "plant_C": 651.7, "Fs": 6.2}
    assert violation(inside, ts)[0] <= 1.0
    for name in COLS:
        one_out = dict(inside)
        one_out[name] = next(t for t in ts if t.name == name).hi * 1.0001
        V, _, binding = violation(one_out, ts)
        assert V > 1.0, f"{name} outside its band did not push V above 1"
        assert binding == name, "the binding target must NAME the one that is out"


def test_the_binding_target_is_the_ARGMAX_not_the_worst_relative_error():
    """`v_i` is normalized by that target's OWN uncertainty, so the binding target is not
    necessarily the one with the largest raw relative error. If it were, the per-target
    uncertainties would not be doing anything."""
    # NPP: 30% relative error against u=0.36 -> v = 0.833   (the LARGER relative error)
    # Fs:  25% relative error against u=0.28 -> v = 0.893   (binds anyway, tighter band)
    ts = _targets()
    sim = {"NPP": 389.0 * 1.30, "plant_C": 651.7, "Fs": 6.2 * 1.25}
    _, v, binding = violation(sim, ts)
    assert binding == "Fs"
    assert abs(sim["NPP"] - 389.0) / 389.0 > abs(sim["Fs"] - 6.2) / 6.2


# =============================================================================
# The load-bearing property, on REAL data
# =============================================================================

def test_the_composite_PREFERS_a_case_that_misses_a_band_by_74_percent():
    """THE reason this objective exists, measured on the R3 ensemble rather than argued.

    Case 7329 is R3's best case by the composite. Its plant_C sits 74% of a band-width OUTSIDE
    the band, paid for by NPP and Fs sitting comfortably inside. Case 2847 is worse on the
    composite and better on `V`, with all three targets within 16% of their bands.

    If `V` is ever changed to something mean-like, this test goes red -- which is the point.
    """
    cases, Y = _r3()
    ts = _targets()
    V, v, binding = violation_matrix(Y, COLS, ts)
    C = composite_rmsre(Y, COLS, ts)
    i7329 = int(np.where(cases == 7329)[0][0])
    i2847 = int(np.where(cases == 2847)[0][0])

    # the composite prefers 7329; V prefers 2847. Both directions asserted, so neither
    # can be satisfied by an objective that simply agrees with the composite.
    assert C[i7329] < C[i2847]
    assert V[i2847] < V[i7329]

    assert binding[i7329] == COLS.index("plant_C")
    assert v[i7329, COLS.index("plant_C")] > 1.7      # far outside
    assert v[i7329, COLS.index("NPP")] < 0.4          # bought with these two
    assert v[i7329, COLS.index("Fs")] < 0.4
    assert max(v[i2847]) < 1.2                        # 2847 is close on ALL three


def test_V_reproduces_the_rounds_OWN_convergence_distance_verdict():
    """Independent agreement, not self-consistency.

    R3's Phase-2 screening built its own metric by hand -- exceedance outside each band in
    half-band units, summed, zero inside -- and named case 2847 at 0.30
    (`use_cases/EcoSIM_BioCON/memory/logs/20260822u_*`). `V` is a different function (a MAX, and
    unclipped inside the band) reaching the same argmin. A change that broke the band
    normalization would move one of these and not the other.
    """
    cases, Y = _r3()
    ts = _targets()
    V, v, _ = violation_matrix(Y, COLS, ts)
    ok = np.isfinite(V)
    conv = np.sum(np.maximum(v - 1.0, 0.0), axis=1)     # the log's metric, re-derived
    assert cases[ok][np.argmin(V[ok])] == 2847
    assert cases[ok][np.argmin(conv[ok])] == 2847
    assert conv[int(np.where(cases == 2847)[0][0])] == pytest.approx(0.30, abs=0.005)


def test_no_R3_case_is_jointly_feasible_which_is_the_rounds_recorded_result():
    """R3's own summary records `n_within_band_all_three: 0`. `V <= 1` must agree, or the two
    band definitions have drifted apart."""
    _, Y = _r3()
    V, _, _ = violation_matrix(Y, COLS, _targets())
    assert int(np.nansum(V <= 1.0)) == 0


# =============================================================================
# An absent result is not a bad one
# =============================================================================

def test_a_missing_value_gives_nan_and_is_NOT_ranked_last():
    """docs/42 section 4: a failed run returns NO cost, not a large one. Imputing a penalty
    would teach anything fitted on this that the region is merely poor."""
    ts = _targets()
    Y = np.array([[389.0, 651.7, 6.2],
                  [np.nan, 651.7, 6.2],
                  [389.0, 651.7, np.nan]])
    V, v, binding = violation_matrix(Y, COLS, ts)
    assert np.isfinite(V[0])
    assert np.isnan(V[1]) and np.isnan(V[2])
    assert np.isnan(v[1]).all(), "a row with one hole must not report the other two v_i as valid"
    assert (binding[1:] == -1).all(), "no binding target may be indexable for an unscored row"
    # and it must not sort to the end as though it were the worst case
    assert not np.nanmax(V) > 1e6


def test_a_DEAD_case_sinks_under_V_without_any_viability_threshold():
    """Worth pinning because it looks like `V` needs an alive filter and it does not: a dead
    EcoSIM case has NPP ~ 0, so v_NPP = 1/u = 2.78 on the arithmetic alone."""
    V, _, _ = violation_matrix(np.array([[0.0, 0.0, 0.0]]), COLS, _targets())
    assert V[0] > 2.7


# =============================================================================
# Refusals
# =============================================================================

def test_a_zero_observation_is_REFUSED_not_turned_into_infinity():
    with pytest.raises(ValueError, match="undefined"):
        Target("z", 0.0, 0.3)


def test_a_non_positive_uncertainty_is_REFUSED():
    for u in (0.0, -0.1):
        with pytest.raises(ValueError, match="must be > 0"):
            Target("z", 1.0, u)


def test_a_missing_target_COLUMN_is_refused_by_name():
    """The target names in targets.yaml and the columns of the extracted matrix are a contract;
    silently scoring fewer targets changes `max_i` invisibly
    ([[feedback_exact_strings_are_contracts]])."""
    with pytest.raises(SystemExit, match="plant_C"):
        violation_matrix(np.zeros((2, 2)), ["NPP", "Fs"], _targets())


def test_a_placeholder_target_is_skipped_and_an_ALL_placeholder_file_is_refused(tmp_path):
    p = tmp_path / "t.yaml"
    p.write_text("targets:\n  a: {observed: 10.0, uncertainty: 0.2}\n"
                 "  b: {observed: null, uncertainty: 0.2}\n")
    got = load_targets(p)
    assert [t.name for t in got] == ["a"]

    p.write_text("targets:\n  b: {observed: null, uncertainty: 0.2}\n")
    with pytest.raises(SystemExit, match="no scorable target"):
        load_targets(p)


def test_requesting_a_target_that_is_not_scorable_is_refused(tmp_path):
    p = tmp_path / "t.yaml"
    p.write_text("targets:\n  a: {observed: 10.0, uncertainty: 0.2}\n")
    with pytest.raises(SystemExit, match="not scorable"):
        load_targets(p, ["a", "b"])


def test_the_real_biocon_targets_file_loads_with_the_bands_docs_42_quotes():
    if not BIOCON_TARGETS.is_file():
        pytest.skip("BioCON targets absent")
    ts = {t.name: t for t in load_targets(BIOCON_TARGETS, COLS)}
    assert ts["plant_C"].lo == pytest.approx(423.6, abs=0.1)    # docs/42 section 1's anchor
    assert ts["NPP"].lo == pytest.approx(249.0, abs=0.1)
    assert ts["Fs"].hi == pytest.approx(7.936, abs=0.01)


# =============================================================================
# Bound to its source
# =============================================================================

def test_composite_rmsre_is_the_LIBRARY_metric_not_a_reimplementation():
    """If this drifted, the disagreement check would be comparing `V` against something no other
    part of A2MC ranks by ([[feedback_bind_derived_facts_to_their_source]])."""
    ts = _targets()
    Y = np.array([[420.0, 500.0, 5.0]])
    got = composite_rmsre(Y, COLS, ts)[0]
    expect = aggregate_costs([abs(420.0 - 389.0) / 389.0,
                              abs(500.0 - 651.7) / 651.7,
                              abs(5.0 - 6.2) / 6.2], method="rmsre")
    assert got == pytest.approx(expect)


def test_both_modules_resolve_the_REPO_ROOT_and_not_their_own_parent():
    """Moving these files into `tools/bayesian_optimization/` broke `parents[1]` -- it then
    pointed at `tools/`, and the CLI died with `No module named 'tools'` the first time it was
    run from the new path. A path constant counted in directory levels breaks silently on the
    next move, so it is asserted against something only the real root has.
    """
    from tools.bayesian_optimization import bo_replay, objective as objective_mod
    for m in (objective_mod, bo_replay):
        assert (m.REPO / "CLAUDE.md").is_file(), (
            f"{m.__name__}.REPO resolves to {m.REPO}, which is not the repository root")
