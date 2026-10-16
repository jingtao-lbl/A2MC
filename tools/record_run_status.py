#!/usr/bin/env python
"""record_run_status.py -- the per-simulation RUN LEDGER, written in real time by Phase 5.

WHAT THIS IS, AND WHAT IT IS NOT (PI, 2026-09-08). A run record is a RECORD: which case ran, from
which base, with which parameter values, under which job id and which binary, what state the
scheduler and the model report, and what it scored. It needs no curation and no human gate, because
nothing in it is a claim -- it is what happened.

That makes it a DIFFERENT object from `gained_knowledge/experiments.json`, which is curated
knowledge behind the Tier-3 write gate and holds the INTERPRETED record: the hypothesis, the
lesson, the do-not-repeat. Writing run status into that store would put an ungated automatic writer
inside the gate built after the May 2026 auto-learn contamination. So the ledger lives OUTSIDE
`gained_knowledge/`, at

    use_cases/{Model}_{Case}/memory/run_records_r{RR}.json

one file PER CALIBRATION ROUND (PI, 2026-10-13), beside `workflow_state_offline_r{RR}.json` and
sharing its `{RR}` -- a round is the unit of work (its own parameter list, base, ensemble, cycles),
and ITS simulation table is a property of that round, not a running total across rounds. A single
shared file meant a later round's write could date an earlier, finished round's record: measured
the morning this was found, one write to register a round-2 gate moved the file's one `_last_updated`
to that day, which a naive reading would have called a reconciliation of round 1's long-settled
rows too. Splitting the file removes the question rather than re-wording it: `_last_updated` is now
true of the round it is IN. Details: `memory/dev_logs_adapterkit/20261013f_*`.

WHY IT EXISTS. The same content was being carried by hand in a caption section of each cycle's
cumulative figure. It was written for cycles c00 through c08 and then silently stopped: ten
consecutive captions omitted it and nothing noticed, because a hand-written section has no checker.
Every field below is already produced by Phase 5 today -- the build writes the parameter values, the
submit writes the job ids, the watcher polls the state every couple of minutes, and the scorer
writes the results -- so this adds a destination rather than new measurement.

STATUS IS THE MODEL'S VERDICT, NOT THE SCHEDULER'S. `completed` means the model's own success check
passed. A job the scheduler calls COMPLETED that left no usable output tape is `failed`, and
recording it otherwise is how a truncated run scores as real
([[feedback_never_parse_a_cli_default_output]]). `tools/model_ensemble_status.py` already
reconciles the two; pass its verdict here rather than `sacct`'s.

THE TABLE IS WRITTEN WITH THE LEDGER. Every write through `save()` also regenerates
`memory/SIMULATIONS_r{RR}.md`, the per-case table, so the two cannot disagree and nobody has to
remember a second command. `table --per-case --out` still exists for printing or for a copy
elsewhere.

WHERE A RUN IS. A record carries `run_dir` (one simulation's directory) or `run_root` (a whole
submission's root, for the one-row-per-submission form a pilot, gate or rerun uses, optionally
narrowed by `case_prefix` / `case_range`). That is what lets `settle` read the model's verdict
and `check` know which case directories a row covers. `tools/submit_run.py` records both at
submit time; the account of why is `memory/dev_logs_adapterkit/20261014a_*`.

USAGE. `--round` is now REQUIRED on every subcommand -- it selects the file, not a filter over
one shared file.

    # submit AND register in one step (the normal route; it calls `upsert` itself)
    python tools/submit_run.py --case-dir <dir> --round 2 --cycle 0 --case <name> \
        --purpose ... --differences ... --binary <archived exe> --run-dir <dir> -- <script.sh>

    # when a job ends: the model's verdict for every open record whose job is terminal
    python tools/record_run_status.py settle --case-dir <dir> --round 2 [--job-id J]

    # at build / submit / poll / score -- idempotent on (round, case)
    python tools/record_run_status.py upsert --case-dir <dir> --round 1 --cycle 19 \
        --case TeRaCONc19_5 --status submitted --job-id 58070165 [--field k=v ...]

    # fold an entire cycle in from its Phase-5 rung/arms data file
    python tools/record_run_status.py from-ladder --case-dir <dir> --round 1 --cycle 19 \
        --data <phase_results/{stem}/R1_c19_ladder.data.json> --stem <stem> [--status completed]

    python tools/record_run_status.py list --case-dir <dir> --round 1 [--cycle 19]

Author: Jing Tao with Claude on Perlmutter
"""
from __future__ import annotations

