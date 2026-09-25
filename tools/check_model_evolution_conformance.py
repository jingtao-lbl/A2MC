#!/usr/bin/env python3
"""A model-evolution record matches the `model-evolution` skill's step-6 contract.

THE STREAM. `use_cases/{Model}_{Case}/memory/model_evolution/{stem}.md` holds what was changed in
a MODEL'S source and what it did to the calibration. It is the third hand-written stream, beside
dev logs (`tools/check_log_conformance.py`) and calibration logs
(`tools/check_calibration_log_conformance.py`), and until now it was the only one with no checker.

WHY IT IS A SEPARATE TOOL AND NOT A SUBTYPE. The two contracts overlap without coinciding. This
stream has its own stem and a `**Round:**` header, and has no `Version`/`Branch`; it shares
`Summary`/`Files Changed`/`Verification` with the dev contract and adds a V0-at-equality
requirement the dev contract has no concept of. Pointing the dev-log checker at a record produces
errors on the filename and header that no correct record can satisfy, so the two refuse each
other's streams by name rather than mis-checking them.

WHAT IT ENFORCES, and why each rule is the one worth having:

    M1  the stem `YYYYMMDDx_model_evolution_r{RR}_{descriptor}.md`, specified in `model-evolution`
        step 6. The date is PARSED, not merely counted: eight digits accepts `20260932`.
    M2  `**Date:**`, `**Author:**`, `**Round:**`. The round is load-bearing -- a record that does
        not say which round ran the change cannot be joined to `calibration_rounds.yaml`.
    M3  `## Skills and memory invoked` (ERROR).
    M4  that section names `model-evolution` (ERROR). Writing one of these MEANS invoking that
        skill, so a record that does not claim it was written without the source of truth open.
    M5  `## Cross-references` (WARN).
    M6  a commit-like identifier somewhere in the record (WARN). The round's `model_change_ledger`
        copies a commit out of here; a record with none forces the next reader back to the shell.
    M7  `## Summary`, M8 `## Files Changed`, M9 `## Verification` (ERROR). A model-source change is
        answerable for WHICH FILES it touched and whether the switch-off build still reproduces the
        baseline; a record without those is missing the only parts a reviewer can act on.
    M10 V0-at-equality evidence (ERROR). Not the verdict alone: the skill's pass criterion is a
        CONJUNCTION, because running the SAME binary twice also produces identical outputs, so
        "outputs identical" is indistinguishable from a specific, plausible harness error. Both
        arms' binary hashes must appear in `## Verification` and must DIFFER. The escape is an
        explicit `not applicable — <reason>`, for an activation or build-provenance record that
        authors no source; silence is not an escape.
    M11 a `!Jing Tao:` annotation named (WARN), per the model-evolution rule that every model-source
        edit carries one.

NON-RETROACTIVE, from `MODELEV_RULE_EFFECTIVE`. Records written before the contract existed are
exempt and reported as a note, so the backlog stays visible without blocking an edit to one. This
matches `check_skill_claims`, `check_log_placeholders` and `check_log_conformance`, each of which
date-scopes a rule it introduced after its stream already had files in it.

    python3 tools/check_model_evolution_conformance.py <record.md> [...]
    python3 tools/check_model_evolution_conformance.py --staged

EXIT 0 clean / 1 warn / 2 error.  Stdlib only.

Author: Jing Tao with Claude on Perlmutter
"""
from __future__ import annotations

import argparse
import datetime
import re
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent

# The contract takes effect on the day it was decided. Earlier records are exempt (PI, 2026-09-24:
# "no need to care about the existing files before the contract").
MODELEV_RULE_EFFECTIVE = "20260924"

_STEM = re.compile(r"^(?P<date>\d{8})(?P<letter>[a-z]{1,3})_model_evolution_r(?P<round>\d{2})_"
                   r"(?P<desc>.+)\.md$")
_LEADING_DATE = re.compile(r"^(\d{8})")

_REQUIRED_HEADER = ["Date", "Author", "Round"]
_CAPABILITY = "Skills and memory invoked"
_GOVERNING_SKILL = "model-evolution"

# PI, 2026-09-24. A model-source change is answerable for WHICH FILES it touched and whether the
# switch-off build still reproduces the baseline; a record without those two is missing the only
# parts a reviewer can act on. Required regardless of what the pre-rule records happened to carry.
_REQUIRED_SECTIONS = [("Summary", "M7"), ("Files Changed", "M8"), ("Verification", "M9")]

