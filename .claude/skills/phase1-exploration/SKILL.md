---
name: phase1-exploration
visibility: public
category: phase
description: Run Phase 1 (EXPLORATION) of the A2MC calibration workflow as the offline agent — the human-in-the-loop analog of the orchestrator's `_run_exploration()` / `reasoning.analyze_sensitivity_results()`. Extract the Y matrix from completed simulations, run Morris sensitivity analysis, and interpret μ* to decide what parameters matter for each target/PFT. Use when the user says "run the sensitivity analysis", "extract the Y matrix", "which parameters matter", "run Phase 1", "Morris rankings", after the Phase 0 ensemble finishes.
modes:
  requires_fates: false      # calibration-workflow phase skill; mode resolved at runtime via describe_mode
  nutrient_pathway: any
  scope: [calibration]
  summary: "Offline analog of Phase 1 (extract Y matrix, Morris sensitivity). Applies in every calibration mode."
---

# Phase 1: Exploration (offline agent)

> **Driven by `calibration-goal`** — the run-to-convergence driver dispatches here when `WorkflowStateOffline.current_phase` routes to this phase; do the phase, then update + `save()` the state so the driver advances. Also runnable standalone (one phase).

The offline analog of `_run_exploration()`. Online, `reasoning.analyze_sensitivity_results()`
interprets the Morris output automatically; **offline, YOU interpret it** — attribute each ranked
parameter to a FATES mechanism, spot cross-PFT vs PFT-specific importance, and decide what's worth
tuning. The extraction + Morris scripts are the same the online agent uses.

> **Floor, not ceiling.** Morris μ* is the online agent's one lens. As the offline agent, reach for
> more when the round warrants it: check σ/μ* for interaction-heavy parameters, look for edge
> effects (params pinned near bounds → a Phase 0 redesign signal), compute a second output variable
> the loop didn't rank, or run a targeted correlation `scientific-analysis` the fixed pipeline has
> no step for. Produce the ranking the online agent would, then go past it.

**Inputs (from Phase 0):** completed TRANS outputs, the X matrix (`$A2MC_ENSEMBLE_MATRIX_FILE`), the
SALib problem (`$A2MC_SALIB_PROBLEM_FILE`). **Deliverable:** Morris rankings (μ, μ*, σ per parameter
per PFT) as CSV + plots, plus your interpretation of what to tune (captured in the phase log), handed to Phase 2.

## Step 0 — completion gate

`tools/diagnose_ensemble_status.py --cases 1-N` — proceed when >95% of cases have TRANS complete.
Failed cases become NaN rows downstream.

> **Before designing or interpreting anything here, hold the MECHANISM NETWORK, not one or two parameters.** At calibration stage the model KB is assumed well-built, so it is where you START and it usually hands you the citation -- it does NOT replace verifying in source: query ALL FIVE surfaces (codebase wiki, RAG index, **knowledge graph**, MODEL-level and SITE-level `gained_knowledge/`) plus the case's own parameter list, pull `parameter -> controls -> mechanism -> affects -> output` for the **scored** variables and the `depends_on` couplings among anything you intend to move together, and only then confirm in source. Needing source to LEARN rather than to CONFIRM means a KB gap, which is a build task. [[feedback_full_mechanism_picture_before_designing_an_experiment]]

