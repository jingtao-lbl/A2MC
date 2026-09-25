"""A SHIPPED copy of the framework cannot satisfy every registry check, and that is not drift.

WHY. `tools/check_skill_registry.py` runs in the development repo and in every tree a sync leg
produces from it. The sync strips every shipped skill's `## Changelog`, removes the
`visibility: private` skills, and ships no case study or internal `docs/NN_` plan, so several
problem classes are GUARANTEED in a destination, and the largest of them is the checker requiring
the `## Changelog` section the sync itself strips. A destination whose project hook chains the
framework's therefore cannot commit a skill file at all without `--no-verify`, which is what makes
this a correctness property and not a tidiness one.

STRICT IS THE DEFAULT, and that is the load-bearing half. Leniency is granted only to a tree a sync
leg has POSITIVELY MARKED with `.a2mc-downstream`. An earlier version inferred the mode from the
ABSENCE of `memory/dev_logs*/`, which softens every tree that merely looks like a copy -- a partial
clone, a worktree checked out without that directory, a future branch before its first log. The
development repo has to fail loudly (PI, 2026-09-24), so a tree must earn leniency rather than fall
into it.

The counts behind that, and why the split falls where it does, are in
`memory/dev_logs_adapterkit/20260924y_A_Shipped_Copy_Cannot_Satisfy_Every_Registry_Check.md`.

The CONTROLS are what make this a check rather than an off switch:

  * a real DRIFT still fails in a filtered tree, so the check keeps teeth where it matters;
  * nothing softens in the development repo;
  * MODES MISSING stays hard, because it is about `skills_catalog.md`, which always ships --
    unlike MODES DRIFT, which is about a `CLAUDE.md` a destination may own;
  * every softened label is asserted against the labels the checker ACTUALLY emits, because a
    renamed label would silently stop matching and quietly re-block the destination
    ([[feedback_exact_strings_are_contracts]]).

Author: Jing Tao with Claude on Perlmutter.
"""
from __future__ import annotations

import importlib.util
import re
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
TOOL = REPO / "tools" / "check_skill_registry.py"


def _mod():
    spec = importlib.util.spec_from_file_location("_csr", TOOL)
    m = importlib.util.module_from_spec(spec)
    sys.modules["_csr"] = m
    spec.loader.exec_module(m)
    return m


@pytest.fixture(scope="module")
def csr():
    if not TOOL.is_file():
        pytest.skip("check_skill_registry.py is not present in this clone")
    return _mod()


# One representative problem string per class, spelled exactly as the checker emits it.
HARD = [
    "DRIFT: 'plotting' on disk but missing from the README 'Current skills' table",
    "FRONTMATTER: 'x' SKILL.md missing `visibility:`",
    "FRONTMATTER-YAML: 'x' frontmatter is not valid YAML",
    "MARKER: AGENTS.md:12 inline '<!-- private -->'",
    "GLOBAL-SKILL-REF: 'x' references `y`, which exists only at user level",
    "PHASE-SECTIONS: cannot import PhaseLogger to compare",
    "MODES MISSING: docs/a2mc_reference/skills_catalog.md entry 'x' has no '- **Modes:**' line",
    "NAME: 'x' frontmatter name does not match its dir",
    # Only ever raised while checking STRICT, so it can never be softened by construction -- but it
    # is listed here so the classification is a recorded decision rather than an omission.
    "MARKER-CONTRADICTION: this tree has `.a2mc-downstream` AND `memory/dev_logs*/`",
]
SOFT = [
    "CHANGELOG: 'plotting' SKILL.md has no `## Changelog` section",
    "CHANGELOG-LAST: 'x' SKILL.md has 1 section(s) after the changelog",
    "DEAD-REF: 'onboard-case' cites `use_cases/ELM-FATES_Kougarok/` which does not exist in the repo",
    "DEAD-SKILL-REF: 'curate-knowledge' references skill `log` which has no dir",
    "RECIPROCITY: 'plotting' declares 'build-surrogate' reciprocal but no such skill exists",
    "MODES DRIFT: CLAUDE.md marks 'compare-calibration-rounds' as FATES",
]


# ---- the partition ------------------------------------------------------------------------------
def test_the_development_repo_is_strict(csr):
    """No marker here, so nothing may soften -- and the marker must not be committable either."""
    assert csr.is_filtered_tree() is False
    assert not (REPO / csr.DOWNSTREAM_MARKER).exists(), "the downstream marker is in the SOURCE repo"
    assert csr.DOWNSTREAM_MARKER in (REPO / ".gitignore").read_text(), (
        "the downstream marker is not gitignored here, so it could be committed into the source")


