#!/usr/bin/env bash
# visibility: public
#
# wrap_for_project_agent.sh — wrap A2MC's harness engineering AROUND a project, so the project
# gets an agent.
#
# A2MC's board, hooks, log contract and checkers, memory bucket and skills discipline are reusable
# independently of calibration. This packs them, plus whatever model capability the project asks
# for, into an `A2MC-<Name>` repository whose ONE top-level `<Project>/` folder holds everything
# the project authors and survives every later refresh.
#
# NOTHING HERE IS REQUIRED TO USE A2MC. A user who wants to calibrate a model just uses A2MC:
# a2mc-init, onboard-model, onboard-case. This is for a project where calibration is one step among
# others, or where there is none at all.
#
#   --init      create the destination: banners and protection FIRST, then the framework surface
#   --refresh   bring framework updates across, leaving every project-owned path untouched
#
# THE ORDER IN --init IS THE POINT. Every protection is established before the first copy, because
# the copy is forward-only three ways over: an exclude hides a path so --delete never considers it,
# dropping an include retracts nothing, and a merge cannot restore what a merged commit deleted.
#
# Author: Jing Tao with Claude on Perlmutter.
set -euo pipefail

A2MC_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
MARKER=".a2mc-downstream"
KNOWN_MODELS=(fates elm ecosim pflotran ats)

PROJECT="" ; DEST="" ; MODELS="" ; REMOTE="" ; MODE="" ; DRY=false ; ALLOW_DIRTY=false ; BRANCH="main"

die()  { echo "ERROR: $*" >&2; exit 1; }
note() { echo "  $*"; }
run()  { if [[ "$DRY" == true ]]; then echo "  [dry] $*"; else eval "$@"; fi; }

usage() {
    sed -n '3,20p' "${BASH_SOURCE[0]}" | sed 's/^# \{0,1\}//'
    cat <<'USAGE'

Usage:
  wrap_for_project_agent.sh --init --project <Name> --dest <path> [--models a,b] [--remote <url>]
  wrap_for_project_agent.sh --refresh --dest <path> [--branch <name>] [--allow-dirty]
  Both accept --dry-run.

  --models   comma-separated from: fates elm ecosim pflotran ats
             Omitted means NONE: no knowledge base, RAG profile, adapter, case template or
             model-specific skill travels. That is the right answer for a project with no
             calibration, and it is where the weight is -- those paths are most of the tree.
USAGE
}

# ---------------------------------------------------------------- arguments
while [[ $# -gt 0 ]]; do
    case "$1" in
        --init) MODE="init" ;;
        --refresh) MODE="refresh" ;;
        --project) PROJECT="${2:-}"; shift ;;
        --dest) DEST="${2:-}"; shift ;;
        --models) MODELS="${2:-}"; shift ;;
        --remote) REMOTE="${2:-}"; shift ;;
        --branch) BRANCH="${2:-}"; shift ;;
        --dry-run) DRY=true ;;
        --allow-dirty) ALLOW_DIRTY=true ;;
        -h|--help) usage; exit 0 ;;
        *) die "unknown argument: $1  (--help for usage)" ;;
    esac
    shift
done
[[ -n "$MODE" ]] || { usage; die "one of --init or --refresh is required"; }
[[ -n "$DEST"  ]] || die "--dest is required"

