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

    use_cases/{Model}_{Case}/memory/run_records.json

beside `workflow_state_offline_r{RR}.json`, which is the other file in that directory that records
rather than curates.

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

USAGE

    # at build / submit / poll / score -- idempotent on (round, case)
    python tools/record_run_status.py upsert --case-dir <dir> --round 1 --cycle 19 \
        --case TeRaCONc19_5 --status submitted --job-id 58070165 [--field k=v ...]

    # fold an entire cycle in from its Phase-5 rung/arms data file
    python tools/record_run_status.py from-ladder --case-dir <dir> --round 1 --cycle 19 \
        --data <phase_results/{stem}/R1_c19_ladder.data.json> --stem <stem> [--status completed]

    python tools/record_run_status.py list --case-dir <dir> [--round 1] [--cycle 19]

Author: Jing Tao with Claude on Perlmutter
"""
from __future__ import annotations

import argparse
import json
import os
import pathlib
from datetime import datetime

#: The vocabulary. `restarted` is a state rather than an event so a case that needed a relaunch is
#: visibly different from one that ran once; `void` is for a rung excluded from every reading
#: (below the model's viability floor), which is not the same as `failed`.
STATUSES = ("pending", "submitted", "running", "completed", "failed", "restarted", "void")

FILENAME = "run_records.json"


def store_path(case_dir: str) -> pathlib.Path:
    d = pathlib.Path(case_dir) / "memory"
    if not d.is_dir():
        raise SystemExit("ERROR: no memory/ under %s -- is this a use_cases/<Model>_<Case> dir?"
                         % case_dir)
    return d / FILENAME


def load(case_dir: str) -> dict:
    p = store_path(case_dir)
    if not p.exists():
        return {
            "_comment": ("Per-simulation RUN LEDGER for this case. A RECORD, not curated knowledge: "
                         "written automatically by Phase 5 and NOT behind the Tier-3 write gate. "
                         "Interpreted knowledge (hypothesis, lesson, do-not-repeat) belongs in "
                         "memory/gained_knowledge/experiments.json, which IS gated."),
            "_schema_version": "1.0",
            "_status_vocabulary": list(STATUSES),
            "_status_note": ("`completed` means the MODEL's own success check passed. A scheduler "
                             "COMPLETED with no usable output tape is `failed`."),
            "records": [],
        }
    return json.loads(p.read_text())


def save(case_dir: str, data: dict) -> pathlib.Path:
    p = store_path(case_dir)
    data["_last_updated"] = datetime.now().isoformat(timespec="seconds")
    p.write_text(json.dumps(data, indent=1) + "\n")
    return p


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


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)

    for name in ("upsert", "from-ladder", "from-submits", "list", "table"):
        p = sub.add_parser(name)
        p.add_argument("--case-dir", default=os.environ.get("A2MC_USE_CASE_DIR"),
                       help="the use_cases/<Model>_<Case> dir; default $A2MC_USE_CASE_DIR")
        p.add_argument("--round", type=int, default=None)
        if name in ("list", "table"):
            p.add_argument("--cycle", type=int, default=None)
        else:
            p.add_argument("--cycle", type=int, required=True)

    u = sub.choices["upsert"]
    u.add_argument("--case", required=True)
    u.add_argument("--status", choices=STATUSES, default=None)
    u.add_argument("--job-id", default=None)
    u.add_argument("--stem", default=None)
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
    data = load(a.case_dir)

    if a.cmd == "table":
        # The per-cycle roster, EMITTED rather than typed. It used to be a hand-written section in
        # each cycle's figure caption, and it stopped being written for ten consecutive cycles with
        # nothing noticing. Generating it from the ledger binds it to its source, so the caption and
        # the record cannot drift apart ([[feedback_bind_derived_facts_to_their_source]]).
        rows = [r for r in data["records"] if a.round is None or r.get("round") == a.round]
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
        print("%d simulation(s) across %d cycle(s), from "
              "`use_cases/.../memory/run_records.json`." % (len(rows), len(by)))
        return 0

    if a.cmd == "list":
        rows = [r for r in data["records"]
                if (a.round is None or r.get("round") == a.round)
                and (a.cycle is None or r.get("cycle") == a.cycle)]
        print("%-18s %5s %5s %-11s %-12s %s" % ("case", "round", "cycle", "status", "job", "scored"))
        for r in sorted(rows, key=lambda x: (x.get("cycle", -1), x.get("case", ""))):
            s = r.get("scored") or {}
            sc = ("NPP %.1f pC %.1f Fs %.3f" % (s["NPP"], s["plant_C"], s["Fs"])
                  if {"NPP", "plant_C", "Fs"} <= set(s) else "-")
            print("%-18s %5s %5s %-11s %-12s %s" % (r.get("case"), r.get("round"), r.get("cycle"),
                                                    r.get("status", "?"), r.get("job_id", "-"), sc))
        print("\n%d record(s)" % len(rows))
        return 0

    rnd = a.round if a.round is not None else 1

    if a.cmd == "upsert":
        rec, created = upsert(data, rnd, a.case, cycle=a.cycle, status=a.status,
                              job_id=a.job_id, stem=a.stem, **_kv(a.field))
        p = save(a.case_dir, data)
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
        p = save(a.case_dir, data)
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
    p = save(a.case_dir, data)
    print("cycle %d: %d case(s) from %s, %d new -> %s"
          % (a.cycle, len(entries), pathlib.Path(a.data).name, n_new, p))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