# The V0 declaration. Its value is either a result, or an explicit not-applicable WITH A REASON --
# an activation or build-provenance record authors no source and has no V0 to run.
_V0_LINE = re.compile(r"^\*\*V0[^*]*:\*\*\s*(?P<val>.+)$", re.M)
_V0_NA = re.compile(r"^\s*(not applicable|n/?a\b|does not apply)", re.I)
_JING = "!Jing Tao:"

# A backticked token that is ENTIRELY hex, 7-40 chars: a git object name. Deliberately strict about
# the whole token, so `a2mc-anchor-fe075014` (an anchor TAG, not a commit) does not satisfy it.
_COMMITISH = re.compile(r"`([0-9a-f]{7,40})`")


class Finding:
    __slots__ = ("path", "code", "level", "msg")

    def __init__(self, path, code, level, msg):
        self.path, self.code, self.level, self.msg = path, code, level, msg

    def __str__(self):
        tag = "ERROR" if self.level == "error" else "warn "
        return f"  {tag} [{self.code}] {self.path.name}: {self.msg}"


def wrong_stream(path: Path):
    """Is this path unambiguously in a stream this tool does NOT govern?

    Fires only on a POSITIVE match for another stream, never on an ambiguous path, so a draft or a
    test fixture stays checkable.
    """
    parts = path.parts
    if any(p.startswith("dev_logs") for p in parts):
        return ("a DEV LOG (memory/dev_logs*/) — use `tools/check_log_conformance.py`, whose "
                "contract is different (Version/Branch header, Summary/Files Changed/Verification)")
    if "use_cases" in parts and "logs" in parts:
        return ("a CALIBRATION log (use_cases/<Case>/memory/logs/) — use "
                "`tools/check_calibration_log_conformance.py`")
    if "ana_logs" in parts or "model_logs" in parts:
        return ("a RETIRED frozen stream (memory/ana_logs/ or memory/model_logs/) — no new record "
                "is written there; model-evolution records live under the case")
    return None


def _real_date(yyyymmdd: str) -> bool:
    try:
        datetime.datetime.strptime(yyyymmdd, "%Y%m%d")
        return True
    except ValueError:
        return False


def _section_body(text: str, heading: str) -> str | None:
    """The body under `## <heading>`, up to the next `## `. None if the heading is absent."""
    m = re.search(r"^##+\s*" + re.escape(heading) + r"\s*$", text, re.M)
    if not m:
        return None
    rest = text[m.end():]
    nxt = re.search(r"^##\s", rest, re.M)
    return rest[:nxt.start()] if nxt else rest


