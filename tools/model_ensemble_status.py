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
import json
import os
import re
import signal
import subprocess
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
_TERMINAL = {"COMPLETED", "FAILED", "CANCELLED", "TIMEOUT", "NODE_FAIL", "OUT_OF_MEMORY", "PREEMPTED"}
_FAIL_PAT = re.compile(r"ENDRUN|Program aborted|srun: error|Variable not found|IO ERROR|Killed|OOM|Segmentation", re.I)


def normalize_state(raw: str) -> str:
    """One sacct State string -> the bare state keyword `_TERMINAL` is written in.

    `sacct` does NOT return a bare keyword. It decorates two ways, and BOTH must be stripped
    or a terminal job reads as active:

        "COMPLETED+"          a truncation marker
        "CANCELLED by 79622"  the cancelling uid, appended with a SPACE

    Measured 2026-10-10: a cancelled 16-task array reported `ACTIVE(CANCELLED by 79622)`, so
    `jobs_terminal` stayed False and every case that had died part-way was still published as
    RUNNING -- the exact failure `ensemble_jobs_terminal` exists to prevent, reintroduced by the
    formatting of the state rather than by the logic. Only `+` was being stripped.

    This is [[feedback_never_parse_a_cli_default_output]] one layer in: the field was requested
    explicitly with `--format=State -P`, which controls WHICH field is returned and not how its
    VALUE is spelled.
    """
    return raw.strip().split("+")[0].split()[0] if raw.strip() else ""


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
        s = normalize_state(line)
        if s:
            return s
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
        seen = {normalize_state(l) for l in out.splitlines() if l.strip()}
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
         case_ids=None, case_prefix=None):
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
            # PREFIX FIRST. `case_index` takes the TRAILING integer, so it cannot tell
            # `<Case>_case5` from `<Case>_valid5`: a round that materializes an independent
            # validation lattice beside its training cases in ONE run root has two dir families
            # sharing an index space, and an index-only filter sweeps in both. That inflates
            # `total`, so `complete + failed == total` can never be met and the terminal signal
            # never fires -- the condition-that-cannot-be-true shape, one layer out.
            # Measured 2026-10-13: --case-range 0-256 over a 257-case gate reported total=513,
            # having added `Lusignan_valid1..256`.
            if case_prefix is not None and not e.name.startswith(case_prefix):
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


# ---------------------------------------------------------------- state publication
#: The state-file schema is a CONTRACT with `tools/check_watcher_state.py`, which reads
#: `status`, `epoch`, `interval_s`, `complete`, `failed`, `total` and -- singular --
#: `job`. A hand-rolled watcher wrote `jobs` and silently disabled that reader's sacct
#: cross-check, so the names here are copied from the consumer, not invented.
_TERMINAL_OK = "ENDED"
_TERMINAL_UNACCOUNTED = "ENDED_UNACCOUNTED"


