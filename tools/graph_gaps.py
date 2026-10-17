#!/usr/bin/env python
"""Check and promote KNOWLEDGE-GRAPH GAP CANDIDATES: nodes and edges the model's graph lacks.

visibility: public
Author: Jing Tao with Claude on Perlmutter

A calibration cycle reasons from the model's knowledge graph (`tools/kb_network.py`) and confirms
each route in model source. Where the source shows a link the graph does not hold, the link is a
GAP. `write-report` requires each cycle report to draw the tested parameters' FULL mechanism
network (`tools/plot_kb_network.py`), stored edges and gaps distinguished, and to stage every gap in
the report's own folder:

    use_cases/<Model>_<Case>/reports/<cycle report>/graph_gap_candidates.yaml   staged by the agent
            |  a human reviews each entry at the end of the cycle (review: accepted | rejected)
            v
    models/<model>/graph_gap_candidates.yaml        accepted gaps, awaiting the build side
            |  wire-knowledge-graph / inject-knowledge add them to the curated seed and rebuild
            v
    the knowledge graph

A candidate is justified by SOURCE, never by a measurement: the model graph represents source-code
relationships and a measured response is a property of one run (`phase6-refinement` Step 3). So every entry carries a `file:line`, and the measurement that prompted the source read
goes in `prompted_by`, as the reason it was looked for rather than the reason it is true.
Design and reasons: `memory/dev_logs_adapterkit/20261017d_A_Cycle_Report_Draws_The_Tested_Mechanism_Network_And_Stages_Its_Gaps.md`.

THE FILE (both locations share the schema):

    schema: 1
    model: ecosim
    profile: ecosim-cb243228          # the registered profile whose graph lacks the link
    source_commit: 0340d71b           # the model commit the citations were read at
    new_nodes:                        # endpoints the graph does not have, with what they are
      mechanism:Phosphorus_Growth_Limit: "RFP1, the P limit on growth ..."
    candidates:
      - id: G1
        from: parameter:CPLF
        relation: controls            # the four shapes the graph holds, below
        to: mechanism:Phosphorus_Growth_Limit
        source: f90src/Plant_bgc/PlantBranchMod.F90:3241     # or a list: the chain, one line per step
        claim: "CPLF sets the P cost per gram of new leaf in RFP1's denominator"
        prompted_by: "EcoSIM_Lusignan R2 c01 E2: CPLF 0.020 cut GPP 30% at base 3678 (stem 20261017j)"
        found: 2026-10-17
        review: pending               # pending | accepted | rejected, set by the HUMAN reviewer
        review_note: ""

ONLY THE FOUR EDGE SHAPES THE GRAPH HOLDS: parameter -controls-> mechanism, mechanism -affects->
output, parameter -affects-> output (an indirect driver), parameter -depends_on-> parameter. The graph
has no mechanism-to-mechanism edge, so a route that runs through two mechanisms (leaf mass, then light
interception, then GPP) is entered in the nearest shape the builder can hold, with the whole chain in
`source` as a list of citations, one per step, and named in `claim`.

WHAT MAKES `check` FAIL (exit 1), named first (`feedback_a_check_that_cannot_fail`):
  * a missing or malformed field; a node id whose type is not parameter/mechanism/output/category;
    an edge shape outside the four above; a duplicate id; a review state outside the three;
  * a `source` citation that is not `path/File.ext:N` or `:N-M`: an edge with no source line is a
    claim no one can check, and the measurement alone never justifies it;
  * an endpoint absent from BOTH the profile's graph and `new_nodes`;
  * an edge the graph ALREADY holds (either direction, any of the three relations): not a gap.
`promote` refuses a file that fails `check`, moves only `review: accepted` entries, skips one whose
(from, relation, to) is already in the model file, and stamps `promoted_from` and `promoted_at`.

Usage:
    python tools/graph_gaps.py check use_cases/<Case>/reports/<cycle report>/graph_gap_candidates.yaml
    python tools/graph_gaps.py check models/ecosim/graph_gap_candidates.yaml
    python tools/graph_gaps.py promote use_cases/<Case>/reports/<cycle report>/graph_gap_candidates.yaml [--dry-run]
"""
from __future__ import annotations

