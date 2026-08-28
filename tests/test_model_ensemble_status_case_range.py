"""--case-range on tools/model_ensemble_status.py.

Added 2026-08-20 when the tool was armed as the -x refresh hook of
tools/watch_slurm_array.sh for the EcoSIM_BioCON R3 prefix. A chunked array runs a SLICE of a
materialized ensemble (4,989 of 59,393 case dirs), and scanning the whole root took >2 min --
unusable as a per-poll hook.
"""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from tools.model_ensemble_status import parse_case_range, case_index, scan  # noqa: E402


@pytest.mark.parametrize("spec,expect", [
    ("0-4988", (0, 4988)),
    ("4989-9918", (4989, 9918)),
    (" 7 - 9 ", (7, 9)),
    ("5-5", (5, 5)),
])
def test_parse_case_range_ok(spec, expect):
    assert parse_case_range(spec) == expect


@pytest.mark.parametrize("bad", ["", "abc", "5", "5-", "-5", "9-3", "1-2-3"])
def test_parse_case_range_rejects(bad):
    with pytest.raises(ValueError):
        parse_case_range(bad)


def test_case_index_reads_trailing_integer():
    assert case_index("BioCON_case4988") == 4988
    assert case_index("BioCON_case0") == 0
    assert case_index("logs") is None
    # a name whose digits are not at the end must not be mistaken for an index
    assert case_index("R3_28Para_Sobol_base") is None


def _mk(root: Path, names):
    for n in names:
        d = root / n
        d.mkdir()
        (d / "submit.sh").write_text("#!/bin/bash\n")


def test_scan_filters_to_the_range(tmp_path, monkeypatch):
    _mk(tmp_path, [f"BioCON_case{i}" for i in range(6)] + ["logs"])
    (tmp_path / "logs" / "submit.sh").unlink()   # logs/ is not a case dir

    import tools.model_ensemble_status as m
    monkeypatch.setattr(m, "_sacct_state", lambda jid: None)

    class _B:
        def check_case_status(self, cd):
            return "COMPLETED"

    monkeypatch.setattr(m, "scan", m.scan)  # keep the real scan
    import models.registry as reg
    monkeypatch.setattr(reg, "get_model", lambda name: _B())

    rows = scan("ecosim", tmp_path, case_range=(2, 4))
    got = sorted(r[0] for r in rows)
    assert got == ["BioCON_case2", "BioCON_case3", "BioCON_case4"]


def test_scan_without_range_returns_all(tmp_path, monkeypatch):
    _mk(tmp_path, [f"BioCON_case{i}" for i in range(4)])
    import tools.model_ensemble_status as m
    monkeypatch.setattr(m, "_sacct_state", lambda jid: None)

    class _B:
        def check_case_status(self, cd):
            return "COMPLETED"

    import models.registry as reg
    monkeypatch.setattr(reg, "get_model", lambda name: _B())

    rows = scan("ecosim", tmp_path)
    assert len(rows) == 4
