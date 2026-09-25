"""The hooks a sequential search needs from S1Surrogate and GPLearner, and the k-NN chunk budget.

A search layer (tools/bayesian_optimization/acquisition.py) fits per-target GPs through
S1Surrogate, so S1Surrogate must be able to:
  * train on EVERY viable row (`calibration_fraction=0`), since each row is an expensive run;
  * expose the per-target posterior mean and std in the space the regressor was fitted in, and
    refuse to for a family whose std is not a predictive posterior;
  * return P(viable) and the hull verdict without a second posterior evaluation, with P(viable)
    correct for a classifier fitted on a single class;
  * make a Kriging-believer copy whose regressors condition on fake observations with every
    hyperparameter frozen, and which can never be saved;
  * subsample a GP without dropping the rows a search ranks best, and say which rows each
    regressor trained on.

Every test is written so that it fails if the behaviour it names is removed.
"""
from __future__ import annotations

import dataclasses
import sys
from pathlib import Path

import numpy as np
import pytest

REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

import models.surrogate.base as base_mod  # noqa: E402
from models.surrogate.base import (  # noqa: E402
    BatchPrediction, HullGate, SurrogateModel, apply_transform, invert_transform)
from models.surrogate.learners import LEARNERS, GPLearner  # noqa: E402
from models.surrogate.spec import Provenance, SurrogateSpec, TargetSpec  # noqa: E402
from models.surrogate.tiers import S0Surrogate, S1Surrogate, load  # noqa: E402
from models.surrogate.validate import run_acceptance  # noqa: E402

pytestmark = pytest.mark.filterwarnings("ignore::sklearn.exceptions.ConvergenceWarning",
                                        "ignore:.*unstamped provenance")


def _spec(transforms=("identity", "log"), lower=(0.0, 0.0), upper=(1.0, 1.0)):
    return SurrogateSpec(
        name="hooks", use_mode="offline_search", tier="S1",
        input_names=("a", "b"), input_lower=lower, input_upper=upper,
        targets=(TargetSpec("t1", observed=1.0, transform=transforms[0]),
                 TargetSpec("t2", observed=2.0, transform=transforms[1])),
        provenance=Provenance(model="test_model"))


def _data(n=120, seed=0):
    """Two smooth positive targets; rows with a < 0.2 are dead (NaN targets)."""
    rng = np.random.default_rng(seed)
    X = rng.uniform(0, 1, size=(n, 2))
    Y = np.column_stack([1.0 + 0.8 * X[:, 0] - 0.3 * X[:, 1],
                         2.0 + 0.5 * X[:, 0] * X[:, 1]]) + rng.normal(0, 0.01, size=(n, 2))
    viable = X[:, 0] >= 0.2
    Y[~viable] = np.nan
    return X, Y, viable


def _gp():
    return GPLearner(n_restarts=0, random_state=0)


def _fit(cf=0.0, learner=None, n=120):
    X, Y, viable = _data(n)
    m = S1Surrogate(_spec(), learner=learner if learner is not None else _gp(),
                    calibration_fraction=cf).fit(X, Y, viable)
    return m, X, Y, viable


# -----------------------------------------------------------------------------------------------
# calibration_fraction = 0
# -----------------------------------------------------------------------------------------------

def test_calibration_fraction_ZERO_trains_on_EVERY_viable_row():
    m0, _, _, viable = _fit(cf=0.0)
    m3, _, _, _ = _fit(cf=0.3)
    n_viable = int(viable.sum())
    assert all(lr.n_used == n_viable for lr in m0._models)
    assert all(lr.n_used < n_viable for lr in m3._models), "the calibrated fit must hold rows out"


def test_an_uncalibrated_model_claims_NO_interval_and_no_quantile():
    m, X, _, _ = _fit(cf=0.0)
    pred = m.predict_batch(X[:5])
    assert pred.lower is None and pred.upper is None
    with pytest.raises(ValueError, match="no conformal quantile"):
        _ = m.conformal_quantile
    assert _fit(cf=0.3)[0].predict_batch(X[:5]).lower is not None


