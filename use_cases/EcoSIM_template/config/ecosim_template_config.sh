# =============================================================================
# EcoSIM SITE CONFIG TEMPLATE — copy to use_cases/EcoSIM_<Case>/config/ecosim_<case>_config.sh
# =============================================================================
# MODEL-SPECIFIC, SITE-AGNOSTIC. This is EcoSIM's template: a standalone (non-CIME)
# binary driven by a namelist. Do NOT use it for a CIME model (FATES) or a deck-driven
# one (PFLOTRAN) — each has its own template beside this file.
#
# Derived from a live EcoSIM case config (not distributed), so every variable here is one A2MC
# actually reads. Replace every <PLACEHOLDER>; the case study is an argument, never
# baked into the template.
#
# Source order — the machine config loads FIRST, and this file loads it for you:
#     source a2mc_noncime_config.sh          # NON-CIME: not a2mc_config.sh
#     source use_cases/EcoSIM_<Case>/config/ecosim_<case>_config.sh
#   Either order works: the machine config is AUTO-SOURCED by this file when it is not
#   already loaded, so the second line ALONE is enough. Sourcing it explicitly first is
#   still correct and still the documented order.
# =============================================================================


SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
export A2MC_USE_CASE_DIR="$(dirname "$SCRIPT_DIR")"
export A2MC_SITE_CONFIG="${SCRIPT_DIR}/$(basename "${BASH_SOURCE[0]}")"
# ---- Auto-source the MACHINE config if it is not already loaded --------------
# Makes driving this case ONE command instead of two:
#     source use_cases/EcoSIM_<Case>/config/ecosim_<case>_config.sh
#
# WHY. a2mc_noncime_config.sh sets the three loop limits -- A2MC_MAX_EXPERIMENTS,
# A2MC_MAX_SKIP_TESTING, A2MC_CONFIDENCE_THRESHOLD -- which orchestrator.py:3567-3571 reads as its
# argparse defaults and which NO site or round config sets. Sourcing only a site config left all
# three UNSET, silently, with nothing announcing the loss.
#
# THE GUARD has TWO clauses and needs both:
#   A2MC_HPC_MPI_RANKS   set by the NON-CIME machine config and NOT by the CIME one,
#                        so it tells the two families apart and a wrong choice gets REPAIRED, not skipped.
#   A2MC_MAX_EXPERIMENTS set by BOTH machine configs and by NO site config, so the guard still fires
#                        when a stale shell-level A2MC_HPC_MPI_RANKS export would otherwise
#                        mask a machine config that was never loaded.
# Tested HERE, before this file sets anything:
#   nothing sourced yet                       -> both unset       -> load it
#   a2mc_noncime_config.sh first              -> both set         -> skip, no double banner
#   a2mc_config.sh (wrong family)             -> family var unset -> load the right one, REPAIRING it
# Re-sourcing a machine config is idempotent (hard exports only; no accumulate patterns), so the
# skip is an ergonomic choice rather than a correctness one.
#
# ORDER IS PRESERVED: this runs at the TOP, so every site override below still wins over the
# machine defaults, and a round wrapper's overrides still win over both.
if [ -z "${A2MC_HPC_MPI_RANKS:-}" ] || [ -z "${A2MC_MAX_EXPERIMENTS:-}" ]; then
    _A2MC_REPO_ROOT="$(cd "${SCRIPT_DIR}/../../.." && pwd)"
    if [ -f "${_A2MC_REPO_ROOT}/a2mc_noncime_config.sh" ]; then
        source "${_A2MC_REPO_ROOT}/a2mc_noncime_config.sh"
    else
        echo "[ecosim_template_config] WARNING: a2mc_noncime_config.sh not found at" \
             "${_A2MC_REPO_ROOT} -- the three loop limits will be UNSET." >&2
    fi
    unset _A2MC_REPO_ROOT
fi


# ---- Model selection (registry dispatch) ----
export A2MC_MODEL="ecosim"
# EcoSIM source tree of the BUILT binary (the RAG/adapter anchor commit 2dea74d9).
# Normal flow: a2mc_noncime_config.sh sets NO A2MC_MODEL_PATH, so the plain `:-` default below
# applies. The `_A2MC_MODEL_PATH_IS_DEFAULT` branch is DEFENSIVE — if someone sources the CIME
# a2mc_config.sh by mistake (it defaults A2MC_MODEL_PATH to the E3SM checkout + sets that flag),
# override it here so the EcoSIM binary still resolves. Respect a user-set value (flag unset).
if [ -z "${A2MC_MODEL_PATH:-}" ] || [ "${_A2MC_MODEL_PATH_IS_DEFAULT:-0}" = "1" ]; then
    export A2MC_MODEL_PATH="<PATH_TO_ECOSIM_CHECKOUT>"      # the tree the built binary came from
    unset _A2MC_MODEL_PATH_IS_DEFAULT
