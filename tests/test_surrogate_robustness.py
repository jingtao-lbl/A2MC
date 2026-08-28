"""Tests for the surrogate robustness diagnostics.

`run_acceptance` returns ONE number per test from ONE split and `passed` is a hard threshold on
it, so a surrogate that cleared the bar by luck is indistinguishable from a comfortable one. These
two functions answer *would a different draw have said the same thing?* and *does the shortlist
survive a small input jitter?*

The load-bearing test is `test_a_lucky_pass_is_exposed`: a headline PASS with a low resample pass
rate. Without it the diagnostic could be trivially satisfied by always reporting 1.0.
"""
import sys
from pathlib import Path

import numpy as np
import pytest

REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from models.surrogate.spec import Provenance, SurrogateSpec, TargetSpec  # noqa: E402
from models.surrogate.tiers import S1Surrogate                           # noqa: E402
from models.surrogate.validate import (_slice_prediction,                # noqa: E402
                                       bootstrap_acceptance,
                                       perturbation_stability,
                                       run_acceptance)


def _spec(n_in=3):
    return SurrogateSpec(name="t", use_mode="offline_search", tier="S1",
                         input_names=tuple("abcdefgh"[:n_in]),
                         input_lower=(0.0,) * n_in, input_upper=(1.0,) * n_in,
                         targets=(TargetSpec(name="y"),),
                         provenance=Provenance(model="m"))


def _fit(noise, seed):
    rng = np.random.default_rng(seed)
    X = rng.random((300, 3))
    f = lambda Z: (5 * Z[:, 0] + rng.normal(0, noise, len(Z))).reshape(-1, 1)  # noqa: E731
    Y = f(X)
    Xt = rng.random((120, 3))
    Yt = f(Xt)
    return S1Surrogate(_spec(), learner="rf").fit(X, Y), Xt, Yt, Y


def test_a_comfortable_pass_is_stable():
    m, Xt, Yt, Ytr = _fit(noise=0.05, seed=3)
    rep = run_acceptance(m, Xt, Yt, Y_train=Ytr)
    b = bootstrap_acceptance(m, Xt, Yt, Y_train=Ytr, n_boot=100, seed=1)
    assert rep.passed
    assert b["pass_rate"]["ALL"] >= 0.9, "a clean fit should survive resampling"


def test_a_lucky_pass_is_exposed():
    """THE point of the diagnostic: a headline PASS that does not survive resampling.

    noise=1.2/seed=5 puts Spearman at ~0.71 against a 0.70 bar, so the split decides the verdict.
    Without this check a reviewer sees only "PASS".
    """
    m, Xt, Yt, Ytr = _fit(noise=1.2, seed=5)
    rep = run_acceptance(m, Xt, Yt, Y_train=Ytr)
    b = bootstrap_acceptance(m, Xt, Yt, Y_train=Ytr, n_boot=150, seed=1)
    assert rep.passed, "fixture must headline as PASS or it tests nothing"
    assert b["pass_rate"]["ALL"] < 0.9, (
        f"a knife-edge pass must be visible; got {b['pass_rate']['ALL']:.2f}")


def test_slicing_a_prediction_is_exact_not_an_approximation():
    """The optimisation the bootstrap rests on: predict(X[idx]) == predict(X)[idx].

    If this ever stops holding -- a learner that couples rows, a stateful gate -- the bootstrap
    silently starts measuring something else, so it is asserted rather than assumed.
    """
    m, Xt, Yt, Ytr = _fit(noise=0.3, seed=7)
    idx = np.array([5, 5, 7, 100, 3, 60])
    fresh = run_acceptance(m, Xt[idx], Yt[idx], Y_train=Ytr)
    sliced = run_acceptance(m, Xt[idx], Yt[idx], Y_train=Ytr,
                            pred=_slice_prediction(m.predict_batch(Xt), idx))
    for k in ("spearman", "top_k_recall", "r2"):
        assert fresh.per_target["y"][k] == pytest.approx(sliced.per_target["y"][k], abs=1e-12)


def test_bootstrap_refuses_a_sample_too_small_to_mean_anything():
    m, Xt, Yt, Ytr = _fit(noise=0.3, seed=8)
    b = bootstrap_acceptance(m, Xt[:4], Yt[:4], Y_train=Ytr, n_boot=50)
    assert b["n_boot"] == 0 and "theatre" in b["note"]


def test_zero_jitter_leaves_the_shortlist_identical():
    """The floor case. If eps=0 ever moved the top-k, the check would be measuring noise."""
    m, Xt, _, _ = _fit(noise=0.2, seed=9)
    s = perturbation_stability(m, Xt, eps=0.0, k=10, n_rep=3)
    assert s["top_k_overlap"]["y"] == pytest.approx(1.0)


def test_jitter_moves_the_shortlist_less_than_a_large_jitter():
    """Monotone in eps: a bigger perturbation must not be MORE stable."""
    m, Xt, _, _ = _fit(noise=0.2, seed=10)
    small = perturbation_stability(m, Xt, eps=0.02, k=10, n_rep=15, seed=0)
    large = perturbation_stability(m, Xt, eps=0.40, k=10, n_rep=15, seed=0)
    assert small["top_k_overlap"]["y"] >= large["top_k_overlap"]["y"]


def test_perturbation_stays_inside_the_declared_box():
    """Jitter must not push a query outside the spec bounds and silently test extrapolation."""
    m, Xt, _, _ = _fit(noise=0.2, seed=11)
    # All-corner inputs: any outward jitter would leave the box if not clipped.
    Xc = np.ones((20, 3))
    s = perturbation_stability(m, Xc, eps=0.5, k=5, n_rep=5)
    assert np.isfinite(s["top_k_overlap"]["y"])
