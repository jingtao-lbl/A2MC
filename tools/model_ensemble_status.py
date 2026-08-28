#!/usr/bin/env python
"""Ensemble status monitor for a model's standalone-run ensemble.

The model-generic analog of the FATES-shaped `tools/diagnose_ensemble_status.py`
(which is CIME/`sacct`-array shaped). Scans a run root of per-case directories
produced by `<Backend>.create_case` and reports, per case, the combination of the
**Slurm job state** (from `job_id.txt` + `sacct`) and the **model success check**
(`spec` backend's `check_case_status`, which for EcoSIM requires the FINAL RESTART
stamped `<final year + 1>-01-01`, NOT merely an `*.h0.*.nc` tape -- EcoSIM opens that
tape at initialisation, so its existence means the run STARTED and a truncated run
leaves the same evidence as a complete one). Reconciles the two into a single status
so a "Slurm COMPLETED but the model did not finish" (a model failure -- the EcoSIM
IEBTYP version mismatch, or a wall-clock kill part-way) is not mistaken for success. Additive (docs/38): a NEW file dispatched through the model backend;
the FATES ensemble tool is untouched.

Statuses: PENDING | RUNNING | COMPLETED | FAILED | UNKNOWN.

For a job ARRAY or a node task-farm no per-case `job_id.txt` exists, so pass
`--ensemble-jobs` to restore the scheduler-reconciliation leg -- otherwise a case that died
part-way is indistinguishable from one still executing and is reported RUNNING indefinitely.

Usage:
    python tools/model_ensemble_status.py --model ecosim --run-root <dir> [--watch 60] [--failed]
    python tools/model_ensemble_status.py --model ecosim --run-root <dir> --ensemble-jobs 123,456

Author: Jing Tao with Claude
"""
from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
_TERMINAL = {"COMPLETED", "FAILED", "CANCELLED", "TIMEOUT", "NODE_FAIL", "OUT_OF_MEMORY", "PREEMPTED"}
_FAIL_PAT = re.compile(r"ENDRUN|Program aborted|srun: error|Variable not found|IO ERROR|Killed|OOM|Segmentation", re.I)


def _sacct_state(job_id: str) -> str | None:
    if not job_id or not job_id[:1].isdigit():
        return None  # dry-run / synthetic id
    try:
        out = subprocess.run(["sacct", "-j", job_id, "-n", "-P", "-o", "State"],
                             capture_output=True, text=True, timeout=30).stdout
    except Exception:
        return None
    # first line = the top-level job state (drop .batch/.extern steps)
    for line in out.splitlines():
        s = line.strip().split()[0] if line.strip() else ""
        if s:
            return s.split("+")[0]  # e.g. "CANCELLED+" -> "CANCELLED"
    return None


def ensemble_jobs_terminal(job_ids: list[str]) -> tuple[bool, dict[str, str]]:
    """Are ALL the named scheduler jobs finished attempting?

    Returns (all_terminal, {job: summary-state}). A job whose state cannot be read counts as
    NOT terminal -- an unreadable scheduler is not evidence that work has stopped.

    Why this exists: `check_case_status` cannot tell "still running" from "died part-way" from
    inside the case dir (both leave a started-but-incomplete tree), so it returns RUNNING and
    documents that this tool reconciles it against the scheduler. That reconciliation ran off
    each case's `job_id.txt` -- and a job ARRAY or a node task-farm writes none, so for R3's
    14,849 cases the leg was entirely inert and 1,129 dead cases were published as RUNNING
    against two arrays that were provably terminal. Naming the ensemble's jobs restores the
    reconciliation for exactly those layouts.
    """
    states: dict[str, str] = {}
    for j in job_ids:
        try:
            out = subprocess.run(["sacct", "-j", j, "--format=State", "-n", "-X", "-P"],
                                 capture_output=True, text=True, timeout=60).stdout
        except Exception:
            states[j] = "UNREADABLE"
            continue
        seen = {l.strip().split("+")[0] for l in out.splitlines() if l.strip()}
        if not seen:
            states[j] = "NO-RECORD"
        elif seen <= _TERMINAL:
            states[j] = "terminal(" + ",".join(sorted(seen)) + ")"
        else:
            states[j] = "ACTIVE(" + ",".join(sorted(seen - _TERMINAL)) + ")"
    all_terminal = bool(states) and all(v.startswith("terminal(") for v in states.values())
    return all_terminal, states


