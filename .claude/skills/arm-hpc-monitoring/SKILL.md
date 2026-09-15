---
name: arm-hpc-monitoring
visibility: public
category: calibration
description: Set up real-time monitoring of an active A2MC HPC ensemble or experiment on Perlmutter at session start (CLAUDE.md Rule 6). Detects live long-running login-node processes (auto-monitor, submitter, extractor) via `ps -ef`, arms Claude `Monitor` tasks on each long-running log with the right event + error filter (silence ≠ success), and reminds Claude to react with proposals rather than just relaying events. Use whenever a session begins (or resumes after compaction) while an ensemble round is in flight. Also use immediately after launching a new submitter or restart job.
modes:
  requires_fates: false      # session-start HPC monitoring; model-agnostic
  nutrient_pathway: any
  scope: [hpc]
  summary: "Monitors any in-flight A2MC ensemble/experiment; model-agnostic."
---

# Arm HPC Monitoring — Session-Start Runbook

Per **CLAUDE.md Rule #6**, when an HPC ensemble is in flight (a multi-thousand-case round), the session must arm `Monitor` on every long-running log within the first few exchanges. Silence on a crashed process looks identical to silence on a still-running process — so coverage **must include error signatures**, not just happy-path events.

## Step 1 — Detect what's running

```bash
ps -ef | grep $USER | grep -E "r5_auto_monitor|submit_phase0|extract_ADSP_RGSP_slim|extract_monthly_variables_FATES|plot_all_extracted" | grep -v grep
```

Typical processes seen on this branch:

| Process | Typical PID lifetime | Log location (typical) |
|---|---|---|
| `r5_auto_monitor.sh` | 12+ hours (full round) | `tmp/r5_auto_monitor_<startTS>.log` |
| `submit_phase0.py --start N --end M` | ~9 h per 1000 cases | `tmp/r5_batch<N>_cases<A>-<B>_<TS>.log` |
| `submit_phase0.py --cases-file ...` (restart) | shorter, sized to cohort | `tmp/r5_rerun_<TS>.log` |
| `extract_ADSP_RGSP_slim.py` / `extract_monthly_variables_FATES.py` | minutes per batch | spawned by auto-monitor; no persistent log |
| `plot_all_extracted*.py` | minutes per milestone | `tmp/r5_plot_milestone<N>_<TS>.log` |

The active handoff log (typically the most recent `dev_logs/2026MMDDx_*.md`) names the live PIDs and exact log paths. **Read it first** to confirm what to arm.

> **Log location — ensemble scale goes to `tmp/`.** The auto-monitor / submitter / plot logs above live in the **repo-relative `tmp/`** (e.g. `~/A2MC-main/tmp/r5_auto_monitor_<TS>.log`) — **not** `~`, **not** a system `/tmp`. For a full ensemble this is the right home (many long-lived, high-volume logs; they don't belong beside the per-case scripts). This is deliberately **distinct from the `offline-testing-workflow` convention**, where a *small* experiment's launcher/submitter running log goes **with its case scripts** (`$A2MC_SCRIPTS_DIR/<ExpName>_<date>/`). Rule of thumb: **ensemble monitoring → `tmp/`; a small offline experiment's run log → job-scripts folder.** Don't over-apply one skill's convention to the other.

> **Standalone-binary model ensembles (non-CIME, e.g. EcoSIM).** Steps 1–7 below are written for
> the FATES/CIME ensemble (an auto-monitor + submitter + extractor process chain writing `tmp/` logs).
> A **standalone-binary model** (per-case `submit.sh` from `<Backend>.create_case`, no long-running
> monitor process) has no such logs — poll its **ensemble status tool** instead:
> ```bash
> python tools/model_ensemble_status.py --model <name> --run-root <ensemble dir> [--watch 60] [--failed] \
>        [--ensemble-jobs <ID[,ID...]>]
> ```
> It reconciles the Slurm job state with the model's own success check (`backend.check_case_status`,
> tape-based), so a "Slurm COMPLETED but no output tape" (a model failure) is reported **FAILED**, not
> success, with the failure line.
>
> **`--ensemble-jobs` is REQUIRED when the ensemble is a job array or a node task-farm**, because the
> reconciliation reads each case's `job_id.txt` and neither layout writes one. Without it a case that
> died part-way is indistinguishable from one still executing and is reported `RUNNING` forever —
> the same "silence looks like progress" shape as anti-pattern #5, one layer down. Measured on
> EcoSIM_BioCON R3: 1,129 dead cases published as RUNNING against two terminal arrays. Arm `Monitor` on that command's output (or a `--watch` background run)
> the same way Steps 2–5 arm it on a FATES log. The event-reaction discipline (Step 4) applies.
>
> **If that ensemble is a SLURM job ARRAY, launch the watcher rather than hand-rolling one:**
> ```bash
> nohup tools/watch_slurm_array.sh -j <jobid> -n <ntasks> -s <stem>/watch_state.json \
>       [-x "<extract-and-plot refresh command>"] > <stem>/watch.log 2>&1 &
> ```
> It publishes a state file whose mtime is a heartbeat, so its own death is detectable —
> `python tools/check_watcher_state.py <stem>/watch_state.json` reports ALIVE / FINISHED / STALE /
> DIED and exits non-zero for the last two. Read **anti-pattern #5** before arming a `Monitor` on
> its log: the log alone cannot report the watcher's death, and a milestone filter matching exact
> counts will miss most of them.

