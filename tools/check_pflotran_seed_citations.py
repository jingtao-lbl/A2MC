#!/usr/bin/env python3
"""check_pflotran_seed_citations.py - verify every citation in the PFLOTRAN
curated seed RESOLVES.

PFLOTRAN-SPECIFIC BY DESIGN, and deliberately NOT `--model`-dispatched.
The citation grammar this enforces is a PFLOTRAN convention introduced with the
v0.2 seed rewrite; it has been exercised against exactly one adapter's seed.
Generalising it now would be speculative, and a `--model` flag would advertise a
portability that has not been earned. If a second adapter adopts the same
convention and the tool survives that contact, promote it then --
`tools/check_ecosim_rag_queries.py` is the precedent for a model-specific
checker living happily beside the model-generic ones.

The V2 curated-YAML validator (``tools/validate_curated_yaml.py``) checks that
parameter/output NAMES resolve and that cross-references cohere. It cannot check
whether the prose is TRUE. The PFLOTRAN v0.1 seed passed V2 cleanly (27/27 A,
13/13 B, 17/17 C) and was still ~20 % wrong
(``memory/dev_logs_adapterkitpflotran/20260801a``).

The rewrite contract's answer was a citation on every factual claim. This tool
is the mechanical half of enforcing that: it does NOT judge whether a claim is
true, but it does prove that every pointer the seed offers **points at something
that exists**, so a reviewer can check any claim in place rather than
re-deriving it. A dangling citation is a claim that cannot be audited, which is
the failure mode the rewrite exists to remove.

Citation grammar (as written in the seed's ``calibration_notes`` / comments)::

    [src: <file>:NNN]            source line, resolved under --source
    [src: <file>:NNN-MMM]        source line range
    [src: <file>:NNN, :MMM]      several lines in the same file
    [deck: <file>:NNN]           the model's real input deck, --deck
    [db: <file>:NNN]             an auxiliary input (database), --aux
    [log: <file>:NNN]            the model's own RUN LOG, --aux
    [data: ...]                  a MEASURED statistic - reported, not resolvable

The ``log`` kind earns its place: PFLOTRAN echoes every defaulted card into its
run log ("<mineral> SPECIFIC_SURFACE_AREA UNITS set to default value"), so the
log is direct RUNTIME evidence of how the reader interpreted a deck -- stronger
than reading the reader's source, because it is what actually happened.

What it checks
--------------
  1. every ``src``/``deck``/``db``/``log`` file exists under the given root
  2. every cited line number is within that file's length
  3. reports the citation DENSITY (claims are the unit that matters: the v0.1
     seed carried 8 file:line citations against the wiki's 2541)
  4. flags entries whose ``calibration_notes`` carry NO citation at all - the
     v0.1 error class, since uncited inference is what failed verification

``--show`` prints each cited line so a human can eyeball that the pointer lands
where the prose says it does. That eyeball pass is the part no tool can do.

Exit codes
----------
    0  PASS  - every citation resolves
    1  usage/path error
    2  unresolved citations, or uncited entries when --require-citations

Usage
-----
    python tools/check_pflotran_seed_citations.py \
        --source ~/…/PFLOTRAN_at_157a26f7/src/pflotran \
        --deck   ~/…/scenario1_miniLEO/pflotran.in \
        --aux    ~/…/scenario1_miniLEO/savannah_river.dat \
        --aux    ~/…/scenario1_miniLEO/pflotran.out \
        --require-citations

Add ``--show`` to print every cited line. DO THAT PASS: a citation that resolves
is not a citation that SUPPORTS its claim, and reading them caught four wrong
line numbers that both this checker and the V2 validator had passed.

Author: Jing Tao with Claude
"""

from __future__ import annotations

import argparse
import re
import sys
from collections import Counter
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import yaml

REPO = Path(__file__).resolve().parent.parent
DEFAULT_SEED = REPO / "models" / "pflotran" / "curated_seed.yaml"

