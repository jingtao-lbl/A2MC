#!/usr/bin/env python
"""Assert the STEM INVARIANT: every `phase_results/{stem}/` has a matching `logs/{stem}.md`.

WHY THIS EXISTS. The invariant is stated in four skills (`phase3-diagnosis`, `phase4-hypothesis`,
`calibration-log`, `calibration-discipline`) and until now enforced by none.
`check_offline_log_evidence.py` validates logs that EXIST and is structurally blind to a folder
whose log is missing -- it cannot report an absence it never enumerates.

MEASURED COST OF THE GAP. Two folders on one campaign sat orphaned for days
(`20260827d_phase1_exploration_...`, `20260831a_phase1_exploration_...`) and were found only by a
hand-rolled loop during a periodic review. An orphan is not cosmetic: the folder holds the figures
and scripts a log cites as its evidence, so an orphan is evidence with nothing pointing at it, and a
log written later under a DIFFERENT stem silently leaves it stranded.

THE SECOND FAILURE IT GUARDS, which is subtler and is what prompted this file. `PhaseLogger`'s
`_offline_letter` scans `logs/`, `phase_results/` AND the session's own stems for used same-day
letters. So a HAND-CREATED artifacts folder reserves a letter before its log exists, the logger then
takes the next one, and the two disagree. On 2026-09-05 that put a Phase-4 log at letter `c` and the
Phase-3 log that preceded it at `d`, so a lexical walk of the day's logs narrated the hypothesis
before the diagnosis.

**The fix for the CAUSE is NOT simply "use `topic_artifact_dir()`", and this file said that for a
day before being corrected.** `topic_stem` keys the letter on the DESCRIPTOR, so
`topic_artifact_dir(phase, X)` and `log_*(title=Y)` mint from X and Y and produce two DIFFERENT
stems whenever those strings differ -- which is the normal case, since one reads like a folder name
and the other like a title. The session that wrote this checker then reproduced the identical bug
an hour later WHILE USING `topic_artifact_dir()`, for exactly that reason.

So the contract is: **pass `topic_artifact_dir(phase, S)` and `log_*(title=S)` THE SAME STRING.**
`PhaseLogger` now warns when it mints a second stem for one phase/round/cycle/iteration on one day,
which is that mistake's signature; this checker catches the state that survives the warning.

**Directional, on purpose.** A folder without a log is an ERROR. A log without a folder is FINE --
an analysis-only phase legitimately produces no artifacts, and erroring on it would push people to
create empty folders to satisfy a checker, which is worse than the thing being checked.

Exit: 0 clean, 1 warnings only, 2 errors.

Run:  python tools/check_stem_pairing.py [--site use_cases/<Case>] [--all]

Author: Jing Tao with Claude on Perlmutter
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

STEM = re.compile(r"^(\d{8})([a-z]+)_phase(\d)_")


def check_site(site: Path) -> tuple[list[str], list[str]]:
    logs, res = site / "memory" / "logs", site / "memory" / "phase_results"
    errors, warns = [], []
    if not res.is_dir():
        # A PATH THAT IS NOT A CASE MUST NOT REPORT CLEAN. `--site` takes a path
        # (`use_cases/<Case>`), and passing a bare case name resolves to a directory that does not
        # exist, whose missing phase_results returned zero errors and printed "stem pairing clean".
        # Measured 2026-09-07: an entire session's stem-pairing reports were vacuous for exactly
        # that reason, and a real orphan was caught by PhaseLogger's own warning instead.
        # A case legitimately without phase_results yet is a WARN; a path that is not a directory
        # at all is an ERROR, because it is a typo rather than a state.
        if not site.is_dir():
            errors.append("NOT A CASE DIRECTORY: %s\n"
                          "  --site takes a PATH, e.g. --site use_cases/<Case>, not a bare case name"
                          % site)
        else:
            warns.append("%s has no memory/phase_results yet; nothing to pair" % site)
        return errors, warns
    have = {p.stem for p in logs.glob("*.md")} if logs.is_dir() else set()
    for d in sorted(res.iterdir()):
        if not d.is_dir() or not STEM.match(d.name):
            continue
        if d.name in have:
            continue
        # Name the near-miss when there is one: an orphan is almost always a stem that drifted by a
        # letter or a descriptor, and saying which log it probably belongs to turns a report into a
        # fix. Match on the date + phase, which the letter cannot change.
        m = STEM.match(d.name)
        kin = sorted(n for n in have
                     if (k := STEM.match(n)) and k.group(1) == m.group(1) and k.group(3) == m.group(3))
        hint = ("  nearest same-day, same-phase log(s): %s" % ", ".join(kin)) if kin else \
               "  no log for that date and phase exists at all"
        errors.append("ORPHAN artifacts folder has no matching log:\n"
                      "    %s\n%s" % (d.relative_to(site.parent.parent), hint))
    return errors, warns


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--site", default=None, help="a single use_cases/<Case> directory")
    ap.add_argument("--all", action="store_true", help="every case under use_cases/")
    a = ap.parse_args()

    repo = Path(__file__).resolve().parents[1]
    if a.site:
        sites = [Path(a.site)]
    else:
        sites = sorted(p for p in (repo / "use_cases").iterdir()
                       if p.is_dir() and (p / "memory" / "phase_results").is_dir())
    errors, warns = [], []
    for s in sites:
        e, w = check_site(s)
        errors += e
        warns += w

    for e in errors:
        print("ERROR  " + e)
    for w in warns:
        print("WARN   " + w)
    n = len(sites)
    if errors:
        print("\n%d orphaned artifacts folder(s) across %d case(s). The stem invariant is that every "
              "phase_results/{stem}/ has a logs/{stem}.md. Mint the folder with "
              "PhaseLogger.topic_artifact_dir(phase, S) and write the log with log_*(title=S) "
              "passing THE SAME STRING S -- the stem is derived from that string, so a folder "
              "named from a descriptor and a log titled differently will not pair, which is how "
              "most of these arise. Naming a folder by hand does it too."
              % (len(errors), n))
        return 2
    print("stem pairing clean: every phase_results/{stem}/ has its log, across %d case(s)." % n)
    return 0


if __name__ == "__main__":
    sys.exit(main())
