#!/bin/bash
# =============================================================================
# A2MC Site Configuration Template
# =============================================================================
#
# Copy this file to your site's config directory and rename:
#   cp use_cases/TEMPLATE/config/template_config.sh \
#      use_cases/<YourSite>/config/<yoursite>_config.sh
#
# Then edit the values below. Source it AFTER the machine config, always in
# this order (feedback_source_config_order_and_round_selection):
#   source a2mc_config.sh                                   # machine-level
#   source use_cases/<YourSite>/config/<yoursite>_config.sh # this file
#   Either order works: the machine config is AUTO-SOURCED by this file when it is not
#   already loaded, so the second line ALONE is enough. Sourcing it explicitly first is
#   still correct and still the documented order.
#
# WHAT BELONGS HERE vs ELSEWHERE
#   a2mc_config.sh ......... machine-level: A2MC_ROOT, A2MC_OUTPUT_ROOT,
#                            A2MC_SCRIPTS_DIR, A2MC_RAG_DIR, A2MC_MODEL_PATH,
#                            calculate_ensemble_size(). Do NOT restate them here.
#   this file .............. everything site- and round-specific.
#   validation/targets.yaml  the targets AND the scoring config (see §5).
#   config/calibration_rounds.yaml
#                            the per-round record. Do NOT hand-type it — derive
#                            it from this file:
#                              python tools/generate_calibration_rounds.py --round N --write
#                              python tools/check_calibration_rounds.py
#
# THE ONE RULE: derive, never hardcode. The parameter count, ensemble size and
# every name built from them come from the parameter list. Change the list (or
# the scheme), not a literal (feedback_derive_pft_count_never_hardcode).
#
# Every variable below is consumed by A2MC code. Verify with:
#   grep -rl A2MC_<VAR> --include='*.py' --include='*.sh' .
# =============================================================================

# Where this file lives — used to derive A2MC_USE_CASE_DIR.
# NOTE: BASH_SOURCE is a bash builtin; under zsh it is empty and A2MC_USE_CASE_DIR
# collapses. Always source from bash (or `bash -c`).
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
export A2MC_USE_CASE_DIR="$(dirname "$SCRIPT_DIR")"
# Absolute path to THIS site config — read by ConfigMode + the setup gate as the
# signal that a site config (not just the machine config) was sourced.
export A2MC_SITE_CONFIG="${SCRIPT_DIR}/$(basename "${BASH_SOURCE[0]}")"
# ---- Auto-source the MACHINE config if it is not already loaded --------------
# Makes driving this case ONE command instead of two:
#     source use_cases/<YourSite>/config/<yoursite>_config.sh
#
# WHY. a2mc_config.sh sets the three loop limits -- A2MC_MAX_EXPERIMENTS,
# A2MC_MAX_SKIP_TESTING, A2MC_CONFIDENCE_THRESHOLD -- which orchestrator.py:3567-3571 reads as its
# argparse defaults and which NO site or round config sets. Sourcing only a site config left all
# three UNSET, silently, with nothing announcing the loss.
#
# THE GUARD has TWO clauses and needs both:
#   A2MC_DIN_LOC_ROOT    set by the CIME machine config and NOT by the non-CIME one,
#                        so it tells the two families apart and a wrong choice gets REPAIRED, not skipped.
#   A2MC_MAX_EXPERIMENTS set by BOTH machine configs and by NO site config, so the guard still fires
#                        when a stale shell-level A2MC_DIN_LOC_ROOT export would otherwise
#                        mask a machine config that was never loaded.
# Tested HERE, before this file sets anything:
#   nothing sourced yet                       -> both unset       -> load it
#   a2mc_config.sh first                      -> both set         -> skip, no double banner
#   a2mc_noncime_config.sh (wrong family)     -> family var unset -> load the right one, REPAIRING it
# Re-sourcing a machine config is idempotent (hard exports only; no accumulate patterns), so the
# skip is an ergonomic choice rather than a correctness one.
#
# ORDER IS PRESERVED: this runs at the TOP, so every site override below still wins over the
# machine defaults, and a round wrapper's overrides still win over both.
if [ -z "${A2MC_DIN_LOC_ROOT:-}" ] || [ -z "${A2MC_MAX_EXPERIMENTS:-}" ]; then
    _A2MC_REPO_ROOT="$(cd "${SCRIPT_DIR}/../../.." && pwd)"
    if [ -f "${_A2MC_REPO_ROOT}/a2mc_config.sh" ]; then
        source "${_A2MC_REPO_ROOT}/a2mc_config.sh"
    else
        echo "[fates_template_config] WARNING: a2mc_config.sh not found at" \
             "${_A2MC_REPO_ROOT} -- the three loop limits will be UNSET." >&2
    fi
    unset _A2MC_REPO_ROOT
