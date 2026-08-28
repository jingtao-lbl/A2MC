#!/usr/bin/env python3
"""validate_wiki_vs_source.py - Generic wiki-vs-source validator (adapter-kit V1).

Model-agnostic sibling of tools/codebase_wiki_validator.py (the FATES-shaped
original, which this file does NOT modify -- the adapter-kit branch is ADDITIVE,
per docs/38). It scans a model's codebase wiki and checks that every cited source
file and every referenced routine actually exists in the model's source tree.

Where the FATES validator hardcodes `.F90` scanning and Fortran routine grammar,
this validator dispatches ALL source-location knowledge through the model's
`ModelSpec` (loaded via `--model <name>`):

    spec.source_extensions     -> which files are "source" (e.g. (".F90", ".f90"))
    spec.routine_decl_patterns -> regexes that declare a routine in source
    spec.module_file_pattern   -> pattern for module-file mentions in wiki text

So it works for `--model ecosim` today and structurally for `--model fates`
(or any future adapter) with no code change.

Checks (reported per wiki page AND in aggregate):
    A. File-citation existence   -- does each cited `<path>.<ext>:<line>` file exist?
    B. Line-bound validity        -- is the cited line within the file's length?
    C. Routine-reference presence -- do referenced routines appear as declarations?
    D. Module-file presence       -- do `*Mod.<ext>` mentions exist in source?

Each page and the whole wiki get a Green / Yellow / Red band:
    Green  >= 90% pass   Yellow  70-90%   Red  < 70%

Read-only on all inputs; only writes the output Markdown report (if --output).

Usage
-----
    ~/a2mc_env/bin/python tools/validate_wiki_vs_source.py \\
        --model ecosim \\
        --wiki docs/ecosim-knowledge-base/ecosim-codebase-wiki-2dea74d9 \\
        --source ~/EcoSIM \\
        --output docs/a2mc_reference/wiki_source_validation_ecosim.md

Exit code: 0 = Green/Yellow, 1 = Red or a fatal input error.

Author: Jing Tao with Claude
"""

from __future__ import annotations

import argparse
import importlib
import re
import sys
from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))
TOOLS_DIR = REPO_ROOT / "tools"
if str(TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(TOOLS_DIR))

# Reuse the FATES validator's generic, language-neutral helpers verbatim.
# (These carry no FATES-specific assumptions: a wiki corpus loader, the
#  Green/Yellow/Red result container, the routine-name blacklist, and the
#  markdown table + colour helpers.)
import codebase_wiki_validator as _cwv  # noqa: E402
from codebase_wiki_validator import (  # noqa: E402
    DimensionResult,
    ROUTINE_BLACKLIST,
    WikiCorpus,
    _table,
    color_for,
    load_wiki,
)


# =============================================================================
# Spec loading (the generic dispatch point)
# =============================================================================

def load_spec(model: str):
    """Return the `ModelSpec` for `model`, loaded from `models/<model>/`.

    Primary path: import the adapter package (which registers its backend) and
    read the spec off the registry -- exactly how framework code reaches a model.
    Fallback: import `models/<model>/spec.py` directly and pick out the single
    `ModelSpec` instance (covers adapters whose backend import is incomplete).
    """
    try:
        importlib.import_module(f"models.{model}")
        from models import registry
        return registry.get_model(model).spec
    except Exception as primary_err:  # noqa: BLE001
        try:
            from models.base import ModelSpec
            spec_mod = importlib.import_module(f"models.{model}.spec")
            for val in vars(spec_mod).values():
                if isinstance(val, ModelSpec):
                    return val
        except Exception:  # noqa: BLE001
            pass
        raise SystemExit(
            f"ERROR: could not load ModelSpec for --model {model!r}: {primary_err}"
        )


# =============================================================================
# Spec-driven regex construction
# =============================================================================

@dataclass
class Patterns:
    """Compiled regexes derived from the model's ModelSpec."""
    cite_paren: re.Pattern
    cite_bare: re.Pattern
    module_file: re.Pattern
    routine_decls: List[re.Pattern]


