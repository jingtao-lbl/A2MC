#!/usr/bin/env python
"""Draw the FULL mechanism network of a set of parameters: the knowledge graph's edges plus its gaps.

visibility: public
Author: Jing Tao with Claude on Perlmutter

`write-report` requires each cycle report to show the mechanism network of every parameter the cycle
tested, as a figure. This draws it from the profile's knowledge graph (the same graph
`tools/kb_network.py` queries) and overlays the GAP CANDIDATES the cycle staged
(`graph_gap_candidates.yaml`, `tools/graph_gaps.py`), so the reader sees the whole mechanism and
which part of it the graph does not yet hold.

WHAT IS DRAWN.
  * every directed `parameter -> controls -> mechanism -> affects -> output` path, at most --hops
    edges, from each named parameter to each named output (the scored variables);
  * the mechanisms each named parameter controls, even where they reach no named output;
  * `depends_on` couplings among the named parameters (dotted, undirected);
  * every stored controls/affects edge between two nodes already drawn;
  * every gap candidate touching a drawn node, iterated so a chain through a NEW node is drawn
    whole: dashed vermillion, labelled with its id, its source line listed beneath the figure.
Columns: parameters, mechanisms, other outputs, the named outputs. A node the graph does not have is
outlined dashed. `--annotate` adds a small line under a node (e.g. what a run measured there),
from a CSV with columns `node,label`.

Writes <out>.png and <out>.json (the drawn nodes and edges, and what each edge rests on).

Usage:
    python tools/plot_kb_network.py --model ecosim --params RTFQ VRNXI DMLF \\
        --outputs ECO_GPP_col ECO_RH_col ECO_RA_col ECO_ET_col --hops 3 \\
        --gaps <report dir>/graph_gap_candidates.yaml [--annotate measured.csv] \\
        --title "<the finding>" --out <report dir>/fig_mechanism_graph
Exit 0 drawn; 1 a gap file fails `tools/graph_gaps.py check`; 2 bad usage, no profile, no node found.
"""
from __future__ import annotations

import argparse
import csv
import importlib.util
import json
import sys
import textwrap
from collections import defaultdict
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
FLOW = ("controls", "affects")
COL = {"parameter": 0, "mechanism": 1, "output": 2, "named": 3, "category": 1}
FILL = {"parameter": "#D6E9F8", "mechanism": "#D4EFE5", "output": "#EEEEEE", "category": "#F3E8D3"}
EDGE = {"parameter": "#0072B2", "mechanism": "#009E73", "output": "#777777", "category": "#B07D2B"}
GAP = "#D55E00"
DIRECT = "#56B4E9"


def _load(name: str, rel: str):
    spec = importlib.util.spec_from_file_location(name, REPO / rel)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


def build(g, params, outputs, mechanisms, hops, gap_docs):
    """-> (nodes {id: info}, edges [(a, rel, b, kind, meta)], gaps used [candidate dicts])."""
    nodes: dict[str, dict] = {}
    edges: dict[tuple[str, str, str], tuple[str, dict]] = {}

    def add(nid, named=False, new=None):
        typ = nid.split(":", 1)[0]
        info = nodes.setdefault(nid, dict(type=typ, named=False, in_graph=nid in g.nodes, desc=""))
        info["named"] |= named
        if new:
            info["desc"] = new
        return nid

    for p in params:
        add(p, named=True)
        for t, at in g.out.get(p, []):
            if at["relation_type"] == "controls" and t.startswith("mechanism:"):
                add(t)
                edges[(p, "controls", t)] = ("stored", {})
    for m in mechanisms:
        add(m, named=True)
    for o in outputs:
        add(o, named=True)
    for p in params:
        for o in outputs:
            for path in g.paths(p, o, hops):
                for a, b in zip(path, path[1:]):
                    add(a), add(b)
                    rel = next(at["relation_type"] for t, at in g.out[a] if t == b and at["relation_type"] in FLOW)
                    edges[(a, rel, b)] = ("stored", {})
    for i, p in enumerate(params):
        for q in params[i + 1:]:
            if any(t == q and at["relation_type"] == "depends_on" for t, at in g.out.get(p, [])) or \
                    any(t == p and at["relation_type"] == "depends_on" for t, at in g.out.get(q, [])):
                edges[(p, "depends_on", q)] = ("stored", {})
    used, changed = [], True
    cands = [(c, d.get("new_nodes") or {}) for d in gap_docs for c in d["candidates"]]
    while changed:
        changed = False
        for c, new_nodes in cands:
            if c in used or not (c["from"] in nodes or c["to"] in nodes):
                continue
            for end in ("from", "to"):
                add(c[end], new=new_nodes.get(c[end]))
            edges[(c["from"], c["relation"], c["to"])] = ("gap", c)
            used.append(c)
            changed = True
    drawn = set(nodes)
    for a in drawn:
        for b, at in g.out.get(a, []):
            if b in drawn and at["relation_type"] in FLOW and (a, at["relation_type"], b) not in edges:
                edges[(a, at["relation_type"], b)] = ("stored", {})
    return nodes, [(a, r, b, k, m) for (a, r, b), (k, m) in edges.items()], used


