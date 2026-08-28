---
name: restart-adapter-ensemble
visibility: public
category: calibration
description: Recover failed cases in a NON-CIME adapter-model ensemble (EcoSIM, PFLOTRAN, ATS) — classify why they died, persist the case list, and relaunch only what is missing. Use on "which cases failed", "rerun the failed cases", "restart the crashed runs", "the ensemble has holes", or before any sensitivity analysis, since a crashed case is a HOLE in a Saltelli design while a finished-but-degenerate case is a valid data point. The non-CIME counterpart to restart-failed-jobs, whose scripts hardcode ELM's restart glob and CIME's submission path.
modes:
  requires_fates: false
  nutrient_pathway: any
  scope: [hpc]
  summary: "Failure triage + relaunch for a standalone-binary adapter ensemble. The reasoning mirrors restart-failed-jobs; the mechanics do not — there is no CIME, and completion is the model's own end-of-run artifact."
---

# restart-adapter-ensemble — recover failed cases in a standalone-binary ensemble

`restart-failed-jobs` is the ELM-family (CIME-submitted) workflow and says so in its own frontmatter: *"the REASONING transfers to any model; the SCRIPTS do not."* This is the other half. An adapter model runs a **standalone binary** per case, so none of CIME's restart machinery applies and the failure signals are different in kind.

## THE LOAD-BEARING RULE — the exit code lies

**Do not classify a case by its exit status, and do not trust the scheduler's job state.** Both report success for runs that did not finish.

Measured on EcoSIM_BioCON R3, 2026-08-20, across 11,425 attempted cases:

| what you might trust | what it actually said | truth |
|---|---|---|
| the model's exit code | `0` | 178 cases had aborted on an internal `ENDRUN` that exits 0 |
| `sacct` on the outer job | `COMPLETED` for **every** case | 853 had not finished |
| the launcher's own check ("output file exists") | COMPLETE | the tape is created at **initialisation**, so it exists from timestep 1 |

**Completion is the model's own END-OF-RUN artifact** — something written only after the last step:

| model | completion artifact |
|---|---|
| EcoSIM | the restart stamped `<final year + 1>-01-01` (`*.ecosim.r.<Y>-*.nc`), where the year is derived from the case's own `runfile.nml` |
| PFLOTRAN | `"Wall Clock Time:"` in the `.out` — a line printed only at normal termination |
| ATS | the launcher's `A2MC_COMPLETED` sentinel, written under `if [ $rc -eq 0 ]` |

Use `backend.check_case_status()`, which encodes this per model, or `tools/model_ensemble_status.py --model <m> --run-root <dir> [--case-range LO-HI]`, which reconciles it against the scheduler.

