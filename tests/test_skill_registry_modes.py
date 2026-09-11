"""Tests for `tools/check_skill_registry.py::modes_check`.

Each of the four registry surfaces carries a MODES cell beside every skill, mirroring that skill's
`modes:` frontmatter. Until 2026-09-05 the registry check compared NAMES and COUNTS and never read
that cell, so the cell could say anything and no run would notice.

The measured cost: `summarize-calibration-round` and `compare-calibration-rounds` went
`requires_fates: true` -> `false` on 2026-08-24 precisely so adapter models could use them, and for
twelve days all four surfaces still said FATES. The documentation told an EcoSIM or PFLOTRAN user
that the standardized round close did not apply to them, and `check_skill_registry.py` reported
clean on every run in between.

Every test here asserts a way the check must FAIL (`feedback_a_check_that_cannot_fail`), plus the
one false-positive that showed up the moment it was first run: a catalog line reading
"`any` — ATS-specific, no FATES dependency" names FATES in its commentary while asserting the
opposite, and a bare word search over the whole cell reported five drifts that were not there.

Author: Jing Tao with Claude
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

from tools.check_skill_registry import (  # noqa: E402
    _fates_from_cell, _fates_on_disk, modes_check, skills_on_disk,
)


# ------------------------------------------------------------------ the cell reader

@pytest.mark.parametrize("cell,expected", [
    ("any", False),
    ("any (HPC)", False),
    ("EcoSIM", False),
    ("**FATES**", True),
    ("FATES", True),
    ("`requires_fates: true`", True),
    ("`requires_fates: false`", False),
    # an explicit declaration wins over the word appearing anywhere else in the cell
    ("`requires_fates: false` — generic since 2026-08-24, was FATES-only before", False),
    ("`requires_fates: true` — FATES parameter files + HPC submission", True),
    # THE FALSE POSITIVE: the value says one thing and the commentary names the other
    ("`any` — ATS-specific, no FATES dependency.", False),
    ("`any` — model-agnostic; the worked examples are FATES/Morris.", False),
    ("`any` — model-agnostic; examples are FATES/Kougarok.", False),
])
def test_the_cell_reader_reads_the_value_not_the_commentary(cell, expected):
    assert _fates_from_cell(cell) is expected, cell


# ------------------------------------------------------------------ the disk reader

def test_disk_reader_returns_none_when_the_skill_declares_nothing():
    """A skill with no `requires_fates` is not evidence of `false`; it is unknown, and unknown
    must be skipped rather than compared, or every silent skill becomes a false drift."""
    assert _fates_on_disk("---\nname: x\n---\n\nbody") is None


@pytest.mark.parametrize("value,expected", [("true", True), ("false", False)])
def test_disk_reader_reads_the_frontmatter(value, expected):
    text = f"---\nname: x\nmodes:\n  requires_fates: {value}\n---\n\nbody"
    assert _fates_on_disk(text) is expected


# ------------------------------------------------------------------ the check itself

def test_the_repo_is_currently_clean():
    """The positive control. If this fails, a real surface has drifted."""
    assert modes_check(skills_on_disk()) == []


def test_a_surface_claiming_FATES_for_a_generic_skill_is_caught(tmp_path, monkeypatch):
    """THE REGRESSION THIS FILE EXISTS FOR.

    Mutation caught: mark a `requires_fates: false` skill as FATES in the AGENTS.md table, which is
    exactly the state two skills sat in for twelve days.
    """
    import tools.check_skill_registry as reg
    agents = tmp_path / "AGENTS.md"
    agents.write_text("| `calibration-goal` | **FATES** | drive the loop |\n")
    monkeypatch.setattr(reg, "AGENTS", agents)
    monkeypatch.setattr(reg, "README", tmp_path / "absent-README.md")
    monkeypatch.setattr(reg, "CATALOG", tmp_path / "absent-CATALOG.md")
    monkeypatch.setattr(reg, "ROOT", tmp_path)          # no CLAUDE.md in tmp_path
    problems = reg.modes_check(reg.skills_on_disk())
    assert any("MODES DRIFT" in p and "calibration-goal" in p for p in problems), problems


def test_a_surface_calling_a_FATES_skill_generic_is_caught(tmp_path, monkeypatch):
    """The other direction, which is the one that silently widens a skill's apparent scope."""
    import tools.check_skill_registry as reg
    agents = tmp_path / "AGENTS.md"
    agents.write_text("| `add-fates-parameter` | any | wire a new knob |\n")
    monkeypatch.setattr(reg, "AGENTS", agents)
    monkeypatch.setattr(reg, "README", tmp_path / "absent-README.md")
    monkeypatch.setattr(reg, "CATALOG", tmp_path / "absent-CATALOG.md")
    monkeypatch.setattr(reg, "ROOT", tmp_path)
    problems = reg.modes_check(reg.skills_on_disk())
    assert any("MODES DRIFT" in p and "add-fates-parameter" in p for p in problems), problems


def test_a_catalog_entry_with_no_modes_line_is_caught(tmp_path, monkeypatch):
    """A cell that does not exist cannot be checked, and silence must not read as agreement."""
    import tools.check_skill_registry as reg
    cat = tmp_path / "skills_catalog.md"
    cat.write_text("### `calibration-goal`\n- **Purpose:** drive the loop.\n")
    monkeypatch.setattr(reg, "CATALOG", cat)
    monkeypatch.setattr(reg, "AGENTS", tmp_path / "absent-AGENTS.md")
    monkeypatch.setattr(reg, "README", tmp_path / "absent-README.md")
    monkeypatch.setattr(reg, "ROOT", tmp_path)
    problems = reg.modes_check(reg.skills_on_disk())
    assert any("MODES MISSING" in p and "calibration-goal" in p for p in problems), problems


def test_a_skill_absent_from_a_surface_is_skipped_not_flagged(tmp_path, monkeypatch):
    """Presence is the 4-way parity check's job. Flagging it here too would double-report it."""
    import tools.check_skill_registry as reg
    agents = tmp_path / "AGENTS.md"
    agents.write_text("| `calibration-goal` | any | drive the loop |\n")
    monkeypatch.setattr(reg, "AGENTS", agents)
    monkeypatch.setattr(reg, "README", tmp_path / "absent-README.md")
    monkeypatch.setattr(reg, "CATALOG", tmp_path / "absent-CATALOG.md")
    monkeypatch.setattr(reg, "ROOT", tmp_path)
    assert reg.modes_check(reg.skills_on_disk()) == []