def _fail_reason(case_dir: Path) -> str:
    for pat in ("slurm_*.err", "slurm_*.out"):
        for f in sorted(case_dir.glob(pat)):
            try:
                for line in f.read_text(errors="ignore").splitlines():
                    if _FAIL_PAT.search(line):
                        return line.strip()[:160]
            except OSError:
                continue
    return ""


_CASE_IDX = re.compile(r"(\d+)$")


def read_cases_file(path) -> set[int]:
    """Case indices from a file of one integer per line (blank lines and `#` comments ignored).

    `--case-range` is CONTIGUOUS, and the population you most want to watch usually is not: a
    relaunch targets the cases that failed, which are scattered. Measured 2026-08-21 on the R3
    relaunch -- 1,129 non-contiguous ids spanning 77..14810, so the narrowest possible RANGE still
    forces a scan of 14,734 dirs, 13x the work, and the refresh hook exceeded its 900 s budget and
    was killed. An explicit id list is the frozen artifact the relaunch already writes
    (`case_ids.txt`), so pointing at it costs nothing and scans exactly what matters.
    """
    ids = set()
    with open(path) as fh:
        for line in fh:
            line = line.split("#", 1)[0].strip()
            if not line:
                continue
            ids.add(int(line))
    if not ids:
        raise ValueError(f"no case ids found in {path}")
    return ids


def parse_case_range(spec: str):
    """Parse "LO-HI" (inclusive) into a (lo, hi) tuple.

    A chunked array round submits a SLICE of a materialized ensemble -- R3's prefix is 4,989
    of 59,393 case dirs -- and scanning the whole root to report on that slice is what made
    this tool unusable as a watcher refresh hook (>2 min, killed).
    """
    m = re.fullmatch(r"\s*(\d+)\s*-\s*(\d+)\s*", spec)
    if not m:
        raise ValueError(f"--case-range must look like LO-HI (inclusive), got {spec!r}")
    lo, hi = int(m.group(1)), int(m.group(2))
    if lo > hi:
        raise ValueError(f"--case-range LO must not exceed HI, got {lo}-{hi}")
    return lo, hi


def case_index(name: str):
    """Trailing integer of a case dir name (BioCON_case4988 -> 4988); None if absent."""
    m = _CASE_IDX.search(name)
    return int(m.group(1)) if m else None


def scan(model: str, run_root: Path, case_range=None, jobs_terminal: bool = False,
         case_ids=None):
    import importlib
    sys.path.insert(0, str(REPO))
    from models import registry
    importlib.import_module(f"models.{model}")
    backend = registry.get_model(model)

    # os.scandir (not iterdir) so the is_dir() test uses the cached d_type instead of a stat,
    # and the case_range filter runs on the NAME -- before any filesystem call. On a 59,393-dir
    # root this is what makes a 4,989-case slice cheap enough to run as a watcher refresh hook.
    cands = []
    with os.scandir(run_root) as it:
        for e in it:
            if not e.is_dir():
                continue
            if case_range is not None or case_ids is not None:
                idx = case_index(e.name)
                if idx is None:
                    continue
                if case_range is not None and not (case_range[0] <= idx <= case_range[1]):
                    continue
                if case_ids is not None and idx not in case_ids:
                    continue
            cands.append(Path(e.path))
    cases = sorted(d for d in cands
                   if (d / "submit.sh").exists() or (d / "job_id.txt").exists())
    rows = []
    for cd in cases:
        jid = (cd / "job_id.txt").read_text().strip() if (cd / "job_id.txt").exists() else ""
        slurm = _sacct_state(jid)
        try:
            model_status = backend.check_case_status(cd)  # model success check (tape-based)
        except Exception:
            model_status = "UNKNOWN"
        # Reconcile slurm state with the model output check.
        if slurm in (None, ""):  # no per-case scheduler info
            if jobs_terminal and model_status == "RUNNING":
                # The ensemble's own jobs are all terminal, so nothing is executing: a case that
                # started and never reached COMPLETED did not finish. Only reachable when the
                # caller named those jobs and they were VERIFIED terminal, so this cannot
                # silently reclassify a live run.
                status = "FAILED"
            else:
                status = model_status
        elif slurm not in _TERMINAL:
            status = "RUNNING" if slurm == "RUNNING" else "PENDING"
        else:  # scheduler finished
            status = "COMPLETED" if model_status == "COMPLETED" else "FAILED"
        reason = _fail_reason(cd) if status == "FAILED" else ""
        rows.append((cd.name, jid, slurm or "-", status, reason))
    return rows


