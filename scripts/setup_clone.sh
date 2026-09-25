#!/usr/bin/env bash
# setup_clone.sh — one-time per-clone setup for an A2MC clone.
#
# Git cannot carry these three things (they live outside the repo tree or are
# per-clone index flags), so every fresh clone / new machine needs them once.
# This script does all three, idempotently and safely (re-runnable):
#
#   1. Activate the repo's git hooks       (git config core.hooksPath .githooks)
#   2. Suppress chroma.sqlite3 read-churn   (git update-index --skip-worktree ...)
#   3. Wire the .claude_memory auto-memory bucket symlink (with backup)
#
# Step 3 runs whenever this clone has a .claude_memory/ bucket, and wires whatever
# bucket THIS BRANCH carries — each branch's .claude_memory/ is its own branch-scoped
# auto-memory (main, adapter-kit, and the demo branch each keep their own copy). On
# this adapter-kit clone it wires the adapter-kit branch's bucket. It is a no-op only
# on a public / no-bucket clone.
#
# Usage:
#   scripts/setup_clone.sh              # do it
#   scripts/setup_clone.sh --dry-run    # preview, change nothing
#
# Rollback for step 3 is printed when it acts. Author: Jing Tao with Claude.

set -u

DRY=0
[ "${1:-}" = "--dry-run" ] && DRY=1

# run a command, or just print it in --dry-run mode (no eval — safe with spaces)
do_or_echo() {
    if [ "$DRY" = 1 ]; then echo "    [dry-run] would run: $*"; else "$@"; fi
}

ROOT="$(git rev-parse --show-toplevel 2>/dev/null)" || { echo "ERROR: not inside a git repo." >&2; exit 1; }
cd "$ROOT" || exit 1

echo "== A2MC clone setup"
echo "   repo:   $ROOT"
echo "   branch: $(git branch --show-current 2>/dev/null)"
[ "$DRY" = 1 ] && echo "   MODE:   DRY-RUN (no changes will be made)"
echo

# ---------------------------------------------------------------- 1. git hooks
echo "[1/3] git hooks (core.hooksPath)"
CUR_HOOKS="$(git config --get core.hooksPath 2>/dev/null || true)"
CUR_HOOKS="${CUR_HOOKS%/}"
if [ "$CUR_HOOKS" = ".githooks" ]; then
    echo "    already set: core.hooksPath = .githooks"
elif [ -n "$CUR_HOOKS" ] && [ "${CUR_HOOKS#/}" = "$CUR_HOOKS" ] && [ "${CUR_HOOKS%%/*}" != ".." ] \
     && [ -d "$ROOT/$CUR_HOOKS" ] \
     && [ -n "$(git -C "$ROOT" ls-files -- "$CUR_HOOKS/pre-commit" "$CUR_HOOKS/commit-msg" 2>/dev/null)" ]; then
    # A hooks directory this repository TRACKS, set by a project folder's own onboarding.
    # Resetting it would break that project's own checks; tools/check_clone_setup.py::_own_hooks_dir
    # is the same rule.
    echo "    kept: core.hooksPath = $CUR_HOOKS (this repository's own tracked hooks)"
elif [ -d "$ROOT/.githooks" ]; then
    do_or_echo git config core.hooksPath .githooks
    echo "    set core.hooksPath = .githooks"
else
    echo "    skip: no .githooks/ directory in this repo"
fi
echo

# ---------------------------------------------------------------- 2. chroma skip-worktree
echo "[2/3] chroma.sqlite3 skip-worktree (RAG read-churn suppression)"
CHROMA="$(git ls-files rag/chroma_db 2>/dev/null | grep '/chroma\.sqlite3$' || true)"
if [ -z "$CHROMA" ]; then
    echo "    skip: no tracked chroma.sqlite3 files"
else
    for f in $CHROMA; do
        if git ls-files -v "$f" 2>/dev/null | grep -q '^S '; then
            echo "    already skip-worktree: $f"
        else
            do_or_echo git update-index --skip-worktree "$f"
            echo "    set skip-worktree: $f"
        fi
    done
    echo "    (to commit a rebuilt index later: git update-index --no-skip-worktree <file> first)"
fi
echo

# ---------------------------------------------------------------- 3. .claude_memory symlink
echo "[3/3] .claude_memory auto-memory bucket symlink (this branch's own bucket)"
if [ ! -d "$ROOT/.claude_memory" ]; then
    echo "    skip: no .claude_memory/ in this repo (public / no-bucket clone)"
