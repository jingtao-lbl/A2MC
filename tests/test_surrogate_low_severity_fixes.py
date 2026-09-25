"""The low-severity findings of the 2026-09-16 surrogate audits, each with a test that fails first.

One file rather than eight scattered additions, because these were recorded as a batch in
`memory/dev_logs_adapterkit/20260922a_Review_Of_The_Recent_Dev_Logs_And_The_Fix_Register.md`
(items C4 and F13/F19/F20/F22/F23) and a reader chasing any one of them wants the others.

Each test names the behaviour BEFORE the fix, so a later reader can tell what would regress.
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


# -----------------------------------------------------------------------------
# F13 — two --figure arguments sharing a basename
# -----------------------------------------------------------------------------

def test_two_figures_with_the_SAME_basename_are_REFUSED(tmp_path):
    """Before: the second overwrote the first and the manifest listed the name twice.

    `shasum -c` then passed over a bundle whose figures/ held one file where the manifest claimed
    two, so the recipient saw a caption describing an image that was not there.
    """
    import tools.package_surrogate as ps

    a = tmp_path / "one" / "fig.png"
    b = tmp_path / "two" / "fig.png"
    a.parent.mkdir(parents=True)
    b.parent.mkdir(parents=True)
    a.write_bytes(b"f1")
    b.write_bytes(b"f2")

    out = tmp_path / "bundle"
    (out / "figures").mkdir(parents=True)
    with pytest.raises(SystemExit) as e:
        ps._copy_figures([str(a), str(b)], out, [], [])
    assert "basename" in str(e.value)


def test_the_SAME_figure_named_twice_is_copied_once(tmp_path):
    """The complement: repeating one path is a caller convenience, not a collision."""
    import tools.package_surrogate as ps

    a = tmp_path / "fig.png"
    a.write_bytes(b"f1")
    out = tmp_path / "bundle"
    (out / "figures").mkdir(parents=True)
    written: list = []
    ps._copy_figures([str(a), str(a)], out, written, [])
    assert [p.name for p in written] == ["fig.png"]


# -----------------------------------------------------------------------------
# F19 — the device a reload lands on
# -----------------------------------------------------------------------------

def test_a_saved_emulator_RECORDS_the_device_its_fit_ran_on(tmp_path):
    """Before: nothing in the artifact said, and the loader used "cuda when available".

    cuDNN's recurrent kernels and the CPU ones do not agree bit for bit, so a CPU-fitted artifact
    reloaded onto a GPU predicts differently from the model that was saved.
    """
    torch = pytest.importorskip("torch")
    from models.surrogate.sequence import KGMLEmulator, load_kgml
    from models.surrogate.spec import Provenance, SurrogateSpec, TargetSpec

    rng = np.random.default_rng(0)
    n, d = 8, 24
    X = rng.uniform(0, 1, size=(n, 2))
    M = rng.normal(size=(d, 1)).astype("f4")
    traj = rng.normal(size=(n, 1, d))
    spec = SurrogateSpec(name="s", tier="S3", use_mode="online_inference",
                         input_names=["a", "b"], input_lower=(0.0, 0.0), input_upper=(1.0, 1.0),
                         targets=(TargetSpec("y"),), provenance=Provenance(model="test"))
    m = KGMLEmulator(spec, driver_names=["q"], hidden=8, layers=1, epochs=1,
                     chunk_days=12, device="cpu")
    m.fit(X, None, trajectories=traj, drivers=M, verbose=False)
    m.save(tmp_path / "art")

    blob = torch.load(tmp_path / "art" / "kgml.pt", weights_only=False, map_location="cpu")
    assert blob["cfg"]["fit_device"].startswith("cpu")

    back = load_kgml(tmp_path / "art", spec, strict=False, check_env=False)
    assert str(back.device).startswith("cpu"), "the reload ignored the recorded fit device"
    assert np.allclose(back.predict_trajectories(X[:2], M),
                       m.predict_trajectories(X[:2], M), atol=1e-6)


# -----------------------------------------------------------------------------
# F20 — a target whose observed value is zero
# -----------------------------------------------------------------------------

def test_an_observed_value_of_ZERO_is_refused_by_name(tmp_path):
    """Before: a bare ZeroDivisionError from inside the scoring loop.

    A relative band is undefined at zero. The refusal names the target so the fix is obvious.
    """
    from scripts.check_surrogate_gate import load_bands

    y = tmp_path / "targets.yaml"
    y.write_text("targets:\n"
                 "  outflow_Fe: {observed: 0.0, uncertainty: 0.25}\n"
                 "  outflow_Mn: {observed: 2.0, uncertainty: 0.25}\n")
    with pytest.raises(SystemExit) as e:
        load_bands(y)
    assert "outflow_Fe" in str(e.value) and "observed: 0" in str(e.value)


def test_normal_bands_still_load(tmp_path):
    """A gate that refused everything would be no better than one that crashed."""
    from scripts.check_surrogate_gate import load_bands

    y = tmp_path / "targets.yaml"
    y.write_text("targets:\n  a: {observed: 2.0, uncertainty: 0.25}\n")
    assert load_bands(y)["a"]["observed"] == 2.0


# -----------------------------------------------------------------------------
# F22 — validation-lattice edge cases
# -----------------------------------------------------------------------------

class _Args:
    """The handful of attributes `check_validation_args` reads."""
    validation_samples = 8
    method = "sobol_seq"
    validation_matrix = "validation_matrix.txt"
    validation_seed = 0
    seed = 7


def test_validation_seed_ZERO_is_a_seed_not_an_unset_variable():
    """Before: `int(env or 0)` made `--validation-seed 0` indistinguishable from unset."""
    from scripts.create_adapter_parameter_sample import check_validation_args

    assert check_validation_args(_Args()) == 0, "seed 0 was read as 'unset'"

    class B(_Args):
        validation_seed = None
    assert check_validation_args(B()) == 1


def test_a_seed_equal_to_the_training_seed_is_still_refused():
    """The independence check must survive the change above."""
    from scripts.create_adapter_parameter_sample import check_validation_args

    class A(_Args):
        validation_seed = 7
    assert check_validation_args(A()) == 1


def test_a_missing_validation_matrix_is_caught_BEFORE_anything_is_written():
    """The refusal used to fire after the training matrix was already on disk."""
    from scripts.create_adapter_parameter_sample import check_validation_args

    class A(_Args):
        validation_matrix = ""
    assert check_validation_args(A()) == 1


def test_near_coincidence_is_measured_not_only_bit_equality():
    """Before: only bit-identical rows counted, so a point a float away passed as held out."""
    from scripts.create_adapter_parameter_sample import _nearest_distance

    A = np.array([[0.0, 0.0], [1.0, 1.0]])
    assert _nearest_distance(A, A + 1e-12) < 1e-9
    assert _nearest_distance(A, A + 0.5) > 0.1


# -----------------------------------------------------------------------------
# F23 — a gate that cannot fail
# -----------------------------------------------------------------------------

def test_the_TIER_GATE_does_fire_when_a_tier_is_on_the_roadmap_only(monkeypatch):
    """`VALID_TIERS == IMPLEMENTED_TIERS` today, so this branch is unreachable in normal use.

    That is not a reason to leave it untested: the branch is the mechanical half of "never skip a
    rung", and an unreachable branch rots. Patching the registry proves it still fires, which is
    what the guardrail claims.
    """
    from models.surrogate import spec as spec_mod
    from models.surrogate.spec import Provenance, SurrogateSpec, TargetSpec

    monkeypatch.setattr(spec_mod, "VALID_TIERS", ("S0", "S1", "S2", "S3", "S4"))
    monkeypatch.setattr(spec_mod, "IMPLEMENTED_TIERS", ("S0", "S1", "S2"))
    with pytest.raises(ValueError, match="ROADMAP"):
        SurrogateSpec(name="s", tier="S3", use_mode="offline_search",
                      input_names=["a"], input_lower=(0.0,), input_upper=(1.0,),
                      targets=(TargetSpec("y"),), provenance=Provenance(model="test"))
