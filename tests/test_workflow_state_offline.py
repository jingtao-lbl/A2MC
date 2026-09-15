"""Regression tests for `tools/workflow_state_offline.py`.

Added 2026-09-12 after `add_thread` crashed on a MIXED-TYPE priority: it sorted on the raw
`priority` value, so `TypeError: '<' not supported between instances of 'int' and 'str'` fired the
moment one state held both forms. Measured on EcoSIM_Kougarok -- threads at priority='high'/'medium'
(this module accepts any value) then one at priority=1, the form `phase0-design` documents -- and a
legitimate Phase-0 HOLD could not be recorded at all.

The test that matters calls `add_thread`, NOT the helper: a first version asserted on
`_priority_key` alone and stayed GREEN with the fix reverted, because reverting changes the SORT
CALL and leaves the helper in place. A test never seen red is not evidence.
"""
import pytest

from tools.workflow_state_offline import WorkflowStateOffline, _priority_key


def _blank(tmp_path):
    site = tmp_path / "use_cases" / "Test_Case" / "memory"
    site.mkdir(parents=True)
    return WorkflowStateOffline(site_dir=str(site.parent), calibration_round=1)


def test_add_thread_accepts_mixed_int_and_word_priorities(tmp_path):
    """THE regression: this raised TypeError before the fix. Exercises add_thread, not the helper."""
    st = _blank(tmp_path)
    st.add_thread("worded", "a thread added with a word priority", priority="high")
    st.add_thread("medium_one", "another word", priority="medium")
    st.add_thread("numeric", "a thread added with the documented int priority", priority=1)
    st.add_thread("blocker", "the one that must surface first", priority=0)
    st.add_thread("unset", "no priority at all")
    ids = [t["id"] for t in st.data["open_threads"]]
    assert ids[0] == "blocker", f"blocker must sort first, got {ids}"
    assert ids[-1] == "unset", f"an unset priority must sort last, got {ids}"


def test_add_thread_is_idempotent_on_id_across_priority_types(tmp_path):
    st = _blank(tmp_path)
    st.add_thread("t", "first", priority="high")
    st.add_thread("t", "second, re-added with an int", priority=0)
    threads = [t for t in st.data["open_threads"] if t["id"] == "t"]
    assert len(threads) == 1
    assert threads[0]["summary"] == "second, re-added with an int"
    assert threads[0]["priority"] == 0


@pytest.mark.parametrize("value,expected", [
    (0, 0.0), (1, 1.0), (3, 3.0),
    ("high", 1.0), ("medium", 2.0), ("low", 3.0), ("critical", 0.0),
    ("2", 2.0),            # numeric string
    ("bogus", 99.0),       # unknown sorts last, never raises
    (True, 99.0),          # bool is an int subclass and is NOT a priority
])
def test_priority_key_normalises(value, expected):
    assert _priority_key({"priority": value}) == expected


def test_priority_key_defaults_when_absent():
    assert _priority_key({}) == 99.0
