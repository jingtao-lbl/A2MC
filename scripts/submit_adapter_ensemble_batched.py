#!/usr/bin/env python3
"""Submit an adapter ensemble in WAVES that respect the scheduler's submission ceiling.

WHY THIS EXISTS. NERSC caps a user at **5000 queued jobs** (`QOSMaxSubmitJobPerUserLimit`). An
adapter model submits ONE job per case — no CIME chain — so a 4608-case round is 4608 jobs and
sits right against that ceiling, with nothing left for the other work a shared account is running.
Submitting it in one pass either aborts partway (leaving a half-materialized, half-submitted round
that `restart-failed-jobs` has a whole special case for) or starves every other lane on the
account.

**The headroom formula is model-dependent and copying it is a real trap.** `arm-hpc-monitoring`
states it as `current_queue + N_new_cases * 3 <= 5000`; the `* 3` is FATES's ADSP->RGSP->TRANS
chain, three jobs per case. An adapter model is `* 1`, so inheriting the FATES form under-uses the
queue threefold. This script takes the multiplier as a parameter rather than assuming either.

WHAT IT DOES, each wave:
  1. Count MY jobs actually in the queue (`squeue -h -r`, array-expanded — `-r` matters, a folded
     array line counts as one and undercounts the ceiling).
  2. headroom = ceiling - reserve - current_queue, in CASES (divided by jobs_per_case).
  3. Materialize + validate + submit `min(headroom, wave_cap, remaining)` cases.
  4. Publish a state file, then sleep and re-check until the queue drains enough for the next wave.

**RESERVE is not padding.** A shared account has other lanes; if this fills the ceiling exactly, the
next `sbatch` anyone runs fails. It also absorbs the race between counting and submitting.

**IDEMPOTENT.** A case that already has `job_id.txt` is treated as submitted and skipped, so an
interrupted run resumes by re-invocation rather than by re-submitting what is already queued.

The state file matches `tools/check_watcher_state.py`'s contract (`status`, `epoch`, `interval_s`,
`complete`, `failed`, `total`), so the heartbeat layer applies here as it does to an array watcher:
this script's own death is detectable, which a log that stops growing cannot show.

Usage (source the site config first):
    nohup python scripts/submit_adapter_ensemble_batched.py \\
        --total 4608 --wave-cap 800 --state tmp/r1_submit_state.json > tmp/r1_submit.log 2>&1 &

Author: Jing Tao with Claude
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))


def log(msg: str) -> None:
    print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] {msg}", flush=True)


def queue_depth(user: str) -> int:
    """MY jobs currently in the queue, ARRAY-EXPANDED.

    `-r` is load-bearing: without it a folded array line (`123_[5-99]`) counts as ONE, which
    undercounts the ceiling by however many tasks it hides. `feedback_never_parse_a_cli_default_output`
    is the same lesson one level up — never read a scheduler CLI's convenience formatting as data.
    """
    r = subprocess.run(["squeue", "-u", user, "-h", "-r", "-o", "%i"],
                       capture_output=True, text=True, timeout=120)
    if r.returncode != 0:
        raise RuntimeError(f"squeue failed: {r.stderr.strip()}")
    return len([l for l in r.stdout.splitlines() if l.strip()])


def already_submitted(run_root: Path, pattern: str, i: int) -> bool:
    return (run_root / pattern.replace("{N}", str(i)) / "job_id.txt").is_file()


def run(cmd: list[str], what: str) -> None:
    r = subprocess.run(cmd, cwd=str(REPO), capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError(f"{what} failed (rc={r.returncode}):\n{r.stdout[-2000:]}\n{r.stderr[-2000:]}")


def publish(state: Path, status: str, done: int, failed: int, total: int, interval: int,
            extra: dict | None = None) -> None:
    state.parent.mkdir(parents=True, exist_ok=True)
    d = {"status": status, "epoch": time.time(), "interval_s": interval,
         "complete": done, "failed": failed, "total": total}
    if extra:
        d.update(extra)
    state.write_text(json.dumps(d, indent=2))


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    env = os.environ.get
    ap.add_argument("--model", default=env("A2MC_MODEL", "pflotran"))
    ap.add_argument("--run-root", default=env("A2MC_OUTPUT_DIR"))
    ap.add_argument("--case-pattern", default=env("A2MC_CASE_NAME_PATTERN", "miniLEO_case{N}"))
    ap.add_argument("--total", type=int, required=True, help="cases 1..TOTAL")
    ap.add_argument("--ceiling", type=int, default=5000, help="scheduler submission cap")
    ap.add_argument("--reserve", type=int, default=400,
                    help="jobs left free for OTHER lanes on this account and for the "
                         "count-then-submit race (default 400)")
    ap.add_argument("--jobs-per-case", type=int, default=1,
                    help="1 for an adapter model (one job per case); 3 for a FATES ADSP/RGSP/TRANS chain")
    ap.add_argument("--wave-cap", type=int, default=800,
                    help="max cases per wave, so an abort loses little and disk fills gradually")
    ap.add_argument("--interval", type=int, default=300, help="seconds between queue re-checks")
    ap.add_argument("--state", default="tmp/adapter_submit_state.json")
    ap.add_argument("--validator", default="scripts/validate_pflotran_ensemble.py",
                    help="pre-submit gate to run on each wave before it is submitted")
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()

    if not a.run_root:
        print("ERROR: --run-root unset (source the site config)", file=sys.stderr)
        return 2
    run_root, state = Path(a.run_root), Path(a.state)
    user = env("USER") or subprocess.run(["whoami"], capture_output=True, text=True).stdout.strip()

    from models.registry import get_model                    # noqa: E402
    import models.pflotran.backend                           # noqa: F401,E402
    backend = get_model(a.model)
    cfg = {k: v for k, v in os.environ.items() if k.startswith("A2MC_")}

    pending = [i for i in range(1, a.total + 1)
               if not already_submitted(run_root, a.case_pattern, i)]
    submitted = a.total - len(pending)
    log(f"model={a.model} run_root={run_root}")
    log(f"total={a.total}  already submitted={submitted}  pending={len(pending)}")
    log(f"ceiling={a.ceiling} reserve={a.reserve} jobs/case={a.jobs_per_case} wave_cap={a.wave_cap}")

    failed = 0
    while pending:
        try:
            depth = queue_depth(user)
        except Exception as e:                                # noqa: BLE001
            log(f"WARN: could not read the queue ({e}); retrying in {a.interval}s")
            publish(state, "RUNNING", submitted, failed, a.total, a.interval,
                    {"note": "queue unreadable"})
            time.sleep(a.interval)
            continue

        headroom_jobs = a.ceiling - a.reserve - depth
        headroom_cases = max(0, headroom_jobs // a.jobs_per_case)
        n = min(headroom_cases, a.wave_cap, len(pending))

        if n <= 0:
            log(f"queue={depth}  headroom={headroom_cases} cases -> WAITING {a.interval}s "
                f"({len(pending)} still to submit)")
            publish(state, "RUNNING", submitted, failed, a.total, a.interval,
                    {"queue_depth": depth, "waiting": True})
            time.sleep(a.interval)
            continue

        wave, pending = pending[:n], pending[n:]
        lo, hi = wave[0], wave[-1]
        contiguous = (hi - lo + 1) == len(wave)
        log(f"queue={depth}  headroom={headroom_cases}  -> WAVE of {len(wave)} "
            f"(cases {lo}..{hi}{'' if contiguous else ', non-contiguous'})")

        # PUBLISH AT WAVE START, not only at wave end. A wave of several hundred cases takes
        # minutes to materialize, validate and submit, and until 2026-08-27 nothing was written
        # during it -- so a death mid-wave left NO state file at all, and `check_watcher_state.py`
        # could only report UNREADABLE, which its own docstring says is "NOT evidence the array is
        # running". That happened: an interrupt killed this script 2 s into its first wave, after
        # 52 of 800 submissions, and the only way to find out was counting job_id.txt files by
        # hand. A heartbeat that starts when the work starts is the whole point of a heartbeat.
        publish(state, "RUNNING", submitted, failed, a.total, a.interval,
                {"queue_depth": depth, "wave_in_progress": [lo, hi], "phase": "materializing"})

        if a.dry_run:
            log("  [dry-run] would materialize, validate, submit")
            submitted += len(wave)
            continue

        try:
            if not contiguous:
                # Never silently submit a different set than the one reported.
                raise RuntimeError("non-contiguous wave: materializer takes --start/--end only. "
                                   "Re-run; the idempotent skip will re-form contiguous runs.")
            run([sys.executable, "scripts/materialize_adapter_ensemble.py",
                 "--start", str(lo), "--end", str(hi)], "materialize")
            run([sys.executable, a.validator, "--start", str(lo), "--end", str(hi)], "validate")
            paths = [run_root / a.case_pattern.replace("{N}", str(i)) for i in wave]
            # SUBMIT IN CHUNKS AND BEAT BETWEEN THEM. `submit_ensemble` issues one `sbatch` per
            # case, ~1 s each, so a 600-case wave spends 10+ MINUTES inside a single call. With
            # the heartbeat published only at wave start and end, that silent stretch exceeds
            # `check_watcher_state.py`'s STALE threshold (2 x interval) and a perfectly healthy
            # submitter reports STALE -- which happened at 07:38 on 2026-08-27, mid-wave, at 569
            # of 600 submitted and the process answering kill -0 the whole time.
            #
            # A FALSE STALE IS NOT A HARMLESS ALARM. This tool's entire job is to distinguish "the
            # watcher died quietly" from "nothing is happening yet"; a monitor that cries dead on
            # a healthy run teaches its reader to discount it, and the next STALE -- the real one
            # -- gets waved off. Fixing the emitter is the only honest fix: the threshold is
            # correct, the silence was not.
            CHUNK = 50
            ids = []
            for k in range(0, len(paths), CHUNK):
                ids += backend.submit_ensemble(paths[k:k + CHUNK], cfg)
                publish(state, "RUNNING", submitted + len(ids), failed, a.total, a.interval,
                        {"queue_depth": depth, "wave_in_progress": [lo, hi],
                         "phase": f"submitting {len(ids)}/{len(paths)}"})
            submitted += len(ids)
            log(f"  submitted {len(ids)} (first={ids[0]} last={ids[-1]})")
        except Exception as e:                                # noqa: BLE001
            failed += len(wave)
            log(f"  WAVE FAILED: {e}")
            publish(state, "DIED", submitted, failed, a.total, a.interval,
                    {"error": str(e)[:500]})
            return 1

        publish(state, "RUNNING", submitted, failed, a.total, a.interval,
                {"queue_depth": depth, "last_wave": [lo, hi]})
        if pending:
            time.sleep(a.interval)

    log(f"ALL SUBMITTED: {submitted}/{a.total} (failed waves: {failed})")
    publish(state, "ENDED", submitted, failed, a.total, a.interval)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
