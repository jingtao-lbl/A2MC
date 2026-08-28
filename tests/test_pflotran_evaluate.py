#!/usr/bin/env python
"""PFLOTRAN case evaluation — the derived `outflow_concentration` reduce and its traps.

Guards the additive wiring that makes `use_cases/PFLOTRAN_miniLEO` SCORABLE (dev log
20260806a; gap matrix 20260802c):
  * backend-declared `MODEL_REDUCES` dispatched to `reduce_derived` by the generic layer;
  * `denominator` carried from targets.yaml onto Target and collected for extraction;
  * the ratio arithmetic (mol/h over kg/h -> mol/L), which cancels miniLEO's unresolved
    area normalisation;
  * WINDOWS ARE HOURS — the generic layer slices `window` as ROW INDICES, and on the real
    tape that silently halves the intended span. Refused, not documented.

Most tests are self-contained (synthetic in-memory tapes). The one that needs the real
miniLEO reference run skips when it is not staged; point A2MC_PFLOTRAN_REFERENCE_MAS at it.

Run:  ~/a2mc_env/bin/python -m pytest tests/test_pflotran_evaluate.py -q
"""
from __future__ import annotations

import os
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent

from models.pflotran.backend import (  # noqa: E402
    PFLOTRAN_TIME_COLUMN, PFLOTRAN_WATER_DENSITY, PFLOTRANBackend)
from tools.model_evaluate_case import reduce_target  # noqa: E402

TARGETS_YAML = REPO / "use_cases/PFLOTRAN_miniLEO/validation/targets.yaml"

NUM = "east Na+ [mol/h]"
DEN = "east Water Mass [kg/h]"


def _tape(times, numer, water):
    """A minimal extracted-history dict in the shape extract_history_variables returns."""
    return {PFLOTRAN_TIME_COLUMN: list(times), NUM: list(numer), DEN: list(water)}


def _target(**kw):
    spec = {"name": "outflow_Na", "variable": NUM, "denominator": DEN,
            "reduce": "outflow_concentration", "observed": 1.0}
    spec.update(kw)
    return spec


# ---------------------------------------------------------------- the arithmetic


def test_outflow_concentration_is_the_ratio_of_two_columns():
    """C = (mol/h) / (kg/h / rho * 1000). One row, hand-checkable."""
    # 1 kg/h at rho=1000 kg/m^3 is exactly 1 L/h, so 2 mol/h -> 2 mol/L.
    got = reduce_target(PFLOTRANBackend(),
                        _tape([1.0], [2.0], [1.0]),
                        _target(water_density=1000.0))
    assert got == pytest.approx(2.0)


def test_default_density_is_the_declared_constant_not_a_buried_number():
    """The density is an assumption; it must be the named constant, and overridable."""
    tape = _tape([1.0], [1.0], [1.0])
    default = reduce_target(PFLOTRANBackend(), tape, _target())
    assert default == pytest.approx(1.0 / (1.0 / PFLOTRAN_WATER_DENSITY * 1000.0))
    override = reduce_target(PFLOTRANBackend(), tape, _target(water_density=500.0))
    assert override == pytest.approx(1.0 / (1.0 / 500.0 * 1000.0))
    assert override != pytest.approx(default)


def test_zero_flow_rows_are_skipped_not_counted_as_zero():
    """No outflow means the concentration is UNDEFINED. Averaging a 0 in biases low."""
    rho = 1000.0
    # two rows at 2 mol/L, one row with no outflow at all
    tape = _tape([1.0, 2.0, 3.0], [2.0, 2.0, 5.0], [1.0, 1.0, 0.0])
    got = reduce_target(PFLOTRANBackend(), tape, _target(water_density=rho))
    assert got == pytest.approx(2.0)          # not 4/3, which counting the 0 row gives


# ---------------------------------------------------------------- windows are HOURS


