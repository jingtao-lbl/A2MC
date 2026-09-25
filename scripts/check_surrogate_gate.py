#!/usr/bin/env python
"""Decide the surrogate gate's CONDITION 2 on a completed ensemble, by a bar fixed in advance.

THE GATE (`docs/41`). A surrogate of the calibration objective is worth building only when BOTH
hold:

  1. the round is sampled space-filling (Sobol' sequence / LHS), AND
  2. **the completed ensemble contains configurations inside the observational bands.**

The gate is explicit that a space-filling design which still MISSES the targets does not open the
build, and states why: a surrogate is an interpolant of its training ensemble, so an ensemble that
never reaches the target region carries no information about the only region worth searching.

WHY THIS IS A SCRIPT AND NOT A JUDGEMENT MADE LATER. Condition 2 is a property of data that does
not exist yet. Deciding "was it close enough" after seeing the numbers is how a gate becomes a
rationalisation. So the bar is written down, committed, and executed unchanged.

THE BAR
-------
**In band, per target:** ``|sim/obs - 1| <= uncertainty_i``, using each target's OWN relative
``uncertainty`` from ``targets.yaml``, NOT the global ``cost_config`` tolerance. A target whose
``observed: 1.0`` is a SENTINEL and whose reduce returns ``1 + NRMSE`` reduces under the same formula
to ``NRMSE <= uncertainty`` -- one rule covers all targets and no special case is needed.

**GATE OPENS** when at least one completed case has **every scored target in band**
simultaneously. That is the gate's literal reading: a configuration inside the bands.

**GATE STAYS CLOSED** otherwise -- and that is a RESULT, not a failure. Exit code 10 says so
distinctly, so a caller can tell "answered no" from "broke" (exit 1/2).

WHAT IT REPORTS WHEN THE GATE STAYS CLOSED, which is the actionable half:

  * ``k_max``   -- the most targets any single case got in band at once. Distinguishes "close on a
                  broad front" from "no case ever coherent".
  * per-target in-band counts -- which targets the box can and cannot reach.
  * **UNREACHABLE targets**: in band in ZERO cases. Over a space-filling design this is strong
    evidence the target is unreachable ANYWHERE in the current parameter box, which is a
    box/model finding rather than a calibration one, and is what routes work to widening the box
    or to model development.

Usage::

    source use_cases/<Case>/config/<case>_config.sh
    python scripts/check_surrogate_gate.py --y-matrix <Y csv> [--json out.json]

Generic: every model-specific fact arrives through ``targets.yaml`` and the Y matrix.

Author: Jing Tao with Claude on Perlmutter
"""
from __future__ import annotations

import argparse
import csv
import json
import os
import sys
from pathlib import Path
from typing import Any, Dict, List

import numpy as np

REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

GATE_OPEN, GATE_CLOSED, USAGE_ERROR = 0, 10, 2


def load_bands(targets_yaml: Path) -> Dict[str, Dict[str, float]]:
    """{target: {observed, uncertainty}} -- each observation's OWN relative uncertainty."""
    import yaml
    d = yaml.safe_load(Path(targets_yaml).read_text())
    out: Dict[str, Dict[str, float]] = {}
    missing: List[str] = []
    zero_obs: List[str] = []
    for name, t in (d.get("targets") or {}).items():
        obs, unc = t.get("observed"), t.get("uncertainty")
        if obs is None or unc is None:
            missing.append(name)
            continue
        if float(obs) == 0.0:
            # A RELATIVE band is undefined at zero, and the in-band test below divides by this
            # value. Refusing here names the target; leaving it produced a bare ZeroDivisionError
            # from the middle of the scoring loop, which reads as a broken script rather than as
            # a target that cannot be banded this way.
            zero_obs.append(name)
            continue
        out[name] = {"observed": float(obs), "uncertainty": float(unc)}
    if zero_obs:
        raise SystemExit(
            f"REFUSING: {len(zero_obs)} target(s) declare observed: 0 and are scored with a "
            f"RELATIVE band: {zero_obs}\n"
            f"  |sim/observed - 1| is undefined at zero. Give these targets an absolute "
            f"tolerance, or a non-zero reference, before running the gate.")
    if missing:
        # Refuse rather than silently scoring a subset: a gate evaluated on 9 of 11 targets is
        # not the gate, and would read as a pass on an easier question.
        raise SystemExit(
            f"REFUSING: {len(missing)} target(s) lack observed/uncertainty and cannot be banded: "
            f"{missing}\n  The gate must be evaluated on EVERY scored target or it answers an "
            f"easier question than the one asked.")
    return out


