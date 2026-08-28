#!/usr/bin/env python3
"""Check a report under use_cases/<site>/reports/ against the `write-report` contract.

Third checker in the family, and deliberately a SEPARATE tool from
`check_log_conformance.py` (dev/ana logs) and `check_calibration_log_conformance.py`
(calibration logs), for the reason those two are separate from each other: the contracts
genuinely differ. A report has a Status/Date/Author header, an Outline, an Author line that
is `Jing Tao with A2MC` and nothing else, and no Version/Branch. Running a log checker over
it would fail every report for sections it is not supposed to have.

WHAT WOULD MAKE THIS FAIL (named first, per `feedback_a_check_that_cannot_fail`):
  R1  a report folder without the required same-day letter                     -> ERROR
  R2  a missing Status / Date / Author header line                             -> ERROR
  R3  an Author line that is not exactly "Jing Tao with A2MC"                  -> ERROR
  R4  a `## Reader's key` / glossary block, removed from the contract 20260824 -> ERROR
  R5  an em dash in report prose (tables and code fences exempt)               -> ERROR
  R6  no `## Skills and memory invoked` section                                -> ERROR
  R7  a figure embedded with non-empty alt text (`![Figure N](...)`)           -> ERROR
  R8  a ROUND report missing its cycle ledger, parameter reference,
      sensitivity figure, next-round plan, or open-questions list              -> WARN
  R9  nothing matched at all (an empty selection reported as success)          -> ERROR

R4, R5, R6 and R8 are DATE-SCOPED to reports dated on/after 20260824, the day those became
contract. Retro-failing 30 existing reports would block unrelated work and teach people to
pass --no-verify, which is how a gate stops being a gate.

Exit 0 clean / 1 warn / 2 error, the same convention as the other two.
"""
from __future__ import annotations
import argparse, pathlib, re, subprocess, sys

REPORT_RE = re.compile(r"use_cases/[^/]+/reports/(\d{8})(z*[a-z])_[^/]+/[^/]+\.md$")
NEW_RULES_FROM = "20260824"
AUTHOR_OK = "**Author:** Jing Tao with A2MC"
ROUND_HINT = re.compile(r"round[_ ]?summary|ROUND_SUMMARY", re.I)


def _strip_uncheckable(text: str) -> str:
    """Drop fenced code and table rows: the em-dash rule exempts both."""
    out, fence = [], False
    for ln in text.split("\n"):
        if ln.strip().startswith("```"):
            fence = not fence
            continue
        if fence or ln.lstrip().startswith("|"):
            continue
        out.append(ln)
    return "\n".join(out)