def test_window_is_hours_not_row_indices():
    """The trap. A 0.5 h tape makes the two readings differ by exactly 2x in span.

    Rows at t = 0.5..3.0 h. window [0, 2] means the first FOUR rows (t <= 2 h), not
    the first THREE (indices 0..2). The concentrations are staged so the two readings
    give different answers — if this ever reads as indices, the value moves.
    """
    times = [0.5, 1.0, 1.5, 2.0, 2.5, 3.0]
    numer = [1.0, 1.0, 1.0, 5.0, 99.0, 99.0]        # row index 3 (t=2.0 h) is the discriminator
    water = [1.0] * 6
    got = reduce_target(PFLOTRANBackend(), _tape(times, numer, water),
                        _target(window=[0, 2], water_density=1000.0))
    assert got == pytest.approx((1.0 + 1.0 + 1.0 + 5.0) / 4)      # hours: 4 rows
    assert got != pytest.approx((1.0 + 1.0 + 1.0) / 3)            # indices: 3 rows


def test_generic_reduce_with_a_window_is_refused():
    """A plain mean+window would be sliced as row indices by the generic layer.

    That is the silent-wrong-answer path, so it raises where the spec is still in hand
    rather than returning a plausible number.
    """
    with pytest.raises(ValueError, match="HOURS"):
        reduce_target(PFLOTRANBackend(),
                      _tape([0.5, 1.0], [1.0, 1.0], [1.0, 1.0]),
                      {"name": "x", "variable": NUM, "reduce": "mean", "window": [0, 1]})


def test_window_selecting_no_rows_raises_and_names_the_trap():
    with pytest.raises(ValueError, match="HOURS"):
        reduce_target(PFLOTRANBackend(), _tape([0.5, 1.0], [1.0, 1.0], [1.0, 1.0]),
                      _target(window=[500, 600]))


# ---------------------------------------------------------------- the plumbing


def test_missing_denominator_raises():
    """A ratio without its second column must not silently become a bare rate."""
    spec = _target()
    del spec["denominator"]
    with pytest.raises(ValueError, match="denominator"):
        reduce_target(PFLOTRANBackend(), _tape([1.0], [1.0], [1.0]), spec)


def test_denominator_is_collected_for_extraction():
    """evaluate_model_case must ask the backend for the denominator column too."""
    from tools.model_evaluate_case import evaluate_model_case

    asked = {}

    class Spy(PFLOTRANBackend):
        def extract_history_variables(self, case_path, variables, time_range=None, tape="h0"):
            asked["variables"] = list(variables)
            return _tape([1.0], [2.0], [1.0])

    evaluate_model_case(Path("/nonexistent"), [_target(water_density=1000.0)],
                        backend=Spy())
    assert DEN in asked["variables"], "the ratio's denominator was never extracted"
    assert NUM in asked["variables"]


def test_targets_yaml_carries_denominator_onto_target():
    """The 10 ratio (outflow_concentration) targets, NOT the hydrograph target added
    2026-08-13 -- that one carries observed_series_file instead of denominator, see
    test_targets_yaml_carries_observed_series_file_onto_hydrograph_target below."""
    from tools.targets_loader import parse_targets_yaml
    targets = parse_targets_yaml(TARGETS_YAML)
    assert targets, "miniLEO targets.yaml parsed empty"
    ratio_targets = {n: t for n, t in targets.items() if t.reduce == "outflow_concentration"}
    assert len(ratio_targets) == 10, "10 chemistry targets since DIC was added 2026-08-07"
    for name, t in ratio_targets.items():
        assert t.denominator == DEN, f"{name} lost its denominator in the loader"


def test_targets_yaml_carries_observed_series_file_onto_hydrograph_target():
    """Regression guard for the same class of bug `denominator` had before it was
    threaded through targets_loader/pflotran_evaluate_case/screen_ensemble: dropping
    observed_series_file anywhere in that chain makes the hydrograph target raise
    ValueError('requires observed_series_file') the moment it is actually scored."""
    from tools.targets_loader import parse_targets_yaml
    targets = parse_targets_yaml(TARGETS_YAML)
    hydro = targets["hydrograph"]
    assert hydro.reduce == "outflow_flux"
    assert hydro.observed_series_file == (
        "use_cases/PFLOTRAN_miniLEO/validation/data/measured_hydrograph.txt")

    from tools.pflotran_evaluate_case import targets_from_yaml
    specs = {s["name"]: s for s in targets_from_yaml(TARGETS_YAML)}
    assert specs["hydrograph"]["observed_series_file"] == hydro.observed_series_file
    assert specs["hydrograph"]["observed"] == pytest.approx(1.0), (
        "hydrograph's observed must be the 1.0 sentinel, not a physical flow value")


