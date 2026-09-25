---
name: scientific-analysis
visibility: public
category: calibration
description: Run a manuscript-supporting scientific investigation that ends in a figure + an ana_log — pose a question, pull ensemble/run data, compute the statistic/mechanism, make a figure, cite evidence, and write a log or report. Use when the user asks to "investigate whether X", "is X correlated with Y", "analyze the mechanism of X", "make a manuscript figure for X", "P-pool / cross-regime / attribution analysis". For a standardized single-round report use summarize-calibration-round; for cross-round figures use compare-calibration-rounds.
modes:
  requires_fates: false
  nutrient_pathway: any
  scope: [analysis]
  summary: "Investigation -> figure -> ana_log workflow; model-agnostic (examples are FATES/Kougarok)."
---

# Scientific Analysis → Figure → ana_log

The interactive agent does the open-ended, manuscript-supporting science that the fixed
calibration loop can't: "is PFT10 P uptake growth-limited or stoichiometric?", "attribute
the R2→R4 change", cross-regime / P-pool investigations. This skill codifies that
workflow so the result is reproducible and properly recorded.

> Use this for *free-form investigation*. For the canned single-round report use
> `summarize-calibration-round`; for cross-round comparison figures use
> `compare-calibration-rounds`. Those are the standardized deliverables; this is the
> exploratory one.

## Step 1 — pose the question precisely + scope the data

State the question as something falsifiable ("P uptake tracks NPP, not leaf stoich"), and
identify exactly what data answers it: which round/ensemble, which variables, which
validation targets, which cases (top-N? all? a contrast pair?).

**If the question touches a MODEL mechanism, check that model's knowledge base FIRST — don't assert
mechanism from names, and don't go straight to the source either.** This line named only
`docs/fates-knowledge-base/` until 2026-09-05, so on an adapter model it pointed at a directory for
the wrong model and read as "no KB applies here". Every onboarded model has one:
`docs/{fates,elm,ecosim,pflotran,ats,resom,sbetr}-knowledge-base/`, greppable with
`git grep -i <term> -- docs/<model>-knowledge-base/` whether or not a RAG profile is active.

**KB first, source to confirm.** The KB usually carries the `file:line` you were about to go find,
plus context the source does not: which axis a dimension belongs to, which of two similarly-named
axes applies, what a prior round measured. Read the source to CONFIRM a load-bearing claim and cite
it — the source remains ground truth on what the model DOES. Measured 2026-09-05: a session reconstructed the EcoSIM `micresb` slot semantics from Fortran over several turns, while `docs/ecosim-knowledge-base/ecosim-codebase-wiki-2dea74d9/microbial_bgc/index.md:133` stated it in one line WITH the same `MicBGCPars.F90:178-179` citation -- and additionally recorded that the 2-slot necromass axis is NOT the 3-slot living-biomass axis, a distinction the source read missed and which turned out to matter. The cost of skipping it: a wrong root-cause diagnosis and two fixes that treated symptoms.

