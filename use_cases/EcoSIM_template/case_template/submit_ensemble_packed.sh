#!/bin/bash
# =============================================================================
# EcoSIM ensemble — NODE-PACKED runner (many cases per allocation)   [TEMPLATE: edit before first use]
# =============================================================================
# THIS IS A TEMPLATE. It is copied into a new case's `case_template/`; set every `<<< SET`
# there and commit the copy with the case.
#
# WHAT IT IS FOR. The default EcoSIM submission is `submit_ensemble_array.sh`: one array task per
# case on the `shared` QOS. That confines the round to the shared partition, and when that pool is
# small or deep, concurrency stalls far below the array throttle with every pending task at
# Reason=Resources -- an array changes the job-record count, not the resource pool. This script
# changes both halves:
#   1. one node-exclusive `regular` allocation instead of a 2-core `shared` slice;
#   2. WORKERS_PER_NODE cases running at once inside it, so each job start does N cases' work.
# Measure before choosing: `tools/check_partition_health.sh --capacity <partition> [n_tasks]`.
# The launch-mode decision is `phase0-design` ("Who owns ensemble submission").
#
# ECOSIM PACKS WELL. A case is SERIAL (`srun -n 1`, OMP=1) with a peak RSS of a few hundred MB, so
# a 128-core node can hold 128 of them. Memory bandwidth, not memory or cores, is the binding
# question -- which is what the gate below measures.
#
# GATE IT ON MEASUREMENT, NOT ON THE ARITHMETIC. "128 cases fit 128 cores" is a core count, not a
# throughput prediction. Time ONE case solo first; if packed cases run much beyond ~2x that,
# FEWER workers per node yields MORE cases per node-hour. Run `--array=0` on a limited worklist and
# compare before scaling.
#
# BEFORE RUNNING THIS, CANCEL any array tasks for the same cases. Two paths running one case
# clobber each other's output, and the loser is silent.
#
# WORK CLAIMING -- mkdir, not flock. `mkdir` is atomic on every POSIX filesystem; flock's behaviour
# on a project filesystem is not something to bet thousands of cases on. A claim is never
# reclaimed: recovery is to re-run scripts/ecosim_worklist.py, which rebuilds the list from the
# RESTARTS rather than from the claims, so a case whose worker died is back on the next list.
#
# WHICH RUNS THIS REGISTERS. A full config-generated Phase-0 ensemble is not recorded in the run
# ledger (its record is the round's Phase-0 stem folder), so its `sbatch` carries
# `A2MC_UNTRACKED_JOB="<why>"` for the agent's sbatch hook. A pilot, gate or rerun of a SUBSET is a
# test someone designed: submit it through `tools/submit_run.py --run-root ...` instead, which
# registers it as one ledger row (`phase5-testing` step 2c).
#
# ---- WHAT YOU MUST EDIT, before the first submit -----------------------------------------
#   1. #SBATCH --job-name   -> <CASE>_R<N>_packed
#   2. #SBATCH --account    -> your allocation (e.g. the site config's $A2MC_HPC_ACCOUNT)
#   3. #SBATCH --ntasks     -> physical cores per node (= WORKERS x 1 for serial EcoSIM)
#   4. #SBATCH --time       -> MEASURED, see the note on that line
#   5. pass --output/--error at submit to place the node logs in the run root
#
# USAGE
#     source use_cases/<Case>/config/<site>_config[_r<N>].sh
#     python scripts/ecosim_worklist.py --run-root "$A2MC_OUTPUT_DIR" \
#            --out "$A2MC_OUTPUT_DIR/worklist_todo.txt" --limit 256        # a gate first
#     mkdir -p "$A2MC_OUTPUT_DIR/logs"
#     A2MC_UNTRACKED_JOB="full Phase-0 ensemble; its record is the phase-0 stem folder" \
#       sbatch --array=0 --output="$A2MC_OUTPUT_DIR/logs/packed_%A_%a.out" \
#              --error="$A2MC_OUTPUT_DIR/logs/packed_%A_%a.err" use_cases/<Case>/case_template/submit_ensemble_packed.sh
#     # then, once the gate's throughput is known, more nodes on the SAME worklist:
#     #   ... sbatch --array=0-15%16 ...
#
# Every array task pulls from the SAME worklist, so the array size is only "how many nodes to ask
# for" -- it does not partition the work and no task owns a range. Stopping early loses nothing;
# the restarts are the state.
# =============================================================================
#SBATCH --job-name=<CASE>_R<N>_packed  # <<< SET
#SBATCH --account=<ACCOUNT>            # <<< SET: your allocation
#SBATCH --qos=regular                  # NODE-EXCLUSIVE -- the whole point
#SBATCH --constraint=cpu
#SBATCH --nodes=1
#SBATCH --ntasks=128                   # <<< SET: physical cores/node = WORKERS x RANKS (EcoSIM: x 1)
#SBATCH --cpus-per-task=1
#SBATCH --time=05:00:00                # <<< SET. ASK FOR WHAT THE WORK NEEDS, NOT A ROUND NUMBER:
                                       # a job that cannot earn a backfill reservation starts only in
                                       # an opportunistic gap, and a 12 h job needs a 12 h gap where a
                                       # 5 h job needs a 5 h one. `scontrol update jobid=<id>
                                       # TimeLimit=...` shortens a pending job and keeps its age.
                                       # FLOOR: must exceed RESERVE_S + CASE_TIMEOUT_S below, or a case
                                       # claimed at the last moment is wall-killed, which looks
                                       # identical to a model failure.