# TWO GRAMMARS, because the PFLOTRAN seed itself uses both:
#
#   BRACKETED: [src: reaction_mineral.F90:562-564], [deck: pflotran.in:239]
#   BARE:      ... deck addresses at pflotran.in:574-583 ... in running prose
#
# Counting only the bracketed form missed 15 real pointers in this seed and let
# two unbracketed deck refs in `source:` fields go unchecked. The bracketed form
# is PREFERRED and is what --require-citations rewards, because it declares
# WHICH ARTIFACT the pointer is into; a bare ref is assumed to be source and
# falls back to a filename match against --deck/--aux before being reported
# unresolved.
_CITE_BLOCK = re.compile(r"\[(?P<kind>src|deck|db|log|data):\s*(?P<body>[^\]]+)\]")
_BARE_REF = re.compile(r"(?<![\[\w:])(?P<file>[\w./+-]+\.(?:F90|f90|in|dat|out))\s*:\s*(?P<lines>\d+(?:-\d+)?)")
# inside a block: "file.F90:12-34, :56" -> file + each line spec
_FILE_RE = re.compile(r"(?P<file>[\w./+-]+\.(?:F90|f90|in|dat|out|py|md))\s*:\s*(?P<lines>[\d\-]+)")
_EXTRA_LINE_RE = re.compile(r"(?<![\w.])[:,]\s*:(?P<line>\d+)")


class Citation:
    __slots__ = ("kind", "file", "start", "end", "where", "raw")

    def __init__(self, kind, file, start, end, where, raw):
        self.kind, self.file, self.start, self.end = kind, file, start, end
        self.where, self.raw = where, raw

    def __str__(self):
        span = f"{self.start}" if self.end == self.start else f"{self.start}-{self.end}"
        return f"[{self.kind}: {self.file}:{span}]"


def _iter_text(seed: dict) -> List[Tuple[str, str]]:
    """(location label, text) for every field a claim can hide in."""
    out: List[Tuple[str, str]] = []
    for section in ("categories", "mechanisms", "outputs", "parameters"):
        for name, body in (seed.get(section) or {}).items():
            if not isinstance(body, dict):
                continue
            for field in ("description", "calibration_notes", "notes", "source"):
                val = body.get(field)
                if isinstance(val, str) and val.strip():
                    out.append((f"{section}/{name}/{field}", val))
    return out


def parse_citations(label: str, text: str) -> List[Citation]:
    """One bracket may mix kinds, e.g.
    ``[deck: pflotran.in:22; src: pm_rt.F90:237-238]`` - a natural way to say
    "the deck turns it on HERE, the source implements it THERE". Split the body
    on ``;`` and let a leading ``kind:`` switch the kind for that segment."""
    cites: List[Citation] = []
    for m in _CITE_BLOCK.finditer(text):
        kind, body = m.group("kind"), m.group("body")
        if kind == "data":
            continue                                    # measured, not resolvable
        for segment in body.split(";"):
            seg_kind = kind
            sm = re.match(r"\s*(src|deck|db|log|data)\s*:", segment)
            if sm:
                seg_kind = sm.group(1)
                segment = segment[sm.end():]
            if seg_kind == "data":
                continue
            last_file: Optional[str] = None
            for fm in _FILE_RE.finditer(segment):
                last_file = fm.group("file")
                spec = fm.group("lines")
                start, _, end = spec.partition("-")
                s = int(start)
                e = int(end) if end else s
                cites.append(Citation(seg_kind, last_file, s, e, label, m.group(0)))
            if last_file:                               # trailing ", :1780" forms
                for em in _EXTRA_LINE_RE.finditer(segment):
                    n = int(em.group("line"))
                    cites.append(Citation(seg_kind, last_file, n, n, label, m.group(0)))

    # Bare `file.F90:NNN` refs OUTSIDE any bracket. Blank the bracketed spans
    # first so a bracketed citation is not also counted as a bare one.
    masked = _CITE_BLOCK.sub(lambda mm: " " * len(mm.group(0)), text)
    for bm in _BARE_REF.finditer(masked):
        spec = bm.group("lines")
        start, _, end = spec.partition("-")
        s = int(start)
        e = int(end) if end else s
        cites.append(Citation("src", bm.group("file"), s, e, label, bm.group(0)))
    return cites


