#!/usr/bin/env python
"""Generic model-dispatched smoke-ensemble runner.

The model-agnostic distillation of `scripts/run_ecosim_smoke_ensemble.py` (the
EcoSIM exemplar, left UNTOUCHED). Stages + submits a tiny 2-case ensemble at the
provisional-bounds corners (lo / hi) for ANY onboarded model, dispatching every
model-specific action through the active `ModelBackend`/`ModelSpec` — never
through hardcoded EcoSIM paths or the EcoSIM namelist edit. Additive per
docs/38 §3 (roadmap L3): a NEW file beside the FATES-shaped originals; nothing
FATES-shaped is rewritten.

Per corner (lo, hi) drawn from the param-list / bounds CSV:
    backend.write_parameter_file  ->  backend.create_case  ->
    (pre-submit) the generic input↔binary compat gate  ->  backend.submit_ensemble

What is NOT hardcoded here (read from config/env — the merged sourced environment
dict — or dispatched through the spec):
  * the model binary + base namelist absolute paths      -> the backend reads its
    own model-specific `config` keys (A2MC_<MODEL>_BINARY, …) out of the env dict.
  * the base parameter file                              -> `A2MC_BASE_PARAM_FILE`.
  * the model source checkout (for the compat scan)      -> `A2MC_MODEL_PATH`.
  * the input↔binary compat contract                     -> `spec.input_reader_sources`
    + `spec.input_read_pattern` (empty => the gate is a graceful no-op).
  * the run-length control                               -> MODEL-SPECIFIC. `spec.
    run_length_control_label` only NAMES it (e.g. EcoSIM "forc_periods"); the actual
    edit belongs in the backend/config, NOT in this generic runner, so this runner
    performs no run-length surgery.

Config contract (the merged machine+site sourced environment, plus CLI overrides):
    A2MC_BASE_PARAM_FILE   base parameter file to perturb + stage        (required)
    A2MC_MODEL_PATH        model source-tree root, for the compat scan   (optional)
    A2MC_OUTPUT_DIR        ensemble run root                             (set from --run-root)
    A2MC_DRY_RUN           truthy => stage but do not sbatch             (set from --dry-run)
    <all other A2MC_* keys> passed through to the backend untouched

Usage (from repo root, a2mc_env python):
    python scripts/run_smoke_ensemble.py --model ecosim \
        --run-root /path/to/smoke_runs \
        --param-list models/ecosim/reference_bounds/ecosim_biocon_param_list.csv \
        [--dry-run] [--force]

Exit 0 on success (submitted, or dry-run staged + compat OK); 2 if the pre-submit
compat gate fires without --force (cases staged, nothing submitted); 1 on usage/IO.

Author: Jing Tao with Claude
"""
from __future__ import annotations

import argparse
import os
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent


def _truthy(v) -> bool:
    return str(v).strip().lower() in ("1", "true", "yes", "on")


def _is_netcdf(path: Path) -> bool:
    """Sniff the CONTENT, not the suffix.

    Same check as `scripts/materialize_adapter_ensemble.py`. Suffix dispatch is the recurring
    first-model assumption in this kit: it was written when every model's input was NetCDF or
    JSON, and it treats the file NAME as the format. NetCDF classic and 64-bit start `CDF`,
    HDF5-backed NetCDF-4 starts with the HDF5 signature.
    """
    try:
        with Path(path).open("rb") as fh:
            head = fh.read(8)
    except OSError:
        return False
    return head[:3] == b"CDF" or head[:8] == b"\x89HDF\r\n\x1a\n"


def _input_file_vars(param_file: Path):
    """Variables PRESENT in the input parameter file, or None if the format has no flat var set.

    RETURNS None RATHER THAN RAISING for a format this cannot enumerate. A text input deck
    (PFLOTRAN's `pflotran.in`) has no flat variable namespace at all -- its parameters are cards
    addressed by block path -- so "which variables does this file provide" is not a question with
    an answer, and the honest result is "the gate does not apply here", not a crash.

    This was the 4th instance of the same first-model assumption already fixed in the materializer
    (NetCDF-only surface routing), the pre-submit validator (integer-PFT canonical-id regex), the
    Phase-2 CLI (Kougarok targets default) and the Y-matrix writer (`%.2f`). It had not bitten only
    because nothing had yet run this script for a text-deck model.
    """
    pf = Path(param_file)
    if _is_netcdf(pf):
        import netCDF4 as nc
        ds = nc.Dataset(pf)
        try:
            return set(ds.variables)
        finally:
            ds.close()
    try:
        import json
        obj = json.loads(pf.read_text())
    except (ValueError, OSError, UnicodeDecodeError):
        return None                     # not NetCDF, not JSON -> no flat variable set
    return set(obj) if isinstance(obj, dict) else set()