## Step 2 — Arm Claude Monitor on the auto-monitor log (always, if present)

Broad event + error filter. This catches normal progress AND failure signatures:

```text
tail -F -n 0 <auto_monitor_log_path> 2>/dev/null \
  | grep -E --line-buffered "QUEUE_BELOW_1000|QUEUE_BELOW_500|QUEUE_ABOVE_500|TRANS_DONE|STARTING_EXTRACTION|EXTRACTION_FINISHED|EXTRACTED_CASES|MILESTONE|REGEN_LAUNCH|IDLE_TICK|R5_TERMINAL|ERROR|Traceback|FAILED|MaxJobsExceeded|Killed|OOM"
```

Always `persistent: true` and a long timeout. Reasoning: this monitor runs for the session lifetime; a short timeout silently drops you off the event stream.

## Step 3 — Arm Claude Monitor on each active submitter log (if any)

For a fresh launch, use the **tight** filter — per-batch progress (`batch [0-9]+/`) emits one event every ~5 min for hours, which is noisy. Limit to quarter-milestones + stage transitions + errors:

```text
tail -F -n 0 <submitter_log_path> 2>/dev/null \
  | grep -E --line-buffered "Stage 3|submission summary|Phase 0|Pre-flight|ERROR|Traceback|FAILED|MaxJobsExceeded|sbatch:|Killed|batch (25|50|75|100)/<TOTAL>"
```

Replace `<TOTAL>` with the actual batch count (e.g., `114` for 1140 cases at batch-size 10). If unknown, omit the batch alternation entirely — milestone monitoring is optional; error monitoring is not.

For a submitter that already finished (log ends with `submission summary: N OK, 0 FAILED`), DO NOT arm a Monitor on it — nothing more will be written. Confirm completion via `tail -5 <log>` first.

## Step 4 — React to events with proposals, not relay

