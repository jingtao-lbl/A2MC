#!/bin/bash
# =============================================================================
# EcoSIM ensemble — SLURM JOB-ARRAY submitter  (TEMPLATE: edit before first use)
# =============================================================================
# ONE `sbatch` drives every case as an array task. Each task is a SERIAL EcoSIM run
# (srun -n 1, OMP=1); parallelism is ACROSS cases — the scheduler runs up to %<N> of
# them at once — NOT within a case. A 1-grid-cell run gains nothing from more cores;
# --cpus-per-task only buys a bigger node slice.
#
# ---- WHAT YOU MUST EDIT, before the first submit -----------------------------------------
#   1. #SBATCH --job-name      -> <CASE>_R<N>
#   2. #SBATCH --account       -> your allocation
#   3. #SBATCH --array         -> 0-<LAST>%<THROTTLE>   (0 = V0 baseline, 1..LAST = samples)
#   4. #SBATCH --time          -> MEASURED, see the note on that line
#   5. CASE_PREFIX             -> must match A2MC_CASE_NAME_PATTERN in your site config
#   6. FINAL_RESTART_YEAR      -> derived from your namelist, see the note at the bottom
# SLURM directives cannot read environment variables, so they are static and there is no way
# to make them derive themselves. Leaving them at another round's values is the single most
# common failure of this script: it submits the wrong number of tasks, and if --output points
# somewhere absolute, writes the logs into the wrong round's directory.
#
# ---- USAGE -------------------------------------------------------------------------------
#     source use_cases/<Model>_<Case>/config/<model>_<case>_config.sh
#     mkdir -p "$A2MC_OUTPUT_DIR/logs"        # SLURM fails a task that cannot open its log
#     sbatch use_cases/<Model>_<Case>/case_template/submit_ensemble_array.sh
#   V0 only:   sbatch --array=0 ...
#   A subset:  sbatch --array=1-50%20 ...
#
# ---- QUEUE LIMIT THAT BINDS AT ENSEMBLE SCALE --------------------------------------------
# `shared` enforces MaxSubmitJobsPU = 5000 and SLURM counts array TASKS individually. Measured
# ceiling: 4,995 pass `sbatch --test-only`. A larger ensemble MUST be split into chunks, and the
# chunks should be aligned on the design's own block stride (e.g. the Saltelli stride) so that a
# partially complete ensemble is still analyzable as whole blocks rather than fragments.
# MaxArraySize is 65,000 and is NOT the binding constraint. Check before assuming:
#     sbatch --test-only --array=0-<LAST> <this script>
# =============================================================================
#SBATCH --job-name=<CASE>_R<N>
#SBATCH --account=<ACCOUNT>
#SBATCH --qos=shared
#SBATCH --constraint=cpu
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=2          # SERIAL run (OMP=1). 2 = memory headroom; a measured EcoSIM
                                   # case peaked at 537 MB RSS. Raising this does NOT speed a run
                                   # up, and under `shared` it multiplies the charge.
#SBATCH --time=03:00:00            # PER TASK. MEASURE IT: run a few cases, then
                                   #   sacct -j <id> -o JobID,Elapsed,State
                                   # and leave real headroom over the observed MAX, not the mean.
                                   # A wall-clock kill produces an unusable row that is hard to
                                   # tell from a model failure. `shared` charges actual usage, so
                                   # headroom costs nothing.
#SBATCH --array=0-<LAST>%<THROTTLE>   # 0 = V0 baseline, 1..LAST = the sampled cases
#SBATCH --output=%x_%A_%a.out      # RELATIVE on purpose. An absolute path here pins the script to
#SBATCH --error=%x_%A_%a.err       # ONE round's directory and silently misfiles the next round's
                                   # logs. To place them with the ensemble, pass at submit time:
                                   #   --output="$A2MC_OUTPUT_DIR/logs/slurm_%A_%a.out"

set -uo pipefail

# ---- REQUIRED environment. No fallbacks, deliberately. -----------------------------------
# Defaulting these to "the last ensemble" makes an UNSOURCED submit succeed against the wrong
# directory with the wrong binary, reporting nothing wrong. A missing variable must kill the
# task instead of being guessed.
: "${A2MC_OUTPUT_DIR:?source the round config first}"
: "${A2MC_ECOSIM_BINARY:?not set — source the round config; it must name an ARCHIVED binary}"
: "${A2MC_ECOSIM_BINARY_SHA256:?not set — source the round config; needed to verify the binary at run time}"

