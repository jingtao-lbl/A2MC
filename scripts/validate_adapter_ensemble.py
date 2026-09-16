#!/usr/bin/env python3
"""Validate a MATERIALIZED adapter ensemble before submission — a hard pre-submit gate.

The adapter analog of FATES's tools/validate_submission_plan.py + verify_parameter_file.py. For
EVERY case dir it re-derives the expected edits from the matrix + param list (the SAME parser that
built the matrix) and asserts the on-disk parameter file, namelist, and submit script match:

  1. STRUCTURE   — every expected case dir exists (baseline + 1..N), each with the param .nc(s) +
                   runfile.nml + submit.sh (a tertiary .nc too, if `--tertiary-base` is given).
  2. PARAM FILE  — for every calibrated (name, pft): the case's NC value == float32(matrix[i][j])
                   (catches wrong value / wrong parameter / wrong PFT); every OTHER PFT of that
                   variable == the base (untouched); values within [lower, upper]. Routed to the
                   PRIMARY or TERTIARY file by probing each base file's own variable names (same
                   routing as materialize_adapter_ensemble.py — never a hardcoded/assumed list).
  3. BASELINE    — the V0 case (if present) is byte-unperturbed (every calibrated PFT == base, on
                   whichever surface it belongs to).
  4. NON-CALIB   — a sample of non-calibrated variables == the base (nothing else was written), on
                   every surface a base file was given for.
  5. NAMELIST    — pft_file_in (and micpar_file_in, if tertiary) point at THIS case's own staged
                   file; the other inputs are absolute and exist.
  6. SUBMIT      — submit.sh names an existing model binary and the case's runfile.

Exit 0 = all green. Non-zero = at least one case failed (prints the first offenders).

Env defaults (source a2mc_noncime_config.sh + the site config first): A2MC_MODEL, A2MC_PARAM_LIST_FILE,
A2MC_ENSEMBLE_MATRIX_FILE, A2MC_OUTPUT_DIR, A2MC_BASE_PARAM_FILE, A2MC_BASE_PARAM_FILE_3 (tertiary,
optional), A2MC_CASE_NAME_PATTERN.
"""

from __future__ import annotations

import argparse
import os
import re
import sys
from pathlib import Path

import numpy as np

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from scripts.create_adapter_parameter_sample import (  # noqa: E402
    secondary_base_default, warn_if_legacy_secondary,
    parse_pft_param_list, canonical_pft_id, nc_varnames, route_surfaces, parse_param_modes,
)

_CID_RE = re.compile(r"^(?P<name>[A-Za-z][A-Za-z0-9_]*?)_(?P<pft>\d+)$")





def _decompose(cid: str):
    """canonical id -> (varname, pft0-based-index or None for broadcast)."""
    m = _CID_RE.match(cid)
    if m:
        return m.group("name"), int(m.group("pft")) - 1
    return cid, None  # bare name = broadcast to all PFTs


def _case_name(pattern: str, n) -> str:
    return pattern.replace("{N}", str(n))


