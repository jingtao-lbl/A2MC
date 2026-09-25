#!/usr/bin/env bash
# visibility: public
#
# _wrap_scaffold.sh — write the project half of a wrapped repo. Called by
# wrap_for_project_agent.sh --init; not meant to be run on its own.
#
# GENERATED, NOT COPIED. An earlier design scaffolded by copying a live instance, which needs a
# donor the user does not have and drifts from whatever that one project happened to grow. Every
# file here is written from this script, so a fresh wrap is reproducible and carries no other
# project's vocabulary.
#
#   $1 = destination repo root   $2 = project folder name   $3 = comma-separated models (may be empty)
#
# Author: Jing Tao with Claude on Perlmutter.
set -euo pipefail

DEST="$1" ; P="$2" ; MODELS="${3:-}"
D="$DEST/$P"
mkdir -p "$D"/{logs,scripts,.claude/hooks,.claude/skills,.githooks}

# ---------------------------------------------------------------- root banners (destination-owned)
cat > "$DEST/README.md" <<EOF
# $P

A project repository built on the A2MC framework.

\`$P/\` holds everything this project authors: its goals, its board, its logs, its scripts and its
agent. Everything else in this repository is the A2MC framework, and is **replaced wholesale** by
\`scripts/wrap_for_project_agent.sh --refresh\`. A framework fix belongs upstream in A2MC, not here.

Start: \`python3 $P/scripts/check_setup.py\`
EOF

cat > "$DEST/CLAUDE.md" <<EOF
# CLAUDE.md — $P

**This is a PROJECT repository, not an A2MC development clone.**

Read \`$P/CLAUDE.md\` — it is the contract for every session here. This file exists so an agent
landing at the repository root is not sent to A2MC's own development guide, which describes a
framework rather than this project.

| | |
|---|---|
| what this project is for | \`$P/RESEARCH_PLAN.md\` |
| what to do next | \`python3 $P/scripts/state.py next\` |
| how work is recorded | \`$P/logs/\`, one log per piece of work |
| the framework half | replaced on every refresh; fix it upstream, never here |
EOF

cat > "$DEST/AGENTS.md" <<EOF
# AGENTS.md — $P

The harness-neutral operating contract for an agent working in **this project**.

A2MC ships its own \`AGENTS.md\` describing a calibration framework and routing every session to its
own router. That document is true in A2MC and false here, which is why this repository owns this
file instead of receiving it.

## Every session

1. \`python3 $P/scripts/check_setup.py\` — the clone is wired, or it says what is missing.
2. Read \`$P/CLAUDE.md\`, then \`$P/RESEARCH_PLAN.md\`.
3. \`python3 $P/scripts/state.py next\` — the board proposes; you choose.

## Two rules that are not negotiable

- **No work without a log.** Open the log in \`$P/logs/\` before starting, not after finishing.
- **A framework fix goes upstream.** Anything outside \`$P/\` is replaced on the next refresh, so a
  change made there is lost and, worse, looks fine until it is.
EOF

# ---------------------------------------------------------------- project documents
cat > "$D/CLAUDE.md" <<EOF
# CLAUDE.md — $P

What an agent must know in **every** session in this project.

## What this project is

See \`RESEARCH_PLAN.md\`. Do not infer the goal from the board: the board holds tasks, the plan holds
the question they serve.

## Where things go

| | |
|---|---|
| the goal, and how it is being answered | \`RESEARCH_PLAN.md\` |
| tasks, decisions, people, key facts | \`PROJECT_STATE.json\` — the board, and the single source |
| \`TODO.md\` | **GENERATED** from the board. Never hand-edit it |
| a record of work done | \`logs/YYYYMMDDx_Topic_In_Title_Case.md\` |
| this project's own scripts | \`scripts/\` |
| this project's own skills | \`.claude/skills/\` — discovered as \`$P:<name>\` |

## The loop

1. \`python3 $P/scripts/state.py next\` proposes a task; you choose.
2. Open the log **before** starting.
3. Do the work. Anything outside \`$P/\` is framework and is not yours to edit here.
4. \`python3 $P/scripts/todo.py\` to regenerate \`TODO.md\`, then commit.

## The framework half

Everything outside \`$P/\` arrives from A2MC and is replaced on every refresh. It is there to be
used — its tools, its checkers, its knowledge bases and whichever models this project asked for
(\`${MODELS:-none}\`). It is not there to be edited.
EOF

cat > "$D/RESEARCH_PLAN.md" <<EOF
# $P — research plan

> **Fill this in before the first task.** It is the document every later "is this worth doing?"
> refers back to, and a board built without it holds tasks nobody can justify.

## The question

<!-- One paragraph. What is not known, and what would count as knowing it. -->

## Why it is answerable

<!-- The data, models and methods that make this tractable. Name what already exists. -->

## How it will be answered

<!-- The steps, in order. Each becomes one or more tasks on the board. -->

## What would make this fail

<!-- State it now, while it is cheap to say. -->

## Models

\`${MODELS:-none}\` — wrapped into this repository at creation. Adding another later means a refresh
with a wider \`--models\`.
EOF

# ---------------------------------------------------------------- the board
cat > "$D/PROJECT_STATE.json" <<EOF
{
  "schema": 1,
  "project": "$P",
  "updated": "$(date -u +%Y-%m-%d)",
  "note": "The board. TODO.md is generated from this file; edit here, never there.",
  "plan": "$P/RESEARCH_PLAN.md",
  "models": "${MODELS:-none}",
  "people": [],
  "key_facts": {},
  "decisions_open": [],
  "decisions_closed": [],
  "tasks": [
    {
      "id": "T1",
      "title": "Fill in RESEARCH_PLAN.md",
      "status": "open",
      "owner": null,
      "note": "Everything else on this board should be justifiable by the plan."
    }
  ]
}
EOF

cat > "$D/logs/README.md" <<EOF
# logs

One log per piece of work, opened **before** the work starts.

\`\`\`
YYYYMMDDx_Topic_In_Title_Case.md
\`\`\`

\`x\` is a per-day letter: a, b, c … Past \`z\`, keep \`z\` as a prefix and append a second letter
(\`za\`, \`zb\` …), which stays sort-stable where \`aa\` would not.

## Required header

\`\`\`markdown
# Title

**Date:** September 25, 2026
**Author:** <name>
**Status:** in progress | complete | abandoned
**Task:** <board id> | none

---
\`\`\`

Free prose below. \`python3 ../scripts/check_log.py <file>\` validates it, and the commit hook runs
it on staged logs.
EOF

# ---------------------------------------------------------------- the project's scripts
# NO `from __future__ import annotations` in anything generated here. The project's own
# documents tell a user to run `python3 <script>`, and the system python3 on some machines is
# 3.6, where that import is a SyntaxError. A scaffold that only runs under the author's
# interpreter is not a scaffold, and the failure lands on the first command a project's own
# documents tell a user to run.
cat > "$D/scripts/state.py" <<'PYEOF'
#!/usr/bin/env python3
"""The board: read PROJECT_STATE.json, answer what is next, and validate it.

visibility: public

The board is the single source. TODO.md is a VIEW of it, regenerated by todo.py, which is why this
file refuses to be the second place a task is written down.
"""
import json, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BOARD = ROOT / "PROJECT_STATE.json"
OPEN = ("open", "in_progress")


def load():
    try:
        return json.loads(BOARD.read_text())
    except FileNotFoundError:
        sys.exit("no %s — is this a wrapped project repo?" % BOARD.name)
    except ValueError as e:
        sys.exit("%s is not valid JSON: %s" % (BOARD.name, e))


def check(d):
    problems = []
    for k in ("schema", "project", "tasks"):
        if k not in d:
            problems.append("missing top-level key %r" % k)
    seen = set()
    for t in d.get("tasks", []):
        tid = t.get("id")
        if not tid:
            problems.append("a task has no id")
        elif tid in seen:
            problems.append("duplicate task id %r" % tid)
        seen.add(tid)
        if t.get("status") not in ("open", "in_progress", "completed", "abandoned"):
            problems.append("task %s has status %r" % (tid, t.get("status")))
    return problems


def main():
    cmd = sys.argv[1] if len(sys.argv) > 1 else "next"
    d = load()
    if cmd == "check":
        p = check(d)
        if p:
            print("\n".join("  - " + x for x in p)); return 1
        print("board ok: %d task(s), project %s" % (len(d.get("tasks", [])), d.get("project")))
        return 0
    if cmd == "next":
        nxt = [t for t in d.get("tasks", []) if t.get("status") in OPEN]
        if not nxt:
            print("nothing open. Add a task to %s." % BOARD.name); return 0
        t = nxt[0]
        print("%s  %s" % (t["id"], t.get("title", "")))
        if t.get("note"): print("   %s" % t["note"])
        return 0
    sys.exit("usage: state.py [next|check]")


if __name__ == "__main__":
    sys.exit(main())
PYEOF

cat > "$D/scripts/todo.py" <<'PYEOF'
#!/usr/bin/env python3
"""Regenerate TODO.md from the board. TODO.md is a VIEW; the board is the source.

visibility: public
"""
import json, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BOARD = ROOT / "PROJECT_STATE.json"
OUT = ROOT / "TODO.md"
CMD = "python3 %s/scripts/todo.py" % ROOT.name


def render(d):
    L = ["<!-- GENERATED FILE. Do not edit. Regenerate: %s -->" % CMD, "",
         "# %s — TODO" % d.get("project", "project"), ""]
    by = {}
    for t in d.get("tasks", []):
        by.setdefault(t.get("status", "open"), []).append(t)
    for status, head in (("in_progress", "In progress"), ("open", "Open"), ("completed", "Done")):
        rows = by.get(status, [])
        if not rows:
            continue
        L += ["## %s" % head, ""]
        for t in rows:
            mark = "x" if status == "completed" else " "
            owner = (" — %s" % t["owner"]) if t.get("owner") else ""
            L.append("- [%s] **%s** %s%s" % (mark, t.get("id", "?"), t.get("title", ""), owner))
        L.append("")
    return "\n".join(L).rstrip() + "\n"


def main():
    d = json.loads(BOARD.read_text())
    new = render(d)
    if "--check" in sys.argv:
        cur = OUT.read_text() if OUT.exists() else ""
        if cur != new:
            print("TODO.md is stale — regenerate with: %s" % CMD); return 1
        print("TODO.md is current"); return 0
    OUT.write_text(new)
    print("wrote %s" % OUT.name)
    return 0


if __name__ == "__main__":
    sys.exit(main())
PYEOF

cat > "$D/scripts/check_log.py" <<'PYEOF'
#!/usr/bin/env python3
"""Validate a project log: its filename, its header, and that it says something.

visibility: public
"""
import re, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
STEM = re.compile(r"^\d{8}[a-z]{1,3}_[A-Za-z0-9][A-Za-z0-9_]*\.md$")
NEED = ("**Date:**", "**Author:**", "**Status:**", "**Task:**")
STATUS = ("in progress", "complete", "abandoned")


def check(p: Path):
    bad = []
    if not STEM.match(p.name):
        bad.append("filename must be YYYYMMDDx_Topic_In_Title_Case.md")
    text = p.read_text(errors="replace")
    head = text.split("---", 1)[0]
    for k in NEED:
        if k not in head:
            bad.append("header missing %s" % k)
    m = re.search(r"\*\*Status:\*\*\s*(.+)", head)
    if m and m.group(1).strip().lower() not in STATUS:
        bad.append("Status must be one of: %s" % ", ".join(STATUS))
    if not text.lstrip().startswith("# "):
        bad.append("must open with a `# Title` line")
    body = text.split("---", 1)[1] if "---" in text else ""
    if len(body.strip()) < 40:
        bad.append("no body — a log with a header and nothing under it records nothing")
    return bad


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    files = [Path(a) for a in args] if args else sorted((ROOT / "logs").glob("2*.md"))
    rc = 0
    for f in files:
        bad = check(f)
        if bad:
            rc = 1
            print("✘ %s" % f.name)
            for b in bad:
                print("    - %s" % b)
    if rc == 0:
        print("✔ %d log(s) conform" % len(files))
    return rc


