---
name: phase2-screening
visibility: public
category: phase
description: Run Phase 2 (SCREENING) of the A2MC calibration workflow as the offline agent — the human-in-the-loop analog of the orchestrator's `_run_screening()` / `reasoning.analyze_screening_results()`. Rank the ensemble against the validation targets (RMSRE, targets-satisfied), find the best / lowest-cost / most-targets cases, read the error/bias patterns, and route the round into Phase 3 diagnosis. Use when the user says "screen the ensemble", "rank against targets", "which case is best", "run Phase 2", "how many targets are met", after Phase 1 sensitivity.
modes:
  requires_fates: false      # calibration-workflow phase skill; mode resolved at runtime via describe_mode
  nutrient_pathway: any
  scope: [calibration]
  summary: "Offline analog of Phase 2 (rank ensemble vs validation targets). Applies in every calibration mode."
---

# Phase 2: Screening (offline agent)

> **Driven by `calibration-goal`** — the run-to-convergence driver dispatches here when `WorkflowStateOffline.current_phase` routes to this phase; do the phase, then update + `save()` the state so the driver advances. Also runnable standalone (one phase).

The offline analog of `_run_screening()`. Online, `reasoning.analyze_screening_results()` reads the
ranked ensemble automatically; **offline, YOU read it** — identify best / lowest-cost / most-targets
cases, the per-target bias (over/under-estimate), edge parameters in the top cases, and PFT
trade-offs, then set up what Phase 3 must explain.

> **Floor, not ceiling.** Ranking + best-case is the online floor. As the offline agent, go further:
> inspect the whole cost distribution (not just top-N), test whether a "best" case is real or a
> contamination artifact before trusting it, look for equifinality (different parameter sets, same
> cost), or compare this round's frontier against a prior round. Produce the online ranking, then
> interrogate it.

**Inputs (from Phase 1):** extracted per-case data + Morris rankings. **Deliverable:** ranked cases
(RMSRE + targets satisfied), the best/lowest-cost/most-targets cases, error-pattern read, + the
whole-ensemble biomass-vs-targets time-series comparison figure → routed to `phase3-diagnosis`.

> **Before designing or interpreting anything here, hold the MECHANISM NETWORK, not one or two parameters.** At calibration stage the model KB is assumed well-built, so it is where you START and it usually hands you the citation -- it does NOT replace verifying in source: query ALL FIVE surfaces (codebase wiki, RAG index, **knowledge graph**, MODEL-level and SITE-level `gained_knowledge/`) plus the case's own parameter list, pull `parameter -> controls -> mechanism -> affects -> output` for the **scored** variables and the `depends_on` couplings among anything you intend to move together, and only then confirm in source. Needing source to LEARN rather than to CONFIRM means a KB gap, which is a build task. [[feedback_full_mechanism_picture_before_designing_an_experiment]]

## Step 1 — rank the ensemble (reads existing extracted outputs — no new simulations)

`phases/phase2_screening/screen_ensemble.py --data-dir $A2MC_EXTRACTED_DATA --top-n 100`. Per-target
relative error → composite RMSRE via `tools/optimize_function.py` / `tools/cost_functions.py`
(shared `tools/evaluate_case.py`); counts targets within tolerance (default ±20%). Outputs ranked
indices, composite cost, per-target errors, `n_satisfied`.

