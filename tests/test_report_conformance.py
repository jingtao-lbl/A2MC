"""`tools/check_report_conformance.py` — every rule fires, and a conforming report is clean.

The checker landed 2026-08-24 with no tests. This file adds them, and the gap that motivated it is
worth stating: while adding R8's open-questions rule I "verified" it against the real R3 round
summary, which reports **clean** — not because the report has an open-questions list (it has none)
but because it is dated 20260823 and every new rule is DATE-SCOPED from 20260824. A rule verified
against an out-of-scope file has not been verified at all. `test_new_rules_are_date_scoped` and
`test_an_in_scope_report_IS_checked` exist so that trap is mechanical rather than remembered.

Written failure-first (`feedback_a_check_that_cannot_fail`): each test names the mutation caught.
"""
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
CHECKER = ROOT / "tools" / "check_report_conformance.py"

HEADER = """# R9 Round Summary

**Status:** Final
**Date:** August 25, 2026
**Author:** Jing Tao with A2MC

## Outline
1. the arc
"""

TABLES = """
| Cycle | Question and its bar | Parameters varied | Result per target | Verdict |
|---|---|---|---|---|
| 1 | is X the cause | CNRT 0.008-0.02 | best 340 gC | REFUTED |

| Parameter | What it is | Source location | Mechanism | Baseline | Range | Role |
|---|---|---|---|---|---|---|
| CNRT | root N:C | PlantBGCPars.F90:1 | root growth cost | 0.016 | 0.008-0.02 | confirmed |
"""

# The five round-level topics now need SECTIONS, not passing mentions. Before 2026-09-05 this
# fixture carried sensitivity, model evolution and the next-round plan as prose only and reported
# CLEAN, which is exactly the defect the tightening fixed: see `test_prose_mentions_are_not_sections`.
BODY = """
## Sensitivity

The sensitivity screen is discussed here.

## The mechanism the round established

Iron tracks its supply because its sink is saturated at 99.50 percent
(`memory/logs/20260101a_diagnosis.md`, `savannah_river.dat:2649`).

## The next-round plan

Widen the levers.

**Model evolution appendix.** No model source change occurred.

## Open questions this round could not settle

| # | Question | What would settle it | What it blocks |
|---|---|---|---|
| 1 | is the bottleneck real | site seedling density | whether R10 widens the levers |

## Skills and memory invoked

- **Skills:** `summarize-calibration-round`, `compare-calibration-rounds`, `write-report`, `calibration-goal`, `calibration-discipline`
"""


def write(tmp_path, body=None, date="20260825", letter="a", name="R9_round_summary.md"):
    d = tmp_path / "use_cases" / "X" / "reports" / f"{date}{letter}_R9_ROUND_SUMMARY"
    d.mkdir(parents=True, exist_ok=True)
    p = d / name
    p.write_text(HEADER + TABLES + (BODY if body is None else body))
    return p


def run(path):
    r = subprocess.run([sys.executable, str(CHECKER), str(path)],
                       capture_output=True, text=True, cwd=ROOT)
    return r.returncode, r.stdout + r.stderr


def test_a_conforming_round_report_is_clean(tmp_path):
    code, out = run(write(tmp_path))
    assert code == 0, out


# ------------------------------------------------------------------ R8: ROUND-report content

@pytest.mark.parametrize("drop,needle", [
    ("| Cycle |", "cycle ledger"),
    ("| Parameter |", "parameter reference"),
    ("## Sensitivity", "sensitivity"),
    ("Model evolution appendix", "model-evolution"),
    ("## The next-round plan", "next-round"),
    ("## Open questions", "open-questions"),
    ("## The mechanism the round established", "mechanism section"),
])
def test_each_required_round_element_is_missed_when_absent(tmp_path, drop, needle):
    """Remove one required element; the matching R8 warning must appear."""
    full = HEADER + TABLES + BODY
    mutated = "\n".join(l for l in full.split("\n") if drop.lower() not in l.lower())
    d = tmp_path / "use_cases" / "X" / "reports" / "20260825a_R9_ROUND_SUMMARY"
    d.mkdir(parents=True, exist_ok=True)
    p = d / "R9_round_summary.md"
    p.write_text(mutated)
    code, out = run(p)
    assert needle in out.lower(), f"dropping {drop!r} did not produce a {needle!r} finding:\n{out}"


