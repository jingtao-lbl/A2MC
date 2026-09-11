---
name: calibration-discipline
visibility: public
category: calibration
description: The per-cycle and per-round DISCIPLINE checklist that keeps a long offline calibration campaign stable — the "definition of done" for each experiment cycle and each round. Use at the start of a multi-cycle offline calibration, and re-check every cycle, to guarantee the stable behaviors happen every cycle, e.g. log each phase with the right skill into log/{stem}.md + a self-documenting phase_results/{stem}/, arm monitors right after every testing-simulation launch (arm-hpc-monitoring for scheduler runs; watch the process + log for local runs), keep the figure script canonical in phase_results (never dev-in-scratch-and-copy), update + validate workflow_state after every phase, write a synthesis report at each cycle end, drive the loop to its limit pausing only at the human gates, and at round end write a round summary that INCLUDES the next-round work plan (param add/remove, bounds, base update). DISTINCT from calibration-goal (the driver LOOP mechanics) and from a single phaseN skill (one phase) — this is the HABITS layer the driver must honor so performance does not drift across cycles.
modes:
  requires_fates: false
  nutrient_pathway: any
  scope: [calibration]
  summary: "Per-cycle/per-round discipline checklist (definition-of-done) that keeps a long offline campaign stable. Model-agnostic; pairs with calibration-goal."
---

<!-- ─────────────────────────── At a glance ─────────────────────────── -->
```text
calibration-goal DRIVES the loop; calibration-discipline is the DEFINITION OF DONE it honors.
the loop = 7 phases (0 DESIGN→1 EXPLORATION→2 SCREENING→3 DIAGNOSIS→4 HYPOTHESIS→5 TESTING→6 REFINEMENT→7 CONVERGED),
nested in 3 iteration levels: ROUND (outer, Phase 0→7; redesign 6→0), experiment CYCLE (middle, 3→6),
skip-testing (inner, 3↔4 on existing data). This checklist runs per CYCLE and per ROUND (below).

THE LOOP LIMITS LIVE IN THE MACHINE CONFIG, which every site config now auto-sources (v2.306):
  source use_cases/{Model}_{Case}/config/<site>_config[_r<N>].sh   # chains round -> site -> machine
  -> A2MC_MAX_SKIP_TESTING (inner) · A2MC_MAX_EXPERIMENTS (middle) · A2MC_CONFIDENCE_THRESHOLD (skip-test exit)
Quote those variables, never a literal. A site or round config does NOT set them; it CHAINS to the one that does.

per experiment cycle (Phase 3→4→5→6):
  □ each phase logged with its phaseN skill + calibration-log → log/{stem}.md + phase_results/{stem}/
  □ every figure self-documenting IN phase_results/{stem}/ (figure + caption.md + its .py + data)
  □ that .py was COPIED FROM the case template in use_cases/{Model}_{Case}/scripts/ and ADAPTED here;
     a script's SECOND use is the trigger to template it (measured: 7 byte-identical duplicate pairs)
  □ analysis is FIRST-HAND this cycle (check_offline_log_evidence.py exit 0 for phase 3/4/6)
  □ every tape variable REDUCED per its own semantics (rate / increment / resetting-cumulative /
     run-cumulative / stock) and checked ACTIVE, never inferred from its name or units
  □ the INNER loop actually ran: before routing 4->5, is there another question EXISTING data can
     answer? keep asking while Phase 5 runs. (measured: 46 logs at iter01, 4 at iter02, cap is
     $A2MC_MAX_SKIP_TESTING)
  □ Phase 6 figure covers EVERY SCORED TARGET, observation drawn as MEASURED (gaps left as gaps)
  □ after ANY Phase-5 testing-simulation launch → arm monitoring on YOUR launches, react with proposals
     (scheduler/HPC run → arm-hpc-monitoring; local/foreground run → watch the process + its log)
  □ workflow_state_offline_r{RR}.json updated + validated after EVERY phase (check_..._offline.py exit 0)
  □ ...and COMMITTED + PUSHED at that same boundary — an unpushed commit lives on ONE node and is
     invisible to the PI (measured: 30 piled up in one session before the PI had to ask)
  □ FINDINGS recorded into the state AS THEY ARE ESTABLISHED, not saved up for Phase 6
     (`st.add_decision(finding, rationale=why)`) — `next_action` is the program COUNTER,
     the `decisions` list is the RECORD, and PhaseLogger rebuilds the reasoning chain from
     the latter. (It is the record of WHAT was established and WHERE; it is not where a claim
     is VERIFIED -- that is the artifact it points at. See "A CLAIM ABOUT WHAT THE ROUND HAS
     ESTABLISHED" below.) Same checker now WARNs when the case has moved with nothing written down.
     ↳ that validator now also WARNs when the state's current phase has no matching offline log
       (stem `_phase{N}_{name}_r{RR}`), so the 'each phase logged' box above is observable rather
       than remembered. WARN not ERROR on purpose: it fires legitimately mid-phase (the state is
       written when a phase STARTS, the log when it ends), and erroring would gate the loop on a
       bookkeeping artifact — which is how gates get bypassed.
  □ routing 6→3 → the RETHINK PROTOCOL is ANSWERED IN THE PHASE-6 LOG, not just the decision recorded
     (synthesize this cycle · re-read phase 1+2 against it · base still right? · binding target moved? ·
      lever CLASS exhausted vs untried · each refutation's DIRECTION + the base's MISS SIGN, still valid?
      → NEW PATHWAYS with falsifiers). Enforced: check C9
  □ cycle end → a synthesis report (write-report): empty-alt figs, no em dash, one canonical script/fig
     ENFORCED by check_cycle_reports.py (pre-commit 18, WARN) -- a closed cycle with no report is named
  □ no KB write / model-source edit before a verified test + human gate

per round (loop limit reached OR converged):
  □ IN ORDER: summarize-calibration-round -> compare-calibration-rounds -> write-report (ROUND report).
    The MIDDLE step is the one that gets skipped, and it is what carries the CROSS-ROUND PARAMETER
    LEDGER (what every prior round did with each parameter) into the plan. Skipping it re-proposes
    refuted levers -- measured, twice, in one round summary.
  □ ROUND SUMMARY report — and it MUST propose the next-round work plan
    (param list add/remove, bounds recenter, base update, residual→model-dev/extraction split),
    plus the TWO required tables (cycle ledger, parameter reference with cross-round status)
  □ curate the round's VERIFIED knowledge into the KB (human-gated): inject-knowledge (findings you
    originated) + curate-knowledge (the online agent's staged proposals) → gained_knowledge/*.json
  □ promote REUSABLE scripts to the shared library (promote_diagnostic_script.py): online generated/ via
    --script; offline phase_results/{stem}/ via --source <path> --dest tools|phase3_diagnosis
    → then GENERALIZE the promoted copy (strip hardcoded paths/stems/case IDs, parameterize — CLAUDE.md 5+8)
  □ MODEL EVOLUTION: if the model source changed since the previous round, the record goes in
    use_cases/{Model}_{Case}/memory/model_evolution/{stem}.md and only a COMPACT APPENDIX TABLE
    in the round report. Engineering provenance is not narrative. Source: the case's
    config/calibration_rounds.yaml `model_change_ledger`
  □ RECORD (do not auto-promote) what use_cases/{Model}_{Case}/scripts/ holds and what each was used for
  □ round_summary + the Phase-6 gate recorded in state; PAUSE for the PI at the gate
```