def load_y(path: Path):
    with Path(path).open() as fh:
        rows = list(csv.DictReader(fh))
    if not rows:
        raise SystemExit(f"{path} has no rows")
    targets = [c for c in rows[0] if c not in ("case", "status")]
    return rows, targets


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    env = os.environ.get
    ap.add_argument("--y-matrix", required=True,
                    help="Y CSV from scripts/extract_flat_ensemble_targets.py")
    ap.add_argument("--targets", default=env("A2MC_VALIDATION_TARGETS"))
    ap.add_argument("--json", default=None, help="also write the verdict as JSON")
    a = ap.parse_args()
    if not a.targets:
        raise SystemExit("--targets unset (source the site config)")

    bands = load_bands(Path(a.targets))
    rows, ycols = load_y(Path(a.y_matrix))

    extra = set(ycols) - set(bands)
    absent = set(bands) - set(ycols)
    if absent:
        raise SystemExit(
            f"REFUSING: targets.yaml declares {sorted(absent)} but the Y matrix has no such "
            f"column(s).\n  Evaluating the gate without them would answer an easier question.")
    if extra:
        print(f"note: Y columns not in targets.yaml, ignored: {sorted(extra)}")

    names = [t for t in ycols if t in bands]
    completed = [r for r in rows if r.get("status") == "COMPLETED"]
    print(f"ensemble  : {len(rows)} rows, {len(completed)} COMPLETED, {len(names)} scored targets")
    if not completed:
        raise SystemExit("REFUSING: no COMPLETED cases; the gate is not yet evaluable.")

    inband = np.zeros((len(completed), len(names)), dtype=bool)
    for i, r in enumerate(completed):
        for j, t in enumerate(names):
            v = r.get(t)
            try:
                sim = float(v)
            except (TypeError, ValueError):
                continue                      # NaN / blank stays False
            if not np.isfinite(sim):
                continue
            b = bands[t]
            inband[i, j] = abs(sim / b["observed"] - 1.0) <= b["uncertainty"]

    per_case = inband.sum(axis=1)
    per_target = inband.sum(axis=0)
    n_all = int((per_case == len(names)).sum())
    k_max = int(per_case.max())
    unreachable = [names[j] for j in range(len(names)) if per_target[j] == 0]

    print(f"\nBAR: a case is 'inside the bands' when ALL {len(names)} targets satisfy "
          f"|sim/obs - 1| <= that target's own uncertainty.\n")
    print(f"  cases with ALL targets in band : {n_all}")
    print(f"  best single case (k_max)       : {k_max} of {len(names)} targets in band")
    print("\n  per-target reachability (cases in band, of "
          f"{len(completed)} completed):")
    for j, t in enumerate(names):
        n = int(per_target[j])
        flag = "  <<< UNREACHABLE IN THIS BOX" if n == 0 else ""
        print(f"    {t:18s} {n:6d}  ({100*n/len(completed):5.1f}%)  "
              f"band +/-{bands[t]['uncertainty']:.2f}{flag}")

    opened = n_all >= 1
    print()
    if opened:
        print(f"VERDICT: GATE OPENS -- {n_all} case(s) sit inside every band. The ensemble carries "
              f"information about the target region, so the surrogate build may proceed.")
    else:
        print("VERDICT: GATE STAYS CLOSED -- no completed case is inside every band.")
        print("  This is a RESULT, not a failure. Per the gate's reasoning, a surrogate fitted "
              "here would\n  interpolate a region that does not contain the answer.")
        if unreachable:
            print(f"  UNREACHABLE targets ({len(unreachable)}): {unreachable}")
            print("  Over a space-filling design, a target in band in ZERO cases is evidence it is "
                  "unreachable\n  ANYWHERE in the current box -- a box/model finding, not a "
                  "calibration one.")
        else:
            print(f"  Every target is individually reachable (best case got {k_max}/{len(names)}), "
                  "so the miss is\n  JOINT: no single configuration satisfies them together. That "
                  "points at a trade-off\n  between targets rather than at an unreachable one.")

    verdict = {"gate_open": opened, "n_all_in_band": n_all, "k_max": k_max,
               "n_targets": len(names), "n_completed": len(completed),
               "per_target_in_band": {t: int(per_target[j]) for j, t in enumerate(names)},
               "unreachable_targets": unreachable,
               "bar": "all targets |sim/obs - 1| <= per-target uncertainty",
               "y_matrix": str(a.y_matrix), "targets_file": str(a.targets)}
    if a.json:
        Path(a.json).write_text(json.dumps(verdict, indent=2))
        print(f"\nwrote {a.json}")
    return GATE_OPEN if opened else GATE_CLOSED


if __name__ == "__main__":
    raise SystemExit(main())
