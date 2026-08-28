# =============================================================================
# PFLOTRAN SITE CONFIG TEMPLATE — copy to use_cases/PFLOTRAN_<Case>/config/pflotran_<case>_config.sh
# =============================================================================
# MODEL-SPECIFIC, SITE-AGNOSTIC. This is PFLOTRAN's template: a standalone (non-CIME)
# binary driven by an input DECK plus a thermodynamic database. Do NOT use it for a
# CIME model (FATES) or a namelist-driven one (EcoSIM) — each has its own template
# beside this file.
#
# PFLOTRAN-specific things this template carries that no other model needs:
#   A2MC_PFLOTRAN_DECK       the card deck that IS the parameter file
#   A2MC_PFLOTRAN_DATABASE   the thermodynamic database (a SECOND tuned surface)
#   A2MC_PFLOTRAN_REFERENCE_MAS  the reference *-mas.dat for the V0 gate
#
# Derived from a live PFLOTRAN case config (not distributed), so every variable is one A2MC
# actually reads. Replace every <PLACEHOLDER>.
#
# Source order — the machine config loads FIRST, and this file loads it for you:
#     source a2mc_noncime_config.sh          # NON-CIME: not a2mc_config.sh
#     source use_cases/PFLOTRAN_<Case>/config/pflotran_<case>_config.sh
#   Either order works: the machine config is AUTO-SOURCED by this file when it is not
#   already loaded, so the second line ALONE is enough. Sourcing it explicitly first is
#   still correct and still the documented order.
# =============================================================================


SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
export A2MC_USE_CASE_DIR="$(dirname "$SCRIPT_DIR")"
export A2MC_SITE_CONFIG="${SCRIPT_DIR}/$(basename "${BASH_SOURCE[0]}")"
# ---- Auto-source the MACHINE config if it is not already loaded --------------
# Makes driving this case ONE command instead of two:
#     source use_cases/PFLOTRAN_<Case>/config/pflotran_<case>_config.sh
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
        echo "[pflotran_template_config] WARNING: a2mc_noncime_config.sh not found at" \
             "${_A2MC_REPO_ROOT} -- the three loop limits will be UNSET." >&2
    fi
    unset _A2MC_REPO_ROOT
fi


# -----------------------------------------------------------------------------
# 1. SITE INFORMATION
# -----------------------------------------------------------------------------
export A2MC_SITE_NAME="<CASE>"
# Biosphere 2, Oracle, Arizona (the LEO facility that <CASE> is the bench-scale
# analogue of). <CASE> itself is an indoor 2 m bench lysimeter, so the
# coordinates are the facility's, not a field site's.
export A2MC_SITE_LAT="32.578"
export A2MC_SITE_LON="-110.851"

# The model this site is calibrated with.
export A2MC_MODEL="pflotran"
export A2MC_PFLOTRAN_VERSION="157a26f7"

# PFLOTRAN has NO PFT axis. Its grouping axis is the mesh REGION, and the
# mass-balance writer has already reduced over a region by the time A2MC sees a
# column -- so A2MC_PFTS is deliberately unset, not empty-by-oversight.
# (spec.grouping_axis = "region")

# -----------------------------------------------------------------------------
# 2. MODEL PATHS
# -----------------------------------------------------------------------------
# The pinned source tree (a git worktree at commit 157a26f7 -- note .git is a
# FILE there, not a directory; the version detector accepts both).
export A2MC_MODEL_PATH="${A2MC_MODEL_PATH:-<PATH_TO_PFLOTRAN_CHECKOUT>}"

# The case bundle (deck, mesh, database, restart, reference outputs). It lives
# outside this repo -- it is 99 MB and belongs to the team's own repository
# (github.com/Janewendo/<case>_pflotran). models/pflotran/datasets.py reads the
# same override.
export A2MC_PFLOTRAN_CASE_DIR="${A2MC_PFLOTRAN_CASE_DIR:-<PATH_TO_INPUT_DECK_DIR>}"
export A2MC_PFLOTRAN_DECK="${A2MC_PFLOTRAN_CASE_DIR}/pflotran.in"
export A2MC_PFLOTRAN_DATABASE="${A2MC_PFLOTRAN_CASE_DIR}/savannah_river.dat"
export A2MC_PFLOTRAN_REFERENCE_MAS="${A2MC_PFLOTRAN_CASE_DIR}/pflotran-mas.dat"

# The BASE "parameter file" is the DECK itself -- PFLOTRAN has no separate
# parameter file. Every per-case deck is written from this one.
export A2MC_BASE_PARAM_FILE="${A2MC_PFLOTRAN_DECK}"

# A build exists and has been proven end-to-end (miniLEO's V0 gate: RMSRE 0.2276,
# matching the reference tape's 0.2277 -- dev logs 20260807c/20260812d). Leave
# UNSET only if your own case's commit has no binary yet, so anything that tries
# to submit fails loudly rather than silently falling back to a bare "pflotran"
# on PATH.
export A2MC_PFLOTRAN_BINARY="${A2MC_PFLOTRAN_BINARY:-${A2MC_MODEL_PATH}/src/pflotran/pflotran}"
export A2MC_PFLOTRAN_RUNTEMPLATE="$(dirname "$(dirname "$A2MC_USE_CASE_DIR")")/models/pflotran/runtemplates/hpc_standalone.sh.tmpl"

