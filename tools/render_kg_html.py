#!/usr/bin/env python
"""Render a RAG profile's knowledge graph as self-contained interactive HTML pages.

visibility: public
Author: Jing Tao with Claude on Perlmutter

Model-agnostic: it reads `rag/graphs/<profile>.json`, the `FATESKnowledgeGraph` node-link format
every builder writes (FATES, EcoSIM, PFLOTRAN), so it works for any registered profile.

Two pages are written to --out-dir:
  <profile>_knowledge_graph.html     every node that has at least one edge, coloured by type;
                                     search, type filters, a focus mode (k-hop neighbourhood of a
                                     node), and one-click focus on the calibration targets.
  <profile>_tested_parameters.html   (with --param-list) the parameters a case tests, the
                                     mechanisms they control and the outputs reachable from them,
                                     plus a coverage table (node / controls edge / output path).
Isolated nodes (no edge at all) are counted on the page and left off the canvas: an output the
model registers but no curated relation reaches is a fact worth stating, not a dot worth drawing.

Run:
  python tools/render_kg_html.py --profile ecosim-cb243228 \\
      --param-list use_cases/EcoSIM_Lusignan/parameters/ecosim_lusignan_param_list_r02b.csv \\
      --case EcoSIM_Lusignan --targets ECO_GPP_col ECO_RA_col ECO_RH_col ECO_ET_col
The pages load d3 7.9.0 from jsdelivr and embed their data; open them in any browser.
"""
from __future__ import annotations

import argparse
import csv
import json
import sys
from collections import deque
from datetime import date
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
from tools.kb_profile import kb_commit  # noqa: E402
D3 = "https://cdn.jsdelivr.net/npm/d3@7.9.0/dist/d3.min.js"


def load_graph(profile: str):
    g = json.loads((REPO / "rag/graphs" / f"{profile}.json").read_text())
    nodes = {n["id"]: n for n in g["nodes"]}
    links = [{**{k: v for k, v in e.items() if k not in ("source", "target")},
              "source": e["source"], "target": e["target"]} for e in g["links"]]
    return nodes, links


def param_names(paths):
    out = []
    for p in paths:
        rows = [ln for ln in open(p) if ln.strip() and not ln.lstrip().startswith("#")]
        for r in csv.DictReader(rows):
            n = (r.get("name") or "").strip()
            if n and n not in out:
                out.append(n)
    return out


def coverage(nodes, links, names):
    out = {}
    for e in links:
        out.setdefault(e["source"], []).append(e)
    rows = []
    for n in names:
        pid = f"parameter:{n}"
        node = nodes.get(pid)
        ctrl = [e["target"].split(":", 1)[1] for e in out.get(pid, [])
                if e["relation_type"] == "controls"]
        path = None
        if node:
            q, seen = deque([(pid, [pid])]), {pid}
            while q and not path:
                cur, pth = q.popleft()
                for e in out.get(cur, []):
                    t = e["target"]
                    if t in seen or nodes.get(t, {}).get("node_type") == "Category" or len(pth) > 3:
                        continue
                    seen.add(t)
                    if nodes.get(t, {}).get("node_type") == "Output":
                        path = " → ".join(x.split(":", 1)[1] for x in pth + [t])
                        break
                    q.append((t, pth + [t]))
        # An inert parameter (curated `inert: true`, or a file value the model never reads) has no
        # controls edge BY DESIGN: the builder refuses one, so its absence is the correct answer
        # and must not be painted as a coverage failure beside the real gaps.
        inert = bool(node and (node.get("inert") or node.get("file_backed") is False))
        rows.append({"name": n, "node": bool(node), "controls": ctrl, "path": path, "inert": inert,
                     "read_site": (node or {}).get("read_site", ""),
                     "file_backed": (node or {}).get("file_backed", True)})
    return rows


def subgraph_for(nodes, links, names, hops=3):
    out = {}
    for e in links:
        out.setdefault(e["source"], []).append(e)
    keep = set()
    for n in names:
        pid = f"parameter:{n}"
        if pid not in nodes:
            continue
        keep.add(pid)
        frontier = {pid}
        for _ in range(hops):
            nxt = set()
            for f in frontier:
                for e in out.get(f, []):
                    t = e["target"]
                    if nodes.get(t, {}).get("node_type") == "Category":
                        continue
                    if nodes.get(t, {}).get("node_type") == "Parameter" and e["relation_type"] == "depends_on":
                        if t.split(":", 1)[1] not in names:
                            continue
                    nxt.add(t)
            keep |= nxt
            frontier = nxt
    return keep


