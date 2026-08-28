#!/usr/bin/env python3
"""Extract the scored-target Y-matrix for a CROSSED TR{N}MG{M} adapter ensemble.

Completion is decided by the backend's `check_case_status` -- the model's own end-of-run artifact --
NOT by the presence of an output tape. Until 2026-08-21 this script used a tape glob, which for
EcoSIM means "the run STARTED" (it opens its single h0 tape at initialisation), so truncated runs
were scored and written as valid Y-matrix rows. See dev log 20260821g.

For each (trait row TR, sweep level MG) case with a completed history tape, evaluate the scored
targets (the non-`track: soil_bgc` entries of the site targets.yaml) via the model backend's verified
reductions, and write one CSV row: TR, MG, <sweep_param>, <target1>, <target2>, .... Missing/failed
tapes (crashed configs) -> NaN, so a Morris/screen downstream can exclude them. Reuses
tools.model_evaluate_case (single-case, verified reductions) — no re-implementation.

Env (source a2mc_noncime_config.sh + the round config first):
    A2MC_MODEL, A2MC_OUTPUT_DIR, A2MC_CASE_NAME_PATTERN (uses {N} and {M}),
    A2MC_N_PARAMS + A2MC_N_TRAJECTORIES (=> N trait rows), A2MC_SECONDARY_SWEEP ("PPI:40,120,200,280"),
    A2MC_USE_CASE_DIR (for validation/targets.yaml).
"""
from __future__ import annotations
import argparse, os, sys, math
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))


def _backend(model: str):
    """The model's backend, for its completion check. Imported lazily so --help costs nothing."""
    import importlib
    from models import registry
    importlib.import_module(f"models.{model}")
    return registry.get_model(model)


def _scored_targets(targets_yaml: Path):
    import yaml
    tg = yaml.safe_load(open(targets_yaml))["targets"]
    return [dict(name=k, **v) for k, v in tg.items() if v.get("track") != "soil_bgc"]


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--model", default=os.environ.get("A2MC_MODEL"))
    ap.add_argument("--run-root", default=os.environ.get("A2MC_OUTPUT_DIR"))
    ap.add_argument("--case-pattern", default=os.environ.get("A2MC_CASE_NAME_PATTERN"))
    ap.add_argument("--sweep", default=os.environ.get("A2MC_SECONDARY_SWEEP"))
    ap.add_argument("--n-tr", type=int,
                    default=int(os.environ.get("A2MC_N_TRAJECTORIES", 0)) * (int(os.environ.get("A2MC_N_PARAMS", 0)) + 1))
    ap.add_argument("--tr-start", type=int, default=0, help="first TR index (0 = the baseline)")
    ap.add_argument("--out", default=None)
    ap.add_argument("--targets", default=None)
    args = ap.parse_args()

    ucd = Path(os.environ.get("A2MC_USE_CASE_DIR", "use_cases/EcoSIM_BioCON"))
    # Priority: --targets CLI flag > $A2MC_VALIDATION_TARGETS (a round wrapper, e.g.
    # ecosim_biocon_config_r3.sh, may override it to a round-specific file) > the site
    # default -- same order as tools/targets_loader.py's resolve_targets_yaml().
    targets_yaml = (Path(args.targets) if args.targets
                    else Path(os.environ["A2MC_VALIDATION_TARGETS"]) if os.environ.get("A2MC_VALIDATION_TARGETS")
                    else ucd / "validation" / "targets.yaml")
    scored = _scored_targets(targets_yaml)
    sweep_param, _, vals = args.sweep.partition(":")
    levels = [float(v) for v in vals.split(",") if v.strip()]
    root = Path(args.run_root)
    out = Path(args.out) if args.out else root / "Y_matrix_scored.csv"

    from tools.model_evaluate_case import evaluate_model_case
    backend = _backend(args.model)
    names = [t["name"] for t in scored]
    rows, done, missing, incomplete, failed = [], 0, 0, 0, 0
    for tr in range(args.tr_start, args.n_tr + 1):
        for m, lvl in enumerate(levels, start=1):
            case = root / args.case_pattern.replace("{N}", str(tr)).replace("{M}", str(m))
            if not case.is_dir():
                rows.append((tr, m, lvl, *[float("nan")] * len(names))); missing += 1; continue
            # Completion is the BACKEND's check, never a tape glob. This script used
            # `case.glob("*.h0.*.nc")`, i.e. "a tape exists" -- and EcoSIM opens its single h0 tape
            # at INITIALISATION and appends to it, so that test answers "did this run START". A run
            # killed at the wall clock, or one that died mid-way, leaves evidence identical to a
            # complete one, and its truncated series was then SCORED and written as a valid row.
            # Fixed in the backend on 2026-08-20 (v2.257); this consumer bypassed the backend
            # entirely and so kept the bug. A reduce that raises on a short series would have landed
            # in the `except` below, but one that does not -- `annual`, which integrates whatever
            # records exist -- returns a plausible SMALLER number instead, which is the dangerous
            # case because nothing looks wrong.
            try:
                status = backend.check_case_status(case)
            except Exception:
                status = "UNKNOWN"
            if status != "COMPLETED":
                rows.append((tr, m, lvl, *[float("nan")] * len(names))); incomplete += 1; continue
            try:
                _, _, sim = evaluate_model_case(case, scored, model=args.model)
                rows.append((tr, m, lvl, *[sim.get(n, float("nan")) for n in names])); done += 1
            except Exception:
                rows.append((tr, m, lvl, *[float("nan")] * len(names))); failed += 1
        if tr % 50 == 0:
            print(f"  TR {tr}/{args.n_tr}  (done {done}, missing {missing}, "
                  f"incomplete {incomplete}, failed {failed})", flush=True)

    with open(out, "w") as f:
        f.write("TR,MG," + sweep_param + "," + ",".join(names) + "\n")
        for r in rows:
            f.write(",".join(("" if (isinstance(x, float) and math.isnan(x)) else f"{x:g}") for x in r) + "\n")
    print(f"\nY-matrix: {out}  ({len(rows)} rows; extracted {done}, missing {missing}, "
          f"incomplete {incomplete}, failed {failed})")
    if incomplete:
        print(f"  NOTE: {incomplete} case(s) had output but had NOT completed. Before 2026-08-21 "
              f"these were SCORED as valid rows.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
