#!/usr/bin/env python
"""Query the knowledge base for the parameter-mechanism-output network around a set of names.

visibility: public
Author: Jing Tao with Claude on Perlmutter

The USE side of the knowledge base, as opposed to the tools that build, validate and patch it. It
queries all three tiers for the parameters, mechanisms and outputs you name, and writes one stamped
artifact a phase log cites (`check_calibration_log_conformance.py` C13 requires it for Phase 3, 4 and 6, and for a diagnose-forensics finding):

  Tier 1  technical documents and the codebase wiki pinned to the profile's commit: every line that
          names the entity, with file:line, and whether that line itself cites model source.
  Tier 2  the two-layer knowledge graph (auto-extracted structure plus the curated
          parameter-mechanism-output network): the edges around each entity, whether each named
          parameter REACHES each named output, and the curated seed entry behind each node; plus
          vector search over the indexed corpus.
  Tier 3  the two-layer adaptive memory: the model-level and the case-level gained knowledge
          (discoveries, experiments, failed approaches, parameter knowledge) that mention the entity.

Then the source: the artifact ends with the code locations the KB itself cites, which is where the
confirming read starts. The KB first, source to confirm (`query-knowledge-base`).

The profile is never typed: `--profile`, else `tools/kb_profile.py` resolves it for the model.

Usage:
  python tools/kb_network.py --model ecosim --params RMOM VCMX --outputs ECO_GPP_col \\
      --case EcoSIM_Lusignan --out-dir use_cases/EcoSIM_Lusignan/memory/phase_results/<stem>
  python tools/kb_network.py --model pflotran --params RATE_CONSTANT --rag-k 0 --out-dir <dir>
Writes kb_network.md and kb_network.json in --out-dir, and a summary on stdout.
Exit 0 written; 1 written, but no named entity is a node of the graph; 2 bad usage or no profile.
"""
from __future__ import annotations

import argparse
import datetime as _dt
import importlib.util
import json
import os
import re
import subprocess
import sys
from collections import defaultdict
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
SCHEMA = 1
_SRC_CITE = re.compile(r"[\w./-]+\.(?:F90|f90|F|f|c|cc|cpp|h|hh|hpp):\d+")
_FLOW = ("controls", "affects")          # the relations a parameter -> mechanism -> output path uses


def _load(name: str, rel: str):
    spec = importlib.util.spec_from_file_location(name, REPO / rel)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


def _git_files(*dirs: str) -> list[str]:
    out = subprocess.run(["git", "-C", str(REPO), "ls-files", "--", *dirs],
                         capture_output=True, text=True).stdout
    return [l for l in out.splitlines() if l.endswith((".md", ".rst", ".txt"))]


# --------------------------------------------------------------------------- tier 2: graph
class Graph:
    def __init__(self, path: Path):
        g = json.loads(path.read_text())
        self.nodes = {n["id"]: n for n in g["nodes"]}
        self.out, self.inn = defaultdict(list), defaultdict(list)
        for e in g["links"]:
            attrs = {k: v for k, v in e.items() if k not in ("source", "target", "weight")}
            self.out[e["source"]].append((e["target"], attrs))
            self.inn[e["target"]].append((e["source"], attrs))

    def find(self, kind: str, name: str) -> list[str]:
        """Node ids for `name`: exact, then FATES's per-PFT copies, then case-insensitive."""
        exact = f"{kind}:{name}"
        if exact in self.nodes:
            return [exact]
        pft = [n for n in self.nodes if n.startswith(exact + ":pft")]
        if pft:
            return pft
        low = exact.lower()
        return [n for n in self.nodes if n.lower() == low]

    def edges_around(self, nid: str) -> list[tuple[str, str, str, dict]]:
        rows = [(nid, a["relation_type"], t, a) for t, a in self.out[nid] if a["relation_type"] != "contains"]
        rows += [(s, a["relation_type"], nid, a) for s, a in self.inn[nid] if a["relation_type"] != "contains"]
        return rows

    def category_of(self, nid: str) -> list[str]:
        return [s for s, a in self.inn[nid] if a["relation_type"] == "contains" and s.startswith("category:")]

    def paths(self, src: str, dst: str, hops: int) -> list[list[str]]:
        """Directed paths src -> dst along controls/affects, at most `hops` edges."""
        found, stack = [], [[src]]
        while stack:
            p = stack.pop()
            if len(p) - 1 >= hops:
                continue
            for t, a in self.out[p[-1]]:
                if a["relation_type"] not in _FLOW or t in p:
                    continue
                if t == dst:
                    found.append(p + [t])
                elif t.startswith("mechanism:"):
                    stack.append(p + [t])
        return sorted(found, key=len)


