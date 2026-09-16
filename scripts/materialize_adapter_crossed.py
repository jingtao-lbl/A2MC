#!/usr/bin/env python3
"""Materialize a CROSSED adapter ensemble: a primary-surface Morris matrix (N trait rows)
crossed with a SECONDARY-surface sweep (M levels), as N×M cases named ``TR{N}MG{M}``.

For a model with two parameter surfaces (see ModelBackend.write_parameter_file surface=,
ModelSpec.secondary_namelist_var), this is the design where the trait sensitivities are
screened at each of a few secondary-surface levels (e.g. EcoSIM: 41 plant traits × a
planting-density sweep PPI ∈ {40,120,200,280}), so you get trait μ* per level PLUS the
secondary-factor response, and only M secondary files are written (shared across trait rows).

Per (trait row n, level m):
  1. primary  = backend.write_parameter_file(prim_base, trait_edits[n], out, surface="primary")
  2. secondary= backend.write_parameter_file(sec_base,  {param: level[m]}, out, surface="secondary")  (M shared)
  3. case TR{n}MG{m} = backend.create_case(name, primary[n], cfg); then the runfile's
     spec.secondary_namelist_var is repointed at the SHARED secondary[m] (no per-case copy).

Writes files ONLY (no sbatch). Optionally a V0 baseline (unperturbed primary × a chosen level).

Env (source a2mc_noncime_config.sh + the site config first):
    A2MC_MODEL, A2MC_BASE_PARAM_FILE (primary base), A2MC_PARAM_LIST_FILE (trait list),
    A2MC_ENSEMBLE_MATRIX_FILE (trait matrix), A2MC_OUTPUT_DIR, A2MC_CASE_NAME_PATTERN (uses {N} and {M}),
    A2MC_SECONDARY_PARAM_FILE (secondary base; the legacy name A2MC_BASE_PARAM_FILE_2 is
    still accepted and the current name wins if both are set),
    A2MC_SECONDARY_SWEEP ("PPI:40,120,200,280").
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
    parse_pft_param_list, secondary_base_default, warn_if_legacy_secondary,
)


def _case_name(pattern: str, n, m) -> str:
    return pattern.replace("{N}", str(n)).replace("{M}", str(m))


def _parse_sweep(spec: str):
    """'PPI:40,120,200,280' -> ('PPI', [40.0,120.0,200.0,280.0])."""
    name, _, vals = spec.partition(":")
    levels = [float(v) for v in vals.split(",") if v.strip()]
    if not name.strip() or not levels:
        raise ValueError(f"bad --secondary-sweep {spec!r}; expected 'PARAM:v1,v2,...'")
    return name.strip(), levels


def _repoint_secondary(runfile: Path, namelist_var: str, target: Path) -> None:
    """Repoint the (already-created) case runfile's secondary namelist var at `target`
    (shared, in place — no per-case copy). Generic: uses spec.secondary_namelist_var."""
    text = runfile.read_text()
    var = re.escape(namelist_var)
    text, n = re.subn(
        r'(' + var + r'\s*=\s*(["\']))[^"\']*(["\'])',
        r'\1' + str(target) + r'\3',
        text,
    )
    if n == 0:
        raise KeyError(f"'{namelist_var}' not found in {runfile} to repoint at the secondary surface")
    runfile.write_text(text)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--model", default=os.environ.get("A2MC_MODEL"))
    ap.add_argument("--param-list", default=os.environ.get("A2MC_PARAM_LIST_FILE"))
    ap.add_argument("--matrix", default=os.environ.get("A2MC_ENSEMBLE_MATRIX_FILE"))
    ap.add_argument("--run-root", default=os.environ.get("A2MC_OUTPUT_DIR"))
    ap.add_argument("--base-param", default=os.environ.get("A2MC_BASE_PARAM_FILE"))
    # BOTH env names, resolved exactly as the ensemble materializer and the validator do.
    # This script read ONLY the legacy name until 2026-09-15, which is the other half of the
    # defect: a config written with the CURRENT name ran here with no secondary base at all.
    _sec_default, _sec_env = secondary_base_default()
    warn_if_legacy_secondary(_sec_env)
    ap.add_argument("--secondary-base", default=_sec_default)
    ap.add_argument("--secondary-sweep", default=os.environ.get("A2MC_SECONDARY_SWEEP"))
    ap.add_argument("--case-pattern", default=os.environ.get("A2MC_CASE_NAME_PATTERN"))
    ap.add_argument("--start", type=int, default=1, help="1-based first trait (TR) row")
    ap.add_argument("--end", type=int, default=0, help="1-based last TR row (0 = all)")
    ap.add_argument("--baseline", action="store_true",
                    help="also materialize a V0 baseline (unperturbed primary x --baseline-level)")
    ap.add_argument("--baseline-tr", default="0", help="the {N} for the V0 baseline (default 0)")
    ap.add_argument("--baseline-level", type=float, default=None,
                    help="secondary level for V0 (default: the sweep level nearest the base)")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    req = {"--model": args.model, "--param-list": args.param_list, "--matrix": args.matrix,
           "--run-root": args.run_root, "--base-param": args.base_param,
           "--secondary-base": args.secondary_base, "--secondary-sweep": args.secondary_sweep,
           "--case-pattern": args.case_pattern}
    miss = [k for k, v in req.items() if not v]
    if miss:
        print(f"ERROR: missing {miss} — source the configs or pass explicitly.", file=sys.stderr)
        return 1
    if "{N}" not in args.case_pattern or "{M}" not in args.case_pattern:
        print(f"ERROR: --case-pattern must contain BOTH {{N}} and {{M}} (got {args.case_pattern!r})",
              file=sys.stderr)
        return 1

    import importlib
    from models import registry
    try:
        importlib.import_module(f"models.{args.model}")
        backend = registry.get_model(args.model)
    except Exception as e:
        print(f"ERROR: model '{args.model}' not onboarded: {e}", file=sys.stderr)
        return 2
    sec_var = getattr(backend.spec, "secondary_namelist_var", "")
    if not sec_var:
        print(f"ERROR: model '{args.model}' declares no secondary surface "
              f"(ModelSpec.secondary_namelist_var is empty)", file=sys.stderr)
        return 2

    prim_base = Path(args.base_param)
    sec_base = Path(args.secondary_base)
    for p in (prim_base, sec_base):
        if not p.exists():
            print(f"ERROR: base file not found: {p}", file=sys.stderr)
            return 1

    sweep_param, levels = _parse_sweep(args.secondary_sweep)
    M = len(levels)
    names, _, _ = parse_pft_param_list(args.param_list)
    X = np.loadtxt(args.matrix)
    if X.ndim == 1:
        X = X.reshape(1, -1)
    if X.shape[1] != len(names):
        print(f"ERROR: matrix has {X.shape[1]} cols but the trait list has {len(names)} names.",
              file=sys.stderr)
        return 1

    n_rows = X.shape[0]
    start = max(1, args.start)
    end = min(args.end if args.end > 0 else n_rows, n_rows)
    run_root = Path(args.run_root)
    cfg = dict(os.environ)
    cfg["A2MC_OUTPUT_DIR"] = str(run_root)

    total = (end - start + 1) * M + (M if args.baseline else 0)
    print(f"Model:        {args.model}   (secondary surface -> {sec_var})")
    print(f"Run root:     {run_root}")
    print(f"Primary base: {prim_base.name}  |  secondary base: {sec_base.name}")
    print(f"Traits:       {len(names)} params  |  TR matrix: {n_rows} rows (using {start}..{end})")
    print(f"Sweep (MG):   {sweep_param} in {levels}  (M={M})")
    print(f"Cases:        {end - start + 1} TR x {M} MG = {(end - start + 1) * M}"
          + (f" (+{M} V0 baseline)" if args.baseline else "")
          + f"  named {_case_name(args.case_pattern, '{N}', '{M}')}")

    if args.dry_run:
        print("\n[DRY-RUN] nothing written. Example cases:")
        for n in [start, start + 1, "...", end]:
            print("   " + "  ".join(_case_name(args.case_pattern, n, m + 1) for m in range(min(M, 4))))
        return 0

    # M shared secondary files (written once; cases point at them in place)
    shared_dir = run_root / "_mgmt_shared"
    shared_dir.mkdir(parents=True, exist_ok=True)
    sec_files = []
    for m, lvl in enumerate(levels, start=1):
        out = shared_dir / f"{sec_base.stem}__{sweep_param}{int(round(lvl))}.nc"
        backend.write_parameter_file(sec_base, {sweep_param: lvl}, out, surface="secondary")
        sec_files.append(out)
    print(f"  wrote {M} shared secondary files -> {shared_dir}/")

    made = 0

    def _one(tr, trait_edits):
        nonlocal made
        # primary written once per TR row (base basename, per-TR staging for the basename repoint)
        prim_stage = run_root / "_prim_stage" / f"TR{tr}" / prim_base.name
        prim_stage.parent.mkdir(parents=True, exist_ok=True)
        backend.write_parameter_file(prim_base, trait_edits, prim_stage, surface="primary")
        for m in range(1, M + 1):
            name = _case_name(args.case_pattern, tr, m)
            cd = backend.create_case(name, prim_stage, cfg)          # stages primary + repoints it
            _repoint_secondary(cd / "runfile.nml", sec_var, sec_files[m - 1])  # shared secondary[m]
            made += 1

    if args.baseline:
        lvl0 = args.baseline_level
        if lvl0 is None:
            lvl0 = min(levels, key=lambda v: abs(v - 120.0))  # nearest the R1-best density
        # only the MG matching lvl0 is a true V0; still emit all M for a full baseline row
        _one(args.baseline_tr, {})

    for i in range(start, end + 1):
        _one(i, dict(zip(names, X[i - 1])))
        if (i - start + 1) % 50 == 0 or i == end:
            print(f"  materialized TR {i - start + 1}/{end - start + 1}  ({made} cases)")

    print(f"\nDone: {made} case dirs under {run_root} (NOT submitted). "
          f"{M} shared secondary files in {shared_dir}. Submit separately.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