import argparse
import json
import os
import pathlib
import subprocess
import sys
from datetime import datetime

#: The vocabulary. `restarted` is a state rather than an event so a case that needed a relaunch is
#: visibly different from one that ran once; `void` is for a rung excluded from every reading
#: (below the model's viability floor), which is not the same as `failed`.
STATUSES = ("pending", "submitted", "running", "completed", "failed", "restarted", "void")

#: PER ROUND, `run_records_r{RR:02d}.json`. `{RR}` matches `workflow_state_offline_r{RR}.json`'s.
#: The legacy single-file name is `_LEGACY_FILENAME` below, kept only so a stale file is DETECTED
#: and refused rather than silently read as empty.
FILENAME = "run_records_r{round:02d}.json"
_LEGACY_FILENAME = "run_records.json"
#: The generated per-case table, beside the ledger and keyed by the same round.
TABLE_FILENAME = "SIMULATIONS_r{round:02d}.md"
#: A record that is still waiting on the scheduler. `settle` resolves these; the Stop hook asks
#: about them.
OPEN_STATUSES = ("submitted", "running", "pending")


def store_path(case_dir: str, round_: int) -> pathlib.Path:
    d = pathlib.Path(case_dir) / "memory"
    if not d.is_dir():
        raise SystemExit("ERROR: no memory/ under %s -- is this a use_cases/<Model>_<Case> dir?"
                         % case_dir)
    legacy = d / _LEGACY_FILENAME
    if legacy.exists():
        raise SystemExit(
            f"ERROR: {legacy} is the pre-2026-10-13 single-file ledger. Migrate it to one "
            f"run_records_r<NN>.json per round before using this tool again -- see "
            f"memory/dev_logs_adapterkit/20261013f_*.md. Refusing to read or write beside it.")
    return d / FILENAME.format(round=round_)


def load(case_dir: str, round_: int) -> dict:
    p = store_path(case_dir, round_)
    if not p.exists():
        return {
            "_comment": ("RUN LEDGER for this case: its TESTING and PILOT runs. A RECORD, not curated knowledge -- "
                         "written by whichever phase launched the run (Phase-5 experiments, Phase-0 pilots and gates) "
                         "and NOT behind the Tier-3 write gate. Interpreted knowledge (hypothesis, lesson, do-not- "
                         "repeat) belongs in memory/gained_knowledge/experiments.json, which IS gated. A full ensemble's "
                         "thousands of cases are NOT tabulated here; their record is that phase stem's armed monitors "
                         "and watchers. So one row may stand for a whole pilot SUBMISSION rather than one simulation."),
            "_schema_version": "1.0",
            "_status_vocabulary": list(STATUSES),
            "_status_note": ("`completed` means the MODEL's own success check passed. A scheduler "
                             "COMPLETED with no usable output tape is `failed`."),
            "records": [],
        }
    return json.loads(p.read_text())


def save(case_dir: str, round_: int, data: dict) -> pathlib.Path:
    """Write the ledger AND regenerate its table, so no writer can leave the two apart."""
    p = store_path(case_dir, round_)
    data["_last_updated"] = datetime.now().isoformat(timespec="seconds")
    p.write_text(json.dumps(data, indent=1) + "\n")
    table_path(case_dir, round_).write_text(render_table(data, round_))
    return p


def table_path(case_dir: str, round_: int) -> pathlib.Path:
    return pathlib.Path(case_dir) / "memory" / TABLE_FILENAME.format(round=round_)


