#!/usr/bin/env python3
"""A knowledge graph's HTML view describes the graph it was rendered from, not an earlier one.

visibility: public

THE RULE. Wherever a profile has an HTML view, `<knowledge_base_dir>/graph_html/<profile>_knowledge_graph.html`
written by `tools/render_kg_html.py`, the nodes and edges embedded in it must be the ones the profile's
graph `rag/graphs/<profile>.json` holds now. The page embeds its data at render time, so a rebuilt
graph leaves the page describing the previous one until it is regenerated, and nothing else notices.

HOW IT COMPARES. The expected page data is computed by the renderer's own `page_data()`, over every node
with at least one edge, exactly as the renderer does for this page; nodes and edges are compared as sets
of their full content, so a changed attribute (a seed description, a relation) is caught as well as a
missing node or edge. The page's targets, tested parameters and layout are not compared: they are
render options, not graph content.

MODES. With no flag, every profile with a page is checked from the working tree. With `--staged`, only
profiles whose graph JSON or page this commit stages are checked, each read from the index.

Exit 0 clean, 1 a page out of step with its graph (blocking in pre-commit check 35).

Usage:  python3 tools/check_kg_html_current.py [--staged] [--profile <p>]
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
from tools.render_kg_html import graph_from_json, page_data  # noqa: E402

MARKER = "const DATA = "


def page_path(profile: str, ms: dict) -> str:
    """Repo-relative path of the profile's full-graph page (the renderer's default location)."""
    return f"{ms.get('knowledge_base_dir', 'docs')}/graph_html/{profile}_knowledge_graph.html"


def embedded_data(html: str) -> dict | None:
    """The DATA object a rendered page embeds, or None if the page carries none."""
    i = html.find(MARKER)
    if i < 0:
        return None
    return json.JSONDecoder().raw_decode(html, i + len(MARKER))[0]


def _canon(items) -> list[str]:
    return sorted(json.dumps(x, sort_keys=True) for x in items)


def compare(graph: dict, html: str, rel: str) -> list[str]:
    """Problems with one page against its graph; [] when the page is in step."""
    data = embedded_data(html)
    if data is None:
        return [f"{rel}: no embedded `{MARKER.strip()}` object; not a render_kg_html page"]
    nodes, links = graph_from_json(graph)
    connected = {l["source"] for l in links} | {l["target"] for l in links}
    want_n, want_l, _ = page_data(nodes, links, connected)
    have_n, have_l = data.get("nodes", []), data.get("links", [])
    if _canon(want_n) == _canon(have_n) and _canon(want_l) == _canon(have_l):
        return []
    want_ids, have_ids = {n["id"] for n in want_n}, {n["id"] for n in have_n}
    pair = lambda l: f"{l['source']} -> {l['target']}"  # noqa: E731
    want_e, have_e = {pair(l) for l in want_l}, {pair(l) for l in have_l}
    msg = (f"{rel}: STALE against its graph: the page draws {len(have_n)} nodes and {len(have_l)} edges, "
           f"the graph now has {len(want_n)} connected nodes and {len(want_l)} edges")
    out = [msg]
    for label, items in (("nodes missing from the page", sorted(want_ids - have_ids)),
                         ("nodes on the page no longer in the graph", sorted(have_ids - want_ids)),
                         ("edges missing from the page", sorted(want_e - have_e)),
                         ("edges on the page no longer in the graph", sorted(have_e - want_e))):
        if items:
            out.append(f"  {label} ({len(items)}): " + ", ".join(items[:6]) + (" ..." if len(items) > 6 else ""))
    if len(out) == 1:
        out.append("  same nodes and edges, but their attributes differ (a description, a relation, a field)")
    return out


def _git(*args: str) -> str:
    r = subprocess.run(["git", "-C", str(REPO), *args], stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                       universal_newlines=True)
    return r.stdout if r.returncode == 0 else ""


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--staged", action="store_true", help="check only what this commit stages, read from the index")
    ap.add_argument("--profile", help="check one profile only")
    a = ap.parse_args(argv)

    milestones = json.loads((REPO / "rag/milestones.json").read_text())["milestones"]
    staged = set(_git("diff", "--cached", "--name-only", "--diff-filter=ACMR").split()) if a.staged else set()
    problems, checked = [], 0
    for profile, ms in sorted(milestones.items()):
        if a.profile and profile != a.profile:
            continue
        gpath, hpath = f"rag/graphs/{profile}.json", page_path(profile, ms)
        if a.staged:
            if gpath not in staged and hpath not in staged:
                continue
            html = _git("show", f":{hpath}")
            if not html:
                continue                      # no page for this profile in the commit: nothing to keep in step
            graph_txt = _git("show", f":{gpath}")
        else:
            if not (REPO / hpath).is_file():
                continue
            html = (REPO / hpath).read_text()
            graph_txt = (REPO / gpath).read_text() if (REPO / gpath).is_file() else ""
        if not graph_txt:
            problems.append(f"{hpath}: its graph {gpath} is missing")
            continue
        checked += 1
        problems += compare(json.loads(graph_txt), html, hpath)

    for p in problems:
        print(f"FAIL: {p}" if not p.startswith("  ") else p)
    if problems:
        print("Fix: regenerate the page with the command in its graph_html/README.md "
              "(python tools/render_kg_html.py --profile <profile> ...) and stage it with the graph.")
        return 1
    print(f"OK: {checked} knowledge-graph page(s) in step with their graphs")
    return 0


if __name__ == "__main__":
    sys.exit(main())
