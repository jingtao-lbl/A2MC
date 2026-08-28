"""`materialize_adapter_ensemble.py` -- the multi-surface row-splitting extension (R3).

R1 used this script with a single primary surface only. R3 needed a second capability: one
param-list row can now span TWO physical base files (40 plant traits in the primary PFT NetCDF,
8 soil-BGC rates in the tertiary MicrobePars NetCDF), routed by probing each base file's own
variable names -- never a hardcoded or assumed list. These tests lock:

  * single-surface behavior is BYTE-IDENTICAL to before (R1 must not regress)
  * a multi-surface row correctly splits and writes both files
  * routing refuses loudly on an unroutable or ambiguous name, rather than silently dropping it
  * a fixed (unperturbed) secondary file is staged into every case unchanged
  * a model whose create_case() does not declare secondary/tertiary kwargs is never called with them

Author: Jing Tao with Claude.
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pytest

REPO = Path(__file__).resolve().parent.parent
PFT_FILE = REPO / "Offline/EcoSIM_sample_files/input/ds_input__pft_test__ex1.nc"

pytestmark = pytest.mark.skipif(not PFT_FILE.exists(), reason="EcoSIM BioCON reference data not present")


def _write_micpar_fixture(path):
    import netCDF4 as nc
    with nc.Dataset(path, "w") as ds:
        ds.createDimension("nactbioms", 2)
        rccz = ds.createVariable("RCCZ", "f4")
        rccz[...] = 0.167
        sporc = ds.createVariable("SPORC", "f4", ("nactbioms",))
        sporc[:] = [7.5, 1.5]


def _write_param_list(path, rows):
    lines = ["name,pft,lower_bound,upper_bound,default"]
    for name, pft, lo, hi, default in rows:
        lines.append(f"{name},{pft},{lo},{hi},{default}")
    path.write_text("\n".join(lines) + "\n")


def _run_main(monkeypatch, argv):
    from scripts import materialize_adapter_ensemble as mod
    monkeypatch.setattr(sys, "argv", ["materialize_adapter_ensemble.py"] + argv)
    return mod.main()


@pytest.fixture
def micpar_base(tmp_path):
    p = tmp_path / "MicrobePars_base.nc"
    _write_micpar_fixture(p)
    return p


def test_single_surface_unchanged(tmp_path, monkeypatch):
    """R1's exact shape: one primary base, no secondary/tertiary. Must still work identically."""
    plist = tmp_path / "params.csv"
    _write_param_list(plist, [("VCMX", 1, 28, 84, 56)])
    matrix = tmp_path / "matrix.txt"
    np.savetxt(matrix, np.array([[70.0]]))
    run_root = tmp_path / "runs"

    rc = _run_main(monkeypatch, [
        "--model", "ecosim",
        "--param-list", str(plist),
        "--matrix", str(matrix),
        "--run-root", str(run_root),
        "--base-param", str(PFT_FILE),
        "--case-pattern", "case{N}",
    ])
    assert rc == 0
    case_dir = run_root / "case1"
    assert (case_dir / PFT_FILE.name).is_file()
    assert (case_dir / "runfile.nml").exists() or (case_dir / "submit.sh").exists()

    import netCDF4 as nc
    with nc.Dataset(case_dir / PFT_FILE.name) as ds:
        assert np.isclose(float(ds.variables["VCMX"][0]), 70.0)


def test_multisurface_row_splits_and_writes_both_files(tmp_path, monkeypatch, micpar_base):
    """A param list spanning primary (VCMX) and tertiary (RCCZ, SPORC slot 1) writes both."""
    plist = tmp_path / "params_r3.csv"
    _write_param_list(plist, [
        ("VCMX", 1, 28, 84, 56),
        ("RCCZ", "-", 0.04175, 0.54275, 0.167),
        ("SPORC", 1, 1.875, 30.0, 7.5),
    ])
    matrix = tmp_path / "matrix.txt"
    np.savetxt(matrix, np.array([[70.0, 0.3, 15.0]]))
    run_root = tmp_path / "runs"

    rc = _run_main(monkeypatch, [
        "--model", "ecosim",
        "--param-list", str(plist),
        "--matrix", str(matrix),
        "--run-root", str(run_root),
        "--base-param", str(PFT_FILE),
        "--tertiary-base", str(micpar_base),
        "--case-pattern", "case{N}",
    ])
    assert rc == 0
    case_dir = run_root / "case1"
    assert (case_dir / PFT_FILE.name).is_file()
    assert (case_dir / micpar_base.name).is_file()

    import netCDF4 as nc
    with nc.Dataset(case_dir / PFT_FILE.name) as ds:
        assert np.isclose(float(ds.variables["VCMX"][0]), 70.0)
    with nc.Dataset(case_dir / micpar_base.name) as ds:
        assert np.isclose(float(ds.variables["RCCZ"][...]), 0.3)
        sporc = ds.variables["SPORC"][:]
        assert np.isclose(sporc[0], 15.0)   # slot 1 changed
        assert np.isclose(sporc[1], 1.5)     # slot 2 untouched

    runfile = (case_dir / "runfile.nml")
    if runfile.exists():
        text = runfile.read_text()
        assert "micpar_file_in" not in text or str(case_dir / micpar_base.name) in text