def _compat_missing(spec, checkout: Path | None, param_file: Path):
    """Generic pre-submit input↔binary compat gate, dispatched through the spec.

    Returns a sorted list of variables the built binary reads but the input file
    lacks, or None if the model declares no compat contract / no checkout given.
    """
    readers = getattr(spec, "input_reader_sources", ()) or ()
    pattern = getattr(spec, "input_read_pattern", "") or ""
    if not readers or not pattern:
        return None  # no source-read contract -> graceful no-op
    if checkout is None or not Path(checkout).is_dir():
        return None  # no checkout to scan; caller warns
    pat = re.compile(pattern)
    required: set[str] = set()
    for rel in readers:
        src = Path(checkout) / rel
        if src.exists():
            required |= set(pat.findall(src.read_text()))
    provided = _input_file_vars(param_file)
    if provided is None:
        return None                     # unenumerable format -> gate not applicable, see below
    return sorted(required - provided)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--model", required=True, help="onboarded model name (e.g. ecosim)")
    ap.add_argument("--run-root", required=True, help="ensemble run root (per-case subdirs land here)")
    ap.add_argument("--param-list", required=True, help="param-list / bounds CSV (names + lo/hi columns)")
    ap.add_argument("--dry-run", action="store_true", help="stage cases but do not sbatch")
    ap.add_argument("--force", action="store_true", help="submit even if the input↔binary compat gate fires")
    args = ap.parse_args()

    sys.path.insert(0, str(REPO))
    import importlib
    from models import registry

    # --- Dispatch: resolve the backend + spec for --model (mirror model_preflight/model_ensemble_status)
    try:
        importlib.import_module(f"models.{args.model}")
    except ModuleNotFoundError:
        print(f"ERROR: model '{args.model}' is not onboarded (no models/{args.model}/ package).", file=sys.stderr)
        print("       A brand-new model needs the `onboard-model` skill first.", file=sys.stderr)
        return 2
    try:
        backend = registry.get_model(args.model)
    except Exception as e:
        print(f"ERROR: model '{args.model}' not onboarded: {e}", file=sys.stderr)
        return 2
    spec = backend.spec

    from phases.phase0_design.create_parameter_sample import parse_param_list

    # --- Config: the merged sourced environment dict + CLI overrides (nothing hardcoded)
    cfg = dict(os.environ)
    run_root = Path(args.run_root)
    cfg["A2MC_OUTPUT_DIR"] = str(run_root)
    cfg["A2MC_DRY_RUN"] = "1" if args.dry_run else cfg.get("A2MC_DRY_RUN", "")

    base_param_file = cfg.get("A2MC_BASE_PARAM_FILE", "")
    if not base_param_file:
        print("ERROR: A2MC_BASE_PARAM_FILE is unset — source the machine+site config first "
              "(the base parameter file this runner perturbs).", file=sys.stderr)
        return 1
    base_param_file = Path(base_param_file)
    if not base_param_file.exists():
        print(f"ERROR: base parameter file not found: {base_param_file}", file=sys.stderr)
        return 1

    param_list = Path(args.param_list)
    if not param_list.exists():
        print(f"ERROR: param list not found: {param_list}", file=sys.stderr)
        return 1

    print(f"Model:        {spec.name} ({spec.display_name})")
    print(f"Run root:     {run_root}")
    print(f"Base params:  {base_param_file}")
    print(f"Param list:   {param_list}")
    if spec.run_length_control_label:
        print(f"Run length:   controlled by '{spec.run_length_control_label}' — MODEL-SPECIFIC; "
              f"applied by the backend/config, NOT by this generic runner.")

    # --- Two corner param sets (lo / hi) from the bounds CSV
    names, lower, upper = parse_param_list(param_list)
    corners = {"smoke_lo": dict(zip(names, lower)), "smoke_hi": dict(zip(names, upper))}

    # --- Stage each corner: write_parameter_file -> create_case (no submit yet)
    case_dirs = []
    for name, mods in corners.items():
        pmods = {f"{n}_1": v for n, v in mods.items()}  # corner values on grouping-axis slot 1
        pfile = run_root / name / base_param_file.name    # keep basename so the namelist repoint matches
        pfile.parent.mkdir(parents=True, exist_ok=True)
        backend.write_parameter_file(base_param_file, pmods, pfile)
        cd = backend.create_case(name, pfile, cfg)
        case_dirs.append(cd)
        print(f"  staged {name}: {cd}")

    # --- Pre-submit input↔binary compat gate (generic, spec-dispatched)
    checkout = cfg.get("A2MC_MODEL_PATH") or None
    missing = _compat_missing(spec, Path(checkout) if checkout else None, base_param_file)
    if missing is None:
        # Three DIFFERENT reasons the gate can be inapplicable. Report the real one: until the
        # third branch existed, a text-deck model fell through to the checkout message and would
        # have been reported as "A2MC_MODEL_PATH not set" even with a perfectly good checkout.
        if not getattr(spec, "input_reader_sources", ()):
            print("  compat gate: n/a (model declares no input↔binary source-read contract)")
        elif checkout is None or not Path(checkout).is_dir():
            print("  compat gate: SKIPPED (A2MC_MODEL_PATH not set / not a directory — no checkout to scan)")
        else:
            print("  compat gate: n/a (the input file has no flat variable namespace — a text deck's "
                  "parameters are cards addressed by block path, so 'which variables does this file "
                  "provide' has no answer to compare against the binary's reads)")
    elif missing:
        print(f"  compat gate: FIRED — input file is missing {len(missing)} var(s) the binary reads "
              f"(older-input/newer-binary mismatch):")
        print(f"      {', '.join(missing)}")
        if not args.force:
            print("ABORT: not submitting. Rebuild the binary at the input's commit, regenerate the input "
                  "with these vars, or re-run with --force to submit anyway.")
            print(f"\nstaged {len(case_dirs)} cases (NOT submitted): {[str(c) for c in case_dirs]}")
            return 2
        print("  --force set: submitting despite the compat mismatch.")
    else:
        print("  compat gate: OK — input file has every variable the binary reads.")

    # --- Submit
    ids = backend.submit_ensemble(case_dirs, cfg)
    print(f"\nsubmitted {len(ids)} cases: {ids}")
    print(f"run root: {run_root}")
    print(f"monitor: python tools/model_ensemble_status.py --model {args.model} "
          f"--run-root {run_root} [--watch 60] [--failed]")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