def check_file(path: Path) -> list:
    if not path.is_file():
        return [Finding(path, "M0", "error", "file not found")]

    other = wrong_stream(path)
    if other:
        return [Finding(path, "M00", "error", "wrong tool: this is %s" % other)]

    text = path.read_text(errors="replace")
    out: list = []

    # ---- exemption: a record written before the contract existed -------------------------------
    lead = _LEADING_DATE.match(path.name)
    if lead and _real_date(lead.group(1)) and lead.group(1) < MODELEV_RULE_EFFECTIVE:
        return []

    # ---- M1 filename ---------------------------------------------------------------------------
    m = _STEM.match(path.name)
    if not m:
        out.append(Finding(path, "M1", "error",
                           "filename is not YYYYMMDDx_model_evolution_r{RR}_{descriptor}.md "
                           "(`model-evolution` step 6); the round is TWO digits"))
    elif not _real_date(m.group("date")):
        out.append(Finding(path, "M1", "error",
                           f"stem date {m.group('date')} is not a real date"))

    # ---- M2 header -----------------------------------------------------------------------------
    missing = [k for k in _REQUIRED_HEADER
               if not re.search(r"^\*\*" + k + r":\*\*", text, re.M)]
    if missing:
        out.append(Finding(path, "M2", "error",
                           "header missing " + ", ".join(missing) +
                           " — **Round:** is what joins this record to calibration_rounds.yaml"))

    # ---- M3 / M4 the capability section --------------------------------------------------------
    body = _section_body(text, _CAPABILITY)
    if body is None:
        out.append(Finding(path, "M3", "error",
                           f"missing required section '## {_CAPABILITY}'"))
    elif _GOVERNING_SKILL not in body:
        out.append(Finding(path, "M4", "error",
                           f"'## {_CAPABILITY}' does not name `{_GOVERNING_SKILL}` — writing this "
                           "record means invoking that skill; claim it or explain in the Gaps line"))

    # ---- M7-M9 the sections a source change is answerable for -----------------------------------
    for sec, code in _REQUIRED_SECTIONS:
        if _section_body(text, sec) is None:
            out.append(Finding(path, code, "error", f"missing required section '## {sec}'"))

    # ---- M10 V0-at-equality evidence ------------------------------------------------------------
    # The skill's pass criterion is a CONJUNCTION: identical outputs ALONE is not evidence, because
    # running the same binary twice also produces identical outputs. Both arms' hashes must be
    # recorded and must DIFFER. So the record has to carry two distinct ones, not just the verdict.
    verif = _section_body(text, "Verification") or ""
    m_v0 = _V0_LINE.search(text)
    if not m_v0:
        out.append(Finding(path, "M10", "error",
                           "no V0-at-equality statement — add a `**V0-at-equality:**` line to "
                           "'## Verification', either the result (with BOTH arms' binary hashes) "
                           "or `not applicable — <reason>`"))
    else:
        val = m_v0.group("val").strip()
        na = _V0_NA.match(val)
        if na:
            reason = val[na.end():].strip(" -—:")
            if len(reason) < 20:
                out.append(Finding(path, "M10", "error",
                                   "V0 declared not applicable with no reason — say why (e.g. "
                                   "'activation record, no source authored and no binary built')"))
        else:
            hashes = set(_COMMITISH.findall(verif))
            if len(hashes) < 2:
                out.append(Finding(path, "M10", "error",
                                   f"V0 claims a result but '## Verification' carries "
                                   f"{len(hashes)} distinct binary hash(es), not 2 — running the "
                                   "SAME binary twice also produces identical outputs, so record "
                                   "both arms and show they differ (`model-evolution` step 5)"))

    # ---- M5 / M6 / M11 warnings -----------------------------------------------------------------
    if _JING not in text:
        out.append(Finding(path, "M11", "warn",
                           f"no `{_JING}` annotation named — every model-source edit carries one "
                           "(CLAUDE.md model-evolution rule (d))"))

    if _section_body(text, "Cross-references") is None:
        out.append(Finding(path, "M5", "warn", "no '## Cross-references' section"))

    if not _COMMITISH.search(text):
        out.append(Finding(path, "M6", "warn",
                           "no commit-like identifier (a backticked 7-40 char hex) — the round's "
                           "`model_change_ledger` copies one out of this record"))

    return out


def _staged_records() -> list:
    out = subprocess.run(["git", "diff", "--cached", "--name-only", "--diff-filter=ACMR"],
                         cwd=REPO, stdout=subprocess.PIPE, universal_newlines=True).stdout.split()
    return [REPO / rel for rel in out
            if rel.endswith(".md") and "/memory/model_evolution/" in rel
            and not rel.endswith("README.md")]


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("paths", nargs="*", type=Path, help="record files to check")
    ap.add_argument("--staged", action="store_true",
                    help="check staged records (what the pre-commit hook runs)")
    args = ap.parse_args()

    files = [p for p in args.paths if not p.is_dir()]
    for d in [p for p in args.paths if p.is_dir()]:
        files += [p for p in sorted(d.glob("*.md")) if p.name != "README.md"]
    if args.staged:
        files += _staged_records()
    files = list(dict.fromkeys(files))
    if not files:
        print("no model-evolution records to check")
        return 0

    findings, exempt = [], 0
    for f in files:
        fs = check_file(f)
        lead = _LEADING_DATE.match(f.name)
        if (not fs and lead and _real_date(lead.group(1))
                and lead.group(1) < MODELEV_RULE_EFFECTIVE):
            exempt += 1
        findings.extend(fs)

    errors = [x for x in findings if x.level == "error"]
    warns = [x for x in findings if x.level == "warn"]

    print(f"model-evolution conformance — {len(files)} record(s) checked")
    for x in findings:
        print(x)
    if exempt:
        print(f"  [note] {exempt} record(s) predate the rule ({MODELEV_RULE_EFFECTIVE}) and are "
              "exempt. Reported so the backlog stays visible.")
    if not findings:
        print("\n✔ every record matches the `model-evolution` step-6 contract")
        return 0
    print(f"\n{len(errors)} error(s), {len(warns)} warning(s)")
    if errors:
        print("Fix per .claude/skills/model-evolution/SKILL.md step 6 — and RE-READ it rather "
              "than recalling it; it changes.")
    return 2 if errors else 1


if __name__ == "__main__":
    sys.exit(main())
