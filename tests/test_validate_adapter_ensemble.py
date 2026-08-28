"""`validate_adapter_ensemble.py` -- tertiary-surface awareness (R3).

Without `--tertiary-base`, the validator only ever looked at the primary parameter file, so an
R3 ensemble (48 params spanning primary + tertiary NetCDFs) would validate "clean" while never
actually checking 8 of its 48 parameters -- a silent under-coverage gap, not a crash. These tests
build a real multi-surface ensemble with materialize_adapter_ensemble.py, then confirm the
validator (a) passes it end-to-end when `--tertiary-base` is given, and (b) actually catches a
tampered tertiary value rather than missing it.

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


def _run(monkeypatch, module_name, argv):
    import importlib
    mod = importlib.import_module(f"scripts.{module_name}")
    monkeypatch.setattr(sys, "argv", [f"{module_name}.py"] + argv)
    return mod.main()


@pytest.fixture
def multisurface_ensemble(tmp_path, monkeypatch):
    """A real 2-case multi-surface ensemble (materialized, not hand-built)."""
    micpar_base = tmp_path / "MicrobePars_base.nc"
    _write_micpar_fixture(micpar_base)
    plist = tmp_path / "params_r3.csv"
    _write_param_list(plist, [
        ("VCMX", 1, 28, 84, 56),
        ("RCCZ", "-", 0.04175, 0.54275, 0.167),
        ("SPORC", 1, 1.875, 30.0, 7.5),
    ])
    matrix = tmp_path / "matrix.txt"
    np.savetxt(matrix, np.array([[70.0, 0.3, 15.0], [60.0, 0.2, 10.0]]))
    run_root = tmp_path / "runs"

    # A real base namelist (not the no-namelist stub) so create_case() actually repoints
    # pft_file_in/micpar_file_in, exactly like R3's real run_r3_hourly.nml does.
    base_nml = tmp_path / "run.nml"
    base_nml.write_text(
        "&ecosim\n"
        f"    pft_file_in = '{PFT_FILE}'\n"
        "    micpar_file_in = ''\n"
        "/\n"
    )
    monkeypatch.setenv("A2MC_ECOSIM_BASE_NAMELIST", str(base_nml))

    rc = _run(monkeypatch, "materialize_adapter_ensemble", [
        "--model", "ecosim",
        "--param-list", str(plist),
        "--matrix", str(matrix),
        "--run-root", str(run_root),
        "--base-param", str(PFT_FILE),
        "--tertiary-base", str(micpar_base),
        "--case-pattern", "case{N}",
    ])
    assert rc == 0
    return {"plist": plist, "matrix": matrix, "run_root": run_root, "micpar_base": micpar_base}


def test_validator_passes_a_correct_multisurface_ensemble(multisurface_ensemble, monkeypatch):
    e = multisurface_ensemble
    rc = _run(monkeypatch, "validate_adapter_ensemble", [
        "--model", "ecosim",
        "--param-list", str(e["plist"]),
        "--matrix", str(e["matrix"]),
        "--run-root", str(e["run_root"]),
        "--base-param", str(PFT_FILE),
        "--tertiary-base", str(e["micpar_base"]),
        "--case-pattern", "case{N}",
        "--no-submit-check",
    ])
    assert rc == 0


def test_validator_catches_a_tampered_tertiary_value(multisurface_ensemble, monkeypatch):
    """Without tertiary awareness this tamper would pass silently -- the whole point of the fix."""
    import netCDF4 as nc
    e = multisurface_ensemble
    tampered = e["run_root"] / "case1" / e["micpar_base"].name
    with nc.Dataset(tampered, "a") as ds:
        ds.variables["RCCZ"][...] = 999.0   # nowhere near the expected 0.3

    rc = _run(monkeypatch, "validate_adapter_ensemble", [
        "--model", "ecosim",
        "--param-list", str(e["plist"]),
        "--matrix", str(e["matrix"]),
        "--run-root", str(e["run_root"]),
        "--base-param", str(PFT_FILE),
        "--tertiary-base", str(e["micpar_base"]),
        "--case-pattern", "case{N}",
        "--no-submit-check",
    ])
    assert rc == 1


def test_validator_without_tertiary_base_only_checks_primary(multisurface_ensemble, monkeypatch):
    """Documents the actual gap this session closed: omitting --tertiary-base still validates
    the primary surface fine (backward compatible), it just can't see the tertiary tamper."""
    import netCDF4 as nc
    e = multisurface_ensemble
    tampered = e["run_root"] / "case1" / e["micpar_base"].name
    with nc.Dataset(tampered, "a") as ds:
        ds.variables["RCCZ"][...] = 999.0

    rc = _run(monkeypatch, "validate_adapter_ensemble", [
        "--model", "ecosim",
        "--param-list", str(e["plist"]),
        "--matrix", str(e["matrix"]),
        "--run-root", str(e["run_root"]),
        "--base-param", str(PFT_FILE),
        "--case-pattern", "case{N}",
        "--no-submit-check",
    ])
    # The param list still references RCCZ/SPORC (tertiary-only names), and with no tertiary
    # base given, route_surfaces() can't place them anywhere -- this must refuse loudly (FATAL),
    # not silently validate only VCMX and call it clean.
    assert rc == 2


