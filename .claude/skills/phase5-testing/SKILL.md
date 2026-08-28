---
name: phase5-testing
visibility: public
category: phase
description: Run Phase 5 (TESTING) of the A2MC calibration workflow as the offline agent — the human-in-the-loop analog of the orchestrator's `_run_testing()`. Execute the hypothesis experiments as new simulation runs — modify parameter files, create + submit cases (ADSP→RGSP→TRANS), monitor, and extract results against targets. This is a thin phase-router — the end-to-end offline procedure lives in `offline-testing-workflow`. Use when the user says "run the experiment", "submit the test cases", "run Phase 5", "test this hypothesis with new simulations", after Phase 4 hands off a hypothesis that needs new simulations.
modes:
  requires_fates: false      # calibration-workflow phase skill; mode resolved at runtime via describe_mode
  nutrient_pathway: any
  scope: [calibration]
  summary: "Offline analog of Phase 5 (HPC experiment execution; routes to offline-testing-workflow). Applies in every calibration mode."
---

# Phase 5: Testing (offline agent) — router

> **Driven by `calibration-goal`** — the run-to-convergence driver dispatches here when `WorkflowStateOffline.current_phase` routes to this phase; on an HPC submit, arm monitors + take the WAIT stop (the Monitor event resumes the driver). Also runnable standalone (one phase).

The offline analog of `_run_testing()`. This phase skill exists so the Phase 0–6 set is complete
and to route you to the full procedure with the phase framing intact. **Do not reimplement
experiment execution here — and route BY MODEL, because NONE of these procedures transfer to each other:**

| model | the full procedure |
|---|---|
| ELM / ELM-FATES (CIME) | **`offline-testing-workflow`** — `create_case.sh`, chained ADSP→RGSP→TRANS legs, `modify_fates_parameters.py` |
| EcoSIM (standalone binary, non-CIME) | **`ecosim-run-workflow`** — three parameter surfaces, the 4096-byte namelist buffer, `materialize_adapter_ensemble.py`, pre-submission validation |
| PFLOTRAN (standalone binary, non-CIME) | **`pflotran-run-workflow`** — the input DECK *is* the parameter file (one surface, addressed by block path), `*-mas.dat` columns with no NetCDF history tape, the 806-hour observation offset, `scripts/validate_pflotran_ensemble.py` |
| ATS (standalone binary, non-CIME) | **`ats-run-workflow`** — XML ParameterList by path; written against a TEMPLATE, not yet a campaign, so refine it from the first real case rather than trusting it whole |

Resolve the model first (`python tools/describe_mode.py`, or `$A2MC_MODEL`). Sending an adapter
experiment down the FATES path fails immediately — there is no `create_case.sh` — but the
expensive direction is subtler: FATES conventions applied to a standalone model (single parameter
surface, no namelist size limit, `sacct COMPLETED` treated as success) produce cases that run and
score wrong.

**And the adapter models do not transfer to EACH OTHER either.** EcoSIM has three parameter
surfaces and a 4096-byte namelist buffer; PFLOTRAN has one surface which is the deck itself, no
namelist at all, and an 806-hour offset between the observation clock and the model clock. A
window written in raw model time on the miniLEO deck scores the pre-experiment spin-up and
contains no observations, while still producing plausible-looking numbers.

> **Floor, not ceiling.** The online Phase 5 runs exactly the experiments Phase 4 designed. As the
> offline agent you can add variants, a wider sweep, an extra control, or a second base case the
> fixed loop wouldn't — `offline-testing-workflow` is built for exactly that latitude (N variants,
> V0 gate, decision tree). Run at least the designed experiment; design more when it's warranted.

**Inputs (from Phase 4):** the hypothesis / experiment design + selected base case.
**Deliverable:** experiment results (per-target metrics vs baseline) → handed to Phase 6.

## Do this

0. **On Phase-5 entry, reset `skip_testing_count = 0`** in `workflow_state_offline_r{RR}.json`. Entering
   Phase 5 commits this experiment cycle to an HPC test and closes the inner (skip-test) loop, which counts
   within one cycle only. (`experiment_count` is unchanged here — it advances on the Phase 6→3 route.) The
   online orchestrator does this reset in code; offline, do it by hand.
