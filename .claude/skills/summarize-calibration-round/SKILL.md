---
name: summarize-calibration-round
visibility: public
category: calibration
description: >-
  Produce a one-round calibration summary for ANY onboarded model — the whole-ensemble figure per scored target, an evaluation report (best case, number of targets met, per-target simulated vs observed against each target's own band), the round's sensitivity screen, and the round's MECHANISM INVENTORY (what the round established about the SYSTEM, each finding carrying a file:line or artifact citation) — ending in a markdown + PDF report. Model-agnostic contract; the figure/screen BACKEND is per model (FATES: combined 519-yr + TRANS biomass graphs and Morris μ*; adapter models: the case's own ensemble plot and whatever screen the round actually produced). A REQUIRED step before the ROUND report. Use when the user asks to "summarize round N", "make a report for R5", "round N summary/report", "how did R3 do", "what did this round establish", "what did we learn this round", "what mechanism did round N find", or wants the combined+TRANS ensemble figures plus evaluation+sensitivity for a SINGLE round. (For comparing rounds against each other, use compare-calibration-rounds instead.)
modes:
  requires_fates: false      # generic since 2026-08-24; the CONTRACT is model-agnostic, the BACKEND is per model
  nutrient_pathway: any
  scope: [analysis]
  summary: "Single-round summary for any model: whole-ensemble figure per scored target + evaluation + the round's sensitivity screen. Targets drive from the case targets.yaml; the producing tools are resolved per model (see 'Resolve the backend FIRST')."
---

# Summarize a Calibration Round

Single-round **standardized** deliverable: ensemble graphs + evaluation + sensitivity + the round's mechanism inventory, tied into a markdown/PDF report with a fixed structure. The cross-round analog is `compare-calibration-rounds`; this is its per-round complement and shares the same footguns + tooling.

**It is not the round report.** That one is `write-report`'s, synthesizes the round's **cycle reports** into an arc plus a next-round plan, and cites the figures produced here. See the section immediately below for how the two fit together and what the round report needs pulled from each cycle.

## When to use

- "Summarize round N", "make a report for R{N}", "how did R{N} do".
- After a round's ensemble (largely) completes, or after relaunched/added cases land.
- NOT for round-vs-round comparison (→ `compare-calibration-rounds`).

## Resolve the BACKEND first — the contract is generic, the tools are not

**This skill was `requires_fates: true` until 2026-08-24 and its whole pipeline was FATES.** On a branch whose purpose is generalizing A2MC beyond ELM, that meant **the standardized round-close deliverable did not exist for any adapter model** — EcoSIM, PFLOTRAN or ATS — so those rounds closed with hand-rolled figures and no standardized evaluation. Fixed by splitting what this skill guarantees from what produces it.

**What this skill guarantees, for every model:**

