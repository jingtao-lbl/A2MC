#!/bin/bash
# Watch a SLURM job array and publish its state to a FILE, not only to a log.
#
# Generalized from use_cases/EcoSIM_BioCON/memory/phase_results/20260814a_phase4_hypothesis_.../
# watch_probe.sh after that watcher died mid-run on 2026-08-15 and nobody found out
# (memory/dev_logs_adapterkit/20260815f_*).
#
# Usage:
#   nohup tools/watch_slurm_array.sh -j <jobid> -n <ntasks> -s <state-file> [-i <sec>] \
#         [-l <logs-dir>] > <watch.log> 2>&1 &
#
# ---------------------------------------------------------------------------
# WHY A STATE FILE (the failure this exists to prevent)
# ---------------------------------------------------------------------------
# A watcher that reports only by appending to a log has a signal that cannot report its own
# death: the log simply stops growing, and "the watcher crashed" is byte-for-byte identical to
# "the array is still running and nothing changed." On 2026-08-15 that is exactly what happened.
# The watcher stopped at complete=227/258 and never wrote its terminal line; the array finished
# fine, and the run sat done-but-unnoticed.
#
# So this version publishes THREE things a reader can check without the watcher's cooperation:
#
#   1. A HEARTBEAT -- the state file is rewritten every poll, so its MTIME is a liveness clock.
#      THIS IS THE PRIMARY MECHANISM, and the only one that survives every death mode. A reader
#      decides "dead" arithmetically: status is RUNNING but (now - epoch) > 2 * interval. The file
#      carries `interval_s` precisely so a reader can compute that without knowing how it was
#      launched. `tools/check_watcher_state.py` implements the test.
#   2. A TERMINAL status written into that file (ENDED / ENDED_UNACCOUNTED), so "finished" is a
#      fact on disk that outlives the process, the session, and the log.
#   3. An EXIT TRAP that stamps status:DIED. This is a CONVENIENCE, NOT THE GUARANTEE, and the
#      first version of this script got that backwards. Measured 2026-08-15: a SIGKILL cannot be
#      trapped by any shell, so the trap never runs; and under SIGTERM bash defers the trap until
#      the current foreground command returns, so a watcher sitting in `sleep 300` stamped nothing
#      for five minutes. The sleep below is therefore backgrounded and `wait`ed (which lets bash
#      run the handler immediately), but a hard kill, a node reboot, or a vanished session still
#      leave the trap unrun. That is why liveness is (1), not (3).
#
# ---------------------------------------------------------------------------
# WHY MILESTONE CROSSINGS, NOT EXACT COUNTS
# ---------------------------------------------------------------------------
# The old Monitor filter matched exact values -- complete=(32|64|96|...) -- on the assumption the
# counter steps through them. It does not: array tasks finish in bursts, so the observed sequence
# was 0, 2, 42, 43, 85, 127, 128, 227 and SEVEN of those eight milestones were missed. This emits
# an explicit `MILESTONE <pct>%` line when a decile is CROSSED, so the marker is a function of
# progress rather than of when the poll happened to land.
set -u

INTERVAL=300; LOGS=""; JOB=""; NTASKS=""; STATE=""
HOOK=""; HOOK_EVERY=1; HOOK_TIMEOUT=600
while getopts "j:n:s:i:l:x:e:t:" o; do case "$o" in
  j) JOB=$OPTARG ;; n) NTASKS=$OPTARG ;; s) STATE=$OPTARG ;;
  i) INTERVAL=$OPTARG ;; l) LOGS=$OPTARG ;;
  x) HOOK=$OPTARG ;; e) HOOK_EVERY=$OPTARG ;; t) HOOK_TIMEOUT=$OPTARG ;;
  *) echo "usage: $0 -j <jobid> -n <ntasks> -s <state-file> [-i sec] [-l logs-dir]" \
          "[-x 'refresh cmd'] [-e every-Nth-poll] [-t hook-timeout-sec]" >&2; exit 2 ;;