PAGE = r"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>__TITLE__</title>
<style>
:root{--bg:#ffffff;--fg:#1d1d1f;--muted:#6b6b70;--panel:#f5f5f7;--line:#d2d2d7;--accent:#0a66c2;
--cat:#8e8e93;--mech:#d97706;--par:#2563eb;--out:#059669;--tested:#dc2626;--edge:#9ca3af}
@media (prefers-color-scheme: dark){:root:not([data-theme="light"]){--bg:#161618;--fg:#ececf0;--muted:#a1a1aa;
--panel:#232327;--line:#3a3a40;--accent:#60a5fa;--cat:#a1a1aa;--mech:#f59e0b;--par:#60a5fa;--out:#34d399;--tested:#f87171;--edge:#5b5b63}}
:root[data-theme="dark"]{--bg:#161618;--fg:#ececf0;--muted:#a1a1aa;--panel:#232327;--line:#3a3a40;--accent:#60a5fa;
--cat:#a1a1aa;--mech:#f59e0b;--par:#60a5fa;--out:#34d399;--tested:#f87171;--edge:#5b5b63}
html,body{margin:0;height:100%}
body{background:var(--bg);color:var(--fg);font:14px/1.45 -apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif;display:flex;flex-direction:column}
header{padding:12px 16px;border-bottom:1px solid var(--line)}
h1{font-size:18px;margin:0 0 4px}
.sub{color:var(--muted);font-size:13px}
.bar{display:flex;flex-wrap:wrap;gap:8px;align-items:center;padding:8px 16px;border-bottom:1px solid var(--line)}
.bar input[type=search]{padding:6px 8px;border:1px solid var(--line);border-radius:6px;background:var(--panel);color:var(--fg);min-width:180px}
.bar button,.bar label{font-size:12px}
button{padding:5px 9px;border:1px solid var(--line);border-radius:6px;background:var(--panel);color:var(--fg);cursor:pointer}
button.on{border-color:var(--accent);color:var(--accent)}
main{flex:1;display:flex;min-height:0}
#canvas{flex:1;min-width:0;position:relative}
svg{width:100%;height:100%;display:block}
aside{width:340px;max-width:40vw;border-left:1px solid var(--line);overflow:auto;padding:12px 14px;background:var(--panel)}
aside h2{font-size:15px;margin:0 0 6px;word-break:break-all}
aside .kv{font-size:12px;margin:4px 0;word-break:break-word}
aside .k{color:var(--muted)}
aside ul{padding-left:18px;margin:4px 0;font-size:12px}
.legend{display:flex;gap:10px;flex-wrap:wrap;font-size:12px;color:var(--muted)}
.dot{display:inline-block;width:10px;height:10px;border-radius:50%;margin-right:4px;vertical-align:middle}
table{border-collapse:collapse;font-size:12px;width:100%}
th,td{border-bottom:1px solid var(--line);padding:4px 6px;text-align:left;vertical-align:top}
th{position:sticky;top:0;background:var(--panel)}
.bad{color:var(--tested);font-weight:600}
#tablewrap{max-height:38vh;overflow:auto;border-top:1px solid var(--line);padding:0 16px 8px}
@media (max-width:760px){main{flex-direction:column}aside{width:auto;max-width:none;border-left:0;border-top:1px solid var(--line);max-height:40vh}#canvas{min-height:55vh}}
</style>
<script src="__D3__"></script>
</head>
<body>
<header>
<h1>__HEADING__</h1>
<div class="sub">__SUBTITLE__</div>
</header>
<div class="bar">
<input type="search" id="q" placeholder="Search a node (e.g. DMRT, ECO_GPP_col)">
<span class="legend">
<span><span class="dot" style="background:var(--par)"></span>Parameter</span>
<span><span class="dot" style="background:var(--mech)"></span>Mechanism</span>
<span><span class="dot" style="background:var(--out)"></span>Output</span>
<span><span class="dot" style="background:var(--cat)"></span>Category</span>
<span><span class="dot" style="background:transparent;border:2px solid var(--tested)"></span>tested in __CASE__</span>
</span>
<span id="typebtns"></span>
<span id="targets"></span>
<button id="reset">Show all</button>
<button id="theme">Theme</button>
</div>
<main>
<div id="canvas"><svg id="svg"></svg></div>
<aside id="info"><h2>Click a node</h2><div class="kv">Click a node to see its attributes and edges; double-click to focus on its neighbourhood (2 hops). Drag to move, scroll to zoom.</div><div class="kv k" id="stats"></div></aside>
</main>
__TABLE__
<script>
const DATA = __DATA__;
const TESTED = new Set(DATA.tested);
const COLORS = {Parameter:"--par",Mechanism:"--mech",Output:"--out",Category:"--cat"};
const css = n => getComputedStyle(document.documentElement).getPropertyValue(n).trim();
const byId = new Map(DATA.nodes.map(n => [n.id, n]));
const adj = new Map(DATA.nodes.map(n => [n.id, []]));
DATA.links.forEach(l => { adj.get(l.source).push(l); adj.get(l.target).push(l); });
document.getElementById("stats").textContent = DATA.stats;
let hiddenTypes = new Set(DATA.hideByDefault);
let focus = null;
const svg = d3.select("#svg"), g = svg.append("g");
svg.call(d3.zoom().scaleExtent([0.05, 6]).on("zoom", e => g.attr("transform", e.transform)));
svg.append("defs").selectAll("marker").data(["controls","affects","depends_on","contains"]).join("marker")
  .attr("id", d => "m-" + d).attr("viewBox","0 -4 8 8").attr("refX",14).attr("refY",0)
  .attr("markerWidth",6).attr("markerHeight",6).attr("orient","auto")
  .append("path").attr("d","M0,-4L8,0L0,4").attr("fill", "var(--edge)");
const sim = d3.forceSimulation().force("charge", d3.forceManyBody().strength(-70))
  .force("link", d3.forceLink().id(d => d.id).distance(l => l.relation_type === "contains" ? 70 : 45))
  .force("x", d3.forceX().strength(0.04)).force("y", d3.forceY().strength(0.04))
  .force("collide", d3.forceCollide(9));
let link = g.append("g").selectAll("line"), node = g.append("g").selectAll("g");
function visible() {
  let ids;
  if (focus) {
    ids = new Set([focus]); let fr = new Set([focus]);
    for (let k = 0; k < 2; k++) { const nx = new Set();
      fr.forEach(id => adj.get(id).forEach(l => { const o = l.source.id||l.source, t = l.target.id||l.target;
        [o, t].forEach(x => { if (!ids.has(x)) { ids.add(x); nx.add(x); } }); })); fr = nx; }
  } else ids = new Set(DATA.nodes.map(n => n.id));
  const ns = DATA.nodes.filter(n => ids.has(n.id) && (!hiddenTypes.has(n.node_type) || n.id === focus));
  const keep = new Set(ns.map(n => n.id));
  const ls = DATA.links.filter(l => keep.has(l.source.id||l.source) && keep.has(l.target.id||l.target));
  return [ns, ls];
}
function render() {
  const [ns, ls] = visible();
  const w = svg.node().clientWidth, h = svg.node().clientHeight;
  link = link.data(ls, l => (l.source.id||l.source) + ">" + (l.target.id||l.target) + l.relation_type)
    .join("line").attr("stroke", "var(--edge)").attr("stroke-opacity", 0.7)
    .attr("stroke-width", l => l.relation_type === "controls" ? 1.4 : 1)
    .attr("stroke-dasharray", l => l.relation_type === "depends_on" ? "3,3" : (l.driver_kind === "indirect" ? "1,3" : null))
    .attr("marker-end", l => "url(#m-" + l.relation_type + ")");
  node = node.data(ns, d => d.id).join(enter => {
    const e = enter.append("g").call(d3.drag().on("start", (ev, d) => { if (!ev.active) sim.alphaTarget(0.3).restart(); d.fx = d.x; d.fy = d.y; })
      .on("drag", (ev, d) => { d.fx = ev.x; d.fy = ev.y; }).on("end", (ev, d) => { if (!ev.active) sim.alphaTarget(0); d.fx = null; d.fy = null; }));
    e.append("circle");
    e.append("text").attr("x", 8).attr("y", 3).attr("font-size", 10).attr("fill", "var(--fg)");
    e.on("click", (ev, d) => show(d)).on("dblclick", (ev, d) => { focus = d.id; render(); show(d); });
    return e; });
  node.select("circle").attr("r", d => d.node_type === "Category" ? 8 : d.node_type === "Mechanism" ? 7 : 5)
    .attr("fill", d => css(COLORS[d.node_type] || "--edge"))
    .attr("stroke", d => TESTED.has(d.label) && d.node_type === "Parameter" ? css("--tested") : "none")
    .attr("stroke-width", 2.5);
  node.select("text").text(d => (ns.length < 260 || d.node_type !== "Output" || TESTED.has(d.label)) ? d.label : "");
  sim.nodes(ns); sim.force("link").links(ls);
  sim.force("x").x(w / 2); sim.force("y").y(h / 2);
  sim.alpha(0.9).restart();
  sim.on("tick", () => { link.attr("x1", l => l.source.x).attr("y1", l => l.source.y).attr("x2", l => l.target.x).attr("y2", l => l.target.y);
    node.attr("transform", d => `translate(${d.x},${d.y})`); });
}
function esc(s) { return String(s ?? "").replace(/[&<>]/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;"}[c])); }
function show(d) {
  const keys = ["node_type","description","units","category","level","read_site","fortran_var","code_location","read_if_present","file_backed","file_backed_note","guard"];
  let h = `<h2>${esc(d.label)}</h2>`;
  keys.forEach(k => { if (d[k] !== undefined && d[k] !== null && d[k] !== "") h += `<div class="kv"><span class="k">${k}:</span> ${esc(typeof d[k] === "object" ? JSON.stringify(d[k]) : d[k])}</div>`; });
  const outE = DATA.links.filter(l => (l.source.id||l.source) === d.id), inE = DATA.links.filter(l => (l.target.id||l.target) === d.id);
  const lab = id => esc((byId.get(id.id||id) || {}).label || id);
  if (outE.length) h += `<div class="kv k">outgoing (${outE.length})</div><ul>` + outE.map(l => `<li>${l.relation_type} → ${lab(l.target)}${l.driver_kind ? " ("+l.driver_kind+")" : ""}</li>`).join("") + "</ul>";
  if (inE.length) h += `<div class="kv k">incoming (${inE.length})</div><ul>` + inE.map(l => `<li>${lab(l.source)} → ${l.relation_type}</li>`).join("") + "</ul>";
  h += `<div class="kv"><button onclick="focus='${d.id}';render()">Focus here</button></div>`;
  document.getElementById("info").innerHTML = h;
}
const tb = d3.select("#typebtns");
["Category","Mechanism","Parameter","Output"].forEach(t => tb.append("button").text(t).classed("on", !hiddenTypes.has(t))
  .on("click", function() { hiddenTypes.has(t) ? hiddenTypes.delete(t) : hiddenTypes.add(t); d3.select(this).classed("on", !hiddenTypes.has(t)); render(); }));
const tg = d3.select("#targets");
DATA.targets.forEach(t => { if (byId.has("output:" + t)) tg.append("button").text(t).on("click", () => { focus = "output:" + t; render(); show(byId.get(focus)); }); });
d3.select("#reset").on("click", () => { focus = null; render(); });
d3.select("#theme").on("click", () => { const r = document.documentElement; const cur = r.dataset.theme || (matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light"); r.dataset.theme = cur === "dark" ? "light" : "dark"; render(); });
d3.select("#q").on("change", function() { const v = this.value.trim().toLowerCase(); const hit = DATA.nodes.find(n => n.label.toLowerCase() === v) || DATA.nodes.find(n => n.label.toLowerCase().includes(v));
  if (hit) { focus = hit.id; render(); show(hit); } });
window.addEventListener("resize", render);
render();
</script>
</body>
</html>
"""


def page(profile, nodes, links, keep, tested, targets, case, heading, subtitle, table_html, hide):
    ns = [{**{k: v for k, v in nodes[i].items() if k != "id"}, "id": i,
           "label": nodes[i].get("name") or i.split(":", 1)[1]} for i in keep]
    ls = [l for l in links if l["source"] in keep and l["target"] in keep]
    n_iso = sum(1 for i in nodes if i not in {l["source"] for l in links} | {l["target"] for l in links})
    stats = (f"Profile {profile}: {len(nodes)} nodes, {len(links)} edges in the graph; this page draws "
             f"{len(ns)} nodes and {len(ls)} edges. {n_iso} nodes have no edge at all and are not drawn.")
    data = {"nodes": ns, "links": ls, "tested": tested, "targets": targets, "stats": stats,
            "hideByDefault": hide}
    return (PAGE.replace("__TITLE__", heading).replace("__HEADING__", heading)
            .replace("__SUBTITLE__", subtitle).replace("__CASE__", case or "the case")
            .replace("__D3__", D3).replace("__TABLE__", table_html)
            .replace("__DATA__", json.dumps(data, separators=(",", ":"))))


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--profile", required=True)
    ap.add_argument("--param-list", action="append", default=[])
    ap.add_argument("--case", default="")
    ap.add_argument("--targets", nargs="*", default=[])
    ap.add_argument("--out-dir", help="default: the profile's knowledge_base_dir/graph_html")
    a = ap.parse_args()
    ms = json.loads((REPO / "rag/milestones.json").read_text())["milestones"][a.profile]
    out_dir = Path(a.out_dir) if a.out_dir else REPO / ms.get("knowledge_base_dir", "docs") / "graph_html"
    out_dir.mkdir(parents=True, exist_ok=True)
    nodes, links = load_graph(a.profile)
    tested = param_names(a.param_list)
    connected = {l["source"] for l in links} | {l["target"] for l in links}
    commit = (kb_commit(ms) or "")[:8]          # the base, or its last in-place patch
    stamp = f"profile {a.profile} (model commit {commit}), rendered {date.today().isoformat()} by tools/render_kg_html.py"
    full = page(a.profile, nodes, links, connected, tested, a.targets, a.case,
                f"{a.profile} knowledge graph",
                f"Every node with at least one edge. {stamp}. Category nodes are hidden by default (hubs).",
                "", ["Category"])
    (out_dir / f"{a.profile}_knowledge_graph.html").write_text(full)
    written = [out_dir / f"{a.profile}_knowledge_graph.html"]
    if tested:
        cov = coverage(nodes, links, tested)
        keep = subgraph_for(nodes, links, tested)
        inert = [r for r in cov if r["inert"]]
        bad = [r for r in cov if not r["inert"] and not (r["node"] and r["controls"] and r["path"])]
        rows = "".join(
            f"<tr><td>{r['name']}</td><td{' class=bad' if not r['node'] else ''}>{'yes' if r['node'] else 'NO'}</td>"
            + (f"<td>inert: no controls edge, by design</td>" if r["inert"] else
               f"<td{' class=bad' if not r['controls'] else ''}>{', '.join(r['controls']) or 'none'}</td>")
            + f"<td{' class=bad' if not r['path'] and not r['inert'] else ''}>{r['path'] or 'none within 3 hops'}</td>"
            f"<td>{r['read_site'] or ('not read on the live path' if r['node'] else '')}</td></tr>" for r in cov)
        table = (f"<div id='tablewrap'><p class='sub'>{len(tested)} tested parameters; "
                 f"{len(tested) - len(bad) - len(inert)} have a node, a controls edge and an output path; "
                 f"{len(inert)} are inert in the model (no controls edge, by design); {len(bad)} have a gap.</p>"
                 "<table><thead><tr><th>parameter</th><th>node</th><th>controls</th><th>shortest path to an output</th>"
                 f"<th>read at (live path)</th></tr></thead><tbody>{rows}</tbody></table></div>")
        sub = page(a.profile, nodes, links, keep, tested, a.targets, a.case,
                   f"{a.case or 'Case'} tested parameters in {a.profile}",
                   f"The {len(tested)} parameters {a.case or 'the case'} tests, the mechanisms they control, and the outputs "
                   f"reachable within three hops. {stamp}.", table, [])
        (out_dir / f"{a.profile}_tested_parameters.html").write_text(sub)
        written.append(out_dir / f"{a.profile}_tested_parameters.html")
    for w in written:
        print(f"wrote {w.relative_to(REPO) if w.is_relative_to(REPO) else w} ({w.stat().st_size // 1024} kB)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
