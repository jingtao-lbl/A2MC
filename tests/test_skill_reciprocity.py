"""Tests for `tools/check_skill_registry.py::reciprocity_check`.

A skill may declare its cross-reference list RECIPROCAL: every skill it names must name it back.
The check exists because `plotting` claimed `phase0-design`, `phase3-diagnosis` and
`scientific-analysis` applied its conventions while none of the three mentioned it — a
one-directional link, invisible from the side that mattered (dev log 20260816c).

Every test here asserts a way the check must FAIL. A reciprocity check that only ever passes is
worth nothing (`feedback_a_check_that_cannot_fail`), and one of these caught exactly that during
development: intersecting the parsed tokens with the known skill set made the "declared skill does
not exist" branch unreachable.

Author: Jing Tao with Claude
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

from tools.check_skill_registry import (  # noqa: E402
    RECIPROCAL_MARK, reciprocity_check, skills_on_disk,
)


@pytest.fixture(scope="module")
def disk():
    d = skills_on_disk()
    assert d, "no skills on disk"
    return d


def _declarers(disk):
    return [n for n, t in disk.items() if RECIPROCAL_MARK in t]


def test_repo_is_currently_reciprocal(disk):
    """The live repo must satisfy the invariant — this is the regression guard."""
    assert reciprocity_check(disk) == []


def test_at_least_one_skill_declares_reciprocity(disk):
    """If nothing declares it, the check iterates over nothing and passes vacuously."""
    assert _declarers(disk), f"no skill declares {RECIPROCAL_MARK}"


def test_missing_back_pointer_fails(disk):
    """The core case: a named skill stops naming the declarer back."""
    d = dict(disk)
    d["phase3-diagnosis"] = d["phase3-diagnosis"].replace("`plotting`", "the plot tool")
    out = reciprocity_check(d)
    assert any("never names" in p and "phase3-diagnosis" in p for p in out), out


def test_declared_skill_that_does_not_exist_fails(disk):
    """A typo'd or renamed skill in the list must be caught.

    REGRESSION: the first implementation intersected the parsed tokens with the known skill set,
    which discarded a nonexistent name before this branch could see it — so the branch was dead
    code and this case produced no problem at all.
    """
    d = dict(disk)
    d.pop("phase5-testing")
    out = reciprocity_check(d)
    assert any("no such skill" in p for p in out), out


def test_reworded_marker_does_not_silently_pass(disk):
    """The anti-silent-pass guard: renaming the marker must fail loudly, not iterate over nothing."""
    d = {k: v.replace(RECIPROCAL_MARK, "**Related figure skills**") for k, v in disk.items()}
    out = reciprocity_check(d)
    assert any("no skill declares" in p for p in out), out


def test_names_moved_out_of_the_bullet_fails(disk):
    """The checker reads the BULLET, not the section — so a list that drifts out of it must fail
    rather than quietly shrink the enforced set to nothing."""
    d = dict(disk)
    # Strip from the start of the name list to the END OF THE BULLET, rather than to a named skill.
    # Pinning the regex to the last name in the list (it was `compare-calibration-rounds`) made this
    # negative control fail open the moment a name was appended: the strip stopped short, one name
    # survived in the bullet, and the checker correctly reported nothing. A test whose negative
    # control silently stops being negative is worse than no test.
    d["plotting"] = re.sub(r"\n  \*\*All seven phase skills\*\*.*?(?=\n\n|\n- \*\*)",
                           "", d["plotting"], flags=re.S)
    assert "compare-calibration-rounds" not in d["plotting"], (
        "the strip did not remove the name list, so this control is no longer negative")
    out = reciprocity_check(d)
    assert any("names no skills" in p for p in out), out


def test_paths_and_code_identifiers_are_not_mistaken_for_skills(disk):
    """A backticked path or dotted identifier in the bullet must not be read as a skill name."""
    d = dict(disk)
    d["plotting"] = d["plotting"].replace(
        "`compare-calibration-rounds`.",
        "`compare-calibration-rounds`. See `tools/some_helper.py` and `models.ecosim.backend`.")
    assert reciprocity_check(d) == []


def test_prose_mentioning_the_marker_is_not_a_declaration(disk):
    """A DECLARATION is a bullet that BEGINS with the marker, not any line quoting it.

    REGRESSION (2026-08-16): the Changelog entry describing this very mechanism quotes the marker
    and names `markdown-to-pdf` / `write-report` in the same sentence. Unanchored, that sentence
    parsed as a second declaration and produced two false RECIPROCITY problems — a checker tripped
    by the documentation of itself.
    """
    d = dict(disk)
    d["plotting"] += (
        "\n\n- 2026-01-01: a changelog line quoting **Reciprocal skills** and naming "
        "`markdown-to-pdf` and `write-report` in passing.\n")
    assert reciprocity_check(d) == []


def test_back_pointer_accepts_a_bare_backticked_name(tmp_path):
    """The back-check must not require a specific PROSE form.

    Found 2026-08-17, the first time a SECOND skill used the reciprocity mechanism. The check was
    built on `cited_skills()` / `_SKILLREF`, which matches only "the `x` skill" / "skills `x`", so
    a reciprocal bullet written as ``- **Reciprocal skills** — `write-report`: ...`` was invisible
    and BOTH halves of a correctly-paired declaration reported as one-directional.

    Same defect as Defect 1 in `20260816d` (reusing `_SKILLREF` where a bare backticked list is
    what appears), fixed there in the declaration parser and missed here in the back-check.
    """
    from tools.check_skill_registry import reciprocity_check
    mark = "**Reciprocal skills**"
    disk = {
        "alpha": f"# alpha\n\n- {mark} — `beta`: borrows its rigor layer.\n",
        # bare backticked name, NOT the prose "the `alpha` skill" form
        "beta":  f"# beta\n\n- {mark} — `alpha`: points back here for non-journal work.\n",
    }
    assert reciprocity_check(disk) == [], "a bare backticked back-pointer must satisfy the check"


def test_bare_name_widening_did_not_disable_the_check(tmp_path):
    """Widening a check is how it quietly stops being able to fail — assert it still can."""
    from tools.check_skill_registry import reciprocity_check
    mark = "**Reciprocal skills**"
    disk = {
        "alpha": f"# alpha\n\n- {mark} — `beta`: borrows its rigor layer.\n",
        "beta":  "# beta\n\nNo mention of the declarer at all.\n",
    }
    probs = reciprocity_check(disk)
    assert any("never names 'alpha' back" in p for p in probs), probs
