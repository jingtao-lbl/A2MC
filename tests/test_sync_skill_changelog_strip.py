"""A shipped SKILL.md must carry no development history (PI, 2026-09-14).

A skill's `## Changelog` is a development record -- dated entries naming dev logs, versions, branch
decisions and the defects that prompted each edit. It is the same class of content as
`memory/dev_logs*/` and a `<!-- private -->` block, and it shipped in full: measured before the
strip existed, 11,644 changelog lines across the 46 skills in the public repo.

WHAT THE FIRST VERSION GOT WRONG, and why the tests below look the way they do. The strip truncated
at the `## Changelog` heading and deleted to end of file. Seven skills keep sections AFTER their
changelog, and `phase5-testing` kept phase 5's expected-section line there, so the strip deleted a
line a SHIPPED checker asserts. The unit tests passed: every fixture put the changelog last, which
is exactly the case that cannot fail. Only a staged real sync, whose destination then failed
`check_skill_registry.py`'s PHASE-SECTIONS rule, caught it.

So three properties are pinned, and the third is the one that would have caught that defect:

  * the changelog BODY is gone, and everything above the heading is untouched;
  * the `## Changelog` HEADING survives, because `tools/check_skill_registry.py` ships and requires
    it -- a strip that removed the section outright would make the public repo fail its own checker;
  * NOTHING ELSE is removed: a section after the changelog survives (fixture), and stripping every
    REAL skill preserves each file's other `## ` headings (data-derived).

Skills now also have to keep the changelog LAST (`check_skill_registry.py` CHANGELOG-LAST, and the
`add-skill` / `refine-skill` contracts), so the bounded rule has nothing to trip over in practice.
The bound and the tool's own FATAL verification stay as the backstop for the case where it does.

Author: Jing Tao with Claude.
"""
from __future__ import annotations

import re
import shutil
import subprocess
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
SKILLS = REPO / ".claude" / "skills"
LEGS = ["scripts/sync_adapterkit_to_public.sh", "scripts/sync_adapterkit_forSaleska.sh"]
_START = "strip_skill_changelogs() {"

SKILL_WITH_LOG = """---
name: demo
visibility: public
---

# Demo

Body text the user needs.

## Changelog
- 2026-09-01: **Rewrote step 4** after `20260901a` found the gate could not fail (v2.399).
- 2026-08-02: initial version, distilled from memory/dev_logs_adapterkit/20260802b_Thing.md
"""

# The shape that broke the first implementation: a section BELOW the changelog.
SKILL_WITH_TRAILING_SECTION = SKILL_WITH_LOG + """
## Before you finish

A closing checklist the user needs, and `phase5-testing` keeps its expected-section line here.
"""

SKILL_WITHOUT_LOG = """---
name: plain
visibility: public
---

# Plain

No changelog section at all.
"""

# A changelog entry holding a heading-like line inside a fence: the bound stops early, entries
# survive, and the tool's own verification must catch that rather than shipping them.
SKILL_WITH_FENCED_HEADING = """---
name: fenced
visibility: public
---

# Fenced

Body.

## Changelog
- 2026-09-01: renamed the section, which used to read:
```
## Old Heading
```
- 2026-08-02: initial version
"""


def _extract(leg: Path) -> str:
    lines = leg.read_text().splitlines()
    try:
        start = next(i for i, ln in enumerate(lines) if ln.strip() == _START)
    except StopIteration:  # pragma: no cover - only when the function is removed
        pytest.fail(
            f"strip_skill_changelogs() is gone from {leg.name}. Without it every shipped SKILL.md "
            "carries its development history. Do not delete this test to make it pass."
        )
    end = next(i for i in range(start + 1, len(lines)) if lines[i] == "}")
    return "\n".join(lines[start : end + 1])


def _run(leg_rel: str, root: Path, *, expect_ok: bool = True) -> subprocess.CompletedProcess:
    leg = REPO / leg_rel
    if not leg.is_file():
        pytest.skip(f"{leg_rel} not present in this clone")
    script = root / "harness.sh"
    script.write_text(f"set -e\n{_extract(leg)}\nstrip_skill_changelogs \"{root}\"\n")
    r = subprocess.run(["bash", str(script)], capture_output=True, text=True)
    if expect_ok:
        assert r.returncode == 0, r.stdout + r.stderr
    return r


