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
import re
import sys

ROOT = os.environ.get("CLAUDE_PROJECT_DIR") or os.path.dirname(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


# Memories bound to the SHAPE of what is being written.
#
# WHY these arrive unbidden instead of being recalled. Measured 2026-10-01 over this repo: 131
# memories, of which 95 are named by no checker, hook or gate -- they exist only as text the agent
# must decide to consult. The three below are the most-missed in the bucket, counted by how many of
# the 18 reflection logs name them as a lesson that did not fire: 12, 8 and 8. Writing a fourth
# memory about the same thing has the same expected effect as the 95. Arriving at the moment of the
# action is the one thing a reminder does that a document cannot.
#
# ONE LIMIT, stated because it is not obvious: `dont_assert_absence_from_one_grep` is really about a
# grep that returns nothing, which is a Bash call this hook does not see. It is bound here to where
# an absence claim gets RECORDED -- a log or a report -- which is the last point before the claim
# becomes durable, not the first point it could be caught.
# `dev_logs` carries a BRANCH SUFFIX on every branch but main (`dev_logs_adapterkit`), so the
# bare alternative matched nothing here -- caught by testing each shape rather than assuming,
# which is the failure mode of the very memory bound below.
_LOGS_AND_REPORTS = (r"^(memory/(dev_logs[a-z_]*|ana_logs|model_logs)"
                     r"|use_cases/[^/]+/(memory/logs|memory/model_evolution|reports))/")

# The knowledge-base files where a per-model tool gets CHOSEN: the KB skills, the builders and
# extractors, the registry and golden queries, and the curated seeds. Bound 2026-10-15 (PI) after a
# review found the KB skills naming FATES tools only. Wiki pages are deliberately left out: a wiki
# rewrite touches dozens of them, the reminder would fire on each, and no tool is chosen there.
_KB_FILES = (r"^(\.claude/skills/(generate-codebase-wiki|build-rag-from-scratch|rebuild-rag"
             r"|validate-rag-chain|wire-knowledge-graph|inject-knowledge|onboard-model)/SKILL\.md"
             r"|scripts/(build_rag_index|build_\w+_rag|extract_\w+_outputs|curated_seed_builder)\.py"
             r"|rag/(milestones\.json|golden_queries\.yaml|data/curated_relationships[\w-]*\.yaml)"
             r"|models/[^/]+/curated_seed[\w-]*\.yaml)$")

MEMORY_BY_SHAPE = (
    (r"^(tests/test_.*|tools/(check|validate)_.*)\.py$",
     "feedback_a_check_that_cannot_fail",
     "name what would make this FAIL before writing it, and prove it fails against the OLD code "
     "-- a test that passes without reaching the branch under test is worse than no test"),
    (_LOGS_AND_REPORTS,
     "feedback_verify_derived_numbers_not_just_citations",
     "every count in here is READ from a command, never recalled; be most suspicious of a number "
     "you produced yourself"),
    (_LOGS_AND_REPORTS,
     "feedback_dont_assert_absence_from_one_grep",
     "an absence claim needs a POSITIVE CONTROL -- prove the matcher fires on something that IS "
     "there before trusting its silence"),
    (r"^use_cases/[^/]+/",
     "feedback_case_artifacts_correct_in_place_no_notes",
     "a case folder is delivered as ONE document set, so a wrong fact is rewritten as the correct "
     "statement and nothing announces the change -- no banner, no dated note. THE TELL is a "
     "sentence whose subject is the previous version rather than the subject matter, which passes "
     "unnoticed because it need not contain the word correction"),
    (_KB_FILES,
     "reference_per_model_kb_build_tools",
     "every knowledge-base BUILD step (wiki, registry, seed, index and graph, validation, patch) has a "
     "DIFFERENT tool per model (FATES/ELM, EcoSIM, PFLOTRAN, ATS) -- find this model's row before the "
     "command, never assume the FATES tool covers the others; the profiles listed there are an inventory, "
     "and the profile a command uses is resolved by tools/kb_profile.py. QUERYING the KB is the "
     "query-knowledge-base skill"),
    (r"^\.claude/(settings\.json|hooks/[^/]+\.(py|sh))$",
     "feedback_registered_hook_filename_is_an_interface",
     "a hook .claude/settings.json registers is an INTERFACE -- never mv or rm its file, because a running "
     "session keeps the old registration for an unknown while and would fail EVERY matching tool call (Bash "
     "included, the undo too); change the content, keep the name"),
)

# This one reminder fires only when the target ALREADY EXISTS. The other three apply to any write
# -- a new log owes verified numbers and a positive control just as much as an edited one -- but
# "correct it in place" presupposes text to correct, so on a brand-new case file it would be crying
# wolf. Declared as a set rather than widening every tuple to four fields, so the three entries
# above stay untouched.
_ONLY_IF_EXISTS = frozenset({"feedback_case_artifacts_correct_in_place_no_notes"})


# When a cited note is not in this tree it is one of the maintainer's internal development
# notes, which do not ship. The RULE is the part that travels; the name is provenance. Said in
# the output rather than left to be puzzled over, and stated for readers in AGENTS.md too.
_NOT_HERE = ("  (The notes cited above are the maintainer's internal development notes and do not "
             "ship with A2MC; the rule is the part that matters. Contact jingtao@lbl.gov if you "
             "want the source note.)")


def memory_lines(rel):
    """Reminders for the shape of `rel`.

    The rule is emitted whether or not this tree carries the note it came from: the discipline is
    generic and useful to any reader, while `.claude_memory/` is excluded from every sync leg. A
    tree without the note gets one line saying so, so an unresolvable citation reads as a policy
    rather than as a broken pointer. That the named notes EXIST here is asserted by
    tests/test_remind_governing_checks_memory_binding.py, which is what catches a typo or a rename.
    """
    out, missing = [], False
    for pattern, name, why in MEMORY_BY_SHAPE:
        if not re.search(pattern, rel):
            continue
        if name in _ONLY_IF_EXISTS and not os.path.isfile(os.path.join(ROOT, rel)):
            continue
        out.append("  REMEMBER %s: %s" % (name, why))
        if not os.path.isfile(os.path.join(ROOT, ".claude_memory", name + ".md")):
            missing = True
    if missing:
        out.append(_NOT_HERE)
    return out


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
    if not gated and not is_skill and not memory_lines(rel):
        return
    if already_said(payload.get("session_id"), rel):
        return

    # The header must match what follows. A path can now reach here with a bound memory and NO
    # gated check, and "these refuse the commit" would then be a promise with nothing behind it.
    if gated:
        lines = ["GOVERNS %s -- these refuse the commit, so satisfy them while you are here:" % rel]
    else:
        lines = ["GOVERNS %s -- nothing gates this path at commit time; the notes below are habits, "
                 "not gates:" % rel]
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
    lines.extend(memory_lines(rel))
    lines.append("  Full picture: python3 tools/harness_query.py --touches %s" % rel)

    print(json.dumps({"hookSpecificOutput": {
        "hookEventName": "PreToolUse",
        "additionalContext": "\n".join(lines)}}))


# Guarded so the module can be IMPORTED -- by a test, or by a probe reading MEMORY_BY_SHAPE --
# without running. Unguarded, an import executed main(), which read an already-exhausted stdin and
# exited 0, taking the importing process with it; that killed a probe on 2026-10-09 and is why the
# regex had to be re-tested by hand. The fail-open contract is unchanged: both the swallow and the
# exit(0) stay inside the guard, so running it as a hook behaves exactly as before.
if __name__ == "__main__":
    try:
        main()
    except Exception:
        pass      # a reminder must never break the tool call it precedes
    sys.exit(0)
