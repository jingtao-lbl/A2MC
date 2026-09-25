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


def main() -> int:
    if len(sys.argv) < 3:
        sys.stderr.write(__doc__)
        return 2
    dest, dropped = Path(sys.argv[1]), set(sys.argv[2:])
    r = prune_readme(dest, dropped)
    c = prune_catalog(dest, dropped)
    print("  de-registered %d README row(s) and %d catalog entry(ies)" % (r, c))
    return 0


if __name__ == "__main__":
    sys.exit(main())