def render_table(data: dict, round_: int, cycle=None, banner: bool = True) -> str:
    """The per-case table, ONE ROW PER SIMULATION (or per submission, for a submission row).

    The per-cycle aggregate (`table` without --per-case) answers "how did the round progress";
    it collapses a set of hand-designed test arms into a single row, which is the wrong shape for
    the question a test campaign actually asks -- what ran, from what, under which binary, and
    where did it get to.
    """
    rows = [r for r in data["records"] if cycle is None or r.get("cycle") == cycle]
    rows.sort(key=lambda r: (r.get("round") or 0, r.get("cycle") or 0, r.get("case") or ""))
    L = []
    if banner:
        L += [f"# Simulations: round {round_}", "",
              f"**GENERATED FILE. Do not edit.** Source of truth is "
              f"`memory/{FILENAME.format(round=round_)}`. `tools/record_run_status.py` rewrites "
              f"this file on every write to the ledger; editing it by hand guarantees it will "
              f"disagree with the ledger, which is worse than not having it.", "",
              # SAY WHAT THE FIELD IS. `_last_updated` is bumped by EVERY writer, so it dates a
              # write, not a reconciliation against the scheduler.
              f"Ledger last written on **{(data.get('_last_updated') or 'unknown')[:10]}**. "
              f"Statuses are reconciled against the scheduler and the model's own success "
              f"check by `record_run_status.py settle` and `refresh`, which this line does not "
              f"date.", ""]
    L += ["| round | cycle | case | status | job | binary | purpose | differences |",
          "|---|---|---|---|---|---|---|---|"]
    for r in rows:
        L.append("| %s | %s | `%s` | %s | %s | %s | %s | %s |" % (
            r.get("round", "-"),
            ("c%02d" % r["cycle"]) if isinstance(r.get("cycle"), int) else "-",
            r.get("case", "-"), _status_cell(r), r.get("job_id") or "-",
            r.get("binary") or "-",
            (r.get("purpose") or "-").replace("|", "\\|").replace("\n", " "),
            (r.get("differences") or "-").replace("|", "\\|").replace("\n", " ")))
    L += ["", "%d simulation(s). `status` is the MODEL's verdict, not the scheduler's: a "
          "scheduler COMPLETED that left no usable output tape is `failed`. A submission row "
          "carries its per-case counts beside the status." % len(rows)]
    return "\n".join(L) + "\n"


def _status_cell(r: dict) -> str:
    s = r.get("status", "-")
    if isinstance(r.get("n_cases"), int):
        s += " (%s/%s ok)" % (r.get("n_completed", "?"), r["n_cases"])
    return s


def upsert(data: dict, rnd: int, case: str, **fields) -> tuple[dict, bool]:
    """Idempotent on (round, case). Returns (record, created)."""
    for r in data["records"]:
        if r.get("round") == rnd and r.get("case") == case:
            r.update({k: v for k, v in fields.items() if v is not None})
            r["updated_at"] = datetime.now().isoformat(timespec="seconds")
            return r, False
    rec = {"round": rnd, "case": case}
    rec.update({k: v for k, v in fields.items() if v is not None})
    rec["updated_at"] = datetime.now().isoformat(timespec="seconds")
    data["records"].append(rec)
    return rec, True


def _kv(pairs):
    out = {}
    for p in pairs or []:
        if "=" not in p:
            raise SystemExit("ERROR: --field expects k=v, got %r" % p)
        k, v = p.split("=", 1)
        try:
            out[k] = json.loads(v)
        except json.JSONDecodeError:
            out[k] = v
    return out


# ---------------------------------------------------------------- scheduler truth
#: A CASE IS NOT CREATED UNTIL IT IS REGISTERED, and its status comes from the SCHEDULER, never
#: from memory. Every other subcommand here is a WRITE someone must remember to call, so without
#: these two the ledger is only ever as complete as the last person to touch it.
#:
#: `refresh` does NOT read sacct itself. It delegates to `tools/model_ensemble_status.scan()`,
#: which reconciles the scheduler state with the model's OWN success check -- the rule this file's
#: header states, that a scheduler COMPLETED leaving no usable output tape is `failed`. One
#: reconciliation shared with the watcher; a second copy here would be a second contract to drift.
#: Account: memory/dev_logs_adapterkit/20261010d_A_Case_Is_Not_Created_Until_It_Is_Registered.md
_SCAN_TO_LEDGER = {"COMPLETED": "completed", "FAILED": "failed",
                   "RUNNING": "running", "PENDING": "submitted"}


def _scan_rows(model: str, run_root: str):
    """(case_name -> (job_id, slurm_state, scan_status, reason)) from the shared reconciliation."""
    sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
    from tools.model_ensemble_status import scan
    rows = scan(model, pathlib.Path(run_root))
    return {name: (jid, slurm, status, reason) for name, jid, slurm, status, reason in rows}