# calibration-discipline — keep a long offline campaign stable

**The failure mode this prevents is DRIFT.** A single offline calibration round is 10 experiment
cycles; a campaign is several rounds. The individual steps are all covered by other skills, but over a
long run it is easy to *skip one some cycle* — forget to arm a monitor after a launch, edit the scratch
copy of a plot script instead of the canonical one, not update the state file, or (the classic) write a
round summary with no next-round plan. Each omission is individually small and individually invisible;
together they make performance uneven. This skill is the **invariant checklist** that makes every cycle
look like every other good cycle. It is the *definition of done*, not a new procedure.

## When to use (vs. calibration-goal vs. a phase skill)

```
DRIVE the loop (what's next → dispatch → advance)      → calibration-goal (the driver)
Do exactly ONE phase                                   → phase{0..6}-*
Is THIS cycle / round actually complete + clean?       → calibration-discipline (this — the checklist)
```

`calibration-goal` decides *what* runs next and advances the state; `calibration-discipline` is *how each
step must be done* so the campaign stays stable. Run this checklist mentally at every phase transition,
and explicitly at each cycle end and round end. The two are complementary: the driver without the
discipline drifts; the discipline without the driver does not move.

## The loop limits are CONFIG, not literals in this file

**Read them from the environment before running any check below.** All three are set in the machine
config and **nowhere else** — a site or round config (e.g. `ecosim_biocon_config_r3.sh`) does not set
them. Since v2.306 it does not have to: **every shipped site config auto-sources its own machine
config** (`a2mc_config.sh` for CIME/ELM-FATES, `a2mc_noncime_config.sh` for the adapter models) when
one is not already loaded, and repairs the wrong one if you sourced it by mistake. So one command:

```bash
source use_cases/{Model}_{Case}/config/<site>_config_r<N>.sh   # round -> site -> machine
```

Sourcing the machine config first still works and is a no-op. Assert rather than assume:
`[ -n "$A2MC_MAX_EXPERIMENTS" ]`.

| variable | bounds | used by |
|---|---|---|
| `A2MC_MAX_SKIP_TESTING` | the INNER skip-testing loop, per cycle | item 3b |
| `A2MC_MAX_EXPERIMENTS` | the MIDDLE experiment-cycle loop, per round | items 6, 9, and the per-round banner |
| `A2MC_CONFIDENCE_THRESHOLD` | the skip-testing confidence exit | `phase4-hypothesis` |

**Why this section exists.** This file carried the literal `10` in three places. `orchestrator.py`
reads all three env vars (`:3567-3571`), so the online agent has always obeyed the config while a
checklist quoting `10` silently contradicted it the moment anyone changed the value. The same defect
was found and fixed in `tools/check_workflow_state_offline.py` on 2026-08-22 (v2.282), which had its
own hardcoded copies agreeing with the config only by coincidence; the PI then pointed out this file
had them too. Two copies of a value with one source of truth is
[[feedback_bind_derived_facts_to_their_source]], and prose is not exempt from it.

**So: quote the variable, never the number.** If you need the value, print it —
`echo "$A2MC_MAX_SKIP_TESTING"` — rather than reciting one from this document. And if a check here
appears to disagree with the config, the config wins: it is what the code reads.

## The per-cycle checklist (Phase 3 → 4 → 5 → 6)

1. **Log every phase with its own skill, into the offline layout.** Execute a phase via its `phaseN`
   skill; record it with `calibration-log` (PhaseLogger, `A2MC_AGENT_MODE=offline`) so it lands as
   `logs/{stem}.md` with the paired `phase_results/{stem}/`. `stem =
   YYYYMMDDx_phase{N}_{name}_r{RR}[_c{EE}[_iter{II}]]_{descriptor}`. Do not hand-roll the format.
2. **Make every `phase_results/{stem}/` folder self-documenting.** Per figure: the figure PNG, a caption
   or `NOTES.md`, the exact producing `.py`, and its data. The figure `.py` is **canonical here** — edit
   and regenerate it *in place*; never develop it in a scratch/CFS dir and copy the PNG back (that is how
   the script and the figure silently diverge). Memory: `feedback_plot_scripts_canonical_in_phase_results`.
   **A new script generating new artifacts that belong to no existing stem lives with the
   REPORT it serves** — normal for a round report, since it synthesizes across all cycles. The rule
   bites when a CYCLE report would copy an existing stem's script and edit it there; the fix then is
   to go back and fix the canonical script in the stem.

2b. **Start from the case's script TEMPLATE, and template a script on its SECOND use.** The template
   lives in `use_cases/{Model}_{Case}/scripts/`, seeded at onboarding (`onboard-case` item 3c). A phase
   **copies the template into its own `phase_results/{stem}/` and adapts it there**; the adapted copy is
   the canonical script for that figure and ships with its caption and data. **This does not conflict
   with "one canonical script per figure, never two copies"** — the *canonical script* stays with its
   figures, the *canonical script TEMPLATE* stays in `scripts/`; they are different artifacts. The
   **second** use of a script is the trigger to promote it into `scripts/` as a template, then copy it
   back and adapt. **Measured, and this is why the rule exists:** one site's `phase_results/` held **7
   script names duplicated across stem folders, all 7 byte-identical**, every one a Phase-5 script copied
   verbatim into its Phase-6 folder because no template tier existed. Checker:
   `tools/check_case_script_tier.py`.
3. **Analysis is first-hand this cycle.** A diagnosis / hypothesis / refinement (phase 3/4/6) log must do
   *this* cycle's analysis and cite a first-hand artifact produced this session, not restate a prior log.
   In **Phase 3**, that first-hand artifact should include a **sim-vs-obs TIME-SERIES comparison** for the
   diagnosed cases (the trajectory shape is often the diagnosis) — don't defer it to the report; and every
   mechanism claim is verified in the checked-out model **source** (`file:line`), not RAG/long_names
   ([[feedback_timeseries_plots_during_diagnosis]]).
   Gate: `python tools/check_offline_log_evidence.py <log.md>` must exit 0.
   Memory: `feedback_offline_logs_need_first_hand_analysis`.
3b. **RUN THE INNER LOOP. It is free, and it has not been running.** Phase 3<->4 is the skip-testing
   loop, capped at `--max-skip-testing` (**`$A2MC_MAX_SKIP_TESTING`**, from the machine config)
   *within one cycle*, and `test_with_existing=false`
   is a property of **one hypothesis**, not the cycle's exit. Read as the cycle's exit it produces:
   frame one hypothesis, skip-test it, find its *experiment* needs simulation, leave — the expensive
   loop spent while the free one still had questions. **Measured across one campaign's three rounds:
   46 phase-3/4 logs at `iter01`, 4 at `iter02`, none higher; all ten of one round's cycles at
   `iter01`.** The loop was not converging early, it was never entering.
   Before routing to Phase 5, ask and answer in the log: *is there another question about this
   cycle's mechanism that the EXISTING ensemble can answer?* **And keep asking while Phase 5 runs** —
   item 3 of the Phase-3/4 working discipline says not to idle through an in-flight experiment, and
   this is the work it means. Contract in `phase4-hypothesis` Step 2, which also carries the trap
   this exposed: **a conditioned screen must be paired with a check that the lever preserves
   membership in the set you conditioned on**, because conditioning on a variable the intervention
   itself moves hides exactly the cost that matters.