RUNROOT="$A2MC_OUTPUT_DIR"
EXE="$A2MC_ECOSIM_BINARY"
export OMP_NUM_THREADS=1

# ---- The binary must be an ARCHIVE, and must still be the archive. -----------------------
# EcoSIM is a shared CMake tree: build/<config>/bin/ecosim.f90.x is ONE file that every build
# overwrites in place, whatever branch is checked out. A queued job resolves its executable when
# it STARTS, so a rebuild between sbatch and start swaps the model with nothing to see in the job
# record. Archive the binary and point here; see config/binary_archive_manifest.json.
case "$EXE" in
  */build/*) echo "REFUSING: $EXE is inside the live build tree. Bind to build_archive/<label>/." >&2; exit 3;;
esac
got=$(sha256sum "$EXE" | cut -d' ' -f1)
if [ "$got" != "$A2MC_ECOSIM_BINARY_SHA256" ]; then
  echo "BINARY MISMATCH: got $got, expected $A2MC_ECOSIM_BINARY_SHA256" >&2; exit 3
fi

# Case dir for this task. HARDCODED to match A2MC_CASE_NAME_PATTERN in the site config; keep the
# two in step by hand. A config-driven ${PATTERN/{N}/...} substitution is brittle — bash's brace
# parsing leaves a stray '}' (<CASE>_case4}), which once failed every task on a first submit.
CASE_PREFIX="<CASE>_case"        # <- EDIT
# Refuse an UNEDITED template loudly. Without this the placeholders are syntactically valid and
# every task just reports FAILED with no stated reason, which reads like a model problem.
case "$CASE_PREFIX" in
  *"<"*) echo "REFUSING: this is the UNEDITED template. Set CASE_PREFIX (and the #SBATCH block)." >&2; exit 4;;
esac
CASE="$RUNROOT/${CASE_PREFIX}${SLURM_ARRAY_TASK_ID}"
[ -d "$CASE" ] || { echo "ERROR: no case dir $CASE" >&2; exit 2; }
[ -x "$EXE" ]  || { echo "ERROR: binary not executable: $EXE" >&2; exit 2; }
cd "$CASE" || exit 2
echo "[case ${SLURM_ARRAY_TASK_ID}] START $(date)  cwd=$CASE"

# Pass the BASENAME, not an absolute path: EcoSIM reads the runfile path into a fixed-length
# buffer and a long absolute path overflows it. runfile.nml is in $CASE, which is cwd.
srun -n 1 "$EXE" runfile.nml
rc=$?

# ---- Completion test: the FINAL RESTART, never the h0 tape. -------------------------------
# EcoSIM opens its single h0 tape at INITIALISATION and appends to it, so the tape exists from the
# first minute of the run. Testing for it scores a wall-clock-killed run as COMPLETE, which is
# precisely the unusable row an ensemble needs to detect. The restart set stamped <final year + 1>
# is written only after the last simulated year finishes.
#
# DERIVE the year from the case's own runfile.nml, do not guess it:
#   start_date year + sum over forc_periods triplets of (y1 - y0 + 1) * repeats
#   e.g. start_date '20000101000000' with forc_periods = 2000, 2022, 1  ->  23 years  ->  2023
# A recycled spin-up is counted correctly by that formula because `repeats` is included.
FINAL_RESTART_YEAR="<FINAL_YEAR_PLUS_1>"   # <- EDIT
case "$FINAL_RESTART_YEAR" in
  *"<"*) echo "REFUSING: FINAL_RESTART_YEAR is still the template placeholder; derive it from runfile.nml." >&2; exit 4;;
esac
if ls "$CASE"/*r."${FINAL_RESTART_YEAR}"-01-01* >/dev/null 2>&1; then
  echo "[case ${SLURM_ARRAY_TASK_ID}] COMPLETE (final restart ${FINAL_RESTART_YEAR}-01-01) $(date)"
else
  echo "[case ${SLURM_ARRAY_TASK_ID}] FAILED (no final restart, rc=$rc) $(date)"; exit 1
fi
