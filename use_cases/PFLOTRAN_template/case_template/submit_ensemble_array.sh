#!/bin/bash
# =============================================================================
# PFLOTRAN ensemble — SLURM JOB-ARRAY submitter  (TEMPLATE, and NOT the default)
# =============================================================================
# ⚠ READ THIS BEFORE USING IT. The default and proven path for a PFLOTRAN
# ensemble is NOT an array. It is:
#
#     scripts/submit_adapter_ensemble_batched.py
#
# which submits per-case jobs in QUEUE-AWARE WAVES against the 5000-job
# `QOSMaxSubmitJobPerUserLimit`, with a reserve for the account's other lanes, a
# model-dependent jobs-per-case multiplier, and idempotency on `job_id.txt` so an
# interrupted run resumes by re-invocation. It is what launched
# `PFLOTRAN_miniLEO R1` (log `20260827c`), including a mid-wave kill at 52 of 800
# submissions that recovered cleanly *because* it is idempotent. It publishes a
# state file matching `tools/check_watcher_state.py`'s contract, so the submitter's
# own death is detectable.
#
# **The queue ceiling is therefore a SOLVED problem, and this file is not the
# solution to it.** An earlier version of this header claimed otherwise; that was
# written before its author read the launch log, and it was wrong.
#
# WHEN AN ARRAY IS ACTUALLY BETTER, and it is a narrow case:
#   * one job id instead of N, so `squeue`/`sacct` stay legible at 10^3-10^4 cases;
#   * near-zero submission-side scheduler load;
#   * `--array=...%K` throttles concurrency in the scheduler rather than in a
#     Python loop that must stay alive to keep pacing.
#
# WHAT AN ARRAY COSTS HERE, and this is why it is not the default:
#   * **it loses per-case submit-script provenance.** `create_case` renders a
#     `submit.sh` per case from the adapter's run template, and this case family's
#     own `case_template/README.md` states that the submit script is the only
#     record of WHICH BINARY a run was bound to plus its run-time hash assertion
#     ([[feedback_bind_runs_to_archived_binaries]]). One array script binds every
#     task to whatever `$A2MC_PFLOTRAN_BINARY` resolved to at submit time.
#   * `#SBATCH` directives are static, so every task shares one walltime and one
#     resource shape.
#   * a mid-array failure has no per-case `job_id.txt` to make recovery idempotent.
#
# So: use the batched submitter unless you have a specific reason not to, and if
# you use this, say in the round record which binary the array was bound to.
#
# THIS IS A TEMPLATE. Copy into your case's `case_template/`, set every `<<< SET`,
# and commit the copy with the case. Do not run it from here.
#
# USAGE -- source the site config first so the run-body vars resolve:
#     source use_cases/<Model>_<Case>/config/<case>_config.sh
#     sbatch use_cases/<Model>_<Case>/case_template/submit_ensemble_array.sh
#   V0 baseline only:  sbatch --array=0 .../submit_ensemble_array.sh
#   A subset:          sbatch --array=1-50%32 .../submit_ensemble_array.sh
#
# The #SBATCH lines cannot read env vars, so override at submit time:
#     sbatch --array=0-4095%128 --output=$A2MC_OUTPUT_DIR/logs/slurm_%A_%a.out \
#            .../submit_ensemble_array.sh
#
# The defaults below MIRROR `PFLOTRAN_miniLEO`'s live config as of 2026-08-27.
# If you change one, change it because your case differs, not by inheriting.
# =============================================================================
#SBATCH --job-name=PFLOTRAN_ens            # <<< SET: case + round
#SBATCH --account=<NERSC_PROJECT>          # <<< SET: your allocation, e.g. $A2MC_HPC_ACCOUNT
#SBATCH --qos=shared                       # A2MC_HPC_QUEUE
#SBATCH --constraint=cpu
#SBATCH --nodes=1                          # A2MC_HPC_NODES
#SBATCH --ntasks=8                         # A2MC_HPC_MPI_RANKS -- see "why 8" below
#SBATCH --cpus-per-task=1                  # A2MC_HPC_CPUS_PER_TASK
#SBATCH --time=04:00:00                    # A2MC_HPC_WALLTIME -- see "why 4 h" below
#SBATCH --array=0-99%64                    # <<< SET: 0 = V0 baseline, 1..N = members
#SBATCH --output=/dev/null                 # <<< SET to $A2MC_OUTPUT_DIR/logs/slurm_%A_%a.out
#SBATCH --error=/dev/null                  # <<< SET likewise

