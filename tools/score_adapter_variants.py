#!/usr/bin/env python3
"""Score a set of adapter-model experiment variants against a case's validation targets.

Generalized from `score_corner_variants.py`, written for the EcoSIM BioCON R3 c01 corner experiment
and promoted here when the c02 cycle needed the same thing an hour later. Copy-then-generalize per
`calibration-discipline` item 12: the original hardcoded its run root, its variant list and its
reference values, all of which are arguments now.

WHAT MAKES IT WORTH REUSING is not the scoring, which is one call to
`tools.model_evaluate_case.evaluate_model_case`. It is the two refusals around it:

  1. IT WILL NOT REPORT ANYTHING until it reproduces a KNOWN reading. Give it a reference case whose
     scored values are already established (`--reference CASE --expect plant_C=255.2,NPP=429.5`) and
     it rescores that case first. If the numbers disagree, the instrument disagrees with the round
     that produced them, every variant reading below it is uninterpretable, and it stops. Same
     reasoning as a V0 gate one level down: prove the instrument reproduces a known reading before
     trusting a new one. On its first run this caught the return tuple being unpacked in the wrong
     order -- `evaluate_model_case` returns `(cost, errors, simulated)`, errors SECOND, and its
     annotation `Tuple[float, Dict, Dict]` says nothing about order. Read the other way it reported
     relative errors wearing the units of values.

  2. IT WILL NOT RUN without the validation window's start year in the environment. EcoSIM runs a
     REAL Gregorian calendar, so a reducer that falls back to a fixed 365 records per year slips a
     day per leap year and produces numbers that are quietly wrong rather than obviously wrong.

    python3 tools/score_adapter_variants.py \\
        --run-root <dir> --variants V0=case_a,V1=case_b \\
        --targets use_cases/<Site>/validation/targets.yaml \\
        --reference <dir>/<case> --expect plant_C=255.2,NPP=429.5 \\
        [--bar plant_C:255.2] [--model ecosim] [--tol 0.02] [--out scores.csv]

EXIT 0 scored / 1 nothing scorable / 2 the self-check failed (nothing is reported).

Author: Jing Tao with Claude
"""
from __future__ import annotations

import argparse
import csv
import os
import pathlib
import sys

import yaml

REPO = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

from tools.model_evaluate_case import evaluate_model_case          # noqa: E402

#: A finished run is identified by its model's own completion artifact, not by a scheduler state:
#: `sacct COMPLETED` is reported for a job whose model aborted cleanly on a balance check, and for
#: one that crashed inside a script that kept going. Both leave no final restart.
DEFAULT_DONE_GLOB = "*.r.2023-*.nc"

#: The reducers need the window's start year; without it they assume 365 records/year.
REQUIRED_ENV = ("A2MC_VALIDATION_START_YEAR",)


def load_targets(path: pathlib.Path) -> list[dict]:
    d = yaml.safe_load(path.read_text())
    ts = d.get("targets", d)
    if isinstance(ts, dict):
        return [dict(v, name=k) for k, v in ts.items() if isinstance(v, dict)]
    return ts


def score(case: pathlib.Path, targets: list[dict], model: str, done_glob: str):
    """-> ((cost, errors, simulated), None) or (None, reason). The reason is never swallowed."""
    if not case.is_dir():
        return None, "case dir absent"
    if not list(case.glob(done_glob)):
        return None, "no completion artifact (failed, aborted, or still running)"
    try:
        return evaluate_model_case(case, targets, model=model), None
    except Exception as e:
        return None, f"scoring RAISED {type(e).__name__}: {e}"


