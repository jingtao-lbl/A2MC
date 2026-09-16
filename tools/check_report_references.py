#!/usr/bin/env python3
"""Check a report's References section: every published work carries a resolvable identifier.

Fourth checker in the report family, beside `check_report_conformance.py` (structure),
`check_report_figures.py` (alt text) and `check_report_figure_freshness.py` (figure drift). It is a
separate tool for the same reason those are separate from each other: it asks a different question
of a different section, and folding it into the conformance checker would make one tool's exit code
mean two unrelated things.

THE FAILURE THIS CATCHES, measured 2026-09-15. A methodology report cited

    Liu, L. et al. (2024). Knowledge-guided machine learning for agroecosystem carbon
    dynamics (KGML-ag-Carbon). *Ecosystem modelling literature.*

The author and the year were real, carried in a module docstring that says "after Liu et al.
(2024)". The title was invented and the venue is a placeholder. The real paper is Nature
Communications 15, 357, with a different title. Nothing in the repo could see it: `write-report` had
no reference step at all, and the only DOI regex in `tools/` belonged to `check_bound_source.py`,
which governs parameter bounds. The entry was caught by the PI reading it.

WHY A STRUCTURAL CHECK IS WORTH HAVING WHEN IT CANNOT VERIFY A DOI RESOLVES. It cannot confirm that
`10.1038/s41467-023-43860-5` is the paper named beside it -- that needs Crossref, and
`literature-review` Stage 2/4 owns that rule for the human. What it CAN do offline is demand that
something resolvable is present, and a fabricated entry has no DOI to give, because nobody opened
the paper. Run against the pre-fix report this is exactly the entry it flags, and the only one.

WHAT WOULD MAKE THIS FAIL (named first, per `feedback_a_check_that_cannot_fail`):
  X1  a published reference entry with no DOI and no URL                  -> ERROR (fabrication-shaped)
  X2  a malformed DOI: a `doi:` prefix or a `10.` with no registrant      -> ERROR
  X3  a `## References` heading with no entries under it                  -> ERROR
  X4  an `Author (Year)` cited in prose with no matching References entry -> WARN  (orphan citation)
  X5  a References entry no prose citation ever names                     -> WARN  (orphan entry)
  X6  an explicit selection that matched no report at all                 -> ERROR (no silent pass)
  X7  an INTERNAL artifact (a log, a phase stem) listed under References  -> WARN  (wrong section)

X1 AND X7 TOGETHER, and how the rule changed. An entry citing an internal artifact by repo path was
originally EXEMPT from X1, on the reasoning that a log has no DOI to give. The PI corrected that on
2026-09-16: an internal artifact does not belong in References at all, it belongs in
Cross-references, so the exemption became X7's warning rather than a silent pass. Detecting it still
needs the same test -- a backticked token that looks like a path, one containing a `/`. Written to
accept any backticked token, that test also swallowed

    Hammond, G. E., ... PFLOTRAN: a massively parallel reactive flow and transport model.
    Revision `157a26f7` as run here.

-- a published book chapter whose only backtick was a git revision. A hash is not a citation, and
the loose form let one through while the tightened form flags both weak entries. Proven on that
file: loose flags 1 of 2, tight flags 2 of 2.

THE SAME CATEGORY ERROR APPEARS IN PROSE and this checker catches it only indirectly. Citing internal
work as `Tao (2026)` dresses an unpublished repo artifact as a publication; with the entry correctly
moved to Cross-references, X4 then fires as "prose cites Tao (2026) with no matching References
entry", which is the right complaint reached by the wrong route. Refer to internal work by what it
is instead. `write-report` skeleton item 8 states the rule for both halves.

X4/X5 are WARNINGS, not errors. A prose mention can legitimately be a passing reference to a body of
work rather than a citation, and an entry can legitimately support a figure caption. Both are worth
seeing; neither is worth blocking a commit over.

Exit 0 clean / 1 warn / 2 error, the same convention as the other three.

Author: Jing Tao with Claude on Perlmutter
"""
from __future__ import annotations
import argparse, pathlib, re, subprocess, sys

REPORT_RE = re.compile(r"use_cases/[^/]+/reports/(\d{8})(z*[a-z])_[^/]+/[^/]+\.md$")
#: Contract dated from the day the References item entered `write-report`. Existing reports keep
#: what they have rather than leaving the checker permanently red -- the same grandfathering, for
#: the same reason, as R4/R5/R6 in `check_report_conformance.py`.
RULES_FROM = "20260915"

