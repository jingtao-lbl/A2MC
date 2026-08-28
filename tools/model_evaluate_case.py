#!/usr/bin/env python
"""Generic model-dispatched obs<->sim alignment + case evaluation (roadmap L3.1).

The model-agnostic parallel of the FATES ``tools/evaluate_case.py`` and the
generalization of ``tools/ecosim_evaluate_case.py`` — the layer that reduces a
simulated history variable to the scalar a validation target compares against,
for ANY onboarded model. Per the adapter-kit additive rule (docs/38 §3/§6):
this is a NEW file dispatched through the active model's ``ModelBackend``; the
FATES ``evaluate_case.py`` (SZPF size × PFT reduction) is untouched and remains
the reference implementation.

The split of responsibility:

  * GROUP-SELECT (model-specific) — picking the grouping-axis (PFT) time series
    out of an extracted variable — is delegated to
    ``backend.select_group_series(data, target)``. The default (flat indexing,
    ``data[:, pft-1]``) is EcoSIM's behavior; a block-structured model (FATES
    SZPF) overrides it on its backend.
  * TIME-REDUCE (model-agnostic) — window/last/mean/max + snapshot index — is
    done here in ``reduce_target`` (lifted verbatim from
    ``tools/ecosim_evaluate_case.py``).
  * COST (model-agnostic) — ``tools.cost_functions.compute_snapshot_cost``,
    identical to FATES so all models score through the same metric layer.

Target spec (one dict per target):
    name       : target id (free label, e.g. "LEAF_C_pft1")
    variable   : history var on the tape (e.g. "LEAF_C_pft")
    pft        : 1-based grouping-axis slot (omit / None for a column-level var)
    time       : 0-based time index for a snapshot,   OR
    window     : [lo, hi] 0-based inclusive index range for a series-snapshot
    reduce     : "last" | "mean" | "max" (window only; default "mean")
    observed   : observed value
    weight     : optional (default 1.0)

Usage (library):
    from tools.model_evaluate_case import evaluate_model_case
    total, errors, sim = evaluate_model_case(case_path, targets, model="ecosim")

Usage (CLI):
    python tools/model_evaluate_case.py --model ecosim <case_path> --targets t.json

Author: Jing Tao with Claude
"""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import numpy as np

REPO = Path(__file__).resolve().parent.parent


def _resolve_backend(model: Optional[str] = None, backend: Optional[Any] = None) -> Any:
    """Resolve a ``ModelBackend``.

    Priority: an explicit ``backend`` instance > a named ``model`` (imported +
    looked up in the registry, the proven dispatch pattern from
    ``tools/model_preflight.py``) > the env-resolved active model.
    """
    if backend is not None:
        return backend
    if str(REPO) not in sys.path:
        sys.path.insert(0, str(REPO))
    import importlib
    from models import registry
    if model is None:
        be, _ = registry.get_active_model()
        return be
    importlib.import_module(f"models.{model}")  # self-registers the backend
    return registry.get_model(model)


# Reduce keywords that are ecosystem-level (plot-scale) and MODEL-SPECIFIC — the generic
# reduce_target dispatches these to backend.reduce_ecosystem (each adapter implements its
# own; there is no model-agnostic default). The generic keywords are max/mean/last.
ECOSYSTEM_REDUCES = frozenset({
    "sum_pft_peak", "growing_season_mean_abs", "growing_season_daytime_mean_abs",
    "annual", "depth_integral", "year_end",
})

# NB `year_end` MUST be listed above, not merely implemented in the backend. A reduce keyword
# missing from this set does not error — it falls through to the snapshot path at the end of
# `reduce_target`, which returns `series[target.get("time", -1)]`, i.e. the LAST RECORD OF THE
# WHOLE TAPE. For a within-year cumulative that is the final year's total: a plausible-looking
# number, silently wrong, and wrong by more the longer the run. Measured 2026-08-15 while adding
# `year_end` — three of its tests passed BEFORE the reducer existed, purely because that
# fallthrough happened to coincide with the expected value on a short fixture.


