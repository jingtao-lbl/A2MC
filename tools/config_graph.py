#!/usr/bin/env python
"""Who SETS and who READS an A2MC_* configuration variable — the repo's own config graph.

A2MC has a GraphRAG over the MODEL's source (FATES, EcoSIM, PFLOTRAN), and nothing at all over its
own configuration surface. That asymmetry cost real time on 2026-08-22: three consecutive wrong
diagnoses about `A2MC_N_SAMPLES`, each corrected by the PI, each settle-able by one query of the
kind this tool answers.

The failure mode it targets is specific. A variable's MEANING lives in its READERS, not in its
declaration or its name -- `A2MC_N_SAMPLES` reads as "the number of samples", the machine config
declares it with a default of 1000, and neither tells you that both samplers pass it to
`sample_sobol` AND `sample_lhs` while morris ignores it entirely. Searching where the symptom
appeared (a config file) answered a different question from the one that mattered (what consumes
this, and how).

    python tools/config_graph.py --var A2MC_N_SAMPLES     # one variable, fully
    python tools/config_graph.py --orphans                # read but never set, and vice versa
    python tools/config_graph.py --like N_SAMPLES         # candidate duplicate names

Enumeration is `git ls-files` (index-based), never a filesystem walk -- a hard requirement on this
machine's shared filesystems.

Author: Jing Tao with Claude
"""
from __future__ import annotations

import argparse
import re
import subprocess
import sys
from collections import defaultdict
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent

VAR = re.compile(r"\bA2MC_[A-Z0-9_]+\b")

#: A write. `export FOO=`, `FOO=`, or a shell default `FOO=${FOO:-x}`.
SET_SH = re.compile(r"^\s*(?:export\s+)?(A2MC_[A-Z0-9_]+)\s*=")
#: A read in shell: $FOO or ${FOO...}
READ_SH = re.compile(r"\$\{?(A2MC_[A-Z0-9_]+)")
#: A read in Python: os.environ.get("FOO"...) / os.environ["FOO"] / getenv("FOO"), and the repo's
#: OWN `_env("FOO", ...)` helper, which five scripts use 61 times between them.
#:
#: THE UNDER-DETECTION THIS FIXES. Without the `_env` alternative this tool reported every variable
#: read only through that helper as "SET but never READ -- dead, or read by something outside the
#: repo". Under-detection is the worst failure mode for a config graph, because the whole point is
#: to answer "what consumes this"; a confident "nothing" is worse than no answer. Caught 2026-08-23
#: when a newly added A2MC_ROUND_CONFIG reported read:0 in the same commit that demonstrably read
#: it -- the regenerated registry field could only have come from that read.
READ_PY = re.compile(r"""(?:environ(?:\.get)?\s*[\(\[]|getenv\s*\(|\b_env\s*\()\s*["'](A2MC_[A-Z0-9_]+)["']""")
#: A write in Python: os.environ["FOO"] = / os.environ.setdefault("FOO"
SET_PY = re.compile(r"""environ(?:\[["'](A2MC_[A-Z0-9_]+)["']\]\s*=|\.setdefault\(\s*["'](A2MC_[A-Z0-9_]+)["'])""")

#: Files that RECORD rather than DEFINE. A dev log quoting a variable is not a consumer, and
#: counting it as one is how a grep-based answer drowns in its own history.
RECORD_PREFIXES = ("memory/", "docs/", ".claude_memory/", "use_cases/")
RECORD_SUFFIXES = (".md", ".json", ".txt", ".yaml", ".yml", ".csv")


#: THE TOOL'S OWN TESTS MUST NOT POLLUTE ITS CENSUS. `tests/test_config_graph.py` defines fixture
#: variables (`A2MC_ORPHAN`, `A2MC_PYVAR`) whose entire purpose is to be read-but-never-set, and
#: they were being reported as two of the "42 orphans" -- a tool grading itself on its own props.
#: Measured 2026-08-22: 42 reported, 2 test-only, **40 genuine**, which is the number the project's
#: TODO already carried. The identical defect was fixed the same morning in pre-commit check (10),
#: which excludes `tests/` after firing 7 times on these same fixtures -- but only the HOOK was
#: fixed, not the tool it calls, so the tool kept reporting the inflated number.
TEST_PREFIXES = ("tests/",)


def tracked_files(include_tests: bool = False) -> list[str]:
    out = subprocess.run(["git", "ls-files"], cwd=REPO, capture_output=True, text=True, timeout=60)
    files = [f for f in out.stdout.splitlines() if f]
    if include_tests:
        return files
    return [f for f in files if not f.startswith(TEST_PREFIXES)]