def test_TWO_calibrated_slots_of_one_variable_are_both_allowed(tmp_path, monkeypatch):
    """REGRESSION (2026-08-14): the untouched-slots check used `k != idx0`, which hardcodes "at
    most one slot per variable is ever calibrated". R3's pre-flight probe calibrates BOTH nactbioms
    slots of SPORC as separate rows, so from row SPORC_1's perspective slot 2 legitimately differs
    from the base — the validator reported 4 false errors per case across all 258 and blocked a
    correct ensemble. The multi-surface tests written the same morning all used a SINGLE slot,
    which is why it survived them.
    """
    micpar_base = tmp_path / "MicrobePars_base.nc"
    _write_micpar_fixture(micpar_base)          # RCCZ scalar + SPORC(nactbioms=2)
    plist = tmp_path / "params_two_slots.csv"
    _write_param_list(plist, [
        ("VCMX", 1, 28, 84, 56),
        ("SPORC", 1, 1.875, 30.0, 7.5),          # both slots calibrated
        ("SPORC", 2, 0.375, 6.0, 1.5),
    ])
    matrix = tmp_path / "matrix.txt"
    np.savetxt(matrix, np.array([[70.0, 20.0, 5.0], [60.0, 3.0, 0.5]]))
    run_root = tmp_path / "runs"

    base_nml = tmp_path / "run.nml"
    base_nml.write_text("&ecosim\n    pft_file_in = '%s'\n    micpar_file_in = ''\n/\n" % PFT_FILE)
    monkeypatch.setenv("A2MC_ECOSIM_BASE_NAMELIST", str(base_nml))

    common = ["--model", "ecosim", "--param-list", str(plist), "--matrix", str(matrix),
              "--run-root", str(run_root), "--base-param", str(PFT_FILE),
              "--tertiary-base", str(micpar_base), "--case-pattern", "case{N}"]
    assert _run(monkeypatch, "materialize_adapter_ensemble", common) == 0
    assert _run(monkeypatch, "validate_adapter_ensemble", common + ["--no-submit-check"]) == 0, \
        "validator rejected an ensemble that calibrates two slots of the same variable"


