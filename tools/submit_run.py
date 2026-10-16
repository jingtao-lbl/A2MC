#!/usr/bin/env python3
"""Submit a run with sbatch AND register it in the case's run ledger, in one step.

visibility: public

WHY ONE STEP. The run ledger (`memory/run_records_r{RR}.json`) and the table generated from it
are only as complete as the last person to remember to write them. Registering at the moment of
submission removes the remembering: the job id, the binary, what the run is for and how it departs
from its base are all known here, and nowhere are they better known. The agent's PreToolUse hook
(`.claude/hooks/block-unregistered-sbatch.py`) refuses a bare `sbatch` and points here. The
account is `memory/dev_logs_adapterkit/20261014a_*`.

WHAT IT REFUSES. A submission without `--purpose`, `--differences`, `--binary` and a run location
(`--run-dir` for one simulation, `--run-root` for one row covering a whole submission). Those are
the fields that make a run reproducible and let `record_run_status.py settle` read the model's own
verdict when the job ends. It also refuses to overwrite a record whose job is still in the queue.

USAGE (everything after `--` is passed to sbatch unchanged):

    python tools/submit_run.py --case-dir use_cases/EcoSIM_Lusignan --round 2 --cycle 0 \
        --case probe5_case53 --stem <phase_results stem> \
        --purpose "what this run is for" --differences "<base> EXCEPT <what> = <value>" \
        --binary /path/to/archived/ecosim.f90.x --run-dir /path/to/Lusignan_case53 \
        [--job-id-file /path/to/Lusignan_case53/job_id.txt] \
        -- --qos=debug /path/to/submit_probe.sh

    # one row for a whole packed submission
    python tools/submit_run.py ... --case R2b_rerun_X_53 --run-root /path/to/run_root \
        --field case_prefix=Lusignan_case -- --job-name=... submit_ensemble_packed.sh

stdout carries ONLY the job id, so `J=$(python tools/submit_run.py ...)` works; everything else
goes to stderr. `--resubmit` replaces an earlier submission of the same record and keeps the old
job id in `history`. `--dry-run` validates and prints the sbatch command without submitting.

When the job ends, `record_run_status.py settle` resolves the record to the model's verdict. A
watcher can run it for you: `tools/watch_slurm_array.sh ... -X '<settle command>'` or
`tools/model_ensemble_status.py ... --on-end '<settle command>'`; this tool prints the command.

Author: Jing Tao with Claude
"""
import argparse
import hashlib
import json
import pathlib
import shlex
import subprocess
import sys
from datetime import datetime

REPO = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))
from tools import record_run_status as rrs  # noqa: E402


def _err(msg: str) -> None:
    print(msg, file=sys.stderr)


def _binary_label(binary: str) -> str:
    """`<archive dir>/<exe> md5:<8>` when the path exists, else the text as given."""
    p = pathlib.Path(binary)
    if p.is_file():
        h = hashlib.md5()
        with open(p, "rb") as fh:
            for chunk in iter(lambda: fh.read(1 << 20), b""):
                h.update(chunk)
        return f"{p.parent.name}/{p.name} md5:{h.hexdigest()[:8]}"
    return binary


