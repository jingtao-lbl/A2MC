# `case_template/` — the files staged into every run

**What lands in each case directory.** For PFLOTRAN that is the input deck (`pflotran.in`), the thermodynamic database, and the mesh/restart/rainfall files each perturbed case needs beside it.

## Skills to use when working in this folder

| doing what | skill |
|---|---|
| **anything that materializes or submits a case** | **`pflotran-run-workflow`** |
| opening a round that needs a new staged file | `phase0-design` |

## Traps worth not rediscovering

- **The deck IS the parameter file.** A PFLOTRAN parameter is an input-deck card addressed by its **block path**, so writing a parameter means rewriting a card in place, not editing a separate file.
- **The database is a SECOND tuned surface** (`A2MC_PFLOTRAN_DATABASE`). A case that stages the deck and forgets the database is not the case you designed.
- The V0 reference is a `*-mas.dat` file (`A2MC_PFLOTRAN_REFERENCE_MAS`); keep it beside the deck it belongs to.

## Phase 5 archives its submit scripts

A Phase-5 experiment copies its job scripts into `memory/phase_results/{stem}/submit_scripts/` — copy, never move. The run directory is untracked scratch and gets cleaned, while the submit script is the only record of **which binary the run was bound to** and its run-time hash assertion. **Phase 0 is exempt**: its scripts are config-generated and number in the thousands.

---

## Why this folder was documentation-only until 2026-08-27, and what it now owns

**PFLOTRAN does not stage a case from this folder, and that is by design.** `models/pflotran/backend.py::create_case` copies the supporting files (mesh, restart checkpoint, rainfall forcing, thermodynamic database) from **the directory that holds `$A2MC_BASE_PARAM_FILE`** -- a base case on scratch -- and renders each case's own `submit.sh` from **`models/pflotran/runtemplates/hpc_standalone.sh.tmpl`**, which lives in the adapter. So the "template" was already two real things, both outside this folder.

That is why `PFLOTRAN_miniLEO` ran a whole round with nothing here but a README, and why the absence was not a defect. **What it does not give you is a way to submit N cases in one job**, because every case gets its own script and `submit_ensemble` loops `sbatch` over them. At 4096 members that is 4096 submissions against Perlmutter's 5000-job limit.

**So this folder owns exactly one artifact:** `submit_ensemble_array.sh`. Copy it into your case's `case_template/`, set every value marked `<<< SET`, and commit the copy with the case.

> ⚠ **It is NOT the default submitter, and the queue ceiling is not an unsolved problem.** `scripts/submit_adapter_ensemble_batched.py` submits per-case jobs in queue-aware waves against the 5000-job limit, with a reserve for the account's other lanes and idempotency on `job_id.txt`; it is what launched `PFLOTRAN_miniLEO R1` and it survived a mid-wave kill at 52 of 800 submissions because of that idempotency. **Use it unless you have a specific reason not to.** An array buys one job id and near-zero submission load at 10^3-10^4 cases; it costs per-case submit-script provenance, which is this project's only record of which binary a run was bound to ([[feedback_bind_runs_to_archived_binaries]]). The array script's own header carries the full trade-off.

| where a PFLOTRAN case's pieces really come from | |
|---|---|
| mesh, restart, forcing, database | the base case dir beside `$A2MC_BASE_PARAM_FILE` |
| the perturbed deck | written in place by `write_parameter_file` before `create_case` runs |
| the per-case `submit.sh` | `models/pflotran/runtemplates/hpc_standalone.sh.tmpl` |
| **the ensemble array submitter** | **here** |