> **AND AN OUTPUT VARIABLE IS VERIFIED LIKE A PARAMETER.** The rule above is written about parameters and mechanisms; a tape field is a third category and the same failure arrives one category over. Before reducing one, establish that it is ACTIVE (a field registered `default='inactive'` is not written unless a run names it, and the model's `docs/<model>-knowledge-base/<model>_output_info_<commit>.cdl` carries a source-derived `:status`) and what its TEMPORAL SEMANTICS are -- rate, per-record increment, within-year cumulative that RESETS, run-cumulative, or stock. One reduction does not fit all five and the units do not separate them. Full rule and the measured cost: `calibration-discipline` item 3c.

## Step 1 — extract the Y matrix (reads existing outputs — no new simulations)

`phases/phase1_exploration/extract_sensitivity_outputs.py --output-var leaf_biomass --cases 1-N
--validation-period 2010 2019` → `Morris{Var}_{N}cases.txt` (cases × PFTs). Runs on the login node;
large ensembles can be memory-heavy — extract in `--cases` ranges, and use `--resume` to continue an
interrupted run.

> **Adapter parallel (non-FATES):** `scripts/extract_and_plot_adapter_ensemble.py` — the backend analog
> of `extract_sensitivity_outputs.py` (NO SZPF). For every completed case it extracts a per-PFT
> carbon-pool series via `backend.extract_history_variables`, reduces it to an annual-PEAK **trajectory**,
> and writes a per-case CSV (final-year, target-window mean, `established` flag) + an `.npz` of all
> trajectories. Runs on a PARTIAL ensemble (a tape = a completed case). The per-case target Y-values for
> Morris come from the same backend extraction (`backend.reduce_ecosystem`), one column per target; feed
> that Y-matrix + `$A2MC_SALIB_PROBLEM_FILE` to the SAME `morris_sensitivity_analysis.py` in Step 2.

> **PFLOTRAN: the adapter parallel above does NOT carry it, and that matters here more than anywhere.**
> `extract_and_plot_adapter_ensemble.py` extracts a **per-PFT carbon-pool** series, reduces it to an
> annual PEAK, and highlights cases that **establish**. miniLEO is abiotic — no PFTs, no carbon pools,
> nothing establishes — so every one of those reductions is meaningless for it. Extract instead from
> the `*-mas.dat` mass-balance tape through `backend.extract_history_variables`, and take the Y-value
> for each target from **`tools/pflotran_evaluate_case.py`**, which applies that target's own `reduce`
> (`outflow_concentration` is a RATIO of two columns; `outflow_flux` is a full-series NRMSE). Feed
> that Y matrix + `$A2MC_SALIB_PROBLEM_FILE` to the SAME `morris_sensitivity_analysis.py` in Step 2 —
> the sensitivity machinery is genuinely generic; only the extraction is not.
>
> **And Step 3's interpretation is not FATES-shaped for this model.** "Attribute each parameter to a
> FATES mechanism" and "cross-PFT patterns" have no analog. The equivalents are: attribute each
> parameter to a REACTION or a FLOW mechanism (verify in the commit-pinned PFLOTRAN wiki or the
> source, never from the card name), and look for cross-TARGET rather than cross-PFT patterns — a
> parameter that moves the hydrograph and the chemistry together is the interesting case, because
> permeability reaches chemistry through residence time (measured 2026-08-27: `PERM_ISO` alone moved
> Mn 0.607 -> 1.007 and Al 0.650 -> 0.359).

> **Footgun — row-order alignment.** The X-matrix row order MUST match the Y-matrix row order (same
> cases, same order) or SALib Morris is meaningless. If you filter failed cases, filter both sides
> with `completed_cases_<TS>.txt`. Audit for NaN rows — >5% NaN, investigate failures first.

## Step 2 — run Morris (analysis of the extracted matrices — no new simulations)

`phases/phase1_exploration/morris_sensitivity_analysis.py --output-var leaf_biomass --y-matrix <Y>
--x-matrix <X> --problem <salib_problem>` → per-PFT `morris_*.csv` (parameter, μ, μ*, σ, rank) +
color-coded `*.png`. `analyze_ensemble.py` is the higher-level driver that chains extract → Morris.

> **The per-PFT μ* ranking plot is a REQUIRED deliverable, not a byproduct** — include it in the phase
> log with a caption naming the top parameters ([[feedback_figures_over_tables_over_words]]). For the
> cross-target μ* overlay (one panel per validation target) use `summarize-calibration-round`; for a
> per-target μ* comparison across rounds use `compare-calibration-rounds`.

## Step 3 — interpret (you are the reasoning)

Produce the same shape as the online `analyze_sensitivity_results` output: **key_parameters**
(each attributed to a FATES mechanism — verify against RAG, never from the name), **interactions**
(high σ/μ*), **cross_pft_patterns** (generic-to-all vs PFT-specific), **edge_effects** (near-bound →
redesign candidates), and a **calibration strategy** (tune order, PFT-by-PFT vs global).

## Step 4 — log and hand off

> **The log is a LIVING record — start it now, enrich as the phase runs.** Not an end-of-phase
> write-up: the operational detail (job/array IDs, which cases failed, what was restarted) is
> unrecoverable a week later. Full contract in `calibration-log`.
>
> **This phase's expected sections** — `PhaseLogger` names any you leave empty:
> Extraction Status · Y Matrix · Morris Results · Interpretation.
>
> **Set the handshake before the `log_*` call**, so the chain is traceable:
> ```python
> logger.set_phase_handshake(
>     inherited_from="<predecessor log STEM> — what it concluded / asked of this phase",
>     handed_to="<what Phase 2 receives; mirror the reasoning/schemas.py field names>",
>     next_action="<the one concrete thing Phase 2 should do>")
> ```
> The log also carries `## Reasoning chain`, rebuilt from `workflow_state_offline` — so keep that
> state updated with the FINDING, not a label; the chain is only as good as what each phase wrote.


Log via `calibration-log` (phase log → `PhaseLogger.log_exploration`): top parameters per PFT, the
mechanism attributions, edge effects, and the tuning recommendation. **Hand off** to
`phase2-screening`. **Advance the driver state:** `st.set_position(current_phase="screening")`;
`st.save()` (`tools/workflow_state_offline.py`).

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

- **The Y matrix this phase extracts is what a surrogate TRAINS on** → **`build-surrogate`**,
  when the round is finished and the question is whether the ensemble can support a learned
  emulator or a ranking accelerator. It names this skill back.
- **ANY figure this phase produces** → **`plotting`**. Load it BEFORE the first `savefig`,
  not after: its load-bearing rule is to **open the rendered PNG and look at it**, and an
  overlapping legend, a stats box on the data or an unreadable font are invisible in the code
  and obvious in the picture. Also fixes fonts/units/semantic colours, and the A2MC ensemble
  figure template for biomass-vs-target time series.
- **Standardized single-round / cross-round figures** → `summarize-calibration-round`,
  `compare-calibration-rounds` (they invoke the same Morris pipeline).
- **A one-off sensitivity question with a figure + ana_log** → `scientific-analysis`.
- **Next:** `phase2-screening` (rank the ensemble against targets).

## Before you finish

**Discipline self-review (automatic).** Before advancing the state, re-check the [`calibration-discipline`](../calibration-discipline/SKILL.md) items that apply to this phase. This is unprompted and per-phase — the user does not have to ask (memory `feedback_schedule_periodic_reviews_with_a_real_mechanism`).

