#!/usr/bin/env python3
"""Remove dropped skills from the destination's registries.

visibility: public

Removing a skill without removing its registry rows is an add-only asymmetry: the destination
would ship registries advertising skills it does not have, and its own parity check would fail on
day one for something the user did not cause. De-registration is symmetric with the drop, and that
is why it happens here rather than being left to whoever notices.

Usage:  _wrap_deregister.py <dest> <skill> [<skill> ...]
"""
import re
import sys
from pathlib import Path


def prune_readme(dest: Path, dropped: set) -> int:
    f = dest / ".claude" / "skills" / "README.md"
    if not f.is_file():
        return 0
    keep, removed = [], 0
    for line in f.read_text().splitlines(keepends=True):
        # a table row naming a dropped skill, either as `name` or as [name](name/SKILL.md)
        if line.lstrip().startswith("|") and any(
                re.search(r"[\[`]%s[\]`]" % re.escape(d), line) for d in dropped):
            removed += 1
            continue
        keep.append(line)
    if removed:
        f.write_text("".join(keep))
    return removed


def prune_catalog(dest: Path, dropped: set) -> int:
    f = dest / "docs" / "a2mc_reference" / "skills_catalog.md"
    if not f.is_file():
        return 0
    lines = f.read_text().splitlines(keepends=True)
    out, i, removed = [], 0, 0
    while i < len(lines):
        m = re.match(r"^### `([a-z0-9-]+)`", lines[i])
        if m and m.group(1) in dropped:
            i += 1
            while i < len(lines) and not lines[i].startswith("### "):
                i += 1
            removed += 1
            continue
        out.append(lines[i])
        i += 1
    if removed:
        f.write_text("".join(out))
    return removed


def prune_root_docs(dest: Path, dropped: set) -> int:
    """A calibrating project's root CLAUDE.md and AGENTS.md carry A2MC's skill tables below the
    marker line. Remove the rows whose FIRST cell is a dropped skill -- first cell only, because
    another skill's row may mention one in passing ("routes to offline-testing-workflow") -- and only
    below the marker, so the project's banner is never touched."""
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from _wrap_root_docs import MARKER
    first_cell = re.compile(r"^\|\s*`(%s)`\s*\|" % "|".join(re.escape(d) for d in dropped))
    removed = 0
    for name in ("CLAUDE.md", "AGENTS.md"):
        f = dest / name
        if not f.is_file():
            continue
        text = f.read_text()
        if MARKER not in text:
            continue
        banner, below = text.split(MARKER, 1)
        kept = []
        for line in below.splitlines(keepends=True):
            if first_cell.match(line):
                removed += 1
                continue
            kept.append(line)
        f.write_text(banner + MARKER + "".join(kept))
    return removed


def main() -> int:
    if len(sys.argv) < 3:
        sys.stderr.write(__doc__)
        return 2
    dest, dropped = Path(sys.argv[1]), set(sys.argv[2:])
    r = prune_readme(dest, dropped)
    c = prune_catalog(dest, dropped)
    d = prune_root_docs(dest, dropped)
    print("  de-registered %d README row(s), %d catalog entry(ies) and %d root-document row(s)"
          % (r, c, d))
    return 0


if __name__ == "__main__":
    sys.exit(main())