REF_HEAD = re.compile(r"^#{2,3}\s*(?:\d+\.\s*)?References\s*$", re.M)
NEXT_HEAD = re.compile(r"^#{1,3}\s", re.M)
#: Deliberately permissive, following `check_bound_source.py`: the point is that SOMETHING
#: resolvable is present, not that it is well-formed.
IDENTIFIER = re.compile(r"\b10\.\d{4,}/\S+|https?://\S+", re.I)
#: An internal artifact cited by repo path. MUST contain a `/` -- see the docstring for the
#: revision-hash hole this closes.
REPO_PATH = re.compile(r"`[^`]*/[^`]*`")
#: `doi:` introducing nothing, or a `10.` with no 4-digit registrant: a truncated or invented DOI.
MALFORMED = re.compile(r"doi:\s*(?![\s\S]*?10\.\d{4,}/)|(?<![\d.])10\.\d{1,3}/", re.I)
#: BOTH citation forms, because a report legitimately uses each and matching only one makes the
#: orphan checks silently one-sided. NARRATIVE `Author (Year)` / `Author et al. (Year)` /
#: `Author and colleagues (Year)`, and PARENTHETICAL `(Author et al., Year)`. Measured while
#: building this: the narrative pattern alone reported `Hammond (2012)` as an orphan entry AFTER
#: the prose citation had been added, because that citation was written `(Hammond et al., 2012)`
#: -- a matcher that fires on one style reads the other as absence ([[feedback_exact_strings_are_contracts]]).
_AUTHOR = r"[A-Z][A-Za-zÀ-ſ-]+"
_SUFFIX = r"(?:\s+(?:et\s+al\.?|and\s+colleagues|&\s+[A-Z][A-Za-z-]+))?"
PROSE_CITE_NARRATIVE = re.compile(rf"\b({_AUTHOR}){_SUFFIX}\s*\((\d{{4}})[a-z]?\)")
PROSE_CITE_PAREN = re.compile(rf"\(({_AUTHOR}){_SUFFIX},\s*(\d{{4}})[a-z]?\)")


def _cites_in(text: str):
    """(author, year) pairs in either citation style."""
    return set(PROSE_CITE_NARRATIVE.findall(text)) | set(PROSE_CITE_PAREN.findall(text))
FENCE = re.compile(r"^```", re.M)


def _strip_fences(text: str) -> str:
    """Code blocks quote citations as examples; they are not the report's own claims."""
    out, keep = [], True
    for line in text.splitlines():
        if line.startswith("```"):
            keep = not keep
            continue
        if keep:
            out.append(line)
    return "\n".join(out)


def _ref_block(text: str):
    """The References section body, or None when the report has no References section."""
    m = REF_HEAD.search(text)
    if not m:
        return None
    rest = text[m.end():]
    nxt = NEXT_HEAD.search(rest)
    return rest[:nxt.start()] if nxt else rest


def _entries(block: str):
    """One reference per non-trivial line. Bullets, tables and blockquotes are not entries.

    A References section often ends with an editorial NOTE ("all four were read from ..."), which is
    prose about the list rather than a member of it. Write such a note as a BLOCKQUOTE and it is
    skipped here; written as a bare paragraph containing a backticked path it trips X7, which is a
    false positive measured on the first real run of that rule.
    """
    for raw in block.splitlines():
        line = raw.strip().lstrip("-*").strip()
        if len(line) < 40 or raw.strip().startswith(("|", ">", "#")):
            continue
        yield line