> **⚠ For a job ARRAY or a node task-farm you MUST pass `--ensemble-jobs <ID[,ID...]>`, or the reconciliation is silently inert.** A case dir cannot distinguish "still running" from "died part-way" — both leave a started-but-incomplete tree — so `check_case_status` returns `RUNNING` and relies on this tool to settle it against the scheduler. That leg reads each case's `job_id.txt`, and **an array or a task-farm writes none**: measured on EcoSIM_BioCON R3, not one of 14,849 case dirs had one, so the scan reported `RUNNING=1129` against two arrays that were provably terminal — and those 1,129 were exactly the round's failures, sitting in a state that reads as "be patient" and never resolves. Naming the jobs restores it; their states are read from `sacct`, and an unreadable scheduler or a job with no record counts as NOT terminal, so the flag cannot reclassify live work.
>
> ```bash
> python tools/model_ensemble_status.py --model <m> --run-root <dir> --ensemble-jobs 57316828,57335995 --failed
> ```
>
> This is the same failure shape as a quiet watcher log (`arm-hpc-monitoring` anti-pattern #5): a signal whose "nothing to report" state is byte-identical to its "everything died" state.

## Step 1 — classify before relaunching

Relaunching without classifying wastes the compute twice: an infrastructure failure restarts fine, a model failure comes back identically.

| class | evidence | restart-eligible? |
|---|---|---|
| **infrastructure** | `NODE_FAIL`, `PartitionDown`, `TIMEOUT`, `OUT_OF_MEMORY`, a `CANCELLED` with no signal | **yes**, unchanged |
| **wall-clock truncation** | terminal state `TIMEOUT`, or elapsed at the limit with a partial tape | yes, with a longer `--time` |
| **model numerical failure** | a fatal signal (SIGFPE = 8), or the model's own abort message | **no** — it will fail identically without a parameter or source change |
| **model self-abort** | an `ENDRUN`-style message, often with a diagnostic dump beside it | no, same reason |

### The same death is recorded differently by submission arm

This is the trap that hid 230 failures for hours. If some cases were launched directly and others under `srun`, **the identical crash produces two different records**:

```bash
# launched directly (a task-farm): the shell sees the signal in the exit code
grep -o "FAILED rc=[0-9]*" <farm log>          # rc=136  == 128 + 8 == SIGFPE

# launched under srun (a per-case array): SLURM records the STEP, and the OUTER job exits 0
sacct -j <jobid> --format=JobID,ExitCode -n -P | grep '\.0|'    # <jobid>_<task>.0 -> 0:8
```

`sacct` on the **outer** job reports **zero failures** for the `srun` arm. Always read the `.0` step's `ExitCode`, whose second field is the signal.

**Use `sacct -P`.** The default format pads and truncates `JobID`, printing `<jobid>_1000` as `<jobid>_10+`, so a regex expecting digits silently drops every array task ≥ 1000 ([[feedback_never_parse_a_cli_default_output]]).

## Step 2 — PERSIST the case list, not a count

**Aggregates cannot be relaunched.** A per-block or per-mode tally is useful for a figure and useless for recovery. Write, into the phase's `phase_results/{stem}/`:

- `failed_cases.csv` — one row per case: id, which arm, its design block, exit code, step signal, classified mode, and whether a diagnostic dump exists;
- `failed_cases.txt` — bare ids, one per line, for a `--cases-file`-style relaunch.

Treat the bare list as **live run-state** (gitignore it) while the ensemble is still running; it is only final once every task is terminal. Commit the CSV snapshot as the record.

## Step 3 — relaunch idempotently

Prefer a launcher that **skips any case already carrying the completion artifact** over building an exact id list. It is simpler, it is safe to re-run, and it self-corrects if the list was stale:

```bash
# re-point at the whole range; only the incomplete cases actually run
sbatch --array=<lo>-<hi>%<throttle> <the ensemble submit script>
```

The cost is walking every case directory; the benefit is that a partially-finished range needs no bookkeeping. Build an explicit `--array` id list only when the skip-scan is too expensive.

**Re-check the mandatory submit-time overrides** — an ensemble submit script's `#SBATCH` directives often still carry a previous round's job name, array range and log paths, so a bare `sbatch` silently writes into the wrong round's directory.

## Step 4 — if a MODEL FIX is involved, three gates

When the failures are numerical and a source change is what unblocks them, relaunching mixes two model versions in one ensemble. That is legitimate **only** if the change is provably inert on the cases that already succeeded.

1. **V0-at-equality** — the unchanged configuration still reproduces the baseline. Bind each arm to an **immutable archived binary**, never the live build path, and make the pass a **conjunction**: identical outputs **AND** provably different binary hashes. Identical outputs alone is not evidence, because running the same binary twice also produces identical outputs.
2. **Inertness** — run a sample of **already-completed** cases with the fix ENABLED and require **bit-identical** output. This is the gate that makes the mixed ensemble defensible, and it is the one most easily skipped.
3. **Efficacy** — run the diagnosed exemplars of each failure mode with the fix enabled and confirm they now reach the completion artifact. If only one mode recovers, relaunch only that mode.

Prefer a **runtime switch** (a namelist variable) over a second build: one binary serves every arm, and a namelist read does not require the variable to be present, so pre-existing case files keep the old default and run unchanged.

## Guardrails

- **Never rebuild a shared build tree while cases are queued.** EcoSIM, PFLOTRAN and ATS build ONE executable that every build overwrites in place, and a queued job resolves its executable at **run** time — so a rebuild silently runs the ensemble's tail on a different program. Archive the binary first, with its `sha256` and a `PROVENANCE.txt`.
- **Recovering crashes is not a scientific improvement.** A degenerate case that now finishes is still degenerate; it is simply recorded rather than missing. Say so, or the count will read as progress.
- **Only ever restart your own launches** ([[feedback_monitor_only_own_session_launches]]).

## Related skills

- `restart-failed-jobs` — the ELM-family (CIME) counterpart. Same reasoning, different mechanics.
- `ecosim-run-workflow` — launching and scoring an EcoSIM ensemble; this skill is what you reach for when part of it did not finish.
- `arm-hpc-monitoring` — arm monitoring on the relaunch, immediately.
- `model-evolution` — the workflow for the source change Step 4 assumes.
- `phase0-design`, `phase1-exploration` — the phases either side of a recovery.

## Notes

- **Branch fit:** adapter-kit. It presumes `models/<name>/` backends and `tools/model_ensemble_status.py`, which exist only where adapter models do.

## Changelog

- 2026-08-21: **`--ensemble-jobs` is now called out as mandatory for arrays and task-farms.** The
  completion section pointed at `model_ensemble_status.py` as though its scheduler reconciliation
  always worked; for the two submission layouts this skill is most often used with, it never did —
  no per-case `job_id.txt` exists, so 1,129 dead EcoSIM_BioCON R3 cases were published as RUNNING
  against terminal arrays. Signal: reconciling that count at the R3 drain.

- 2026-08-21: Initial version — distilled from the EcoSIM_BioCON R3 prefix recovery, where 853 of 11,425 cases failed and none of it was visible from the exit status. `sacct` reported COMPLETED for every case; the launcher's tape check reported COMPLETE because EcoSIM creates its history tape at initialisation; and the two submission arms recorded the identical SIGFPE two different ways, hiding 230 of them until the `.0` step's ExitCode was read. Sources: the EcoSIM model-dev records of 2026-08-20 and 2026-08-21, and `use_cases/EcoSIM_BioCON/memory/phase_results/20260820a_phase0_design_r03_*/RELAUNCH_FAILED_CASES.md`.
