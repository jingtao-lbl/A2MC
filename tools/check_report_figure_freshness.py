#!/usr/bin/env python3
"""A report's embedded figure must still match the canonical figure it cites.

THE FAILURE THIS CATCHES, measured 2026-09-13. `write-report` states the rule plainly: a phase
figure's canonical home is its `phase_results/{stem}/`, a report embeds a COPY of the rendered PNG
and cites the producing script, and when the figure changes you regenerate it in the stem and
re-copy. One report's Figure 1 then drifted THREE corrections behind its source -- a restructured
panel, a retitled figure, and three relocated legends -- while the report was re-rendered to PDF and
docx three times in that window, each render faithfully re-embedding the stale image. Nothing
noticed, because `check_report_figures.py` inspects alt text and no other check looks at the bytes.

WHY A DECLARED MAPPING AND NOT FILENAME MATCHING. Reports RENAME figures on copy: the measured case
is `R1b_kgml_emulator.png` becoming `fig1_emulator.png`, which is good practice (a report numbers
its figures) and fatal to any name-based rule. So each report folder declares its sources in a
`figure_sources.tsv`, and `--init` writes that file for you by finding the byte-identical original.

WHY AN UNMAPPED FIGURE WARNS RATHER THAN PASSING. A report with no manifest is a report whose
invariant is UNCHECKED, which is a different thing from a report that is fine. Passing it silently
would make this checker report clean across a repo that has adopted none of it
([[feedback_a_check_that_cannot_fail]]). The counts are printed on every run for the same reason.

    figure_sources.tsv  (in the report folder, tab-separated, '#' comments allowed)
        fig1_emulator.png	use_cases/<Case>/memory/phase_results/<stem>/R1b_kgml_emulator.png

Usage::

    python3 tools/check_report_figure_freshness.py                       # every report in the repo
    python3 tools/check_report_figure_freshness.py <report_dir | report.md | reports_dir>
    python3 tools/check_report_figure_freshness.py <report_dir> --init   # write the manifest
    python3 tools/check_report_figure_freshness.py --staged              # pre-commit mode
    python3 tools/check_report_figure_freshness.py --strict-unmapped     # unmapped becomes an ERROR

Exit 0 = clean, 1 = warnings, 2 = errors (a drifted copy, a dead pointer, a stale entry).
Stdlib only.

Author: Jing Tao with Claude on Perlmutter
"""
from __future__ import annotations

import argparse
import hashlib
import subprocess
import sys
from pathlib import Path
from typing import Dict, List, Optional, Tuple

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = "figure_sources.tsv"
IMAGE_SUFFIXES = (".png", ".jpg", ".jpeg")

#: Reports whose folder date precedes this are EXEMPT from needing a manifest (PI, 2026-09-15:
#: "existing reports are fine; just enforce the rule going forward"). 84 report folders predate the
#: rule, most in cases another effort owns, and retro-warning them would be a permanent wall of
#: noise about work nobody is going to revisit -- a checker whose output is always red is a checker
#: nobody reads. Same grandfathering pattern, and the same reason, as the embed-your-figures rule in
#: `check_offline_log_evidence.py`.
#:
#: Two properties keep the exemption from becoming a hole. It is COUNTED AND REPORTED, never silent.
#: And it exempts only the REQUIREMENT to declare a source: a grandfathered report that declares one
#: anyway is drift-checked in full, so adopting the rule on an old report is opt-in and immediately
#: effective.
MANIFEST_REQUIRED_FROM = "20260915"

