"""Tests for ``tools/check_capability_change_logged.py``.

The check exists because a capability change that never bumps a version passes every other gate by
not claiming anything. So the tests are mostly about the two ways it must NOT behave: firing on
ordinary edits (which is how a check becomes noise and gets ignored), and staying silent on the
commit that motivated it.

`faea9be7` is used as a real fixture rather than a synthetic one — it is the measured instance, and
a synthetic diff would not prove the checker reads this repo's actual history.
"""
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from tools.check_capability_change_logged import (CAPABILITY_PATHS,  # noqa: E402
                                                  SIGNALS, is_capability_path)

TOOL = REPO / "tools" / "check_capability_change_logged.py"


def _has(rev: str) -> bool:
    r = subprocess.run(["git", "-C", str(REPO), "cat-file", "-e", f"{rev}^{{commit}}"],
                       capture_output=True)
    return r.returncode == 0


def _run(*args):
    r = subprocess.run([sys.executable, str(TOOL), *args],
                       capture_output=True, text=True, cwd=str(REPO))
    return r.returncode, r.stdout + r.stderr


@pytest.mark.skipif(not _has("faea9be7"), reason="fixture commit absent (shallow clone?)")
def test_fires_on_the_commit_that_motivated_it():
    """`faea9be7` added a fourth sampling method with no bump and no log."""
    rc, out = _run("--commit", "faea9be7")
    assert rc == 1
    assert "CAPABILITY CHANGE WITH NO VERSION BUMP AND NO DEV LOG" in out
    assert "create_adapter_parameter_sample.py" in out
    # It must name WHY, not merely that a file was touched.
    assert "changed CLI choices list" in out or "new top-level function" in out


@pytest.mark.skipif(not _has("dc4038d5"), reason="fixture commit absent")
def test_a_range_that_includes_the_follow_up_log_is_clean():
    """The mid-arc case: code in one commit, its log in the next.

    This is the reason the tool documents the RANGE as the audit unit. If this ever starts
    failing, the tool has become noisy on correct work, which is how a check gets ignored.
    """
    rc, out = _run("--range", "5f82a939^..dc4038d5")
    assert rc == 0
    assert "accompanied by" in out


@pytest.mark.skipif(not _has("e31a25da"), reason="fixture commit absent")
def test_quiet_on_a_docs_and_log_only_commit():
    """11 files touched, no capability surface among them."""
    rc, out = _run("--commit", "e31a25da")
    assert rc == 0
    assert "no capability-surface change" in out


def test_capability_paths_exclude_tests_docs_and_cases():
    """A test, a doc or case work is not an A2MC capability.

    Including them would make the check fire constantly, and a check that is usually noise gets
    muted — the failure this repo has already measured for monitors and reviews.
    """
    assert is_capability_path("scripts/x.py")
    assert is_capability_path("tools/x.py")
    assert is_capability_path("orchestrator.py")
    assert not is_capability_path("tests/test_x.py")
    assert not is_capability_path("docs/41_plan.md")
    assert not is_capability_path("memory/dev_logs_adapterkit/20260827a_x.md")
    assert not is_capability_path("use_cases/PFLOTRAN_miniLEO/config/x.sh")


def test_signals_match_public_surface_changes_and_not_body_edits():
    """The discriminating property: a new top-level def fires, an indented one does not.

    An indented `def` is a method or a nested helper, which is far more often a refactor than a new
    capability. Getting this wrong in either direction is what decides whether the check is useful.
    """
    import re

    def fires(line: str) -> bool:
        return any(re.search(p, line) for p, _ in SIGNALS)

    assert fires("def sample_sobol_sequence(problem, n_samples, seed):")
    assert fires("class SurrogateSpec:")
    assert fires('    ap.add_argument("--no-second-order", action="store_true")')
    assert fires('                    choices=["morris", "sobol", "sobol_seq", "lhs"],')

    assert not fires("    def _helper(self):")          # a method
    assert not fires("    x = compute(y) + 1")           # a body edit
    assert not fires("# a comment mentioning def and class")
    assert not fires('    print("choices are limited")')