def build_patterns(spec) -> Patterns:
    exts = spec.source_extensions or (".F90", ".f90")
    ext_alt = "|".join(re.escape(e) for e in exts)
    # Parenthesised citation: "(subdir/File.F90:123"
    cite_paren = re.compile(r"\(([A-Za-z0-9_/\-]+(?:" + ext_alt + r")):(\d+)")
    # Bare citation: "subdir/File.F90:123" or "File.F90:123"
    cite_bare = re.compile(
        r"(?<![\w/])([A-Za-z0-9_][A-Za-z0-9_/\-]*(?:" + ext_alt + r")):(\d+)"
    )
    module_file = re.compile(r"\b(" + (spec.module_file_pattern or r"\w+Mod\.F90") + r")")
    routine_decls = [
        re.compile(p, re.IGNORECASE | re.MULTILINE)
        for p in (spec.routine_decl_patterns or ())
    ]
    return Patterns(cite_paren, cite_bare, module_file, routine_decls)


# Fortran generic-interface declaration: `interface endrun`. A wiki often
# references the public interface name, not its underlying specific procedures,
# so interface names count as declared routines. Only used when the model's
# source extensions include a Fortran extension (see build_source_index).
_IFACE_RE = re.compile(
    r"^\s*(?:abstract\s+)?interface\s+([A-Za-z][A-Za-z0-9_]*)\s*$",
    re.IGNORECASE | re.MULTILINE,
)
_FORTRAN_EXTS = {".f90", ".f", ".f77", ".f95", ".f03", ".f08"}

# Well-known language intrinsics that appear in routine context in a wiki but
# are never declared in source. Supplements the FATES ROUTINE_BLACKLIST (which
# we import read-only and must not edit; adapter-kit is additive per docs/38).
_INTRINSIC_SUPPLEMENT = {
    "command_argument_count", "get_command_argument", "get_environment_variable",
    "date_and_time", "system_clock", "cpu_time", "random_number", "random_seed",
    "move_alloc", "c_loc", "c_f_pointer", "execute_command_line",
}

# Backtick routine-reference extraction (language-neutral; mirrors the FATES
# validator's high-precision candidate patterns). A backticked identifier is
# treated as a routine reference only if it is a call form `foo()` or is
# preceded by a routine keyword (call/subroutine/function/routine/invokes).
_PAT_CALL = re.compile(r"`([A-Za-z][A-Za-z0-9_]*)\s*\(\s*\)`?")
_PAT_CALL2 = re.compile(r"`([A-Za-z][A-Za-z0-9_]*)`\s*\(\s*\)")
_PAT_KW = re.compile(
    r"\b(?:call|calls?\s+to|invokes?|invoked\s+by|subroutine|function|"
    r"routine|called\s+(?:from|by))\s+`([A-Za-z][A-Za-z0-9_]*)`",
    re.IGNORECASE,
)


def extract_routine_refs(text: str) -> Counter:
    """Routine identifiers referenced in one wiki page (Counter name->count)."""
    counter: Counter = Counter()
    for pat in (_PAT_CALL, _PAT_CALL2, _PAT_KW):
        for m in pat.finditer(text):
            ident = m.group(1)
            low = ident.lower()
            if len(ident) < 4 or low in ROUTINE_BLACKLIST \
                    or low in _INTRINSIC_SUPPLEMENT:
                continue
            counter[ident] += 1
    return counter


# =============================================================================
# Source index (spec-driven extensions)
# =============================================================================

@dataclass
class SourceIndex:
    rel_paths: Set[str] = field(default_factory=set)
    by_basename: Dict[str, List[str]] = field(default_factory=dict)
    line_counts: Dict[str, int] = field(default_factory=dict)
    declared_routines: Set[str] = field(default_factory=set)  # lowercased

    def has_path(self, rel: str) -> bool:
        return rel in self.rel_paths

    def has_basename(self, base: str) -> bool:
        return base in self.by_basename

    def resolve_candidates(self, path: str) -> List[str]:
        if self.has_path(path):
            return [path]
        base = path.rsplit("/", 1)[-1]
        return list(self.by_basename.get(base, []))


def build_source_index(source_root: Path, spec, pats: Patterns) -> SourceIndex:
    """Walk the source tree collecting files (by spec.source_extensions),
    their line counts, and the global set of declared routine names."""
    idx = SourceIndex()
    exts = {e.lower() for e in (spec.source_extensions or (".F90", ".f90"))}
    scan_interfaces = bool(exts & _FORTRAN_EXTS)
    for p in source_root.rglob("*"):
        if not p.is_file() or p.suffix.lower() not in exts:
            continue
        try:
            rel = str(p.relative_to(source_root)).replace("\\", "/")
        except ValueError:
            continue
        idx.rel_paths.add(rel)
        idx.by_basename.setdefault(p.name, []).append(rel)
        try:
            text = p.read_text(encoding="utf-8", errors="replace")
        except Exception:
            idx.line_counts[rel] = 0
            continue
        idx.line_counts[rel] = text.count("\n") + (0 if text.endswith("\n") else 1)
        for rpat in pats.routine_decls:
            for m in rpat.finditer(text):
                if m.groups():
                    idx.declared_routines.add(m.group(1).lower())
        if scan_interfaces:
            for m in _IFACE_RE.finditer(text):
                idx.declared_routines.add(m.group(1).lower())
    return idx


