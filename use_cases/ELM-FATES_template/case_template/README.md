# `case_template/` — the files staged into every run

**What lands in each case directory.** For ELM-FATES that is the CIME case-creation and submission scripts copied and sed-parameterized per ensemble member.

## Skills to use when working in this folder

| doing what | skill |
|---|---|
| **anything that materializes or submits a case** | **`offline-testing-workflow`** |
| opening a round that needs a new staged file | `phase0-design` |

## Traps worth not rediscovering

- **A case script MUST source its variables from the configs**, never hand-code them: `a2mc_config.sh` for machine settings and the site config for the rest. Prefer `tools/create_case.sh --write-script` over hand-authoring ([[feedback_case_template_should_source_config]]).
- **No `module load python` before CIME.** It clobbers the `a2mc_env` Python and `create_newcase` dies ([[feedback_no_module_load_python_for_cime]]).
- ELM history files are **`.elm.h0`**, not `.clm2.h0` -- a CLM/CESM habit that silently matches nothing here.

## Phase 5 archives its submit scripts

A Phase-5 experiment copies its job scripts into `memory/phase_results/{stem}/submit_scripts/` — copy, never move. The run directory is untracked scratch and gets cleaned, while the submit script is the only record of **which binary the run was bound to** and its run-time hash assertion. **Phase 0 is exempt**: its scripts are config-generated and number in the thousands.