def main(argv=None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if "--" not in argv:
        _err("ERROR: put the sbatch arguments after `--`, e.g. ... -- --qos=debug submit.sh")
        return 2
    cut = argv.index("--")
    ours, sbatch_args = argv[:cut], argv[cut + 1:]
    if not sbatch_args:
        _err("ERROR: nothing after `--`: no script to submit")
        return 2

    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--case-dir", required=True, help="use_cases/<Model>_<Case>")
    ap.add_argument("--round", type=int, required=True)
    ap.add_argument("--cycle", type=int, required=True)
    ap.add_argument("--case", required=True, help="the ledger record name (unique in the round)")
    ap.add_argument("--purpose", required=True)
    ap.add_argument("--differences", required=True,
                    help="'<base> EXCEPT <what> = <value>' -- what makes the run reproducible")
    ap.add_argument("--binary", required=True,
                    help="the ARCHIVED executable the run is bound to; md5 is recorded if it exists")
    loc = ap.add_mutually_exclusive_group(required=True)
    loc.add_argument("--run-dir", help="this simulation's directory")
    loc.add_argument("--run-root", help="the root of a whole submission (one ledger row)")
    ap.add_argument("--stem", default=None, help="the phase_results stem the run belongs to")
    ap.add_argument("--model", default=None, help="onboarded model (default: the ledger's, or ecosim)")
    ap.add_argument("--job-id-file", default=None,
                    help="also write the job id here (e.g. <run_dir>/job_id.txt, which the "
                         "watchers read)")
    ap.add_argument("--field", action="append", default=[], help="extra k=v for the record")
    ap.add_argument("--resubmit", action="store_true",
                    help="replace an earlier submission of this record (its job id goes to history)")
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args(ours)

    for name in ("purpose", "differences", "binary"):
        if not getattr(a, name).strip():
            _err(f"ERROR: --{name} is empty")
            return 2
    where = a.run_dir or a.run_root
    if not pathlib.Path(where).is_dir():
        _err(f"ERROR: run location does not exist: {where}")
        return 2

    data = rrs.load(a.case_dir, a.round)
    prior = next((r for r in data["records"] if r.get("case") == a.case), None)
    if prior and not a.resubmit:
        _err(f"ERROR: {a.case} is already in the round {a.round} ledger (status "
             f"{prior.get('status')}, job {prior.get('job_id')}). Pick a new record name, or pass "
             f"--resubmit to replace that submission.")
        return 2
    if prior and prior.get("status") in rrs.OPEN_STATUSES and prior.get("job_id"):
        st = rrs._job_states([prior["job_id"]]).get(str(prior["job_id"]), "")
        if not rrs._is_terminal(st):
            _err(f"ERROR: {a.case}'s job {prior['job_id']} has not ended ({st or 'unreadable'}); "
                 f"cancel it first, or settle it, before resubmitting.")
            return 2

    cmd = ["sbatch", "--parsable"] + sbatch_args
    if a.dry_run:
        _err("dry run, would submit: " + " ".join(shlex.quote(c) for c in cmd))
        _err(f"and register {a.case} in round {a.round} as submitted")
        return 0

    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        _err(proc.stderr.strip() or proc.stdout.strip())
        _err("ERROR: sbatch failed; nothing was registered")
        return proc.returncode or 1
    job = proc.stdout.strip().split(";")[0].strip()
    if not job[:1].isdigit():
        _err(f"ERROR: could not read a job id from sbatch's output: {proc.stdout!r}. The job MAY "
             f"have been submitted; check squeue and register it with record_run_status.py upsert.")
        return 1

    fields = rrs._kv(a.field)
    if prior:
        hist = prior.get("history") or ""
        fields["history"] = (hist + "; " if hist else "") + (
            f"job {prior.get('job_id')} replaced by {job} on {datetime.now():%Y-%m-%d %H:%M}")
        for k in ("slurm_state", "fail_reason", "fail_mode", "void_reason", "outcome",
                  "settled_at", "n_cases", "n_completed", "n_failed"):
            prior.pop(k, None)
    model = a.model or (prior or {}).get("model") or "ecosim"
    rrs.upsert(data, a.round, a.case, cycle=a.cycle, status="submitted", job_id=job,
               stem=a.stem, purpose=a.purpose, differences=a.differences,
               binary=_binary_label(a.binary), run_dir=a.run_dir, run_root=a.run_root,
               model=model, submitted_at=datetime.now().isoformat(timespec="seconds"),
               sbatch=" ".join(shlex.quote(c) for c in sbatch_args), **fields)
    rrs.save(a.case_dir, a.round, data)
    if a.job_id_file:
        pathlib.Path(a.job_id_file).write_text(job + "\n")

    settle = (f"{sys.executable} {REPO}/tools/record_run_status.py settle --case-dir "
              f"{pathlib.Path(a.case_dir).resolve()} --round {a.round} --job-id {job}")
    _err(f"submitted {job}; registered {a.case} (round {a.round}, cycle {a.cycle}) as submitted")
    _err(f"when it ends, settle it (or give a watcher this as its on-end hook):\n  {settle}")
    print(job)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