def test_unknown_derived_reduce_raises_not_silently_defaults():
    with pytest.raises(NotImplementedError, match="derived reduce"):
        PFLOTRANBackend().reduce_derived(_tape([1.0], [1.0], [1.0]),
                                         _target(), "no_such_reduce")


# ---------------------------------------------------------- outflow_flux (full-series NRMSE)
#
# Added 20260813 to close the "SCORABLE BUT NOT YET WIRED" gap targets.yaml flagged for
# the absolute hydrograph. A per-point relative-error version was tried first and
# rejected: miniLEO's tipping-bucket gauge genuinely reads exact 0.0 mm/h between
# pulses (confirmed against the real series -- a repeated tip-quantum value like
# 0.092624 alternates with 0.0, the signature of "no tip this bin", not sensor
# failure), and dividing by that floor blew the RMSRE up to >19 on the real V0 run,
# dominated by 8 of 874 points. NRMSE (normalized once, by the observed RANGE) does
# not have that failure mode -- true zeros are just ordinary data.

MEASURED_HYDROGRAPH = REPO / "use_cases/PFLOTRAN_miniLEO/validation/data/measured_hydrograph.txt"


def _flux_target(**kw):
    spec = {"name": "hydrograph", "variable": DEN, "reduce": "outflow_flux",
            "observed": 1.0, "observed_series_file": str(MEASURED_HYDROGRAPH)}
    spec.update(kw)
    return spec


def _write_series(path: Path, rows) -> None:
    """rows: iterable of (day_since_experiment_start, mm/h)."""
    path.write_text("\n".join(f"{d}\t{v}" for d, v in rows) + "\n")


def test_outflow_flux_requires_observed_series_file():
    spec = _flux_target()
    del spec["observed_series_file"]
    with pytest.raises(ValueError, match="observed_series_file"):
        reduce_target(PFLOTRANBackend(), _tape([806.0], [0.0], [1.0]), spec)


def test_outflow_flux_missing_series_file_raises(tmp_path):
    with pytest.raises(FileNotFoundError, match="observed_series_file"):
        reduce_target(PFLOTRANBackend(), _tape([806.0], [0.0], [1.0]),
                      _flux_target(observed_series_file=str(tmp_path / "nope.txt")))


def test_outflow_flux_perfect_match_returns_the_sentinel_one(tmp_path):
    """A simulation that reproduces the measured series exactly -> nrmse=0 -> 1.0 + 0.

    rho=1000, area=1 makes ``-water/rho/area*1000 == -water`` exactly, so the water
    column can be hand-picked to equal the negative of the measured mm/h values.
    """
    series = tmp_path / "measured.txt"
    _write_series(series, [(0.0, 5.0), (0.5, 10.0), (1.0, 0.0)])
    start_h = 806.0
    times = [start_h, start_h + 12.0, start_h + 24.0]        # days 0, 0.5, 1.0
    water = [-5.0, -10.0, 0.0]
    tape = _tape(times, [0.0] * 3, water)
    got = reduce_target(PFLOTRANBackend(), tape,
                        _flux_target(observed_series_file=str(series), water_density=1000.0,
                                     plan_area_m2=1.0, experiment_start_h=start_h))
    assert got == pytest.approx(1.0, abs=1e-9)


