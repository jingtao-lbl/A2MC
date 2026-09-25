"""A thread has to be retirable, and a closed round has to notice when one was not retired.

Register item H1. `close_thread()` existed and nothing required calling it, and a thread carried
no date, so staleness could not be measured even in principle. PFLOTRAN_miniLEO R1 closed on
2026-09-02 holding 16 open threads -- a wait on a filesystem drain, a queue gate, and an item
marked "NOT YET DONE" that had been done -- and the checker that validates this file on every
commit touching the case had no way to see any of it. A cold session reads an open thread as live
work, which is the whole cost.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from tools.workflow_state_offline import WorkflowStateOffline  # noqa: E402


def _state(tmp_path):
    (tmp_path / "memory").mkdir(parents=True, exist_ok=True)
    return WorkflowStateOffline.load(site_dir=str(tmp_path))


def test_a_thread_records_when_it_was_OPENED_and_last_TOUCHED(tmp_path):
    st = _state(tmp_path)
    st.add_thread("t1", "something", next_action="do it")
    t = st.data["open_threads"][0]
    assert t["opened"] and t["updated"], t
    assert t["opened"] == t["updated"], "a fresh thread's two stamps are the same day"


def test_RE_AFFIRMING_a_thread_keeps_its_opened_date(tmp_path):
    """Re-stating a thread does not make it new: `opened` is what says how long it has been open."""
    st = _state(tmp_path)
    st.add_thread("t1", "first wording")
    st.data["open_threads"][0]["opened"] = "2026-01-01"       # pretend it is old
    st.add_thread("t1", "restated wording", next_action="still this")
    t = st.data["open_threads"][0]
    assert t["opened"] == "2026-01-01", "re-affirming must not reset the opened date"
    assert t["updated"] > t["opened"], "but it must move the updated date"
    assert t["summary"] == "restated wording"


def test_closing_a_thread_removes_it(tmp_path):
    st = _state(tmp_path)
    st.add_thread("t1", "x")
    st.add_thread("t2", "y")
    st.close_thread("t1")
    assert [t["id"] for t in st.data["open_threads"]] == ["t2"]


# --------------------------------------------------------------------------------------------
# The checker rule
# --------------------------------------------------------------------------------------------

def _run_checker(path):
    import subprocess
    py = str(Path.home() / "a2mc_env" / "bin" / "python")
    return subprocess.run([py, str(REPO / "tools" / "check_workflow_state_offline.py"),
                           "--file", str(path)], capture_output=True, text=True, cwd=str(REPO))


def _closed_round(tmp_path, threads, report):
    """A minimal CLOSED round state carrying `threads`."""
    d = json.loads((REPO / "use_cases" / "PFLOTRAN_miniLEO" / "memory"
                    / "workflow_state_offline_r01.json").read_text())
    d["open_threads"] = threads
    d["round_close"] = {"report_path": report, "closed_at": "2026-09-02",
                        "steps": {"summarize": True, "compare": True, "report": True}}
    p = tmp_path / "workflow_state_offline_r01.json"
    p.write_text(json.dumps(d, indent=2))
    return p


def test_a_CLOSED_round_with_untouched_threads_is_REPORTED(tmp_path):
    """The measured failure: threads that outlived the close and were never looked at again."""
    p = _closed_round(tmp_path, [
        {"id": "waiting_on_a_drain", "summary": "x", "next_action": "WAIT",
         "opened": "2026-08-28", "updated": "2026-08-28"}],
        report="use_cases/PFLOTRAN_miniLEO/reports/20260902b_R1_ROUND_SUMMARY/R1_round_report.md")
    out = _run_checker(p).stdout
    assert "have not been touched since the round closed" in out, out
    assert "waiting_on_a_drain" in out


def test_a_RE_AFFIRMED_thread_is_accepted(tmp_path):
    """A thread may legitimately outlive its round -- an open question, a standing instruction --
    so the rule asks for a decision, not for deletion. Moving `updated` past the close is that
    decision, and it must silence the warning or nobody will bother making it."""
    p = _closed_round(tmp_path, [
        {"id": "open_question_for_r2", "summary": "x", "next_action": "decide at R2 design",
         "opened": "2026-08-28", "updated": "2026-09-22"}],
        report="use_cases/PFLOTRAN_miniLEO/reports/20260902b_R1_ROUND_SUMMARY/R1_round_report.md")
    out = _run_checker(p).stdout
    assert "have not been touched since the round closed" not in out, out


def test_an_UNSTAMPED_thread_counts_as_unreviewed(tmp_path):
    """Every thread written before the stamp existed has no date. Silence would be the wrong
    reading: unknown is not the same as reviewed."""
    p = _closed_round(tmp_path, [{"id": "legacy_thread", "summary": "x", "next_action": "y"}],
        report="use_cases/PFLOTRAN_miniLEO/reports/20260902b_R1_ROUND_SUMMARY/R1_round_report.md")
    out = _run_checker(p).stdout
    assert "legacy_thread" in out, out