if __name__ == "__main__":
    sys.exit(main())
PYEOF

cat > "$D/scripts/check_setup.py" <<'PYEOF'
#!/usr/bin/env python3
"""Is this clone wired? One command instead of remembering four.

visibility: public

It DERIVES what it expects -- it enumerates the hooks this project actually has rather than
hardcoding their names, because a checker that hardcodes one name says nothing when a second
hook goes missing.
"""
import json, subprocess, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent      # the project folder
REPO = ROOT.parent
OK, BAD = "  ok  ", " FAIL "


def run(*a):
    try:
        # stdout=PIPE + universal_newlines, not capture_output=True + text=True: both of those
        # are 3.7+, and this script is run with whatever python3 the user has.
        r = subprocess.run(a, cwd=REPO, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                           universal_newlines=True, timeout=15)
        return r.returncode, r.stdout.strip()
    except (OSError, subprocess.SubprocessError):
        return 1, ""


def rows():
    out = []
    rc, top = run("git", "rev-parse", "--show-toplevel")
    out.append(("Repository", rc == 0, top or "not a git repository", None))

    rc, hp = run("git", "config", "--get", "core.hooksPath")
    want = "%s/.githooks" % ROOT.name
    out.append(("Git hooks", hp == want, hp or "unset",
                "git config core.hooksPath %s" % want))

    board = ROOT / "PROJECT_STATE.json"
    ok = board.is_file()
    if ok:
        try:
            json.loads(board.read_text())
        except ValueError:
            ok = False
    out.append(("Board", ok, board.name, "fix %s" % board.name))

    # DERIVED: every hook this project ships must be registered in the repo's settings.
    settings = REPO / ".claude" / "settings.json"
    hooks = sorted(p.name for p in (ROOT / ".claude" / "hooks").glob("*.py"))
    reg = settings.read_text() if settings.is_file() else ""
    missing = [h for h in hooks if h not in reg]
    out.append(("Agent hooks", not missing,
                "%d registered" % (len(hooks) - len(missing)) if hooks else "none to register",
                "register %s in .claude/settings.json" % ", ".join(missing) if missing else None))

    rc, _ = run("python3", "%s/scripts/check_log.py" % ROOT.name)
    out.append(("Logs", rc == 0, "conform" if rc == 0 else "see check_log.py", None))
    return out