def is_record(path: str) -> bool:
    """Documentation/state, not code. Kept separate rather than dropped -- provenance matters."""
    if path.endswith((".py", ".sh")):
        return path.startswith("use_cases/") and "/config/" not in path
    return path.endswith(RECORD_SUFFIXES) or path.startswith(RECORD_PREFIXES)


def scan(files: list[str]):
    """-> {var: {"set": [(path,line,text)], "read": [...], "record": [...]}}"""
    g: dict[str, dict[str, list]] = defaultdict(lambda: {"set": [], "read": [], "record": []})
    for rel in files:
        p = REPO / rel
        try:
            text = p.read_text(errors="ignore")
        except (OSError, UnicodeDecodeError):
            continue
        if "A2MC_" not in text:
            continue
        record = is_record(rel)
        py = rel.endswith(".py")
        for i, line in enumerate(text.splitlines(), 1):
            if "A2MC_" not in line:
                continue
            hit = (line.strip()[:150])
            if record:
                for v in set(VAR.findall(line)):
                    g[v]["record"].append((rel, i, hit))
                continue
            sets = set()
            if py:
                for m in SET_PY.finditer(line):
                    sets.add(m.group(1) or m.group(2))
                reads = set(READ_PY.findall(line))
            else:
                m = SET_SH.match(line)
                if m:
                    sets.add(m.group(1))
                reads = set(READ_SH.findall(line))
            for v in sets:
                g[v]["set"].append((rel, i, hit))
            # A shell default `FOO=${FOO:-x}` both sets and reads FOO; the set is what matters.
            for v in reads - sets:
                g[v]["read"].append((rel, i, hit))
    return g


def show_var(g, var: str, quiet: bool = False) -> int:
    e = g.get(var)
    if not e:
        print(f"✘ {var}: no occurrence anywhere in tracked files", file=sys.stderr)
        return 1
    print(f"=== {var}")
    for kind, label in (("set", "SET BY"), ("read", "READ BY")):
        rows = e[kind]
        print(f"  {label} ({len(rows)}):" if rows else f"  {label}: (none)")
        for rel, i, hit in rows:
            print(f"    {rel}:{i}")
            if not quiet:
                print(f"        {hit}")
    if e["record"] and not quiet:
        print(f"  mentioned in {len(e['record'])} record file(s) (logs/docs/state) — not consumers")
    # The two shapes worth flagging without being asked.
    if e["read"] and not e["set"]:
        print("  ⚠ READ but never SET in tracked files — relies on a default or the environment")
    if e["set"] and not e["read"]:
        print("  ⚠ SET but never READ — dead, or read by something outside the repo")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--var", help="show setters and readers for one variable")
    ap.add_argument("--like", help="variables whose name contains this substring (duplicate hunt)")
    ap.add_argument("--orphans", action="store_true",
                    help="variables read-but-never-set or set-but-never-read")
    ap.add_argument("--quiet", action="store_true", help="paths only, no source lines")
    ap.add_argument("--include-tests", action="store_true",
                    help="also scan tests/ (off by default: fixture variables there are "
                         "read-but-never-set BY DESIGN and inflate the orphan census)")
    a = ap.parse_args()

    g = scan(tracked_files(a.include_tests))

    if a.var:
        return show_var(g, a.var, a.quiet)

    if a.like:
        names = sorted(v for v in g if a.like.upper() in v)
        if not names:
            print(f"no variable name contains {a.like!r}", file=sys.stderr)
            return 1
        print(f"=== {len(names)} variable(s) whose name contains {a.like!r}")
        print("    (two names for ONE quantity is the shape that cost a day on 2026-08-22)")
        for v in names:
            print(f"  {v:34s} set:{len(g[v]['set']):2d}  read:{len(g[v]['read']):2d}")
        return 0

    if a.orphans:
        unset = sorted(v for v, e in g.items() if e["read"] and not e["set"])
        unread = sorted(v for v, e in g.items() if e["set"] and not e["read"])
        print(f"=== READ but never SET ({len(unset)}) — each relies on a default")
        for v in unset:
            print(f"  {v:34s} read in {len(g[v]['read'])} place(s)")
        print(f"\n=== SET but never READ ({len(unread)}) — dead, or consumed outside the repo")
        for v in unread:
            print(f"  {v:34s} set in {len(g[v]['set'])} place(s)")
        return 0

    print(f"{len(g)} A2MC_* variables in tracked files. Use --var / --like / --orphans.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
