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
