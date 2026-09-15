---
name: diagnose-forensics
visibility: public
category: calibration
description: Triage ONE suspicious result before reading it as science — an outlier case, a too-good "best" case, a small failure cluster, a number that looks impossible — to determine FIRST whether it is real or an artifact (contamination, infrastructure timing, mislabeled index, NaN, stale run-state), then root-cause it. Reactive and single-anomaly. Use when the user asks "why is case X an outlier", "is this result real or contamination", "investigate this anomaly / failure cluster", "this best case looks too good". For the whole round's failing targets use phase3-diagnosis instead.
modes:
  requires_fates: false
  nutrient_pathway: any
  scope: [analysis]
  summary: "Artifact-triage then root-cause for a SINGLE anomaly; model-agnostic, with the FATES and adapter tool paths named separately."
---

# Ensemble Forensics (artifact triage, then root cause)

When one result looks surprising — a case scoring far better or worse than its neighbours, a small cluster of failures, a "most-targets" winner that seems too good, a number that cannot physically be right — **triage for artifacts BEFORE reading it as scientific signal.** Most "interesting" tiny patterns turn out to be contamination or infrastructure timing. Only after a result survives triage do you root-cause it.

**Scope, because it is easy to reach for the wrong skill.** This is the REACTIVE, single-anomaly path: *is this one thing real?* The whole round's failing targets, and the ranked root causes behind them, belong to [`phase3-diagnosis`](../phase3-diagnosis/SKILL.md). If you are asking why a round will not calibrate, you are in the wrong skill.

> Worked example this skill generalizes: a bogus "most-targets" champion that turned out to be an experiment output file leaking into the ensemble's extract directory and matching the glob, not a real case.

## Step 1 — artifact triage (do this first)

Run the checks that apply; any hit means the "signal" is an artifact, not science.

- **Contamination (a foreign case in the analysis set).** Is the case ID inside the round's sampled design range? Does its name match the round's case pattern, or is it a leak from a Phase-5 experiment that a glob picked up? List the extract or run directory and look for output files that do not belong. *The suffix that marks an experiment case is per-campaign* — the FATES extractor gates on `_exp`; an adapter round uses whatever its case pattern sets, so read the pattern rather than assuming a literal.
- **Mislabeled index on a partial ensemble.** A screening index can be *position+1* rather than the real case number, especially when the ensemble is incomplete. Resolve the case by its recorded case NUMBER from the scoring output, never by a row index into a file whose length depends on how many cases finished.
- **Failure-signature, not science.** For a failure cluster, check the scheduler's exit codes, end times and node list, plus the tail of the model's own run log, before reading case-ID or parameter-vector clustering as meaningful. Small cohorts of 3 to 10 jobs are prone to infrastructure-timing artifacts that look exactly like signal. **Never parse a scheduler CLI's default output** — it abbreviates states, truncates job names and collapses array ranges; use `sacct -P` / `squeue -r` with explicit format fields ([[feedback_never_parse_a_cli_default_output]]).
- **Garbage metrics.** NaN, Inf, or schema-mismatched values that passed a non-empty check. A reducer that returns a number is not a reducer that returned a *correct* number.
- **Truncated or mis-windowed output.** Does the case actually cover the scored window? A run killed on wall-clock leaves a partial tape that scores as a real, low value. Completion is the model's own terminal signal, not the presence of an output file — for EcoSIM that is the final restart, never the h0 tape.
- **Stale run-state.** Re-derive counts from the live scheduler plus what is on disk plus the newest dated log before quoting a number ([[feedback_verify_run_state_before_quoting]]). A completed run log may be gzipped, in which case a plain `grep` returns a clean and meaningless zero.

If any triage check fires it is a tooling or data bug, not a discovery. **Fix it and supersede** the affected analysis or figure — a new dated log plus a banner on the old one, per the `log` skill's supersede protocol. Never quietly edit the old conclusion.

## Step 2 — root-cause (only after triage passes)

