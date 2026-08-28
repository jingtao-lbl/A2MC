#!/usr/bin/env python
"""Extract the scored-target Y-matrix for a FLAT `<prefix>case{N}` adapter ensemble.

The sibling of `extract_crossed_ensemble_targets.py`, which handles the CROSSED `TR{N}MG{M}`
layout and cannot read a flat one. A Morris/Sobol/LHS ensemble materialized by
`scripts/materialize_adapter_ensemble.py` is flat: case `i` carries matrix row `i-1`.

Model-dispatched, not model-specific: every reduction goes through
`tools.model_evaluate_case.evaluate_model_case`, so a target is scored by the same verified code
path the single-case evaluator uses. Nothing is re-implemented here.

FAILED CASES ARE KEPT AS LABELLED ROWS, not dropped. A row carries `status` and NaN targets when
the case did not finish, because *which* configurations fail is itself a result -- and for a
Saltelli design the position of a hole decides whether the estimator is usable at all.

Completion is decided by the backend's `check_case_status`, i.e. by the model's end-of-run
artifact. It is NOT decided by the exit code: EcoSIM's mass-balance ENDRUN exits 0, so a scheduler
that reports COMPLETED is not evidence the science finished (see dev log 20260820d).

WHY CHUNKS RUN IN FRESH SUBPROCESSES (--chunk-size, ON by default). The prior art this script
generalizes (use_cases/EcoSIM_BioCON/memory/phase_results/20260811g_morris_fs_soilbgc_screen/
extract_morris_results.py) chunks cases 10 at a time into separate processes, because scoring 241
cases in ONE long-running interpreter made some cases with genuinely valid, complete output tapes
spuriously raise 'NoneType is not iterable' -- non-reproducible when re-evaluated in isolation.
This script was first written without that isolation and would have scored 14,848 cases in one
interpreter, 60x that scale. The consequence is specific and bad: a spurious failure is written as
a FAILED ROW, and for a Saltelli design a hole's position decides whether the estimator is usable,
so a leak would manufacture fake holes that get blamed on the model. The leak's ONSET was never
bisected, so the default chunk (50) sits well below the only measurement rather than being tuned.
`--chunk-size 0` disables isolation; do not, except for a handful of cases. See dev log 20260821f.

DO NOT RUN THIS WHILE THE ENSEMBLE IS STILL WRITING AT SCALE. Scoring reads a ~94 MB history tape
per case; with thousands of cases writing hourly output to the same parallel filesystem the reader
lands in uninterruptible I/O wait (process state `D`) and makes no progress, while stealing
bandwidth from the runs. Measured 2026-08-20: 1.21 s per case on a quiet filesystem, versus zero
rows in 70 s against ~2000 concurrently-writing cases. Extract after the ensemble drains, or
chunk it over ranges whose cases are already finished.

Usage (source the machine + round config first):
    python scripts/extract_flat_ensemble_targets.py --first 0 --last 14848 --out Y.csv
    python scripts/extract_flat_ensemble_targets.py --first 0 --last 14848 --resume   # skip done rows

Author: Jing Tao with Claude
"""
from __future__ import annotations

import argparse
import csv
import math
import os
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))


def scored_targets(targets_yaml: Path):
    import yaml
    tg = yaml.safe_load(open(targets_yaml))["targets"]
    # `track: soil_bgc` marks a diagnostic target, not a scored one -- same rule as the crossed
    # extractor, kept identical so the two cannot disagree about what "scored" means.
    return [dict(name=k, **v) for k, v in tg.items() if v.get("track") != "soil_bgc"]


def chunk_bounds(first: int, last: int, size: int):
    """Inclusive [first,last] split into <=size blocks. Must PARTITION: no gap, no overlap.

    Extracted so it is testable. A gap silently drops cases from the Y matrix, and for a Saltelli
    design a missing row is exactly the failure the whole extractor exists to avoid manufacturing.
    """
    if size <= 0:
        raise ValueError(f"chunk size must be positive, got {size}")
    if last < first:
        raise ValueError(f"empty range {first}..{last}")
    return [(a, min(a + size - 1, last)) for a in range(first, last + 1, size)]