def test_calibration_fraction_bounds_and_the_minimum_rows_without_a_split():
    for bad in (-0.1, 1.0):
        with pytest.raises(ValueError, match=r"\[0, 1\)"):
            S1Surrogate(_spec(), calibration_fraction=bad)
    X, Y, _ = _data(40)
    one = np.zeros(40, bool)
    one[0] = True
    with pytest.raises(ValueError, match=">= 2"):
        S1Surrogate(_spec(), learner=_gp(), calibration_fraction=0.0).fit(X, Y, one)
    three = np.zeros(40, bool)
    three[:3] = True
    with pytest.raises(ValueError, match=">= 4"):
        S1Surrogate(_spec(), learner=_gp(), calibration_fraction=0.3).fit(X, Y, three)
    two = np.zeros(40, bool)
    two[:2] = True
    Y2 = Y.copy()
    Y2[:2] = [[1.0, 2.0], [1.1, 2.1]]
    S1Surrogate(_spec(), learner=_gp(), calibration_fraction=0.0).fit(X, Y2, two)


def test_an_uncalibrated_model_ROUND_TRIPS_save_and_load(tmp_path):
    m, X, _, _ = _fit(cf=0.0)
    m.save(tmp_path / "art")
    back = load(tmp_path / "art", strict=False)
    assert back.calibrated is False and back.predict_batch(X[:3]).lower is None
    assert np.array_equal(back.predict_batch(X[:7]).values, m.predict_batch(X[:7]).values)


# -----------------------------------------------------------------------------------------------
# posterior, viability, hull
# -----------------------------------------------------------------------------------------------

def test_posterior_is_in_the_FITTED_space_and_inverts_to_the_point_prediction():
    m, X, _, _ = _fit(cf=0.0)
    mu, sd = m.posterior(X[:9])
    vals = m.predict_batch(X[:9]).values
    for j, t in enumerate(m.spec.targets):
        assert np.allclose(invert_transform(mu[:, j], t.transform), vals[:, j])
    # t2 is log-transformed: its posterior mean is log-scale, not native
    assert np.all(np.abs(mu[:, 1] - np.log(vals[:, 1])) < 1e-9)
    assert np.all(sd > 0)


def test_posterior_is_REFUSED_for_a_family_with_no_native_std():
    m, X, _, _ = _fit(cf=0.0, learner="gbm")
    with pytest.raises(ValueError, match="no native std"):
        m.posterior(X[:3])


def test_viability_and_hull_are_the_fields_predict_batch_reports():
    m, X, _, _ = _fit(cf=0.0)
    Q = np.vstack([X[:20], [[0.05, 0.5], [3.0, 3.0]]])
    pred = m.predict_batch(Q)
    dist, inside = m.hull(Q)
    assert np.array_equal(m.viability(Q), pred.viability)
    assert np.array_equal(dist, pred.hull_distance) and np.array_equal(inside, pred.in_hull)
    assert not inside[-1], "a point far outside the box must be outside the hull"


# -----------------------------------------------------------------------------------------------
# Kriging believer
# -----------------------------------------------------------------------------------------------

def test_believe_FREEZES_hyperparameters_keeps_the_mean_and_leaves_the_original_untouched():
    m, X, _, _ = _fit(cf=0.0)
    Q = np.random.default_rng(3).uniform(0.2, 1.0, size=(40, 2))
    before_mu, before_sd = m.posterior(Q)
    pick = np.array([[0.6, 0.4]])
    b = m.believe(pick)
    mu_b, _ = b.posterior(Q)
    assert np.max(np.abs(mu_b - before_mu)) < 1e-8, "a believed mean must not move the mean"
    for lr0, lr1 in zip(m._models, b._models):
        assert np.array_equal(lr0._m.kernel_.theta, lr1._m.kernel_.theta)
        assert lr1.n_used == lr0.n_used + 1
    mu0, sd0 = m.posterior(Q)
    assert np.array_equal(mu0, before_mu) and np.array_equal(sd0, before_sd)
    assert b.believed and not m.believed and b.calibrated is False


