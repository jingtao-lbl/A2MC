"""Tests for the two UNIVERSAL checks in tools/check_offline_log_evidence.py.

Both apply to every offline phase log, not only the analysis phases 3/4/6 -- which is the point.
The restatement checks used to early-return for phases 0/1/2/5/7, so a phase-1 log got a green
tick from a function that had inspected nothing, and that vacuous tick was quoted as evidence of
quality (2026-08-22). Each test names a way the check must FAIL
(auto-memory `feedback_a_check_that_cannot_fail`).

Author: Jing Tao with Claude
"""
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "tools"))

cole = pytest.importorskip("check_offline_log_evidence")

PNG_BYTES = b"\x89PNG\r\n\x1a\n" + b"\0" * 32


def _site(tmp_path, stem, log_text, figures=(), extras=()):
    """Build a minimal site tree: memory/logs/{stem}.md + memory/phase_results/{stem}/."""
    site = tmp_path / "SiteX"
    (site / "memory" / "logs").mkdir(parents=True)
    topic = site / "memory" / "phase_results" / stem
    topic.mkdir(parents=True)
    for f in figures:
        (topic / f).write_bytes(PNG_BYTES)
    for f in extras:
        (topic / f).write_text("x")
    log = site / "memory" / "logs" / f"{stem}.md"
    log.write_text(log_text)
    return log


STEM = "20260822a_phase1_exploration_r03_demo"


def test_a_figure_named_only_in_prose_is_not_embedded(tmp_path):
    """The failure the PI caught: the log names its folder, so the figure renders as text and
    the reader has to go hunting. Naming is not showing."""
    log = _site(tmp_path, STEM,
                f"See `phase_results/{STEM}/plot.png` for the result.\n",
                figures=["plot.png"], extras=["NOTES.md", "make.py", "d.csv"])
    errs, warns = cole.check_log(log, REPO)
    assert not errs
    assert any("not EMBEDDED" in w for w in warns)


def test_an_embedded_figure_satisfies_the_check(tmp_path):
    log = _site(tmp_path, STEM,
                f"![](../phase_results/{STEM}/plot.png)\n\n**Figure 1.** What it shows.\n",
                figures=["plot.png"], extras=["NOTES.md", "make.py", "d.csv"])
    errs, warns = cole.check_log(log, REPO)
    assert not errs
    assert not any("not EMBEDDED" in w for w in warns)


def test_partial_embedding_names_only_the_missing_figures(tmp_path):
    log = _site(tmp_path, STEM,
                f"![](../phase_results/{STEM}/a.png)\n",
                figures=["a.png", "b.png"], extras=["NOTES.md", "make.py", "d.csv"])
    errs, warns = cole.check_log(log, REPO)
    w = next(x for x in warns if "not EMBEDDED" in x)
    assert "1 of 2" in w and "b.png" in w and "a.png" not in w.split("(")[1]


def test_a_dead_artifact_pointer_is_an_ERROR_not_a_warning(tmp_path):
    """A dead pointer reads as a citation, so a reader chases it instead of disbelieving it.
    Real instance: a renamed stem left frozen in a log's baked-in reasoning chain."""
    log = _site(tmp_path, STEM,
                f"![](../phase_results/{STEM}/plot.png)\n"
                "Prior work in `phase_results/20260815a_phase6_refinement_r03_gone/`.\n",
                figures=["plot.png"], extras=["NOTES.md", "make.py", "d.csv"])
    errs, warns = cole.check_log(log, REPO)
    assert any("dead artifact pointer" in e for e in errs)
    assert any("20260815a_phase6_refinement_r03_gone" in e for e in errs)


def test_a_live_artifact_pointer_does_not_error(tmp_path):
    log = _site(tmp_path, STEM,
                f"![](../phase_results/{STEM}/plot.png)\nSee `phase_results/{STEM}/` for data.\n",
                figures=["plot.png"], extras=["NOTES.md", "make.py", "d.csv"])
    errs, _ = cole.check_log(log, REPO)
    assert not errs


def test_a_literal_stem_placeholder_is_not_treated_as_a_pointer(tmp_path):
    """Docs and templates write `phase_results/{stem}/` literally. Erroring on that would make
    the check fire on prose it cannot possibly resolve, which is how a check gets disabled."""
    log = _site(tmp_path, STEM,
                f"![](../phase_results/{STEM}/plot.png)\n"
                "Artifacts live in `phase_results/{stem}/` by convention.\n",
                figures=["plot.png"], extras=["NOTES.md", "make.py", "d.csv"])
    errs, _ = cole.check_log(log, REPO)
    assert not errs