fi

# Repo root: two levels up from use_cases/<Site>/config/
export A2MC_ROOT="$(dirname "$(dirname "$A2MC_USE_CASE_DIR")")"

# -----------------------------------------------------------------------------
# 1. SITE IDENTITY
# -----------------------------------------------------------------------------
export A2MC_SITE_NAME="MySite"           # used in case names, ensemble names, log paths
export A2MC_SITE_DESCRIPTION="One line describing the site"
export A2MC_SITE_LAT="64.86"             # decimal degrees
export A2MC_SITE_LON="-164.83"           # decimal degrees

# -----------------------------------------------------------------------------
# 2. DOMAIN / SURFACE / FORCING DATA  (read by tools/create_case.sh)
# -----------------------------------------------------------------------------
# One shared directory plus bare FILENAMES — that split is what create_case.sh
# expects. (An older template used A2MC_DOMAIN_DATA / A2MC_SURFACE_DATA holding
# full paths; nothing reads those names. Use the DIR + FILE forms below.)
export A2MC_DOMAIN_DIR="/path/to/your/domain_and_surface_data"
export A2MC_DOMAIN_FILE="domain_${A2MC_SITE_NAME}.nc"
export A2MC_SURFACE_FILE="surfdata_${A2MC_SITE_NAME}.nc"
# Soil-order input (ELM CNP); may live in the same dir as above.
export A2MC_SOILORDER_DIR="/path/to/your/soilorder_data"
export A2MC_SOILORDER_FILE="soilorder_${A2MC_SITE_NAME}.nc"
# Atmospheric forcing directory.
export A2MC_FORCING_DIR="/path/to/your/atm_forcing"

# -----------------------------------------------------------------------------
# 3. PFT CONFIGURATION
# -----------------------------------------------------------------------------
# Comma-separated, 1-based FATES PFT ids A2MC will calibrate — the ids from the
# BASE PARAMETER FILE's fates_pftname list, NOT ELM's static surfdata PFTs.
# PFT ids are NOT stable across FATES API versions: map by functional type and
# verify against the base file (feedback_verify_pft_identity_across_versions).
# Set this only for PFT-level goals; an ecosystem-flux goal (tower/MODIS GPP)
# does not need it. Example = an arctic 3-PFT set on an api-43 parameter file.
export A2MC_PFTS="10,11,12"              # evergreen shrub, deciduous shrub, graminoid (api-43 ids)

# -----------------------------------------------------------------------------
# 4. SAMPLING + PARAMETER LIST  (everything downstream derives from these)
# -----------------------------------------------------------------------------
# Scheme decides how the ensemble SIZE is computed from the parameter count —
# Morris trajectories, Sobol and LHS all differ. Change the scheme or the list,
# never a hardcoded ensemble count.
export A2MC_SAMPLING_SCHEME="morris"     # morris | lhs | sobol | custom
export A2MC_N_TRAJECTORIES=30            # Morris trajectories

# The parameter list. Its FILENAME is the only place a parameter count may appear
# as a literal (e.g. "para169"); everything below derives from the content.
export A2MC_PARAM_LIST_FILE="${A2MC_USE_CASE_DIR}/parameters/${A2MC_SITE_NAME}_Parameter_List.csv"

# Parameter count, derived from the list CONTENT (authoritative, format-agnostic:
# handles the explicit-column CSV and the legacy shorthand .txt). Falls back to a
# "paraNNN" token in the filename only if the tool cannot run.
export A2MC_N_PARAMS=$(python "${A2MC_ROOT}/tools/count_param_list.py" "$A2MC_PARAM_LIST_FILE" 2>/dev/null \
    || { _p="${A2MC_PARAM_LIST_FILE##*para}"; echo "${_p%%[!0-9]*}"; })
