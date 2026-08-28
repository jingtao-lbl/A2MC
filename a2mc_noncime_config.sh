#!/bin/bash
# =======================================================================================
# A2MC Configuration — NON-CIME MACHINE SETTINGS (parallel to a2mc_config.sh)
#
# The machine-level config for models driven through a `models/<name>` ModelBackend as a
# STANDALONE binary (EcoSIM, and future non-CIME adapters) — NOT through CIME/create_case.sh.
#
# WHY A PARALLEL FILE (not a2mc_config.sh):
#   a2mc_config.sh is ~80% CIME/E3SM/FATES-specific (E3SM_ROOT, COMPSET, ADSP/RGSP/TRANS,
#   RES=ELM_USRDAT, create_newcase, and — critically — it DEFAULTS A2MC_MODEL_PATH to the
#   E3SM checkout). A non-CIME model must NOT inherit any of that (the A2MC_MODEL_PATH default
#   in particular would shadow the model's own checkout). But a2mc_config.sh ALSO holds the
#   genuinely generic settings every model needs (AI API config, python env, iteration control,
#   sampling, RAG dir). This file carries ONLY those generic settings, so a non-CIME site can
#   source it in place of a2mc_config.sh and keep the sacred source order:
#       source a2mc_noncime_config.sh                              # machine (non-CIME)
#       source use_cases/<site>/config/<site>_config.sh            # site + model
#   The site config owns A2MC_MODEL_PATH (this file deliberately does NOT set it).
#
# KEEP-IN-SYNC: the AI CONFIGURATION / ITERATION CONTROL / SAMPLING DEFAULTS blocks below
#   mirror the same-named blocks in a2mc_config.sh. They are duplicated (not sourced) so
#   a2mc_config.sh stays byte-identical to the main branch (adapter-kit additive rule, docs/38).
#   If you change AI config in one file, change it in the other. (Diff check:
#   `diff <(sed -n '/AI CONFIGURATION/,/USE CASE DIRECTORY/p' a2mc_config.sh) \
#         <(sed -n '/AI CONFIGURATION/,/USE CASE DIRECTORY/p' a2mc_noncime_config.sh)`.)
# =======================================================================================

# ========================
# REPO ROOT
# ========================
# a2mc_config.sh references ${A2MC_ROOT} (e.g. for A2MC_RAG_DIR) but relies on it being set
# elsewhere; set it explicitly here from this file's location (repo root).
export A2MC_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# ========================
# PROJECT / MACHINE
# ========================
export A2MC_USER="${USER:-jingtao}"
export A2MC_MACHINE="${A2MC_MACHINE:-pm-cpu}"
# NOTE: no A2MC_PROJECT / A2MC_E3SM_ROOT here — those are CIME/FATES-specific. HPC account for
# a non-CIME model is set per-site (e.g. A2MC_HPC_ACCOUNT in the site config).

# ========================
# HPC ENSEMBLE LAUNCH (generic baseline; a site config OVERRIDES per its own round choice)
# ========================
# MPI ranks / nodes per ensemble-member run. Only meaningful for a genuinely MPI-parallel
# non-CIME model (e.g. PFLOTRAN, PETSc/MPI-parallel); a model that isn't MPI-parallel per
# case (e.g. EcoSIM) simply never reads these two. Defaults to SERIAL (1) — the safe,
# reproducible baseline when nothing model-specific is known; unlike A2MC_HPC_ACCOUNT
# (no sane generic value exists — it names a specific allocation), "run one rank unless told
# otherwise" is a reasonable cross-model default. A site config sets its OWN value
# UNCONDITIONALLY (not `${VAR:-N}`) to override this for its round's ensemble-design choice —
# see use_cases/PFLOTRAN_miniLEO/config/pflotran_minileo_config.sh §5b for the worked example
# and the evidence behind that site's particular choice.
export A2MC_HPC_MPI_RANKS="${A2MC_HPC_MPI_RANKS:-1}"
export A2MC_HPC_NODES="${A2MC_HPC_NODES:-1}"
export A2MC_HPC_CPUS_PER_TASK="${A2MC_HPC_CPUS_PER_TASK:-1}"

# ========================
# PYTHON ENVIRONMENT
# ========================
# Activate a2mc_env (Py3.11 with the scientific + netCDF4 stack). Unlike a2mc_config.sh we do
# NOT `module load python` first — that is a CIME-era step (and a known footgun: NERSC's base
# python can clobber a2mc_env, [[feedback_no_module_load_python_for_cime]]); a standalone
# adapter run needs only a2mc_env on PATH.
export A2MC_VENV="${HOME}/a2mc_env"
if [ -d "${A2MC_VENV}" ]; then
    source "${A2MC_VENV}/bin/activate"
fi

# ========================
# RAG / VERSION ASSOCIATION (generic — see docs/18)
# ========================
# A2MC_MODEL_PATH is INTENTIONALLY NOT set here — the site config sets it to the model's
# checkout root, and the orchestrator's alignment hook selects the RAG profile from it.
export A2MC_RAG_DIR="${A2MC_RAG_DIR:-${A2MC_ROOT}/rag}"
export A2MC_RAG_AUTO_REBUILD="${A2MC_RAG_AUTO_REBUILD:-false}"

