# A2MC Tool Index (GENERATED — do not hand-edit)

**Regenerate:** `python tools/generate_tool_index.py` · **Verify:** `--check` (exit 1 if stale)

Every script in `tools/` and `scripts/`, with its own module docstring's first line, and **which agent-facing document names it**. A script named by no skill, memory, or top-level doc is flagged **ORPHAN** — that is the discoverability debt, not a bug: each orphan is a candidate either to be cited from the skill that should own it, or to be retired.

This is the complete one-line lookup. `tools_reference.md` is the hand-written narrative reference (APIs, worked usage) for a handful of them — the two are complementary.

**163 scripts** (145 CLI, 18 library) · **18 orphans** (11 %)

---

## Orphans — named by no skill, memory or top-level doc

| script | summary |
|---|---|
| `tools/calendar_blocks.py` | Leap-aware calendar blocking for model history tapes — one implementation, shared |
| `tools/case_parser.py` | case_parser.py - Parse CIME case directories into A2MC ConfigMode |
| `tools/check_phase_script_docs.py` | check_phase_script_docs.py — verify each phases/phaseN_*/CLAUDE.md "Scripts in This |
| `tools/compare_netcdf_science.py` | Compare two run directories' NetCDF outputs on their DATA, not their bytes |
| `tools/elm_ecosystem_variables.py` | ELM ecosystem-level (site-scalar) output-variable registry for ECO_ targets |
| `tools/extract_ecosystem_series.py` | Ecosystem-level (site-scalar) calibration-target extraction — the ECO_<var> path |
| `tools/extract_land_series.py` | ELM land-column (snow + soil) calibration-target extraction — SNOW_/SOIL_ keys |
| `tools/extract_site_common.py` | Shared readers for the level-dispatched extractors (ecosystem / land site / profile) |
| `tools/generate_tool_index.py` | Generate the index of every script in `tools/` and `scripts/`, and name the ORPHANS |
| `tools/land_output_variables.py` | ELM land-column (snow + soil) output-variable registry for SNOW_/SOIL_ targets |
| `tools/plot_sim_vs_obs_timeseries_ecosim_biocon.py` | Sim-vs-obs TIME SERIES for one EcoSIM **BioCON** case, driven by the site's `targets.yaml` |
| `tools/populate_experiments.py` | Populate experiment entries into workflow_state.json for Phase 6 resume |
| `tools/round_paths.py` | Round-aware path resolution for A2MC calibration artifacts |
| `tools/score_adapter_variants.py` | Score a set of adapter-model experiment variants against a case's validation targets |
| `scripts/audit_param_list_against_api.py` | audit_param_list_against_api.py - One-off utility to find renamed/removed |
| `scripts/convert_official_docs.py` | convert_official_docs.py - Convert FATES tech-doc RST source to Markdown |
| `scripts/ecosim_case_census.py` | Case-level census for a node-packed or task-farmed EcoSIM ensemble |
| `scripts/migrate_fates_wiki.py` | Migrate FATES wiki content to organized knowledge base structure |

---

## All scripts, by purpose

### Checkers and gates