1. **Invoke the model's procedure from the table above** (FATES: `offline-testing-workflow`;
   EcoSIM: `ecosim-run-workflow`; PFLOTRAN: `pflotran-run-workflow`). For FATES it owns the whole
   path end-to-end: variant design,
   parameter-file generation via `tools/modify_fates_parameters.py` (+ `verify_modifications()`),
   case creation via `tools/create_case.sh --case-suffix` (the `_exp` convention — NEVER invent
   out-of-Morris case numbers), submission, the **V0 reproducibility gate** (validate the first
   completed variant before trusting V1+), extraction, and analysis. The corresponding phase
   scripts are `phases/phase5_testing/design_experiments.py`, `submit_experiments.py`,
   `monitor_experiments.py`.
2. **Monitor** the in-flight experiment → `arm-hpc-monitoring`. **Failed jobs** → distinguish
   infrastructure (restart-eligible) from model failures via `restart-failed-jobs`.
2b. **ARCHIVE THIS PHASE'S JOB SCRIPTS into `phase_results/{stem}/submit_scripts/`** — one per case, plus one
   representative `runfile.nml`. **Phase 0 is deliberately EXEMPT.** Its job scripts are generated from the machine + round config by the materializer, and an ensemble is thousands of cases (one R3 round is 59,393), so archiving them would be both enormous and redundant: the config plus the generator already reproduces them exactly. Phase 5 is different because its handful of variants are hand-designed and hand-repointed, so nothing else records what actually ran. **Copy, never move:** the scheduler reads the operative copy from the run
   directory. Do it as soon as the scripts are final, not at Phase 6.
   **Why this is a step and not housekeeping.** The run directory is untracked scratch that gets cleaned,
   and the submit script is the only record of **which binary this run was bound to** plus its run-time
   hash assertion. A log stating "V0 gate PASS" with no archived submit script cannot show which
   executable produced that number. On 2026-08-23 a cycle nearly ran against the wrong binary because
   `materialize_adapter_ensemble.py` emits the LIVE build path by default and that path had since been
   rebuilt ([[feedback_bind_runs_to_archived_binaries]]).
   `check_offline_log_evidence.py` WARNs when a phase-0/5 stem folder has no `submit_scripts/`
   (non-retroactive from `20260823`).
3. **Log** via `calibration-log` (phase log → `PhaseLogger.log_testing` /
   `log_experiment_design`).
4. **Advance the driver state** once results are extracted: `st.set_position(current_phase="refinement")`;
   `st.save()` (`tools/workflow_state_offline.py`) so `resolve_next_action` resolves Phase 6.

## Footguns (the load-bearing ones; full set in `offline-testing-workflow`)

- **Case-suffix, not new case numbers.** Experiments use `--case-suffix exp_<id>`; inventing a
  case number collides with / leaks into the Morris ensemble extract dir.
- **V0 gate before trust.** Reproduce V0 (baseline params) before reading V1+ as signal — catches
  build / param-file errors early.



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
- **The actual execution** → `offline-testing-workflow`. **Monitor** → `arm-hpc-monitoring`.
  **Restart** → `restart-failed-jobs`.
- **Next:** `phase6-refinement` (evaluate results, extract lessons, decide convergence).

## Changelog

- 2026-08-27: **PFLOTRAN and ATS added to the routing table, in parallel with EcoSIM** (PI-directed,
  at the start of the first PFLOTRAN campaign). `pflotran-run-workflow` was written 2026-08-26 and
  this table did not list it, so Phase 5 routed the model NOWHERE at the phase where a wrong route
  costs compute. Measured that day: PFLOTRAN appeared ONCE across all seven phase skills and both
  drivers, against 32 mentions of EcoSIM. Also states that the adapter models do not transfer to
  EACH OTHER — the skill already warned about FATES-conventions-on-EcoSIM and was silent on the
  adapter-to-adapter case, which is the one a growing registry makes likelier.

- 2026-08-23 (later): **Re-sited the job-script archive rule as Step 2b of "Do this".** It first landed as an orphan paragraph between the Footguns and Scripts sections, belonging to neither — the PI asked whether this skill carried the rule at all, which is what a rule with no home looks like from the outside. Archiving is an ACTION this phase takes, so it is now a numbered step next to submission and monitoring, where the scripts become final.
- 2026-08-23 (corrected same day): the rule is **PHASE 5 ONLY**; Phase 0 is exempt because its ensemble scripts are config-generated and number in the tens of thousands (PI).
- 2026-08-23: **Phase 5 archives its JOB SCRIPTS into `phase_results/{stem}/submit_scripts/`.** PI-directed. Copy, never move: the scheduler reads the operative copy from the run directory, but that directory is untracked scratch and gets cleaned, while the submit script is where the binary a run was bound to and its run-time hash assertion are written down. A log claiming a passed V0 gate with no archived submit script cannot show which executable produced the number. Signal: on 2026-08-23 a cycle nearly ran against the wrong binary because the materializer emits the LIVE build path by default. Updates `feedback_plot_scripts_canonical_in_phase_results`, which had said run drivers simply stay in CFS.