class StateFile:
    """Publish a watcher heartbeat to disk, and refuse to be the second instance.

    The MTIME is the liveness signal: a watcher that reports only by appending to a log
    cannot report its own death, because a log that stops growing looks the same whether
    the jobs are quiet or the watcher is gone. SIGKILL cannot be trapped, so the
    arithmetic test (`status == RUNNING` and the heartbeat older than two intervals) is
    the only one that survives every death mode -- the DIED stamp below is a
    convenience, never the guarantee.
    """

    def __init__(self, path, interval_s, note=""):
        self.path = Path(path)
        self.pid_path = Path(str(path) + ".pid")
        self.interval_s = max(1, int(interval_s))
        self.note = note
        self.job = ""
        self.end_hook_status = None   # set once the --on-end command has run
        self._claim()

    # -- singleton -------------------------------------------------------------
    @staticmethod
    def _starttime(pid):
        """The process's start time in clock ticks since boot (`/proc/<pid>/stat` f22).

        This is the identity token, in preference to the command line: pid + start time
        names one process INSTANCE and cannot be inherited by a recycled id, whereas a
        cmdline match depends on how the path happened to be spelled in argv and goes
        silently blind when a wrapper passes it relatively or through the environment.
        """
        try:
            raw = Path(f"/proc/{pid}/stat").read_text()
        except OSError:
            return None
        # The comm field is parenthesised and may itself contain spaces and parens, so
        # fields are counted from AFTER the final ')' -- splitting on whitespace from the
        # start mis-indexes every field for a process whose name has a space in it.
        try:
            fields = raw[raw.rindex(")") + 1:].split()
            return fields[19]          # f22 overall = index 19 after pid and comm
        except (ValueError, IndexError):
            return None

    def _live_owner(self):
        """Return the pid of a LIVE watcher already publishing to this path, else None.

        Both halves are necessary. Liveness alone refuses to start whenever an unrelated
        process has inherited a dead watcher's pid. Identity alone cannot tell a running
        owner from a finished one.
        """
        try:
            parts = self.pid_path.read_text().split()
            pid, claimed = int(parts[0]), (parts[1] if len(parts) > 1 else None)
        except (OSError, ValueError, IndexError):
            return None
        if pid == os.getpid():
            return None                # re-entry by the same process is not a conflict
        try:
            os.kill(pid, 0)
        except (OSError, ProcessLookupError, PermissionError):
            return None                # not alive -> a crashed watcher must not wedge the path
        if claimed is None:
            return pid                 # pre-token pid file: fall back to liveness alone
        return pid if self._starttime(pid) == claimed else None

    def _claim(self):
        owner = self._live_owner()
        if owner is not None:
            raise SystemExit(
                f"REFUSING TO START: pid {owner} is already publishing to {self.path}.\n"
                f"  Two watchers on one state file is how a stale instance wins the last\n"
                f"  write and publishes a count the live one disagrees with.\n"
                f"  Stop it first:  kill {owner}   (then re-run)")
        self.pid_path.parent.mkdir(parents=True, exist_ok=True)
        me = os.getpid()
        self.pid_path.write_text(f"{me} {self._starttime(me)}\n")

    # -- publication -----------------------------------------------------------
    def write(self, status, counts, total, job=""):
        self.job = job or self.job
        payload = {
            "ts": time.strftime("%Y-%m-%d %H:%M:%S"),
            "epoch": int(time.time()),
            "status": status,
            "job": self.job,
            "pending": int(counts.get("PENDING", 0)),
            "running": int(counts.get("RUNNING", 0)),
            "complete": int(counts.get("COMPLETED", 0)),
            "failed": int(counts.get("FAILED", 0)),
            "total": int(total),
            "interval_s": self.interval_s,
            "watcher_pid": os.getpid(),
            "note": self.note,
        }
        if self.end_hook_status is not None:
            payload["end_hook_status"] = self.end_hook_status
        tmp = self.path.with_suffix(self.path.suffix + ".tmp")
        tmp.write_text(json.dumps(payload, indent=1) + "\n")
        tmp.replace(self.path)     # atomic: a reader never sees a half-written file

    def terminal(self, counts, total, job=""):
        """Stamp the finish, distinguishing a full account from a partial one.

        ENDED_UNACCOUNTED exists because `complete + failed == total` is the only
        arithmetic that licenses the word finished. A watcher that stops with cases in
        neither bucket has stopped, not finished, and publishing that as ENDED is how a
        round gets read as complete while cases sit unexamined.
        """
        done = int(counts.get("COMPLETED", 0)) + int(counts.get("FAILED", 0))
        status = _TERMINAL_OK if done == int(total) else _TERMINAL_UNACCOUNTED
        self.write(status, counts, total, job)
        return status

    def died(self, counts, total):
        try:
            self.write("DIED", counts, total)
        except OSError:
            pass


