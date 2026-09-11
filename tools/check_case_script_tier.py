#!/usr/bin/env python3
"""A script reused across phases belongs in the case's TEMPLATE tier, not copied between stem folders.

THE FAILURE THIS EXISTS FOR, measured before the rule was written. One site's `phase_results/` held
**7 script names duplicated across stem folders, and all 7 were byte-identical** -- every one a Phase-5
analysis script copied verbatim into its Phase-6 folder. Nothing was wrong with any individual copy;
there was simply nowhere for a reusable script to live, so each phase that needed one duplicated the
last phase's. Two copies of a script drift the moment one is edited, and the evidence gate checks that
a script EXISTS, never that it is the same script.

THE THREE TIERS (PI, 2026-08-22):

    use_cases/{Model}_{Case}/scripts/          the canonical script TEMPLATE   <- seeded at onboarding
    .../memory/phase_results/{stem}/           the canonical script + its figure, caption, data
    tools/ , phases/phase3_diagnosis/          the generalized site-agnostic utility

A phase copies the template into its own `{stem}/` and ADAPTS it there. A script's SECOND use is the
trigger to add it to `scripts/`. This does NOT conflict with "one canonical script per figure, never
two copies": the canonical *script* stays with its figures, the canonical script *TEMPLATE* stays in
`scripts/`, and they are different artifacts.

So: two `{stem}/` folders holding the same script name, with nothing of that name in the case's
`scripts/`, means the template tier was skipped. That is decidable, which is what makes this a check.

    python3 tools/check_case_script_tier.py [--site <Model>_<Case>] [--staged]

EXIT 0 clean / 1 WARN. WARN not ERROR: whether two same-named scripts are genuinely the same tool is
a judgement, and gating a commit on a judgement is how gates get bypassed wholesale. What it removes
is the ability to duplicate SILENTLY.

Author: Jing Tao with Claude
"""
from __future__ import annotations

import argparse
import collections
import hashlib
import re
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent

#: EFFECTIVE DATE. The 7 duplicate groups that motivated this rule all predate it (2026-07-17), and a
#: checker that is permanently red is a checker nobody reads -- the same reasoning as checks (12), (13)
#: and (14). A group is judged by its NEWEST member: duplicating an old script into a new phase today
#: is a new violation, while two old copies sitting untouched are not. The exempt count is printed so
#: the backlog stays a visible decision rather than a disappeared one.
TIER_RULE_EFFECTIVE = "20260822"

STEM_DATE = re.compile(r"(\d{8})")


def tracked_files() -> list[str]:
    """Enumerate from the git index, never a filesystem walk.

    Two reasons, both load-bearing here. A recursive walk of a shared filesystem is prohibited on this
    machine; and a walk measures the DISK while the rule is about what the branch carries
    ([[feedback_a_gate_must_measure_the_branch_not_the_disk]]). `--others --exclude-standard` includes
    files written this session that are not yet committed, which are exactly the ones worth catching.
    """
    out = subprocess.run(["git", "ls-files", "--cached", "--others", "--exclude-standard",
                          "--", "use_cases"],
                         cwd=REPO, capture_output=True, text=True)
    return out.stdout.split() if out.returncode == 0 else []


def scan(site_filter=None):
    """-> (findings, n_exempt). A finding is one duplicated script name with no template.

    `site_filter` is None (every case) or a collection of case directory names. It became a
    COLLECTION on 2026-09-08 so the pre-commit hook can scope one invocation to the cases whose
    files are actually staged: run repo-wide, this check prints other cases' stem names into every
    commit, and in a shared clone those are stems from campaigns the committer is not working on.
    Measured that day: a Phase-5 experiment in one case was named with a NUMBERING CONVENTION
    belonging to another, whose stems this warning had put in front of the author on roughly a
    dozen consecutive commits.
    """
    if isinstance(site_filter, str):
        site_filter = {site_filter}
    elif site_filter is not None:
        site_filter = set(site_filter)
    files = tracked_files()

    # site -> set of template names, and site -> {script name: [(stem, path)]}
    templates: dict[str, set[str]] = collections.defaultdict(set)
    instances: dict[str, dict[str, list[tuple[str, str]]]] = collections.defaultdict(
        lambda: collections.defaultdict(list))

    for rel in files:
        parts = rel.split("/")
        if len(parts) < 3 or parts[0] != "use_cases" or not rel.endswith(".py"):
            continue
        site = parts[1]
        if site_filter is not None and site not in site_filter:
            continue
        if parts[2] == "scripts":
            templates[site].add(parts[-1])
        elif "memory/phase_results/" in rel:
            i = parts.index("phase_results")
            if i + 2 < len(parts):                      # phase_results/<stem>/<file>.py
                instances[site][parts[-1]].append((parts[i + 1], rel))

    findings, exempt = [], 0
    for site, byname in instances.items():
        for name, hits in byname.items():
            if len(hits) < 2:
                continue
            if name in templates.get(site, set()):
                continue                                 # the template tier is being used
            newest = max((STEM_DATE.match(s).group(1) if STEM_DATE.match(s) else "00000000")
                         for s, _ in hits)
            if newest < TIER_RULE_EFFECTIVE:
                exempt += 1
                continue
            digests = {hashlib.md5((REPO / p).read_bytes()).hexdigest()
                       for _, p in hits if (REPO / p).is_file()}
            findings.append(dict(site=site, name=name, hits=sorted(hits),
                                 identical=len(digests) == 1))
    return findings, exempt


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--site", action="append", default=None, metavar="CASE",
                    help="restrict to this use case; repeatable. Omit to scan every case.")
    args = ap.parse_args(argv)

    findings, exempt = scan(args.site)

    if findings:
        scope = "" if not args.site else f" in {', '.join(sorted(args.site))}"
        print(f"\n  [warn] check_case_script_tier: {len(findings)} script(s) duplicated across "
              f"phase_results/ folders with no template in the case's scripts/{scope}")
        for f in findings:
            same = "BYTE-IDENTICAL" if f["identical"] else "diverged copies"
            print(f"    {f['site']}/{f['name']}  ({len(f['hits'])} copies, {same})")
            for stem, _ in f["hits"][:4]:
                print(f"        {stem[:66]}")
            print(f"      -> add it to use_cases/{f['site']}/scripts/ as the template, then copy it "
                  f"back\n         into each phase's folder and adapt it there.")
        print("\n    A script's SECOND use is the trigger to template it. The canonical script stays")
        print("    with its figures; the canonical script TEMPLATE stays in the case's scripts/.")
        if exempt:
            print(f"    ({exempt} group(s) predate {TIER_RULE_EFFECTIVE} and are exempt.)")
        return 1

    if exempt:
        print(f"  [note] {exempt} duplicated-script group(s) predate the rule "
              f"({TIER_RULE_EFFECTIVE}) and are exempt.")
    scope = "every case" if not args.site else ", ".join(sorted(args.site))
    print(f"✔ check_case_script_tier: no untemplated duplicate scripts across phase_results/ "
          f"folders ({scope})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