def test_believe_SHRINKS_the_spread_where_the_fake_observation_sits():
    """Sparse data so the posterior spread there is dominated by lack of data, not noise."""
    rng = np.random.default_rng(1)
    X = rng.uniform(0, 1, size=(12, 2))
    Y = np.column_stack([1 + np.sin(4 * X[:, 0]), 2 + X[:, 1]])
    m = S1Surrogate(_spec(("identity", "identity")), learner=_gp(),
                    calibration_fraction=0.0).fit(X, Y)
    far = np.array([[0.97, 0.03]])
    _, sd_before = m.posterior(far)
    _, sd_after = m.believe(far).posterior(far)
    assert np.all(sd_after < 0.5 * sd_before)


def test_a_believed_copy_REFUSES_to_save(tmp_path):
    m, _, _, _ = _fit(cf=0.0)
    with pytest.raises(RuntimeError, match="Kriging-believer"):
        m.believe(np.array([[0.5, 0.5]])).save(tmp_path / "fake")
    assert not (tmp_path / "fake").exists(), "nothing may be written before the refusal"


def test_believe_is_REFUSED_for_a_learner_that_cannot_condition():
    m, _, _, _ = _fit(cf=0.0, learner="rf")
    with pytest.raises(NotImplementedError, match="local penalisation"):
        m.believe(np.array([[0.5, 0.5]]))


def test_condition_on_EQUALS_an_exact_fixed_kernel_posterior_on_the_augmented_data():
    from sklearn.gaussian_process import GaussianProcessRegressor
    rng = np.random.default_rng(0)
    X = rng.uniform(0, 1, (30, 3))
    y = np.sin(3 * X[:, 0]) + X[:, 1] ** 2 + 0.01 * rng.normal(size=30)
    g = _gp().fit(X, y)
    Xn = rng.uniform(0, 1, (4, 3))
    yn = g.predict(Xn) + 0.3                      # a lie that is NOT the mean, so the mean moves
    c = g.condition_on(Xn, yn)
    Q = rng.uniform(0, 1, (25, 3))
    ym, ys = g._m._y_train_mean, g._m._y_train_std
    Z = np.vstack([g._m.X_train_, g._z(Xn)])
    ref = GaussianProcessRegressor(kernel=g._m.kernel_, optimizer=None, normalize_y=False,
                                   alpha=g._m.alpha).fit(Z, (np.concatenate([y, yn]) - ym) / ys)
    m_ref, s_ref = ref.predict(g._z(Q), return_std=True)
    m_c, s_c = c.predict_mean_std(Q)
    assert np.allclose(m_c, m_ref * ys + ym, atol=1e-10) and np.allclose(s_c, s_ref * ys, atol=1e-10)
    assert np.max(np.abs(m_c - g.predict(Q))) > 1e-3, "the non-mean lie must move the mean"


def test_condition_on_REFUSES_when_sklearn_hides_the_normalisation():
    g = _gp().fit(np.random.default_rng(0).uniform(0, 1, (10, 2)), np.arange(10.0))
    del g._m._y_train_std
    with pytest.raises(RuntimeError, match="_y_train_std"):
        g.condition_on([[0.5, 0.5]], [1.0])


# -----------------------------------------------------------------------------------------------
# HullGate chunk budget
# -----------------------------------------------------------------------------------------------

def test_the_knn_chunk_budget_counts_DIMENSIONS_not_only_rows(monkeypatch):
    rng = np.random.default_rng(0)
    p, n_train, n_query = 28, 400, 300
    gate = HullGate().fit(rng.normal(size=(n_train, p)))
    monkeypatch.setattr(base_mod, "_KNN_CHUNK_ELEMENTS", 2e5)
    shapes = []
    real_norm = np.linalg.norm

    def spy(a, *args, **kw):
        shapes.append(np.shape(a))
        return real_norm(a, *args, **kw)

    monkeypatch.setattr(np.linalg, "norm", spy)
    d_small = gate.distance(rng.normal(size=(n_query, p)))
    assert shapes and all(s[0] * s[1] * s[2] <= 2e5 for s in shapes), shapes[:3]
    monkeypatch.setattr(np.linalg, "norm", real_norm)
    monkeypatch.setattr(base_mod, "_KNN_CHUNK_ELEMENTS", 2e7)
    rng2 = np.random.default_rng(0)
    rng2.normal(size=(n_train, p))
    d_big = gate.distance(rng2.normal(size=(n_query, p)))
    assert np.array_equal(d_small, d_big), "chunking must not change the distances"


