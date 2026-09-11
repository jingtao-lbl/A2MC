"""`check_cycle_reports.py` must catch a closed cycle with no report, and must not cry wolf.

THE GAP THIS CHECKER CLOSES, measured 2026-09-09. Cycles 14, 15 and 16 of `EcoSIM_Lusignan` R1b
were closed with no cycle report; the omission was recorded in the round summary as "debt" and the
round was closed on top of it. `calibration-discipline` item 7 requires a report at each cycle end
and `write-report` builds the ROUND report by synthesizing the CYCLE reports, so the round report
had to re-derive from raw phase logs -- the anti-pattern that contract explicitly names. Nothing
produced a signal, because every other Phase-6 requirement has a checker and this one did not.

**Every test here is a way the checker must FAIL** (`feedback_a_check_that_cannot_fail`). The two
that matter most are `test_round_tag_is_extracted_across_the_underscore`, which pins the regex bug
that made the first version under-report, and `test_a_later_rounds_report_does_not_answer_for_an_
earlier_one`, which pins the false pass that bug caused.

Author: Jing Tao with Claude on Perlmutter
"""
from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


def _mod():
    sp = importlib.util.spec_from_file_location("ccr", ROOT / "tools" / "check_cycle_reports.py")
    m = importlib.util.module_from_spec(sp)
    sp.loader.exec_module(m)
    return m


M = _mod()


def make_case(tmp_path, name, phase6, reports):
    """Build a minimal case tree: phase-6 log stems and report directory names."""
    case = tmp_path / name
    (case / "memory" / "logs").mkdir(parents=True)
    for stem in phase6:
        (case / "memory" / "logs" / stem).write_text("# log\n")
    (case / "reports").mkdir()
    for d in reports:
        (case / "reports" / d).mkdir()
    return case


# ---- the two regressions that made the FIRST version of this checker wrong ---------------

@pytest.mark.parametrize("name,expected", [
    ("20260717b_R1_cycle3_seedC_factorial", {(1, 3)}),
    ("20260719a_R2_c00_VRNXI_experiment_cycle", {(2, 0)}),
    ("20260908a_R1b_cycle13_the_two_halves_are_one_axis", {(1, 13)}),
    ("20260905a_R1_c00_corner_ladder", {(1, 0)}),
    ("20260901a_R1_c00_Cycle_Report_Birnessite_Lever", {(1, 0)}),
])
def test_round_tag_is_extracted_across_the_underscore(name, expected):
    """THE BUG. `\\bR(\\d+)\\b` matches nothing in `R1_cycle3`: `_` is a word character, so there
    is no boundary between the `1` and the `_`. The round came back None for every report in the
    repo, and the first measurement reported 1 missing cycle where the truth is 6."""
    assert M.report_cycles(name) == expected


def test_a_later_rounds_report_does_not_answer_for_an_earlier_one(tmp_path):
    """THE FALSE PASS the bug above caused: with the round unknown, a permissive fallback let
    `R2_c00` silently satisfy R1 cycle 0. Measured on `EcoSIM_BioCON`."""
    case = make_case(tmp_path, "Case",
                     ["20260716e_phase6_refinement_r01_c00_x.md"],
                     ["20260719a_R2_c00_VRNXI_experiment_cycle"])
    missing, n_closed, _, _ = M.audit(case)
    assert n_closed == 1
    assert [(r, c) for r, c, _ in missing] == [(1, 0)]


# ---- the check itself --------------------------------------------------------------------

def test_closed_cycle_with_no_report_is_reported(tmp_path):
    case = make_case(tmp_path, "Case",
                     ["20260908h_phase6_refinement_r01_c14_x.md"],
                     ["20260909a_R1b_ROUND_SUMMARY"])
    missing, _, _, _ = M.audit(case)
    assert [(r, c) for r, c, _ in missing] == [(1, 14)]


def test_the_round_summary_alone_does_not_satisfy_any_cycle(tmp_path):
    """A ROUND report is not a cycle report, and must not be mistaken for one -- which is exactly
    what happened at `EcoSIM_BioCON` R1 cycle 10, whose content was folded into the round summary."""
    case = make_case(tmp_path, "Case",
                     [f"2026090{i}a_phase6_refinement_r01_c0{i}_x.md" for i in (1, 2, 3)],
                     ["20260909a_R1_ROUND_SUMMARY", "20260909b_R1_FINAL_CONFIGURATION"])
    missing, _, _, _ = M.audit(case)
    assert len(missing) == 3


