#!/usr/bin/env python
"""Build the PFLOTRAN RAG index (profile pflotran-157a26f7).

Mirrors `scripts/build_ecosim_rag.py` -- the established per-model build path for
a non-FATES adapter. It reuses the generic building blocks (`rag.loader`,
`rag.vector_store.FATESVectorStore`) and does NOT touch the FATES
`scripts/build_rag_index.py`, which is `ELMFATESVersion`-shaped and hard-requires
an E3SM checkout (`components/elm/`), so the canonical FATES indices are
unaffected.

WHAT THIS BUILDS, AND WHAT IT REFUSES TO
----------------------------------------
PFLOTRAN differs from EcoSIM in the two inputs the GRAPH layer is built from:

  * **No parameter NetCDF.** PFLOTRAN's parameter surface is a free-form text
    card deck, per-case, so there is no model-default file to parse for a
    parameter inventory (addressing scheme: dev logs 20260730d / 20260731e).
  * **No output CDL.** Outputs are a fixed-width mass-balance text file plus
    Tecplot snapshots, not NetCDF (wiki `output_io/`).
  * **No curated seed yet.** `models/pflotran/curated_seed.yaml` does not exist;
    authoring it is `onboard-model` step 7 and is PI-in-the-loop.

The vector layer needs none of those -- it is built from the wiki, which is
validated Green. The graph layer needs all three. So this script builds the
vector layer and **refuses to write a graph** until a curated seed exists.

That refusal is deliberate. Writing an empty graph would produce a
profile that LOOKS built: `rag/graphs/pflotran-157a26f7.json` would exist, the
metadata would record a successful build, and the failure would only surface
much later as a GraphRAG traversal that silently returns nothing. The
`build-rag-from-scratch` skill's Step V calls this exact shape a "silent
half-build". Better to have no graph file than a misleading one.

Usage:
    ~/a2mc_env/bin/python scripts/build_pflotran_rag.py --rebuild

Author: Jing Tao with Claude
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

import yaml  # noqa: E402

from rag.loader import load_markdown_files, chunk_documents          # noqa: E402
from rag.vector_store import FATESVectorStore                        # noqa: E402

PROFILE = "pflotran-157a26f7"
COLLECTION = "pflotran_knowledge"


def _rel(p) -> Path:
    p = Path(p)
    return p if p.is_absolute() else REPO / p


def load_milestone() -> dict:
    ms = json.loads((REPO / "rag/milestones.json").read_text())["milestones"]
    if PROFILE not in ms:
        sys.exit(f"ERROR: milestone {PROFILE} not registered in rag/milestones.json")
    return ms[PROFILE]



# ---------------------------------------------------------------------------
# Curated chunks — the seed's prose, retrievable by the vector layer.
# ---------------------------------------------------------------------------
def build_curated_chunks(seed: dict) -> list:
    """One chunk per curated entity, so a semantic query can hit the CURATED
    statement (with its citations) and not only the wiki page behind it."""
    chunks = []
    for mname, m in (seed.get("mechanisms") or {}).items():
        chunks.append({
            "content": f"Mechanism {mname}: {m.get('description','')} "
                       f"Source: {m.get('source','')}.",
            "source": f"curated:mechanism:{mname}", "type": "curated-mechanism",
            "title": mname, "format": "curated", "entity_type": "mechanism",
            "chunk_id": f"pflotran/mechanism/{mname}",
        })
    for cname, c in (seed.get("categories") or {}).items():
        chunks.append({
            "content": f"Category {cname} ({c.get('full_name','')}): "
                       f"{c.get('description','')} "
                       f"Mechanisms: {', '.join(c.get('mechanisms') or [])}. "
                       f"Key outputs: {', '.join(c.get('key_outputs') or [])}. "
                       f"Calibratable: {c.get('calibratable')}.",
            "source": f"curated:category:{cname}", "type": "curated-category",
            "title": cname, "format": "curated", "entity_type": "category",
            "chunk_id": f"pflotran/category/{cname}",
        })
    for pname, par in (seed.get("parameters") or {}).items():
        chunks.append({
            "content": f"Parameter {pname} (category {par.get('category','')}): "
                       f"{(par.get('calibration_notes') or '').strip()}",
            "source": f"curated:parameter:{pname}", "type": "curated-parameter",
            "title": pname, "format": "curated", "entity_type": "parameter",
            "chunk_id": f"pflotran/parameter/{pname}",
        })
    for oname, o in (seed.get("outputs") or {}).items():
        chunks.append({
            "content": f"Output {oname} (category {o.get('category','')}): "
                       f"{o.get('description','')} {(o.get('notes') or '').strip()} "
                       f"Affected by: {', '.join(o.get('affected_by') or [])}.",
            "source": f"curated:output:{oname}", "type": "curated-output",
            "title": oname, "format": "curated", "entity_type": "output",
            "chunk_id": f"pflotran/output/{oname}",
        })
    return chunks


# ---------------------------------------------------------------------------
# Knowledge graph.
# ---------------------------------------------------------------------------
def _output_inventory(mas: Path, registry: Path = None):
    """``{full_header: PFLOTRANOutputVariable}`` from the live tape, else the
    committed registry, else empty.

    Order matters and is deliberate: the tape a run actually produced is that run's
    truth, while the registry is a pinned SNAPSHOT of one deck's surface
    (`scripts/extract_pflotran_outputs.py` — read its scope warning: the registry is
    DECK-scoped, not model-scoped). Falling back keeps a machine without the 99 MB
    case bundle from silently building a graph with zero output nodes.
    """
    from models.pflotran.output_parser import PFLOTRANOutputParser as _P
    if mas and Path(mas).is_file():
        return _P().parse(mas)
    # `scripts/` is not a package, so load the sibling by path rather than by import.
    import importlib.util
    _spec = importlib.util.spec_from_file_location(
        "_extract_pflotran_outputs", Path(__file__).resolve().parent / "extract_pflotran_outputs.py")
    _mod = importlib.util.module_from_spec(_spec)
    _spec.loader.exec_module(_mod)
    reg = Path(registry) if registry is not None else _mod.default_registry_path()
    load_registry = _mod.load_registry
    if reg.is_file():
        print(f"  outputs: tape absent — using the committed registry {reg.name} "
              f"(DECK-SCOPED snapshot)")
        return load_registry(reg)
    print("  outputs: NEITHER the reference tape NOR the committed registry is present "
          "— the graph will carry only curated outputs")
    return {}


def build_graph(seed: dict, deck: Path, mas: Path) -> "FATESKnowledgeGraph":
    """PFLOTRAN's graph, and it differs from EcoSIM's in ONE structural way.

    EcoSIM keys parameters by a bare Fortran name, so parser keys and seed keys
    are the same string. PFLOTRAN's parser keys by DECK BLOCK PATH
    (`CHEMISTRY/MINERAL_KINETICS/Glass_FB/RATE_CONSTANT`) while the seed keys by
    the CARD/LEAF (`RATE_CONSTANT`) -- deliberately, because the knowledge is
    true of every instance of the card and an address-keyed seed would describe
    one deck rather than the model.

    So the graph node is the LEAF, and the deck addresses that share it are
    recorded on that node as `addresses`. That keeps the graph model-scoped
    (which is what a calibration agent reasons about) without losing the
    per-address information a WRITER needs. It is also why a parameter can be
    reached from the seed at all: an address-keyed node set would match nothing.
    """
    from rag.knowledge_graph import FATESKnowledgeGraph
    from models.pflotran.parameter_parser import PFLOTRANParameterParser
    from models.pflotran.output_parser import PFLOTRANOutputParser

    kg = FATESKnowledgeGraph()

    for cname, c in (seed.get("categories") or {}).items():
        kg.add_category(cname, description=c.get("full_name") or c.get("description"))
    for mname, m in (seed.get("mechanisms") or {}).items():
        kg.add_mechanism(mname, description=m.get("description"),
                         code_location=m.get("source"))

    # --- parameter nodes: leaf-keyed, with their deck addresses attached ---
    addresses = {}
    if deck and deck.is_file():
        for path, knob in PFLOTRANParameterParser().parse(deck).items():
            leaf = path.split("/")[-1].split("[")[0]
            if "#" in leaf:                       # positional col, e.g. 'Glass_FB#vol_frac'
                leaf = leaf.split("#")[-1]
            addresses.setdefault(leaf, []).append(path)

    seed_params = seed.get("parameters") or {}
    for pname, par in seed_params.items():
        kg.add_parameter(pname, category=par.get("category"),
                         description=(par.get("calibration_notes") or "").strip()[:400])
        node = f"parameter:{pname}"
        if node in kg.graph and pname in addresses:
            kg.graph.nodes[node]["addresses"] = addresses[pname]
            kg.graph.nodes[node]["n_addresses"] = len(addresses[pname])

    # --- output nodes: every real column, so the graph knows the full surface ---
    # Two sources, same result. The live tape is preferred (it is the run's own
    # truth); the COMMITTED REGISTRY is the fallback, because the tape lives in a
    # 99 MB team bundle outside this repo and its absence used to drop all 332
    # column nodes while the build still reported success.
    for name, ov in _output_inventory(mas).items():
        kg.add_output(name, description=ov.variable, units=ov.units,
                      level=ov.dimension_level)

    P, M, O, C = kg.PARAMETER, kg.MECHANISM, kg.OUTPUT, kg.CATEGORY
    pid = lambda n: f"{P.lower()}:{n}"          # noqa: E731
    mid = lambda n: f"{M.lower()}:{n}"          # noqa: E731
    oid = lambda n: f"{O.lower()}:{n}"          # noqa: E731
    cid = lambda n: f"{C.lower()}:{n}"          # noqa: E731

    def ensure_output(n):
        if oid(n) not in kg.graph:
            kg.add_output(n)

    for cname, c in (seed.get("categories") or {}).items():
        for mname in (c.get("mechanisms") or []):
            if mid(mname) in kg.graph:
                kg.add_relationship(cid(cname), mid(mname), kg.CONTAINS)
        for oname in (c.get("key_outputs") or []):
            ensure_output(oname)
            kg.add_relationship(cid(cname), oid(oname), kg.AFFECTS)

    for pname, par in seed_params.items():
        if pid(pname) not in kg.graph:
            continue
        cat = par.get("category")
        if cat and cid(cat) in kg.graph:
            kg.add_relationship(cid(cat), pid(pname), kg.CONTAINS)
        for mname in (par.get("controls") or []):
            if mid(mname) in kg.graph:
                kg.add_relationship(pid(pname), mid(mname), kg.CONTROLS)
        for oname in (par.get("affects") or []):
            ensure_output(oname)
            kg.add_relationship(pid(pname), oid(oname), kg.AFFECTS)
        for rel in (par.get("related_to") or []):
            if pid(rel) in kg.graph:
                kg.add_relationship(pid(pname), pid(rel), kg.DEPENDS_ON)

    # outputs -> affected_by -> parameters (the seed carries this direction too;
    # it is NOT symmetric with `affects`, so both are walked deliberately)
    for oname, o in (seed.get("outputs") or {}).items():
        ensure_output(oname)
        for pname in (o.get("affected_by") or []):
            if pid(pname) in kg.graph:
                kg.add_relationship(pid(pname), oid(oname), kg.AFFECTS)
    return kg


def main() -> int:
    ap = argparse.ArgumentParser(description=f"Build the PFLOTRAN RAG index ({PROFILE}).")
    ap.add_argument("--rebuild", action="store_true", help="Rebuild the vector store from scratch")
    ap.add_argument("--no-write-counts", action="store_true",
                    help="Do not write expected_counts back to milestones.json")
    args = ap.parse_args()

    ms = load_milestone()
    kb_dir = _rel(ms["knowledge_base_dir"])
    wiki_dir = kb_dir / ms["model_wiki_subdir"]
    if not wiki_dir.is_dir():
        sys.exit(f"ERROR: wiki dir not found: {wiki_dir}")

    curated_path = ms.get("curated_yaml_path")
    persist_dir = REPO / "rag/chroma_db" / PROFILE
    meta_out = REPO / "rag/metadata" / f"{PROFILE}.json"
    meta_out.parent.mkdir(parents=True, exist_ok=True)

    os.environ["A2MC_RAG_DIR"] = str(REPO / "rag")
    os.environ["A2MC_RAG_ACTIVE"] = PROFILE

    print("=" * 68)
    print(f"  Building PFLOTRAN RAG profile: {PROFILE}")
    print(f"  wiki:    {wiki_dir}")
    print(f"  curated: {curated_path or '(none — GRAPH LAYER WILL BE SKIPPED)'}")
    print("=" * 68)

    # ---- vector layer (wiki only) ----
    wiki_docs = load_markdown_files(str(wiki_dir))
    for d in wiki_docs:
        d["kb_source"] = "pflotran"
    chunks = chunk_documents(wiki_docs)
    if curated_path:
        _seed_for_chunks = yaml.safe_load(_rel(curated_path).read_text())
        cur_chunks = build_curated_chunks(_seed_for_chunks)
        chunks = chunks + cur_chunks
        print(f"curated chunks: {len(cur_chunks)}")
    print(f"\nwiki pages: {len(wiki_docs)}   chunks: {len(chunks)}")

    if args.rebuild and persist_dir.exists():
        shutil.rmtree(persist_dir)
    vs = FATESVectorStore(persist_dir=str(persist_dir), collection_name=COLLECTION)
    vs.add_documents(chunks)
    chunk_count = vs.collection.count()
    print(f"vector store documents: {chunk_count}  -> {persist_dir}")

    # ---- graph layer: build it, or refuse rather than write an empty one ----
    graph_built = False
    n_nodes = n_edges = None
    if curated_path:
        seed = yaml.safe_load(_rel(curated_path).read_text())
        deck = Path(os.environ.get("A2MC_PFLOTRAN_DECK", "")) or None
        mas = Path(os.environ.get("A2MC_PFLOTRAN_REFERENCE_MAS", "")) or None
        if deck is None or not deck.is_file():
            ds_deck = _rel(ms.get("param_file") or "")
            deck = ds_deck if ds_deck.is_file() else None
        if mas is None or not mas.is_file():
            ds_mas = _rel(ms.get("output_cdl") or "")
            mas = ds_mas if ds_mas.is_file() else None
        print(f"\n  deck:    {deck or '(absent — parameter ADDRESSES will be omitted)'}")
        print(f"  outputs: {mas if (mas and mas.is_file()) else '(tape absent — falling back to the committed registry)'}")

        kg = build_graph(seed, deck, mas)
        graph_out = REPO / "rag/graphs" / f"{PROFILE}.json"
        graph_out.parent.mkdir(parents=True, exist_ok=True)
        kg.save(str(graph_out))
        n_nodes = kg.graph.number_of_nodes()
        n_edges = kg.graph.number_of_edges()
        graph_built = True
        print(f"\ngraph: {n_nodes} nodes, {n_edges} edges  -> {graph_out}")
    else:
        print("\n" + "!" * 68)
        print("GRAPH LAYER SKIPPED — no curated seed for PFLOTRAN.")
        print("  A graph needs a parameter inventory, an output inventory and curated")
        print("  relationships. PFLOTRAN has no parameter NetCDF and no output CDL (its")
        print("  deck is text and its outputs are fixed-width text + Tecplot), and")
        print("  models/pflotran/curated_seed.yaml has not been authored")
        print("  (onboard-model step 7, PI-in-the-loop).")
        print("  Writing an EMPTY graph here would look like a successful build and")
        print("  fail silently later, so no graph file is written at all.")
        print("  THIS PROFILE IS VECTOR-ONLY until the seed exists.")
        print("!" * 68)

    meta = {
        "metadata_schema_version": 1,
        "profile_name": PROFILE,
        "adapter": "pflotran",
        "built_at": datetime.now(timezone.utc).isoformat(),
        "model_commit_built": ms["model_commit_built"],
        "wiki_subdir": ms["model_wiki_subdir"],
        "param_file": None,
        "output_cdl": None,
        "curated_yaml": curated_path,
        "layers_built": ["vector"] + (["graph"] if graph_built else []),
        "vector_only_reason": (None if graph_built else
                               "no curated seed (onboard-model step 7, PI-in-the-loop); "
                               "PFLOTRAN also has no param NetCDF / output CDL"),
        "stats": {"chunk_count": chunk_count,
                  "graph_nodes": n_nodes, "graph_edges": n_edges},
    }
    meta_out.write_text(json.dumps(meta, indent=2) + "\n")
    print(f"\nmetadata -> {meta_out}")

    if not args.no_write_counts:
        mp = REPO / "rag/milestones.json"
        allm = json.loads(mp.read_text())
        allm["milestones"][PROFILE]["expected_counts"]["documents"] = chunk_count
        mp.write_text(json.dumps(allm, indent=2) + "\n")
        print(f"armed count-regression guard: documents={chunk_count}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
