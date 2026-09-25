#!/bin/bash
# =============================================================================
# PFLOTRAN ensemble — NODE-PACKED runner (many cases per allocation)   [TEMPLATE]
# =============================================================================
# THIS IS A TEMPLATE. Copy into your case's `case_template/`, set every `<<< SET`,
# and commit the copy with the case. Do not run it from here.
#
# WHAT IT IS FOR. A PFLOTRAN case is a small MPI job -- miniLEO runs 8 ranks --
# so the obvious submission is one `sbatch` per case on the `shared` QOS. That
# is what `submit_adapter_ensemble_batched.py` does, it is the DEFAULT, and for
# a few hundred cases it is the right answer. At a few THOUSAND cases it stops
# being the right answer, for a reason that is about the queue and not the model.
#
# WHY, measured on PFLOTRAN_miniLEO R1 (2026-08-28), not assumed:
#
# R1 was submitted as 4096 individual `--qos=shared --ntasks=8` jobs. That
# confines the entire round to ONE partition:
#
#     shared_milan_ss11    70 nodes    601 running   9881 pending
#     regular_milan_ss11 2853 nodes    445 running   8166 pending
#
# Comparable queue DEPTH, a 40x difference in POOL SIZE. The measured
# consequence was a steady 9 completions/hour with concurrency pinned at ~6,
# then 0 running with 4010 queued and the partition UP -- every pending job
# reporting Reason=Priority, nothing crashed. 4032 cases at that rate is 18.7
# days. m5199's FairShare is 0.0479 at EffectvUsage 1.0 and job priority 67688
# sits below bf_min_prio_reserve 69121, so these jobs never earn a backfill
# reservation and start only in opportunistic gaps.
#
# Check the equivalent numbers for YOUR cluster before adopting this -- `sinfo -p
# <partition> -o '%D'` and `squeue -p <partition> -o '%T'` are the two commands.
# On a machine whose shared pool is not small, none of this is needed.
#
# This script changes BOTH halves of that:
#   1. one node-exclusive `regular` allocation instead of an 8-core `shared`
#      slice, moving the work into the 2853-node pool where a 1-node request is
#      the SMALLEST object in a partition averaging 6.4 nodes per running job;
#   2. WORKERS_PER_NODE cases running concurrently inside that allocation, so
#      each scarce job start does N cases' worth of work instead of one.
#
# WHAT IS NOT YET PROVEN, and why the first submission is a V0 gate:
#   * that `srun --exact -n 8` really does run N steps concurrently inside one
#     allocation here (it should; test it, do not assume it);
#   * the per-case slowdown from running WORKERS_PER_NODE x RANKS PETSc ranks
#     against one node's memory bandwidth. On miniLEO the solo distribution was
#     p50 21 min (n=86, min 12, max 59). If packed cases take much more than
#     ~2x the solo p50, FEWER workers per node may yield MORE cases per
#     node-hour. Measure it on a small gate run; do not assume the arithmetic.
#
# ONE ADVANTAGE OVER `submit_ensemble_array.sh` WORTH KNOWING. The array script
# has to reconstruct each case's directory name from a HARDCODED prefix plus
# `$SLURM_ARRAY_TASK_ID`, because `#SBATCH --array` indexes integers. This one
# reads case directory NAMES from a worklist file, so it carries no case-naming
# assumption at all and a non-contiguous set of cases costs nothing. It shares
# the array script's real drawback: one script binds many cases to whatever
# `$A2MC_PFLOTRAN_BINARY` resolved to at submit time, so RECORD THAT BINARY in
# the round record ([[feedback_bind_runs_to_archived_binaries]]). It echoes the
# path at startup for exactly this reason.
#
# WORK CLAIMING -- mkdir, not flock. `mkdir` is atomic on every POSIX
# filesystem including the project filesystem this runs on; flock's behaviour
# there is not something to bet 4000 cases on. A claim is never reclaimed:
# recovery is to re-run scripts/pflotran_worklist.py, which rebuilds the list
# from the TAPES rather than from the claims, so a case whose worker died is
# simply back on the next list. Same idempotency philosophy as
# submit_adapter_ensemble_batched.py's job_id.txt.
#
# USAGE -- source the site config first so the run-body vars resolve:
#     source use_cases/PFLOTRAN_miniLEO/config/pflotran_minileo_config.sh
#     python scripts/pflotran_worklist.py --run-root "$A2MC_OUTPUT_DIR" \
#            --out "$A2MC_OUTPUT_DIR/worklist_todo.txt"
#     sbatch --array=0-3 use_cases/.../submit_ensemble_packed.sh    # gate first: a few nodes
#     sbatch --array=0-39%20 use_cases/.../submit_ensemble_packed.sh  # then the rest
#
# Every array task pulls from the SAME worklist, so the array size is just "how
# many nodes to ask for" -- it does not partition the work and no task owns a
# range. Stopping early loses nothing; the tapes are the state.
# =============================================================================
#SBATCH --job-name=PFLOTRAN_packed         # <<< SET: case + round
#SBATCH --account=<NERSC_PROJECT>          # <<< SET: your allocation, e.g. $A2MC_HPC_ACCOUNT
#SBATCH --qos=regular                      # NODE-EXCLUSIVE -- the whole point; see the header
#SBATCH --constraint=cpu
#SBATCH --nodes=1
#SBATCH --ntasks=128                       # <<< SET: physical cores/node = WORKERS x RANKS
#SBATCH --cpus-per-task=1
#SBATCH --time=06:00:00                    # <<< SET: >> one case, so several waves fit
#SBATCH --output=/dev/null                 # <<< SET to $A2MC_OUTPUT_DIR/logs/packed_%A_%a.out
#SBATCH --error=/dev/null                  # <<< SET likewise

