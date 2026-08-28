"""End-to-end smoke test for the PFLOTRAN adapter (onboard-model step 13).

The PFLOTRAN counterpart of `tests/test_ecosim_e2e.py`, driving the offline chain
against the miniLEO reference case with no compiled binary and no HPC run:

    adapter/spec/backend load
      -> parse the input DECK (121 knobs, addressed by block path)
      -> load the case's parameter bounds (Phase-0 parse_param_list)
      -> write_parameter_file -> create_case -> submit_ensemble (dry-run)
      -> extract_history_variables (from the reference mass-balance tape)
      -> evaluate_pflotran_case (obs<->sim alignment + the shared cost layer)

STATUS (2026-08-12): the offline chain is now FULLY WIRED — deck writing
(`20260812a`), case-directory assembly and submission (`20260812c`) are all
implemented. See `test_pflotran_write_parameter_file.py` and
`test_pflotran_create_case.py` for their own dedicated coverage; this file
covers the CHAIN, end to end. What remains is real HPC execution (an actual
`sbatch`, not a dry-run) and the ensemble-design question the run template
itself flags (the shared restart checkpoint under perturbed parameters) —
neither is a code gap this test suite can assert.

Run:  ~/a2mc_env/bin/python -m pytest tests/test_pflotran_e2e.py -v

Author: Jing Tao with Claude
"""
from __future__ import annotations

import os
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent

PARAM_LIST = REPO / "use_cases/PFLOTRAN_miniLEO/parameters/pflotran_minileo_param_list.csv"
TARGETS = REPO / "use_cases/PFLOTRAN_miniLEO/validation/targets.yaml"

_TAPE = os.environ.get("A2MC_PFLOTRAN_REFERENCE_MAS", "")
_CASE_DIR = Path(_TAPE).parent if _TAPE else None
_DECK = Path(os.environ.get("A2MC_PFLOTRAN_DECK", "")) if os.environ.get("A2MC_PFLOTRAN_DECK") else None

_needs_case = pytest.mark.skipif(
    not (_TAPE and Path(_TAPE).is_file()),
    reason="miniLEO reference case not staged (set A2MC_PFLOTRAN_REFERENCE_MAS)")


def test_adapter_and_spec_load():
    from models.pflotran.backend import PFLOTRANBackend
    be = PFLOTRANBackend()
    assert be.spec.name == "pflotran"
    # PFLOTRAN has no PFT axis; its grouping axis is the mesh region.
    assert be.spec.grouping_axis == "region"
    assert "outflow_concentration" in be.MODEL_REDUCES


def test_case_parameter_bounds_parse():
    from phases.phase0_design.create_parameter_sample import parse_param_list
    names, lower, upper = parse_param_list(PARAM_LIST)
    assert len(names) == 16, ("miniLEO's parameter list is 16 knobs -- was 17 until\n        2026-08-27, when LIQUID_SATURATION was cut after a probe measured it INERT\n        under the deck's pre-steady-state restart (bit-identical tape, max rel diff\n        exactly 0.0). See memory/logs/20260827a_phase0_design_r01_restart_consistency_probe.md")
    assert all(lo < hi for lo, hi in zip(lower, upper)), "every bound must be ordered"


@pytest.mark.skipif(not (_DECK and _DECK.is_file()),
                    reason="miniLEO deck not staged (set A2MC_PFLOTRAN_DECK)")
def test_deck_parses_to_addressable_knobs():
    from models.pflotran.backend import PFLOTRANBackend
    params = PFLOTRANBackend().parse_parameters(_DECK)
    assert len(params) == 121, "the miniLEO deck exposes 121 addressable knobs"
    # keys are BLOCK PATHS, not bare names — the property the graph builder relies on
    assert any("/" in k for k in params), "deck knobs must be addressed by block path"


@pytest.mark.skipif(not (_DECK and _DECK.is_file()),
                    reason="miniLEO deck not staged (set A2MC_PFLOTRAN_DECK)")
