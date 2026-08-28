# `case_template/` — the files staged into every run

**What lands in each case directory.** For the model that is whatever that model stages into a case directory -- a namelist, an input deck, or CIME case scripts.

## Skills to use when working in this folder

| doing what | skill |
|---|---|
| **anything that materializes or submits a case** | **that model's run-workflow skill** |
| opening a round that needs a new staged file | `phase0-design` |

## Traps worth not rediscovering

- **This is the SHARED fallback template.** Every onboarded model has its own authored `use_cases/<Prefix>_template/`, and `tools/create_use_case.py` seeds from that when it exists. This directory is only reached for a model that has none, so its guidance is deliberately generic -- read the model's own template folder first.
- Files here are **prefixed by model key** (`ecosim_template_config.sh`, `fates_template_config.sh`) and flattened, because one directory holds every model's seed. `create_use_case.py` renames the matching one and deletes the rest.

## Phase 5 archives its submit scripts

A Phase-5 experiment copies its job scripts into `memory/phase_results/{stem}/submit_scripts/` — copy, never move. The run directory is untracked scratch and gets cleaned, while the submit script is the only record of **which binary the run was bound to** and its run-time hash assertion. **Phase 0 is exempt**: its scripts are config-generated and number in the thousands.
