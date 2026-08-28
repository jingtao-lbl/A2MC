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

BODY = """
The sensitivity screen is discussed here. A model-evolution appendix follows at the end.
The next-round plan is in the final section.

## Open questions this round could not settle

| # | Question | What would settle it | What it blocks |
|---|---|---|---|
| 1 | is the bottleneck real | site seedling density | whether R10 widens the levers |

## Skills and memory invoked

- **Skills:** none
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
    ("sensitivity", "sensitivity"),
    ("model-evolution", "model-evolution"),
    ("next-round", "next-round"),
    ("Open questions", "open-questions"),
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