def test_outflow_flux_true_zero_observations_do_not_blow_up(tmp_path):
    """The regression case: real zero-flow measurements, sim slightly above zero there.

    Under per-point relative error this diverges (division by 0); NRMSE must not.
    """
    series = tmp_path / "measured.txt"
    _write_series(series, [(0.0, 0.0), (0.5, 0.0), (1.0, 20.0), (1.5, 0.0)])
    start_h = 806.0
    times = [start_h + 12.0 * i for i in range(4)]
    # sim reads a small residual flow (0.3 mm/h) exactly where measured is 0
    water = [-0.3, -0.3, -20.0, -0.3]
    tape = _tape(times, [0.0] * 4, water)
    got = reduce_target(PFLOTRANBackend(), tape,
                        _flux_target(observed_series_file=str(series), water_density=1000.0,
                                     plan_area_m2=1.0, experiment_start_h=start_h))
    assert 1.0 < got < 1.5, f"NRMSE sentinel should stay small and finite, got {got}"


def test_outflow_flux_window_is_hours_and_gap_needs_no_special_case(tmp_path):
    """A gap in the MEASURED series (no rows, like miniLEO's day-3-to-11 outage) simply
    contributes nothing -- no explicit exclusion logic is needed, interpolation just
    never lands there. A window narrower than the full record changes which measured
    rows count.
    """
    series = tmp_path / "measured.txt"
    # a gap between day 1 and day 10 -- mirrors the real file's day-3-to-11 outage
    _write_series(series, [(0.0, 1.0), (0.5, 1.0), (10.0, 1.0), (10.5, 1.0)])
    start_h = 806.0
    times = [start_h + 12.0 * i for i in range(3000)]     # dense sim coverage, days 0-1500
    water = [-1.0] * 3000
    tape = _tape(times, [0.0] * 3000, water)

    full = reduce_target(PFLOTRANBackend(), tape,
                         _flux_target(observed_series_file=str(series), water_density=1000.0,
                                      plan_area_m2=1.0, experiment_start_h=start_h))
    assert full == pytest.approx(1.0, abs=1e-9)   # perfect match on both sides of the gap

    narrow = reduce_target(PFLOTRANBackend(), tape,
                           _flux_target(observed_series_file=str(series), water_density=1000.0,
                                        plan_area_m2=1.0, experiment_start_h=start_h,
                                        window=[start_h, start_h + 20.0]))
    assert narrow == pytest.approx(1.0, abs=1e-9)   # still perfect, just fewer rows counted


def test_outflow_flux_window_selecting_no_measured_rows_raises():
    """Window covers the SIM tape (so that guard doesn't fire first) but sits far
    below the real committed file's ~806h start, so the MEASURED side is empty."""
    with pytest.raises(ValueError, match="no measured points"):
        reduce_target(PFLOTRANBackend(), _tape([0.0, 0.5], [0.0, 0.0], [-1.0, -1.0]),
                      _flux_target(window=[0, 1]))


def test_outflow_flux_reduce_is_dispatched_from_model_reduces():
    assert "outflow_flux" in PFLOTRANBackend.MODEL_REDUCES


def test_committed_measured_hydrograph_file_is_well_formed():
    """The checked-in data file itself, independent of the reduce logic."""
    import numpy as np
    data = np.loadtxt(MEASURED_HYDROGRAPH)
    assert data.shape == (950, 2)
    assert data[:, 0].min() == pytest.approx(0.0)
    assert 33.0 < data[:, 0].max() < 34.0
    assert (data[:, 1] >= 0.0).all(), "outflow rate cannot be negative"


# The outflow_flux real-reference-tape regression test lives at the bottom of this
# file, alongside the concentration targets' equivalent anchor -- both need
# _REF/_REF_DIR, defined there (see test_outflow_flux_reference_run_is_a_small_finite_nrmse).


# ---------------------------------------------------------------- screening reach

def _write_case(case_dir: Path, na_rate: float, nrows: int = 8):
    """A minimal PFLOTRAN case: a 3-column *-mas.dat plus a completed *.out.

    Mirrors the real tape's two load-bearing format properties — a quoted,
    comma-separated HEADER and whitespace-only, separator-free DATA rows.
    """
    case_dir.mkdir(parents=True, exist_ok=True)
    header = ','.join(f'"{c}"' for c in (PFLOTRAN_TIME_COLUMN, NUM, DEN))
    rows = [f"  {0.5 * (i + 1):14.8E}  {na_rate:14.8E}  {1.0:14.8E}" for i in range(nrows)]
    (case_dir / "pflotran-mas.dat").write_text(header + "\n" + "\n".join(rows) + "\n")
    (case_dir / "pflotran.out").write_text("Wall Clock Time: 1.0 seconds\n")


