#!/usr/bin/env python3
"""Keep incident detail in the dev logs and out of source docstrings.

THE RULE (`feedback_notes_go_to_dev_logs_not_source`): a docstring states what the code does and why
it is shaped that way. Dates, costs and post-mortems belong in the dev log, which is written to be
read as history and is where the DETAIL should be complete. A source file may cite that log; it
should not retell it.

WHAT THIS DOES **NOT** DO, and the measurement matters, because a checker that fires on a third of
the codebase gets switched off. Dated evidence in an inline comment is this repo's established and
useful style: 1,461 occurrences across 609 tracked `.py` and `.sh` files, almost all of them a single
clause attached to the line it justifies ("...which is how seven attributed commits got past this
hook on 2026-09-04"). Those are not touched. Two narrower signals are:

  1. AN OBSERVED ENVIRONMENT STATE, anywhere in a docstring or comment. A filesystem that is "97.6%
     full", or "39.05 of 40.00 GiB" used, is a measurement of a mutable world, so it is wrong the
     moment anything changes and it cannot be repaired by editing the code it documents. Measured
     across every tracked Python file: zero occurrences today, one before the commit that prompted
     this, so the signal is specific rather than merely quiet.

  2. A DATED NARRATIVE ADDED TO A MODULE DOCSTRING WITH NO POINTER TO WHERE THE DETAIL LIVES. Scoped
     to module docstrings, because that is where narrative accumulates, and to lines this commit
     ADDS, so the 201 pre-existing files that predate the convention never fire while new prose is
     held to it. Forty-two files already carry such a pointer, so this asks for an existing habit.

Neither signal says "delete the explanation". Both say: keep the rule in the docstring, put the
incident in the dev log, and name the log.

The account of the commit that prompted this, in full, is in
`memory/dev_logs_adapterkit/reflection/20260923e_Reflection_I_Never_Measured_The_Resources_I_Was_Spending.md`.

check-source-notes: allow - this file quotes the environment-state patterns it detects, as examples

Usage:
    python3 tools/check_source_notes.py --staged       # what the pre-commit hook runs
    python3 tools/check_source_notes.py <paths...>     # signal 1 only, on whole files

Exit: 0 clean, 1 a finding.

Author: Jing Tao with Claude
"""

import ast
import re
import subprocess
import sys
import tokenize
from io import StringIO

#: A measurement of a mutable environment. "39.05 of 40.00 GiB", "97.6% full", "0.95 GiB free".
ENV_STATE = re.compile(
    r"\b\d+(?:\.\d+)?\s+of\s+\d+(?:\.\d+)?\s*(?:GiB|GB|TiB|MB)\b"
    r"|\b\d{1,3}(?:\.\d+)?\s*%\s*(?:full|used|free)\b", re.I)
DATE = re.compile(r"\b20\d{2}-[01]\d-[0-3]\d\b")
#: A dev log, ana log, model log, reflection, or a bare log stem such as `20260923e_`.
POINTER = re.compile(r"memory/(?:dev_logs|ana_logs|model_logs)|/reflection/|\b20\d{6}[a-z]{1,3}_")

REMEDY = ("Move the incident to the dev log, where the detail belongs and should be COMPLETE, and "
          "leave the durable rule here. Cite the log by path or stem.")

#: A file that DOCUMENTS the pattern matches itself, which is every linter's problem with its own
#: definition file and its fixtures. The opt-out is per file, must carry a reason after the colon,
#: and every use is COUNTED in the output, so an exemption is visible rather than silent. It
#: suppresses signal 1 only: the dev-log pointer of signal 2 is asked of every file, including this
#: one.
ALLOW = re.compile(r"check-source-notes:\s*allow\s*[-:]\s*(\S.*)")


def _sh(*args):
    # 3.6-compatible: capture_output= and text= are 3.7+, and the pre-commit hook runs the system
    # python3, which is 3.6 here. The first version used them and CRASHED, which a caller reading
    # only the exit code would have read as a finding.
    p = subprocess.run(args, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                       universal_newlines=True)
    return p.stdout or ""


