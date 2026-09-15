"""KGMLEmulator: (theta, drivers) -> trajectories, with branch wiring and a mass-balance hinge.

The capability being tested is the one a ROM cannot have: the emulator is conditioned on the DAILY
DRIVERS, so it can be asked about weather it never trained on. Everything else here guards a way
that conditioning could be faked or a physics term could be imposed without justification.
"""
from __future__ import annotations

import numpy as np
import pytest

torch = pytest.importorskip("torch", reason="KGMLEmulator needs torch")

from models.surrogate.sequence import KGMLEmulator, load_kgml       # noqa: E402
from models.surrogate.spec import Provenance, SurrogateSpec, TargetSpec  # noqa: E402


def _case(n=60, d=120, seed=0):
    """Fluxes driven BOTH by theta and by the daily drivers, with NEE = GPP - Reco exactly.

    Built so a theta-only model cannot succeed: the driver term carries real variance.
    """
    rng = np.random.default_rng(seed)
    X = rng.uniform(0.0, 1.0, size=(n, 3))
    t = np.arange(d)
    temp = 15.0 + 10.0 * np.sin(2 * np.pi * t / 60.0) + rng.normal(0, 0.5, d)
    rad = 150.0 + 80.0 * np.sin(2 * np.pi * t / 60.0) + rng.normal(0, 5.0, d)
    M = np.column_stack([rad, temp]).astype("f4")
    years = np.repeat([2001, 2002], d // 2)

    GPP = np.empty((n, d)); RA = np.empty((n, d)); RH = np.empty((n, d))
    for i in range(n):
        a, b, c = X[i]
        GPP[i] = (0.5 + 2.0 * a) * (rad / 150.0) + 0.02 * rng.normal(size=d)
        RA[i] = (0.2 + 1.0 * b) * np.exp(0.05 * (temp - 15.0)) + 0.01 * rng.normal(size=d)
        RH[i] = (0.2 + 0.8 * c) * np.exp(0.06 * (temp - 15.0)) + 0.01 * rng.normal(size=d)
    NEE = GPP - (RA + RH)
    traj = np.stack([GPP, RA, RH, NEE], axis=1)
    names = ["GPP", "RA", "RH", "NEE"]
    spec = SurrogateSpec(
        name="syn", tier="S3", use_mode="online_inference",
        input_names=["a", "b", "c"], input_lower=(0.0,) * 3, input_upper=(1.0,) * 3,
        targets=[TargetSpec(k, observed=1.0) for k in names],
        provenance=Provenance(model="test"))
    return X, traj, M, years, spec, names


def _fit(X, traj, M, years, spec, **kw):
    kw.setdefault("mass_balance", {"GPP": 1.0, "RA": -1.0, "RH": -1.0, "NEE": -1.0})
    # the respiration terms are the denominator, as in KGML: they are bounded away from zero
    # all year while GPP is not
    kw.setdefault("mass_balance_scale", ["RA", "RH"])
    kw.setdefault("mass_balance_tol", 0.02)
    m = KGMLEmulator(spec, driver_names=["rad", "temp"], time_index=years,
                     hidden=24, layers=1, dropout=0.0, epochs=12, batch_size=16,
                     chunk_days=60, random_state=0, **kw)
    return m.fit(X, None, trajectories=traj, drivers=M, verbose=False)


def test_a_declared_mass_balance_without_a_tolerance_is_REFUSED():
    """THE guard. KGML's tol_MB = 0.01 belongs to ecosys; a tolerance is a claim about how
    tightly a particular process model closes its own budget, and porting one unchecked is how a
    physics term ends up fighting the data."""
    _, _, _, years, spec, _ = _case()
    with pytest.raises(ValueError, match="without `mass_balance_tol`"):
        KGMLEmulator(spec, driver_names=["rad", "temp"], time_index=years,
                     mass_balance={"GPP": 1.0, "RA": -1.0}, mass_balance_scale=["RA"])


def test_it_predicts_a_trajectory_of_the_right_shape():
    X, traj, M, years, spec, names = _case()
    m = _fit(X, traj, M, years, spec)
    P = m.predict_trajectories(X[:5], M)
    assert P.shape == (5, len(names), M.shape[0])
    assert np.isfinite(P).all()


def test_it_RESPONDS_to_drivers_it_was_not_given_before():
    """The capability a theta-only ROM cannot have. Change the weather, the prediction must move.

    A model that ignored its driver channel would return the same series for any weather, which is
    exactly what a ROM conditioned only on theta does.
    """
    X, traj, M, years, spec, _ = _case()
    m = _fit(X, traj, M, years, spec)
    warm = M.copy(); warm[:, 1] += 6.0          # a warmer year the model never saw
    base = m.predict_trajectories(X[:8], M)
    alt = m.predict_trajectories(X[:8], warm)
    rel = np.abs(alt - base).mean() / np.abs(base).mean()
    assert rel > 0.02, (
        f"changing the drivers moved the prediction by only {rel:.4%}; the emulator is "
        f"effectively ignoring its driver channel")


def test_it_RESPONDS_to_theta():
    """The other half: two parameter vectors must not give the same answer."""
    X, traj, M, years, spec, _ = _case()
    m = _fit(X, traj, M, years, spec)
    P = m.predict_trajectories(X[:16], M)
    spread = P.std(axis=0).mean()
    assert spread > 1e-3, f"predictions barely vary across theta (spread {spread:.2e})"


def test_the_branch_wiring_changes_the_computation():
    """`branch_of` must actually route parents into the child's input, not be decorative."""
    X, traj, M, years, spec, names = _case()
    plain = _fit(X, traj, M, years, spec)
    wired = _fit(X, traj, M, years, spec, branch_of={"NEE": ["GPP", "RA", "RH"]})
    j = names.index("NEE")
    a = plain.predict_trajectories(X[:8], M)[:, j]
    b = wired.predict_trajectories(X[:8], M)[:, j]
    assert not np.allclose(a, b), "wiring NEE to its parents changed nothing"
    # and the wired net must have a wider input on that branch
    assert (wired._net.branch["NEE"].input_size
            == plain._net.branch["NEE"].input_size + 3)


def test_refusals_on_malformed_structure():
    _, _, _, years, spec, _ = _case()
    kw = dict(driver_names=["rad", "temp"], time_index=years,
              mass_balance={"GPP": 1.0}, mass_balance_scale=["GPP"], mass_balance_tol=0.01)
    with pytest.raises(ValueError, match="not a target"):
        KGMLEmulator(spec, branch_of={"Nope": ["GPP"]}, **kw)
    with pytest.raises(ValueError, match="chained branches"):
        KGMLEmulator(spec, branch_of={"NEE": ["RA"], "RA": ["GPP"]}, **kw)
    with pytest.raises(ValueError, match="not a target"):
        KGMLEmulator(spec, driver_names=["rad", "temp"], time_index=years,
                     mass_balance={"Nope": 1.0}, mass_balance_scale=["GPP"],
                     mass_balance_tol=0.01)


def test_fit_without_drivers_is_refused():
    X, traj, M, years, spec, _ = _case()
    m = KGMLEmulator(spec, driver_names=["rad", "temp"], time_index=years,
                     mass_balance={"GPP": 1.0}, mass_balance_scale=["GPP"],
                     mass_balance_tol=0.01)
    with pytest.raises(ValueError, match="needs both"):
        m.fit(X, None, trajectories=traj)


def test_round_trips_through_save_and_load(tmp_path):
    X, traj, M, years, spec, _ = _case()
    m = _fit(X, traj, M, years, spec, branch_of={"NEE": ["GPP", "RA", "RH"]})
    before = m.predict_trajectories(X[:4], M)
    m.save(tmp_path)
    again = load_kgml(tmp_path, spec)
    assert np.allclose(again.predict_trajectories(X[:4], M), before, atol=1e-5), (
        "a reloaded emulator predicts differently than the one that was saved")
    assert again.branch_of == {"NEE": ["GPP", "RA", "RH"]}


def test_a_mass_balance_without_a_SCALE_is_refused():
    """The denominator of a relative hinge must be a declared choice.

    Measured on EcoSIM_Lusignan R1b: using |GPP| as the scale gives a p99 relative residual of
    74748 against 0.91 for |RA + RH|, because GPP reaches exactly zero in winter while respiration
    floors at 0.0015. KGML divides by the respiration terms for that reason, and the reason is
    stated nowhere in the paper or the library.
    """
    _, _, _, years, spec, _ = _case()
    with pytest.raises(ValueError, match="without `mass_balance_scale`"):
        KGMLEmulator(spec, driver_names=["rad", "temp"], time_index=years,
                     mass_balance={"GPP": 1.0, "RA": -1.0}, mass_balance_tol=0.01)
