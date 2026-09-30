#!/usr/bin/env python3
"""Before a file is written, say what governs it.

visibility: public

WHY. The repository's discipline is a chain -- a skill says how, a checker asserts it, a hook refuses
the commit -- and an agent otherwise meets the chain by TRIPPING it: the checker fires at commit time,
long after the edit, naming a rule nobody mentioned while the file was being written. Worse, a contract
usually lives in several places, so editing the one instance in front of you is the single most common
mistake here.

`docs/skill_graph/A2MC_Harness_Network.html` already draws this chain, but an agent cannot look at a
picture. So this hook asks `tools/harness_query.py` the same question at the moment of the edit.
Account: `memory/dev_logs_adapterkit/20260925s_Asking_The_Harness_What_Governs_A_Path.md`.

It is INFORMATION, never a block. Every path exits 0, including every failure: a reminder that breaks
the tool call it precedes is worse than no reminder.

It speaks ONCE PER PATH PER SESSION. A hook that repeats itself on the fifth edit of the same file
gets scrolled past, and then it is not read on the first edit of the next one either.

Author: Jing Tao with Claude on Perlmutter.
"""
import json
import os
import sys

ROOT = os.environ.get("CLAUDE_PROJECT_DIR") or os.path.dirname(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def already_said(session, rel):
    """True if this path was announced earlier in this session. Fails OPEN: on any trouble we
    speak again, because a duplicate reminder is a smaller harm than a silent first one."""
    try:
        d = os.path.join(ROOT, "tmp", ".harness_governs")
        os.makedirs(d, exist_ok=True)
        f = os.path.join(d, (session or "nosession").replace("/", "_")[:64])
        seen = set()
        if os.path.isfile(f):
            with open(f) as fh:
                seen = set(l.strip() for l in fh)
        if rel in seen:
            return True
        with open(f, "a") as fh:
            fh.write(rel + "\n")
    except Exception:
        return False
    return False


def main():
    payload = json.load(sys.stdin)
    ti = payload.get("tool_input") or {}
    path = ti.get("file_path") or ti.get("notebook_path") or ""
    if not path:
        return
    rel = path[len(ROOT) + 1:] if path.startswith(ROOT + os.sep) else path
    rel = rel.lstrip("/")
    if not rel or rel.startswith("tmp/"):
        return

    sys.path.insert(0, os.path.join(ROOT, "tools"))
    import harness_query as Q

    gated = [(n, t) for n, t, g in Q._gate_hits(rel) if g != "always"]
    shorts = set(t.replace("check_", "").replace("validate_", "") for _n, t in gated)
    recip = Q._reciprocal(shorts)
    is_skill = rel.startswith(".claude/skills/") and rel.endswith("/SKILL.md")

    # Say nothing when there is nothing to say. Most of this tree IS governed, so the dedupe above
    # is what keeps this from becoming wallpaper -- but an ungoverned path must stay silent outright.
    if not gated and not is_skill:
        return
    if already_said(payload.get("session_id"), rel):
        return

    lines = ["GOVERNS %s -- these refuse the commit, so satisfy them while you are here:" % rel]
    for num, tool in gated:
        lines.append("  (%s) tools/%s.py" % (num, tool))
    for a, b, lab in recip:
        lines.append("  RECIPROCAL %s <-> %s: %s. One half alone looks finished." % (a, b, lab))
    if is_skill:
        if os.path.isfile(os.path.join(ROOT, rel)):
            lines.append("  Editing an EXISTING skill changes a contract: follow the `refine-skill` "
                         "skill -- show the PI the exact diff with its evidence and wait for approval, "
                         "then re-read the WHOLE file after the edit, not just the changed lines.")
        else:
            lines.append("  A NEW skill: follow the `add-skill` skill, which registers it in all four "
                         "places at once.")
        lines.append("  This skill's `visibility:` is read by BOTH sync legs; its registry rows in "
                     "CLAUDE.md, AGENTS.md, .claude/skills/README.md and "
                     "docs/a2mc_reference/skills_catalog.md must move in and out of the private "
                     "blocks with it, and `## Changelog` must stay the LAST section.")
    lines.append("  Full picture: python3 tools/harness_query.py --touches %s" % rel)

    print(json.dumps({"hookSpecificOutput": {
        "hookEventName": "PreToolUse",
        "additionalContext": "\n".join(lines)}}))


try:
    main()
except Exception:
    pass          # a reminder must never break the tool call it precedes
sys.exit(0)