def test_nothing_softens_outside_a_filtered_tree(csr):
    hard, soft = csr.partition(HARD + SOFT, filtered=False)
    assert soft == []
    assert len(hard) == len(HARD) + len(SOFT)


def test_the_expected_classes_soften_in_a_shipped_copy(csr):
    hard, soft = csr.partition(HARD + SOFT, filtered=True)
    assert sorted(soft) == sorted(SOFT), "a class softened or failed to soften unexpectedly"
    assert sorted(hard) == sorted(HARD)


# ---- controls -----------------------------------------------------------------------------------
def test_CONTROL_real_drift_still_blocks_in_a_shipped_copy(csr):
    """The whole point: a filtered tree is still checked for what it DOES carry."""
    hard, _ = csr.partition([HARD[0]], filtered=True)
    assert hard == [HARD[0]], "DRIFT softened, which would make this an off switch"


def test_CONTROL_modes_missing_stays_hard_because_the_catalog_always_ships(csr):
    """MODES MISSING is about skills_catalog.md, which is on every leg's INCLUDE list.
    MODES DRIFT is about a CLAUDE.md a destination may own. The prefix is deliberately
    'MODES DRIFT' and not 'MODES' for exactly this reason."""
    missing = [p for p in HARD if p.startswith("MODES MISSING")]
    hard, soft = csr.partition(missing, filtered=True)
    assert hard == missing and soft == []


def test_CONTROL_every_softened_label_is_one_the_checker_emits(csr):
    """A renamed label would silently stop matching and quietly re-block the destination."""
    src = TOOL.read_text()
    emitted = set(re.findall(r'f?"([A-Z][A-Z -]*):', src))
    for prefix in csr.FILTERED_SOFT:
        assert any(lbl == prefix or lbl.startswith(prefix) for lbl in emitted), (
            f"FILTERED_SOFT names {prefix!r} but the checker emits no such label. "
            f"Emitted: {sorted(emitted)}")


def test_CONTROL_every_emitted_label_is_classified_on_purpose(csr):
    """No label may be new and unconsidered: either it softens in a shipped copy or it does not,
    and this test is where that decision is recorded."""
    src = TOOL.read_text()
    emitted = {l for l in re.findall(r'f?"([A-Z][A-Z -]*):', src) if l != "ERROR"}
    known = {p.split(":", 1)[0] for p in HARD + SOFT}
    assert emitted <= known, (
        f"unclassified problem label(s): {sorted(emitted - known)}. Add a representative string to "
        f"HARD or SOFT above, which is the decision about whether a shipped copy can satisfy it.")


def test_CONTROL_an_unmarked_tree_is_STRICT_however_much_it_looks_like_a_copy(csr, tmp_path, monkeypatch):
    """The inversion. A bare tree has no dev logs and is still strict, because it was never marked.
    This is the case the previous implementation got wrong."""
    monkeypatch.setattr(csr, "ROOT", tmp_path)
    assert not any(tmp_path.glob("memory/dev_logs*")), "fixture precondition"
    filtered, complaint = csr.downstream_state()
    assert filtered is False, "an unmarked tree softened; leniency must be earned, not inferred"
    assert complaint is None


def test_a_marked_tree_is_downstream(csr, tmp_path, monkeypatch):
    monkeypatch.setattr(csr, "ROOT", tmp_path)
    (tmp_path / csr.DOWNSTREAM_MARKER).write_text("written by a sync leg\n")
    filtered, complaint = csr.downstream_state()
    assert filtered is True and complaint is None


def test_CONTROL_a_marker_beside_dev_logs_is_a_mistake_and_checks_strict(csr, tmp_path, monkeypatch):
    """Nothing copies the marker upstream, so the two together mean it arrived by hand."""
    monkeypatch.setattr(csr, "ROOT", tmp_path)
    (tmp_path / csr.DOWNSTREAM_MARKER).write_text("stray\n")
    (tmp_path / "memory" / "dev_logs_adapterkit").mkdir(parents=True)
    filtered, complaint = csr.downstream_state()
    assert filtered is False, "a development tree softened because a stray marker was present"
    assert complaint and complaint.startswith("MARKER-CONTRADICTION")


def test_CONTROL_every_sync_leg_writes_the_marker(csr):
    """The mode only reaches a destination if a leg puts it there.

    DISCOVERED, never named: a leg is named for its destination and this file ships, so a
    hand-list would publish a private destination's name."""
    legs = sorted((REPO / "scripts").glob("sync_*.sh"))
    if not legs:
        pytest.skip("no sync leg in this clone (a downstream copy does not carry them)")
    for leg in legs:
        assert csr.DOWNSTREAM_MARKER in leg.read_text(), (
            f"{leg.name} does not write {csr.DOWNSTREAM_MARKER}, so its destination would check "
            f"STRICT and block on content it cannot carry")
