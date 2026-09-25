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


def test_it_round_trips_through_the_GENERIC_loader_with_its_provenance_checked(tmp_path):
    """`tiers.load` is the loader every consumer calls. It must reach this class by the name in
    `tier.json` rather than by the tier, because the spec declares S3 and the S3 branch expects a
    different file. Through it the artifact's own spec is read and a stated provenance is compared,
    neither of which `load_kgml` does when called directly.
    """
    from models.surrogate.tiers import load
    X, traj, M, years, spec, _ = _case()
    m = _fit(X, traj, M, years, spec)
    m.save(tmp_path / "art")
    back = load(tmp_path / "art", strict=False)
    assert isinstance(back, KGMLEmulator)
    assert np.array_equal(m.predict_trajectories(X[:4], M), back.predict_trajectories(X[:4], M))
    assert np.array_equal(m.predict_batch(X[:4], M).values, back.predict_batch(X[:4], M).values)
    with pytest.raises(ValueError, match="provenance mismatch"):
        load(tmp_path / "art", expect=Provenance(model="another_model"))


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


# ---------------------------------------------------------------------------
# The loss terms that target WITHIN-CASE structure.
#
# The data loss is MSE on Y standardised per target over cases AND time, so its denominator is
# dominated by between-case spread: a prediction at roughly each case's own level already scores
# well while its shape in time is free. `anomaly_weight` removes each window's own mean before the
# MSE, and `diff_weight` scores the step-to-step change. Both default to 0.0, so an existing fit is
# unchanged.
# ---------------------------------------------------------------------------

def test_the_new_terms_default_OFF_and_leave_the_fit_bit_identical():
    """The switch-off case must reproduce the old behaviour exactly, or nothing below is comparable."""
    X, traj, M, years, spec, _ = _case()
    a = _fit(X, traj, M, years, spec)
    b = _fit(X, traj, M, years, spec, anomaly_weight=0.0, diff_weight=0.0)
    pa = a.predict_trajectories(X[:4], M)
    pb = b.predict_trajectories(X[:4], M)
    assert np.array_equal(pa, pb)


@pytest.mark.parametrize("kw", [{"anomaly_weight": 1.0}, {"diff_weight": 1.0}])
def test_each_term_actually_changes_the_fit(kw):
    """A weight that is stored but never reaches the objective is a setting that does nothing."""
    X, traj, M, years, spec, _ = _case()
    base = _fit(X, traj, M, years, spec)
    tuned = _fit(X, traj, M, years, spec, **kw)
    assert not np.allclose(base.predict_trajectories(X[:4], M),
                           tuned.predict_trajectories(X[:4], M))


def test_the_anomaly_term_is_BLIND_to_a_per_case_level_shift():
    """The property that makes it the right term, asserted on the arithmetic rather than a fit.

    Shifting a whole window by a constant leaves its shape untouched. Plain MSE sees the shift;
    the mean-removed term does not. That difference is the entire point.
    """
    from torch import nn
    yb = torch.tensor([[[0.0], [1.0], [2.0], [1.0]]])          # (B=1, T=4, L=1)
    shifted = yb + 7.0
    mse = nn.MSELoss()
    assert float(mse(shifted, yb)) == pytest.approx(49.0)
    anom = mse(shifted - shifted.mean(dim=1, keepdim=True), yb - yb.mean(dim=1, keepdim=True))
    assert float(anom) == pytest.approx(0.0, abs=1e-12)


def test_the_diff_term_PUNISHES_a_flat_prediction_at_the_right_mean():
    """The failure mode both emulators showed: right level, wrong dynamics.

    A flat line at the window mean is what a level-dominated objective is happy with. The
    difference term is not: the truth moves at every step and the prediction moves at none.
    """
    from torch import nn
    yb = torch.tensor([[[0.0], [2.0], [0.0], [2.0]]])
    flat = torch.full_like(yb, float(yb.mean()))
    mse = nn.MSELoss()
    d_true, d_pred = yb[:, 1:] - yb[:, :-1], flat[:, 1:] - flat[:, :-1]
    assert float(mse(d_pred, d_true)) == pytest.approx(4.0)     # every step missed
    assert float(mse(flat - flat.mean(dim=1, keepdim=True),
                     yb - yb.mean(dim=1, keepdim=True))) == pytest.approx(1.0)