**STAGE MATTERS, AND THIS IS THE CALIBRATION-STAGE RULE (PI, 2026-09-06).** While ONBOARDING a model the KB does not exist yet, source is the only recourse, and [[feedback_param_description_can_lie_verify_in_source]] governs: trace the read, then the internal variable, then its usage, especially before setting a bound. **At CALIBRATION stage the case is set up and the KB is assumed well-built, so the KB is where you START and it usually hands you the citation. It does NOT replace verifying in source: a KB page tells you what a thing IS, and only the code settles what it DOES -- or, just as often, what is ABSENT from it, which no page can state.** Query all five surfaces FIRST, then confirm in source. If you are in the source to LEARN what a parameter does rather than to CONFIRM what the KB told you, stop and name which it is: either you skipped the KB, or the KB has a gap. **A gap is a BUILD TASK** (rebuild the wiki, extend the curated seed, curate the round's findings at round close) and not something to route around every cycle.

**THE KB IS FIVE SURFACES, NOT ONE, AND THEY ARE NOT INTERCHANGEABLE. QUERY ALL FIVE, not the first one or two that answer.** They are: the **codebase wiki** `docs/<model>-knowledge-base/<model>-codebase-wiki-<commit>/` (`git grep -i <term> -- docs/<model>-knowledge-base/`, which works with no RAG profile active), the **RAG vector index** `rag/chroma_db/<profile>/` and the **knowledge graph** `rag/graphs/<profile>.json` (both via `HybridRetriever`), the **MODEL-level adaptive memory** `memory/<model>/gained_knowledge/`, and the **SITE-level adaptive memory** `use_cases/{Model}_{Case}/memory/gained_knowledge/`. The last two are the ones that get forgotten and they are populated: 21 entries for EcoSIM at model level, 28 for one case at site level, on 2026-09-05. Measured the same day on ONE parameter, `SPORC`: the knowledge-graph node carried a one-line description and units but no bounds, no code location and no mention of the two-slot axis, while the codebase wiki carried the slot semantics, the defaults AND the `MicBGCPars.F90` citation. Concluding "the KB does not have it" from the thin surface would have been wrong, so check the surfaces that hold that KIND of knowledge rather than the first one you open.

**The curated overlay lives in DIFFERENT PLACES by model family, and looking in the wrong one reads as "it does not exist".** An adapter model keeps it at `models/<model>/curated_seed.yaml`; only the FATES profiles use `rag/data/curated_relationships_<profile>.yaml`. The active profile's `rag/metadata/<profile>.json` names the file its graph was built from, so read that rather than guessing the path. Measured 2026-09-06: `models/ecosim/curated_seed.yaml` was declared missing on the strength of an `ls rag/data/`, and it is human-authored and is what built the EcoSIM graph.

**MEASURED COST OF QUERYING ONE SURFACE INSTEAD OF FIVE (EcoSIM_TeRaCON R1, seven cycles, 2026-09-06).** The graph stated `parameter:RMOM --controls--> mechanism:Microbial_Maintenance_Respiration --affects--> output:CO2_SEMIS_FLX_col`, the exact variable that case scores as `Fs`, and named 12 parameters for that output where a rank-correlation screen surfaced 4. The curated seed's `RMOM` entry carried the mechanism, the `NitroPars.F90:209` citation, the positive sign, the Morris rank and the `VMXO` coupling. The SITE store listed `RMOM` as an untested rank-1 alternative and recorded `CNRT` as a confirmed lever at +41% `plant_C`. All of it was re-derived from correlations across two cycles. The graph also declares three `depends_on` pairs among nine levers composed in one experiment, which is the documented explanation for a non-additivity that got written up as a discovery.

**THEN GO TO THE SOURCE AND CONFIRM IT. This step is not optional and is not reserved for claims you have already decided are load-bearing.** Confirming is not the same as learning: at calibration stage you arrive at the source already knowing what the KB says, in order to check it, so the read is short and targeted. A long exploratory source read at this stage is the signal described above. The KB tells you what a thing IS; the source tells you what it DOES. Open the `file:line` the KB handed you in the checkout at `$A2MC_MODEL_PATH` and read **the code that USES the value**, not only its declaration or its description string: a `description`, a `long_name` or a `units` field in any of these surfaces can be wrong, which is a standing rule here ([[feedback_param_description_can_lie_verify_in_source]]) and is exactly why the KB read is a starting point rather than an answer. Confirming costs one command -- `git -C "$A2MC_MODEL_PATH" show HEAD:<path> | sed -n '<lo>,<hi>p'` -- against the hours a wrong mechanism costs downstream.

## Step 2 — pull + analyze

Reuse the analysis tooling rather than re-deriving:
- `use_cases/{Model}_{Case}/analysis/` scripts (attribution, contrast, forcing comparison) and
  `tools/plot_ensemble_cases.py` / `tools/extract_ADSP_RGSP_slim.py` for ensemble data.
- **For any per-PFT / SZPF extraction in a custom script, use `tools/fates_utils`** — `get_szpf_range()`,
  `extract_pft_data()`, `aggregate_szpf_by_pft()`, `get_pft_index()`, `identify_dimension_level()`. Do
  **not** hand-roll the SZPF (`levscpf`) index: it is **PFT-major** `(pft-1)×nlevsclass`, where
  **`nlevsclass` is file-derived** (`get_n_size_classes(ds)` from `fates_levscls` — 13 in the common
  default but *configurable*, NOT a fixed constant), plus a 0-based/1-based PFT offset. (The FATES wiki's
  `(size_class-1)*numpft+pft` is a known **wiki error** — the source is PFT-major; `fates_utils` encodes
  the correct form.) `fates_utils` is the canonical helper the extract/plot tools use.
- Compute the actual statistic (correlation r, attribution, regression) — quote the
  number, don't hand-wave. If a tiny/odd subset is involved, run `diagnose-forensics`
  triage first (is it real or an artifact?).

## Step 3 — make the figure (filename convention)

**Use the `plotting` skill, and load it before the first `savefig`.** It carries the fonts,
units, semantic colours and the A2MC ensemble template — and the one step that actually
catches a broken figure: **open the rendered PNG and look at it.** An overlapping legend or a
label sitting on the data never shows up in the code.

Save figures under `use_cases/{Model}_{Case}/analysis/` with the **round + axis-mode + case
count** embedded in the name (memory: plot filename convention) — e.g.
`R4_combined_519yr_top50_<topic>.png` — to avoid the `ensemble_biomass_all_cases.png`
ambiguity from past sessions. Figures are gitignored, so the filename is the only durable
pointer.

## Step 4 — write the ana_log (cite explicit evidence)

Write an `ana_log` via the `/log` skill (`/log ana <topic>` → `memory/ana_logs/`). The
load-bearing rule: **every quantitative claim names its figure / statistic / data file
inline**, and a section drawing on several artifacts gets an **"Artifacts this section is
based on"** table. A claim with no cited source is a red flag — find the source or soften
it. Render to PDF with the `markdown-to-pdf` skill if it's a shareable note.

## Step 5 — land the lesson (optional)

If the analysis yields a vetted, generalizable discovery, add it to the curated KB — but
Tier-3 is **interactive-only**, so author it deliberately (an `interactive`-mode
MemoryManager / by hand) or stage + promote via `curate-knowledge`. Do NOT inject an
unverified hunch.

## Notes
- ana_logs are manuscript working notes — tracked on this branch, excluded from public
  sync.
- Pairs with: `diagnose-forensics` (triage odd results), `compare-calibration-rounds` /
  `summarize-calibration-round` (standardized figures), `/log` (the ana_log + supersede
  protocol), `markdown-to-pdf` (render), `curate-knowledge` (land a lesson).