def layout(nodes, edges, params):
    """Columns by type, ordered within a column by the mean row of each node's neighbours."""
    has_inner = any(i["type"] == "output" and not i["named"] for i in nodes.values())
    col = {}
    for n, i in nodes.items():
        c = COL["named" if (i["type"] == "output" and i["named"]) else i["type"]]
        col[n] = c if (c != 3 or has_inner) else 2
    cols = defaultdict(list)
    for n in nodes:
        cols[col[n]].append(n)
    cols[0] = [p for p in params if p in nodes] + [n for n in cols[0] if n not in params]
    nbr = defaultdict(set)
    for a, _, b, _, _ in edges:
        nbr[a].add(b), nbr[b].add(a)
    row = {n: i for c in cols for i, n in enumerate(cols[c])}
    for _ in range(3):
        for c in sorted(cols)[1:]:
            cols[c].sort(key=lambda n: (sum(row[m] for m in nbr[n] if col[m] < c) /
                                        max(1, sum(1 for m in nbr[n] if col[m] < c))) if any(col[m] < c for m in nbr[n]) else 1e9)
            for i, n in enumerate(cols[c]):
                row[n] = i
    height = max(len(v) for v in cols.values())
    pos = {}
    for c, members in cols.items():
        off = (height - len(members)) / 2.0
        for i, n in enumerate(members):
            pos[n] = (c, -(off + i))
    return pos, height, max(cols) + 1


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--model", required=True)
    ap.add_argument("--profile")
    ap.add_argument("--params", nargs="+", required=True)
    ap.add_argument("--outputs", nargs="+", required=True, help="the scored variables the parameters should reach")
    ap.add_argument("--mechanisms", nargs="*", default=[])
    ap.add_argument("--hops", type=int, default=3)
    ap.add_argument("--gaps", nargs="*", type=Path, default=[], help="graph_gap_candidates.yaml file(s)")
    ap.add_argument("--annotate", type=Path, help="CSV node,label: a small line drawn under that node")
    ap.add_argument("--title", default="")
    ap.add_argument("--out", required=True, type=Path, help="output path without extension")
    a = ap.parse_args(argv)

    kp = _load("_kb_profile", "tools/kb_profile.py")
    try:
        profile = a.profile or kp.resolve_or_default(a.model).profile
    except kp.NoMatch as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    gp = REPO / "rag" / "graphs" / f"{profile}.json"
    if not gp.is_file():
        print(f"ERROR: rag/graphs/{profile}.json absent", file=sys.stderr)
        return 2
    kn = _load("_kb_network", "tools/kb_network.py")
    g = kn.Graph(gp)
    gg = _load("_graph_gaps", "tools/graph_gaps.py")
    gap_docs = []
    for f in a.gaps:
        errs, doc = gg.check(f, g)
        if errs:
            print(f"ERROR: {f} fails tools/graph_gaps.py check:\n  " + "\n  ".join(errs), file=sys.stderr)
            return 1
        if doc["profile"] != profile:
            print(f"ERROR: {f} is for profile {doc['profile']}, the graph drawn is {profile}", file=sys.stderr)
            return 1
        gap_docs.append(doc)

    def ids(kind, names):
        out = []
        for n in names:
            found = g.find(kind, n) or [f"{kind}:{n}"]
            out += found
        return out
    params, outputs, mechs = ids("parameter", a.params), ids("output", a.outputs), ids("mechanism", a.mechanisms)
    absent = [n for n in params + outputs + mechs if n not in g.nodes]
    nodes, edges, used = build(g, params, outputs, mechs, a.hops, gap_docs)
    still = [n for n in absent if not nodes.get(n, {}).get("desc")]
    if len(still) == len(params + outputs + mechs):
        print("ERROR: no named entity is a node of the graph or of a gap file", file=sys.stderr)
        return 2
    notes = {}
    if a.annotate:
        with open(a.annotate) as fh:
            for r in csv.DictReader(fh):
                notes.setdefault(r["node"] if ":" in r["node"] else next(
                    (n for n in nodes if n.split(":", 1)[1] == r["node"]), r["node"]), []).append(r["label"])

    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.lines import Line2D
    plt.rcParams.update({"savefig.dpi": 200, "font.size": 8.5, "axes.titlesize": 10, "legend.fontsize": 8,
                         "legend.frameon": False})
    pos, height, ncol = layout(nodes, edges, params)
    gap_lines = [f"{c['id']}: {c['from'].split(':', 1)[1]} --{c['relation']}--> {c['to'].split(':', 1)[1]}  "
                 f"[{', '.join(c['source']) if isinstance(c['source'], list) else c['source']}]  {c['claim']}" for c in used]
    foot = sum(len(textwrap.wrap(s, 170)) for s in gap_lines)
    fig_h = max(3.5, 0.62 * height + 1.6 + 0.17 * foot)
    fig, ax = plt.subplots(figsize=(3.6 * ncol + 1.0, fig_h))
    ax.set_xlim(-0.55, ncol - 0.45)
    ax.set_ylim(-height - 0.3, 0.9)
    ax.axis("off")
    heads = ["parameters", "mechanisms", "other outputs" if ncol == 4 else "outputs", "scored outputs"]
    for c in range(ncol):
        ax.text(c, 0.7, heads[c] if ncol == 4 else (heads[c] if c < 2 else "outputs"), ha="center",
                fontsize=9, fontweight="bold", color="0.3")
    def label_of(n, i):
        name = n.split(":", 1)[1]
        return "\n".join(textwrap.wrap(name.replace("_", " ") if i["type"] == "mechanism" else name, 22))
    # half-width of each node's box in data units, so an arrow starts and ends at the box edge
    unit_in = (3.6 * ncol + 1.0) / ncol
    hw = {n: 0.5 * max(len(l) for l in label_of(n, i).split("\n")) * 0.075 / unit_in + 0.05 for n, i in nodes.items()}
    for a_, rel, b, kind, meta in edges:
        (x0, y0), (x1, y1) = pos[a_], pos[b]
        if rel == "depends_on":
            ax.annotate("", xy=(x1 - hw[b], y1), xytext=(x0 - hw[a_], y0),
                        arrowprops=dict(arrowstyle="-", ls=":", color="0.5", lw=1.0,
                                        connectionstyle="arc3,rad=-0.5", shrinkA=2, shrinkB=2))
            continue
        gap = kind == "gap"
        direct = abs(x1 - x0) > 1                     # a parameter -affects-> output edge: no mechanism named
        rad = (0.32 if y1 >= y0 else -0.32) if direct else 0.06
        color = GAP if gap else (DIRECT if direct else "0.45")
        ax.annotate("", xy=(x1 - hw[b], y1), xytext=(x0 + hw[a_], y0),
                    arrowprops=dict(arrowstyle="-|>", color=color, lw=1.4 if gap else 0.9,
                                    ls="--" if gap else "-", mutation_scale=9, shrinkA=1, shrinkB=1,
                                    connectionstyle=f"arc3,rad={rad}"))
        if gap:
            ax.text((x0 + hw[a_] + x1 - hw[b]) / 2, (y0 + y1) / 2 + 0.12, meta["id"], color=GAP, fontsize=8,
                    fontweight="bold", ha="center", va="bottom", bbox=dict(boxstyle="round,pad=0.12", fc="white", ec="none"))
    for n, i in nodes.items():
        x, y = pos[n]
        ax.text(x, y, label_of(n, i), ha="center", va="center", fontsize=8.5 if i["named"] else 8,
                fontweight="bold" if i["named"] else "normal",
                bbox=dict(boxstyle="round,pad=0.35", fc=FILL.get(i["type"], "white"),
                          ec=GAP if not i["in_graph"] else EDGE.get(i["type"], "0.4"),
                          ls="--" if not i["in_graph"] else "-", lw=1.4 if (i["named"] or not i["in_graph"]) else 0.8))
        for k, note in enumerate(notes.get(n, [])):
            ax.text(x, y - 0.3 - 0.17 * k, note, ha="center", va="top", fontsize=7.2, color="0.2")
    handles = [Line2D([], [], color="0.45", lw=0.9, label=f"edge in the knowledge graph ({profile})"),
               Line2D([], [], color=DIRECT, lw=0.9, label="parameter affects output directly (graph; no mechanism named)"),
               Line2D([], [], color=GAP, lw=1.4, ls="--", label="gap: confirmed in model source, absent from the graph"),
               Line2D([], [], color="0.5", lw=1.0, ls=":", label="depends_on coupling (graph)")]
    ax.legend(handles=handles, loc="lower left", bbox_to_anchor=(0.0, 1.0), ncol=2, fontsize=8)
    if gap_lines:
        fig.text(0.01, 0.005, "\n".join(l for s in gap_lines for l in textwrap.wrap(s, 170)),
                 fontsize=7.4, color="0.2", va="bottom", family="monospace")
    if a.title:
        fig.suptitle(a.title, fontsize=10)
    fig.tight_layout(rect=(0, 0.02 + 0.016 * foot, 1, 0.97 if a.title else 1))
    a.out.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(a.out.with_suffix(".png"), bbox_inches="tight")
    a.out.with_suffix(".json").write_text(json.dumps(dict(
        profile=profile, params=params, outputs=outputs, hops=a.hops, gap_files=[str(f) for f in a.gaps],
        nodes=[dict(id=n, **i) for n, i in nodes.items()],
        edges=[dict(source=x, relation=r, target=y, kind=k, gap_id=m.get("id"), gap_source=m.get("source"))
               for x, r, y, k, m in edges],
        absent_named=[n for n in still]), indent=1))
    n_gap = sum(1 for e in edges if e[3] == "gap")
    print(f"{profile}: {len(nodes)} node(s), {len(edges) - n_gap} graph edge(s), {n_gap} gap edge(s) -> "
          f"{a.out.with_suffix('.png')}" + (f"; named but in neither graph nor gaps: {', '.join(still)}" if still else ""))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
