"""Negative tests for `tools/check_log_conformance.py`.

A checker you have only ever watched PASS is not a verified checker: a typo in a
section-name constant, an inverted condition, or an exit code hardcoded to 0 all
produce output indistinguishable from a working gate. So every rule L1-L5 gets a
case that must FAIL, alongside the conforming baseline that must pass.

Written after a first, ad-hoc negative test covered only L3 and L4 — and, in
doing so, revealed that L1 accepted the fake stem `20260899z` (month 08, day 99)
because the pattern only asserted "eight digits". That gap is now `test_L1_*`.

Run:  ~/a2mc_env/bin/python -m pytest tests/test_log_conformance.py -q
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "tools"))

import check_log_conformance as clc  # noqa: E402


GOOD = """\
# A Conforming Dev Log

**Date:** August 1, 2026
**Author:** Jing Tao with Claude
**Type:** Enhancement
**Version:** v2.218
**Branch:** A2MC-adapter-kit-PFLOTRAN

---

## Summary
x

## Problem
x

## Solution
x

## Files Changed
x

## Verification
x

## Skills and memory invoked
- **Skills:** none.

## Cross-references
- x

## Next
x
"""
# NOTE: Problem/Solution/Next were added 2026-08-14. The fixture is named GOOD, so it must satisfy
# the CURRENT contract, not the subset the checker happened to enforce when it was written — it
# previously carried only the four sections `_DEV_SECTIONS` verified, which is precisely the gap
# main's audit found (8 sections required in prose, 4 enforced in code).

GOOD_ANA = GOOD.replace("**Version:** v2.218\n", "")


def _write(tmp_path: Path, name: str, body: str, stream="dev_logs_adapterkitpflotran") -> Path:
    d = tmp_path / "memory" / stream
    d.mkdir(parents=True, exist_ok=True)
    p = d / name
    p.write_text(body)
    return p


def _codes(findings, level=None):
    return sorted(f.code for f in findings if level is None or f.level == level)


# --------------------------------------------------------------------------
# Baseline — the gate must PASS a conforming log, or every negative test below
# is meaningless (a checker that fails everything also "rejects").
# --------------------------------------------------------------------------

def test_conforming_dev_log_passes(tmp_path):
    p = _write(tmp_path, "20260801a_Good_Log.md", GOOD)
    assert clc.check_file(p) == []


def test_conforming_ana_log_passes(tmp_path):
    p = _write(tmp_path, "20260801a_Good_Log.md", GOOD_ANA, stream="ana_logs")
    assert clc.check_file(p) == []


# --------------------------------------------------------------------------
# L1 — filename
# --------------------------------------------------------------------------

@pytest.mark.parametrize("name", [
    "not_a_log.md",                      # no date stem at all
    "2026801a_Short_Date.md",            # 7 digits
    "20260801_No_Letter.md",             # missing the sequence letter
    "20260801a_lowercase_topic.md",      # topic not Title_Case
])
def test_L1_rejects_malformed_filenames(tmp_path, name):
    p = _write(tmp_path, name, GOOD)
    assert "L1" in _codes(clc.check_file(p), "error")


def test_L1_rejects_impossible_calendar_date(tmp_path):
    """The regression this suite was written for: `20260899` is eight digits
    but month 08 has no day 99, and the pattern alone accepted it."""
    p = _write(tmp_path, "20260899z_Fake_Date.md", GOOD)
    errs = [f for f in clc.check_file(p) if f.level == "error"]
    assert any(f.code == "L1" and "real calendar date" in f.msg for f in errs)


def test_L1_accepts_the_za_overflow_letter(tmp_path):
    """Past `z`, the convention is `za`..`zz` (sort-stable). Must NOT be rejected."""
    p = _write(tmp_path, "20260801za_Overflow_Letter.md", GOOD)
    assert "L1" not in _codes(clc.check_file(p))


# --------------------------------------------------------------------------
# L2 — header
# --------------------------------------------------------------------------

def test_L2_rejects_missing_header_field(tmp_path):
    p = _write(tmp_path, "20260801a_No_Branch.md",
               GOOD.replace("**Branch:** A2MC-adapter-kit-PFLOTRAN\n", ""))
    assert "L2" in _codes(clc.check_file(p), "error")


def test_L2_rejects_missing_h1_title(tmp_path):
    p = _write(tmp_path, "20260801a_No_Title.md",
               GOOD.replace("# A Conforming Dev Log\n", "Not a title\n"))
    assert "L2" in _codes(clc.check_file(p), "error")


def test_L2_rejects_version_on_an_ana_log(tmp_path):
    """ana logs are not version-tied; carrying Version is an error, not a warning."""
    p = _write(tmp_path, "20260801a_Ana_With_Version.md", GOOD, stream="ana_logs")
    errs = [f for f in clc.check_file(p) if f.level == "error"]
    assert any(f.code == "L2" and "Version" in f.msg for f in errs)


def test_L2_warns_on_out_of_order_header(tmp_path):
    """Order is a warning, not an error — the fields are all present."""
    swapped = GOOD.replace(
        "**Type:** Enhancement\n**Version:** v2.218\n",
        "**Version:** v2.218\n**Type:** Enhancement\n")
    p = _write(tmp_path, "20260801a_Swapped_Header.md", swapped)
    f = clc.check_file(p)
    assert "L2" in _codes(f, "warn") and "L2" not in _codes(f, "error")


# --------------------------------------------------------------------------
# L3 / L4 — sections (the two the original ad-hoc test covered)
# --------------------------------------------------------------------------

@pytest.mark.parametrize("section", ["Summary", "Files Changed",
                                     "Verification", "Cross-references"])
def test_L3_rejects_each_missing_required_section(tmp_path, section):
    p = _write(tmp_path, "20260801a_Missing_Section.md",
               GOOD.replace(f"## {section}\n", "## Something Else\n"))
    assert "L3" in _codes(clc.check_file(p), "error")


def _day_after(yyyymmdd: str) -> str:
    """Dates are DERIVED from the checker's own constant, never hardcoded.

    These three tests previously pinned the literal `20260801`, which silently encoded a WRONG
    boundary: `CAPABILITY_SECTION_SINCE` conflated the day the section was introduced with the day
    it became required (corrected to 20260803 on 2026-08-14 per main's audit). A test that
    snapshots a constant asserts yesterday's contract and fails the moment the constant is fixed —
    exactly the copy-don't-import trap already found in the leak-token list this same day.
    """
    import datetime
    d = datetime.date(int(yyyymmdd[:4]), int(yyyymmdd[4:6]), int(yyyymmdd[6:]))
    return (d + datetime.timedelta(days=1)).strftime("%Y%m%d")


def test_L4_errors_after_the_boundary_date(tmp_path):
    p = _write(tmp_path, f"{_day_after(clc.CAPABILITY_SECTION_SINCE)}a_After_Boundary.md",
               GOOD.replace("## Skills and memory invoked\n", "## Unrelated\n"))
    assert "L4" in _codes(clc.check_file(p), "error")


def test_L4_only_warns_on_the_boundary_date(tmp_path):
    """A date cannot express 'when the rule reached THIS branch', so same-day is
    a warning — logs written that day may legitimately predate its arrival."""
    p = _write(tmp_path, f"{clc.CAPABILITY_SECTION_SINCE}a_On_Boundary.md",
               GOOD.replace("## Skills and memory invoked\n", "## Unrelated\n"))
    f = clc.check_file(p)
    assert "L4" in _codes(f, "warn") and "L4" not in _codes(f, "error")


def test_L4_silent_before_the_rule_existed(tmp_path):
    """~200 older logs must not be retroactively failed."""
    p = _write(tmp_path, "20260715a_Before_Rule.md",
               GOOD.replace("## Skills and memory invoked\n", "## Unrelated\n"))
    assert "L4" not in _codes(clc.check_file(p))


# --------------------------------------------------------------------------
# L5 — branch header vs directory
# --------------------------------------------------------------------------

def test_L5_warns_when_branch_header_contradicts_the_directory(tmp_path):
    p = _write(tmp_path, "20260801a_Wrong_Branch.md",
               GOOD.replace("**Branch:** A2MC-adapter-kit-PFLOTRAN",
                            "**Branch:** A2MC-adapter-kit-ATS"))
    assert "L5" in _codes(clc.check_file(p), "warn")


def test_L5_tolerates_punctuation_differences(tmp_path):
    """`dev_logs_adapterkitpflotran` vs `A2MC-adapter-kit-PFLOTRAN` must match:
    the comparison squashes hyphens/underscores and case."""
    p = _write(tmp_path, "20260801a_Right_Branch.md", GOOD)
    assert "L5" not in _codes(clc.check_file(p))


# --------------------------------------------------------------------------
# Exit codes — the hook depends on these, so assert them directly
# --------------------------------------------------------------------------

def test_exit_code_is_2_on_error_and_1_on_warning_only(tmp_path, monkeypatch, capsys):
    bad = _write(tmp_path, "20260802a_Bad.md",
                 GOOD.replace("## Files Changed\n", "## Nope\n"))
    # Boundary date => L4 is a WARNING, so this exercises the rc=1 path. Derived, not hardcoded.
    warn_only = _write(tmp_path, f"{clc.CAPABILITY_SECTION_SINCE}a_Warn.md",
                       GOOD.replace("## Skills and memory invoked\n", "## Unrelated\n"))
    good = _write(tmp_path, f"{clc.CAPABILITY_SECTION_SINCE}b_Good.md", GOOD)

    def run(*paths):
        monkeypatch.setattr(sys, "argv", ["check_log_conformance.py", *map(str, paths)])
        rc = clc.main()
        capsys.readouterr()
        return rc

    assert run(bad) == 2
    assert run(warn_only) == 1
    assert run(good) == 0


# --------------------------------------------------------------------------
# Non-log files that live in a log directory (2026-08-03)
# --------------------------------------------------------------------------

def test_style_guide_is_not_checked_as_a_log(tmp_path, monkeypatch, capsys):
    """`memory/dev_logs/CLAUDE.md` IS the spec. Staging it made the pre-commit hook check the
    spec as though it were an instance of the spec and fail it 5 ways, blocking the very commit
    that fixed the spec."""
    real = _write(tmp_path, "20260801a_Real.md", GOOD)
    (real.parent / "CLAUDE.md").write_text("# Log Style Guide\n\nNot a log.\n")

    monkeypatch.setattr(sys, "argv", ["check_log_conformance.py", "--dir", str(real.parent)])
    rc = clc.main()
    out = capsys.readouterr().out
    assert rc == 0, out
    assert "1 file(s) checked" in out, f"the style guide should not be counted: {out}"


def test_a_log_whose_NAME_ends_in_claude_md_is_still_checked(tmp_path, monkeypatch, capsys):
    """The exclusion is an EXACT-name set, not a suffix match. A real log is called
    `20260602b_Handoff_Sync_Target_Flag_Drift_In_CLAUDE.md`; an `endswith('CLAUDE.md')` guard
    would silently skip it -- excluding a genuine log is worse than the bug being fixed."""
    bad = _write(tmp_path, "20260801a_Flag_Drift_In_CLAUDE.md",
                 GOOD.replace("## Files Changed\n", "## Nope\n"))

    monkeypatch.setattr(sys, "argv", ["check_log_conformance.py", "--dir", str(bad.parent)])
    rc = clc.main()
    out = capsys.readouterr().out
    assert rc == 2, f"a log merely NAMED *_CLAUDE.md must still be checked: {out}"
    assert "1 file(s) checked" in out


# --------------------------------------------------------------------------
# L7 — the bidirectional memory link (2026-08-07)
# --------------------------------------------------------------------------
# `**Memory:**` lists memories APPLIED; `**Memory written:**` lists memories this log
# CREATED or CHANGED. Only the second can be paired against a memory's `**Source:**`,
# which is why no bidirectional check existed before. Measured on the two obvious
# proxies before building this: requiring the Source log to merely MENTION the memory
# failed 7 of 9, and requiring it in `Files Changed` failed 11.

def _log_with_written(tmp_path, written: str):
    body = GOOD.replace(
        "- **Skills:** none.", f"- **Skills:** none.\n- **Memory written:** {written}", 1)
    assert "Memory written" in body, "fixture anchor drifted -- GOOD no longer has the Skills line"
    return _write(tmp_path, "20260801a_Real.md", body)


def test_L7_warns_when_the_memory_does_not_link_back(tmp_path, monkeypatch, capsys):
    """A half-connected pair is the whole point: the log claims authorship, the memory
    does not confirm it. WARN not ERROR while the backfill is outstanding."""
    mem = clc.REPO / ".claude_memory" / "feedback_a_check_that_cannot_fail.md"
    assert mem.exists(), "fixture memory must exist for this test to mean anything"
    assert "20260801a" not in mem.read_text(), "fixture memory must NOT name the test log"

    log = _log_with_written(tmp_path, "`feedback_a_check_that_cannot_fail`")
    monkeypatch.setattr(sys, "argv", ["check_log_conformance.py", "--dir", str(log.parent)])
    rc = clc.main()
    out = capsys.readouterr().out
    assert rc == 1, f"L7 must WARN (rc 1), not error (rc 2): {out}"
    assert "[L7]" in out and "back-link is missing" in out, out


def test_L7_warns_when_the_claimed_memory_does_not_exist(tmp_path, monkeypatch, capsys):
    """Claiming to have written a memory that isn't there asserts a provenance no reader
    can follow -- the same defect L6 catches for APPLIED memories."""
    log = _log_with_written(tmp_path, "`feedback_this_memory_is_invented`")
    monkeypatch.setattr(sys, "argv", ["check_log_conformance.py", "--dir", str(log.parent)])
    rc = clc.main()
    out = capsys.readouterr().out
    assert rc == 1, f"must WARN (rc 1), not error: {out}"
    assert "[L7]" in out and "not in .claude_memory/" in out, out


def test_L7_is_silent_when_the_log_writes_nothing(tmp_path, monkeypatch, capsys):
    """`Memory written` is OPTIONAL. Most logs create no memory, and a check that fired on
    all of them would be noise the reader learns to skip."""
    log = _write(tmp_path, "20260801a_Real.md", GOOD)
    monkeypatch.setattr(sys, "argv", ["check_log_conformance.py", "--dir", str(log.parent)])
    rc = clc.main()
    out = capsys.readouterr().out
    assert rc == 0 and "[L7]" not in out, out


def test_L7_passes_when_the_pair_is_closed(tmp_path, monkeypatch, capsys):
    """The positive case must be reachable, or the check can only ever fail. Uses a real
    memory whose Source names the real log that wrote it."""
    mem = clc.REPO / ".claude_memory" / "feedback_slurm_shared_qos_mem_inflates_cpus.md"
    if not mem.exists() or "20260807d" not in mem.read_text():
        import pytest
        pytest.skip("fixture pair not present in this checkout")
    body = GOOD.replace("- **Skills:** none.",
                        "- **Skills:** none.\n"
                        "- **Memory written:** `feedback_slurm_shared_qos_mem_inflates_cpus`", 1)
    log = _write(tmp_path, "20260807d_Real.md", body)
    monkeypatch.setattr(sys, "argv", ["check_log_conformance.py", "--dir", str(log.parent)])
    rc = clc.main()
    out = capsys.readouterr().out
    assert rc == 0 and "[L7]" not in out, f"a closed pair must be silent: {out}"


# --------------------------------------------------------------------------
# check_rag_index_committed — the COMMITTED index vs the COMMITTED counts
# --------------------------------------------------------------------------
# Lives here rather than in its own file because it shares the "read from git,
# not from disk" discipline: on disk the rebuild is always present, which is
# exactly why the 1374-expected / 1314-actual mismatch was invisible for a week.

def test_rag_index_checker_passes_on_current_head():
    """HEAD must be self-consistent. If this fails, an index/counts pair is out of sync."""
    import subprocess
    r = subprocess.run([sys.executable, str(clc.REPO / "tools/check_rag_index_committed.py")],
                       capture_output=True, text=True, cwd=clc.REPO)
    assert r.returncode == 0, f"HEAD has a RAG index/counts mismatch:\n{r.stdout}\n{r.stderr}"


def test_rag_index_checker_CATCHES_the_historical_bug():
    """The check must FAIL on the real defect, or it is decoration.

    932498d9 is the last commit before the rebuild landed: milestones.json claimed
    documents=1374 while the committed pflotran index held 1314 with zero curated chunks.
    """
    import subprocess
    probe = subprocess.run(["git", "cat-file", "-e", "932498d9^{commit}"],
                           capture_output=True, cwd=clc.REPO)
    if probe.returncode != 0:
        import pytest
        pytest.skip("reference commit 932498d9 not present in this checkout")
    r = subprocess.run([sys.executable, str(clc.REPO / "tools/check_rag_index_committed.py"),
                        "--rev", "932498d9"], capture_output=True, text=True, cwd=clc.REPO)
    assert r.returncode == 2, f"must ERROR on the known-bad revision, got {r.returncode}:\n{r.stdout}"
    assert "1374" in r.stdout and "1314" in r.stdout, r.stdout
    assert "pflotran-157a26f7" in r.stdout, r.stdout


# --------------------------------------------------------------------------
# L7 — two logs may not share a stem. Added 2026-09-22, the day it happened.
# --------------------------------------------------------------------------

def test_L7_rejects_two_logs_sharing_a_stem(tmp_path):
    """The failure this rule was written from, reproduced.

    Two sessions wrote a handoff on the same day, three minutes apart. Neither could see the
    other's uncommitted file, so both took `b`, and once both were committed the stem `20260922b`
    named two different logs -- with the session snapshot resolving it to whichever it found
    first. A stem is a citation, so it has to name one file.
    """
    a = _write(tmp_path, "20260801b_First_Log.md", GOOD)
    b = _write(tmp_path, "20260801b_Second_Log.md", GOOD)
    assert "L7" in _codes(clc.check_file(a), "error")
    assert "L7" in _codes(clc.check_file(b), "error")


def test_L7_names_the_NEXT_FREE_letter_so_the_fix_is_obvious(tmp_path):
    """A refusal that does not say what to rename to invites a second collision."""
    _write(tmp_path, "20260801a_Taken.md", GOOD)
    _write(tmp_path, "20260801b_First_Log.md", GOOD)
    b = _write(tmp_path, "20260801b_Second_Log.md", GOOD)
    msg = [f.msg for f in clc.check_file(b) if f.code == "L7"][0]
    assert "20260801c" in msg, msg
    assert "20260801b_First_Log.md" in msg, "the message must name the other file"


def test_L7_is_silent_when_every_stem_is_unique(tmp_path):
    """The ordinary case: a directory of distinct letters must stay clean."""
    for name in ("20260801a_One.md", "20260801b_Two.md", "20260801c_Three.md"):
        p = _write(tmp_path, name, GOOD)
    assert _codes(clc.check_file(p)) == []


def test_L7_respects_the_z_overflow_when_suggesting_a_letter(tmp_path):
    """Past z the convention is za, zb, ... and the suggestion must follow it, not restart at a."""
    for ch in "abcdefghijklmnopqrstuvwxy":
        _write(tmp_path, "20260801%s_Log%s.md" % (ch, ch.upper()), GOOD)
    _write(tmp_path, "20260801z_LogZ.md", GOOD)
    dup = _write(tmp_path, "20260801z_Another.md", GOOD)
    msg = [f.msg for f in clc.check_file(dup) if f.code == "L7"][0]
    assert "20260801za" in msg, msg


# L7 — a memory written by MORE THAN ONE log (2026-10-01)
# --------------------------------------------------------------------------
# Checked against the REAL log and the REAL memory, in place. Two earlier attempts at this
# were wrong and are recorded so they are not repeated: a synthetic bucket needed `clc.REPO`
# repointed at a temp tree, which also moves `skills_dir` and the git cwd -- a wide change for
# a narrow test; and a tmp fixture log cannot work here at all, because pytest's tmp_path is
# INSIDE this repo, so its repo-relative path is `tmp/pytest/.../memory/<stream>/<file>` and no
# real `**Source:**` line can ever match that. The checker is run from where it really runs.


def test_L7_closes_the_pair_for_the_SECOND_author_of_a_memory():
    """`reference_chroma_sqlite_read_churn` is created by `20260929c` and extended by
    `20260930k`, and cites both with full repo-relative paths. L7 read only the FIRST
    `**Source:**` line and compared the BASENAME, so the second author was reported
    half-connected. Both real logs must now pass.
    """
    mem = clc.REPO / ".claude_memory" / "reference_chroma_sqlite_read_churn.md"
    if not mem.exists():
        pytest.skip("the real multi-source memory is not present in this checkout")
    # The logs are DISCOVERED from the memory's own Source lines, never listed by name: this test
    # ships, and a log's filename can carry the name of a private downstream repository, which
    # the sync legs' private-destination gate refuses to publish.
    sources = [line for line in mem.read_text().splitlines() if line.startswith("**Source:**")]
    logs = [clc.REPO / rel for line in sources
            for rel in re.findall(r"`(memory/dev_logs[^`]*\.md)`", line)]
    if len(logs) < 2 or not all(p.exists() for p in logs):
        pytest.skip("the real multi-source pair is not present in this checkout")

    for log in logs:
        findings = [f for f in clc.check_file(log) if f.code == "L7"]
        assert not findings, f"{log.name}: {[f.msg for f in findings]}"


@pytest.mark.parametrize("path, gated", [
    ("memory/dev_logs_adapterkit/20261015a_EcoSIM_KB_Reanchor.md", True),
    ("memory/ana_logs/20261015a_Some_Analysis.md", True),
    # Workflow B audit reports: filed under a dev-log tree by the codebase-wiki contract
    ("memory/dev_logs_adapterkit/ecosim_wiki_audit_cb243228/01_photosynthesis.md", False),
    ("memory/dev_logs/fates_wiki_audit_e85d997/02_architecture.md", False),
    # a folder that merely mentions audits is NOT exempt, nor is an audit-named FILE
    ("memory/dev_logs_adapterkit/wiki_audit_notes/01_x.md", True),
    ("memory/dev_logs_adapterkit/ecosim_wiki_audit_cb243228.md", True),
    ("memory/dev_logs_adapterkit/README.md", False),
    ("use_cases/X/memory/logs/20261015a_x.md", False),
])
def test_staged_gate_exempts_only_wiki_audit_folders(path, gated):
    """The exemption is a FOLDER named <model>_wiki_audit_<hex commit>, nothing broader: a looser
    match would let an ordinary dev log escape the gate by its folder name."""
    assert clc._is_staged_log_path(Path(path)) is gated