def main():
    print("%s setup — %s\n" % (ROOT.name, REPO))
    bad = 0
    for name, ok, detail, fix in rows():
        print("  [%s] %-14s %s" % (OK if ok else BAD, name, detail))
        if not ok:
            bad += 1
            if fix:
                print("                        -> %s" % fix)
    print()
    if bad:
        print("%d row(s) need attention." % bad)
        return 1
    print("Every row ok. Next: python3 %s/scripts/state.py next" % ROOT.name)
    return 0


if __name__ == "__main__":
    sys.exit(main())
PYEOF
chmod +x "$D/scripts/"*.py

# ---------------------------------------------------------------- the agent layer
cat > "$D/.claude/hooks/session-start.py" <<'PYEOF'
#!/usr/bin/env python3
"""Print this project's board at session start, so a session opens knowing where it is.

visibility: public
"""
import json, os, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]          # the project folder
BOARD = ROOT / "PROJECT_STATE.json"


def main():
    try:
        d = json.loads(BOARD.read_text())
    except (OSError, ValueError):
        return 0                                     # never block a session on the board
    lines = ["%s — project board" % d.get("project", ROOT.name)]
    if d.get("models") and d["models"] != "none":
        lines.append("  models wrapped: %s" % d["models"])
    tasks = d.get("tasks", [])
    nxt = [t for t in tasks if t.get("status") in ("open", "in_progress")]
    lines.append("  %d task(s), %d open" % (len(tasks), len(nxt)))
    if nxt:
        t = nxt[0]
        lines.append("  NEXT: %s  %s" % (t.get("id", "?"), t.get("title", "")))
    lines.append("  plan: %s   loop: %s/CLAUDE.md" % (d.get("plan", "RESEARCH_PLAN.md"), ROOT.name))
    print("\n".join(lines))
    return 0


