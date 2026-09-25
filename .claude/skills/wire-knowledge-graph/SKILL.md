---
name: wire-knowledge-graph
visibility: public
category: kb-build
description: Audit and fix WHICH RELATIONS a model's knowledge graph actually carries from its curated seed, and verify a graph rebuild is purely additive. Each onboarded model has its OWN `build_graph()` (FATES `rag/graph_builder.py`, EcoSIM `scripts/build_ecosim_rag.py`, PFLOTRAN `scripts/build_pflotran_rag.py`) reading its OWN seed field names, so a relation block one builder walks can be one another ignores — silently, since a field nothing reads produces no error, no skip message and no count change. Use when the user says "the graph cannot reach X from Y", "why does the graph not know about this parameter", "is the graph built", "add this relation to the graph", "audit the graph wiring", "does the builder read the whole seed", or when a Phase 3/4 traversal from a scored output returns nothing. NOT for reindexing or the vector store (use rebuild-rag), NOT for the wiki-to-YAML content chain (use validate-rag-chain).
modes:
  requires_fates: false
  nutrient_pathway: any
  scope: [rag]
  summary: "Audit/fix which curated relations reach the graph; per-model, model-agnostic workflow."
---

# Wire the Knowledge Graph — which relations actually reach it

The curated seed states relations; `build_graph()` turns some of them into edges. **This skill owns the gap between those two sentences.**

> **Interpreter.** Call it `$PY` below — `~/a2mc_env/bin/python` on Perlmutter.

## The failure this exists for, and why nothing else catches it

A seed field that **no builder pass reads** is inert. It passes `tools/validate_curated_yaml.py`, which checks that its names RESOLVE and never that anything consumes them. It produces no `skipped edge` line, because nothing tried. It moves no count, so the builders' count-regression guard is blind: **counts do not fall when an edge is never created.** And it reads correctly in the file, so a human reviewing the seed sees the relation stated.

**Measured on EcoSIM, 2026-09-08, twice in one audit.** `outputs.*.direct_drivers` / `indirect_drivers` (111 entries, 73 edges) and `categories.*.key_outputs` (22 entries, 22 edges) were both read for chunk text and by no relation pass. Among the missing was `RSMX -> ECO_ET_col`, the driver of the scored target a live round was stuck on, in a case where two consecutive diagnoses had already recorded "the graph cannot reach my target" as a blocking build task and neither found the cause. `dev_logs_adapterkit/20260908h_The_Output_Block_Nobody_Read.md`.

**`rebuild-rag` covers the adjacent and different failure**: an edge whose ENDPOINT does not resolve, which the FATES builder reports as `skipped edge: endpoint not found`. That one is loud. This one is silent.

## Step 0 — route to the model's own builder. There is no shared one.

| model | graph builder | signature | seed |
|---|---|---|---|
| FATES / ELM | `rag/graph_builder.py:build_fates_graph` (via `scripts/build_rag_index.py`) | `(include_pft_specific, ...)` | declares `rag/data/curated_relationships_<profile>.yaml`, **reads `rag/data/curated_relationships.yaml`** — see the warning below |
| EcoSIM | `scripts/build_ecosim_rag.py:build_graph` | `(params, output_cdl, seed)` | `models/ecosim/curated_seed.yaml` |
| PFLOTRAN | `scripts/build_pflotran_rag.py:build_graph` | `(seed, deck, mas)` | `models/pflotran/curated_seed.yaml` |
| ATS | none on this branch | — | — |

**One builder per model is deliberate and is not to be merged** (PI, `dev_logs_adapterkitats/20260801h`). Only the DATA STRUCTURE is shared: every builder constructs `rag/knowledge_graph.py::FATESKnowledgeGraph` with the same four relations (`contains`, `controls`, `affects`, `depends_on`).

**The parallelism is load-bearing because NODE IDENTITY differs per model**, which is the thing a merged builder could not carry:

- **EcoSIM** keys parameters by bare Fortran name, so parser keys and seed keys are the same string.
- **PFLOTRAN**'s parser keys by deck block path (`CHEMISTRY/MINERAL_KINETICS/Glass_FB/RATE_CONSTANT`) while its seed keys by the card leaf (`RATE_CONSTANT`), deliberately, because the knowledge is true of every instance of the card. The node is the LEAF; the deck addresses live on it as `addresses`.
- **FATES** additionally carries `PFT`, `Dimension` and `Module` node types and the `has_dimension` / `belongs_to` / `competes_with` / `implemented_in` relations that neither adapter has.

> **FATES's declared seed was NOT its effective seed until 2026-09-08, and the shape of that bug is worth keeping.** `scripts/build_rag_index.py` resolved the per-profile YAML, printed it, and handed it only to chunk tagging, calling `build_fates_graph()` without `curated_yaml_path`; that parameter defaults to `None` and `rag/graph_builder.py:634` resolved it to `DEFAULT_CURATED_RELATIONSHIPS_PATH`. Every profile's graph was therefore overlaid from the shared canonical file while its chunks came from the per-milestone one, so the two halves of one profile disagreed about the model. Fixed on PI direction and api-43-1 rebuilt (`20260908k`). **The lesson generalises: a path a builder RESOLVES and PRINTS is not evidence it USED it.** `--seed` exists to answer that question for any profile — audit against the file you suspect and see which one the numbers fit.

**A case's scored-target NAME is not a graph node.** The graph represents model SOURCE relations only — parameter, mechanism, model variable — and is case- and target-independent by construction (PI, `20260908b`). `plant_C` is a scoring convention over `[SHOOT_C_pft, Root_C_pft]`, not a model variable. A measured elasticity never becomes an edge either: the graph is corrected by SOURCE TRACING, which a measurement may prompt and never justifies.

## Step 1 — the coverage audit: every seed relation field, and whether a pass reads it

**Do this by reading the builder, not by querying the graph.** A graph missing an edge looks identical whether the pass is absent or the seed is silent, and the query cannot tell you which.

**Run `tools/check_graph_coverage.py` for the mechanical half** — it does the seed-to-graph
comparison for every registered profile in one pass and exits 1 on a field that is stated in a seed
and reaches no edge:

```bash
$PY tools/check_graph_coverage.py                      # all profiles
$PY tools/check_graph_coverage.py --profile <name> --verbose   # list every unconnected pair
$PY tools/check_graph_coverage.py --profile <name> --seed <path>   # test which seed a graph came from
```

**It runs in the pre-commit hook** (check 19), fired only by a commit touching a seed, a graph or a
builder. It went in only once every non-legacy profile was green: a check that is red on arrival is
one people learn to skip. A `legacy: true` milestone is reported and never fails the run, because
`rag/milestones.json`'s own note on `api-31-0` says not to rebuild it.

**It proves an edge exists between the pair, never that THIS field produced it**, so the grep half
below is still yours to do. EcoSIM's `parameters.depends_on` is read by no pass and still reports
`wired`, because both its entries also appear in `related_to`, which the builder maps onto the same
edge. Enumerate the seed's relation-bearing fields and grep the builder for each:

```bash
$PY - <<'PY'
import yaml, collections
seed = yaml.safe_load(open("models/<model>/curated_seed.yaml"))
for block in ("categories", "mechanisms", "parameters", "outputs"):
    f = collections.Counter()
    for v in (seed.get(block) or {}).values():
        if isinstance(v, dict):
            f.update(k for k, x in v.items() if isinstance(x, list))
    print(block, dict(f))
PY
grep -n 'get("<field>"\|get('"'"'<field>'"'"'' scripts/build_<model>_rag.py
```

A field that appears in the seed and nowhere in the builder is the defect. **Then check the SIBLING builders for the same field**, because the pass usually exists somewhere: PFLOTRAN has walked its outputs block since the day it was written, and that is what made EcoSIM's absence legible rather than a judgement call.

The wiring as of 2026-09-08, for orientation only — **re-derive it, do not trust this table to be current**:

| seed relation | FATES | EcoSIM | PFLOTRAN |
|---|---|---|---|
| `categories.*.mechanisms` -> contains | no category block | yes | yes |
| `categories.*.key_outputs` -> affects | no | **yes (2026-09-08)** | yes |
| `mechanisms.*.parameters` -> controls | yes | yes | seed-side only |
| `mechanisms.*.affects` -> affects | yes | yes | via categories |
| `parameters.*.controls` / `.affects` / `.related_to` | yes | yes | yes |
| output block -> parameter drivers | `controlled_by`, `key_parameters` | `direct_drivers`, `indirect_drivers` **(2026-09-08)** | `affected_by` |

