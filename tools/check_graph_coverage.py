#!/usr/bin/env python
"""Which curated relations actually reach a model's knowledge graph — the `wire-knowledge-graph` audit.

WHAT IT CATCHES. A curated relation FIELD that no builder pass reads is inert, and every existing
mechanism is blind to it: it passes `tools/validate_curated_yaml.py`, which checks that names
RESOLVE and never that anything consumes them; it emits no `skipped edge` line, because nothing
tried; and it moves no count, so the builders' count-regression guard cannot see it — counts do not
fall when an edge is never created. Measured 2026-09-08 on EcoSIM: two whole relation blocks unread
for months, 95 edges, among them the driver of the scored target a live round was stuck on.

HOW. For every list-valued relation field in every seed block, count how many entries have a
resolvable endpoint and how many are joined by an edge in the built graph. Direction-agnostic and
type-agnostic on purpose: a field's intended edge direction is not knowable a priori, so an entry
counts as connected if ANY edge joins the two nodes either way with any relation type. That
under-reports subtly-wrong wiring and never invents a defect, which is the right bias for a gate.

  resolvable > 0 and connected == 0   ->  UNREAD, exit 1. Nothing reads that field.
  0 < connected < resolvable          ->  PARTIAL, reported, not a failure on its own: the usual
                                          causes are an endpoint of the wrong TYPE (`turnover` is a
                                          category where a mechanism was expected) and a graph built
                                          from a different seed than the one declared.
  no endpoint resolves                ->  nothing to wire; the seed names things this profile does
                                          not carry, which is `validate_curated_yaml`'s business.

WHICH SEED. The milestone's declared `curated_yaml_path`. **That is the seed the profile is supposed
to be built from, not necessarily the one it WAS built from**, and the difference is a real finding:
`scripts/build_rag_index.py` resolves the per-profile YAML, prints it and passes it to chunk tagging,
but calls `build_fates_graph()` without `curated_yaml_path`, so the FATES graphs are overlaid from
the shared `rag/data/curated_relationships.yaml` instead. Use `--seed` to audit against a different
file when you are testing that hypothesis.

Exit codes: 0 clean, 1 at least one UNREAD field, 2 usage.

Author: Jing Tao with Claude on Perlmutter
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent

#: seed block -> the node-id prefix its keys carry.
BLOCK_PREFIX = {"categories": "category", "mechanisms": "mechanism",
                "parameters": "parameter", "outputs": "output"}

#: list-valued fields that are NOT relations, so counting them as unwired would be noise.
NON_RELATION = {"dimensions", "addresses", "bounds", "values", "tags", "aliases",
                "units", "applies_in"}


def _relation_fields(seed: dict) -> dict:
    """-> {(block, field): [(entity_name, [entries...]), ...]} for every list-valued relation."""
    found: dict = {}
    for block, entries in seed.items():
        if block not in BLOCK_PREFIX or not isinstance(entries, dict):
            continue
        for name, entry in entries.items():
            if not isinstance(entry, dict):
                continue
            for field, val in entry.items():
                if (isinstance(val, list) and val and field not in NON_RELATION
                        and all(isinstance(x, str) for x in val)):
                    found.setdefault((block, field), []).append((name, val))
    return found


def audit(profile: str, seed_path: Path, graph_path: Path, verbose: bool = False):
    """-> (rows, unread_fields). Prints the per-field table."""
    import yaml

    seed = yaml.safe_load(seed_path.read_text()) or {}
    g = json.loads(graph_path.read_text())
    nodes = {n["id"] for n in g["nodes"]}
    adj = set()
    for e in g["links"]:
        adj.add((e["source"], e["target"]))
        adj.add((e["target"], e["source"]))

    print(f"\n{profile}")
    print(f"  seed  {seed_path.relative_to(REPO)}")
    print(f"  graph {graph_path.relative_to(REPO)}  ({len(nodes)} nodes, {len(g['links'])} edges)")
    print(f"  {'block.field':40s} {'entries':>7s} {'resolv':>7s} {'conn':>6s}  verdict")

    rows, unread = 0, []
    for (block, field), occurrences in sorted(_relation_fields(seed).items()):
        total = resolvable = connected = 0
        misses = []
        for name, values in occurrences:
            src = f"{BLOCK_PREFIX[block]}:{name}"
            for raw in values:
                val = raw.split("#")[0].strip()
                total += 1
                targets = [f"{p}:{val}" for p in BLOCK_PREFIX.values() if f"{p}:{val}" in nodes]
                if not targets:
                    continue
                resolvable += 1
                if any((src, t) in adj for t in targets):
                    connected += 1
                else:
                    misses.append(f"{src} -> {val}  (resolves as {targets[0]})")
        if resolvable == 0:
            verdict = "no endpoint resolves — nothing to wire"
        elif connected == 0:
            verdict = "*** UNREAD — resolvable and zero edges ***"
            unread.append(f"{profile}: {block}.{field} ({resolvable} resolvable, 0 edges)")
        elif connected < resolvable:
            verdict = f"partial — {resolvable - connected} resolvable but unconnected"
        else:
            verdict = "wired"
        print(f"  {block + '.' + field:40s} {total:7d} {resolvable:7d} {connected:6d}  {verdict}")
        if misses and verbose:
            for m in misses:
                print(f"      {m}")
        rows += 1
    if rows == 0:
        print("  (no list-valued relation fields in this seed)")
    return rows, unread


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--profile", action="append",
                    help="profile from rag/milestones.json; repeatable, default all")
    ap.add_argument("--seed", type=Path,
                    help="audit against THIS seed instead of the milestone's declared one "
                         "(single --profile only); use it to test which seed a graph came from")
    ap.add_argument("--verbose", action="store_true", help="list every unconnected pair")
    a = ap.parse_args()

    reg = json.loads((REPO / "rag/milestones.json").read_text())["milestones"]
    want = a.profile or sorted(reg)
    unknown = [p for p in want if p not in reg]
    if unknown:
        print(f"unknown profile(s): {unknown}", file=sys.stderr)
        return 2
    if a.seed and len(want) != 1:
        print("--seed applies to a single --profile", file=sys.stderr)
        return 2

    print("curated-seed -> knowledge-graph coverage  (wire-knowledge-graph, Step 1)")
    all_unread, checked, notes = [], 0, []
    for prof in want:
        seed_path = a.seed or (REPO / reg[prof]["curated_yaml_path"])
        graph_path = REPO / "rag/graphs" / f"{prof}.json"
        if not (seed_path.exists() and graph_path.exists()):
            print(f"\n{prof}: seed or graph missing — skipped")
            continue
        rows, unread = audit(prof, seed_path, graph_path, a.verbose)
        checked += rows
        # A `legacy: true` milestone is FROZEN: rag/milestones.json's own note on api-31-0 says
        # "do not rebuild", because its YAML is a snapshot matching that epoch's source names. Its
        # findings are reported and do NOT fail the run — a check that can never go green on a
        # profile nobody is allowed to fix is a check people learn to ignore.
        if reg[prof].get("legacy"):
            if unread:
                notes.append(f"  {prof}: LEGACY/frozen — {len(unread)} unread field(s) reported "
                             f"above and NOT counted as failures; this profile is not to be "
                             f"rebuilt (see its note in rag/milestones.json).")
            continue
        all_unread += unread
    if notes:
        print("\nnotes:")
        for n in notes:
            print(n)
    if all_unread:
        print(f"\nERROR: {len(all_unread)} relation field(s) are stated in a seed and reach no edge:",
              file=sys.stderr)
        for u in all_unread:
            print(f"  - {u}", file=sys.stderr)
        print("  Each is a field no builder pass reads. Add the pass to that model's OWN builder "
              "(see the `wire-knowledge-graph` skill), then rebuild and diff.", file=sys.stderr)
        return 1
    print(f"\n✔ every curated relation field with a resolvable endpoint reaches the graph "
          f"({checked} field(s) across {len(want)} profile(s))")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