The session-start runbook explicitly calls out (`CLAUDE.md` Rule #6, paraphrased):

> "react to events with proposals, not just relay: queue-threshold downcross → headroom math + propose next batch; extraction-milestone crossing → regenerate the ensemble plot per `feedback_plot_filename_convention`; ensemble-terminal signal → propose next phase (e.g. Phase 1 extraction + Morris sensitivity for an exploration round)."

Concrete reaction table:

| Event | Required reaction (not just "noted") |
|---|---|
| `QUEUE_BELOW_1000` / `QUEUE_BELOW_500` | Compute headroom: `current_queue + N_new_cases × JOBS_PER_CASE ≤ 5000`. Propose next batch (combined vs split). **See the note below — the multiplier is NOT always 3.** |
| `TRANS_DONE` + `STARTING_EXTRACTION` in normal cadence | Silent acknowledgment (use "Normal" or omit). These arrive every poll cycle. |
| Milestone-crossing extracted count (e.g., 2750, 3000) | The auto-monitor's `regen_milestone_plot.sh` should fire automatically. Confirm `REGEN_LAUNCHED` events follow. If not, manually invoke the site's `use_cases/{Model}_{Case}/analysis/regen_milestone_plot.sh`. |
| `QUEUE_ABOVE_500` (after a submission launches) | Acknowledge as expected; sentinel re-arms for next downcross. |
| `R5_TERMINAL` / `EXTRACTION_FINISHED` (round complete) | Propose Phase 1 (extraction + Morris sensitivity analysis) per the round-completion runbook. |
| `FAILED` / `Traceback` / `MaxJobsExceeded` / `Killed` / `OOM` | **Stop. Investigate.** Pull recent log context, identify the source process, propose remediation (often: cancel the zombie/dead-dependency chain per **Step 7**, restart submitter, or invoke the `restart-failed-jobs` skill). |
| A chained phase (e.g. an AD-spinup → spinup → transient leg) crashes | Its downstream phases are now zombies. Cancel the dead chain (**Step 7**) so it doesn't linger in the queue or hang a completion watcher. |

If you find yourself replying with "Normal" or just relaying the event text three times in a row to a non-routine event, you are failing the proposals rule — re-read the table.

### The headroom multiplier is MODEL-DEPENDENT — 3 is FATES's number, not the scheduler's

`current_queue + N_new_cases × 3 ≤ 5000` is written for **ELM/ELM-FATES**, where one calibration
case is a **three-job dependency chain** (ADSP → RGSP → TRANS, submitted with `--dependency=afterok:`).
The `5000` is NERSC's `QOSMaxSubmitJobPerUserLimit`; the **`× 3` is the chain length**, and it is the
part that travels badly.

| model family | jobs per case | multiplier |
|---|---|---|
| ELM / ELM-FATES (CIME) | ADSP + RGSP + TRANS | **× 3** |
| EcoSIM, PFLOTRAN, ATS (standalone binary) | one `submit.sh` per case | **× 1** |
| any of the above submitted as a **job ARRAY** | one task per case, and **each task counts** | **× 1 per task** — the array does not buy you ceiling headroom, only concurrency control via `%N` |

**Both directions of getting this wrong cost something real.** Inheriting `× 3` on an adapter model
**under-uses the queue threefold** — an 8704-case PFLOTRAN round would be metered as though it were
26,112 jobs and crawl. Inheriting `× 1` on FATES **overshoots the ceiling by 3×** and the submitter
aborts partway on `QOSMaxSubmitJobPerUserLimit`, leaving a half-submitted round; that failure has its
own recovery path in `restart-failed-jobs` (Step 1, `tools/diagnose_qos_failures.py`) precisely
because it has happened.

**Two more things the formula does not say, and both bite:**

- **Count the queue ARRAY-EXPANDED.** `squeue -u $USER -h -r` — without `-r` a folded array line
  (`123_[5-99]`) counts as **one**, so the headroom is computed against a number that can be
  hundreds too small. Same family as [[feedback_never_parse_a_cli_default_output]]: never read a
  scheduler CLI's convenience formatting as data.
- **Leave a RESERVE.** Filling the ceiling exactly starves every other lane on a shared account —
  the next `sbatch` anyone runs fails — and there is a genuine race between counting the queue and
  submitting into it. Subtract a few hundred before dividing.

`scripts/submit_adapter_ensemble_batched.py` implements this loop with the multiplier and the reserve
as parameters rather than constants, so neither is inherited by accident.



## Step 5 — Verify silence detection works

A monitor with only happy-path filters (e.g., `QUEUE_BELOW_500|TRANS_DONE|elapsed_steps`) will be **silent during a crash** — and silence reads identical to "still running." Before ending your arming, sanity-check that your filter alternation includes:

- At least one progress signal (`TRANS_DONE`, `Stage 3`, etc.)
- At least three failure signals (`ERROR`, `Traceback`, `FAILED`, ideally also `Killed`, `OOM`, `MaxJobsExceeded`)

If your filter doesn't satisfy this, widen it before arming. Some extra noise is far better than missing a crashloop.

## Step 6 — Volume-control: tighten filters on noisy submitter logs

If a Monitor produces > ~20 events in 10 minutes, it will likely auto-stop (the harness drops over-noisy monitors). Common culprit: per-batch `batch N/114` lines from `submit_phase0.py`. Tighten by:

1. `TaskStop <old_monitor_id>`
2. Re-arm with quarter-milestone alternation: `batch (25|50|75|100)/<TOTAL>` instead of `batch [0-9]+/`
3. Keep all error signals in the new filter

Document the tightening in the active dev_log so the next session uses the cleaner filter.

## Step 7 — Cancel zombie / dead-dependency jobs (unblocks completion monitors)

When one phase of a chained multi-phase case (`AD-spinup → spinup → transient`, submitted with `--dependency=afterok:`) **crashes**, every downstream phase becomes un-runnable. SLURM marks the *immediate* dependent `DependencyNeverSatisfied`, but it often does **not** propagate that state further down the chain: the grand-child phase keeps showing reason `Dependency` (as if it's just waiting) even though its parent is permanently dead. These are **zombie jobs** — they will never run, but they linger in the queue indefinitely (SLURM does not auto-purge them unless `kill_invalid_depend` is set cluster-wide, which it usually is not on Perlmutter).

**Why this matters for monitoring (the trap):** a "wait until the batch fully resolves" watcher that counts *runnable* jobs (`R` + PD with a satisfiable reason) will **never reach 0** — the un-propagated zombies sit in `PD|Dependency` forever, so the completion signal never fires. You wait on a run that finished hours ago.

**Detect** — a `DependencyNeverSatisfied` job is the head of a dead chain; everything downstream of it in the same case is a zombie:

```bash
# any never-satisfiable job = a crashed ancestor somewhere in its chain
squeue -u $USER -h -o "%.12i %r %j" | grep -E "DependencyNeverSatisfied"
```

**Confirm dead before canceling** (never cancel on suspicion): the ancestor phase must have actually failed, not just be slow. Check the crashed phase's `CaseStatus` (should show a non-`success` end, or the job is simply gone with no `case.run success`):

```bash
tail -4 ${A2MC_E3SM_ROOT}/cime/scripts/<case>_<PHASE>/CaseStatus   # look for a crash, not "case.run success"
```

**Read the crash cause by JOB ID — never a log glob.** CIME writes a *new*
`e3sm.log.<jobid>.<timestamp>` (plus `lnd.log.<jobid>.*`, `atm.log.<jobid>.*`) for **every** run
of a case and **never deletes the old ones**. So a case that crashed, was fixed, and resubmitted
has BOTH the stale crash log and the healthy new log in `run/` — and `grep <pattern> run/e3sm.log.*`
matches the *old* crash, reporting a **false "crashed again"** while the current run is fine.
**Capture the SLURM job id at submit** (`case.submit` prints `Submitted job id is <jobid>`) and
inspect only that run's logs:

```bash
JID=<jobid>                    # the id from THIS submission (e.g. 55824374)
RUNDIR=$(cd ${A2MC_E3SM_ROOT}/cime/scripts/<case>_<PHASE> && ./xmlquery -value RUNDIR)
grep -c "ERROR\|ENDRUN\|EDPftvarcon" "$RUNDIR"/e3sm.log.$JID.*   # THIS run only — NOT e3sm.log.*
tail -20 "$RUNDIR"/lnd.log.$JID.*                                # ELM-side detail, same run
```

Cross-check with elapsed time: a job still `RUNNING` far past the crash point (e.g. hours, when the
crash hit at ~2 min into init) cannot have crashed at init — trust `squeue` elapsed over a stale log.

**Cancel surgically** — target only the provably-dead chain by name pattern or explicit IDs; **never** blanket-`scancel -u $USER` (that kills the live variants too):

```bash
ids=$(squeue -u $USER -h -o "%i %j" | grep -E "<dead-variant-name-pattern>" | awk '{print $1}')
echo "$ids"          # eyeball the list FIRST — confirm no live variants matched
scancel $ids
```

Safety: these are your own guaranteed-non-runnable jobs, and cancellation is reversible (resubmit the chain if a fix lands). This is routine housekeeping, not a destructive act — but the *targeting* is what must be exact. Re-list the queue after canceling to confirm only the live chains remain.

## Anti-patterns

1. **Do NOT** rely on the happy-path filter alone — if the process crashes, you'll never know.
2. **Do NOT** arm a Monitor without `persistent: true` for session-length watches — a 5-minute timeout means you stop receiving events 5 min after the harness fires.
3. **Do NOT** sleep/poll to wait for monitor events. The events arrive as notifications. If you need a one-shot "wait until ready," use Bash `run_in_background` with an `until` loop instead.
4. **Do NOT** narrate every event back to the user. Acknowledge with "Normal" or silence for routine, react with proposals for threshold crossings and errors.
5. **Do NOT** assume the auto-monitor survived the previous session — Claude Monitors are session-local. A nohup'd auto-monitor script itself survives, but the *tail process* armed by `Monitor` does not. Always re-arm at session start.

   **And do NOT treat a quiet log as a running job.** A watcher that reports only by appending to a log has a signal that cannot report its own death: the log stops growing, and "the watcher crashed" is byte-identical to "still running, nothing changed." A 258-task array once finished and sat unnoticed for ~19 h for three compounding reasons — the armed tail belonged to a session that had ENDED (decisive on its own: a matching line WAS emitted and went nowhere), the watcher died without writing its terminal line, and the milestone filter matched EXACT counts (`complete=(32|64|96|…)`) while array tasks finish in bursts, so 7 of 8 observed values missed. Full account: `memory/dev_logs_adapterkit/20260815f_Watcher_Publishes_State_To_Disk_*`.

   So: launch with `tools/watch_slurm_array.sh`, which publishes a STATE FILE whose mtime is a heartbeat, and check it with `tools/check_watcher_state.py` (STALE and DIED both exit non-zero). **Liveness is the heartbeat, not a shell trap** — SIGKILL cannot be trapped, so `RUNNING` plus an mtime older than two poll intervals is the only test that survives every death mode. Filter on CROSSINGS (`MILESTONE <pct>%`), never exact counts.

   **A dedicated watcher process is a WEAKER signal than a periodically refreshed extract-and-plot pass over the finished cases**, unless it publishes state to disk: that pass reads the filesystem, is the science artifact you look at anyway, and degrades visibly when it stalls — whereas a log-only watcher's failure looks like silence. Prefer running both; `watch_slurm_array.sh -x <cmd>` drives the refresh from the same heartbeat, so there is one process to keep alive rather than two.
6. **Do NOT** count `PD|Dependency` jobs as "still runnable" in a completion/resolution watcher without first purging zombies (Step 7) — a crashed chain leaves un-propagated dependents in `PD|Dependency` that never run, so the watcher hangs forever on a finished batch.
7. **Do NOT** use blanket `scancel -u $USER` to clear zombies — it kills the live variants too. Cancel by name pattern / explicit IDs, and eyeball the ID list before firing.
8. **Do NOT** `grep e3sm.log.*` / `lnd.log.*` across a case's run dir to check for a crash — CIME keeps **every** prior run's logs, so a stale crashed-run log yields a false "crashed again." Scope to the current run's job id (`e3sm.log.<jobid>.*`), and cross-check elapsed `RUNNING` time (Step 7).

## The `pgrep -f` self-match — it will make your watcher immortal

**A `Monitor` whose loop terminates on `! pgrep -f <script>` never terminates**, because the monitor's
own command line CONTAINS that string and `pgrep -f` matches full command lines. The pattern always
finds at least one process: itself. The loop runs forever, re-emitting a result that finished hours
ago, and a monitor that keeps firing on completed work is noise, which gets tuned out along with the
real events.

Measured 2026-08-22: a V0-verification monitor kept reporting `YEAR=2022` for three runs that had
terminated at 14:50, until it was stopped by hand at 16:43.

**This is the same trap in a third costume, all on one day.** `pkill -f chain_relaunch.sh` killed the
shell that ran it, mid-command, so an edit never applied. A build-wait loop's `pgrep -f` matched
itself and could never see the build finish (recorded in `model-evolution` step 4). And now this.

**Use a PID, not a pattern.** The watcher scripts in this skill already do it right, and the fix is
to copy them rather than hand-roll a pattern match:

```bash
nohup bash watcher.sh > watch.log 2>&1 &     # launch
echo $! > watch.pid                          # record the PID at launch
kill -0 "$(cat watch.pid)" 2>/dev/null       # liveness: unambiguous, no self-match
kill "$(cat watch.pid)"                      # stop: kills that process and nothing else
```

If you genuinely must match on a pattern, exclude yourself (`pgrep -f pat | grep -v $$`) — but the
PID file is simpler and cannot be fooled.

**And prefer a file-based terminal signal over a process check.** A watcher that decides "the work is
done" by asking whether a process still exists is asking the wrong question anyway: the process can
die without finishing. Gate on the artifact the work produces (a final restart, a terminal line in a
log, a state file marked complete), and use the PID only for the watcher's own liveness.

## Cross-references

- **`phase0-design`** — owns the launch itself, including which mode and throttle the ensemble
  was submitted with. Monitoring shape follows from that choice (a per-case array and a node
  task-farm record a crash differently), so read its Step 3 before arming anything here.

- Companion restart workflow: the `restart-failed-jobs` skill.
- **`calibration-goal`** — the run-to-convergence driver: when it hits a phase with an in-flight ensemble it takes a WAIT stop and relies on the `Monitor` events armed here as its **cross-wait re-invocation trigger** (the completion/milestone event resumes the driver loop).
- The interactive-agent operating contract: `AGENTS.md`.
- A site's live auto-monitor script (if any) lives under `use_cases/{Model}_{Case}/analysis/`.

