#!/usr/bin/env python
"""Model RAG guard: golden-query content check + count-regression check.

Model-generic (collection/profile-aware): the non-FATES analog of
tools/check_rag_queries.py (which is FATES/HybridRetriever shaped). Reads the
per-profile `collection` from rag/golden_queries.yaml and queries that vector
store directly + reads the graph JSON, so it needs none of the FATES retriever
plumbing and works for ANY registered model profile (EcoSIM today, any future
adapter). Pass `--profile <name>`; defaults to the EcoSIM profile. (Filename is
kept for back-compat; the logic is model-generic — this retires the need for a
per-model golden-query script, roadmap L3.3.)

Two guards (both proven on the api-31->api-43 migration, dev_logs 20260710s/v):
  1. count-regression — built index vs rag/milestones.json expected_counts
     (a >2% drop in docs/nodes/edges fails; the silent-shrink class).
  2. golden-query content — realistic queries with must_contain / must_not_contain
     assertions; the must_not_contain traps catch FATES/CLM priors leaking into
     EcoSIM's KB (the reason EcoSIM needs its own knowledge layer).

Exit 0 = pass (or graceful skip if the embedding model is unavailable);
exit 1 = a content/count assertion failed.

Usage: a2mc_env/bin/python tools/check_ecosim_rag_queries.py [--profile ecosim-2dea74d9]

Author: Jing Tao with Claude
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import yaml

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

DEFAULT_PROFILE = "ecosim-2dea74d9"


def _skip(msg: str) -> int:
    print(f"  [skip] {msg}")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description="Model RAG golden-query + count guard (profile-aware).")
    ap.add_argument("--profile", default=DEFAULT_PROFILE,
                    help=f"RAG profile to check (default {DEFAULT_PROFILE}); must have a golden_queries.yaml entry with a `collection`")
    PROFILE = ap.parse_args().profile

    cfg = yaml.safe_load((REPO / "rag/golden_queries.yaml").read_text()) or {}
    spec = (cfg.get("profiles") or {}).get(PROFILE)
    if not spec:
        print(f"  [warn] profile '{PROFILE}' not in golden_queries.yaml — nothing to test")
        return 0
    collection = spec.get("collection", "ecosim_knowledge")

    errors: list[str] = []
    n_checks = 0

    # --- 1. count-regression guard ---
    ms = json.loads((REPO / "rag/milestones.json").read_text())["milestones"][PROFILE]
    expected = ms.get("expected_counts") or {}
    meta_path = REPO / "rag/metadata" / f"{PROFILE}.json"
    if expected and meta_path.exists() and any(v is not None for v in expected.values()):
        stats = json.loads(meta_path.read_text()).get("stats", {})
        built = {
            "documents": stats.get("chunk_count", 0),
            "nodes": stats.get("graph_nodes", 0),
            "edges": stats.get("graph_edges", 0),
        }
        for k in ("documents", "nodes", "edges"):
            n_checks += 1
            if expected.get(k) and built[k] < expected[k] * 0.98:
                drop = 100.0 * (expected[k] - built[k]) / expected[k]
                errors.append(f"count-regression: {k} built {built[k]} < expected "
                              f"{expected[k]} ({drop:.1f}% drop)")
        print(f"  count check: built {built} vs expected {expected}")

    # --- 2. golden-query content check ---
    persist = REPO / "rag/chroma_db" / PROFILE
    if not persist.exists():
        return _skip(f"no built index at {persist} — run scripts/build_ecosim_rag.py first")
    try:
        from rag.vector_store import FATESVectorStore
        vs = FATESVectorStore(persist_dir=str(persist), collection_name=collection)
    except Exception as e:
        return _skip(f"could not load vector store / embedding model ({e})")

    for q in spec.get("queries") or []:
        name = q.get("name", q.get("query", "?"))
        try:
            results = vs.query(q["query"], n_results=6)
            ctx = " ".join(r["content"] for r in results).lower()
            # must_not_contain polices SOURCE-GROUNDED wiki content only. Curated
            # chunks intentionally contrast EcoSIM with FATES/CLM ("NOT Farquhar"),
            # so a forbidden term there is correct commentary, not a leak.
            ctx_wiki = " ".join(r["content"] for r in results
                                if r.get("type") == "codebase-wiki").lower()
        except Exception as e:
            errors.append(f"query '{name}': retrieval failed ({e})")
            continue
        for sub in q.get("must_contain") or []:
            n_checks += 1
            if sub.lower() not in ctx:
                errors.append(f"query '{name}': MISSING required text {sub!r}")
        for sub in q.get("must_not_contain") or []:
            n_checks += 1
            if sub.lower() in ctx_wiki:
                errors.append(f"query '{name}': found FORBIDDEN text {sub!r} in "
                              f"source wiki (FATES/CLM prior leaked into EcoSIM KB)")
        any_list = q.get("must_contain_any") or []
        if any_list:
            n_checks += 1
            if not any(s.lower() in ctx for s in any_list):
                errors.append(f"query '{name}': none of {any_list} present in context")

    # --- 3. graph presence (plant axis exists) ---
    gpath = REPO / "rag/graphs" / f"{PROFILE}.json"
    if gpath.exists():
        g = json.loads(gpath.read_text())
        n_param = sum(1 for n in g.get("nodes", []) if n.get("node_type") == "Parameter")
        n_out = sum(1 for n in g.get("nodes", []) if n.get("node_type") == "Output")
        n_checks += 1
        # Sparsity floors are PROFILE-DECLARED, not hardcoded. The former literals (20 params,
        # 50 outputs) were EcoSIM-scaled -- its output CDL carries 516 variables -- and a model
        # indexed from a smaller surface fails a floor it was never measured against.
        #
        # NOTE (corrected 2026-08-01): an earlier version of this comment justified the ATS floor
        # by claiming 9 observations "IS its complete target surface". That was WRONG. 9 is what
        # one deck REQUESTS in its `observations` block; the same deck defines ~39 State fields
        # (37 evaluators + 2 PK primaries), and across four decks the count is 0/0/7/9. The floor
        # value stands only because the ATS RAG is currently BUILT from the requested surface --
        # if that is widened to the available surface, re-derive it. See dev log 20260801j.
        # Defaults preserve EcoSIM behaviour.
        min_param = int(spec.get("min_param_nodes", 20))
        min_out = int(spec.get("min_output_nodes", 50))
        if n_param < min_param or n_out < min_out:
            errors.append(f"graph too sparse: {n_param} params (min {min_param}), "
                          f"{n_out} outputs (min {min_out})")
        print(f"  graph: {n_param} parameter nodes, {n_out} output nodes "
              f"(floors {min_param}/{min_out})")

    print(f"\n  profile '{PROFILE}': ran {n_checks} assertions, {len(errors)} failed")
    if errors:
        print(f"\n✘ RAG guard FAILED for profile {PROFILE!r}:", file=sys.stderr)
        for e in errors:
            print(f"    - {e}", file=sys.stderr)
        return 1
    print(f"✔ RAG guard [{PROFILE}]: content + counts correct")
    return 0


if __name__ == "__main__":
    sys.exit(main())
