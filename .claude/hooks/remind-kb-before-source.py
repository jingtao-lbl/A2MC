#!/usr/bin/env python3
"""PreToolUse (Read, Bash) hook: model source read before the knowledge base was queried.

visibility: public

WHY THIS EXISTS
---------------

In calibration, a diagnosis or a hypothesis gets the parameter-mechanism-output picture from the
three-tier knowledge base first (technical documents and the commit-pinned codebase wiki; RAG and
the two-layer graph; the two-layer adaptive memory) and goes to model source only to CONFIRM it
(`query-knowledge-base`). The shortcut -- straight to the Fortran -- re-derives what the knowledge
base already holds, misses what earlier rounds learned, and never finds the knowledge base's own
gaps. `check_calibration_log_conformance.py` C13 catches it when the Phase 3, 4 or 6 log, or a forensics log, is written; this
catches it at the moment of the shortcut. Account:
`memory/dev_logs_adapterkit/20261015h_Phase_3_And_4_Query_The_Knowledge_Base_Before_The_Source.md`.

WHAT IT DOES
------------

* Records `tools/kb_network.py` being run in this session (a Bash command that executes it).
* When model SOURCE is read -- the Read tool on a Fortran/C/C++ file outside this repository, or a
  Bash grep/sed/cat/head/tail/awk/less on such a file -- and the session has not run
  `kb_network.py`, it says so, once per session.
* Silent where no case carries calibration state (no `use_cases/*/memory/workflow_state_offline_r*.json`):
  while a model is being ONBOARDED the knowledge base does not exist yet and source is correct.

Never a block: every path exits 0, including every failure.

Author: Jing Tao with Claude on Perlmutter
"""
import glob
import json
import os
import re
import sys

ROOT = os.environ.get("CLAUDE_PROJECT_DIR") or os.path.dirname(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

SOURCE_EXT = re.compile(r"\.(?:F90|f90|F|f|c|cc|cpp|h|hh|hpp)\b")
READ_VERB = re.compile(r"(?:^|[\s;&|(])(?:grep|egrep|rg|sed|cat|head|tail|awk|less|more|git\s+(?:-C\s+\S+\s+)?(?:grep|show))\b")
RUNS_KB_NETWORK = re.compile(r"(?:python[0-9.]*|\$\{?PY\}?)\b[^|;&\n]*?\bkb_network\.py\b")

MESSAGE = (
    "KB FIRST -- this session is reading model source (%s) and has not queried the knowledge base.\n"
    "  In calibration, get the parameter-mechanism-output picture from the three tiers first, then come\n"
    "  back here to CONFIRM it (`query-knowledge-base`):\n"
    "    python tools/kb_network.py --model <m> --params <P...> --outputs <O...> --case <Model_Case> \\\n"
    "        --out-dir use_cases/<Model_Case>/memory/phase_results/<stem>\n"
    "  A Phase 3, 4 or 6 log, or a forensics log, must cite the kb_network artifact (check_calibration_log_conformance C13).\n"
    "  Onboarding a model, before its knowledge base exists, is the exception."
)


def _state(session):
    d = os.path.join(ROOT, "tmp", ".harness_governs")
    os.makedirs(d, exist_ok=True)
    return os.path.join(d, (session or "nosession").replace("/", "_")[:64] + ".kbquery")


def _marks(session):
    try:
        with open(_state(session)) as fh:
            return set(l.strip() for l in fh)
    except OSError:
        return set()


def _mark(session, what):
    try:
        with open(_state(session), "a") as fh:
            fh.write(what + "\n")
    except OSError:
        pass


def in_calibration():
    """Some case has offline calibration state. Bounded: two fixed levels under use_cases/."""
    return bool(glob.glob(os.path.join(ROOT, "use_cases", "*", "memory", "workflow_state_offline_r*.json")))


def source_target(payload):
    """The model-source path being read, or None."""
    tool = payload.get("tool_name")
    ti = payload.get("tool_input") or {}
    if tool == "Read":
        f = ti.get("file_path") or ""
        if SOURCE_EXT.search(os.path.basename(f)):
            real = os.path.realpath(f)
            if not real.startswith(os.path.realpath(ROOT) + os.sep):
                return f
        return None
    if tool == "Bash":
        cmd = ti.get("command") or ""
        if READ_VERB.search(cmd):
            m = re.search(r"[\w./~${}-]*" + SOURCE_EXT.pattern, cmd)
            if m:
                return m.group(0)
    return None


def main():
    try:
        payload = json.load(sys.stdin)
        session = payload.get("session_id")
        tool = payload.get("tool_name")
        if tool == "Bash" and RUNS_KB_NETWORK.search((payload.get("tool_input") or {}).get("command") or ""):
            _mark(session, "queried")
            return
        target = source_target(payload)
        if not target or not in_calibration():
            return
        marks = _marks(session)
        if "queried" in marks or "reminded" in marks:
            return
        _mark(session, "reminded")
        print(json.dumps({"hookSpecificOutput": {"hookEventName": "PreToolUse",
                                                 "additionalContext": MESSAGE % target}}))
    except Exception:
        pass


if __name__ == "__main__":
    main()
    sys.exit(0)
