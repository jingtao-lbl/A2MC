"""Tests for the surrogate promotion gate and the use_mode acceptance battery.

Two contracts land together here because they are two halves of one claim: that
`AcceptanceReport.passed` is **necessary and not sufficient**.

  * `MODE_CRITERIA` makes `use_mode` mean something — it was declared, validated, documented as
    selecting the battery, and read by nothing.
  * `tools/promote_surrogate.py` is the human gate, because the checks that should decide whether a
    surrogate may steer a search are not thresholds.

Every test below asserts a way one of them must REFUSE, since a gate that cannot refuse is not a
gate ([[feedback_a_check_that_cannot_fail]]).
"""
import json
import sys
from pathlib import Path

import numpy as np
import pytest

REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from models.surrogate.spec import Provenance, SurrogateSpec, TargetSpec   # noqa: E402
from models.surrogate.tiers import S1Surrogate                            # noqa: E402
from models.surrogate.validate import (criteria_for, r2_score,            # noqa: E402
                                       run_acceptance)
from tools.promote_surrogate import (PROMOTION_FILE, check_promotion,     # noqa: E402
                                     _acceptance)


def _spec(mode="offline_search"):
    return SurrogateSpec(name="t", use_mode=mode, tier="S1",
                         input_names=("a", "b", "c"),
                         input_lower=(0.0,) * 3, input_upper=(1.0,) * 3,
                         targets=(TargetSpec(name="y"),),
                         provenance=Provenance(model="m"))


def _fit(mode, noise=0.0, seed=0):
    rng = np.random.default_rng(seed)
    X = rng.random((300, 3))
    f = lambda Z: (5 * Z[:, 0] + rng.normal(0, noise, len(Z))).reshape(-1, 1)  # noqa: E731
    Y = f(X)
    Xt, Yt = rng.random((100, 3)), None
    Yt = f(Xt)
    m = S1Surrogate(_spec(mode), learner="rf").fit(X, Y)
    return m, Xt, Yt, Y


# ---------------------------------------------------------------- use_mode

def test_the_two_modes_gate_on_different_tests():
    """The asymmetry docs/41 states: calibration gates coverage, inference gates accuracy."""
    off = criteria_for("offline_search")
    on = criteria_for("online_inference")
    assert off["min_r2"] is None and off["gate_coverage"] is True
    assert on["min_r2"] is not None and on["gate_coverage"] is False


def test_an_unknown_use_mode_is_refused_not_defaulted():
    """Falling back to another mode's bar is the exact failure this table fixes."""
    with pytest.raises(ValueError, match="no acceptance criteria"):
        criteria_for("something_else")


def test_a_noisy_surrogate_passes_calibration_and_fails_inference():
    """THE discriminating test. Same response, opposite verdicts, for a stated reason.

    Heavy noise preserves the ORDER while destroying the pointwise value. A calibration surrogate
    needs to rank; a runtime emulator's pointwise value is the product.
    """
    # noise=0.7/seed=1 lands R2 ~0.78 with rho ~0.89 and top-10 recall 0.60: comfortably
    # inside the calibration bars and comfortably outside the 0.9 inference bar, with margin
    # on both sides so the test is not balanced on a knife edge.
    m_off, Xt, Yt, Ytr = _fit("offline_search", noise=0.7, seed=1)
    r_off = run_acceptance(m_off, Xt, Yt, Y_train=Ytr)
    m_on, Xt2, Yt2, Ytr2 = _fit("online_inference", noise=0.7, seed=1)
    r_on = run_acceptance(m_on, Xt2, Yt2, Y_train=Ytr2)

    assert r_off.passed, "ranking is the calibration requirement and it is met"
    assert not r_on.passed, "pointwise accuracy is the inference requirement and it is not"
    assert "pointwise_accuracy" not in r_off.verdicts, "R2 must not gate a calibration surrogate"
    assert r_on.verdicts["pointwise_accuracy"] is False


def test_r2_is_measured_and_reported_in_both_modes():
    """Not gating it is different from not measuring it — a reader still needs the number."""
    m, Xt, Yt, Ytr = _fit("offline_search", noise=0.4, seed=2)
    r = run_acceptance(m, Xt, Yt, Y_train=Ytr)
    assert np.isfinite(r.per_target["y"]["r2"])


def test_r2_of_a_constant_truth_is_nan_not_one():
    """Zero variance means R2 is undefined; returning 1.0 would report a perfect fit to nothing."""
    assert np.isnan(r2_score(np.ones(10), np.ones(10)))


def test_an_explicit_threshold_still_overrides_the_mode():
    """Backward compatibility: a caller that passed thresholds keeps controlling them."""
    m, Xt, Yt, Ytr = _fit("offline_search", noise=0.0, seed=3)
    r = run_acceptance(m, Xt, Yt, Y_train=Ytr, min_spearman=1.01)
    assert r.verdicts["ranking_fidelity"] is False, "an impossible bar must fail"


# ---------------------------------------------------------------- promotion

def _acc(tmp_path, passed=True):
    p = tmp_path / "acceptance.json"
    p.write_text(json.dumps({"passed": passed, "summary": "s"}))
    return p


def test_an_unpromoted_surrogate_is_not_usable(tmp_path):
    _acc(tmp_path)
    ok, why = check_promotion(tmp_path)
    assert ok is False and "not promoted" in why


def test_a_promotion_must_be_bound_to_the_report_it_was_granted_against(tmp_path):
    _acc(tmp_path)
    (tmp_path / PROMOTION_FILE).write_text(json.dumps(
        {"promoted": True, "acceptance_sha": "deadbeefdeadbeef", "basis": "x"}))
    ok, why = check_promotion(tmp_path)
    assert ok is False and "STALE" in why


def test_a_correctly_bound_promotion_is_usable(tmp_path):
    _acc(tmp_path)
    _, digest = _acceptance(tmp_path)
    (tmp_path / PROMOTION_FILE).write_text(json.dumps(
        {"promoted": True, "acceptance_sha": digest, "basis": "checked monotonicity",
         "promoted_at": "2026-08-27T12:00:00", "reviewed_by": "tester"}))
    ok, why = check_promotion(tmp_path)
    assert ok is True and "promoted" in why


def test_a_revoked_promotion_is_not_usable(tmp_path):
    _acc(tmp_path)
    _, digest = _acceptance(tmp_path)
    (tmp_path / PROMOTION_FILE).write_text(json.dumps(
        {"promoted": True, "acceptance_sha": digest, "basis": "x",
         "revoked": True, "revoked_at": "2026-08-27", "revoke_reason": "found a leak"}))
    ok, why = check_promotion(tmp_path)
    assert ok is False and "REVOKED" in why


def test_promotion_without_acceptance_is_refused(tmp_path):
    """A surrogate cannot be approved before it has been measured."""
    with pytest.raises(SystemExit, match="REFUSING"):
        _acceptance(tmp_path)