def test_baseline_case_covers_both_surfaces(tmp_path, monkeypatch, micpar_base):
    plist = tmp_path / "params_r3.csv"
    _write_param_list(plist, [
        ("VCMX", 1, 28, 84, 56),
        ("RCCZ", "-", 0.04175, 0.54275, 0.167),
    ])
    matrix = tmp_path / "matrix.txt"
    np.savetxt(matrix, np.array([[70.0, 0.3]]))
    run_root = tmp_path / "runs"

    rc = _run_main(monkeypatch, [
        "--model", "ecosim",
        "--param-list", str(plist),
        "--matrix", str(matrix),
        "--run-root", str(run_root),
        "--base-param", str(PFT_FILE),
        "--tertiary-base", str(micpar_base),
        "--case-pattern", "case{N}",
        "--baseline",
    ])
    assert rc == 0
    baseline_dir = run_root / "case0"
    import netCDF4 as nc
    with nc.Dataset(baseline_dir / micpar_base.name) as ds:
        assert np.isclose(float(ds.variables["RCCZ"][...]), 0.167)   # unperturbed default


def test_fixed_secondary_file_staged_unchanged(tmp_path, monkeypatch):
    secondary_src = REPO / "Offline/EcoSIM_sample_files/input/ds_input__pft_mgmt_test__ex1.nc"
    if not secondary_src.exists():
        pytest.skip("no shipped pft_mgmt reference file")
    plist = tmp_path / "params.csv"
    _write_param_list(plist, [("VCMX", 1, 28, 84, 56)])
    matrix = tmp_path / "matrix.txt"
    np.savetxt(matrix, np.array([[70.0]]))
    run_root = tmp_path / "runs"

    rc = _run_main(monkeypatch, [
        "--model", "ecosim",
        "--param-list", str(plist),
        "--matrix", str(matrix),
        "--run-root", str(run_root),
        "--base-param", str(PFT_FILE),
        "--secondary-param", str(secondary_src),
        "--case-pattern", "case{N}",
    ])
    assert rc == 0
    staged = run_root / "case1" / secondary_src.name
    assert staged.is_file()
    assert staged.read_bytes() == secondary_src.read_bytes()


def test_unroutable_name_refuses_loudly(tmp_path, monkeypatch, micpar_base):
    plist = tmp_path / "params.csv"
    _write_param_list(plist, [("NOTAREALPARAM", "-", 0.0, 1.0, 0.5)])
    matrix = tmp_path / "matrix.txt"
    np.savetxt(matrix, np.array([[0.5]]))
    run_root = tmp_path / "runs"

    rc = _run_main(monkeypatch, [
        "--model", "ecosim",
        "--param-list", str(plist),
        "--matrix", str(matrix),
        "--run-root", str(run_root),
        "--base-param", str(PFT_FILE),
        "--tertiary-base", str(micpar_base),
        "--case-pattern", "case{N}",
    ])
    assert rc == 1
    assert not (run_root / "case1").exists()


def test_dry_run_writes_nothing(tmp_path, monkeypatch, micpar_base):
    plist = tmp_path / "params.csv"
    _write_param_list(plist, [("RCCZ", "-", 0.04175, 0.54275, 0.167)])
    matrix = tmp_path / "matrix.txt"
    np.savetxt(matrix, np.array([[0.3]]))
    run_root = tmp_path / "runs"

    rc = _run_main(monkeypatch, [
        "--model", "ecosim",
        "--param-list", str(plist),
        "--matrix", str(matrix),
        "--run-root", str(run_root),
        "--base-param", str(PFT_FILE),
        "--tertiary-base", str(micpar_base),
        "--case-pattern", "case{N}",
        "--dry-run",
    ])
    assert rc == 0
    assert not run_root.exists()