def _write_skills(root: Path, skills: dict) -> Path:
    for name, body in skills.items():
        d = root / ".claude" / "skills" / name
        d.mkdir(parents=True, exist_ok=True)
        (d / "SKILL.md").write_text(body)
    return root


@pytest.fixture
def dest(tmp_path: Path) -> Path:
    return _write_skills(tmp_path, {"demo": SKILL_WITH_LOG, "plain": SKILL_WITHOUT_LOG,
                                    "trailing": SKILL_WITH_TRAILING_SECTION})


def _text(root: Path, name: str) -> str:
    return (root / ".claude" / "skills" / name / "SKILL.md").read_text()


# --------------------------------------------------------------- the body goes


@pytest.mark.parametrize("leg_rel", LEGS)
def test_the_changelog_body_does_not_ship(leg_rel: str, dest: Path):
    _run(leg_rel, dest)
    text = _text(dest, "demo")
    assert "20260901a" not in text and "v2.399" not in text, text
    assert "dev_logs_adapterkit" not in text, text
    assert not re.search(r"^- 2026-", text, re.M), "a dated changelog entry survived"


@pytest.mark.parametrize("leg_rel", LEGS)
def test_the_whole_section_goes_heading_included(leg_rel: str, dest: Path):
    """PI, 2026-09-15: a changelog is a MAINTAINER's artifact — a public user of the kit never
    writes one. An empty `## Changelog` heading would advertise a record that was withheld and
    invite a section nobody is expected to keep, so the heading goes with the body. The
    `## Changelog` rule in `tools/check_skill_registry.py` is a developer-side rule for THIS repo,
    not a contract the shipped copy has to satisfy."""
    _run(leg_rel, dest)
    text = _text(dest, "demo")
    assert not re.search(r"^## Changelog", text, re.M), "the changelog heading still ships"
    assert "Kept in the A2MC development repository." not in text, "the pointer line still ships"


@pytest.mark.parametrize("leg_rel", LEGS)
def test_everything_above_the_heading_is_untouched(leg_rel: str, dest: Path):
    _run(leg_rel, dest)
    kept = SKILL_WITH_LOG.split("## Changelog")[0]
    assert _text(dest, "demo").startswith(kept), "content above the changelog was altered"


@pytest.mark.parametrize("leg_rel", LEGS)
def test_a_skill_without_a_changelog_is_left_alone(leg_rel: str, dest: Path):
    _run(leg_rel, dest)
    assert _text(dest, "plain") == SKILL_WITHOUT_LOG


# --------------------------------------------------------------- and NOTHING else goes


@pytest.mark.parametrize("leg_rel", LEGS)
def test_a_section_after_the_changelog_survives(leg_rel: str, dest: Path):
    """THE 2026-09-15 DEFECT. Truncating at the heading deleted this section."""
    _run(leg_rel, dest)
    text = _text(dest, "trailing")
    assert "## Before you finish" in text, text
    assert "A closing checklist the user needs" in text, text
    assert not re.search(r"^- 2026-", text, re.M), "the changelog body survived instead"


@pytest.mark.parametrize("leg_rel", LEGS)
def test_stripping_every_real_skill_preserves_its_other_headings(leg_rel: str, tmp_path: Path):
    """Data-derived, over the skills as they actually are -- the check the fixtures could not be."""
    root = tmp_path / "copy"
    (root / ".claude").mkdir(parents=True)
    shutil.copytree(SKILLS, root / ".claude" / "skills")
    # Key on the skill's DIRECTORY name. `p.name` is the literal "SKILL.md" for every match, so a
    # dict keyed on it collapses all 51 skills onto one entry and then reads
    # `.claude/skills/SKILL.md`, which does not exist -- measured 2026-09-15: the test raised
    # FileNotFoundError and compared nothing, while looking like it covered every skill.
    before = {p.parent.name: [ln for ln in p.read_text().splitlines()
                              if ln.startswith("## ") and ln.strip() != "## Changelog"]
              for p in sorted(SKILLS.glob("*/SKILL.md"))}
    assert len(before) > 20, f"only {len(before)} skills enumerated -- the walk went blind"
    _run(leg_rel, root)
    for name, headings in before.items():
        after = [ln for ln in (root / ".claude" / "skills" / name / "SKILL.md").read_text().splitlines()
                 if ln.startswith("## ") and ln.strip() != "## Changelog"]
        assert after == headings, f"{name}: headings changed\n  before={headings}\n  after={after}"


