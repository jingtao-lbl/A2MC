#!/usr/bin/env python3
"""PostToolUse hook: fire when the SETUP STAGE has just advanced.

Why this exists
---------------
`SessionStart` names the setup stage once, at startup. But setup is a sequence:
`a2mc-init` finishes and the next stage is `onboard-case`; a case is scaffolded
and its parameter list and preflight are next. **The stage that was true at
session start is stale within the hour**, and nothing observes the transition.

That is the identical failure `remind-arm-monitoring.py` was written for, and its
docstring names it exactly: *"the moment the invocation condition became true went
unobserved. This hook observes it."* Setup staging is the same shape one layer
over -- a conditional instruction, correctly evaluated once, never re-evaluated.

Contract
--------
Reads the PostToolUse payload on stdin. If the completed action **crossed a stage
boundary** (a real case scaffolded, a site config / targets.yaml / parameter list
written, a milestone registered), it re-reads the stage from disk and emits a
`systemMessage` naming the skill AND the specific items still outstanding -- taken
from `check_stage_ready.py`'s own rows, never restated here.

It NEVER blocks: every trigger is a normal, desirable action.

Fires on the TRANSITION, not the state. A stamp file records the last stage
reported, so a run of writes inside one stage stays quiet; re-emitting on every
write is the fastest way to train the reader to skip it. The outstanding-item
count is part of the stamp key, so genuine progress *within* a stage is reported
once, and only when the count actually changes.

Deliberately NOT matched: `--dry-run`, `--list`, `--write-script`, reads of any
kind, and this file itself.

Author: Jing Tao with Claude
"""
import json
import os
import re
import sys

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
STAMP = os.path.join(REPO, ".claude", ".last_setup_stage")

# Bash commands that cross a stage boundary.
BASH_RE = re.compile(
    r"\b(?:"
    r"create_use_case\.py"            # a real case now exists -> stage 3
    r"|init_adapter\.py"              # an adapter package now exists -> stage 2 underway
    r"|build_\w*rag\w*\.py"           # RAG built -> stage 2 nears done
    r"|setup_clone\.sh"               # clone wired
    r")\b",
    re.I,
)
# Written paths that cross a boundary. A write is the observable moment a setup
# artifact comes into existence; reads and previews are not.
PATH_RE = re.compile(
    r"use_cases/[^/]+/config/[^/]+\.sh"          # site config      (onboard-case Step 4)
    r"|use_cases/[^/]+/validation/targets\.yaml"  # the spec         (onboard-case)
    r"|use_cases/[^/]+/config/calibration_rounds\.yaml"
    r"|use_cases/[^/]+/parameters/"               # parameter list   (GATE 2)
    r"|rag/milestones\.json"                      # milestone        (onboard-model step 9)
    r"|memory/[^/]+/gained_knowledge/",           # adaptive memory  (onboard-model step 10)
    re.I,
)
QUIET_RE = re.compile(r"--dry-run\b|--list\b|--write-script\b|remind-setup-stage", re.I)

WRITE_TOOLS = {"Write", "Edit", "NotebookEdit"}

SKILL = {1: "a2mc-init", 2: "onboard-model", 3: "onboard-case"}

# Which MODEL an onboard-model action is about. Auto-detection can never return stage 2 on a line that
# ships registered adapters, so without this the hook announced "SETUP STAGE 1 (`a2mc-init`)" in the
# middle of onboard-model (audit 20260923b, F33).
MODEL_HINT_RE = re.compile(
    r"init_adapter\.py\b.*?--model[= ]+([a-z0-9_]+)"
    r"|build_([a-z0-9]+)_rag\.py"
    r"|memory/([a-z0-9_]+)/gained_knowledge/",
    re.I)


def _model_hint(payload):
    ti = payload.get("tool_input") or {}
    text = ti.get("command", "") or ti.get("file_path", "") or ""
    m = MODEL_HINT_RE.search(text.replace("\\", "/"))
    if not m:
        return None
    name = next(g for g in m.groups() if g)
    return None if name.lower() in ("gained_knowledge",) else name.lower()


