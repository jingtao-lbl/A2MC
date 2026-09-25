"""`check_deferred_work_queued` + the staged-log discovery both new checkers share.

THE REGRESSION THIS PINS. Both checkers filtered staged paths with `"/memory/dev_logs" in rel` --
a LEADING SLASH that git paths do not have (`git diff --cached --name-only` yields
`memory/dev_logs_adapterkit/x.md`). So both silently matched zero dev logs and printed a clean
result: `check_skill_claims` had been skipping every dev log since it was written, and
`check_deferred_work_queued` never fired through the hook at all. Caught 2026-08-22 only because a
test staged a REAL modified log and the expected warning did not appear -- an earlier attempt
`touch`ed the file, which stages nothing, and that vacuous test "passed".

Every test below names the mutation it must fail on.

Author: Jing Tao with Claude
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent


def _load(name: str):
    spec = importlib.util.spec_from_file_location(name, REPO / "tools" / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


dwq = _load("check_deferred_work_queued")
csc = _load("check_skill_claims")


# --------------------------------------------------------------------------- staged-log discovery

#: Paths exactly as `git diff --cached --name-only` emits them: repo-relative, NO leading slash.
#: The two checkers' scopes differ DELIBERATELY and the split is asserted rather than assumed:
#: `check_skill_claims` also covers calibration phase logs (they carry a "Skills and memory
#: invoked" section), while `check_deferred_work_queued` does not -- a phase log's `## Next` is
#: the handshake to the NEXT PHASE, already carried by the offline state's `next_action`, so
#: routing it into TODO.md would add noise every cycle rather than catching a dropped item.
BOTH = [
    "memory/dev_logs_adapterkit/20260822a_Topic.md",
    "memory/dev_logs/20260101a_Topic.md",
]
CLAIMS_ONLY = ["use_cases/EcoSIM_BioCON/memory/logs/20260822a_phase3_x.md"]
NOT_LOGS = ["tools/check_x.py", "docs/39_Plan.md", "README.md"]
#: RETIRED frozen streams -- `memory/model_logs/` (2026-08-24) and `memory/ana_logs/` (2026-09-06).
#: No new log is written to either, so neither checker scans them. The AMBIGUITY defence still
#: counts them: `_short_is_unambiguous` enumerates `memory/*logs*/*.md` and is independent of this
#: filter, so a dev log sharing a date+letter with a frozen model log is still caught.
RETIRED = [
    "memory/model_logs/20260822a_Topic.md",
    "memory/ana_logs/20260712a_Topic.md",
]


def _staged(mod, rel, monkeypatch):
    monkeypatch.setattr(mod.subprocess, "run",
                        lambda *a, **k: type("R", (), {"stdout": rel})())
    return mod.staged_logs()


@pytest.mark.parametrize("rel", BOTH)
def test_git_style_paths_are_recognised_as_logs(rel, monkeypatch):
    """MUTATION: restore the leading slash in either checker's filter -> this fails.

    This is the whole bug. A filter written for absolute paths silently matches nothing when fed
    git's relative ones, and a checker that matches nothing reports success.
    """
    for mod in (dwq, csc):
        assert _staged(mod, rel, monkeypatch), f"{mod.__name__} missed {rel!r}"


@pytest.mark.parametrize("rel", CLAIMS_ONLY)
def test_calibration_phase_logs_are_claims_scope_only(rel, monkeypatch):
    """MUTATION: widen dwq to calibration logs -> this fails.

    Pins the deliberate asymmetry above, so narrowing or widening either scope is a decision
    someone has to make explicitly rather than a silent drift.
    """
    assert _staged(csc, rel, monkeypatch), "skill-claims must cover calibration phase logs"
    assert not _staged(dwq, rel, monkeypatch), "deferral routing must NOT cover phase logs"


@pytest.mark.parametrize("rel", NOT_LOGS)
def test_non_logs_are_ignored(rel, monkeypatch):
    """MUTATION: widen either filter to any .md -> this fails on docs/39_Plan.md."""
    for mod in (dwq, csc):
        assert _staged(mod, rel, monkeypatch) == [], f"{mod.__name__} took {rel!r} for a log"


# ------------------------------------------------------------------------------- deferral parsing

def _write(tmp_path: Path, body: str) -> Path:
    p = tmp_path / "20260822a_Some_Topic.md"
    p.write_text(body)
    return p


def test_a_next_section_with_items_is_deferred_work(tmp_path):
    """MUTATION: make has_real_work() always return False -> this fails."""
    p = _write(tmp_path, "# T\n\n## Next\n\n1. Do the thing TODO.md does not know about.\n")
    assert [h for h, _ in dwq.section_bodies(p.read_text())]
    assert dwq.has_real_work("1. Do the thing.")


def test_an_honest_nothing_outstanding_is_not_deferred_work():
    """MUTATION: drop the NOTHING regex -> this fails, and every clean log warns forever.

    A check that cannot be satisfied honestly gets bypassed wholesale, so the escape hatch is
    load-bearing rather than a courtesy.
    """
    assert not dwq.has_real_work("Nothing outstanding. The round is closed.")


def test_prose_without_items_is_not_a_task():
    """MUTATION: return True for any non-empty body -> this fails.

    A closing remark under '## Next' is not a queued task; treating it as one manufactures
    busywork on every commit.
    """
    assert not dwq.has_real_work("This closes the thread opened last week.")


@pytest.mark.parametrize("head", [
    "## Next", "## What this does NOT fix", "## Deferred", "## Open questions", "## Still open"])
def test_every_deferral_heading_shape_is_matched(head):
    """MUTATION: drop any alternative from DEFER_HEADS -> that parametrisation fails.

    Anchored to LITERAL headings, not to DEFER_HEADS itself: a test that iterates the pattern it
    validates cannot detect an omission in it (the circular-test failure found on 2026-08-22).
    """
    got = dwq.section_bodies(f"# T\n\n{head}\n\n1. An item.\n")
    assert got and got[0][0] == head


def test_routing_is_by_stem_and_the_short_form_counts(tmp_path, monkeypatch):
    """MUTATION: require the FULL stem only -> this fails on the short-form TODO line.

    Uniqueness is pinned separately below; here it is stubbed TRUE so this test exercises the
    ROUTING logic rather than the state of the real repo's log directories. Without the stub it
    began failing the moment a second stream grew a log with the same date+letter, which is a
    property of the repo and not of the behaviour under test.
    """
    monkeypatch.setattr(dwq, "_short_is_unambiguous", lambda s: True)
    p = _write(tmp_path, "# T\n\n## Next\n\n1. An item.\n")
    monkeypatch.setattr(dwq, "todo_text", lambda: "- see 20260822a for the follow-up")
    assert dwq.main([str(p)]) == 0
    monkeypatch.setattr(dwq, "todo_text", lambda: "- nothing relevant here")
    assert dwq.main([str(p)]) == 1


def test_a_missing_todo_warns_rather_than_passing(tmp_path, monkeypatch):
    """MUTATION: return 0 when TODO.md is absent -> this fails.

    Degrade loudly: a checker that cannot do its job must never print a result it did not earn.
    """
    p = _write(tmp_path, "# T\n\n## Next\n\n1. An item.\n")
    monkeypatch.setattr(dwq, "todo_text", lambda: "")
    assert dwq.main([str(p)]) == 1


# ------------------------------------- the short form must be UNAMBIGUOUS across log streams

def test_an_ambiguous_short_form_does_not_satisfy_the_link(monkeypatch, tmp_path):
    """MUTATION: accept any `short in todo` -> this fails.

    `memory/dev_logs_<branch>/` and `memory/model_logs/` keep INDEPENDENT same-day letter sequences,
    so one date+letter prefix can name two different logs. On 2026-08-22 a model log deferring three
    real items passed because TODO.md cited the DEV log of the same letter: a false clean, produced
    by the checker written to prevent false cleans.
    """
    monkeypatch.setattr(dwq, "_short_is_unambiguous", lambda s: False)
    monkeypatch.setattr(dwq, "todo_text", lambda: "- see 20260822c for the follow-up")
    p = tmp_path / "20260822c_Some_Topic.md"
    p.write_text("# T\n\n## Next\n\n1. An item.\n")
    assert dwq.main([str(p)]) == 1, "an ambiguous short form must NOT satisfy the link"


def test_an_unambiguous_short_form_still_satisfies_it(monkeypatch, tmp_path):
    """MUTATION: require the full stem always -> this fails.

    Dropping the short form entirely would be over-correction: a TODO line legitimately cites the
    date+letter, and rejecting that would make the check noisy on correctly-queued work.
    """
    monkeypatch.setattr(dwq, "_short_is_unambiguous", lambda s: True)
    monkeypatch.setattr(dwq, "todo_text", lambda: "- see 20260822c for the follow-up")
    p = tmp_path / "20260822c_Some_Topic.md"
    p.write_text("# T\n\n## Next\n\n1. An item.\n")
    assert dwq.main([str(p)]) == 0


def test_uniqueness_counts_UNTRACKED_logs_too():
    """MUTATION: drop --others --exclude-standard -> this fails while the log is unstaged.

    A log written this session is not yet tracked, and a tracked-only enumeration called it the
    unique holder of its prefix. The gate must measure the working tree, not the index.
    """
    import subprocess
    out = subprocess.run(["git", "ls-files", "--cached", "--others", "--exclude-standard",
                          "--", "memory/*logs*/*.md"],
                         cwd=REPO, capture_output=True, text=True).stdout.split()
    tracked = subprocess.run(["git", "ls-files", "--", "memory/*logs*/*.md"],
                             cwd=REPO, capture_output=True, text=True).stdout.split()
    assert len(out) >= len(tracked), "the enumeration must be a superset of the tracked one"


# ------------------------------------- the retired streams are no longer scanned

def test_retired_streams_are_not_scanned_for_deferrals(monkeypatch):
    """`memory/model_logs/` and `memory/ana_logs/` are frozen: no new log is written to either,
    so a deferral cannot appear in one. Scanning them can only produce work about closed files."""
    assert _staged(dwq, "\n".join(RETIRED), monkeypatch) == []


def test_the_ambiguity_defence_still_counts_the_retired_streams(monkeypatch, tmp_path):
    """The CONTROL for the narrowing: not scanning a stream must not stop it from making a
    short form ambiguous. `_short_is_unambiguous` globs `memory/*logs*/*.md`, not this filter."""
    import inspect
    src = inspect.getsource(dwq._short_is_unambiguous)
    assert "memory/*logs*/*.md" in src, (
        "the ambiguity enumeration must still span every stream, scanned or not")
