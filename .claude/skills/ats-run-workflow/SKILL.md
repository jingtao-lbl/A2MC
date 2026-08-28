---
name: ats-run-workflow
description: Run and test ATS — the XML-deck counterpart to ecosim-run-workflow. Design a probe or ensemble, write perturbed Teuchos ParameterList decks, assemble case directories, submit, and score against the deck's own observation .dat files. Use for "run an ATS experiment/probe/ensemble", "set up ATS cases", "submit the ATS array", "why did my ATS cases fail", "score the ATS run", or any ATS Phase-0/Phase-5 work. States plainly which half of the adapter is complete and which is v0.1, because a first ATS case is onboarding the run path as well as the case.
visibility: public
category: calibration
modes:
  requires_fates: false
  nutrient_pathway: any
  scope: [ats]
  summary: "ATS's Phase-0/Phase-5 procedure — a nested XML deck as the parameter file, observations declared in the deck, and a run path that is honestly v0.1."
---

# ats-run-workflow — run and test ATS

The ATS counterpart to `ecosim-run-workflow`. ATS is structurally unlike both siblings: it is **C++**, its parameters live in a **nested Teuchos ParameterList XML deck addressed by path**, and its calibration targets come from the deck's **`observations` block** rather than from a history tape.

## ⚠ Read this before planning a campaign

`models/ats/backend.py` states its own status, and this skill repeats it rather than papering over it:

> * `parse_parameters` / `parse_outputs` / `write_parameter_file` — **COMPLETE** (XML in/out).
> * `create_case` / `submit_ensemble` / `check_case_status` / `extract_history_variables` — **functional-minimal**: they encode the real ATS run shape (stage deck, `srun ats`, completion markers, `.dat` extraction) but the run-template and observation-injection polish is deferred.

And there is no worked case: `use_cases/ATS_template/` carries `<PLACEHOLDER>` on every path and a null on every observation, on purpose. **A first real ATS case is onboarding the run path as well as the case** — expect to fix the run template, and budget for it.

That is not a reason to avoid the model. It is a reason to (a) run a **single case end to end before designing an ensemble**, and (b) log what breaks, because the next person inherits it.

## Step 0 — source the RIGHT configs

```bash
source use_cases/ATS_<Case>/config/ats_<case>_config.sh    # auto-sources a2mc_noncime_config.sh
```

**`a2mc_config.sh` is the CIME/FATES one and is the wrong file here** ([[feedback_two_machine_configs_cime_vs_noncime]]). The site config chains the right one and repairs a wrong choice, but cannot unset what a mistaken CIME config already exported.

## Step 1 — the parameter surface is the XML deck, addressed by PATH

A parameter is **not** a bare name. It is a leaf in a nested `ParameterList`, addressed by its path through the tree, and `ATSParameterParser` / `set_parameter_values` read and write it in place. The grouping axis is **`region`** — a *string* axis, so a tool that coerces the axis to an integer PFT id raises on this list.

**Every value in the shipped template is a `<PLACEHOLDER>` on purpose.** Filling one with a plausible-looking number is worse than leaving it, because a fabricated config looks like a working one ([[feedback_placeholder_targets_structure_not_values]]). The RED gate is the deliverable until the real values arrive.

**`bound_source` is required on every row** from the five-term vocabulary; for a model with no worked case, honest rows are `provisional:` and say why.

## Step 2 — targets are declared IN the deck, not in a history flag

This is the difference that catches people coming from FATES or EcoSIM. There is no history tape and no `hist_fincl` analogue:

> ATS targets are declared as observation entries in the deck, so `create_case` **injects an observations block** rather than a hist list.

Two consequences:

- **An observation is already reduced over its region by the deck's `functional`.** Reducing it again in the scoring path double-applies the reduction. Read what the deck's functional already did before choosing a `reduce`.
- **A target that is not in the deck produces no output at all** — not a NaN, not an empty column. If a target is missing after a run, check the injected observations block before suspecting extraction.

Outputs are HDF5/XDMF visualization plus **comma-delimited observation `.dat` files**.

## Step 3 — one case, end to end, before any ensemble

```bash
python scripts/materialize_adapter_ensemble.py --dry-run          # ALWAYS dry-run first
python scripts/materialize_adapter_ensemble.py --baseline --baseline-index 0
python scripts/validate_adapter_ensemble.py --expect-baseline
```