def test_the_checks_run_for_a_NON_analysis_phase(tmp_path):
    """The regression this whole file exists for: phases 0/1/2/5/7 used to early-return, so a
    phase-1 log received a green tick from a function that had inspected nothing."""
    for phase in ("0_design", "1_exploration", "2_screening", "5_testing"):
        stem = f"20260822a_phase{phase}_r03_demo"
        log = _site(tmp_path / phase, stem,
                    f"Named only: `phase_results/{stem}/plot.png`.\n",
                    figures=["plot.png"], extras=["NOTES.md", "make.py", "d.csv"])
        _, warns = cole.check_log(log, REPO)
        assert any("not EMBEDDED" in w for w in warns), f"phase {phase} was skipped"


def test_a_folder_with_no_figures_is_silent(tmp_path):
    log = _site(tmp_path, STEM, "No figures this phase.\n", extras=["NOTES.md"])
    errs, warns = cole.check_log(log, REPO)
    assert not errs
    assert not any("not EMBEDDED" in w for w in warns)


# ---------------------------------------------------------------------------
# The embed rule has an EFFECTIVE DATE (PI, 2026-08-22): logs written before it are
# grandfathered. The risk of a dated rule is that it quietly becomes a no-op, so these
# pin BOTH directions -- it must still fire on or after the date.
# ---------------------------------------------------------------------------

def test_a_log_predating_the_rule_is_grandfathered(tmp_path):
    stem = "20260821a_phase1_exploration_r03_old"
    log = _site(tmp_path, stem, f"Named only: `phase_results/{stem}/plot.png`.\n",
                figures=["plot.png"], extras=["NOTES.md", "make.py", "d.csv"])
    _, warns = cole.check_log(log, REPO)
    assert not any("not EMBEDDED" in w for w in warns)


def test_the_rule_fires_ON_its_effective_date(tmp_path):
    """A boundary written as `<` would be off by one day and silently exempt day zero."""
    stem = f"{cole.EMBED_RULE_EFFECTIVE}a_phase1_exploration_r03_onthedate"
    log = _site(tmp_path, stem, f"Named only: `phase_results/{stem}/plot.png`.\n",
                figures=["plot.png"], extras=["NOTES.md", "make.py", "d.csv"])
    _, warns = cole.check_log(log, REPO)
    assert any("not EMBEDDED" in w for w in warns)


def test_the_rule_fires_after_its_effective_date(tmp_path):
    stem = "20270101a_phase6_refinement_r03_future"
    log = _site(tmp_path, stem, f"Named only: `phase_results/{stem}/plot.png`.\n",
                figures=["plot.png"], extras=["NOTES.md", "make.py", "d.csv"])
    _, warns = cole.check_log(log, REPO)
    assert any("not EMBEDDED" in w for w in warns)


def test_a_grandfathered_log_is_STILL_checked_for_dead_pointers(tmp_path):
    """The date exempts one WARN, not the whole function. A dead pointer is a defect at any age."""
    stem = "20260101a_phase1_exploration_r03_ancient"
    log = _site(tmp_path, stem,
                "Prior work in `phase_results/20260815a_phase6_refinement_r03_gone/`.\n",
                figures=["plot.png"], extras=["NOTES.md", "make.py", "d.csv"])
    errs, _ = cole.check_log(log, REPO)
    assert any("dead artifact pointer" in e for e in errs)


# --- a target that resolves to nothing must FAIL, not pass (2026-08-28) -------------------
# A mistyped path returned exit 0 with the same green tick as a clean run, differing only in a
# "0 offline log(s) scanned" line the reader has no reason to distrust. Found when the 3-hourly
# self-review ran `--site PFLOTRAN_miniLEO` (missing the `use_cases/` prefix) and quoted the
# resulting tick as evidence the case's logs were clean.

def test_a_nonexistent_target_FAILS(tmp_path):
    """The whole point is to gate; a typo must not read as a clean gate."""
    assert cole.main(["--site", str(tmp_path / "no_such_case")]) == 1


def test_a_nonexistent_bare_path_FAILS(tmp_path):
    assert cole.main([str(tmp_path / "nope.md")]) == 1


def test_an_existing_dir_with_no_matching_logs_still_PASSES(tmp_path):
    """A young case legitimately has no offline logs yet -- that is empty, not broken."""
    d = tmp_path / "use_cases" / "New_Case" / "memory" / "logs"
    d.mkdir(parents=True)
    assert cole.main(["--site", str(tmp_path / "use_cases" / "New_Case")]) == 0