set -uo pipefail

# <<< SET the default to (physical cores per node) / (MPI ranks per case), and
# keep --ntasks above equal to their product. On Perlmutter CPU: 128 / 8 = 16.
WORKERS_PER_NODE="${A2MC_PACKED_WORKERS:-16}"
# Cap on ONE case, so a non-converging Sobol' point cannot hold a worker slot for
# the whole allocation. miniLEO_case29 burned its full 4 h request and reached
# t=65 h of 1680 -- below the 806 h observation offset, so it had no salvageable
# Y-value even in principle. 2 h is ~2x the 59 min solo max, leaving room for the
# packed-contention slowdown this gate is measuring.
CASE_TIMEOUT_S="${A2MC_PACKED_CASE_TIMEOUT_S:-7200}"
# Stop claiming new cases with less than this left, so a claimed case is not
# killed mid-solve by the wall clock -- which looks identical to a model failure
# until someone reads the log.
RESERVE_S="${A2MC_PACKED_RESERVE_S:-7500}"

# ---- Toolchain (runtime) -- must match what the binary was BUILT against ----
# Build PETSc and PFLOTRAN with the same compiler, and run with the modules both
# were built with; the case's site config carries them in A2MC_PFLOTRAN_MODULES.
# The Cray PE release is part of that pairing and NERSC retires releases
# (cpe/23.12 went in 2026-09); the current recipe is models/pflotran/BUILD.md.
# NEVER `module load PrgEnv-gnu` after `cpe/<release>` -- it silently reverts the swap.
# NEVER `module purge` on Perlmutter -- it leaves MODULEPATH broken.
# PETSc 3.23+ does not build the 157a26f7 pin (tested with 3.24: it FAILS).
eval "${A2MC_PFLOTRAN_MODULES:?source the site config first}"

export OMP_NUM_THREADS=1          # PFLOTRAN parallelism is MPI, not OpenMP
export SLURM_CPUS_PER_TASK=1      # must agree with SLURM_TRES_PER_TASK=cpu=1

RUNROOT="${A2MC_OUTPUT_DIR:?source the site config first}"
EXE="${A2MC_PFLOTRAN_BINARY:?source the site config first}"
DECK_NAME="$(basename "${A2MC_BASE_PARAM_FILE:?source the site config first}")"
RANKS="${A2MC_HPC_MPI_RANKS:-8}"
WORKLIST="${A2MC_PACKED_WORKLIST:-$RUNROOT/worklist_todo.txt}"
CLAIMS="$RUNROOT/.claims"

[ -f "$WORKLIST" ] || { echo "ERROR: no worklist at $WORKLIST -- run scripts/pflotran_worklist.py" >&2; exit 2; }
[ -x "$EXE" ]      || { echo "ERROR: binary not executable: $EXE" >&2; exit 2; }
mkdir -p "$CLAIMS"