set -uo pipefail

# ---- Perlmutter 'shared' QOS footgun -- cost a silently-dead job 2026-08-07 ----
# On the shared QOS a --mem request SCALES THE ALLOCATED CPU COUNT
# (MaxMemPerCPU=1905 MB), so asking 16G for a run whose real footprint is 32 MB
# set SLURM_CPUS_PER_TASK=10 against SLURM_TRES_PER_TASK=cpu=1 and srun aborted:
#   "fatal: cpus-per-task set by two different environment variables"
# The job exited in 6 seconds with State=COMPLETED ExitCode=0:0 having run
# NOTHING. Do NOT add --mem; pin the two so they agree.
export SLURM_CPUS_PER_TASK="${A2MC_HPC_CPUS_PER_TASK:-1}"

# ---- Toolchain (runtime) -- must match what the binary was BUILT against ----
# Build PETSc and PFLOTRAN with the same compiler, and run with the modules both
# were built with; the case's site config carries them in A2MC_PFLOTRAN_MODULES.
# The Cray PE release is part of that pairing and NERSC retires releases
# (cpe/23.12 went in 2026-09); the current recipe is models/pflotran/BUILD.md.
# NEVER `module load PrgEnv-gnu` after `cpe/<release>` -- it silently reverts the swap.
# NEVER `module purge` on Perlmutter -- it leaves MODULEPATH broken.
# PETSc 3.23+ does not build the 157a26f7 pin (tested with 3.24: it FAILS).
eval "${A2MC_PFLOTRAN_MODULES:?source the site config first}"

export OMP_NUM_THREADS="${A2MC_OMP_NUM_THREADS:-1}"   # parallelism is MPI, not OpenMP

# ---- Paths, all from the sourced config -- no invented variable names --------
# The deck's BASENAME is derived from $A2MC_BASE_PARAM_FILE (the round base deck),
# because that is the file `create_case` stages every case around. There is no
# separate "deck name" variable and one must not be invented: two names for one
# quantity is the shape that has already cost this project three wrong diagnoses.
RUNROOT="${A2MC_OUTPUT_DIR:?source the site config first}"
EXE="${A2MC_PFLOTRAN_BINARY:?source the site config first}"
DECK_NAME="$(basename "${A2MC_BASE_PARAM_FILE:?source the site config first}")"
RANKS="${A2MC_HPC_MPI_RANKS:-8}"

# Case dir for this array task. The prefix is HARDCODED on purpose, matching
# $A2MC_CASE_NAME_PATTERN (miniLEO's is `miniLEO_case{N}`). A config-driven
# ${PATTERN/{N}/...} substitution is BRITTLE -- bash's brace parsing leaves a
# stray '}' (miniLEO_case4}), which failed every task of an EcoSIM submit.
CASE="$RUNROOT/miniLEO_case${SLURM_ARRAY_TASK_ID}"     # <<< SET the prefix

[ -d "$CASE" ] || { echo "ERROR: no case dir $CASE" >&2; exit 2; }
[ -x "$EXE"  ] || { echo "ERROR: binary not executable: $EXE" >&2; exit 2; }

# PFLOTRAN resolves EVERY auxiliary input relative to the WORKING DIRECTORY, so
# the run must cd into the case and be given the deck's BASENAME. An absolute
# deck path works for the deck and silently breaks the mesh, restart, database
# and forcing lookups.
cd "$CASE"

