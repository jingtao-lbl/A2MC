---
name: arm-local-monitoring
visibility: public
category: calibration
description: Watch an A2MC ensemble running on a WORKSTATION, with no scheduler — the local counterpart of arm-hpc-monitoring. Arms a Claude `Monitor` on the dispatcher log an `A2MC_EXEC_MODE=local` submission writes, checks liveness from the process table and the filesystem rather than from `squeue`/`sacct`, and says which of the HPC three-layer watcher contract applies off a scheduler and which does not. Use after submitting locally, when resuming a session with local runs in flight, or when someone asks how to monitor a run on their laptop.
modes:
  requires_fates: false
  nutrient_pathway: any
  scope: [session]
  summary: "Monitors a local (no-scheduler) A2MC ensemble; model-agnostic."
---

# arm-local-monitoring — watching a run that has no queue

**Use this when `A2MC_EXEC_MODE=local`.** On HPC, `arm-hpc-monitoring` is the skill and its three-layer watcher contract is load-bearing. Here there is no queue, and **most of that contract does not transfer** — following it anyway means building a watcher around a scheduler that is not there.

## What changes, and what does not

| | HPC (`arm-hpc-monitoring`) | local (this skill) |
|---|---|---|
| what a "job" is | a scheduler record | a process, and the files it writes |
| liveness | `sacct` / `squeue -r` | the process table, plus output mtime |
| the log to watch | the auto-monitor / submitter logs | `local_dispatch.log`, beside the cases |
| the watcher script | required — polls the scheduler | **not needed**, see below |
| the heartbeat check | `tools/check_watcher_state.py` | **does not apply** — it is scheduler-aware |
| completion | terminal-state allow-list, cross-checked | `check_case_status` — unchanged, it already reads the filesystem |

**The one thing that is identical is the one that matters most: completion.** `check_case_status` requires the FINAL RESTART, not the presence of an output tape, because a run killed mid-way leaves a tape too. That test is filesystem-based on every backend, so it is exactly as valid on a laptop as on Perlmutter. Do not invent a local completion test; call the backend's.

**Why no watcher script here.** On HPC the watcher exists because the scheduler is a separate system whose state must be polled and republished. Locally the thing you want to know — is the dispatcher alive, have the cases written their restarts — is readable directly, so a watcher would be a process whose only job is to look at what you can already see, and it would then need its own liveness check ([[feedback_a_check_that_cannot_fail]]).

## Step 1 — Find the dispatch, and confirm it is actually running

A local submission writes three things next to the cases. Read them rather than asking the user:

```bash
ENS=<the ensemble root, the parent of the case dirs>
ls "$ENS"/local_dispatch.log "$ENS"/local_cases.txt        # written by the dispatcher
cat <case>/job_id.txt                                       # LOCAL-<dispatcher pid>-<n>
```

The dispatcher PID is embedded in every `job_id.txt`. Check it, and check it is the dispatcher rather than a recycled PID:

```bash
PID=$(sed 's/^LOCAL-\([0-9]*\)-.*/\1/' <case>/job_id.txt)
ps -o pid=,etime=,args= -p "$PID" 2>/dev/null || echo "dispatcher $PID is GONE"
```

**A dead dispatcher with unfinished cases is the local analogue of a crashed watcher, and it is silent the same way**: the log simply stops growing, which is byte-identical to a long case running quietly. That is why the step is `ps`, not "the log looks idle".

## Step 2 — Arm the Monitor on the dispatch log

One Monitor, on `local_dispatch.log`. The filter must carry **both** a progress signal and the error signatures, for the reason `arm-hpc-monitoring` gives and which is not HPC-specific: *silence on a crash is identical to silence on a long run*.

```
EcoSIM start|EcoSIM end|local dispatch end|WARN: no h0 tape|ERROR|Traceback|Killed|Segmentation|Cannot allocate
```

`EcoSIM start` / `EcoSIM end` are printed by the run template per case, so they are the progress signal — on a serial workstation run they may be hours apart, which is precisely why a transitions-only filter would be mute. Adapt the model-specific pair to whichever backend is running; the two classes (progress, failure) are the contract.

**Two failure signatures matter more locally than on HPC** and belong in every local filter. `Killed` is the OOM killer, which on a shared workstation arrives without warning and leaves a partial tape. `Cannot allocate` is the same problem caught earlier. Neither has a scheduler to record them, so the log is the only place they appear.

## Step 3 — React with proposals, not relay

Same discipline as the HPC skill. The events differ:

| event | the proposal |
|---|---|
| `local dispatch end` | run `check_case_status` over every case; report COMPLETED vs FAILED, and **do not call the ensemble finished on the dispatcher exiting** — it exits when the last case is launched-and-returned, including cases that died |
| `WARN: no h0 tape` on any case | that case started and produced nothing; propose reading its tail before the rest finish, since the cause is usually shared |
| `Killed` / `Cannot allocate` | propose LOWERING `A2MC_LOCAL_WORKERS` and re-running only the affected cases. This is the local equivalent of a wall-clock kill and the remedy is concurrency, not walltime |
| long silence with the dispatcher alive | normal on a workstation. Check output mtime before proposing anything — a serial case legitimately runs for hours |
| dispatcher gone, cases unfinished | the sharp one. Report which cases never completed and propose relaunching **only those** |

## Step 4 — Verify the Monitor can actually fire

Do not trust an unproven filter ([[feedback_exact_strings_are_contracts]]). The strings above are written by the run template, so confirm they are the strings THIS template emits:

```bash
grep -n 'echo "' <the run template>          # the progress lines the filter must match
grep -c 'EcoSIM start' "$ENS"/local_dispatch.log   # >0 once the first case has begun
```

A filter matching nothing is indistinguishable from a quiet run, which is the failure this step exists to prevent.

## Anti-patterns

1. **Porting the three-layer watcher contract wholesale.** Layer (c), the heartbeat via `tools/check_watcher_state.py`, is scheduler-aware and does not apply. Building layers (a) and (b) around a `squeue` that does not exist produces a watcher that reports nothing forever.
2. **Treating the dispatcher's exit as ensemble completion.** It exits when the last case returns, successfully or not. Completion is `check_case_status` over every case.
3. **Inventing a local completion test.** The backend already has one, it is filesystem-based, and it encodes that an output tape means STARTED rather than FINISHED.
4. **Running the poll loop as the Monitor command.** Session-local, same anti-pattern as on HPC: it dies with the session and reports nothing afterwards.
5. **Assuming a laptop can take the HPC worker count.** `A2MC_LOCAL_WORKERS` counts WHOLE cases, each a serial binary with its own memory footprint. The default is `min(4, cpu_count)` for that reason.

## Cross-references

- `arm-hpc-monitoring` — the scheduler counterpart; read it for the reasoning this skill diverges from, and use it whenever `A2MC_EXEC_MODE` is `hpc` (the default)
- `models/ecosim/README.md` §"Where the cases run" — what local mode writes and where
- `restart-adapter-ensemble` — relaunching the cases this skill finds unfinished
- `memory/dev_logs_adapterkit/20260915g_A_Local_Execution_Mode_For_EcoSIM_And_The_Silent_Dry_Run.md` — why local mode is small, and the silent dry run that preceded it

## Notes

- **Branch fit:** the `models/` adapter registry is an `adapter-kit` construct, and `A2MC_EXEC_MODE` is implemented on the EcoSIM backend today. PFLOTRAN and ATS are queued to converge on the same switch; until they do, this skill's Step 1 applies wherever a dispatcher log exists and the rest is model-agnostic.