# -----------------------------------------------------------------------------------------------
# Posterior admission: only a predictive posterior std may be integrated as a Gaussian
# -----------------------------------------------------------------------------------------------

def test_only_the_GP_declares_a_posterior_std():
    flags = {name: cls.posterior_std for name, cls in LEARNERS.items()}
    assert flags == {name: name == "gp" for name in LEARNERS}, flags


def test_posterior_is_REFUSED_for_rf_by_name_and_still_served_for_gp():
    m, X, _, _ = _fit(cf=0.0, learner="rf")
    with pytest.raises(ValueError, match=r"'rf'.*Gaussian posterior"):
        m.posterior(X[:3])
    mu, sd = _fit(cf=0.0)[0].posterior(X[:3])
    assert mu.shape == sd.shape == (3, 2) and np.all(np.isfinite(mu)) and np.all(sd > 0)


# -----------------------------------------------------------------------------------------------
# Viability from a classifier fitted on a single class
# -----------------------------------------------------------------------------------------------

class _StubClassifier:
    """`classes_` plus a constant `predict_proba` row, standing in for a fitted classifier."""

    def __init__(self, classes, row):
        self.classes_ = np.asarray(classes)
        self._row = np.asarray(row, dtype=float)

    def predict_proba(self, X):
        return np.tile(self._row, (len(X), 1))


def test_viability_of_a_SINGLE_CLASS_classifier_comes_from_classes_not_the_columns():
    """docs/45 test 9. The stubs return the two columns `[1 - p, p]` that a degenerate
    single-class fit returns whatever its class, so reading `classes_.index(1)` as the column
    reports P = 0 for an all-viable fit and fails outright for an all-dead one."""
    m, X, _, _ = _fit(cf=0.0)
    assert m._clf is not None, "the fixture must fit a classifier (it has dead rows)"
    Q = X[:7]
    m._clf = _StubClassifier([1], [0.0, 1.0])
    assert np.array_equal(m.viability(Q), np.ones(7))
    m._clf = _StubClassifier([0], [1.0, 0.0])
    assert np.array_equal(m.viability(Q), np.zeros(7))
    m._clf = _StubClassifier([0, 2], [0.4, 0.6])
    with pytest.raises(ValueError, match="no label 1"):
        m.viability(Q)
    m._clf = _StubClassifier([0, 1], [0.2, 0.3, 0.5])
    with pytest.raises(ValueError, match="one column per class"):
        m.viability(Q)
    m._clf = _StubClassifier([1, 0], [0.7, 0.3])
    assert np.allclose(m.viability(Q), 0.7), "the column of label 1 follows classes_ order"
    assert np.array_equal(m.predict_batch(Q).viability, m.viability(Q))


def test_viability_of_the_real_single_class_MLP_classifier_is_ONE():
    pytest.importorskip("torch")
    from models.surrogate.learners import MLPEnsembleClassifier
    m, X, _, _ = _fit(cf=0.0)
    m._clf = MLPEnsembleClassifier().fit(X, np.ones(len(X), dtype=int))
    assert list(m._clf.classes_) == [1]
    assert np.array_equal(m.viability(X[:5]), np.ones(5))


# -----------------------------------------------------------------------------------------------
# GP subsample by priority, and the rows each regressor trained on
# -----------------------------------------------------------------------------------------------

def _old_subsample(X, y, max_points, random_state):
    """The GPLearner subsample as it was before `priority` existed, frozen here verbatim, and
    returning the drawn indices too."""
    idx = np.arange(len(X))
    if len(X) > max_points:
        rng = np.random.default_rng(random_state)
        idx = rng.choice(len(X), max_points, replace=False)
        X, y = X[idx], y[idx]
    return X, y, idx


