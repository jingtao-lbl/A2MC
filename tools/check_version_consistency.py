#!/usr/bin/env python3
"""Guard the A2MC version number against collision and drift.

Catches the failure of 2026-07-30: two branches independently bumped to the SAME version
(v2.209). Each branch was internally consistent, so nothing complained — and because both
edited `CLAUDE.md` to the identical string, `git merge-tree` reported the merge CLEAN. The
collision only becomes visible in the merged changelog, which is exactly where this looks.

Checks (ERROR, exit 1):
  1. the version in CLAUDE.md's `**Status:** Implementation Complete (vX.YZ)` header appears
     EXACTLY ONCE as a `- **vX.YZ**` entry in memory/a2mc_development_history.md
  2. no version has two changelog entries (the merge-collision signature)
  3. README.md's `**Version:** X.YZ` line agrees with that header

Check 3 exists because it had already failed. On 2026-09-03 the README said 2.317 while
CLAUDE.md said 2.355 -- 38 versions of drift, in the file a new reader sees first, because the
README carried its own COPY of a number with a single authority and nothing compared the two.
Fixing the number without adding the comparison would have guaranteed a repeat.
"""
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CLAUDE_MD = ROOT / "CLAUDE.md"
CHANGELOG = ROOT / "memory" / "a2mc_development_history.md"
README_MD = ROOT / "README.md"


def main():
    if not CLAUDE_MD.exists() or not CHANGELOG.exists():
        print("check_version_consistency: files absent (skip)")
        return 0

    m = re.search(r"\*\*Status:\*\*.*?\((v[\d.]+)\)", CLAUDE_MD.read_text(encoding="utf-8"))
    if not m:
        print("check_version_consistency: no version header in CLAUDE.md (skip)")
        return 0
    header = m.group(1)

    entries = re.findall(r"^- \*\*(v[\d.]+)\*\*", CHANGELOG.read_text(encoding="utf-8"), re.M)
    errors = []

    # Severity split: a duplicate on the CURRENT version is a live collision and blocks;
    # a historical duplicate is a record of one that already happened (v2.80 has 3 entries
    # from April 2026) and only warns — the changelog is a record, not something to rewrite.
    warnings = []
    for v in sorted({v for v in entries if entries.count(v) > 1}):
        msg = (f"{v} has {entries.count(v)} changelog entries — two changes claimed the same "
               f"version (the cross-branch collision signature)")
        if v == header:
            errors.append(msg + ". Renumber the later one BEFORE committing.")
        else:
            warnings.append(msg + " (historical; left as-is)")

    if header not in entries:
        errors.append(f"CLAUDE.md header says {header} but no `- **{header}**` entry exists in "
                      f"memory/a2mc_development_history.md — add the changelog entry or fix the header.")

    # README.md restates the version for a reader who never opens CLAUDE.md. That restatement is
    # a derived fact, so it is checked rather than trusted. Absent line = skip, not fail: the
    # README is not required to carry one, only to be right if it does.
    if README_MD.exists():
        rm = re.search(r"^\*\*Version:\*\*\s*v?([\d.]+)", README_MD.read_text(encoding="utf-8"), re.M)
        if rm:
            readme_v = "v" + rm.group(1).rstrip(".")
            if readme_v != header:
                errors.append(f"README.md says Version {readme_v} but CLAUDE.md's header says "
                              f"{header} — CLAUDE.md is the authority; update the README line.")

    for w in warnings:
        print(f"  [warn] {w}")
    if errors:
        print(f"\u2718 {len(errors)} version problem(s):")
        for e in errors:
            print(f"  - {e}")
        return 1
    print(f"\u2714 version consistent: CLAUDE.md {header} has exactly one changelog entry "
          f"({len(entries)} versions logged)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
