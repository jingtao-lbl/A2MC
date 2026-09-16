#!/usr/bin/env python3
"""Materialize an ADAPTER (non-FATES) model's Phase-0 ensemble from a sampled matrix.

The missing "create parameter files from the sampled txt file" step for adapter models — the
analog of FATES's phases/phase0_design/generate_parameter_files.py, done through the model's
ModelBackend (docs/38 additive; no CIME, no shared-file edit).

For each row of the Morris/Sobol/LHS matrix it:
  1. maps the row -> {canonical_id: value} using the SAME parser that generated the matrix
     (scripts/create_adapter_parameter_sample.py::parse_pft_param_list — column j <-> names[j],
     so no reordering is possible), then
  2. SPLITS the row's edits by which base file's variable set actually contains each canonical
     id's bare name (see "Multi-surface rows" below) — one param list can now span more than one
     physical parameter file, not just PFT slots within one file, then
  3. backend.write_parameter_file(base, edits, per_case_param_file, surface=...) per surface that
     has edits this row, then
  4. backend.create_case(case_name, primary_file, cfg, secondary_param_file=..., tertiary_param_file=...)
     (stage namelist + submit.sh; secondary/tertiary omitted for a single-surface model).

It writes files ONLY — it does NOT sbatch (submission is a separate, deliberate step:
backend.submit_ensemble, or the phase0 submit path). Optionally also materializes a V0 BASELINE
case (row-free, the unperturbed base = the documented defaults) as the ensemble's reference point.

Multi-surface rows (added for EcoSIM_BioCON R3, generic to any model with >1 parameter surface):
one param list can mix names from more than one physical base file (e.g. R3's 48 rows: 40 plant
traits in the primary PFT NetCDF, 8 soil-BGC rates in the tertiary MicrobePars NetCDF). Surface
membership is determined by PROBING each base file's own variable names (never assumed or hand-
listed) — a canonical id's bare name (the part before a trailing `_<int>` PFT/slot suffix, the
same convention every backend already uses) must exist in exactly one supplied base file's variable
set, or the run refuses loudly rather than silently mis-routing an edit. A surface with NO base
file given (e.g. `--tertiary-base` omitted) is simply not available for routing — exactly today's
single-surface behavior when only `--base-param` is given.

The SECONDARY surface (e.g. EcoSIM's stand-management file) is a separate, simpler case: this
script does not sweep or perturb it (that crossed-design use case is `materialize_adapter_crossed.py`).
`--secondary-param` stages one FIXED file, unchanged, into every case (e.g. R3 holding planting
density at R2's best value while the primary/tertiary surfaces are Sobol-sampled).

Env (source a2mc_noncime_config.sh + the site config first):
    A2MC_MODEL                onboarded model name (registry dispatch)          (required)
    A2MC_BASE_PARAM_FILE      primary base file to perturb + stage per row      (required)
    A2MC_SECONDARY_PARAM_FILE secondary base file; PER-CASE if the param list samples
                              a name on it, else staged fixed                     (optional)
    A2MC_BASE_PARAM_FILE_3    tertiary base file to perturb + stage per row     (optional)
    A2MC_BASE_PARAM_FILE_4    quaternary base file to perturb + stage per row   (optional)
    A2MC_PARAM_LIST_FILE      the explicit-column param list (name + pft)        (required)
    A2MC_OUTPUT_DIR           ensemble run root (per-case subdirs land here)     (required)
    A2MC_CASE_NAME_PATTERN    case-dir name; `{N}` = 1-based case index          (required)
    <all other A2MC_* keys> passed through to backend.create_case untouched
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

import numpy as np

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from scripts.create_adapter_parameter_sample import (  # noqa: E402
    secondary_base_default, warn_if_legacy_secondary,
    parse_pft_param_list, nc_varnames, route_surfaces, is_netcdf, parse_param_modes,
    bare_name,
)





def _case_name(pattern: str, n) -> str:
    return pattern.replace("{N}", str(n))


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--model", default=os.environ.get("A2MC_MODEL"))
    ap.add_argument("--param-list", default=os.environ.get("A2MC_PARAM_LIST_FILE"))
    ap.add_argument("--matrix", default=os.environ.get("A2MC_ENSEMBLE_MATRIX_FILE"),
                    help="sampled matrix (default $A2MC_ENSEMBLE_MATRIX_FILE)")
    ap.add_argument("--run-root", default=os.environ.get("A2MC_OUTPUT_DIR"))
    ap.add_argument("--base-param", default=os.environ.get("A2MC_BASE_PARAM_FILE"),
                    help="PRIMARY base file, perturbed per row (default $A2MC_BASE_PARAM_FILE)")
    _sec_default, _sec_env = secondary_base_default()
    warn_if_legacy_secondary(_sec_env)
    ap.add_argument("--secondary-param", default=_sec_default,
                    help="SECONDARY base file. Written PER CASE when the param list samples a name on this surface (e.g. EcoSIM PPI); staged unperturbed into every case when it does not. "
                         "(default $A2MC_SECONDARY_PARAM_FILE; omit for a single/dual-surface model)")
    ap.add_argument("--quaternary-base", default=os.environ.get("A2MC_BASE_PARAM_FILE_4"),
                    help="quaternary base file to perturb + stage per row "
                         "(default $A2MC_BASE_PARAM_FILE_4; EcoSIM = the grid/soil NetCDF)")
    ap.add_argument("--tertiary-base", default=os.environ.get("A2MC_BASE_PARAM_FILE_3"),
                    help="TERTIARY base file, perturbed per row like --base-param "
                         "(default $A2MC_BASE_PARAM_FILE_3; omit for a single-surface model)")
    ap.add_argument("--case-pattern", default=os.environ.get("A2MC_CASE_NAME_PATTERN"))
    ap.add_argument("--start", type=int, default=1, help="1-based first matrix row to materialize")
    ap.add_argument("--end", type=int, default=0, help="1-based last row (0 = all)")
    ap.add_argument("--baseline", action="store_true", help="also materialize a V0 baseline case (unperturbed base)")
    ap.add_argument("--baseline-index", default="0", help="the {N} for the V0 baseline case (default 0)")
    ap.add_argument("--dry-run", action="store_true", help="report what WOULD be written; write nothing")
    args = ap.parse_args()

    miss = [k for k, v in [("--model", args.model), ("--param-list", args.param_list),
                           ("--matrix", args.matrix), ("--run-root", args.run_root),
                           ("--base-param", args.base_param), ("--case-pattern", args.case_pattern)] if not v]
    if miss:
        print(f"ERROR: missing required inputs {miss} — source a2mc_noncime_config.sh + the site config, "
              f"or pass them explicitly.", file=sys.stderr)
        return 1

    import importlib
    from models import registry
    try:
        importlib.import_module(f"models.{args.model}")
        backend = registry.get_model(args.model)
    except Exception as e:
        print(f"ERROR: model '{args.model}' not onboarded: {e}", file=sys.stderr)
        return 2

    base = Path(args.base_param)
    if not base.exists():
        print(f"ERROR: primary base parameter file not found: {base}", file=sys.stderr)
        return 1
    secondary = Path(args.secondary_param) if args.secondary_param else None
    if secondary is not None and not secondary.exists():
        print(f"ERROR: secondary parameter file not found: {secondary}", file=sys.stderr)
        return 1
    quaternary_base = Path(args.quaternary_base) if args.quaternary_base else None
    if quaternary_base is not None and not quaternary_base.exists():
        print(f"ERROR: quaternary base parameter file not found: {quaternary_base}", file=sys.stderr)
        return 1
    tertiary_base = Path(args.tertiary_base) if args.tertiary_base else None
    if tertiary_base is not None and not tertiary_base.exists():
        print(f"ERROR: tertiary base parameter file not found: {tertiary_base}", file=sys.stderr)
        return 1

    names, _, _ = parse_pft_param_list(args.param_list)
    modes = parse_param_modes(args.param_list)          # {} when the list has no `mode` column
    multiplier_ids = {cid for cid, m in modes.items() if m == "multiplier"}
    X = np.loadtxt(args.matrix)
    if X.ndim == 0:      # a matrix file with exactly one value loads as a bare scalar
        X = X.reshape(1, 1)
    elif X.ndim == 1:
        X = X.reshape(1, -1)
    if X.shape[1] != len(names):
        print(f"ERROR: matrix has {X.shape[1]} columns but the param list has {len(names)} names — "
              f"they must match (column j <-> names[j]).", file=sys.stderr)
        return 1

    try:
        if is_netcdf(base):
            primary_vars = nc_varnames(base)
            tertiary_vars = nc_varnames(tertiary_base) if tertiary_base is not None else set()
            quaternary_vars = nc_varnames(quaternary_base) if quaternary_base is not None else set()
            routing = route_surfaces(
                names, primary_vars, tertiary_vars, tertiary_base is not None,
                quaternary_vars=quaternary_vars,
                quaternary_given=quaternary_base is not None,
                secondary_names=backend.secondary_param_names(),
                secondary_given=secondary is not None)
        else:
            # A NON-NETCDF primary surface (PFLOTRAN's text input deck). `route_surfaces`
            # probes NetCDF variable names, so it cannot describe this file at all -- see
            # `is_netcdf`'s docstring for why that assumption was invisible until the first
            # real PFLOTRAN materialization. Route everything to the single surface and let
            # the model's own writer validate each address against the deck's grammar, which
            # is a stricter check than a flat name-set membership test.
            if tertiary_base is not None:
                raise ValueError(
                    f"a tertiary base was supplied but the primary base {base.name} is not a "
                    "NetCDF, so surfaces cannot be routed by probing. Multi-surface routing "
                    "is only implemented for NetCDF parameter files.")
            routing = {cid: "primary" for cid in names}
    except ValueError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 1
    n_tertiary = sum(1 for s in routing.values() if s == "tertiary")
    n_quaternary = sum(1 for s in routing.values() if s == "quaternary")
    n_secondary = sum(1 for s in routing.values() if s == "secondary")

    n_rows = X.shape[0]
    end = args.end if args.end > 0 else n_rows
    start = max(1, args.start)
    end = min(end, n_rows)
    run_root = Path(args.run_root)

    cfg = dict(os.environ)
    cfg["A2MC_OUTPUT_DIR"] = str(run_root)

    print(f"Model:        {args.model}")
    print(f"Run root:     {run_root}")
    print(f"Base params:  primary={base.name}"
          + (f"  secondary({'PER-CASE' if n_secondary else 'fixed'})={secondary.name}" if secondary else "")
          + (f"  tertiary={tertiary_base.name}" if tertiary_base else "")
          + (f"  quaternary={quaternary_base.name}" if quaternary_base else ""))
    print(f"Param list:   {len(names)} params "
          f"({len(names) - n_tertiary - n_secondary - n_quaternary} primary, "
          f"{n_secondary} secondary, {n_tertiary} tertiary, {n_quaternary} quaternary)"
          f"  |  matrix: {n_rows} rows x {X.shape[1]} cols")
    print(f"Materialize:  rows {start}..{end}  ({end - start + 1} cases)"
          + (f" + V0 baseline (case {args.baseline_index})" if args.baseline else ""))
    print(f"Case dirs:    {run_root}/{_case_name(args.case_pattern, '{N}')}/  (param file(s) + runfile.nml + submit.sh)")
    if args.dry_run:
        print("\n[DRY-RUN] nothing written. Example case dirs:")
        for i in ([args.baseline_index] if args.baseline else []) + [start, start + 1, "...", end]:
            print(f"    {run_root}/{_case_name(args.case_pattern, i)}/")
        return 0

    # Base values for every MULTIPLIER row, read ONCE from the surface each is routed to. Resolving
    # the factor here rather than in a backend keeps `write_parameter_file` unchanged across every
    # adapter: it already accepts a list, so an array parameter is handed the scaled ARRAY and a
    # scalar the scaled scalar. Broadcasting a bare factor would set every element to the factor,
    # which is the defect this exists to fix.
    base_vals = {}
    if multiplier_ids:
        import netCDF4 as _nc
        _srcs = {"primary": base, "secondary": secondary, "tertiary": tertiary_base,
                 "quaternary": quaternary_base}
        for cid in sorted(multiplier_ids):
            if cid not in routing:
                continue
            src = _srcs.get(routing[cid])
            if src is None or not is_netcdf(src):
                raise SystemExit(
                    f"ERROR: {cid} is mode=multiplier but its {routing[cid]} surface is not a "
                    f"NetCDF base whose current value can be read. A multiplier needs a base to "
                    f"multiply.")
            bare = bare_name(cid)
            with _nc.Dataset(src) as _d:
                if bare not in _d.variables:
                    raise SystemExit(f"ERROR: {cid} is mode=multiplier but '{bare}' is not a "
                                     f"variable in {Path(src).name}")
                base_vals[cid] = np.array(_d.variables[bare][:], dtype=float)
        print("Multiplier rows: " + ", ".join(
            f"{c} (base shape {base_vals[c].shape}, {base_vals[c].min():g}..{base_vals[c].max():g})"
            for c in sorted(base_vals)))

    def _resolve(edits: dict) -> dict:
        """Turn a mode=multiplier FACTOR into the concrete value the writer should store."""
        out = {}
        for k, v in edits.items():
            if k in base_vals:
                scaled = base_vals[k] * float(v)
                out[k] = scaled.tolist() if scaled.ndim else float(scaled)
            else:
                out[k] = v
        return out

    def _materialize(name: str, edits: dict) -> Path:
        edits = _resolve(edits)
        primary_edits = {k: v for k, v in edits.items() if routing[k] == "primary"}
        tertiary_edits = {k: v for k, v in edits.items() if routing[k] == "tertiary"}
        quaternary_edits = {k: v for k, v in edits.items() if routing[k] == "quaternary"}
        secondary_edits = {k: v for k, v in edits.items() if routing[k] == "secondary"}
        case_dir = run_root / name
        case_dir.mkdir(parents=True, exist_ok=True)

        pfile = case_dir / base.name
        backend.write_parameter_file(base, primary_edits, pfile)

        tfile = None
        if quaternary_base is not None:
            qfile = case_dir / quaternary_base.name
            backend.write_parameter_file(quaternary_base, quaternary_edits, qfile,
                                         surface="quaternary")
        if tertiary_base is not None:
            tfile = case_dir / tertiary_base.name
            backend.write_parameter_file(tertiary_base, tertiary_edits, tfile, surface="tertiary")

        # Pass secondary/tertiary ONLY when actually used: not every backend's create_case()
        # declares these kwargs (e.g. the template backend declares neither), so passing them
        # as an explicit None would raise TypeError on a model that never asked for them —
        # this keeps single-surface models (R1's case, and every other adapter today) calling
        # create_case() with the exact same signature as before this script gained surfaces.
        extra = {}
        if secondary_edits:
            # SAMPLED secondary surface: write a PER-CASE file, exactly as primary/tertiary do.
            sfile = case_dir / secondary.name
            backend.write_parameter_file(secondary, secondary_edits, sfile, surface="secondary")
            extra["secondary_param_file"] = sfile
        elif secondary is not None:
            # FIXED-STAGE path, unchanged: no secondary parameter is being sampled, so every case
            # points at the one shared base. This is what every ensemble before 2026-09-01 did and
            # it must stay byte-identical (SCOPE_secondary_surface_routing.md, F5).
            extra["secondary_param_file"] = secondary
        if tfile is not None:
            extra["tertiary_param_file"] = tfile
        if quaternary_base is not None:
            extra["quaternary_param_file"] = qfile
        return backend.create_case(name, pfile, cfg, **extra)

    made = []
    # V0 baseline: the unperturbed base = the documented defaults (no edits, either surface)
    if args.baseline:
        name = _case_name(args.case_pattern, args.baseline_index)
        made.append(_materialize(name, {}))

    for i in range(start, end + 1):
        edits = dict(zip(names, X[i - 1]))            # column j <-> names[j]
        name = _case_name(args.case_pattern, i)
        made.append(_materialize(name, edits))
        if i % 100 == 0 or i == end:
            print(f"  materialized {i - start + 1}/{end - start + 1}")

    print(f"\nDone: {len(made)} case dirs under {run_root} (NOT submitted). "
          f"Submit separately (backend.submit_ensemble / the phase0 submit path).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