def test_screening_reaches_the_derived_reduce(tmp_path, capsys):
    """The loop, not just the CLI: phase2 screening must score a PFLOTRAN ensemble.

    The screening path builds its own variable list and target dicts, so a
    denominator dropped THERE reproduces the bug independently of
    evaluate_model_case — and the per-target reduce swallows exceptions into NaN,
    which makes a fully-failed target look like a screened one.
    """
    import sys as _sys
    _sys.path.insert(0, str(REPO / "phases/phase2_screening"))
    from screen_ensemble import _load_ensemble_simulated_backend
    from tools.optimize_function import Target

    ens = tmp_path / "ensemble"
    _write_case(ens / "case1", na_rate=2.0)
    _write_case(ens / "case2", na_rate=4.0)

    targets = {"outflow_Na": Target(
        name="outflow_Na", observed=2.0e-3, variable=NUM, denominator=DEN,
        reduce="outflow_concentration", window=[0, 4], pft="east")}

    simulated, case_numbers = _load_ensemble_simulated_backend(
        ens, targets, config=None, backend=PFLOTRANBackend(),
        cache_path=None, verbose=False, use_cache=False)[:2]

    vals = [float(v[0]) for v in simulated["outflow_Na"]]
    assert len(case_numbers) == 2, "both completed cases should be discovered"
    assert not any(v != v for v in vals), (
        "screening reduced a PFLOTRAN target to NaN — the derived reduce was not reached")
    # rho=997.16 default: C = rate / (1 kg/h / rho * 1000)
    assert vals == pytest.approx(sorted([2.0 / (1000.0 / PFLOTRAN_WATER_DENSITY),
                                         4.0 / (1000.0 / PFLOTRAN_WATER_DENSITY)]))


def test_screening_reports_a_failed_reduce_instead_of_silent_nan(tmp_path, capsys):
    """An all-NaN target must announce itself. It is indistinguishable downstream."""
    import sys as _sys
    _sys.path.insert(0, str(REPO / "phases/phase2_screening"))
    from screen_ensemble import _load_ensemble_simulated_backend
    from tools.optimize_function import Target

    ens = tmp_path / "ensemble"
    _write_case(ens / "case1", na_rate=2.0)
    # a ratio target with NO denominator -> the reduce raises -> NaN
    targets = {"broken": Target(name="broken", observed=1.0, variable=NUM,
                                reduce="outflow_concentration", window=[0, 4])}

    simulated, _ = _load_ensemble_simulated_backend(
        ens, targets, config=None, backend=PFLOTRANBackend(),
        cache_path=None, verbose=False, use_cache=False)[:2]

    assert float(simulated["broken"][0][0]) != float(simulated["broken"][0][0])   # NaN
    out = capsys.readouterr().out
    assert "WARNING" in out and "broken" in out and "denominator" in out


# ---------------------------------------------------------------- tape location

def _resolve(case_dir, monkeypatch, explicit=None):
    from models.pflotran.datasets import _reference_mas
    if explicit is None:
        monkeypatch.delenv("A2MC_PFLOTRAN_REFERENCE_MAS", raising=False)
    else:
        monkeypatch.setenv("A2MC_PFLOTRAN_REFERENCE_MAS", str(explicit))
    return _reference_mas(Path(case_dir))


def test_reference_tape_found_in_either_layout(tmp_path, monkeypatch):
    """PFLOTRAN writes its tape where the run was launched: flat beside the deck in
    the hand-copied bundle, under output/ in the team's own repository. A tape that
    is not found does NOT fail — the RAG build quietly drops every column node — so
    both layouts must resolve."""
    flat_case = tmp_path / "flat"
    flat_case.mkdir()
    (flat_case / "pflotran-mas.dat").write_text("x")
    assert _resolve(flat_case, monkeypatch) == flat_case / "pflotran-mas.dat"

    nested_case = tmp_path / "nested"
    (nested_case / "output").mkdir(parents=True)
    (nested_case / "output" / "pflotran-mas.dat").write_text("x")
    assert _resolve(nested_case, monkeypatch) == nested_case / "output" / "pflotran-mas.dat"


