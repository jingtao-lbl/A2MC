---
name: validate-rag-chain
visibility: public
category: kb-build
description: Validate the source→wiki→curated-YAML→RAG chain before shipping, using the three A2MC validators in dependency order. Use when the user asks to "validate the wiki/RAG", "check the wiki against source", "did the rebuild regress", "check for hallucinations before merging the wiki", "validate the curated YAML", or after generating a wiki / editing curated_relationships.yaml / rebuilding the RAG at a new commit. Runs codebase_wiki_validator (wiki↔source) → yaml_wiki_validator (YAML↔wiki+param+output) → rag_diff (profile vs reference), applies the Green/Yellow/Red banding and the fabrication-vs-false-positive triage. Distilled from docs/a2mc_reference/rag_validation_workflow.md.
modes:
  requires_fates: false
  nutrient_pathway: any
  scope: [rag]
  summary: "Validate the RAG chain (3 validators); model-agnostic."
---

# Validate the RAG Chain (3 validators, in order)

Full playbook, dimension tables, and the worked api-31-0→api-43-1 example are in
**`docs/a2mc_reference/rag_validation_workflow.md`**. This skill is the run-order +
triage runbook.

> **Why.** The chain `source → wiki → curated YAML → RAG → AI calibration` has four hops; a
> hallucination at any hop propagates downstream silently. The three validators close every
> edge. Run them **in dependency order and fix any Red before the next tier** — a Step-2
> "BOTH found" verdict is meaningless if the Step-1 wiki claim it rests on was fabricated.

## When to run

1. **Before canonizing a new/regenerated wiki** (the `generate-codebase-wiki` subagents can
   hallucinate — validate before it becomes the source of truth).
2. **After a curated-YAML edit** (hand edits drift from the wiki + param file).
3. **After a RAG rebuild at a new commit** (diff vs the prior milestone catches regressions).

A one-line YAML tweak doesn't need the full sweep — re-run only the affected layer.

## Step 1 — wiki vs source  (`codebase_wiki_validator.py`)

"Does the wiki cite real files, real line numbers, real routines, real parameter names?"

```bash
python tools/codebase_wiki_validator.py \
    --wiki   docs/fates-knowledge-base/fates-codebase-wiki-<HASH> \
    --source <path-to-source-checkout-at-that-commit> \
    --param-file docs/fates-knowledge-base/fates_params_info_<HASH>.json \
    --output docs/a2mc_reference/wiki_source_validation_fates_<HASH>.md
```

Five dimensions: (1) file-citation existence, (2) line-bound validity, (3) routine
declaration presence, (4) parameter-name validity, (5) module-file presence.

**Triage Dim 4 carefully** — it has a known false-positive rate because the wiki uses the
param prefix (`fates_*`) for derived-type names, namelist flags, and filenames. Read the
report's "wiki-only parameter names" table before calling them fabrications. **Dim 5 is the
strongest signal** — a `PRTMyHypothesisMod.F90`-style placeholder module is unambiguously
fake. Get to Yellow/Green here before Step 2.

## Step 2 — YAML vs wiki + param + output  (`yaml_wiki_validator.py`)

"Are the curated relationships consistent with the wiki + param file + output CDL at this
commit?" **Skip if Step 1 is Red.**

```bash
python tools/yaml_wiki_validator.py \
    --yaml rag/data/curated_relationships.yaml \
    --wiki docs/fates-knowledge-base/fates-codebase-wiki-<HASH> \
    --param-file docs/fates-knowledge-base/fates_params_info_<HASH>.json \
    --output-cdl docs/fates-knowledge-base/elm_fates_output_info_<HASH>.cdl \
    --output docs/a2mc_reference/yaml_wiki_validation_<HASH>.md
```