else
    # The harness reads memory from ~/.claude/projects/<cwd-key>/memory, where
    # <cwd-key> is the repo's absolute path with every '/' replaced by '-'.
    KEY="$(printf '%s' "$ROOT" | sed 's#/#-#g')"
    BUCKET="$HOME/.claude/projects/$KEY/memory"

    # If the derived bucket does not exist, a prior session may have used a
    # different path alias — try to discover an existing bucket for this repo.
    if [ ! -e "$BUCKET" ] && [ ! -L "$BUCKET" ]; then
        BASE="$(basename "$ROOT")"
        FOUND="$(find "$HOME/.claude/projects" -maxdepth 2 -type d -name memory -path "*${BASE}*" 2>/dev/null | head -1)"
        [ -n "$FOUND" ] && { echo "    note: derived path absent; using discovered bucket $FOUND"; BUCKET="$FOUND"; }
    fi

    if [ -L "$BUCKET" ]; then
        echo "    already symlinked: $BUCKET -> $(readlink "$BUCKET")"
    elif [ -d "$BUCKET" ]; then
        echo "    existing real bucket: $BUCKET"
        echo "    machine-only memories (present here but NOT in the repo) — review before they're shadowed:"
        ONLY="$(diff -rq "$BUCKET" "$ROOT/.claude_memory" 2>/dev/null | grep "^Only in $BUCKET" || true)"
        if [ -n "$ONLY" ]; then echo "$ONLY" | sed 's/^/      /'; echo "      ^ copy any you want to keep into $ROOT/.claude_memory (then commit) BEFORE proceeding."; else echo "      (none)"; fi
        do_or_echo mv "$BUCKET" "$BUCKET.pre-symlink-bak"
        do_or_echo ln -s "$ROOT/.claude_memory" "$BUCKET"
        echo "    backed up -> $BUCKET.pre-symlink-bak"
        echo "    symlinked  -> $ROOT/.claude_memory"
        echo "    ROLLBACK:  rm \"$BUCKET\" && mv \"$BUCKET.pre-symlink-bak\" \"$BUCKET\""
    else
        # no bucket yet (fresh clone, no session has run here)
        do_or_echo mkdir -p "$(dirname "$BUCKET")"
        do_or_echo ln -s "$ROOT/.claude_memory" "$BUCKET"
        echo "    created symlink: $BUCKET -> $ROOT/.claude_memory"
    fi

    if [ "$DRY" = 0 ] && [ -e "$BUCKET/MEMORY.md" ]; then
        echo "    verify: $(head -1 "$BUCKET/MEMORY.md")"
    fi
fi

# ---------------------------------------------------------------------------------------------
# 5. the temp directory a RUNTIME write lands in
#
# NERSC's hard rule is no writes outside $HOME. The PreToolUse hook that enforces it can only read
# a command's TEXT, so a path built at runtime -- a tempfile constructor, a library's scratch file
# -- carries no literal to match and slips past it. Pointing the temp-directory variable inside
# $HOME fixes that by construction, in any language that honours the variable.
#
# This lives in a SHELL PROFILE, so git cannot carry it and a fresh clone always starts without
# it. This step reports and prints the line; it does NOT edit your profile, because that file is
# outside this repository and outside this script's remit.
# ---------------------------------------------------------------------------------------------
echo
echo "== 5. runtime temp directory"
if [ -z "${NERSC_HOST:-}" ]; then
    # The rule is NERSC's; off NERSC this step does not apply, matching check_clone_setup.py's NA
    # (audit 20260923b, F28 and persona P2).
    echo "    N/A: not a NERSC machine (NERSC_HOST unset); the \$HOME-only write rule is NERSC's"
else
TD_REAL="$(cd "${TMPDIR:-/nonexistent}" 2>/dev/null && pwd -P || echo "")"
HOME_REAL="$(cd "$HOME" && pwd -P)"
case "$TD_REAL" in
    "$HOME_REAL"|"$HOME_REAL"/*)
        echo "    OK: $TMPDIR is inside \$HOME"
        ;;
    *)
        echo "    NOT SET UP: a runtime temp write would land outside \$HOME."
        echo "    Add this to your shell profile (~/.bashrc), then open a new shell:"
        echo
        echo "        [ -z \"\$SLURM_JOB_ID\" ] && [ -d \"$ROOT/tmp\" ] && export TMPDIR=\"$ROOT/tmp\""
        echo
        echo "    The SLURM_JOB_ID guard is deliberate: inside a batch job the system default"
        echo "    stands, so a large job's temporaries stay on node-local storage rather than"
        echo "    filling the home quota."
        ;;
esac
fi

echo
echo "== done.$([ "$DRY" = 1 ] && echo ' (dry-run — nothing changed)')"
