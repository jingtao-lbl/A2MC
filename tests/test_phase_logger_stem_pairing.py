"""The offline topic stem must PAIR a log with its artifact folder across PROCESSES.

`_offline_stems` is an in-memory cache, so before 2026-08-22 a second process -- the usual shape,
where one run creates `phase_results/` and a later one writes the log -- allocated the NEXT free
letter and the log silently stopped matching its own folder. That cost a folder rename and 18
repointed state references on the R3 phase-1 log.

Each test names a way the pairing must FAIL (`feedback_a_check_that_cannot_fail`).

Author: Jing Tao with Claude
"""
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

pl = pytest.importorskip("tools.phase_logger")


def _logger(tmp_path, monkeypatch):
    site = tmp_path / "SiteX"
    # exist_ok: the helper is called TWICE per test to simulate two processes on one site.
    (site / "memory" / "logs").mkdir(parents=True, exist_ok=True)
    (site / "memory" / "phase_results").mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv("A2MC_AGENT_MODE", "offline")
    lg = pl.PhaseLogger(str(site))
    lg.set_iteration_context(iteration=0, calibration_round=3, experiment_count=1,
                             skip_testing_count=0)
    return lg, site


def test_a_fresh_logger_reuses_the_stem_of_an_existing_artifact_dir(tmp_path, monkeypatch):
    """The regression: process 1 makes the folder, process 2 must write INTO that pairing."""
    lg1, site = _logger(tmp_path, monkeypatch)
    d = lg1.topic_artifact_dir(2, "my topic")
    assert d.is_dir()

    lg2, _ = _logger(tmp_path, monkeypatch)          # fresh logger == fresh process
    lg2.site_dir = site
    lg2.log_dir = site / "memory" / "logs"
    assert lg2.topic_stem(2, "my topic") == d.name


def test_a_fresh_logger_reuses_the_stem_of_an_existing_LOG(tmp_path, monkeypatch):
    lg1, site = _logger(tmp_path, monkeypatch)
    stem = lg1.topic_stem(2, "my topic")
    (site / "memory" / "logs" / f"{stem}.md").write_text("x")

    lg2, _ = _logger(tmp_path, monkeypatch)
    lg2.site_dir = site
    lg2.log_dir = site / "memory" / "logs"
    assert lg2.topic_stem(2, "my topic") == stem


def test_a_DIFFERENT_topic_still_gets_its_own_letter(tmp_path, monkeypatch):
    """Reuse must key on the FULL suffix. Collapsing two topics onto one letter would be a
    worse bug than the one being fixed -- two logs overwriting each other."""
    lg1, site = _logger(tmp_path, monkeypatch)
    a = lg1.topic_artifact_dir(2, "topic one")

    lg2, _ = _logger(tmp_path, monkeypatch)
    lg2.site_dir = site
    lg2.log_dir = site / "memory" / "logs"
    b = lg2.topic_stem(2, "topic two")
    assert b != a.name
    assert lg2._offline_seq(b) != lg2._offline_seq(a.name)


def test_a_different_PHASE_with_the_same_descriptor_gets_its_own_letter(tmp_path, monkeypatch):
    lg1, site = _logger(tmp_path, monkeypatch)
    a = lg1.topic_artifact_dir(2, "same words")

    lg2, _ = _logger(tmp_path, monkeypatch)
    lg2.site_dir = site
    lg2.log_dir = site / "memory" / "logs"
    assert lg2.topic_stem(6, "same words") != a.name


def test_a_different_ROUND_gets_its_own_letter(tmp_path, monkeypatch):
    """r03 and r04 are different work; the suffix carries the round, so they must not collide."""
    lg1, site = _logger(tmp_path, monkeypatch)
    a = lg1.topic_artifact_dir(2, "same words")

    lg2, _ = _logger(tmp_path, monkeypatch)
    lg2.site_dir = site
    lg2.log_dir = site / "memory" / "logs"
    lg2.set_iteration_context(iteration=0, calibration_round=4, experiment_count=1,
                              skip_testing_count=0)
    assert lg2.topic_stem(2, "same words") != a.name


def test_the_stem_is_stable_within_one_process(tmp_path, monkeypatch):
    lg, _ = _logger(tmp_path, monkeypatch)
    assert lg.topic_stem(2, "t") == lg.topic_stem(2, "t") == lg.topic_artifact_dir(2, "t").name


# ---------------------------------------------------------------------------------------------
# The 60-char truncation must not leave a trailing separator.
#
# THE FAILURE THESE EXIST FOR (2026-08-23). `_clean_descriptor` ends with `s[:60]`, and the cut
# lands wherever it lands. When it lands on the '_' between two words, the descriptor -- and so the
# stem -- ends in '_'. Nothing breaks loudly: the log is written, the folder is created, and the two
# names differ from every hand-typed form of the same path by one invisible character. Measured that
# day: two of one cycle's three phase titles hit it, each costing a rename plus a repointed state
# entry, and the state's `log_path` stopped resolving until it was fixed.
#
# The stem's whole job is to PAIR logs/{stem}.md with phase_results/{stem}/, so a character that
# makes the pairing fragile is a defect in the pairing.

def test_a_descriptor_truncated_on_a_separator_does_not_end_in_one():
    """The real 2026-08-23 title, which cut at exactly the underscore before 'headroom'."""
    d = pl.PhaseLogger._clean_descriptor(
        "R3 c06 refinement: did slowing decomposition buy back the Fs headroom")
    assert not d.endswith("_"), f"stem descriptor ends in a separator: {d!r}"
    assert d == "r3_c06_refinement_did_slowing_decomposition_buy_back_the_fs"


def test_the_truncation_still_happens():
    """Guard the OTHER direction: stripping must not be implemented by dropping the cut."""
    long = "x" * 200
    assert len(pl.PhaseLogger._clean_descriptor(long)) == 60


def test_a_descriptor_of_only_separators_still_yields_a_usable_stem():
    """`'___'[:60].rstrip('_')` is empty, and an empty descriptor would build a stem ending in '_'."""
    assert pl.PhaseLogger._clean_descriptor("___") == "topic"
    assert pl.PhaseLogger._clean_descriptor("") == "topic"
    assert pl.PhaseLogger._clean_descriptor("   ") == "topic"


def test_no_phase_stem_ends_in_a_separator(tmp_path, monkeypatch):
    """End to end: the stem itself, not just the descriptor, across every runnable phase."""
    lg, _ = _logger(tmp_path, monkeypatch)
    title = "R3 c06 refinement: did slowing decomposition buy back the Fs headroom"
    for phase in range(0, 7):
        stem = lg.topic_stem(phase, title)
        assert not stem.endswith("_"), f"phase {phase} stem ends in a separator: {stem!r}"
