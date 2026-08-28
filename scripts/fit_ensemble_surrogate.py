#!/usr/bin/env python
"""Fit, validate and save a surrogate from a completed A2MC ensemble.

This is the assembly machinery **step A4 would have used**, and the distinction matters. A4 was not
a coding task left undone: it was the QUESTION "do the existing R1/R2 ensembles suffice, or is a
purpose-built ensemble a precondition?", it answered *precondition*, and it was WITHDRAWN on
2026-07-31 (`docs/41` Phase A). Nothing from it carries forward. So this script does not "finish
A4" -- it supplies the assembly step for Phase C, once the gate opens.

**AND THE GATE IS NOT OPEN.** The surrogate build is paused until the completed ensemble contains
configurations inside the observational bands; decide that with `scripts/check_surrogate_gate.py`,
never by impression. Fitting is legitimate for a constraint or sensitivity model, which the gate
does not block; fitting an OBJECTIVE emulator to interpolate toward an unsampled target region is
exactly what it does block.

The layout this was waiting on is no longer guessed: it is `scripts/extract_flat_ensemble_targets.py`'s
Y CSV beside the round's X matrix, both verified against a real ensemble rather than assumed.

It closes the middle of the Phase-1 chain for a space-filling round:

    extract_flat_ensemble_targets.py  ->  THIS  ->  surrogate_sobol_indices.py
        Y matrix from the tapes           fit +        indices from a Saltelli
                                        validate        design through it

THE JOIN IS ASSERTED, NOT ASSUMED. Case `i` carries matrix row `i-1`, which is the materializer's
convention and the one the pre-submit validator re-derives. That is a one-line assumption capable of
silently permuting every index downstream, so this script joins on the Y CSV's own `case` column and
refuses a row whose case number falls outside the matrix, rather than zipping two files positionally
and trusting they line up.

VIABILITY COMES FROM THE `status` COLUMN, NOT FROM FINITE-Y. `S1Surrogate.fit` will fall back to
"a row is viable when every target is finite" and its own comment calls that a fallback only,
because the ensemble should carry real labels so a crash is distinguishable from merely-missing
output. The extractor already writes `status` per case; using it keeps that distinction.

WHAT THE DEFAULT SPLIT IS AND IS NOT. Without `--test-matrix`, this holds out a random subset of the
SAME ensemble. That measures interpolation within one low-discrepancy point set, and it is **not**
an independent validation ensemble: the held-out points come from the same scrambled Sobol' lattice
as the training points, so they are more predictable than genuinely new draws and the resulting R2
is optimistic. The honest number comes from an independently scrambled ensemble passed via
`--test-matrix`/`--test-y`. The report records which was used, so a later reader cannot mistake one
for the other.

Usage::

    source use_cases/<Case>/config/<case>_config.sh
    python scripts/fit_ensemble_surrogate.py \\
        --y-matrix <Y csv from extract_flat_ensemble_targets.py> \\
        --out <dir> [--learner rf] [--bakeoff]

Author: Jing Tao with Claude on Perlmutter
"""
from __future__ import annotations

import argparse
import csv
import json
import os
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import numpy as np

REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))


# =============================================================================
# Loading
# =============================================================================

def load_y_csv(path: Path) -> Tuple[List[int], List[str], np.ndarray, np.ndarray]:
    """Read the extractor's Y CSV -> (case numbers, target names, Y, viable)."""
    with Path(path).open() as fh:
        rows = list(csv.DictReader(fh))
    if not rows:
        raise SystemExit(f"{path} has no rows")
    targets = [c for c in rows[0] if c not in ("case", "status")]
    cases = [int(r["case"]) for r in rows]
    Y = np.array([[float(r[t]) if r[t] not in ("", "nan", "None") else np.nan
                   for t in targets] for r in rows], dtype=float)
    viable = np.array([r.get("status", "") == "COMPLETED" for r in rows], dtype=bool)
    return cases, targets, Y, viable


