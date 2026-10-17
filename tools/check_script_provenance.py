#!/usr/bin/env python3
"""A new script in a phase folder names the case template it came from, or says there was none.

visibility: public

WHY. The three-tier rule says a phase starts from the case's template in `use_cases/<Case>/scripts/`,
copies it into `memory/phase_results/{stem}/` and adapts it there. Nothing recorded whether that
happened, so a script written from scratch beside a template that already did the job looked exactly
like a legitimate first use. `check_case_script_tier.py` sees only byte-identical duplicates, after
the fact. This makes the choice explicit at the moment the script is added: its docstring (a shell
script's header comment) carries ONE line

    Template: scripts/<name>.py          an adapted copy of that case script template
    Template: case_template/<name>       an adapted copy of one of the case's run files (a launcher)
    Template: none (first use)           written here because no template covers it

and the line is checked:

  * a NEW phase script with neither the line nor byte-identity to a template is reported;
  * the named file must exist in the case's `scripts/` or `case_template/` (a bare name is looked
    up in `scripts/` first);
  * `Template: none` is refused when the case has a template or run file of the SAME file name,
    since that is a copy whose line was never updated, or a rewrite of something that exists.

An UNEDITED copy needs no line: byte-identity to a file in either folder is its provenance. Archived run files
(`run_tracking/`, `submit_scripts/`) are records, not scripts written for the phase, and are skipped.

SCOPE. Only scripts ADDED in the commit (`--staged`), so nothing written before the rule is
re-litigated; `--all` audits every phase script and reports, for a deliberate review.

    python3 tools/check_script_provenance.py --staged | --all | FILE ...

Exit 0 clean, 1 a violation (blocking in pre-commit check 33).

Author: Jing Tao with Claude on Perlmutter
"""
from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PHASE_SCRIPT = re.compile(r"^use_cases/([^/]+)/memory/phase_results/.+\.(py|sh)$")
ARCHIVES = ("/run_tracking/", "/submit_scripts/")
LINE = re.compile(r"^\s*(?:#\s*)?Template:\s*(\S.*?)\s*$", re.M)
HEAD_LINES = 60
TIERS = ("scripts", "case_template")


def declared(path: Path) -> str | None:
    """The value of the first `Template:` line in the file's opening lines, or None."""
    try:
        head = "\n".join(path.read_text(errors="replace").splitlines()[:HEAD_LINES])
    except OSError:
        return None
    m = LINE.search(head)
    return m.group(1) if m else None


def judge(path: Path, root: Path = ROOT) -> str | None:
    """A problem with this phase script's provenance, or None when it is stated and true."""
    rel = path.resolve().relative_to(root.resolve()).as_posix()
    m = PHASE_SCRIPT.match(rel)
    if not m or any(a in "/" + rel for a in ARCHIVES):
        return None
    case = root / "use_cases" / m.group(1)
    tiers = [case / t for t in TIERS if (case / t).is_dir()]
    try:
        body = path.read_bytes()
    except OSError:
        return None
    for d in tiers:
        for t in d.iterdir():
            if t.is_file() and t.suffix == path.suffix and t.read_bytes() == body:
                return None                       # an unedited copy: identity is its provenance
    value = declared(path)
    if value is None:
        return (f"{rel}: no `Template:` line. Name what it was adapted from (`Template: scripts/<name>` "
                f"or `Template: case_template/<name>`), or write `Template: none (first use)`")
    if value.lower().startswith("none"):
        twins = [f"{d.name}/{path.name}" for d in tiers if (d / path.name).is_file()]
        if twins:
            return (f"{rel}: says `Template: none`, but the case has {twins[0]} of the same name; "
                    f"name it, or explain the rewrite in the docstring and rename")
        return None
    name = value.split()[0].strip("`'\"")
    for t in TIERS:                                # strip a use_cases/<Case>/ or bare tier prefix
        if f"/{t}/" in name:
            return None if (case / t / name.split(f"/{t}/", 1)[-1]).is_file() else \
                f"{rel}: `Template: {value}` names no file in use_cases/{m.group(1)}/{t}/"
        if name.startswith(t + "/"):
            return None if (case / name).is_file() else \
                f"{rel}: `Template: {value}` names no file in use_cases/{m.group(1)}/{t}/"
    if any((case / t / name).is_file() for t in TIERS):
        return None
    return f"{rel}: `Template: {value}` names no file in use_cases/{m.group(1)}/scripts/ or case_template/"


def staged_added(root: Path = ROOT) -> list[Path]:
    names = subprocess.run(["git", "-C", str(root), "diff", "--cached", "--name-only",
                            "--diff-filter=A"], capture_output=True, text=True).stdout.split()
    return [root / n for n in names if PHASE_SCRIPT.match(n)]


def all_phase_scripts(root: Path = ROOT) -> list[Path]:
    names = subprocess.run(["git", "-C", str(root), "ls-files", "--", "use_cases/*/memory/phase_results/*"],
                           capture_output=True, text=True).stdout.split()
    return [root / n for n in names if PHASE_SCRIPT.match(n)]


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("files", nargs="*", type=Path)
    ap.add_argument("--staged", action="store_true", help="phase scripts ADDED in the staged diff")
    ap.add_argument("--all", action="store_true", help="audit every tracked phase script")
    a = ap.parse_args(argv)
    files = [f if f.is_absolute() else ROOT / f for f in a.files]
    if a.staged:
        files += staged_added()
    if a.all:
        files += all_phase_scripts()
    problems = [p for f in files if f.is_file() for p in [judge(f)] if p]
    if not problems:
        print(f"check_script_provenance: {len(files)} phase script(s) checked, provenance stated")
        return 0
    for p in problems:
        print(f"check_script_provenance: {p}")
    print("  Read the case's template index (use_cases/<Case>/scripts/README.md) before writing a "
          "phase script; the three-tier rule is in each phase skill's 'Scripts' section.")
    return 1


if __name__ == "__main__":
    sys.exit(main())
