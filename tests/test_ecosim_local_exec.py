"""`A2MC_EXEC_MODE=local` runs an ensemble on a workstation. HPC behaviour is unchanged.

The defect this closes was silent: with no `sbatch` on PATH, submit_ensemble staged every
case, launched nothing, wrote a synthetic id into job_id.txt and returned it. On a laptop that
is indistinguishable from a successful submission, and a monitor armed on it waits forever for
jobs that never existed.

Every test asserts either a way local mode must WORK end to end, or a way the HPC path must be
BIT-IDENTICAL to what it was ([[feedback_a_check_that_cannot_fail]]).
"""
from __future__ import annotations

import os
import sys
import time
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from models.ecosim import backend as B     # noqa: E402


# --------------------------------------------------------------------------- the mode switch
def test_default_is_hpc_so_nothing_existing_changes():
    assert B._exec_mode({}) == "hpc"
    assert B._exec_mode({"A2MC_EXEC_MODE": ""}) == "hpc"


def test_mode_is_case_insensitive():
    assert B._exec_mode({"A2MC_EXEC_MODE": "LOCAL"}) == "local"


def test_an_unrecognised_mode_is_REFUSED_not_silently_treated_as_hpc():
    """A typo must not quietly submit to a scheduler the user thought they had opted out of."""
    with pytest.raises(ValueError):
        B._exec_mode({"A2MC_EXEC_MODE": "slurm"})


@pytest.mark.parametrize("bad", ["0", "-1"])
def test_worker_count_must_be_at_least_one(bad):
    with pytest.raises(ValueError):
        B._local_workers({"A2MC_LOCAL_WORKERS": bad})


def test_worker_count_is_conservative_by_default():
    """EcoSIM is serial, so this counts whole cases; four on a laptop is already four cores."""
    assert 1 <= B._local_workers({}) <= 4


# --------------------------------------------------------- the silent-dry-run defect, closed
def test_missing_sbatch_in_HPC_mode_RAISES_instead_of_faking_submission(tmp_path, monkeypatch):
    """THE test. This is the exact path a collaborator on a laptop used to fall through."""
    case = tmp_path / "c0"; case.mkdir()
    (case / "submit.sh").write_text("#!/bin/bash\ntrue\n")
    monkeypatch.setattr(B.shutil, "which", lambda n: None)
    with pytest.raises(RuntimeError) as e:
        B.EcoSIMBackend().submit_ensemble([case], {})
    msg = str(e.value)
    assert "A2MC_EXEC_MODE=local" in msg, "the refusal must name the way out"
    assert "A2MC_DRY_RUN" in msg
    assert not (case / "job_id.txt").exists(), "a refused submission must write no job id"


def test_an_EXPLICIT_dry_run_still_works_with_no_sbatch(tmp_path, monkeypatch):
    """A2MC_DRY_RUN is a feature the e2e tests rely on; only the IMPLICIT fallback is gone."""
    case = tmp_path / "c0"; case.mkdir()
    (case / "submit.sh").write_text("#!/bin/bash\ntrue\n")
    monkeypatch.setattr(B.shutil, "which", lambda n: None)
    ids = B.EcoSIMBackend().submit_ensemble([case], {"A2MC_DRY_RUN": "1"})
    assert ids == ["DRYRUN-0000"]


# --------------------------------------------------------------------------- local execution
@pytest.mark.skipif(not all(map(lambda c: __import__("shutil").which(c), ("xargs", "setsid"))),
                    reason="needs xargs and setsid")
def test_local_mode_ACTUALLY_RUNS_the_cases(tmp_path):
    """End to end with a stand-in for the binary: each case must leave its own evidence."""
    cases = []
    for i in range(3):
        c = tmp_path / f"case{i}"; c.mkdir()
        (c / "submit.sh").write_text(
            "#!/bin/bash\nset -e\necho ran > ran.txt\n")
        cases.append(c)

    ids = B.EcoSIMBackend().submit_ensemble(cases, {"A2MC_EXEC_MODE": "local",
                                                    "A2MC_LOCAL_WORKERS": "2"})
    assert len(ids) == 3 and all(j.startswith("LOCAL-") for j in ids)

    for c in cases:
        for _ in range(100):
            if (c / "ran.txt").exists():
                break
            time.sleep(0.1)
        assert (c / "ran.txt").is_file(), f"{c.name} was never executed"
        assert (c / "job_id.txt").read_text().startswith("LOCAL-")


@pytest.mark.skipif(not all(map(lambda c: __import__("shutil").which(c), ("xargs", "setsid"))),
                    reason="needs xargs and setsid")
def test_local_mode_returns_BEFORE_the_cases_finish(tmp_path):
    """Submission must be non-blocking, exactly as sbatch is. The phase scripts, the census
    and check_case_status are all written around polling after a submit that returned."""
    c = tmp_path / "slow"; c.mkdir()
    (c / "submit.sh").write_text("#!/bin/bash\nsleep 5\necho done > ran.txt\n")
    t0 = time.time()
    B.EcoSIMBackend().submit_ensemble([c], {"A2MC_EXEC_MODE": "local"})
    assert time.time() - t0 < 3, "submit_ensemble blocked until the run finished"
    assert not (c / "ran.txt").exists()


def test_local_mode_writes_a_dispatch_log_to_arm_a_monitor_on(tmp_path):
    c = tmp_path / "case0"; c.mkdir()
    (c / "submit.sh").write_text("#!/bin/bash\ntrue\n")
    B.EcoSIMBackend().submit_ensemble([c], {"A2MC_EXEC_MODE": "local"})
    for _ in range(50):
        if (tmp_path / "local_dispatch.log").exists():
            break
        time.sleep(0.1)
    assert (tmp_path / "local_dispatch.log").is_file()
    assert (tmp_path / "local_cases.txt").is_file()


def test_local_mode_refuses_a_case_with_no_submit_script(tmp_path):
    c = tmp_path / "empty"; c.mkdir()
    with pytest.raises(FileNotFoundError):
        B.EcoSIMBackend().submit_ensemble([c], {"A2MC_EXEC_MODE": "local"})


# --------------------------------------------------------------------------- the template
def _code(path: Path) -> str:
    """Executable lines only. The template's header EXPLAINS how it differs from the HPC one,
    so it names srun and module load in prose; what must be absent is the calls."""
    return "\n".join(l for l in path.read_text().split("\n")
                     if l.strip() and not l.lstrip().startswith("#"))


def test_a_local_template_ships_and_carries_NO_scheduler_directives():
    t = REPO / "models/ecosim/runtemplates/local_serial.sh.tmpl"
    assert t.is_file()
    code = _code(t)
    assert "#SBATCH" not in t.read_text().replace("no SBATCH", "")   # no directive anywhere
    assert "srun" not in code, "a local template must not invoke srun"
    assert "module load" not in code, "a workstation usually has no module command"
    body = t.read_text()
    assert "{{MODEL_BINARY}}" in body and "{{OUTPUT_DIR}}" in body
    assert '"$EXE"' in code, "it must actually invoke the binary"


def test_the_HPC_template_is_untouched_and_still_the_default():
    t = REPO / "models/ecosim/runtemplates/hpc_standalone.sh.tmpl"
    assert "#SBATCH" in t.read_text() and "srun" in t.read_text()
