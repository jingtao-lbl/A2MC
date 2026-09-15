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
   - **The MODEL knowledge base**, `docs/<model>-knowledge-base/` — what a parameter, dimension or
     mechanism IS, before you write a bound for it. **KB first, source to confirm (PI, 2026-09-05):**
     grep it with `git grep -i <term> -- docs/<model>-knowledge-base/` even with no RAG profile
     active. It usually carries the `file:line` you were about to go find, plus context the source
     does not — which axis a dimension belongs to, which of two similarly-named axes applies, what a
     prior round measured. Read the source to CONFIRM; it stays ground truth on what the model DOES.
     Measured 2026-09-05: a session reconstructed the EcoSIM `micresb` slot semantics from Fortran over several turns, while `docs/ecosim-knowledge-base/ecosim-codebase-wiki-2dea74d9/microbial_bgc/index.md:133` stated it in one line WITH the same `MicBGCPars.F90:178-179` citation -- and additionally recorded that the 2-slot necromass axis is NOT the 3-slot living-biomass axis, a distinction the source read missed and which turned out to matter. The cost of skipping it: a wrong root-cause diagnosis and two fixes that treated symptoms. 

     **STAGE MATTERS, AND THIS IS THE CALIBRATION-STAGE RULE (PI, 2026-09-06).** While ONBOARDING a model the KB does not exist yet, source is the only recourse, and [[feedback_param_description_can_lie_verify_in_source]] governs: trace the read, then the internal variable, then its usage, especially before setting a bound. **At CALIBRATION stage the case is set up and the KB is assumed well-built, so the KB is where you START and it usually hands you the citation. It does NOT replace verifying in source: a KB page tells you what a thing IS, and only the code settles what it DOES -- or, just as often, what is ABSENT from it, which no page can state.** Query all five surfaces FIRST, then confirm in source. If you are in the source to LEARN what a parameter does rather than to CONFIRM what the KB told you, stop and name which it is: either you skipped the KB, or the KB has a gap. **A gap is a BUILD TASK** (rebuild the wiki, extend the curated seed, curate the round's findings at round close) and not something to route around every cycle. Full rule: [[feedback_full_mechanism_picture_before_designing_an_experiment]].

     **THE KB IS FIVE SURFACES, NOT ONE, AND THEY ARE NOT INTERCHANGEABLE. QUERY ALL FIVE, not the first one or two that answer.** They are: the **codebase wiki** `docs/<model>-knowledge-base/<model>-codebase-wiki-<commit>/` (`git grep -i <term> -- docs/<model>-knowledge-base/`, which works with no RAG profile active), the **RAG vector index** `rag/chroma_db/<profile>/` and the **knowledge graph** `rag/graphs/<profile>.json` (both via `HybridRetriever`), the **MODEL-level adaptive memory** `memory/<model>/gained_knowledge/`, and the **SITE-level adaptive memory** `use_cases/{Model}_{Case}/memory/gained_knowledge/`. The last two are the ones that get forgotten and they are populated: 21 entries for EcoSIM at model level, 28 for one case at site level, on 2026-09-05. Measured the same day on ONE parameter, `SPORC`: the knowledge-graph node carried a one-line description and units but no bounds, no code location and no mention of the two-slot axis, while the codebase wiki carried the slot semantics, the defaults AND the `MicBGCPars.F90` citation. Concluding "the KB does not have it" from the thin surface would have been wrong, so check the surfaces that hold that KIND of knowledge rather than the first one you open.

     **The curated overlay lives in DIFFERENT PLACES by model family, and looking in the wrong one reads as "it does not exist".** An adapter model keeps it at `models/<model>/curated_seed.yaml`; only the FATES profiles use `rag/data/curated_relationships_<profile>.yaml`. The active profile's `rag/metadata/<profile>.json` names the file its graph was built from, so read that rather than guessing the path. Measured 2026-09-06: `models/ecosim/curated_seed.yaml` was declared missing on the strength of an `ls rag/data/`, and it is human-authored and is what built the EcoSIM graph.

     **MEASURED COST OF QUERYING ONE SURFACE INSTEAD OF FIVE (EcoSIM_TeRaCON R1, seven cycles, 2026-09-06).** The graph stated `parameter:RMOM --controls--> mechanism:Microbial_Maintenance_Respiration --affects--> output:CO2_SEMIS_FLX_col`, the exact variable that case scores as `Fs`, and named 12 parameters for that output where a rank-correlation screen surfaced 4. The curated seed's `RMOM` entry carried the mechanism, the `NitroPars.F90:209` citation, the positive sign, the Morris rank and the `VMXO` coupling. The SITE store listed `RMOM` as an untested rank-1 alternative and recorded `CNRT` as a confirmed lever at +41% `plant_C`. All of it was re-derived from correlations across two cycles. The graph also declares three `depends_on` pairs among nine levers composed in one experiment, which is the documented explanation for a non-additivity that got written up as a discovery.

     **THEN GO TO THE SOURCE AND CONFIRM IT. This step is not optional and is not reserved for claims you have already decided are load-bearing.** Confirming is not the same as learning: at calibration stage you arrive at the source already knowing what the KB says, in order to check it, so the read is short and targeted. A long exploratory source read at this stage is the signal described above. The KB tells you what a thing IS; the source tells you what it DOES. Open the `file:line` the KB handed you in the checkout at `$A2MC_MODEL_PATH` and read **the code that USES the value**, not only its declaration or its description string: a `description`, a `long_name` or a `units` field in any of these surfaces can be wrong, which is a standing rule here ([[feedback_param_description_can_lie_verify_in_source]]) and is exactly why the KB read is a starting point rather than an answer. Confirming costs one command -- `git -C "$A2MC_MODEL_PATH" show HEAD:<path> | sed -n '<lo>,<hi>p'` -- against the hours a wrong mechanism costs downstream.

     **Phase 0 is where this is cheapest and most valuable**, because a bound or
     an axis label written from a guess here is inherited by every case in the round.
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
> - **Submission, when the QUEUE rather than the model is the bottleneck** — a third form exists,
>   `use_cases/PFLOTRAN_template/case_template/submit_ensemble_packed.sh`, which runs **many cases
>   concurrently inside ONE node-exclusive allocation**. Reach for it only on the specific signal
>   below, because it is the least conventional of the three.
>   **The signal is a small per-case shape meeting a small shared pool.** A PFLOTRAN case is a small
>   MPI job (miniLEO: 8 ranks), so on a `shared` QOS it takes a node *slice* — and if the cluster's
>   shared partition is itself small, thousands of such jobs contend inside it regardless of how they
>   were submitted. **An array does not help here: it changes the job-record count, not the resource
>   pool.** Measured on `PFLOTRAN_miniLEO` R1 (2026-08-28, log `20260828a`): `shared_milan_ss11` holds
>   **70 nodes** against `regular_milan_ss11`'s **2853** at comparable queue depth, and the round
>   settled at 8.8 completions/hour with concurrency never above 6 and reaching 0 with 4010 queued —
>   every pending job reporting `Reason=Priority`, nothing crashed. That projects to **19 days** for
>   4096 cases.
>   **Diagnose before adopting**, since on a cluster with a large shared pool none of this applies:
>   `sinfo -p <partition> -o '%D'` for pool size, `squeue -p <partition> -o '%T'` for depth,
>   `squeue -o '%Q'` against `scontrol show config`'s `bf_min_prio_reserve` for whether your jobs can
>   earn a backfill reservation at all, and `sshare -U -u $USER` for the account's FairShare.
>   **It costs no extra allocation** — `shared` charges ranks/cores-per-node per case, a packed node
>   charges one node for (cores/ranks) cases. Same core-hours, minus idle slots at the worklist tail.
>   Its input comes from **`scripts/pflotran_worklist.py`**, whose completion test is the **final time
>   in the `*-mas.dat` tape, not the tape's existence** — a TIMEOUT case leaves a partial tape that a
>   file-existence test scores as done, silently leaving a hole in the design matrix. Two properties
>   are worth knowing before relying on it: it reads case **directory names** from that worklist, so
>   unlike the array form it carries no case-naming assumption and a non-contiguous set costs nothing;
>   and like the array form, **one script binds many cases to one binary**, so record which
>   ([[feedback_bind_runs_to_archived_binaries]]).
>   **Gate it on measurement, not on the arithmetic.** "16 cases fit a 128-core node" is a core count,
>   not a throughput prediction: N cases' worth of MPI ranks contend for one node's memory bandwidth,
>   so if packed cases run much beyond ~2x their solo p50, *fewer* workers per node may yield *more*
>   cases per node-hour. Run a one-node gate on a carved-out subset first — and cancel that subset's
>   individually-queued jobs before it, or the two paths run the same case and clobber each other.
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

## Step 4a — a failure the monitor reports is WORK, not a statistic

**The moment monitoring reports failed cases, diagnose the cause and FIX IT.** Not at the end of the phase, not queued, not surfaced to the PI as a blocker. A failure count you record and move past is a phase that has stopped doing its job — and the fix is usually cheap while the round is young and expensive after it has run.

**Three categories, and you must decide which one you are looking at before you act:**

| category | how it shows | what to do |
|---|---|---|
| **your own run scripts / config** | a failure that is not about the science at all — a guard that misfires, a walltime that never gets scheduled, a worklist that empties early | **fix and resubmit.** This is the category most often missed, because a broken script looks like a broken model |
| **infrastructure** | NODE_FAIL, PartitionDown, SIGKILL clusters, out-of-memory | `restart-failed-jobs` (CIME) / `restart-adapter-ensemble` (non-CIME) |
| **the model** | the run reaches the model and the model cannot survive the parameter set | **a RESULT, not an error** — characterise it (which parameters, what threshold, what mechanism), then decide whether a BOUND is wrong. If it is, cut it now: an in-round bound correction is the phase's own work, not a `TODO.md` item ([`calibration-discipline`](../calibration-discipline/SKILL.md), "FIX IT NOW vs QUEUE IT") |

**Measured on EcoSIM_Lusignan R1, 2026-09-05, where all three appeared in one phase:**

- **Own script, twice.** A `strings "$EXE" | grep -q <symbol>` guard under `set -o pipefail` returned 141 from SIGPIPE **even though the match succeeded**, killing a job six seconds in; and `srun` inside a `while read` loop **consumed the worklist through stdin**, so every worker ran exactly one case (128 workers, 128 claims, 128 of 256 cases never claimed). Neither is a model failure and neither would ever have been fixed by a restart skill. Both were found by reading the log of a *reported failure* rather than counting it.
- **Model.** 26 of 128 cases drove soil organic matter negative and **exited `rc=0`**, so `sacct` recorded them COMPLETED. Diagnosing rather than tallying showed all 26 had `OMGR >= 0.68`, zero of 102 successes did, and time-to-failure was monotone in `OMGR` — a first-order rate whose ×4 upper bound emptied its pool in one hourly step. The bound was cut in-round.

**A `rc=0` failure is the reason the completion test must be the model's own terminal artifact.** If the scheduler's exit status were trusted here, 26 truncated runs would have entered screening as complete. Gate on the artifact (a final restart, a mass tape), never on `sacct`.

**Do not let a known failure class go quiet.** Once characterised, a recurring failure is routine and should stop being narrated — but "routine" means *understood and either fixed or accepted with a reason*, never *seen often enough to ignore*.

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
  `calibration-goal`, `build-surrogate`.
  **`build-surrogate` is here because of a decision this phase owns and can only make once:**
  whether the round also draws an INDEPENDENT validation lattice (a second Sobol' draw with a
  different scramble seed, run like any other case and then held). It cannot be recovered later
  by re-splitting, because every split of one sequence draws train and test from the same point
  set. `A2MC_SOBOL_SEQ_VALID_SAMPLES` / `_SEED` / `A2MC_VALID_MATRIX_FILE` configure it and
  `scripts/create_adapter_parameter_sample.py` refuses a validation seed equal to the training
  seed. **`tools/check_skill_registry.py::reciprocity_check` enforces this** and fails
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

## Before you finish

**Discipline self-review (automatic).** Before advancing the state, re-check the [`calibration-discipline`](../calibration-discipline/SKILL.md) items that apply to this phase. This is unprompted and per-phase — the user does not have to ask (memory `feedback_schedule_periodic_reviews_with_a_real_mechanism`).

