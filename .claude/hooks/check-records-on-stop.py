#!/usr/bin/env python3
"""Stop hook -- do not end a turn with a case's run ledger, table or offline state behind its work.

visibility: public

WHY AT THE END OF A TURN. The run ledger, the table generated from it and the offline state's
decisions are written after the work they describe, so each depends on being remembered; the end of
a turn is the last moment the agent can still act on a reminder. The account is
`memory/dev_logs_adapterkit/20261014a_*`.

WHAT IT CHECKS, for each case THIS SESSION TOUCHED (a commit since the session started, or an
uncommitted change under `use_cases/<case>/`):

  1. RUNS NOT SETTLED. A ledger record still `submitted`/`running` whose scheduler job has ended,
     and which names a `run_dir` or `run_root` (so `record_run_status.py settle` can read the
     model's verdict). One `sacct` call covers every such job.
  2. TABLE BEHIND ITS LEDGER. `memory/SIMULATIONS_r{RR}.md` differs from what the ledger renders.
     `record_run_status.py` rewrites the table on every save, so this means a hand edit.
  3. A MODEL-EVOLUTION RECORD NEWER THAN THE STATE. A record under `memory/model_evolution/`
     modified during this session after the newest decision in the case's active offline state.
     The calibration loop already keeps the state current; model-evolution work is where it fell
     behind, so that is what this asks about.

WHAT IT DOES. Any finding blocks the stop once, with the commands that fix it, as
`{"decision": "block", "reason": ...}`. When Claude Code is already continuing because of a stop
hook (`stop_hook_active`), it does not block again: the reason has been delivered, and blocking on
a condition the agent cannot resolve in-turn (a peer session's record, an unreadable scheduler)
would only loop. Any internal error exits 0 silently: a broken check must never trap a session.

Author: Jing Tao with Claude
"""
import json
import os
import re
import subprocess
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(os.environ.get("CLAUDE_PROJECT_DIR") or Path(__file__).resolve().parents[2])
sys.path.insert(0, str(ROOT))


def _reexec_if_old():
    """The hook is registered as `python3`, which on some machines is older than the tools it
    imports (they need 3.8). Re-run under the project's interpreter, found the way the pre-commit
    hook's `pick_py` finds it; with none available, return False and the hook stays silent."""
    if sys.version_info >= (3, 8):
        return True
    if os.environ.get("A2MC_STOP_HOOK_REEXEC"):
        return False
    for cand in (os.environ.get("A2MC_PYTHON", ""),
                 os.path.expanduser("~/a2mc_env/bin/python3"),
                 os.path.join(os.environ.get("A2MC_VENV", ""), "bin", "python3")):
        if cand and os.path.isfile(cand) and os.access(cand, os.X_OK):
            os.environ["A2MC_STOP_HOOK_REEXEC"] = "1"
            os.execv(cand, [cand, os.path.abspath(__file__)])
    return False


def _git(*args) -> str:
    try:
        return subprocess.run(["git", "-C", str(ROOT)] + list(args), capture_output=True,
                              text=True, timeout=20).stdout
    except Exception:
        return ""


def session_start(transcript_path: str):
    """The first timestamp in the session transcript (UTC, as written), or None."""
    try:
        with open(transcript_path) as fh:
            for _ in range(50):
                line = fh.readline()
                if not line:
                    break
                ts = (json.loads(line) or {}).get("timestamp")
                if ts:
                    return datetime.fromisoformat(ts.replace("Z", "+00:00"))
    except Exception:
        pass
    return None


def touched_cases(since) -> set:
    cases = set()
    for line in _git("status", "--porcelain", "--", "use_cases").splitlines():
        m = re.search(r"use_cases/([^/\s]+)/", line)
        if m:
            cases.add(m.group(1))
    if since is not None:
        out = _git("log", "--since", since.isoformat(), "--name-only", "--format=", "--",
                   "use_cases")
        cases |= {m.group(1) for m in re.finditer(r"^use_cases/([^/\s]+)/", out, re.M)}
    return {c for c in cases if (ROOT / "use_cases" / c / "memory").is_dir()}