OK, WARN, ERROR = 0, 1, 2


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for block in iter(lambda: fh.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


# ---------------------------------------------------------------------------------------------
# finding reports, WITHOUT walking the filesystem
# ---------------------------------------------------------------------------------------------

def _git_files(*patterns: str) -> List[Path]:
    """Tracked plus untracked-but-not-ignored files matching a pathspec.

    Index-based, never a filesystem walk: this repo lives on a shared NERSC filesystem where a
    recursive traversal is prohibited, and a checker that measures the DISK rather than the BRANCH
    is wrong for a second reason anyway ([[feedback_a_gate_must_measure_the_branch_not_the_disk]]).
    """
    try:
        out = subprocess.run(
            ["git", "ls-files", "--cached", "--others", "--exclude-standard", "-z", "--", *patterns],
            cwd=ROOT, capture_output=True, text=True, check=True).stdout
    except (subprocess.CalledProcessError, FileNotFoundError):
        return []
    return [ROOT / p for p in out.split("\0") if p]


def report_dirs_from(target: Optional[str]) -> List[Path]:
    """Resolve a CLI target to the report FOLDERS it names."""
    if target is None:
        dirs = {f.parent for f in _git_files("use_cases/*/reports/*/*")}
        return sorted(d for d in dirs if d.is_dir())
    p = Path(target)
    if not p.is_absolute():
        p = (ROOT / p) if not p.exists() else p.resolve()
    if p.is_file():
        return [p.parent]
    if not p.is_dir():
        return []
    # a `reports/` parent, or a single report folder
    if p.name == "reports":
        return sorted(c for c in p.iterdir() if c.is_dir())
    return [p]


def report_images(d: Path) -> List[Path]:
    """Figures in a report folder, excluding the report's own rendered outputs.

    A report rendered beside its source shares that source's stem, so `<topic>.pdf` next to
    `<topic>.md` is the deliverable rather than a figure and must not be asked to match a
    canonical source it never had.
    """
    doc_stems = {f.stem for f in d.iterdir() if f.is_file() and f.suffix.lower() == ".md"}
    return sorted(f for f in d.iterdir()
                  if f.is_file() and f.suffix.lower() in IMAGE_SUFFIXES
                  and f.stem not in doc_stems)


def report_date(d: Path) -> Optional[str]:
    """The `YYYYMMDD` prefix of a `{YYYYMMDDx}_{topic}` report folder, or None if unparseable.

    An unparseable name is treated as grandfathered rather than as new: the folder-naming
    convention has its own checker, and refusing to commit over a name this tool cannot read would
    be this tool enforcing someone else's rule.
    """
    head = d.name[:8]
    return head if head.isdigit() else None


def manifest_required(d: Path) -> bool:
    day = report_date(d)
    return day is not None and day >= MANIFEST_REQUIRED_FROM


# ---------------------------------------------------------------------------------------------
# the manifest
# ---------------------------------------------------------------------------------------------

def read_native(path: Path) -> set:
    """Figures a report DECLARES as report-native, via `# report-native <figure.png>` comment lines.

    WHY THIS EXISTS. `write-report` section 3 makes the report folder the canonical home for a
    synthesis figure belonging to no single phase, and this tool's own error message tells the author
    such a figure "belongs in a comment line". That advice did not work: `manifest_required` makes
    every embedded figure need a MAPPED entry for a report dated on or after the cutoff, and
    `read_manifest` skips comments, so a correctly-authored report-native figure was an ERROR with no
    conforming way to clear it. The only ways out were to map a figure to ITSELF, which is a check
    that cannot fail, or to leave the report permanently red.

    A declaration is not an escape hatch. Each figure must be named explicitly on its own line, so an
    unlisted figure is still an error, and a figure that DOES carry a mapped source is still compared
    by hash.
    """
    out = set()
    if not path.is_file():
        return out
    for raw in path.read_text().splitlines():
        line = raw.strip()
        if not line.startswith("#") or "report-native" not in line:
            continue
        for tok in line.lstrip("#").split():
            if tok.lower().endswith((".png", ".jpg", ".jpeg", ".svg")):
                out.add(tok)
    return out


def read_manifest(d: Path) -> Dict[str, str]:
    path = d / MANIFEST
    if not path.is_file():
        return {}
    out: Dict[str, str] = {}
    for lineno, raw in enumerate(path.read_text().splitlines(), 1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        parts = [c for c in line.split("\t") if c.strip()]
        if len(parts) != 2:
            raise ValueError(f"{path}:{lineno}: expected '<figure>\\t<source>', got {raw!r}")
        out[parts[0].strip()] = parts[1].strip()
    return out


def init_manifest(d: Path) -> Tuple[int, int]:
    """Write `figure_sources.tsv` by matching each report image to a byte-identical original.

    A figure with no hash match is left OUT and reported, because the two reasons for that are both
    worth a human look: the figure is report-native (no canonical source exists, which is legitimate
    and documented in `write-report`), or the copy has ALREADY drifted, which is the very condition
    this tool exists to find. Guessing either way would defeat it.
    """
    images = report_images(d)
    if not images:
        return 0, 0
    candidates = _git_files("use_cases/*/memory/phase_results/*/*.png",
                            "use_cases/*/memory/phase_results/*/*/*.png")
    by_hash: Dict[str, Path] = {}
    for c in candidates:
        if c.is_file():
            by_hash.setdefault(sha256(c), c)

    lines = [f"# Canonical source of each figure copied into this report.",
             f"# Checked by tools/{Path(__file__).name}; regenerate a figure in its",
             f"# phase_results stem, then re-copy it here and this check passes again.",
             f"# <figure in this folder>\\t<repo-relative canonical source>"]
    matched = 0
    for img in images:
        src = by_hash.get(sha256(img))
        if src is None:
            continue
        lines.append(f"{img.name}\t{src.relative_to(ROOT)}")
        matched += 1
    (d / MANIFEST).write_text("\n".join(lines) + "\n")
    return matched, len(images)


# ---------------------------------------------------------------------------------------------
# the check
# ---------------------------------------------------------------------------------------------

def check_report(d: Path, strict_unmapped: bool = False
                 ) -> Tuple[List[str], List[str], int, int, bool]:
    """(errors, warnings, n_checked, n_unmapped, exempt) for one report folder."""
    errors: List[str] = []
    warnings: List[str] = []
    images = report_images(d)
    rel = d.relative_to(ROOT) if str(d).startswith(str(ROOT)) else d
    try:
        manifest = read_manifest(d)
    except ValueError as exc:
        return [str(exc)], warnings, 0, 0, False

    # NOT `if not images: return`. A report whose figures have all been removed while its manifest
    # still lists them is precisely a stale record, and returning early there would pass it in
    # silence -- the failure mode this whole tool exists to prevent, reproduced inside the tool.
    # Caught by its own test on first run.
    if not images and not manifest:
        return errors, warnings, 0, 0, False

    # A report that predates the rule and has not opted in is exempt from being ASKED for a source.
    # One that has a manifest is checked in full whatever its date.
    if not manifest and not manifest_required(d):
        return errors, warnings, 0, 0, True

    checked = 0
    unmapped = 0
    names = {i.name for i in images}

    for fig, src_rel in sorted(manifest.items()):
        if fig not in names:
            errors.append(f"{rel}/{MANIFEST} lists `{fig}`, which is not in the folder. "
                          f"A stale entry makes the manifest a record of a report that no "
                          f"longer exists; remove it or restore the figure.")
            continue
        src = ROOT / src_rel
        if not src.is_file():
            errors.append(f"{rel}/{fig}: its canonical source `{src_rel}` does not exist. "
                          f"A dead pointer reads as provenance and resolves to nothing.")
            continue
        if sha256(d / fig) != sha256(src):
            errors.append(
                f"{rel}/{fig} DIFFERS from its canonical source `{src_rel}`.\n"
                f"      The report embeds a stale copy. Regenerate the figure in its stem if it "
                f"needs changing, then re-copy it here and re-render the report: a PDF built from "
                f"a stale PNG is rebuilt stale every time.")
            continue
        checked += 1

    native = read_native(d / MANIFEST)
    missing = [i.name for i in images if i.name not in manifest and i.name not in native]
    unmapped = len(missing)
    if missing:
        shown = ", ".join(missing[:4]) + (f", +{len(missing) - 4} more" if len(missing) > 4 else "")
        msg = (f"{rel}: {unmapped} figure(s) with no entry in {MANIFEST}, so nothing verifies they "
               f"still match what they were copied from ({shown}). "
               f"`--init` maps the ones that are byte-identical copies; a report-native figure has "
               f"no canonical source and belongs in a comment line.")
        (errors if (strict_unmapped or manifest_required(d)) else warnings).append(msg)

    return errors, warnings, checked, unmapped, False


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("target", nargs="?", default=None,
                    help="a report folder, a report .md, a reports/ dir, or nothing for all")
    ap.add_argument("--init", action="store_true",
                    help="write figure_sources.tsv for the target report(s) by hash-matching")
    ap.add_argument("--staged", action="store_true",
                    help="check only reports with a staged file (pre-commit mode)")
    ap.add_argument("--strict-unmapped", action="store_true",
                    help="treat an unmapped figure as an ERROR rather than a warning")
    a = ap.parse_args(argv)

    if a.staged:
        try:
            out = subprocess.run(["git", "diff", "--cached", "--name-only", "-z"],
                                 cwd=ROOT, capture_output=True, text=True, check=True).stdout
        except (subprocess.CalledProcessError, FileNotFoundError):
            out = ""
        dirs = sorted({(ROOT / p).parent for p in out.split("\0")
                       if p and "/reports/" in p})
        dirs = [d for d in dirs if d.is_dir()]
    else:
        dirs = report_dirs_from(a.target)

    if a.init:
        for d in dirs:
            matched, total = init_manifest(d)
            rel = d.relative_to(ROOT) if str(d).startswith(str(ROOT)) else d
            if total:
                print(f"  {rel}/{MANIFEST}: {matched} of {total} image(s) matched")
                if matched < total:
                    print(f"    {total - matched} unmatched: either report-native (no canonical "
                          f"source) or ALREADY DRIFTED. Check before adding by hand.")
        return OK

    all_err: List[str] = []
    all_warn: List[str] = []
    n_checked = n_unmapped = n_reports = n_exempt = 0
    for d in dirs:
        errs, warns, checked, unmapped, exempt = check_report(
            d, strict_unmapped=a.strict_unmapped)
        if exempt:
            n_exempt += 1
            continue
        if checked or unmapped or errs:
            n_reports += 1
        all_err += errs
        all_warn += warns
        n_checked += checked
        n_unmapped += unmapped

    print(f"report figure freshness — {n_reports} report(s) in scope, "
          f"{n_checked} figure(s) verified against a canonical source, {n_unmapped} unmapped")
    if n_exempt:
        # Never silent: a backlog that vanishes from the output is a backlog nobody pays down.
        print(f"  [note] {n_exempt} report(s) predate {MANIFEST_REQUIRED_FROM} and are exempt from "
              f"declaring a source. Reported so the backlog stays visible; `--init` opts one in, "
              f"and any that already declares one is drift-checked in full.")

    for w in all_warn:
        print(f"  warn  {w}")
    for e in all_err:
        print(f"  ERROR {e}")

    if all_err:
        print(f"\n{len(all_err)} error(s). A report that embeds a stale figure shows its reader "
              f"something its own prose no longer describes.")
        return ERROR
    if all_warn:
        print(f"\n{len(all_warn)} warning(s): figures whose freshness is UNCHECKED, not figures "
              f"known to be fine. `--init` maps them.")
        return WARN
    if n_checked == 0:
        print("  (no figure in scope had a declared source, so nothing was actually verified)")
    else:
        print("✔ every mapped report figure matches its canonical source")
    return OK


if __name__ == "__main__":
    sys.exit(main())