import argparse
import datetime as _dt
import importlib.util
import re
import sys
from pathlib import Path

import yaml

REPO = Path(__file__).resolve().parents[1]
SCHEMA = 1
TYPES = ("parameter", "mechanism", "output", "category")
RELATIONS = ("controls", "affects", "depends_on")
SHAPES = {("parameter", "controls", "mechanism"), ("mechanism", "affects", "output"),
          ("parameter", "affects", "output"), ("parameter", "depends_on", "parameter")}
REVIEWS = ("pending", "accepted", "rejected")
SOURCE = re.compile(r"^[\w./-]+\.(?:F90|f90|F|f|c|cc|cpp|h|hh|hpp|py|in|xml):\d+(?:-\d+)?$")
NODE = re.compile(r"^(%s):[\w.+-]+$" % "|".join(TYPES))
REQUIRED = ("id", "from", "relation", "to", "source", "claim", "prompted_by", "found", "review")


def _load_graph(profile: str):
    spec = importlib.util.spec_from_file_location("_kb_network", REPO / "tools" / "kb_network.py")
    mod = importlib.util.module_from_spec(spec)
    sys.modules["_kb_network"] = mod
    spec.loader.exec_module(mod)
    path = REPO / "rag" / "graphs" / f"{profile}.json"
    if not path.is_file():
        raise FileNotFoundError(f"rag/graphs/{profile}.json absent: profile {profile!r} has no graph")
    return mod.Graph(path)


def has_edge(g, a: str, b: str) -> bool:
    """True if the graph joins a and b along any flow or coupling relation, either direction."""
    return any(t == b and at["relation_type"] in RELATIONS for t, at in g.out.get(a, [])) or \
        any(t == a and at["relation_type"] in RELATIONS for t, at in g.out.get(b, []))


def check(path: Path, g=None) -> tuple[list[str], dict]:
    """-> (errors, parsed document). `g` is the profile's graph, loaded when not given."""
    errs: list[str] = []
    try:
        doc = yaml.safe_load(path.read_text()) or {}
    except (OSError, yaml.YAMLError) as exc:
        return [f"cannot read: {exc}"], {}
    for k in ("schema", "model", "profile", "source_commit", "candidates"):
        if k not in doc:
            errs.append(f"top-level `{k}` missing")
    if errs:
        return errs, doc
    if doc["schema"] != SCHEMA:
        errs.append(f"schema {doc['schema']!r}, expected {SCHEMA}")
    if not isinstance(doc["candidates"], list):
        return errs + ["`candidates` must be a list (an empty list says no gap was found)"], doc
    new_nodes = doc.get("new_nodes") or {}
    for nid in new_nodes:
        if not NODE.match(str(nid)):
            errs.append(f"new_nodes: `{nid}` is not <{'|'.join(TYPES)}>:<name>")
    if g is None:
        try:
            g = _load_graph(doc["profile"])
        except FileNotFoundError as exc:
            return errs + [str(exc)], doc
    seen = set()
    for i, c in enumerate(doc["candidates"]):
        where = f"candidate {c.get('id', f'#{i + 1}')}"
        miss = [k for k in REQUIRED if c.get(k) in (None, "")]
        if miss:
            errs.append(f"{where}: missing {', '.join(miss)}")
            continue
        if c["id"] in seen:
            errs.append(f"{where}: duplicate id")
        seen.add(c["id"])
        for end in ("from", "to"):
            nid = str(c[end])
            if not NODE.match(nid):
                errs.append(f"{where}: {end} `{nid}` is not <{'|'.join(TYPES)}>:<name>")
            elif nid not in g.nodes and nid not in new_nodes:
                errs.append(f"{where}: {end} `{nid}` is neither a node of {doc['profile']} nor in new_nodes")
        shape = (str(c["from"]).split(":", 1)[0], c["relation"], str(c["to"]).split(":", 1)[0])
        if shape not in SHAPES:
            errs.append(f"{where}: shape {shape[0]} -{shape[1]}-> {shape[2]} is not one the graph holds "
                        f"({', '.join(f'{a}-{r}->{b}' for a, r, b in sorted(SHAPES))})")
        cites = c["source"] if isinstance(c["source"], list) else [c["source"]]
        bad = [x for x in cites if not SOURCE.match(str(x))]
        if bad or not cites:
            errs.append(f"{where}: source {bad or cites} is not path/File.ext:N[-M]; an edge needs a source line")
        if c["review"] not in REVIEWS:
            errs.append(f"{where}: review `{c['review']}` not in {REVIEWS}")
        if str(c["from"]) in g.nodes and str(c["to"]) in g.nodes and has_edge(g, str(c["from"]), str(c["to"])):
            errs.append(f"{where}: {c['from']} and {c['to']} are already joined in {doc['profile']}: not a gap")
    return errs, doc


