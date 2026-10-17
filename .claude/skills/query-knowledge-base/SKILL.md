---
name: query-knowledge-base
visibility: public
category: calibration
description: Query A2MC's three-tier knowledge base BEFORE reasoning from model source — Tier 1 technical documents and the commit-pinned codebase wiki, Tier 2 RAG vector search and the two-layer knowledge graph (auto-extracted structure plus the curated parameter-mechanism-output network), Tier 3 the two-layer adaptive memory (model-level and case-level gained knowledge) — to get the full parameter-mechanism-output picture, then go to source only to CONFIRM. The USE side of the knowledge base, distinct from the skills that build or patch it. Required by Phase 3 (diagnosis), Phase 4 (hypothesis) and Phase 6 (refinement) logs and by any log recording a diagnose-forensics finding, which must name this skill and cite the kb_network artifact. Use when the user says "what does the KB say about X", "query the knowledge base", "which parameters reach this output", "what controls X", "check the KB first", or whenever diagnosis, hypothesis, forensics or a model change is about to reason about a parameter, mechanism or output.
modes:
  requires_fates: false
  nutrient_pathway: any
  scope: [calibration]
  summary: "Query the three KB tiers network-first (tools/kb_network.py), then confirm in source. Every model."
---

# query-knowledge-base — the knowledge base first, the source to confirm

A2MC's knowledge base is built so that a calibration agent does not have to re-derive a model from its source every time it reasons about it. This skill is how it is USED. Building, validating and patching it is a different job with different tools (`build-rag-from-scratch`, `rebuild-rag`, `generate-codebase-wiki`, `validate-rag-chain`, `wire-knowledge-graph`, `inject-knowledge`; the per-model build tools are in [[reference_per_model_kb_build_tools]]).

## The three tiers (by design)

| tier | what it holds | how it is trusted |
|---|---|---|
| **1 — technical documents and codebase wiki** | literature, the model's official technical documents, and the codebase wiki pinned to a model commit | every claim cites the file and line, and is cross-verified against source (`validate-rag-chain` Step 1) |
| **2 — RAG and knowledge graph** | vector search over the indexed corpus, and a two-layer graph: the auto-extracted structure (parameters, outputs, dimensions, modules) and the curated parameter-mechanism-output relationship network | the curated layer is source-cited per entry (`tools/check_<model>_seed_citations.py`) and wired edge by edge (`wire-knowledge-graph`) |
| **3 — two-layer adaptive memory** | gained knowledge learned across calibration rounds: discoveries, experiments, failed approaches and parameter knowledge, at the MODEL layer and the CASE layer | human-curated before it is written (`curate-knowledge`, `inject-knowledge`); an unverified diagnosis is never written here |

They answer different questions and are not interchangeable: the graph says what is CONNECTED, the wiki says HOW and WHERE in source, the memory says what has already been TRIED and what it showed. Querying the one that answers first and stopping is the failure this skill exists to prevent. Phase skills that speak of "five surfaces" mean the same thing: the wiki (Tier 1), RAG and graph (Tier 2), and the model and case memory (Tier 3).

## When

- **Required:** every Phase 3 (diagnosis), Phase 4 (hypothesis) and Phase 6 (refinement) log, and any calibration log that names `diagnose-forensics`, names this skill and cites a `kb_network` artifact (`tools/check_calibration_log_conformance.py` C11 and C13).
- **Expected:** `model-evolution` (scoping a change), and any answer to "what controls X" or "why did Y not move".
- **Not at onboarding.** While a model is being onboarded the knowledge base does not exist yet, source is the only recourse, and the source-first rules of `onboard-model` govern. This is the calibration-stage rule.

## Step 1 — run the network query

Name the parameters, mechanisms and outputs the reasoning is about, and write the artifact into the phase's own results directory:

```bash
python tools/kb_network.py --model <model> --params <P ...> --mechanisms <M ...> --outputs <O ...> \
    --case <Model_Case> --out-dir use_cases/<Model_Case>/memory/phase_results/<stem>
```

- The profile is resolved by `tools/kb_profile.py` for the model; pass `--profile <p>` only to query a specific registered one.
- `--rag-k 0` skips vector search (no embedding model loads); keep the default for a real query.
- `--hops` (default 2) bounds a parameter-to-output path; raise it to find indirect routes.
- Exit 1 means no named entity is a node of the graph: the artifact is still written, and that is itself the first finding.