# ========================
# ITERATION CONTROL   (mirrors a2mc_config.sh — keep in sync)
# ========================
export A2MC_MAX_SKIP_TESTING=10
export A2MC_MAX_EXPERIMENTS=10
export A2MC_CONFIDENCE_THRESHOLD=0.95

# ========================
# SAMPLING DEFAULTS   (mirrors a2mc_config.sh — keep in sync)
# ========================
export A2MC_SAMPLING_SCHEME="${A2MC_SAMPLING_SCHEME:-morris}"
export A2MC_N_PARAMS=${A2MC_N_PARAMS:-100}
export A2MC_N_TRAJECTORIES=${A2MC_N_TRAJECTORIES:-30}
export A2MC_N_SAMPLES=${A2MC_N_SAMPLES:-1000}

calculate_ensemble_size() {
    local scheme="${1:-$A2MC_SAMPLING_SCHEME}"
    local n_params="${2:-$A2MC_N_PARAMS}"
    local n_traj="${3:-$A2MC_N_TRAJECTORIES}"
    local n_samp="${4:-$A2MC_N_SAMPLES}"
    case "$scheme" in
        # morris takes a trajectory count and no N; lhs and sobol take N.
        morris) echo $((n_traj * (n_params + 1))) ;;
        lhs)    echo "$n_samp" ;;
        # sobol_seq is the raw scrambled Sobol' SEQUENCE, not the Saltelli design: the ensemble is
        # exactly N rows, like lhs. Kept as its own branch rather than folded into lhs) so that a
        # reader sees the method is handled deliberately -- and because falling through to the
        # error branch returned 0, which is worse than an error since a consumer sizing headroom
        # from it silently gets nothing. Measured 2026-08-27 on the live PFLOTRAN R1 config.
        sobol_seq) echo "$n_samp" ;;
        # Sobol reads the CANONICAL A2MC_N_SAMPLES (the same N the samplers use --
        # create_parameter_sample.py and create_adapter_parameter_sample.py both pass n_samples to
        # sample_sobol AND sample_lhs, so N is generic across the two non-morris schemes; only
        # morris is different, taking a trajectory count instead).
        #
        # What IS sobol-specific is the second-order flag, and this branch used to ignore it --
        # hardcoding (2P+2) while the samplers honour --no-second-order and emit N(P+2). Measured
        # 2026-08-22: a first-order-only design would have been over-counted ~2x, silently.
        sobol)
            case "${A2MC_SOBOL_SECOND_ORDER:-1}" in
                0|false|False) echo $((n_samp * (n_params + 2))) ;;
                *)             echo $((n_samp * (2 * n_params + 2))) ;;
            esac ;;
        custom) echo "${A2MC_TOTAL_ENSEMBLE:-0}" ;;
        *)      echo "ERROR: Unknown sampling scheme: $scheme" >&2; echo 0 ;;
    esac
}

# ========================
# AI CONFIGURATION   (mirrors a2mc_config.sh — keep in sync)
# ========================
# Provider: "anthropic" (direct) | "openai" (direct) | "cborg" (LBL proxy).
export A2MC_AI_PROVIDER="${A2MC_AI_PROVIDER:-cborg}"

# Model auto-derived from provider unless overridden AFTER sourcing.
case "${A2MC_AI_PROVIDER}" in
    anthropic) export A2MC_AI_MODEL="${A2MC_AI_MODEL:-claude-opus-4-20250514}" ;;
    openai)    export A2MC_AI_MODEL="${A2MC_AI_MODEL:-gpt-4o}" ;;
    cborg)     export A2MC_AI_MODEL="${A2MC_AI_MODEL:-anthropic/claude-sonnet}" ;;
    *)         export A2MC_AI_MODEL="${A2MC_AI_MODEL:-claude-opus-4-20250514}" ;;
esac

export A2MC_AI_BASE_URL="${A2MC_AI_BASE_URL:-}"
export A2MC_AI_MAX_TOKENS="${A2MC_AI_MAX_TOKENS:-4096}"
export A2MC_AI_DIAG_MAX_TOKENS="${A2MC_AI_DIAG_MAX_TOKENS:-32768}"
# API key env var name auto-derived from provider if empty (anthropic→ANTHROPIC_API_KEY,
# openai→OPENAI_API_KEY, cborg→CBORG_API_KEY).
export A2MC_AI_API_KEY_ENV="${A2MC_AI_API_KEY_ENV:-}"

# ========================
# USE CASE DIRECTORY (set by site config)
# ========================
export A2MC_USE_CASE_DIR="${A2MC_USE_CASE_DIR:-}"

# ========================
# HELPER FUNCTIONS (generic subset — no CIME create_newcase)
# ========================
make_case_name() {
    local prefix=$1 case_num=$2 suffix=${3:-} phase=$4
    if [ -n "$suffix" ]; then echo "${prefix}_${case_num}_${suffix}_${phase}"
    else echo "${prefix}_${case_num}_${phase}"; fi
}

echo "A2MC non-CIME base configuration loaded (adapter/standalone-binary models)."
echo "Next: source use_cases/{site}/config/{site}_config.sh   (it sets A2MC_MODEL + A2MC_MODEL_PATH)"
