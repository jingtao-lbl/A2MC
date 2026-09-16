"""End-to-end smoke test for the EcoSIM adapter (roadmap Phase E).

Drives the full offline chain against the shipped BioCON reference data, without
an HPC run (submission is dry-run; extraction/evaluation use the reference h0
tape as a stand-in for a completed case):

    adapter/spec/backend load
      -> parse the PFT parameter file
      -> load provisional bounds (Phase-0 parse_param_list)
      -> build parameter sets (bound corners)
      -> write_parameter_file (per-PFT + broadcast mods on the .nc)
      -> create_case + submit_ensemble (dry-run)
      -> extract_history_variables (from the reference tape)
      -> evaluate_ecosim_case (L3.1 obs<->sim alignment + generic cost)

Run:  a2mc_env/bin/python -m pytest tests/test_ecosim_e2e.py -v

Author: Jing Tao with Claude
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

REPO = Path(__file__).resolve().parent.parent
PFT_FILE = REPO / "Offline/EcoSIM_sample_files/input/ds_input__pft_test__ex1.nc"
TAPE_DIR = REPO / "Offline/EcoSIM_sample_files/output"
BOUNDS = REPO / "models/ecosim/reference_bounds/ecosim_biocon_param_list.csv"

pytestmark = pytest.mark.skipif(
    not (PFT_FILE.exists() and TAPE_DIR.exists() and BOUNDS.exists()),
    reason="EcoSIM BioCON reference data not present",
)


def test_adapter_and_parsing():
    from models.ecosim.backend import EcoSIMBackend
    be = EcoSIMBackend()
    assert be.spec.name == "ecosim"
    params = be.parse_parameters(PFT_FILE)
    assert "VCMX" in params and "UPMXPO" in params
    # PFT axis resolves to 3 (BioCON test1_ex1)
    parser = be.spec.parameter_parser_class()
    parser.parse(PFT_FILE)
    assert parser.get_pft_count() == 3


def test_bounds_parse():
    from phases.phase0_design.create_parameter_sample import parse_param_list
    names, lower, upper = parse_param_list(BOUNDS)
    assert len(names) == 32
    assert np.all(lower < upper) and not np.any(np.isnan(lower)) and not np.any(np.isnan(upper))


def test_full_chain(tmp_path):
    from models.ecosim.backend import EcoSIMBackend
    from phases.phase0_design.create_parameter_sample import parse_param_list
    from tools.ecosim_evaluate_case import evaluate_ecosim_case

    be = EcoSIMBackend()
    names, lower, upper = parse_param_list(BOUNDS)

    # Two parameter sets at the bound corners (deterministic stand-in for a
    # Morris sample; the full Morris path is exercised by create_parameter_sample).
    samples = {"case_lo": dict(zip(names, lower)), "case_hi": dict(zip(names, upper))}

    cfg = {
        "A2MC_OUTPUT_DIR": str(tmp_path / "runs"),
        "A2MC_DRY_RUN": "1",
        "A2MC_ECOSIM_BINARY": "/does/not/need/to/exist/ecosim.f90.x",
    }

    case_dirs = []
    for case_name, mods in samples.items():
        # Apply each sampled value to PFT slot 1 (the dominant BioCON PFT).
        pmods = {f"{n}_1": v for n, v in mods.items()}
        pfile = tmp_path / f"{case_name}.nc"
        be.write_parameter_file(PFT_FILE, pmods, pfile)
        # Confirm the write took on a spot-check parameter.
        import netCDF4 as nc
        with nc.Dataset(pfile) as d:
            assert np.isclose(d.variables["VCMX"][0], mods["VCMX"])
        cd = be.create_case(case_name, pfile, cfg)
        assert (cd / "submit.sh").exists() and (cd / "runfile.nml").exists()
        case_dirs.append(cd)

    # Dry-run submit → synthetic ids, one per case.
    ids = be.submit_ensemble(case_dirs, cfg)
    assert len(ids) == 2 and all(i.startswith("DRYRUN-") for i in ids)

    # Extraction + evaluation stand-in: use the reference tape as a "completed case".
    targets = [
        {"name": "LEAF_C_pft1", "variable": "LEAF_C_pft", "pft": 1, "time": -1, "observed": 50.0},
        {"name": "NPP_pft1", "variable": "NPP_pft", "pft": 1, "window": [0, 11], "reduce": "mean", "observed": 1.0},
    ]
    total, errors, sim = evaluate_ecosim_case(TAPE_DIR, targets, backend=be)
    assert set(errors) == {"LEAF_C_pft1", "NPP_pft1"}
    assert np.isfinite(total) and total >= 0
    for name in errors:
        assert np.isfinite(sim[name])


def test_create_case_rejects_oversized_namelist(tmp_path):
    """create_case() must fail loudly, not at sbatch, if the runfile would exceed EcoSIM's fixed
    4096-byte namelist read buffer (fileUtil.F90:25) -- hit for real 2026-08-10, 20260810e_*.md."""
    from models.ecosim.backend import EcoSIMBackend
    be = EcoSIMBackend()

    pfile = tmp_path / "base.nc"
    pfile.write_bytes(PFT_FILE.read_bytes())

    oversized_nml = tmp_path / "oversized.nml"
    oversized_nml.write_text("&ecosim\n" + ("! padding line to blow the buffer\n" * 200) + "/\n")
    cfg_big = {"A2MC_OUTPUT_DIR": str(tmp_path / "runs_big"),
               "A2MC_ECOSIM_BASE_NAMELIST": str(oversized_nml)}
    with pytest.raises(ValueError, match="namelist read buffer"):
        be.create_case("case_oversized", pfile, cfg_big)

    fine_nml = tmp_path / "fine.nml"
    fine_nml.write_text("&ecosim\n    case_name = 'x'\n/\n")
    cfg_fine = {"A2MC_OUTPUT_DIR": str(tmp_path / "runs_fine"),
                "A2MC_ECOSIM_BASE_NAMELIST": str(fine_nml)}
    cd = be.create_case("case_fine", pfile, cfg_fine)
    assert (cd / "runfile.nml").exists()


def test_run_r3_hourly_namelist_fits_the_buffer():
    """The LIVE R3 base namelist (ecosim_biocon_config_r3.sh's A2MC_ECOSIM_BASE_NAMELIST) must
    itself stay under the 4096-byte buffer, since create_case() copies it near-verbatim -- this
    was violated once already (5023 bytes, 20260810e_*.md Errata) and must not regress silently."""
    from models.ecosim.backend import EcoSIMBackend
    nml = REPO / "use_cases/EcoSIM_BioCON/case_template/run_r3_hourly.nml"
    assert len(nml.read_bytes()) < EcoSIMBackend._NAMELIST_BUFFER_BYTES


def test_evaluate_on_real_tape():
    """L3.1 alignment + generic cost on the REAL reference EcoSIM tape.

    Uses peak-season / annual-mean reductions (a year-end snapshot of LEAF_C is 0
    from winter senescence) and a NEGATIVE-index window (regression for the
    window `series[lo:hi+1]` empty-slice bug when hi == -1).
    """
    from models.ecosim.backend import EcoSIMBackend
    from tools.ecosim_evaluate_case import evaluate_ecosim_case, reduce_ecosim_target

    be = EcoSIMBackend()
    ext = be.extract_history_variables(TAPE_DIR, ["LEAF_C_pft", "NPP_pft"])
    # negative-index window must not select an empty slice
    peak = reduce_ecosim_target(ext, {"variable": "LEAF_C_pft", "pft": 1, "window": [-365, -1], "reduce": "max"})
    assert np.isfinite(peak) and peak > 0

    targets = [
        {"name": "peak_LEAF_C", "variable": "LEAF_C_pft", "pft": 1, "window": [-365, -1], "reduce": "max", "observed": peak * 1.1},
        {"name": "annual_NPP", "variable": "NPP_pft", "pft": 1, "window": [-365, -1], "reduce": "mean", "observed": 0.04},
    ]
    total, errors, sim = evaluate_ecosim_case(TAPE_DIR, targets, backend=be)
    assert np.isfinite(total) and total >= 0
    assert set(errors) == {"peak_LEAF_C", "annual_NPP"} and all(np.isfinite(v) for v in sim.values())


def test_write_parameter_file_guards(tmp_path):
    from models.ecosim.backend import EcoSIMBackend
    be = EcoSIMBackend()
    # unknown parameter must raise, not silently no-op
    with pytest.raises(KeyError):
        be.write_parameter_file(PFT_FILE, {"NOTAPARAM": 1.0}, tmp_path / "x.nc")
    # out-of-range PFT index must raise
    with pytest.raises(IndexError):
        be.write_parameter_file(PFT_FILE, {"VCMX_99": 1.0}, tmp_path / "y.nc")
    # an unrecognized surface name must raise, not silently no-op.
    # "quaternary" was the example here until 2026-09-15, when it became a REAL surface
    # (the grid/soil file). Using a live surface name as the negative case is how such a
    # test goes green-to-red the day the thing it names gets implemented, so the example
    # is now a name no adapter will ever claim.
    with pytest.raises(ValueError, match="primary.*secondary.*tertiary.*quaternary"):
        be.write_parameter_file(PFT_FILE, {}, tmp_path / "z.nc", surface="quinary")


def _make_micpar_fixture(path):
    """A minimal MicrobePars.nc-shaped file for testing the TERTIARY surface, without
    depending on real reference data (none is shipped in Offline/EcoSIM_sample_files).
    Shape verified against the real base 2026-08-13 (RCCZ scalar, SPORC nactbioms(2))."""
    import netCDF4 as nc
    with nc.Dataset(path, "w") as ds:
        ds.createDimension("nactbioms", 2)
        rccz = ds.createVariable("RCCZ", "f4")
        rccz[...] = 0.167
        sporc = ds.createVariable("SPORC", "f4", ("nactbioms",))
        sporc[:] = [7.5, 1.5]


def test_write_parameter_file_tertiary_surface(tmp_path):
    """The TERTIARY surface (MicrobePars.nc: RCCZ/VMXO/RMOM/GO2X/SPORC/SPOMC, wired
    2026-08-13 to run R3's promoted top-6 soil-BGC parameters) uses the SAME plain
    named-variable writer as "primary" -- a bare name broadcasts/sets the whole
    variable, NAME_<slot> writes one nactbioms element."""
    from models.ecosim.backend import EcoSIMBackend
    be = EcoSIMBackend()
    base = tmp_path / "MicrobePars_base.nc"
    _make_micpar_fixture(base)

    out = tmp_path / "MicrobePars_case1.nc"
    be.write_parameter_file(base, {"RCCZ": 0.5, "SPORC_1": 10.0}, out, surface="tertiary")

    import netCDF4 as nc
    with nc.Dataset(out) as ds:
        assert np.isclose(float(ds.variables["RCCZ"][...]), 0.5)
        sporc = ds.variables["SPORC"][:]
        assert np.isclose(sporc[0], 10.0)          # slot 1 changed
        assert np.isclose(sporc[1], 1.5)            # slot 2 untouched


def test_create_case_stages_and_repoints_tertiary(tmp_path):
    """create_case(tertiary_param_file=...) stages the file and repoints
    spec.tertiary_namelist_var ("micpar_file_in") -- same mechanism as the existing
    secondary surface. Uses the REAL R3 live base namelist so this also confirms the
    repointed result stays under EcoSIM's 4096-byte buffer with a realistic staged
    path, not just the static template (test_run_r3_hourly_namelist_fits_the_buffer
    only checks the latter)."""
    from models.ecosim.backend import EcoSIMBackend
    be = EcoSIMBackend()

    pfile = tmp_path / "base.nc"
    pfile.write_bytes(PFT_FILE.read_bytes())
    micpar = tmp_path / "MicrobePars_case1.nc"
    _make_micpar_fixture(micpar)

    base_nml = REPO / "use_cases/EcoSIM_BioCON/case_template/run_r3_hourly.nml"
    # A deep, realistic output root -- longer than a tmp_path -- so the repointed
    # micpar_file_in line is at least as long as a real ensemble case would produce.
    long_root = tmp_path / "R3_40Para_Sobol_20260813" / "BioCON_case0001_a_realistically_long_run_root"
    cfg = {"A2MC_OUTPUT_DIR": str(long_root), "A2MC_ECOSIM_BASE_NAMELIST": str(base_nml)}

    cd = be.create_case("case1", pfile, cfg, tertiary_param_file=micpar)
    runfile = cd / "runfile.nml"
    assert runfile.exists()
    assert len(runfile.read_bytes()) < EcoSIMBackend._NAMELIST_BUFFER_BYTES

    text = runfile.read_text()
    staged_micpar = cd / micpar.name
    assert staged_micpar.is_file()
    assert f"micpar_file_in = '{staged_micpar}'" in text


def test_create_case_tertiary_missing_var_raises(tmp_path):
    """If the base namelist has no micpar_file_in line at all, a tertiary_param_file
    must fail loudly (mirrors the existing secondary-surface KeyError), not silently
    drop the surface."""
    from models.ecosim.backend import EcoSIMBackend
    be = EcoSIMBackend()

    pfile = tmp_path / "base.nc"
    pfile.write_bytes(PFT_FILE.read_bytes())
    micpar = tmp_path / "MicrobePars_case1.nc"
    _make_micpar_fixture(micpar)

    nml = tmp_path / "no_micpar.nml"
    nml.write_text("&ecosim\n    case_name = 'x'\n/\n")
    cfg = {"A2MC_OUTPUT_DIR": str(tmp_path / "runs"), "A2MC_ECOSIM_BASE_NAMELIST": str(nml)}

    with pytest.raises(KeyError, match="tertiary_param_file"):
        be.create_case("case_notertiary", pfile, cfg, tertiary_param_file=micpar)
