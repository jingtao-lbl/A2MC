#!/bin/bash
# model_archive_build.sh — archive a model's built executable, keyed by branch+commit.
#
# WHY THIS EXISTS
#   A git branch isolates SOURCE, not ARTIFACTS. Models built with a shared CMake/make tree
#   (EcoSIM, PFLOTRAN, ATS) have exactly ONE executable, and every build overwrites it in place
#   whatever branch is checked out. On 2026-08-07 that destroyed the binary an entire completed
#   calibration campaign had been run with: the output tapes survived, the executable did not.
#   CIME models (ELM/FATES) build per CASE and do not have this failure mode.
#
#   Run this after every successful build, BEFORE building anything else.
#   Contract: .claude/skills/model-evolution/SKILL.md step 3.5.
#
# USAGE
#   tools/model_archive_build.sh --tree <src> --binary <path> --archive <dir>
#                                [--label <name> --commit <sha>]
#
#   --tree     the model source checkout (a git repo; branch/commit are read from it)
#   --binary   the built executable, ABSOLUTE or relative to --tree
#   --archive  archive root; the copy lands in <archive>/<label>_<shortsha>/
#   --label    archive label; defaults to the checked-out branch.
#   --commit   commit the binary was built from; defaults to the tree's HEAD.
#
# ARCHIVE IMMEDIATELY AFTER THE BUILD, while the tree still matches the binary. That is the only
# state in which this script can derive provenance at all. If the tree has since been restored to
# a different branch -- exactly what a guarded parent-baseline build leaves behind -- then BOTH
# the branch and HEAD are wrong for that binary, so --label and --commit must be given TOGETHER
# and their correctness is the caller's responsibility. Supplying only --label is refused: it
# produced a nonsense pairing (parent's label + change's SHA, on the parent's binary) the first
# time this script was used, which is the very mislabelling it is meant to prevent.
#
# Generic by parameterization rather than by ModelSpec dispatch: the spec has no build-artifact
# fields yet. Promoting this to `--model <name>` needs additive spec fields (build system +
# binary path); see TODO.md.
set -euo pipefail

TREE=""; BINARY=""; ARCHIVE=""; LABEL=""; COMMIT=""
while [ $# -gt 0 ]; do
  case "$1" in
    --tree)    TREE="$2"; shift 2;;
    --binary)  BINARY="$2"; shift 2;;
    --archive) ARCHIVE="$2"; shift 2;;
    --label)   LABEL="$2"; shift 2;;
    --commit)  COMMIT="$2"; shift 2;;
    -h|--help) sed -n '2,33p' "$0"; exit 0;;
    *) echo "ERROR: unknown argument '$1'" >&2; exit 2;;
  esac
done
[ -n "$TREE" ] && [ -n "$BINARY" ] && [ -n "$ARCHIVE" ] || {
  echo "ERROR: --tree, --binary and --archive are required (see --help)" >&2; exit 2; }
[ -d "$TREE/.git" ] || { echo "ERROR: '$TREE' is not a git checkout" >&2; exit 2; }

case "$BINARY" in /*) EXE="$BINARY";; *) EXE="$TREE/$BINARY";; esac
[ -f "$EXE" ] || { echo "ERROR: no executable at $EXE" >&2; exit 1; }

# Refuse when the model's own tracked source is dirty: the archived binary would not correspond
# to the commit it is about to be filed under. Scoped to TRACKED changes -- an earlier version
# globbed '*.F90' and counted hundreds of untracked vendored sources inside the build dir,
# firing on every run.
DIRTY=$(git -C "$TREE" status --porcelain --untracked-files=no | wc -l)
if [ "$DIRTY" -ne 0 ]; then
  echo "ERROR: '$TREE' has uncommitted tracked changes -- commit first, or the archived binary" >&2
  echo "       will be filed under a commit whose source is not what produced it:" >&2
  git -C "$TREE" status --porcelain --untracked-files=no | head -5 >&2
  exit 1
fi

# Either BOTH overrides or NEITHER. One alone silently mixes tree-derived and caller-supplied
# provenance, which is how a parent binary got filed under a change commit.
if { [ -n "$LABEL" ] && [ -z "$COMMIT" ]; } || { [ -z "$LABEL" ] && [ -n "$COMMIT" ]; }; then
  echo "ERROR: --label and --commit must be given TOGETHER. One alone mixes caller-supplied and" >&2
  echo "       tree-derived provenance and mislabels the archive." >&2
  exit 2
fi
if [ -n "$LABEL" ]; then
  SHA="$COMMIT"
  echo "NOTE: provenance supplied by the caller (label=$LABEL commit=$SHA); not verified against $TREE" >&2
else
  SHA=$(git -C "$TREE" rev-parse --short HEAD)
  LABEL=$(git -C "$TREE" branch --show-current)
  [ -n "$LABEL" ] || LABEL="detached"
fi
DEST="$ARCHIVE/$(echo "$LABEL" | tr '/ ' '--')_$SHA"

if [ -e "$DEST/$(basename "$EXE")" ]; then
  echo "ERROR: $DEST already holds an archived binary. Refusing to overwrite an archive --" >&2
  echo "       that is the very failure this script exists to prevent. Remove it deliberately" >&2
  echo "       if you really mean to replace it." >&2
  exit 1
fi

mkdir -p "$DEST"
cp -p "$EXE" "$DEST/"
MD5=$(md5sum "$EXE" | cut -d' ' -f1)
{
  # Report the commit this binary is FILED under, which is $SHA -- not necessarily the tree's
  # HEAD, since the caller may have overridden both. Writing `git log -1` unconditionally would
  # contradict the directory name in exactly the override case.
  echo "commit:  $SHA"
  git -C "$TREE" log -1 --format="tree HEAD: %H (%s)"
  echo "label:   $LABEL"
  echo "tree:    $TREE"
  echo "binary:  $EXE"
  echo "md5:     $MD5"
  echo "archived: $(date)"
} > "$DEST/PROVENANCE.txt"

echo "archived -> $DEST"
echo "md5 $MD5"