def _rowsort(A):
    """Rows in lexicographic order, so two row sets compare regardless of their order."""
    A = np.asarray(A, dtype=float)
    return A[np.lexsort(A.T[::-1])]


def _gp_rows(n=60, seed=7):
    rng = np.random.default_rng(seed)
    X = rng.uniform(0, 1, (n, 2))
    y = np.sin(3 * X[:, 0]) + X[:, 1]
    return X, y, rng


def test_priority_subsample_KEEPS_the_best_rows_a_random_draw_would_drop():
    """docs/45 test 14. The `keep_best` smallest FINITE priorities are kept (ties to the lower
    index), the rest are drawn from the others with the learner's seed, and `n_used` and
    `train_idx_` say so."""
    n, mp, k = 60, 15, 3
    X, y, rng = _gp_rows(n)
    pr = rng.normal(size=n)
    pr[5], pr[9] = -np.inf, np.nan                     # non-finite: never force-kept
    best = sorted(np.flatnonzero(np.isfinite(pr)), key=lambda i: (pr[i], i))[:k]
    dropping = [rs for rs in range(12)
                if best[0] not in np.random.default_rng(rs).choice(n, mp, replace=False)]
    assert len(dropping) >= 3, "the fixture must have seeds where a plain draw drops the minimum"
    for rs in dropping[:3]:
        g = GPLearner(max_points=mp, n_restarts=0, random_state=rs)
        with pytest.warns(RuntimeWarning, match="subsampled"):
            g.fit(X, y, priority=pr, keep_best=k)
        others = np.array([i for i in range(n) if i not in best])
        drawn = others[np.random.default_rng(rs).choice(len(others), mp - k, replace=False)]
        assert np.array_equal(g.train_idx_, np.sort(np.concatenate([best, drawn])))
        assert g.n_used == mp == len(g.train_idx_)
        assert np.allclose(_rowsort(g.training_inputs()), _rowsort(X[g.train_idx_]))
    ties = rng.integers(0, 4, n).astype(float)
    g = GPLearner(max_points=mp, n_restarts=0, random_state=0)
    with pytest.warns(RuntimeWarning, match="subsampled"):
        g.fit(X, y, priority=ties, keep_best=k)
    assert set(np.flatnonzero(ties == 0)[:k]) <= set(g.train_idx_), "ties go to the lower index"
    with pytest.raises(ValueError, match="keep_best"):
        GPLearner(max_points=mp).fit(X, y, priority=pr, keep_best=mp + 1)


def test_without_priority_the_subsample_is_BIT_IDENTICAL_to_the_old_draw():
    n, mp = 60, 15
    X, y, rng = _gp_rows(n)
    for rs in (0, 3):
        g = GPLearner(max_points=mp, n_restarts=0, random_state=rs)
        with pytest.warns(RuntimeWarning, match="subsampled"):
            g.fit(X, y)
        Xo, yo, idx = _old_subsample(X, y, mp, rs)
        assert np.array_equal(g._m.X_train_, (Xo - Xo.mean(axis=0)) / Xo.std(axis=0))
        assert np.array_equal(g._m.y_train_, (yo - yo.mean()) / yo.std())
        assert np.array_equal(g.train_idx_, np.sort(idx)) and g.n_used == mp
        # the stored rows keep the draw order, so they match train_idx_ as a set, not by position
        assert np.allclose(g.training_inputs(), Xo)
        assert np.allclose(_rowsort(g.training_inputs()), _rowsort(X[g.train_idx_]))
    # at or below max_points nothing is subsampled, with or without a priority
    g = GPLearner(max_points=n, n_restarts=0).fit(X, y, priority=rng.normal(size=n), keep_best=5)
    assert np.array_equal(g.train_idx_, np.arange(n)) and g.n_used == n
    assert np.array_equal(g._m.X_train_, (X - X.mean(axis=0)) / X.std(axis=0))


