#!/usr/bin/env python
"""PFLOTRAN obs<->sim alignment + case evaluation (the model's parallel of
``tools/ecosim_evaluate_case.py``; gap matrix in dev log ``20260802c``).

Scores a completed PFLOTRAN case's mass-balance tape against a case's
``targets.yaml`` and returns the same ``(total_cost, per_target_errors,
simulated)`` triple every other model's evaluator returns, through the same
shared cost layer (``tools.cost_functions.compute_snapshot_cost``).

WHAT IS MODEL-SPECIFIC HERE, AND WHY IT IS NOT IN THE GENERIC LAYER
------------------------------------------------------------------
Two things, both living on ``PFLOTRANBackend`` (see its ``MODEL_REDUCES``):

1. **The targets are RATIOS, not columns.** miniLEO's absolute
   observation-to-model area normalisation is unresolved — four independent
   estimates disagree by up to 13x (``targets.yaml`` BLOCKER) — so no absolute
   mass or depth target is scorable. An outflow CONCENTRATION divides two
   columns written at the same coupler, so the area cancels exactly:

       C_X = (X [mol/h]) / (Water Mass [kg/h] / rho * 1000)   [mol/L]

   The generic single-variable reduce path cannot express a ratio.

2. **Windows are HOURS, not row indices.** The generic
   ``model_evaluate_case.reduce_target`` slices ``window`` as 0-based rows. On
   the miniLEO tape (3360 rows, uniform 0.5 h, 0.5-1680 h) the index reading of
   ``[0, 768]`` covers 0.5-384.5 h — half the intended span, and a plausible
   number rather than an error. Every reduce resolves the window against the
   tape's own ``Time [h]`` column.

RELATION TO THE SITE SCRIPT
---------------------------
``use_cases/PFLOTRAN_miniLEO/validation/compare_outflow_chemistry.py`` was the
reference implementation of this reduce and remains the human-facing
species-by-species comparison table. This module is the A2MC-facing path: same
arithmetic, driven from ``targets.yaml`` through the backend, so the ensemble
screening layer can score cases. The two agreeing is a regression test
(``tests/test_pflotran_evaluate.py``).

Usage (library)::

    from tools.pflotran_evaluate_case import evaluate_pflotran_case, targets_from_yaml
    targets = targets_from_yaml("use_cases/PFLOTRAN_miniLEO/validation/targets.yaml")
    total, errors, sim = evaluate_pflotran_case(case_dir, targets)

Usage (CLI)::

    python tools/pflotran_evaluate_case.py <case_dir> \\
        --targets use_cases/PFLOTRAN_miniLEO/validation/targets.yaml

Author: Jing Tao with Claude
"""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

REPO = Path(__file__).resolve().parent.parent
if str(REPO) not in sys.path:          # so the CLI works when run as a script
    sys.path.insert(0, str(REPO))

from tools.model_evaluate_case import evaluate_model_case, reduce_target  # noqa: E402


def _backend():
    from models.pflotran.backend import PFLOTRANBackend
    return PFLOTRANBackend()


def targets_from_yaml(yaml_file) -> List[Dict[str, Any]]:
    """Load a case's ``targets.yaml`` into the target-spec dicts the evaluator takes.

    The generic ``tools.targets_loader`` owns the parsing (one source of truth for
    the file format); this converts its ``Target`` objects into the flat dict spec
    ``model_evaluate_case`` consumes, carrying the fields a PFLOTRAN derived reduce
    needs — ``denominator`` (the ratio's second column), the hour ``window``, and
    ``observed_series_file`` (the full measured series ``outflow_flux`` scores
    against).

    Targets with no ``variable`` are skipped: on this model that means a target
    recorded in the file but not scorable from the mass-balance tape (miniLEO's
    pH and porewater targets are documented there as exactly that).
    """
    from tools.targets_loader import parse_targets_yaml
    specs: List[Dict[str, Any]] = []
    for name, t in parse_targets_yaml(yaml_file).items():
        if not t.variable:
            continue
        spec: Dict[str, Any] = {
            "name": name,
            "variable": t.variable,
            "observed": t.observed,
            "uncertainty": t.uncertainty,
            "units": t.units,
        }
        if t.denominator:
            spec["denominator"] = t.denominator
        if t.observed_series_file:
            spec["observed_series_file"] = t.observed_series_file
        if t.reduce:
            spec["reduce"] = t.reduce
        if t.window is not None:
            spec["window"] = t.window
        if t.time_index is not None:
            spec["time"] = t.time_index
        if t.pft is not None:
            spec["pft"] = t.pft
        specs.append(spec)
    return specs


def reduce_pflotran_target(extracted: Dict[str, Any], target: Dict[str, Any]) -> float:
    """Reduce one target spec against an extracted PFLOTRAN history dict to a scalar.

    Thin wrapper over the generic ``reduce_target`` bound to a PFLOTRAN backend,
    which dispatches this model's derived reduces (``outflow_concentration``).
    """
    return reduce_target(_backend(), extracted, target)


def evaluate_pflotran_case(
    case_path: Path,
    targets: List[Dict[str, Any]],
    backend: Optional[Any] = None,
    method: str = "relative_error",
    aggregation: str = "rmsre",
) -> Tuple[float, Dict[str, float], Dict[str, float]]:
    """Evaluate a completed PFLOTRAN case's ``*-mas.dat`` against validation targets.

    Returns ``(total_cost, per_target_errors, simulated_values)`` — identical
    contract to ``evaluate_ecosim_case`` / ``evaluate_model_case``.
    """
    return evaluate_model_case(
        Path(case_path), targets, backend=backend or _backend(),
        method=method, aggregation=aggregation)


def _cli() -> int:
    import argparse
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("case_path", help="case dir containing a completed *-mas.dat")
    ap.add_argument("--targets", required=True, help="a case's targets.yaml")
    ap.add_argument("--method", default=None,
                    help="per-target error metric (default: the file's cost_config)")
    ap.add_argument("--aggregation", default=None,
                    help="how to combine per-target errors (default: the file's cost_config)")
    args = ap.parse_args()

    if str(REPO) not in sys.path:
        sys.path.insert(0, str(REPO))
    from tools.targets_loader import parse_cost_config

    cc = parse_cost_config(args.targets)
    method = args.method or cc["error_method"]
    aggregation = args.aggregation or cc["aggregation_method"]

    targets = targets_from_yaml(args.targets)
    if not targets:
        print(f"ERROR: no tape-scorable targets in {args.targets}", file=sys.stderr)
        return 1
    total, errors, sim = evaluate_pflotran_case(
        Path(args.case_path), targets, method=method, aggregation=aggregation)

    obs = {t["name"]: float(t["observed"]) for t in targets}
    units = {t["name"]: t.get("units", "") for t in targets}
    print(f"case: {args.case_path}")
    print(f"targets: {len(targets)} from {args.targets}   "
          f"cost: {method} / {aggregation}\n")
    print(f"{'target':18s} {'observed':>12s} {'simulated':>12s} {'sim/obs':>9s} "
          f"{'error':>9s}  units")
    for name in errors:
        ratio = sim[name] / obs[name] if obs[name] else float("nan")
        print(f"{name:18s} {obs[name]:12.5g} {sim[name]:12.5g} {ratio:9.3f} "
              f"{errors[name]:9.4f}  {units.get(name, '')}")
    print(f"\ntotal_cost ({aggregation}) = {total:.4f}")
    return 0


if __name__ == "__main__":
    sys.path.insert(0, str(REPO))
    raise SystemExit(_cli())
