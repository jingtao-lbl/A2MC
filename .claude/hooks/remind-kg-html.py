#!/usr/bin/env python3
"""PostToolUse hook: a knowledge graph changed, and its HTML view still describes the previous one.

visibility: public

Why this exists
---------------
A profile's HTML view, `<knowledge_base_dir>/graph_html/<profile>_knowledge_graph.html`, embeds the
graph's nodes and edges when `tools/render_kg_html.py` writes it. A rebuild rewrites
`rag/graphs/<profile>.json` and leaves the page as it was, and nothing else compares the two. The
incident that motivated this is in `memory/dev_logs_adapterkit/20261016j_A_Graph_And_Its_HTML_View_Are_Checked_Against_Each_Other.md`.

CHECK THE ARTIFACT, NOT THE COMMAND
-----------------------------------
The tool call only decides WHETHER to look: a command that runs a RAG builder or the renderer, or that
names `rag/graphs/` or a `graph_html/` folder, or a Write/Edit to one of them. The comparison itself is
`tools/check_kg_html_current.py`, which computes what each page should hold with the renderer's own
`page_data()`. The hook speaks only when a page is out of step, so a build that changed nothing in the
graph, or one followed by the regeneration, stays silent.

Pre-commit check (35) refuses the commit while a staged graph and its page disagree; this says so at
the moment the graph changes, with the command that fixes it. Never blocks. Never raises.

Author: Jing Tao with Claude on Perlmutter
"""
import json
import os
import re
import subprocess
import sys

ROOT = os.environ.get("CLAUDE_PROJECT_DIR") or os.path.dirname(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
TRIGGER = re.compile(r"rag/graphs/|graph_html|build_rag_index\.py|build_ecosim_rag\.py|"
                     r"build_pflotran_rag\.py|build_ats_rag\.py|render_kg_html\.py")


def interpreter():
    """A Python new enough for the checker (3.7+); the hook itself runs under the system python3."""
    for p in (os.environ.get("A2MC_PYTHON"), os.path.expanduser("~/a2mc_env/bin/python")):
        if p and os.path.isfile(p) and os.access(p, os.X_OK):
            return p
    return None


def main():
    payload = json.load(sys.stdin)
    if payload.get("tool_name") not in ("Bash", "Write", "Edit", "NotebookEdit"):
        return
    ti = payload.get("tool_input") or {}
    text = " ".join(str(ti.get(k, "")) for k in ("file_path", "notebook_path", "command"))
    if not TRIGGER.search(text):
        return
    py = interpreter()
    if not py:
        return
    try:
        r = subprocess.run([py, os.path.join(ROOT, "tools", "check_kg_html_current.py")],
                           stdout=subprocess.PIPE, stderr=subprocess.STDOUT, universal_newlines=True,
                           timeout=90, cwd=ROOT)
    except Exception:
        return
    if r.returncode != 1:
        return
    lines = [l for l in r.stdout.splitlines() if l.strip()][:12]
    note = ["KNOWLEDGE GRAPH HTML VIEW IS STALE: the graph changed and its page still shows the previous one."]
    note.extend("  " + l for l in lines)
    note.append("  Regenerate it now with the command in that graph_html/README.md and stage it with the "
                "graph (pre-commit 35 refuses the commit while they disagree).")
    print(json.dumps({"hookSpecificOutput": {
        "hookEventName": "PostToolUse",
        "additionalContext": "\n".join(note)}}))


if __name__ == "__main__":
    try:
        main()
    except Exception:
        pass
