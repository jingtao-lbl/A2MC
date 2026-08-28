#!/usr/bin/env python3
"""Does any LIVE doc still make a claim we have retired?

WHY THIS EXISTS. Three times in two days a sweep reported the documentation surface fully
enumerated and it was not, every time because `git grep` was asked for the wrong shape of the same
claim:

  1. grepped for the COMMAND (`source a2mc_config.sh`) and missed the two rules that state the
     contract in prose without naming a file;
  2. grepped for the PROSE (`source both`) and missed `Source **both** before every run.`, where
     the markdown emphasis sits INSIDE the phrase;
  3. and each time the miss was invisible, because a grep that finds nothing looks exactly like a
     surface that is clean.

So this tool does two things a bare grep cannot. It NORMALISES before matching (emphasis, code
ticks, and `_`-vs-space are removed, in both directions), and it takes a REGISTRY of retired claims
with their alternate phrasings, so a claim is written down once and re-checked forever instead of
being re-derived from memory by whoever next edits a doc.

    python tools/check_doc_claims.py                     # every registered claim, whole live surface
    python tools/check_doc_claims.py --staged            # only files staged for commit
    python tools/check_doc_claims.py --pattern 'foo bar' # ad-hoc: does any live doc say this?

Exit 0 clean, 1 on a hit, 2 on a usage error.

WHAT IS NOT SCANNED, and why it must not be. A dev log, an ana log, the changelog and a dated
`docs/NN_*.md` plan all record what was true WHEN WRITTEN; rewriting them falsifies them. A skill's
`## Changelog` section is the same thing one level down -- an entry saying "this file used to say X"
legitimately quotes X forever. Both are excluded structurally rather than by allow-listing every
instance, because the alternative is a checker that is permanently red and therefore unread.

Author: Jing Tao with Claude
"""
from __future__ import annotations

import argparse
import pathlib
import re
import subprocess
import sys

try:
    import yaml
except ImportError:                                          # pragma: no cover - env-dependent
    print("check_doc_claims: pyyaml required", file=sys.stderr)
    sys.exit(2)

ROOT = pathlib.Path(__file__).resolve().parents[1]
REGISTRY = ROOT / "tools" / "doc_claims.yaml"

# How far into a file a retired/superseded banner must appear to count. A banner is a
# HEADER, not something buried on line 300 -- bounding it stops a passing mention deep in a
# live document from silently switching the whole file off.
BANNER_LINES = 12

# Markdown emphasis and code ticks break a phrase for a literal matcher without changing what a
# reader sees. `~` is strikethrough. `_` is BOTH italic markup and load-bearing inside identifiers
# (`a2mc_config.sh`), so it is handled by matching against two variants rather than by guessing.
_STRIP = str.maketrans("", "", "*`~")


def variants(line: str) -> tuple[str, str]:
    """The two normalised forms of a line: emphasis stripped, and additionally `_` as a space.

    Matching against both means `source **both** config files` and `source_both_config_files` are
    each reachable, without merging `a2mc_config.sh` into `a2mcconfig.sh` and losing it.
    """
    flat = re.sub(r"\s+", " ", line.translate(_STRIP)).strip().lower()
    return flat, re.sub(r"\s+", " ", flat.replace("_", " ")).strip()


def git_files(staged: bool) -> list[str]:
    """Enumerate from git, never the disk.

    `--cached --others --exclude-standard` is this BRANCH's view plus files not yet added, so a
    doc written this session is covered and a gitignored stray never is
    (feedback_a_gate_must_measure_the_branch_not_the_disk).
    """
    cmd = (["git", "diff", "--cached", "--name-only", "--diff-filter=ACMR"] if staged
           else ["git", "ls-files", "--cached", "--others", "--exclude-standard"])
    out = subprocess.run(cmd, capture_output=True, text=True, cwd=ROOT, check=True).stdout.split()
    return sorted(f for f in out if f.endswith((".md", ".sh", ".py")))


def _glob_re(g: str) -> re.Pattern:
    """Translate a path glob to a regex where `**` really means ANY DEPTH.

    `pathlib.PurePath.match` treats `**` as a single component, so `use_cases/*/reports/**` did NOT
    match `use_cases/C/reports/D/r.md` -- the exclusion looked present and was inert. Found while
    seeding the registry, when 35 pre-2026-08-24 reports were reported as violations of a rule they
    predate. Translate explicitly instead of trusting a matcher's dialect.
    """
    out, i = [], 0
    while i < len(g):
        if g.startswith("**/", i):
            out.append("(?:.*/)?"); i += 3
        elif g.startswith("**", i):
            out.append(".*"); i += 2
        elif g[i] == "*":
            out.append("[^/]*"); i += 1
        elif g[i] == "?":
            out.append("[^/]"); i += 1
        elif g[i] == "[":                       # a character class passes through verbatim --
            j = g.index("]", i) + 1             # escaping it made `docs/[0-9][0-9]_*.md` inert
            out.append(g[i:j]); i = j
        else:
            out.append(re.escape(g[i])); i += 1
    return re.compile("^" + "".join(out) + "$")