3c. **AN OUTPUT VARIABLE IS VERIFIED LIKE A PARAMETER. Never infer what a tape field MEANS from its name or its units.** The standing rule -- KB first, confirm in source, never infer behaviour from a name -- has always been written about **parameters and mechanisms**. Output variables are a third category, no rule named them, and the same failure mode arrives one category over. Before reducing any tape variable, establish two things about it:

   - **Is it ACTIVE?** A field registered `default='inactive'` is not written unless a run names it, and a tape that carries it anyway may be carrying something else. For EcoSIM this is in the KB already: `docs/ecosim-knowledge-base/ecosim_output_info_<commit>.cdl` gives every field a `:status = "active"|"inactive"` attribute, derived from the source rather than from a tape.
   - **What is its TEMPORAL SEMANTICS?** A rate, a per-record increment, a within-year cumulative that RESETS, a run-cumulative, or a stock. **One reduction does not fit all five**, and the units alone do not distinguish them: `gC/m2` is worn by both a per-record increment and a run-cumulative.

   **MEASURED 2026-09-08, and both halves cost something.** A diagnostic pull applied a single `nanmean` over the last 365 records to six variables. `NPP_pft` is a per-record increment whose annual value is a SUM (its mean is comparable to nothing); `Uptk_NMin_CumYr_FLX_pft` is a sawtooth resetting each year, whose annual total is the value at year end, so a mean returns roughly half of it and depends on where the reset falls; `CAN_cumGPP_pft` is monotone-cumulative, where a mean reports where the run was on average rather than what it accumulated. Separately, `CAN_GPP_pft` was read as gross production on the strength of its name and units; it is `default='inactive'` and carried the `NPP_pft` values, and the KB's own CDL said `status = "inactive"` in a line that was never opened. The false reading escalated into an alarm that the round had scored gross production against a net observation for twenty cycles, disproved only by a column-level cross-check.

   **The case already solves this for the targets it SCORES and not for anything else.** `validation/targets.yaml` gives every scored target its own `reduce:` (`annual`, `sum_pft_peak`, `growing_season_daytime_mean_abs` with its `tape:`). Diagnostic reads have no equivalent, which is the gap: **pick the reduction per variable, from that variable's own semantics, and say in the log which reduction each one got.** Where a scored target's variable is involved, use the target's own `reduce` rather than a second opinion.