def promote(src: Path, dry_run: bool = False, g=None, models_root: Path | None = None) -> int:
    errs, doc = check(src, g)
    if errs:
        print(f"REFUSED: {src} fails check:\n  " + "\n  ".join(errs), file=sys.stderr)
        return 1
    dst = (models_root or REPO / "models") / doc["model"] / "graph_gap_candidates.yaml"
    if dst.is_file():
        model_doc = yaml.safe_load(dst.read_text()) or {}
        if model_doc.get("profile") != doc["profile"]:
            print(f"REFUSED: {dst} is for profile {model_doc.get('profile')!r}, "
                  f"this file for {doc['profile']!r}", file=sys.stderr)
            return 1
    else:
        model_doc = dict(schema=SCHEMA, model=doc["model"], profile=doc["profile"],
                         source_commit=doc["source_commit"], new_nodes={}, candidates=[])
    have = {(c["from"], c["relation"], c["to"]) for c in model_doc["candidates"]}
    used = {str(c[e]) for c in doc["candidates"] for e in ("from", "to")}
    try:
        rel = src.resolve().relative_to(REPO)
    except ValueError:
        rel = src
    moved, pending = [], []
    for c in doc["candidates"]:
        if c["review"] == "pending":
            pending.append(c["id"])
        if c["review"] != "accepted":
            continue
        key = (c["from"], c["relation"], c["to"])
        if key in have:
            print(f"  skip {c['id']}: {key[0]} --{key[1]}--> {key[2]} is already in the model file")
            continue
        entry = dict(c, id=f"{doc['model']}-{len(model_doc['candidates']) + 1:03d}",
                     source_commit=doc["source_commit"], promoted_from=f"{rel}#{c['id']}",
                     promoted_at=_dt.date.today().isoformat())
        model_doc["candidates"].append(entry)
        have.add(key)
        moved.append(c["id"])
    for nid, desc in (doc.get("new_nodes") or {}).items():
        if nid in used:
            model_doc.setdefault("new_nodes", {}).setdefault(nid, desc)
    print(f"{len(moved)} accepted candidate(s) to {dst}: {', '.join(moved) or 'none'}")
    if pending:
        print(f"  NOT promoted, still pending review: {', '.join(pending)}")
    if moved and not dry_run:
        dst.parent.mkdir(parents=True, exist_ok=True)
        dst.write_text(yaml.safe_dump(model_doc, sort_keys=False, allow_unicode=True, width=110))
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("check")
    c.add_argument("files", nargs="+", type=Path)
    p = sub.add_parser("promote")
    p.add_argument("file", type=Path)
    p.add_argument("--dry-run", action="store_true")
    a = ap.parse_args(argv)
    if a.cmd == "promote":
        return promote(a.file, a.dry_run)
    rc = 0
    for f in a.files:
        errs, doc = check(f)
        n = len(doc.get("candidates") or []) if isinstance(doc, dict) else 0
        if errs:
            rc = 1
            print(f"✘ {f}: {len(errs)} error(s)")
            for e in errs:
                print(f"    {e}")
        else:
            print(f"✔ {f}: {n} candidate(s), schema clean")
    return rc


if __name__ == "__main__":
    raise SystemExit(main())
