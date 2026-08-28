"""Tests for ``scripts/check_surrogate_gate.py`` — the surrogate gate's condition 2.

This script exists to stop a judgement being made after the data is seen, so the tests are mostly
about it being able to return BOTH verdicts and refusing to answer an easier question than the one
asked. A gate that can only pass is not a gate ([[feedback_a_check_that_cannot_fail]]).
"""
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from scripts.check_surrogate_gate import (GATE_CLOSED, GATE_OPEN,  # noqa: E402
                                          load_bands)

SCRIPT = REPO / "scripts" / "check_surrogate_gate.py"

TARGETS_YAML = """\
site: T
targets:
  a:
    observed: 1.0
    uncertainty: 0.10
  b:
    observed: 100.0
    uncertainty: 0.50
"""


def _yaml(tmp_path, text=TARGETS_YAML):
    p = tmp_path / "targets.yaml"
    p.write_text(text)
    return p


def _ycsv(tmp_path, rows, cols=("a", "b")):
    p = tmp_path / "y.csv"
    lines = ["case,status," + ",".join(cols)]
    for r in rows:
        lines.append(",".join(str(r[c]) for c in ("case", "status", *cols)))
    p.write_text("\n".join(lines) + "\n")
    return p


def _run(y, targets):
    r = subprocess.run([sys.executable, str(SCRIPT), "--y-matrix", str(y),
                        "--targets", str(targets)], capture_output=True, text=True)
    return r.returncode, r.stdout + r.stderr


def test_gate_opens_when_one_case_is_inside_every_band(tmp_path):
    y = _ycsv(tmp_path, [{"case": 1, "status": "COMPLETED", "a": 1.0, "b": 100.0}])
    rc, out = _run(y, _yaml(tmp_path))
    assert rc == GATE_OPEN
    assert "GATE OPENS" in out


def test_gate_stays_closed_when_no_single_case_satisfies_all(tmp_path):
    """Each target is individually reachable but never TOGETHER — the joint miss.

    This is the case the verdict text must distinguish from an unreachable target, because the
    two route to completely different work: a trade-off between targets versus a box that cannot
    reach one at all.
    """
    y = _ycsv(tmp_path, [
        {"case": 1, "status": "COMPLETED", "a": 1.0, "b": 1000.0},   # a in, b out
        {"case": 2, "status": "COMPLETED", "a": 5.0, "b": 100.0},    # b in, a out
    ])
    rc, out = _run(y, _yaml(tmp_path))
    assert rc == GATE_CLOSED
    assert "GATE STAYS CLOSED" in out
    assert "JOINT" in out
    assert "UNREACHABLE" not in out.split("VERDICT")[1]


def test_a_target_in_band_in_zero_cases_is_reported_unreachable(tmp_path):
    y = _ycsv(tmp_path, [
        {"case": 1, "status": "COMPLETED", "a": 1.0, "b": 1e6},
        {"case": 2, "status": "COMPLETED", "a": 1.05, "b": 1e6},
    ])
    rc, out = _run(y, _yaml(tmp_path))
    assert rc == GATE_CLOSED
    assert "UNREACHABLE" in out
    assert "'b'" in out or '"b"' in out or "['b']" in out


def test_the_band_is_per_target_uncertainty_not_a_global_tolerance(tmp_path):
    """The discriminating test.

    `b` sits 40% off its observation. Under its OWN uncertainty (0.50) that is in band; under a
    global 0.25 tolerance, or under `a`'s 0.10, it would not be. If this ever fails, the script
    has started reading the wrong field and the gate has silently become a different question.
    """
    y = _ycsv(tmp_path, [{"case": 1, "status": "COMPLETED", "a": 1.0, "b": 140.0}])
    rc, out = _run(y, _yaml(tmp_path))
    assert rc == GATE_OPEN, out


def test_non_finite_and_blank_targets_count_as_out_of_band(tmp_path):
    y = _ycsv(tmp_path, [{"case": 1, "status": "COMPLETED", "a": 1.0, "b": "nan"}])
    rc, out = _run(y, _yaml(tmp_path))
    assert rc == GATE_CLOSED


def test_failed_cases_are_excluded_from_the_denominator(tmp_path):
    """A FAILED row must not be scored, and must not count as a completed case."""
    y = _ycsv(tmp_path, [
        {"case": 1, "status": "FAILED", "a": "nan", "b": "nan"},
        {"case": 2, "status": "COMPLETED", "a": 1.0, "b": 100.0},
    ])
    rc, out = _run(y, _yaml(tmp_path))
    assert rc == GATE_OPEN
    assert "1 COMPLETED" in out


def test_refuses_a_target_missing_its_band(tmp_path):
    """A gate evaluated on a subset of targets answers an easier question."""
    bad = TARGETS_YAML.replace("    uncertainty: 0.50\n", "")
    with pytest.raises(SystemExit) as e:
        load_bands(_yaml(tmp_path, bad))
    assert "REFUSING" in str(e.value)


def test_refuses_when_the_y_matrix_lacks_a_declared_target(tmp_path):
    y = _ycsv(tmp_path, [{"case": 1, "status": "COMPLETED", "a": 1.0}], cols=("a",))
    rc, out = _run(y, _yaml(tmp_path))
    assert rc != GATE_OPEN and rc != GATE_CLOSED
    assert "REFUSING" in out


def test_refuses_an_ensemble_with_no_completed_case(tmp_path):
    y = _ycsv(tmp_path, [{"case": 1, "status": "FAILED", "a": "nan", "b": "nan"}])
    rc, out = _run(y, _yaml(tmp_path))
    assert rc not in (GATE_OPEN, GATE_CLOSED)
    assert "not yet evaluable" in out
