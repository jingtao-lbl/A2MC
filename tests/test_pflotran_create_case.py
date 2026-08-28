"""PFLOTRAN create_case / submit_ensemble: assembling and launching a case.

Covers the calling convention scripts/materialize_adapter_ensemble.py actually uses
(the deck arrives ALREADY WRITTEN at its final case-dir location -- create_case's job
is staging the static supporting files + rendering the submit script), the exclusion
rules (the base case's own output/ dir must never be staged; the base deck must never
overwrite the already-perturbed one), submit.sh's rendered placeholders, and
submit_ensemble's dry-run path.

Gated on a real miniLEO deck (A2MC_PFLOTRAN_DECK), same pattern as
tests/test_pflotran_e2e.py, since the deck + its supporting files live on CFS and are
not committed.

Run:  ~/a2mc_env/bin/python -m pytest tests/test_pflotran_create_case.py -v

Author: Jing Tao with Claude
"""
from __future__ import annotations

import os
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
_DECK = Path(os.environ.get("A2MC_PFLOTRAN_DECK", "")) if os.environ.get("A2MC_PFLOTRAN_DECK") else None
_needs_deck = pytest.mark.skipif(
    not (_DECK and _DECK.is_file()),
    reason="miniLEO deck not staged (set A2MC_PFLOTRAN_DECK)")

RUNTEMPLATE = REPO / "models/pflotran/runtemplates/hpc_standalone.sh.tmpl"


def _backend():
    from models.pflotran.backend import PFLOTRANBackend
    return PFLOTRANBackend()


def _base_cfg(**overrides):
    cfg = {
        "A2MC_BASE_PARAM_FILE": str(_DECK),
        "A2MC_PFLOTRAN_RUNTEMPLATE": str(RUNTEMPLATE),
        "A2MC_HPC_ACCOUNT": "m5199", "A2MC_HPC_QUEUE": "regular",
        "A2MC_HPC_NODES": "1", "A2MC_HPC_MPI_RANKS": "8", "A2MC_HPC_CPUS_PER_TASK": "1",
        "A2MC_HPC_WALLTIME": "04:00:00", "A2MC_PFLOTRAN_BINARY": "/fake/pflotran",
        "A2MC_DRY_RUN": "1",
    }
    cfg.update(overrides)
    return cfg


def _staged_case(tmp_path, case_name="c1", modifications=None):
    be = _backend()
    pfile = tmp_path / case_name / _DECK.name
    pfile.parent.mkdir(parents=True, exist_ok=True)
    be.write_parameter_file(_DECK, modifications or {}, pfile)
    case_dir = be.create_case(case_name, pfile, _base_cfg())
    return be, case_dir, pfile


@_needs_deck
def test_stages_every_static_file_from_the_base_case_dir(tmp_path):
    be, case_dir, pfile = _staged_case(tmp_path)
    src_names = {p.name for p in _DECK.parent.iterdir() if p.is_file()}
    staged_names = {p.name for p in case_dir.iterdir()}
    # every static file from the source dir must be present (deck + submit.sh added on top)
    assert src_names <= staged_names
    assert (staged_names - src_names) == {"submit.sh"}


@_needs_deck
def test_output_directory_is_never_staged(tmp_path):
    be, case_dir, pfile = _staged_case(tmp_path)
    assert not (case_dir / "output").exists(), (
        "the base case's own output/ (prior run's results) is not an input and must "
        "not be copied into a fresh case dir")


@_needs_deck
def test_staged_deck_is_the_perturbed_one_not_the_base(tmp_path):
    from models.pflotran.parameter_parser import PFLOTRANParameterParser
    be, case_dir, pfile = _staged_case(tmp_path, modifications={"RATE_CONSTANT_Glass_FB": -13.5})
    p = PFLOTRANParameterParser()
    reparsed = p.parse(case_dir / _DECK.name)
    assert p.errors == []
    assert reparsed["CHEMISTRY/MINERAL_KINETICS/Glass_FB/RATE_CONSTANT"].value == -13.5, (
        "create_case must not overwrite the already-perturbed deck with a copy of the base")


@_needs_deck
def test_create_case_is_idempotent(tmp_path):
    be, case_dir, pfile = _staged_case(tmp_path, modifications={"RATE_CONSTANT_Glass_FB": -13.5})
    before = (case_dir / "savannah_river.dat").read_bytes()
    be.create_case("c1", pfile, _base_cfg())   # second call must not raise or corrupt staged files
    after = (case_dir / "savannah_river.dat").read_bytes()
    assert before == after


@_needs_deck
def test_submit_script_renders_launch_placeholders(tmp_path):
    be, case_dir, pfile = _staged_case(tmp_path)
    text = (case_dir / "submit.sh").read_text()
    assert "#SBATCH --job-name=c1" in text
    assert "#SBATCH --account=m5199" in text
    assert "#SBATCH --nodes=1" in text
    assert "#SBATCH --ntasks=8" in text
    assert "srun -n 8" in text
    assert str(case_dir) in text
    # every ACTUAL placeholder the template declares (excluding its own prose comment
    # that literally says "{{PLACEHOLDERS}}") must be substituted
    for token in ("{{CASE_NAME}}", "{{ACCOUNT}}", "{{NODES}}", "{{MPI_RANKS}}",
                  "{{CPUS_PER_TASK}}", "{{OUTPUT_DIR}}", "{{MODEL_BINARY}}", "{{RUN_CMD}}"):
        assert token not in text, f"{token} was not substituted"


@_needs_deck
def test_secondary_surface_not_implemented(tmp_path):
    be = _backend()
    pfile = tmp_path / "c2" / _DECK.name
    pfile.parent.mkdir(parents=True, exist_ok=True)
    be.write_parameter_file(_DECK, {}, pfile)
    with pytest.raises(NotImplementedError, match="secondary surface"):
        be.create_case("c2", pfile, _base_cfg(), secondary_param_file=Path("dummy"))


@_needs_deck
def test_missing_base_param_file_config_raises(tmp_path):
    be = _backend()
    pfile = tmp_path / "c3" / _DECK.name
    pfile.parent.mkdir(parents=True, exist_ok=True)
    be.write_parameter_file(_DECK, {}, pfile)
    with pytest.raises(KeyError, match="A2MC_BASE_PARAM_FILE"):
        be.create_case("c3", pfile, {})


@_needs_deck
def test_submit_ensemble_dry_run_writes_job_id_and_does_not_call_sbatch(tmp_path):
    be, case_dir, pfile = _staged_case(tmp_path)
    job_ids = be.submit_ensemble([case_dir], _base_cfg(A2MC_DRY_RUN="1"))
    assert job_ids == ["DRYRUN-0000"]
    assert (case_dir / "job_id.txt").read_text().strip() == "DRYRUN-0000"


def test_submit_ensemble_missing_submit_script_raises(tmp_path):
    be = _backend()
    empty_case = tmp_path / "no_submit_here"
    empty_case.mkdir()
    with pytest.raises(FileNotFoundError, match="no submit.sh"):
        be.submit_ensemble([empty_case], {"A2MC_DRY_RUN": "1"})
