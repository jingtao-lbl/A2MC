#!/usr/bin/env python3
"""PreToolUse (Bash) hook: refuse moving or deleting a hook that .claude/settings.json registers.

visibility: public

WHY THIS EXISTS
---------------

A registered hook whose file is moved or deleted errors on every matching tool call in every running
session, and a PreToolUse error blocks the call: a moved Bash hook makes EVERY Bash command fail,
including the one that would undo the move. Fixing `.claude/settings.json` does not rescue it in time:
a running session does not pick up the change at once (a Bash call right after the edit still ran the
old registration; a hook registered later ran in the same session only some calls afterwards). Measured 2026-10-15 with
`git mv .claude/hooks/remind-per-model-kb-tools.py ...` (memory
`feedback_registered_hook_filename_is_an_interface`; account
`memory/dev_logs_adapterkit/20261015i_A_Registered_Hook_Keeps_Its_Name_And_Phase_6_Queries_The_KB.md`).

WHAT IT REFUSES
---------------

A Bash command that runs `mv`, `git mv`, `rm` or `git rm` on a `.claude/hooks/<file>` that the
current `.claude/settings.json` registers. The registered names are READ from settings.json on every
call, never listed here. A hook that is not registered may be moved freely. The refusal is the right
default because the move cannot be undone from inside the session it breaks; a deliberate rename
goes through a forwarding shim (the memory says how).

Every failure of the hook itself is silent and allows the command: a guard that breaks the tool
call for its own reasons is the failure it exists to prevent.

Author: Jing Tao with Claude on Perlmutter
"""
import json
import os
import re
import sys

ROOT = os.environ.get("CLAUDE_PROJECT_DIR") or os.path.dirname(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

#: mv / git mv / rm / git rm as the COMMAND of a simple command (after splitting on ; & | and newlines).
#: Matching anywhere in the line refused a `git add` of hook files whose heredoc commit message merely
#: said "mv ... rm" (measured 2026-10-15, 20261015i).
MOVE = re.compile(r"^\s*(?:\(\s*)?(?:sudo\s+)?(?:git\s+(?:-C\s+\S+\s+)?)?(?:mv|rm)\b")


def registered():
    """Basenames of the hook files .claude/settings.json registers, read now."""
    try:
        with open(os.path.join(ROOT, ".claude", "settings.json")) as fh:
            text = fh.read()
    except OSError:
        return set()
    return set(re.findall(r"\.claude/hooks/([\w.-]+\.(?:py|sh))", text))


def main():
    try:
        data = json.load(sys.stdin)
        if data.get("tool_name") != "Bash":
            return
        cmd = (data.get("tool_input") or {}).get("command", "") or ""
        if ".claude/hooks/" not in cmd:
            return
        names = registered()
        hit = set()
        for seg in re.split(r"[;&|\n]+", cmd.replace("\\\n", " ")):
            if MOVE.search(seg):
                hit |= {n for n in names if re.search(r"\.claude/hooks/" + re.escape(n) + r"\b", seg)}
        hit = sorted(hit)
        if not hit:
            return
        reason = ("`%s` is registered in .claude/settings.json. A running session keeps that registration for an "
                  "unknown while after settings.json changes, so moving or deleting the file makes EVERY matching "
                  "tool call fail in all of them (for a Bash hook, every Bash command, including the one that would "
                  "undo it). Change the file's content and keep its name; for a real rename, add the new file, "
                  "register it, and leave the old one as a forwarding shim until no session that knew the old name "
                  "can be running. "
                  "Memory: feedback_registered_hook_filename_is_an_interface." % ", ".join(hit))
        print(json.dumps({"hookSpecificOutput": {"hookEventName": "PreToolUse",
                                                 "permissionDecision": "deny",
                                                 "permissionDecisionReason": reason}}))
    except Exception:
        pass


if __name__ == "__main__":
    main()
    sys.exit(0)