It writes `kb_network.md` (to read and cite) and `kb_network.json` (stamped with the profile and the knowledge base's commit, which the phase-log checker reads).

## Step 2 — read it tier by tier

1. **Reachability (Tier 2).** Does each named parameter reach each named output, and through which mechanism? "NOT REACHABLE" is either a real absence in the model or a gap in the curated network; Step 3 decides which. Two consecutive diagnoses once recorded "the graph cannot reach my target" without finding that a seed block was simply never read by the builder (`wire-knowledge-graph`).
2. **The network around each entity (Tier 2).** Its category, the mechanisms it controls, the outputs it affects, its `depends_on` couplings, and the sibling parameters that control the same mechanism, which are the competing levers.
3. **Curated seed entries (Tier 2).** `calibration_notes`, `code_location`, `inert` declarations.
4. **Documents (Tier 1).** The lines naming the entity in the profile's own pinned wiki and documents, and which of them cite source. An entity absent from Tier 1 is a documentation gap.
5. **Memory (Tier 3).** What the model layer and the case layer already hold: a failed approach on this lever, a measured viability bound, a discovery about the mechanism. Reading this is what stops a round from re-testing what an earlier round refuted.
6. **Gaps.** The artifact lists them. A gap is a build task for the knowledge base, not a reason to skip it.

**Then interactive retrieval when the artifact is not enough** — the same tiers, by hand:

```bash
A2MC_RAG_ACTIVE=<profile> python -c "
from rag import HybridRetriever
r = HybridRetriever(auto_build=False)
print(r.get_targeted_context(param_names=['<P>'], output_names=['<O>'])[:3000])
print(r.find_parameters_for_output('<O>'))"
```

## Step 3 — then the source, to CONFIRM

Open the code locations the artifact lists under "Then the source", which the knowledge base itself cites. Confirm the mechanism the network describes; do not learn it from source first. **If the source contradicts the knowledge base, that is a knowledge-base defect**: say so in the log and route it to the build side (a wiki claim to `generate-codebase-wiki`, a seed relation to `inject-knowledge` or `wire-knowledge-graph`, a patch for a source change to `generate-codebase-wiki` Workflow P). A parameter description can be wrong too; the equation is the authority ([[feedback_param_description_can_lie_verify_in_source]]).

## Step 4 — record it in the log

In the phase log, or for a forensics finding whichever calibration log it lands in:

- Name this skill under **Skills** in "Skills and memory invoked".
- Cite the artifact by path, e.g. `phase_results/<stem>/kb_network.md`, in the evidence the reasoning rests on.
- State, per tier, what it established and which gaps it left, and what the source confirmed or contradicted.

A sentence saying the knowledge base was consulted is not evidence that it was: the checker asks for the stamped artifact for that reason, after a word-match rule was rejected as satisfiable without doing the work.

## Where each tier lives, per model

| | FATES / ELM | adapter models (EcoSIM, PFLOTRAN, ATS) |
|---|---|---|
| Tier 1 wiki | `docs/fates-knowledge-base/<fates_wiki_subdir>/`, `docs/elm-knowledge-base/<elm_wiki_subdir>/` | `<knowledge_base_dir>/<model_wiki_subdir>/` |
| Tier 2 graph | `rag/graphs/<profile>.json` | `rag/graphs/<profile>.json` |
| Tier 2 curated network | `rag/data/curated_relationships_<profile>.yaml` | `models/<model>/curated_seed.yaml` |
| Tier 2 vectors | `rag/chroma_db/<profile>/`, collection `fates_knowledge` | `rag/chroma_db/<profile>/`, the milestone's `collection_name` |
| Tier 3 model layer | `memory/gained_knowledge/` (unprefixed: FATES only) | `memory/<model>/gained_knowledge/` |
| Tier 3 case layer | `use_cases/<Model_Case>/memory/gained_knowledge/` | `use_cases/<Model_Case>/memory/gained_knowledge/` |
| which profile matches a checkout | `scripts/rag_match.py` | `tools/model_preflight.py --model <model>` |

The paths in angle brackets are fields of the profile's entry in `rag/milestones.json`; `tools/kb_network.py` reads them, so a query never needs them typed. `tools/model_knowledge_store.py` resolves the Tier 3 model layer; copying one model's knowledge into another's store is a cross-model misroute.

## Guardrails

- **All three tiers, every time.** The answer from the first tier that responds is not the full picture.
- **A gap is a finding.** Record it; do not paper over it by reading source and moving on. In a calibration cycle, a link the source confirms and the graph lacks is staged in the cycle report's `graph_gap_candidates.yaml` (`write-report` item 5; `tools/graph_gaps.py`) for human review, and drawn in the report's mechanism graph (`tools/plot_kb_network.py`).
- **Tier 3 is read here and written elsewhere.** A conclusion reached in this session goes to memory only after a Phase 5 test verifies it and a human curates it ([[feedback_no_kb_injection_before_verified_test]]).
- **The profile is resolved, never typed** (`tools/kb_profile.py`).

## Cross-references

- `phase3-diagnosis`, `phase4-hypothesis`, `phase6-refinement`, `diagnose-forensics` — the four that require this skill; `model-evolution` — the other that uses it.
- `curate-knowledge`, `inject-knowledge` — how Tier 3 and the curated network are written.
- `wire-knowledge-graph` — when the graph cannot reach a target the source says it should.
- `.claude/hooks/remind-kb-before-source.py` — reminds when model source is read in a session that has not run `tools/kb_network.py`.
- Memory: [[feedback_full_mechanism_picture_before_designing_an_experiment]] (the rule), [[reference_per_model_kb_build_tools]] (the build side).