# -----------------------------------------------------------------------------
# 3. PARAMETER + VALIDATION FILES
# -----------------------------------------------------------------------------
export A2MC_PARAM_LIST_FILE="${A2MC_USE_CASE_DIR}/parameters/pflotran_<case>_param_list.csv"
export A2MC_ENSEMBLE_MATRIX_FILE="${A2MC_USE_CASE_DIR}/parameters/pflotran_<case>_morris_matrix.txt"
export A2MC_SALIB_PROBLEM_FILE="${A2MC_USE_CASE_DIR}/parameters/salib_problem_pflotran_<case>.txt"
export A2MC_VALIDATION_TARGETS="${A2MC_USE_CASE_DIR}/validation/targets.yaml"

# Count sampled parameters from the list rather than hardcoding, so adding a row
# cannot silently desynchronise the Morris design.
export A2MC_N_PARAMS=$(grep -vcE '^#|^name,|^[[:space:]]*$' "$A2MC_PARAM_LIST_FILE" 2>/dev/null || echo 0)
export A2MC_N_TRAJECTORIES=20
export A2MC_SAMPLING_SCHEME=morris

# -----------------------------------------------------------------------------
# 4. ENSEMBLE NAMING / OUTPUT
# -----------------------------------------------------------------------------
export A2MC_ENSEMBLE_PREFIX="<CASE>_PFLOTRAN"
export A2MC_CASE_NAME_PATTERN="<CASE>_case{N}"
export A2MC_ENSEMBLE_NAME="R1_${A2MC_N_PARAMS}Para_Morris${A2MC_N_TRAJECTORIES}"
# CFS, never ~/ -- run output on Perlmutter must not land under $HOME
# (feedback_no_temp_files_on_home_use_cfs). A stale $HOME/Desktop/... default here
# went unnoticed until the first real submission (20260812d) -- fill in a real CFS
# path (e.g. /global/cfs/cdirs/<project>/<user>/<Case>_runs), not a home-dir one.
export A2MC_OUTPUT_ROOT="${A2MC_OUTPUT_ROOT:-<PATH_TO_ENSEMBLE_OUTPUT_ROOT_ON_CFS>}"
export A2MC_OUTPUT_DIR="${A2MC_OUTPUT_ROOT}/${A2MC_ENSEMBLE_NAME}"
export A2MC_EXTRACTED_DATA="${A2MC_OUTPUT_DIR}_Extract"

# -----------------------------------------------------------------------------
# 5. HPC (proven: 20260812d ran a real ensemble member end to end)
# -----------------------------------------------------------------------------
export A2MC_HPC_ACCOUNT="${A2MC_HPC_ACCOUNT:-<HPC_ACCOUNT>}"
export A2MC_HPC_QUEUE="${A2MC_HPC_QUEUE:-regular}"
export A2MC_HPC_NODES="1"
export A2MC_HPC_CPUS_PER_TASK="1"
export A2MC_OMP_NUM_THREADS="1"

# MPI_RANKS -- THIS SITE'S ROUND CHOICE. UNCONDITIONAL assignment (not
# ${A2MC_HPC_MPI_RANKS:-N}) on purpose: a2mc_noncime_config.sh (sourced before
# this file) already sets a generic serial (1) default, so a ${VAR:-N} fallback
# HERE would silently never fire and this site's intended rank count would be
# ignored (feedback_layered_config_override_must_be_unconditional). Pick a real
# number -- 8 is what miniLEO uses; the team's own reference ran serial and
# agreed slightly better with it (20260807g), so serial is a defensible
# alternative if reproducing their exact numbers matters more than wall-clock.
export A2MC_HPC_MPI_RANKS=8
# Reference run: 64.5 min wall clock on the team's machine
# (pflotran.out:116683). Leave real headroom -- a perturbed member can be
# slower, and a member that dies on wall clock looks identical to a model
# failure until you read the log.
export A2MC_HPC_WALLTIME="04:00:00"

# -----------------------------------------------------------------------------
# 6. RAG / VERSION ASSOCIATION
# -----------------------------------------------------------------------------
export A2MC_ROOT="$(dirname "$(dirname "$A2MC_USE_CASE_DIR")")"
export A2MC_RAG_DIR="${A2MC_ROOT}/rag"
# The orchestrator's alignment hook normally SETS this by matching
# A2MC_MODEL_PATH against rag/milestones.json. Stated here for the offline agent,
# which does not run that hook.
export A2MC_RAG_ACTIVE="pflotran-157a26f7"

# -----------------------------------------------------------------------------
# Summary
# -----------------------------------------------------------------------------
echo "=== A2MC site config: ${A2MC_SITE_NAME} (model: ${A2MC_MODEL}) ==="
echo "  Use case dir:  ${A2MC_USE_CASE_DIR}"
echo "  Model path:    ${A2MC_MODEL_PATH}"
echo "  Case dir:      ${A2MC_PFLOTRAN_CASE_DIR}"
echo "  Params:        ${A2MC_N_PARAMS} (grouping axis: region — PFLOTRAN has no PFT axis)"
echo "  Ensemble:      ${A2MC_ENSEMBLE_NAME}"
echo "  RAG profile:   ${A2MC_RAG_ACTIVE}"
echo "  Binary:        ${A2MC_PFLOTRAN_BINARY:-(UNSET -- no build at the pinned commit; execution path is not live)}"