def test_write_create_submit_chain(tmp_path):
    """The three previously-unwired stages, run back to back through the SAME calling
    convention scripts/materialize_adapter_ensemble.py uses (deck written directly at its
    final case-dir location; create_case stages the rest; submit_ensemble dry-runs)."""
    from models.pflotran.backend import PFLOTRANBackend
    be = PFLOTRANBackend()

    case_name = "e2e_case001"
    pfile = tmp_path / case_name / _DECK.name
    pfile.parent.mkdir(parents=True, exist_ok=True)
    be.write_parameter_file(_DECK, {"RATE_CONSTANT_Glass_FB": -13.0}, pfile)

    cfg = {
        "A2MC_BASE_PARAM_FILE": str(_DECK),
        "A2MC_PFLOTRAN_RUNTEMPLATE": str(REPO / "models/pflotran/runtemplates/hpc_standalone.sh.tmpl"),
        "A2MC_HPC_MPI_RANKS": "8", "A2MC_HPC_ACCOUNT": "m5199", "A2MC_DRY_RUN": "1",
    }
    case_dir = be.create_case(case_name, pfile, cfg)
    assert case_dir == pfile.parent
    assert (case_dir / "submit.sh").exists()
    assert (case_dir / "savannah_river.dat").exists(), "the database must be staged alongside the deck"

    job_ids = be.submit_ensemble([case_dir], cfg)
    assert job_ids == ["DRYRUN-0000"]
    assert (case_dir / "job_id.txt").read_text().strip() == job_ids[0]


@_needs_case
def test_case_status_reads_pflotrans_own_signals():
    """A run with many timestep cuts has NOT failed — MAX_TS_CUTS is a per-timestep
    consecutive budget, and the miniLEO run completed with 168 lifetime cuts against a
    limit of 20. Reading that as failure is the mis-triage this method exists to avoid."""
    from models.pflotran.backend import PFLOTRANBackend
    assert PFLOTRANBackend().check_case_status(_CASE_DIR) == "COMPLETED"


@_needs_case
def test_extract_returns_named_columns_and_the_time_axis():
    from models.pflotran.backend import PFLOTRANBackend
    got = PFLOTRANBackend().extract_history_variables(
        _CASE_DIR, ["east Na+ [mol/h]", "east Water Mass [kg/h]"])
    assert "Time [h]" in got, "the time column must always come back; windows are hours"
    assert len(got["east Na+ [mol/h]"]) == len(got["Time [h]"]) == 3360


@_needs_case
def test_full_chain_scores_the_reference_case():
    """The chain's payoff: a completed case scored against the case's own targets.yaml."""
    from tools.pflotran_evaluate_case import evaluate_pflotran_case, targets_from_yaml

    targets = targets_from_yaml(TARGETS)
    assert len(targets) == 11, (
        "10 chemistry targets (DIC added 2026-08-07) + hydrograph added 2026-08-13")
    total, errors, sim = evaluate_pflotran_case(_CASE_DIR, targets)

    assert set(errors) == {t["name"] for t in targets}
    assert all(v == v and v > 0 for v in sim.values()), "every target must reduce to a real value"
    # The reference run's known skill. A change here means the chain changed, not the model.
    # Was 0.2082 over 9 targets on the pre-correction window [0, 768]; the window is now
    # [806, 1574] model hours (the observation clock is offset by 806 h) and DIC is a
    # tenth target. Phase 0 log 20260807b_phase0_design_r01_* carries that before/after.
    # UPDATED 2026-08-13 (dev log 20260813b): hydrograph (outflow_flux, NRMSE) is an 11th
    # target, err=0.0709 -- below the RMS of the other 10 -- so the aggregate moves down,
    # 0.2277 -> 0.2181. This is the "total_cost changes from a 10- to 11-target aggregate"
    # consequence flagged when outflow_flux was first wired (not added live) -- confirmed
    # here now that it IS added live.
    assert total == pytest.approx(0.2181, abs=0.001)
