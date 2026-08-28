#!/usr/bin/env python
"""Generate a provisional, default-anchored parameter-list (with bounds) for ANY
onboarded model — the model-generic distillation of
``scripts/generate_ecosim_bounds.py``.

The curated seed carries *relationships*, not ranges. Morris/Sobol sampling needs
per-parameter [lower, upper] bounds. This script produces a first, PROVISIONAL
bounds artifact so a Phase-0 ensemble can be designed:

  * parameters = the calibratable subset in the model seed's ``parameters:`` block
    (``models/<model>/curated_seed.yaml``). Discrete switches are excluded by
    construction — the seed lists them only under mechanisms, never here.
  * default value = read from the model's parameter/input file via the active
    model backend (``backend.parse_parameters`` → the adapter's parser), at the
    dominant grouping-axis slot (``--pft-index``, 0 by default).
  * bounds = default ± ``frac``·|default|, clamped to [0, 1] for the seed/spec
    fraction set and to >= 0 for non-negative kinds. Zero/absent defaults get a
    flagged [0, 1] placeholder.

The fraction/signed heuristics are NOT hard-coded here — they are read from the
active model's ``ModelSpec``:

  * ``spec.fraction_param_names``  — param names bounded to [0, 1]
  * ``spec.fraction_categories``   — seed/param categories whose members are [0, 1]
  * ``spec.signed_param_names``    — params that may be negative (skip the >=0 clamp)

so the identical algorithm serves EcoSIM, and any future adapter, without an edit.
This is ADDITIVE (docs/38 §3): the FATES-shaped ``generate_ecosim_bounds.py`` is
left untouched; this is a NEW file dispatched through the model backend/spec, the
same proven scaffold as ``tools/model_preflight.py`` / ``tools/model_ensemble_status.py``.

The output CSV is directly consumable by
``phases/phase0_design/create_parameter_sample.py::parse_param_list`` (name +
lower_bound/upper_bound columns).

**These bounds are PROVISIONAL** — anchored only to the default value, not to
literature or expert priors. Refine per parameter before a production ensemble.

Usage:
    python scripts/model_generate_bounds.py --model ecosim \
        [--seed models/ecosim/curated_seed.yaml] \
        [--pft-file <the model's dataset parameter_file>] \
        [--pft-index 0] [--frac 0.5] \
        [--out models/ecosim/reference_bounds/ecosim_param_list.csv]

Defaults for --seed / --pft-file / --out resolve to the model's own paths when
omitted (seed from ``models/<model>/``, param file from the model's registered
dataset, out under ``models/<model>/reference_bounds/``).

Author: Jing Tao with Claude
"""
from __future__ import annotations

import argparse
import csv
import importlib
import sys
from pathlib import Path

import yaml

REPO = Path(__file__).resolve().parent.parent


def _bounds(name, category, default, frac, frac_params, frac_categories, signed_params):
    """Provisional [lo, hi] from a default value.

    Byte-for-byte the same algorithm as ``generate_ecosim_bounds._bounds``; the
    only change is that the fraction/signed sets are passed in from the spec
    instead of being module globals.
    """
    if default is None:
        return (0.0, 1.0, True)  # flagged placeholder
    d = float(default)
    if d == 0.0:
        return (0.0, 1.0, True)  # flagged placeholder
    span = frac * abs(d)
    lo, hi = d - span, d + span
    is_fraction = name in frac_params or category in frac_categories
    if is_fraction:
        lo, hi = max(0.0, lo), min(1.0, hi) if d <= 1.0 else hi
    elif name not in signed_params and d > 0:
        lo = max(0.0, lo)
    return (lo, hi, False)


def _record_default(record, pft_index):
    """Extract a scalar default at ``pft_index`` from a parser record.

    Handles both adapter-contract shapes: a dict record with a ``"default"`` key
    (models/_template) and a dataclass record with ``.default_values`` (EcoSIM).
    Mirrors the legacy ``float(arr[idx]) if arr.ndim else float(arr)`` semantics:
    a scalar is taken as-is; a 1-D sequence is indexed at ``pft_index``; anything
    deeper (or absent) fails the ``float()`` coercion and returns None (→ flagged
    placeholder), exactly as the direct-netCDF read did.
    """
    if record is None:
        return None
    if isinstance(record, dict):
        dv = record.get("default", record.get("default_values"))
    else:
        dv = getattr(record, "default_values", None)
        if dv is None:
            dv = getattr(record, "default", None)
    if dv is None:
        return None
    try:
        if isinstance(dv, (list, tuple)):
            v = dv[pft_index]
        else:
            v = dv
        return float(v)
    except (IndexError, TypeError, ValueError):
        return None


