#!/usr/bin/env python
"""The HUMAN GATE between a surrogate that measured well and a surrogate that may be USED.

WHY THIS IS SEPARATE FROM `run_acceptance`. That function MEASURES; this one AUTHORISES. Keeping
them apart means a surrogate can be re-measured without being re-approved, and approved without the
metrics being silently recomputed underneath the approval. Mixing measurement and decision is how a
gate becomes a formality.

WHY A HUMAN AT ALL, WHEN THE METRICS ALREADY PASS. `AcceptanceReport.passed` is necessary and not
sufficient, for three reasons the thresholds cannot see:

  1. **The thresholds test skill, not relevance.** A surrogate can rank beautifully inside a
     training region that does not contain the answer. That is the standing surrogate gate
     (`docs/41`, `scripts/check_surrogate_gate.py`) and it is about the ENSEMBLE, not the fit.
  2. **Physical plausibility is not a metric.** The project tutorial's development sequence, stage
     7, requires "held-out scenario skill AND PHYSICAL CHECKS before using the surrogate in
     calibration." Whether a predicted response surface is physically sensible is a judgement.
  3. **The split may be optimistic and still pass.** A random hold-out from the same scrambled
     Sobol' lattice measures interpolation within one point set; `acceptance.json` records which
     split produced it, and reading that is a human act.

This mirrors A2MC's other Tier-3 write gate (`tools/review_pending_knowledge.py`): the machinery
proposes, a human disposes, and the approval is recorded with WHO and ON WHAT BASIS rather than as a
bare boolean.

STATE LIVES IN `promotion.json`, beside the artifact, so it travels with it. A promotion is bound to
the acceptance report it was granted against (by content hash): re-fitting the surrogate invalidates
the approval rather than silently inheriting it.

Usage::

    python tools/promote_surrogate.py review  <surrogate_dir>
    python tools/promote_surrogate.py promote <surrogate_dir> --basis "..." --reviewed-by NAME
    python tools/promote_surrogate.py revoke  <surrogate_dir> --reason "..."
    python tools/promote_surrogate.py status  <surrogate_dir>

Author: Jing Tao with Claude on Perlmutter
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

PROMOTION_FILE = "promotion.json"
ACCEPTANCE_FILE = "acceptance.json"

OK, NOT_PROMOTED, USAGE = 0, 10, 2


def _acceptance(d: Path) -> Tuple[Dict[str, Any], str]:
    """The acceptance report and its content hash. The hash is what binds an approval to a fit."""
    p = d / ACCEPTANCE_FILE
    if not p.is_file():
        raise SystemExit(
            f"REFUSING: no {ACCEPTANCE_FILE} in {d}.\n"
            "  A surrogate cannot be promoted before it has been measured. Run\n"
            "  scripts/fit_ensemble_surrogate.py first.")
    raw = p.read_bytes()
    return json.loads(raw), hashlib.sha256(raw).hexdigest()[:16]


def _promotion(d: Path) -> Optional[Dict[str, Any]]:
    p = d / PROMOTION_FILE
    return json.loads(p.read_text()) if p.is_file() else None


def check_promotion(surrogate_dir) -> Tuple[bool, str]:
    """(is_promoted, human-readable reason). The API a consumer should call before USING a surrogate.

    Returns False rather than raising, so a caller can decide whether an unpromoted surrogate is a
    hard stop (using it to steer a search) or a note (an exploratory diagnostic).
    """
    d = Path(surrogate_dir)
    pr = _promotion(d)
    if pr is None:
        return False, ("not promoted: no promotion.json. A human must review and approve it with "
                       "tools/promote_surrogate.py promote")
    if pr.get("revoked"):
        return False, f"promotion REVOKED on {pr.get('revoked_at')}: {pr.get('revoke_reason')}"
    try:
        _, digest = _acceptance(d)
    except SystemExit:
        return False, "promoted, but acceptance.json is now missing; the approval is unbound"
    if pr.get("acceptance_sha") != digest:
        return False, (
            f"promotion is STALE: it was granted against acceptance {pr.get('acceptance_sha')} but "
            f"the report on disk is {digest}. The surrogate was re-fitted after approval; review "
            "and promote again.")
    return True, (f"promoted {pr.get('promoted_at')} by {pr.get('reviewed_by') or 'unattributed'}")


def cmd_review(d: Path, _a) -> int:
    """Print what a reviewer needs, INCLUDING what the metrics cannot tell them."""
    rep, digest = _acceptance(d)
    print(f"surrogate      : {d}")
    print(f"acceptance sha : {digest}")
    print(f"metrics passed : {rep.get('passed')}")
    print(f"split          : {rep.get('split_kind')}")
    print(f"n_train/n_test : {rep.get('n_train')} / {rep.get('n_test')}")
    print(f"learner        : {rep.get('learner')}")
    print("\n--- verdicts ---")
    for k, v in (rep.get("verdicts") or {}).items():
        print(f"  [{'ok ' if v else 'FAIL'}] {k}")
    for n in (rep.get("notes") or []):
        print(f"  note: {n}")
    print("\n--- per target ---")
    for t, dd in (rep.get("per_target") or {}).items():
        bits = [f"{k}={dd[k]:.3f}" for k in ("spearman", "r2", "coverage")
                if isinstance(dd.get(k), (int, float))]
        print(f"  {t:24s} " + "  ".join(bits))
    rb = rep.get("robustness") or {}
    boot, pert = rb.get("bootstrap") or {}, rb.get("perturbation") or {}
    if boot.get("n_boot"):
        rate = (boot.get("pass_rate") or {}).get("ALL")
        print(f"\n--- robustness ({boot['n_boot']} resamples of the {boot.get('n_test')} test rows) ---")
        if rate is not None:
            verdict = ("STABLE" if rate >= 0.9 else
                       "MARGINAL" if rate >= 0.5 else "NOT STABLE")
            print(f"  the verdict holds on {100*rate:.0f}% of resamples   [{verdict}]")
            if rep.get("passed") and rate < 0.9:
                print("  ** the headline says PASS but it does not survive resampling. A pass this\n"
                      "     close to the bar is a coin flip on which split you happened to draw. **")
        for k, q in sorted((boot.get("quantiles") or {}).items()):
            print(f"    {k:24s} p05 {q['p05']:.3f}   p50 {q['p50']:.3f}   p95 {q['p95']:.3f}")
    if pert.get("top_k_overlap"):
        print(f"\n  top-{pert.get('k')} shortlist overlap under {100*pert.get('eps', 0):.0f}% input jitter:")
        for t, v in sorted(pert["top_k_overlap"].items()):
            print(f"    {t:24s} {v:.2f}")
        print("    (LOW overlap with a HIGH rho means the top candidates are effectively TIED,\n"
              "     so the shortlist's ORDER is not meaningful even though the fit is good.\n"
              "     That is a property of the problem as much as of the surrogate.)")

    print("""