def _crossed(payload):
    """Did this completed action cross a stage boundary?"""
    tool = payload.get("tool_name")
    ti = payload.get("tool_input") or {}
    if tool == "Bash":
        cmd = ti.get("command", "") or ""
        return bool(cmd) and not QUIET_RE.search(cmd) and bool(BASH_RE.search(cmd))
    if tool in WRITE_TOOLS:
        path = ti.get("file_path", "") or ti.get("notebook_path", "") or ""
        return bool(path) and bool(PATH_RE.search(path.replace(os.sep, "/")))
    return False


def _succeeded(payload):
    resp = payload.get("tool_response") or {}
    if isinstance(resp, dict) and resp.get("success") is False:
        return False
    return True


def _stage_and_gaps(payload=None):
    """Re-read the stage + outstanding items from check_stage_ready.py.

    Reuses that module rather than restating the routing or the checks -- a second
    copy of either would drift from the first. Returns (stage, gaps, next_skill_text).
    """
    import importlib.util
    spec = importlib.util.spec_from_file_location(
        "_csr", os.path.join(REPO, "tools", "check_stage_ready.py"))
    if spec is None or spec.loader is None:
        return None, [], ""
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    stage, _why = m.detect_stage()

    # The per-clone rows, at every stage (F38). They are the only rows setup_clone.sh changes, and
    # the hook fires on it, so leaving them out reported nothing about the one action it watched.
    gaps, clone_ok = [], True
    try:
        sys.path.insert(0, os.path.join(REPO, "tools"))
        from check_clone_setup import clone_rows
        bad = [r for r in clone_rows() if r[0] == m.FAIL]
        clone_ok = not bad
        gaps += ["clone: %s%s" % (label, " — " + detail if detail else "") for _, label, detail in bad]
    except Exception:
        pass

    hint = _model_hint(payload or {})
    if hint and hint in (m.onboarded_models() or []):
        stage = 2
        rows = [("model " + hint, r) for r in m.stage2_rows(hint)]
    elif stage == 4:
        return 4, gaps, m.next_skill(4, clone_ok)
    elif stage == 1:
        rows = [("", r) for r in m.stage1_rows()]
    elif stage == 2:
        rows = [("model " + n, r) for n in (m.onboarded_models() or []) for r in m.stage2_rows(n)]
    else:
        rows = [("case " + c, r) for c in (m.real_cases() or []) for r in m.stage3_rows(c)]
    # Name the case or model a gap belongs to: with two cases, an unlabelled list is ambiguous (F108).
    gaps += ["%s%s%s" % ((who + ": ") if who else "", label, " — " + detail if detail else "")
             for who, (status, label, detail) in rows if status == m.FAIL]
    return stage, gaps, m.next_skill(stage, clone_ok)


def main():
    try:
        payload = json.load(sys.stdin)
    except Exception:
        sys.exit(0)                                   # unparseable -> stay silent
    try:
        if not _crossed(payload) or not _succeeded(payload):
            sys.exit(0)

        stage, gaps, nxt = _stage_and_gaps(payload)
        if stage is None or (stage == 4 and not gaps):
            sys.exit(0)                               # setup complete, clone wired -> nothing to say

        # Fire on the TRANSITION: stage, or the number of outstanding items, changed.
        key = "%s:%s" % (stage, len(gaps))
        try:
            with open(STAMP) as fh:
                if fh.read().strip() == key:
                    sys.exit(0)
        except OSError:
            pass
        try:
            with open(STAMP, "w") as fh:
                fh.write(key)
        except OSError:
            pass                                      # unwritable -> still report, just repeat

        head = ("SETUP STAGE %d: the stage answer from session start is now stale. Next: %s.\n"
                % (stage, nxt))
        if gaps:
            body = "%d item(s) still outstanding:\n" % len(gaps)
            body += "".join("  ✗ %s\n" % g for g in gaps[:6])
            if len(gaps) > 6:
                body += "  … and %d more\n" % (len(gaps) - 6)
        else:
            body = ("No mechanical items outstanding. The remaining ones are human-only "
                    "(approvals, interviews) — see the checklist.\n")
        tail = ("Definition of done: the `setup-discipline` skill. "
                "Full audit: python3 tools/check_stage_ready.py")

        print(json.dumps({"hookSpecificOutput": {
            "hookEventName": "PostToolUse",
            "additionalContext": head + body + tail}}))
    except Exception:
        pass                                          # a hook must never break a session
    sys.exit(0)


if __name__ == "__main__":
    main()
