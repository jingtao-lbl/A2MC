"""Tests for ``scripts/fit_ensemble_surrogate.py`` — ensemble to fitted surrogate.

This script is the join between two files that nothing else cross-checks: the design matrix and
the extracted Y matrix. Getting that join wrong does not raise anywhere downstream — it trains
each target on another case's inputs and every later index is confidently wrong — so the tests
here are mostly about the ways it must REFUSE ([[feedback_a_check_that_cannot_fail]]).
"""
import csv
import sys
from pathlib import Path

import numpy as np
import pytest

REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from scripts.fit_ensemble_surrogate import (align_to_matrix,  # noqa: E402
                                            load_y_csv)


def _write_y(path: Path, rows, targets=("t1", "t2")):
    with path.open("w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=["case", "status", *targets])
        w.writeheader()
        w.writerows(rows)
    return path


def test_viability_comes_from_status_not_from_finite_values(tmp_path):
    """A FAILED case must be labelled FAILED even if its columns happen to parse.

    S1Surrogate.fit falls back to "viable == every target finite" and its own comment calls that a
    fallback only: a crash and a merely-missing output are different facts, and which
    configurations crash is itself a result.
    """
    p = _write_y(tmp_path / "y.csv", [
        {"case": 1, "status": "COMPLETED", "t1": "1.0", "t2": "2.0"},
        {"case": 2, "status": "FAILED", "t1": "nan", "t2": "nan"},
        {"case": 3, "status": "COMPLETED", "t1": "3.0", "t2": "4.0"},
    ])
    cases, targets, Y, viable = load_y_csv(p)
    assert cases == [1, 2, 3]
    assert targets == ["t1", "t2"]
    assert viable.tolist() == [True, False, True]
    assert np.isnan(Y[1]).all()
    assert Y[0].tolist() == [1.0, 2.0]


def test_case_i_maps_to_row_i_minus_one(tmp_path):
    """The convention the materializer writes and the validator re-derives."""
    X = np.arange(50, dtype=float).reshape(10, 5)
    got = align_to_matrix([1, 4, 10], X)
    assert got.shape == (3, 5)
    assert np.array_equal(got[0], X[0])
    assert np.array_equal(got[1], X[3])
    assert np.array_equal(got[2], X[9])


def test_non_contiguous_and_out_of_order_cases_still_map_correctly(tmp_path):
    """The join is BY CASE NUMBER, not positional.

    A partially-complete ensemble yields gaps, so the Y file's rows are not a prefix of the
    matrix. Zipping the two files positionally would appear to work and be wrong on every row
    after the first gap.
    """
    X = np.arange(100, dtype=float).reshape(20, 5)
    got = align_to_matrix([7, 2, 19], X)
    assert np.array_equal(got[0], X[6])
    assert np.array_equal(got[1], X[1])
    assert np.array_equal(got[2], X[18])


def test_refuses_a_case_beyond_the_matrix(tmp_path):
    """The check must be able to FAIL.

    A case number past the end means the Y file and the matrix describe different rounds.
    Clipping or dropping those rows would train on a subset nobody chose.
    """
    X = np.zeros((10, 3))
    with pytest.raises(SystemExit) as e:
        align_to_matrix([1, 11], X)
    assert "REFUSING" in str(e.value)
    assert "outside" in str(e.value)


def test_refuses_case_zero(tmp_path):
    """Case 0 is the V0 baseline and carries NO matrix row.

    Under case i <-> row i-1 it would index row -1, which in numpy is the LAST row -- silently
    pairing the baseline's outputs with the final design point's inputs.
    """
    X = np.zeros((10, 3))
    with pytest.raises(SystemExit) as e:
        align_to_matrix([0, 1], X)
    assert "REFUSING" in str(e.value)


def test_empty_y_file_is_refused(tmp_path):
    p = _write_y(tmp_path / "y.csv", [])
    with pytest.raises(SystemExit):
        load_y_csv(p)