4. **Arm monitors the moment you launch a testing simulation.** Right after a Phase-5 launch, arm
   monitoring on the run's live log(s) with the event + error filters — and **only on runs THIS session
   launched** (`feedback_monitor_only_own_session_launches`; never adopt another effort's jobs). The
   mechanism depends on the run style: a **scheduler / HPC** run (SLURM on Perlmutter) → `arm-hpc-monitoring`
   (it detects the submitter/extractor via `ps`, tails the logs, watches `squeue`); a **local / foreground**
   run (a model without a scheduler) → watch the process and its stdout/log directly (there is no `squeue`,
   so gate on the process exiting + error lines in the log). **For a standalone-binary model on a
   scheduler (EcoSIM, PFLOTRAN, ATS) the status source is
   `tools/model_ensemble_status.py --model <name> --run-root <dir> [--watch 60]`**, which reconciles the
   Slurm state with the model's OWN success check, so "Slurm COMPLETED but no usable output tape" is
   reported FAILED rather than success. Either way, **silence on a crash looks identical to silence on
   still-running**, so cover error signatures, not just happy-path events, and react to what you see with
   **proposals** (headroom math, next batch, next-phase extraction), not bare relay.
   **Filter on the SUMMARY COUNT, not the per-case lines.** That status tool reprints every case's state
   each poll, so a filter matching `COMPLETED` fires on unchanged state every interval and the monitor is
   stopped for noise. Match the count (`COMPLETED=4`) plus the failure signatures. Measured 2026-08-27:
   three identical notifications from a four-case run before the filter was tightened.
5. **Update and validate the state after every phase.** Write the phase transition into
   `workflow_state_offline_r{RR}.json` (`tools/workflow_state_offline.py`), then
   `python tools/check_workflow_state_offline.py` must exit 0. A corrupt/stale state misdrives the whole
   loop; validating after *every* write is the lesson from the mid-campaign state-format crash.

5b. **COMMIT AND PUSH at the same boundary.** The phase is not done when the state validates; it is done
   when the work has left the machine. **An unpushed commit exists on exactly one node** — on an HPC login
   node a session can lose, with no offsite copy — **and it is invisible to the PI until it lands**, which
   removes their ability to redirect the work while redirecting is still cheap. Both costs grow with the
   size of the pile. Push after each completed phase, each finished skill edit, each fix with its test; if
   several commits land on one thread, push once as that thread closes. The gap should be minutes and a
   handful of commits, never an hour and dozens. **Measured: one session accumulated 30 unpushed commits** —
   two full experiment cycles, a cycle report, a five-skill contract arc and two infrastructure fixes — and
   pushed only when the PI said *"you can't accumulate so many and not push."* Nothing in this checklist
   caught it, because item 5 asks whether the state is valid and never whether the work is safe.
   Destination and message rules are governed elsewhere and unchanged (branch safety, no AI attribution,
   model source to the fork only); **public sync is a separate explicit action and is never part of this.**
6. **Track the objective, not the loudest crash — and NEVER self-declare exhaustion below the loop limit.**
   The goal is the fit to the validation targets. When a crash and a calibration signal compete for
   attention, the targeted performance experiment is the objective
   (`feedback_performance_experiment_is_the_objective`); exhaust the input/param explanation before
   concluding a model-source change is needed. **Read the RAW counter, not your conclusion:** if
   `experiment_count < max_experiments` and not `converged`, the only valid states are "running a cycle"
   or "launching the next" — never "paused/complete/exhausted." Your "the rest is futile" conviction is
   the *hypothesis the remaining cycles test*, not a licence to skip them; the moment you feel most certain
   the space is exhausted is the moment to keep driving (R2 c00 declared "exhausted" at 0/10 while
   XRLA-down remained an untested, source-verified lever, found in the very next cycle). See
   `feedback_never_self_declare_exhaustion`.
6b. **On a 6→3 routing, ANSWER the rethink protocol in the Phase-6 log.** The route is the default and, until 2026-08-23, was only a counter increment: nothing said what a rethink should DO, so a cycle could re-enter Phase 3 carrying the previous cycle's base, binding target and lever class forward unexamined. Measured on one round: three consecutive rethinks ran on ONE base and attacked ONE target, and the cycle that finally re-examined both found the base already held that target in band with half a band's headroom — so the experiment those cycles kept designing would have broken the target the base held. The protocol is `phase6-refinement` Step 4 and its six questions are all settled by existing data at zero compute: synthesize THIS cycle (phases 3-6, separating what it ESTABLISHED from what it merely tried); re-read Phases 1 and 2 against that synthesis rather than citing them; is the BASE still right for the question now being asked; has the BINDING TARGET moved; what lever CLASS has the round exhausted versus never tried; and for each refuted lever, which DIRECTION was moved from a base with which SIGN of miss, and does that still apply — a refutation is a property of a (parameter, direction, base) triple, and a dose that moved monotonically the wrong way is positive evidence for the opposite direction rather than a closed door. The deliverable is **NEW PATHWAYS, plural**, each with its class and its falsifier, named in `set_phase_handshake(handed_to=...)` so Phase 3 starts from them. **Where it must be written:** the Phase-6 log, because the next cycle reads the log and not the state enum (`calibration-log`, Enrichment contract). **Enforced:** `check_calibration_log_conformance.py` C9 errors when a 6→3 log carries no rethink section and warns when it is thin or names no pathway. **Carried onward:** the class verdict and pathways go into the cycle report too (`write-report`, CYCLE item 4) — drawn from this synthesis, not derived again.

7. **Synthesize a report at each cycle end. ENFORCED: `tools/check_cycle_reports.py`** (pre-commit 18, WARN) reports every closed cycle with no report folder, so skipping one is visible instead of silent -- measured 2026-09-09, three cycles closed without one and the omission was recorded as "debt" rather than fixed. Use `write-report`, whose "two calibration deliverables"
   section now states this report's **scope**: it must walk the whole inner loop iteration by
   iteration, name every hypothesis with its falsification bar and the variants and job ids that
   tested it, and report results **per variant per SCORED target** against the measurements. Plus the
   house rules: zero-context reader, empty-alt figures (`![](fig.png)` + a bold `**Figure N.**`
   caption), **no em dash**, one canonical script per figure, folder `reports/{YYYYMMDDx}_{topic}/`
   (same-day letter required). Cross-reference the logs; do not duplicate them. At round end the
   round report synthesizes the **cycle reports**, not the raw logs again.
8. **No premature writes.** No curated-KB injection and no model-source edit until a Phase-5 test verifies
   the hypothesis AND the human gate clears (`feedback_no_kb_injection_before_verified_test`).

## The per-round checklist (loop limit reached, or converged)

> **A round is done ONLY at `experiment_count == max_experiments` OR `converged` — not on your judgment
> that the space is exhausted.** In particular `stop_model_dev` below the loop limit is NOT a legitimate
> gate arrival: it needs the loop limit reached, `converged`, or an explicit `human_confirmed_exhaustion`
> (enforced by `validate_phase6_decision` since 2026-07-21). A self-authored `next_targeted_experiment=NONE`
> + exhaustion_justification is not sufficient. If you are below the limit and not converged, you are not at
> the per-round checklist yet — go back to item 6 and run the next cycle.

9. **Write the round summary — and it MUST propose the next-round work plan.** A round summary that only
   narrates what happened is **incomplete**. Whether the round converged or hit the cycle limit, the
   summary must end with a concrete **next-round plan** the PI can act on.

   **THREE STEPS, IN ORDER, AND THE MIDDLE ONE IS THE ONE THAT GETS SKIPPED** (PI, 2026-08-24):

   ```
   summarize-calibration-round  ->  compare-calibration-rounds  ->  write-report (ROUND report)
      this round's figures,           the CROSS-ROUND PARAMETER      the arc + the plan,
      evaluation, and screen          LEDGER + what earlier          carrying BOTH of the above
                                      rounds established
   ```

   **`compare-calibration-rounds` is a step, not an option.** Every bullet below is a cross-round
   question — which parameters earlier rounds already tested and refuted, where the bounds came from
   and what still carries provisional debt, what was baked into the base and when, which residuals
   were already routed. This checklist named neither skill in item 9 until now (only one of them, once,
   in Cross-references), and the cost is measured: a round summary written from one round's artifacts
   proposed re-adding **two** parameters that earlier rounds had already refuted with named mechanisms,
   and both survived every checker because nothing in the round-close path opened a prior round
   (`memory/dev_logs_adapterkit/reflection/20260824a_*`, `20260824b_*`).

   The plan the summary ends with:
   - **Parameter list — add / remove.** Which dominant levers to *add* to the calibration list (e.g. ones
     that were fixed inputs but proved decisive), which insensitive ones to *drop* (justified by the
     sensitivity screen).
   - **Bounds — recenter / widen.** Which priors/bounds to move and why (developer correction, or the
     round's evidence that a value sits at a bound).
   - **Base update.** Which verified fixes to bake into the next round's base configuration so it starts
     from the best-known state (a fresh sensitivity screen on a *stale/dead* base is void — re-anchor).
   - **Residual split.** Route each unmet target to its track: a model-development item (source change on
     the fork, its own discipline) vs. an extraction/spin-up/data item (not a parameter problem).
   - **Mechanics.** The redesign is Phase 6 → Phase 0 with `calibration_round++`; list the sequence.
10. **Record the gate and PAUSE.** Write `round_summary` + the Phase-6 decision context into the state,
    leave `phase6_decision` for the human at a genuine fork (converge / redesign / stop→model-dev), and
    surface the decision. This is one of the four human gates — do not decide it unilaterally. *Once the PI
    records `redesign_6to0`*, opening round N+1 (per-round config wrapper → R{N} param list → add the round
    to `calibration_rounds.yaml` → fresh `workflow_state_offline_r{RR}.json` → sample on the corrected base)
    is the **`phase0-design`** skill's "Opening a NEW round" section — do not stand up a round before the gate.

Once the PI clears the gate, run **[`round-housekeeping`](../round-housekeeping/SKILL.md)** — the step
that now OWNS items 11 and 12 and the four they were missing (the open-questions list Phase 0 consumes,
the round's remaining bound debt, the non-empty-KB assertion, and recording the result in the state so
`check_workflow_state_offline.py` can see it happened). It has a state position:
`resolve_next_action()` returns `close("housekeeping")` and the driver executes it, so it no longer
fires only if someone remembers — which is what let one case reach **thirty experiment cycles with an
empty site knowledge base**. **A converged round runs it too, with a FULLER checklist** (PI, 2026-08-25):
convergence is the campaign boundary and hands work to nobody.

Items 11 and 12 below remain as the checklist statement of what that skill sequences (both are
human-gated Tier-3 writes, so they happen **at / after** the gate, not before — item 8):

11. **Curate the round's verified knowledge into the KB.** Only findings a Phase-5 test actually verified
    this round (never a mechanism-story, `feedback_no_kb_injection_before_verified_test`). Two inputs, one
    destination `use_cases/{Model}_{Case}/memory/gained_knowledge/{discoveries,experiments,parameters,failed_approaches}.json`:
    a finding **you** originated → `inject-knowledge`; the online agent's **staged** proposals in
    `auto_discovered_pending.json` → review + promote/discard via `curate-knowledge`
    (`tools/review_pending_knowledge.py`). "Online proposes, offline disposes" — you are the sole curated
    writer. (The dir is created on first write; it may not exist yet for a new site.)
12. **Promote reusable scripts into the shared library.** A diagnostic/analysis script that proved
    reusable graduates out of its scratch home so future rounds/sites auto-discover it:
    - **online** agent's `phases/phase3_diagnosis/generated/*.py` → `phases/phase3_diagnosis/` via
      `tools/promote_diagnostic_script.py` (`--list` → `--script <n> --dry-run` → promote; it registers the
      tool in `DIAGNOSTIC_TOOLS_INVENTORY`).
    - **offline** (interactive) scripts you wrote into `use_cases/{Model}_{Case}/memory/phase_results/{stem}/` →
      `tools/` (a generic analysis utility) or `phases/phase3_diagnosis/` (a reusable `test_hypothesis`),
      via `promote_diagnostic_script.py --source <path> --dest tools|phase3_diagnosis` (`--dry-run` first;
      `--dest tools` just copies, `--dest phase3_diagnosis` also registers it in `DIAGNOSTIC_TOOLS_INVENTORY`).
      **Promotion is copy-then-generalize, not copy-and-done:** a `phase_results/{stem}/` script hardcodes
      its output path, stem, and case IDs, so after promoting you **must edit the copy** to remove hardcoded
      paths/stems/case/site names and parameterize inputs (argparse or `tools/config.py`) — CLAUDE.md rules
      5 + 8 (keep generic, no hardcoded paths). Promote **only genuinely reusable** scripts; one-off figure
      scripts stay in `phase_results/{stem}/` as the log's evidence.
    - **the case's `use_cases/{Model}_{Case}/scripts/` templates** → **RECORD them in the round summary,
      do NOT auto-promote.** List what the case's template dir holds and what each was used for. A script
      reused across one site's round is evidence it is reusable *for that case*, not that it generalizes
      across models, and promotion to `tools/` stays a separate human-gated decision (PI, 2026-08-22).

## Footguns (the exact drifts this catches)

- **A round summary with no next-round plan** — narrates the round but leaves the PI nothing to act on.
  Item 9 is the fix; it is the most common omission.
- **Dev-in-scratch-and-copy plot scripts** — the report/`phase_results` folder ends up with a new figure
  but a stale script. Edit the canonical script in `phase_results/{stem}/` and regenerate in place (item 2).
- **A launch with no monitor** — silence on a crash looks identical to silence on still-running; arm
  immediately (item 4), and only on your own jobs.
- **Skipping the state update/validate** — the next session's resume brain (and `calibration-goal`) then
  misdrives. Update + `check_workflow_state_offline.py` after every phase (item 5).

  **Two different things live in that file and only one of them was being kept.** `next_action` and
  the phase/counters are the **program counter** — where the loop resumes. The `decisions` list is
  the **record** — what this round has established. `PhaseLogger` rebuilds its `## Reasoning chain`
  block from `decisions` on *every* log write, so a finding that never reaches the state is
  invisible to the next phase, which is the re-derivation the loop exists to prevent.

  **Record a finding when it is established, not at Phase 6.** Phase 6 *extracts and curates*
  lessons (human-gated, behind a verified test); it is not where findings first get written down.
  Measured 2026-08-21: a day of R3 work established eight substantive findings — a definitive
  failure census, a misdiagnosis and its real cause, six passed gates, a model defect, three reasons
  a round was not comparable to its predecessor — and the state held **two** decisions, both from
  that morning. Everything else was prose in `next_action` and in commit messages. Nothing flagged
  it.

  ```python
  st.add_decision("Fs IS reachable from rate-only params — my earlier claim refuted",
                  rationale="85 of 2,314 sampled cases put Fs in band; case 157 reaches ~6 vs 6.2 obs")
  ```

  A decision entry reading *"ran the sweep"* contributes nothing to a chain; the finding and its
  evidence are what a later phase can stand on. `check_workflow_state_offline.py` now **WARNs** when
  a case has moved (commits touching it) with nothing recorded since the newest decision — a nudge,
  never a gate, and pre-commit check (9) surfaces the same warning when case work is staged.
- **Stopping early on a self-declared gate** — the loop runs to `experiment_count == max_experiments` or
  `converged`. The tempting loophole is to declare you have "reached a gate" (`stop_model_dev`) at a low
  cycle count and pause — but a `stop_model_dev` you authored below the loop limit is NOT a legitimate gate
  arrival; it is the premature-stop failure. A GENUINE gate is: the loop limit reached, `converged`, or a
  fork with `human_confirmed_exhaustion`. Don't halt with cycles remaining on your own "it's futile" call
  (`feedback_never_self_declare_exhaustion`, `feedback_offline_agent_drives_the_workflow`). This is the R2
  drift: `stop_model_dev` at 0/10 passed the old checks because the failure was written INTO the state the
  checks read — a consistency check can't catch a premise you corrupted; read the raw counter.
- **Promoting a script verbatim** — a `phase_results/{stem}/` script hardcodes paths, its stem, and case
  IDs; copied to `tools/` unchanged it breaks on the next run/site. Promotion is copy-**then-generalize**
  (item 12): edit the copy to be site/run-agnostic before committing.

## SEARCH BEFORE YOU RECORD — the case has usually been here already

**Before recording a finding as NEW, or a premise as UNVERIFIED, or a question as OPEN, search the
case's own logs.** On 2026-08-22 I did neither, twice in one hour, and both had been settled:

| what I recorded | what the case already held |
|---|---|
| "the NPP scope is an unverified premise" | asked 08-07, answered 08-08, retracted 08-09, re-established **from the manuscript** in `20260809b`, with the residual depth asymmetry quantified at ~11% |
| a frontier result, presented as a discovery | `20260807b` Finding 2, still standing: the observed Fs and NPP are mutually inconsistent at steady state, Fs/NPP = 3.47 against an expected 1.2-1.8 |

**A plain `git grep` is not enough, and that is the interesting part.** In the first case my grep DID
surface the right thread and I read it — but the answer was three logs downstream through a
correction chain, and a grep shows you the log you found, not the log that supersedes it. This
project's logging convention puts banners at the top of a superseded log precisely so a reader can
follow the chain; a keyword search does not surface them.

```bash
python3 tools/prior_art.py <keyword> [...] --site <Site> [--all-streams]
```

It ranks logs by how many of your terms they carry, prints each one's **title** and any
**RETRACTED / CORRECTED / SUPERSEDED / WITHDRAWN** banner, and says so loudly when any hit carries
one. Both of the failures above are caught by it in a single call.

**When to run it:** before `add_decision` on anything you believe is new; before writing "no log
records X"; before a Phase-3 diagnosis names a root cause; and before a round summary claims a
finding. It costs seconds, and this is the third occasion in one session where the alternative was
recording something the case already knew ([[feedback_dont_assert_absence_from_one_grep]],
[[feedback_reread_the_decision_before_writing_its_successor]]).

### A CLAIM ABOUT WHAT THE ROUND HAS ESTABLISHED IS VERIFIED AT THE ARTIFACT, NOT AT THE INDEX

**"The round has never found X", "no lever does Y", "every lever we measured behaves like Z" is the
same high-risk shape as a claim that a variable is never read in the source, and it needs the same
discipline: TRACE IT, do not grep it** (PI, 2026-09-08).

**The three layers are each a POINTER TO THE NEXT, and only the last one settles anything:**

```
decisions[] / the ## Reasoning chain   ->  tells you WHICH cycle and WHICH log
        the log stem it names           ->  tells you WHICH artifact folder
        phase_results/{stem}/ + its data ->  SETTLES IT
```

**Checking the index is not enough, and this is not a hypothetical.** A `decisions[]` entry is prose
written at the time — a synthesis of the artifact, exactly as a phase log is a synthesis of its stem
folder — and this project has already measured a bar that lived only in prose and appeared in **no
artifact anywhere in the round**, one of whose three values was wrong by 1e-4 relative. A round-level
claim rests on the same kind of sentence. So open the folder, read the data file the script wrote,
and confirm the number before writing that the round has or has not established something.

**MEASURED, 2026-09-08, and it is the cleanest instance this project has.** One cycle's refinement log
concluded *"nine levers, no exceptions"* and *"the round has never found a negative-rate lever and has
never explicitly looked for one."* That same log mentions the parameter that refutes both statements
**35 times — every one of them inside its own auto-generated reasoning chain, and none in its body.**
The evidence sat in the same file as the conclusion. The next cycle overturned it not by re-reading
the chain but by opening three earlier cycles' Phase-5 data files and recomputing the rates from
them: 1.92, 2.42 and 37.10, none inside the range the log had just declared universal.

**And the search that should have caught it did not.** `prior_art.py` on the phrase *"negative
exchange rate opposite direction plant_C NPP"* returned **0 of 111 logs**, while **86 of 111** mention
the parameter by name. Term-overlap ranking degrades badly on a phrase. **Search the bare NOUN** — the
parameter name, the case id, the mechanism — and only then narrow.

## ARM THE REVIEW AT SESSION START — it is a mechanism or it is nothing

**This checklist only works if it actually fires.** Through 2026-08-22 it fired because the PI typed
it, six times in one session, which is not a mechanism: it is the PI doing the agent's bookkeeping.
The agent also ran the checks *from memory of this skill* at least once instead of invoking it,
which is the failure `check_skill_claims.py` exists to catch, one level up.

So: **when a campaign is live, arm the recurring self-review before doing anything else.**

```
CronCreate(cron="23 */3 * * *", recurring=true, prompt=<the self-review prompt>)
```

**Pick the CADENCE from how fast this model's simulations actually go, not from a fixed hour** (PI,
2026-08-27). The review is worth running about once per natural batch of progress: a model whose cases
take ~15 minutes and whose round is hundreds of short cases wants a review every few hours, not every
hour, because an hourly one mostly reports the same in-flight state and trains the reader to ignore it.
A multi-day chained run wants it rarer still. Three-hourly is a reasonable default for a short-case
adapter round; adjust once the round's real throughput is known. Pick an off-:00/:30 minute. The prompt must (a) say **INVOKE the skill**, not "check against it",
(b) carry the five checks, and (c) end with **DRIVE THE LOOP THROUGH** — a review that stops at
reporting leaves the loop parked, which is the drift this whole skill exists to prevent.

**Two limits, both worth stating rather than discovering.** A cron job is **session-only** and dies
with the session, so re-arming is part of session start, not a one-time setup; and it fires only
while the REPL is idle, so it will not interrupt long work. Neither makes it worthless: an armed
cron that survives an hour of quiet is strictly better than a checklist nobody runs.

**Nothing in the loop is the PI's decision except the Phase-6 converge/redesign/stop fork.** `rethink_6to3` is auto-taken — meaning it needs no PI approval, **NOT that it needs no work**. Auto-taken is about the gate, not the effort: the routing is automatic and the rethink protocol behind it (item 6b) is mandatory. **FIX IT NOW vs QUEUE IT — and the examples matter, because getting them backwards parks the loop.**

**FIX IMMEDIATELY, inside the phase that found it, never queued and never surfaced as a blocker:** a parameter BOUND that the round's own data shows is wrong, a source DEFECT, a bug in A2MC's tooling, a broken run script, a mis-set walltime or queue. These are the phase's work. A round that discovers its own bound is degenerate and then stops to ask has converted a finding into a delay. **When monitoring reports failed cases, DIAGNOSE AND FIX — model bug, infrastructure failure, or a mistake in your own run scripts — before continuing** (`phase0-design` Step 4a).

**QUEUE in `TODO.md`** only what is genuinely out of the round's scope: a NEW MECHANISM to design, or a SIGNIFICANT CHANGE TO MODEL STRUCTURE. Those are `model-evolution` work with their own discipline and their own gate.

**And a queued item is still not a loop gate.** Ending a turn by surfacing one as though it blocks is the same premature stop as item 6, wearing politeness instead of a verdict.

**Measured, 2026-09-05 (PI correction).** This paragraph previously read *"A model-evolution item queued in TODO.md (a parameter bound, a source defect) is NOT a loop gate"* — whose parenthetical implied a bound or a defect is the kind of thing you QUEUE. R1's gate found `OMGR`'s upper bound degenerate on units grounds, with 26 of 26 failures above 0.68 and a monotone dose-response; the agent then parked the loop across several turns asking the PI to choose, having read this very line as licensing the pause. The bound was its own call to make on the evidence it already had.

## Two of these items are observed, not just written down

Item 4 (arm monitors) and item 5 (update + validate state) have hooks, because both are conditional
instructions whose condition becomes true mid-session — the moment it does went unobserved.

- **`remind-arm-monitoring.py`** fires when a Bash command actually submits jobs.
- **`remind-calibration-discipline.py`** fires on two things. It validates a state file the moment
  one is written, and — the half that matters — it watches **phase work** (a `phase{N}` log, a
  `phase_results/` artifact) and reports when the newest artifact is dated *after* the state's
  `updated_at`. **A hook keyed only on state writes is blind to an agent that forgets to write one.**

It compares timestamps, not phase numbers: a legitimate Phase-6 → Phase-0 redesign moves the phase
backwards, so "the log says phase 6, the state says design" is a correct state, not a stale one.

Both stay silent unless something is actually wrong. Calibration is the main working loop, so a
per-transition checklist reminder would be noise, and noise gets muted.

## Cross-references

- `setup-discipline` — the same habits layer one stage earlier: the per-STAGE definition of done for `a2mc-init` / `onboard-model` / `onboard-case`, before a campaign exists.

- Driver + orient: `calibration-goal` (the loop this discipline is the definition-of-done for),
  `onboard-session` (cold-start; its Step 4 DRIVE-vs-PAUSE list is the same gate set).
- **Figures: `plotting` — load it BEFORE the first `savefig` in any cycle.** This skill already
  says WHERE a figure lives (`phase_results/{stem}/`, script canonical beside it); `plotting`
  says how it must LOOK and carries the one check that catches a broken figure — open the
  rendered PNG and look at it.
- Pieces: `calibration-log`, the `phase0-design`…`phase6-refinement` skills, `arm-hpc-monitoring`,
  `write-report`, `summarize-calibration-round` (the standardized round summary — generic since 2026-08-24; contract model-agnostic, backend per model), `curate-knowledge`
  (the KB write gate), `model-evolution` (the residual model-dev track).
- Memories: `feedback_never_self_declare_exhaustion` (the R2 premature-stop failure this skill now guards),
  `feedback_offline_agent_drives_the_workflow`, `feedback_offline_agent_operating_discipline`,
  `feedback_offline_logs_need_first_hand_analysis`, `feedback_plot_scripts_canonical_in_phase_results`,
  `feedback_monitor_only_own_session_launches`, `feedback_no_kb_injection_before_verified_test`,
  `feedback_performance_experiment_is_the_objective`.

## Notes

- **Branch fit:** generic offline-calibration discipline — model-agnostic, applies on any branch. Distilled
  on `adapter-kit` from the EcoSIM BioCON R1 ten-cycle onboarding; hand off to `main` (adapter-kit never
  pushes back, `docs/38`).

## Changelog

- 2026-09-09: **Item 2 says where a REPORT's own script lives.** The canonical-script rule was read as forbidding scripts in report folders; it governs a phase's figure scripts. A new script making new artifacts that belong to no stem lives with the report it serves, which is normal for a round report. PI correction, after the rule was applied too broadly.

- 2026-09-08 (later): **New item 3c -- an OUTPUT VARIABLE is verified like a parameter.** PI-directed, after a diagnostic pull applied one `nanmean` to six tape variables with five different temporal semantics and read an `inactive` field as gross production. The standing verify-in-source rule was written about PARAMETERS and mechanisms; output variables are a third category no rule named, so the identical failure mode arrived one category over in the same session that had applied the rule rigorously to a parameter. Two checks now required before reducing anything: is the field ACTIVE (the model's output-info CDL carries `:status`, derived from source), and what are its temporal semantics (a mean of a resetting cumulative returns half its annual total; a mean of a monotone cumulative is meaningless). Notes that the case already does this correctly for SCORED targets via `targets.yaml`'s `reduce:` and that diagnostic reads have no equivalent, which is the gap. No `description` change.
- 2026-09-08: **New section: a claim about what the ROUND has established is verified at the ARTIFACT, not at the index** (PI-directed, fix-now). The file already required searching before recording a finding as new, and `prior_art.py` for the superseded-log case. What it did not say is what to do with what the search RETURNS: `decisions[]` and the auto-generated reasoning chain are POINTERS -- they name the cycle and the log; the log names its stem; **`phase_results/{stem}/` and the data file the script wrote are what settle it.** A decision entry is prose written at the time, the same kind of object as a phase log, and this project has already measured a bar that lived only in prose and appeared in no artifact anywhere in the round. **Measured the day this landed, and it is the cleanest instance so far:** one refinement log concluded *"nine levers, no exceptions"* and *"the round has never found a negative-rate lever"* while mentioning the refuting parameter **35 times, every one inside its own auto-generated reasoning chain and none in its body** -- the evidence was in the same file as the conclusion. The next cycle overturned it by opening three earlier cycles' Phase-5 data files and recomputing, not by re-reading the chain. Also records the retrieval failure that let it through: `prior_art.py` on a five-word phrase returned 0 of 111 logs while 86 of 111 mention the parameter by name, so **search the bare NOUN first**. Twin clause added to `phase6-refinement` Step 2b, which is where such sentences get written. Reconciled in the same pass: the At-a-glance line calling `decisions` "the RECORD" now says it is the record of what was established and where, not where a claim is verified. No `description` change.

- 2026-08-27: **The self-review cadence is chosen from the model's simulation speed, not fixed at
  hourly** (PI-directed). An hourly review of a round whose cases take ~15 minutes mostly reports
  unchanged in-flight state, and a reminder that is usually noise gets ignored — the same failure the
  file already warns about for monitors. Three-hourly is the stated default for a short-case adapter
  round. Item 4 also gains `tools/model_ensemble_status.py` as the status source for a
  standalone-binary model on a scheduler, and the filter rule that goes with it: match the SUMMARY
  COUNT, not the per-case lines, which reprint every poll (measured: three identical notifications
  from one four-case run).
- 2026-08-26: **The two-step source order is now optional, and this file says so.** v2.306 gave every shipped site config a guard that auto-sources its own machine config (`a2mc_config.sh` for CIME/ELM-FATES, `a2mc_noncime_config.sh` for the adapter models) when one is not already loaded, and REPAIRS the wrong one if it was sourced by mistake. Nothing here was wrong -- the explicit machine-then-site order still works and still takes precedence -- so the instruction is shortened and the old form kept as a stated no-op. Asserted by `tests/test_site_config_autosource.py`. PI-directed. This file is where it mattered most: it told the reader to source the machine config FIRST because the three loop limits live there and nowhere else, which was the true reason and is now discharged by the chain instead of by the reader. Both the at-a-glance block and the loop-limits section show one command, and the section ends with the assertion to run (`[ -n "$A2MC_MAX_EXPERIMENTS" ]`) rather than an instruction to remember.
- 2026-08-24: **Item 9 now names the three round-close steps in order, and the At-a-glance box with them.** PI-directed. `summarize-calibration-round` appeared once in this file, in Cross-references, and `compare-calibration-rounds` not at all, so the definition of done for a round never required either — while item 9's four plan bullets are all cross-round questions. Measured cost: a round summary proposed re-adding two parameters earlier rounds had refuted with named mechanisms, and both survived every checker. Both skills were made generic the same day, so the ordering now applies to adapter models too rather than only to FATES.


- 2026-08-23 (later): **New item 5b — commit AND PUSH at the same boundary as the state update.** PI-directed after a single session accumulated 30 unpushed commits on a feature branch and pushed only when asked. Item 5 already required the state be updated and validated after every phase, which reads as the whole obligation and is not: it asks whether the state is VALID and never whether the work is SAFE. An unpushed commit exists on one node, on HPC a login node the session can lose, and is invisible to the PI until it lands, so a long unpushed run removes their ability to redirect work while that is still cheap. Destination rules are unchanged and governed elsewhere; public sync stays a separate explicit action. [[feedback_push_at_every_phase_boundary]].
- 2026-08-23 (later): **Item 6b and the At-a-glance line carry the rethink protocol's SIXTH question** — for each refuted lever, which direction was moved, from a base with which sign of miss, and does that still apply. PI-directed; rationale and evidence in `phase6-refinement`'s own changelog entry of the same day. Stated here because this file enumerates the protocol's questions, so leaving it at five would have made the definition-of-done disagree with the protocol it points at.
- 2026-08-23: **New per-cycle item 6b — on a 6→3 routing, ANSWER the rethink protocol in the Phase-6 log**, plus the matching At-a-glance line. Numbered 6b rather than 7 following this file's own convention for an inserted item (cf. 2b, 3b), and because the per-ROUND checklist CONTINUES the same sequence at 9 — renumbering the cycle list would have silently collided with 'Write the round summary'. PI-prompted, completing the arc that added the protocol to `phase6-refinement` Step 4, the logging obligation to `calibration-log`, the C9 enforcement, and the propagation into `write-report`. This file was the one place in that arc still silent on it, and its single mention of the route said only that `rethink_6to3` is "auto-taken", which once a protocol existed read as "automatic, nothing to do" and contradicted it. That line now says auto-taken is about the GATE, not the effort: no PI approval needed, protocol still mandatory. Evidence: three consecutive rethinks in one round ran on one base and attacked one target, and the cycle that finally re-examined both found the base already held that target in band with half a band of headroom, so the experiment those cycles kept designing would have broken the target the base held. Details: `memory/dev_logs_adapterkit/20260823e_*` and `20260823f_*`.


- 2026-08-22 (later): **New per-cycle item 2b (start from the case script TEMPLATE) and a round-close addition (RECORD the template dir, do not auto-promote).** PI-directed. The template lives in `use_cases/{Model}_{Case}/scripts/`, seeded at onboarding; a phase copies it into its `phase_results/{stem}/` and ADAPTS it there. A script's **second** use is the trigger to template it. This does not conflict with "one canonical script per figure, never two copies": the canonical *script* stays with its figures, the canonical script *TEMPLATE* stays in `scripts/`. Round close records what the template dir holds and what each was used for; promotion to `tools/` stays a separate human-gated decision, since reuse within one case is not evidence of cross-model generality. Measured: 7 byte-identical duplicate pairs. Checker `tools/check_case_script_tier.py`.

- 2026-08-22 (later): **The loop limits are read from the machine config, not quoted as literals.** PI-caught: this file carried the literal `10` in three places (the At-a-glance line, item 3b's measured-cap note, and item 3b's body) while `A2MC_MAX_SKIP_TESTING`, `A2MC_MAX_EXPERIMENTS` and `A2MC_CONFIDENCE_THRESHOLD` live in `a2mc_noncime_config.sh` / `a2mc_config.sh` and **nowhere else** — a site or round config does not set them. `orchestrator.py:3567-3571` reads all three, so a checklist quoting `10` contradicted the online agent the moment the value changed. New section "The loop limits are CONFIG, not literals in this file" names the sourcing command and the three variables; the three literals now quote the variable. Same defect and same day as v2.282, which fixed the hardcoded copies in `tools/check_workflow_state_offline.py`. [[feedback_bind_derived_facts_to_their_source]].

- 2026-08-22: **Two additions, both PI-directed, both for gaps that were invisible because nothing measured them.** (1) **New item 3b: run the inner loop.** `test_with_existing=false` is a property of one hypothesis and was being read as the cycle's exit, so the free Phase-3<->4 loop was never entering while every cycle spent an HPC experiment. Measured across one campaign's three rounds: 46 phase-3/4 logs at `iter01`, 4 at `iter02`, none higher, against a cap of 10. Adds the pre-routing question, the keep-asking-while-Phase-5-runs instruction, and a pointer to the conditioned-screen trap now documented in `phase4-hypothesis` Step 2. (2) **Item 7 gains the cycle report's stated scope**, now that `write-report` names the CYCLE and ROUND reports as structural deliverables (`20260822p`); the At-a-glance box also gains the every-scored-target figure requirement that `phase6-refinement` Step 1b now states model-neutrally. Details: `memory/dev_logs_adapterkit/20260822q_*`.

- 2026-08-21: **The state's `decisions` list is called out as a distinct obligation from its phase
  position, and "record findings as they are established" replaces the implicit "extract at Phase
  6".** The checklist said the state must be "updated + validated after EVERY phase", which reads as
  the program counter and is how it was being used: on 2026-08-21 a day of work produced eight
  findings and the state recorded two, both from that morning, with everything else in `next_action`
  prose and commit messages. `PhaseLogger` rebuilds its reasoning chain from `decisions`, so the
  next phase would have been blind to what it stands on. Paired mechanisms so this is not left to
  discipline: `check_workflow_state_offline.py::_check_decisions_current()` warns when a case has
  moved with nothing recorded, and pre-commit check (9) surfaces it when case work is staged.
  PI-prompted. Details: `memory/dev_logs_adapterkit/20260821m_*`.

- 2026-08-16: **Names the `plotting` skill.** The link was one-directional — `plotting` claimed
  these skills apply its conventions while they never mentioned it, so a whole case's figures
  could be produced without the conventions or the view-the-PNG check being loaded. PI-directed.
- 2026-07-21: **Closed the premature-stop loophole** (R2 c00 drift: `stop_model_dev` declared at
  `experiment_count 0/10` while a source-verified lever remained; the 3-hour check rubber-stamped it because
  the wrong decision was written into the state it reads). Hardened item 6 (read the RAW counter, never
  self-declare exhaustion below the loop limit, your "futile" conviction is the hypothesis the cycles test),
  added a per-round-checklist banner (a round is done ONLY at loop limit / converged / `human_confirmed_exhaustion`),
  rewrote the "Stopping early" footgun to kill the "reached a gate" escape hatch, and cross-referenced the new
  `feedback_never_self_declare_exhaustion`. Paired code guardrail: `validate_phase6_decision` now errors on
  `stop_model_dev` below the loop limit without `human_confirmed_exhaustion`.
- 2026-07-18: Item 12 + a footgun: promotion is copy-**then-generalize** — a phase_results/{stem}/ script
  hardcodes paths/stems/case IDs, so the promoted copy must be edited site/run-agnostic (CLAUDE.md 5+8).
- 2026-07-18: Item 12's offline promotion is no longer manual — `promote_diagnostic_script.py` now takes
  `--source <path> --dest tools|phase3_diagnosis`, so a `phase_results/{stem}/` script promotes with one command.
- 2026-07-18: Added the two round-close housekeeping steps to the per-round checklist (items 11–12):
  **curate the round's verified knowledge** into `gained_knowledge/*.json` (inject-knowledge / curate-knowledge,
  human-gated) and **promote reusable scripts** (online `generated/` → `phase3_diagnosis` via
  `promote_diagnostic_script.py`; offline `phase_results/{stem}/` → `tools/` or `phase3_diagnosis`, manual).
  Both were implicit / lived only in `phase6-refinement`. Paired: `phase6-refinement` Step 3b.
- 2026-07-18: Added a one-line workflow orientation to the At-a-glance (the 7 phases + the 3 nested
  iteration levels: round / experiment cycle / skip-testing) so the checklist's per-cycle/per-round
  scope is legible without opening `calibration-goal`.
- 2026-07-18: Reworded item 4 to be run-style-agnostic — "testing-simulation launch" (not "HPC launch"),
  and split the monitoring mechanism: scheduler/HPC run → `arm-hpc-monitoring`; local/foreground run →
  watch the process + its log directly (no `squeue`). `arm-hpc-monitoring` is scheduler-specific; a
  dedicated non-HPC monitoring skill is a TODO for when the first local-run adapter model appears.
- 2026-07-18: Initial version — distilled from the EcoSIM_BioCON R1 offline onboarding (10 experiment cycles,
  `memory/dev_logs_adapterkit/2026071*`), where the stable behaviors (self-documenting `phase_results/{stem}/`,
  per-cycle reports, arm-after-launch, state-validate-after-write, canonical figure scripts, drive-to-limit)
  were all performed but scattered across many skills/memories with no single definition-of-done. Item 9
  (round summary MUST propose the next-round plan) added after the R1 summary initially shipped without one.