# --------------------------------------------------------------------------- tier 1: documents
def doc_hits(names: list[str], ms: dict, per_name: int) -> dict:
    """Lines naming each entity in the profile's documents: its pinned wiki, never another
    profile's, and the knowledge base's other documents."""
    if ms.get("adapter"):
        roots = [ms.get("knowledge_base_dir") or ""]
        own = {ms.get("model_wiki_subdir")}
    else:                                                   # FATES/ELM: two knowledge bases
        roots = ["docs/fates-knowledge-base", "docs/elm-knowledge-base"]
        own = {ms.get("fates_wiki_subdir"), ms.get("elm_wiki_subdir")}
    files = [f for f in _git_files(*[r for r in roots if r])
             if not any(("-codebase-wiki-" in part and part not in own) for part in f.split("/"))]
    pats = {n: re.compile(r"(?<![\w])%s(?![\w])" % re.escape(n)) for n in names}
    hits = {n: {"count": 0, "lines": []} for n in names}
    for f in files:
        try:
            lines = (REPO / f).read_text(encoding="utf-8", errors="replace").splitlines()
        except OSError:
            continue
        for i, line in enumerate(lines, 1):
            for n, pat in pats.items():
                if pat.search(line):
                    h = hits[n]
                    h["count"] += 1
                    if len(h["lines"]) < per_name:
                        h["lines"].append({"file": f, "line": i, "cites_source": bool(_SRC_CITE.search(line)),
                                           "text": line.strip()[:220]})
    return hits


# --------------------------------------------------------------------------- tier 2: seed + vectors
def seed_entries(seed_path: Path, kinds: dict[str, list[str]]) -> dict:
    import yaml
    seed = yaml.safe_load(seed_path.read_text()) or {}
    out = {}
    for kind, block in (("params", "parameters"), ("mechanisms", "mechanisms"), ("outputs", "outputs")):
        for n in kinds.get(kind, []):
            e = (seed.get(block) or {}).get(n)
            if isinstance(e, dict):
                out[n] = {k: (v if not isinstance(v, str) else v[:400]) for k, v in e.items() if not k.startswith("_")}
    return out


def vector_hits(profile: str, ms: dict, query: str, k: int) -> dict:
    if k <= 0:
        return {"skipped": "--rag-k 0"}
    try:
        sys.path.insert(0, str(REPO))
        from rag.vector_store import FATESVectorStore
        vs = FATESVectorStore(persist_dir=str(REPO / "rag" / "chroma_db" / profile),
                              collection_name=ms.get("collection_name") or "fates_knowledge",
                              require_existing=True)
        res = vs.query(query, n_results=k)
    except Exception as exc:                                   # report, never fail the whole query
        return {"error": f"{type(exc).__name__}: {exc}"}
    return {"query": query, "results": [{"source": r.get("source"), "type": r.get("type"),
                                         "distance": r.get("distance"),
                                         "text": (r.get("content") or "")[:240].replace("\n", " ")}
                                        for r in res]}