# ---- Input-completeness gate ----
# A missing auxiliary input aborts partway through a run Slurm may still report
# COMPLETED. The list is the four the miniLEO deck names; edit for your deck.
for f in "$DECK_NAME" savannah_river.dat rainfall_PERTH_spinup3224h.txt \
         mesh_rotated10_0.025_ugi.h5 pflotran-presteadystate_restart_1-11.h5; do
  [ -f "$f" ] || echo "WARN: expected input '$f' not present in $CASE" >&2
done

# ---- RESTART CAVEAT -- READ BEFORE TRUSTING AN ENSEMBLE ----
# If the deck restarts from a checkpoint, that checkpoint was produced under the
# BASE parameter set. A member perturbing porosity, permeability, the van
# Genuchten curve or the mineral assemblage restarts from a state INCONSISTENT
# with its own parameters, and PFLOTRAN will not complain. Whether that is
# acceptable for a screen is an ensemble-design decision for the PI; for
# miniLEO R1 it was settled by an explicit restart-consistency probe (log
# `20260827a`), not by assumption.

echo "[case ${SLURM_ARRAY_TASK_ID}] START $(date)  cwd=$CASE  ranks=$RANKS"
echo "[case ${SLURM_ARRAY_TASK_ID}] binary=$EXE"   # the array's only binary record

# ---- Run ----
# WHY 8 RANKS, not serial: DECIDED BY THE PI 2026-08-27 with the evidence in
# hand, and recorded in the site config so it is not reopened. Rank count DOES
# perturb the solve -- measured over the first 8 timesteps against the team's
# serial reference run, serial reproduced 70.75 % of values bit-identically
# (worst rel. diff 3.2e-4) against 8 ranks' 68.49 % (5.6e-4) -- but that is a
# numerical perturbation, not a correctness issue, and the `shared` QOS removes
# the cost argument that favoured serial: at 8 ranks a case takes an 8-core
# slice rather than a whole 128-core node. Do not "fix" this back to serial.
set +e
srun -n "$RANKS" "$EXE" -pflotranin "$DECK_NAME"
RC=$?
set -e

echo "[case ${SLURM_ARRAY_TASK_ID}] pflotran rc=$RC $(date)"

# ---- Failure triage: SLURM SUCCESS IS NOT MODEL SUCCESS ----
if [ "$RC" -eq 88 ]; then
  # EXIT_FAILURE = 88 is PFLOTRAN's real failure signal
  # (pflotran_constants.F90:63) -- timestep cuts exhausted, or dt < dt_min.
  echo "[case ${SLURM_ARRAY_TASK_ID}] FAILED rc=88 (EXIT_FAILURE)" >&2
  ls -la ./*_cut_to_failure* 2>/dev/null || true
  exit 88
elif [ "$RC" -ne 0 ]; then
  echo "[case ${SLURM_ARRAY_TASK_ID}] FAILED rc=$RC" >&2
  exit "$RC"
fi

# The mass-balance tape is the deliverable. No tape means no calibratable output,
# whatever the exit code said. HARD GATE, not a warning: it is the only check
# that catches a launch that never happened (see the shared-QOS footgun above,
# where rc was 0 and no tape existed).
if ! compgen -G "./*-mas.dat" > /dev/null; then
  echo "[case ${SLURM_ARRAY_TASK_ID}] FAILED: no *-mas.dat tape produced" >&2
  exit 88
fi

# A large LIFETIME cut count is NOT a failure. MAX_TS_CUTS is a per-timestep
# consecutive budget; the miniLEO reference run completed with 168 lifetime FLOW
# cuts against a limit of 20. Reference cost: 64.5 min on the team's machine;
# miniLEO's own 4-case test run was 13.8-15.9 min, and the 4 h request is
# deliberate headroom because a member killed on wall clock looks identical to a
# model failure until someone reads the log.
grep -E "Wall Clock Time" ./pflotran.out 2>/dev/null | tail -1 || true
echo "[case ${SLURM_ARRAY_TASK_ID}] COMPLETE (mas tape written) $(date)"