| script | | summary | named by |
|---|---|---|---|
| `tools/check_bound_source.py` | CLI | Check a parameter list's `bound_source` column against the canonical vocabulary | `skill:round-housekeeping`, `TODO.md` |
| `tools/check_calibration_log_conformance.py` | CLI | check_calibration_log_conformance.py — assert a CALIBRATION log matches the `calibration-log` | `skill:calibration-discipline`, `skill:calibration-log`, `skill:log` +4 |
| `tools/check_calibration_rounds.py` | CLI | Validate an existing calibration_rounds.yaml round against the LIVE A2MC config | `skill:a2mc-init`, `skill:onboard-case`, `skills_catalog.md` |
| `tools/check_capability_change_logged.py` | CLI | Flag an A2MC CAPABILITY change that carries no version bump and no dev log | `TODO.md` |
| `tools/check_case_script_tier.py` | CLI | A script reused across phases belongs in the case's TEMPLATE tier, not copied between stem folders | `skill:calibration-discipline`, `skill:onboard-case`, `skill:phase0-design` +8 |
| `tools/check_cycle_reports.py` | CLI | Assert that every CLOSED experiment cycle has a cycle report | `skill:calibration-discipline`, `skill:write-report`, `TODO.md` |
| `tools/check_deferred_work_queued.py` | CLI | A log that DEFERS work must route that work into TODO.md, the queue that is actually read | `TODO.md` |
| `tools/check_dev_log_for_version.py` | CLI | Does the version in CLAUDE.md have a dev log that CLAIMS it? | `memory:feedback_commit_only_your_own_changes` |
| `tools/check_doc_claims.py` | CLI | Does any LIVE doc still make a claim we have retired? | `skill:memory-checkup`, `skills_catalog.md`, `AGENTS.md` +1 |
| `tools/check_ecosim_rag_queries.py` | CLI | Model RAG guard: golden-query content check + count-regression check | `skill:cherrypick-from-main`, `skill:inject-knowledge`, `skill:onboard-model` +4 |
| `tools/check_ecosim_validation_years.py` | CLI | Assert an EcoSIM case's SCORING calendar matches the calendar it actually ran on | `TODO.md` |
| `tools/check_graph_coverage.py` | CLI | Which curated relations actually reach a model's knowledge graph — the `wire-knowledge-graph` audit | `skill:wire-knowledge-graph`, `TODO.md` |
| `tools/check_log_conformance.py` | CLI | check_log_conformance.py — assert a dev/ana log matches the `log` skill's contract | `skill:calibration-log`, `skill:log`, `skill:manage-auto-memory` +4 |
| `tools/check_log_placeholders.py` | CLI | A rendered log must not carry a PLACEHOLDER where a finding belongs | `TODO.md` |
| `tools/check_memory_bucket.py` | CLI | Validate the git-synced Claude memory bucket (.claude_memory/) | `skill:add-skill`, `skill:manage-auto-memory`, `skill:memory-checkup` +11 |
| `tools/check_offline_log_evidence.py` | CLI | Evidence gate for offline (interactive-agent) phase logs — docs/33 §3a (meta-validation | `skill:calibration-discipline`, `skill:calibration-goal`, `skill:calibration-log` +12 |
| `tools/check_param_branch_sites.py` | CLI | Enumerate EVERY source site that reads a model parameter, with its enclosing subroutine | `memory:feedback_param_description_can_lie_verify_in_source` |
| `tools/check_pflotran_seed_citations.py` | CLI | check_pflotran_seed_citations.py - verify every citation in the PFLOTRAN | `memory:feedback_verify_derived_numbers_not_just_citations`, `TODO.md` |
| `tools/check_phase_script_docs.py` | CLI | check_phase_script_docs.py — verify each phases/phaseN_*/CLAUDE.md "Scripts in This | **ORPHAN** |
| `tools/check_rag_coverage.py` | CLI | RAG coverage self-test (docs/33 §3c, meta-validation Phase 1). Catches the "a kb_source or a | `skill:rebuild-rag`, `skill:validate-rag-chain`, `memory:feedback_offline_agent_operating_discipline` +2 |
| `tools/check_rag_index_committed.py` | CLI | Assert the COMMITTED RAG index matches the COMMITTED expected_counts | `TODO.md` |
| `tools/check_rag_queries.py` | CLI | RAG golden-query test (meta-validation, content layer) | `skill:rebuild-rag`, `skill:validate-rag-chain`, `TODO.md` |
| `tools/check_report_conformance.py` | CLI | Check a report under use_cases/<site>/reports/ against the `write-report` contract | `skill:write-report` |
| `tools/check_report_figures.py` | CLI | Report figure-caption linter. Catches the duplicated-caption footgun: a markdown image whose | `skill:write-report`, `memory:feedback_report_figure_empty_alt_text` |
| `tools/check_setup_ready.py` | CLI | Goal-conditional 'is this site ready for Phase 0?' preflight for A2MC setup | `skill:a2mc-init`, `skill:onboard-case`, `skill:setup-discipline` +6 |
| `tools/check_skill_claims.py` | CLI | Verify a log's "Skills and memory invoked" claim against what was ACTUALLY invoked | `skill:calibration-discipline`, `skill:write-report`, `memory:feedback_commit_only_your_own_changes` +1 |
| `tools/check_skill_registry.py` | CLI | Mechanical skill-registry + contract health check for A2MC (no LLM, no deps) | `skill:add-skill`, `skill:calibration-goal`, `skill:cherrypick-from-main` +14 |
| `tools/check_stage_ready.py` | CLI | Which SETUP STAGE is this clone in, and is that stage mechanically complete? | `skill:onboard-model`, `skill:setup-discipline`, `user_guide.md` +1 |
| `tools/check_stem_pairing.py` | CLI | Assert the STEM INVARIANT: every `phase_results/{stem}/` has a matching `logs/{stem}.md` | `skill:calibration-log`, `TODO.md` |
| `tools/check_version_consistency.py` | CLI | Guard the A2MC version number against collision and drift | `memory:feedback_commit_only_your_own_changes`, `CLAUDE.md`, `TODO.md` |
| `tools/check_watcher_state.py` | CLI | Report whether a `watch_slurm_array.sh` watcher is alive, finished, or silently dead | `skill:arm-hpc-monitoring`, `skill:ecosim-run-workflow`, `skill:phase0-design` +2 |
| `tools/check_workflow_state_offline.py` | CLI | Invariant checker for the offline resume state (`workflow_state_offline_r{RR}.json`) | `skill:calibration-discipline`, `skill:calibration-goal`, `skill:onboard-session` +7 |
| `scripts/check_adapter_calibration_rounds.py` | CLI | Validate an ADAPTER (non-FATES) calibration_rounds.yaml round vs the live config + CSV | `skill:onboard-case` |
| `scripts/check_surrogate_gate.py` | CLI | Decide the surrogate gate's CONDITION 2 on a completed ensemble, by a bar fixed in advance | `TODO.md` |

### Validators

| script | | summary | named by |
|---|---|---|---|
| `tools/validate_adapter_parity.py` | CLI | Compare each model adapter's ModelSpec field population against its siblings | `skill:cherrypick-from-main`, `memory:feedback_per_model_scripts_not_generic`, `TODO.md` |
| `tools/validate_adapter_parser_contract.py` | CLI | Validate an adapter's parser CONTRACT: call shape, record shape, and field completeness | `TODO.md` |
| `tools/validate_agent_surface.py` | CLI | validate_agent_surface.py — pre-flight validator for the interactive-agent surface | `skill:memory-checkup`, `memory:feedback_a_gate_must_measure_the_branch_not_the_disk`, `memory:feedback_leak_is_dev_logs_plans_private_files_not_paths` +2 |
| `tools/validate_ats_wiki.py` | CLI | validate_ats_wiki.py — ATS-specific codebase-wiki validator series | `TODO.md` |
| `tools/validate_curated_yaml.py` | CLI | validate_curated_yaml.py - Model-generic curated-relationships YAML validator (V2) | `skill:onboard-model`, `skill:wire-knowledge-graph`, `skills_catalog.md` +1 |
| `tools/validate_model_memory.py` | CLI | Validate a model's adaptive-memory store against what MemoryManager actually READS | `TODO.md` |
| `tools/validate_model_targets.py` | CLI | Validate a backend-dispatched calibration targets.yaml against a model's output registry | `skill:cherrypick-from-main`, `skill:ecosim-run-workflow`, `skill:onboard-case` +4 |
| `tools/validate_param_list.py` | CLI | Validate a FATES parameter-list CSV against the model parameter file (docs/37) | `skill:port-param-file`, `memory:feedback_verify_pft_identity_across_versions`, `TODO.md` |
| `tools/validate_restart_script.py` | CLI | Validate auto-generated ELM-FATES ensemble restart scripts | `skill:restart-failed-jobs`, `memory:feedback_build_validators_for_all_pitfalls`, `skills_catalog.md` |
| `tools/validate_seed_coverage.py` | CLI | Validate curated-seed COVERAGE: every category has a mechanism, every parameter is reachable | `skill:inject-knowledge`, `skill:onboard-model`, `skill:rebuild-rag` +2 |
| `tools/validate_submission_plan.py` | CLI | Pre-flight validation for a Phase 0 ensemble submission | `skill:offline-testing-workflow`, `skill:phase0-design`, `memory:feedback_build_validators_for_all_pitfalls` +2 |
| `tools/validate_targets_config.py` | CLI | validate_targets_config.py — pre-flight validator for a case's targets.yaml | `skill:a2mc-init`, `skill:onboard-case`, `memory:feedback_build_validators_for_all_pitfalls` +2 |
| `tools/validate_wiki_vs_source.py` | CLI | validate_wiki_vs_source.py - Generic wiki-vs-source validator (adapter-kit V1) | `skill:onboard-model`, `TODO.md` |
| `scripts/validate_adapter_ensemble.py` | CLI | Validate a MATERIALIZED adapter ensemble before submission — a hard pre-submit gate | `skill:ats-run-workflow`, `skill:diagnose-forensics`, `skill:ecosim-run-workflow` +3 |
| `scripts/validate_pflotran_ensemble.py` | CLI | Validate a materialized PFLOTRAN ensemble before submission — a hard pre-submit gate | `skill:phase0-design`, `skill:phase5-testing`, `TODO.md` |

### Builders (RAG, indexes, cases)

| script | | summary | named by |
|---|---|---|---|
| `scripts/build_ecosim_rag.py` | CLI | Build the EcoSIM RAG/GraphRAG index (profile ecosim-2dea74d9) | `skill:inject-knowledge`, `skill:onboard-model`, `skill:rebuild-rag` +6 |
| `scripts/build_pflotran_rag.py` | CLI | Build the PFLOTRAN RAG index (profile pflotran-157a26f7) | `skill:rebuild-rag`, `skill:wire-knowledge-graph`, `memory:feedback_per_model_scripts_not_generic` +2 |
| `scripts/build_rag_index.py` | CLI | Build RAG and GraphRAG indexes for the A2MC version-association infrastructure | `skill:build-rag-from-scratch`, `skill:inject-knowledge`, `skill:onboard-model` +16 |

### Extraction

| script | | summary | named by |
|---|---|---|---|
| `tools/extract_ADSP_RGSP_slim.py` | CLI | extract_ADSP_RGSP_slim.py — fast 2-variable extractor for spinup phases | `skill:arm-hpc-monitoring`, `skill:scientific-analysis`, `memory:feedback_elm_history_files_are_elm_h0` +1 |
| `tools/extract_and_plot_selected_cases.py` | CLI | extract_and_plot_selected_cases.py — extract + V0-check + overlay-plot a SMALL | `skill:compare-calibration-rounds`, `skill:ecosim-run-workflow`, `skill:offline-testing-workflow` +8 |
| `tools/extract_ecosystem_series.py` | lib | Ecosystem-level (site-scalar) calibration-target extraction — the ECO_<var> path | **ORPHAN** |
| `tools/extract_knowledge.py` | CLI | Knowledge Extraction Module for A2MC | `tools_reference.md`, `CLAUDE.md` |
| `tools/extract_land_series.py` | lib | ELM land-column (snow + soil) calibration-target extraction — SNOW_/SOIL_ keys | **ORPHAN** |
| `tools/extract_monthly_variables_FATES.py` | CLI | Extract All Variables from Monthly ELM-FATES Output (Comprehensive) | `skill:arm-hpc-monitoring`, `skill:compare-calibration-rounds`, `skill:offline-testing-workflow` +7 |
| `tools/extract_site_common.py` | lib | Shared readers for the level-dispatched extractors (ecosystem / land site / profile) | **ORPHAN** |
| `scripts/extract_and_plot_adapter_ensemble.py` | CLI | Extract + plot an ADAPTER (non-FATES) model ensemble's trajectories | `skill:phase1-exploration`, `skill:phase2-screening` |
| `scripts/extract_crossed_ensemble_targets.py` | CLI | Extract the scored-target Y-matrix for a CROSSED TR{N}MG{M} adapter ensemble | `skill:compare-calibration-rounds` |
| `scripts/extract_ecosim_outputs.py` | CLI | extract_ecosim_outputs.py - Build ecosim_output_info_<commit>.cdl from a | `skill:onboard-model`, `memory:feedback_check_kit_precedent_before_asking`, `memory:feedback_per_model_scripts_not_generic` +1 |
| `scripts/extract_elm_outputs.py` | CLI | extract_elm_outputs.py - Build elm_output_info_<commit>.cdl from ELM source | `codebase_wiki_generation_roadmap.md`, `mode_aware_howto.md`, `mode_aware_workflow.md` +2 |
| `scripts/extract_flat_ensemble_targets.py` | CLI | Extract the scored-target Y-matrix for a FLAT `<prefix>case{N}` adapter ensemble | `skill:compare-calibration-rounds`, `skill:summarize-calibration-round`, `TODO.md` |
| `scripts/extract_pflotran_outputs.py` | CLI | extract_pflotran_outputs.py — Build pflotran_output_info_<commit>.json, the | `TODO.md` |

### Plotting

| script | | summary | named by |
|---|---|---|---|
| `tools/plot_ensemble_cases.py` | CLI | Ensemble case visualization — whole-ensemble biomass vs validation targets | `skill:compare-calibration-rounds`, `skill:phase0-design`, `skill:phase2-screening` +6 |
| `tools/plot_sim_vs_obs_timeseries_ecosim_biocon.py` | CLI | Sim-vs-obs TIME SERIES for one EcoSIM **BioCON** case, driven by the site's `targets.yaml` | **ORPHAN** |

### Generators

| script | | summary | named by |
|---|---|---|---|
| `tools/generate_calibration_rounds.py` | CLI | Scaffold a calibration_rounds.yaml round entry FROM the sourced A2MC configs | `skill:a2mc-init`, `skill:onboard-case`, `skill:phase0-design` |
| `tools/generate_tool_index.py` | CLI | Generate the index of every script in `tools/` and `scripts/`, and name the ORPHANS | **ORPHAN** |
| `scripts/generate_adapter_calibration_rounds.py` | CLI | Generate a calibration_rounds.yaml round entry for an ADAPTER (non-FATES) model | `skill:onboard-case`, `skill:phase0-design`, `TODO.md` |
| `scripts/generate_ecosim_bounds.py` | CLI | Generate a provisional EcoSIM parameter-list (with bounds) for Phase 0 sampling | `skill:literature-review`, `skill:onboard-case`, `memory:feedback_per_model_scripts_not_generic` +2 |

### Submission

| script | | summary | named by |
|---|---|---|---|
| `scripts/submit_adapter_ensemble_batched.py` | CLI | Submit an adapter ensemble in WAVES that respect the scheduler's submission ceiling | `skill:arm-hpc-monitoring`, `skill:phase0-design`, `TODO.md` |

### Runners

| script | | summary | named by |
|---|---|---|---|
| `tools/run_template_validator.py` | CLI | run_template_validator.py - V5 of the A2MC adapter-kit validator suite | `skill:onboard-model` |
| `scripts/run_ecosim_smoke_ensemble.py` | CLI | Submit a tiny REAL EcoSIM ensemble to validate the backend against live Slurm | `memory:feedback_per_model_scripts_not_generic`, `TODO.md` |
| `scripts/run_smoke_ensemble.py` | CLI | Generic model-dispatched smoke-ensemble runner | `skill:onboard-model`, `TODO.md` |

### Diagnostics

| script | | summary | named by |
|---|---|---|---|
| `tools/diagnose_ensemble_status.py` | CLI | Diagnose and restart incomplete ELM-FATES ensemble simulations | `skill:onboard-session`, `skill:phase0-design`, `skill:phase1-exploration` +8 |
| `tools/diagnose_qos_failures.py` | CLI | Diagnose which (case, phase) submissions failed when an auto-generated | `skill:arm-hpc-monitoring`, `skill:restart-failed-jobs` |

### Knowledge promotion

| script | | summary | named by |
|---|---|---|---|
| `tools/promote_diagnostic_script.py` | CLI | Promote a reusable diagnostic/analysis script to the permanent library | `skill:calibration-discipline`, `skill:phase3-diagnosis`, `skill:phase6-refinement` +4 |
| `tools/promote_knowledge.py` | CLI | Promote a CASE discovery into its MODEL's knowledge base — the executor the arrow never had | `skill:round-housekeeping`, `memory:feedback_no_case_state_in_memory`, `CLAUDE.md` +1 |
| `tools/promote_surrogate.py` | CLI | The HUMAN GATE between a surrogate that measured well and a surrogate that may be USED | `TODO.md` |

### Writers

| script | | summary | named by |
|---|---|---|---|
| `tools/write_phase_log.py` | CLI | Write an offline calibration PHASE LOG and its paired artifact folder, from one payload | `skill:calibration-log`, `TODO.md` |

### Other

| script | | summary | named by |
|---|---|---|---|
| `tools/adapter_conformance_validator.py` | CLI | adapter_conformance_validator.py - Validate an adapter scaffold against the | `skill:cherrypick-from-main`, `skill:onboard-model`, `TODO.md` |
| `tools/auto_rebuild.py` | lib | auto_rebuild.py - Tier-aware drift handler for the orchestrator alignment hook | `memory:feedback_verify_tests_actually_ran`, `rag_build_roadmap.md`, `user_guide.md` +1 |
| `tools/binary_archive_manifest.py` | CLI | Generate and VERIFY the manifest of archived model binaries | `skill:ats-run-workflow`, `skill:model-evolution`, `skill:pflotran-run-workflow` +2 |
| `tools/calendar_blocks.py` | lib | Leap-aware calendar blocking for model history tapes — one implementation, shared | **ORPHAN** |
| `tools/case_parser.py` | lib | case_parser.py - Parse CIME case directories into A2MC ConfigMode | **ORPHAN** |
| `tools/codebase_wiki_validator.py` | CLI | codebase_wiki_validator.py - Validate a codebase wiki against the source tree | `skill:onboard-model`, `skill:setup-discipline`, `skill:validate-rag-chain` +5 |
| `tools/compare_netcdf_science.py` | CLI | Compare two run directories' NetCDF outputs on their DATA, not their bytes | **ORPHAN** |
| `tools/compare_rounds.py` | CLI | Cross-Round Comparison Tool for Subset Replay | `skill:compare-calibration-rounds` |
| `tools/config.py` | CLI | A2MC Configuration Module | `skill:a2mc-init`, `skill:calibration-discipline`, `skill:offline-testing-workflow` +16 |
| `tools/config_graph.py` | CLI | Who SETS and who READS an A2MC_* configuration variable — the repo's own config graph | `TODO.md` |
| `tools/cost_functions.py` | CLI | Cost Functions for A2MC Calibration | `skill:phase2-screening`, `memory:reference_calibration_vs_validation_data_taxonomy`, `tools_reference.md` +2 |
| `tools/count_param_list.py` | CLI | Print the number of sampled parameters (Morris/Sobol columns) in a parameter list | `TODO.md` |
| `tools/create_use_case.py` | CLI | Scaffold a new use case directory from use_cases/TEMPLATE (or an existing case) | `skill:onboard-case`, `skill:onboard-model`, `skill:setup-discipline` +1 |
| `tools/cross_milestone_validator.py` | CLI | cross_milestone_validator.py - Compare applies_in: tagging across milestones | `mode_aware_howto.md`, `mode_aware_workflow.md`, `rag_validation_workflow.md` +1 |
| `tools/describe_mode.py` | CLI | describe_mode.py — print the active A2MC run configuration ("mode") | `skill:compare-calibration-rounds`, `skill:onboard-case`, `skill:phase0-design` +6 |
| `tools/ecosim_check_input_compat.py` | CLI | Pre-submit input↔binary compatibility check for EcoSIM | `memory:feedback_per_model_scripts_not_generic`, `TODO.md` |
| `tools/ecosim_evaluate_case.py` | CLI | EcoSIM obs<->sim alignment + case evaluation — thin shim (roadmap L3.1) | `memory:feedback_per_model_scripts_not_generic`, `TODO.md` |
| `tools/elm_ecosystem_variables.py` | lib | ELM ecosystem-level (site-scalar) output-variable registry for ECO_ targets | **ORPHAN** |
| `tools/estab_exp_make_param_files.py` | CLI | PFT10 Establishment Experiment — Variant Param File Generator | `skill:offline-testing-workflow` |
| `tools/evaluate_case.py` | lib | Evaluate a Single Case Against Validation Targets | `skill:a2mc-init`, `skill:diagnose-forensics`, `skill:onboard-case` +10 |
| `tools/fates_output_variables.py` | lib | FATES Output Variable Registry - Single Source of Truth | `memory:reference_calibration_vs_validation_data_taxonomy`, `fates_data_reference.md` |
| `tools/fates_utils.py` | lib | FATES Data Utilities for A2MC | `memory:feedback_performance_experiment_is_the_objective`, `memory:project_adapter_kit_branch_strategy`, `fates_data_reference.md` +1 |
| `tools/hpc_utils.py` | lib | HPC Utilities for A2MC | `user_guide.md`, `CLAUDE.md` |
| `tools/land_output_variables.py` | lib | ELM land-column (snow + soil) output-variable registry for SNOW_/SOIL_ targets | **ORPHAN** |
| `tools/mode_metadata_validator.py` | CLI | mode_metadata_validator.py - Tier 4 of the RAG validation triangle | `memory:feedback_build_validators_for_all_pitfalls`, `codebase_wiki_generation_roadmap.md`, `mode_aware_howto.md` +4 |
| `tools/model_check_input_compat.py` | CLI | Generic pre-submit input↔binary version-compat guard for ANY onboarded model | `skill:diagnose-forensics`, `skill:ecosim-version-drift`, `skill:onboard-model` +3 |
| `tools/model_ensemble_status.py` | CLI | Ensemble status monitor for a model's standalone-run ensemble | `skill:arm-hpc-monitoring`, `skill:calibration-discipline`, `skill:diagnose-forensics` +4 |
| `tools/model_evaluate_case.py` | CLI | Generic model-dispatched obs<->sim alignment + case evaluation (roadmap L3.1) | `skill:diagnose-forensics`, `skill:onboard-model`, `TODO.md` |
| `tools/model_knowledge_store.py` | lib | Resolve and load the MODEL layer of A2MC's adaptive memory | `CLAUDE.md`, `TODO.md` |
| `tools/model_preflight.py` | CLI | Generic model preflight — version + PFT inventory for ANY onboarded model | `skill:a2mc-init`, `skill:onboard-model`, `skill:setup-discipline` +2 |
| `tools/model_version.py` | CLI | model_version.py - Detect ELM + FATES git state from an E3SM checkout | `version_association_workflow.md` |
| `tools/modify_fates_parameters.py` | CLI | FATES Parameter Modification Tool | `skill:add-fates-parameter`, `skill:offline-testing-workflow`, `skill:phase0-design` +5 |
| `tools/optimize_function.py` | lib | Optimize Parameter Sets Using Multi-Target Cost Function | `skill:onboard-case`, `skill:onboard-model`, `skill:phase2-screening` +3 |
| `tools/param_spec.py` | CLI | Canonical FATES parameter-list loader (docs/37 — parameter-naming refactor) | `skill:onboard-case`, `skill:onboard-model`, `skill:phase0-design` +1 |
| `tools/param_transforms.py` | CLI | Derived-parameter transforms for the A2MC parameter list (scoping: dev_logs/20260710a) | `memory:feedback_verify_tests_actually_ran` |
| `tools/pflotran_evaluate_case.py` | CLI | PFLOTRAN obs<->sim alignment + case evaluation (the model's parallel of | `skill:phase1-exploration`, `skill:phase6-refinement`, `TODO.md` |
| `tools/phase_logger.py` | CLI | Phase Logger for A2MC Workflow | `skill:calibration-log`, `skill:write-report`, `memory:feedback_ask_where_else_this_contract_lives` +6 |
| `tools/populate_experiments.py` | CLI | Populate experiment entries into workflow_state.json for Phase 6 resume | **ORPHAN** |
| `tools/port_param_file.py` | CLI | Port a calibrated parameter file across model (e.g. FATES API) versions | `skill:port-param-file`, `memory:feedback_port_tuned_base_param_file_across_versions`, `skills_catalog.md` |
| `tools/prior_art.py` | CLI | Has this been investigated before? Search a case's logs and REPORT THEIR CORRECTION STATUS | `skill:calibration-discipline`, `TODO.md` |
| `tools/profile_completeness_validator.py` | CLI | profile_completeness_validator.py - Statistical coverage check for a built profile | `mode_aware_howto.md`, `mode_aware_workflow.md`, `rag_validation_workflow.md` +1 |
| `tools/rag_diff.py` | CLI | rag_diff.py - Compare two A2MC RAG/GraphRAG profiles and emit a Markdown diff report | `skill:onboard-model`, `skill:validate-rag-chain`, `memory:feedback_per_model_scripts_not_generic` +6 |
| `tools/rag_manifest.py` | CLI | rag_manifest.py - Milestone registry CRUD | `version_association_workflow.md` |
| `tools/rag_metadata.py` | CLI | rag_metadata.py - Read / write per-RAG-profile metadata | `version_association_workflow.md` |
| `tools/rag_refresh.py` | lib | rag_refresh.py - Pure-Python T1 metadata refresh for a registered RAG profile | `user_guide.md`, `TODO.md` |
| `tools/rag_selector.py` | CLI | rag_selector.py - Match a user's ELM-FATES checkout to a registered milestone | `version_association_workflow.md` |
| `tools/read_reduced.py` | CLI | read_reduced.py -- resolve the CORRECT time-axis reduction for a model output variable | `TODO.md` |
| `tools/record_run_status.py` | CLI | record_run_status.py -- the per-simulation RUN LEDGER, written in real time by Phase 5 | `skill:phase5-testing`, `skill:round-housekeeping`, `TODO.md` |
| `tools/review_pending_knowledge.py` | CLI | review_pending_knowledge.py — human-in-the-loop curation of proposed Tier-3 knowledge | `skill:calibration-discipline`, `skill:curate-knowledge`, `skill:inject-knowledge` +6 |
| `tools/round_paths.py` | CLI | Round-aware path resolution for A2MC calibration artifacts | **ORPHAN** |
| `tools/score_adapter_variants.py` | CLI | Score a set of adapter-model experiment variants against a case's validation targets | **ORPHAN** |
| `tools/session_report.py` | lib | Session Report Generator | `skill:calibration-log`, `CLAUDE.md` |
| `tools/skill_graph.py` | CLI | The skill graph — answer "when I invoke skill X, which skills are related, and did I miss one?" | `TODO.md` |
| `tools/smoke_test_skills.py` | CLI | Tier-2 deterministic smoke harness for the A2MC interactive-agent skill layer | `skill:add-skill`, `skill:refine-skill`, `TODO.md` |
| `tools/snapshot_validator.py` | CLI | snapshot_validator.py - End-to-end snapshot test of mode-aware retrieval | `mode_aware_howto.md`, `mode_aware_workflow.md`, `rag_validation_workflow.md` +1 |
| `tools/subdaily_window_reduce.py` | lib | Growing-season, fixed-hour-window mean — a model-agnostic array reducer | `TODO.md` |
| `tools/targets_loader.py` | lib | Generic validation-target loader (framework-level, site-agnostic) | `skill:onboard-model`, `memory:feedback_placeholder_targets_structure_not_values`, `TODO.md` |
| `tools/verify_parameter_file.py` | CLI | Verify FATES Parameter File Against Ensemble Matrix | `skill:offline-testing-workflow`, `TODO.md` |
| `tools/workflow_state_offline.py` | CLI | Offline-agent resume state (docs/31) | `skill:calibration-discipline`, `skill:calibration-goal`, `skill:calibration-log` +14 |
| `tools/workflow_status.py` | CLI | Master Workflow Status Tracker for A2MC | `tools_reference.md`, `CLAUDE.md` |
| `tools/yaml_wiki_validator.py` | CLI | yaml_wiki_validator.py - Validate curated_relationships.yaml against the codebase wiki | `skill:cherrypick-from-main`, `skill:onboard-model`, `skill:validate-rag-chain` +8 |
| `scripts/audit_param_list_against_api.py` | CLI | audit_param_list_against_api.py - One-off utility to find renamed/removed | **ORPHAN** |
| `scripts/convert_official_docs.py` | CLI | convert_official_docs.py - Convert FATES tech-doc RST source to Markdown | **ORPHAN** |
| `scripts/create_adapter_parameter_sample.py` | CLI | Generate a parameter sample for an ADAPTER (non-FATES) model's Phase 0 | `skill:ecosim-run-workflow`, `skill:onboard-model`, `skill:phase0-design` +2 |
| `scripts/curated_seed_builder.py` | CLI | curated_seed_builder.py - Implements Recipe G1 from | `skill:onboard-model`, `skill:setup-discipline`, `modeler_questionnaire.md` +2 |
| `scripts/ecosim_case_census.py` | CLI | Case-level census for a node-packed or task-farmed EcoSIM ensemble | **ORPHAN** |
| `scripts/ecosim_worklist.py` | CLI | Build the TODO worklist for a node-packed EcoSIM ensemble run | `TODO.md` |
| `scripts/fit_ensemble_surrogate.py` | CLI | Fit, validate and save a surrogate from a completed A2MC ensemble | `TODO.md` |
| `scripts/given_data_sensitivity.py` | CLI | Sensitivity indices computed DIRECTLY on a space-filling ensemble — no surrogate, no special design | `skill:ecosim-run-workflow`, `skill:phase0-design`, `TODO.md` |
| `scripts/init_adapter.py` | CLI | init_adapter.py - Walk a new modeler through the A2MC adapter pipeline | `skill:onboard-model`, `skill:setup-discipline`, `memory:project_adapter_kit_shaping_questions` +3 |
| `scripts/materialize_adapter_crossed.py` | CLI | Materialize a CROSSED adapter ensemble: a primary-surface Morris matrix (N trait rows) | `TODO.md` |
| `scripts/materialize_adapter_ensemble.py` | CLI | Materialize an ADAPTER (non-FATES) model's Phase-0 ensemble from a sampled matrix | `skill:ats-run-workflow`, `skill:ecosim-run-workflow`, `skill:onboard-model` +4 |
| `scripts/migrate_fates_wiki.py` | CLI | Migrate FATES wiki content to organized knowledge base structure | **ORPHAN** |
| `scripts/model_generate_bounds.py` | CLI | Generate a provisional, default-anchored parameter-list (with bounds) for ANY | `skill:onboard-model`, `memory:reference_param_bounds_sourcing_pipeline`, `TODO.md` |
| `scripts/pflotran_worklist.py` | CLI | Emit the list of PFLOTRAN ensemble cases that still need to run | `skill:phase0-design`, `TODO.md` |
| `scripts/rag_bump.py` | CLI | rag_bump.py - Orchestrate a RAG profile bump (T1 / T2 / T3) | `rag_build_roadmap.md`, `user_guide.md`, `version_association_howto.md` +1 |
| `scripts/rag_list.py` | CLI | rag_list.py - List registered RAG milestones | `skill:a2mc-init`, `user_guide.md`, `version_association_howto.md` +2 |
| `scripts/rag_match.py` | CLI | rag_match.py - Match a user's E3SM checkout to a milestone, with bump advisor | `skill:a2mc-init`, `skill:onboard-case`, `skill:setup-discipline` +5 |
| `scripts/seed_memory_from_yaml.py` | CLI | Seed A2MC Memory from User-Curated YAML File | `user_guide.md`, `CLAUDE.md` |
| `scripts/surrogate_sobol_indices.py` | CLI | Compute Sobol' indices by running a large Saltelli design through a FITTED SURROGATE | `TODO.md` |
| `scripts/verify_mode_aware.py` | CLI | verify_mode_aware.py - Mode-aware RAG retrieval verification harness | `mode_aware_howto.md`, `mode_aware_workflow.md`, `rag_validation_workflow.md` +2 |
| `scripts/verify_phase4.py` | CLI | verify_phase4.py - Phase 4 closeout verification | `user_guide.md`, `version_association_howto.md`, `version_association_workflow.md` |