- 2026-08-22 (later): **Adds the three-tier script rule**: look in `use_cases/{Model}_{Case}/scripts/` for a canonical script TEMPLATE first, copy it into this phase's `phase_results/{stem}/` and ADAPT it there; write one from scratch when no template exists; a script's SECOND use is the trigger to promote it into `scripts/`. PI-directed, extended to every phase skill after the rule initially landed in only two. Does not conflict with "one canonical script per figure, never two copies" -- the canonical script stays with its figures, the canonical script TEMPLATE stays in `scripts/`. Evidence: 7 byte-identical duplicate script pairs measured across one site's phase_results folders. Checker `tools/check_case_script_tier.py`.

- 2026-08-18: **Routing forked BY MODEL.** The skill sent every Phase-5 experiment to `offline-testing-workflow`, which is CIME/FATES (`create_case.sh`, chained ADSP->RGSP->TRANS, `modify_fates_parameters.py`) and does not transfer to a standalone-binary model. EcoSIM now routes to the new `ecosim-run-workflow`. The failure this prevents is not the loud one (there is no `create_case.sh`, so the FATES path dies at once) but the quiet one: FATES conventions applied to EcoSIM -- one parameter surface, no namelist size limit, `sacct COMPLETED` read as success -- produce cases that run and score wrong. Signal: PI, on adding the EcoSIM skill.
- 2026-08-16: **Names the `plotting` skill for any figure this phase produces.** The link was
  one-directional — `plotting`'s own cross-references claimed the phase skills apply its
  conventions, while most phase skills never mentioned it, so a session could produce figures
  for a whole case without the conventions or the view-the-PNG check ever being loaded. That
  happened: three sets of Lusignan figures were made before it was invoked, and the first
  invocation immediately caught a stats box drawn over the data. PI-directed ("every phase
  needs the plotting skill").
- 2026-08-02: Log step now states the **living-record** contract (start at phase start, enrich as it runs —
  the operational detail is unrecoverable later), names **this phase's expected sections** so an omission is
  visible, and shows `set_phase_handshake()` so the chain is traceable. Full contract: `calibration-log`.
- 2026-07-15: Wired the Step-4 `set_position(current_phase="refinement")` state-advance (once results are extracted, so `resolve_next_action` resolves Phase 6). Ported from demo `d3cbbf5` (offline-workflow enforcement sweep).
- 2026-07-06: Added Step 0 — reset `skip_testing_count = 0` on Phase-5 entry (closes the inner loop for the
  cycle). Pairs with the Phase-6 middle-loop gate + Phase-4 inner-loop counter. Ported from demo `2d3f4b0`.
- 2026-07-02: Created — thin Phase 5 router mirroring `_run_testing()`; delegates execution to `offline-testing-workflow`, hands off to `phase6-refinement`.

## Log it as a LIVING record

`offline-testing-workflow` owns the mechanics; **the log is still yours**, and it starts when the
variants are submitted, not when the results land. The operational detail — job/array IDs, which
variants failed when the scheduler hiccupped, what was restarted — is unrecoverable a week later.
Full contract in `calibration-log`.

**Phase 5's expected sections** — `PhaseLogger` names any you leave empty:
Experiments Designed · Submission · Simulation Status · Monitoring Armed · Failures and Restarts · V0 Reproducibility Gate · Results Preview · Results Summary.

**Results Preview** is the load-bearing one: before trusting any result, show that each new test came
out sane. It pairs with the **V0 reproducibility gate** — V0 proves the variant reproduces its base,
the preview proves the variant itself is not nonsense.

```python
logger.set_phase_handshake(
    inherited_from="<phase4 log STEM> — the hypothesis + its success_criteria bar",
    handed_to="experiment results vs the bar (Phase 6 rules CONFIRMED/REFUTED against it)",
    next_action="<the one concrete thing Phase 6 should evaluate>")
```

## Before you finish

**Discipline self-review (automatic).** Before advancing the state, re-check the [`calibration-discipline`](../calibration-discipline/SKILL.md) items that apply to this phase. This is unprompted and per-phase — the user does not have to ask (memory `feedback_schedule_periodic_reviews_with_a_real_mechanism`).