#SBATCH --output=packed_%A_%a.out      # RELATIVE on purpose; pass --output at submit to place them
#SBATCH --error=packed_%A_%a.err

set -uo pipefail

# Refuse an UNEDITED template loudly: the placeholders above are otherwise syntactically valid.
case "${SLURM_JOB_NAME:-}" in
  *"<"*) echo "REFUSING: this is the UNEDITED template. Set the #SBATCH block first." >&2; exit 4;;
esac

# EcoSIM is SERIAL, so workers = cores. Keep --ntasks above equal to WORKERS x RANKS.
WORKERS_PER_NODE="${A2MC_PACKED_WORKERS:-128}"
# Cap on ONE case, so a parameter set that grinds cannot hold a slot all allocation. Set it to
# ~2x the measured solo time, leaving room for the packed-contention slowdown.
CASE_TIMEOUT_S="${A2MC_PACKED_CASE_TIMEOUT_S:-7200}"
# Stop claiming with less than this left, so a claimed case is not killed mid-run by the wall
# clock -- which looks identical to a model failure until someone reads the log.
RESERVE_S="${A2MC_PACKED_RESERVE_S:-7500}"
# Optional lineage check: a symbol the binary must carry (e.g. a switch this round depends on).
# Empty means no check.
REQUIRED_SYMBOL="${A2MC_PACKED_REQUIRED_SYMBOL:-}"

export OMP_NUM_THREADS=1          # EcoSIM is serial; the build default is mpi=0

RUNROOT="${A2MC_OUTPUT_DIR:?source the site config first}"
EXE="${A2MC_ECOSIM_BINARY:?source the site config first}"
EXE_SHA256="${A2MC_ECOSIM_BINARY_SHA256:?source the site config first}"
WORKLIST="${A2MC_PACKED_WORKLIST:-$RUNROOT/worklist_todo.txt}"
CLAIMS="$RUNROOT/.claims"