# ---------------------------------------------------------------- the source must be CLEAN
# THIS SCRIPT COPIES; IT DOES NOT FILTER. Everything it copies is taken as fit to travel, so the
# source has to be an A2MC release rather than a working tree it was cut from. The two are
# distinguishable by what only the latter carries -- development logs, an agent memory bucket, a
# maintainer's TODO -- so that is what the guard looks for, and it refuses rather than guessing.
assert_clean_source() {
    local dirty=()
    compgen -G "$A2MC_ROOT/memory/dev_logs*" >/dev/null 2>&1 && dirty+=("memory/dev_logs*/")
    [[ -d "$A2MC_ROOT/.claude_memory" ]] && dirty+=(".claude_memory/")
    [[ -f "$A2MC_ROOT/TODO.md" ]] && dirty+=("TODO.md")
    if [[ ${#dirty[@]} -gt 0 ]]; then
        echo "ERROR: this looks like an A2MC DEVELOPMENT clone, not a public one." >&2
        printf '       found: %s\n' "${dirty[@]}" >&2
        cat >&2 <<'WHY'

       Wrap from a released A2MC clone, not from a working tree it was cut from. This script
       copies what it finds without filtering, so a development tree's contents would be
       carried straight into the new project repository.

       Clone A2MC, then run this from there.
WHY
        exit 1
    fi
}

# ---------------------------------------------------------------- the framework surface
# UNIVERSAL — every project gets these. The harness is the reason to wrap A2MC at all.
UNIVERSAL=(
    "tools/" "scripts/" "tests/" "templates/" "phases/" "reasoning/" "orchestrator.py"
    ".claude/hooks/" ".claude/skills/" ".githooks/" "a2mc_config.sh" "a2mc_noncime_config.sh"
    "docs/a2mc_reference/" "docs/tutorial/" "memory/__init__.py" "memory/manager.py" "memory/store.py"
    "plot/" "pytest.ini" "requirements.txt" "LICENSE" "VERSION" "use_cases/README.md" "use_cases/TEMPLATE/"
)
# AGENTS.md is NOT here, deliberately: it is DESTINATION-OWNED. A2MC's own opens by calling itself
# a calibration framework and routes every session to its router, which is true there and false in a
# project repo. The scaffold writes the project's before any framework path lands; listing it here
# would have the copy overwrite it.
#
# The online loop (orchestrator.py, reasoning/) is in UNIVERSAL deliberately: it is 0.7 MB against
# rag/ at 91 MB, and eight shipped skills cite it as the online counterpart they are the offline
# analog of, so dropping it saves nothing and creates eight dead references.

# MODEL-SCOPED — every one of these paths is already named for its model, so the subset derives.
model_paths() {                       # $1 = model
    local m="$1"
    [[ -d "$A2MC_ROOT/docs/$m-knowledge-base" ]] && echo "docs/$m-knowledge-base/"
    [[ -d "$A2MC_ROOT/models/$m"             ]] && echo "models/$m/"
    [[ -d "$A2MC_ROOT/memory/$m"             ]] && echo "memory/$m/"
    # FATES is A2MC's built-in path, so its knowledge store is the unprefixed one.
    [[ "$m" == "fates" && -d "$A2MC_ROOT/memory/gained_knowledge" ]] && echo "memory/gained_knowledge/"
    local tpl
    for tpl in "$A2MC_ROOT"/use_cases/*_template; do
        [[ -d "$tpl" ]] || continue
        local b; b="$(basename "$tpl")"
        # ELM-FATES_template serves both fates and elm; match case-insensitively on the stem.
        if [[ "${b,,}" == *"${m,,}"* ]]; then echo "use_cases/$b/"; fi
    done
    # RAG profiles are named <model>-<hash>, or api-<major>-<minor> for the FATES/ELM line.
    local p pre
    for p in "$A2MC_ROOT"/rag/chroma_db/*/; do
        [[ -d "$p" ]] || continue
        pre="$(basename "$p")"
        if [[ "$pre" == "$m"-* ]] || { [[ "$m" == "fates" || "$m" == "elm" ]] && [[ "$pre" == api-* ]]; }; then
            echo "rag/chroma_db/$pre/"; echo "rag/graphs/$pre.json"; echo "rag/metadata/$pre.json"
        fi
    done
}

WANTED=()
if [[ -n "$MODELS" ]]; then
    IFS=',' read -ra WANTED <<< "$MODELS"
    for m in "${WANTED[@]}"; do
        [[ " ${KNOWN_MODELS[*]} " == *" $m "* ]] || die "unknown model '$m' — known: ${KNOWN_MODELS[*]}"
    done
fi

build_includes() {
    INCLUDES=("${UNIVERSAL[@]}")
    # rag/ machinery travels whenever ANY model does; its profiles are added per model above.
    if [[ ${#WANTED[@]} -gt 0 ]]; then
        local f
        for f in "$A2MC_ROOT"/rag/*.py "$A2MC_ROOT"/rag/*.json "$A2MC_ROOT"/rag/*.yaml; do
            [[ -f "$f" ]] && INCLUDES+=("rag/$(basename "$f")")
        done
        INCLUDES+=("rag/data/")
        local m path
        for m in "${WANTED[@]}"; do
            while IFS= read -r path; do [[ -n "$path" ]] && INCLUDES+=("$path"); done < <(model_paths "$m")
        done
    fi
}

# Skills the project's model set does NOT need. Derived from each skill's `modes.scope`, never a
# hand-list: a hand-list goes stale the first time a skill is added.
pick_py() {
    # A capable python, not merely A python. The system python3 here is 3.6 and cannot parse the
    # resolver; picking it silently is how the drop step returned "0 dropped" while shipping every
    # model's skills to a project that asked for one.
    local p
    for p in "${A2MC_PYTHON:-}" "$HOME/a2mc_env/bin/python3" python3; do
        [[ -n "$p" ]] && command -v "$p" >/dev/null 2>&1 \
            && "$p" -c 'import sys; sys.exit(0 if sys.version_info[:2] >= (3,7) else 1)' >/dev/null 2>&1 \
            && { echo "$p"; return; }
    done
    return 1
}

# Skills the project's model set does NOT need. Derived from each skill's `modes.scope`, never a
# hand-list: a hand-list goes stale the first time a skill is added.
#
# THIS FAILS LOUDLY ON PURPOSE. Its failure mode is "ship every model's skills to a project that
# asked for one", which looks exactly like success in the output and is only visible much later,
# in someone else's repo.
drop_skills() {
    local py resolver="$A2MC_ROOT/tools/skill_models.py"
    [[ -f "$resolver" ]] || die "tools/skill_models.py is missing; cannot decide which skills this project needs"
    py="$(pick_py)" || die "no python >= 3.7 found; set A2MC_PYTHON. Refusing to guess the skill subset."
    local arg="$MODELS"
    [[ -z "$arg" ]] && arg="__none__"
    if [[ "$arg" == "__none__" ]]; then
        # No models requested: every model-scoped skill goes.
        "$py" - "$resolver" <<'PY' || die "the skill resolver failed; refusing to ship an unfiltered skill set"
import importlib.util, sys
spec = importlib.util.spec_from_file_location("sm", sys.argv[1])
m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
for n, mods in sorted(m.all_skills().items()):
    if mods:
        print(n)
PY
    else
        "$py" "$resolver" --drop-for "$arg" || die "the skill resolver failed for models '$arg'; refusing to ship an unfiltered skill set"
    fi
}

# ---------------------------------------------------------------- shared helpers
project_collides() {                  # a project folder must not shadow a framework path
    local p="$1" e
    for e in "${UNIVERSAL[@]}"; do
        [[ "${e%/}" == "$p" ]] && return 0
    done
    [[ -e "$A2MC_ROOT/$p" ]] && return 0
    return 1
}

write_marker() {
    cat > "$DEST/$MARKER" <<'EOF'
# This is a DOWNSTREAM COPY of the A2MC framework, produced by wrap_for_project_agent.sh.
#
# Framework paths here are REPLACED on every refresh. Do not fix framework code in this repo:
# the fix belongs upstream, where the refresh runs from. Everything this project authors lives in
# its own top-level folder and is never touched.
#
# A2MC's checkers read this file. Its presence tells them that whatever this copy does not carry --
# a model the project did not ask for, and material that does not travel with a release -- is absent
# BY DESIGN, so they report it as advisory rather than failing.
EOF
}

# ============================================================================ INIT
do_init() {
    assert_clean_source
    [[ -n "$PROJECT" ]] || die "--init requires --project"
    [[ "$PROJECT" =~ ^[A-Za-z][A-Za-z0-9_-]*$ ]] || die "project name must start with a letter and contain only letters, digits, - or _"
    project_collides "$PROJECT" && die "project name '$PROJECT' collides with a framework path — pick another"
    [[ ! -e "$DEST" || -z "$(ls -A "$DEST" 2>/dev/null)" ]] || die "destination '$DEST' exists and is not empty"

    echo "=== wrap_for_project_agent --init ==="
    note "project : $PROJECT"
    note "dest    : $DEST"
    note "models  : ${MODELS:-<none> (no knowledge base, RAG, adapter or model skill will travel)}"
    echo

    run "mkdir -p '$DEST'"
    if [[ "$DRY" == false ]]; then
        git -C "$DEST" rev-parse --git-dir >/dev/null 2>&1 || git -C "$DEST" init -q -b "$BRANCH"
        [[ -n "$REMOTE" ]] && { git -C "$DEST" remote remove origin 2>/dev/null || true; git -C "$DEST" remote add origin "$REMOTE"; }
        # core.hooksPath is per-clone and UNTRACKED, so git cannot carry it and a fresh clone of
        # this repo starts without it. Set it here, and the project's setup check asks for it again
        # on every other clone. It points at the PROJECT's hooks, which chain the framework's --
        # both halves run, so this is not a trade.
        git -C "$DEST" config core.hooksPath "$PROJECT/.githooks"
    fi

    build_includes

    # ---- 1. banners and protection BEFORE any framework path is copied --------------------
    echo "Writing the project's own documents (before any framework path lands)..."
    if [[ "$DRY" == false ]]; then
        mkdir -p "$DEST/$PROJECT"/{logs,scripts,.claude/hooks,.claude/skills,.githooks}
        "$A2MC_ROOT/scripts/_wrap_scaffold.sh" "$DEST" "$PROJECT" "$MODELS"
    fi
    note "root CLAUDE.md, README.md, AGENTS.md  (destination-owned: a refresh never overwrites them)"
    note "$PROJECT/ scaffold: RESEARCH_PLAN.md PROJECT_STATE.json CLAUDE.md TODO.md logs/ scripts/"

    # ---- 2. the separation manifest, DERIVED ---------------------------------------------
    if [[ "$DRY" == false ]]; then
        {
            echo "# Separation manifest — generated by wrap_for_project_agent.sh. Do not edit."
            echo "# Regenerate: scripts/wrap_for_project_agent.sh --refresh --dest <this repo>"
            echo
            echo "project: $PROJECT"
            echo "models: ${MODELS:-none}"
            echo "generated: $(date -u +%Y-%m-%dT%H:%M:%SZ)"
            echo
            echo "destination_owned:"
            printf '  - %s\n' "$PROJECT/" "CLAUDE.md" "README.md" "AGENTS.md" "$MARKER" ".gitignore"
            echo
            echo "framework_paths:"
            printf '  - %s\n' "${INCLUDES[@]}"
        } > "$DEST/$PROJECT/SEPARATION_MANIFEST.yaml"
    fi
    note "$PROJECT/SEPARATION_MANIFEST.yaml  (derived from the include list, not hand-written)"

    # ---- 3. the framework surface ---------------------------------------------------------
    echo "Copying the framework surface (${#INCLUDES[@]} paths)..."
    copy_framework
    write_marker_step

    # ---- 4. .gitignore and the first commit ----------------------------------------------
    if [[ "$DRY" == false ]]; then
        cat > "$DEST/.gitignore" <<'EOF'
__pycache__/
*.pyc
.pytest_cache/
.ipynb_checkpoints/
tmp/
*.log
EOF
        git -C "$DEST" add -A
        git -C "$DEST" -c user.name="${GIT_AUTHOR_NAME:-$(git config user.name)}" \
            -c user.email="${GIT_AUTHOR_EMAIL:-$(git config user.email)}" \
            commit -qm "Wrap A2MC for $PROJECT

Framework half from A2MC $(cat "$A2MC_ROOT/VERSION" 2>/dev/null || echo "unknown"), models: ${MODELS:-none}.
The $PROJECT/ folder is this repository's own and is never overwritten by a refresh."
    fi
    echo
    echo "=== done ==="
    note "next: cd $DEST && python3 $PROJECT/scripts/check_setup.py"
}

copy_framework() {
    local item src dst
    for item in "${INCLUDES[@]}"; do
        src="$A2MC_ROOT/${item%/}"
        if [[ ! -e "$src" ]]; then note "[!] MISSING (not in the source): $item"; continue; fi
        dst="$DEST/${item%/}"
        if [[ "$DRY" == true ]]; then echo "  [dry] $item"; continue; fi
        mkdir -p "$(dirname "$dst")"
        if [[ -d "$src" ]]; then
            rsync -aL --delete --exclude='__pycache__' --exclude='*.pyc' --exclude='.ipynb_checkpoints' \
                  --exclude='.pytest_cache' "$src/" "$dst/"
        else
            rsync -aL "$src" "$dst"
        fi
    done
    # Skills belonging only to models this project did not ask for.
    local s n=0
    while IFS= read -r s; do
        [[ -n "$s" ]] || continue
        if [[ "$DRY" == true ]]; then echo "  [dry] drop skill: $s"; else rm -rf "$DEST/.claude/skills/$s"; fi
        n=$((n+1))
    done < <(drop_skills | sort -u)
    note "model-scoped skills dropped: $n"

    # De-register what was dropped, so the destination's registries describe what it actually has.
    if [[ "$DRY" == false && $n -gt 0 ]]; then
        local py2 names
        py2="$(pick_py)" || die "no python >= 3.7 to de-register dropped skills"
        names="$(drop_skills | sort -u | tr '\n' ' ')"
        # shellcheck disable=SC2086
        "$py2" "$A2MC_ROOT/scripts/_wrap_deregister.py" "$DEST" $names
    fi
}

write_marker_step() {
    if [[ "$DRY" == false ]]; then write_marker; fi
    note "$MARKER written (framework checkers will read this tree as a downstream copy)"
}

# ============================================================================ REFRESH
do_refresh() {
    assert_clean_source
    [[ -d "$DEST/.git" ]] || die "destination '$DEST' is not a git repository"
    [[ -f "$DEST/$MARKER" ]] || die "destination has no $MARKER — this does not look like a wrapped project repo"

    local cur; cur="$(git -C "$DEST" rev-parse --abbrev-ref HEAD)"
    [[ "$cur" == "$BRANCH" ]] || die "destination is on '$cur'; this refresh writes '$BRANCH' only. Switch it, or pass --branch."

    local dirty; dirty="$(git -C "$DEST" status --porcelain | wc -l)"
    if [[ "$dirty" -gt 0 && "$ALLOW_DIRTY" == false ]]; then
        git -C "$DEST" status --short | head -20 >&2
        die "destination working tree is DIRTY ($dirty path(s)). A refresh is rsync --delete per path and destroys uncommitted work with no record. Commit it, or pass --allow-dirty once you have looked."
    fi

    # Read the manifest so the refresh uses the SAME project and model set --init did.
    local man; man="$(ls "$DEST"/*/SEPARATION_MANIFEST.yaml 2>/dev/null | head -1)"
    [[ -n "$man" ]] || die "no SEPARATION_MANIFEST.yaml in the destination — was this created by --init?"
    PROJECT="$(awk '/^project:/{print $2}' "$man")"
    local man_models; man_models="$(awk '/^models:/{print $2}' "$man")"
    [[ "$man_models" == "none" ]] && man_models=""
    if [[ -z "$MODELS" ]]; then MODELS="$man_models"; WANTED=(); [[ -n "$MODELS" ]] && IFS=',' read -ra WANTED <<< "$MODELS"; fi

    echo "=== wrap_for_project_agent --refresh ==="
    note "project : $PROJECT   models: ${MODELS:-none}   branch: $BRANCH"

    build_includes

    # DESTINATION_OWNED hard-abort: a project path must never re-enter the copy list.
    local item
    for item in "${INCLUDES[@]}"; do
        case "${item%/}" in
            "$PROJECT"|CLAUDE.md|README.md|AGENTS.md|"$MARKER")
                die "'$item' is destination-owned and is in the copy list. Refusing: a refresh would overwrite the project's own file." ;;
        esac
    done
    note "destination-owned guard: clear"

    echo "Refreshing the framework surface (${#INCLUDES[@]} paths)..."
    copy_framework
    write_marker_step

    if [[ "$DRY" == false ]]; then
        echo
        echo "Changed by this refresh:"
        git -C "$DEST" status --short | sed 's/^/  /' | head -30
        local n; n="$(git -C "$DEST" status --porcelain | wc -l)"
        [[ "$n" -eq 0 ]] && note "nothing changed — the destination was already current"
        echo
        note "review, then commit IN THE DESTINATION. This script never commits a refresh:"
        note "  git -C $DEST add -A && git -C $DEST commit -m 'Refresh A2MC framework'"
    fi
}

case "$MODE" in
    init) do_init ;;
    refresh) do_refresh ;;
esac