if __name__ == "__main__":
    sys.exit(main())
PYEOF

cat > "$D/.githooks/pre-commit" <<HOOKEOF
#!/bin/bash
# visibility: public
#
# BOTH HALVES RUN. \`core.hooksPath\` is repository-wide and single-valued, so pointing it here would
# REPLACE the repository root's \`.githooks/\` for this clone. It does not, because the last step of
# this script CALLS the root hook. So a commit gets this project's checks AND the framework's.
#
# Do NOT \`git config --unset core.hooksPath\` to "get the framework checks back": that silences the
# project checks below and changes nothing about the framework's.
set -u
ROOT="\$(git rev-parse --show-toplevel)"
P="$P"
rc=0

staged() { git diff --cached --name-only --diff-filter=ACM; }

# --- staged project logs must conform -------------------------------------------------------
LOGS=\$(staged | grep -E "^\$P/logs/2.*\.md\$" || true)
if [ -n "\$LOGS" ]; then
    if ! python3 "\$ROOT/\$P/scripts/check_log.py" \$LOGS; then
        echo "pre-commit: a staged log does not conform (see above)." >&2
        rc=1
    fi
fi

# --- the board must stay valid, and TODO.md is generated from it -----------------------------
if staged | grep -q "^\$P/PROJECT_STATE.json\$"; then
    python3 "\$ROOT/\$P/scripts/state.py" check || rc=1
    if ! python3 "\$ROOT/\$P/scripts/todo.py" --check >/dev/null 2>&1; then
        echo "  [warn] TODO.md is stale — regenerate: python3 \$P/scripts/todo.py" >&2
    fi