def _priority_fixture():
    """Viable rows with t2 missing on some, a priority whose global minimum is one of them, and
    a GP cap below the fit rows so the subsample decides what each regressor sees."""
    X, Y, viable = _data(120)
    rng = np.random.default_rng(11)
    pr = np.where(viable, rng.uniform(1.0, 2.0, 120), np.nan)
    live = np.flatnonzero(viable)
    r_min, r_t2 = live[4], live[9]
    pr[r_min], pr[r_t2] = 0.1, 0.2
    Y[[r_min, live[20], live[21]], 1] = np.nan           # t2 cannot train on the global minimum
    return X, Y, viable, pr, r_min, r_t2


def test_S1_fit_passes_priority_to_EACH_regressor_on_its_OWN_rows():
    X, Y, viable, pr, r_min, r_t2 = _priority_fixture()
    lr = GPLearner(n_restarts=0, random_state=0, max_points=30)
    m = S1Surrogate(_spec(), learner=lr, calibration_fraction=0.0)
    with pytest.warns(RuntimeWarning, match="subsampled"):
        m.fit(X, Y, viable, priority=pr, keep_best=2)
    for j, t in enumerate(m.spec.targets):
        fit_rows = np.flatnonzero(viable & np.isfinite(Y[:, j]))
        want = r_min if j == 0 else r_t2
        assert want == fit_rows[np.argmin(pr[fit_rows])]
        assert want not in fit_rows[np.random.default_rng(0).choice(len(fit_rows), 30,
                                                                    replace=False)], \
            "the fixture must be one where a plain draw drops this target's minimum"
        rows = m.train_rows_[j]
        assert want in rows and len(rows) == 30 == m._models[j].n_used
        assert set(rows) <= set(fit_rows)
        assert np.allclose(_rowsort(m._models[j].training_inputs()), _rowsort(X[rows]))
        assert np.isclose(m.target_sd_[j], np.std(apply_transform(Y[rows, j], t.transform)),
                          rtol=1e-12, atol=0)
    assert not np.array_equal(m.train_rows_[0], m.train_rows_[1])
    # A calibration split fits in permuted row order, so the subsample indices must be applied
    # to that order before the rows are sorted.
    mc = S1Surrogate(_spec(), learner=lr, calibration_fraction=0.3)
    with pytest.warns(RuntimeWarning, match="subsampled"):
        mc.fit(X, Y, viable, priority=pr, keep_best=2)
    for j in range(2):
        assert np.allclose(_rowsort(mc._models[j].training_inputs()),
                           _rowsort(X[mc.train_rows_[j]]))


def test_S1_fit_REFUSES_a_priority_the_learner_cannot_take():
    X, Y, viable = _data(60)
    with pytest.raises(ValueError, match="'rf'.*priority"):
        S1Surrogate(_spec(), learner="rf", calibration_fraction=0.0).fit(
            X, Y, viable, priority=np.arange(60.0))
    with pytest.raises(ValueError, match="priority"):
        S1Surrogate(_spec(), learner=_gp(), calibration_fraction=0.0).fit(
            X, Y, viable, keep_best=3)


def test_a_MISSIZED_priority_and_a_negative_or_FRACTIONAL_keep_best_are_refused():
    """A priority one row short would otherwise rank rows against the wrong entries without an
    error, and a fractional keep_best would be silently truncated."""
    n, mp = 40, 10
    X, y, _ = _gp_rows(n)
    pr = np.arange(n, dtype=float)
    for cap in (mp, n):                                   # with and without a subsample
        with pytest.raises(ValueError, match=f"priority has {n - 1} entries, X has {n} rows"):
            GPLearner(max_points=cap, n_restarts=0).fit(X, y, priority=pr[:-1], keep_best=2)
    with pytest.raises(ValueError, match=r"keep_best must be in \[0, max_points"):
        GPLearner(max_points=mp, n_restarts=0).fit(X, y, priority=pr, keep_best=-1)
    with pytest.raises(ValueError, match="whole number"):
        GPLearner(max_points=mp, n_restarts=0).fit(X, y, priority=pr, keep_best=2.9)
    g = GPLearner(max_points=mp, n_restarts=0, random_state=0)
    with pytest.warns(RuntimeWarning, match="keeping the 2 lowest-priority rows"):
        g.fit(X, y, priority=pr, keep_best=2.0)
    assert {0, 1} <= set(g.train_idx_), "an integral float keep_best is accepted as that int"
    Xs, Ys, viable = _data(60)
    with pytest.raises(ValueError, match="priority has 59 entries, X has 60 rows"):
        S1Surrogate(_spec(), learner=_gp(), calibration_fraction=0.0).fit(
            Xs, Ys, viable, priority=np.arange(59.0), keep_best=1)


