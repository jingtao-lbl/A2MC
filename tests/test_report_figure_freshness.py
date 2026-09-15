"""A report's embedded figure must still match the canonical figure it cites.

The failure this guards is silent by construction: a stale PNG renders perfectly, the report builds,
every other checker passes, and the reader is shown something the prose no longer describes. It
happened for three consecutive corrections and three PDF rebuilds before a human noticed by looking.

Every test below asserts a way the checker must FAIL, or a way it must not pass silently
([[feedback_a_check_that_cannot_fail]]).
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from tools.check_report_figure_freshness import (MANIFEST, ERROR, OK, WARN,   # noqa: E402
                                                 check_report, init_manifest,
                                                 read_manifest, report_images)

PNG = b"\x89PNG\r\n\x1a\n" + b"canonical" * 32
OTHER = b"\x89PNG\r\n\x1a\n" + b"different" * 32


def _case(tmp_path, copy_bytes=PNG, manifest=True, day="20261231"):
    """A report folder and the phase_results stem it copied its figure from.

    `day` defaults AFTER `MANIFEST_REQUIRED_FROM`, so the fixture is a report the rule applies to;
    a pre-cutoff default would silently measure the exemption in every test below.
    """
    stem = tmp_path / "use_cases" / "C" / "memory" / "phase_results" / "20260101a_stem"
    stem.mkdir(parents=True)
    (stem / "R1_thing.png").write_bytes(PNG)

    rpt = tmp_path / "use_cases" / "C" / "reports" / f"{day}a_topic"
    rpt.mkdir(parents=True)
    (rpt / "report.md").write_text("# r\n\n![](fig1.png)\n")
    (rpt / "fig1.png").write_bytes(copy_bytes)
    if manifest:
        (rpt / MANIFEST).write_text(
            "# c\nfig1.png\tuse_cases/C/memory/phase_results/20260101a_stem/R1_thing.png\n")
    return rpt, stem


def _run(rpt, monkeypatch, tmp_path, **kw):
    """check_report resolves sources against ROOT, so point ROOT at the fixture tree."""
    import tools.check_report_figure_freshness as m
    monkeypatch.setattr(m, "ROOT", tmp_path)
    return m.check_report(rpt, **kw)


# --------------------------------------------------------------------------------------------
# the failure it exists for
# --------------------------------------------------------------------------------------------

def test_a_DRIFTED_copy_is_an_ERROR(tmp_path, monkeypatch):
    """THE test. The copy renders fine and says something the source no longer says."""
    rpt, _ = _case(tmp_path, copy_bytes=OTHER)
    errs, warns, checked, unmapped, _ = _run(rpt, monkeypatch, tmp_path)
    assert len(errs) == 1 and "DIFFERS" in errs[0]
    assert checked == 0


def test_a_matching_copy_is_clean(tmp_path, monkeypatch):
    rpt, _ = _case(tmp_path)
    errs, warns, checked, unmapped, _ = _run(rpt, monkeypatch, tmp_path)
    assert errs == [] and warns == []
    assert checked == 1 and unmapped == 0


def test_a_source_that_no_longer_EXISTS_is_an_ERROR(tmp_path, monkeypatch):
    """A dead pointer reads as provenance and resolves to nothing."""
    rpt, stem = _case(tmp_path)
    (stem / "R1_thing.png").unlink()
    errs, _, _, _, _ = _run(rpt, monkeypatch, tmp_path)
    assert len(errs) == 1 and "does not exist" in errs[0]


def test_a_manifest_entry_for_a_MISSING_figure_is_an_ERROR(tmp_path, monkeypatch):
    """A stale entry makes the manifest a record of a report that no longer exists."""
    rpt, _ = _case(tmp_path)
    (rpt / "fig1.png").unlink()
    errs, _, _, _, _ = _run(rpt, monkeypatch, tmp_path)
    assert len(errs) == 1 and "not in the folder" in errs[0]


# --------------------------------------------------------------------------------------------
# it must not pass silently on a report it has not actually checked
# --------------------------------------------------------------------------------------------

def test_an_UNMAPPED_figure_in_an_IN_SCOPE_report_is_an_ERROR(tmp_path, monkeypatch):
    """Going forward the mapping is required, so a new report that declares nothing must fail
    rather than warn. Counting it as verified would be worse still."""
    rpt, _ = _case(tmp_path, manifest=False)
    errs, warns, checked, unmapped, exempt = _run(rpt, monkeypatch, tmp_path)
    assert len(errs) == 1 and "no entry" in errs[0]
    assert warns == []
    assert checked == 0, "an unverified figure was counted as verified"
    assert unmapped == 1 and exempt is False


def test_strict_unmapped_turns_that_warning_into_an_error(tmp_path, monkeypatch):
    rpt, _ = _case(tmp_path, manifest=False)
    errs, warns, _, _, _ = _run(rpt, monkeypatch, tmp_path, strict_unmapped=True)
    assert len(errs) == 1 and warns == []


def test_unmapped_messages_COLLAPSE_to_one_per_report(tmp_path, monkeypatch):
    """One warning per figure was 259 lines on the first repo-wide run, which is a checker nobody
    reads. The actionable unit is the report, because the remedy is one --init per folder."""
    rpt, _ = _case(tmp_path, manifest=False)
    for i in range(6):
        (rpt / f"extra{i}.png").write_bytes(OTHER)
    errs, warns, _, unmapped, _ = _run(rpt, monkeypatch, tmp_path)
    msgs = errs + warns
    assert len(msgs) == 1, f"expected one collapsed message, got {len(msgs)}"
    assert unmapped == 7
    assert "+3 more" in msgs[0]


def test_a_malformed_manifest_line_is_an_ERROR_not_a_silent_skip(tmp_path, monkeypatch):
    rpt, _ = _case(tmp_path)
    (rpt / MANIFEST).write_text("fig1.png only-one-column\n")
    errs, _, checked, _, _ = _run(rpt, monkeypatch, tmp_path)
    assert len(errs) == 1 and "expected" in errs[0]
    assert checked == 0


# --------------------------------------------------------------------------------------------
# what is NOT a figure
# --------------------------------------------------------------------------------------------

def test_the_reports_own_rendered_output_is_not_treated_as_a_figure(tmp_path):
    """`<topic>.pdf` beside `<topic>.md` is the deliverable, and has no canonical source to match."""
    rpt, _ = _case(tmp_path)
    (rpt / "report.pdf").write_bytes(b"%PDF-1.4")
    (rpt / "report.jpg").write_bytes(OTHER)          # same stem as report.md -> excluded
    names = {i.name for i in report_images(rpt)}
    assert names == {"fig1.png"}


# --------------------------------------------------------------------------------------------
# --init
# --------------------------------------------------------------------------------------------

def test_init_maps_a_byte_identical_copy(tmp_path, monkeypatch):
    import tools.check_report_figure_freshness as m
    rpt, stem = _case(tmp_path, manifest=False)
    monkeypatch.setattr(m, "ROOT", tmp_path)
    monkeypatch.setattr(m, "_git_files", lambda *pats: [stem / "R1_thing.png"])
    matched, total = m.init_manifest(rpt)
    assert (matched, total) == (1, 1)
    assert read_manifest(rpt) == {
        "fig1.png": "use_cases/C/memory/phase_results/20260101a_stem/R1_thing.png"}


def test_init_leaves_an_ALREADY_DRIFTED_figure_unmapped_rather_than_guessing(tmp_path, monkeypatch):
    """Guessing a source for a figure that matches nothing would paper over the exact condition the
    tool exists to find. It is also how a report-native figure acquires a false provenance."""
    import tools.check_report_figure_freshness as m
    rpt, stem = _case(tmp_path, copy_bytes=OTHER, manifest=False)
    monkeypatch.setattr(m, "ROOT", tmp_path)
    monkeypatch.setattr(m, "_git_files", lambda *pats: [stem / "R1_thing.png"])
    matched, total = m.init_manifest(rpt)
    assert (matched, total) == (0, 1)
    assert read_manifest(rpt) == {}


# --------------------------------------------------------------------------------------------
# end to end, on the real repository
# --------------------------------------------------------------------------------------------

def test_the_real_methodology_report_is_clean_and_actually_verifies_something(tmp_path):
    """A live guard: this report is the one whose figure drifted, and a run that verified ZERO
    figures would pass just as quietly as one that verified three."""
    rpt = REPO / "use_cases/EcoSIM_Lusignan/reports/20260913a_KGML_Emulator_Methodology"
    if not (rpt / MANIFEST).is_file():
        pytest.skip("methodology report not present in this checkout")
    r = subprocess.run([sys.executable, "tools/check_report_figure_freshness.py", str(rpt)],
                       cwd=REPO, capture_output=True, text=True)
    assert r.returncode == OK, r.stdout
    assert "3 figure(s) verified against a canonical source" in r.stdout


# --------------------------------------------------------------------------------------------
# grandfathering: enforce going forward, stay silent about history (PI, 2026-09-15)
# --------------------------------------------------------------------------------------------

def test_a_report_PREDATING_the_rule_with_no_manifest_is_EXEMPT_and_counted(tmp_path, monkeypatch):
    """84 report folders predate the rule, most in cases another effort owns. Retro-warning them
    would make the output permanently red, which is the state in which a checker stops being read."""
    rpt, _ = _case(tmp_path, manifest=False, day="20260101")
    errs, warns, checked, unmapped, exempt = _run(rpt, monkeypatch, tmp_path)
    assert exempt is True
    assert errs == [] and warns == []
    assert checked == 0 and unmapped == 0


def test_a_grandfathered_report_that_OPTS_IN_is_drift_checked_in_full(tmp_path, monkeypatch):
    """The exemption covers the REQUIREMENT to declare a source, never the check itself. Otherwise
    adopting the rule on an old report would buy nothing and nobody would."""
    rpt, _ = _case(tmp_path, copy_bytes=OTHER, manifest=True, day="20260101")
    errs, _, _, _, exempt = _run(rpt, monkeypatch, tmp_path)
    assert exempt is False
    assert len(errs) == 1 and "DIFFERS" in errs[0]


def test_a_report_dated_ON_the_cutoff_is_IN_scope(tmp_path, monkeypatch):
    """A boundary that silently excluded its own first day would delay the rule by one report."""
    import tools.check_report_figure_freshness as m
    rpt, _ = _case(tmp_path, manifest=False, day=m.MANIFEST_REQUIRED_FROM)
    errs, _, _, _, exempt = _run(rpt, monkeypatch, tmp_path)
    assert exempt is False and len(errs) == 1


def test_an_UNPARSEABLE_folder_name_is_treated_as_grandfathered(tmp_path, monkeypatch):
    """The folder-naming convention has its own checker; refusing a commit over a name this tool
    cannot read would be this tool enforcing someone else's rule."""
    rpt, _ = _case(tmp_path, manifest=False, day="notadate")
    _, _, _, _, exempt = _run(rpt, monkeypatch, tmp_path)
    assert exempt is True