def align_to_matrix(cases: List[int], X_all: np.ndarray) -> np.ndarray:
    """Rows of X for the given case numbers, under case i <-> row i-1.

    Refuses rather than clipping. A case number past the end of the matrix means the Y file and
    the matrix describe different rounds, and silently dropping those rows would train a surrogate
    on a subset nobody chose.
    """
    idx = np.array(cases, dtype=int) - 1
    bad = [c for c, i in zip(cases, idx) if i < 0 or i >= len(X_all)]
    if bad:
        raise SystemExit(
            f"REFUSING: {len(bad)} case number(s) fall outside the {len(X_all)}-row design matrix "
            f"(first few: {bad[:5]}).\n"
            "  The Y file and the X matrix probably describe different rounds. Check\n"
            "  $A2MC_ENSEMBLE_MATRIX_FILE against the run root the Y file was extracted from.")
    return X_all[idx]


def _sha256(path: Optional[str], n: int = 16) -> str:
    """Short content hash of a file, or "" when it is absent.

    Empty means "not recorded" to ``Provenance.mismatches``, which treats it as unknown rather
    than as a mismatch -- so a missing input weakens the guard instead of blocking the fit.
    """
    import hashlib
    if not path or not Path(path).is_file():
        return ""
    h = hashlib.sha256()
    with Path(path).open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()[:n]


def _a2mc_version() -> str:
    try:
        for line in (REPO / "CLAUDE.md").read_text().splitlines()[:20]:
            if line.startswith("**Status:**") and "v2." in line:
                return line.split("(")[-1].rstrip(")").strip()
    except Exception:                                            # noqa: BLE001
        pass
    return ""


def _model_commit(model_path: Optional[str]) -> str:
    if not model_path or not Path(model_path).is_dir():
        return ""
    import subprocess
    r = subprocess.run(["git", "-C", model_path, "rev-parse", "--short", "HEAD"],
                       capture_output=True, text=True)
    return r.stdout.strip() if r.returncode == 0 else ""


def build_spec(param_list: Path, targets_yaml: Path, name: str, model: str,
               created: str, base_param_file: Optional[str],
               model_path: Optional[str]):
    """A SurrogateSpec whose input order IS the design-matrix column order.

    PROVENANCE IS STAMPED HERE, and it is not decoration. `Provenance.mismatches` only compares
    fields populated on BOTH sides, so an unstamped artifact is silently unprotected -- loading it
    later cannot detect that the parameter list, the base deck, the scoring convention or the model
    source changed underneath it. `tiers.load` warns about exactly that, which is how this gap was
    found. The scoring convention is bound as the CONTENT HASH of `targets.yaml` rather than a
    label, because this case's own history shows why: re-anchoring the targets onto Cycle A moved
    the V0 total from 0.2180 to 0.3540 without touching the model, so a surrogate trained under one
    target definition scores against a different objective than one trained under the other.
    """
    from models.surrogate.spec import (Provenance, SurrogateSpec, TargetSpec,   # noqa: E402
                                       hash_param_list)
    from scripts.create_adapter_parameter_sample import parse_pft_param_list
    from tools.pflotran_evaluate_case import targets_from_yaml

    names, lo, hi = parse_pft_param_list(param_list)
    lo = [float(v) for v in lo]
    hi = [float(v) for v in hi]
    tgts = targets_from_yaml(targets_yaml)
    tspecs = tuple(TargetSpec(name=t["name"], observed=t.get("observed")) for t in tgts)
    prov = Provenance(
        model=model,
        model_commit=_model_commit(model_path),
        param_list_hash=hash_param_list(list(names), lo, hi),
        base_param_file_hash=_sha256(base_param_file),
        scoring_convention=f"targets-sha256:{_sha256(str(targets_yaml))}",
        training_ensemble_id=name,
        a2mc_version=_a2mc_version(),
        created=created)
    return SurrogateSpec(
        name=name, use_mode="offline_search", tier="S1",
        input_names=tuple(names),
        input_lower=tuple(lo), input_upper=tuple(hi),
        targets=tspecs,
        provenance=prov,
        notes=f"fitted from {param_list.name} + {targets_yaml.name}")


