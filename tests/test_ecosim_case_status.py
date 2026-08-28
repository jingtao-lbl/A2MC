"""EcoSIMBackend.check_case_status must require the FINAL RESTART, not a tape that exists.

Written 2026-08-20. The old implementation returned COMPLETED as soon as an `*.ecosim.h0.*.nc`
tape was present, but EcoSIM creates that single tape at initialisation and appends to it -- so
the test answered "did this run START", and a run killed at the wall clock or dying part-way left
exactly the same evidence as a complete one. Measured on R3 chunk 1: it reported 32 COMPLETED
where sacct had 12 terminal tasks; with the fix the scan agreed with sacct exactly (16 and 16).

It mattered beyond reporting: phases/phase2_screening/screen_ensemble.py skips any case whose
status is not COMPLETED, so a truncated run was being scored as if it had finished.
"""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from models.ecosim.backend import EcoSIMBackend  # noqa: E402

BE = EcoSIMBackend()
STEM = "BioCON__test1_ex1.ecosim"


def _case(tmp_path, start=2000, forc="2000, 2022, 1", nml=True):
    cd = tmp_path / "BioCON_case1"
    cd.mkdir(exist_ok=True)
    if nml:
        (cd / "runfile.nml").write_text(
            f"&ecosim\n    start_date = '{start}0101000000'\n    forc_periods = {forc}\n/\n")
    return cd


def _tape(cd):            # the h0 tape EcoSIM opens at init and appends to
    (cd / f"{STEM}.h0.2000-01-01-00000.nc").write_text("x")


def _final_restart(cd, year):
    (cd / f"{STEM}.r.{year}-01-01-000000.nc").write_text("x")


# --- expected_final_restart_year -------------------------------------------------
def test_single_period_start_plus_length(tmp_path):
    assert BE.expected_final_restart_year(_case(tmp_path)) == 2023


def test_recycled_spinup_multiplies_by_repeats(tmp_path):
    """A spin-up recycles forcing: (2000,2004,10) is 50 simulated years, not 5."""
    assert BE.expected_final_restart_year(_case(tmp_path, forc="2000, 2004, 10")) == 2050


def test_multiple_triplets_sum(tmp_path):
    # 5*10 spin-up then a 23-yr transient = 73 years
    cd = _case(tmp_path, forc="2000, 2004, 10, 2000, 2022, 1")
    assert BE.expected_final_restart_year(cd) == 2073


def test_shortened_run_is_judged_against_its_own_namelist(tmp_path):
    """The smoke ensemble rewrites forc_periods; the case must be judged by ITS config."""
    assert BE.expected_final_restart_year(_case(tmp_path, forc="2000, 2001, 1")) == 2002


@pytest.mark.parametrize("forc", ["2000, 2022", "2022, 2000, 1", "2000, 2022, 0", "junk"])
def test_unparseable_or_impossible_forc_periods_is_none(tmp_path, forc):
    assert BE.expected_final_restart_year(_case(tmp_path, forc=forc)) is None


def test_missing_namelist_is_none(tmp_path):
    assert BE.expected_final_restart_year(_case(tmp_path, nml=False)) is None


# --- check_case_status -----------------------------------------------------------
def test_final_restart_means_completed(tmp_path):
    cd = _case(tmp_path)
    _tape(cd)
    _final_restart(cd, 2023)
    assert BE.check_case_status(cd) == "COMPLETED"


def test_tape_alone_is_not_completed(tmp_path):
    """THE BUG: an h0 tape exists from the first timestep. It must not read as finished."""
    cd = _case(tmp_path)
    _tape(cd)
    assert BE.check_case_status(cd) == "RUNNING"


def test_a_truncated_run_is_not_completed(tmp_path):
    """A run killed at the wall clock leaves the tape AND intermediate restarts, but never the
    final one. This is the unusable row an ensemble has to detect."""
    cd = _case(tmp_path)
    _tape(cd)
    for y in range(2001, 2010):
        (cd / f"{STEM}.r.{y}-01-01-000000.nc").write_text("x")
    assert BE.check_case_status(cd) == "RUNNING"


def test_wrong_final_year_is_not_completed(tmp_path):
    """A restart exists, but not the one this case's own run length calls for."""
    cd = _case(tmp_path, forc="2000, 2022, 1")
    _tape(cd)
    _final_restart(cd, 2005)
    assert BE.check_case_status(cd) == "RUNNING"


def test_nothing_started_is_pending(tmp_path):
    assert BE.check_case_status(_case(tmp_path)) == "PENDING"


def test_no_namelist_and_no_output_is_unknown(tmp_path):
    """Completion cannot be asserted without a run length; UNKNOWN beats a false COMPLETED."""
    assert BE.check_case_status(_case(tmp_path, nml=False)) == "UNKNOWN"


def test_error_in_slurm_err_is_failed(tmp_path):
    cd = _case(tmp_path)
    (cd / "slurm_1.err").write_text("srun: error: node failed\n")
    assert BE.check_case_status(cd) == "FAILED"
