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

> **Floor, not ceiling — but widening the design is a Phase-4 act, not a Phase-5 one.** The online
> Phase 5 runs exactly the experiments Phase 4 designed. As the offline agent you may see that the
> design should be wider — more variants, an extra control, a second base — and
> `offline-testing-workflow` is built for that latitude (N variants, V0 gate, decision tree). **Take
> it by going back and recording the widened design and its bar in the Phase-4 log, then execute
> that.** The rule this does NOT license is deciding in the builder: a variant added at staging time
> has no pre-registered expectation, so Phase 6 has nothing to rule it against and the extra case
> buys a number rather than an answer. Run at least the designed experiment; widen it deliberately
> and on the record.

**Inputs (from Phase 4):** the hypothesis / experiment design + selected base case.
**Deliverable:** experiment results (per-target metrics vs baseline) → handed to Phase 6, **and every simulation recorded in the case's run ledger** (step 2c).

> **Before designing or interpreting anything here, hold the MECHANISM NETWORK, not one or two parameters.** At calibration stage the model KB is assumed well-built, so it is where you START and it usually hands you the citation -- it does NOT replace verifying in source: query ALL FIVE surfaces (codebase wiki, RAG index, **knowledge graph**, MODEL-level and SITE-level `gained_knowledge/`) plus the case's own parameter list, pull `parameter -> controls -> mechanism -> affects -> output` for the **scored** variables and the `depends_on` couplings among anything you intend to move together, and only then confirm in source. Needing source to LEARN rather than to CONFIRM means a KB gap, which is a build task. [[feedback_full_mechanism_picture_before_designing_an_experiment]]

## Do this

0. **On Phase-5 entry, reset `skip_testing_count = 0`** in `workflow_state_offline_r{RR}.json`. Entering
   Phase 5 commits this experiment cycle to an HPC test and closes the inner (skip-test) loop, which counts
   within one cycle only. (`experiment_count` is unchanged here — it advances on the Phase 6→3 route.) The
   online orchestrator does this reset in code; offline, do it by hand.
