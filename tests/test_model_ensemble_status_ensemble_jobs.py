"""--ensemble-jobs on tools/model_ensemble_status.py.

Added 2026-08-21. `check_case_status` cannot separate "still running" from "died part-way"
from inside a case dir, and documents that this tool reconciles it against the scheduler --
but the reconciliation ran off each case's `job_id.txt`, which a job ARRAY and a node
task-farm never write. For EcoSIM_BioCON R3 that made the leg inert across all 14,849 cases:
the scan published RUNNING=1129 against two arrays that were provably terminal, and those
1,129 were the round's failures.

Every test below names a way the feature must FAIL, not a way it succeeds -- a flag that
reclassifies RUNNING to FAILED must not be able to do so while work is live.
"""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import tools.model_ensemble_status as mes  # noqa: E402


class _Run:
    def __init__(self, stdout): self.stdout = stdout


def _fake_sacct(mapping):
    """Stand in for subprocess.run, returning per-job State output."""
    def run(cmd, **kw):
        job = cmd[cmd.index("-j") + 1]
        return _Run(mapping.get(job, ""))
    return run


def test_all_terminal_is_terminal(monkeypatch):
    monkeypatch.setattr(mes.subprocess, "run",
                        _fake_sacct({"1": "COMPLETED\n", "2": "COMPLETED\nFAILED\n"}))
    ok, states = mes.ensemble_jobs_terminal(["1", "2"])
    assert ok is True
    assert all(v.startswith("terminal(") for v in states.values())


def test_one_running_job_blocks_reclassification(monkeypatch):
    """The whole point: a live job must keep incomplete cases reported as RUNNING."""
    monkeypatch.setattr(mes.subprocess, "run",
                        _fake_sacct({"1": "COMPLETED\n", "2": "RUNNING\nCOMPLETED\n"}))
    ok, states = mes.ensemble_jobs_terminal(["1", "2"])
    assert ok is False
    assert states["2"].startswith("ACTIVE(")


def test_pending_job_blocks_reclassification(monkeypatch):
    monkeypatch.setattr(mes.subprocess, "run", _fake_sacct({"9": "PENDING\n"}))
    assert mes.ensemble_jobs_terminal(["9"])[0] is False


def test_unreadable_scheduler_is_not_terminal(monkeypatch):
    """An unreadable scheduler is not evidence that work has stopped."""
    def boom(cmd, **kw):
        raise OSError("sacct unavailable")
    monkeypatch.setattr(mes.subprocess, "run", boom)
    ok, states = mes.ensemble_jobs_terminal(["1"])
    assert ok is False and states["1"] == "UNREADABLE"


def test_no_record_is_not_terminal(monkeypatch):
    """A job sacct has never heard of must not be read as finished."""
    monkeypatch.setattr(mes.subprocess, "run", _fake_sacct({}))
    ok, states = mes.ensemble_jobs_terminal(["12345"])
    assert ok is False and states["12345"] == "NO-RECORD"


def test_empty_job_list_is_not_terminal(monkeypatch):
    """Naming no jobs must not silently assert that everything finished."""
    assert mes.ensemble_jobs_terminal([])[0] is False


def _case(tmp_path, name, *files):
    d = tmp_path / name
    d.mkdir()
    (d / "submit.sh").write_text("#!/bin/bash\n")
    for f in files:
        (d / f).write_text("x")
    return d


def _patch_backend(monkeypatch, verdicts):
    class _B:
        def check_case_status(self, cd):
            return verdicts[Path(cd).name]

    class _Reg:
        @staticmethod
        def get_model(_):
            return _B()
    monkeypatch.setitem(sys.modules, "models", type(sys)("models"))
    sys.modules["models"].registry = _Reg
    import importlib
    monkeypatch.setattr(importlib, "import_module", lambda *_a, **_k: None)


def test_scan_reclassifies_only_when_jobs_terminal(tmp_path, monkeypatch):
    _case(tmp_path, "c1")   # started, never completed  -> backend says RUNNING
    _case(tmp_path, "c2")   # completed
    _patch_backend(monkeypatch, {"c1": "RUNNING", "c2": "COMPLETED"})

    rows = {r[0]: r[3] for r in mes.scan("ecosim", tmp_path, None, jobs_terminal=False)}
    assert rows["c1"] == "RUNNING", "must not reclassify while work may be live"

    rows = {r[0]: r[3] for r in mes.scan("ecosim", tmp_path, None, jobs_terminal=True)}
    assert rows["c1"] == "FAILED", "a started case that never completed, with nothing running"
    assert rows["c2"] == "COMPLETED", "a complete case is untouched by the flag"


def test_pending_case_is_not_reclassified(tmp_path, monkeypatch):
    """Only RUNNING is ambiguous. A case that never started stays PENDING."""
    _case(tmp_path, "c3")
    _patch_backend(monkeypatch, {"c3": "PENDING"})
    rows = {r[0]: r[3] for r in mes.scan("ecosim", tmp_path, None, jobs_terminal=True)}
    assert rows["c3"] == "PENDING"


# --------------------------------------------------------------------------------------------
# --cases-file (added 2026-08-21). --case-range is CONTIGUOUS; a relaunch population is not.
# On the R3 relaunch the narrowest enclosing range still forced a scan of 14,734 dirs to watch
# 1,129, and the refresh hook exceeded its 900 s budget and was killed. Measured after: 38 s.
# --------------------------------------------------------------------------------------------

def test_read_cases_file_parses_ids(tmp_path):
    p = tmp_path / "ids.txt"
    p.write_text("77\n104\n\n14810\n")
    assert mes.read_cases_file(p) == {77, 104, 14810}


def test_read_cases_file_ignores_comments_and_blanks(tmp_path):
    p = tmp_path / "ids.txt"
    p.write_text("# the failed cases\n77\n\n  104  # sigfpe\n\n")
    assert mes.read_cases_file(p) == {77, 104}


def test_read_cases_file_rejects_an_empty_list(tmp_path):
    """An empty list must RAISE, not scan everything.

    Silently falling back to the full ensemble is the dangerous reading: the caller asked to narrow
    and would get the opposite, at 13x the cost, with no signal.
    """
    p = tmp_path / "ids.txt"
    p.write_text("# nothing but a comment\n\n")
    with pytest.raises(ValueError):
        mes.read_cases_file(p)


def test_read_cases_file_rejects_garbage(tmp_path):
    p = tmp_path / "ids.txt"
    p.write_text("77\nnot-a-number\n")
    with pytest.raises(ValueError):
        mes.read_cases_file(p)


def test_scan_honours_a_case_id_list(tmp_path, monkeypatch):
    for n in (1, 2, 3):
        _case(tmp_path, f"c{n}")
    _patch_backend(monkeypatch, {"c1": "COMPLETED", "c2": "COMPLETED", "c3": "COMPLETED"})
    rows = mes.scan("ecosim", tmp_path, None, False, case_ids={1, 3})
    assert sorted(r[0] for r in rows) == ["c1", "c3"], "scanned outside the id list"


def test_case_ids_and_case_range_intersect(tmp_path, monkeypatch):
    """Given both, a case must satisfy BOTH -- neither may widen the other."""
    for n in (1, 2, 3, 4):
        _case(tmp_path, f"c{n}")
    _patch_backend(monkeypatch, {f"c{n}": "COMPLETED" for n in (1, 2, 3, 4)})
    rows = mes.scan("ecosim", tmp_path, (2, 4), False, case_ids={1, 2})
    assert sorted(r[0] for r in rows) == ["c2"]