**Check the knowledge base before asserting a mechanism, then confirm in the source.** The KB is five surfaces and they are not interchangeable: the codebase wiki `docs/<model>-knowledge-base/`, the RAG vector index `rag/chroma_db/<profile>/`, the knowledge graph `rag/graphs/<profile>.json`, the MODEL-level adaptive memory `memory/<model>/gained_knowledge/`, and the SITE-level adaptive memory `use_cases/{Model}_{Case}/memory/gained_knowledge/`. Then open the `file:line` the KB gives you in the checkout at `$A2MC_MODEL_PATH` and read the code that USES the value. **Never name a mechanism from a parameter name** — a `description`, a `long_name` or a `units` string can be wrong ([[feedback_param_description_can_lie_verify_in_source]]).

**The tooling splits by model family. Do not inherit the wrong one.**

| Question | ELM / ELM-FATES (CIME) | a non-CIME adapter model |
|---|---|---|
| What parameters does this case have, and how does it differ from another? | `phases/phase3_diagnosis/read_case_parameters.py`, `compare_case_parameters.py` | read the case's staged parameter file(s) directly; an adapter case may span up to three parameter SURFACES, so check which one carries the name |
| Any parameter pinned at a bound? | `phases/phase3_diagnosis/check_edge_parameters.py` | compare the case's row against the param list's `lower_bound` / `upper_bound` |
| Which targets, and how far off? | `phases/phase3_diagnosis/compare_targets.py` | `tools/model_evaluate_case.py`, scoring through each target's OWN `reduce` and window |
| Did it collapse or crash? | `phases/phase3_diagnosis/detect_collapse.py` | `tools/model_ensemble_status.py` for the census; then read the trajectory, since a collapse and a small stand differ only in the time series |
| Are the case's inputs what they claim to be? | checksum the referenced inputs against the base | `tools/model_check_input_compat.py`, `scripts/validate_adapter_ensemble.py` |
| Mechanism: carbon, mortality, nutrients | `analyze_carbon_balance.py`, `analyze_mortality.py`, `analyze_nutrient_balance.py`, `analyze_nutrient_pools.py`, `diagnose_pft_limitations.py` — **all FATES-shaped and vegetation-specific** | no equivalent exists; write the analysis into `phase_results/{stem}/` as a canonical script and say what it measures |
| Plot it | `phases/phase3_diagnosis/plot_diagnostics.py` | the case's figure template in `use_cases/{Model}_{Case}/scripts/`, via `plotting` |

Several FATES tools dispatch through `phases/phase3_diagnosis/run_diagnostics_scripts.py` / `dispatch.py`. For an abiotic or non-vegetation model the mechanism row has no analog at all, and saying so is more useful than running a tool that returns nothing.

## Step 3 — write it up, into the right stream

- **A finding inside a calibration round** → that round's phase log under `use_cases/{Model}_{Case}/memory/logs/`, via `calibration-log`. This is the common case and it is where the round's own reader will look.
- **A tooling, contamination or framework bug** → a `dev_log` recording root cause and fix, plus a supersede banner on any analysis it invalidated.
- **A vetted, generalizable lesson** → propose it for the curated KB via `curate-knowledge`. **Site-level first**: a finding measured at one site, at one base, is site knowledge; promotion to `memory/<model>/gained_knowledge/` is a separate, later decision on evidence from more than one case.

## Notes

- The order is load-bearing: **triage, then root-cause, then write-up.** Reading a pattern as science before triage is how the contamination episodes happened.
- **A deterministic model with a different output had a different input.** If a case will not reproduce, re-check the inputs by checksum rather than reasoning by elimination about the execution path.
- Related skills: [`phase3-diagnosis`](../phase3-diagnosis/SKILL.md) (the whole round, proactive), `restart-failed-jobs` and `restart-adapter-ensemble` (once infra-versus-model is settled), `plotting` (any figure this produces), `curate-knowledge` (to land a confirmed lesson), `log` and `calibration-log` (write-up and supersede).