0b. **INSTANTIATE THE BASE BY COPYING IT — and check it was chosen for this experiment.**
   Phase 4 hands you a *selected base case*; this step is how that case becomes N case directories.

   **FOLLOW PHASE 4'S DESIGN. Adjust for practical reasons; do not redesign.** What varies, from
   which base, in which direction and against what bar is settled in Phase 4
   (`phase4-hypothesis` Steps 0, 2a and 2b), and your job is to realise it correctly and to prove
   that you did. Execution meets things a design cannot foresee, and handling them is this phase's
   work rather than a reason to stall.

   **The test is whether the adjustment changes what the experiment would CONFIRM or REFUTE.**

   - **Practical — make it, then RECORD it in the Phase-5 log.** A requested value that is not
     representable at the parameter file's dtype and lands a few ULP away; a dose respaced because
     two rungs would have staged the same stored value; a case resubmitted after an infrastructure
     failure; a wall-clock, queue or concurrency change; a case naming or run-root change. None of
     these move the bar, and all of them are unrecoverable later if not written down.
   - **Scientific — go back to Phase 4 and record it there.** Which parameter moves, in which
     direction, from which base, over what range, or what would count as a pass. A variant added or
     a bar loosened at staging time has no pre-registered expectation, so Phase 6 has nothing to
     rule it against and the extra case buys a number rather than an answer.

   A borderline case is a Phase-4 case: the cost of walking the design back one phase is minutes,
   and the cost of a result nobody can interpret is the cycle.

   **The base rule, restated so the executor can check it rather than take it on trust.** It is the
   same rule as `phase4-hypothesis` Step 2a, seen from the execution side — if you change one,
   change both. The base should be from among the round's TOP cases, ranked by in-band count with
   the composite as tie-break, with **anything below the model's viability floor excluded** (a
   collapsed stand posts a flattering composite for the wrong reason, since every relative error
   approaches -1). **The current best is not automatically the right base**, and Phase 4 should
   have said which one it chose and why. **If the log does not say, stop and ask before building** —
   an unstated base makes Phase 6's verdict unreadable, since a refutation is a property of a
   `(parameter, direction, base)` triple.

   **Instantiating it.** **Start from the chosen case's ACTUAL configuration, never from a
   reconstruction of it.** For a standalone-binary model that means copying its staged parameter
   files, its namelist and its submit script, repointing the paths, and modifying the COPY, rather
   than rebuilding the base from the round's design matrix. For a CIME model the equivalent is
   `create_case.sh --case-suffix` off the selected base case, which already works this way — the
   rule below is why that matters, and it is the adapter path that has to be told.

   **Why that distinction is load-bearing and not stylistic.** Rebuilding from the matrix can only
   express parameters that are IN the matrix, so an experiment built that way is silently confined
   to the round's sampled parameter list. Every parameter the design never sampled becomes
   untestable, and nothing reports it: the build succeeds, the run scores, and the cycle concludes
   about a lever class it could not have moved. Measured on one site: ten consecutive experiment
   cycles rebuilt from the matrix, and the round's eventual blocking finding was that six whole
   parameter categories and seven of twenty-one plant-side mechanisms had no sampled parameter at
   all — none of which any of those cycles could have tested.

   Copying also makes the **V0 gate exact by construction rather than by tolerance**: the control
   arm carries byte-identical parameter files, so assert that identity (`filecmp`, full content)
   instead of comparing scores within an rtol. A departure then means non-determinism in the model
   or the environment, which is a different and more serious finding than a staging error.

   Everything a case holds that names its own directory is an absolute path inside it, so
   repointing is one substitution of the old case dir for the new one across the namelist and the
   submit script. **Verify by reading back from disk, never from the write:** each moved value
   against the Phase-4 plan, each unmoved lever equal to the base exactly, and **no other variable
   in the file differing from the source** — that last one is what catches an edit landing in the
   wrong slot. The builder should exit non-zero rather than report a pass it did not earn.

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
2b. **ARCHIVE THIS PHASE'S JOB SCRIPTS into `phase_results/{stem}/submit_scripts/`** — each case's submit
   script and its own namelist or input deck, since variants can differ in either. **Phase 0 is deliberately EXEMPT.** Its job scripts are generated from the machine + round config by the materializer, and an ensemble is thousands of cases (one R3 round is 59,393), so archiving them would be both enormous and redundant: the config plus the generator already reproduces them exactly. The exemption covers the PER-CASE scripts only: the ensemble's launcher, its command line and its worklist go in the Phase-0 stem's `run_tracking/` (`phase0-design` Step 3), because a command-line override is reproduced by no config. Phase 5 is different because its handful of variants are hand-designed and hand-repointed, so nothing else records what actually ran. **Copy, never move:** the scheduler reads the operative copy from the run
   directory. Do it BEFORE submitting, as soon as the scripts are final, not at Phase 6.
   **A PreToolUse gate now holds a submission until this is done** (`.claude/hooks/require-run-skill-before-submit.py`): a `tools/submit_run.py` or full-ensemble `sbatch` for a case is refused unless the model's run skill (`ecosim-run-workflow`, `pflotran-run-workflow`, `ats-run-workflow`, `offline-testing-workflow`) was invoked and the case's `case_template/README.md` was read since the session's newest compaction, and the submitted script and every namelist or deck in the run directory already have byte-identical copies in the stem's `submit_scripts/` (or `run_tracking/submit_scripts/`). `A2MC_RUN_GATE_OVERRIDE="<why>"` on the command lets a case with no run skill or template through.
   **Why this is a step and not housekeeping.** The run directory is untracked scratch that gets cleaned,
   and the submit script is the only record of **which binary this run was bound to** plus its run-time
   hash assertion. A log stating "V0 gate PASS" with no archived submit script cannot show which
   executable produced that number. On 2026-08-23 a cycle nearly ran against the wrong binary because
   `materialize_adapter_ensemble.py` emits the LIVE build path by default and that path had since been
   rebuilt ([[feedback_bind_runs_to_archived_binaries]]).
   `check_offline_log_evidence.py` WARNs when a phase-5 stem folder has no `submit_scripts/`
   (non-retroactive from `20260823`). Phase 0 is exempt, as above.
