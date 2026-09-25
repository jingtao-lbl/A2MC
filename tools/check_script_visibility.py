#!/usr/bin/env python3
"""A new test or tool must declare whether it SHIPS, the way a skill does.

visibility: public

PUBLIC, and the reason is a real constraint on this whole mechanism. This tool is wired into
`.githooks/pre-commit`, which SHIPS and invokes its tools with no existence guard, so a tool marked
private would be excluded by the legs and then called by the hook in a tree that does not have it.
**So `visibility: private` is usable today for a TEST, and for a tool only if the hook does not
invoke it.** Making a hook-invoked tool private needs the hook to skip a missing tool first; that
is recorded in `TODO.md` rather than done here.

WHY. `tests/` and `tools/` are whole INCLUDE paths on both sync legs, so a new file ships the
moment it is committed and nothing asks whether it should. A skill answers this in its frontmatter
and the legs DERIVE the exclusion from it; a script had no equivalent, so the decision was made by
default and never recorded. This asks for the same one-line declaration:

    # visibility: public     # ships downstream with the framework (the usual answer)
    # visibility: private    # development-only; the legs exclude it by basename

It is accepted anywhere in the file's header region, in a comment or inside the module docstring,
so it reads naturally in either style. `public` is not a no-op: it is the author stating that a
downstream reader can run this, which is the decision the default was silently making.

NON-RETROACTIVE. Only files git records as ADDED on or after the effective date are in scope, so
the existing tools and tests are not flagged. A file with no add date is new or uncommitted, i.e.
being written now, so it IS in scope. Same mechanism as `check_memory_bucket`'s provenance rule.

WHAT THIS DOES NOT DO. It does not decide whether the existing development-discipline tooling
should ship; that is a standing decision recorded in `TODO.md`. It only stops a NEW script from
joining either side of it silently.

Usage:
    python3 tools/check_script_visibility.py [--staged] [paths...]

Exit: 0 clean, 1 a file in scope carries no declaration.

Author: Jing Tao with Claude on Perlmutter.
"""
from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(Path(__file__).resolve().parent))

# Files added on or after this date must declare. Deliberately AFTER the day the rule was written,
# because the instruction was "no need to do that for our existing scripts, but for future scripts"
# — and everything committed on the day of the decision is an existing script by that reading.
EFFECTIVE = "2026-09-25"

# The directories whose contents ship whole, so a file landing in one is a publishing decision.
WATCHED = ("tools/", "tests/", "scripts/")   # scripts/ ships wholesale too
SUFFIXES = (".py", ".sh")

# Header region only: a `visibility:` mentioned deep in a file is prose about something else.
HEADER_LINES = 40
_DECL = re.compile(r"^[\s#]*visibility:\s*(public|private)\s*$", re.M)

# Files that are not a test or a tool in the sense this rule is about.
_EXEMPT_NAMES = {"__init__.py", "conftest.py"}


def declared(path: Path) -> str:
    """'public', 'private', or '' when the header carries no declaration."""
    try:
        head = "\n".join(path.read_text(errors="replace").splitlines()[:HEADER_LINES])
    except OSError:
        return ""
    m = _DECL.search(head)
    return m.group(1) if m else ""


def added_date(path: Path) -> str:
    """YYYY-MM-DD this file was first committed; '' if untracked/new or git is unavailable."""
    try:
        out = subprocess.run(
            ["git", "log", "--diff-filter=A", "--format=%ad", "--date=short", "--", str(path)],
            cwd=ROOT, capture_output=True, text=True, timeout=10,
        ).stdout.strip().splitlines()
        return out[-1] if out else ""      # last line = the ORIGINAL add, not a later re-add
    except (OSError, subprocess.SubprocessError):
        return ""


def in_scope(rel: str) -> bool:
    name = Path(rel).name
    return (rel.startswith(WATCHED) and rel.endswith(SUFFIXES) and name not in _EXEMPT_NAMES)


def staged_paths() -> list:
    try:
        out = subprocess.run(
            ["git", "diff", "--cached", "--name-only", "--diff-filter=ACM"],
            cwd=ROOT, capture_output=True, text=True, timeout=10).stdout
    except (OSError, subprocess.SubprocessError):
        return []
    return [p for p in out.split() if in_scope(p)]


def check(rels: list):
    """(problems, checked, exempt). `checked` counts files the rule actually applied to."""
    problems, checked, exempt = [], 0, 0
    for rel in rels:
        path = ROOT / rel
        if not path.is_file():
            continue
        # A file git has never recorded is being written now, so it is in scope.
        when = added_date(path)
        if when and when < EFFECTIVE:
            exempt += 1
            continue
        checked += 1
        if not declared(path):
            problems.append(rel)
    return problems, checked, exempt


def main() -> int:
    # A downstream copy adds every tool and test in one commit, so all of them read as new.
    # The rule is about an AUTHOR deciding whether their new script ships; a copy authored
    # nothing. Skip rather than demanding a declaration on 300 files nobody wrote here.
    from downstream import is_downstream
    if is_downstream(ROOT):
        print("check_script_visibility: downstream copy (skip) — nothing here was authored "
              "in this tree")
        return 0

    args = [a for a in sys.argv[1:] if a != "--staged"]
    rels = ([str(Path(a).resolve().relative_to(ROOT)) for a in args] if args
            else staged_paths() if "--staged" in sys.argv[1:] else [])
    if not args and "--staged" not in sys.argv[1:]:
        rels = [p for p in subprocess.run(
            ["git", "ls-files", "tools", "tests"], cwd=ROOT,
            capture_output=True, text=True).stdout.split() if in_scope(p)]

    rels = [r for r in rels if in_scope(r)]
    problems, checked, exempt = check(rels)

    if not problems:
        # Say what was CHECKED, not what was looked at. A rule that is exempting everything
        # should read as exempting everything, not as passing.
        print(f"✔ check_script_visibility: {checked} file(s) declare `visibility:`; "
              f"{exempt} predate the rule ({EFFECTIVE}) and are exempt")
        return 0

    print(f"✘ {len(problems)} new file(s) do not declare whether they ship:")
    for rel in problems:
        print(f"  - {rel}")
    print()
    print("  `tests/` and `tools/` are whole INCLUDE paths on both sync legs, so this file ships")
    print("  the moment it is committed. Say so on purpose. Add ONE line to the header:")
    print()
    print("      # visibility: public      # a downstream reader can run this")
    print("      # visibility: private     # development-only; the legs exclude it by basename")
    print()
    print("  Which one? `public` unless its SUBJECT cannot exist in a released copy — a")
    print("  development log, an agent memory bucket, a maintainer's TODO. Note a tool the")
    print("  shipped pre-commit invokes must be `public`, or the hook calls a missing file.")
    return 1


if __name__ == "__main__":
    sys.exit(main())
