"""tools/check_dev_log_for_version.py — does CLAUDE.md's version have a log that claims it?

Added 2026-08-21 after three framework changes shipped without a dev log in one session, two of them
*after* the gap was diagnosed in writing. Account:
`memory/dev_logs_adapterkit/reflection/20260821i_*`.

Every test below names a way the check must FAIL or must NOT fire. A presence gate that cannot fail
is worse than no gate: it converts an unnoticed omission into a certified one
(`feedback_a_check_that_cannot_fail`).
"""
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

from tools.check_dev_log_for_version import (  # noqa: E402
    claude_md_version, log_dirs, logs_claiming,
)

LOG = """\
# A Title

**Date:** August 21, 2026
**Author:** Jing Tao with Claude
**Type:** Bug fix
**Version:** {version}
{extra}
**Branch:** adapter-kit
"""


def _repo(tmp_path, claude_version="v2.264", logs=()):
    tmp_path.mkdir(parents=True, exist_ok=True)
    (tmp_path / "CLAUDE.md").write_text(
        f"# X\n\n**Status:** Implementation Complete ({claude_version})\n")
    d = tmp_path / "memory" / "dev_logs_adapterkit"
    d.mkdir(parents=True)
    (tmp_path / "memory" / "model_logs").mkdir()
    (d / "reflection").mkdir()
    for name, version, extra in logs:
        (d / name).write_text(LOG.format(version=version, extra=extra))
    return tmp_path


def test_reads_the_version_from_claude_md(tmp_path):
    assert claude_md_version(_repo(tmp_path, "v2.264")) == "v2.264"


def test_missing_status_header_is_not_silently_ok(tmp_path):
    """An unreadable version must not resolve to something that then 'passes'."""
    (tmp_path / "CLAUDE.md").write_text("# X\n\nno status line here\n")
    assert claude_md_version(tmp_path) is None


def test_a_log_claiming_the_version_is_found(tmp_path):
    r = _repo(tmp_path, logs=[("20260821h_x.md", "v2.264", "")])
    assert [p.name for p in logs_claiming("v2.264", r)] == ["20260821h_x.md"]


def test_no_log_claiming_it_is_EMPTY(tmp_path):
    """THE test. This is the state that shipped three times and was invisible."""
    r = _repo(tmp_path, logs=[("20260821h_x.md", "v2.261", "")])
    assert logs_claiming("v2.264", r) == []


def test_a_changelog_row_does_not_count(tmp_path):
    """A version mentioned in prose is not a claim.

    This is the exact bypass that occurred: a detailed changelog row whose `Details:` pointed at an
    older log. Mentioning the version somewhere must never satisfy the gate.
    """
    r = _repo(tmp_path, logs=[("20260821h_x.md", "v2.261", "")])
    (r / "memory" / "a2mc_development_history.md").write_text(
        "- **v2.264** (2026-08-21): a long detailed row. Details: `20260821h_x.md`.\n")
    body = r / "memory" / "dev_logs_adapterkit" / "20260821h_x.md"
    body.write_text(body.read_text() + "\nThis log discusses v2.264 at length.\n")
    assert logs_claiming("v2.264", r) == [], "prose mentioning the version satisfied the gate"


def test_also_covers_lets_one_log_claim_an_arc(tmp_path):
    r = _repo(tmp_path, logs=[("20260821h_x.md", "v2.264", "**Also covers:** v2.263")])
    assert [p.name for p in logs_claiming("v2.263", r)] == ["20260821h_x.md"]
    assert [p.name for p in logs_claiming("v2.264", r)] == ["20260821h_x.md"]


def test_also_covers_accepts_several(tmp_path):
    r = _repo(tmp_path, logs=[("a.md", "v2.264", "**Also covers:** v2.262, v2.263")])
    for v in ("v2.262", "v2.263", "v2.264"):
        assert logs_claiming(v, r), f"{v} not claimed"


def test_a_retrospective_header_claims_nothing(tmp_path):
    """`**Version:** (no bump — a retrospective)` must not be read as claiming anything."""
    r = _repo(tmp_path, logs=[("refl.md", "(no bump — a retrospective)", "")])
    assert logs_claiming("v2.264", r) == []


def test_a_multi_version_header_string_does_not_claim(tmp_path):
    """`**Version:** v2.263 + v2.264` is ambiguous; Also covers: is the supported form."""
    r = _repo(tmp_path, logs=[("a.md", "v2.263 + v2.264", "")])
    assert logs_claiming("v2.263", r) == []
    assert logs_claiming("v2.264", r) == []


def test_a_prefix_version_does_not_match(tmp_path):
    """v2.26 must not satisfy a check for v2.264, nor the reverse."""
    r = _repo(tmp_path, logs=[("a.md", "v2.26", "")])
    assert logs_claiming("v2.264", r) == []
    r2 = _repo(tmp_path / "b", logs=[("a.md", "v2.264", "")])
    assert logs_claiming("v2.26", r2) == []


def test_reflection_and_model_log_dirs_are_searched(tmp_path):
    r = _repo(tmp_path)
    refl = r / "memory" / "dev_logs_adapterkit" / "reflection" / "x.md"
    refl.write_text(LOG.format(version="v2.264", extra=""))
    assert [p.name for p in logs_claiming("v2.264", r)] == ["x.md"]
    ml = r / "memory" / "model_logs" / "m.md"
    ml.write_text(LOG.format(version="v2.265", extra=""))
    assert [p.name for p in logs_claiming("v2.265", r)] == ["m.md"]


def test_log_dirs_glob_so_a_new_branch_dir_is_covered(tmp_path):
    """A per-branch log dir must not fall outside the check by being newly created."""
    r = _repo(tmp_path)
    newd = r / "memory" / "dev_logs_somenewbranch"
    newd.mkdir()
    (newd / "a.md").write_text(LOG.format(version="v2.264", extra=""))
    assert newd in log_dirs(r)
    assert [p.name for p in logs_claiming("v2.264", r)] == ["a.md"]


def test_it_fires_on_the_real_repo_for_an_unused_version():
    """Guard against a check that cannot fail in situ: an invented version must have no claimant."""
    assert logs_claiming("v99.999") == []


def test_the_real_repo_current_version_is_claimed():
    """And the live state must pass, or the gate is not usable."""
    v = claude_md_version()
    assert v, "CLAUDE.md has no readable version"
    assert logs_claiming(v), f"{v} is claimed by no dev log"
