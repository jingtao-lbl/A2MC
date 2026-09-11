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
# Tables numbered, never lettered (`write-report`, PI 2026-09-09). Dated like the rules above:
# reports written before it keep their lettered labels, so the checker is not permanently red.
NUMBERED_TABLES_FROM = "20260909"
AUTHOR_OK = "**Author:** Jing Tao with A2MC"
# The round-level rules apply to the ROUND REPORT, identified by its own FILENAME or its H1 title
# -- not by its folder. Matching the folder made every companion document in a round-summary
# folder a round report: measured 2026-09-05, a cross-round ledger and a holdout analysis drew 6
# and 7 warnings each for lacking a sensitivity section and a next-round plan they were never
# supposed to carry. A gate that cries wolf is a gate people pass with --no-verify.
ROUND_HINT = re.compile(r"round[_ ]?(summary|report)", re.I)
ROUND_TITLE = re.compile(r"^#\s+.*round[_ ]?(summary|report)", re.I | re.M)

# A round report is the OUTPUT of a pipeline, not a document someone sits down and writes. These
# four skills are the pipeline (PI, 2026-09-05): the standardized bundle and its two required
# tables, the report contract itself, the driver that reaches the round close, and the per-cycle
# discipline that produced the artifacts being synthesized. A round report written without them
# is not a round report with a missing citation -- it is a round report assembled from whatever
# happened to be on disk, which is how one lost its own central mechanism. ERROR, not warning:
# the remedy is to run them and redo the report, not to add the names.
# `compare-calibration-rounds` is required for EVERY round including the FIRST, and the objection
# that a first round has nothing to compare is true only of its Deliverable 2, the cross-round
# figures. Deliverables 1, 1b and 1c all have content at R1, and the one-column ledger a first
# round produces IS the baseline every later round is checked against: without it, R2's comparison
# has no prior state to read and must reconstruct it from logs, which is the failure this skill
# exists to prevent.
REQUIRED_ROUND_SKILLS = ("summarize-calibration-round", "compare-calibration-rounds",
                         "write-report", "calibration-goal", "calibration-discipline")


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


def _section_body(text: str, m: "re.Match") -> str:
    """The text under heading `m`, up to the next heading of the SAME or shallower level."""
    level = len(m.group(1))
    rest = text[m.end():]
    nxt = re.search(r"^#{1,%d}\s" % level, rest, re.M)
    return rest[:nxt.start()] if nxt else rest


