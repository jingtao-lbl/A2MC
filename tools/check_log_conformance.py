#!/usr/bin/env python3
"""check_log_conformance.py — assert a dev/ana log matches the `log` skill's contract.

WHY THIS EXISTS, AND WHY IT IS A CHECKER RATHER THAN A CHECKLIST LINE
--------------------------------------------------------------------
On 2026-08-01 a single session produced four conformance failures in a row:

  * a 70-commit merge went entirely unlogged (the skill was never invoked);
  * the `log` skill CHANGED MID-SESSION — commit `3fd9ae54` added the
    "Skills and memory invoked" section and arrived inside the very merge that
    went unlogged — and the two logs written afterwards were produced from
    memory of the skill's earlier shape, so both were non-conformant;
  * one log was missing the REQUIRED `## Files Changed` section, a requirement
    that long predated the change and simply went unchecked;
  * one log was written without invoking the skill at all, because no subtype in
    its table matched the shape needed.

The lesson is the one in `feedback_skill_is_authoritative_over_memory`: "I read
it earlier" is not "I read the current one". A checklist item asking the author
to re-read the skill is exactly the step an author who already skipped the skill
will skip again — so the check is mechanical
(`feedback_build_validators_for_all_pitfalls`).

DELIBERATELY DEPENDENCY-FREE: stdlib only, no PyYAML. The Tier-2 skill smoke
harness cannot go green on a Mac precisely because it shells a checker that needs
`yaml` under a system `python3` that lacks it; this one runs anywhere.

WHAT IT CHECKS
--------------
  L1  filename       `YYYYMMDDx_Topic_In_Title_Case.md` (x = a..z, then za..zz)
  L2  header order   Title -> Date -> Author -> Type -> [Version] -> Branch
                     `Version` is REQUIRED for dev logs, FORBIDDEN for ana logs
  L3  sections       required sections present for the stream
  L4  capability     "Skills and memory invoked" — enforced only for logs dated
                     on/after the day it landed (2026-08-01), so ~200 older logs
                     are not retroactively failed
  L5  branch match   a log under `dev_logs_<branch>/` names that branch

Scope: pass explicit paths (what the pre-commit hook does), or a directory plus
`--since YYYYMMDD` for a sweep.

Exit: 0 clean · 1 warnings only · 2 any error.

Usage
-----
    python3 tools/check_log_conformance.py memory/dev_logs_adapterkitpflotran/20260801i_*.md
    python3 tools/check_log_conformance.py --dir memory/dev_logs_adapterkitpflotran --since 20260801
    python3 tools/check_log_conformance.py --staged        # what the hook runs

Author: Jing Tao with Claude
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from datetime import datetime
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent

# The day `3fd9ae54` added the "Skills and memory invoked" section to the log
# skill. Logs dated before this are not judged against a rule that did not exist.
#
# SAME-DAY IS A WARNING, NOT AN ERROR, and the reason is a real limitation worth
# stating: a date is only a PROXY for "when the requirement reached THIS branch".
# The rule landed on `adapter-kit` on 2026-08-01 and arrived here later the same
# day via a merge, so logs written on the boundary date may legitimately predate
# it on this branch. Strictly after the boundary, it is an error.
CAPABILITY_SECTION_SINCE = "20260803"

# 2026-08-14 correction (main's audit `20260814d_Audit_Log_Skill_Format_Divergence...`, verified
# here against `memory/dev_logs/CLAUDE.md`): this constant was `20260801`, which conflated the day
# the section was INTRODUCED with the day it became REQUIRED. The spec's own record is explicit —
# "On 2026-08-03 the bug was here: this section listed 5 required sections and filed *Skills and
# memory invoked* under Optional" — so before 08-03 it was optional and logs must not be judged
# against it. Two different events; the earlier date failed logs that were conformant when written.

# The day the full 8-section list became required in the spec. Sections beyond the legacy four are
# only enforced from here, so older conformant logs are never retroactively failed (same
# non-retroactivity pattern as CAPABILITY_SECTION_SINCE above).
FULL_SECTIONS_SINCE = "20260803"

_FNAME = re.compile(r"^(?P<date>\d{8})(?P<letter>z*[a-z])_(?P<topic>[A-Z][A-Za-z0-9]*"
                    r"(?:_[A-Za-z0-9.]+)*)\.md$")

# Header fields in their required order. `Version` is conditional (see L2).
_DEV_HEADER = ["Date", "Author", "Type", "Version", "Branch"]
_ANA_HEADER = ["Date", "Author", "Type", "Branch"]

_DEV_SECTIONS = ["Summary", "Files Changed", "Verification", "Cross-references"]
_ANA_SECTIONS = ["Cross-references"]          # ana logs are freer-form by design
_CAPABILITY = "Skills and memory invoked"

# Sections required BEYOND the legacy four above, per SUBTYPE. The skill's own subtype table gives
# each subtype a different distinctive-section set, so a uniform 8-section check is wrong: a
# Handoff_To_Main log is "Why this is a handoff · What landed here · Action items for main ·
# Verify-on-main commands" and legitimately has no Problem/Solution, and a Session log is
# "Summary · What was done · State at session end · Open threads ..." Measured before wiring this:
# a flat 8-section rule would have failed `20260803e` and `20260805a`, both correctly-formed
# HANDOFF logs. Only the genuine violation (a REGULAR log missing `## Next`) should fail.
_EXTRA_SECTIONS_BY_SUBTYPE = {
    "regular":    ["Problem", "Solution", "Next"],
    "audit":      ["Problem", "Solution"],     # Files Changed = "None — audit only"; no Next needed
    "session":    [],                          # has its own shape (State at session end, ...)
    "handoff":    [],                          # has its own shape entirely
    "reflection": [],                          # has its own shape entirely (grouped-by-root-cause
                                                # retrospective, no Problem/Solution/Next by design —
                                                # `log` skill's subtype table: "the errors grouped by
                                                # root cause · why existing skills/memories didn't
                                                # prevent them · concrete mechanisms, not exhortation")
}


def _subtype(path: Path, present: set, text: str) -> str:
    """Best-effort subtype, from the log's own shape rather than a declared field.

    Detection is deliberately shape-based: the `log` skill does not require a machine-readable
    subtype marker, so inferring from the sections a writer actually used is the only signal that
    cannot go stale relative to the content.
    """
    if "reflection" in path.parts:
        # Path-based, not content-based: the `log` skill's own convention is that a Reflection log
        # LIVES in `<dev_logs_dir>/reflection/` (any branch's, not just this one's), which is a
        # stronger, less accidental signal than any prose heading a "regular" log might also use.
        return "reflection"
    if "Why this is a handoff" in present or "Handoff" in path.name:
        return "handoff"
    if "State at session end" in present or "What was done" in present:
        return "session"
    if re.search(r"^## Files Changed\s*$\s*\n+\s*None\b", text, re.M):
        return "audit"
    return "regular"

# Files that LIVE in a log directory but are not logs. `memory/dev_logs/CLAUDE.md` is the
# style guide itself: staging it made the pre-commit hook check the spec as though it were an
# instance of the spec, and fail it 5 ways (2026-08-03).
_NOT_LOGS = {"CLAUDE.md", "README.md", "MEMORY.md", "index.md"}


class Finding:
    __slots__ = ("path", "code", "level", "msg")

    def __init__(self, path, code, level, msg):
        self.path, self.code, self.level, self.msg = path, code, level, msg

    def __str__(self):
        tag = "ERROR" if self.level == "error" else "warn "
        return f"  {tag} [{self.code}] {self.path.name}: {self.msg}"


def _is_ana(path: Path) -> bool:
    return "ana_logs" in path.parts


def _branch_from_dir(path: Path) -> str | None:
    """`memory/dev_logs_adapterkitpflotran/` -> the squashed branch token."""
    for part in path.parts:
        if part.startswith("dev_logs_"):
            return part[len("dev_logs_"):]
    return None


def wrong_stream(path: Path):
    """Is this path unambiguously in a stream this tool does NOT govern?

    Fires only on a POSITIVE match for another stream, never on an ambiguous path, so a draft or a
    test fixture stays checkable. Added 2026-08-14 alongside the new sibling: verified that without
    it, pointing THIS tool at a calibration log produced 6 errors demanding
    Problem/Solution/Verification — sections a calibration log is not supposed to have — which
    reads as "your log is broken" when the truth is "wrong tool".
    """
    parts = path.parts
    if "use_cases" in parts and "logs" in parts:
        return ("a CALIBRATION log (use_cases/<site>/memory/logs/) — use "
                "`tools/check_calibration_log_conformance.py`, whose contract is different "
                "(per-phase sections for a phase log; a lighter header for a free-form one)")
    if "model_logs" in parts:
        return ("a MODEL-DEV log (memory/model_logs/) — that stream has its own header shape and "
                "is held by review, not by a checker (see memory/model_logs/CLAUDE.md)")
    return None


def check_file(path: Path) -> list[Finding]:
    out: list[Finding] = []
    if not path.is_file():
        return [Finding(path, "L0", "error", "file not found")]
    other = wrong_stream(path)
    if other:
        return [Finding(path, "L00", "error", "wrong tool: this is %s" % other)]
    text = path.read_text(errors="replace")
    lines = text.splitlines()
    ana = _is_ana(path)

    # ---- L1 filename ----
    m = _FNAME.match(path.name)
    if not m:
        out.append(Finding(path, "L1", "error",
                           "filename is not YYYYMMDDx_Topic_In_Title_Case.md"))
        date = ""
    else:
        date = m.group("date")
        # The pattern only proves "eight digits". Check it is a REAL date --
        # found when a negative test used the fake stem `20260899z` (month 08,
        # day 99) and L1 accepted it.
        try:
            datetime.strptime(date, "%Y%m%d")
        except ValueError:
            out.append(Finding(path, "L1", "error",
                               f"filename date {date!r} is not a real calendar date"))
            date = ""

    # ---- L2 header order ----
    head = lines[:14]
    seen: list[str] = []
    for ln in head:
        fm = re.match(r"^\*\*(\w+):\*\*", ln)
        if fm:
            seen.append(fm.group(1))
    want = _ANA_HEADER if ana else _DEV_HEADER
    if not lines or not lines[0].startswith("# "):
        out.append(Finding(path, "L2", "error", "first line is not an `# H1` title"))
    if ana and "Version" in seen:
        out.append(Finding(path, "L2", "error",
                           "ana logs must NOT carry a Version field"))
    missing_hdr = [f for f in want if f not in seen]
    if missing_hdr:
        out.append(Finding(path, "L2", "error",
                           f"header missing {', '.join(missing_hdr)}"))
    else:
        order = [f for f in seen if f in want]
        if order != want:
            out.append(Finding(path, "L2", "warn",
                               f"header order is {order}, expected {want}"))

    # ---- L3 required sections ----
    present = {ln[3:].strip() for ln in lines if ln.startswith("## ")}
    for sec in (_ANA_SECTIONS if ana else _DEV_SECTIONS):
        if sec not in present:
            out.append(Finding(path, "L3", "error", f"missing required section '## {sec}'"))

    # ---- L3b the rest of the required list, subtype-aware and non-retroactive ----
    # Until 2026-08-14 this checker verified only the four sections above, while the skill prose
    # presented eight as required — so Problem/Solution/Next were documented but never enforced,
    # and a log missing one passed clean (found by main's audit `20260814d_Audit_Log_Skill_...`).
    if not ana and date and date >= FULL_SECTIONS_SINCE:
        sub = _subtype(path, present, text)
        for sec in _EXTRA_SECTIONS_BY_SUBTYPE.get(sub, []):
            if sec not in present:
                out.append(Finding(
                    path, "L3b", "warn" if date == FULL_SECTIONS_SINCE else "error",
                    f"missing required section '## {sec}' (subtype: {sub}; required for logs "
                    f"dated after {FULL_SECTIONS_SINCE})"))

    # ---- L4 capability section (only once the rule existed) ----
    if date and date >= CAPABILITY_SECTION_SINCE and _CAPABILITY not in present:
        boundary = date == CAPABILITY_SECTION_SINCE
        out.append(Finding(
            path, "L4", "warn" if boundary else "error",
            f"missing '## {_CAPABILITY}'"
            + (" — but dated on the boundary day, so it may predate the rule "
               "reaching this branch" if boundary
               else f" (required for logs dated after {CAPABILITY_SECTION_SINCE}; "
                    "'None' is a valid answer)")))

    # ---- L5 branch header matches the directory ----
    want_branch = _branch_from_dir(path)
    if want_branch:
        bm = re.search(r"^\*\*Branch:\*\*\s*(.+?)\s*$", text, re.M)
        if bm:
            squashed = bm.group(1).replace("-", "").replace("_", "").lower()
            if want_branch.lower() not in squashed:
                out.append(Finding(path, "L5", "warn",
                                   f"Branch header {bm.group(1)!r} does not match "
                                   f"directory token {want_branch!r}"))

    out.extend(_check_capability_names(path, text))
    out.extend(_check_memory_written(path, text))
    return out


# A log stem (`20260801e`, `20260731c_Making_…`) is a legitimate citation, not a skill name.
_STEM = re.compile(r"^\d{8}[a-z]{1,3}(_|$)")
_MEM_PREFIX = ("feedback_", "project_", "reference_", "user_")


def _check_capability_names(path: Path, text: str) -> list:
    """L6 — the skills and memories a log CLAIMS to have used must exist.

    L4 checks only that the section is PRESENT. A log could name `phase9-nonsense` or an
    invented memory and pass, which is worse than omitting the section: it asserts a
    provenance the reader cannot follow, and it silently breaks the cross-reference pass
    that `memory-checkup` runs over exactly these names.

    Deliberately narrow, because the citation contract in check_memory_bucket.py produced
    6 false positives out of 6 hits on its first cut. Only backticked single tokens on the
    `**Skills:**` / `**Memory:**` lines of that one section are considered; anything with a
    path separator, a shell variable, whitespace, or a log-stem shape is skipped. Measured
    before wiring: 33 skill and 11 memory tokens across the repo's logs, 0 false positives
    after the stem exclusion.

    Applies to calibration phase logs too, not only dev logs — a phase log claiming
    `phase3-diagnosis` and a memory it did not consult is the same defect.
    """
    out = []
    m = re.search(rf"^## {re.escape(_CAPABILITY)}\s*$(.*?)(?=^## |\Z)", text, re.S | re.M)
    if not m:
        return out                                   # absence is L4's business, not L6's
    section = m.group(1)
    skills_dir, mem_dir = REPO / ".claude" / "skills", REPO / ".claude_memory"

    for label, kind in (("Skills", "skill"), ("Memory", "memory")):
        line = re.search(rf"\*\*{label}:?\*\*(.*)", section)
        if not line:
            continue
        for tok in (t.strip().strip(",.") for t in re.findall(r"`([^`\n]+)`", line.group(1))):
            if not tok or "/" in tok or "$" in tok or " " in tok or _STEM.match(tok):
                continue
            if kind == "skill":
                if not (skills_dir / tok).is_dir():
                    out.append(Finding(path, "L6", "error",
                                       f"claims skill `{tok}`, which is not in .claude/skills/"))
            else:
                if not tok.startswith(_MEM_PREFIX):
                    continue                          # not a memory slug; leave it alone
                if not (mem_dir / f"{tok}.md").exists():
                    out.append(Finding(path, "L6", "error",
                                       f"claims memory `{tok}`, which is not in .claude_memory/"))
    return out


def _check_memory_written(path: Path, text: str) -> list:
    """L7 — a log's `**Memory written:**` line and the memory's `**Source:**` must agree.

    WARNING, not error, deliberately and for now. The convention is new (2026-08-07) and 100
    of 109 memories predate the `**Source:**` rule entirely, so erroring would block unrelated
    commits on a debt nobody has paid down yet. Promote to error once the backfill lands.

    WHY THIS EXISTS. `**Memory:**` lists memories APPLIED; this line lists memories this log
    CREATED OR CHANGED — a distinction the capability section did not previously make, and the
    reason no bidirectional check was possible before. Measured 2026-08-07 on the two obvious
    proxies: requiring the Source log to merely *mention* the memory failed 7 of 9 memories,
    and requiring it in `Files Changed` failed 11 — both because a log naming a memory it
    produced was not a thing the convention asked for. This line is that thing.

    The check is one-directional here (log -> memory); `check_memory_bucket.py` walks the other
    way (memory -> log), and only both together close the loop. Neither alone would have caught
    the 2026-08-07 defect, where two memories cited a real log containing none of their content.
    """
    out = []
    m = re.search(rf"^## {re.escape(_CAPABILITY)}\s*$(.*?)(?=^## |\Z)", text, re.S | re.M)
    if not m:
        return out
    line = re.search(r"\*\*Memory written:?\*\*(.*)", m.group(1))
    if not line:
        return out
    stem = path.name.split("_", 1)[0]
    for tok in (t.strip().strip(",.") for t in re.findall(r"`([^`\n]+)`", line.group(1))):
        if not tok or "/" in tok or "$" in tok or " " in tok or not tok.startswith(_MEM_PREFIX):
            continue
        mem = REPO / ".claude_memory" / f"{tok}.md"
        if not mem.exists():
            out.append(Finding(path, "L7", "warn",
                               f"claims to have written memory `{tok}`, which is not in "
                               f".claude_memory/ (write the memory first, then the log)"))
            continue
        mem_text = mem.read_text(encoding="utf-8", errors="replace")
        # A path-qualified `**Source:**` is unambiguous, so hold it to the stricter test: it must
        # name THIS log's filename. Stem-only matching would accept a same-stem log in another
        # branch dir (`20260806a` names one log in dev_logs_adapterkit and another in
        # dev_logs_adapterkitpflotran), which is the mirror of the defect fixed in
        # check_memory_bucket on 2026-08-19. Bare-stem citations keep the legacy test.
        cited_paths = [ln for ln in mem_text.splitlines() if ln.startswith("**Source:**")
                       and "/" in ln]
        matched = (path.name in cited_paths[0] if cited_paths else stem in mem_text)
        if not matched:
            out.append(Finding(path, "L7", "warn",
                               f"names `{tok}` under 'Memory written' but that memory's "
                               f"`**Source:**` never names this log ({stem}) — the back-link "
                               f"is missing, so the pair is only half-connected"))
    return out


def _pure_rename_paths(repo):
    """Staged paths whose CONTENT did not change: a rename at 100% similarity.

    WHY (2026-08-25): the staged-file gates use `--diff-filter=ACMR`, and R includes renames, so a
    DIRECTORY rename re-gates every file it moved even though not one byte changed. Measured:
    renaming `use_cases/Kougarok` to `use_cases/ELM-FATES_Kougarok` staged 36 files, and this gate
    failed the commit on a PRE-EXISTING defect in a log the rename merely relocated. That is
    exactly the "block unrelated work you did not touch" failure the staged-only design exists to
    prevent, arriving through a door that design did not cover.

    A rename WITH edits (R0xx, similarity below 100) is NOT in this set and is still checked, which
    is what makes this a narrowing rather than a hole.
    """
    import subprocess
    try:
        out = subprocess.check_output(
            ["git", "diff", "--cached", "-M", "--name-status", "--diff-filter=R"],
            cwd=str(repo)).decode("utf-8", "replace")
    except Exception:
        return set()
    pure = set()
    for ln in out.splitlines():
        f = ln.split("\t")
        if len(f) >= 3 and f[0].strip() == "R100":
            pure.add(f[2].strip())
    return pure


def _staged_logs() -> list[Path]:
    try:
        raw = subprocess.check_output(
            ["git", "diff", "--cached", "--name-only", "--diff-filter=ACMR"],
            text=True, cwd=REPO)
    except (subprocess.CalledProcessError, FileNotFoundError):
        return []
    keep = []
    _pure = _pure_rename_paths(REPO)
    for line in raw.splitlines():
        if line.strip() in _pure:          # pure rename: nothing new to gate
            continue
        p = Path(line)
        if p.suffix != ".md":
            continue
        if p.name in _NOT_LOGS:
            continue
        if any(part.startswith("dev_logs") or part == "ana_logs" for part in p.parts):
            keep.append(REPO / p)
    return keep


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("paths", nargs="*", type=Path, help="log files to check")
    ap.add_argument("--dir", type=Path, help="check a whole log directory")
    ap.add_argument("--since", default=None,
                    help="with --dir: only logs dated YYYYMMDD or later")
    ap.add_argument("--staged", action="store_true",
                    help="check staged log files (what the pre-commit hook runs)")
    args = ap.parse_args()

    files: list[Path] = list(args.paths)
    if args.staged:
        files += _staged_logs()
    if args.dir:
        for p in sorted(args.dir.glob("*.md")):
            if p.name in _NOT_LOGS:       # the style guide is not an instance of itself
                continue
            if args.since:
                m = _FNAME.match(p.name)
                if not m or m.group("date") < args.since:
                    continue
            files.append(p)

    files = [f for f in dict.fromkeys(files)]          # de-dupe, keep order
    if not files:
        print("no log files to check")
        return 0

    findings: list[Finding] = []
    for f in files:
        findings.extend(check_file(f))

    errors = [x for x in findings if x.level == "error"]
    warns = [x for x in findings if x.level == "warn"]

    print(f"log conformance — {len(files)} file(s) checked")
    for x in findings:
        print(x)
    if not findings:
        print("\n✔ all logs conform to the `log` skill contract")
        return 0
    print(f"\n{len(errors)} error(s), {len(warns)} warning(s)")
    if errors:
        print("Fix per .claude/skills/log/SKILL.md — and RE-READ it rather than "
              "recalling it; it changes.")
    return 2 if errors else 1


if __name__ == "__main__":
    sys.exit(main())