2c. **RECORD EVERY SIMULATION IN THE RUN LEDGER, as it happens — this is a Phase-5 duty, not a
   reporting one.** `use_cases/{Model}_{Case}/memory/run_records_r<NN>.json` (one file PER
   ROUND since 2026-10-13), via
   `tools/record_run_status.py`. One record per case: its cycle, its stem, its job id, the
   parameter values it staged, its status, and its scores once they exist.

   **A run submitted with `sbatch` (the standalone-binary models) goes THROUGH
   `tools/submit_run.py`, which registers it in the same step.** It runs `sbatch` and writes the
   record (status `submitted`, job id, binary with its md5, purpose, differences, and where the run
   lives), and it refuses a submission missing any of those. A bare `sbatch` is refused by the
   agent's PreToolUse hook, which points here; a job the ledger does not record (an extraction, a
   build) declares itself on the command with `A2MC_UNTRACKED_JOB="<why>"`.

   ```bash
   # SUBMIT + REGISTER, per case (stdout is only the job id)
   J=$(python tools/submit_run.py --case-dir "$A2MC_USE_CASE_DIR" --round 1 --cycle 19 \
       --case <case> --stem <stem> --purpose "..." --differences "<base> EXCEPT <what> = <value>" \
       --binary <archived exe> --run-dir <case dir> --job-id-file <case dir>/job_id.txt \
       -- <the sbatch arguments and script>)
   # when its job ends: the MODEL's verdict (a watcher can run this for you, below)
   python tools/record_run_status.py settle --case-dir "$A2MC_USE_CASE_DIR" --round 1 --job-id "$J"
   # once the cycle's scoring artifact exists, fold the scores in at once
   python tools/record_run_status.py from-ladder --case-dir "$A2MC_USE_CASE_DIR" --round 1 \
       --cycle 19 --data <stem>/R1_c19_ladder.data.json --stem <stem> --status completed
   ```

   A pilot, a gate or a rerun of many cases is ONE ROW for the whole submission: pass
   `--run-root <root>` instead of `--run-dir` (narrowed with `--field case_prefix=...` and
   `--field case_range=LO-HI` when the root holds more than this submission). `settle` then
   records the per-case counts, and `check` treats every case directory the row covers as
   registered.

   **Status is the MODEL's verdict, never the scheduler's.** `pending / submitted / running /
   completed / failed / restarted / void`, where `completed` means the model's own success check
   passed. A job `sacct` calls COMPLETED that left no usable output tape is `failed`
   ([[feedback_never_parse_a_cli_default_output]]); `tools/model_ensemble_status.py` already
   reconciles the two, so pass its verdict.

   **The watcher you already run settles the record when the job ends.** Give it the `settle`
   command that `submit_run.py` prints as its on-end hook: `watch_slurm_array.sh ... -X '<settle>'`
   or `model_ensemble_status.py ... --watch N --on-end '<settle>'`. It runs once at the terminal
   state, its output lands in the watch log, and `end_hook_status` in the state file says whether it
   worked. A record left open after its job ended is caught by the agent's Stop hook, which blocks
   the end of the turn until it is settled.

   **A CASE IS NOT CREATED UNTIL IT IS REGISTERED, and its status comes from the SCHEDULER, never
   from memory** (PI, 2026-10-10, adopted from a sibling project's track-simulations skill). Two
   subcommands enforce that half of the contract, and without them the ledger could only ever be as
   complete as whoever remembered to call `upsert`:

   ```bash
   # states read BACK from the scheduler, reconciled with the model's own success check
   python tools/record_run_status.py refresh --round <N> --run-root <run root> --model <model>
   # a case that actually RAN and is not registered; a recorded status that disagrees; thin records
   python tools/record_run_status.py check   --round <N> --run-root <run root> --model <model>
   ```

   `refresh` delegates to `tools/model_ensemble_status.scan()` rather than reading `sacct` itself,
   so the ledger and the watcher share ONE reconciliation; a second copy here would be a second
   contract to drift. It will not overwrite a `void` or `restarted` record, because those are human
   judgements about a run rather than scheduler states -- a deliberately cancelled arm must not be
   re-reported as `failed` and chased by a restart.

   **`--purpose` and `--differences` are the reproducibility fields.** `differences` says how the
   case departs from the base, in the form `<base> EXCEPT <what> = <value>`; `check` warns when it
   is absent, because a case whose departure is not written down cannot be rebuilt. Record
   `--binary` too: on a shared build tree the submit script is the only record of which executable
   a run was bound to ([[feedback_bind_runs_to_archived_binaries]]).

   **The READABLE view is `table --per-case`, and it is a different question from `table`.** The
   plain `table` is a per-CYCLE aggregate, which answers "how did the round progress" and collapses
   a set of hand-designed arms into one row; `--per-case` gives one row per SIMULATION with its
   status, job, binary, purpose and differences. It lives beside the ledger as
   `memory/SIMULATIONS_r<NN>.md`, and `record_run_status.py` REWRITES IT ON EVERY LEDGER WRITE, so
   it is never a separate step. Never hand-edit it: the next write overwrites the edit, and the Stop
   hook reports a table whose rows disagree with the ledger.

   **This is worth running for TESTING runs and not for a large Phase-0 ensemble** (PI): the value
   is a readable table of a handful of hand-designed variants, and 8192 config-generated cases are
   already reproducible from the config plus the generator, with their full record in the `run_tracking/`
   subfolder of the round's Phase-0 stem (`phase0-design` Step 3) -- the same reasoning that exempts Phase 0 from the submit-script archive in
   step 2b. Such an ensemble gets no ledger row; its `sbatch` carries `A2MC_UNTRACKED_JOB`.

   **This is a RECORD, so it is UNGATED and it is not knowledge.** It goes nowhere near
   `gained_knowledge/experiments.json`, which is curated, human-gated, and holds the *interpreted*
   record — hypothesis, outcome class, lesson — written at or after the Phase-6 gate by
   `round-housekeeping`. Nothing in the ledger is a claim, which is exactly why an automatic writer
   is safe here and would not be there.

   **Why it is a step and not housekeeping.** The same content was carried by hand in a caption
   section of each cycle's cumulative figure. It was written for one round's cycles c00 through c08
   and then silently stopped: ten consecutive captions omitted it and nothing noticed, because a
   hand-written section has no checker. `check_offline_log_evidence.py` now WARNs per phase-5 log
   when a case named in `submit_scripts/` is absent from the ledger (non-retroactive from
   `20260908`), and `round-housekeeping` step 6 checks the round-level total.
3. **Log** via `calibration-log` (phase log → `PhaseLogger.log_testing` /
   `log_experiment_design`).
4. **Advance the driver state** once results are extracted: `st.set_position(current_phase="refinement")`;
   `st.save()` (`tools/workflow_state_offline.py`) so `resolve_next_action` resolves Phase 6.

## Footguns (the load-bearing ones; full set in `offline-testing-workflow`)

- **Case-suffix, not new case numbers.** Experiments use `--case-suffix exp_<id>`; inventing a
  case number collides with / leaks into the Morris ensemble extract dir.
- **V0 gate before trust.** Reproduce V0 (baseline params) before reading V1+ as signal. **What it
  catches depends on how step 0b instantiated the base.** A base REBUILT from a design matrix or a
  parameter generator: V0 catches build and param-file errors, and agreement is within a tolerance.
  A base COPIED from an existing case: V0's parameter files are byte-identical, so agreement is
  EXACT and the gate no longer tests the staging at all — a departure means non-determinism in the
  model or the environment, which is a different and more serious finding. Know which gate you are
  running before you interpret a pass.



## Scripts: start from the case TEMPLATE, adapt it HERE

**Every script this phase writes follows the three-tier rule** (`calibration-discipline` item 2b):

```
use_cases/{Model}_{Case}/scripts/     the canonical script TEMPLATE   (seeded at onboarding)
        │  copy into this phase's folder, then ADAPT for this phase's purpose
        ▼
memory/phase_results/{stem}/          the canonical SCRIPT for this figure, beside its
                                      caption, data and notes -- this is the log's evidence
```

1. **Read the case's template index first: `use_cases/{Model}_{Case}/scripts/README.md`.** Read it; listing the folder is not enough. The index is generated from each template's own docstring (`tools/case_script_index.py`), so it lists every template, and the edit-time hook puts the same list in front of you when you create a new script in a phase folder. Run files (launchers, namelists) have their own generated index in `use_cases/{Model}_{Case}/case_template/README.md`. If a template covers what this phase needs, copy it into this phase's `phase_results/{stem}/` and adapt it there. Do not run it from `scripts/` and do not edit the template to suit one phase: the template is the shared shape, the copy is this phase's instrument.
2. **If there is NO template, write one from scratch** in `phase_results/{stem}/`. That is the correct first-use state and nothing is wrong with it.
   **Either way, the new script names its source** on one line of its docstring (a shell script's header comment): `Template: scripts/<name>` for an adapted copy (`Template: case_template/<name>` for an adapted launcher or run file), `Template: none (first use)` when nothing fits. An unedited copy needs no line, since it is byte-identical to its template. `tools/check_script_provenance.py` (pre-commit 33) refuses a new phase script without the line, and refuses `none` beside a template of the same name.
3. **On a script's SECOND use, promote it to `scripts/` as the template**, then copy it back into the new phase's folder and adapt. Second use is the trigger, not third. Drop the `Template:` line from the promoted file and regenerate the index (`python3 tools/case_script_index.py --case use_cases/{Model}_{Case} --write`); a hook flags a template the index does not list, and pre-commit 32 refuses a `scripts/` change while the index is stale.

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

## Log it as a LIVING record

`offline-testing-workflow` owns the mechanics; **the log is still yours**, and it starts when the
variants are submitted, not when the results land. The operational detail — job/array IDs, which
variants failed when the scheduler hiccupped, what was restarted — is unrecoverable a week later.
Full contract in `calibration-log`.

**Phase 5's expected sections** — `PhaseLogger` names any you leave empty:
Experiments Designed · Submission · Simulation Status · Monitoring Armed · Failures and Restarts · V0 Reproducibility Gate · Results Preview · Results Summary.

**`Experiments Designed` carries the design AS EXECUTED.** A practical adjustment made at staging time (step 0b) is recorded there with what changed and why — `Failures and Restarts` is for things that went wrong, and a respaced dose or a clipped value is not a failure, so without this it has nowhere to go and vanishes.

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

