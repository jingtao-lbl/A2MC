#!/usr/bin/env python
"""EcoSIM obs<->sim alignment + case evaluation — thin shim (roadmap L3.1).

As of the L3.1 genericization (docs/38 §6), the real implementation lives in the
model-agnostic ``tools/model_evaluate_case.py``. This module is a back-compat
shim that re-exports the EcoSIM-flavored entry points as thin wrappers over the
generic layer, so existing importers (``tests/test_ecosim_e2e.py``, any EcoSIM
call sites) keep working unchanged.

What moved where:
  * time-reduction (window/last/mean/max + snapshot index) -> generic
    ``model_evaluate_case.reduce_target``
  * GROUP-SELECT (EcoSIM flat ``data[:, pft-1]``) -> the default
    ``ModelBackend.select_group_series`` (EcoSIM inherits the default)
  * cost -> shared ``tools.cost_functions.compute_snapshot_cost``

Target spec + return contract are identical to before (see
``tools/model_evaluate_case`` for the full field docs).

Author: Jing Tao with Claude
"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from tools.model_evaluate_case import evaluate_model_case, reduce_target


def reduce_ecosim_target(extracted: Dict[str, Any], target: Dict[str, Any]) -> float:
    """Reduce one target spec against an extracted EcoSIM history dict to a scalar.

    Thin wrapper over the generic ``reduce_target`` bound to an EcoSIM backend
    (whose default ``select_group_series`` does the flat ``(time, pft)`` index).
    """
    from models.ecosim.backend import EcoSIMBackend
    return reduce_target(EcoSIMBackend(), extracted, target)


def evaluate_ecosim_case(
    case_path: Path,
    targets: List[Dict[str, Any]],
    backend: Optional[Any] = None,
    method: str = "relative_error",
    aggregation: str = "rmsre",
) -> Tuple[float, Dict[str, float], Dict[str, float]]:
    """Evaluate an EcoSIM case's h0 tape against validation targets.

    Thin wrapper over the generic ``evaluate_model_case`` with the EcoSIM
    backend. Returns ``(total_cost, per_target_errors, simulated_values)``.
    """
    if backend is None:
        from models.ecosim.backend import EcoSIMBackend
        backend = EcoSIMBackend()
    return evaluate_model_case(
        Path(case_path), targets, backend=backend, method=method, aggregation=aggregation)


def _cli() -> int:
    import argparse
    import json
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("case_path", help="case dir (or any dir) containing a *.ecosim.h0.*.nc tape")
    ap.add_argument("--targets", required=True, help="JSON file: list of target specs")
    args = ap.parse_args()
    targets = json.load(open(args.targets))
    total, errors, sim = evaluate_ecosim_case(Path(args.case_path), targets)
    print(f"total_cost (rmsre): {total:.4f}")
    for name in errors:
        print(f"  {name:20s} sim={sim[name]:.4g}  err={errors[name]:.4f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(_cli())