def cmd_refresh(args) -> int:
    data = load(args.case_dir, args.round)
    seen = _scan_rows(args.model, args.run_root)
    changed = unmatched = 0
    for r in data["records"]:
        # No round filter here: every record in this file IS round `args.round`, by construction
        # of a per-round file. A leftover `r.get("round") != args.round` filter would be DEAD
        # code asserting something the file layout already guarantees.
        hit = seen.get(r.get("case", ""))
        if hit is None:
            unmatched += 1
            continue
        jid, slurm, scan_status, reason = hit
        new = _SCAN_TO_LEDGER.get(scan_status)
        if new is None:                      # UNKNOWN -- say nothing rather than guess
            continue
        before = r.get("status")
        # A `void` or `restarted` record is a HUMAN judgement about the run, not a scheduler
        # state, so refresh must not overwrite it -- that is the "stale id kept forever" mistake
        # inverted: here the risk is a machine erasing a deliberate annotation.
        if before in ("void", "restarted"):
            continue
        r["slurm_state"] = slurm
        if jid and not r.get("job_id"):
            r["job_id"] = jid
        if reason:
            r["fail_reason"] = reason
        if before != new:
            r["status"] = new
            r["updated_at"] = datetime.now().isoformat(timespec="seconds")
            changed += 1
            print(f"  {r['case']:28s} {before or '-':10s} -> {new}")
    save(args.case_dir, args.round, data)
    print(f"  refreshed: {changed} status change(s); {unmatched} record(s) not under this run root")
    return 0


def _resolved(p) -> str:
    try:
        return str(pathlib.Path(p).resolve())
    except Exception:
        return str(p)


def _row_covers(row: dict, name: str) -> bool:
    """Does a submission row (one with `run_root`) cover the case directory `name`?"""
    pre = row.get("case_prefix")
    if pre and not name.startswith(pre):
        return False
    rng = row.get("case_range")
    if rng:
        sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
        from tools.model_ensemble_status import case_index, parse_case_range
        lo, hi = parse_case_range(str(rng))
        idx = case_index(name)
        if idx is None or not (lo <= idx <= hi):
            return False
    return True


def cmd_check(args) -> int:
    data = load(args.case_dir, args.round)
    seen = _scan_rows(args.model, args.run_root)
    recs = {r.get("case"): r for r in data["records"]}
    errors, warns = [], []

    # A row may stand for a whole SUBMISSION (the ledger's own header says so): `run_root` names
    # the root it covers. A per-case record may also name its directory in `run_dir`, which is how
    # a probe whose record name differs from its directory name is found.
    root = _resolved(args.run_root)
    subs = [r for r in data["records"] if r.get("run_root") and _resolved(r["run_root"]) == root]
    run_dirs = {_resolved(r["run_dir"]) for r in data["records"] if r.get("run_dir")}

    # (1) THE RULE: a case that actually ran and is not registered.
    retired = set(data.get("_retired_cases", []))
    for name, (jid, slurm, status, _reason) in sorted(seen.items()):
        if name in recs or name in retired:
            continue
        if _resolved(pathlib.Path(args.run_root) / name) in run_dirs:
            continue
        if any(_row_covers(s, name) for s in subs):
            continue
        errors.append(f"UNREGISTERED: {name} has a run directory (job={jid or '-'}, "
                      f"{status}) and no ledger record. Register it: record_run_status.py upsert "
                      f"--round <N> --case {name} --purpose ... --differences ... (or one row for "
                      f"the whole submission with --run-root)")

    # (1b) a settled submission row whose completed count disagrees with the case directories.
    for s in subs:
        if s.get("status") in OPEN_STATUSES or not isinstance(s.get("n_completed"), int):
            continue
        n_ok = sum(1 for name, row in seen.items()
                   if _row_covers(s, name) and row[2] == "COMPLETED")
        if n_ok != s["n_completed"]:
            errors.append(f"DRIFT: submission row {s['case']} records n_completed="
                          f"{s['n_completed']}, the case directories show {n_ok} -- run `settle`")

    # (2) a recorded status that disagrees with the scheduler + model check.
    for name, r in sorted(recs.items()):
        hit = seen.get(name)
        if hit is None:
            continue
        want = _SCAN_TO_LEDGER.get(hit[2])
        if want and r.get("status") not in (want, "void", "restarted"):
            errors.append(f"DRIFT: {name} recorded {r.get('status')!r}, reconciliation says "
                          f"{want!r} (slurm={hit[1]}) -- run `refresh`")

    # (3) reproducibility fields the sibling skill found load-bearing.
    for name, r in sorted(recs.items()):
        if not r.get("job_id") and r.get("status") not in ("pending", "void"):
            warns.append(f"{name}: no job_id recorded")
        if not r.get("differences"):
            warns.append(f"{name}: no `differences` -- how this case departs from the base is "
                         f"what makes it reproducible; a vague or absent one makes it not")

    for e in errors:
        print(f"  ERROR  {e}")
    for w in warns:
        print(f"  warn   {w}")
    if not errors and not warns:
        print("\nok, no problems found")
    else:
        print(f"\n{len(errors)} error(s), {len(warns)} warning(s)")
    return 2 if errors else 0


