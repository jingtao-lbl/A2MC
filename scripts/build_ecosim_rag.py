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


# ---------------------------------------------------------------------------
# Definition chunks (params + outputs) — EcoSIM parser feeds the vector store.
# ---------------------------------------------------------------------------
def build_definition_chunks(param_file: Path, output_cdl: Path, seed: dict) -> list[dict]:
    chunks: list[dict] = []
    pp = EcoSIMParameterParser()
    params = pp.parse(param_file)
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
def build_graph(param_file: Path, output_cdl: Path, seed: dict) -> FATESKnowledgeGraph:
    kg = FATESKnowledgeGraph()

    # Categories
    for cname, c in seed.get("categories", {}).items():
        kg.add_category(cname, description=c.get("full_name"))

    # Mechanisms (code_reference -> code_location)
    for mname, m in seed.get("mechanisms", {}).items():
        kg.add_mechanism(mname, description=m.get("description"),
                         code_location=m.get("code_reference"))

    # All real params as nodes (category from parser; curated overrides)
    pp = EcoSIMParameterParser()
    params = pp.parse(param_file)
    seed_params = seed.get("parameters", {})
    for name, par in params.items():
        if par.is_string:
            continue
        cat = seed_params.get(name, {}).get("category", par.category)
        kg.add_parameter(name, category=cat, description=par.long_name,
                         units=par.units)

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
    param_file = _rel(ms["param_file"])
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
    print(f"  params:  {param_file}")
    print(f"  outputs: {output_cdl}")
    print(f"  curated: {curated}")
    print("=" * 64)

    chunk_count = 0
    if not args.graph_only:
        # Vector store
        wiki_docs = load_markdown_files(str(wiki_dir))
        for d in wiki_docs:
            d["kb_source"] = "ecosim"
        wiki_chunks = chunk_documents(wiki_docs)
        def_chunks = build_definition_chunks(param_file, output_cdl, seed)
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
    kg = build_graph(param_file, output_cdl, seed)
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
    prev = (ms.get("expected_counts") or {})
    if not args.graph_only and any(v is not None for v in prev.values()):
        regressions = [
            f"    {k}: built {new_counts[k]} < expected {prev[k]} "
            f"({100.0*(prev[k]-new_counts[k])/prev[k]:.1f}% drop)"
            for k in ("documents", "nodes", "edges")
            if prev.get(k) and new_counts[k] < prev[k] * 0.98
        ]
        if regressions and not args.allow_shrink:
            print("ERROR: EcoSIM RAG index shrank vs expected_counts (rag/milestones.json).\n"
                  "This is the silent-degradation class. Mismatches:\n"
                  + "\n".join(regressions)
                  + "\n  Fix the inputs, or pass --allow-shrink if the smaller build is intended.",
                  file=sys.stderr)
            sys.exit(3)

    # Arm the count-regression guard: write expected_counts into milestones.json
    if not args.no_write_counts and not args.graph_only:
        mpath = REPO / "rag/milestones.json"
        mjson = json.loads(mpath.read_text())
        mjson["milestones"][PROFILE]["expected_counts"] = new_counts
        mpath.write_text(json.dumps(mjson, indent=2) + "\n")
        print(f"expected_counts written to milestones.json: "
              f"docs={chunk_count} nodes={stats.get('total_nodes')} edges={stats.get('total_edges')}")

    print("\nBUILD COMPLETE")


if __name__ == "__main__":
    main()
