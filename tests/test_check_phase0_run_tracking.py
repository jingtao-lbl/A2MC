"""tools/check_phase0_run_tracking.py: a round leaves Phase 0 only with its ensemble's run record.

visibility: public

Each test builds a throwaway case and names the mistake it catches. The first is the positive
control: a round past Phase 0 with no run_tracking/ must be reported, or every pass below is vacuous.
"""
import json

from tools.check_phase0_run_tracking import check_case

STEM = "20261020a_phase0_design_r02_the_round"


def _case(tmp_path, phase, stem=STEM, files=()):
    case = tmp_path / "Model_Case"
    (case / "memory" / "phase_results" / stem).mkdir(parents=True)
    (case / "memory" / "workflow_state_offline_r02.json").write_text(
        json.dumps({"calibration_round": 2, "current_phase": phase}))
    for f in files:
        p = case / "memory" / "phase_results" / stem / "run_tracking" / f
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text("x")
    return case


COMPLETE = ("SUBMISSION_r02.md", "submit_scripts/launcher.sh", "state_full.json", "watch_full.digest.log")


def test_past_phase0_without_record_is_reported(tmp_path):
    assert check_case(_case(tmp_path, "exploration"))           # fails if a missing record passes


def test_complete_record_passes(tmp_path):
    assert check_case(_case(tmp_path, "exploration", files=COMPLETE)) == []


def test_each_required_piece_is_checked(tmp_path):
    for drop in COMPLETE:
        case = _case(tmp_path / drop.replace("/", "_"), "screening",
                     files=[f for f in COMPLETE if f != drop])
        assert check_case(case), f"dropping {drop} went unreported"   # fails if any piece is optional


def test_still_in_design_is_not_checked(tmp_path):
    assert check_case(_case(tmp_path, "design")) == []          # the record is due at the handoff


def test_stem_before_cutoff_is_exempt(tmp_path):
    assert check_case(_case(tmp_path, "exploration", stem="20260901a_phase0_design_r02_old")) == []
