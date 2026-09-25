#!/usr/bin/env python3
"""Is THIS CLONE wired? One command, instead of remembering four things git cannot carry.

WHY IT EXISTS. `scripts/setup_clone.sh` does the wiring and has since 2026-07-28. Nothing ever
checked that it had been run, and a setup step nobody checks is a setup step that silently did not
happen. The failure is invisible in the worst way: the session does less than the person believes
it is doing, and every individual command still succeeds.

WHY IT IS SEPARATE FROM check_stage_ready.py. That script asks which SETUP STAGE a clone is in,
and answers stage 4 -- "setup is done" -- as soon as any case carries offline workflow state. A
case is DELIVERED: emailed as a folder and unpacked under `use_cases/`. So a brand-new clone that
has been wired to nothing reports "setup is done" the moment someone drops a finished case into
it, and the per-clone rows, which live in that script's stage-1 branch, are never reached. The
clone's wiring and the case's maturity are independent facts; this file owns the first one, and
`check_stage_ready.py` now asks it at every stage rather than only at stage 1.

EVERY ROW IS REQUIRED. None of these is a matter of taste. Without `core.hooksPath` the repository's
own commit checks never fire and a malformed commit is accepted rather than refused; without the
`skip-worktree` flag a database file rewritten on every read shows as permanently modified and gets
committed by accident; without an author name A2MC stamps the wrong person, or nobody, onto every
log it writes. The two rows that do not apply to a given clone -- a memory bucket it does not carry,
a RAG index it does not ship -- report NA rather than FAIL, because a row that cannot apply is not a
row that failed.

Exit 0 = no FAIL. Exit 1 = at least one FAIL, i.e. this clone is not set up.

    python3 tools/check_clone_setup.py
    python3 tools/check_clone_setup.py --quiet     # only what is not done
"""
import argparse
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))

PASS, FAIL, NA = "PASS", "FAIL", "NA"
_MARK = {PASS: "✓", FAIL: "✗", NA: "–"}

FIX = "scripts/setup_clone.sh"


def _git(*args):
    try:
        return subprocess.run(["git", "-C", str(ROOT)] + list(args), stdout=subprocess.PIPE,
                              stderr=subprocess.DEVNULL, universal_newlines=True,
                              timeout=15).stdout
    except (OSError, subprocess.SubprocessError):
        return ""


def _own_hooks_dir(cur):
    """True when `core.hooksPath` names a hooks directory this repository TRACKS, other than
    `.githooks`: a project folder's own commit checks, set by that project's own onboarding.

    Those are commit checks this repository ships, so the clone is wired, and `setup_clone.sh`
    keeps such a path rather than resetting it (the same rule, in shell). A directory git does not
    track, one outside the repository, and one with no hook in it do not count.
    """
    if not cur or os.path.isabs(cur) or cur.split("/")[0] == "..":
        return False
    d = ROOT / cur
    if not d.is_dir():
        return False
    tracked = _git("ls-files", "--", cur).split()
    return any(Path(t).name in ("pre-commit", "commit-msg") for t in tracked)


def _hooks_row():
    cur = _git("config", "--get", "core.hooksPath").strip()
    if cur == ".githooks":
        return (PASS, "git hooks active", "core.hooksPath = .githooks")
    if _own_hooks_dir(cur.rstrip("/")):
        return (PASS, "git hooks active", "core.hooksPath = %s (this repository's own tracked hooks)" % cur)
    if not (ROOT / ".githooks").is_dir():
        return (NA, "git hooks active", "this clone ships no .githooks/")
    detail = ("unset — the repo's commit checks never fire, so a bad commit message is accepted"
              if not cur else "points at %r, not .githooks" % cur)
    return (FAIL, "git hooks active", detail + "  →  " + FIX)


def _skip_worktree_row():
    """The tracked chroma DBs are rewritten by every RAG READ, so without the flag they are
    permanently 'modified' and get swept into an unrelated commit."""
    tracked = [l for l in _git("ls-files", "rag/chroma_db").splitlines()
               if l.endswith("chroma.sqlite3")]
    if not tracked:
        return (NA, "chroma read-churn suppressed", "no tracked chroma.sqlite3 in this clone")
    # `git ls-files -v` tags each path: "S" = skip-worktree, "H" = cached/normal, and a
    # LOWERCASE tag means assume-unchanged, which is a different flag that does not suppress
    # this churn. So the test is `== "S"`, not a case test -- the first version of this row
    # used `.isupper()` and reported all four files unflagged while three carried "S".
    marks = {}
    for line in _git("ls-files", "-v", "rag/chroma_db").splitlines():
        if len(line) > 2 and line[1] == " ":
            marks[line[2:]] = line[0]
    missing = [p for p in tracked if marks.get(p, "H") != "S"]
    if not missing:
        return (PASS, "chroma read-churn suppressed", "%d file(s) skip-worktree" % len(tracked))
    return (FAIL, "chroma read-churn suppressed",
            "%d of %d unflagged; they will show as modified forever  →  %s"
            % (len(missing), len(tracked), FIX))


