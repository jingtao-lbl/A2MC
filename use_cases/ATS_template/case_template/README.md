# `case_template/` — the files staged into every run

**What lands in each case directory.** For ATS that is the XML ParameterList deck and the mesh file it references.

## Skills to use when working in this folder

| doing what | skill |
|---|---|
| **anything that materializes or submits a case** | **`ats-run-workflow`** |
| opening a round that needs a new staged file | `phase0-design` |

## Traps worth not rediscovering

- **The deck IS the parameter file**, and a parameter is addressed by its **path through the nested ParameterList**, not by a bare name.
- **The run wiring is v0.1 and unproven.** `models/ats/backend.py` says so in its own docstring: a first real ATS case is onboarding the run path as well as the case.

## Phase 5 archives its submit scripts

A Phase-5 experiment copies its job scripts into `memory/phase_results/{stem}/submit_scripts/` — copy, never move. The run directory is untracked scratch and gets cleaned, while the submit script is the only record of **which binary the run was bound to** and its run-time hash assertion. **Phase 0 is exempt**: its scripts are config-generated and number in the thousands.