# --------------------------------------------------------------------------- tier 3: memory
def memory_hits(store: Path, names: list[str], cap: int) -> dict:
    out = {"store": str(store.relative_to(REPO)) if store.is_relative_to(REPO) else str(store),
           "present": store.is_dir(), "files": {}}
    if not store.is_dir():
        return out
    pats = [re.compile(r"(?<![\w])%s(?![\w])" % re.escape(n)) for n in names]
    for f in sorted(store.glob("*.json")):
        try:
            data = json.loads(f.read_text())
        except (OSError, ValueError):
            continue
        # Three shapes are live: a list of entries under a store key (`{"failed_approaches": [...]}`),
        # a keyed collection under it (`{"parameters": {"FCO2": {...}}}`), and entries stored as
        # top-level keys of their own (a case's `{"et_seasonal_error_is_one_axis": {...}}`).
        items = []
        for key, val in (data.items() if isinstance(data, dict) else [("", data)]):
            if str(key).startswith("_"):
                continue
            if isinstance(val, list):
                items += [(key, None, e) for e in val]
            elif isinstance(val, dict) and val and all(isinstance(v, dict) for v in val.values()):
                items += [(key, k, e) for k, e in val.items()]
            elif isinstance(val, dict):
                items.append((key, key, val))
        entries = []
        for key, label, e in items:
            if not any(p.search(json.dumps(e, default=str)) for p in pats):
                continue
            if isinstance(e, dict):
                label = label or e.get("id") or e.get("name") or e.get("approach") or e.get("title")
                text = (e.get("description") or e.get("statement") or e.get("why_failed") or e.get("mechanism")
                        or e.get("outcome") or e.get("measured") or "")
            else:
                text = str(e)
            entries.append({"key": key, "label": str(label)[:120] if label else None, "text": str(text)[:240]})
        if entries:
            out["files"][f.name] = {"matches": len(entries), "entries": entries[:cap]}
    return out


# --------------------------------------------------------------------------- report
def _md_cell(s) -> str:
    return str(s).replace("|", "\\|").replace("\n", " ")


