#!/bin/bash
# Report the partition state behind a user's PENDING jobs, and the blocking REASON census.
#
# WHY THIS EXISTS. A partition outage produces no failures and no completions -- it looks exactly
# like a slow queue, which is the one thing an ensemble monitor cannot distinguish from progress.
# On 2026-08-27 all 2453 R1 jobs sat on `shared_milan_ss11` with State=DOWN for over an hour, and it
# was diagnosed only by hand after completions flatlined; before that it was misread twice, first as
# fair-share ramping and then as an unrelated GPU reservation whose start time happened to match.
#
# The scheduler states the reason plainly in `squeue -o "%r"`. Nothing was asking it.
#
# Prints one line per (partition, reason) pair plus each partition's State, so a DOWN partition
# announces itself instead of being inferred from a completion count that stopped moving.
set -uo pipefail
# ---------------------------------------------------------------------------------------------
# CAPACITY mode: ask whether a partition can plausibly CARRY a round, BEFORE anything is queued.
#
# WHY A SECOND MODE. Everything above is post-submission: it explains jobs that are already
# pending. The failure it cannot reach is choosing the wrong partition in the first place, which
# produces no error at all -- the submit succeeds, tasks sit at Reason=Resources, and the round
# is a month long before anyone notices. Measured 2026-10-10: an 8193-case round went to a
# 70-node pool holding 21133 queued tasks from all users and got 10 concurrent against a %512
# throttle. The same case had already measured this in a previous round and written it down; a
# check that reads the CLUSTER needs nobody to have read that.
#
#   tools/check_partition_health.sh --capacity <partition> [n_tasks]
#
# It deliberately does not predict a completion time. Achievable concurrency depends on backfill,
# fair-share and other users, none of which is knowable in advance. What IS knowable is how much
# contention each node is already under, and that is enough to tell a usable pool from a hopeless
# one.
if [ "${1:-}" = "--capacity" ]; then
    part="${2:?usage: --capacity <partition> [n_tasks]}"
    ntasks="${3:-0}"
    nodes=$(sinfo -p "$part" -h -o '%D' 2>/dev/null | awk '{s+=$1} END{print s+0}')
    idle=$(sinfo -p "$part" -h -t idle -o '%D' 2>/dev/null | awk '{s+=$1} END{print s+0}')
    queued=$(squeue -p "$part" -h -r -t PENDING 2>/dev/null | wc -l)
    [ "$nodes" -eq 0 ] && { echo "PARTITION_CAPACITY: $part -- no such partition, or sinfo unavailable"; exit 2; }
    per_node=$(( queued / (nodes > 0 ? nodes : 1) ))
    printf "PARTITION_CAPACITY: %-22s nodes=%-6s idle=%-5s queued=%-7s queued_per_node=%s\n" \
           "$part" "$nodes" "$idle" "$queued" "$per_node"
    [ "$ntasks" -gt 0 ] && printf "PARTITION_CAPACITY: you intend to add %s task(s) to that\n" "$ntasks"
    # 50 queued tasks per node is a deliberately loose line: it is not a throughput model, it is
    # the point past which a round is competing with far more work than the pool can hold, and
    # every observed instance of this failure was an order of magnitude beyond it.
    if [ "$per_node" -ge 50 ]; then
        echo "PARTITION_CAPACITY: *** CONTENDED *** $per_node queued task(s) per node."
        echo "PARTITION_CAPACITY: a per-case job here will sit at Reason=Resources. An ARRAY does NOT"
        echo "PARTITION_CAPACITY: help -- it changes the job-record count, not the resource pool."
        echo "PARTITION_CAPACITY: consider the node-packed path (submit_ensemble_packed.sh), which runs"
        echo "PARTITION_CAPACITY: many serial cases inside ONE node-exclusive allocation. For a serial"
        echo "PARTITION_CAPACITY: model that is FEWER cores per case, not more. Gate it on a one-node"
        echo "PARTITION_CAPACITY: measurement first: packed cases contend for memory bandwidth."
        exit 1
    fi
    echo "PARTITION_CAPACITY: usable -- contention is low enough that per-case jobs should schedule."
    exit 0
fi

USER_ID="${1:-$USER}"
FILTER="${2:-}"

rows=$(squeue -u "$USER_ID" -h -r -o "%P|%r|%j" 2>/dev/null)
[ -n "$FILTER" ] && rows=$(echo "$rows" | grep -- "$FILTER")
if [ -z "$rows" ]; then echo "PARTITION_HEALTH: no pending/running jobs$([ -n "$FILTER" ] && echo " matching '$FILTER'")"; exit 0; fi

echo "$rows" | awk -F'|' '{print $1"|"$2}' | sort | uniq -c | sort -rn | while read -r n key; do
    part="${key%%|*}"; reason="${key##*|}"
    state=$(scontrol show partition "$part" 2>/dev/null | tr ' ' '\n' | grep -m1 '^State=' | cut -d= -f2)
    state="${state:-UNKNOWN}"
    flag=""
    [ "$state" != "UP" ] && flag="  <<< PARTITION $state"
    [ "$reason" = "PartitionDown" ] && flag="$flag  <<< BLOCKED, NOT SLOW"
    printf "PARTITION_HEALTH: %6d job(s)  partition=%-22s state=%-8s reason=%s%s\n" \
           "$n" "$part" "$state" "$reason" "$flag"
done