fi

# ---- EcoSIM backend inputs (read by EcoSIMBackend.create_case / submit_ensemble) ----
# Model version label for the round record (the fe075014 anchor; the checkout may sit on an
# experiment branch off it, which the round record captures separately as branch/commit).
export A2MC_ECOSIM_VERSION="fe075014"
export A2MC_ECOSIM_BINARY="${A2MC_MODEL_PATH}/build/Linux-x86_64-double-Release/bin/ecosim.f90.x"
# Base namelist staged + repointed per case. SITE-OWNED template with ABSOLUTE input paths
# (the shipped Offline sample used relative ../../input/input_test/ paths that do NOT resolve
# from an ensemble case dir — create_case only repoints pft_file_in, not the other 5 inputs).
# Carries the hist_fincl1 output activation + a 23-yr exploratory stop_n (KEY KNOB, see the file).
#
# OUTPUT FREQUENCY (`hist_nhtfrq`/`hist_fincl2`, second history tape): the namelist's h0 tape is
# whatever cadence `hist_nhtfrq` sets (typically daily, `-24`) — fine for annual/seasonal-mean
# targets, but a target defined as a SUB-DAILY statistic (e.g. a daytime-only mean, matching a
# campaign's sampling protocol rather than an all-hours mean) needs sub-daily output to compute.
# `hist_nhtfrq` is a PER-TAPE array (EcoSIM `HistFileMod.F90:51`, applied at `:733`), so adding a
# second, higher-frequency tape (`hist_fincl2`/`hist_nhtfrq = -24, -1` for hourly) does not change
# tape 1 or any target scored from it. Wire a change like this as a ROUND-SCOPED override of
# `A2MC_ECOSIM_BASE_NAMELIST` (a new `case_template/run_<round>_<tag>.nml`, referenced from a
# `<site>_config_r<N>.sh` round wrapper) rather than editing the shared base `run.nml` in place —
# so earlier rounds stay reproducible off their own namelist. See EcoSIM_BioCON's
# `case_template/run_r3_hourly.nml` + `config/ecosim_biocon_config_r3.sh` for a worked example
# (added for a growing-season daytime-mean `Fs` target, 2026-08-09).
#
# ⚠ KEEP THE NEW FILE'S COMMENTS SHORT. EcoSIM reads the WHOLE runfile into a fixed 4096-byte
# buffer before parsing (`fileUtil.F90:25`) and ABORTS at startup if it doesn't fit — hit for
# real 2026-08-10 (`EcoSIM_BioCON/memory/logs/20260810e_*.md` Errata; auto-memory
# `reference_ecosim_namelist_buffer_4096_bytes`). `EcoSIMBackend.create_case()` now raises loudly
# if a generated runfile would exceed this, but a base namelist so close to the limit that any
# case's staged paths tip it over is still a bad base — keep new base namelists terse.
export A2MC_ECOSIM_BASE_NAMELIST="${A2MC_USE_CASE_DIR}/case_template/run.nml"
export A2MC_ECOSIM_RUNTEMPLATE="$(dirname "$(dirname "$A2MC_USE_CASE_DIR")")/models/ecosim/runtemplates/hpc_standalone.sh.tmpl"
# The pft parameter file the ensemble perturbs = Jinyun's `mod` base, which has all 20 per-PFT vars the fe075014 binary reads AND corrects the 4 values: RCS [-10,-5,-3]->[0.1,0.2,0.333], IEBTYP 1->3, ISNTYP 0->1, PhiMEAN 0.01->0.1. Sanity checker: 0 ERROR, only 1 WARN (CNLF, a CALIBRATED ceiling — handled). 
export A2MC_BASE_PARAM_FILE="${A2MC_BASE_PARAM_FILE:-<PATH_TO_BASE_PFT_PARAM_FILE>.nc}"

# ---- HPC (Perlmutter shared/serial) ----
export A2MC_HPC_ACCOUNT="${A2MC_HPC_ACCOUNT:-<HPC_ACCOUNT>}"
export A2MC_HPC_QUEUE="${A2MC_HPC_QUEUE:-shared}"
export A2MC_HPC_CPUS_PER_TASK="8"
export A2MC_HPC_WALLTIME="24:00:00"
export A2MC_OMP_NUM_THREADS="1"