def _drive_chunked(args, out: Path, names) -> int:
    """Score the range in FRESH SUBPROCESSES of this script, then concatenate.

    Ported from the prior art this script generalizes,
    use_cases/EcoSIM_BioCON/memory/phase_results/20260811g_morris_fs_soilbgc_screen/
    extract_morris_results.py, which chunks 10 at a time and says why: processing 241 cases in one
    long-running interpreter made some cases with GENUINELY VALID, COMPLETE output tapes spuriously
    raise `'NoneType' is not iterable`, non-reproducible when the same case was re-evaluated in
    isolation. Writing this script from scratch instead of promoting that one is how the mitigation
    was dropped (dev log 20260821f).

    Why it matters more here than there: a spurious failure is written as a FAILED ROW, and for a
    Saltelli design a hole's position decides whether the estimator is usable at all. A leak would
    therefore manufacture fake holes and they would be blamed on the model.

    The leak's ONSET was never bisected -- 241-in-one-interpreter is the only measurement -- so the
    default chunk (50) is deliberately well below it rather than tuned. Each chunk resumes into its
    own file, so an interrupted run re-does at most one chunk.
    """
    import subprocess
    chunk_dir = Path(args.chunk_dir) if args.chunk_dir else Path(str(out) + ".chunks")
    chunk_dir.mkdir(parents=True, exist_ok=True)
    total = args.last - args.first + 1
    bounds = chunk_bounds(args.first, args.last, args.chunk_size)
    print(f"chunked: {total} cases in {len(bounds)} subprocess(es) of <= {args.chunk_size}")
    t0 = time.time()
    parts = []
    for i, (a, b) in enumerate(bounds, start=1):
        part = chunk_dir / f"chunk_{a:07d}_{b:07d}.csv"
        parts.append(part)
        cmd = [sys.executable, str(Path(__file__).resolve()),
               "--model", args.model, "--run-root", args.run_root,
               "--case-pattern", args.case_pattern, "--targets", args.targets,
               "--first", str(a), "--last", str(b), "--out", str(part),
               "--chunk-size", "0", "--progress-every", "10000"]
        if args.resume:
            cmd.append("--resume")
        r = subprocess.run(cmd, capture_output=True, text=True)
        if r.returncode != 0:
            # A dead chunk is NOT silently tolerated: its cases would otherwise vanish from the
            # matrix entirely, which is a hole that looks like nothing at all.
            print(f"ERROR: chunk {a}-{b} exited {r.returncode}", file=sys.stderr)
            print(r.stdout[-2000:], file=sys.stderr); print(r.stderr[-2000:], file=sys.stderr)
            return 1
        if i % 10 == 0 or i == len(bounds):
            el = time.time() - t0
            print(f"  chunk {i}/{len(bounds)}  ({el:.0f}s, {el / i:.1f}s per chunk)", flush=True)

    tally = {}
    n_rows = 0
    with open(out, "w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["case", "status"] + names)
        for part in parts:
            with open(part) as pf:
                rd = csv.reader(pf)
                next(rd, None)                      # drop the per-chunk header
                for row in rd:
                    w.writerow(row); n_rows += 1
                    tally[row[1]] = tally.get(row[1], 0) + 1
    if n_rows != total:
        print(f"ERROR: concatenated {n_rows} rows for a {total}-case range", file=sys.stderr)
        return 1
    print(f"\nwrote {out}  ({n_rows} rows, in {time.time() - t0:.0f}s)")
    for k, v in sorted(tally.items(), key=lambda kv: -kv[1]):
        print(f"    {k:28s} {v}")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--model", default=os.environ.get("A2MC_MODEL"))
    ap.add_argument("--run-root", default=os.environ.get("A2MC_OUTPUT_DIR"))
    ap.add_argument("--case-pattern", default=os.environ.get("A2MC_CASE_NAME_PATTERN", "case{N}"))
    ap.add_argument("--targets", default=os.environ.get("A2MC_VALIDATION_TARGETS"))
    ap.add_argument("--first", type=int, required=True)
    ap.add_argument("--last", type=int, required=True)
    ap.add_argument("--out", default=None)
    ap.add_argument("--resume", action="store_true",
                    help="keep rows already present in --out and only score the missing cases")
    ap.add_argument("--progress-every", type=int, default=200)
    ap.add_argument("--flush-every", type=int, default=25,
                    help="fsync-free flush cadence; the row-by-row write is only inspectable "
                         "and crash-resilient if the buffer is actually flushed")
    ap.add_argument("--chunk-size", type=int, default=50,
                    help="score this many cases per FRESH SUBPROCESS, then concatenate (0 = run "
                         "everything in this interpreter). Default 50; see the module docstring "
                         "for why isolation is not optional.")
    ap.add_argument("--chunk-dir", default=None,
                    help="where per-chunk CSVs live (default <out>.chunks/)")
    args = ap.parse_args()

    if not args.model or not args.run_root or not args.targets:
        print("ERROR: --model/--run-root/--targets (or their env vars) are required", file=sys.stderr)
        return 1

    root = Path(args.run_root)
    out = Path(args.out) if args.out else root / "Y_matrix_scored.csv"
    targets = scored_targets(Path(args.targets))
    names = [t["name"] for t in targets]

    if args.chunk_size and args.chunk_size > 0:
        return _drive_chunked(args, out, names)

    import importlib
    from models import registry
    importlib.import_module(f"models.{args.model}")
    backend = registry.get_model(args.model)
    from tools.model_evaluate_case import evaluate_model_case

    done: dict[int, list] = {}
    if args.resume and out.is_file():
        with open(out) as fh:
            for row in csv.DictReader(fh):
                # a row is only reusable if it actually carries a score
                if row.get("status") == "COMPLETED":
                    done[int(row["case"])] = [row[n] for n in names]
        print(f"resume: {len(done)} scored rows kept from {out}")

    t0 = time.time()
    tally = {"COMPLETED": 0, "reused": 0, "not_complete": 0, "score_error": 0}
    with open(out, "w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["case", "status"] + names)
        for n in range(args.first, args.last + 1):
            if n in done:
                w.writerow([n, "COMPLETED"] + done[n]); tally["reused"] += 1
                continue
            cdir = root / args.case_pattern.replace("{N}", str(n))
            try:
                status = backend.check_case_status(cdir)
            except Exception:
                status = "UNKNOWN"
            if status != "COMPLETED":
                w.writerow([n, status] + [math.nan] * len(names)); tally["not_complete"] += 1
                continue
            try:
                _, _, sim = evaluate_model_case(cdir, targets, model=args.model)
                w.writerow([n, "COMPLETED"] + [sim.get(k, math.nan) for k in names])
                tally["COMPLETED"] += 1
            except Exception as exc:
                w.writerow([n, f"SCORE_ERROR:{type(exc).__name__}"] + [math.nan] * len(names))
                tally["score_error"] += 1
            if (n - args.first + 1) % args.flush_every == 0:
                fh.flush()
            if (n - args.first + 1) % args.progress_every == 0:
                el = time.time() - t0
                print(f"  {n - args.first + 1}/{args.last - args.first + 1} "
                      f"({el:.0f}s, {el / max(tally['COMPLETED'], 1):.2f}s per scored case)", flush=True)

    el = time.time() - t0
    print(f"\nwrote {out}")
    print(f"  scored={tally['COMPLETED']} reused={tally['reused']} "
          f"not_complete={tally['not_complete']} score_error={tally['score_error']}  in {el:.0f}s")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
