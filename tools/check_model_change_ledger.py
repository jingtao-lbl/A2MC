#!/usr/bin/env python3
"""A `model_change_ledger` row still matches the record it was copied from.

THE DERIVED FACT. `summarize-calibration-round` copies a model change's commit, branch, kind and
V0 result out of a `use_cases/{Model}_{Case}/memory/model_evolution/` record into that case's
`config/calibration_rounds.yaml`. Both `summarize-calibration-round` and
`compare-calibration-rounds` then read the COPY at every round close, so a row that has drifted
from its source is consumed rather than merely stored. Two artifacts disagreeing is one missing
derivation.

`check_model_evolution_conformance.py` checks the record; this checks the LINK, in both
directions, which is the same shape the repo runs between a memory and its log -- and for the same
reason: neither half alone catches a pointer that resolves to a real file containing none of the
content it is cited for.

SCOPE, deliberately narrow. Only a `model_log` pointing into a case's own `memory/model_evolution/`
is checked. An entry with no `model_log`, or one pointing into the RETIRED repo-root
`memory/model_logs/` archive, is SKIPPED: those record changes made before the stream moved under
the case in 2026-08-24, and this tool is not for chasing them.

    G1  the pointer resolves to a FILE (ERROR). Not `exists()` -- a bare `memory/model_evolution/`
        is a directory, which exists, so an `exists()` check reports the broken pointers clean.
        That would put the failure this tool exists to catch inside the tool itself.
    G2  the record carries the entry's `commit` (ERROR). This is the drift check.
    G3  every record under the case is named by at least one entry (WARN, the reverse direction).

A `model_log` is resolved CASE-relative first, then repo-relative, so both spellings in use today
work and the retired archive at the repo root remains expressible.

NO DATE EXEMPTION, unlike the log checkers. A ledger is read at every round close, so a stale row
is acted on rather than filed; the alternative to an exemption is repairing the row.

    python3 tools/check_model_change_ledger.py [<case_dir> ...]   # default: every use_cases/*/
    python3 tools/check_model_change_ledger.py --staged

EXIT 0 clean / 1 warn / 2 error.  Needs pyyaml (use the a2mc_env interpreter).

Author: Jing Tao with Claude on Perlmutter
"""
from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path

import yaml

REPO = Path(__file__).resolve().parent.parent

RETIRED = "memory/model_logs"
CASE_STREAM = "memory/model_evolution"

# NON-RETROACTIVE (PI, 2026-09-24), keyed on the RECORD's stem date exactly as
# check_model_evolution_conformance.py is. A row copied before the link was checked recorded
# whatever it recorded, and a disagreement there is history rather than a defect anyone is about
# to act on; blocking a commit on one punishes whoever next touches that case. The exempt count
# prints on every run so the backlog stays visible instead of becoming invisible.
LEDGER_RULE_EFFECTIVE = "20260924"
_STEM_DATE = re.compile(r"(\d{8})")


def _pre_contract(ml: str) -> bool:
    """True when the record this row points at was written before the rule took effect."""
    m = _STEM_DATE.match(Path(ml).name)
    return bool(m) and m.group(1) < LEDGER_RULE_EFFECTIVE


class Finding:
    __slots__ = ("case", "code", "level", "msg")

    def __init__(self, case, code, level, msg):
        self.case, self.code, self.level, self.msg = case, code, level, msg

    def __str__(self):
        tag = {"error": "ERROR", "warn": "warn ", "note": "[note]"}[self.level]
        return f"  {tag} [{self.code}] {self.case}: {self.msg}"


def _resolve(ml: str, case: Path, repo: Path):
    """Case-relative first, then repo-relative. Returns a Path or None."""
    for cand in (case / ml, repo / ml):
        if cand.is_file():
            return cand
    return None


def check_case(case: Path, repo: Path = REPO) -> list:
    cfg = case / "config" / "calibration_rounds.yaml"
    if not cfg.is_file():
        return []
    try:
        doc = yaml.safe_load(cfg.read_text()) or {}
    except yaml.YAMLError as e:
        return [Finding(case.name, "G0", "error", f"calibration_rounds.yaml is not valid YAML: {e}")]

    changes = (doc.get("model_change_ledger") or {}).get("changes") or []
    out, named, exempt = [], set(), 0

    for c in changes:
        cid = c.get("id", "?")
        ml = c.get("model_log")
        if not ml or RETIRED in ml:
            continue                              # out of scope, by design
        if CASE_STREAM not in ml:
            continue
        if _pre_contract(ml):
            exempt += 1
            hit = _resolve(ml, case, repo)
            if hit is not None:
                named.add(hit.resolve())      # still counts for G3, so it is not double-reported
            continue
        hit = _resolve(ml, case, repo)
        if hit is None:
            out.append(Finding(case.name, "G1", "error",
                               f"change `{cid}`: model_log `{ml}` resolves to no FILE "
                               "(a bare directory `exists()` and is not a record)"))
            continue
        named.add(hit.resolve())
        commit = str(c.get("commit") or "").strip()
        if commit and commit not in hit.read_text(errors="replace"):
            out.append(Finding(case.name, "G2", "error",
                               f"change `{cid}`: ledger says commit `{commit}`, which does not "
                               f"appear in {hit.name} — the copy has drifted from its source"))

    stream = case / CASE_STREAM
    if stream.is_dir():
        for rec in sorted(stream.glob("*.md")):
            if rec.name == "README.md" or rec.resolve() in named:
                continue
            if _pre_contract(rec.name):
                exempt += 1
                continue
            out.append(Finding(case.name, "G3", "warn",
                               f"{rec.name} is named by no ledger entry — a change with a record "
                               "and no row is invisible to the round close"))
    if exempt:
        out.append(Finding(case.name, "G9", "note",
                           f"{exempt} row(s)/record(s) predate the rule "
                           f"({LEDGER_RULE_EFFECTIVE}) and are exempt"))
    return out


def _staged_cases() -> list:
    out = subprocess.run(["git", "diff", "--cached", "--name-only", "--diff-filter=ACMR"],
                         cwd=REPO, stdout=subprocess.PIPE, universal_newlines=True).stdout.split()
    names = set()
    for rel in out:
        p = rel.split("/")
        if len(p) > 2 and p[0] == "use_cases" and (
                "calibration_rounds.yaml" in rel or CASE_STREAM in rel):
            names.add(p[1])
    return [REPO / "use_cases" / n for n in sorted(names)]


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("cases", nargs="*", type=Path)
    ap.add_argument("--staged", action="store_true")
    args = ap.parse_args()

    cases = list(args.cases)
    if args.staged:
        cases += _staged_cases()
    if not cases:
        cases = [p for p in sorted((REPO / "use_cases").glob("*")) if p.is_dir()]
    cases = [c for c in dict.fromkeys(cases) if (c / "config" / "calibration_rounds.yaml").is_file()]
    if not cases:
        print("no ledger to check")
        return 0

    findings = []
    for c in cases:
        findings.extend(check_case(c))

    errors = [x for x in findings if x.level == "error"]
    warns = [x for x in findings if x.level == "warn"]
    print(f"model-change ledger — {len(cases)} case(s) checked")
    for x in findings:
        print(x)
    if not errors and not warns:
        print("\n✔ every ledger row resolves to a record that carries its commit")
        return 0
    print(f"\n{len(errors)} error(s), {len(warns)} warning(s)")
    if errors:
        print("Fix per .claude/skills/model-evolution/SKILL.md step 6 — the ledger copies commit, "
              "branch and V0 result OUT of the record, so the record is the source.")
    return 2 if errors else 1


if __name__ == "__main__":
    sys.exit(main())