@pytest.mark.parametrize("leg_rel", LEGS)
def test_it_refuses_rather_than_ship_entries_it_could_not_bound(leg_rel: str, tmp_path: Path):
    """If a changelog ever holds a heading-like line in a fence, the bound stops early. The tool's
    own verification must then FAIL the sync instead of shipping the surviving entries."""
    root = _write_skills(tmp_path, {"fenced": SKILL_WITH_FENCED_HEADING})
    r = _run(leg_rel, root, expect_ok=False)
    assert r.returncode != 0, "a strip that left dated entries reported success"
    assert "dated changelog entry survived" in (r.stdout + r.stderr)


@pytest.mark.parametrize("leg_rel", LEGS)
def test_it_reports_how_many_files_it_touched(leg_rel: str, dest: Path):
    """Silence would be indistinguishable from a strip that matched nothing."""
    assert "2 shipped SKILL.md file(s)" in _run(leg_rel, dest).stdout


# --------------------------------------------------------------- the invariants behind the rule


@pytest.mark.parametrize("leg_rel", LEGS)
def test_each_leg_actually_CALLS_the_strip(leg_rel: str):
    """THE GAP THE OTHER TESTS CANNOT SEE. Every test above lifts the function out and runs it, so
    they pass whether or not a leg invokes it. Measured 2026-09-15 by mutation: deleting the call
    from the public leg's post-pass left all 19 tests green, while a real sync would have shipped
    every changelog. So pin the wiring: the call exists, and it sits inside the real-sync post-pass
    (`if [[ "$DRY_RUN" == false ]]`), not in the dry-run path where it would never run."""
    leg = REPO / leg_rel
    if not leg.is_file():
        pytest.skip(f"{leg_rel} not present in this clone")
    lines = leg.read_text().splitlines()
    calls = [i for i, ln in enumerate(lines)
             if re.match(r'\s*strip_skill_changelogs\s+"\$\w+"\s*$', ln)]
    assert calls, f"{leg.name} defines strip_skill_changelogs() but never calls it"
    post_pass = next(i for i, ln in enumerate(lines) if ln.strip() == 'if [[ "$DRY_RUN" == false ]]; then')
    assert any(i > post_pass for i in calls), (
        f"{leg.name} calls the strip outside the real-sync post-pass, where it would not run"
    )


def test_both_legs_carry_the_same_function():
    """Two legs solving one rule two ways is how the next reader concludes the rule is unclear."""
    a, b = (_extract(REPO / leg) for leg in LEGS)
    assert a == b, "the legs' strip_skill_changelogs() copies have drifted"


def test_every_skill_keeps_its_changelog_last():
    """The contract `check_skill_registry.py` CHANGELOG-LAST enforces, asserted on the real tree:
    with nothing after the changelog, the strip has nothing it could take by mistake."""
    offenders = {}
    for p in sorted(SKILLS.glob("*/SKILL.md")):
        m = re.search(r"^## Changelog\s*$", p.read_text(), re.M)
        if m is None:
            continue
        after = [ln for ln in p.read_text()[m.end():].splitlines() if ln.startswith("## ")]
        if after:
            offenders[p.parent.name] = after
    assert not offenders, f"sections after the changelog: {offenders}"


def test_premise_real_skills_carry_changelogs_worth_stripping():
    """If the source skills stopped carrying changelogs, the tests above would pass vacuously."""
    skills = sorted(SKILLS.glob("*/SKILL.md"))
    with_log = [s for s in skills if re.search(r"^## Changelog", s.read_text(), re.M)]
    assert len(with_log) > 20, f"only {len(with_log)} of {len(skills)} skills carry a changelog"