# ------------------------------------------------------------------ the date scope

def test_new_rules_are_date_scoped(tmp_path):
    """REGRESSION. Retro-failing ~30 existing reports would block unrelated work and teach people
    to pass --no-verify. A report dated before the cut-off must NOT be judged by the new rules."""
    body = BODY.replace("## Open questions this round could not settle", "## Something else")
    p = write(tmp_path, body=body, date="20260801")
    code, out = run(p)
    assert "open-questions" not in out.lower(), out


def test_an_in_scope_report_IS_checked(tmp_path):
    """The other half, and the one that matters: date-scoping must not swallow the rule entirely.

    Without this pair, a rule can look verified while every file it was tried on was out of scope.
    """
    body = BODY.replace("## Open questions this round could not settle", "## Something else")
    code, out = run(write(tmp_path, body=body, date="20260825"))
    assert "open-questions" in out.lower(), out


# ------------------------------------------------------------------ the other rules

def test_a_wrong_author_line_is_an_error(tmp_path):
    p = write(tmp_path)
    p.write_text(p.read_text().replace("Jing Tao with A2MC", "Jing Tao with Claude"))
    code, out = run(p)
    assert code == 2 and "author" in out.lower(), out


def test_a_glossary_block_is_an_error(tmp_path):
    p = write(tmp_path)
    p.write_text(p.read_text().replace("## Outline", "## Reader's key\n\nterm: meaning\n\n## Outline"))
    code, out = run(p)
    assert code == 2, out


def test_an_em_dash_in_prose_is_an_error(tmp_path):
    p = write(tmp_path)
    p.write_text(p.read_text().replace("The sensitivity screen is discussed here.",
                                       "The sensitivity screen — discussed here."))
    code, out = run(p)
    assert code == 2 and "em dash" in out.lower(), out


def test_a_missing_capability_section_is_an_error(tmp_path):
    p = write(tmp_path)
    p.write_text(p.read_text().replace("## Skills and memory invoked", "## Something Else"))
    code, out = run(p)
    assert code == 2 and "skills and memory" in out.lower(), out


def test_a_non_empty_figure_alt_text_is_an_error(tmp_path):
    p = write(tmp_path)
    p.write_text(p.read_text() + "\n![Figure 1](fig.png)\n")
    code, out = run(p)
    assert code == 2, out


def test_a_report_folder_without_its_letter_is_rejected(tmp_path):
    d = tmp_path / "use_cases" / "X" / "reports" / "20260825_R9_ROUND_SUMMARY"   # no letter
    d.mkdir(parents=True, exist_ok=True)
    p = d / "R9_round_summary.md"
    p.write_text(HEADER + TABLES + BODY)
    code, out = run(p)
    assert code == 2 and "letter" in out.lower(), out


def test_an_empty_selection_is_an_error_not_a_pass():
    """Anti-silent-pass: 'nothing matched' must never report success."""
    code, _ = run(ROOT / "tools" / "definitely_not_a_report.md")
    assert code == 2


# ------------------------------ 2026-09-05: the four word-match checks, and the mechanism section

PROSE_ONLY = """
We discuss sensitivity at length, and the next-round plan, and model evolution,
and the open-question list, entirely in prose, under no heading of their own.
The mechanism is mentioned too.

## Skills and memory invoked
- **Skills:** none
"""


def test_prose_mentions_are_not_sections(tmp_path):
    """THE REGRESSION THIS FILE EXISTS FOR.

    Until 2026-09-05 the round checks were bare substring matches, so a report that merely used the
    words `sensitivit`, `next-round`, `model evolution` and `open-question` anywhere in prose passed
    all four. They were checks that could not fail. Each must now name its missing SECTION.
    """
    code, out = run(write(tmp_path, body=PROSE_ONLY))
    low = out.lower()
    for needle in ("sensitivity section", "model-evolution appendix",
                   "next-round plan section", "open-questions", "mechanism section"):
        assert needle in low, f"{needle!r} not reported for a prose-only report:\n{out}"
    assert code != 0


