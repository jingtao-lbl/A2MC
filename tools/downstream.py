#!/usr/bin/env python3
"""Is this tree a downstream copy of A2MC, or the development repo?

visibility: public

ONE definition, imported by every checker that needs it. Two copies of this predicate would drift,
and the drift would be invisible: each checker would keep working, just disagreeing about which
tree it is in.

STRICT IS THE DEFAULT. Leniency is granted only to a tree a wrap or a sync has POSITIVELY MARKED.
Inferring it from an absence -- no dev logs, no memory bucket -- softens every tree that merely
looks like a copy, including a partial clone and a worktree checked out without those paths.
"""
from pathlib import Path

MARKER = ".a2mc-downstream"


def state(root: Path):
    """(is_downstream, complaint).

    A tree carrying the marker AND a development tree's own directories is a mistake rather than a
    mode -- nothing copies the marker upstream, so the two together mean it arrived by hand. That
    checks STRICT and says so.
    """
    marked = (root / MARKER).is_file()
    if marked and any(root.glob("memory/dev_logs*")):
        return False, (
            "MARKER-CONTRADICTION: this tree has `%s` AND `memory/dev_logs*/`, so it claims to be "
            "a copy and a development repo at once. Checking STRICT. Delete `%s` here — a wrap or "
            "a sync writes it into a DESTINATION and nothing copies it upstream." % (MARKER, MARKER))
    return marked, None


def is_downstream(root: Path) -> bool:
    return state(root)[0]
