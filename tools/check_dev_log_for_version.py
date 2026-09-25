#!/usr/bin/env python
"""Does the version in CLAUDE.md have a dev log that CLAIMS it?

`check_version_consistency.py` pairs `CLAUDE.md`'s version with the **changelog**. Nothing paired it
with a **log file**, so "bumped the version, wrote no dev log" passed silently. Measured 2026-08-21:
three framework changes shipped that way in one session — and two of them *after* the gap had been
diagnosed and written down, because the diagnosis lived in a `## Next` section rather than at the
moment of commit. Full account: `memory/dev_logs_adapterkit/reflection/20260821i_*`.

What this checks, and only this: the version string in `CLAUDE.md` appears as the `**Version:**`
header of at least one log under `memory/dev_logs*/` (including `reflection/`) or
`memory/model_logs/`. It deliberately does NOT judge the log's content — `check_log_conformance.py`
enforces shape, and a gate demanding substance manufactures filler. A thin log is still a file a
reader can see is thin; a missing log is invisible, which is the asymmetry this closes.

What it CANNOT catch, stated so the coverage is not overread:
  * a change that ships with no version bump at all (nothing triggers) — the third instance above
  * a stub log with the right header
  * two versions bumped inside one commit: only CLAUDE.md's current version is examined

Usage:
    python tools/check_dev_log_for_version.py            # 0 ok · 1 no log claims the version
    python tools/check_dev_log_for_version.py --version v2.264

Author: Jing Tao with Claude
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent

# `**Version:** v2.264` — anchored, and tolerant of trailing whitespace only. A header that says
# `v2.264 + v2.263` or `(no bump — a retrospective)` deliberately does NOT match: a log claiming a
# version must say exactly which one, or the pairing is unverifiable.
_VERSION_HEADER = re.compile(r"^\*\*Version:\*\*\s*(v\d+\.\d+)\s*$", re.M)
# A single arc can legitimately span two versions (the mitigation, then the test that proves it).
# `**Also covers:** v2.263, v2.262` lets one log claim them WITHOUT weakening the exact-match rule:
# it is an extra line someone has to type on purpose, which is the difference between a deliberate
# act and the drift this check exists to stop.
_ALSO_COVERS = re.compile(r"^\*\*Also covers:\*\*\s*(.+)$", re.M)
_CLAUDE_VERSION = re.compile(r"^\*\*Status:\*\*.*?\((v\d+\.\d+)\)", re.M)


def claude_md_version(repo: Path = REPO) -> str | None:
    """The version CLAUDE.md's Status header declares, or None."""
    p = repo / "CLAUDE.md"
    if not p.is_file():
        return None
    m = _CLAUDE_VERSION.search(p.read_text(errors="ignore"))
    return m.group(1) if m else None


def log_dirs(repo: Path = REPO) -> list[Path]:
    """Every directory whose logs may claim a version, including reflection/ subdirs.

    `glob` rather than a hardcoded list: log dirs are per-branch (`dev_logs_adapterkit`,
    `dev_logs_adapterkitats`, …) and a new feature branch must not silently fall outside the check.
    """
    out = [d for d in repo.glob("memory/dev_logs*") if d.is_dir()]
    out += [d for d in repo.glob("memory/dev_logs*/reflection") if d.is_dir()]
    ml = repo / "memory" / "model_logs"
    if ml.is_dir():
        out.append(ml)
    return out


def logs_claiming(version: str, repo: Path = REPO) -> list[Path]:
    """Every log file whose `**Version:**` header is exactly `version`."""
    hits = []
    for d in log_dirs(repo):
        for p in sorted(d.glob("*.md")):
            try:
                txt = p.read_text(errors="ignore")
            except OSError:
                continue
            claimed = set(_VERSION_HEADER.findall(txt))
            for extra in _ALSO_COVERS.findall(txt):
                claimed.update(re.findall(r"v\d+\.\d+", extra))
            if version in claimed:
                hits.append(p)
    return hits


def main() -> int:
    # A downstream copy has no CLAUDE.md version header: that file is the PROJECT's there, and the
    # development history this check enforces does not travel. Skip rather than error -- failing on
    # an absence that is by design blocks a commit for something the user did not cause.
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from downstream import is_downstream
    if is_downstream(REPO):
        print("check_dev_log_for_version: downstream copy (skip) — the version header is the "
              "project's here, and dev logs do not travel")
        return 0

    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--version", help="check this version instead of CLAUDE.md's")
    ap.add_argument("--quiet", action="store_true")
    args = ap.parse_args()

    version = args.version or claude_md_version()
    if not version:
        print("ERROR: could not read a version from CLAUDE.md's **Status:** header", file=sys.stderr)
        return 1

    hits = logs_claiming(version)
    if hits:
        if not args.quiet:
            print(f"✔ {version} is claimed by {len(hits)} log(s):")
            for p in hits:
                print(f"    {p.relative_to(REPO)}")
        return 0

    print(f"✘ {version} (CLAUDE.md) is claimed by NO dev log.", file=sys.stderr)
    print("", file=sys.stderr)
    print("  A changelog row is not a dev log. Pointing a new version's `Details:` at an older log", file=sys.stderr)
    print("  is the specific move this check exists to stop — it looks like cross-referencing and", file=sys.stderr)
    print("  leaves the version undocumented.", file=sys.stderr)
    print("", file=sys.stderr)
    print("  Write the log FIRST, then bump. Give it a header line reading exactly:", file=sys.stderr)
    print(f"      **Version:** {version}", file=sys.stderr)
    print("  in one of:", file=sys.stderr)
    for d in log_dirs():
        print(f"      {d.relative_to(REPO)}/", file=sys.stderr)
    print("", file=sys.stderr)
    print("  If one log legitimately covers several versions, add a header line", file=sys.stderr)
    print(f"      **Also covers:** {version}", file=sys.stderr)
    print("  to the log that owns the arc — deliberate, and visible to a reader.", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