def _rounds(case: str, prefix: str):
    out = []
    for p in (ROOT / "use_cases" / case / "memory").glob(prefix + "_r*.*"):
        m = re.search(r"_r(\d+)\.", p.name)
        if m:
            out.append((int(m.group(1)), p))
    return sorted(out)


def _rows(text: str) -> list:
    """The table's rows only. The banner is prose that may be reworded between versions; the rows
    are the content that must agree with the ledger."""
    return [l for l in text.splitlines() if l.startswith("| ")]


def check_runs_and_tables(cases) -> list:
    from tools import record_run_status as rrs
    problems, pending = [], []
    for case in sorted(cases):
        for rnd, p in _rounds(case, "run_records"):
            try:
                data = json.loads(p.read_text())
            except Exception:
                continue
            tp = rrs.table_path(str(ROOT / "use_cases" / case), rnd)
            if tp.exists() and _rows(tp.read_text()) != _rows(rrs.render_table(data, rnd)):
                problems.append(f"{case} r{rnd:02d}: {tp.name} no longer matches its ledger (a hand "
                                f"edit?). Regenerate: python tools/record_run_status.py table "
                                f"--per-case --case-dir use_cases/{case} --round {rnd} --out {tp}")
            for r in data.get("records", []):
                if (r.get("status") in rrs.OPEN_STATUSES and r.get("job_id")
                        and (r.get("run_dir") or r.get("run_root"))):
                    pending.append((case, rnd, r))
    if pending:
        states = rrs._job_states([r["job_id"] for _, _, r in pending])
        done = {}
        for case, rnd, r in pending:
            st = states.get(str(r["job_id"]), "")
            if rrs._is_terminal(st):
                done.setdefault((case, rnd), []).append(f"{r['case']} (job {r['job_id']}, {st})")
        for (case, rnd), names in sorted(done.items()):
            problems.append(f"{case} r{rnd:02d}: {len(names)} run(s) ended but are still open in the "
                            f"ledger: {', '.join(names)}. Settle them: python "
                            f"tools/record_run_status.py settle --case-dir use_cases/{case} "
                            f"--round {rnd}")
    return problems


def check_state(cases, since) -> list:
    from tools.check_workflow_state_offline import newest_decision_time
    problems = []
    for case in sorted(cases):
        rs = _rounds(case, "workflow_state_offline")
        if not rs:
            continue
        rnd, sp = rs[-1]
        try:
            st = json.loads(sp.read_text())
        except Exception:
            continue
        if st.get("converged"):
            continue
        newest = newest_decision_time(st.get("decisions"))
        try:
            t_dec = datetime.fromisoformat(newest).timestamp() if newest else 0.0
        except ValueError:
            t_dec = 0.0
        t_ses = since.timestamp() if since is not None else 0.0
        me = ROOT / "use_cases" / case / "memory" / "model_evolution"
        # `at` is recorded to the second while mtime is sub-second, so a record written in the
        # same second as its decision would otherwise read as newer; one second is that resolution.
        late = sorted(p.name for p in me.glob("*.md")
                      if p.name != "README.md" and p.stat().st_mtime > max(t_dec + 1.0, t_ses))
        if late:
            problems.append(f"{case}: model-evolution record(s) changed after the newest decision in "
                            f"{sp.name} ({newest or 'none'}): {', '.join(late)}. Record what they "
                            f"establish: WorkflowStateOffline.load(calibration_round={rnd}, "
                            f"site_dir='use_cases/{case}').add_decision(finding, rationale).save()")
    return problems


def main() -> int:
    if not _reexec_if_old():
        return 0
    try:
        payload = json.load(sys.stdin)
    except Exception:
        return 0
    if payload.get("stop_hook_active"):
        return 0
    try:
        since = session_start(payload.get("transcript_path") or "")
        cases = touched_cases(since)
        if not cases:
            return 0
        problems = check_runs_and_tables(cases) + check_state(cases, since)
    except Exception:
        return 0
    if not problems:
        return 0
    reason = ("The case records are behind the work this session did. Bring them up to date "
              "before ending the turn:\n- " + "\n- ".join(problems) +
              "\n(Contract: .claude/hooks/check-records-on-stop.py)")
    json.dump({"decision": "block", "reason": reason}, sys.stdout)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