esac; done
[ -n "$JOB" ] && [ -n "$NTASKS" ] && [ -n "$STATE" ] || {
  echo "ERROR: -j, -n and -s are all required" >&2; exit 2; }

mkdir -p "$(dirname "$STATE")"

# --- RUN A RUN-SCOPED COPY OF THIS SCRIPT ------------------------------------------------------
# Bash reads a script by BYTE OFFSET as it executes -- it does not load the file up front. So
# editing this file while an instance is running moves the ground under that instance: it resumes
# mid-file at a shifted offset and dies on whatever garbage lands there.
#
# MEASURED 2026-09-03, and it is why this block exists. Commit 5f613ec6 fixed the bad-squeue-poll
# bug in this very file while a watcher launched the previous day was still executing the OLD
# code. That watcher resumed at a shifted offset and died with
#   watch_slurm_array.sh: line 190: syntax error near unexpected token `)'
# INSIDE the block the fix had just added. The fix was correct; deploying it killed the thing it
# was fixing, and a 3,733-task array then ran unwatched for 31 hours.
#
# So: copy this file next to the state file and exec the copy. `exec` REPLACES the process, so the
# PID does not change and any pid file recorded by the launcher stays valid. Past this point the
# original is never read again and can be edited, committed or rewritten freely.
#
# The guard variable prevents an exec loop; the snapshot's own copy sees it set and falls through.
# A snapshot that cannot be written is a WARNING, not a failure: running unprotected is strictly
# better than not watching at all, and the warning says which one you got.
if [ -z "${A2MC_WATCHER_SNAPSHOT:-}" ]; then
  _snap="$(dirname "$STATE")/.watch_slurm_array.${JOB}.snapshot.sh"
  if cp -- "$0" "$_snap.tmp" 2>/dev/null && mv -- "$_snap.tmp" "$_snap" 2>/dev/null; then
    chmod +x "$_snap" 2>/dev/null || true
    echo "[$(date '+%F %T')] exec'ing a run-scoped snapshot: $_snap" \
         "(sha $(sha256sum "$_snap" 2>/dev/null | cut -c1-12))"
    A2MC_WATCHER_SNAPSHOT="$_snap" exec bash "$_snap" "$@"
  fi
  echo "[$(date '+%F %T')] WARN could not snapshot $0 to $(dirname "$STATE") -- running the LIVE" \
       "file, which an edit or a commit can kill mid-run" >&2
fi

EMPTY_STREAK=0
FINAL_STREAK=0
LAST_DECILE=-1
FINISHED=0

HOOK_STATUS="NONE"; HOOK_EPOCH=0; HOOK_FAILS=0; POLL=0

write_state() {   # status pending running complete failed
  # Written to a temp file and moved, so a reader never sees a half-written state.
  cat > "$STATE.tmp" <<EOF
{"ts": "$(date '+%F %T')", "epoch": $(date +%s), "status": "$1", "job": "$JOB",
 "pending": $2, "running": $3, "complete": $4, "failed": $5, "total": $NTASKS,
 "interval_s": $INTERVAL, "watcher_pid": $$, "logs": "$LOGS",
 "hook_status": "$HOOK_STATUS", "hook_epoch": $HOOK_EPOCH, "hook_fail_streak": $HOOK_FAILS}
EOF
  mv -f "$STATE.tmp" "$STATE"
}