def check(path: pathlib.Path, repo: pathlib.Path):
    errs, warns = [], []
    rel = path.relative_to(repo).as_posix() if path.is_relative_to(repo) else str(path)
    m = REPORT_RE.search(rel)
    if not m:
        return [f"{rel}: not a report path (expected use_cases/<site>/reports/YYYYMMDDx_<topic>/<f>.md)"], []
    if m.group(1) < RULES_FROM:
        return [], []                                   # grandfathered, see RULES_FROM

    text = path.read_text(encoding="utf-8", errors="replace")
    body = _strip_fences(text)
    block = _ref_block(body)
    name = rel.split("/reports/")[-1]

    if block is None:
        # No References section is legitimate: most reports cite only internal artifacts. But a
        # report that names published work in prose and lists none is the orphan case at its worst.
        return [], []

    entries = list(_entries(block))
    if not entries:
        return [f"{name}: a `References` heading with no entries. An empty section reads as "
                f"'sources were checked' and is the one state worse than no section"], []

    for e in entries:
        if REPO_PATH.search(e) and not IDENTIFIER.search(e):
            # X7. An internal artifact in References is a CATEGORY error, not a missing DOI: a log or
            # a phase stem is not a publication and a reader sent to the bibliography for it is sent
            # to the wrong place (PI, 2026-09-16). Warned rather than errored -- the entry is real
            # and resolvable, it is simply in the wrong section.
            warns.append(f"{name}: internal artifact listed under References: \"{e[:90]}\". A log, "
                         f"report or phase stem belongs in Cross-references or Provenance, not among "
                         f"published works")
            continue
        if not IDENTIFIER.search(e):
            errs.append(f"{name}: reference with NO resolvable identifier (no DOI, no URL): "
                        f"\"{e[:100]}\". A published work you opened has a DOI to give; an entry "
                        f"assembled from a docstring or a recollection does not. `write-report` "
                        f"discipline, and `literature-review` Stage 2/4 for validating it")
        elif MALFORMED.search(e):
            errs.append(f"{name}: malformed DOI in \"{e[:100]}\" — a `doi:` introducing nothing, or "
                        f"a `10.x/` with no 4-digit registrant. A truncated DOI resolves to nothing "
                        f"and reads as provenance")

    # X4/X5 — the two directions of orphanhood, both warnings.
    prose = body[:REF_HEAD.search(body).start()]
    cited = _cites_in(prose)
    listed = _cites_in(block)
    listed |= {(e.split(",")[0].split()[0], y)
               for e in entries for y in re.findall(r"\((\d{4})[a-z]?\)", e) if e.split()}
    for a, y in sorted(cited - {(x, y2) for x, y2 in listed}):
        warns.append(f"{name}: prose cites `{a} ({y})` with no matching References entry")
    for a, y in sorted({(x, y2) for x, y2 in listed} - cited):
        warns.append(f"{name}: References lists `{a} ({y})` that no prose citation names")
    return errs, warns


def staged(repo: pathlib.Path):
    out = subprocess.run(["git", "diff", "--cached", "--name-only", "--diff-filter=ACMR"],
                         cwd=repo, capture_output=True, text=True).stdout.split("\n")
    return [repo / p for p in out if REPORT_RE.search(p)]


def all_reports(repo: pathlib.Path):
    """Every tracked REPORT. Filtered by REPORT_RE here rather than in `check`, because a sweep and
    an explicit path mean different things: a `reports/README.md` swept up by a glob is not a report
    and must be skipped, while the same path passed by hand is a mistake worth an error (X6's
    sibling). Folding the two made the sweep report 14 errors for files nobody claimed were reports.
    """
    out = subprocess.run(["git", "ls-files", "use_cases/*/reports/*.md",
                          "use_cases/*/reports/*/*.md", "use_cases/*/reports/*/*/*.md"], cwd=repo,
                         capture_output=True, text=True).stdout.split()
    return [repo / p for p in out if REPORT_RE.search(p)]


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("paths", nargs="*", type=pathlib.Path)
    ap.add_argument("--staged", action="store_true", help="check staged report files only")
    a = ap.parse_args()
    repo = pathlib.Path(__file__).resolve().parents[1]

    if a.staged:
        files = staged(repo)
        if not files:
            return 0                                    # nothing staged is a legitimate no-op
    elif a.paths:
        files = [p.resolve() for p in a.paths]
        if not files:
            print("check_report_references: no report files given", file=sys.stderr)
            return 2                                    # X6
    else:
        files = all_reports(repo)

    E, W, with_refs = [], [], 0
    for f in files:
        if not f.exists():
            E.append(f"{f}: does not exist"); continue
        if _ref_block(_strip_fences(f.read_text(encoding="utf-8", errors="replace"))) is not None:
            with_refs += 1
        e, w = check(f, repo)
        E += e; W += w

    print(f"report references — {len(files)} report(s) in scope, {with_refs} with a References section")
    for w in W: print(f"  warn  {w}")
    for e in E: print(f"  ERROR {e}")
    if not E and not W:
        print("✔ every published reference carries a resolvable identifier")
    else:
        print(f"\n{len(E)} error(s), {len(W)} warning(s)")
        print("A citation is the one claim in a report a reader cannot check without leaving it. "
              "See .claude/skills/write-report/SKILL.md and .claude/skills/literature-review/SKILL.md.")
    return 2 if E else (1 if W else 0)


if __name__ == "__main__":
    raise SystemExit(main())
