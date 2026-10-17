"""The adapter sampler's optional `scale` column: `log10` rows are drawn uniformly in log10(value).

visibility: public

What these hold the sampler to:
  * a list WITHOUT the column samples byte-for-byte as before, and a list WITH it leaves every
    unmarked column byte-identical to that run (the unit sample is drawn first; only marked
    columns are transformed), so adding the feature changes nothing for existing lists;
  * a `log10` column stays inside its declared bounds and is uniform in log space -- about half
    its draws below the geometric mean, where a linear draw would put about 5%;
  * the independent validation design is drawn in the same space and still passes its
    coincidence checks;
  * an unknown scale, or a log10 row with lower <= 0, is refused rather than guessed.

Author: Jing Tao with Claude
"""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import numpy as np

REPO = Path(__file__).resolve().parents[1]
SCRIPT = REPO / "scripts" / "create_adapter_parameter_sample.py"

HEADER = "name,pft,surface,default,lower_bound,upper_bound,bound_source"
ROWS = ["ALPHA,1,primary,0.5,0.1,0.9,fixture",
        "WIDE,1,primary,2.0,1.0,200.0,fixture",
        "GAMMA,1,primary,0.0,-2.0,2.0,fixture"]


def _list(tmp_path, scales=None, name="params.csv"):
    if scales is None:
        text = "\n".join([HEADER] + ROWS) + "\n"
    else:
        text = "\n".join([HEADER + ",scale"] + [r + "," + s for r, s in zip(ROWS, scales)]) + "\n"
    p = tmp_path / name
    p.write_text(text)
    return p


def _run(tmp_path, plist, tag, method="sobol_seq", extra=()):
    env = dict(os.environ)
    for k in ("A2MC_SOBOL_SEQ_VALID_SAMPLES", "A2MC_SOBOL_SEQ_VALID_SEED", "A2MC_VALID_MATRIX_FILE",
              "A2MC_N_SAMPLES", "A2MC_SAMPLING_SCHEME"):
        env.pop(k, None)
    mat, prob = tmp_path / f"matrix_{tag}.txt", tmp_path / f"problem_{tag}.txt"
    cmd = [sys.executable, str(SCRIPT), "--method", method, "--param-list-file", str(plist),
           "--output-matrix", str(mat), "--output-problem", str(prob), "--seed", "123"]
    cmd += ["--trajectories", "8"] if method == "morris" else ["--n-samples", "256"]
    r = subprocess.run(cmd + list(extra), capture_output=True, text=True, env=env, cwd=REPO)
    return r, mat


def test_unmarked_columns_are_byte_identical(tmp_path):
    r0, m0 = _run(tmp_path, _list(tmp_path), "none")
    r1, m1 = _run(tmp_path, _list(tmp_path, ["", "log10", "linear"], "p1.csv"), "log")
    assert r0.returncode == 0, r0.stderr
    assert r1.returncode == 0, r1.stderr
    A, B = np.loadtxt(m0), np.loadtxt(m1)
    assert np.array_equal(A[:, [0, 2]], B[:, [0, 2]]), "an unmarked column changed"
    assert not np.array_equal(A[:, 1], B[:, 1]), "the log10 column was not transformed"


def test_an_all_linear_scale_column_changes_nothing(tmp_path):
    _, m0 = _run(tmp_path, _list(tmp_path), "none")
    r, m1 = _run(tmp_path, _list(tmp_path, ["linear", "", "linear"], "p2.csv"), "lin")
    assert r.returncode == 0, r.stderr
    assert np.array_equal(np.loadtxt(m0), np.loadtxt(m1))


def test_log10_column_is_in_bounds_and_uniform_in_log(tmp_path):
    r, m = _run(tmp_path, _list(tmp_path, ["", "log10", ""]), "log")
    assert r.returncode == 0, r.stderr
    w = np.loadtxt(m)[:, 1]
    assert w.min() >= 1.0 and w.max() <= 200.0
    below_geomean = np.mean(w < np.sqrt(1.0 * 200.0))
    assert 0.45 < below_geomean < 0.55, below_geomean      # a linear draw gives ~0.06
    assert np.mean(w < 10.0) > 0.35                        # a linear draw gives ~0.045


def test_morris_honours_the_scale(tmp_path):
    r, m = _run(tmp_path, _list(tmp_path, ["", "log10", ""]), "morris", method="morris")
    assert r.returncode == 0, r.stderr
    w = np.loadtxt(m)[:, 1]
    assert w.min() >= 1.0 - 1e-9 and w.max() <= 200.0 + 1e-9
    assert np.mean(w < 10.0) > 0.3


def test_validation_design_is_drawn_in_the_same_space(tmp_path):
    val = tmp_path / "valid.txt"
    r, _ = _run(tmp_path, _list(tmp_path, ["", "log10", ""]), "val",
                extra=["--validation-samples", "64", "--validation-seed", "7", "--validation-matrix", str(val)])
    assert r.returncode == 0, r.stdout + r.stderr
    v = np.loadtxt(val)[:, 1]
    assert v.min() >= 1.0 and v.max() <= 200.0 and np.mean(v < 10.0) > 0.3


def test_unknown_scale_is_refused(tmp_path):
    r, _ = _run(tmp_path, _list(tmp_path, ["", "ln", ""]), "bad")
    assert r.returncode != 0 and "unknown scale" in (r.stdout + r.stderr)


def test_log10_with_nonpositive_lower_is_refused(tmp_path):
    r, _ = _run(tmp_path, _list(tmp_path, ["", "", "log10"]), "neg")   # GAMMA's lower is -2
    assert r.returncode != 0 and "lower > 0" in (r.stdout + r.stderr)
