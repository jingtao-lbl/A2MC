# `case_template/` — the files staged into every run

**What lands in each case directory.** For EcoSIM that is `run.nml`, the namelist staged into every case directory.

## Skills to use when working in this folder

| doing what | skill |
|---|---|
| **anything that materializes or submits a case** | **`ecosim-run-workflow`** |
| opening a round that needs a new staged file | `phase0-design` |

## Traps worth not rediscovering

- **The 4096-byte cliff.** EcoSIM reads the runfile into a fixed 4096-byte buffer (`fileUtil.F90:25`) and aborts at startup. `backend.create_case` gates on it so materialization fails loudly rather than the run dying later. The case name lives inside the staged paths, so every extra digit costs bytes: `case1` 4092, `case999` 4098, `case59392` 4104. Keep the operative namelist comment-thin and put the prose in a sidecar `*.ANNOTATED.md`.
- Input paths must be **absolute** -- the shipped sample's relative paths do not resolve from a case directory. `create_case` repoints **only** `pft_file_in`, by basename.
- Run length comes from `forc_periods = <y0>, <y1>, <repeats>`, the driver year loop -- **not** from `stop_n`, a non-binding within-timer cap.
- `hist_nhtfrq` is **per-tape**, so adding an hourly tape leaves the daily one alone.

## Phase 5 archives its submit scripts

A Phase-5 experiment copies its job scripts into `memory/phase_results/{stem}/submit_scripts/` — copy, never move. The run directory is untracked scratch and gets cleaned, while the submit script is the only record of **which binary the run was bound to** and its run-time hash assertion. **Phase 0 is exempt**: its scripts are config-generated and number in the thousands.