> **Footgun — `--max-case-num` contamination guard.** When experiment cases (e.g. `_exp` / #5001+)
> share the extract dir with the Morris ensemble, pass `--max-case-num 4890` so screening ranks
> only the ensemble. Without it, foreign cases inflate the top-N. (Same guard the
> `compare-calibration-rounds` cap enforces.)

> **Footgun — index vs case number.** Screening `Set_ID`/indices can be *position+1*, not the real
> case number. Use the JSON `best_case_num` + the `_results.txt` `Sim_` columns, not the indices
> file, before quoting a "best case" (see `diagnose-forensics`).

## Step 1b — plot the whole-ensemble biomass-vs-targets comparison (REQUIRED, esp. TIME SERIES)

Ranking gives the *numbers*; the screening read also needs the **visual** — where every case's biomass
trajectory sits relative to the target bands. Produce it with **`tools/plot_ensemble_cases.py`** (the
generic whole-ensemble plotter and the **reference implementation of the A2MC ensemble figure template** —
the fixed purple-cloud / red-best / blue-most-targets / obs-diamond / ±20%-band color scheme is codified in
the `plotting` skill; source the round config first, [[reference_ensemble_combined_plot_pipeline]]):

- **`--combined`** — the 519-yr ADSP+RGSP+TRANS axis: the full spin-up→transient trajectory of every
  case (purple cloud) with best-NRMSE (red) + most-targets (blue) highlighted and the observation
  bands. Reveals late collapse / overshoot-then-crash / non-equilibration that an endpoint RMSRE hides.
- default (TRANS-only) — the calibration-window view for the target comparison.
- `--top-n N` highlights the best N; **`--pft-ids`** (pass the mode's calibrated PFTs — api-43 arctic =
  **10/11/12**, not the api-31 7/9/10, [[feedback_verify_pft_identity_across_versions]]), `--round-label`,
  `--output-dir` per the round.

Both this and the phase-2-local near-duplicate `phases/phase2_screening/plot_screening.py`
(`plot_ensemble_biomass()`) read `FATES_LEAFC_SZPF` + `FATES_FROOTC_SZPF`, summed over each PFT's size
classes via `tools/fates_utils.get_szpf_range` (×1000 kg→g C/m²), overlaying obs ±20%. **For a one-off
custom case outside the case-number/`…PrescP` pattern** (e.g. a ported base like `p2939uni`), the ensemble
plotter's case-number discovery doesn't apply — read the SZPF directly with the same variables/ranges
(worked example: the base-viability screen
`use_cases/ELM-FATES_Kougarok/memory/logs/20260715a_phase2_screening_r01_api43_p2939uni_base_viability_*`).

Output: `R{N}_{combined,TRANS}_{count}cases_ensemble.png`. **Standard deliverable, not optional QA** — a
single-month RMSRE hides the trajectory, and the visual is how PFT collapse / competitive-exclusion
patterns first show up before Phase 3 names them. Packaged version (graphs + eval + μ*) →
`summarize-calibration-round`; cross-round frontier overlays → `compare-calibration-rounds`. Every figure
gets a caption + plain-finding line in the log ([[feedback_figures_over_tables_over_words]]).

> **Adapter parallel (non-FATES):** the whole-ensemble trajectory-vs-target plot is
> `scripts/extract_and_plot_adapter_ensemble.py` (instead of `plot_ensemble_cases.py`, which is SZPF/
> ADSP-RGSP-TRANS-specific). It overlays every case's annual-peak pool trajectory on a log axis —
> **highlighting cases that ESTABLISH** (>= `--establish-frac` × `--target-value` in the window) + an
> optional reference tape + the target line — and writes the per-case CSV/npz. The ranking itself
> (Step 1) already dispatches through the backend: `screen_ensemble`'s backend branch discovers
> completed run subdirs and extracts via `backend.extract_history_variables` + `model_evaluate_case.reduce_target`
> (masking model spval → NaN), so `--data-dir $A2MC_OUTPUT_DIR` on an adapter model just works. EcoSIM R1 (`20260716a`).
>
> **PFLOTRAN: Step 1 dispatches, Step 1b does not.** `screen_ensemble.py`'s backend branch keys on
> `$A2MC_MODEL` (`:333-342`), so the RANKING covers any registered adapter. The Step-1b FIGURE does
> not: both `plot_ensemble_cases.py` (SZPF + ADSP/RGSP/TRANS) and
> `extract_and_plot_adapter_ensemble.py` (per-PFT carbon pools, establishment) assume a vegetation
> model. For miniLEO the equivalent whole-ensemble view is every case's **outflow concentration and
> hydrograph over the scored window**, against the observation bands — written into
> `phase_results/{stem}/` from the case's own template in `use_cases/PFLOTRAN_miniLEO/scripts/`
> (`compare_outflow_chemistry.py` is the per-species table; the ensemble overlay is a new script on
> its first use). **Do not skip the figure because no tool exists** — `phase6-refinement` Step 1b
> states the same rule, and the requirement is the figure, not the driver.

> **The top-N view is a `--cases` FILTER on this figure, never a second script.** The whole-ensemble
> view and the leaders view are one figure over different case sets, so `--top-n 100` selects cases and
> the same script draws them. Found the hard way: `compare_biomass_topcases.py` is FATES-only and has no
> adapter counterpart, and the reflex was to write one instead of adding a case filter to the template
> that already draws this figure. The template is shared with `phase3-diagnosis` and `phase6-refinement`
> Step 1b, which is why a fourth copy is exactly what §"Scripts: start from the case TEMPLATE" prevents.

## Step 2 — read the patterns (you are the reasoning)

Mirror `analyze_screening_results`: **pft_performance** (cases within uncertainty, quality),
**target_bias** (UNDEREST/OVEREST + consistency), **edge_parameters** (top cases pinned at bounds),
**pft_tradeoffs** (shared-parameter conflicts), **priority_targets** for diagnosis. Complementary top-N
panel: `phases/phase2_screening/compare_biomass_topcases.py --top-n 50` (top-N biomass vs targets; a
focused zoom on the leaders that complements the Step-1b whole-ensemble figure).

## Step 3 — log and route

> **The log is a LIVING record — start it now, enrich as the phase runs.** Not an end-of-phase
> write-up: the operational detail (job/array IDs, which cases failed, what was restarted) is
> unrecoverable a week later. Full contract in `calibration-log`.
>
> **This phase's expected sections** — `PhaseLogger` names any you leave empty:
> Ranking · Ensemble vs Targets Plot · Best Cases · Patterns.
>
> **Set the handshake before the `log_*` call**, so the chain is traceable:
> ```python
> logger.set_phase_handshake(
>     inherited_from="<predecessor log STEM> — what it concluded / asked of this phase",
>     handed_to="<what Phase 3 receives; mirror the reasoning/schemas.py field names>",
>     next_action="<the one concrete thing Phase 3 should do>")
> ```
> The log also carries `## Reasoning chain`, rebuilt from `workflow_state_offline` — so keep that
> state updated with the FINDING, not a label; the chain is only as good as what each phase wrote.


Log via `calibration-log` (phase log → `PhaseLogger.log_screening`): best/lowest-cost/most-targets
cases, targets met, bias patterns, priority targets. **Route** to `phase3-diagnosis` with the
priority targets + candidate base cases. **Advance the driver state:**
`st.set_position(current_phase="diagnosis")`; `st.save()` (`tools/workflow_state_offline.py`).

## Scripts: start from the case TEMPLATE, adapt it HERE

**Every script this phase writes follows the three-tier rule** (`calibration-discipline` item 2b):

```
use_cases/{Model}_{Case}/scripts/     the canonical script TEMPLATE   (seeded at onboarding)
        │  copy into this phase's folder, then ADAPT for this phase's purpose
        ▼
memory/phase_results/{stem}/          the canonical SCRIPT for this figure, beside its
                                      caption, data and notes -- this is the log's evidence
```

1. **Look in `use_cases/{Model}_{Case}/scripts/` first.** If a template covers what this phase needs, copy it into this phase's `phase_results/{stem}/` and adapt it there. Do not run it from `scripts/` and do not edit the template to suit one phase: the template is the shared shape, the copy is this phase's instrument.
2. **If there is NO template, write one from scratch** in `phase_results/{stem}/`. That is the correct first-use state and nothing is wrong with it.
3. **On a script's SECOND use, promote it to `scripts/` as the template**, then copy it back into the new phase's folder and adapt. Second use is the trigger, not third.

**This does not conflict with "one canonical script per figure, never two copies."** The canonical *script* always stays with its figures; the canonical script *TEMPLATE* stays in `scripts/`. Different artifacts, different jobs.

**Why it is a rule and not a preference:** measured on one site, `phase_results/` held **7 script names duplicated across stem folders, all 7 byte-identical** -- each a Phase-5 script copied verbatim into its Phase-6 folder, because there was nowhere for a reusable script to live. `tools/check_case_script_tier.py` (pre-commit 15, WARN) flags the next one.

## Related skills / next phase

- **ANY figure this phase produces** → **`plotting`**. Load it BEFORE the first `savefig`,
  not after: its load-bearing rule is to **open the rendered PNG and look at it**, and an
  overlapping legend, a stats box on the data or an unreadable font are invisible in the code
  and obvious in the picture. Also fixes fonts/units/semantic colours, and the A2MC ensemble
  figure template for biomass-vs-target time series.
- **Canned single-round report (graphs + eval + μ*)** → `summarize-calibration-round`.
  **Cross-round frontier** → `compare-calibration-rounds`. This skill produces the core ensemble
  comparison figure itself (Step 1b) and *decides + routes*; those two package it into a standardized
  report / render the cross-round overlays.
- **A "best" case looks too good** → `diagnose-forensics` (triage before trusting).
- **Next:** `phase3-diagnosis`.

## Before you finish

**Discipline self-review (automatic).** Before advancing the state, re-check the [`calibration-discipline`](../calibration-discipline/SKILL.md) items that apply to this phase. This is unprompted and per-phase — the user does not have to ask (memory `feedback_schedule_periodic_reviews_with_a_real_mechanism`).