# Fail LOUD rather than letting an empty count flow into every derived name below
# (an unnoticed empty yields an ensemble called "..._Para" and an ensemble size of 0).
if [[ -z "${A2MC_N_PARAMS}" || ! "${A2MC_N_PARAMS}" =~ ^[0-9]+$ ]]; then
    echo "WARNING: could not derive A2MC_N_PARAMS from '${A2MC_PARAM_LIST_FILE}'." >&2
    echo "         Create your parameter list first (a2mc-init / phase0-design), then re-source." >&2
    export A2MC_N_PARAMS=0
fi

# SALib problem file — regenerated by phases/phase0_design/create_parameter_sample.py.
export A2MC_SALIB_PROBLEM_FILE="${A2MC_USE_CASE_DIR}/parameters/salib_problem_para${A2MC_N_PARAMS}.txt"

# Total ensemble size — computed by scheme (Morris: N_TRAJECTORIES x (N_PARAMS+1)).
export A2MC_TOTAL_ENSEMBLE=$(calculate_ensemble_size)

# The sample matrix written by Phase 0 (rows = A2MC_TOTAL_ENSEMBLE, cols = A2MC_N_PARAMS).
export A2MC_ENSEMBLE_MATRIX_FILE="${A2MC_USE_CASE_DIR}/parameters/${A2MC_SITE_NAME}_Morris_matrix.txt"

# -----------------------------------------------------------------------------
# 5. VALIDATION TARGETS
# -----------------------------------------------------------------------------
# The LIVE target file, loaded via tools/targets_loader.py. It carries BOTH the
# targets and the scoring settings:
#   cost_config: {error_method, aggregation_method, tolerance, tolerance_type}
#   time_year / time_month: the observation window
# Those live in the YAML, NOT in env vars — older configs exported
# A2MC_ERROR_METHOD / A2MC_AGGREGATION_METHOD / A2MC_TOLERANCE /
# A2MC_VALIDATION_{START_YEAR,END_YEAR,MONTHS} / A2MC_TOP_N, and nothing reads
# them any more. Edit validation/targets.yaml instead, then:
#   python tools/validate_targets_config.py
export A2MC_VALIDATION_TARGETS="${A2MC_USE_CASE_DIR}/validation/targets.yaml"

# -----------------------------------------------------------------------------
# 6. MODEL BUILD / NAMELIST OPTIONS
# -----------------------------------------------------------------------------
# Nutrient supplementation per spin-up phase (ADSP / RGSP / TRANS). Recorded in
# calibration_rounds.yaml `protocol`. "ALL" supplements, "NONE" runs prognostic.
export A2MC_RGSP_SUPLPHOS="ALL"
# ELM build options. Drives BOTH the build and the mode-aware RAG filter.
export A2MC_ELM_OPTIONS="-bgc fates -nutrient cnp -nutrient_comp_pathway eca -soil_decomp century"
export A2MC_FATES_PARTEH_MODE=2          # 1 = carbon-only; 2 = CNP

# Tier 2 FATES feature flags (default off; set only if enabled in user_nl_elm)
#export A2MC_FATES_SPITFIRE_MODE=1        # 0 = off, 1 = lightning, 2 = + managed
#export A2MC_USE_FATES_PLANTHYDRO=true    # plant hydraulics
#export A2MC_USE_FATES_LOGGING=true       # logging mortality
#export A2MC_USE_FATES_NOCOMP=true        # PFTs in separate patches (no competition)

# -----------------------------------------------------------------------------
# 7. PARAMETER FILES (base + per-case)
# -----------------------------------------------------------------------------
# The BASE parameter file: the template every per-case file is built from. A2MC
# reads the PFT count/names from it, and every NON-calibrated parameter flows
# from it unchanged into every case — so on an API migration prefer a site-TUNED
# prior over the generic default (feedback_port_tuned_base_param_file_across_versions).
# api-43+ is JSON; older FATES uses .nc/.cdl.
export A2MC_BASE_PARAM_FILE="${A2MC_MODEL_PATH}/components/elm/src/external_models/fates/parameter_files/fates_params_default.json"

# Where the per-case parameter files are written by Phase 0. Anchor it on
# ${A2MC_OUTPUT_ROOT} (machine-level) — never a literal /global/... or /home/...
# path, and include the round token so two rounds cannot overwrite each other.
export A2MC_PARAM_DIR="${A2MC_OUTPUT_ROOT}/ParameterFiles/${A2MC_SITE_NAME}_para${A2MC_N_PARAMS}_Morris"
# Per-case filename pattern; {N} = case number. Include the round token too.
export A2MC_PARAM_PATTERN="fates_params_${A2MC_SITE_NAME}_para${A2MC_N_PARAMS}_En{N}.json"

