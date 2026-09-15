"""S3Surrogate: S2 plus process structure, where the structure holds by construction.

The claim S3 makes that S2 cannot is POINTWISE: a derived target equals the sum of its components
at every timestep, for every learner, under any weights. A soft penalty makes that likely; these
tests assert it is exact, and that a wrong structural rule is refused rather than absorbed.
"""
from __future__ import annotations

import numpy as np
import pytest

from models.surrogate.spec import IMPLEMENTED_TIERS, Provenance, SurrogateSpec, TargetSpec
from models.surrogate.tiers import REDUCERS, S2Surrogate, S3Surrogate, load


def _case(n=200, d=120, seed=0, dip=False):
    """Synthetic ensemble where Reco = RA + RH holds exactly, as it does on the tape.

    With `dip`, ET approaches zero so a truncated basis reconstructs negative values —
    the condition the admissibility channel exists for.
    """
    rng = np.random.default_rng(seed)
    X = rng.uniform(0.0, 1.0, size=(n, 3))
    t = np.linspace(0.0, 4 * np.pi, d)
    years = np.repeat([2001, 2002, 2003, 2004], d // 4)
    GPP = np.empty((n, d)); RA = np.empty((n, d)); RH = np.empty((n, d)); ET = np.empty((n, d))
    for i in range(n):
        a, b, c = X[i]
        GPP[i] = 3.0 + 2.0 * a + (1.0 + b) * np.sin(t) + 0.03 * rng.normal(size=d)
        RA[i] = 1.0 + 1.5 * b + 0.4 * np.cos(t) + 0.02 * rng.normal(size=d)
        RH[i] = 0.8 + 1.0 * c + 0.3 * np.sin(t + 1.0) + 0.02 * rng.normal(size=d)
        if dip:
            # RECTIFIED: exactly zero for half the cycle, as ET is through winter. A truncated
            # SVD basis cannot represent the corner and rings below zero on either side of it,
            # which is the real condition the admissibility channel exists for.
            ET[i] = np.clip((1.0 + a) * np.sin(t), 0.0, None) + 0.01 * rng.normal(size=d)
        else:
            ET[i] = 1.5 + 0.8 * a + 1.2 * np.sin(t) ** 2 + 0.02 * rng.normal(size=d)
    traj = np.stack([GPP, RA, RH, RA + RH, ET], axis=1)          # Reco is index 3
    names = ["GPP", "RA", "RH", "Reco", "ET"]
    spec = SurrogateSpec(
        name="synthetic", tier="S3", use_mode="offline_search",
        input_names=["a", "b", "c"], input_lower=(0.0, 0.0, 0.0), input_upper=(1.0, 1.0, 1.0),
        targets=[TargetSpec(k, observed=1.0) for k in names],
        provenance=Provenance(model="test"))
    return X, traj, years, spec, names


def _fit(cls, X, traj, years, spec, **kw):
    Y = REDUCERS["annual_mean_sum"](traj, years)
    m = cls(spec, learner="rf", n_components=8, reduce="annual_mean_sum",
            time_index=years, random_state=0, **kw)
    return m.fit(X, Y, trajectories=traj)


def test_s3_is_in_the_registry():
    assert "S3" in IMPLEMENTED_TIERS


def test_the_composed_identity_holds_POINTWISE_not_just_on_average():
    """The whole point of the structural channel. Every timestep, not a small mean penalty."""
    X, traj, years, spec, names = _case()
    m = _fit(S3Surrogate, X, traj, years, spec,
             compose={"Reco": ["RA", "RH"]}, nonneg=["GPP", "RA", "RH", "Reco", "ET"])
    P = m.predict_trajectories(X[:20])
    i_reco, i_ra, i_rh = names.index("Reco"), names.index("RA"), names.index("RH")
    assert np.allclose(P[:, i_reco], P[:, i_ra] + P[:, i_rh], atol=1e-10), (
        "the derived target is not exactly its components' sum at every timestep")


def test_an_unstructured_S2_does_NOT_satisfy_the_identity():
    """The negative control that makes the test above meaningful rather than tautological."""
    X, traj, years, spec, names = _case()
    object.__setattr__(spec, "tier", "S2")
    m = _fit(S2Surrogate, X, traj, years, spec)
    P = m.predict_trajectories(X[:20])
    i_reco, i_ra, i_rh = names.index("Reco"), names.index("RA"), names.index("RH")
    resid = np.abs(P[:, i_reco] - (P[:, i_ra] + P[:, i_rh])).max()
    assert resid > 1e-8, (
        "S2 happened to satisfy the identity exactly, so the S3 test proves nothing here")


def test_a_WRONG_compose_rule_is_refused_at_fit():
    """A structural claim is a claim about the model and must be checked against the data."""
    X, traj, years, spec, _ = _case()
    with pytest.raises(ValueError, match="TRAINING trajectories disagree"):
        _fit(S3Surrogate, X, traj, years, spec, compose={"Reco": ["GPP", "RH"]})


def test_nonneg_clamps_and_RECORDS_how_often_it_had_to():
    """A constraint that silently repairs predictions hides how wrong the model was."""
    X, traj, years, spec, names = _case(dip=True)
    m = _fit(S3Surrogate, X, traj, years, spec,
             compose={"Reco": ["RA", "RH"]}, nonneg=["ET"])
    P = m.predict_trajectories(X[:40])
    assert (P[:, names.index("ET")] >= 0).all(), "a clamped target still returned negatives"
    assert "ET" in m.nonneg_violation_rate, "the violation rate was not recorded"
    assert m.nonneg_violation_rate["ET"] > 0, (
        "this fixture is meant to force violations; if none occur the test proves nothing")


def test_components_are_still_fitted_and_scored():
    """Deriving Reco must not remove RA and RH from the prediction."""
    X, traj, years, spec, names = _case()
    m = _fit(S3Surrogate, X, traj, years, spec, compose={"Reco": ["RA", "RH"]})
    b = m.predict_batch(X[:5])
    assert b.values.shape == (5, len(names))
    assert np.isfinite(b.values).all()


def test_refusals_on_a_malformed_structure():
    X, traj, years, spec, _ = _case()
    with pytest.raises(ValueError, match="not a target"):
        S3Surrogate(spec, compose={"Nope": ["RA"]}, reduce="annual_mean_sum", time_index=years)
    with pytest.raises(ValueError, match="not a target"):
        S3Surrogate(spec, compose={"Reco": ["Nope"]}, reduce="annual_mean_sum", time_index=years)
    with pytest.raises(ValueError, match="chained composition"):
        S3Surrogate(spec, compose={"Reco": ["RA", "RH"], "GPP": ["Reco"]},
                    reduce="annual_mean_sum", time_index=years)


def test_round_trips_through_save_and_load(tmp_path):
    X, traj, years, spec, names = _case()
    m = _fit(S3Surrogate, X, traj, years, spec,
             compose={"Reco": ["RA", "RH"]}, nonneg=["ET"])
    before = m.predict_trajectories(X[:4])
    m.save(tmp_path)
    again = load(tmp_path, expect=None)
    assert type(again).__name__ == "S3Surrogate"
    assert again.compose == {"Reco": ["RA", "RH"]}
    assert np.allclose(again.predict_trajectories(X[:4]), before)
    i_reco, i_ra, i_rh = names.index("Reco"), names.index("RA"), names.index("RH")
    P = again.predict_trajectories(X[:4])
    assert np.allclose(P[:, i_reco], P[:, i_ra] + P[:, i_rh], atol=1e-10), (
        "the reloaded model lost its structure")