def _check_submit_script(script: Path, run_root: Path, sample_ids, case_pattern=None):
    """Dry-run the ENSEMBLE array submit script's task dispatch for sample SLURM_ARRAY_TASK_IDs.

    Runs the real script with SLURM_ARRAY_TASK_ID set and `srun` stubbed to a no-op, so it exercises
    the ACTUAL case-dir resolution + hard preconditions (case dir exists, binary executable) without
    launching a job. A broken dispatch (e.g. a stray-brace `BioCON_case4}`, a missing binary) exits 2 /
    prints an `ERROR:` line; a good one reaches the (stubbed) run. This closes the gap that let a
    bash brace-substitution bug fail every array task after per-case validation passed (`20260716a`).
    Returns a list of problem strings.
    """
    import subprocess
    import tempfile
    import shutil as _sh

    problems = []
    stub = Path(tempfile.mkdtemp())
    (stub / "srun").write_text("#!/bin/bash\nexit 0\n")
    os.chmod(stub / "srun", 0o755)
    env = dict(os.environ)
    env["PATH"] = str(stub) + os.pathsep + env.get("PATH", "")
    # The dry-check must use the pattern the VALIDATION is running against, not whatever the
    # ambient environment holds. Without this the check resolved the config's default pattern and
    # reported `no case dir <default>0` for every task of an EXPERIMENT run root, which is a false
    # negative that cost two cycles a --no-submit-check workaround.
    if case_pattern:
        env["A2MC_CASE_NAME_PATTERN"] = case_pattern
    try:
        for tid in sample_ids:
            env["SLURM_ARRAY_TASK_ID"] = str(tid)
            try:
                r = subprocess.run(["bash", str(script)], env=env, cwd=str(run_root),
                                   capture_output=True, text=True, timeout=60)
            except Exception as e:  # noqa: BLE001
                problems.append(f"task {tid}: dry-run raised {e}"); continue
            out = r.stdout + r.stderr
            # exit 2 = a hard precondition failure (case dir missing / binary not executable);
            # an `ERROR:` line reports which. A clean dispatch reaches the stubbed srun (exit 0/1).
            if r.returncode == 2 or "ERROR:" in out:
                errline = [l for l in out.splitlines() if "ERROR" in l]
                problems.append(f"task {tid}: {errline[-1].strip() if errline else 'exit 2 (precondition failed)'}")
    finally:
        _sh.rmtree(stub, ignore_errors=True)
    return problems


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--model", default=os.environ.get("A2MC_MODEL"))
    ap.add_argument("--param-list", default=os.environ.get("A2MC_PARAM_LIST_FILE"))
    ap.add_argument("--matrix", default=os.environ.get("A2MC_ENSEMBLE_MATRIX_FILE"))
    ap.add_argument("--run-root", default=os.environ.get("A2MC_OUTPUT_DIR"))
    ap.add_argument("--base-param", default=os.environ.get("A2MC_BASE_PARAM_FILE"))
    _sec_default, _sec_env = secondary_base_default()
    warn_if_legacy_secondary(_sec_env)
    ap.add_argument("--secondary-param", default=_sec_default,
                    help="secondary base file, if the param list samples that surface (e.g. EcoSIM "
                         "pft_mgmt PPI) — default $A2MC_SECONDARY_PARAM_FILE")
    ap.add_argument("--quaternary-base", default=os.environ.get("A2MC_BASE_PARAM_FILE_4"),
                    help="quaternary base file, if the param list spans a 4th surface (EcoSIM = the "
                         "grid/soil NetCDF) — default $A2MC_BASE_PARAM_FILE_4; omit when unused")
    ap.add_argument("--tertiary-base", default=os.environ.get("A2MC_BASE_PARAM_FILE_3"),
                    help="tertiary base file, if the param list spans a 3rd surface (e.g. EcoSIM "
                         "MicrobePars.nc) — default $A2MC_BASE_PARAM_FILE_3; omit for a single-surface ensemble")
    ap.add_argument("--case-pattern", default=os.environ.get("A2MC_CASE_NAME_PATTERN"))
    ap.add_argument("--baseline-index", default="0")
    ap.add_argument("--expect-baseline", action="store_true", help="require the V0 baseline case to exist")
    ap.add_argument("--rtol", type=float, default=1e-5, help="float32 relative tolerance for value checks")
    ap.add_argument("--max-report", type=int, default=15)
    ap.add_argument("--submit-script", default=None,
                    help="ensemble array submit script to dry-check (default <use-case>/case_template/submit_ensemble_array.sh)")
    ap.add_argument("--no-submit-check", action="store_true", help="skip the submit-script dry-check")
    args = ap.parse_args()

    import netCDF4 as nc

    names, lower, upper = parse_pft_param_list(args.param_list)
    decomp = [_decompose(c) for c in names]
    X = np.loadtxt(args.matrix)
    if X.ndim == 1:
        X = X.reshape(1, -1)
    n_rows, n_cols = X.shape
    run_root = Path(args.run_root)
    base_ds = nc.Dataset(args.base_param)
    base = {v: np.asarray(base_ds.variables[v][:]).ravel() for v in base_ds.variables}
    base_ds.close()
    base_name = Path(args.base_param).name

    tertiary_path = Path(args.tertiary_base) if args.tertiary_base else None
    tertiary_name = tertiary_path.name if tertiary_path else None
    quaternary_path = Path(args.quaternary_base) if args.quaternary_base else None
    quaternary_name = quaternary_path.name if quaternary_path else None
    tertiary_base_vals = {}
    # SECONDARY surface: a sampled value here was UNVERIFIED before 2026-09-01, because the
    # surface could only be staged fixed and so never needed checking. Its base value is read
    # through the BACKEND rather than as a NetCDF variable -- EcoSIM's PPI is a token inside a
    # fixed-width string, invisible to `nc_varnames`.
    # The secondary surface is model-dispatched (declared names + a token reader), so unlike the
    # NetCDF surfaces this validator now needs the backend itself.
    import importlib
    from models import registry as _registry
    try:
        importlib.import_module(f"models.{args.model}")
        backend = _registry.get_model(args.model)
    except Exception as e:
        print(f"FATAL: model '{args.model}' not onboarded: {e}", file=sys.stderr)
        return 2

    secondary_path = Path(args.secondary_param) if getattr(args, "secondary_param", None) else None
    modes = parse_param_modes(args.param_list)
    secondary_base_vals = {}
    if tertiary_path is not None:
        tds = nc.Dataset(tertiary_path)
        tertiary_base_vals = {v: np.asarray(tds.variables[v][:]).ravel() for v in tds.variables}
        tds.close()

    try:
        routing = route_surfaces(names, nc_varnames(args.base_param),
                                  nc_varnames(tertiary_path) if tertiary_path else set(),
                                  tertiary_path is not None,
                                  secondary_names=backend.secondary_param_names(),
                                  secondary_given=secondary_path is not None)
    except ValueError as e:
        print(f"FATAL: {e}", file=sys.stderr)
        return 2

    # a sample of NON-calibrated vars to confirm nothing else changed, per surface
    calibrated_primary_bare = {decomp[i][0] for i, v in enumerate(names) if routing[v] == "primary"}
    calibrated_tertiary_bare = {decomp[i][0] for i, v in enumerate(names) if routing[v] == "tertiary"}
    noncalib_sample = [v for v in base if v not in calibrated_primary_bare][:10]
    noncalib_tertiary_sample = [v for v in tertiary_base_vals if v not in calibrated_tertiary_bare][:10]

    errors, checked = [], 0

    def err(case, msg):
        if len(errors) < args.max_report:
            errors.append(f"{case}: {msg}")

    if n_cols != len(names):
        print(f"FATAL: matrix has {n_cols} cols but param list has {len(names)} names", file=sys.stderr)
        return 2

    cases = ([(_case_name(args.case_pattern, args.baseline_index), None)]
             if (args.expect_baseline or (run_root / _case_name(args.case_pattern, args.baseline_index)).is_dir())
             else [])
    cases += [(_case_name(args.case_pattern, i), i) for i in range(1, n_rows + 1)]

    # (surface, var) -> {slot indices this parameter list calibrates}. Built once, because the
    # "untouched slots" check below must know about EVERY calibrated slot of a variable, not just
    # the one it happens to be looking at.
    calibrated_slots = {}
    for j, (var, idx0) in enumerate(decomp):
        if idx0 is not None:
            calibrated_slots.setdefault((routing[names[j]], var), set()).add(idx0)

    for case, row_i in cases:
        cdir = run_root / case
        pf = cdir / base_name
        tf = (cdir / tertiary_name) if tertiary_name else None
        qf = (cdir / quaternary_name) if quaternary_name else None
        nml = cdir / "runfile.nml"
        sub = cdir / "submit.sh"
        # 1. structure
        for f in ([pf, nml, sub] + ([tf] if tf is not None else [])
                  + ([qf] if qf is not None else [])):
            if not f.exists():
                err(case, f"missing {f.name}")
        if not pf.exists() or (tf is not None and not tf.exists()):
            continue
        checked += 1

        # 2/3/4. parameter file(s) — routed to whichever surface each name belongs to
        ds = nc.Dataset(pf)
        tds = nc.Dataset(tf) if tf is not None else None
        try:
            for j, (var, idx0) in enumerate(decomp):
                surface = routing[names[j]]
                if surface == "secondary":
                    # Verified through the BACKEND, not as a NetCDF variable. A multiplier is not
                    # supported here: the secondary writer stores one token, so there is no base
                    # array to scale, and route_surfaces would have to be taught otherwise first.
                    if modes.get(names[j]) == "multiplier":
                        err(case, f"{names[j]}: mode=multiplier is not supported on the secondary "
                                  f"surface (a single token has no base array to scale)")
                        continue
                    sfile = (cdir / secondary_path.name) if secondary_path else None
                    if sfile is None or not sfile.exists():
                        err(case, f"{names[j]} (secondary): no staged secondary file in this case dir")
                        continue
                    try:
                        got = backend.read_secondary_param(sfile, names[j])
                    except Exception as e:
                        err(case, f"{names[j]} (secondary): unreadable — {e}"); continue
                    if row_i is None:
                        want = backend.read_secondary_param(secondary_path, names[j])
                    else:
                        # The writer stores an INTEGER token, so compare the ROUNDED value or every
                        # case fails for a reason that is not an error.
                        want = round(float(X[row_i - 1][j]))
                    if not np.isclose(got, want, rtol=0, atol=0.5):
                        err(case, f"{names[j]} (secondary) got {got:g} expected {want:g}")
                    checked += 1
                    continue
                cur_ds = ds if surface == "primary" else tds
                cur_base = base if surface == "primary" else tertiary_base_vals
                if var not in cur_ds.variables:
                    err(case, f"var {var} absent ({surface} surface)"); continue
                arr = np.asarray(cur_ds.variables[var][:]).ravel()
                if row_i is None:
                    # V0 baseline: the expected value is the BASE's own, which for a SCALAR
                    # parameter (idx0 is None) must be read as element 0 of the raveled array.
                    # `cur_base[var][None]` makes numpy read None as np.newaxis and hand back a
                    # 1-element array, which float() rejects -- the validator crashed outright on
                    # R3's first --expect-baseline run (2026-08-18). It survived until now because
                    # every earlier ensemble carried its V0 as a MATRIX ROW rather than a separate
                    # baseline case, so this branch was never taken with a scalar parameter, and
                    # R3 is the first round whose tertiary surface has scalars at all
                    # (RCCZ/VMXO/RMOM/GO2X/DCKML are all dims=()).
                    base_arr = np.asarray(cur_base[var]).ravel()
                    if idx0 is None:
                        # The whole variable must equal the BASE, elementwise. Taking element 0 as
                        # a scalar expectation (the previous form) is right only for a UNIFORM
                        # array and silently wrong for a varied one: SPOSC's twenty entries span
                        # 0 to 7.5, so V0 was reported as "broadcast != 7.5" while being exactly
                        # correct. A scalar parameter ravels to one element, so this covers it too.
                        if not np.allclose(arr, base_arr, rtol=args.rtol, atol=1e-12):
                            err(case, f"{names[j]} ({surface}) V0 != base elementwise")
                        checked += 1
                        continue
                    expect = float(base_arr[idx0])
                elif modes.get(names[j]) == "multiplier":
                    # The matrix column is a FACTOR, not a value: the expected content is the
                    # BASE array scaled elementwise. Comparing the factor itself would fail every
                    # case, and comparing a broadcast scalar would PASS the very defect the mode
                    # exists to fix.
                    factor = float(X[row_i - 1][j])
                    want_arr = np.asarray(cur_base[var]).ravel() * factor
                    if not np.allclose(arr, want_arr, rtol=args.rtol, atol=1e-12):
                        err(case, f"{names[j]} ({surface}) != base x {factor:g} elementwise")
                    if not (lower[j] - 1e-9 <= factor <= upper[j] + 1e-9):
                        err(case, f"{names[j]} factor {factor:g} out of "
                                  f"[{lower[j]:g},{upper[j]:g}]")
                    checked += 1
                    continue
                else:
                    expect = float(X[row_i - 1][j])
                if idx0 is None:  # broadcast / scalar
                    if not np.allclose(arr, expect, rtol=args.rtol, atol=1e-12):
                        err(case, f"{names[j]} ({surface}) broadcast != {expect:g}")
                else:
                    got = float(arr[idx0])
                    if not np.isclose(got, expect, rtol=args.rtol, atol=1e-12):
                        err(case, f"{names[j]} ({surface}) slot{idx0+1} got {got:g} expected {expect:g}")
                    # Slots of this var that NO parameter row calibrates must equal the base.
                    # `calibrated_slots` (not `!= idx0`) because a variable may have MORE THAN ONE
                    # slot calibrated -- R3's probe calibrates BOTH nactbioms slots of SPORC and of
                    # SPOMC as separate rows, so from row SPORC_1's perspective slot 2 legitimately
                    # differs from the base. The old `k != idx0` test hardcoded "at most one slot
                    # per variable is ever calibrated" and reported 4 false errors per case across
                    # all 258 (found 2026-08-14 by running the validator on the first ensemble that
                    # violated that assumption; the multi-surface tests written the same morning all
                    # used a single slot, so it survived them).
                    for k in range(len(arr)):
                        if k in calibrated_slots.get((surface, var), ()):
                            continue
                        if not np.isclose(float(arr[k]), float(cur_base[var][k]), rtol=1e-6, atol=1e-30):
                            err(case, f"{var} ({surface}) slot{k+1} changed (should be untouched)")
                    # bounds (skip the baseline, which sits AT the default)
                    if row_i is not None and not (lower[j] - 1e-9 <= expect <= upper[j] + 1e-9):
                        err(case, f"{names[j]} value {expect:g} out of [{lower[j]:g},{upper[j]:g}]")
            for v in noncalib_sample:
                if not np.allclose(np.asarray(ds.variables[v][:]).ravel(), base[v], rtol=1e-6, atol=1e-30, equal_nan=True):
                    err(case, f"non-calibrated var {v} changed (primary)")
            if tds is not None:
                for v in noncalib_tertiary_sample:
                    if not np.allclose(np.asarray(tds.variables[v][:]).ravel(), tertiary_base_vals[v],
                                       rtol=1e-6, atol=1e-30, equal_nan=True):
                        err(case, f"non-calibrated var {v} changed (tertiary)")
        finally:
            ds.close()
            if tds is not None:
                tds.close()

        # 5. namelist
        if nml.exists():
            t = nml.read_text()
            m = re.search(r"pft_file_in\s*=\s*['\"]([^'\"]+)['\"]", t)
            if not m or Path(m.group(1)).name != base_name or str(cdir) not in m.group(1):
                err(case, "pft_file_in does not point at this case's staged param file")
            if tertiary_name is not None:
                m3 = re.search(r"micpar_file_in\s*=\s*['\"]([^'\"]+)['\"]", t)
                if not m3 or Path(m3.group(1)).name != tertiary_name or str(cdir) not in m3.group(1):
                    err(case, "micpar_file_in does not point at this case's staged tertiary file")
            # The grid input is a PASSIVE shared input until the quaternary surface is in use,
            # at which point it becomes per-case and must point INTO the case like the others.
            # Checking it only in the passive branch below would pass a case whose grid file was
            # perturbed and then left pointing at the shared base -- the sampled soil values
            # written and never read.
            if quaternary_name is not None:
                m4 = re.search(r"grid_file_in\s*=\s*['\"]([^'\"]+)['\"]", t)
                if not m4 or Path(m4.group(1)).name != quaternary_name or str(cdir) not in m4.group(1):
                    err(case, "grid_file_in does not point at this case's staged quaternary file")
            _passive = (r"(?:clm_hour_file_in|soil_mgmt_in|atm_ghg_in|pft_mgmt_in)"
                        if quaternary_name is not None
                        else r"(?:grid_file_in|clm_hour_file_in|soil_mgmt_in|atm_ghg_in|pft_mgmt_in)")
            for other in re.findall(_passive + r"\s*=\s*['\"]([^'\"]+)['\"]", t):
                if not other.startswith("/"):
                    err(case, f"non-absolute input path: {other}")
                elif not Path(other).exists():
                    err(case, f"input path missing: {other}")

        # 6. submit
        if sub.exists():
            s = sub.read_text()
            mb = re.search(r"(\S*ecosim\.f90\.x|\$\{?MODEL_BINARY\}?|\S+/bin/\S+)", s)
            # accept a rendered absolute binary path; verify if it looks like one
            bpath = os.environ.get("A2MC_ECOSIM_BINARY", "")
            if bpath and bpath not in s:
                err(case, "submit.sh does not reference the configured model binary")
            if "runfile.nml" not in s and str(nml) not in s:
                err(case, "submit.sh does not reference the case runfile")

    # submit-script dry-check — the ENSEMBLE array dispatcher, which per-case validation can't see.
    # Catches the case-dir/binary bugs that fail every task after the case files pass (e.g. the bash
    # brace-substitution that resolved to a stray `BioCON_case4}`, 20260716a).
    submit_msg = "submit-script check: skipped"
    if not args.no_submit_check:
        ss = args.submit_script
        if not ss:
            ucd = os.environ.get("A2MC_USE_CASE_DIR")
            if ucd:
                for c in (Path(ucd) / "case_template" / "submit_ensemble_array.sh",
                          Path(ucd) / "submit_ensemble_array.sh"):
                    if c.exists():
                        ss = str(c); break
        if ss and Path(ss).exists():
            # Sample the BASELINE index only when a baseline case actually exists. An experiment
            # is materialized as rows 1..N with no unperturbed case 0, so including index 0
            # unconditionally reported `no case dir ...0` on every correct experiment ensemble.
            has_baseline = bool(cases) and cases[0][1] is None
            sample = sorted({1, max(1, n_rows // 2), n_rows}
                            | ({int(args.baseline_index)} if has_baseline else set()))
            for p in _check_submit_script(Path(ss), run_root, sample,
                                          case_pattern=args.case_pattern):
                err("submit-script", p)
            submit_msg = f"submit-script dry-check ({Path(ss).name}): tasks {sample}"
        else:
            submit_msg = "submit-script check: no submit_ensemble_array.sh found (skipped)"

    ok = not errors
    print(f"Validated {len(cases)} case dir(s), {checked} check(s) "
          f"(structure, param file, namelist, submit) under {run_root}")
    print(f"  params/case: {len(names)}  |  matrix: {n_rows}x{n_cols}  |  baseline: "
          f"{'yes' if cases and cases[0][1] is None else 'no'}")
    print(f"  {submit_msg}")
    if ok:
        print("✅ ALL CHECKS PASS — ensemble is consistent with the matrix and safe to submit.")
        return 0
    print(f"❌ {len(errors)}+ problem(s) (first {args.max_report}):")
    for e in errors:
        print("   -", e)
    return 1


if __name__ == "__main__":
    sys.exit(main())
