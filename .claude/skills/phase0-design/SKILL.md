---
name: phase0-design
visibility: public
category: phase
description: Run Phase 0 (DESIGN) of the A2MC calibration workflow as the offline agent — the human-in-the-loop analog of the orchestrator's `_run_design()`. Sample the parameter space (Morris/Sobol/LHS), materialize one FATES parameter file per case, generate + build + submit the ensemble, and arm monitoring. Use when the user says "design a new round", "set up the ensemble", "sample the parameters", "submit the Morris ensemble", "start a calibration round", "expand the parameter space (redesign)".
modes:
  requires_fates: false      # calibration-workflow phase skill; mode resolved at runtime via describe_mode
  nutrient_pathway: any
  scope: [calibration]
  summary: "Offline analog of online Phase 0 (design/sample/submit the ensemble). Applies in every calibration mode."
---

# Phase 0: Design & Submit (offline agent)

> **Driven by `calibration-goal`** — the run-to-convergence driver dispatches here when `WorkflowStateOffline.current_phase` routes to this phase; do the phase, then update + `save()` the state so the driver advances. Also runnable standalone (one phase).

The offline analog of the orchestrator's `_run_design()`. Online this is deterministic sampling +
submission; offline **you own the design decisions** the online loop takes from config — scheme,
trajectory count, which parameters vary, bounds, and whether this is a fresh round or a
redesign/replay. The underlying scripts are the same the online agent drives.

> **Floor, not ceiling.** This skill is the minimum to stand up a round the way the online agent
> would. Reconsidering the parameter list — what to add, what to drop and to what fixed value, and
> where each bound comes from — is **not** optional judgment: it is **Step 0.5, required for every
> Phase 0**. Beyond that floor you can do more: sanity-check the sampling against prior-round μ*
> before spending compute, or design a targeted sub-ensemble the fixed loop would never propose.
> Match the discipline (verify param existence, don't clobber the committed matrix, validate before
> submit), then exercise judgment about *what* to sample.

**Deliverable:** simulation jobs queued (ADSP→RGSP→TRANS dependency chains), `submission_manifest.json`
written, monitoring armed.

## Opening a NEW round (redesign, Phase 6 → 0, `calibration_round++`)

Arriving here from Phase 6 with the middle loop exhausted (or all candidates pinned at bounds) is the
**redesign** path — a whole new round on a corrected base, not another cycle. Stand it up in this order
**before** Step 1 (sampling); each round is a *superset* of the last, recorded, not an in-place edit:

0. **Gate first (authorization).** The redesign must be an explicit human-gated Phase-6 decision:
   `phase6_decision.decision == "redesign_6to0"` recorded on the **previous** round's
   `workflow_state_offline_r{RR}.json` and passing `validate_phase6_decision()`. Do NOT open a new round
   while the prior gate is still `null` (that is "closed at the gate, awaiting the PI", not "go"). The
   round's next-round plan (the round-summary report's plan section) is the design input.
