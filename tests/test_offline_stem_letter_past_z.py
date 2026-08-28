"""The offline stem's date letter goes PAST z as za, zb, ... -- the checkers must follow it.

WHY THIS TEST EXISTS. `tools/check_offline_log_evidence.py` matched `\\d{8}[a-z]`, a SINGLE date
letter, while the convention (root CLAUDE.md, implemented in `phase_logger._offline_letter`) is that
the 27th same-day log is `za`, then `zb`, and so on -- chosen so `ls` still sorts chronologically.
The gate therefore did not recognise those stems as offline logs at all, and skipped them SILENTLY:
it printed "0 analysis-phase" and exited 0, which reads exactly like a pass. Measured on one site's
log directory when the defect was found: 9 of 103 analysis-phase offline logs were being skipped,
including a round-close refinement log.

`tools/session_report.py` carried the same single-letter regex and so omitted the same logs from
every session report.

The tests below assert the FAILING direction first -- a `z`-prefixed stem must be RECOGNISED -- so
reverting either regex to `[a-z]` fails this file rather than passing it quietly.
"""
import importlib.util
import pathlib

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]


def _load(rel, name):
    spec = importlib.util.spec_from_file_location(name, ROOT / rel)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


EVID = _load("tools/check_offline_log_evidence.py", "evid")
REPORT = _load("tools/session_report.py", "sessrep")

#: real stems from one site's logs/ -- the plain-letter case and the past-z cases.
PLAIN = "20260822c_phase2_screening_r03_r3_screening_of_the_alive_sub_ensemble.md"
PAST_Z = [
    "20260721za_phase3_diagnosis_r02_c08_iter01_c08_convergence_shot_fine_vrnxi_diagnosis.md",
    "20260721zk_phase6_refinement_r02_c09_c09_round_close_at_loop_limit_2of3.md",
    "20260823zd_phase4_hypothesis_r03_c08_iter06_c08_iteration_6_which_pair_is_antagonistic.md",
]


@pytest.mark.parametrize("name", PAST_Z)
def test_evidence_gate_recognises_a_past_z_stem(name):
    """THE REGRESSION. With `\\d{8}[a-z]` these returned None and the log was skipped in silence."""
    m = EVID.STEM_RE.match(name)
    assert m is not None, f"evidence gate does not recognise {name} as an offline log"


@pytest.mark.parametrize("name", PAST_Z)
def test_session_report_recognises_a_past_z_stem(name):
    m = REPORT.OFFLINE_STEM_RE.match(name)
    assert m is not None, f"session_report does not recognise {name} as an offline log"


def test_the_plain_single_letter_case_still_works():
    """The fix must WIDEN the pattern, not move it."""
    assert EVID.STEM_RE.match(PLAIN) is not None
    assert REPORT.OFFLINE_STEM_RE.match(PLAIN) is not None


def test_the_phase_number_is_captured_correctly_past_z():
    """Recognising the stem is not enough -- the phase number drives ANALYSIS_PHASES routing, so a
    regex that matched but mis-grouped would still skip the restatement checks."""
    m = EVID.STEM_RE.match(PAST_Z[1])
    assert int(m.group(2)) == 6
    assert m.group(2) in {str(p) for p in EVID.ANALYSIS_PHASES}
    assert m.group(1) == "20260721zk", "the date+letter group must capture BOTH letters"


def test_a_non_offline_name_is_still_rejected():
    """Guard the guard: a pattern loose enough to match anything would pass every test above."""
    for bad in ["README.md", "20260721_phase3_diagnosis_r02_x.md",
                "20260721zk_Some_Dev_Log_Topic.md", "2026072zk_phase3_diagnosis_r02_x.md"]:
        assert EVID.STEM_RE.match(bad) is None, f"{bad} should not match an offline phase stem"
