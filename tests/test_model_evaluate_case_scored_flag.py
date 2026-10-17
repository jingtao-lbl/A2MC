"""`scored: false` keeps a GUARD target out of evaluate_model_case's total, and nothing else.

A targets file can carry targets that are reported but not optimised: EcoSIM_Lusignan's R2 file
scores twelve seasonal totals and keeps the three annual totals as `scored: false` guards, because
each annual total is the sum of four scored seasons and would otherwise be counted twice. Each test
here states the way the behaviour could be wrong and fails if it is.

visibility: public
"""
from pathlib import Path

import numpy as np
import pytest

from tools.model_evaluate_case import evaluate_model_case


class _FakeBackend:
    """One column per variable; `mean` reduce over it. Enough to exercise the cost layer only."""

    def __init__(self, values):
        self.values = values

    def extract_history_variables(self, case, names, tape="h0"):
        return {n: np.full(4, self.values[n], dtype=float) for n in names}

    def select_group_series(self, data, target):
        return data


def _targets(guard_scored):
    t = [dict(name="a", variable="a", observed=100.0),
         dict(name="b", variable="b", observed=100.0),
         dict(name="g", variable="g", observed=100.0)]
    if guard_scored is not None:
        t[2]["scored"] = guard_scored
    return t


# a and b are each 10% off; the guard g is 50% off, so including it changes the total visibly
BE = _FakeBackend({"a": 110.0, "b": 90.0, "g": 150.0})
RMSRE_AB = 0.10
RMSRE_ABG = float(np.sqrt((0.1 ** 2 + 0.1 ** 2 + 0.5 ** 2) / 3))


def test_guard_is_excluded_from_the_total():
    total, _, _ = evaluate_model_case(Path("."), _targets(False), backend=BE)
    assert total == pytest.approx(RMSRE_AB)          # fails if the guard still enters the aggregate


def test_guard_is_still_reported():
    _, errors, sim = evaluate_model_case(Path("."), _targets(False), backend=BE)
    assert set(errors) == {"a", "b", "g"}            # fails if the guard is dropped instead of kept out
    assert sim["g"] == pytest.approx(150.0)


def test_unflagged_and_true_targets_are_scored():
    for flag in (None, True):
        total, _, _ = evaluate_model_case(Path("."), _targets(flag), backend=BE)
        assert total == pytest.approx(RMSRE_ABG)     # fails if the default flipped to unscored


def test_all_guards_refuses():
    t = [dict(x, scored=False) for x in _targets(False)]
    with pytest.raises(ValueError):
        evaluate_model_case(Path("."), t, backend=BE)