# =============================================================================
# Main
# =============================================================================

def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    env = os.environ.get
    ap.add_argument("--y-matrix", required=True, help="Y CSV from extract_flat_ensemble_targets.py")
    ap.add_argument("--x-matrix", default=env("A2MC_ENSEMBLE_MATRIX_FILE"))
    ap.add_argument("--param-list", default=env("A2MC_PARAM_LIST_FILE"))
    ap.add_argument("--targets", default=env("A2MC_VALIDATION_TARGETS"))
    ap.add_argument("--model", default=env("A2MC_MODEL", "pflotran"))
    ap.add_argument("--name", default=env("A2MC_ENSEMBLE_NAME", "ensemble"))
    ap.add_argument("--learner", default="rf")
    ap.add_argument("--bakeoff", action="store_true",
                    help="compare learner families before fitting and report the ranking")
    ap.add_argument("--test-fraction", type=float, default=0.2)
    ap.add_argument("--test-matrix", default=None,
                    help="X of an INDEPENDENT validation ensemble (the honest test)")
    ap.add_argument("--test-y", default=None, help="its Y CSV")
    ap.add_argument("--seed", type=int, default=123)
    ap.add_argument("--n-boot", type=int, default=200,
                    help="test-set resamples used to ask whether the verdict is stable "
                         "(0 disables, which leaves the reviewer unable to tell a comfortable "
                         "pass from a lucky one)")
    ap.add_argument("--perturb-eps", type=float, default=0.10,
                    help="relative input jitter for the top-k shortlist stability check")
    # Provenance.created is caller-supplied on purpose, so that rebuilding the same artifact from
    # the same inputs is reproducible; stamping it from the clock would make every rebuild differ.
    # Pass the original date to reproduce an earlier artifact byte-for-byte.
    ap.add_argument("--created", default=None,
                    help="ISO date stamped into provenance (default: today). Pass the ORIGINAL "
                         "date to reproduce an earlier artifact.")
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    if a.created is None:
        import datetime
        a.created = datetime.date.today().isoformat()

    for flag, val in (("--x-matrix", a.x_matrix), ("--param-list", a.param_list),
                      ("--targets", a.targets)):
        if not val:
            raise SystemExit(f"{flag} unset (source the site config)")

    from models.surrogate.tiers import S1Surrogate                       # noqa: E402
    from models.surrogate.validate import run_acceptance                 # noqa: E402

    X_all = np.loadtxt(a.x_matrix)
    cases, targets, Y, viable = load_y_csv(Path(a.y_matrix))
    X = align_to_matrix(cases, X_all)

    spec = build_spec(Path(a.param_list), Path(a.targets), a.name, a.model,
                      created=a.created,
                      base_param_file=env("A2MC_BASE_PARAM_FILE"),
                      model_path=env("A2MC_MODEL_PATH"))
    unstamped = spec.provenance.unstamped_fields()
    if unstamped:
        print(f"WARNING: provenance fields not recorded: {unstamped} -- the artifact is "
              f"UNPROTECTED against a change in them, not verified against it")
    if list(spec.target_names) != targets:
        missing = set(spec.target_names) ^ set(targets)
        raise SystemExit(
            f"REFUSING: the Y file's columns and targets.yaml disagree (symmetric difference: "
            f"{sorted(missing)}).\n"
            "  Y column order IS the target order; a mismatch would train each target's model on\n"
            "  another target's values.")
    if X.shape[1] != spec.n_inputs:
        raise SystemExit(f"REFUSING: matrix has {X.shape[1]} columns, param list has "
                         f"{spec.n_inputs} parameters")

    print(f"ensemble  : {len(cases)} cases, {int(viable.sum())} viable "
          f"({100*viable.mean():.1f}%), {spec.n_inputs} inputs, {len(targets)} targets")

    # Split. Only viable rows can train a regressor; the classifier learns from all of them.
    rng = np.random.default_rng(a.seed)
    if a.test_matrix and a.test_y:
        Xtr, Ytr, vtr = X, Y, viable
        tc, tt, Yte, vte = load_y_csv(Path(a.test_y))
        Xte = align_to_matrix(tc, np.loadtxt(a.test_matrix))
        split_kind = "INDEPENDENT validation ensemble"
    else:
        perm = rng.permutation(len(X))
        ntest = max(1, int(round(a.test_fraction * len(X))))
        te, tr = perm[:ntest], perm[ntest:]
        Xtr, Ytr, vtr = X[tr], Y[tr], viable[tr]
        Xte, Yte, vte = X[te], Y[te], viable[te]
        split_kind = ("random hold-out from the SAME lattice -- optimistic, NOT an independent "
                      "validation ensemble")
    print(f"split     : {len(Xtr)} train / {len(Xte)} test  [{split_kind}]")

    bakeoff = None
    if a.bakeoff:
        from models.surrogate.validate import bakeoff_summary, compare_learners
        m = vtr
        bakeoff = compare_learners(spec, Xtr[m], Ytr[m])
        print(bakeoff_summary(bakeoff))

    model = S1Surrogate(spec, learner=a.learner).fit(Xtr, Ytr, viable=vtr)

    m = vte
    if m.sum() < 2:
        raise SystemExit("REFUSING: fewer than 2 viable test rows; acceptance would be vacuous")
    rep = run_acceptance(model, Xte[m], Yte[m], Y_train=Ytr[vtr], viable_test=vte[m])
    print("\n" + rep.summary())

    # ROBUSTNESS, computed once here so the human gate can read it without refitting.
    # `passed` is a hard threshold on ONE split, which cannot distinguish a comfortable
    # surrogate from one that cleared the bar by luck. Resampling the test set costs no refit.
    from models.surrogate.validate import (bootstrap_acceptance,          # noqa: E402
                                           perturbation_stability)
    boot = bootstrap_acceptance(model, Xte[m], Yte[m], Y_train=Ytr[vtr],
                                n_boot=a.n_boot, seed=a.seed)
    pert = perturbation_stability(model, Xte[m], eps=a.perturb_eps, seed=a.seed)
    rate = (boot.get("pass_rate") or {}).get("ALL")
    if rate is not None:
        print(f"\nrobustness: the verdict holds on {100*rate:.0f}% of {boot['n_boot']} "
              f"test-set resamples")
        if rep.passed and rate < 0.9:
            print("  WARNING: the headline says PASS but the verdict is NOT stable under "
                  "resampling.\n  Treat this as a marginal result; the promotion reviewer "
                  "should see this line.")

    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    model.save(out)
    payload = {"passed": bool(rep.passed),
               "robustness": {"bootstrap": boot, "perturbation": pert},
               "summary": rep.summary(),
               "verdicts": rep.verdicts,
               "per_target": rep.per_target,
               "overall": rep.overall,
               "notes": rep.notes,
               "split_kind": split_kind,
               "n_train": int(len(Xtr)), "n_test": int(len(Xte)),
               "n_viable_train": int(vtr.sum()),
               "learner": a.learner, "seed": a.seed,
               "y_matrix": str(a.y_matrix), "x_matrix": str(a.x_matrix)}
    (out / "acceptance.json").write_text(json.dumps(payload, indent=2, default=str))
    if bakeoff is not None:
        (out / "bakeoff.json").write_text(json.dumps(bakeoff, indent=2, default=str))
    print(f"\nsaved surrogate + acceptance.json to {out}")
    print("NOTE: acceptance.json is what scripts/surrogate_sobol_indices.py --accuracy-report reads.")
    return 0 if rep.passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