def parse_pairs(s: str) -> dict:
    out = {}
    for part in (s or "").split(","):
        if not part.strip():
            continue
        k, _, v = part.partition("=")
        out[k.strip()] = v.strip()
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--run-root", required=True)
    ap.add_argument("--variants", required=True,
                    help="comma-separated LABEL=casedir pairs, e.g. 'V0=BioCON_c01v1,V1=BioCON_c01v2'")
    ap.add_argument("--targets", required=True)
    ap.add_argument("--model", default=os.environ.get("A2MC_MODEL", "ecosim"))
    ap.add_argument("--reference", help="a case whose scored values are already KNOWN")
    ap.add_argument("--expect", help="the known values, e.g. 'plant_C=255.2,NPP=429.5'")
    ap.add_argument("--tol", type=float, default=0.02, help="fractional tolerance for the self-check")
    ap.add_argument("--bar", help="TARGET:VALUE a variant must exceed, e.g. 'plant_C:455.5'")
    ap.add_argument("--done-glob", default=DEFAULT_DONE_GLOB)
    ap.add_argument("--out", default="variant_scores.csv")
    a = ap.parse_args()

    missing = [v for v in REQUIRED_ENV if not os.environ.get(v)]
    if missing:
        print(f"  ✘ unset: {missing}. Source the machine, site and round configs first. Without the")
        print("    start year the reducers assume 365 records/year, and a real Gregorian calendar")
        print("    slips a day per leap year. Refusing to score.")
        return 2

    targets = load_targets(pathlib.Path(a.targets))
    root = pathlib.Path(a.run_root)
    print(f"  targets: {[t['name'] for t in targets]}   model: {a.model}\n")

    if a.reference and a.expect:
        print(f"  SELF-CHECK — rescoring {pathlib.Path(a.reference).name} against its known reading")
        ref, why = score(pathlib.Path(a.reference), targets, a.model, a.done_glob)
        if ref is None:
            print(f"  ✘ cannot self-check: {why}. STOPPING — no variant reading is interpretable")
            print("    until the instrument is shown to reproduce a known one.")
            return 2
        _, _, vals = ref
        ok = True
        for k, want in parse_pairs(a.expect).items():
            got, want = vals.get(k), float(want)
            if got is None:
                print(f"    ✘ {k}: not produced"); ok = False; continue
            rel = abs(got - want) / abs(want) if want else abs(got)
            print(f"    {'ok' if rel <= a.tol else 'MISMATCH':8s} {k:10s} got {got:10.2f}  "
                  f"known {want:10.2f}  rel {rel:.4f}")
            ok &= rel <= a.tol
        if not ok:
            print("\n  ✘ the scorer does not reproduce the known numbers. Every variant reading below")
            print("    would be uninterpretable. STOPPING rather than reporting them.")
            return 2
        print("  ✔ self-check passed — the instrument reproduces a known reading\n")
    else:
        print("  [warn] no --reference/--expect given: the scores below are UNVALIDATED against any")
        print("         known reading. Supply them when one exists.\n")

    bar_t, bar_v = (a.bar.split(":", 1) if a.bar and ":" in a.bar else (None, None))
    bar_v = float(bar_v) if bar_v else None

    names = [t["name"] for t in targets]
    rows = []
    print("  " + f"{'var':6s} {'case':22s} " + " ".join(f"{n:>9s}" for n in names) + "   verdict")
    for pair in a.variants.split(","):
        lab, _, case = pair.partition("=")
        lab, case = lab.strip(), case.strip()
        r, why = score(root / case, targets, a.model, a.done_glob)
        if r is None:
            print(f"  {lab:6s} {case:22s} " + " ".join(f"{'-':>9s}" for _ in names) + f"   {why}")
            rows.append({"variant": lab, "case": case, "status": why})
            continue
        _, errs, vals = r
        cells = " ".join(f"{vals.get(n, float('nan')):9.2f}" for n in names)
        verdict = "scored"
        if bar_t and vals.get(bar_t) is not None:
            verdict = f"{bar_t} {'ABOVE' if vals[bar_t] > bar_v else 'below'} {bar_v:g}"
        print(f"  {lab:6s} {case:22s} {cells}   {verdict}")
        row = {"variant": lab, "case": case, "status": "complete"}
        row.update({n: vals.get(n) for n in names})
        row.update({f"relerr_{n}": errs.get(n) for n in names})
        rows.append(row)

    if rows:
        out = pathlib.Path(a.out)
        keys = sorted({k for r in rows for k in r})
        with open(out, "w", newline="") as fh:
            w = csv.DictWriter(fh, fieldnames=keys); w.writeheader(); w.writerows(rows)
        print(f"\n  wrote {out}")
    return 0 if any(r.get("status") == "complete" for r in rows) else 1


if __name__ == "__main__":
    raise SystemExit(main())