# ---------------------------------------------------------------------------
# The V0 BASELINE path with a SCALAR parameter (2026-08-18)
# ---------------------------------------------------------------------------
def test_validator_handles_a_baseline_case_containing_a_scalar_parameter(tmp_path, monkeypatch):
    """`--expect-baseline` + a scalar (dims=()) calibrated parameter used to CRASH the validator.

    For the baseline the expected value comes from the BASE file rather than a matrix row, and the
    code read it as `cur_base[var][idx0]`. A scalar row carries `idx0 is None`, and numpy reads
    `arr[None]` as `np.newaxis`, returning a 1-element array that float() rejects:
        TypeError: only 0-dimensional arrays can be converted to Python scalars

    It survived every earlier round because they carried their V0 as a MATRIX ROW rather than a
    separate baseline case, so this branch was never reached with a scalar -- and R3 is the first
    round whose tertiary surface has scalars at all (RCCZ/VMXO/RMOM/GO2X/DCKML are all dims=()).
    Found by running it on the real 59,393-case R3 ensemble, which crashed outright.
    """
    micpar_base = tmp_path / "MicrobePars_base.nc"
    _write_micpar_fixture(micpar_base)
    plist = tmp_path / "params.csv"
    _write_param_list(plist, [
        ("VCMX", 1, 28, 84, 56),
        ("RCCZ", "-", 0.04175, 0.54275, 0.167),      # SCALAR -- the one that crashed it
        ("SPORC", 1, 1.875, 30.0, 7.5),
    ])
    matrix = tmp_path / "matrix.txt"
    np.savetxt(matrix, np.array([[70.0, 0.3, 15.0], [60.0, 0.2, 10.0]]))
    run_root = tmp_path / "runs"
    base_nml = tmp_path / "run.nml"
    base_nml.write_text(f"&ecosim\n    pft_file_in = '{PFT_FILE}'\n    micpar_file_in = ''\n/\n")
    monkeypatch.setenv("A2MC_ECOSIM_BASE_NAMELIST", str(base_nml))

    common = ["--model", "ecosim", "--param-list", str(plist), "--matrix", str(matrix),
              "--run-root", str(run_root), "--base-param", str(PFT_FILE),
              "--tertiary-base", str(micpar_base), "--case-pattern", "case{N}"]
    assert _run(monkeypatch, "materialize_adapter_ensemble",
                common + ["--baseline", "--baseline-index", "0"]) == 0
    # must not raise, and must PASS: the baseline is unperturbed by construction
    assert _run(monkeypatch, "validate_adapter_ensemble",
                common + ["--expect-baseline", "--no-submit-check"]) == 0


def test_validator_catches_a_tampered_scalar_in_the_baseline(tmp_path, monkeypatch):
    """The companion: the baseline check must still FAIL when the scalar is perturbed, or the fix
    above would have bought a crash-free check that cannot detect anything."""
    import netCDF4 as nc
    micpar_base = tmp_path / "MicrobePars_base.nc"
    _write_micpar_fixture(micpar_base)
    plist = tmp_path / "params.csv"
    # two params so the saved matrix is unambiguously 2-D; RCCZ is the scalar under test
    _write_param_list(plist, [("RCCZ", "-", 0.04175, 0.54275, 0.167),
                              ("SPORC", 1, 1.875, 30.0, 7.5)])
    matrix = tmp_path / "matrix.txt"
    np.savetxt(matrix, np.array([[0.3, 15.0], [0.2, 10.0]]))
    run_root = tmp_path / "runs"
    base_nml = tmp_path / "run.nml"
    base_nml.write_text(f"&ecosim\n    pft_file_in = '{PFT_FILE}'\n    micpar_file_in = ''\n/\n")
    monkeypatch.setenv("A2MC_ECOSIM_BASE_NAMELIST", str(base_nml))

    common = ["--model", "ecosim", "--param-list", str(plist), "--matrix", str(matrix),
              "--run-root", str(run_root), "--base-param", str(PFT_FILE),
              "--tertiary-base", str(micpar_base), "--case-pattern", "case{N}"]
    assert _run(monkeypatch, "materialize_adapter_ensemble",
                common + ["--baseline", "--baseline-index", "0"]) == 0

    tampered = run_root / "case0" / micpar_base.name
    with nc.Dataset(tampered, "a") as ds:
        ds.variables["RCCZ"][...] = 0.999          # baseline must be UNperturbed
    assert _run(monkeypatch, "validate_adapter_ensemble",
                common + ["--expect-baseline", "--no-submit-check"]) != 0