def test_train_rows_and_target_sd_without_a_subsample():
    X, Y, viable, _, r_min, _ = _priority_fixture()
    m = S1Surrogate(_spec(), learner=_gp(), calibration_fraction=0.0).fit(X, Y, viable)
    for j, t in enumerate(m.spec.targets):
        rows = np.flatnonzero(viable & np.isfinite(Y[:, j]))
        assert np.array_equal(m.train_rows_[j], rows)
        assert np.isclose(m.target_sd_[j], np.std(apply_transform(Y[rows, j], t.transform)),
                          rtol=1e-12, atol=0)
    assert (r_min in m.train_rows_[0]) and (r_min not in m.train_rows_[1])


def test_trains_on_is_per_regressor_EXACT_and_sees_believed_points():
    X, Y, viable, _, r_min, _ = _priority_fixture()
    m = S1Surrogate(_spec(), learner=_gp(), calibration_fraction=0.0).fit(X, Y, viable)
    both = np.flatnonzero(viable & np.all(np.isfinite(Y), axis=1))[0]
    assert np.array_equal(m.trains_on(X[both]), [True, True])
    assert np.array_equal(m.trains_on(X[r_min]), [True, False]), "t2 never saw that row"
    assert np.array_equal(m.trains_on(X[np.flatnonzero(~viable)[0]]), [False, False])
    one_coord = X[both] + np.array([1e-6, 0.0])
    assert np.array_equal(m.trains_on(one_coord), [False, False]), "L-inf: one coordinate off"
    assert np.array_equal(m.trains_on(X[both] + 1e-12), [True, True]), "within 1e-9 of range"
    pick = np.array([0.555, 0.444])
    assert np.array_equal(m.believe(pick[None, :]).trains_on(pick), [True, True])
    assert np.array_equal(m.trains_on(pick), [False, False])
    with pytest.raises(ValueError, match="one point"):
        m.trains_on(X[:2])
    with pytest.raises(ValueError, match="training_inputs"):
        _fit(cf=0.0, learner="rf")[0].trains_on(X[both])


def test_trains_on_tolerance_is_1e_9_of_EACH_input_range_not_an_absolute_1e_9():
    """Input ranges of 1e3 and 1e-3: the tolerances are 1e-6 and 1e-12. A 5e-7 offset on the
    wide input is still the training point and a 1e-11 offset on the narrow one is not, which
    an absolute 1e-9, or one tolerance shared by both inputs, gets wrong in one direction."""
    lower, upper = (0.0, 100.0), (1e3, 100.001)
    rng = np.random.default_rng(4)
    X = np.column_stack([rng.uniform(lower[0], upper[0], 40),
                         rng.uniform(lower[1], upper[1], 40)])
    Y = np.column_stack([1.0 + X[:, 0] / 1e3, 2.0 + (X[:, 1] - 100.0) * 1e3])
    m = S1Surrogate(_spec(lower=lower, upper=upper), learner=_gp(),
                    calibration_fraction=0.0).fit(X, Y)
    x = X[3]
    assert np.array_equal(m.trains_on(x), [True, True])
    assert np.array_equal(m.trains_on(x + [5e-7, 0.0]), [True, True]), "within 1e-6 on input a"
    assert np.array_equal(m.trains_on(x + [2e-6, 0.0]), [False, False]), "beyond 1e-6 on a"
    assert np.array_equal(m.trains_on(x + [0.0, 1e-11]), [False, False]), "beyond 1e-12 on b"


