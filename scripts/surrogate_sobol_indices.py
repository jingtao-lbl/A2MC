#!/usr/bin/env python
"""Compute Sobol' indices by running a large Saltelli design through a FITTED SURROGATE.

WHY THIS EXISTS. A2MC's sensitivity path assumed the design and the analyzer match: sample
Saltelli, run the simulator, call ``SALib.analyze.sobol``. That breaks for a round designed as a
**space-filling** ensemble. A scrambled Sobol' SEQUENCE is not a Saltelli DESIGN -- it has no
A/B/AB cross-sampling structure, so ``sobol.analyze`` cannot read it, and ``morris.analyze``
cannot either because there are no trajectories. Feeding a space-filling matrix to either
analyzer does not error; it returns numbers computed from a structure that is not there.

The architecture this implements instead:

    space-filling ensemble on the EXPENSIVE simulator   ->  train a surrogate
    an independent ensemble                             ->  validate it
    a very large Saltelli design through the CHEAP surrogate -> Sobol' indices

The simulator is asked only for what it is uniquely able to give: well-spread samples of the
true response. The 34*N model evaluations a second-order Saltelli estimate needs are paid for in
surrogate predictions, which cost milliseconds.

WHAT THIS SCRIPT REFUSES TO DO, AND WHY THAT IS THE POINT. Indices computed from an inaccurate
surrogate are precise numbers about the wrong function, and nothing downstream can tell them
from good ones -- the estimator's own confidence intervals narrow with N regardless, so they
describe sampling error in the surrogate, never the surrogate's error against the simulator.
So accuracy is a GATE, not a footnote: without ``--accuracy-report`` (or an explicit
``--no-accuracy-gate``) this script exits non-zero before sampling anything.

GENERIC BY DESIGN. This is A2MC's own machinery, so it is generic across models; everything
model-specific reaches it through the ``SurrogateSpec`` and the saved surrogate.

Usage::

    python scripts/surrogate_sobol_indices.py \\
        --surrogate <dir saved by SurrogateModel.save> \\
        --accuracy-report <acceptance.json> \\
        --n-base 8192 --second-order \\
        --out phase_results/<stem>/

Author: Jing Tao with Claude on Perlmutter
"""
from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

import numpy as np

REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))


# =============================================================================
# The accuracy gate
# =============================================================================

def load_accuracy_gate(path: Optional[str], allow_missing: bool) -> Dict[str, Any]:
    """Return the acceptance evidence, or refuse.

    A surrogate that has not been validated against held-out simulator runs cannot support a
    sensitivity claim. The gate is deliberately blunt: a missing report is a hard stop rather
    than a warning, because a warning printed above 200 lines of indices is read as noise.
    """
    if path is None:
        if allow_missing:
            return {"gated": False,
                    "note": "EXPLICITLY UNGATED via --no-accuracy-gate; indices are "
                            "NOT supported by held-out evidence and must not be reported "
                            "as a sensitivity result"}
        raise SystemExit(
            "REFUSING: no --accuracy-report given.\n"
            "  Sobol' indices from an unvalidated surrogate are precise numbers about the wrong\n"
            "  function, and the estimator's own confidence intervals cannot reveal it -- they\n"
            "  narrow with N whatever the surrogate's error against the simulator.\n"
            "  Run models.surrogate.validate.run_acceptance first, or pass --no-accuracy-gate\n"
            "  if you are deliberately producing a throwaway diagnostic.")
    rep = json.loads(Path(path).read_text())
    # ONE derivation of the verdict, shared with tools/promote_surrogate.py. Reading `passed`
    # directly was wrong twice over: it is a PROPERTY of AcceptanceReport rather than a field, so a
    # report serialized from the dataclass has `verdicts` and no `passed`, and this gate then fell
    # through to the promotion check having read no verdict at all. Measured 2026-09-22: 8 of 21
    # tracked acceptance.json files, three of which record a FAIL in their verdicts.
    from models.surrogate.validate import report_passed                # noqa: E402
    passed = report_passed(rep)
    if passed is False:
        raise SystemExit(
            f"REFUSING: the acceptance report at {path} records passed=False.\n"
            f"  {rep.get('summary', '')}\n"
            "  Fix the surrogate (more training points, a different learner family, or a\n"
            "  restricted input box) before asking it for sensitivity indices.")
    if passed is None:
        # FAIL CLOSED. No verdict is not a pass: an emulator fit script that writes its own
        # summary dict produces a file that looks like an acceptance report and rules nothing
        # in or out, and treating that as permission is how an unvalidated surrogate reaches a
        # published sensitivity table.
        raise SystemExit(
            f"REFUSING: the acceptance report at {path} records NO VERDICT.\n"
            "  It has neither a `passed` field nor a non-empty `verdicts` block, so nothing in\n"
            "  it says the surrogate was accepted. This is what an ad-hoc summary written by a\n"
            "  fit script looks like.\n"
            "  Produce a real report with models.surrogate.validate.run_acceptance, or pass\n"
            "  --no-accuracy-gate if you are deliberately producing a throwaway diagnostic.")

    # PASSING METRICS ARE NECESSARY AND NOT SUFFICIENT. Using a surrogate to steer a search is a
    # decision, and the checks that should decide it -- is the training region the one that
    # contains the answer, does the response look physically sensible, was the split optimistic --
    # are not thresholds. So the gate is the HUMAN promotion, not the report.
    from tools.promote_surrogate import check_promotion            # noqa: E402
    promoted, why = check_promotion(Path(path).parent)
    if not promoted and not allow_missing:
        raise SystemExit(
            f"REFUSING: the acceptance metrics pass, but this surrogate is not PROMOTED.\n"
            f"  {why}\n"
            "  Review it and record the approval:\n"
            f"      python tools/promote_surrogate.py review  {Path(path).parent}\n"
            f"      python tools/promote_surrogate.py promote {Path(path).parent} \\\n"
            "          --basis '<what you checked beyond the metrics>' --reviewed-by NAME\n"
            "  Or pass --no-accuracy-gate for a throwaway diagnostic, which stamps the output\n"
            "  as unsupported.")
    return {"gated": True, "report_path": str(path), "passed": passed,
            "promoted": promoted, "promotion": why,
            "summary": rep.get("summary")}