def _job_states(job_ids) -> dict:
    """{job_id: bare state} for the named jobs in ONE sacct call. An array or a multi-row job is
    terminal only when every row is; an unreadable or absent job maps to "" (not terminal)."""
    sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
    from tools.model_ensemble_status import normalize_state, _TERMINAL
    ids = sorted({str(j) for j in job_ids if str(j)[:1].isdigit()})
    if not ids:
        return {}
    try:
        out = subprocess.run(["sacct", "-j", ",".join(ids), "-X", "-P", "-n", "-o", "JobID,State"],
                             capture_output=True, text=True, timeout=60).stdout
    except Exception:
        return {j: "" for j in ids}
    seen: dict = {}
    for line in out.splitlines():
        if "|" not in line:
            continue
        jid, st = line.split("|", 1)
        base = jid.split("_")[0].split(".")[0]
        seen.setdefault(base, set()).add(normalize_state(st))
    res = {}
    for j in ids:
        s = seen.get(j, set())
        if not s:
            res[j] = ""
        elif s <= _TERMINAL:
            res[j] = sorted(s)[0] if len(s) == 1 else "+".join(sorted(s))
        else:
            res[j] = "ACTIVE"
    return res


def _is_terminal(state: str) -> bool:
    sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
    from tools.model_ensemble_status import _TERMINAL
    return bool(state) and state != "ACTIVE" and set(state.split("+")) <= _TERMINAL


def settle_records(data: dict, model: str, job_id=None, states=None) -> list[str]:
    """Resolve every OPEN record whose job has ended to the MODEL's verdict. Returns a report.

    A single run (`run_dir`) is `completed` only if the model's own success check passes on its
    directory; a submission row (`run_root`) gets its per-case counts and is `completed` when
    every covered case has a model verdict. A job CANCELLED in the scheduler becomes `void`
    with a reason that says the reason itself is still owed. A record with neither location is
    left open and reported: without a directory there is no model verdict to read, and the
    scheduler's word alone is not one.
    """
    sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
    from tools.model_ensemble_status import scan, _fail_reason, parse_case_range
    open_recs = [r for r in data["records"] if r.get("status") in OPEN_STATUSES and r.get("job_id")
                 and (job_id is None or str(r.get("job_id")) == str(job_id))]
    if states is None:
        states = _job_states([r["job_id"] for r in open_recs])
    now = datetime.now().isoformat(timespec="seconds")
    report = []
    for r in open_recs:
        st = states.get(str(r["job_id"]), "")
        if not _is_terminal(st):
            if st == "ACTIVE" and r.get("status") == "submitted":
                r["status"], r["updated_at"] = "running", now
            continue
        r["slurm_state"] = st
        mdl = r.get("model") or model
        if st == "CANCELLED":
            r["status"] = "void"
            r.setdefault("void_reason", "CANCELLED in the scheduler. Why is not known to `settle`; "
                                        "record it with upsert --field void_reason=...")
        elif r.get("run_root"):
            rng = parse_case_range(str(r["case_range"])) if r.get("case_range") else None
            rows = scan(mdl, pathlib.Path(r["run_root"]), rng, True, None, r.get("case_prefix"))
            n_ok = sum(1 for x in rows if x[3] == "COMPLETED")
            n_bad = sum(1 for x in rows if x[3] == "FAILED")
            r.update(n_cases=len(rows), n_completed=n_ok, n_failed=n_bad)
            missing = len(rows) - n_ok - n_bad
            if missing:
                r["status"] = "failed"
                r["fail_mode"] = (f"the submission ended with {missing} of {len(rows)} case(s) "
                                  f"carrying no model verdict (never started, or unreadable)")
            else:
                r["status"] = "completed"
        elif r.get("run_dir"):
            sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
            try:
                import importlib
                from models import registry
                importlib.import_module(f"models.{mdl}")
                verdict = registry.get_model(mdl).check_case_status(pathlib.Path(r["run_dir"]))
            except Exception as exc:    # e.g. the built-in FATES path, which has no models/ backend
                report.append(f"  OPEN   {r['case']:28s} job {r['job_id']} {st}: no model verdict "
                              f"for model {mdl!r} ({type(exc).__name__}); record it with upsert")
                continue
            r["status"] = "completed" if verdict == "COMPLETED" else "failed"
            if r["status"] == "failed":
                reason = _fail_reason(pathlib.Path(r["run_dir"]))
                if reason:
                    r["fail_reason"] = reason
        else:
            report.append(f"  OPEN   {r['case']:28s} job {r['job_id']} {st}: no run_dir or "
                          f"run_root, so no model verdict to read -- add one with upsert")
            continue
        r["updated_at"] = r["settled_at"] = now
        report.append(f"  settled {r['case']:28s} job {r['job_id']} {st} -> {r['status']}")
    return report