def report(rows, show_failed_only=False):
    from collections import Counter
    counts = Counter(r[3] for r in rows)
    print(f"cases: {len(rows)} | " + " ".join(f"{k}={v}" for k, v in sorted(counts.items())))
    for name, jid, slurm, status, reason in rows:
        if show_failed_only and status != "FAILED":
            continue
        line = f"  {status:10} {name:20} job={jid:10} slurm={slurm}"
        if reason:
            line += f"\n      ↳ {reason}"
        print(line)
    return counts


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--model", required=True, help="onboarded model name (e.g. ecosim)")
    ap.add_argument("--run-root", required=True, help="ensemble run root (per-case subdirs)")
    ap.add_argument("--watch", type=int, default=0, metavar="SEC",
                    help="poll every SEC seconds until all cases are terminal (0 = one-shot)")
    ap.add_argument("--failed", action="store_true", help="list only FAILED cases")
    ap.add_argument("--ensemble-jobs", metavar="ID[,ID...]",
                    help="the scheduler job(s) that ran this ensemble. A job ARRAY or a node "
                         "task-farm writes no per-case job_id.txt, so without this the "
                         "scheduler-reconciliation leg is inert and a case that died part-way "
                         "is reported RUNNING forever. Their states are READ, not assumed: "
                         "reclassification happens only if every named job is terminal.")
    ap.add_argument("--cases-file", metavar="PATH",
                    help="scan ONLY the case indices listed in this file (one per line). Use for a "
                         "scattered population such as a relaunch, where the narrowest enclosing "
                         "--case-range still scans an order of magnitude too much.")
    ap.add_argument("--case-range", metavar="LO-HI",
                    help="restrict the scan to case dirs whose trailing index is in [LO,HI] "
                         "(inclusive) -- for a chunked array that runs a slice of the ensemble")
    args = ap.parse_args()

    try:
        case_range = parse_case_range(args.case_range) if args.case_range else None
        case_ids = read_cases_file(args.cases_file) if args.cases_file else None
    except (ValueError, OSError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    if case_ids is not None:
        print(f"scanning {len(case_ids)} listed case(s) from {args.cases_file}")

    run_root = Path(args.run_root)
    if not run_root.is_dir():
        print(f"ERROR: run root not found: {run_root}", file=sys.stderr)
        return 1

    jobs = [j.strip() for j in (args.ensemble_jobs or "").split(",") if j.strip()]
    while True:
        jobs_terminal = False
        if jobs:
            jobs_terminal, states = ensemble_jobs_terminal(jobs)
            print("ensemble jobs: " + "  ".join(f"{j}={s}" for j, s in states.items())
                  + ("  -> all terminal; started-but-incomplete cases are FAILED, not RUNNING"
                     if jobs_terminal else "  -> some still active; incomplete cases stay RUNNING"))
        rows = scan(args.model, run_root, case_range, jobs_terminal, case_ids)
        counts = report(rows, args.failed)
        pending = counts.get("PENDING", 0) + counts.get("RUNNING", 0)
        if not args.watch or pending == 0:
            break
        print(f"  … {pending} still active; re-checking in {args.watch}s", flush=True)
        time.sleep(args.watch)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