def _memory_row():
    bucket = ROOT / ".claude_memory"
    if not bucket.is_dir():
        return (NA, "memory bucket wired", "this clone carries no .claude_memory/ (normal for a public clone)")
    harness = Path(os.path.expanduser("~/.claude/projects/%s/memory" % str(ROOT).replace("/", "-")))
    if harness.is_symlink() and harness.resolve() == bucket.resolve():
        return (PASS, "memory bucket wired", "harness memory → .claude_memory/")
    return (FAIL, "memory bucket wired",
            "the agent's memories go to a personal directory and reach no one  →  " + FIX)


def _author_row():
    from whoami import resolve
    name, how, guess = resolve()
    if name is None:
        return (FAIL, "author name resolves",
                "unset — A2MC cannot stamp the logs it writes  →  "
                'python3 tools/whoami.py --set "Your Name"')
    if guess:
        return (FAIL, "author name resolves",
                "only a guess from %s (%r), which is often a handle rather than a name  →  "
                'python3 tools/whoami.py --set "Your Name"' % (how, name))
    return (PASS, "author name resolves", "%s (via %s)" % (name, how))


def _tmpdir_row():
    """Does a runtime temp write land somewhere legal on this machine?

    NERSC's hard rule is no writes outside $HOME, and the PreToolUse hook that enforces it can
    only read a command's TEXT: a path built at RUNTIME -- a tempfile constructor, a library's own
    scratch file, a plotting backend's cache -- carries no literal for it to match. Pointing the
    temp-directory variable at the repo's gitignored tmp/ fixes that by construction, in any
    language that honours it, which is why it is the real fix and the hook is the backstop.

    It lives in a shell profile, so GIT CANNOT CARRY IT: a fresh clone, or the same clone on
    another machine, silently has only the backstop, and nothing reported that until this row
    existed (2026-09-22, register item F1). Anything inside $HOME counts, not only the repo's own
    tmp/ -- the rule is about the quota boundary, not a particular directory.
    """
    # The rule is NERSC's, so the row applies only on a NERSC machine. Off NERSC it is NA, per
    # this file's own contract that a row which cannot apply reports NA rather than FAIL. Until
    # 2026-09-23 it FAILed on every laptop and workstation (TMPDIR is unset on Linux and under
    # /var/folders on macOS), so every non-NERSC user saw "THIS CLONE IS NOT FULLY SET UP" at
    # every session for a rule that does not bind them (audit 20260923b, finding F28).
    if not os.environ.get("NERSC_HOST"):
        return (NA, "TMPDIR inside $HOME",
                "not a NERSC machine (NERSC_HOST unset); the $HOME-only write rule is NERSC's")
    td = os.environ.get("TMPDIR", "")
    fix = ('point TMPDIR at %s/tmp in your shell profile, guarded on $SLURM_JOB_ID being unset '
           'so a batch job keeps node-local scratch' % ROOT)
    if not td:
        return (FAIL, "TMPDIR inside $HOME",
                "unset, so a runtime temp write lands outside $HOME and breaks the NERSC rule  -> " + fix)
    home = os.path.realpath(os.path.expanduser("~"))
    real = os.path.realpath(os.path.expandvars(td))
    if real == home or real.startswith(home + os.sep):
        inside_repo = real.startswith(os.path.realpath(str(ROOT)))
        return (PASS, "TMPDIR inside $HOME", "the repo's tmp/" if inside_repo else real)
    return (FAIL, "TMPDIR inside $HOME",
            "%s is outside $HOME, so a runtime temp write breaks the NERSC rule  -> %s" % (real, fix))


def clone_rows():
    """The per-clone wiring rows. Imported by check_stage_ready.py and the session-start hook so
    there is exactly one definition of what 'wired' means."""
    return [_hooks_row(), _skip_worktree_row(), _memory_row(), _author_row(),
            _tmpdir_row()]


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--quiet", "-q", action="store_true", help="only rows that are not done")
    args = ap.parse_args()

    rows = clone_rows()
    fails = [r for r in rows if r[0] == FAIL]

    print("\nPer-clone setup — %s\n" % ROOT)
    for status, label, detail in rows:
        if args.quiet and status != FAIL:
            continue
        print("  %s %-30s %s" % (_MARK[status], label, detail))

    if fails:
        print("\n  %d of %d not done. Most are fixed by one idempotent command:\n" % (len(fails), len(rows)))
        print("      %s\n" % FIX)
        print("  These live outside the repository tree or in the per-clone git index, so git")
        print("  cannot carry them and a fresh clone always starts without them.\n")
        return 1

    print("\n  This clone is set up.\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
