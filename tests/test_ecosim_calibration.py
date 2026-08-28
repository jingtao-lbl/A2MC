#!/usr/bin/env python
"""Backend-dispatched calibration screening for EcoSIM (the turnkey loop's ranking end).

Guards the additive wiring that lets `phases/phase2_screening/screen_ensemble.py` rank an
EcoSIM ensemble through the ModelBackend instead of the FATES SZPF path (dev log 20260713g):
  * `targets_loader` carries per-target extraction specs (variable/pft/window/reduce) onto Target;
  * `_resolve_screening_backend` dispatches (FATES → None, ecosim → backend);
  * the backend branch extracts per case + reduces + ranks, and the ranking honors obs distance.

Self-contained: writes tiny synthetic EcoSIM h0 tapes (no scratch dependency).

Run:  A2MC_MODEL=ecosim a2mc_env/bin/python -m pytest tests/test_ecosim_calibration.py -q
"""
from __future__ import annotations

import os
from pathlib import Path

import numpy as np
import pytest

REPO = Path(__file__).resolve().parent.parent


def _write_tape(case_dir: Path, shoot_pft2: float, root_pft2: float, ntime: int = 300):
    """Write a minimal EcoSIM-shaped h0 tape: SHOOT_C_pft/Root_C_pft (time, pft=3)."""
    import netCDF4 as nc
    case_dir.mkdir(parents=True, exist_ok=True)
    ds = nc.Dataset(case_dir / "case.ecosim.h0.2000-01-01-00000.nc", "w")
    ds.createDimension("time", ntime)
    ds.createDimension("pft", 3)
    for name, pft2_val in (("SHOOT_C_pft", shoot_pft2), ("Root_C_pft", root_pft2)):
        v = ds.createVariable(name, "f4", ("time", "pft"))
        arr = np.zeros((ntime, 3), dtype="f4")
        # a mid-season peak for pft2 (index 1); pft1/pft3 small; spval in a padded tail step
        arr[150:240, 1] = pft2_val
        arr[0, 2] = 1e30  # spval fill — must be masked, not counted as a peak
        v[:] = arr
    ds.close()
    # A COMPLETE case, not just a tape. EcoSIM opens its single h0 tape at initialisation, so a
    # tape alone is evidence the run STARTED; check_case_status requires the restart stamped
    # <final year + 1> that is written only after the last simulated year, and screen_ensemble
    # skips anything not COMPLETED. Without these two files this fixture is a truncated run.
    (case_dir / "runfile.nml").write_text(
        "&ecosim\n    start_date = '20000101000000'\n    forc_periods = 2000, 2022, 1\n/\n")
    (case_dir / "case.ecosim.r.2023-01-01-000000.nc").write_text("restart")


PFT_TARGETS = Path(__file__).resolve().parent / "fixtures" / "ecosim_pft_targets.yaml"


def test_targets_loader_carries_extraction_specs():
    from tools.targets_loader import parse_targets_yaml
    tg = parse_targets_yaml(PFT_TARGETS)
    assert tg, "no targets parsed"
    t = tg["c4_shoot_C"]
    assert t.variable == "SHOOT_C_pft" and t.pft == 1
    assert t.window == [150, 240] and t.reduce == "max"


def test_screening_backend_dispatch(monkeypatch):
    from phases.phase2_screening.screen_ensemble import _resolve_screening_backend
    monkeypatch.delenv("A2MC_MODEL", raising=False)
    assert _resolve_screening_backend() is None          # FATES → SZPF path
    monkeypatch.setenv("A2MC_MODEL", "ecosim")
    assert type(_resolve_screening_backend()).__name__ == "EcoSIMBackend"


def test_backend_screening_ranks_ensemble(tmp_path, monkeypatch):
    monkeypatch.setenv("A2MC_MODEL", "ecosim")
    from tools.targets_loader import parse_targets_yaml
    from phases.phase2_screening.screen_ensemble import screen_ensemble, ScreeningConfig

    # observed for c3_shoot_C (pft2) is 100.0 in the BioCON targets.yaml.
    # case2 (shoot pft2 = 95) is closer to obs than case1 (= 20) → case2 must rank better.
    _write_tape(tmp_path / "BioCON_case1", shoot_pft2=20.0, root_pft2=160.0)
    _write_tape(tmp_path / "BioCON_case2", shoot_pft2=95.0, root_pft2=160.0)

    tg = parse_targets_yaml(PFT_TARGETS)
    cfg = ScreeningConfig(data_dir=tmp_path, year_start=2000, year_end=2022)
    res = screen_ensemble(tmp_path, tg, config=cfg, top_n=2, verbose=False)

    assert res.best_case_num == 2, "the case closer to observed shoot C should rank best"
    # spval was masked: the c3 peak must be the 95 we wrote, not 1e30
    assert res.best_cost < 1.0


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