# =============================================================================
# Sampling + prediction
# =============================================================================

def saltelli_design(spec, n_base: int, second_order: bool, seed: int) -> np.ndarray:
    """A Saltelli design over the SPEC'S OWN input box, in the spec's column order.

    The column order is load-bearing: ``SurrogateSpec.input_names`` IS the X column order, so a
    problem dict built from anything else silently permutes the design.
    """
    from SALib.sample import sobol as sobol_sample

    problem = {"num_vars": spec.n_inputs,
               "names": list(spec.input_names),
               "bounds": [[lo, hi] for lo, hi in
                          zip(spec.input_lower, spec.input_upper)]}
    X = sobol_sample.sample(problem, n_base, calc_second_order=second_order,
                            scramble=True, seed=seed)
    return problem, X


def predict_in_chunks(model, X: np.ndarray, chunk: int) -> Dict[str, np.ndarray]:
    """Predict a large design without materializing every intermediate at once.

    Also accumulates the extrapolation verdict. A Saltelli design fills the box UNIFORMLY while
    the training set was space-filling over the same box, so coverage is usually fine -- but
    "usually" is not a claim, and a corner the training set never reached produces confident
    nonsense that the indices then average in.
    """
    vals: List[np.ndarray] = []
    in_hull_n = 0
    in_hull_seen = 0
    for k in range(0, len(X), chunk):
        pred = model.predict_batch(X[k:k + chunk])
        vals.append(np.asarray(pred.values, dtype=float))
        if pred.in_hull is not None:
            in_hull_n += int(np.sum(pred.in_hull))
            in_hull_seen += len(pred.in_hull)
    Y = np.vstack(vals)
    return {"Y": Y,
            "in_hull_fraction": (in_hull_n / in_hull_seen) if in_hull_seen else None}


def analyze(problem, Y_col: np.ndarray, second_order: bool, seed: int) -> Dict[str, Any]:
    from SALib.analyze import sobol as sobol_analyze
    return sobol_analyze.analyze(problem, Y_col, calc_second_order=second_order,
                                 print_to_console=False, seed=seed)


# =============================================================================
# Main
# =============================================================================