TASK="${SLURM_ARRAY_TASK_ID:-0}"
JOB="${SLURM_ARRAY_JOB_ID:-${SLURM_JOB_ID:-0}}"
START_EPOCH=$(date +%s)
# Wall-clock deadline from the allocation itself, not from a hardcoded copy of
# the #SBATCH value -- two numbers for one quantity is how they drift apart.
END_EPOCH=$(( START_EPOCH + $(squeue -h -j "${SLURM_JOB_ID}" -o '%l' 2>/dev/null |
             awk -F: '{n=NF; s=0; m=1; for(i=n;i>0;i--){s+=$i*m; m*=60} print (s>0?s:21600)}') ))

echo "[node $TASK] START $(date)  workers=$WORKERS_PER_NODE ranks/case=$RANKS"
echo "[node $TASK] binary=$EXE"        # the packed run's only binary record
echo "[node $TASK] worklist=$WORKLIST  ($(wc -l < "$WORKLIST") cases)"
echo "[node $TASK] deadline=$(date -d @$END_EPOCH 2>/dev/null || echo $END_EPOCH)"

run_one_case() {
  local slot="$1" case_name="$2"
  local dir="$RUNROOT/$case_name"
  local log="$dir/packed_${JOB}_${TASK}_s${slot}.log"

  if [ ! -d "$dir" ]; then
    echo "[node $TASK slot $slot] SKIP $case_name: no case dir" >&2
    return 0
  fi
  # A stale partial tape from an earlier killed attempt must go, or the
  # completion test downstream reads the OLD tape and calls this case done.
  rm -f "$dir"/*-mas.dat

  local t0 rc
  t0=$(date +%s)
  echo "[node $TASK slot $slot] RUN $case_name $(date)"
  (
    cd "$dir" || exit 2
    # --exact confines this step to its own 8 tasks; without it the step takes
    # the whole allocation and the workers serialise silently.
    timeout -s TERM "$CASE_TIMEOUT_S" \
      srun --exact --nodes=1 --ntasks="$RANKS" --cpus-per-task=1 --cpu-bind=cores \
           "$EXE" -pflotranin "$DECK_NAME"
  ) > "$log" 2>&1
  rc=$?
  local dt=$(( $(date +%s) - t0 ))

  # ---- Failure triage: SLURM SUCCESS IS NOT MODEL SUCCESS ----
  # EXIT_FAILURE = 88 is PFLOTRAN's real failure signal
  # (pflotran_constants.F90:63) -- timestep cuts exhausted, or dt < dt_min.
  # 124 is `timeout`'s. And the mass-balance tape is the deliverable: no tape
  # means no calibratable output whatever the exit code said, which is the only
  # check that catches a launch that never happened.
  if [ "$rc" -eq 124 ]; then
    echo "[node $TASK slot $slot] TIMEOUT $case_name after ${dt}s (cap ${CASE_TIMEOUT_S}s)" >&2
  elif [ "$rc" -eq 88 ]; then
    echo "[node $TASK slot $slot] FAILED $case_name rc=88 EXIT_FAILURE after ${dt}s" >&2
  elif [ "$rc" -ne 0 ]; then
    echo "[node $TASK slot $slot] FAILED $case_name rc=$rc after ${dt}s" >&2
  elif ! compgen -G "$dir/*-mas.dat" > /dev/null; then
    echo "[node $TASK slot $slot] FAILED $case_name: rc=0 but no *-mas.dat tape" >&2
  else
    echo "[node $TASK slot $slot] DONE $case_name in ${dt}s"
  fi
  return 0
}

worker() {
  local slot="$1"
  while IFS= read -r case_name; do
    [ -z "$case_name" ] && continue
    now=$(date +%s)
    if [ $(( END_EPOCH - now )) -lt "$RESERVE_S" ]; then
      echo "[node $TASK slot $slot] STOP claiming: under ${RESERVE_S}s of wall clock left"
      return 0
    fi
    # Atomic claim. Exactly one worker across ALL nodes wins each mkdir.
    if mkdir "$CLAIMS/$case_name" 2>/dev/null; then
      echo "$JOB:$TASK:$slot" > "$CLAIMS/$case_name/owner"
      run_one_case "$slot" "$case_name"
    fi
  done < "$WORKLIST"
  echo "[node $TASK slot $slot] worklist exhausted"
}

for s in $(seq 1 "$WORKERS_PER_NODE"); do
  worker "$s" &
done
wait

echo "[node $TASK] END $(date)  elapsed=$(( $(date +%s) - START_EPOCH ))s"