def cmd_settle(args) -> int:
    data = load(args.case_dir, args.round)
    rep = settle_records(data, args.model, args.job_id)
    save(args.case_dir, args.round, data)
    print("\n".join(rep) if rep else "  nothing to settle (no open record has a finished job)")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)

    for name in ("upsert", "from-ladder", "from-submits", "list", "table", "refresh", "check",
                 "settle"):
        p = sub.add_parser(name)
        p.add_argument("--case-dir", default=os.environ.get("A2MC_USE_CASE_DIR"),
                       help="the use_cases/<Model>_<Case> dir; default $A2MC_USE_CASE_DIR")
        p.add_argument("--round", type=int, required=True,
                       help="selects the FILE (run_records_r<NN>.json), not a filter")
        if name in ("list", "table", "refresh", "check", "settle"):
            p.add_argument("--cycle", type=int, default=None)
        else:
            p.add_argument("--cycle", type=int, required=True)
        if name in ("refresh", "check"):
            p.add_argument("--run-root", required=True,
                           help="the ensemble/experiment run root holding the per-case dirs")
        if name in ("refresh", "check", "settle"):
            p.add_argument("--model", default=os.environ.get("A2MC_MODEL", "ecosim"))

    st = sub.choices["settle"]
    st.add_argument("--job-id", default=None,
                    help="settle only the record(s) carrying this job id (default: every open "
                         "record whose job has ended)")

    tb = sub.choices["table"]
    tb.add_argument("--per-case", action="store_true",
                    help="one row per SIMULATION (case/status/job/binary/differences) instead of "
                         "the per-cycle aggregate. The per-cycle view answers 'how did the round "
                         "progress'; this one answers 'what exactly ran', which is what a handful "
                         "of hand-designed test arms needs")
    tb.add_argument("--out", default=None,
                    help="write the per-case table to PATH as a GENERATED file (banner included) "
                         "instead of printing it")

    u = sub.choices["upsert"]
    u.add_argument("--case", required=True)
    u.add_argument("--status", choices=STATUSES, default=None)
    u.add_argument("--job-id", default=None)
    u.add_argument("--stem", default=None)
    u.add_argument("--purpose", default=None, help="why this case exists")
    u.add_argument("--differences", default=None,
                   help="how it departs from the base: '<base> EXCEPT <what> = <value>'. The field "
                        "that makes the case reproducible -- never leave it vague")
    u.add_argument("--binary", default=None, help="the archived binary this run was bound to")
    u.add_argument("--run-dir", default=None,
                   help="this simulation's directory, where `settle` reads the model's verdict")
    u.add_argument("--run-root", default=None,
                   help="for ONE ROW PER SUBMISSION: the root holding the submission's case dirs "
                        "(narrow it with --field case_prefix=... / case_range=LO-HI)")
    u.add_argument("--field", action="append", help="extra k=v (JSON value if parseable)")

    f = sub.choices["from-ladder"]
    f.add_argument("--data", required=True, help="a Phase-5 rungs/arms data JSON")
    f.add_argument("--stem", default=None)
    f.add_argument("--status", choices=STATUSES, default=None,
                   help="status to stamp on every case the file names")
    f.add_argument("--experiment", default=None)

    #: `from-submits` reads the case ids out of a cycle's ARCHIVED submit_scripts/ (phase5-testing
    #: step 2b makes that archive a contract), so a cycle whose scoring artifact was free-form text
    #: still lands its case list and job ids in the ledger. It records WHICH SIMULATIONS RAN and
    #: deliberately records no scores: a score parsed out of a bespoke report is a number this tool
    #: would be AUTHORING rather than recording ([[feedback_verify_run_state_before_quoting]]).
    g = sub.choices["from-submits"]
    g.add_argument("--submit-dir", required=True, help="a cycle's phase_results/{stem}/submit_scripts/")
    g.add_argument("--stem", default=None)
    g.add_argument("--job-ids", default=None, help="optional job_ids.txt from the same stem")
    g.add_argument("--status", choices=STATUSES, default="completed")
    g.add_argument("--experiment", default=None)

    a = ap.parse_args()
    if not a.case_dir:
        raise SystemExit("ERROR: no --case-dir and no $A2MC_USE_CASE_DIR. Refusing to guess.")
    data = load(a.case_dir, a.round)

    if a.cmd == "refresh":
        return cmd_refresh(a)
    if a.cmd == "check":
        return cmd_check(a)
    if a.cmd == "settle":
        return cmd_settle(a)

    if a.cmd == "table" and getattr(a, "per_case", False):
        text = render_table(data, a.round, a.cycle, banner=bool(a.out))
        n = sum(1 for r in data["records"] if a.cycle is None or r.get("cycle") == a.cycle)
        if a.out:
            pathlib.Path(a.out).write_text(text)
            print("wrote %s (%d simulation(s))" % (a.out, n))
        else:
            print(text)
        return 0

    if a.cmd == "table":
        # The per-cycle roster, EMITTED rather than typed. It used to be a hand-written section in
        # each cycle's figure caption, and it stopped being written for ten consecutive cycles with
        # nothing noticing. Generating it from the ledger binds it to its source, so the caption and
        # the record cannot drift apart ([[feedback_bind_derived_facts_to_their_source]]).
        rows = list(data["records"])  # the file already IS this round
        by = {}
        for r in rows:
            by.setdefault(r.get("cycle"), []).append(r)
        print("| cycle | cases | tags | dead | scored |")
        print("|---|---|---|---|---|")
        for c in sorted(by, key=lambda x: (x is None, x)):
            rs = sorted(by[c], key=lambda x: x.get("case", ""))
            tags = ", ".join(r.get("tag") or "-" for r in rs)
            dead = sum(1 for r in rs if r.get("alive") is False)
            scored = sum(1 for r in rs if r.get("scored"))
            print("| c%02d | %d | %s | %d | %d |" % (c, len(rs), tags, dead, scored))
        print()
        print("%d simulation(s) across %d cycle(s), from `use_cases/.../memory/%s`."
              % (len(rows), len(by), FILENAME.format(round=a.round)))
        return 0

    if a.cmd == "list":
        rows = [r for r in data["records"]
                if a.cycle is None or r.get("cycle") == a.cycle]
        print("%-18s %5s %5s %-11s %-12s %s" % ("case", "round", "cycle", "status", "job", "scored"))
        for r in sorted(rows, key=lambda x: (x.get("cycle", -1), x.get("case", ""))):
            s = r.get("scored") or {}
            sc = ("NPP %.1f pC %.1f Fs %.3f" % (s["NPP"], s["plant_C"], s["Fs"])
                  if {"NPP", "plant_C", "Fs"} <= set(s) else "-")
            print("%-18s %5s %5s %-11s %-12s %s" % (r.get("case"), r.get("round"), r.get("cycle"),
                                                    r.get("status", "?"), r.get("job_id", "-"), sc))
        print("\n%d record(s)" % len(rows))
        return 0

    rnd = a.round  # required; selects the FILE, so it is never a default

    if a.cmd == "upsert":
        rec, created = upsert(data, rnd, a.case, cycle=a.cycle, status=a.status,
                              job_id=a.job_id, stem=a.stem, purpose=a.purpose,
                              differences=a.differences, binary=a.binary, run_dir=a.run_dir,
                              run_root=a.run_root, **_kv(a.field))
        p = save(a.case_dir, a.round, data)
        print("%s %s (round %d cycle %d) -> %s" %
              ("created" if created else "updated", a.case, rnd, a.cycle, p))
        return 0

    if a.cmd == "from-submits":
        d = pathlib.Path(a.submit_dir)
        # FOUR conventions are in use in real archives, and the case token can sit on EITHER side
        # of the word "submit":
        #     <case>_submit.sh   <case>.submit.sh   submit_<case>.sh   submit.<case>.sh
        # This originally matched only the two SUFFIX forms, and EcoSIM_Lusignan archives with the
        # PREFIX form, so a backfill across fifteen cycles found nothing and raised fifteen times
        # (2026-09-09). The failure was loud, which is the one thing that went right; a glob that
        # silently returns an empty set is [[feedback_exact_strings_are_contracts]].
        # A bare `submit.sh` carries no case token at all and is skipped rather than yielding "".
        def _case_token(name: str) -> str:
            stem = name[: -len(".sh")]
            for sep in ("_", "."):
                if stem.endswith(sep + "submit"):
                    return stem[: -len(sep + "submit")]
                if stem.startswith("submit" + sep):
                    return stem[len("submit" + sep):]
            return ""

        cases = sorted({t for t in (_case_token(f.name) for f in d.glob("*submit*.sh")) if t})
        if not cases:
            raise SystemExit(
                "ERROR: no submit script with a case token under %s\n"
                "  Looked for <case>_submit.sh, <case>.submit.sh, submit_<case>.sh, "
                "submit.<case>.sh\n  Found: %s"
                % (d, sorted(f.name for f in d.glob("*.sh")) or "nothing"))
        jobs = {}
        if a.job_ids and pathlib.Path(a.job_ids).exists():
            for line in pathlib.Path(a.job_ids).read_text().split():
                if line.strip().isdigit():
                    jobs.setdefault("_ordered", []).append(line.strip())
        ordered = jobs.get("_ordered", [])
        n_new = 0
        for i, case in enumerate(cases):
            _, created = upsert(data, rnd, case, cycle=a.cycle, stem=a.stem,
                                status=a.status, experiment=a.experiment,
                                job_id=(ordered[i] if i < len(ordered) else None),
                                provenance="submit_scripts archive")
            n_new += int(created)
        p = save(a.case_dir, a.round, data)
        print("cycle %d: %d case(s) from %s, %d new -> %s" % (a.cycle, len(cases), d, n_new, p))
        return 0

    # from-ladder
    j = json.loads(pathlib.Path(a.data).read_text())
    entries = j.get("rungs") or j.get("arms") or []
    if not entries:
        raise SystemExit("ERROR: %s carries neither `rungs` nor `arms`" % a.data)
    n_new = 0
    for e in entries:
        case = e.get("case")
        if not case:
            continue
        fields = {"cycle": a.cycle, "tag": e.get("tag"), "stem": a.stem,
                  "experiment": a.experiment, "status": a.status,
                  "provenance": pathlib.Path(a.data).name}
        if e.get("scores"):
            fields["scored"] = e["scores"]
        if e.get("multipliers"):
            fields["multipliers"] = e["multipliers"]
        if "dose" in e:
            fields["dose"] = e["dose"]
        if "usable" in e:
            fields["usable"] = e["usable"]
        if "alive" in e:
            fields["alive"] = e["alive"]
        if "tau" in e:
            fields["tau"] = e["tau"]
        if e.get("dir"):
            fields["run_dir"] = e["dir"]
        _, created = upsert(data, rnd, case, **fields)
        n_new += int(created)
    p = save(a.case_dir, a.round, data)
    print("cycle %d: %d case(s) from %s, %d new -> %s"
          % (a.cycle, len(entries), pathlib.Path(a.data).name, n_new, p))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