**The three vocabularies are not a standard anyone is failing to meet.** Each builder reads its own seed, so each seed is free to name its own fields; there is nothing to align and no alias to add. What must match is builder-to-its-own-seed, and that is what the audit checks.

## Step 2 — write the pass, with the four decisions that are easy to get wrong

Mirror the sibling that already has it. Each of these was made, or nearly made, wrong:

1. **Skip an unresolved PARAMETER, never mint it.** `if pid(pname) not in kg.graph: continue`. Minting is how three phantom outputs entered the EcoSIM graph and answered queries about variables the model does not have (removed 2026-09-06). An unresolved name is a seed defect for a human; report it, do not create it.
2. **An OUTPUT named in the seed may legitimately precede the parsed registry**, so `ensure_output()` rather than a skip is right there — the curator is entitled to assert a history-tape variable, and `validate_curated_yaml.py` dimension B is the check on that claim. This asymmetry with rule 1 is deliberate.
3. **Never overwrite an existing edge.** `networkx.add_edge` REPLACES attributes on a repeat, so a later pass that re-asserts a relation the parameter side already wired will relabel it. Guard with `if kg.graph.has_edge(...): continue`. Wiring EcoSIM's outputs block without this would have relabelled 38 already-correct edges.
4. **Record a distinction as an ATTRIBUTE, not as a weight.** `rag/knowledge_graph.py` stores `weight` and returns it in edge listings; nothing in `hybrid_retriever.py` reads it. Encoding direct-versus-indirect as 1.0 against 0.5 would look like a ranking signal while being inert. EcoSIM uses `driver_kind="direct"|"indirect"`.

## Step 3 — rebuild, and prove the rebuild is ADDITIVE

Save the graph first, rebuild graph-only where the builder supports it, then diff node by node and edge by edge. A count line is not a diff: it cannot show a pre-existing edge whose attributes were replaced.

**The rebuild flag differs per builder, and getting it wrong is SILENT:**

| model | invocation | trap |
|---|---|---|
| EcoSIM | `scripts/build_ecosim_rag.py --graph-only` | — |
| PFLOTRAN | no `--graph-only`; see `rebuild-rag` | — |
| FATES | **`scripts/build_rag_index.py --rebuild --graph-only --profile <name>`** | **`--graph-only` ALONE does not rebuild.** `build_rag_index.py:576` is `if args.rebuild or not Path(g_path).exists()`, so with an existing graph it LOADS and re-saves it. The run reports "Graph saved", the counts match, and nothing changed. Measured 2026-09-08. |

**A FATES rebuild additionally needs a sourced site config** (`A2MC_MODEL_PATH`, `A2MC_PFTS`, `A2MC_BASE_PARAM_FILE`) and the ELM output CDL, and those decide the PFT nodes and hundreds of `parameter -> pft` edges. An in-process reproduction that omitted the ELM CDL produced **1279 nodes / 2323 edges against the committed 3178 / 2772**. The exact invocation behind the committed FATES graphs is recorded nowhere, so treat a FATES rebuild as unproven until its diff says otherwise, and never accept "the count guard passed" in place of the diff.

**Re-saving is not free.** That no-op FATES run rewrote `rag/metadata/<profile>.json`, reverting a host-path scrub and writing an absolute personal path back into a tracked file. Check `git diff` on the metadata after any rebuild, not only on the graph.