def _resolve(cite: Citation, source: Optional[Path], deck: Optional[Path],
             aux: List[Path]) -> Optional[Path]:
    if cite.kind == "deck":
        if deck and deck.name == cite.file:
            return deck
        return None
    if cite.kind in ("db", "log"):
        for a in aux:
            if a.name == cite.file:
                return a
        return None
    if source:
        direct = source / cite.file
        if direct.is_file():
            return direct
        hits = list(source.rglob(cite.file))
        if len(hits) == 1:
            return hits[0]
    # A BARE ref is assumed to be source, but a seed's prose legitimately names
    # the deck or an aux file without a bracket ("deck addresses at x.in:574").
    # Fall back on a filename match before declaring it unresolved -- otherwise
    # the checker reports a false dangling citation for correct prose.
    if deck and deck.name == cite.file:
        return deck
    for a in aux:
        if a.name == cite.file:
            return a
    return None


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--yaml", type=Path, default=None,
                    help=f"default {DEFAULT_SEED.relative_to(REPO)}")
    ap.add_argument("--source", type=Path, help="model source dir for [src:]")
    ap.add_argument("--deck", type=Path, help="input deck for [deck:]")
    ap.add_argument("--aux", type=Path, action="append", default=[],
                    help="auxiliary input or run log for [db:]/[log:] (repeatable)")
    ap.add_argument("--show", action="store_true", help="print each cited line")
    ap.add_argument("--require-citations", action="store_true",
                    help="fail if any entry's notes carry no citation")
    args = ap.parse_args()

    seed_path = args.yaml or DEFAULT_SEED
    if not seed_path.is_file():
        print(f"ERROR: no seed at {seed_path}", file=sys.stderr)
        return 1
    seed = yaml.safe_load(seed_path.read_text())

    texts = _iter_text(seed)
    all_cites: List[Citation] = []
    uncited: List[str] = []
    for label, text in texts:
        cites = parse_citations(label, text)
        all_cites.extend(cites)
        if label.endswith(("/calibration_notes", "/notes")) and not cites:
            if "[data:" not in text:
                uncited.append(label)

    cache: Dict[Path, int] = {}
    bad: List[Tuple[Citation, str]] = []
    ok = 0
    print(f"Seed: {seed_path.relative_to(REPO)}")
    print(f"Citations found: {len(all_cites)}  "
          f"(across {len(texts)} claim-bearing fields)\n")

    for c in all_cites:
        path = _resolve(c, args.source, args.deck, args.aux)
        if path is None:
            bad.append((c, "file not found"))
            continue
        if path not in cache:
            cache[path] = sum(1 for _ in path.open(errors="replace"))
        n = cache[path]
        if c.start < 1 or c.end > n:
            bad.append((c, f"line out of range (file has {n} lines)"))
            continue
        ok += 1
        if args.show:
            lines = path.read_text(errors="replace").splitlines()
            print(f"  {c}  <- {c.where}")
            for i in range(c.start, min(c.end, c.start + 4) + 1):
                print(f"      {i:5d}| {lines[i-1].rstrip()}")

    by_kind = Counter(c.kind for c in all_cites)
    print(f"\nResolved: {ok}/{len(all_cites)}   by kind: {dict(by_kind)}")
    print(f"Distinct files cited: {len(cache)}")

    if uncited:
        print(f"\nUNCITED claim fields ({len(uncited)}) - the v0.1 error class:")
        for u in uncited:
            print(f"  - {u}")

    if bad:
        print(f"\nUNRESOLVED ({len(bad)}):")
        for c, why in bad:
            print(f"  {c}  [{why}]  <- {c.where}")
        return 2
    if uncited and args.require_citations:
        return 2
    print("\nPASS - every citation resolves.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