fi

# --- TODO.md is GENERATED --------------------------------------------------------------------
if staged | grep -q "^\$P/TODO.md\$" && ! staged | grep -q "^\$P/PROJECT_STATE.json\$"; then
    echo "  [warn] TODO.md is staged without the board. It is GENERATED; a hand edit is overwritten." >&2
fi

# --- the framework's own checks, chained ------------------------------------------------------
# Safe because every framework check is gated on a framework path, so a commit touching only
# \$P/ passes it silently. What DOES still fire is its ungated oversized-blob guard, which this
# project wants anyway: a host rejects a large file at PUSH, when the commit already exists.
if [ -x "\$ROOT/.githooks/pre-commit" ]; then
    "\$ROOT/.githooks/pre-commit" || rc=1
fi

exit \$rc
HOOKEOF

cat > "$D/.githooks/commit-msg" <<'HOOKEOF'
#!/bin/bash
# visibility: public
#
# Chains the framework's commit-msg rather than duplicating its rules, so the framework's copy
# stays authoritative and this file cannot drift from it.
set -u
ROOT="$(git rev-parse --show-toplevel)"
if [ -x "$ROOT/.githooks/commit-msg" ]; then
    exec "$ROOT/.githooks/commit-msg" "$1"
fi
exit 0
HOOKEOF
chmod +x "$D/.githooks/pre-commit" "$D/.githooks/commit-msg" "$D/.claude/hooks/session-start.py"

# ---------------------------------------------------------------- register the project's hooks
python3 - "$DEST" "$P" <<'PYEOF'
import json, sys, pathlib
dest, p = pathlib.Path(sys.argv[1]), sys.argv[2]
f = dest / ".claude" / "settings.json"
f.parent.mkdir(parents=True, exist_ok=True)
try:
    d = json.loads(f.read_text())
except (OSError, ValueError):
    d = {}
hooks = d.setdefault("hooks", {})
entry = {"type": "command",
         "command": 'python3 "${CLAUDE_PROJECT_DIR}/%s/.claude/hooks/session-start.py"' % p}
groups = hooks.setdefault("SessionStart", [])
if not any(h.get("command") == entry["command"] for g in groups for h in g.get("hooks", [])):
    groups.append({"hooks": [entry]})
f.write_text(json.dumps(d, indent=2) + "\n")
print("  registered %s/.claude/hooks/session-start.py in .claude/settings.json" % p)
PYEOF

# ---------------------------------------------------------------- generate TODO.md
python3 "$D/scripts/todo.py" >/dev/null 2>&1 || true