def staged_source():
    out = _sh("git", "diff", "--cached", "--name-only", "--diff-filter=ACM")
    return [p for p in out.split() if p.endswith((".py", ".sh"))]


def added_lines(path):
    """Lines this commit ADDS to `path`, so pre-existing prose is never judged."""
    out = _sh("git", "diff", "--cached", "-U0", "--", path)
    return [l[1:] for l in out.splitlines() if l.startswith("+") and not l.startswith("+++")]


def doc_and_comment_text(path):
    """(module docstring or '', every docstring and comment concatenated)."""
    try:
        src = open(path, errors="ignore").read()
    except OSError:
        return "", ""
    if path.endswith(".sh"):
        head, body = [], []
        for line in src.splitlines():
            s = line.strip()
            if s.startswith("#"):
                body.append(s.lstrip("#").strip())
                if not head or head[-1] != "":
                    head.append(s.lstrip("#").strip())
            elif s and head:
                head.append("")
        return "\n".join(head), "\n".join(body)
    chunks = []
    module_doc = ""
    try:
        tree = ast.parse(src)
        module_doc = ast.get_docstring(tree) or ""
        chunks.append(module_doc)
        for n in ast.walk(tree):
            if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                chunks.append(ast.get_docstring(n) or "")
    except SyntaxError:
        pass
    try:
        for tok in tokenize.generate_tokens(StringIO(src).readline):
            if tok.type == tokenize.COMMENT:
                chunks.append(tok.string.lstrip("#").strip())
    except Exception:
        pass
    return module_doc, "\n".join(c for c in chunks if c)


def check(paths, staged):
    findings, exempt = [], []
    for p in paths:
        module_doc, all_text = doc_and_comment_text(p)
        allowed = ALLOW.search(all_text)
        if allowed:
            exempt.append((p, allowed.group(1).strip()))

        # --- signal 1: an observed environment state, which decays ---
        for m in () if allowed else ENV_STATE.finditer(all_text):
            lo = max(0, m.start() - 60)
            findings.append(
                f"{p}: states an OBSERVED ENVIRONMENT STATE in a docstring or comment "
                f"-- ...{all_text[lo:m.end() + 30].strip()}...\n"
                f"      A measurement of a mutable world is wrong as soon as anything changes, and "
                f"editing this file cannot repair it. {REMEDY}")

        # --- signal 2: dated narrative ADDED to a module docstring, with nowhere to go for detail ---
        if staged and module_doc and DATE.search(module_doc) and not POINTER.search(module_doc):
            added = "\n".join(added_lines(p))
            if DATE.search(added):
                findings.append(
                    f"{p}: this commit adds a DATED passage to the module docstring, and that "
                    f"docstring names no dev log.\n"
                    f"      {REMEDY} An inline comment carrying one dated clause beside the line it "
                    f"justifies is fine and is not what this flags.")
    return findings, exempt


def main(argv=None):
    # A downstream copy adds the whole framework in one commit, so every file with a dated
    # passage reads as newly authored. This check is about what an AUTHOR is adding; nothing
    # was authored here. Skip, rather than reporting 92 findings nobody can act on.
    import os.path
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    from downstream import is_downstream
    from pathlib import Path as _P
    if is_downstream(_P(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))):
        print("check_source_notes: downstream copy (skip) — nothing here was authored in this tree")
        return 0

    argv = list(sys.argv[1:] if argv is None else argv)
    staged = "--staged" in argv
    paths = [a for a in argv if not a.startswith("-")]
    if staged:
        paths = staged_source()
    if not paths:
        print("check_source_notes: no source file to check")
        return 0
    findings, exempt = check(paths, staged)
    for f, why in exempt:
        print(f"  [exempt] {f}: signal 1 waived -- {why}")
    if findings:
        print(f"\n  {len(findings)} finding(s): incident detail belongs in the dev log, not in source.\n")
        for f in findings:
            print(f"  - {f}")
        return 1
    print(f"✔ check_source_notes: {len(paths)} source file(s) clean "
          f"(no environment-state assertion, no undocumented dated narrative)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