def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--surrogate", required=True,
                    help="directory written by SurrogateModel.save()")
    ap.add_argument("--accuracy-report", default=None,
                    help="JSON acceptance report from models.surrogate.validate.run_acceptance")
    ap.add_argument("--no-accuracy-gate", action="store_true",
                    help="proceed WITHOUT held-out evidence; the output is stamped unsupported")
    ap.add_argument("--n-base", type=int, default=8192,
                    help="Saltelli base N; total evaluations are N*(2P+2) with second order, "
                         "N*(P+2) without")
    ap.add_argument("--second-order", action="store_true",
                    help="also estimate S_ij (costs 2P+2 rather than P+2 per base sample)")
    # Default 123 matches `create_adapter_parameter_sample.py --seed`, deliberately, and is NOT
    # read from an env var. Introducing an `A2MC_SEED` here would have been a fourth spelling of
    # "a seed" beside that argparse default and `A2MC_SOBOL_SEQ_VALID_SEED` -- generic enough to
    # read as "the seed for everything" while actually controlling only the Saltelli design. The
    # pre-commit variable check flagged it at birth; dismissing that same warning is what let
    # A2MC_N_SOBOL_SAMPLES become a duplicate of A2MC_N_SAMPLES and cost three wrong diagnoses.
    ap.add_argument("--seed", type=int, default=123,
                    help="seed for the Saltelli design (NOT the ensemble's sampling seed)")
    ap.add_argument("--chunk", type=int, default=50_000)
    ap.add_argument("--targets", nargs="*", default=None,
                    help="restrict to these target names (default: all in the spec)")
    ap.add_argument("--out", required=True, help="output directory")
    a = ap.parse_args()

    gate = load_accuracy_gate(a.accuracy_report, a.no_accuracy_gate)

    from models.surrogate.tiers import load as load_surrogate      # noqa: E402
    model = load_surrogate(Path(a.surrogate))
    spec = model.spec
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)

    problem, X = saltelli_design(spec, a.n_base, a.second_order, a.seed)
    per_base = (2 * spec.n_inputs + 2) if a.second_order else (spec.n_inputs + 2)
    print(f"surrogate : {spec.name} (tier {spec.tier}, {spec.n_inputs} inputs, "
          f"{len(spec.targets)} targets)")
    print(f"gate      : {'PASSED ' + str(gate.get('summary'))[:60] if gate['gated'] else 'UNGATED'}")
    print(f"design    : Saltelli N={a.n_base}, second_order={a.second_order} "
          f"-> {len(X)} points ({per_base} per base sample)")

    pred = predict_in_chunks(model, X, a.chunk)
    Y = pred["Y"]
    if pred["in_hull_fraction"] is not None:
        print(f"coverage  : {pred['in_hull_fraction']*100:.2f}% of design points inside the "
              f"training hull")

    wanted = a.targets or spec.target_names
    rows_first: List[Dict[str, Any]] = []
    rows_second: List[Dict[str, Any]] = []
    for name in wanted:
        j = spec.target_names.index(name)
        y = Y[:, j]
        if not np.all(np.isfinite(y)):
            print(f"  {name}: SKIPPED, surrogate produced non-finite predictions")
            continue
        res = analyze(problem, y, a.second_order, a.seed)
        for i, pname in enumerate(spec.input_names):
            rows_first.append({"target": name, "parameter": pname,
                               "S1": float(res["S1"][i]), "S1_conf": float(res["S1_conf"][i]),
                               "ST": float(res["ST"][i]), "ST_conf": float(res["ST_conf"][i])})
        if a.second_order and "S2" in res:
            S2, S2c = res["S2"], res["S2_conf"]
            for i in range(spec.n_inputs):
                for k in range(i + 1, spec.n_inputs):
                    rows_second.append({"target": name,
                                        "parameter_i": spec.input_names[i],
                                        "parameter_j": spec.input_names[k],
                                        "S2": float(S2[i, k]),
                                        "S2_conf": float(S2c[i, k])})
        top = sorted(((float(res["ST"][i]), p) for i, p in enumerate(spec.input_names)),
                     reverse=True)[:5]
        print(f"  {name}: top ST -> " + ", ".join(f"{p} {v:.3f}" for v, p in top))

    with (out / "sobol_first_total.csv").open("w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=["target", "parameter", "S1", "S1_conf", "ST", "ST_conf"])
        w.writeheader(); w.writerows(rows_first)
    if rows_second:
        with (out / "sobol_second_order.csv").open("w", newline="") as fh:
            w = csv.DictWriter(fh, fieldnames=["target", "parameter_i", "parameter_j",
                                               "S2", "S2_conf"])
            w.writeheader(); w.writerows(rows_second)

    meta = {"surrogate_dir": str(a.surrogate), "spec_name": spec.name, "tier": spec.tier,
            "n_base": a.n_base, "second_order": a.second_order,
            "n_design_points": int(len(X)), "seed": a.seed,
            "in_hull_fraction": pred["in_hull_fraction"],
            "accuracy_gate": gate,
            "input_names": list(spec.input_names),
            "targets_analyzed": wanted}
    (out / "sobol_provenance.json").write_text(json.dumps(meta, indent=2))
    print(f"\nwrote {out}/sobol_first_total.csv"
          + (f", {out}/sobol_second_order.csv" if rows_second else "")
          + f", {out}/sobol_provenance.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