def test_the_VALIDATION_loss_carries_the_same_terms_as_the_training_loss():
    """The checkpoint must be chosen on the objective the fit is minimising, not on part of it.

    `_nn.fit_torch` states this in its docstring and enforces it structurally by passing ONE
    `batch_loss` to both sides. `KGMLEmulator` runs its own loop, so until 2026-09-22 its
    validation loss was a bare MSE while its training loss carried the anomaly, difference and
    mass-balance terms: every fit chose its weights on level-only error whatever objective it was
    trained against, the 20260916a ablation included.

    `val` is the objective, `val_data` the plain MSE kept beside it. With a non-zero anomaly weight
    the two must differ, and `val` must be the larger, because the extra term is non-negative.
    """
    X, traj, M, years, spec, _ = _case(n=12, d=30)
    m = _fit(X, traj, M, years, spec, **_nomb(anomaly_weight=1.0))
    assert m.history, "no epochs recorded"
    for h in m.history:
        assert "val" in h and "val_data" in h
        assert h["val"] >= h["val_data"] - 1e-9, h
    assert any(h["val"] > h["val_data"] + 1e-9 for h in m.history), \
        "the anomaly term never reached the validation loss"


def test_with_NO_extra_terms_the_two_validation_numbers_AGREE():
    """The other half: a plain fit must not have its recorded loss shifted by this change.

    Without it the fix could have been written to add a term unconditionally, which would make
    every historical `val` incomparable with a new one rather than only the ones that asked for a
    shaped objective.
    """
    X, traj, M, years, spec, _ = _case(n=12, d=30)
    m = _fit(X, traj, M, years, spec, **_nomb())
    for h in m.history:
        assert h["val"] == pytest.approx(h["val_data"], rel=1e-9, abs=1e-12), h


def test_the_weights_round_trip_through_save_and_load(tmp_path):
    """A reloaded artifact must record the objective it was trained against."""
    X, traj, M, years, spec, _ = _case()
    m = _fit(X, traj, M, years, spec, anomaly_weight=0.5, diff_weight=0.25)
    m.save(tmp_path / "art")
    back = load_kgml(tmp_path / "art", spec, strict=False)
    assert back.anomaly_weight == 0.5 and back.diff_weight == 0.25
    assert np.array_equal(m.predict_trajectories(X[:4], M),
                          back.predict_trajectories(X[:4], M))


def test_an_artifact_saved_BEFORE_these_terms_existed_still_loads(tmp_path):
    """Old bundles carry no such keys; they must default rather than refuse."""
    X, traj, M, years, spec, _ = _case()
    m = _fit(X, traj, M, years, spec)
    m.save(tmp_path / "art")
    blob = torch.load(tmp_path / "art" / "kgml.pt", weights_only=False, map_location="cpu")
    blob["cfg"].pop("anomaly_weight"); blob["cfg"].pop("diff_weight")
    torch.save(blob, tmp_path / "art" / "kgml.pt")
    back = load_kgml(tmp_path / "art", spec, strict=False)
    assert back.anomaly_weight == 0.0 and back.diff_weight == 0.0


# ---------------------------------------------------------------------------
# The transformer encoder.
#
# Selected by cell="transformer", with the same trunk-plus-branches shape as the recurrent cells.
# The one property that is not shared: a recurrent cell is causal by construction, and an attention
# encoder is not unless it is masked.
# ---------------------------------------------------------------------------

def test_a_transformer_fit_runs_and_predicts_the_right_shape():
    X, traj, M, years, spec, names = _case(n=20, d=60)
    m = _fit(X, traj, M, years, spec, cell="transformer")
    assert m.predict_trajectories(X[:3], M).shape == (3, len(names), 60)


def test_the_ATTENTION_IS_CAUSAL_so_a_step_cannot_see_its_future():
    """THE property that decides whether the artifact is an emulator or a smoother.

    Two driver records identical up to step k and different after it must produce identical
    predictions at every step up to k. An unmasked encoder fails this, and the failure is invisible
    in any accuracy metric computed on a whole window -- it simply scores better.
    """
    X, traj, M, years, spec, _ = _case(n=20, d=60)
    m = _fit(X, traj, M, years, spec, cell="transformer")
    k = 30
    M2 = M.copy()
    M2[k:] = M2[k:] * 3.0 + 50.0                      # a large, obvious change, future-only
    a = m.predict_trajectories(X[:2], M)
    b = m.predict_trajectories(X[:2], M2)
    assert np.allclose(a[:, :, :k], b[:, :, :k], atol=1e-5), "a step saw its own future"
    assert not np.allclose(a[:, :, k:], b[:, :, k:]), "the change had no effect at all; test is inert"