# ---- The binary must be an ARCHIVE, and must still be the archive. ----------------
# One script binds MANY cases to one binary, so this echo plus these assertions are the only
# record of what produced every result in this allocation.
case "$EXE" in
  */build/*) echo "REFUSING: $EXE is inside the live build tree." >&2; exit 3;;
esac
got=$(sha256sum "$EXE" | cut -d' ' -f1)
[ "$got" = "$EXE_SHA256" ] || { echo "BINARY MISMATCH: got $got expected $EXE_SHA256" >&2; exit 3; }
symbol_hits="-"
if [ -n "$REQUIRED_SYMBOL" ]; then
  # COUNT, never `grep -q`, on the right of a pipe under `set -o pipefail`: grep -q exits on first
  # match, `strings` dies of SIGPIPE (141), and pipefail fails the pipeline although the match
  # SUCCEEDED.
  symbol_hits=$(strings "$EXE" | grep -c "$REQUIRED_SYMBOL")
  [ "$symbol_hits" -gt 0 ] \
    || { echo "REFUSING: $EXE has no $REQUIRED_SYMBOL symbol -- wrong lineage" >&2; exit 4; }
fi

[ -f "$WORKLIST" ] || { echo "ERROR: no worklist at $WORKLIST -- run scripts/ecosim_worklist.py" >&2; exit 2; }
[ -x "$EXE" ]      || { echo "ERROR: binary not executable: $EXE" >&2; exit 2; }
mkdir -p "$CLAIMS"

TASK="${SLURM_ARRAY_TASK_ID:-0}"
JOB="${SLURM_ARRAY_JOB_ID:-${SLURM_JOB_ID:-0}}"
START_EPOCH=$(date +%s)
# Deadline from the allocation itself, not a hardcoded copy of the #SBATCH value -- two numbers
# for one quantity is how they drift apart.
#
# TAKE EXACTLY ONE LINE, AND PROVE IT IS A NUMBER. `squeue -j` on an ARRAY member can return one
# line PER SIBLING TASK, and the count depends on how many siblings are visible at that instant;
# multi-line output made the arithmetic fail, the deadline came out empty, and a node exited after
# two seconds having run zero cases, with exit status 0. Never assume a scheduler CLI returns the
# number of rows you expect.
WALL_S=$(squeue -h -j "${SLURM_JOB_ID}" -o '%l' 2>/dev/null | head -1 |
         awk -F: '{n=NF; s=0; m=1; for(i=n;i>0;i--){s+=$i*m; m*=60} print s}')
case "$WALL_S" in ''|*[!0-9]*) WALL_S="" ;; esac
if [ -z "$WALL_S" ] || [ "$WALL_S" -le 0 ] 2>/dev/null; then
  WALL_S=43200
  # SAY SO. A silent fallback is how a wrong deadline survives.
  echo "[node ${SLURM_ARRAY_TASK_ID:-0}] WARN could not read the allocation walltime from squeue;" \
       "falling back to ${WALL_S}s. Check the deadline below against the job's real TimeLimit." >&2
fi
END_EPOCH=$(( START_EPOCH + WALL_S ))

echo "[node $TASK] START $(date)  workers=$WORKERS_PER_NODE (serial cases)"
echo "[node $TASK] binary=$EXE  sha=$EXE_SHA256  required_symbol=${REQUIRED_SYMBOL:-none} hits=$symbol_hits"
echo "[node $TASK] worklist=$WORKLIST  ($(wc -l < "$WORKLIST") cases)"
echo "[node $TASK] deadline=$(date -d @$END_EPOCH 2>/dev/null || echo $END_EPOCH)"

run_one_case() {
  local slot="$1" case_name="$2" fy="$3"
  local dir="$RUNROOT/$case_name"
  local log="$dir/packed_${JOB}_${TASK}_s${slot}.log"

  if [ ! -d "$dir" ]; then
    echo "[node $TASK slot $slot] SKIP $case_name: no case dir" >&2
    return 0
  fi
  # The completion year is READ from the worklist, not re-derived here: scripts/ecosim_worklist.py
  # computes it once from each case's own runfile.nml and emits "<case>\t<year>". One derivation,
  # carried forward, cannot drift from itself.
  # A stale restart from a killed attempt must go, or the completion test reads the OLD artifact
  # and calls this case done.
  rm -f "$dir"/*.ecosim.r.*.nc "$dir"/*.ecosim.h0.*.nc "$dir"/rpointer.esim 2>/dev/null

  local t0 rc dt
  t0=$(date +%s)
  echo "[node $TASK slot $slot] RUN $case_name $(date)"
  (
    cd "$dir" || exit 2
    # --exact confines this step to its own single task; without it the step takes the whole
    # allocation and the workers serialise silently.
    # BASENAME, not an absolute path: EcoSIM reads the runfile path into a fixed-length buffer.
    timeout -s TERM "$CASE_TIMEOUT_S" \
      srun --exact --nodes=1 --ntasks=1 --cpus-per-task=1 --cpu-bind=cores \
           "$EXE" runfile.nml
  ) > "$log" 2>&1
  rc=$?
  dt=$(( $(date +%s) - t0 ))

  # ---- Failure triage: SLURM SUCCESS IS NOT MODEL SUCCESS ----
  # EcoSIM exits rc=0 on real failures (an internal ENDRUN, or soil organic matter driven negative),
  # so the FINAL RESTART is the deliverable and the only test that means what it says.
  if [ "$rc" -eq 124 ]; then
    echo "[node $TASK slot $slot] TIMEOUT $case_name after ${dt}s (cap ${CASE_TIMEOUT_S}s)" >&2
  elif [ "$rc" -ne 0 ]; then
    echo "[node $TASK slot $slot] FAILED $case_name rc=$rc after ${dt}s" >&2
  elif ! compgen -G "$dir/*r.${fy}-01-01*" > /dev/null; then
    # The common, INFORMATIVE case: a parameter set the model cannot survive.
    echo "[node $TASK slot $slot] MODELFAIL $case_name: rc=0 but no r.${fy}-01-01 restart after ${dt}s" >&2
  else
    echo "[node $TASK slot $slot] DONE $case_name in ${dt}s"
  fi
  return 0
}

worker() {
  local slot="$1"
  # READ ON FD 3, NOT STDIN. A command inside a `while read` loop INHERITS the loop's stdin and
  # consumes it: `srun` swallowed the rest of the worklist, so every worker ran exactly ONE case.
  # A dedicated FD is used rather than `srun ... < /dev/null` because that redirect fixes only the
  # command it is attached to and silently regresses when another command is added to the loop.
  while IFS=$'\t' read -r -u 3 case_name fy; do
    [ -z "$case_name" ] && continue
    [ -z "$fy" ] && { echo "[node $TASK slot $slot] SKIP $case_name: worklist carries no year" >&2; continue; }
    now=$(date +%s)
    if [ $(( END_EPOCH - now )) -lt "$RESERVE_S" ]; then
      echo "[node $TASK slot $slot] STOP claiming: under ${RESERVE_S}s of wall clock left"
      return 0
    fi
    # Atomic claim. Exactly one worker across ALL nodes wins each mkdir.
    if mkdir "$CLAIMS/$case_name" 2>/dev/null; then
      echo "$JOB:$TASK:$slot" > "$CLAIMS/$case_name/owner"
      run_one_case "$slot" "$case_name" "$fy"
    fi
  done 3< "$WORKLIST"
  echo "[node $TASK slot $slot] worklist exhausted"
}

for s in $(seq 1 "$WORKERS_PER_NODE"); do
  worker "$s" &
done
wait

echo "[node $TASK] END $(date)  elapsed=$(( $(date +%s) - START_EPOCH ))s"