def test_explicit_reference_tape_env_wins(tmp_path, monkeypatch):
    case = tmp_path / "case"
    (case / "output").mkdir(parents=True)
    (case / "output" / "pflotran-mas.dat").write_text("x")
    elsewhere = tmp_path / "somewhere-else-mas.dat"
    elsewhere.write_text("x")
    assert _resolve(case, monkeypatch, explicit=elsewhere) == elsewhere


def test_absent_tape_resolves_to_a_concrete_path_not_empty(tmp_path, monkeypatch):
    """A consumer must be able to report WHICH file is missing."""
    case = tmp_path / "empty"
    case.mkdir()
    assert _resolve(case, monkeypatch) == case / "pflotran-mas.dat"


# ---------------------------------------------------------------- the real tape

_REF = os.environ.get("A2MC_PFLOTRAN_REFERENCE_MAS", "")
_REF_DIR = Path(_REF).parent if _REF else None


@pytest.mark.skipif(not (_REF and Path(_REF).is_file()),
                    reason="miniLEO reference run not staged (set A2MC_PFLOTRAN_REFERENCE_MAS)")
def test_reference_run_reproduces_the_published_baseline_ratios():
    """The regression anchor: score the real reference tape and reproduce the model/obs
    ratios published in targets.yaml's BASELINE SKILL block.

    UPDATED 2026-08-07 with the window correction. These ratios were previously
    {Si 1.035, Na 0.956, K 0.905, Fe 0.782, P 0.777, Mg 0.789, Ca 1.210, Mn 1.191,
    Al 0.605} and were wrong: the targets scored MODEL hours 0-768, but the observation
    clock is offset from the model clock by 806 h, so the measured record 0-768 h is
    model hours 806-1574. The old window covered the pre-experiment period. Mn's miss
    changed SIGN under the fix. See the Phase 0 log
    use_cases/PFLOTRAN_miniLEO/memory/logs/20260807b_phase0_design_r01_*.md.

    NOTE these no longer match use_cases/.../compare_outflow_chemistry.py, which still
    uses the original window convention. targets.yaml is the authority.
    """
    from tools.pflotran_evaluate_case import evaluate_pflotran_case, targets_from_yaml

    published = {"outflow_Si": 1.160, "outflow_Na": 1.032, "outflow_K": 1.044,
                 "outflow_Fe": 0.889, "outflow_P": 0.810, "outflow_Mg": 0.898,
                 "outflow_Ca": 1.386, "outflow_Mn": 0.607, "outflow_Al": 0.650,
                 "outflow_DIC": 0.932}

    targets = targets_from_yaml(TARGETS_YAML)
    assert len(targets) == 11, (
        "10 chemistry targets (DIC added 2026-08-07) + hydrograph added 2026-08-13")
    _, _, sim = evaluate_pflotran_case(_REF_DIR, targets)

    for name, expected in published.items():
        obs = next(float(t["observed"]) for t in targets if t["name"] == name)
        assert sim[name] / obs == pytest.approx(expected, abs=0.001), name


@pytest.mark.skipif(not (_REF and Path(_REF).is_file()),
                    reason="miniLEO reference run not staged (set A2MC_PFLOTRAN_REFERENCE_MAS)")
def test_outflow_flux_reference_run_is_a_small_finite_nrmse():
    """Regression anchor for outflow_flux on the real reference tape, same pattern as
    the concentration targets' anchor above. Not a tight bound -- just: wired, finite,
    and small (this is the V0 baseline, already known to have the right volume /
    over-damped peak timing)."""
    from tools.pflotran_evaluate_case import evaluate_pflotran_case

    targets = [_flux_target(window=[806, 1574])]
    _, errors, sim = evaluate_pflotran_case(_REF_DIR, targets)
    assert 0.0 < sim["hydrograph"] - 1.0 < 1.0, sim["hydrograph"]