Five dimensions: (A) every YAML parameter has a wiki page, (B) every YAML mechanism has a
matching wiki section, (C) every `affects:` output is in the CDL, (D) every `code_reference`
(`File::routine`) resolves at source, (E) `calibration_notes` citation freshness sample.
Dim A "wiki-absent parameters" and Dim D failures are usually **renames at the new commit**
(`fates_cnp_km_nh4` → `fates_cnp_eca_km_nh4`) — cross-reference the param file / upstream
commit log and fix the YAML (the `inject-knowledge` skill's edit conventions apply).

## Step 3 (optional) — RAG profile diff  (`rag_diff.py`)

"How does this milestone's RAG compare to a known-good reference?" Skip on a first build
(no reference profile yet).

```bash
python tools/rag_diff.py \
    --profile-a-graph <reference-graph>.json --profile-a-wiki <ref-wiki> \
    --profile-a-param <ref-param> --profile-a-name <ref-name> \
    --profile-b-graph rag/fates_knowledge_graph.json --profile-b-wiki <new-wiki> \
    --profile-b-param <new-param> --profile-b-name <new-name> \
    --output docs/a2mc_reference/rag_diff_<ref>_vs_<new>.md
```

Four dimensions: nodes, edges, params, mechanisms. **Expected diff for a clean version bump
is "small reorder + a handful of renames."** Unexpectedly large removed-nodes/edges =
something dropped; large added = something duplicated or mis-categorized → root-cause back
in Step 1/2.

## Step 4 (post-rebuild) — index self-test, ROUTED BY MODEL

The three validators above check the *source→wiki→YAML→graph* chain; they do **not** catch a whole
knowledge base silently missing from the **vector index** (the 2026-07-05/06 ELM-wiki-absent bug — the
retriever answered FATES-only with no error). After a rebuild, run the one for your model:

| model | run this |
|---|---|
| **ELM / FATES** | `python tools/check_rag_coverage.py --profile <profile>`  (docs/33 §3c) — plus `tools/check_rag_queries.py` for content |
| **EcoSIM** | `python tools/check_ecosim_rag_queries.py --profile ecosim-2dea74d9` |
| **PFLOTRAN** | `python tools/check_ecosim_rag_queries.py --profile pflotran-157a26f7` |

**`check_ecosim_rag_queries.py` is model-GENERIC despite its filename**, which is kept for
back-compat: it reads the per-profile `collection` from `rag/golden_queries.yaml` and queries that
vector store directly, so it needs none of the FATES retriever plumbing and works for any registered
profile. It carries **both** guards in one run — a count-regression check against
`rag/milestones.json` and the golden-query content assertions, plus graph node floors.

**Do not read "FATES-only script" as "adapter models are unchecked."** `check_rag_coverage.py` reads
`rag/canary_queries.yaml`, which lists only the two `api-*` profiles, so on an adapter profile it
falls through to the default `fates_knowledge` collection and exits 1 — a missing config block, not a
missing capability. Measured 2026-09-06: reading that failure as an absence of coverage produced a
wrong conclusion in a dev log, corrected the same day.

### Step 4b — the curated-seed coverage gate (`validate_seed_coverage.py`)

**Run this after any curated-seed or curated-YAML edit**, for every model:

```bash
python tools/validate_seed_coverage.py --seed <the file the profile was built from>
```

C1 asserts every category with parameters has at least one mechanism; C2 asserts every calibratable
parameter is named by at least one. It exists because the seed builder prints
`[SKIP] category X has no assigned mechanisms` and then **exits 0**, so a partial seed reads as a
finished one — and an unreachable parameter is invisible to Phase 3, which can only recommend what a
mechanism reaches.

**Model-agnostic, verified on all three shapes** rather than assumed: `models/ecosim/curated_seed.yaml`
(PASS 10/10, 44/44), `models/pflotran/curated_seed.yaml` (FAIL, 4 unreachable) and
`rag/data/curated_relationships_api-43-1.yaml` (FAIL, unreachable parameters plus an orphan
mechanism). Read `rag/metadata/<profile>.json` for which file to pass — adapters keep it at
`models/<model>/curated_seed.yaml`, only the FATES profiles use `rag/data/`.

## Verdict scheme & triage

Banding (all three validators): **Green** ≥90% every dimension · **Yellow** any dim 70–90% ·
**Red** any dim <70%. Don't chase every line item — categorize first:

| Category | Action |
|---|---|
| Real fabrication (placeholder module, dead routine) | fix now — wiki rewrite or YAML refinement |
| Validator false positive (regex hit on derived-type / namelist / filename) | note in report's false-positive section; queue validator improvement |
| By-design scope mismatch (FATES wiki cites ELM-side file) | repath the citation or move the section to the other model's wiki |
| Renamed at this commit | cross-ref upstream commit log; update wiki/YAML to the new name |

A real first-pass outcome (api-31-0→api-43-1): Step 1 Red→Yellow after triaging Dim-4 false
positives; Step 2 Red→Yellow after fixing renamed phantoms; Step 3 within expected drift.
Whole pass ~half a working day for a coupled pair; re-runs after fixes are seconds.

## Notes

- Reports are Markdown tables, stack-readable when run in order; name them
  `tools/<name>_validator.py` → `docs/a2mc_reference/<check>_<HASH>.md`.
- This is **step 4** of the adapter-kit pipeline: `generate-codebase-wiki` →
  `rebuild-rag` → `inject-knowledge`/curated YAML → **validate**. Recipes V1 (patch wiki
  fabrications), V2 (curated-YAML drift after a bump), V3 (suspected regression) in the
  roadmap.
- Not yet covered (deferred): param-file↔source consistency, end-to-end retrieval smoke
  tests. If you build either, follow the `tools/<name>_validator.py` convention and add a
  section to the roadmap.
- Branch note: this is forward-dev tooling (milestone bumps live on `main`/adapter-kit);
  on a version-pinned manuscript branch its main use is a sanity pass after a curated-YAML
  injection + `--graph-only` rebuild.

## Changelog

- 2026-09-06: **Step 4 routes by model, and gains Step 4b for the curated-seed coverage gate.** PI-directed. Step 4 named only `check_rag_coverage.py`, which is FATES-only by configuration, so on an adapter model it exits 1 and the step read as inapplicable — while `tools/check_ecosim_rag_queries.py` is model-generic despite its filename and covers EcoSIM and PFLOTRAN today. **Signal:** on 2026-09-06 that failure was read as "the silently-missing-KB class is undetectable on the adapter line" and written into a dev log; it was false and was corrected the same day. New Step 4b names `tools/validate_seed_coverage.py`, which was referenced by **no skill at all** despite being the natural gate after a curated-seed edit — the seed builder skips an uncovered category and exits 0, so a partial seed reads as finished. Every claim in both steps was verified before being written: the generic guard runs on `pflotran-157a26f7` (14 assertions), and the seed gate runs on all three seed shapes with two genuine FAILs. No `description` changed, so no trigger moved.

- 2026-06-17: Initial version — distilled from docs/a2mc_reference/rag_validation_workflow.md.
