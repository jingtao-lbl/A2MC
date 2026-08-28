"""Phase 5 must archive its job scripts into phase_results/{stem}/submit_scripts/.

The run root is untracked scratch; the submit script is the only record of which BINARY a run was
bound to. PHASE 0 IS EXEMPT: its ensemble scripts are config-generated and far too numerous. Every test names a way the check must FIRE or must NOT ([[feedback_a_check_that_cannot_fail]]).

The FIRST version of this check sat below `if phase not in ANALYSIS_PHASES: return`, so it could
never fire for phase 5 -- the only phase it targets. `test_it_fires_for_phase_5` is the regression.

Author: Jing Tao with Claude
"""
import importlib.util

import pytest

SRC = "tools/check_offline_log_evidence.py"


def load():
    spec = importlib.util.spec_from_file_location("_ev", SRC)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def make(site, stem, phase, with_scripts=False):
    (site / "memory" / "logs").mkdir(parents=True, exist_ok=True)
    d = site / "memory" / "phase_results" / stem
    d.mkdir(parents=True, exist_ok=True)
    if with_scripts:
        (d / "submit_scripts").mkdir()
        (d / "submit_scripts" / "case1_submit.sh").write_text("#!/bin/bash\n")
    log = site / "memory" / "logs" / f"{stem}.md"
    log.write_text(f"# T\n\n**Site:** S\n**Phase:** {phase}\n")
    return log


def fires(m, log, site):
    _e, w = m.check_log(log, site)
    return any("submit_scripts" in x for x in w)


def test_it_fires_for_phase_5(tmp_path):
    """THE REGRESSION. Phase 5 is a NON-analysis phase, so a check placed below the
    analysis-phase early return is silent for exactly the phase it exists for."""
    m = load()
    log = make(tmp_path, "20260901a_phase5_testing_r03_c09_x", 5)
    assert fires(m, log, tmp_path)


def test_it_is_SILENT_once_the_scripts_are_archived(tmp_path):
    m = load()
    log = make(tmp_path, "20260901a_phase5_testing_r03_c09_x", 5, with_scripts=True)
    assert not fires(m, log, tmp_path)


def test_an_EMPTY_submit_scripts_dir_still_fires(tmp_path):
    """A directory created and never filled is the failure wearing the fix's clothes."""
    m = load()
    stem = "20260901a_phase5_testing_r03_c09_x"
    log = make(tmp_path, stem, 5)
    (tmp_path / "memory" / "phase_results" / stem / "submit_scripts").mkdir()
    assert fires(m, log, tmp_path)


@pytest.mark.parametrize("phase,word", [(0, "design"), (1, "exploration"), (2, "screening"),
                                        (3, "diagnosis"), (4, "hypothesis"), (6, "refinement")])
def test_it_does_NOT_fire_for_any_phase_but_5(tmp_path, phase, word):
    """PHASE 0 IS EXEMPT and this is the regression for it: its ensemble job scripts are
    config-generated and number in the tens of thousands (one round is 59,393 cases), so the
    config plus the generator IS the reproducible record. PI-corrected the day the rule landed."""
    m = load()
    log = make(tmp_path, f"20260901a_phase{phase}_{word}_r03_c09_x", phase)
    assert not fires(m, log, tmp_path)


def test_it_is_NON_RETROACTIVE(tmp_path):
    m = load()
    log = make(tmp_path, "20260801a_phase5_testing_r03_c01_old", 5)
    assert not fires(m, log, tmp_path)


def test_the_boundary_DATE_itself_fires(tmp_path):
    """>= not >, so the day the rule takes effect is covered."""
    m = load()
    log = make(tmp_path, "20260823a_phase5_testing_r03_c05_x", 5)
    assert fires(m, log, tmp_path)
