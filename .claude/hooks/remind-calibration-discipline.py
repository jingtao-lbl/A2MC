#!/usr/bin/env python3
"""PostToolUse hook: the offline calibration loop just moved, and the bookkeeping may not have.

Why this exists
---------------
`calibration-discipline` is a per-cycle checklist, i.e. a CONDITIONAL instruction whose condition
becomes true repeatedly during a session. That is the same shape `remind-arm-monitoring.py` and
`remind-setup-stage.py` exist for: the moment it becomes true goes unobserved.

TWO triggers, and the second is the one that matters
---------------------------------------------------
A. **The state file was written** -> validate it immediately (`check_workflow_state_offline.py`).
   A corrupt state is worse than none: the resume brain is what a cold session trusts.

B. **Phase work landed and the state did NOT follow.** Keying only on (A) would make this hook blind
   to the exact failure it should catch -- an agent that forgets to update the state never triggers a
   hook that watches state writes. So (B) watches the WORK (a `phase{N}` log, a `phase_results/`
   artifact) and compares the newest artifact against the state's `updated_at`.

Why `updated_at` and not the phase number
-----------------------------------------
Comparing the log's `phase{N}` to `current_phase` looks obvious and is wrong: a legitimate Phase-6 ->
Phase-0 redesign moves the phase BACKWARDS, so "log says 6, state says design" is a normal, correct
state. Measured on EcoSIM_BioCON R3, which is exactly that case. Timestamps do not have that
ambiguity: an artifact dated after the last state write means work landed and the state did not
follow, whatever direction the loop moved.

NOISE IS THE FAILURE MODE. Calibration is the main working loop, unlike setup, so this fires only
when something is actually WRONG -- never "here is your checklist". Silent when the discipline was
followed, silent when there is no offline campaign at all.

Never blocks. Never raises.

Author: Jing Tao with Claude
"""
import json
import os
import re
import sys

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
STAMP = os.path.join(REPO, ".claude", ".last_calibration_reminder")

STATE_RE = re.compile(r"use_cases/[^/]+/memory/workflow_state_offline_r\d+\.json$", re.I)
WORK_RE = re.compile(
    r"use_cases/[^/]+/memory/logs/.*phase\d.*\.md$"       # a phase log
    r"|use_cases/[^/]+/memory/phase_results/",             # a phase_results artifact
    re.I)
STEM_DATE_RE = re.compile(r"(20\d{6})")
WRITE_TOOLS = {"Write", "Edit", "NotebookEdit"}


def _written_path(payload):
    if payload.get("tool_name") not in WRITE_TOOLS:
        return ""
    ti = payload.get("tool_input") or {}
    p = ti.get("file_path") or ti.get("notebook_path") or ""
    return p.replace(os.sep, "/")


def _case_root(path):
    m = re.search(r"(use_cases/[^/]+)/memory/", path)
    return os.path.join(REPO, m.group(1)) if m else ""


def _newest_state(case_root):
    d = os.path.join(case_root, "memory")
    if not os.path.isdir(d):
        return "", {}
    files = sorted(f for f in os.listdir(d)
                   if re.match(r"workflow_state_offline_r\d+\.json$", f))
    if not files:
        return "", {}
    full = os.path.join(d, files[-1])
    try:
        with open(full) as fh:
            return full, json.load(fh)
    except (OSError, ValueError):
        return full, {}


def _newest_work_date(case_root):
    """Newest YYYYMMDD stem across phase logs and phase_results dirs."""
    best = ""
    for sub, is_dir in (("memory/logs", False), ("memory/phase_results", True)):
        d = os.path.join(case_root, sub)
        if not os.path.isdir(d):
            continue
        for name in os.listdir(d):
            if not is_dir and not re.search(r"phase\d", name, re.I):
                continue
            m = STEM_DATE_RE.match(name)
            if m and m.group(1) > best:
                best = m.group(1)
    return best


def _emit(msg):
    print(json.dumps({"hookSpecificOutput": {
        "hookEventName": "PostToolUse", "additionalContext": msg}}))


def _fresh(key):
    """True the first time this exact condition is seen; suppresses repeats."""
    try:
        with open(STAMP) as fh:
            if fh.read().strip() == key:
                return False
    except OSError:
        pass
    try:
        with open(STAMP, "w") as fh:
            fh.write(key)
    except OSError:
        pass
    return True


def main():
    try:
        payload = json.load(sys.stdin)
    except Exception:
        sys.exit(0)
    try:
        resp = payload.get("tool_response") or {}
        if isinstance(resp, dict) and resp.get("success") is False:
            sys.exit(0)
        path = _written_path(payload)
        if not path:
            sys.exit(0)
        case_root = _case_root(path)
        if not case_root or not os.path.isdir(case_root):
            sys.exit(0)

        # --- A. the state was just written -> validate it
        if STATE_RE.search(path):
            import subprocess
            full = os.path.join(REPO, path) if not os.path.isabs(path) else path
            r = subprocess.run(
                [sys.executable, os.path.join(REPO, "tools", "check_workflow_state_offline.py"),
                 "--file", full, "--quiet"],
                capture_output=True, text=True, timeout=30, cwd=REPO)
            # A CRASHED validator is not a failing check. Without this, a missing import or a
            # wrong cwd makes the hook announce "STATE INVALID" over a traceback -- crying wolf
            # about the user's data because our own tool broke. Measured 2026-08-19: a synthetic
            # clone lacking the validator's imports produced exactly that.
            crashed = "Traceback (most recent call last)" in (r.stderr or "")
            if r.returncode != 0 and not crashed and _fresh("stateinvalid:" + os.path.basename(full)):
                _emit("OFFLINE STATE INVALID — the resume brain is what a cold session trusts, so a "
                      "corrupt state is worse than none.\n"
                      + (r.stdout or r.stderr or "").strip()[:600] + "\n"
                      "Fix before the next phase: python3 tools/check_workflow_state_offline.py")
            sys.exit(0)

        # --- B. phase work landed; did the state follow?
        if not WORK_RE.search(path):
            sys.exit(0)
        state_file, state = _newest_state(case_root)
        if not state_file:
            sys.exit(0)                       # no offline campaign here -> not our business
        updated = (state.get("updated_at") or "").replace("-", "")[:8]
        work = _newest_work_date(case_root)
        if not work or not updated or work <= updated:
            sys.exit(0)                       # state kept up, or undatable -> silent

        case = os.path.basename(case_root)
        if _fresh("stale:%s:%s>%s" % (case, work, updated)):
            _emit(
                "PHASE WORK LANDED, STATE NOT UPDATED — `calibration-discipline` item 5.\n"
                "  newest phase artifact: %s   state `updated_at`: %s (%s)\n"
                "The offline state is the resume brain: a cold session reads it to learn where the "
                "loop is, so work it does not record is work the next session cannot see.\n"
                "Write the phase transition into %s, then validate:\n"
                "  python3 tools/check_workflow_state_offline.py"
                % (work, state.get("updated_at"), os.path.basename(state_file),
                   os.path.relpath(state_file, REPO)))
    except Exception:
        pass                                  # a hook must never break a session
    sys.exit(0)


if __name__ == "__main__":
    main()
