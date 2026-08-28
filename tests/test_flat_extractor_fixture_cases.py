"""End-to-end fixture test for scripts/extract_flat_ensemble_targets.py.

Named as still-outstanding in dev log 20260821f and built 2026-08-21. The property tests there
cover the chunk arithmetic and the real-case runs cover the happy path; what neither covers is the
TRUNCATED case, which is the one that matters:

  a run that started and died part-way leaves output that LOOKS like a finished run
  (EcoSIM opens its single h0 tape at initialisation), so the danger is not that it errors --
  it is that it gets SCORED and written into the Y matrix as a valid row.

For a Saltelli design a hole's position decides whether the estimator is usable, so a truncated
case silently scored is worse than a missing one: it is a wrong number in a place nothing flags.

The fixtures need no real NetCDF. `EcoSIMBackend.check_case_status` classifies from the runfile
TEXT and the output file NAMES, so empty files with the right names are faithful to the code path
under test.
"""
import csv
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

RUNFILE = """\
&ecosim
    case_name = 'FIX'
    start_date = '20000101000000'
    forc_periods = 2000, 2002, 1
/
"""
# start 2000 + (2002-2000+1)*1 = 3 simulated years -> a complete run stamps its restart 2003.
FINAL_YEAR = 2003


def _case(root: Path, n: int, *, runfile=True, h0=False, restart_year=None, slurm_out=False):
    d = root / f"case{n}"
    d.mkdir(parents=True)
    if runfile:
        (d / "runfile.nml").write_text(RUNFILE)
    if h0:
        (d / "FIX.ecosim.h0.2000-01-01-00000.nc").write_bytes(b"")
    if restart_year is not None:
        (d / f"FIX.ecosim.r.{restart_year}-01-01-000000.nc").write_bytes(b"")
    if slurm_out:
        (d / "slurm_1.out").write_text("started\n")
    return d


@pytest.fixture
def ensemble(tmp_path):
    """case1 COMPLETE · case2 TRUNCATED · case3 ABSENT · case4 PENDING."""
    root = tmp_path / "run"
    root.mkdir()
    _case(root, 1, h0=True, restart_year=FINAL_YEAR)          # finished: final restart present
    _case(root, 2, h0=True, restart_year=FINAL_YEAR - 1)      # died part-way: tape + earlier restart
    #    case3: deliberately not created at all
    _case(root, 4)                                            # staged, never ran
    return root


@pytest.fixture
def targets_yaml(tmp_path):
    p = tmp_path / "targets.yaml"
    p.write_text(
        "targets:\n"
        "  NPP:\n    observed: 1.0\n    uncertainty: 0.1\n"
        "  plant_C:\n    observed: 2.0\n    uncertainty: 0.2\n"
    )
    return p


def _run(monkeypatch, ensemble, targets_yaml, out, chunk_size, calls):
    """Invoke the extractor's main() in-process with scoring stubbed."""
    import tools.model_evaluate_case as mec

    def fake_eval(case_path, targets, **kw):
        calls.append(Path(case_path).name)
        return 0.0, {}, {"NPP": 11.0, "plant_C": 22.0}

    monkeypatch.setattr(mec, "evaluate_model_case", fake_eval)
    import importlib.util
    spec = importlib.util.spec_from_file_location(
        "flatx", REPO / "scripts/extract_flat_ensemble_targets.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    monkeypatch.setattr(sys, "argv", [
        "extract_flat_ensemble_targets.py",
        "--model", "ecosim", "--run-root", str(ensemble),
        "--case-pattern", "case{N}", "--targets", str(targets_yaml),
        "--first", "1", "--last", "4", "--out", str(out),
        "--chunk-size", str(chunk_size),
    ])
    assert mod.main() == 0
    with open(out) as fh:
        return {int(r["case"]): r for r in csv.DictReader(fh)}, mod


def test_every_case_in_range_gets_a_row(monkeypatch, ensemble, targets_yaml, tmp_path):
    """No case may be silently dropped -- a missing row is an invisible hole."""
    calls = []
    rows, _ = _run(monkeypatch, ensemble, targets_yaml, tmp_path / "y.csv", 0, calls)
    assert sorted(rows) == [1, 2, 3, 4]


def test_truncated_case_is_not_scored(monkeypatch, ensemble, targets_yaml, tmp_path):
    """THE test. case2 has a tape and an earlier restart; it must not become a number."""
    calls = []
    rows, _ = _run(monkeypatch, ensemble, targets_yaml, tmp_path / "y.csv", 0, calls)

    assert rows[2]["status"] != "COMPLETED", "a truncated run was reported COMPLETED"
    assert rows[2]["NPP"] in ("nan", ""), f"a truncated run was SCORED: NPP={rows[2]['NPP']!r}"
    assert "case2" not in calls, "the scorer was invoked on a case that never finished"


def test_complete_case_is_scored(monkeypatch, ensemble, targets_yaml, tmp_path):
    """The gate must not be so strict that a genuinely finished case is refused."""
    calls = []
    rows, _ = _run(monkeypatch, ensemble, targets_yaml, tmp_path / "y.csv", 0, calls)
    assert rows[1]["status"] == "COMPLETED"
    assert float(rows[1]["NPP"]) == 11.0 and float(rows[1]["plant_C"]) == 22.0
    assert calls == ["case1"], f"scored the wrong set of cases: {calls}"


def test_absent_and_pending_cases_are_labelled_not_scored(monkeypatch, ensemble, targets_yaml, tmp_path):
    calls = []
    rows, _ = _run(monkeypatch, ensemble, targets_yaml, tmp_path / "y.csv", 0, calls)
    for n in (3, 4):
        assert rows[n]["status"] != "COMPLETED"
        assert rows[n]["NPP"] in ("nan", "")
    assert "case3" not in calls and "case4" not in calls


def test_chunked_and_single_process_agree(monkeypatch, ensemble, targets_yaml, tmp_path):
    """Isolation must not change the answer.

    Skipped rather than faked: the chunked driver re-invokes this script as a SUBPROCESS, which
    does not inherit the monkeypatched scorer, so case1 would legitimately differ. The equivalence
    is verified against the real ensemble instead (dev log 20260821f: diff clean, cases 1-12 at
    chunk size 4); what is checked here is that the two paths classify the NON-scored cases
    identically, which is the part the subprocess boundary cannot affect.
    """
    single, mod = _run(monkeypatch, ensemble, targets_yaml, tmp_path / "s.csv", 0, [])
    chunked, _ = _run(monkeypatch, ensemble, targets_yaml, tmp_path / "c.csv", 2, [])
    assert sorted(single) == sorted(chunked)
    for n in (2, 3, 4):
        assert single[n]["status"] == chunked[n]["status"], f"case{n} classified differently"
