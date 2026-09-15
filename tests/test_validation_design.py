"""The INDEPENDENT validation design, drawn at Phase 0 when the ensemble is designed.

WHY THIS BELONGS AT PHASE 0 AND NOT IN THE FITTER. A held-out set carved out of one Sobol' sequence
is still that sequence: train and test are draws from the same point set, so any such split measures
interpolation inside it, however the split is chosen. An independent test has to be DRAWN with a
different scramble seed and RUN, and both of those are design-time acts. By the time a surrogate is
being fitted the opportunity is gone, and no amount of cleverness at fit time recovers it.

Measured 2026-09-13: `A2MC_SOBOL_SEQ_VALID_SAMPLES`, `A2MC_SOBOL_SEQ_VALID_SEED` and
`A2MC_VALID_MATRIX_FILE` were declared in a site config with 25 lines of rationale and read by no
Python anywhere in the repo. These tests exist so that cannot silently become true again.
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import numpy as np
import pytest

REPO = Path(__file__).resolve().parents[1]
SCRIPT = REPO / "scripts" / "create_adapter_parameter_sample.py"

#: The real header, trimmed to the columns `parse_pft_param_list` needs. A bare name/lower/upper
#: CSV is NOT this format and the parser rejects it, which is the right behaviour.
PARAM_LIST = """# a fixture parameter list
name,pft,surface,default,lower_bound,upper_bound,bound_source
ALPHA,1,primary,0.5,0.1,0.9,fixture
BETA,1,primary,2.0,1.0,5.0,fixture
GAMMA,1,primary,0.0,-2.0,2.0,fixture
DELTA,1,primary,15.0,10.0,20.0,fixture
"""


def _setup(tmp_path):
    pl = tmp_path / "params.csv"
    pl.write_text(PARAM_LIST)
    return pl, tmp_path / "matrix.txt", tmp_path / "problem.txt", tmp_path / "valid.txt"


def _run(tmp_path, extra, env_extra=None):
    import os
    pl, mat, prob, val = _setup(tmp_path)
    env = dict(os.environ)
    for k in ("A2MC_SOBOL_SEQ_VALID_SAMPLES", "A2MC_SOBOL_SEQ_VALID_SEED",
              "A2MC_VALID_MATRIX_FILE", "A2MC_N_SAMPLES", "A2MC_SAMPLING_SCHEME"):
        env.pop(k, None)
    env.update(env_extra or {})
    cmd = [sys.executable, str(SCRIPT), "--method", "sobol_seq",
           "--param-list-file", str(pl), "--output-matrix", str(mat),
           "--output-problem", str(prob), "--n-samples", "64", "--seed", "123"] + extra
    r = subprocess.run(cmd, capture_output=True, text=True, env=env, cwd=REPO)
    return r, mat, val


# --------------------------------------------------------------------------------------------
# it draws one
# --------------------------------------------------------------------------------------------

def test_it_writes_an_independent_validation_matrix(tmp_path):
    r, mat, val = _run(tmp_path, ["--validation-samples", "32", "--validation-seed", "999",
                                  "--validation-matrix", str(tmp_path / "valid.txt")])
    assert r.returncode == 0, r.stderr
    V = np.loadtxt(tmp_path / "valid.txt")
    X = np.loadtxt(mat)
    assert V.shape == (32, 4)
    assert X.shape == (64, 4)
    assert "INDEPENDENT" in r.stdout


def test_no_validation_point_coincides_with_a_training_point(tmp_path):
    r, mat, _ = _run(tmp_path, ["--validation-samples", "32", "--validation-seed", "999",
                                "--validation-matrix", str(tmp_path / "valid.txt")])
    assert r.returncode == 0, r.stderr
    X, V = np.loadtxt(mat), np.loadtxt(tmp_path / "valid.txt")
    train = {row.tobytes() for row in np.ascontiguousarray(X, dtype=float)}
    assert not any(row.tobytes() in train for row in np.ascontiguousarray(V, dtype=float))


def test_the_env_vars_are_READ_not_merely_declared(tmp_path):
    """The failure this whole feature exists to prevent: a contract nothing consumes."""
    r, mat, _ = _run(tmp_path, [], env_extra={
        "A2MC_SOBOL_SEQ_VALID_SAMPLES": "16",
        "A2MC_SOBOL_SEQ_VALID_SEED": "20260827",
        "A2MC_VALID_MATRIX_FILE": str(tmp_path / "valid.txt")})
    assert r.returncode == 0, r.stderr
    assert (tmp_path / "valid.txt").is_file(), (
        "the env vars were set and no validation matrix appeared; they are declared and unread")
    assert np.loadtxt(tmp_path / "valid.txt").shape == (16, 4)


# --------------------------------------------------------------------------------------------
# it REFUSES
# --------------------------------------------------------------------------------------------

def test_it_REFUSES_a_validation_seed_equal_to_the_training_seed(tmp_path):
    """The seed IS the independence. Same seed, same lattice, and the file still looks fine."""
    r, _, _ = _run(tmp_path, ["--validation-samples", "32", "--validation-seed", "123",
                              "--validation-matrix", str(tmp_path / "valid.txt")])
    assert r.returncode == 1
    assert "equals --seed" in r.stderr
    assert not (tmp_path / "valid.txt").exists()


def test_it_refuses_a_validation_design_with_no_seed(tmp_path):
    r, _, _ = _run(tmp_path, ["--validation-samples", "32",
                              "--validation-matrix", str(tmp_path / "valid.txt")])
    assert r.returncode == 1
    assert "no safe default" in r.stderr


def test_it_refuses_when_there_is_nowhere_to_write_it(tmp_path):
    r, _, _ = _run(tmp_path, ["--validation-samples", "32", "--validation-seed", "999"])
    assert r.returncode == 1
    assert "nowhere to write" in r.stderr


def test_it_refuses_a_validation_design_on_a_SALTELLI_run(tmp_path):
    """A Saltelli design's points are one-coordinate perturbations of each other, so an extra
    independent block of them is not the instrument this flag claims to build."""
    import os
    pl, mat, prob, val = _setup(tmp_path)
    env = dict(os.environ)
    for k in ("A2MC_SOBOL_SEQ_VALID_SAMPLES", "A2MC_SOBOL_SEQ_VALID_SEED",
              "A2MC_VALID_MATRIX_FILE", "A2MC_N_SAMPLES", "A2MC_SAMPLING_SCHEME"):
        env.pop(k, None)
    r = subprocess.run(
        [sys.executable, str(SCRIPT), "--method", "sobol", "--param-list-file", str(pl),
         "--output-matrix", str(mat), "--output-problem", str(prob), "--n-samples", "16",
         "--no-second-order", "--validation-samples", "8", "--validation-seed", "999",
         "--validation-matrix", str(val)],
        capture_output=True, text=True, env=env, cwd=REPO)
    assert r.returncode == 1
    assert "only meaningful for --method sobol_seq" in r.stderr


# --------------------------------------------------------------------------------------------
# and it says so when there is none
# --------------------------------------------------------------------------------------------

def test_with_no_validation_design_it_says_so_PLAINLY(tmp_path):
    """Silence here is how EcoSIM_Lusignan R1b was designed without one and nobody noticed until a
    surrogate had already been built on it four times."""
    r, _, _ = _run(tmp_path, [])
    assert r.returncode == 0
    assert "validation design: NONE" in r.stdout
    assert "cannot be fixed later by re-splitting" in r.stdout