def run_on_end(cmd: str, timeout_s: int) -> str:
    """Run the on-end command once; print its output into this log; return OK/TIMEOUT/FAILED."""
    print(f"ON_END running: {cmd}", flush=True)
    try:
        proc = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=timeout_s,
                              stdin=subprocess.DEVNULL)
        for line in (proc.stdout + proc.stderr).splitlines():
            print(f"[ON_END] {line}", flush=True)
        status = "OK" if proc.returncode == 0 else "FAILED"
        print(f"ON_END {status} (rc={proc.returncode})", flush=True)
    except subprocess.TimeoutExpired:
        status = "TIMEOUT"
        print(f"ON_END TIMEOUT after {timeout_s}s", flush=True)
    return status


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
    ap.add_argument("--state-file", metavar="PATH",
                    help="publish a heartbeat here every poll (requires --watch). The file's "
                         "MTIME is the liveness signal, which is what lets a DEAD watcher be "
                         "told apart from a quiet one; read it with tools/check_watcher_state.py. "
                         "A second instance pointed at the same path REFUSES to start.")
    ap.add_argument("--state-note", metavar="TEXT", default="",
                    help="free-form note carried in the state file (e.g. which arms these are)")
    ap.add_argument("--on-end", metavar="CMD", default="",
                    help="with --watch: run CMD once when every case is terminal (output in this "
                         "log, outcome in the state file as end_hook_status). The intended CMD is "
                         "`tools/record_run_status.py settle ... --job-id <job>`, which "
                         "tools/submit_run.py prints, so the run ledger gets the model's verdict "
                         "when the run ends.")
    ap.add_argument("--on-end-timeout", type=int, default=600, metavar="SEC")
    ap.add_argument("--case-prefix", metavar="PREFIX",
                    help="scan ONLY case dirs whose name starts with PREFIX (e.g. "
                         "'Lusignan_case'). REQUIRED to disambiguate when a run root holds more "
                         "than one case family -- a training set and an independent validation "
                         "lattice share an index space, and --case-range/--cases-file match the "
                         "TRAILING INTEGER only, so without this they match both families.")
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

    state = None
    if args.state_file:
        if not args.watch:
            print("ERROR: --state-file requires --watch (a one-shot run has no heartbeat to "
                  "publish, and a single stamped file would read as a live watcher)",
                  file=sys.stderr)
            return 1
        state = StateFile(args.state_file, args.watch, args.state_note)
        _last = {"counts": {}, "total": 0}

        def _on_signal(signum, _frame):
            state.died(_last["counts"], _last["total"])
            print(f"WATCHER_DIED (signal {signum}); state stamped DIED", flush=True)
            raise SystemExit(1)

        for _sig in (signal.SIGTERM, signal.SIGINT):
            signal.signal(_sig, _on_signal)

    while True:
        jobs_terminal = False
        if jobs:
            jobs_terminal, states = ensemble_jobs_terminal(jobs)
            print("ensemble jobs: " + "  ".join(f"{j}={s}" for j, s in states.items())
                  + ("  -> all terminal; started-but-incomplete cases are FAILED, not RUNNING"
                     if jobs_terminal else "  -> some still active; incomplete cases stay RUNNING"))
        rows = scan(args.model, run_root, case_range, jobs_terminal, case_ids,
                    args.case_prefix)
        counts = report(rows, args.failed)
        pending = counts.get("PENDING", 0) + counts.get("RUNNING", 0)
        # `total` is DERIVED from the scan, never passed in. A hardcoded total is how a
        # watcher's own finish test becomes unreachable: 3 arms against a literal 4 means
        # complete+failed can never meet it, and the watcher runs until it is killed.
        total = len(rows)
        job_field = ",".join(jobs) if jobs else ",".join(
            dict.fromkeys(r[1] for r in rows if r[1] and r[1] != "-"))
        if state is not None:
            _last["counts"], _last["total"] = counts, total
        if not args.watch or pending == 0:
            if state is not None:
                status = state.terminal(counts, total, job_field)
                print(f"ENSEMBLE_TERMINAL {status} complete={counts.get('COMPLETED', 0)} "
                      f"failed={counts.get('FAILED', 0)} of {total}", flush=True)
            if args.watch and args.on_end:
                end_status = run_on_end(args.on_end, args.on_end_timeout)
                if state is not None:
                    state.end_hook_status = end_status
                    state.write(status, counts, total, job_field)
            break
        if state is not None:
            state.write("RUNNING", counts, total, job_field)
        print(f"  … {pending} still active; re-checking in {args.watch}s", flush=True)
        time.sleep(args.watch)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