1. a **whole-ensemble figure covering EVERY SCORED TARGET**, with the observation drawn as measured (gaps left as gaps) and each target's own acceptance band;
2. an **evaluation**: the best case by the round's own metric, how many cases meet how many targets, and per-target simulated against observed;
3. **a SENSITIVITY FIGURE and a sensitivity DISCUSSION. Always, whatever the sampling method, and whether or not the designed estimator worked** (PI, 2026-08-24). "The estimator did not converge" is a licence to change instrument, never to omit the section. It happened once, and the instructive part is that the round had **already computed** usable rankings: its Phase 1 recorded a point-biserial viability screen it explicitly labelled usable, with an alignment control, plus per-target rankings among the survivors, all sitting in a JSON that nothing ever plotted. The gap was between COMPUTED and PRESENTED, not between possible and impossible. **Fall down this ladder until something works, and name in the discussion which rung you are on and why:** (a) the design's own estimator, Sobol/Saltelli S1 and ST or Morris mu\* and sigma; (b) if it did not converge, the **controlled single-parameter pairs the design already contains** (a Saltelli block's A/AB and B/BA rows differ in exactly one column, and one round recovered 2,374 such already-run experiments across all 28 parameters at zero compute) — report the median effect **beside its sign consistency**, since a near-zero median for a base-dependent lever is not the same finding as a weak parameter; (c) regression-based sensitivity over the whole sample, standardized regression coefficients or rank correlation, which any design supports including LHS and plain random; (d) the always-available floor, **per-parameter quintile response of each scored target**, which needs nothing but the Y matrix and the design matrix. **And where deaths are non-trivial, the section covers VIABILITY as its own dimension**, not only the scored targets among survivors: which parameters kill, in which direction, at what threshold. A round that lost 81 percent of its ensemble has most of its sensitivity information in that dimension, and a section computed on the alive sub-ensemble alone silently discards it;
4. **the SYNTHESIS across every experiment cycle and every inner-loop iteration of the round.** Read the **CYCLE REPORTS**, one per experiment cycle, not the raw logs (the nesting diagram above is the rule: each layer synthesizes the layer directly beneath it). Each cycle report already walks its own inner loop iteration by iteration, naming each hypothesis with its falsification bar, so the synthesis here is over cycles and inherits the iterations through them. A cycle with no report is a gap to fix before this step, not a cycle to skip;
5. **the TWO REQUIRED TABLES, produced here** and carried by the round report (numbered Table 1, Table 2 there, never lettered). **the CYCLE LEDGER table:** one row per experiment cycle including the screening/design cycle, with the question or hypothesis and its falsification bar, the parameters varied and the values tested, the result per scored target, and the verdict with what it taught. **the PARAMETER REFERENCE table:** every parameter the round names, with what it is and its units, where it acts in the source as `file:line`, the mechanism it affects, the baseline, the range tested, and its role. Its cross-round **status** column is filled at the next step by `compare-calibration-rounds`, not here. Formats and worked rows: `write-report`, the ROUND report section;
6. **a MODEL EVOLUTION RECORD, whenever the model source changed at all since the previous round, PLUS a compact table appended to the round report** (PI, 2026-08-24, revised the same day). **The detail does not go in the narrative.** Engineering provenance in the middle of a science report reads as an intrusion, and the PI said so about the first attempt. Split it:
   - **The record** lives at `use_cases/{Model}_{Case}/memory/model_evolution/{stem}.md`, using the same stem convention as a phase log so it sorts and cross-references the same way: `YYYYMMDDx_model_evolution_r{RR}_{descriptor}.md`. It carries which binary the round **actually ran** (from the ledger's `round_binaries`, not from the `ecosim_source` block, which records only what the round was configured against and routinely disagrees), every change separating it from the previous round with that change's `kind`, each one's V0-at-equality result, the comparability verdict **split by what is being compared** (a change can leave per-case values bit-identical and still make counts incomparable), what no change addresses, and any change that exists but is absent from this binary.
   - **The report** carries only an **appendix table at the end**: commit, what it updated, kind, present in which rounds, effect on a run, plus three one-line comparability statements and a pointer to the record. One sentence in the design section says which binary ran and points at the appendix.
   - Source of truth for both is the case's `config/calibration_rounds.yaml` `model_change_ledger`. If nothing changed, one line saying so. If the case has no ledger, say that rather than omitting, because an absent ledger is a provenance finding rather than a licence to skip;
7. a markdown report, PDF-renderable, that the ROUND report then cites (see the section below);
8. **the MECHANISM INVENTORY: what the round established about the SYSTEM** (2026-09-05). Not the arc, which is guarantee 4, and not a parameter's role, which is the parameter reference table. This is the physical or biological finding: what controls what, through which term, at what magnitude, with a `file:line` or artifact citation for every number. **Its sources are the round's diagnoses, and one of them is machine-readable**: every Phase-3 diagnosis and Phase-6 refinement of the round, plus `use_cases/{Model}_{Case}/memory/workflow_state_offline_r{NN}.json`, whose `evidence.diagnoses[] / .hypotheses[] / .experiments[]` carry a `one_line` written when each finding was fresh and whose `decisions[]` carries every finding as it was established. **`write-report` REQUIRES a mechanism section in the round report and does not derive it, exactly as with the two tables — so if it is missing there, the missing work is here.** Signal: one round report described a two-solute trade-off correctly in four places and never named the pH dependence causing it, the fixed source ratio creating it, or the saturation asymmetry splitting it. Every number was in that round's first Phase-3 diagnosis with citations and in its state file. Nothing in this skill asked for it, so nothing carried it up, and the omission was invisible because every other requirement was a structure with a checker while this one belonged to no structure.

**These are this skill's output and they are the INPUT `write-report` builds the ROUND report from.** That is the direction, and it is worth being explicit because it is easy to invert: the cycle reports feed **this** skill, this skill's synthesis and tables feed **`write-report`**, and `write-report` writes the narrative. `write-report` REQUIRES both tables to be present in the round report; it does not derive them. If they are missing, the missing work is here.

**What is per model.** Resolve it before running anything: `python tools/describe_mode.py`, or read `$A2MC_MODEL`.

| | FATES / ELM (CIME) | EcoSIM, PFLOTRAN, ATS (adapter) |
|---|---|---|
| ensemble figure | `tools/plot_ensemble_cases.py` (`--combined` 519-yr + TRANS), 3 PFT x 2 organ | the case's own ensemble/target plot template in `use_cases/{Model}_{Case}/scripts/`, one panel per scored target |
| screening / evaluation | `phases/phase2_screening/screen_ensemble.py` | `scripts/extract_flat_ensemble_targets.py` output + the case's screen (e.g. `screen_params_vs_targets.py`) |
| sensitivity | `phases/phase1_exploration/morris_sensitivity_analysis.py`, Morris μ* | the ladder in guarantee 3, in order: the design's own estimator, then controlled single-parameter pairs extracted from the design, then regression or rank correlation, then per-parameter quintile response. **A figure is produced either way; state which rung and why** |
| case naming | `A2MC_CASE_NAME_PATTERN`, `PtCNPEn(\d+)…_TRANS` | `A2MC_CASE_NAME_PATTERN`, flat `<prefix>case{N}` |

**The footguns below are written in FATES terms and most of them generalize.** Read each one for its *mechanism* rather than its tool name: footgun 1 is "an out-of-range experiment case swept into a whole-ensemble screen", which is a naming-pattern problem every model has; footgun 6 is "a partial ensemble invalidates the sensitivity but not the ranking", which is universal. Footguns 3 and 4 are genuinely Morris-file-specific and do not apply where Morris was not run.

**If a required piece does not exist for this model, say so in the report rather than dropping the section.** A round summary silently missing its sensitivity section reads as if none was needed.

## Inputs (source the round's config first)

```bash
source use_cases/{Model}_{Case}/config/<site>_config_r<N>.sh   # sets ENSEMBLE_OUTPUT, EXTRACTED_DATA,
                                                        # A2MC_CASE_NAME_PATTERN, targets; and
                                                        # auto-sources its machine config (v2.306)
```
Round run dir = `$A2MC_ENSEMBLE_OUTPUT`; extract dir = `$A2MC_EXTRACTED_DATA`.

## FIRST: this is STEP 1 of a three-step round close, and it is not the round report

```
summarize-calibration-round   ->   compare-calibration-rounds   ->   write-report (ROUND report)
   THIS skill: this round          what EARLIER rounds            the arc + the next-round plan,
   figures + evaluation            established, and the           carrying BOTH of the above
   + the round's screen            per-parameter cross-round
                                   status the plan needs
```

**All three are steps, not options** (PI, 2026-08-24; `write-report`'s ROUND report section is the contract). Skipping step 2 is the one that has actually cost something: a round summary written from one round's artifacts proposed re-adding two parameters that earlier rounds had already refuted with named mechanisms. This skill's output is INPUT to the round report, which synthesizes the CYCLE reports

**Two different artifacts close a round and they are easy to confuse.** Getting the relationship wrong produces either a round report that re-narrates every cycle from raw logs, or a standardized summary that tries to be a narrative.

**The nesting, verbatim from `write-report` so the two skills cannot drift apart:**

```
phase logs + phase_results/{stem}/     one per phase, per inner-loop ITERATION
        │  (the evidence: figures, captions, canonical scripts, data)
        ▼
CYCLE REPORT      one per experiment cycle (Phase 3→4→5→6)
        │  synthesizes EVERY log and EVERY phase_results/ folder of that cycle
        ▼
ROUND REPORT      one per calibration round
           synthesizes the CYCLE REPORTS, not the raw logs again
        ▲
THIS SKILL        supplies the round-wide FIGURES and TABLES the round report cites  <- you are here
```

**Those round-wide figures belong to no phase stem, so their script lives with the report it serves.** The canonical-script rule (`calibration-discipline` item 2) governs a PHASE's figure scripts and does not apply here; it bites only when a report copies an existing stem's script and edits it there. When a figure this skill CITES from a cycle needs changing, fix the canonical script in its stem and regenerate.

**Each layer synthesizes the layer directly beneath it and CITES the one below that.** That is the whole rule, and both ways of breaking it are common: a cycle report that re-derives from raw logs duplicates them, and a round report that re-derives from raw logs duplicates every cycle report. This skill sits to the side of that chain rather than inside it: it is the round-wide evidence the top layer cites, not a layer of the synthesis.

**This skill is the standardized, FIXED deliverable**: the whole-ensemble figure covering every scored target, the screening evaluation, the round's own sensitivity ranking (Morris mu\* where Morris was run, whatever the round actually produced otherwise, and an explicit statement where it produced none), and the round's **mechanism inventory** (guarantee 8). It answers *"what does the whole round's ensemble look like, and what did the round establish about the system"*. It still does **not** narrate what the cycles learned, and it should not try to: the ARC across cycles is the round report's, and the distinction is the one guarantee 8 turns on. A mechanism is a property of the system, stated once with its evidence; the arc is the story of how the round came to believe it. Added 2026-09-05, because leaving the mechanism to the narrative layer alone is how one round report lost it.

**The round report is `write-report`'s** ("the two calibration deliverables"). It synthesizes the **cycle reports**, not the raw logs, and it must end with a concrete next-round work plan (`calibration-discipline` item 9). Where both exist, **the round report cites this skill's figures.**

### Synthesizing the cycle reports — what the round report needs from them

When the round report is written, walk the cycle reports **in order** and pull, per cycle:

| from each cycle report | into the round arc |
|---|---|
| the hypothesis and its **falsification bar** | what the round believed at that point |
| the variants that tested it, and the **verdict** | CONFIRMED / PARTIAL / REFUTED, and the number that decided it |
| the **inner-loop** iterations | what was settled for free, and what each one corrected in the one before |
| the **binding target** at cycle end | whether the round's obstacle moved or stayed put |
| what the cycle **retired** | levers, bases and designs the next round must not re-propose |

Then say the things **no single cycle report can**, which is the whole reason the layer exists:

1. **The arc.** Which lever was established, which was retired, and what each cycle's failure taught the next. A round is a sequence of corrections; a list of four verdicts is not that sequence.
2. **Where the obstacle moved to.** The binding target at round start against the binding target at round end, and whether the residual is the same one, a different one, or the same one for a newly-understood reason.
3. **What is now known to be OUT of reach within the round's own bounds** — a lever whose response was still steepening at its declared limit is a bounds question, not a mechanism question, and only the cross-cycle view distinguishes them.
4. **Which cycles produced findings that are candidates for the curated KB** (human-gated at the round-close, item 11), and which produced a **failed approach** worth recording so it is not re-proposed.
5. **Cost.** How many cycles, how many HPC experiments, and how many questions were settled for free in the inner loop. A round that spent ten experiments to answer what four could have is a finding about the process, not just the science.

**Cite, never restate.** Each claim names the cycle report it came from. If a number needs repeating, repeat the number and cite its source; do not re-derive it from the logs, because that is how the round report and the cycle report drift into disagreeing.

## Three deliverables

> **These three are the TOOL-produced artifacts** — figures, an evaluation, a sensitivity ranking. Guarantee 8, the mechanism inventory, is written rather than computed, so it has no tooling row here; its home is item 4 of the report structure below and its sources are the round's diagnoses and its offline state file.

### 1. Whole-ensemble graphs (combined + TRANS)
`tools/plot_ensemble_cases.py` (`--combined` for the 519-yr ADSP+RGSP+TRANS axis; default for the TRANS-only zoom) — or the round wrapper `regen_ensemble_milestone_plot.sh` / `use_cases/{Model}_{Case}/analysis/regen_milestone_plot.sh`. Combined needs ADSP(1-200)+RGSP(201-400)+TRANS NCs per case (extract all 3 phases). Output: `R{N}_{combined,TRANS}_{count}cases_ensemble.png`.
- **Per-round graphs are UNCAPPED**: include the round's own legitimate extra cases (e.g. R3 + its 51 model-swap reruns = 4941, merged via offset case numbers). Do NOT pass a case cap here.

### 2. Evaluation report (screening)
`phases/phase2_screening/screen_ensemble.py --data-dir $A2MC_EXTRACTED_DATA --top-n 100 --output-dir <out>` → best case #, composite NRMSE, # targets met, per-target best-case sim vs obs.
- **Cap foreign contamination:** pass `--max-case-num <Morris size>` (e.g. 4890) so out-of-Morris experiment cases that happen to share the extract dir (e.g. H1 clumping #5001) don't rank as "best". This is distinct from #1: the round's *own* reruns are a separate model-swap view, not part of its Morris screening.
- Read `_results.txt` Sim_ columns + `screening_result.json` `best_case_num`, NOT the indices file.

### 3. Sensitivity report (Morris μ*)
Per target (PFT×organ): `build_Y_from_monthly.py` (builds Y, auto-excludes case# > ensemble size) → `phases/phase1_exploration/morris_sensitivity_analysis.py --output-var {leaf,fineroot}_biomass --x-matrix <Morris X> --y-matrix <Y> --problem <salib_problem> --output-dir <out>` → per-PFT μ* CSVs.
- **Partial-ensemble caveat:** Morris μ* needs reasonably complete trajectories; with many missing cases (NaN rows) SALib drops incomplete trajectories. Report how many trajectories survived and flag μ* as provisional if the round is far from complete (e.g. R5 at 92.6% with deterministic model-failure dropouts — μ* usable but caveated).

## Report writing standard (the report is for a HUMAN with NO project context)

A round summary is read by a PI, a collaborator, or a manuscript reviewer who has **never seen the codebase, the logs, or any internal name.** Internal logs may use project shorthand because writer and reader share context; a *report* may not. Write to that reader:

1. **Executive summary first.** Open with 3–5 plain-language sentences a reader can understand alone: what the round tested, what it found, and what happens next.
2. **Define-or-avoid every internal term.** Expand each experiment codename / model-internal / A2MC term to plain language on FIRST use, or don't use it. Banned-unless-defined includes: any run-specific experiment codename, FATES internals (`PARTEH`, `ADSP/RGSP/TRANS`, `cohort_n`, `l2fr`, `prescribed_puptake`, `EDMainMod.F90:1010`), and A2MC terms (`V0`, `Morris μ*`, `skip-test`). e.g. write "the plant carbon–nutrient allocation solver (called PARTEH in FATES)", not "PARTEH".
3. **Every claim is a complete sentence: plain finding → mechanism → evidence.** No isolated jargon phrases. Template: *"[what happened, in physical/biological terms]; [why — the mechanism]; [the number or figure that shows it]."* **Bad:** "72 solver failures are restart-eligible." **Good:** "72 of the simulations stopped when the plant carbon–nutrient allocation solver failed to converge numerically; re-running five identical copies of one such case reproduced none of the failures (0 of 5), so these are numerical round-off artifacts that mostly succeed on resubmission — not model errors a parameter change could fix."
4. **Physically grounded, code as a footnote.** Lead with the biology (plant establishment, biomass, leaf-out timing) and the physical quantity; cite the source-file location as supporting detail, not the headline.
5. **Every figure and statistic carries its interpretation inline** — the `feedback_figures_over_tables_over_words` caption discipline, applied to the report body: name the figure, quote the key number, say what it means.
6. **The stranger test.** Each sentence must stand alone and be correct + clear to a stranger. If a sentence needs the reader to already know an internal term, rewrite it.
7. **A valid round outcome is "stop → improve the model."** A round can conclude that the *parameter* approach is exhausted and the next step is a model-code change — state that plainly with its evidence, not just "the next round changes X".

## The report (markdown → PDF)

> **This is the STANDARDIZED summary, not the round report.** The two are different documents and both exist at round close. This one has a **fixed structure** and answers *"what does the whole round's ensemble look like"*: figures, tables, rankings. The **round report** is `write-report`'s, narrates the **arc across the cycle reports**, and carries the next-round work plan. It **cites** the figures produced here rather than regenerating them. Writing only this one leaves the PI without the arc; writing only the other leaves it without the round-wide numbers.

Write `R{N}_summary_<date>.md` (a git-tracked home such as `reports/R{N}_summary_{date}/` keeps the report + its figures together), then render with the **`markdown-to-pdf`** skill. Structure (apply the writing standard above throughout):
0. **Executive summary** — 3–5 plain sentences (see standard #1).
1. **Header** — round N, protocol (suppl-N/P, prescribed vs coupled, FATES build), ensemble size + completion % (+ what the incomplete cases are: infra vs deterministic model failures, each explained).
2. **Evaluation** — best case # + composite NRMSE; per-target table (best-case sim vs obs, with ±20% and ±1 SD); # of 6 targets met; embed the combined + TRANS figures.
3. **Sensitivity** — top-N parameters per scored target (table) plus the per-round sensitivity figure, **always present** whatever the estimator; name the rung of guarantee 3's ladder and its limits (trajectory or sample count, convergence diagnostics, provisional flags), and add the **viability** dimension where deaths are non-trivial.
4. **Mechanism** — guarantee 8. What the round established about the system, each as finding then mechanism then evidence, every number carrying a `file:line`, an artifact path or a named log. Sourced from the round's diagnoses and its offline state file, not re-derived. This is what `write-report` builds the round report's mechanism section from; a mechanism that is a relation between two parameters, or that turns on a variable neither sampled nor scored, has no row in either required table and reaches the reader only through this item.
5. **Caveats + next steps** — bounds at edges, model-failure modes, what a next round should change.

## Footguns (shared with compare-calibration-rounds)

- Screening evaluation: **cap with `--max-case-num`** to drop foreign experiment cases; per-round **graphs stay uncapped** for the round's own reruns.
- **Where Morris was run:** the CSV `rank` column is by `mu`; rank by **`mu_star`** for importance. And the sensitivity file prefix is always `morris_leafbiomass_*`, so the organ is set by the **directory**, never by the filename. Both are Morris-file specifics and do not apply to a round that ran a different screen or none.
- Use `_results.txt` + JSON, not the (partial-ensemble-buggy) `screening_top50_indices.txt`.
- Extraction conventions are **MODEL-SPECIFIC, and naming only the FATES pair here was the same defect corrected in `phase6-refinement` on 2026-08-22**: a convention bound to one model's tooling silently does not apply on another, and nothing notices. **ELM / ELM-FATES:** `extract_monthly_variables_FATES.py` (production, `_exp`-gated) vs `extract_and_plot_selected_cases.py` (any phase/suffix via CLI) — see `offline-testing-workflow`. **A non-CIME adapter model:** its own run skill, e.g. `ecosim-run-workflow`, which owns its tape layout, reducers and calendar. Score through the **target's own `reduce` and `tape`** either way, never a reimplementation.
- NERSC: scratch under `$HOME`/repo `tmp/` only.

## Cross-references

- **`plotting`** — every figure this skill produces goes through it: fonts, units, semantic colours, the A2MC ensemble template, and the load-bearing check (open the rendered PNG and look at it). Load it before the first `savefig`.
- **The round-close sequence this skill sits inside**, in order: `phase6-refinement` records the convergence gate and **pauses for the human**; `calibration-discipline` items 9 to 12 are the per-round definition of done (round summary WITH a next-round plan, then curation and script promotion, both after the gate clears); `write-report` owns the **ROUND report** that cites this skill's figures; `curate-knowledge` and `inject-knowledge` are the human-gated KB writes; `phase0-design` opens round N+1 once the PI records `redesign_6to0`. `calibration-goal` is the driver that dispatches the whole sequence.
- **Where this skill's inputs come from**: `phase1-exploration` (the Morris sensitivity this summarizes), `phase2-screening` (the evaluation), `phase0-design` (the ensemble itself), and `calibration-log` for the phase logs the cycle reports rest on.
- **Model-specific extraction**, per the footgun above: `offline-testing-workflow` (ELM / ELM-FATES, CIME) or the adapter model's own run skill, e.g. `ecosim-run-workflow`.
- Adjacent deliverables: `compare-calibration-rounds` (cross-round, the multi-round analog), `markdown-to-pdf` (rendering).
- Tools: `tools/plot_ensemble_cases.py`, `phases/phase2_screening/screen_ensemble.py`, `phases/phase1_exploration/morris_sensitivity_analysis.py`, `tools/regen_ensemble_milestone_plot.sh`.

## Changelog

- 2026-09-09: **Says where this skill's round-wide figures keep their script.** They belong to no phase stem, so the script lives with the report it serves; the canonical-script rule applies to a phase's figure scripts, and a CITED cycle figure is fixed in its own stem. PI correction.

- 2026-09-05 (later): **TRIGGER CHANGE — `description` rewritten.** It advertised only the figure, the evaluation and the sensitivity screen, so guarantee 8 existed in the file and nothing routed to it: a person asking *"what did this round establish"* or *"what did we learn this round"* fired no skill. The description now names the MECHANISM INVENTORY as a deliverable, states that this is a required step before the ROUND report, and adds those two phrasings as triggers. **When this skill fires has therefore changed deliberately.** Same pass corrected a 12-day drift on all four registry surfaces: `.claude/skills/README.md`, `AGENTS.md`, the catalog and the root `CLAUDE.md` all still marked this skill **FATES** although it went `requires_fates: false` on 2026-08-24, so the docs told an adapter-model user it did not apply to them. `check_skill_registry.py` passes on names and counts and does not read the modes column, which is why the drift survived.

- 2026-09-05: **GUARANTEE 8, the MECHANISM INVENTORY: what the round established about the SYSTEM.** PI-directed, from an audit asking whether this skill had the same failure shape as `write-report`. It did, and worse after that skill's fix: `write-report` now REQUIRES a mechanism section in the round report and explicitly does not derive it, exactly as with the two tables, so the requirement had **no producer upstream**. Every guarantee here was a structure — a figure, an evaluation, a ranking, two tables, a model-evolution record, a PDF — and none asked what the round had learned about the system. Guarantee 8 names the deliverable, distinguishes it from guarantee 4 (the arc, which is process) and from Table B (a parameter's role, one cell), and names the sources in order, the machine-readable one first: `workflow_state_offline_r{NN}.json`'s `evidence[].one_line` and `decisions[]`, written when each finding was fresh. Report structure gains item 4, Mechanism, and Caveats renumbers to 5. Signal: one round report described a two-solute trade-off correctly in four places and never named the pH dependence causing it; every number was in that round's first Phase-3 diagnosis and its state file. **Reconciled in the same pass (step 5):** the one-line summary at the top and the "standardized, FIXED deliverable" paragraph both enumerated the old three and the second said the skill does not narrate what the cycles learned — true of the ARC and false of the MECHANISM, so it now draws that distinction explicitly rather than reading as a licence to omit; and the "Three deliverables" section is marked as the TOOL-produced artifacts, since guarantee 8 is written rather than computed. `description` untouched; no trigger change.

- 2026-08-26: **The two-step source order is now optional, and this file says so.** v2.306 gave every shipped site config a guard that auto-sources its own machine config (`a2mc_config.sh` for CIME/ELM-FATES, `a2mc_noncime_config.sh` for the adapter models) when one is not already loaded, and REPAIRS the wrong one if it was sourced by mistake. Nothing here was wrong -- the explicit machine-then-site order still works and still takes precedence -- so the instruction is shortened and the old form kept as a stated no-op. Asserted by `tests/test_site_config_autosource.py`. PI-directed. The setup block drops its pick-by-run-style machine-config line.

- 2026-08-24 (later, 4): **A sensitivity figure and discussion are now UNCONDITIONAL.** PI-directed, correcting guarantee 3 as I had written it that morning: it allowed "an explicit statement that the round produced none and why", which is an escape hatch and was taken. One round's Saltelli estimator did not converge, the round summary shipped with no sensitivity figure, and the same ensemble turned out to contain 2,374 already-run controlled single-parameter experiments across all 28 parameters, recoverable at zero compute, plus quintile survival responses and a measurable per-parameter lethality. The estimator failing is a reason to change instrument. Guarantee 3 now carries a four-rung fallback ladder (design estimator, controlled pairs from the design, regression or rank correlation, per-parameter quintile response) with the rung to be named in the discussion, the pairs rung carrying the sign-consistency caveat, and a requirement to treat **viability** as its own sensitivity dimension where deaths are non-trivial. The backend table and the report-structure item were reconciled in the same pass, and `write-report` now requires the round report to carry both.
- 2026-08-24 (later, 3): **Two guarantees added and the file reflowed.** PI-directed. The guarantee list ended at the figures, the evaluation and the screen, and never said the skill **synthesizes the round's cycle reports** — which is the work that turns a pile of per-cycle artifacts into a round, and which the nesting diagram directly above it already implied. New item 4 states it, reads the CYCLE REPORTS rather than the raw logs, and notes that a cycle with no report is a gap to fix rather than a cycle to skip. New item 5 moves the **two required tables** here as something this skill PRODUCES, with `write-report` requiring rather than deriving them and `compare-calibration-rounds` filling Table B's cross-round status at step 2. The direction is now stated explicitly in both skills, because it is easy to invert: cycle reports feed this skill, this skill feeds `write-report`, and `write-report` writes the ROUND report narrative. Same pass: the two Morris-file footguns are now scoped "where Morris was run", and the file is **reflowed to one paragraph per line** per the house no-hard-wrap rule (131 lines in the 90-110 column band down to 16, all remaining ones code blocks or table rows), using a purpose-written reflow with a content-preservation assertion that fired once on blockquote markers before passing.
- 2026-08-24 (later): **Carries the canonical report-nesting diagram verbatim from `write-report`**, replacing the abbreviated copy that had lost its annotations: which artifact is the evidence layer, that a cycle report synthesizes EVERY log and EVERY `phase_results/` folder of its cycle, and that a round report synthesizes the CYCLE REPORTS and not the raw logs again. Two skills describing one contract in two shapes is how they drift, and the abbreviated version had already dropped the "not the raw logs again" rule that is the whole point. PI-directed. Same pass fixed a leftover FATES-ism the genericization missed: the fixed deliverable now names "the round's own sensitivity ranking" rather than "the Morris sensitivity ranking".
- 2026-08-24: **Made GENERIC (`requires_fates: true` -> `false`), and stated as step 1 of a three-step round close.** PI-directed. The skill was the *standardized* round-close deliverable and was FATES-only, so on the branch whose purpose is generalizing A2MC past ELM **no adapter model had one**: EcoSIM, PFLOTRAN and ATS rounds closed with hand-rolled figures and no standardized evaluation. The fix splits the **contract** (whole-ensemble figure covering every scored target with observations drawn as measured, an evaluation, the round's own screen or an explicit statement that there was none, a PDF-renderable report) from the **backend** (per model, resolved via `describe_mode`, table in the new "Resolve the BACKEND first" section). The footguns are kept and re-framed: most describe mechanisms every model has, and the two that are genuinely Morris-file-specific are marked. Also adds the three-step ordering diagram — this skill, then `compare-calibration-rounds`, then the ROUND report — because the middle step was skippable and skipping it let a round summary re-propose two already-refuted parameters. **`description` and `modes` both touched**, so when this skill fires has changed deliberately: it now applies to any model, not only FATES.



- 2026-08-22: **Says what this skill is NOT, and what the round report needs from the cycle reports.** PI-directed. Three gaps. (1) The skill described three deliverables and never said where they GO: the round report is `write-report`'s, it synthesizes the CYCLE reports rather than the raw logs, and this skill supplies the round-wide figures it cites. Added the layer diagram and a per-cycle extraction table, plus the five things no single cycle report can say (the arc of corrections, where the binding target moved, what is out of reach WITHIN the round's own bounds, KB and failed-approach candidates, and the cost in cycles against questions settled free). (2) The extraction footgun named only the FATES pair, which is **the same model-bound defect corrected in `phase6-refinement` the same day**: a convention tied to one model's tooling silently does not apply on another. Now routed per model family. (3) Cross-references named four skills and missed the entire round-close sequence (`phase6-refinement`, `calibration-discipline` items 9-12, `write-report`, `curate-knowledge`, `inject-knowledge`, `phase0-design`, `calibration-goal`) and every input phase (`phase1-exploration`, `phase2-screening`, `calibration-log`); a "Worked references" line was also left garbled by an earlier scrub and is removed rather than left as a dead pointer. Details: `memory/dev_logs_adapterkit/20260822r_*`.

- 2026-08-16: **Names the `plotting` skill.** `plotting` listed this skill as one that applies its conventions while this one never mentioned it — a one-directional link. The reciprocal pointer is now required in both directions. PI-directed.
- 2026-07-06: Added the **Report writing standard** (report is for a human with no project context: executive summary, define-or-avoid jargon, complete plain-finding→mechanism→evidence sentences, the stranger test, "stop→improve-model" as a valid outcome) + a git-tracked report-location note. Ported from demo (`d788bd1`/`2cb3056`/`3519a61`), scrubbed of Kougarok run-specific codenames. See memory `feedback_report_writing_self_contained`.
- 2026-06-17: `## Changelog` convention adopted (see .claude/skills/README.md). Earlier history: git log + memory/dev_logs/.