def excluded(rel: str, globs: list[str]) -> bool:
    return any(_glob_re(g).match(rel) for g in globs)


def scan_file(path: pathlib.Path, claims: list[dict], stop_headings: list[str],
              rel_for_scope: str = "", retired_markers: tuple[str, ...] = ()) -> list[tuple]:
    """Report (line_no, claim_id, raw_line) for each un-allowed hit.

    Scanning STOPS at a stop-heading (a skill's `## Changelog`), because everything below it is a
    record of what the file used to say.

    The whole file is SKIPPED when its opening carries a retired/superseded banner. That makes the
    banner load-bearing rather than decorative: a document that says "this is history, read X
    instead" is history, and its reader is told so in the document rather than by this registry's
    exclude list -- which they never see.
    """
    try:
        text = path.read_text(errors="replace")
    except (OSError, UnicodeDecodeError):
        return []
    if retired_markers:
        head = " ".join(text.splitlines()[:BANNER_LINES]).lower()
        if any(m in head for m in retired_markers):
            return []
    hits = []
    for i, raw in enumerate(text.splitlines(), 1):
        head = raw.strip().lower().rstrip(":")
        if any(head == h for h in stop_headings):
            break
        flat, spaced = variants(raw)
        if not flat:
            continue
        for c in claims:
            if c["_only"] and not any(_glob_re(g).match(rel_for_scope) for g in c["_only"]):
                continue
            if any(re.search(p, flat) or re.search(p, spaced) for p in c["_pat"]):
                if any(re.search(a, flat) or re.search(a, spaced) for a in c["_allow"]):
                    continue
                hits.append((i, c["id"], raw.strip()))
                break
    return hits


def load_registry(path: pathlib.Path,
                  ad_hoc: list[str] | None) -> tuple[list[dict], list[str], list[str], list[str]]:
    if ad_hoc:
        claims = [{"id": "ad-hoc", "why": "supplied on the command line",
                   "_pat": [re.escape(p.lower()) for p in ad_hoc], "_allow": [], "_only": []}]
        reg = yaml.safe_load(path.read_text()) if path.is_file() else {}
        return (claims, reg.get("exclude_globs", []), reg.get("stop_headings", []),
                reg.get("retired_markers", []))
    reg = yaml.safe_load(path.read_text())
    claims = []
    for c in reg["claims"]:
        c["_pat"] = [p.lower() for p in c["patterns"]]
        c["_allow"] = [a.lower() for a in c.get("allow", [])]
        c["_only"] = c.get("only", [])          # empty = every scanned file
        claims.append(c)
    return (claims, reg.get("exclude_globs", []), reg.get("stop_headings", []),
            reg.get("retired_markers", []))


def main(argv=None) -> int:
    global ROOT                       # git_files() and the path joins below read it
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--staged", action="store_true", help="only files staged for commit")
    ap.add_argument("--pattern", action="append", metavar="TEXT",
                    help="ad-hoc claim (repeatable); skips the registry")
    ap.add_argument("--registry", default=str(REGISTRY))
    ap.add_argument("--root", default=str(ROOT), help=argparse.SUPPRESS)
    args = ap.parse_args(argv)

    ROOT = pathlib.Path(args.root).resolve()
    reg_path = pathlib.Path(args.registry)
    if not reg_path.is_absolute():
        reg_path = ROOT / reg_path
    if not args.pattern and not reg_path.is_file():
        print(f"check_doc_claims: no registry at {reg_path}", file=sys.stderr)
        return 2

    claims, ex_globs, stop_headings, retired_markers = load_registry(reg_path, args.pattern)
    stop_headings = [h.lower().rstrip(":") for h in stop_headings]
    retired_markers = tuple(m.lower() for m in retired_markers)

    files = [f for f in git_files(args.staged) if not excluded(f, ex_globs)]
    all_hits = []
    for rel in files:
        for ln, cid, raw in scan_file(ROOT / rel, claims, stop_headings, rel,
                                      retired_markers):
            all_hits.append((rel, ln, cid, raw))

    label = "ad-hoc pattern" if args.pattern else f"{len(claims)} registered claim(s)"
    if not all_hits:
        print(f"✔ doc claims: {label} — no live doc still says it "
              f"({len(files)} file(s) scanned)")
        return 0

    print(f"✘ doc claims: {len(all_hits)} hit(s) across {len({h[0] for h in all_hits})} file(s)\n")
    by_claim: dict[str, list] = {}
    for rel, ln, cid, raw in all_hits:
        by_claim.setdefault(cid, []).append((rel, ln, raw))
    for cid, rows in by_claim.items():
        why = next((c.get("why", "") for c in claims if c["id"] == cid), "")
        print(f"  [{cid}] {why}")
        for rel, ln, raw in rows:
            print(f"      {rel}:{ln}: {raw[:150]}")
        print()
    print("Each line above states something this repo no longer does. Update it, or -- if the text")
    print("is legitimately historical -- exclude its path or add an `allow:` pattern in the registry.")
    return 1


if __name__ == "__main__":
    sys.exit(main())