def _cites(body: str) -> bool:
    """A checkable citation: a `file:line`, a backticked data/source file, or an artifact path."""
    return bool(re.search(r"`[^`]+[.:][A-Za-z0-9_]+[:.][0-9]+"
                          r"|`[^`]*\.(py|F90|dat|in|out|json|yaml|csv|nc|md)[^`]*`"
                          r"|memory/(logs|phase_results)/", body))


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
        lettered = re.findall(r"\bTable [A-Z]\b", prose) if date >= NUMBERED_TABLES_FROM else []
        if lettered:
            errs.append(f"{name}: lettered table label(s) {sorted(set(lettered))} in report prose. "
                        f"Scientific reports number tables Table 1, Table 2, ... "
                        f"(`write-report`, PI 2026-09-09)")
        if not re.search(r"^##+\s*Skills and memory invoked", text, re.M):
            errs.append(f"{name}: missing '## Skills and memory invoked'. Required for reports since "
                        f"2026-08-24, same as the log streams. 'None' is a valid answer")
        if ROUND_HINT.search(pathlib.Path(rel).name) or ROUND_TITLE.search(text):
            if not re.search(r"^\|\s*Cycle\s*\|", text, re.M):
                warns.append(f"{name}: ROUND report with no cycle ledger (a table whose first column "
                             f"is 'Cycle') -- `write-report`, the CYCLE LEDGER table")
            if not re.search(r"^\|\s*Parameter\s*\|", text, re.M):
                warns.append(f"{name}: ROUND report with no parameter reference (a table whose first "
                             f"column is 'Parameter') -- `write-report`, the PARAMETER REFERENCE table")
            skills_line = "\n".join(
                l for l in text.split("\n")
                if re.match(r"\s*[-*]?\s*\*\*Skills:?\*\*", l))
            missing = [k for k in REQUIRED_ROUND_SKILLS if f"`{k}`" not in skills_line]
            if missing:
                errs.append(
                    f"{name}: ROUND report does not name {', '.join(missing)} on its "
                    f"'**Skills:**' line. These four are the pipeline a round report is the OUTPUT "
                    f"of, not optional citations. If they were not run, the fix is to run them and "
                    f"REDO the report; if they were, name them exactly (backticked) so the claim is "
                    f"greppable and `check_skill_claims.py` can verify it")

            # These four ask for a SECTION, not for the word. A bare substring match is a check
            # that cannot fail: "sensitivity" appears in any report that mentions the word once in
            # prose, so the check passed on reports that carried no such section. Anchored to a
            # markdown heading (or, for the appendix, its bold lead-in), each now FAILS on a report
            # that discusses the topic in passing without giving it a home. Tightened 2026-09-05.
            if not re.search(r"^#{2,}.*sensitivit", text, re.I | re.M):
                warns.append(f"{name}: ROUND report with no sensitivity SECTION (a heading, not the "
                             f"word in passing). Required whatever the sampling method; fall down "
                             f"the ladder in `summarize-calibration-round`")
            if not re.search(r"^(#{2,}.*|\*\*)(model[ _-]?evolution)", text, re.I | re.M):
                warns.append(f"{name}: ROUND report with no model-evolution appendix (a heading or a "
                             f"bold lead-in, not the phrase in passing). Required when the model "
                             f"source changed since the previous round; the DETAIL belongs in "
                             f"memory/model_evolution/{{stem}}.md and only a compact table here")
            if not re.search(r"^#{2,}.*next[- ]round", text, re.I | re.M):
                warns.append(f"{name}: ROUND report with no next-round plan SECTION -- "
                             f"`calibration-discipline` item 9, the most common omission")
            # The mechanism section: the round's science, indexed by neither table. Its source is
            # the first Phase-3 diagnosis. FAILS when the heading is absent, and separately when
            # the heading exists but cites nothing -- a mechanism with no `file:line`, artifact
            # path or named log is an assertion, which is the state this check was written for.
            # Scan EVERY mechanism-ish heading, not the first. Under the canonical outline the
            # first match is the section heading ("4. Mechanism and hypothesis testing") whose own
            # intro carries no numbers, while the citations live in a subsection below it. Taking
            # only the first match reported "cites nothing" on a correctly cited report.
            mech_hits = list(re.finditer(r"^(#{2,})\s*(.*(?:mechanism|what the round established|"
                                         r"diagnosis).*)$", text, re.I | re.M))
            if not mech_hits:
                warns.append(f"{name}: ROUND report with no mechanism section -- what the round "
                             f"established about the SYSTEM, sourced from the first Phase-3 "
                             f"diagnosis. Neither required table is indexed by mechanism, so a "
                             f"finding about an unsampled or unscored variable has no row anywhere "
                             f"and its absence leaves no visible hole. `write-report`, the ROUND "
                             f"report section")
            elif not any(_cites(_section_body(text, m)) for m in mech_hits):
                warns.append(f"{name}: mechanism section cites nothing checkable. Every number "
                             f"needs a `file:line`, an artifact path or a named log; without "
                             f"one it is an assertion the next round cannot re-judge")
            # Also a heading, and also carrying its TABLE: the skill specifies the columns
            # (question, what would settle it, what it blocks) precisely because a question
            # without those two is a musing. A prose mention of "open questions" passed before.
            oq = re.search(r"^#{2,}.*open[- ]question", text, re.I | re.M)
            if oq and not re.search(r"^\|\s*#?\s*\|\s*Question\s*\|", text, re.I | re.M):
                warns.append(f"{name}: open-questions section with no table. Each item needs WHAT "
                             f"WOULD SETTLE IT and WHAT IT BLOCKS; a question with neither is a "
                             f"musing, not a task `round-housekeeping` step 4 can carry forward")
            if not oq:
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