# The refresh hook is the SECOND signal: the watcher reads the scheduler, the hook reads the
# filesystem (typically an extract-and-plot pass over the finished cases). They fail in different
# ways, and the disagreements are the point -- "ENDED but nothing landed" is mass silent failure,
# "cases landing but watcher STALE" is the monitoring breaking rather than the run.
#
# Run as ONE process rather than a second daemon on purpose: a separate plot loop would need its
# own heartbeat and its own liveness check, i.e. it could die silently in exactly the way this
# script exists to prevent. One process, one heartbeat, both signals.
#
# Two protections, both learned from this script's own failures:
#   - `timeout`-wrapped. A slow hook must never stall the poll loop, because a stalled loop stops
#     writing the heartbeat and the watcher then reports itself STALE while perfectly healthy --
#     a false death, the mirror of the false-life bug that trap-without-exit produced.
#   - the hook's outcome is RECORDED in the state file (status + consecutive-failure streak), so a
#     hook that has been failing for an hour is visible instead of being a plot that quietly
#     stopped updating. A refresh whose failure is invisible is the original bug again.
run_hook() {
  [ -n "$HOOK" ] || return 0
  POLL=$((POLL + 1))
  if [ $((POLL % HOOK_EVERY)) -ne 0 ]; then
    return 0
  fi
  local t0 rc
  t0=$(date +%s)
  timeout "$HOOK_TIMEOUT" bash -c "$HOOK" >/dev/null 2>&1 </dev/null
  rc=$?
  HOOK_EPOCH=$(date +%s)
  if [ "$rc" -eq 0 ]; then
    HOOK_STATUS="OK"; HOOK_FAILS=0
    echo "[$(date '+%F %T')] HOOK ok in $((HOOK_EPOCH - t0))s"
  elif [ "$rc" -eq 124 ]; then
    HOOK_STATUS="TIMEOUT"; HOOK_FAILS=$((HOOK_FAILS + 1))
    echo "[$(date '+%F %T')] HOOK TIMEOUT after ${HOOK_TIMEOUT}s (streak $HOOK_FAILS) --" \
         "the refresh is slower than its budget; raise -t or -e, or narrow what it reads"
  else
    HOOK_STATUS="FAILED"; HOOK_FAILS=$((HOOK_FAILS + 1))
    echo "[$(date '+%F %T')] HOOK FAILED rc=$rc (streak $HOOK_FAILS)"
  fi
}

STAMPED=0
stamp_died() {
  # Only a DEATH if we never reached a terminal branch, and only once.
  if [ "$FINISHED" -eq 0 ] && [ "$STAMPED" -eq 0 ]; then
    STAMPED=1
    write_state "DIED" "${PEND:-0}" "${RUN:-0}" "${OK:-0}" "${BAD:-0}"
    echo "[$(date '+%F %T')] WATCHER DIED before a terminal state (last: complete=${OK:-?}" \
         "failed=${BAD:-?} of $NTASKS). State file stamped DIED."
  fi
}
# A SIGNAL handler must EXIT. Measured 2026-08-15: with `trap on_exit EXIT INT TERM`, SIGTERM ran
# the handler, wrote DIED -- and then the loop RESUMED and overwrote the file with RUNNING one
# second later, because bash returns to where it was interrupted unless the handler exits. The
# state file then claimed the watcher was alive moments after it had reported its own death,
# which is worse than no stamp at all: it is a liveness signal that lies.
on_signal() { stamp_died; exit 143; }
trap stamp_died EXIT
trap on_signal INT TERM

write_state "STARTING" 0 0 0 0
echo "[$(date '+%F %T')] watching job $JOB ($NTASKS tasks), state -> $STATE, every ${INTERVAL}s"