# ---- Ensemble output + case naming ----
# Hard-set (not :-) so EcoSIM ensembles land in their own tree even when a2mc_config.sh
# has already exported a FATES-specific A2MC_OUTPUT_ROOT. Override by exporting AFTER sourcing.
export A2MC_OUTPUT_ROOT="<PATH_TO_ENSEMBLE_OUTPUT_ROOT>/EcoSIM_<CASE>_<MODEL_VERSION>"
export A2MC_ENSEMBLE_NAME="<ROUND_TAG>_<NPARA>Para_<NCASES>En"    # e.g. R1_40Para_820En #Hardcoded for 40 parameters and 20 Morris trajectories
export A2MC_OUTPUT_DIR="${A2MC_OUTPUT_ROOT}/${A2MC_ENSEMBLE_NAME}"
# Per-case subdir name; {N} = case index. The screening backend branch discovers cases
# as completed subdirs of A2MC_OUTPUT_DIR and parses this trailing integer.
export A2MC_CASE_NAME_PATTERN="<CASE>_case{N}"

# ---- Parameter design ----
export A2MC_PARAM_LIST_FILE="${A2MC_USE_CASE_DIR}/parameters/<case>_param_list.csv"
# Morris design: the SITE config sets the REAL param/trajectory counts, overriding the generic
# defaults in a2mc_noncime_config.sh (100/30). A2MC_N_PARAMS is DERIVED from the param-list CSV
# (data rows) so it can never drift from the list; A2MC_N_TRAJECTORIES is the round's Morris choice.
# Ensemble = N_TRAJECTORIES x (N_PARAMS + 1) = 20 x 41 = 820 (the R1_40Para_820En name).
export A2MC_N_PARAMS=$(grep -vcE '^#|^name,|^[[:space:]]*$' "$A2MC_PARAM_LIST_FILE" 2>/dev/null || echo 40)
export A2MC_N_TRAJECTORIES=20
export A2MC_SAMPLING_SCHEME=morris
# Sampled ensemble matrix + SALib problem (WRITTEN by scripts/create_adapter_parameter_sample.py;
# the matrix is READ by scripts/materialize_adapter_ensemble.py --matrix default, the salib problem
# by tools/check_setup_ready.py). Mirrors the Kougarok/FATES site convention.
export A2MC_ENSEMBLE_MATRIX_FILE="${A2MC_USE_CASE_DIR}/parameters/ecosim_<case>_morris_matrix.txt"
export A2MC_SALIB_PROBLEM_FILE="${A2MC_USE_CASE_DIR}/parameters/salib_problem_ecosim_<case>.txt"

# ---- Validation targets (loaded generically by tools/targets_loader.py) ----
export A2MC_VALIDATION_TARGETS="${A2MC_USE_CASE_DIR}/validation/targets.yaml"
# THE RUN'S span, not the scored window. `A2MC_VALIDATION_START_YEAR` is the calendar year of
# history record 0 -- run.nml's `start_date` -- and is an ANCHOR for leap-aware year blocking,
# NOT a filter: it skips nothing. Which years are SCORED is each target's `window_years` in
# validation/targets.yaml, and that is also where a spin-up is excluded.
#
# Putting the first VALIDATION year here silently scores the spin-up instead of the observation
# window: the anchor shifts every block label, so `window_years` then selects the run's opening
# years. It is silent because the block boundaries do not move and coverage stays complete. This
# cost an entire 4,097-case round -- see
# memory/dev_logs_adapterkit/20260905c_The_Scoring_Calendar_Nobody_Checked.md
#
# The pair is consumed as `sim_years: "<start>-<end>"` by the round-record generator; no reducer
# reads the END year at all.
#
# VERIFY, before submitting anything:  python tools/check_ecosim_validation_years.py
# BETTER STILL: pin `start_year:` in each target block of validation/targets.yaml, so scoring does
# not depend on this variable at all.
export A2MC_VALIDATION_START_YEAR="<RUN_START_YEAR>"
export A2MC_VALIDATION_END_YEAR="<RUN_END_YEAR>"

echo "[ecosim_<case>_config] A2MC_MODEL=$A2MC_MODEL  binary=$(basename "$A2MC_ECOSIM_BINARY")  out=$A2MC_OUTPUT_DIR"