# -----------------------------------------------------------------------------
# 8. ENSEMBLE NAMING + OUTPUT PATHS
# -----------------------------------------------------------------------------
# Name THIS round's ensemble so it identifies the config AND the round; the
# param count derives, so a new list automatically yields a new name.
export A2MC_ENSEMBLE_NAME="${A2MC_SITE_NAME}_FATESapi43_CNPECA_Para${A2MC_N_PARAMS}"
export A2MC_ENSEMBLE_PREFIX="${A2MC_SITE_NAME}_ELM-FATES"
# {N} = member index, {PHASE} = spin-up phase (ADSP/RGSP/TRANS).
export A2MC_CASE_NAME_PATTERN="${A2MC_ENSEMBLE_PREFIX}_PtCNPEn{N}_{PHASE}"
export A2MC_ENSEMBLE_OUTPUT="${A2MC_OUTPUT_ROOT}/${A2MC_ENSEMBLE_NAME}"
export A2MC_EXTRACTED_DATA="${A2MC_OUTPUT_ROOT}/${A2MC_ENSEMBLE_NAME}_Extract"
# CIME case scripts + run logs. Anchor on ${A2MC_SCRIPTS_DIR}; include the round
# token so a new round does not build into the previous round's tree.
export A2MC_CASE_SCRIPTS="${A2MC_SCRIPTS_DIR}/${A2MC_ENSEMBLE_NAME}"
export A2MC_LOG_DIR="${A2MC_CASE_SCRIPTS}"

# -----------------------------------------------------------------------------
# 9. HISTORY OUTPUT VARIABLES
# -----------------------------------------------------------------------------
# Size x PFT (SZPF) history fields written into user_nl_elm. Trim to what your
# targets and diagnostics actually need — every field costs disk on a large
# ensemble. This minimal set covers biomass + N/P pools per PFT.
export A2MC_HIST_SZPF_VARS="'FATES_VEGC_ABOVEGROUND_SZPF','FATES_LEAFC_SZPF','FATES_FROOTC_SZPF','FATES_STOREC_SZPF','FATES_NPP_SZPF'"

# -----------------------------------------------------------------------------
# 10. OPTIONAL — case-dir enrichment for mode-aware retrieval
# -----------------------------------------------------------------------------
# ConfigMode resolves: env vars (above, = user INTENT) > case dir > ELM defaults.
# A case dir adds Tier 2 use_fates_* flags from user_nl_elm/lnd_in. Any one
# ensemble member works as the reference (members differ only in param file).
#export A2MC_CASE_DIR="${A2MC_E3SM_ROOT}/cime/scripts/${A2MC_ENSEMBLE_PREFIX}_PtCNPEn1_TRANS"
#export A2MC_CASE_NAME="${A2MC_ENSEMBLE_PREFIX}_PtCNPEn1_TRANS"
# If neither is set, the env-vars-only path is used (still fully supported).
# See docs/a2mc_reference/mode_aware_workflow.md.

# -----------------------------------------------------------------------------
# Summary
# -----------------------------------------------------------------------------
echo "=== A2MC site config: ${A2MC_SITE_NAME} ==="
echo "  Use case dir:  ${A2MC_USE_CASE_DIR}"
echo "  PFTs (FATES):  ${A2MC_PFTS:-(unset — ecosystem-level goal?)}"
echo "  Param list:    $(basename "${A2MC_PARAM_LIST_FILE}") (${A2MC_N_PARAMS} params)"
echo "  Sampling:      ${A2MC_SAMPLING_SCHEME}, ${A2MC_N_TRAJECTORIES} trajectories -> ${A2MC_TOTAL_ENSEMBLE} cases"
echo "  Ensemble:      ${A2MC_ENSEMBLE_NAME:-(unset)}"
echo "  ELM_OPTIONS:   ${A2MC_ELM_OPTIONS}"
echo "  PARTEH mode:   ${A2MC_FATES_PARTEH_MODE}"
echo "  Case dir:      ${A2MC_CASE_DIR:-(unset; using env-vars-only path)}"