# =============================================================================
# Per-page validation
# =============================================================================

@dataclass
class PageResult:
    page: str
    file_pass: int = 0
    file_total: int = 0
    line_pass: int = 0
    line_total: int = 0
    routine_pass: int = 0
    routine_total: int = 0
    missing_files: List[str] = field(default_factory=list)       # "path:line"
    overshoot_lines: List[Tuple[str, int, int]] = field(default_factory=list)
    missing_routines: List[Tuple[str, int]] = field(default_factory=list)
    external_routines: List[Tuple[str, int]] = field(default_factory=list)

    @property
    def checked(self) -> int:
        return self.file_total + self.routine_total

    @property
    def passed(self) -> int:
        return self.file_pass + self.routine_pass

    @property
    def fraction(self) -> float:
        return (self.passed / self.checked) if self.checked else 1.0

    @property
    def band(self) -> str:
        f = self.fraction
        if f >= 0.90:
            return "Green"
        if f >= 0.70:
            return "Yellow"
        return "Red"


def find_page_citations(text: str, pats: Patterns) -> List[Tuple[str, int]]:
    seen: Set[Tuple[str, int]] = set()
    out: List[Tuple[str, int]] = []
    for rex in (pats.cite_paren, pats.cite_bare):
        for m in rex.finditer(text):
            key = (m.group(1), int(m.group(2)))
            if key not in seen:
                seen.add(key)
                out.append(key)
    return out


def external_sets(spec) -> Tuple[Set[str], List[re.Pattern]]:
    """Externals declared by the model's ModelSpec.

    A model built ON a framework (PFLOTRAN on PETSc, ATS on Amanzi) legitimately
    cites symbols and headers that do NOT live in its own source tree. Without
    classification every one is reported "unresolved", and that noise is what
    buries a genuine fabrication. Self-contained models (EcoSIM, FATES) declare
    nothing here, so both sets are empty and behaviour is unchanged.
    """
    syms = {x.lower() for x in (getattr(spec, "external_symbol_names", ()) or ())}
    mods = [re.compile(x) for x in (getattr(spec, "external_module_patterns", ()) or ())]
    return syms, mods


def validate_page(page: str, text: str, source: SourceIndex,
                  pats: Patterns, ext_syms: Set[str] = frozenset()) -> PageResult:
    res = PageResult(page=page)

    # A/B: file-citation existence + line bounds
    for path, line in find_page_citations(text, pats):
        res.file_total += 1
        cands = source.resolve_candidates(path)
        if cands:
            res.file_pass += 1
            res.line_total += 1
            max_lines = max(source.line_counts.get(c, 0) for c in cands)
            if line <= max_lines:
                res.line_pass += 1
            else:
                res.overshoot_lines.append((f"{path}:{line}", max_lines,
                                            line - max_lines))
        else:
            res.missing_files.append(f"{path}:{line}")

    # C: routine references
    for name, count in extract_routine_refs(text).items():
        res.routine_total += 1
        if name.lower() in source.declared_routines:
            res.routine_pass += 1
        elif name.lower() in ext_syms:
            # Declared-external (framework) symbol -- expected, not a fabrication.
            res.routine_pass += 1
            res.external_routines.append((name, count))
        else:
            res.missing_routines.append((name, count))

    return res


# =============================================================================
# Aggregate module-file check (whole wiki)
# =============================================================================

def validate_module_files(corpus: WikiCorpus, source: SourceIndex,
                          pats: Patterns,
                          ext_mods: List[re.Pattern] = ()) -> DimensionResult:
    result = DimensionResult()
    mentions: Set[str] = set()
    for text in corpus.files.values():
        for m in pats.module_file.finditer(text):
            mentions.add(m.group(1))
    for mod in sorted(mentions):
        result.total += 1
        if source.has_basename(mod) or any(p.search(mod) for p in ext_mods):
            result.pass_count += 1
        else:
            origin = _cwv.find_first_origin(corpus, mod)
            result.rows.append((mod, origin))
    return result


# =============================================================================
# Report
# =============================================================================

def band_for(fraction: float) -> str:
    if fraction >= 0.90:
        return "Green"
    if fraction >= 0.70:
        return "Yellow"
    return "Red"


