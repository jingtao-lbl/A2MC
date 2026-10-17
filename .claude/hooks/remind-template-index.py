#!/usr/bin/env python3
"""PostToolUse hook: a case's script templates or run files changed, and its README index no longer lists them.

visibility: public

Why this exists
---------------
A phase chooses its script from the case's template index in `use_cases/<Case>/scripts/README.md`,
and its run files (launchers, namelists) from the one in `case_template/README.md`; both are generated
by `tools/case_script_index.py` from each file's own first line. A template is added
the moment a script is promoted on its second use -- by a Write, or more often by a `cp` from a phase
folder -- and the index is then one template short until someone regenerates it. A stale index is
the failure this whole tier exists to prevent: the next phase reads the README, does not see the
template, and writes the script from scratch.

CHECK THE ARTIFACT, NOT THE COMMAND
-----------------------------------
Guessing from a command line whether it wrote into `scripts/` is fragile (`cp`, `mv`, `install`,
redirections, a script that copies). So this hook only uses the tool call to find WHICH case to look
at -- a path under `use_cases/<Case>/scripts/` named in the Write target or anywhere in the Bash
command -- and then asks the index itself whether it is current. It speaks only when a template in
that folder is missing from the index, the index lists one that is gone, or a template's summary
line changed. A command that merely READS a template (copying it into a phase folder) leaves the
index current and the hook silent.

A case whose README carries no generated index yet is reported only if a template there is NEW
(untracked), so copying from an older case's templates does not nag about that case's README.

Pre-commit check (32) refuses the commit while the index is stale; this says so at the moment the
template appears, with the one command that fixes it. Never blocks. Never raises.

Author: Jing Tao with Claude on Perlmutter
"""
import json
import os
import re
import subprocess
import sys

ROOT = os.environ.get("CLAUDE_PROJECT_DIR") or os.path.dirname(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
CASE_TIER = re.compile(r"use_cases/([A-Za-z0-9_.\-]+)/(scripts|case_template)(?:/|\b)")


def tiers_named(payload):
    """{case: set of tiers} named in the Write target or anywhere in the Bash command."""
    ti = payload.get("tool_input") or {}
    text = " ".join(str(ti.get(k, "")) for k in ("file_path", "notebook_path", "command"))
    out = {}
    for case, tier in CASE_TIER.findall(text):
        out.setdefault(case, set()).add(tier)
    return out


def untracked(case, tier):
    out = subprocess.run(["git", "-C", ROOT, "ls-files", "--others", "--exclude-standard", "--",
                          "use_cases/%s/%s" % (case, tier)],
                         stdout=subprocess.PIPE, universal_newlines=True).stdout
    return [l for l in out.split() if not l.endswith("README.md")]


def main():
    payload = json.load(sys.stdin)
    if payload.get("tool_name") not in ("Bash", "Write", "Edit", "NotebookEdit"):
        return
    sys.path.insert(0, os.path.join(ROOT, "tools"))
    import case_script_index as I

    notes = []
    for case, named in sorted(tiers_named(payload).items()):
        cdir = I.Path(ROOT) / "use_cases" / case
        tiers = [t for t in I.TIERS if t in named and (cdir / t).is_dir()
                 and (I.current_block(cdir / t / "README.md") is not None or untracked(case, t))]
        if not tiers:
            continue
        problems = I.check(cdir, I.Path(ROOT), tiers)
        if problems:
            notes.append("TEMPLATE INDEX STALE for %s:" % case)
            notes.extend("  " + p for p in problems[:8])
            notes.append("  Regenerate it now: python3 tools/case_script_index.py --case use_cases/%s "
                         "%s--write   (pre-commit 32 refuses the change while it is stale; a phase "
                         "that reads a stale index writes from scratch what is already here)"
                         % (case, "".join("--tier %s " % t for t in tiers)))
    if notes:
        print(json.dumps({"hookSpecificOutput": {
            "hookEventName": "PostToolUse",
            "additionalContext": "\n".join(notes)}}))


if __name__ == "__main__":
    try:
        main()
    except Exception:
        pass      # a reminder must never break the tool call it follows
    sys.exit(0)