0b. **READ WHAT THE PREVIOUS ROUND LEFT YOU — before designing anything.** This step is the arc's
   missing consumer: until 2026-08-25 this skill read the gate and started sampling, so a round could
   be designed with no input from the round that produced it. Three inputs, all of which exist by the
   time the gate clears:

   - **The previous round's OPEN-QUESTIONS list**, emitted by `round-housekeeping` step 4 and pointed
     at by `housekeeping.open_questions_path` in that round's state. Go through it item by item and
     state, for each, whether this design **answers, defers or drops** it. An item silently dropped is
     the failure this list exists to prevent.
   - **The SITE knowledge base**, `use_cases/{Model}_{Case}/memory/gained_knowledge/` — the per-case
     store, not the generic repo-root one:

     ```python
     from memory import MemoryManager
     m = MemoryManager("use_cases/{Model}_{Case}/memory/gained_knowledge")
     m.stats(); m.get_all_discoveries()          # what earlier rounds established
     ```

     **Read `failed_approaches` BEFORE proposing the parameter list.** A parameter an earlier round
     refuted with a named mechanism must not be re-added without saying why this time differs.
     Measured cost of skipping this: one round summary proposed re-adding **two** parameters that
     earlier rounds had already refuted, and both survived every checker because nothing in the
     round-close path opened a prior round. If `stats()` is all zeros, the previous round's
     housekeeping did not run — say so rather than proceeding as if the store were authoritative.
   - **The CROSS-ROUND parameter ledger** from `compare-calibration-rounds`, which answers "what did
     every earlier round do with parameter X" in one table.

   **The worked precedent, and this contract is derived from it rather than invented.**
   `use_cases/EcoSIM_BioCON/reports/20260813a_Pre_R3_Summary/Pre_R3_Summary_Report.md` is the one
   existing instance of this synthesis — written **by hand, with no skill behind it**, which is the
   argument that the work is necessary enough to do unprompted and unsupported enough not to recur.
   Its shape maps onto the three inputs above: *"Where R2 left off"* (the prior round's state), the
   investigations that settled what the round could not decide from its own data, *"R3's design
   decisions"*, the parameter list, and **§8 "Open items: named, not silently dropped"** — whose
   title states the whole point of step 0b. Read it as the model. Two things in it are now out of
   contract: it opens with a `## Reader's key` glossary block, which `write-report` removed on
   2026-08-24 (define terms inline on first use instead), and its open items are prose rather than
   the table with *what would settle it* and *what it blocks*.

1. **Per-round config wrapper `{site}_config_r{N}.sh`.** Rounds do NOT get a separate full config — they get
   a thin wrapper that **sources the base `{site}_config.sh` and overrides only the round-specific env**:
   `A2MC_ENSEMBLE_NAME` (→ `R{N}_...`), `A2MC_PARAM_LIST_FILE` (→ the R{N} list), **`A2MC_BASE_PARAM_FILE`
   (→ the round's corrected/best base, NOT the prior dead/stale base)**, and the output/param/case-scripts
   paths. Override AFTER sourcing. (Precedent: demo Kougarok `kougarok_config_r3.sh`/`_r4.sh`/`_r5.sh` —
   note the demo wrappers are **unpadded** `_r{N}`, while the offline state file below is **padded** `_r{RR}`.)
2. **The R{N} parameter artifacts** (the point of the redesign — the changed parameter set): a new
   param-list CSV implementing the plan + its salib_problem, designed per **Step 0.5** below. Step 1 then
   generates the Morris matrix from this CSV. Never reuse the prior round's committed matrix (Step-1
   overwrite footgun).
3. **Add round N to `calibration_rounds.yaml`.** With the R{N} config sourced, run the round-record generator
   (`tools/generate_calibration_rounds.py` for FATES, `scripts/generate_adapter_calibration_rounds.py` for an
   adapter model) `--round N --write` — it derives the block from the config + CSV + targets; then hand-fill
   the preserved narrative (`rationale`, `changes_from_previous`). Validate with the paired checker.
4. **New offline state `workflow_state_offline_r{RR}.json`.** A fresh per-round singleton
   (`tools/workflow_state_offline.py`) with `calibration_round = N`, `current_phase = "design"`. The driver
   then resolves the next action against the new round.
5. **Then proceed to Step 1** below on the new round (sample → materialize → validate → submit) with the
   R{N} config sourced — a **fresh** sensitivity screen on the corrected base (a prior round's μ* sampled
   around a stale/dead base is void). Log the redesign rationale in Step 5's `## Parameter Set and Bounds`.

> **Adapter models (non-FATES, on adapter-kit).** The end-to-end procedure, including the traps
> this summary cannot carry, lives in each model's OWN run skill — **`ecosim-run-workflow`** (the
> 4096-byte namelist buffer, three parameter surfaces, pre-submission validation),
> **`pflotran-run-workflow`** (the deck IS the parameter file, `*-mas.dat` scoring, the 806-hour
> observation offset), **`ats-run-workflow`** (XML ParameterList by path).
> Resolve the model FIRST
> (`$A2MC_MODEL` / `tools/describe_mode.py`). Steps 1–3 below name the FATES/ELM scripts; a non-FATES
> adapter uses **PARALLEL scripts** (they IMPORT the shared SALib sampler / dispatch through the
> `ModelBackend`; they never edit `create_parameter_sample.py`, which is byte-locked to main, docs/38):
> - **Step 1 (sample):** `scripts/create_adapter_parameter_sample.py` (NOT the shared sampler) reads the
>   EXPLICIT-COLUMN param list (`name` + `pft` [+ `organ`] — the official name kept SEPARATE from the
>   PFT/organ id; RULE + `use_cases/TEMPLATE/parameters/parameter_list_template.csv`) via
>   `parse_pft_param_list`, building the canonical id `{name}_{pft}`, then reuses the shared
>   `sample_morris`/`sobol`/`lhs` + writers — **plus one method the shared sampler does NOT have:**
>   **`sobol_seq`, the scrambled Sobol' SEQUENCE.** So the adapter path offers FOUR methods where
>   the FATES path offers three. `sobol` and `sobol_seq` are DIFFERENT DESIGNS, not a flag on one:
>   `sobol` is the SALTELLI construction (N(2P+2) rows, cross-sampled A/B/AB_i, for variance
>   decomposition), `sobol_seq` is the raw low-discrepancy sequence (exactly N rows, space-filling,
>   for surrogate training). Of Saltelli's N(2P+2) points only 2N are independent, so every held-out
>   AB_i point has a training neighbour one coordinate away and a surrogate cross-validates
>   OPTIMISTICALLY while interior coverage stays thin — right for estimating indices, wrong for
>   training. **A `sobol_seq` round has no SALib analyzer**: neither `sobol.analyze` nor
>   `morris.analyze` applies, and neither ERRORS — see `scripts/given_data_sensitivity.py` and
>   `phase1-exploration`.
> - **Step 2 (materialize):** `scripts/materialize_adapter_ensemble.py [--baseline] [--dry-run]` maps
>   each matrix row → `{canonical_id: value}` (same parser → column j ↔ names[j]) →
>   `backend.write_parameter_file(base, edits, out)` (the model's OWN parameter surface; EcoSIM = the
>   pft NetCDF) → `backend.create_case` (one self-contained case dir). NOT
>   `generate_parameter_files.py`/`modify_fates_parameters.py`. `--baseline` also writes the V0 case.
> - **Step 3 (validate → submit):** FIRST the pre-submit gate — for a NetCDF-parameter-file model,
>   `scripts/validate_adapter_ensemble.py`
>   (parallel to FATES's `validate_submission_plan.py`; re-derives every case's edits from the matrix and
>   asserts the on-disk param file / namelist / submit.sh match — value·parameter·PFT·bounds·baseline,
>   **and dry-runs the ensemble submit script's task dispatch** with `srun` stubbed — the check that
>   catches a broken array dispatcher before it fails every task, `20260716a`) + `tools/model_check_input_compat.py`
>   (input↔binary). THEN submit — each case is a SERIAL standalone run (EcoSIM: `srun -n 1`, OMP=1), so
>   parallelism is ACROSS cases: prefer a **SLURM job array** over 821 individual `sbatch`. The site ships one
>   at `use_cases/{Model}_{Case}/case_template/submit_ensemble_array.sh` — `sbatch …/submit_ensemble_array.sh`
>   (`--array=0-N%<conc>`; `--array=0` for the V0 baseline first). NO CIME, NO ADSP→RGSP→TRANS chain, NO
>   shared `bld/`. (`backend.submit_ensemble` — loop-`sbatch` per case — is the fallback; the array is
>   the efficient default. `cpus-per-task` adds NO speed to a 1-cell run — it's memory/node-slice only.)
> **PFLOTRAN differs from EcoSIM on four of the steps above — verified 2026-08-27 while running the
> first PFLOTRAN Phase 0, not inferred:**
> - **Step 1 (sample)** — the same `create_adapter_parameter_sample.py`, but the `pft` column carries a
>   NAMED sub-address, not an integer (`RATE_CONSTANT_Glass_FB`, `M_all3`, `PERM_ISO_Bolitic`). A tool
>   that coerces that axis to an int raises: `tools/param_spec.py::load_param_spec` does exactly that
>   and is the WRONG loader here; use `parse_pft_param_list`.
> - **Step 2 (materialize)** — the same `materialize_adapter_ensemble.py`, but only since 2026-08-27.
>   Before that it probed NetCDF variable names unconditionally and raised `OSError: NetCDF: Unknown
>   file format` on a text input deck, so no PFLOTRAN ensemble could be built at all.
> - **Step 3 (validate)** — **NOT `validate_adapter_ensemble.py`.** That script is NetCDF- and
>   integer-PFT-shaped throughout and cannot parse one PFLOTRAN parameter id. Use the parallel
>   **`scripts/validate_pflotran_ensemble.py`**, whose "nothing else was written" check is an
>   exhaustive line diff against the base deck. And note `tools/model_check_input_compat.py --model
>   pflotran` reports **N/A** — the spec declares no input-reader compat contract — so it is a
>   skipped check, **not a passed one**; do not read its exit 0 as a gate.
> - **Submission** — **the default for a large adapter round is
>   `scripts/submit_adapter_ensemble_batched.py`, not a bare loop and not an array.** It submits
>   per-case jobs in QUEUE-AWARE WAVES against the 5000-job `QOSMaxSubmitJobPerUserLimit`, with a
>   reserve for the account's other lanes, a model-dependent jobs-per-case multiplier (FATES's
>   ADSP→RGSP→TRANS chain is ×3; an adapter is ×1, and inheriting the FATES form under-uses the queue
>   threefold), and idempotency on `job_id.txt` so an interrupted run resumes by re-invocation. It is
>   what launched `PFLOTRAN_miniLEO R1` (4,097 cases, log `20260827c`), surviving a mid-wave kill at
>   52 of 800 submissions because of that idempotency, and it publishes a state file matching
>   `tools/check_watcher_state.py`'s contract so the submitter's own death is detectable.
>   A **job-array template now exists** (`use_cases/PFLOTRAN_template/case_template/submit_ensemble_array.sh`,
>   with miniLEO's filled copy beside its `BASE_CASE_MANIFEST.md`), but it is the narrow alternative,
>   not the default: an array buys one job id and low submission-side load, and costs **per-case
>   submit-script provenance**, which is the only record of which binary a run was bound to
>   ([[feedback_bind_runs_to_archived_binaries]]). Whether an array even relieves the submit ceiling
>   here is **unverified** — `MaxArraySize` is 65000, but if pending array tasks count individually
>   against `MaxSubmitJobsPU` it gives no relief at all.
>
> - **Scoring** uses the backend extraction (`reduce_target` → `backend.reduce_ecosystem` for
>   ecosystem-level targets). Step 4 (monitoring) is model-agnostic. Worked example: `20260715d/e` (EcoSIM R1).

## Step 0.5 — design the parameter set (REQUIRED, every Phase 0)

**Do this before Step 1, every round — not only a redesign.** Step 1 samples whatever the CSV says, so
this is the decision that determines everything after it. Round 1 is not exempt: it must equally state
what is deliberately *not* calibrated and where its bounds came from. Answer all four **in the log**
(§Step 5, `## Parameter Set and Bounds`), not just in the round record.

**ADD — each new parameter, with the evidence for it.** Prior-round μ*, a Phase-3 diagnosis, or a
mechanism the previous screen never varied. A lever nothing measured is a guess. R2's whole soil-BGC
finding is the pattern: the surface that decided `Fs` was never in the plant-trait list.

**DROP — each removed parameter, AND the fixed value it now takes, AND where that value comes from.**

> ⚠️ **A dropped parameter does NOT fall back to the CSV `default` column** — that column is
> documentation. The backend copies `$A2MC_BASE_PARAM_FILE` and applies only the matrix edits
> (`ModelBackend.write_parameter_file`), so **dropping a parameter transfers control of its value to the
> base file.** Verify the base carries the value you intend, and say so in the log.
>
> This has bitten twice. `20260716a`: `RCS`/`IEBTYP`/`ISNTYP`/`PhiMEAN` were not in EcoSIM's 40-param
> list, so they "flow from the base file AS-IS into every case" — one a 10× discrepancy the input checker
> did not flag, costing a decisive mod-base test to rule out. And the api-31→api-43 port, where 61 of 159
> defaults changed ([[feedback_port_tuned_base_param_file_across_versions]]: *the calibration list can't
> protect them*).
>
> Check it, don't assume it: read the value straight out of the base file for every parameter you drop.

**BOUNDS — record `bound_source` for every parameter**, in the canonical template's vocabulary. There are
**FIVE** prefixes and every entry must start with one of them (see
`use_cases/TEMPLATE/parameters/parameter_list_template.csv`, which is the source of truth, and
`tools/param_spec.py`, which carries the field onto `ParamSpec`):
`measured:` (this project's own measurements — name the dataset and the statistic) ·
`literature:` (MUST carry a citation AND a resolvable DOI) ·
`database:` (TRY / FRED / FLUXNET and similar — name the database, the record, and its DOI) ·
`prior_round:` (carried from an earlier round — name the round and what narrowed it) ·
`provisional:` (no evidence yet — say so and give the basis).
**Never leave the cell blank:** a blank reads as "not recorded", which the next reader cannot distinguish
from a published range. Add `source-verified` when the parameter's MEANING and UNITS were confirmed against
the model source, not just its name.
A bound still marked `provisional:` from a prior round is a debt — refine it or re-affirm it explicitly.
Re-centring a bound silently discards its provenance ([[reference_param_bounds_sourcing_pipeline]]:
a naive ±50% is a provisional *seed*, not a bound).

**SITE PLAUSIBILITY — for each range, is it physically achievable at THIS site?** Tier-G traits can come
from TRY/FRED; Tier-S site conditions need per-site measured error bars. A knob that only reaches its
target outside measurement uncertainty is a **finding, not a calibration** — say so rather than sampling
it quietly. (`20260730a`: reaching observed soil respiration needed the soil-carbon pool at ×6, "far
outside any plausible measurement uncertainty on a soil-carbon stock".)

## Step 1 — sample the parameter space (parameter-file prep — no simulations)

`phases/phase0_design/create_parameter_sample.py --method {morris|sobol|lhs}` reads
`$A2MC_PARAM_LIST_FILE` (name + bounds) and writes the ensemble matrix (`$A2MC_ENSEMBLE_MATRIX_FILE`)
and SALib problem (`$A2MC_SALIB_PROBLEM_FILE`). Morris: `--trajectories T` (N = T×(P+1)).

> **Adapter parallel (non-FATES):** `scripts/create_adapter_parameter_sample.py` — same CLI/output,
> but reads the explicit `name`+`pft` list via `parse_pft_param_list` (canonical id `{name}_{pft}`) and
> imports the shared SALib sampler. See the adapter callout above.

> **Footgun — matrix overwrite.** `$A2MC_ENSEMBLE_MATRIX_FILE` for Kougarok points at the
> **committed, byte-stable 4890-set matrix the manuscript depends on**. To regenerate without
> clobbering it, write to a scratch path (`--output-matrix`) or repoint the env var to a fresh
> round file first.

**Redesign / replay** (reuse a prior round's NC dir instead of fresh sampling):
`apply_param_override.py` (global override, e.g. R5's `prescribed_puptake=1.0` onto R3's NCs) or
`create_subset_replay.py` (top-N replay preserving source case numbers).

## Step 2 — materialize per-case parameter files (parameter-file prep — no simulations)

`phases/phase0_design/generate_parameter_files.py` reads the X matrix + `$A2MC_BASE_PARAM_FILE` and
writes one parameter file per row into `$A2MC_PARAM_DIR` (pattern `$A2MC_PARAM_PATTERN`, `{N}`
placeholder). It is **method- and format-agnostic** (JSON at api-43+, NetCDF at api-31 and earlier)
and dispatches to `tools/modify_fates_parameters.py` for the per-parameter edits. Verify file
count = N_sets.

> **Adapter parallel (non-FATES):** `scripts/materialize_adapter_ensemble.py [--baseline] [--dry-run]`
> — maps each matrix row → `{canonical_id: value}` → `backend.write_parameter_file` → `backend.create_case`
> (one self-contained case dir: param file + runfile.nml + submit.sh), instead of `generate_parameter_files.py`.
> `--baseline` writes the unperturbed V0 case; `--dry-run` reports the target layout. Files only, no submit.

> **Footgun — column↔parameter mapping + file format.** The X-matrix column order must match the site
> parameter list; `build_param_lookup()` in `tools/modify_fates_parameters.py` maps each shorthand →
> FATES name + PFT + organ. Confirm `tools/describe_mode.py` shows the milestone you expect so the
> right parameter-file format (JSON vs NetCDF) is written. Never assume a column's meaning.

## Step 3 — generate scripts, build, submit the simulations

`phases/phase0_design/submit_phase0.py --start 1 --end N --dry-run` first (preview), then `--submit`.
It (3a) writes per-case scripts via `tools/create_case.sh --write-script`, (3b) auto-validates via
`tools/validate_submission_plan.py`, (3c.1) builds ONE case fresh (~30 min), (3c.2) runs the rest in
`--batch-size` parallel batches reusing the build's `bld/`. Non-sequential rounds: `--cases-file`.

> **Adapter parallel (non-FATES):** the pre-submit gate is **the one for YOUR model**, not one shared
> script — `scripts/validate_adapter_ensemble.py` for a NetCDF-parameter-file model (EcoSIM), and
> `scripts/validate_pflotran_ensemble.py` for PFLOTRAN, whose ids the former cannot even parse (see
> the adapter block above, Step 3). Either re-derives every case's edits from the matrix and asserts
> the on-disk artifacts match. Plus `tools/model_check_input_compat.py` (input↔binary) — which returns
> **N/A** for a model declaring no compat contract, so read it as skipped rather than passed. Run what
> applies green before `backend.submit_ensemble`.

> **Footgun — build-case reuse.** All cases share the build case's `bld/`. If the build case fails,
> every dependent case is orphaned — confirm it completed before the batch. Restart it separately,
> then `--skip-build-case --build-case N`.

## Step 4 — arm monitoring, don't idle-wait

Launch `tools/ensemble_auto_monitor.sh` (queue polling + auto extraction kick + **extraction-progress
ensemble plots** — it triggers `tools/regen_ensemble_milestone_plot.sh`, a thin wrapper over
`tools/plot_ensemble_cases.py`, each time the extracted-case count crosses a checkpoint →
`R{N}_{combined,TRANS}_{count}cases_ensemble.png`, [[reference_ensemble_combined_plot_pipeline]]; these are
in-flight progress snapshots of the running ensemble, not a graduated result),
then hand monitoring setup to `arm-hpc-monitoring` (CLAUDE.md Rule #6). Point-in-time completion:
`tools/diagnose_ensemble_status.py --cases 1-N` (writes completed/incomplete lists + a validated
restart script). Infrastructure failures → `restart-failed-jobs`; model failures need a fix first.

## Step 5 — log it and hand off

> **The log is a LIVING record — start it now, enrich as the phase runs.** Not an end-of-phase
> write-up: the operational detail (job/array IDs, which cases failed, what was restarted) is
> unrecoverable a week later. Full contract in `calibration-log`.
>
> **This phase's expected sections** — `PhaseLogger` names any you leave empty:
> Parameter Set and Bounds · Sampling Design · Cases Materialized · Submission · Simulation Status · Monitoring Armed · Failures and Restarts · Verification Plots.
>
> **`Parameter Set and Bounds` carries Step 0.5** — pass it via `log_design(parameter_set_changes=...)`
> (Markdown). It is emitted only when supplied, so an omission shows up in the gap list rather than as an
> empty heading. This is the section the add/drop/bounds/plausibility decision lands in; the round record
> (`calibration_rounds.yaml` `rationale` / `changes_from_previous`) is a summary, not a substitute.
>
> **Set the handshake before the `log_*` call**, so the chain is traceable:
> ```python
> logger.set_phase_handshake(
>     inherited_from="<predecessor log STEM> — what it concluded / asked of this phase",
>     handed_to="<what Phase 1 receives; mirror the reasoning/schemas.py field names>",
>     next_action="<the one concrete thing Phase 1 should do>")
> ```
> The log also carries `## Reasoning chain`, rebuilt from `workflow_state_offline` — so keep that
> state updated with the FINDING, not a label; the chain is only as good as what each phase wrote.


Log via `calibration-log` (phase log → `PhaseLogger.log_design`): scheme, N cases, param dir,
manifest hash, plus Step 0.5 via `parameter_set_changes=` (the redesign rationale lives there, not in a
second place). **Offline logging convention:** set **`A2MC_AGENT_MODE=offline`**
so the log lands FLAT at `use_cases/{Model}_{Case}/memory/logs/{YYYYMMDDx}_phase0_design_r{RR}_{descriptor}.md`
(docs/31) — NOT the online `{session_id}/phase0_design/` nested path. **Hand off** to `phase1-exploration`
once TRANS (or the adapter's single run) is >95% complete. **Advance the driver state:**
`st.set_position(current_phase="exploration")`; `st.save()` (`tools/workflow_state_offline.py` — the offline
analog of the online phase transition, so `resolve_next_action` picks up `exploration` next). (Arrived here
from Phase 6 with all candidates pinned at bounds? That's the 6→0 redesign — start a new
`calibration_round` per "Opening a NEW round" above, and widen bounds / add parameters through Step 0.5,
which is where a pinned bound has to be re-sourced rather than just stretched.)

> **Design can be PREPARED but HELD.** If the base case doesn't even establish (e.g. a dead adapter run
> with no gradient to sample), the round is designed (targets + params + bounds + extraction) but **not
> submittable** — do NOT force an ensemble. Record the hold: keep `st.set_position(current_phase="design")`
> and add a priority-1 open thread naming the precondition to clear
> (`st.add_thread("<blocker>", summary=..., next_action=<what unblocks submit>, priority=1)`); `save()`.
> The driver then surfaces that thread instead of a phantom "submit" step. (EcoSIM R1 sat here, held on a
> live/compounding base case — `20260715d`.)

## Who owns ensemble submission (read before reaching for another skill)

**This skill owns HOW an ensemble reaches the scheduler, including the choice of launch mode.**
Four skills touch this surface and it used to be unclear which decided what, so a launch-mode
question had no home and the reasoning lived in a case folder instead. The split is now:

| question | skill |
|---|---|
| *which launch mode, what throttle, will this even fit under the submit ceiling* | **`phase0-design`** (here, Step 3) |
| how does THIS model build/stage/run a case | the model's runner — `ecosim-run-workflow`, `pflotran-run-workflow`, `ats-run-workflow` |
| how do I watch it once it is running | `arm-hpc-monitoring` |
| how do I recover the cases that died | `restart-adapter-ensemble` (non-CIME) / `restart-failed-jobs` (CIME) |

- **Reciprocal skills** — the skills that hand off to or from ensemble submission, and which must
  name `phase0-design` back so the pointer cannot rot into a one-directional claim:
  `ecosim-run-workflow`, `pflotran-run-workflow`, `arm-hpc-monitoring`, `restart-adapter-ensemble`, `restart-failed-jobs`,
  `calibration-goal`. **`tools/check_skill_registry.py::reciprocity_check` enforces this** and fails
  the pre-commit gate if any of them stops naming this skill — the same mechanism `plotting` uses,
  and for the same reason: a one-directional cross-reference is invisible from the side that needed
  to read it. Measured 2026-08-21, before this bullet existed: `arm-hpc-monitoring` and
  `restart-adapter-ensemble` were each already one-directional with this skill.



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
- **Monitoring the in-flight ensemble** → `arm-hpc-monitoring`. **Failed jobs** → `restart-failed-jobs`.
- **Rebuilding a new site/model's knowledge base first** → `build-rag-from-scratch`.
- **Next:** `phase1-exploration` (extract Y matrix + Morris sensitivity).

## Changelog

- 2026-08-27 (later): **The PFLOTRAN submission bullet was stale within hours of being written, and its replacement names the real default.** It said miniLEO had no job-array template and that an array was 'an open item, not a solved one' — both written before reading that round's launch log. The actual default is `scripts/submit_adapter_ensemble_batched.py` (queue-aware waves, a reserve, a model-dependent jobs-per-case multiplier, idempotency on `job_id.txt`), which this skill did not mention at all despite owning the launch-mode decision; it is what put 4,097 cases on the scheduler. A template array submitter now also exists, repositioned as the narrow alternative with its cost stated (per-case binary provenance) and one property still unverified (whether an array relieves `MaxSubmitJobsPU`). Found by the 3-hourly self-review, which is the mechanism working: a skill claim invalidated by the same day's work.

- 2026-08-27: **The adapter block names every adapter model's run skill, and states where PFLOTRAN
  DIFFERS from EcoSIM on four steps** (PI-directed, at the start of the first PFLOTRAN campaign).
  The block named EcoSIM alone and presented `materialize_adapter_ensemble.py` and
  `validate_adapter_ensemble.py` as *the* adapter path without qualification — and on the first real
  PFLOTRAN Phase 0 the first crashed on a text deck and the second could not parse a single
  parameter id. A summary that looks complete is the more dangerous kind, so the differences are
  stated rather than left to be discovered: the named grouping axis, the materializer fix, the
  parallel validator, the input-compat check that reports N/A rather than passing, and the absent
  job-array template.

- 2026-08-23 (corrected same day): **The job-script archive rule does NOT apply to Phase 0, and was removed from this skill.** PI-corrected. Phase 0 materializes an ENSEMBLE — one R3 round is 59,393 cases — and its submit scripts are generated from the machine and round config by the materializer, so archiving them would be enormous and redundant: the config plus the generator reproduces them exactly. The rule belongs to Phase 5 alone, whose handful of variants are hand-designed and hand-repointed onto a specific binary, so nothing else records what actually ran. Originally added here on the mistaken assumption that any phase putting simulations on a scheduler needed it.
- 2026-08-23 (superseded): **Phase 0 and Phase 5 archive their JOB SCRIPTS into `phase_results/{stem}/submit_scripts/`.** PI-directed. Copy, never move: the scheduler reads the operative copy from the run directory, but that directory is untracked scratch and gets cleaned, while the submit script is where the binary a run was bound to and its run-time hash assertion are written down. A log claiming a passed V0 gate with no archived submit script cannot show which executable produced the number. Signal: on 2026-08-23 a cycle nearly ran against the wrong binary because the materializer emits the LIVE build path by default. Updates `feedback_plot_scripts_canonical_in_phase_results`, which had said run drivers simply stay in CFS.

- 2026-08-22 (later): **Adds the three-tier script rule**: look in `use_cases/{Model}_{Case}/scripts/` for a canonical script TEMPLATE first, copy it into this phase's `phase_results/{stem}/` and ADAPT it there; write one from scratch when no template exists; a script's SECOND use is the trigger to promote it into `scripts/`. PI-directed, extended to every phase skill after the rule initially landed in only two. Does not conflict with "one canonical script per figure, never two copies" -- the canonical script stays with its figures, the canonical script TEMPLATE stays in `scripts/`. Evidence: 7 byte-identical duplicate script pairs measured across one site's phase_results folders. Checker `tools/check_case_script_tier.py`.

- 2026-08-18: The adapter-model blockquote now points at **`ecosim-run-workflow`** for the end-to-end EcoSIM procedure. The step list here carries the parallel SCRIPTS but not the traps (the 4096-byte namelist buffer, the three parameter surfaces, pre-submission validation), and a summary that looks complete is the more dangerous kind. Signal: PI, on adding the EcoSIM skill.
- 2026-08-16: **Names the `plotting` skill for any figure this phase produces.** The link was
  one-directional — `plotting`'s own cross-references claimed the phase skills apply its
  conventions, while most phase skills never mentioned it, so a session could produce figures
  for a whole case without the conventions or the view-the-PNG check ever being loaded. That
  happened: three sets of Lusignan figures were made before it was invoked, and the first
  invocation immediately caught a stats box drawn over the data. PI-directed ("every phase
  needs the plotting skill").
- 2026-08-07: Added **Step 0.5 — design the parameter set (REQUIRED, every Phase 0)**, and the matching
  logged section `Parameter Set and Bounds` (new optional `log_design(parameter_set_changes=...)`, emitted
  only when supplied so the gap check can still fire; `_EXPECTED_SECTIONS[0]` updated, parity gated by
  `check_skill_registry.py::phase_section_check`). The whole design decision had been **one clause** — *"add
  dominant levers, drop insensitive ones, recenter/widen bounds"* — with no procedure, and the log had no
  section to carry it. Signal: PI correction (2026-08-07) naming four unanswerable questions, plus a trap
  that had already fired twice — a **dropped parameter does not take the CSV `default`; it takes whatever
  `$A2MC_BASE_PARAM_FILE` holds** (`20260716a`, 4 non-calibrated EcoSIM params flowing from the base as-is,
  one a 10× discrepancy no checker flagged; and the api-31→api-43 port's 61-of-159 default drift). Also
  brings `bound_source` provenance into this skill — it was required by `onboard-case`/`onboard-model` at
  list *creation* and silently optional at list *revision*, which is when re-centring discards it — and adds
  the site-plausibility question (`20260730a`: a ×6 soil-carbon pool is a finding, not a calibration).
  **Scoped to every Phase 0, not only redesigns** (PI): `20260716a` was a round-1 failure.
- 2026-08-02: Log step now states the **living-record** contract (start at phase start, enrich as it runs —
  the operational detail is unrecoverable later), names **this phase's expected sections** so an omission is
  visible, and shows `set_phase_handshake()` so the chain is traceable. Full contract: `calibration-log`.
- 2026-07-18: Added **"Opening a NEW round (redesign, Phase 6 → 0)"** — the explicit pre-Step-1 setup to
  stand up round N+1: the redesign gate (prior round's `phase6_decision == redesign_6to0`), the per-round
  config **wrapper** `{site}_config_r{N}.sh` (sources base + overrides ensemble/param-list/**base-param-file**),
  the R{N} param-list CSV + salib_problem, adding round N to `calibration_rounds.yaml` (FATES vs adapter
  generator), and a fresh `workflow_state_offline_r{RR}.json` — then sample on the corrected base. Distilled
  from the demo Kougarok multi-round `calibration_rounds.yaml` (r3/r4/r5 wrappers) + the EcoSIM R1→R2 plan.
- 2026-07-16: Step-3 submit is now a **SLURM job array** (`use_cases/{Model}_{Case}/case_template/submit_ensemble_array.sh`) — parallelism is ACROSS cases (each a serial run; `cpus-per-task` is memory-only), preferred over 821 individual `sbatch` (`backend.submit_ensemble` = fallback). The pre-submit gate now also **dry-runs the submit-script dispatch** (`srun` stubbed) — the check that would have caught the brace-substitution bug that failed every array task (`20260716a`).
- 2026-07-15: Added the adapter **pre-submit gate** `scripts/validate_adapter_ensemble.py` (parallel to FATES's `tools/validate_submission_plan.py`) to Step 3 + the adapter callout — re-derives every case's edits from the matrix and asserts the on-disk param file/namelist/submit.sh match (value·parameter·PFT·bounds·V0·input-paths), run green with `tools/model_check_input_compat.py` before `backend.submit_ensemble`. `20260715f` (EcoSIM R1: 821/821 pass).
- 2026-07-15: Named the **parallel adapter scripts** alongside the FATES ones — Step 1 `scripts/create_adapter_parameter_sample.py` (explicit `name`+`pft` list via `parse_pft_param_list`, imports the shared SALib sampler) and Step 2 `scripts/materialize_adapter_ensemble.py` (matrix row → `backend.write_parameter_file` → `create_case`, `--baseline` V0). Rewrote the adapter callout (the old "shorthand `VCMX_<pft>`" + shared-`parse_param_list` pointers were stale — adapters now use the explicit-column format + the parallel scripts, no edit to the byte-locked shared sampler). `20260715e`.
- 2026-07-15: Three adapter-kit refinements from the EcoSIM R1 onboarding (`20260715d`): (1) an **adapter-model
  (non-FATES) branch** — Steps 2–3 dispatch through the `ModelBackend` (`write_parameter_file` on the model's
  own param surface + `create_case` single standalone run, no CIME/ADSP→TRANS/shared-`bld/`), not the FATES
  path; (2) the **offline logging convention** made explicit (`A2MC_AGENT_MODE=offline` → flat
  `memory/logs/{stem}.md`, not the online nested `{session_id}/phase0_design/`); (3) a **PREPARED-but-HELD**
  note — a round can be designed yet un-submittable when the base case doesn't establish (record via
  `current_phase="design"` + a priority-1 open thread).
- 2026-07-15: Wired the explicit `set_position(current_phase="exploration")` state-advance in the handoff step (the offline program-counter advance main's generic banner lacked). Ported from demo `d3cbbf5` (offline-workflow enforcement sweep).
- 2026-07-15: Named the concrete progress-plot tool chain in Step 4 — `ensemble_auto_monitor.sh` → `regen_ensemble_milestone_plot.sh` → `plot_ensemble_cases.py` at each extracted-case checkpoint (was vague "milestone plots"); reworded to **extraction-progress ensemble plots** (in-flight snapshots, not a graduated result). Ported from demo `cd14d24`/`b85fc2c`, adapted — main has no promote-milestone layer to contrast against.
- 2026-07-02: Created — offline Phase 0 routine mirroring `_run_design()`; drives create_parameter_sample → generate_parameter_files → submit_phase0, delegates monitoring/restart, hands off to `phase1-exploration`.

## Before you finish

**Discipline self-review (automatic).** Before advancing the state, re-check the [`calibration-discipline`](../calibration-discipline/SKILL.md) items that apply to this phase. This is unprompted and per-phase — the user does not have to ask (memory `feedback_schedule_periodic_reviews_with_a_real_mechanism`).
