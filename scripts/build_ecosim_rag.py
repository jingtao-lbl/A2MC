#!/usr/bin/env python
"""Build the EcoSIM RAG/GraphRAG index (profile ecosim-2dea74d9).

Adapter-kit dogfood, concrete-first (Doc 19 / onboard-model step 9). This is a
DEDICATED EcoSIM build path that reuses the generic RAG building blocks
(`rag.loader`, `rag.vector_store.FATESVectorStore`, `rag.knowledge_graph`) fed
with EcoSIM content via the `models/ecosim` adapter + curated seed. It does NOT
touch the FATES `scripts/build_rag_index.py` (which is ELMFATESVersion-shaped),
so the canonical FATES indices are byte-for-byte unaffected.

The D-pass unifies this into `build_rag_index.py` via `ModelSpec` dispatch
(replacing the `if adapter == 'ecosim'` split with `spec.*`).

Inputs (from rag/milestones.json[ecosim-2dea74d9] + models/ecosim adapter):
  - wiki:      docs/ecosim-knowledge-base/ecosim-codebase-wiki-2dea74d9/  (41 md)
  - params:    Offline/EcoSIM_sample_files/input/ds_input__pft_test__ex1.nc
  - outputs:   docs/ecosim-knowledge-base/ecosim_output_info_2dea74d9.cdl (516)
  - curated:   models/ecosim/curated_seed.yaml (v0.1 ai-draft)

Outputs:
  - rag/chroma_db/ecosim-2dea74d9/   (vector store)
  - rag/graphs/ecosim-2dea74d9.json  (knowledge graph)
  - rag/metadata/ecosim-2dea74d9.json
  - writes expected_counts back into rag/milestones.json (arms the T6 guard)

Usage (Perlmutter): ~/a2mc_env/bin/python scripts/build_ecosim_rag.py --rebuild

Author: Jing Tao with Claude
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

import yaml

from rag.loader import load_markdown_files, chunk_documents
from rag.vector_store import FATESVectorStore
from rag.knowledge_graph import FATESKnowledgeGraph
from models.ecosim.parameter_parser import EcoSIMParameterParser
from models.ecosim.output_parser import EcoSIMOutputParser

PROFILE = "ecosim-2dea74d9"
COLLECTION = "ecosim_knowledge"


def _rel(p) -> Path:
    p = Path(p)
    return p if p.is_absolute() else REPO / p


def load_milestone() -> dict:
    m = json.loads((REPO / "rag/milestones.json").read_text())
    return m["milestones"][PROFILE]


def parse_param_surfaces(param_files: list[Path]) -> dict:
    """Parse EVERY declared parameter surface and merge, first file wins on a name clash.

    EcoSIM has THREE parameter surfaces (primary plant traits, secondary planting
    management, tertiary microbial) and this builder used to read only the first.
    Everything the curated seed said about the other two was then dropped by the
    `if pid(pname) not in kg.graph: continue` guards below -- silently, because a
    missing Parameter node is skipped while a missing Output node is created by
    ensure_output(). Measured 2026-09-01 on ecosim-2dea74d9: 12 of the seed's 44
    parameters never became nodes (CKC GO2X HSORP RCCY RCCZ RMOM SPOMC SPORC SPOSC
    TSORP VMXF VMXO) and all seven microbial mechanism nodes carried ZERO parameter
    edges, so the reasoning layer had no parameter-level content for Fs at all.
    """
    pp = EcoSIMParameterParser()
    merged: dict = {}
    for pf in param_files:
        if not pf.exists():
            print(f"  WARNING: parameter surface not found, skipping: {pf}")
            continue
        got = pp.parse(pf)
        new = [n for n in got if n not in merged]
        for n in new:
            merged[n] = got[n]
        print(f"  surface {pf.name}: {len(got)} parsed, {len(new)} new")
    return merged


def warn_unresolved_seed_params(seed: dict, params: dict) -> list[str]:
    """Name every curated parameter that no surface supplies. Never silent."""
    missing = [n for n in (seed.get("parameters") or {}) if n not in params]
    if missing:
        print(f"  WARNING: {len(missing)} curated parameter(s) match no parsed surface "
              f"and will have NO graph node or edges: {', '.join(sorted(missing))}")
    return missing


# ---------------------------------------------------------------------------
# Definition chunks (params + outputs) — EcoSIM parser feeds the vector store.
# ---------------------------------------------------------------------------
def build_definition_chunks(params: dict, output_cdl: Path, seed: dict) -> list[dict]:
    chunks: list[dict] = []
    seed_params = seed.get("parameters", {})
    for name, par in params.items():
        if par.is_string:
            continue
        cal = seed_params.get(name, {}).get("calibration_notes", "")
        dims = ", ".join(par.dimensions) if par.dimensions else "scalar"
        content = (
            f"EcoSIM parameter {name} ({par.category}). "
            f"{par.long_name or 'no long_name'}. "
            f"Units: {par.units}. Dimensions: {dims}. "
            f"PFT-specific: {par.is_pft_specific}. "
            + (f"Calibration: {cal.strip()}" if cal else "")
        )
        chunks.append({
            "content": content,
            "source": f"param:{name}",
            "type": "parameter-definition",
            "title": name,
            "format": "definition",
            "entity_type": "parameter",
            "param_category": par.category,
            "is_pft_specific": bool(par.is_pft_specific),
            "chunk_id": f"ecosim/param/{name}",
        })

    op = EcoSIMOutputParser()
    outs = op.parse(output_cdl)
    seed_outs = seed.get("outputs", {})
    for name, ov in outs.items():
        diag = seed_outs.get(name, {}).get("diagnostic_value", "")
        dims = ", ".join(ov.dimensions) if ov.dimensions else "scalar"
        content = (
            f"EcoSIM output variable {name} ({ov.category}, {ov.dimension_level}). "
            f"{ov.long_name or 'no long_name'}. Units: {ov.units}. Dimensions: {dims}. "
            + (f"Diagnostic: {diag.strip()}" if diag else "")
        )
        chunks.append({
            "content": content,
            "source": f"output:{name}",
            "type": "output-definition",
            "title": name,
            "format": "definition",
            "entity_type": "output",
            "output_category": ov.category,
            "dimension_level": ov.dimension_level,
            "chunk_id": f"ecosim/output/{name}",
        })
    return chunks


# ---------------------------------------------------------------------------
# Curated-seed chunks — mechanisms + categories become retrievable calibration
# guidance (the highest-value semantic content).
# ---------------------------------------------------------------------------
def build_curated_chunks(seed: dict) -> list[dict]:
    chunks: list[dict] = []
    for mname, m in seed.get("mechanisms", {}).items():
        content = (
            f"Mechanism {mname}: {m.get('description','')} "
            f"Code: {m.get('code_reference','')}. "
            f"Parameters: {', '.join(m.get('parameters',[]) or [])}. "
            f"Affects: {', '.join(m.get('affects',[]) or [])}. "
            f"{(m.get('notes') or '').strip()}"
        )
        chunks.append({
            "content": content, "source": f"curated:mechanism:{mname}",
            "type": "curated-mechanism", "title": mname, "format": "curated",
            "entity_type": "mechanism", "chunk_id": f"ecosim/mechanism/{mname}",
        })
    for cname, c in seed.get("categories", {}).items():
        content = (
            f"Category {cname} ({c.get('full_name','')}): {c.get('description','')} "
            f"Mechanisms: {', '.join(c.get('mechanisms',[]) or [])}. "
            f"Key outputs: {', '.join(c.get('key_outputs',[]) or [])}."
        )
        chunks.append({
            "content": content, "source": f"curated:category:{cname}",
            "type": "curated-category", "title": cname, "format": "curated",
            "entity_type": "category", "chunk_id": f"ecosim/category/{cname}",
        })
    return chunks


# ---------------------------------------------------------------------------
# Knowledge graph — full param/output surface + curated relationships.
# ---------------------------------------------------------------------------
def _source_status() -> tuple:
    """Classify every parameter-file variable against the source: (file_read, mentioned).

    THREE STATES, AND CONFLATING THE LAST TWO DELETES LIVE PHYSICS. The first cut of this helper
    returned only the `ncd_getvar` set and dropped everything else, which flagged `CHL4`, `H2KI`
    and `OAKI`. Only `CHL4` is dead:

      file_read   read by a name-literal `ncd_getvar` -> a file value reaches the model. Normal.
      mentioned   used in the physics but NOT read from the file -- `H2KI` and `OAKI` are set as
                  compiled constants in `initNitroPars` (NitroPars.F90:144-145) and used in the
                  Gibbs free-energy terms (MicBGCFGMod.F90:2597, MicAutoCplxFGMod.F90:1677). They
                  are LIVE, so they stay in the graph -- but the value in MicrobePars.nc is INERT,
                  and a calibration slot pointing at one would be a silent no-op. Marked
                  `file_backed: false` rather than dropped.
      neither     absent from every .F90 -- genuinely dead. `CHL4` ("bundle sheath(C4)
                  chlorophyll") is ecosys's parameterization; EcoSIM's F90 uses one `CHL`
                  partitioned by `fCHLMESO`. Dropped: a dead knob with the file's own long_name as
                  its description is worse than no node.

    Empty sets when the checkout is unavailable, so the caller degrades to the old behaviour rather
    than silently emptying the graph.
    """
    import os, re, subprocess
    root = os.environ.get("A2MC_MODEL_PATH")
    if not root or not os.path.isdir(root):
        print("  NOTE: $A2MC_MODEL_PATH unset/missing -- cannot classify parameters against source")
        return set(), None
    out = subprocess.run(["git", "grep", "-h", "ncd_getvar"], cwd=root,
                         capture_output=True, text=True).stdout
    file_read = set(re.findall(r"ncd_getvar\([^,]+,\s*'([A-Za-z0-9_]+)'", out))
    names = subprocess.run(["git", "grep", "-hoE", r"\b[A-Z][A-Z0-9_]{2,}\b", "--", "*.F90"],
                           cwd=root, capture_output=True, text=True).stdout
    return file_read, set(names.split())


def build_graph(params: dict, output_cdl: Path, seed: dict) -> FATESKnowledgeGraph:
    kg = FATESKnowledgeGraph()

    # Categories
    for cname, c in seed.get("categories", {}).items():
        kg.add_category(cname, description=c.get("full_name"))

    # Mechanisms (code_reference -> code_location)
    for mname, m in seed.get("mechanisms", {}).items():
        kg.add_mechanism(mname, description=m.get("description"),
                         code_location=m.get("code_reference"))

    # All real params as nodes (category from parser; curated overrides)
    #
    # TWO THINGS THIS LOOP GETS WRONG IF WRITTEN NAIVELY, both found 2026-09-12:
    #
    # (1) A PARAMETER FILE CAN CARRY VARIABLES THE MODEL NO LONGER READS, and promoting one to a
    #     node publishes a dead knob with the FILE's long_name as its description. EcoSIM's shipped
    #     sample `ds_input__pft_test__ex1.nc` carries `CHL4` -- "fraction of leaf protein in bundle
    #     sheath(C4) chlorophyll" -- which appears in ZERO .F90 files. It is ecosys's (the F77
    #     ancestor's) parameterization: ecosys split C3 and C4 chlorophyll across CHL and CHL4,
    #     while EcoSIM's F90 uses ONE CHL partitioned by fCHLMESO. The curated YAML never referenced
    #     it; it entered purely by being parsed. `_read_by_source` filters on the model's own
    #     `ncd_getvar` calls, so a file variable must be read to become knowledge.
    #
    # (2) A PARAMETER CAN HAVE MORE THAN ONE IMPLEMENTATION, selected by a type flag, and until now
    #     the graph had no way to say so: all 192 Parameter nodes carried `code_location: null` and
    #     no node or edge encoded a condition. `CHL` is read in C3Photosynthesis AND
    #     C4Photosynthesis with different formulas; `git grep` returns both and the first hit is a
    #     coin flip. `guard` is emitted verbatim from the curated seed onto the node so a retrieval
    #     surfaces the SELECTOR alongside the parameter.
    seed_params = seed.get("parameters", {})
    file_read, mentioned = _source_status()
    dropped, inert = [], []
    for name, par in params.items():
        if par.is_string:
            continue
        if mentioned is not None and name not in file_read:
            if name not in mentioned:
                dropped.append(name)          # absent from every .F90 -- dead
                continue
            inert.append(name)                # live in code, but the FILE value is never read
        cur = seed_params.get(name, {})
        cat = cur.get("category", par.category)
        kg.add_parameter(name, category=cat, description=par.long_name,
                         units=par.units, code_location=cur.get("code_location"))
        node = kg.graph.nodes[f"{kg.PARAMETER.lower()}:{name}"]
        if cur.get("guard"):
            node["guard"] = cur["guard"]
        if name in inert:
            node["file_backed"] = False
            node["file_backed_note"] = (
                "Used in the physics but NOT read from the parameter file -- the model uses a "
                "compiled-in constant. Writing this variable into the file is a SILENT NO-OP, so "
                "it cannot be calibrated until it is promoted to a file-read parameter.")
    if dropped:
        print(f"  dropped {len(dropped)} parameter-file variable(s) absent from every .F90 "
              f"(dead in this model version): {', '.join(sorted(dropped))}")
    if inert:
        print(f"  {len(inert)} variable(s) present in a parameter file but NOT read from it "
              f"(compiled-in constant; writing them is a silent no-op): {', '.join(sorted(inert))}")
    n_guard = sum(1 for v in seed_params.values() if v.get("guard"))
    if n_guard:
        print(f"  {n_guard} parameter(s) carry a branch GUARD "
              f"(more than one implementation, selected by a type flag)")

    # All real outputs as nodes
    op = EcoSIMOutputParser()
    outs = op.parse(output_cdl)
    for name, ov in outs.items():
        kg.add_output(name, description=ov.long_name, units=ov.units,
                      level=ov.dimension_level)

    P, M, O, C = kg.PARAMETER, kg.MECHANISM, kg.OUTPUT, kg.CATEGORY

    def pid(n): return f"{P.lower()}:{n}"
    def mid(n): return f"{M.lower()}:{n}"
    def oid(n): return f"{O.lower()}:{n}"
    def cid(n): return f"{C.lower()}:{n}"

    def ensure_output(n):
        if oid(n) not in kg.graph:
            kg.add_output(n)

    # category -> contains -> mechanism ; mechanism -> affects -> output
    for cname, c in seed.get("categories", {}).items():
        for mname in c.get("mechanisms", []) or []:
            if mid(mname) in kg.graph:
                kg.add_relationship(cid(cname), mid(mname), kg.CONTAINS)
        # `key_outputs` is the category's answer to "which scored things does this area of the
        # model move", and it was read for chunk text and for no edge until 2026-09-08, costing 22
        # category -> output edges. Same defect as the outputs block one loop below, one seed block
        # over, and the PFLOTRAN builder wires this field too. An output named here may be one the
        # parsed CDL does not carry, so `ensure_output` rather than a skip: unlike a parameter, an
        # output name in the seed is a claim about the history tape that the curator is entitled to
        # make ahead of the registry, and the three phantom outputs removed in 2026-09-06 were
        # caught by `tools/validate_curated_yaml.py` dimension B, which checks exactly that.
        for oname in c.get("key_outputs", []) or []:
            ensure_output(oname)
            kg.add_relationship(cid(cname), oid(oname), kg.AFFECTS)
    for mname, m in seed.get("mechanisms", {}).items():
        for pname in m.get("parameters", []) or []:
            if pid(pname) in kg.graph:
                kg.add_relationship(pid(pname), mid(mname), kg.CONTROLS)
        for oname in m.get("affects", []) or []:
            ensure_output(oname)
            kg.add_relationship(mid(mname), oid(oname), kg.AFFECTS)

    # param -> controls -> mechanism ; param -> affects -> output ; related_to
    for pname, p in seed_params.items():
        if pid(pname) not in kg.graph:
            continue
        for mname in p.get("controls", []) or []:
            if mid(mname) in kg.graph:
                kg.add_relationship(pid(pname), mid(mname), kg.CONTROLS)
        for oname in p.get("affects", []) or []:
            ensure_output(oname)
            kg.add_relationship(pid(pname), oid(oname), kg.AFFECTS)
        for rel in p.get("related_to", []) or []:
            if pid(rel) in kg.graph:
                kg.add_relationship(pid(pname), pid(rel), kg.DEPENDS_ON)

    # outputs -> {direct,indirect}_drivers -> parameters. The seed carries this direction too and
    # it is NOT symmetric with `parameters.*.affects`: an output entry names what drives IT, which
    # is the question a diagnosis asks, while a parameter entry names what it reaches. Walking only
    # the parameter side dropped 73 curated edges here, among them RSMX -> ECO_ET_col, which is why
    # the round's binding target could be reached only two hops through a mechanism. The PFLOTRAN
    # builder has had this pass since it was written; EcoSIM's never did.
    #
    # `driver_kind` records the curator's direct/indirect distinction as an edge attribute rather
    # than as a weight: nothing in the retriever reads `weight` today, so encoding it there would
    # look like a ranking signal while being inert.
    #
    # An unknown driver name is SKIPPED, never minted. Minting is how three phantom outputs entered
    # this graph in the first place (fixed 2026-09-06), and `warn_unresolved_seed_params` already
    # reports the names so a typo stays visible instead of becoming a node.
    for oname, o in (seed.get("outputs") or {}).items():
        ensure_output(oname)
        for kind, field in (("direct", "direct_drivers"), ("indirect", "indirect_drivers")):
            for pname in (o.get(field) or []):
                if pid(pname) not in kg.graph:
                    continue
                if kg.graph.has_edge(pid(pname), oid(oname)):
                    continue          # the parameter side already asserted it; do not downgrade
                kg.add_relationship(pid(pname), oid(oname), kg.AFFECTS, driver_kind=kind)
    return kg


def main():
    ap = argparse.ArgumentParser(description="Build the EcoSIM RAG index (ecosim-2dea74d9).")
    ap.add_argument("--rebuild", action="store_true", help="Rebuild vector store from scratch")
    ap.add_argument("--graph-only", action="store_true", help="Only rebuild the graph")
    ap.add_argument("--no-write-counts", action="store_true",
                    help="Do not write expected_counts back to milestones.json")
    ap.add_argument("--allow-shrink", action="store_true",
                    help="Bypass the count-regression guard (a deliberate smaller build)")
    args = ap.parse_args()

    ms = load_milestone()
    kb_dir = _rel(ms["knowledge_base_dir"])
    wiki_dir = kb_dir / ms["model_wiki_subdir"]
    output_cdl = kb_dir / ms["output_cdl"]
    param_files = [_rel(ms["param_file"])] + [
        _rel(x) for x in (ms.get("param_files_extra") or [])
    ]
    curated = _rel(ms["curated_yaml_path"])
    seed = yaml.safe_load(curated.read_text())

    persist_dir = REPO / "rag/chroma_db" / PROFILE
    graph_out = REPO / "rag/graphs" / f"{PROFILE}.json"
    meta_out = REPO / "rag/metadata" / f"{PROFILE}.json"
    graph_out.parent.mkdir(parents=True, exist_ok=True)
    meta_out.parent.mkdir(parents=True, exist_ok=True)

    os.environ["A2MC_RAG_DIR"] = str(REPO / "rag")
    os.environ["A2MC_RAG_ACTIVE"] = PROFILE

    print("=" * 64)
    print(f"  Building EcoSIM RAG profile: {PROFILE}")
    print(f"  wiki:    {wiki_dir}")
    for _pf in param_files:
        print(f"  params:  {_pf}")
    print(f"  outputs: {output_cdl}")
    print(f"  curated: {curated}")
    print("=" * 64)

    params = parse_param_surfaces(param_files)
    warn_unresolved_seed_params(seed, params)

    chunk_count = 0
    if not args.graph_only:
        # Vector store
        wiki_docs = load_markdown_files(str(wiki_dir))
        for d in wiki_docs:
            d["kb_source"] = "ecosim"
        wiki_chunks = chunk_documents(wiki_docs)
        def_chunks = build_definition_chunks(params, output_cdl, seed)
        cur_chunks = build_curated_chunks(seed)
        all_chunks = wiki_chunks + def_chunks + cur_chunks
        print(f"\nchunks: wiki={len(wiki_chunks)} definitions={len(def_chunks)} "
              f"curated={len(cur_chunks)} total={len(all_chunks)}")

        if args.rebuild and persist_dir.exists():
            import shutil
            shutil.rmtree(persist_dir)
        vs = FATESVectorStore(persist_dir=str(persist_dir), collection_name=COLLECTION)
        vs.add_documents(all_chunks)
        chunk_count = vs.collection.count()
        print(f"vector store documents: {chunk_count}")

    # Graph
    print("\nBuilding knowledge graph...")
    kg = build_graph(params, output_cdl, seed)
    kg.save(str(graph_out))
    stats = kg.get_stats()
    print(f"graph: {stats.get('total_nodes')} nodes, {stats.get('total_edges')} edges -> {graph_out}")

    if args.graph_only and meta_out.exists():
        chunk_count = json.loads(meta_out.read_text()).get("stats", {}).get("chunk_count", 0)

    # Metadata
    from datetime import datetime, timezone
    meta = {
        "metadata_schema_version": 1,
        "profile_name": PROFILE,
        "adapter": "ecosim",
        "built_at": datetime.now(timezone.utc).isoformat(),
        "model_commit_built": ms["model_commit_built"],
        "wiki_subdir": ms["model_wiki_subdir"],
        "param_file": ms["param_file"],
        "param_files_extra": ms.get("param_files_extra") or [],
        "output_cdl": ms["output_cdl"],
        "curated_yaml": ms["curated_yaml_path"],
        "curated_yaml_status": "v0.1-ai-draft-pending-PI-review",
        "stats": {
            "chunk_count": chunk_count,
            "graph_nodes": stats.get("total_nodes", 0),
            "graph_edges": stats.get("total_edges", 0),
        },
    }
    meta_out.write_text(json.dumps(meta, indent=2))
    print(f"metadata -> {meta_out}")

    # Count-regression guard: a >2% DROP in docs/nodes/edges vs the registered
    # expected_counts fails the build (the silent-index-shrink class, dev_log 20260710s).
    # Growth is allowed. Bypass a deliberate smaller build with --allow-shrink.
    new_counts = {
        "documents": chunk_count,
        "nodes": stats.get("total_nodes", 0),
        "edges": stats.get("total_edges", 0),
    }
    # WHICH counts this run actually rebuilt. A --graph-only run does not re-embed, so its
    # `documents` is read back out of the previous metadata (above) and comparing it against
    # expected_counts is a tautology that always passes. Its nodes and edges ARE freshly built,
    # and they are precisely what a curated-YAML edit changes -- including by silently dropping
    # an edge whose endpoint is not in the CDL, which is the documented footgun of that mode.
    # Gating the whole guard on `not args.graph_only` therefore disarmed it exactly where it was
    # most needed. Same principle as the FATES builder, which checks only the half it rebuilt.
    built_keys = ("documents", "nodes", "edges") if not args.graph_only else ("nodes", "edges")

    prev = (ms.get("expected_counts") or {})
    if any(v is not None for v in prev.values()):
        regressions = [
            f"    {k}: built {new_counts[k]} < expected {prev[k]} "
            f"({100.0*(prev[k]-new_counts[k])/prev[k]:.1f}% drop)"
            for k in built_keys
            if prev.get(k) and new_counts[k] < prev[k] * 0.98
        ]
        if regressions and not args.allow_shrink:
            print("ERROR: EcoSIM RAG index shrank vs expected_counts (rag/milestones.json).\n"
                  "This is the silent-degradation class. Mismatches:\n"
                  + "\n".join(regressions)
                  + "\n  Fix the inputs, or pass --allow-shrink if the smaller build is intended.",
                  file=sys.stderr)
            sys.exit(3)

    # Arm the count-regression guard: write expected_counts into milestones.json.
    # A --graph-only run updates ONLY the keys it rebuilt, leaving `documents` at whatever the
    # last full build recorded, so the expectation tracks the artifact instead of drifting from
    # it silently on every curated-YAML edit.
    if not args.no_write_counts:
        mpath = REPO / "rag/milestones.json"
        mjson = json.loads(mpath.read_text())
        counts = dict(mjson["milestones"][PROFILE].get("expected_counts") or {})
        counts.update({k: new_counts[k] for k in built_keys})
        mjson["milestones"][PROFILE]["expected_counts"] = counts
        mpath.write_text(json.dumps(mjson, indent=2) + "\n")
        print("expected_counts written to milestones.json: "
              + " ".join(f"{k}={counts[k]}" for k in ("documents", "nodes", "edges") if k in counts)
              + ("  (graph-only: documents left at the last full build)" if args.graph_only else ""))

    print("\nBUILD COMPLETE")


if __name__ == "__main__":
    main()