def write_markdown(r: dict, path: Path) -> None:
    q, t2, L = r["query"], r["tier2"], []
    L += [f"# Knowledge-base network: {', '.join(q['params'] + q['mechanisms'] + q['outputs'])}", "",
          f"**Generated by:** `{r['generated_by']}`",
          f"**Profile:** {r['profile']} (model {r['model']}; knowledge base at {r['kb_commit'][:8]}; "
          f"{r['patches']} patch(es))",
          f"**Queried:** {r['queried_at']}", "",
          "The three tiers, the knowledge base first; then the source, to confirm (`query-knowledge-base`).", ""]
    L += ["## Reachability (Tier 2 graph)", ""]
    if t2["reach"]:
        L += ["| parameter | output | path(s) |", "|---|---|---|"]
        for x in t2["reach"]:
            p = " ; ".join(" -> ".join(n.split(":", 1)[1] for n in path) for path in x["paths"][:3])
            L.append(f"| {x['param']} | {x['output']} | {_md_cell(p) if p else '**NOT REACHABLE** within ' + str(q['hops']) + ' edges'} |")
    else:
        L.append("Name both a parameter and an output to test reachability.")
    L += ["", "## Tier 2 — knowledge graph: the network around each entity", ""]
    for n, info in t2["entities"].items():
        if not info["nodes"]:
            L += [f"- **{n}**: not a node of the graph", ""]
            continue
        cats = ", ".join(c.split(":", 1)[1] for c in info["categories"]) or "none"
        L += [f"**{n}** ({info['kind']}; category: {cats}; {len(info['edges'])} edge(s))", "",
              "| from | relation | to | attributes |", "|---|---|---|---|"]
        for e in info["edges"][:40]:
            attrs = ", ".join(f"{k}={v}" for k, v in e["attrs"].items() if k != "relation_type")
            L.append(f"| {e['src']} | {e['rel']} | {e['dst']} | {_md_cell(attrs)} |")
        if len(info["edges"]) > 40:
            L.append(f"| … | | {len(info['edges']) - 40} more in kb_network.json | |")
        L.append("")
    L += ["## Tier 2 — curated seed entries", ""]
    for n, e in r["tier2"]["seed"].items():
        L.append(f"- **{n}**: " + "; ".join(f"{k}: {_md_cell(v)}" for k, v in e.items()))
    if not r["tier2"]["seed"]:
        L.append("None of the names has a curated seed entry.")
    v = r["tier2"]["vectors"]
    L += ["", "## Tier 2 — vector search", ""]
    if "results" in v:
        L += [f"Query: `{v['query']}`", "", "| source | type | distance | text |", "|---|---|---|---|"]
        L += [f"| {_md_cell(x['source'])} | {x['type']} | {x['distance']:.3f} | {_md_cell(x['text'])} |"
              if isinstance(x["distance"], (int, float)) else
              f"| {_md_cell(x['source'])} | {x['type']} | | {_md_cell(x['text'])} |" for x in v["results"]]
    else:
        L.append(f"Not run: {v.get('skipped') or v.get('error')}")
    L += ["", "## Tier 1 — technical documents and codebase wiki", ""]
    for n, h in r["tier1"].items():
        L.append(f"- **{n}**: {h['count']} line(s)" + ("" if h["count"] else " — **absent from the documents**"))
        L += [f"  - `{x['file']}:{x['line']}`{' (cites source)' if x['cites_source'] else ''}: {_md_cell(x['text'])}"
              for x in h["lines"]]
    L += ["", "## Tier 3 — adaptive memory", ""]
    for layer, m in r["tier3"].items():
        if not m["present"]:
            L.append(f"- **{layer}** (`{m['store']}`): store absent")
            continue
        if not m["files"]:
            L.append(f"- **{layer}** (`{m['store']}`): nothing mentions these names")
        for f, d in m["files"].items():
            L.append(f"- **{layer}** `{f}`: {d['matches']} entr(ies)")
            L += [f"  - {_md_cell(x['label'] or x['key'])}: {_md_cell(x['text'])}" for x in d["entries"]]
    L += ["", "## Gaps", ""]
    L += [f"- {g}" for g in r["gaps"]] or ["None found."]
    L += ["", "## Then the source: where the knowledge base points", ""]
    L += [f"- `{c}`" for c in r["source_pointers"]] or ["The knowledge base cites no source location for these names."]
    path.write_text("\n".join(L) + "\n")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--model", required=True, help="ecosim, pflotran, ats, or fates")
    ap.add_argument("--profile", help="a registered profile (default: tools/kb_profile.py resolves it)")
    ap.add_argument("--params", nargs="*", default=[])
    ap.add_argument("--mechanisms", nargs="*", default=[])
    ap.add_argument("--outputs", nargs="*", default=[])
    ap.add_argument("--case", help="the case, e.g. EcoSIM_Lusignan, for the case-level adaptive memory "
                                   "(a use_cases/<case> path is accepted too)")
    ap.add_argument("--hops", type=int, default=2, help="max edges on a parameter -> output path (default 2)")
    ap.add_argument("--rag-k", type=int, default=5, help="vector hits to keep (0 skips vector search)")
    ap.add_argument("--per-name", type=int, default=6, help="document lines kept per name (default 6)")
    ap.add_argument("--out-dir", required=True, help="where kb_network.md/.json go, normally phase_results/<stem>/")
    a = ap.parse_args()
    if not (a.params or a.mechanisms or a.outputs):
        print("ERROR: name at least one --params, --mechanisms or --outputs", file=sys.stderr)
        return 2
    if a.case:
        # Accept the path form as well as the bare name, and refuse a case that is not there: a
        # wrong value used to resolve to use_cases/use_cases/<case> and report the case layer as
        # "store absent", which reads as an empty store rather than as a typo.
        a.case = Path(a.case.rstrip("/")).name if "use_cases" in Path(a.case).parts else a.case.strip("/")
        if not (REPO / "use_cases" / a.case).is_dir():
            print(f"ERROR: --case {a.case}: there is no use_cases/{a.case}/ in this tree", file=sys.stderr)
            return 2

    kp = _load("_kb_profile", "tools/kb_profile.py")
    reg = kp.registry()
    if a.profile:
        if a.profile not in reg:
            print(f"ERROR: {a.profile} is not a registered profile", file=sys.stderr)
            return 2
        profile = a.profile
    else:
        try:
            profile = kp.resolve_or_default(a.model).profile
        except kp.NoMatch as exc:
            print(f"ERROR: {exc}\nPass --profile to query a specific registered profile.", file=sys.stderr)
            return 2
    ms = reg[profile]
    gpath = REPO / "rag" / "graphs" / f"{profile}.json"
    if not gpath.is_file():
        print(f"ERROR: {gpath.relative_to(REPO)} absent: the profile has no graph", file=sys.stderr)
        return 2
    g = Graph(gpath)

    kinds = {"params": a.params, "mechanisms": a.mechanisms, "outputs": a.outputs}
    gkind = {"params": "parameter", "mechanisms": "mechanism", "outputs": "output"}
    entities, gaps, any_node = {}, [], False
    for k, names in kinds.items():
        for n in names:
            nodes = g.find(gkind[k], n)
            any_node |= bool(nodes)
            edges, cats = [], []
            for nid in nodes:
                edges += [{"src": s, "rel": rel, "dst": t, "attrs": at} for s, rel, t, at in g.edges_around(nid)]
                cats += g.category_of(nid)
            entities[n] = {"kind": gkind[k], "nodes": nodes, "categories": sorted(set(cats)), "edges": edges}
            if not nodes:
                gaps.append(f"`{n}` is not a {gkind[k]} node of the {profile} graph")
            elif k == "params" and not any(e["rel"] == "controls" for e in edges):
                gaps.append(f"`{n}` controls no mechanism in the graph (inert, or a missing seed relation)")
            elif k == "outputs" and not g.inn.get(nodes[0]):
                gaps.append(f"`{n}` has no incoming edge: nothing in the graph reaches it")
    reach = []
    for p in a.params:
        for o in a.outputs:
            paths = []
            for ps in g.find("parameter", p):
                for os_ in g.find("output", o):
                    paths += g.paths(ps, os_, a.hops)
            reach.append({"param": p, "output": o, "paths": paths[:5]})
            if not paths and g.find("parameter", p) and g.find("output", o):
                gaps.append(f"`{p}` does not reach `{o}` within {a.hops} edges")

    names = a.params + a.mechanisms + a.outputs
    seed_rel = ms.get("curated_yaml_path")
    seed = seed_entries(REPO / seed_rel, kinds) if seed_rel and (REPO / seed_rel).is_file() else {}
    t1 = doc_hits(names, ms, a.per_name)
    gaps += [f"`{n}` appears in none of the profile's documents" for n, h in t1.items() if not h["count"]]
    mks = _load("_model_knowledge_store", "tools/model_knowledge_store.py")
    t3 = {"model": memory_hits(mks.model_store_dir(a.model, REPO), names, a.per_name)}
    if a.case:
        t3["case"] = memory_hits(REPO / "use_cases" / a.case / "memory" / "gained_knowledge", names, a.per_name)

    pointers = []
    for e in seed.values():
        for v in e.values():
            pointers += _SRC_CITE.findall(v) if isinstance(v, str) else []
    for h in t1.values():
        for x in h["lines"]:
            pointers += _SRC_CITE.findall(x["text"])
    pointers = list(dict.fromkeys(pointers))[:30]

    r = {"kb_network": SCHEMA, "generated_by": "python tools/kb_network.py " + " ".join(sys.argv[1:]),
         "profile": profile, "model": a.model, "kb_commit": kp.kb_commit(ms) or "", "base_commit": kp.base_commit(ms) or "",
         "patches": len(ms.get("patches") or []),
         "queried_at": _dt.datetime.now(_dt.timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
         "query": {**kinds, "case": a.case, "hops": a.hops},
         "tier1": t1,
         "tier2": {"graph": str(gpath.relative_to(REPO)), "entities": entities, "reach": reach, "seed": seed,
                   "vectors": vector_hits(profile, ms, " ".join(names), a.rag_k)},
         "tier3": t3, "gaps": gaps, "source_pointers": pointers}
    out = Path(a.out_dir)
    out.mkdir(parents=True, exist_ok=True)
    (out / "kb_network.json").write_text(json.dumps(r, indent=1, default=str) + "\n")
    write_markdown(r, out / "kb_network.md")
    n_edges = sum(len(e["edges"]) for e in entities.values())
    n_mem = sum(d["matches"] for m in t3.values() for d in m["files"].values())
    print(f"{profile}: {n_edges} graph edge(s), {sum(h['count'] for h in t1.values())} document line(s), "
          f"{n_mem} memory entr(ies), {len(gaps)} gap(s) -> {out}/kb_network.md")
    return 0 if any_node else 1


if __name__ == "__main__":
    sys.exit(main())
