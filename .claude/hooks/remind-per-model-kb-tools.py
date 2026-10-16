#!/usr/bin/env python3
"""PreToolUse (Bash) hook: a knowledge-base BUILD command first names that step's tool for every model.

visibility: public

WHY THIS EXISTS
---------------

Every step that BUILDS, VALIDATES or PATCHES the knowledge base -- validate the wiki, extract the
output registry, build the index and graph, check the golden queries, check the seed's citations,
patch a profile -- has a DIFFERENT tool per model (FATES/ELM, EcoSIM, PFLOTRAN, ATS). Running the
FATES tool against an adapter profile does not fail usefully: it reports on the wrong collection, or
reads as "not applicable" and the step is skipped. A 2026-10-15 review found the knowledge-base
skills naming FATES tools only; the per-model table lives in the memory
`reference_per_model_kb_build_tools`. QUERYING the knowledge base is a different job, the
`query-knowledge-base` skill (`tools/kb_network.py`), reminded by `remind-kb-before-source.py`.

`remind-governing-checks.py` names the memory when a knowledge-base FILE is edited. Running a
command edits nothing, so this hook covers the other half: the moment a build tool is about to run.
Accounts: `memory/dev_logs_adapterkit/20261015g_A_Knowledge_Base_Command_Names_Its_Step_For_Every_Model.md`
and, for the build/query split, `memory/dev_logs_adapterkit/20261015h_Phase_3_And_4_Query_The_Knowledge_Base_Before_The_Source.md`.

THE FILENAME IS AN INTERFACE. It still says "kb-tools" although the hook is about build tools:
a running session does not pick up a changed `.claude/settings.json` at once, so renaming a
registered hook makes each of them fail every Bash call, the undo included (measured 2026-10-15,
`20261015h`, `20261015i`; memory feedback_registered_hook_filename_is_an_interface).

WHAT IT DOES
------------

Fires when a command EXECUTES one of the per-model build tools through a Python interpreter
(`python`, `python3`, `$PY`, `~/a2mc_env/bin/python`, ...). Reading the file (`sed`, `cat`,
`git grep`) does not count. It prints the rule and, when the memory is in this tree, the table ROW
that holds the tool, so the reader sees that step's tool for every model and not only the one about
to run. The row is READ from the memory at run time and never restated here, so the hook cannot
drift from the table; `tests/test_reference_per_model_kb_build_tools.py` holds the table to the
repository.

Once per (session, tool). Never a block: every path exits 0, including every failure, because a
reminder that breaks the command it precedes is worse than none.

Author: Jing Tao with Claude on Perlmutter
"""
import json
import os
import re
import sys

ROOT = os.environ.get("CLAUDE_PROJECT_DIR") or os.path.dirname(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
MEMORY = "reference_per_model_kb_build_tools"

#: The per-model tools that BUILD, VALIDATE or PATCH the knowledge base. A new one belongs here and in
#: the memory's table. Querying the knowledge base is `tools/kb_network.py`, reminded elsewhere.
_TOOLS = (r"build_rag_index|build_\w+_rag|extract_\w+_outputs|curated_seed_builder"
          r"|codebase_wiki_validator|validate_wiki_vs_source|validate_ats_wiki|yaml_wiki_validator"
          r"|validate_curated_yaml|check_rag_queries|check_ecosim_rag_queries|check_rag_coverage"
          r"|check_\w+_seed_citations|check_ecosim_tested_params_in_kb|ecosim_param_source_map"
          r"|kb_patch|rag_diff")

#: The tool must be EXECUTED by an interpreter, in the same simple command: `python ... tool.py`.
RUNS = re.compile(r"(?:python[0-9.]*|\$\{?PY\}?)\b[^|;&\n]*?\b(" + _TOOLS + r")\.py\b")

RULE = ("  REMEMBER %s: every knowledge-base BUILD step has a DIFFERENT tool per model (FATES/ELM, "
        "EcoSIM, PFLOTRAN, ATS) -- check this is the right model's tool before it runs; the profile a "
        "command uses is resolved by tools/kb_profile.py, never picked from a list. Querying the KB is "
        "`query-knowledge-base`." % MEMORY)

NOT_HERE = ("  (The table lives in the maintainer's development notes, which do not ship with A2MC; "
            "the rule is the part that matters.)")


def _cells(line):
    return [c.strip() for c in line.strip().strip("|").split("|")]


def row_for(tool):
    """The memory's table row that names `tool`, as 'step: model=cell; ...', or None."""
    path = os.path.join(ROOT, ".claude_memory", MEMORY + ".md")
    try:
        with open(path) as fh:
            lines = [l for l in fh.read().splitlines() if l.startswith("| ")]
    except OSError:
        return None
    if not lines:
        return None
    header = _cells(lines[0])
    for line in lines[1:]:
        if re.search(r"`%s\.py\b" % re.escape(tool), line):
            cells = _cells(line)
            pairs = ["%s: %s" % (h, c) for h, c in zip(header[1:], cells[1:])]
            return "  %s -- %s" % (cells[0], "  |  ".join(pairs))
    return None


def already_said(session, tool):
    """True if this tool was announced earlier in this session. Fails OPEN: a duplicate reminder
    is a smaller harm than a silent first one."""
    try:
        d = os.path.join(ROOT, "tmp", ".harness_governs")
        os.makedirs(d, exist_ok=True)
        f = os.path.join(d, (session or "nosession").replace("/", "_")[:64] + ".kbtools")
        seen = set()
        if os.path.isfile(f):
            with open(f) as fh:
                seen = set(l.strip() for l in fh)
        if tool in seen:
            return True
        with open(f, "a") as fh:
            fh.write(tool + "\n")
    except Exception:
        return False
    return False


def message(cmd, session):
    m = RUNS.search(cmd or "")
    if not m:
        return None
    tool = m.group(1)
    if already_said(session, tool):
        return None
    row = row_for(tool)
    out = ["KB BUILD COMMAND -- `%s.py` is one model's tool for this build step." % tool]
    out.append(row if row else NOT_HERE)
    out.append(RULE)
    return "\n".join(out)


def main():
    try:
        payload = json.load(sys.stdin)
        if payload.get("tool_name") != "Bash":
            return
        msg = message((payload.get("tool_input") or {}).get("command", ""), payload.get("session_id"))
        if msg:
            print(json.dumps({"hookSpecificOutput": {"hookEventName": "PreToolUse",
                                                     "additionalContext": msg}}))
    except Exception:
        pass


if __name__ == "__main__":
    main()
    sys.exit(0)
