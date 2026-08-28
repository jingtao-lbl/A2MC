# =============================================================================
# ATS SITE CONFIG TEMPLATE — copy to use_cases/ATS_<Case>/config/ats_<case>_config.sh
# =============================================================================
# MODEL-SPECIFIC, CASE-AGNOSTIC. This is ATS's template: a standalone (non-CIME) C++
# binary driven by an XML ParameterList input deck. Do NOT use it for a CIME model
# (FATES), a namelist-driven one (EcoSIM), or a card-deck one (PFLOTRAN) — each has its
# own template beside this file.
#
# ★ EVERY <PLACEHOLDER> IS DELIBERATE. Structure is wired; values are NOT.
#   Replace each one. Filling them with plausible-looking values is worse than leaving
#   them, because a fabricated config looks like a working one
#   ([[feedback_placeholder_targets_structure_not_values]]).
#
# ATS-specific things this template carries that no other model needs:
#   A2MC_ATS_EXE        the ATS binary (read by models/ats/backend.py)
#   A2MC_ATS_DECK       the XML ParameterList deck that IS the parameter file
#   A2MC_ATS_MESH       the mesh file the deck references
#
# Source order — the machine config loads FIRST, and this file loads it for you:
#     source a2mc_noncime_config.sh          # NON-CIME: not a2mc_config.sh
#     source use_cases/ATS_<Case>/config/ats_<case>_config.sh
#   Either order works: the machine config is AUTO-SOURCED by this file when it is not
#   already loaded, so the second line ALONE is enough. Sourcing it explicitly first is
#   still correct and still the documented order.
#   Picking the wrong machine config is a common adapter-branch failure
#   ([[feedback_two_machine_configs_cime_vs_noncime]]).
# =============================================================================

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
export A2MC_USE_CASE_DIR="$(dirname "$SCRIPT_DIR")"
export A2MC_SITE_CONFIG="${SCRIPT_DIR}/$(basename "${BASH_SOURCE[0]}")"
# ---- Auto-source the MACHINE config if it is not already loaded --------------
# Makes driving this case ONE command instead of two:
#     source use_cases/ATS_<Case>/config/ats_<case>_config.sh
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
        echo "[ats_template_config] WARNING: a2mc_noncime_config.sh not found at" \
             "${_A2MC_REPO_ROOT} -- the three loop limits will be UNSET." >&2
    fi
    unset _A2MC_REPO_ROOT
fi


# -----------------------------------------------------------------------------
# 1. SITE INFORMATION
# -----------------------------------------------------------------------------
export A2MC_SITE_NAME="<CASE>"
export A2MC_SITE_LAT="<LAT>"
export A2MC_SITE_LON="<LON>"

export A2MC_MODEL="ats"
export A2MC_ATS_VERSION="<COMMIT_OR_TAG>"

# ATS has NO PFT axis. Its grouping axis is the mesh REGION / material, and observation
# targets are already reduced over a region by their `functional` before A2MC sees them
# — so A2MC_PFTS is deliberately UNSET, not empty-by-oversight.
# (models/ats/spec.py: grouping_axis="region", default_groups=())

# -----------------------------------------------------------------------------
# 2. MODEL PATHS
# -----------------------------------------------------------------------------
# The pinned source tree. Push model-source work to the `fork` remote ONLY, never
# upstream ([[feedback_model_source_push_fork_only]]).
export A2MC_MODEL_PATH="${A2MC_MODEL_PATH:-<PATH_TO_ATS_CHECKOUT>}"

# The binary. BIND A RUN TO AN ARCHIVED BINARY, never a live build path: the build tree
# is shared and a queued job resolves its exe at RUN time
# ([[feedback_bind_runs_to_archived_binaries]]).
export A2MC_ATS_EXE="${A2MC_ATS_EXE:-<PATH_TO_ARCHIVED_ats_BINARY>}"

# The case bundle (XML deck, mesh, forcing, reference observations).
export A2MC_ATS_CASE_DIR="${A2MC_ATS_CASE_DIR:-<PATH_TO_CASE_BUNDLE_DIR>}"
export A2MC_ATS_DECK="${A2MC_ATS_CASE_DIR}/<deck>.xml"
export A2MC_ATS_MESH="${A2MC_ATS_CASE_DIR}/<mesh>.exo"
export A2MC_ATS_REFERENCE_OBS="${A2MC_ATS_CASE_DIR}/<reference observations>"

# -----------------------------------------------------------------------------
# 3. CALIBRATION INPUTS
# -----------------------------------------------------------------------------
export A2MC_PARAM_LIST_FILE="${A2MC_USE_CASE_DIR}/parameters/<case>_param_list.csv"
export A2MC_TARGETS_FILE="${A2MC_USE_CASE_DIR}/validation/targets.yaml"

# The base deck a round perturbs. For round N>1 this is the round's CORRECTED base,
# not the prior dead/stale one — a fresh sensitivity screen on a stale base is void.
export A2MC_BASE_PARAM_FILE="${A2MC_BASE_PARAM_FILE:-${A2MC_ATS_DECK}}"

# -----------------------------------------------------------------------------
# 4. RUN / SCHEDULER
# -----------------------------------------------------------------------------
# Read by models/ats/backend.py. Leave A2MC_SUBMIT_CMD unset to run locally.
export A2MC_CASE_ROOT="${A2MC_CASE_ROOT:-<PATH_TO_CASE_OUTPUT_ROOT>}"
export A2MC_MPI_LAUNCH="${A2MC_MPI_LAUNCH:-srun}"
# export A2MC_SUBMIT_CMD="sbatch"

# -----------------------------------------------------------------------------
# 5. WHAT IS NOT WIRED YET — read this before assuming a full round runs
# -----------------------------------------------------------------------------
# `models/ats/backend.py` states its own maturity: "Parameter/output I/O is complete;
# run wiring is v0.1." Parameter parsing, output parsing and the spec are real; the
# submit/monitor/extract path is NOT proven end to end, because no ATS case existed
# until this template. Treat the first case as onboarding the RUN path too, and log
# what it takes — that is the gap this template exists to let someone close.
