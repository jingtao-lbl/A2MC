"""The two rules `tools/check_calibration_rounds.py` gained on 2026-09-22, each with the case
that made it necessary.

Both come from PFLOTRAN_miniLEO's R1 record (register item D4):

  * its `ensemble_output` named a directory that has never existed, for three weeks and through a
    round close, because the only check on that field compared it to an environment variable and
    fired only when the variable was set;
  * its `ensembles: 4096` was flagged as a mismatch by the MORRIS identity
    `trajectories x (params+1)`, which a scrambled Sobol' design does not obey -- a checker firing
    on a correct record, which is how people learn to ignore a checker.

Driven through the CLI because that is how the tool is used; a green path and a red path for each.
"""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
TOOL = REPO / "tools" / "check_calibration_rounds.py"
PY = os.environ.get("A2MC_PYTHON", str(Path.home() / "a2mc_env" / "bin" / "python"))

ROUND = """\
model: pflotran
site: TEST_Case
rounds:
  1:
    parameters: 3
    ensembles: {ensembles}
    sampling_scheme: {scheme}
    paths:
      ensemble_output: {out}
      param_list: {plist}
      salib_problem: {problem}
    validation_targets_file: {targets}
"""


def _case(tmp_path, *, out: Path, scheme="sobol_seq", ensembles=4096):
    cfg = tmp_path / "config"
    cfg.mkdir(parents=True, exist_ok=True)
    for name in ("params.csv", "problem.txt", "targets.yaml"):
        (cfg / name).write_text("x\n")
    (cfg / "calibration_rounds.yaml").write_text(ROUND.format(
        ensembles=ensembles, scheme=scheme, out=out,
        plist=cfg / "params.csv", problem=cfg / "problem.txt", targets=cfg / "targets.yaml"))
    return cfg


def _run(tmp_path, **env_extra):
    env = dict(os.environ)
    env.update({"A2MC_USE_CASE_DIR": str(tmp_path), "A2MC_N_PARAMS": "3",
                "A2MC_MODEL": "pflotran", "A2MC_SAMPLING_SCHEME": "sobol_seq",
                "A2MC_PARAM_LIST_FILE": str(tmp_path / "config" / "params.csv"),
                "A2MC_SALIB_PROBLEM_FILE": str(tmp_path / "config" / "problem.txt"),
                "A2MC_VALIDATION_TARGETS": str(tmp_path / "config" / "targets.yaml")})
    env.update({k: str(v) for k, v in env_extra.items()})
    return subprocess.run([PY, str(TOOL)], capture_output=True, text=True, env=env, cwd=str(REPO))


def test_a_MISSING_ensemble_output_is_caught_when_its_parent_is_present(tmp_path):
    """The defect that survived three weeks: a path nothing ever looked for."""
    parent = tmp_path / "runs"
    parent.mkdir()
    _case(tmp_path, out=parent / "R1_typo")
    r = _run(tmp_path)
    assert "ensemble_output exists" in r.stdout
    assert "is missing, but its parent" in r.stdout, r.stdout


def test_a_PRESENT_ensemble_output_passes(tmp_path):
    parent = tmp_path / "runs"
    real = parent / "R1_real"
    real.mkdir(parents=True)
    _case(tmp_path, out=real)
    r = _run(tmp_path)
    assert "[✓] ensemble_output exists on this machine" in r.stdout, r.stdout


def test_an_UNMOUNTED_tree_is_not_reported_as_a_bad_record(tmp_path):
    """A Mac reading a Perlmutter record must not be told the record is wrong."""
    _case(tmp_path, out=Path("/nonexistent-mount-point-for-this-test/runs/R1"))
    r = _run(tmp_path)
    assert "is not mounted here" in r.stdout, r.stdout
    assert "is missing, but its parent" not in r.stdout


def test_the_MORRIS_identity_is_SKIPPED_for_a_space_filling_design(tmp_path):
    """4096 Sobol' points over 16 parameters match no trajectory count, and the record is right."""
    parent = tmp_path / "runs"
    real = parent / "R1"
    real.mkdir(parents=True)
    _case(tmp_path, out=real, scheme="sobol_seq", ensembles=4096)
    r = _run(tmp_path)
    assert "Morris-only identity" in r.stdout, r.stdout
    assert "[✗] ensembles" not in r.stdout


def test_the_MORRIS_identity_still_APPLIES_to_a_morris_design(tmp_path):
    """The other half: gating it on the scheme must not switch it off everywhere."""
    parent = tmp_path / "runs"
    real = parent / "R1"
    real.mkdir(parents=True)
    _case(tmp_path, out=real, scheme="morris", ensembles=999)
    r = _run(tmp_path, A2MC_SAMPLING_SCHEME="morris", A2MC_N_TRAJECTORIES="30")
    assert "[✗] ensembles == trajectories x (params+1)" in r.stdout, r.stdout