def overall_band(file_frac: float, routine_frac: float,
                 line_frac: float, module_frac: float) -> str:
    bands = [band_for(f) for f in (file_frac, routine_frac, line_frac, module_frac)]
    if all(b == "Green" for b in bands):
        return "Green"
    if any(b == "Red" for b in bands):
        return "Red"
    return "Yellow"


def build_report(model: str, wiki_root: Path, source_root: Path,
                 spec, corpus: WikiCorpus, source: SourceIndex,
                 pages: List[PageResult], module_dim: DimensionResult) -> Tuple[str, str, dict]:
    file_pass = sum(p.file_pass for p in pages)
    file_total = sum(p.file_total for p in pages)
    line_pass = sum(p.line_pass for p in pages)
    line_total = sum(p.line_total for p in pages)
    rout_pass = sum(p.routine_pass for p in pages)
    rout_total = sum(p.routine_total for p in pages)

    file_frac = file_pass / file_total if file_total else 1.0
    line_frac = line_pass / line_total if line_total else 1.0
    rout_frac = rout_pass / rout_total if rout_total else 1.0
    mod_frac = module_dim.fraction

    verdict = overall_band(file_frac, rout_frac, line_frac, mod_frac)

    counts = {
        "file": (file_pass, file_total, band_for(file_frac)),
        "line": (line_pass, line_total, band_for(line_frac)),
        "routine": (rout_pass, rout_total, band_for(rout_frac)),
        "module": (module_dim.pass_count, module_dim.total, module_dim.status),
        "verdict": verdict,
    }

    out: List[str] = [
        f"# Wiki-Source Validation ({model}): {wiki_root.name} vs {source_root.name}",
        "",
        f"**Generated:** {datetime.utcnow().isoformat(timespec='seconds')}Z",
        "",
        f"**Model:** `{model}`  (source extensions: "
        f"{', '.join(spec.source_extensions)})",
        f"**Wiki:** `{wiki_root}`",
        f"**Source:** `{source_root}`",
        "",
        "---",
        "",
        "## Summary",
        "",
        f"- Wiki pages: {len(corpus.files)}",
        f"- Source files: {len(source.rel_paths)}",
        f"- Declared routines indexed: {len(source.declared_routines)}",
        "",
    ]
    out += _table(
        ["Check", "Status", "Pass / Total"],
        [
            ("A. File-citation existence", color_for(band_for(file_frac)),
             f"{file_pass}/{file_total}"),
            ("B. Line-bound validity", color_for(band_for(line_frac)),
             f"{line_pass}/{line_total}"),
            ("C. Routine-reference presence", color_for(band_for(rout_frac)),
             f"{rout_pass}/{rout_total}"),
            ("D. Module-file presence", color_for(module_dim.status),
             f"{module_dim.pass_count}/{module_dim.total}"),
        ],
    )
    out += [
        "",
        f"**Overall verdict:** {verdict}",
        "",
        "(Green = all checks >= 90% pass; Yellow = any check 70-90%; "
        "Red = any check < 70%)",
        "",
        "---",
        "",
        "## Per-page results",
        "",
    ]
    page_rows = []
    for p in sorted(pages, key=lambda x: (x.fraction, x.page)):
        page_rows.append((
            f"`{p.page}`",
            color_for(p.band),
            f"{p.file_pass}/{p.file_total}",
            f"{p.routine_pass}/{p.routine_total}",
            f"{int(p.fraction * 100)}%",
        ))
    out += _table(
        ["Wiki page", "Band", "Files", "Routines", "Overall"],
        page_rows,
    )
    out.append("")

    # Missing files, per page
    out += ["---", "", "## Cited files that do NOT exist in source", ""]
    any_missing_files = False
    for p in pages:
        if p.missing_files:
            any_missing_files = True
            out.append(f"### `{p.page}`")
            out += _table(
                ["Citation (file:line)"],
                [(f"`{c}`",) for c in p.missing_files],
            )
            out.append("")
    if not any_missing_files:
        out += ["All cited source files exist.", ""]

    # Missing routines, per page
    out += ["---", "", "## Referenced routines NOT found in source", ""]
    any_missing_rout = False
    for p in pages:
        if p.missing_routines:
            any_missing_rout = True
            out.append(f"### `{p.page}`")
            out += _table(
                ["Routine", "Mentions"],
                [(f"`{n}`", c) for n, c in p.missing_routines],
            )
            out.append("")
    if not any_missing_rout:
        out += ["All referenced routines resolve to a declaration in source.", ""]

    # Line overshoots (secondary)
    total_overshoot = sum(len(p.overshoot_lines) for p in pages)
    out += ["---", "",
            f"## Cited lines beyond file length ({total_overshoot})", ""]
    if total_overshoot:
        for p in pages:
            if p.overshoot_lines:
                out.append(f"### `{p.page}`")
                out += _table(
                    ["Citation (file:line)", "File lines", "Overshoot"],
                    [(f"`{c}`", n, over) for c, n, over in p.overshoot_lines],
                )
                out.append("")
    else:
        out += ["All cited line numbers are within file bounds.", ""]

    # Module files
    out += ["---", "", "## Module files mentioned but missing from source", ""]
    if module_dim.rows:
        out += _table(
            ["Module file", "First wiki page"],
            [(f"`{m}`", f"`{o}`") for m, o in module_dim.rows],
        )
        out.append("")
    else:
        out += ["All mentioned module files exist in source.", ""]

    return "\n".join(out), verdict, counts