def test_an_unmasked_encoder_WOULD_fail_that_test():
    """The negative control: without the mask, information flows backwards in time.

    Asserted on the encoder in isolation, so the guarantee is pinned to the mask rather than to
    whatever the fitted weights happen to do.
    """
    from torch import nn
    T, D = 12, 4
    enc = nn.TransformerEncoder(
        nn.TransformerEncoderLayer(D, 2, dim_feedforward=8, dropout=0.0,
                                   batch_first=True, norm_first=True),
        1, enable_nested_tensor=False).eval()
    x = torch.randn(1, T, D)
    # A perturbation that varies ACROSS FEATURES. A uniform shift is removed by the first
    # LayerNorm, which makes the control inert while still looking like a large change.
    x2 = x.clone(); x2[:, T // 2:] = x2[:, T // 2:] * 3.0 + torch.tensor([5.0, -3.0, 2.0, -4.0])
    causal = torch.triu(torch.ones(T, T, dtype=torch.bool), diagonal=1)
    with torch.no_grad():
        free_a, free_b = enc(x), enc(x2)
        mask_a, mask_b = enc(x, mask=causal), enc(x2, mask=causal)
    assert not torch.allclose(free_a[:, :T // 2], free_b[:, :T // 2], atol=1e-6)
    assert torch.allclose(mask_a[:, :T // 2], mask_b[:, :T // 2], atol=1e-6)


def test_a_hidden_size_not_divisible_by_nhead_is_REFUSED_at_construction():
    """Caught when the object is built, not with a torch shape error part-way through a fit."""
    X, traj, M, years, spec, _ = _case(n=10, d=30)
    with pytest.raises(ValueError, match="divisible by nhead"):
        KGMLEmulator(spec, driver_names=["rad", "temp"], time_index=years,
                     cell="transformer", hidden=30, nhead=4)


def test_the_nhead_refusal_covers_the_GRAPH_layer_too_not_only_the_transformer():
    """`nhead` has two consumers and the guard covered one of them until 2026-09-22.

    A recurrent cell plus a spatial_graph reaches `nn.MultiheadAttention(hidden, nhead)` just as a
    transformer does, so an indivisible pair used to construct cleanly and die part-way through the
    first fit on torch's own bare `AssertionError: embed_dim must be divisible by num_heads`.
    """
    X, traj, M, years, spec, _ = _case(n=10, d=30)
    with pytest.raises(ValueError, match="divisible by nhead"):
        KGMLEmulator(spec, driver_names=["rad", "temp"], time_index=years,
                     cell="gru", hidden=30, nhead=4, spatial_graph=[("GPP", "RA")])


def test_a_recurrent_cell_with_NO_graph_ignores_nhead_entirely():
    """The other half of the contract: nothing consumes nhead, so no pair is refused.

    Without this, the fix above could have been written as an unconditional divisibility rule,
    which would refuse a perfectly good plain GRU for a parameter it never reads.
    """
    X, traj, M, years, spec, _ = _case(n=10, d=30)
    m = KGMLEmulator(spec, driver_names=["rad", "temp"], time_index=years,
                     cell="gru", hidden=30, nhead=4)
    assert m.hidden == 30 and m.nhead == 4 and not m.spatial_graph


def test_an_unknown_cell_is_REFUSED_and_the_message_names_the_cells():
    X, traj, M, years, spec, _ = _case(n=10, d=30)
    with pytest.raises(ValueError, match="transformer' or 'tcn'"):
        KGMLEmulator(spec, driver_names=["rad", "temp"], time_index=years, cell="mamba")


def test_the_transformer_round_trips_through_save_and_load(tmp_path):
    X, traj, M, years, spec, _ = _case(n=20, d=60)
    m = _fit(X, traj, M, years, spec, cell="transformer")
    m.save(tmp_path / "art")
    back = load_kgml(tmp_path / "art", spec, strict=False)
    assert back.cell == "transformer" and back.nhead == m.nhead
    assert np.array_equal(m.predict_trajectories(X[:3], M),
                          back.predict_trajectories(X[:3], M))


# ---------------------------------------------------------------------------
# Temporal convolutions. Causal by LEFT padding; a convolution padded on both sides reads the steps
# after the one it predicts, which is the same leak an unmasked attention encoder has.
# ---------------------------------------------------------------------------

def test_a_tcn_fit_runs_and_predicts_the_right_shape():
    X, traj, M, years, spec, names = _case(n=20, d=60)
    m = _fit(X, traj, M, years, spec, cell="tcn")
    assert m.predict_trajectories(X[:3], M).shape == (3, len(names), 60)


def test_the_TCN_IS_CAUSAL_so_a_step_cannot_see_its_future():
    X, traj, M, years, spec, _ = _case(n=20, d=60)
    m = _fit(X, traj, M, years, spec, cell="tcn")
    k = 30
    M2 = M.copy()
    M2[k:] = M2[k:] * 3.0 + 50.0
    a = m.predict_trajectories(X[:2], M)
    b = m.predict_trajectories(X[:2], M2)
    assert np.array_equal(a[:, :, :k], b[:, :, :k]), "a step saw its own future"
    assert not np.allclose(a[:, :, k:], b[:, :, k:]), "the change had no effect at all; test is inert"


def test_a_convolution_padded_on_BOTH_sides_WOULD_fail_that_test():
    """The negative control: centred padding lets step t read t+1."""
    conv = torch.nn.Conv1d(2, 2, 3, padding=1)
    x = torch.randn(1, 2, 20)
    y = x.clone()
    y[:, :, 10:] = y[:, :, 10:] * 3.0 + 5.0
    with torch.no_grad():
        assert not torch.allclose(conv(x)[:, :, :10], conv(y)[:, :, :10], atol=1e-6)


def test_the_TCN_memory_ends_at_its_RECEPTIVE_FIELD():
    """Unlike a recurrent cell, nothing older than the receptive field can reach a prediction."""
    X, traj, M, years, spec, _ = _case(n=20, d=60)
    m = _fit(X, traj, M, years, spec, cell="tcn")
    rf = m._net.trunk.receptive_field + m._net.branch["GPP"].receptive_field - 1
    early = M.copy()
    early[0] = early[0] * 3.0 + 50.0
    a = m.predict_trajectories(X[:2], M)
    b = m.predict_trajectories(X[:2], early)
    assert not np.allclose(a[:, :, 0], b[:, :, 0]), "the change had no effect at all; test is inert"
    assert np.array_equal(a[:, :, rf:], b[:, :, rf:]), "a step saw further back than the receptive field"


def test_a_tcn_kernel_below_two_is_REFUSED():
    X, traj, M, years, spec, _ = _case(n=10, d=30)
    with pytest.raises(ValueError, match="tcn_kernel"):
        KGMLEmulator(spec, driver_names=["rad", "temp"], time_index=years, cell="tcn", tcn_kernel=1)


def test_the_tcn_round_trips_through_save_and_load(tmp_path):
    X, traj, M, years, spec, _ = _case(n=20, d=60)
    m = _fit(X, traj, M, years, spec, cell="tcn", tcn_kernel=4)
    m.save(tmp_path / "art")
    back = load_kgml(tmp_path / "art", spec, strict=False)
    assert back.cell == "tcn" and back.tcn_kernel == 4
    assert np.array_equal(m.predict_trajectories(X[:3], M),
                          back.predict_trajectories(X[:3], M))


# ---------------------------------------------------------------------------
# Graph attention over the target axis.
#
# For a case whose targets are the same quantity at several locations, the declared graph says
# which locations may inform which. Off unless a graph is given.
# ---------------------------------------------------------------------------

def _nomb(**kw):
    """The fixture wires a mass balance by default; a spatial case here declares none."""
    kw.update(mass_balance=None, mass_balance_scale=None, mass_balance_tol=None)
    return kw


def test_no_graph_declared_leaves_the_network_unchanged():
    X, traj, M, years, spec, _ = _case(n=20, d=60)
    a = _fit(X, traj, M, years, spec)
    assert a._net.graph is None
    b = _fit(X, traj, M, years, spec, spatial_graph=[])
    assert np.array_equal(a.predict_trajectories(X[:3], M), b.predict_trajectories(X[:3], M))


def test_the_ADJACENCY_IS_RESPECTED_so_an_unconnected_target_cannot_inform_another():
    """THE property of a declared graph: a target draws on its neighbours and on nothing else.

    Asserted on the layer, driven with a perturbation in one target's row, because at inference
    every target sees the same theta and drivers -- there is no per-target input to vary.
    """
    X, traj, M, years, spec, names = _case(n=20, d=60)
    m = _fit(X, traj, M, years, spec, **_nomb(spatial_graph=[("GPP", "RA")]))
    layer = m._net.graph.eval()
    dev = next(layer.parameters()).device          # the fit may have run on a GPU
    L, H = len(names), m.hidden
    base = torch.zeros(1, 1, L, H, device=dev)
    bumped = base.clone()
    bumped[0, 0, names.index("GPP")] = 1.0                 # perturb GPP's representation only
    with torch.no_grad():
        a, b = layer(base), layer(bumped)
    moved = {n: not torch.allclose(a[0, 0, i], b[0, 0, i], atol=1e-6) for i, n in enumerate(names)}
    assert moved["RA"], "RA is connected to GPP and did not see it"
    assert not moved["RH"] and not moved["NEE"], "an unconnected target saw GPP"


def test_an_edge_naming_an_unknown_target_is_REFUSED():
    X, traj, M, years, spec, _ = _case(n=10, d=30)
    with pytest.raises(ValueError, match="do not exist"):
        KGMLEmulator(spec, driver_names=["rad", "temp"], time_index=years,
                     spatial_graph=[("GPP", "Nope")])


def test_a_graph_COMBINED_with_hierarchical_branches_is_REFUSED():
    """Not silently one-or-the-other: a wired branch consumes parent PREDICTIONS, produced after
    the graph layer would have mixed the representations they come from."""
    X, traj, M, years, spec, _ = _case(n=10, d=30)
    with pytest.raises(ValueError, match="cannot be combined"):
        KGMLEmulator(spec, driver_names=["rad", "temp"], time_index=years,
                     spatial_graph=[("GPP", "RA")], branch_of={"NEE": ["GPP"]})


def test_the_graph_round_trips_through_save_and_load(tmp_path):
    X, traj, M, years, spec, _ = _case(n=20, d=60)
    m = _fit(X, traj, M, years, spec, **_nomb(spatial_graph=[("GPP", "RA")]))
    m.save(tmp_path / "art")
    back = load_kgml(tmp_path / "art", spec, strict=False)
    assert back.spatial_graph == [("GPP", "RA")]
    assert np.array_equal(m.predict_trajectories(X[:3], M),
                          back.predict_trajectories(X[:3], M))


# -----------------------------------------------------------------------------
# A fit that was STOPPED is not a fit that converged
# -----------------------------------------------------------------------------

def test_a_fit_whose_BEST_EPOCH_IS_THE_LAST_says_so():
    """The budget, not the data, ended it -- and until 2026-09-22 nothing said so.

    Measured across every fit this class had produced: the miniLEO baseline's best epoch was 29 of
    29, the Lusignan KGML fit's 39 of 39, both loss-ablation arms' 28 of 29. On that evidence
    `20260916g` recorded "both had converged ... so it was not capacity and not under-training" and
    moved the investigation to the objective. A validation curve that never turns up has not
    converged; it was cut off. `_nn.fit_torch` warns for exactly this and this class's own loop did
    not.
    """
    X, traj, M, years, spec, _ = _case(n=12, d=30)
    with pytest.warns(RuntimeWarning, match="budget ended this fit"):
        m = _fit(X, traj, M, years, spec, **_nomb())
    assert m.fit_info_["best_epoch"] == m.epochs - 1
    assert m.fit_info_["stopped_by_patience"] is False
    assert m.fit_info_["epochs_run"] == m.epochs


def test_PATIENCE_stops_the_fit_and_the_record_says_which_rule_ended_it():
    """The other half: with patience set, a fit that stops early must not read as a budget cut.

    A diverging learning rate makes validation worsen immediately, so patience is what ends this
    fit. Without the distinction, "best epoch is not the last" would be the only signal and it
    cannot tell a converged fit from one killed by patience.
    """
    X, traj, M, years, spec, _ = _case(n=12, d=30)
    m = KGMLEmulator(spec, driver_names=["rad", "temp"], time_index=years,
                     hidden=8, layers=1, dropout=0.0, epochs=30, batch_size=16,
                     chunk_days=30, random_state=0, lr=5.0, patience=1,
                     mass_balance=None, mass_balance_scale=None, mass_balance_tol=None)
    m.fit(X, None, trajectories=traj, drivers=M, verbose=False)
    assert m.fit_info_["stopped_by_patience"] is True
    assert m.fit_info_["epochs_run"] < 30, m.fit_info_
    assert m.fit_info_["best_epoch"] < m.fit_info_["epochs_run"] - 1 or m.fit_info_["epochs_run"] == 2


def test_the_stopping_rule_ROUND_TRIPS_so_a_reload_reproduces_the_fit(tmp_path):
    """`patience` changes which weights an artifact holds, so it belongs in the saved config."""
    X, traj, M, years, spec, _ = _case(n=12, d=30)
    with pytest.warns(RuntimeWarning):
        m = _fit(X, traj, M, years, spec, **_nomb(patience=50))
    m.save(tmp_path / "art")
    back = load_kgml(tmp_path / "art", spec, strict=False, check_env=False)
    assert back.patience == 50