```bash
cp rag/graphs/<profile>.json ./tmp/graph_before.json
$PY scripts/build_<model>_rag.py --graph-only
$PY - <<'PY'
import json, collections
def load(p):
    g = json.load(open(p))
    return ({n["id"]: {k: v for k, v in n.items() if k != "id"} for n in g["nodes"]},
            {(e["source"], e["target"], e["relation_type"]):
             {k: v for k, v in e.items() if k not in ("source", "target")} for e in g["links"]})
bn, be = load("./tmp/graph_before.json"); an, ae = load("rag/graphs/<profile>.json")
print("nodes", len(bn), "->", len(an), "added", sorted(set(an)-set(bn)), "removed", sorted(set(bn)-set(an)))
print("node attr changes:", [k for k in set(bn) & set(an) if bn[k] != an[k]])
added = sorted(set(ae)-set(be))
print("edges", len(be), "->", len(ae), "| added", len(added), "| removed", len(set(be)-set(ae)))
print("PRE-EXISTING edge attr changes:", [k for k in set(be) & set(ae) if be[k] != ae[k]])
print("added shapes:", collections.Counter((s.split(':')[0]+'->'+t.split(':')[0], r) for s, t, r in added))
PY
```

**What a correct additive rebuild looks like:** edges added, **zero removed, zero node changes, zero pre-existing edge attribute changes**, and every added edge in the shape the new pass emits. **Reconcile the count against what you expect**, and expect the exact number: EcoSIM's outputs pass predicted 73 and delivered 72, and the missing one was `CNWL`, a seed name resolving to nothing — the skip guard demonstrating itself rather than a bug.

**Committing.** `chroma.sqlite3` carries `--skip-worktree` in every clone so `git add` stages nothing from it; a graph-only rebuild does not touch it anyway. Stage `rag/graphs/<profile>.json`, `rag/metadata/<profile>.json` and `rag/milestones.json` (the builder rewrites `expected_counts` for the half it rebuilt) — by explicit path, since a shared clone may hold other sessions' changes.

## Step 4 — pin it with a seed-to-graph completeness test

A count guard cannot express this class, so assert the IMPLICATION: **for every curated relation whose two endpoints both exist as nodes, the edge is in the graph.** Worked example: `tests/test_ecosim_graph_matches_seed.py`.

That single assertion covers two different regressions — a pass removed or never written, and a seed edited without a rebuild — and it stays true as the seed grows, which a count does not. Add beside it:

- a test **per newly wired block**, so a regression names itself instead of appearing inside a 73-line list;
- a **minting** test: a driver name existing as a node with neither description nor units is what a minted node looks like;
- an **unresolved-names** assertion holding the count at its known value, so the next dangling reference fails the suite instead of joining a crowd.

**Run the negative control both ways** — restore the pre-fix graph, confirm the tests fail, restore the new one, confirm they pass and the file is byte-identical. A test written after the fix and never seen red is not evidence.

## Guardrails

- **Do not edit `rag/graph_builder.py` to fix an adapter defect.** It serves FATES only; no adapter builder imports it. This was the first diagnosis of the 2026-09-08 audit and it was wrong.
- **Read the builder that runs.** Measuring the graph tells you what came out, never which code produced it. Two answers in that audit were built from correct measurements and an invented causal chain.
- **A graph-only rebuild leaves the VECTOR STORE behind**, and nothing reports it: three such rebuilds left EcoSIM's store with 18 of 21 mechanism chunks stale and one missing, while `chunk_count` never moved. If the seed's PROSE changed and not only its relations, a full rebuild is owed — `rebuild-rag` owns that.
- **Adding an edge is a claim about the model's SOURCE.** Confirm it in the code before wiring it, and cite `file:line` in the seed entry. A relation that is true of a run is case knowledge and belongs in `use_cases/{Model}_{Case}/memory/gained_knowledge/`.

## Cross-references

- `rebuild-rag` — reindexing, the vector store, the wiki bump, the commit trap, and the endpoint-not-found skip.
- `validate-rag-chain` — source to wiki to curated YAML content validation, upstream of this.
- `build-rag-from-scratch` — the whole layer for a new model; this skill is one step inside it.
- `phase3-diagnosis`, `phase4-hypothesis` — the consumers. A traversal from a scored output that returns nothing is the symptom that routes here.
- `dev_logs_adapterkit/20260908h_The_Output_Block_Nobody_Read.md` (the audit), `20260906f_The_Scored_Targets_Had_No_Edges.md`, `20260908b_Case_Level_Mechanism_Graphs_And_The_Node_Identity_Rule.md` (why a measurement is not an edge), `dev_logs_adapterkitats/20260801h_Reverse_Generic_RAG_Builder_To_Per_Model.md` (why the builders stay parallel).