# =============================================================================
# CLI
# =============================================================================

def parse_args() -> argparse.Namespace:
    ap = argparse.ArgumentParser(
        description="Validate a model's codebase wiki against its source tree "
                    "(generic; dispatches through the model's ModelSpec)."
    )
    ap.add_argument("--model", required=True,
                    help="Model name (e.g. ecosim, fates). Loads "
                         "models/<name>/spec.py for source-scan dispatch.")
    ap.add_argument("--wiki", required=True, type=Path,
                    help="Wiki root directory (recursive .md scan)")
    ap.add_argument("--source", required=True, type=Path,
                    help="Model source tree root")
    ap.add_argument("--output", required=False, type=Path, default=None,
                    help="Optional path to write the Markdown report")
    return ap.parse_args()


def main() -> int:
    args = parse_args()
    if not args.wiki.exists():
        print(f"ERROR: --wiki not found: {args.wiki}", file=sys.stderr)
        return 1
    if not args.source.exists():
        print(f"ERROR: --source not found: {args.source}", file=sys.stderr)
        return 1

    spec = load_spec(args.model)
    print(f"Model: {spec.name}  ({spec.display_name})")
    print(f"  source extensions:  {spec.source_extensions}")
    print(f"  module-file pattern: {spec.module_file_pattern}")
    pats = build_patterns(spec)

    print(f"Loading wiki:    {args.wiki}")
    corpus = load_wiki(args.wiki)
    print(f"  wiki pages: {len(corpus.files)}")

    print(f"Indexing source: {args.source}")
    source = build_source_index(args.source, spec, pats)
    print(f"  source files: {len(source.rel_paths)}, "
          f"declared routines: {len(source.declared_routines)}")

    print("Validating pages...")
    ext_syms, ext_mods = external_sets(spec)
    if ext_syms or ext_mods:
        print(f"  declared externals: {len(ext_syms)} symbols, "
              f"{len(ext_mods)} module patterns (framework boundary)")
    pages = [validate_page(rel, text, source, pats, ext_syms)
             for rel, text in corpus.files.items()]

    print("Checking module-file mentions...")
    module_dim = validate_module_files(corpus, source, pats, ext_mods)

    report, verdict, counts = build_report(
        args.model, args.wiki, args.source, spec, corpus, source,
        pages, module_dim,
    )

    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(report, encoding="utf-8")
        print(f"Wrote report: {args.output}")

    # Short stdout summary
    print("")
    print("=" * 60)
    print(f"WIKI-SOURCE VALIDATION SUMMARY ({spec.name})")
    print("=" * 60)
    for label, key in (("A. File-citation existence", "file"),
                       ("B. Line-bound validity", "line"),
                       ("C. Routine-reference presence", "routine"),
                       ("D. Module-file presence", "module")):
        p, t, band = counts[key]
        print(f"  {label:32s} {p:>5}/{t:<5}  {band}")
    n_bad_files = sum(len(p.missing_files) for p in pages)
    n_bad_rout = sum(len(p.missing_routines) for p in pages)
    red_pages = [p.page for p in pages if p.band == "Red"]
    print(f"  Missing file citations: {n_bad_files}")
    print(f"  Unresolved routines:    {n_bad_rout}")
    print(f"  Red pages: {len(red_pages)}"
          + (f"  -> {', '.join(red_pages)}" if red_pages else ""))
    print(f"\nOVERALL VERDICT: {verdict}")

    return 0 if verdict != "Red" else 1


if __name__ == "__main__":
    sys.exit(main())