def check(path: pathlib.Path, repo: pathlib.Path):
    errs, warns = [], []
    rel = path.relative_to(repo).as_posix() if path.is_absolute() else path.as_posix()
    m = REPORT_RE.search(rel)
    if not m:
        return [f"{rel}: not a report path, or the folder lacks the required same-day letter "
                f"(expected use_cases/<site>/reports/YYYYMMDDx_<topic>/<file>.md)"], []
    date = m.group(1)
    new_rules = date >= NEW_RULES_FROM
    text = path.read_text(errors="replace")
    prose = _strip_uncheckable(text)
    name = path.name

    for field in ("**Status:**", "**Date:**", "**Author:**"):
        if field not in text:
            errs.append(f"{name}: missing required header field {field}")
    if "**Author:**" in text and AUTHOR_OK not in text:
        got = next((l.strip() for l in text.split("\n") if l.startswith("**Author:**")), "?")
        errs.append(f"{name}: author line must be exactly '{AUTHOR_OK}' for a report "
                    f"(reports/ credit the framework, not the harness); got {got!r}")

    for bad in re.finditer(r"!\[(?!\])([^\]]+)\]\(", text):
        errs.append(f"{name}: figure embedded with alt text {bad.group(1)!r} -- pandoc renders the "
                    f"label twice. Use ![](file.png) plus a bold **Figure N.** caption")

    if new_rules:
        if re.search(r"^##+\s*Reader'?s key", text, re.M):
            errs.append(f"{name}: carries a '## Reader's key' block, removed from the contract "
                        f"2026-08-24. Define terms inline on first use instead")
        if "—" in prose:
            n = prose.count("—")
            errs.append(f"{name}: {n} em dash(es) in report prose. Use a comma, colon, parentheses, "
                        f"or split the sentence (tables and code fences are exempt)")
        if not re.search(r"^##+\s*Skills and memory invoked", text, re.M):
            errs.append(f"{name}: missing '## Skills and memory invoked'. Required for reports since "
                        f"2026-08-24, same as the log streams. 'None' is a valid answer")
        if ROUND_HINT.search(rel):
            if not re.search(r"^\|\s*Cycle\s*\|", text, re.M):
                warns.append(f"{name}: ROUND report with no cycle ledger (a table whose first column "
                             f"is 'Cycle') -- `write-report` Table A")
            if not re.search(r"^\|\s*Parameter\s*\|", text, re.M):
                warns.append(f"{name}: ROUND report with no parameter reference (a table whose first "
                             f"column is 'Parameter') -- `write-report` Table B")
            if not re.search(r"sensitivit", text, re.I):
                warns.append(f"{name}: ROUND report with no sensitivity section. Required whatever the "
                             f"sampling method; fall down the ladder in `summarize-calibration-round`")
            if not re.search(r"model[ _-]?evolution|model_change_ledger", text, re.I):
                warns.append(f"{name}: ROUND report with no model-evolution appendix. Required when the "
                             f"model source changed since the previous round; the DETAIL belongs in "
                             f"memory/model_evolution/{{stem}}.md and only a compact table here")
            if not re.search(r"next[- ]round", text, re.I):
                warns.append(f"{name}: ROUND report with no next-round plan -- "
                             f"`calibration-discipline` item 9, the most common omission")
            if not re.search(r"open[- ]question", text, re.I):
                warns.append(f"{name}: ROUND report with no open-questions list. The report "
                             f"ENUMERATES what the round could not settle (each with what would "
                             f"settle it and what it blocks); `round-housekeeping` step 4 CARRIES "
                             f"them to the next Phase 0. Without the list they survive only as "
                             f"sentences in prose, and nothing can tell a settled question from a "
                             f"forgotten one")
    return errs, warns


def staged(repo: pathlib.Path):
    out = subprocess.run(["git", "diff", "--cached", "--name-only", "--diff-filter=ACMR"],
                         cwd=repo, capture_output=True, text=True).stdout.split("\n")
    return [repo / p for p in out if REPORT_RE.search(p)]


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("paths", nargs="*", type=pathlib.Path)
    ap.add_argument("--staged", action="store_true", help="check staged report files only")
    a = ap.parse_args()
    repo = pathlib.Path(__file__).resolve().parents[1]

    files = staged(repo) if a.staged else [p.resolve() for p in a.paths]
    if a.staged and not files:
        return 0                                    # nothing staged is a legitimate no-op
    if not files:
        print("check_report_conformance: no report files given", file=sys.stderr)
        return 2                                    # R9: an empty explicit selection is NOT a pass

    E, W = [], []
    for f in files:
        if not f.exists():
            E.append(f"{f}: does not exist"); continue
        e, w = check(f, repo)
        E += e; W += w
    print(f"report conformance — {len(files)} file(s) checked")
    for w in W: print(f"  warn  {w}")
    for e in E: print(f"  ERROR {e}")
    if not E and not W:
        print("\n✔ all reports conform to the `write-report` skill contract")
    else:
        print(f"\n{len(E)} error(s), {len(W)} warning(s)")
        print("Fix per .claude/skills/write-report/SKILL.md — and RE-READ it rather than recalling it.")
    return 2 if E else (1 if W else 0)


if __name__ == "__main__":
    sys.exit(main())