@pytest.mark.parametrize("report", [
    "20260905a_R1_c07_topic",        # zero-padded
    "20260905a_R1_c7_topic",         # unpadded
    "20260905a_R1_cycle7_topic",     # the word, unpadded
    "20260905a_R1_cycle07_topic",    # the word, padded
])
def test_every_naming_convention_in_the_repo_is_accepted(tmp_path, report):
    """Four forms are live in this repo today. A matcher that accepts only one cries wolf on
    three real cases, and a checker that cries wolf gets ignored."""
    case = make_case(tmp_path, "Case", ["20260905b_phase6_refinement_r01_c07_x.md"], [report])
    missing, _, _, _ = M.audit(case)
    assert missing == []


def test_an_untagged_report_is_accepted_permissively(tmp_path):
    """A single-round case may omit the round tag. Being permissive there is deliberate."""
    case = make_case(tmp_path, "Case", ["20260905b_phase6_refinement_r01_c07_x.md"],
                     ["20260905a_cycle7_no_round_tag"])
    assert M.audit(case)[0] == []


def test_a_cycle_with_no_phase6_log_is_not_demanded(tmp_path):
    """An in-flight cycle has not closed, so it owes nothing yet. Demanding a report for it would
    fire on every cycle mid-run, which is how a check gets disabled."""
    case = make_case(tmp_path, "Case",
                     ["20260905a_phase3_diagnosis_r01_c09_x.md",
                      "20260905b_phase5_testing_r01_c09_x.md"],
                     [])
    missing, n_closed, _, _ = M.audit(case)
    assert n_closed == 0 and missing == []


def test_a_case_with_no_logs_at_all_is_silent(tmp_path):
    case = tmp_path / "Empty"
    (case / "reports").mkdir(parents=True)
    assert M.audit(case) == ([], 0, 0, 0)


# ---- the anti-silent-pass guard ----------------------------------------------------------

def test_guard_trips_when_no_phase6_log_exists_anywhere(tmp_path, capsys):
    """If PhaseLogger's stem changed, every comparison stops matching and the checker would
    report clean forever. That is the failure it is least able to see about itself."""
    case = make_case(tmp_path, "Case", ["20260905a_phase6_REFINEMENT_RENAMED_r01_c00_x.md"], [])
    rc = M.main([str(case)])
    assert rc == 2
    assert "ANTI-SILENT-PASS" in capsys.readouterr().err


def test_guard_trips_when_no_report_yields_a_cycle_token(tmp_path, capsys):
    """Phase-6 logs exist but no report directory anywhere parses as a cycle: either nobody
    writes cycle reports, or the folder convention moved. Clean would be a false pass."""
    case = make_case(tmp_path, "Case", ["20260905a_phase6_refinement_r01_c00_x.md"],
                     ["20260905a_some_investigation", "20260906a_another_topic"])
    rc = M.main([str(case)])
    assert rc == 2
    assert "ANTI-SILENT-PASS" in capsys.readouterr().err


def test_guard_does_not_trip_when_the_conventions_are_intact(tmp_path):
    case = make_case(tmp_path, "Case", ["20260905a_phase6_refinement_r01_c00_x.md"],
                     ["20260905b_R1_c00_topic"])
    assert M.main([str(case)]) == 0


# ---- exit codes --------------------------------------------------------------------------

def test_missing_is_a_warning_by_default_and_an_error_under_strict(tmp_path):
    """WARN by default because six real gaps sit in a case this branch does not own; erroring
    would block another effort's commits over history that predates the check."""
    case = make_case(tmp_path, "Case", ["20260905a_phase6_refinement_r01_c00_x.md"],
                     ["20260905b_R1_c99_unrelated"])
    assert M.main([str(case)]) == 0
    assert M.main([str(case), "--strict"]) == 1


def test_the_live_repo_is_auditable_and_lusignan_is_clean():
    """An integration check against the real tree: the case this checker was written for must be
    clean, and the checker must not crash on any real case."""
    lus = ROOT / "use_cases" / "EcoSIM_Lusignan"
    if not (lus / "memory" / "logs").is_dir():
        pytest.skip("EcoSIM_Lusignan not present in this checkout")
    missing, n_closed, _, _ = M.audit(lus)
    assert n_closed >= 16, "expected at least 16 closed cycles in R1b"
    assert missing == [], f"EcoSIM_Lusignan should be clean, got {missing}"