**Always materialize a `--baseline`.** A round whose V0 exists only as a matrix row cannot answer "does the base still reproduce?".

Then run that single case and read its output before scaling. Given the v0.1 run wiring, the questions to answer first are mechanical: does the staged deck resolve its mesh path, does `srun ats` start, does the completion marker appear, and does a `.dat` file with the expected observation columns exist.

## Step 4 — submit and monitor

`create_case` writes a per-case run script (`# A2MC ATS case run script (v0.1). Runs ATS on the staged deck.`) and `submit_ensemble` dispatches it. Arm monitoring the moment anything is submitted, on **your own** launches only ([[feedback_monitor_only_own_session_launches]]) — follow `arm-hpc-monitoring` rather than re-deriving a watcher.

**Census before scoring.** A scheduler-COMPLETED case is not a usable case; check that each case actually produced its observation `.dat` with the expected columns, and treat a partially covered window as an ERROR rather than a smaller sample — early termination is usually instability, so the surviving tail is biased.

## Step 5 — the Phase-6 figure this model owns

`phase6-refinement` step 1b requires a sim-vs-obs overlay **covering every scored target** before the verdict is written, and routes the implementation here for ATS.

The figure must carry **one panel per scored target**, the **measurements as measured** with gaps left as gaps, the **control on top** so the V0 gate is visually confirmed rather than asserted, and the **whole trajectory** rather than the windowed number alone. Score through the target's own `reduce` — remembering the deck's `functional` has already reduced over the region — and copy the case's template from `use_cases/{Model}_{Case}/scripts/`, adapting it so the canonical script lives in `phase_results/{stem}/` beside its caption and data.

**Self-check before trusting it.** The windowed number the figure draws must reproduce what the scoring path reports. If it does not, the figure is drawing something other than what the round is scored on, and it should say so instead of plotting.

## Model source, if it comes to that

ATS builds into a **shared CMake tree**, so `model-evolution` step 3.5 applies in full: archive the binary *before* building a change, record it with `tools/binary_archive_manifest.py --generate`, and bind every run to the archive rather than the live build path — a queued job resolves its executable at run time, and the rebuild that swaps it need not be yours ([[feedback_bind_runs_to_archived_binaries]]). Note that the manifest's `ARCHIVES` registry has **no ATS entry yet**; adding one is part of the first model-evolution work on this model.

Push model source to the `fork` remote only, never upstream ([[feedback_model_source_push_fork_only]]).

## Footguns, collected

- Sourcing `a2mc_config.sh` instead of letting the site config chain the non-CIME one.
- Expecting a history tape or a `hist_fincl` list — targets are **injected into the deck**.
- Double-reducing an observation the deck's `functional` already reduced over its region.
- Filling a `<PLACEHOLDER>` with a plausible number so the config *looks* ready.
- Designing an ensemble before one case has run end to end, on a run path its own author calls v0.1.
- Treating a scheduler-COMPLETED case as a scored case.
- Coercing the `region` grouping axis to an integer.

## Related skills

- `phase0-design` (round opening), `phase5-testing` (the phase router), `phase6-refinement` (step 1b routes its figure requirement here), `restart-adapter-ensemble` (recovering a failed set), `arm-hpc-monitoring`, `calibration-discipline`, `plotting`, `model-evolution`, `onboard-case`, `onboard-model`.
- Siblings that do **not** transfer: `ecosim-run-workflow` (namelist-driven), `pflotran-run-workflow` (card-deck driven), `offline-testing-workflow` (CIME/FATES).

## Notes

- **Branch fit:** `adapter-kit` and any branch carrying the ATS adapter. Model-specific by design ([[feedback_per_model_scripts_not_generic]]).
- **Status:** written against a template case, not a worked one. Refine it from the first real ATS campaign rather than trusting it whole — and use `refine-skill` so the change is evidence-backed.

## Changelog

- 2026-08-26: Initial version — written to fill the placeholder the 107-README campaign cited. ATS had **no run-workflow skill at all**, so every case README naming `ats-run-workflow` was pointing at something that did not exist. Distilled from `models/ats/{spec,backend,parameter_parser,output_parser}.py` read directly, and from `use_cases/ATS_template/`. Deliberately states the adapter's own v0.1 status rather than reading as if a worked case existed: parameter/output I/O is complete, the run wiring is functional-minimal, and there is no real ATS case on this machine. PI-directed: placeholders during the campaign, skills immediately after.