def test_a_mechanism_section_that_cites_nothing_is_reported(tmp_path):
    """A mechanism with no `file:line`, artifact path or named log is an assertion.

    Mutation caught: strip the citations out of the mechanism section and leave the heading.
    """
    body = BODY.replace("(`memory/logs/20260101a_diagnosis.md`, `savannah_river.dat:2649`)", "")
    code, out = run(write(tmp_path, body=body))
    assert "cites nothing checkable" in out.lower(), out


def test_an_open_questions_section_without_its_table_is_reported(tmp_path):
    """The skill specifies the columns; a heading alone lets a musing pass as a task."""
    body = "\n".join(l for l in BODY.split("\n") if not l.startswith("| "))
    code, out = run(write(tmp_path, body=body))
    assert "open-questions section with no table" in out.lower(), out


# ------------------------------ 2026-09-05: WHICH file the round rules apply to

def test_a_companion_doc_in_a_round_folder_is_not_round_checked(tmp_path):
    """Routing was by FOLDER, so every .md beside a round report was treated as one.

    Measured: a cross-round ledger and a holdout analysis in one round-summary folder drew 6 and 7
    warnings each for lacking sections they were never meant to carry. A noisy gate gets bypassed.
    """
    body = "\n## Skills and memory invoked\n- **Skills:** none\n"
    d = tmp_path / "use_cases" / "X" / "reports" / "20260825a_R9_ROUND_SUMMARY"
    d.mkdir(parents=True, exist_ok=True)
    p = d / "R9_holdout_validation.md"
    p.write_text(HEADER.replace("# R9 Round Summary", "# R9 holdout validation") + body)
    code, out = run(p)
    assert "cycle ledger" not in out.lower(), out
    assert "next-round" not in out.lower(), out


def test_a_round_report_named_anything_is_still_checked_via_its_title(tmp_path):
    """The filename is not the only handle: an H1 saying "round report" routes it too.

    Mutation caught: name a round report `analysis.md` to escape every round-level rule.
    """
    d = tmp_path / "use_cases" / "X" / "reports" / "20260825a_whatever"
    d.mkdir(parents=True, exist_ok=True)
    p = d / "analysis.md"
    p.write_text(HEADER.replace("# R9 Round Summary", "# R9: the round report") + PROSE_ONLY)
    code, out = run(p)
    assert "mechanism section" in out.lower(), out


# ------------------------------ 2026-09-05: the four skills a round report is the OUTPUT of

REQUIRED_SKILLS = ("summarize-calibration-round", "compare-calibration-rounds",
                   "write-report", "calibration-goal", "calibration-discipline")
SKILLS_OK = ("\n### Skills and memory invoked\n- **Skills:** "
             + ", ".join(f"`{k}`" for k in REQUIRED_SKILLS) + "\n")


@pytest.mark.parametrize("dropped", REQUIRED_SKILLS)
def test_a_round_report_missing_a_required_skill_is_an_ERROR(tmp_path, dropped):
    """Not a warning: the remedy is to run the skill and redo the report.

    Mutation caught: drop exactly one of the four names from the Skills line. The base fixture
    names all four, so `test_a_conforming_round_report_is_clean` is the positive control.
    """
    body = BODY.replace(f"`{dropped}`, ", "").replace(f", `{dropped}`", "")
    assert f"`{dropped}`" not in body, "the mutation did not remove the name"
    code, out = run(write(tmp_path, body=body))
    assert dropped in out, out
    assert "error" in out.lower(), out
    assert code != 0


def test_an_unbackticked_skill_name_does_not_count(tmp_path):
    """`check_skill_claims.py` reads BACKTICKED tokens, so the two checks must agree on the form.

    Mutation caught: name the skill in prose, without backticks.
    """
    body = BODY.replace("`calibration-goal`", "calibration-goal")
    code, out = run(write(tmp_path, body=body))
    assert "calibration-goal" in out and "error" in out.lower(), out