def test_train_rows_target_sd_and_trains_on_SURVIVE_save_and_load(tmp_path):
    X, Y, viable, _, r_min, _ = _priority_fixture()
    m = S1Surrogate(_spec(), learner=_gp(), calibration_fraction=0.0).fit(X, Y, viable)
    m.save(tmp_path / "art")
    back = load(tmp_path / "art", strict=False)
    assert all(np.array_equal(a, b) for a, b in zip(back.train_rows_, m.train_rows_))
    assert np.array_equal(back.target_sd_, m.target_sd_)
    assert np.array_equal(back.trains_on(X[r_min]), [True, False])
    mu0, sd0 = m.posterior(X[:6])
    mu1, sd1 = back.posterior(X[:6])
    assert np.array_equal(mu0, mu1) and np.array_equal(sd0, sd1)


# -----------------------------------------------------------------------------------------------
# Acceptance report for an uncalibrated S1
# -----------------------------------------------------------------------------------------------

class _TierS1WithoutIntervals(SurrogateModel):
    """A tier-S1 model that is NOT an S1Surrogate and returns no intervals."""

    calibrated = False

    def __init__(self, inner):
        super().__init__(inner.spec)
        self.inner, self.fitted = inner, True

    def fit(self, X, Y, viable=None):
        return self

    def predict_batch(self, X):
        return BatchPrediction(spec=self.spec, values=self.inner.predict_batch(X).values)

    def _save_artifacts(self, directory):
        raise NotImplementedError


def test_run_acceptance_says_an_UNCALIBRATED_S1_may_not_rule_anything_out():
    """The note keys on the MODEL (an S1Surrogate with calibrated False), not on the tier: a
    tier-S1 model of another class without intervals keeps the generic note."""
    Xt, Yt, vt = _data(60, seed=1)
    Xt, Yt = Xt[vt], Yt[vt]

    def notes(model):
        return run_acceptance(model, Xt, Yt).notes

    m0 = _fit(cf=0.0)[0]
    s1_notes = notes(m0)
    new = [n for n in s1_notes if "without a calibration split" in n]
    assert len(new) == 1 and "claims no intervals" in new[0] and "rule anything out" in new[0]
    assert not any("tier produces no intervals" in n for n in s1_notes)
    assert not any("calibration split" in n for n in notes(_fit(cf=0.3)[0]))
    X, Y, viable = _data(120)
    s0 = S0Surrogate(dataclasses.replace(_spec(), tier="S0"), learner=_gp()).fit(X, Y, viable)
    s0_notes = notes(s0)
    assert any("tier produces no intervals" in n for n in s0_notes)
    assert not any("calibration split" in n for n in s0_notes)
    other = notes(_TierS1WithoutIntervals(m0))
    assert any("tier produces no intervals" in n for n in other)
    assert not any("calibration split" in n for n in other)


def test_run_acceptance_names_a_BELIEVED_copy_and_does_not_call_it_calibration_fraction_zero():
    """A Kriging-believer copy of a CALIBRATED model has calibration_fraction 0.3 and no
    intervals. Detecting "uncalibrated" from calibration_fraction would give it the generic
    note; reusing the calibration_fraction=0 note would misstate how it was fitted."""
    Xt, Yt, vt = _data(60, seed=1)
    Xt, Yt = Xt[vt], Yt[vt]
    pick = np.array([[0.5, 0.5]])
    for cf in (0.3, 0.0):
        b = _fit(cf=cf)[0].believe(pick)
        assert b.calibration_fraction == cf and b.believed and not b.calibrated
        b_notes = run_acceptance(b, Xt, Yt).notes
        new = [n for n in b_notes if "Kriging-believer copy" in n]
        assert len(new) == 1, (cf, b_notes)
        assert "fake observations" in new[0] and "rule anything out" in new[0]
        assert not any("calibration_fraction=0" in n for n in b_notes), (cf, b_notes)
        assert not any("tier produces no intervals" in n for n in b_notes), (cf, b_notes)