def reduce_target(backend: Any, extracted: Dict[str, Any], target: Dict[str, Any]) -> float:
    """Reduce one target spec against an extracted history dict to a scalar.

    ``extracted`` maps variable name -> ndarray (from
    ``backend.extract_history_variables``). The model-specific GROUP-SELECT is
    delegated to ``backend.select_group_series``; the time reduction below is
    model-agnostic.
    """
    var = target["variable"]
    how = target.get("reduce", "mean")

    # ---- Ecosystem-level reductions → MODEL-SPECIFIC (delegated to the backend) ----
    # Σ-over-group / per-year rate integration / depth integrals depend on the model's
    # group axis, calendar, timestep and soil geometry, so each adapter owns them
    # (mirrors select_group_series). The generic layer only dispatches; there is no
    # model-agnostic default (base.reduce_ecosystem raises NotImplementedError).
    if how in ECOSYSTEM_REDUCES:
        return backend.reduce_ecosystem(extracted, target, how)

    # ---- DERIVED reductions → MODEL-SPECIFIC, declared by the backend ----
    # A target that is not any one column (PFLOTRAN's outflow_concentration is a
    # RATIO of two) cannot go through the single-variable path below. The set is
    # declared on the backend, not enumerated here, so a new adapter adds its own
    # vocabulary without editing this file.
    if how in getattr(backend, "MODEL_REDUCES", frozenset()):
        return backend.reduce_derived(extracted, target, how)

    if var not in extracted:
        raise KeyError(f"variable '{var}' not in extracted history {list(extracted)}")
    data = np.asarray(extracted[var])

    # GROUP-SELECT (model-specific) -> a 1-D (time,) series.
    series = np.asarray(backend.select_group_series(data, target))

    # TIME-REDUCE (model-agnostic; lifted verbatim from ecosim_evaluate_case).
    if "window" in target:
        lo, hi = target["window"]
        # hi is an inclusive index; hi == -1 means "to the end" (hi+1 == 0 would
        # otherwise give an empty slice for a negative end index).
        end = None if hi == -1 else hi + 1
        seg = series[lo:end]
        if seg.size == 0:
            raise ValueError(f"{var}: window {target['window']} selects no time steps "
                             f"(series length {series.shape[0]})")
        how = target.get("reduce", "mean")
        return float({"last": seg[-1], "mean": np.mean(seg), "max": np.max(seg)}[how])
    ti = int(target.get("time", -1))
    return float(series[ti])


def evaluate_model_case(
    case_path: Path,
    targets: List[Dict[str, Any]],
    model: Optional[str] = None,
    backend: Optional[Any] = None,
    method: str = "relative_error",
    aggregation: str = "rmsre",
) -> Tuple[float, Dict[str, float], Dict[str, float]]:
    """Evaluate a completed case's history tape against validation targets.

    Resolves the model backend (explicit ``backend`` > named ``model`` >
    env-active), extracts the needed variables, reduces each target to a scalar,
    and scores through the shared ``compute_snapshot_cost`` so every model uses
    the identical cost layer.

    Returns ``(total_cost, per_target_errors, simulated_values)``.
    """
    backend = _resolve_backend(model, backend)

    # ecosystem targets like plant_C = [SHOOT_C_pft, Root_C_pft]) and picking up the
    # optional second column a derived reduce forms a ratio against (`denominator`,
    # e.g. PFLOTRAN's "east Water Mass [kg/h]"). GROUPED by which history tape each
    # target reads (`target.get("tape", "h0")`). Most models/targets have exactly
    # one tape and this collapses to a single extract call; a model with more than
    # one history tape (e.g. EcoSIM's hourly "h1" second tape, wired for a sub-daily-window
    # target -- see growing_season_daytime_mean_abs) gets one extract call per tape, merged.
    # A denominator that is not extracted here would surface as a KeyError deep inside the
    # backend's reduce.
    vars_by_tape: Dict[str, set] = {}
    for t in targets:
        vlist = list(t["variable"]) if isinstance(t["variable"], (list, tuple)) else [t["variable"]]
        if t.get("denominator"):
            vlist = vlist + [t["denominator"]]
        vars_by_tape.setdefault(t.get("tape", "h0"), set()).update(vlist)

    extracted: Dict[str, Any] = {}
    for tape, vnames in vars_by_tape.items():
        got = backend.extract_history_variables(Path(case_path), sorted(vnames), tape=tape)
        collisions = (set(got) - {"time"}) & set(extracted)
        if collisions:
            raise ValueError(
                f"variable(s) {sorted(collisions)} requested from more than one tape in the "
                f"same target set (tape '{tape}' and an earlier one) -- targets must agree on "
                f"which tape a given variable name comes from")
        # "time" is dropped when >1 tape is in play: different tapes have different cadences
        # (e.g. h0 daily vs h1 hourly), so there is no single well-defined merged time axis,
        # and nothing downstream (reduce_target/reduce_ecosystem) reads extracted["time"].
        extracted.update({k: v for k, v in got.items()
                          if k != "time" or len(vars_by_tape) == 1})

    simulated: Dict[str, float] = {}
    observed: Dict[str, float] = {}
    for t in targets:
        simulated[t["name"]] = reduce_target(backend, extracted, t)
        observed[t["name"]] = float(t["observed"])

    from tools.cost_functions import compute_snapshot_cost
    total_cost, errors = compute_snapshot_cost(
        simulated, observed, method=method, aggregation=aggregation)
    return total_cost, errors, simulated


def _cli() -> int:
    import argparse
    import json
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("case_path", help="case dir containing a completed history tape")
    ap.add_argument("--model", required=True, help="onboarded model name (e.g. ecosim)")
    ap.add_argument("--targets", required=True, help="JSON file: list of target specs")
    ap.add_argument("--method", default="relative_error", help="per-target error metric")
    ap.add_argument("--aggregation", default="rmsre", help="how to combine per-target errors")
    args = ap.parse_args()

    sys.path.insert(0, str(REPO))
    with open(args.targets) as fh:
        targets = json.load(fh)
    total, errors, sim = evaluate_model_case(
        Path(args.case_path), targets, model=args.model,
        method=args.method, aggregation=args.aggregation)
    print(f"model: {args.model}   total_cost ({args.aggregation}): {total:.4f}")
    for name in errors:
        print(f"  {name:20s} sim={sim[name]:.4g}  err={errors[name]:.4f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(_cli())