# Every external call is `timeout`-wrapped and reads from /dev/null: a busy or degraded SLURM
# controller makes squeue/sacct HANG rather than fail, and a wedged watcher is indistinguishable
# from a quiet run.
while true; do
  # -r is LOAD-BEARING: without it squeue prints an array's pending tasks in COMPACT form as a
  # single line (57316828_[21-4988]), so `wc -l` returns 1 no matter how many are queued. Measured
  # 2026-08-20 on R3 chunk 1: pending was published as 1 against 4,959 actually pending. -r expands
  # one line per task. (Running elements happen to list individually either way, but -r there too
  # keeps the two counts derived the same way rather than relying on that coincidence.)
  # CAPTURE squeue's EXIT STATUS, not just its output. `| wc -l` swallows the status, so a
  # timeout or a transient scheduler error yields 0 and is INDISTINGUISHABLE from "no jobs left".
  # Measured 2026-09-02: one bad poll took wave-2 from running=109 to running=0 in a single
  # interval, the watcher declared ENDED_UNACCOUNTED and EXITED, and 109 live jobs were left
  # unwatched with a state file that read terminal -- which also made the health guard report
  # the array FINISHED rather than stale, so nothing downstream could catch it either.
  _pend_raw=$(timeout 20 squeue -j "$JOB" -h -r -t PENDING -o '%i' 2>/dev/null </dev/null); _pend_rc=$?
  _run_raw=$(timeout 20 squeue -j "$JOB" -h -r -t RUNNING -o '%i' 2>/dev/null </dev/null);  _run_rc=$?
  PEND=$(printf '%s' "$_pend_raw" | grep -c .)
  RUN=$(printf '%s' "$_run_raw"  | grep -c .)
  SQUEUE_OK=1; { [ $_pend_rc -ne 0 ] || [ $_run_rc -ne 0 ]; } && SQUEUE_OK=0
  # Completion from sacct: the accounting record of each task's FINAL STATUS, and the only
  # authority on "finished". It keeps that status after squeue has forgotten the job (squeue drops
  # a job MinJobAge after it ends, 300 s on Perlmutter), so it is the question to ask; the queue is
  # not. Do NOT count output files (a model that creates its tape at init makes "file exists" mean
  # STARTED, not finished), and do NOT grep multi-GB stdout (the scan cannot finish and returns a
  # partial count that looks like a total). `-P` because the default output truncates states to ten
  # characters (CANCELLED+, OUT_OF_ME+) and is not data ([[feedback_never_parse_a_cli_default_output]]).
  # The exit status is captured for the same reason squeue's is: a failed read yields nothing,
  # and "nothing" must never be scored.
  ST=$(timeout 30 sacct -j "$JOB" -P -n -X --format=State 2>/dev/null </dev/null); _sacct_rc=$?
  SACCT_OK=1; [ $_sacct_rc -ne 0 ] && SACCT_OK=0
  OK=$(printf '%s\n' "$ST" | grep -c '^COMPLETED')
  BAD=$(printf '%s\n' "$ST" | grep -cE '^(FAILED|TIMEOUT|CANCELLED|NODE_FAIL|OUT_OF_MEMORY|BOOT_FAIL|DEADLINE)')

  echo "[$(date '+%F %T')] PROGRESS pending=$PEND running=$RUN complete=$OK failed=$BAD of $NTASKS"
  # Heartbeat written BEFORE the hook runs, so a long refresh never makes the watcher look dead.
  write_state "RUNNING" "$PEND" "$RUN" "$OK" "$BAD"
  run_hook
  write_state "RUNNING" "$PEND" "$RUN" "$OK" "$BAD"   # re-stamp to publish the hook outcome

  DECILE=$(( (OK + BAD) * 10 / NTASKS ))
  if [ "$DECILE" -gt "$LAST_DECILE" ]; then
    LAST_DECILE=$DECILE
    echo "[$(date '+%F %T')] MILESTONE $((DECILE * 10))% ($((OK + BAD))/$NTASKS accounted)"
  fi
  [ "$BAD" -gt 0 ] && echo "[$(date '+%F %T')] TASK FAILURES detected: $BAD -- inspect ${LOGS:-<logs>}"

  # ---- Is it finished? Only a FINISHED STATUS says so. -----------------------------------------
  # ENDED requires every task to carry a final state in the accounting record (the allow-list
  # above), read successfully, on TWO CONSECUTIVE polls (so a task requeued between them is seen).
  # The queue is NOT asked whether the job is finished: a job's absence from squeue is not a status,
  # and squeue forgets every finished job after MinJobAge. Deciding ENDED on "two empty squeue
  # polls" made the watcher hold for ever whenever those polls straddled that purge (measured
  # 2026-09-23: V0 job 58788324 ended 08:36:07, purged ~08:41:07, second poll 08:41:38; the watcher
  # then held until stopped by hand). squeue still serves one purpose here: if it SUCCESSFULLY lists
  # live tasks while sacct says all are final, the two disagree and the watcher holds.
  if [ "$SACCT_OK" -eq 1 ] && [ "$((OK + BAD))" -ge "$NTASKS" ]; then
    FINAL_STREAK=$((FINAL_STREAK+1))
  else
    FINAL_STREAK=0
  fi
  # The queue's view, used only for the UNACCOUNTED branch below and the contradiction guard. A
  # failed squeue is logged and simply contributes nothing; it no longer blocks a finish.
  if [ "$SQUEUE_OK" -eq 0 ]; then
    echo "[$(date '+%F %T')] WARN squeue poll FAILED (pend rc=$_pend_rc run rc=$_run_rc) --" \
         "pending/running unknown this poll; completion is read from sacct"
    EMPTY_STREAK=0
  elif [ "$PEND" -eq 0 ] && [ "$RUN" -eq 0 ]; then
    EMPTY_STREAK=$((EMPTY_STREAK+1))
  else
    EMPTY_STREAK=0
  fi
  [ "$SACCT_OK" -eq 0 ] && echo "[$(date '+%F %T')] WARN sacct read FAILED (rc=$_sacct_rc) -- no task status this poll; holding"
  QUEUE_LISTS_LIVE=0
  { [ "$SQUEUE_OK" -eq 1 ] && [ "$((PEND + RUN))" -gt 0 ]; } && QUEUE_LISTS_LIVE=1

  if [ "$FINAL_STREAK" -ge 2 ] && [ "$QUEUE_LISTS_LIVE" -eq 1 ]; then
    echo "[$(date '+%F %T')] WARN sacct records all $NTASKS tasks final but squeue still lists" \
         "$((PEND + RUN)) live -- holding until they agree"
  fi
  if [ "$FINAL_STREAK" -ge 2 ] && [ "$QUEUE_LISTS_LIVE" -eq 0 ]; then
    FINISHED=1; write_state "ENDED" "$PEND" "$RUN" "$OK" "$BAD"
    echo "[$(date '+%F %T')] ARRAY ENDED complete=$OK failed=$BAD of $NTASKS (final status from sacct)"
  elif [ "$SQUEUE_OK" -eq 1 ] && [ "$EMPTY_STREAK" -ge 2 ] && [ "$SACCT_OK" -eq 1 ] \
       && [ "$((OK + BAD))" -lt "$NTASKS" ]; then
    # The queue is confirmed empty by two SUCCESSFUL polls, and a SUCCESSFUL sacct read shows some
    # tasks with no final status. That is not a finish, and it is published as one that is not: the
    # checker fails it. A FAILED sacct read proves nothing either way, so it holds instead.
    FINISHED=1; write_state "ENDED_UNACCOUNTED" "$PEND" "$RUN" "$OK" "$BAD"
    echo "[$(date '+%F %T')] ARRAY ENDED UNACCOUNTED complete=$OK failed=$BAD of $NTASKS --" \
         "$((NTASKS - OK - BAD)) tasks have no final status in sacct; inspect ${LOGS:-<logs>}"
  fi
  if [ "$FINISHED" -eq 1 ]; then
    # NOTE: a task can exit 0 having written a PARTIAL output (an early-terminating run still
    # reports COMPLETED). "ENDED" means the scheduler is done, never that the science is valid --
    # the scoring path's window-coverage check is what catches truncated runs.
    break
  fi
  # Backgrounded + waited, NOT a bare `sleep`: bash defers a trap until the current foreground
  # command returns, so a bare `sleep 300` delays the DIED stamp by up to the full interval.
  sleep "$INTERVAL" & wait $!
done