--- WHAT THESE NUMBERS DO NOT TELL YOU (the reason this gate is human) ---
  1. RELEVANCE, not skill. A surrogate can rank well inside a region that does not contain the
     answer. Check the standing gate separately: scripts/check_surrogate_gate.py
  2. PHYSICAL PLAUSIBILITY. Does the predicted response behave sensibly in the directions you
     understand? No threshold above asks this.
  3. WHAT THE SPLIT MEANS. A hold-out drawn from the SAME scrambled Sobol lattice measures
     interpolation within one point set and reads optimistically. The `split` line says which
     you have.

To approve:
  python tools/promote_surrogate.py promote {d} --basis "..." --reviewed-by NAME""".format(d=d))
    return OK


def cmd_promote(d: Path, a) -> int:
    rep, digest = _acceptance(d)
    if not rep.get("passed") and not a.force:
        raise SystemExit(
            "REFUSING: acceptance.json records passed=false.\n"
            f"  {str(rep.get('summary', ''))[:300]}\n"
            "  Fix the surrogate rather than approving around it. --force exists for a deliberate\n"
            "  exception and stamps the promotion as forced.")
    if not (a.basis or "").strip():
        raise SystemExit(
            "REFUSING: --basis is required and must say what was checked BEYOND the metrics.\n"
            "  A promotion with no stated basis is a rubber stamp, which is the failure this gate\n"
            "  exists to prevent. Name the physical checks you made and the split you accepted.")
    pr = {"promoted": True,
          "promoted_at": datetime.now().isoformat(timespec="seconds"),
          "reviewed_by": a.reviewed_by or "",
          "basis": a.basis.strip(),
          "acceptance_sha": digest,
          "metrics_passed": bool(rep.get("passed")),
          "forced": bool(a.force),
          "use_mode": (rep.get("overall") or {}).get("use_mode")}
    (d / PROMOTION_FILE).write_text(json.dumps(pr, indent=2))
    print(f"PROMOTED {d}")
    print(f"  bound to acceptance {digest}; re-fitting invalidates this approval")
    if a.force:
        print("  WARNING: forced over a failing acceptance report; the stamp records that")
    return OK


def cmd_revoke(d: Path, a) -> int:
    pr = _promotion(d)
    if pr is None:
        raise SystemExit(f"REFUSING: {d} has no {PROMOTION_FILE} to revoke.")
    if not (a.reason or "").strip():
        raise SystemExit("REFUSING: --reason is required; a revocation with no reason is unreadable.")
    pr.update({"revoked": True,
               "revoked_at": datetime.now().isoformat(timespec="seconds"),
               "revoke_reason": a.reason.strip()})
    (d / PROMOTION_FILE).write_text(json.dumps(pr, indent=2))
    print(f"REVOKED {d}: {a.reason.strip()}")
    return OK


def cmd_status(d: Path, _a) -> int:
    ok, why = check_promotion(d)
    print(f"{'PROMOTED' if ok else 'NOT PROMOTED'}: {why}")
    return OK if ok else NOT_PROMOTED


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    for name, help_ in (("review", "print the report plus what it cannot tell you"),
                        ("promote", "record human approval"),
                        ("revoke", "withdraw a previous approval"),
                        ("status", "is this surrogate usable?")):
        s = sub.add_parser(name, help=help_)
        s.add_argument("surrogate_dir")
        if name == "promote":
            s.add_argument("--basis", required=True,
                           help="what you checked BEYOND the metrics (required)")
            s.add_argument("--reviewed-by", default="")
            s.add_argument("--force", action="store_true",
                           help="approve despite a failing acceptance report; stamped as forced")
        if name == "revoke":
            s.add_argument("--reason", required=True)
    a = ap.parse_args()

    d = Path(a.surrogate_dir)
    if not d.is_dir():
        raise SystemExit(f"REFUSING: {d} is not a directory")
    return {"review": cmd_review, "promote": cmd_promote,
            "revoke": cmd_revoke, "status": cmd_status}[a.cmd](d, a)


if __name__ == "__main__":
    raise SystemExit(main())