def _resolve_dataset(model: str, registry):
    """Return the model's canonical (or first) registered dataset, or None."""
    versions = registry.list_datasets(model).get(model, [])
    if not versions:
        return None
    canonical = None
    for v in versions:
        ds = registry.get_dataset(model, v)
        if getattr(ds, "canonical", False):
            canonical = ds
            break
    return canonical or registry.get_dataset(model, versions[0])


def _abs(path) -> Path:
    """Resolve a (possibly repo-relative) path against the repo root."""
    p = Path(path)
    return p if p.is_absolute() else (REPO / p)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--model", required=True, help="onboarded model name (e.g. ecosim)")
    ap.add_argument("--seed", default=None, help="curated seed YAML (default: models/<model>/curated_seed.yaml)")
    ap.add_argument("--pft-file", default=None, help="parameter/input file (default: the model's registered dataset parameter_file)")
    ap.add_argument("--pft-index", type=int, default=0, help="grouping-axis slot to read defaults from (0-based)")
    ap.add_argument("--frac", type=float, default=0.5, help="fractional half-width of the bound (default 0.5 = +/-50%%)")
    ap.add_argument("--out", default=None, help="output CSV (default: models/<model>/reference_bounds/<model>_param_list.csv)")
    args = ap.parse_args()

    sys.path.insert(0, str(REPO))
    try:
        from models import registry
    except Exception as e:  # pragma: no cover
        print(f"ERROR: cannot import model registry: {e}", file=sys.stderr)
        return 1
    # Importing the model package self-registers its backend + datasets.
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

    # ---- Resolve paths (model defaults where sensible) ----
    seed_path = _abs(args.seed) if args.seed else (REPO / "models" / args.model / "curated_seed.yaml")
    if args.pft_file:
        pft_path = _abs(args.pft_file)
    else:
        ds = _resolve_dataset(args.model, registry)
        if ds is None or ds.parameter_file is None:
            print(f"ERROR: no --pft-file given and model '{args.model}' has no dataset parameter_file to default to.", file=sys.stderr)
            return 1
        pft_path = _abs(ds.parameter_file)
    out_path = _abs(args.out) if args.out else (
        REPO / "models" / args.model / "reference_bounds" / f"{args.model}_param_list.csv"
    )

    if not seed_path.exists():
        print(f"ERROR: seed not found: {seed_path}", file=sys.stderr)
        return 1
    if not pft_path.exists():
        print(f"ERROR: parameter file not found: {pft_path}", file=sys.stderr)
        return 1

    # ---- Load the calibratable subset + the model's default surface ----
    seed = yaml.safe_load(open(seed_path))
    params = seed.get("parameters", {})  # the calibratable subset
    if not params:
        print(f"ERROR: seed has no 'parameters:' block: {seed_path}", file=sys.stderr)
        return 1
    parsed = backend.parse_parameters(pft_path)  # dispatches through spec.parameter_parser_class

    # ---- Spec-driven bounds heuristics (no model-specific constants here) ----
    frac_params = set(spec.fraction_param_names)
    frac_categories = set(spec.fraction_categories)
    signed_params = set(spec.signed_param_names)

    rows, flagged = [], []
    for name, meta in sorted(params.items()):
        cat = (meta or {}).get("category", "other")
        default = _record_default(parsed.get(name), args.pft_index)
        lo, hi, flag = _bounds(name, cat, default, args.frac, frac_params, frac_categories, signed_params)
        if flag:
            flagged.append(name)
        rows.append({
            "name": name, "category": cat,
            "default": "" if default is None else f"{default:.6g}",
            "lower_bound": f"{lo:.6g}", "upper_bound": f"{hi:.6g}",
            "bound_source": "PLACEHOLDER" if flag else "default+/-%d%%" % int(args.frac * 100),
        })

    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", newline="") as f:
        f.write("# PROVISIONAL %s parameter list + bounds (default-anchored, +/-%d%%).\n"
                % (spec.display_name, int(args.frac * 100)))
        f.write("# Generated by scripts/model_generate_bounds.py --model %s. Refine ranges before a production ensemble.\n"
                % args.model)
        f.write("# Consumable by phases/phase0_design/create_parameter_sample.py::parse_param_list.\n")
        w = csv.DictWriter(f, fieldnames=["name", "category", "default", "lower_bound", "upper_bound", "bound_source"])
        w.writeheader()
        w.writerows(rows)

    print(f"wrote {len(rows)} parameters -> {out_path}")
    if flagged:
        print(f"  {len(flagged)} PLACEHOLDER bounds (zero/absent default, need manual ranges): {flagged}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
