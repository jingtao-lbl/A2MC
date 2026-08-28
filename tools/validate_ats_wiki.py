#!/usr/bin/env python3
"""validate_ats_wiki.py — ATS-specific codebase-wiki validator series.

The generic `validate_wiki_vs_source.py` (V1) checks that every *citation* resolves
(file exists, line in-bounds, routine/module name appears in source). That is necessary
but not sufficient for ATS, for two reasons this tool addresses:

  1. **Out-of-scope boundary.** ATS is built ON Amanzi and documents ATS source ONLY, so
     the wiki legitimately names Amanzi-framework symbols (`UpdateMatrices`, `MatrixMFD.hh`,
     …) that the generic validator can't find in the ATS tree and therefore flags. Left
     unclassified, the ATS wiki is perpetually "Yellow" from these false-positives, which
     drowns out any real fabrication. This tool classifies each unresolved reference against
     the ATS `ModelSpec`'s declared external boundary (`spec.external_symbol_names` /
     `spec.external_module_patterns`) into EXTERNAL-EXPECTED vs GENUINELY-UNRESOLVED — only
     the latter is a real defect.

  2. **Factory keys are load-bearing and citation-invisible.** ATS PKs/evaluators are
     selected in the XML input deck by exact type/factory-key strings (`"transport ATS"`,
     `"simple Carbon"`). A wiki that prints the wrong key (a real defect found in the
     b044298a wiki: `"carbon simple"` vs the actual `"simple Carbon"`) passes every citation
     check yet would mis-instruct a user. This tool extracts backticked quoted key strings
     from the wiki and verifies each appears as a string literal in ATS source.

The series (each a named check; overall verdict = worst):

    S1  Amanzi-boundary resolution   -- unresolved routines/modules are all EXTERNAL-EXPECTED
    S2  Pin-header completeness       -- every page carries Source pin + Last verified @ commit
    S3  Factory-key presence          -- every quoted key string exists as a source literal

Read-only. Exit 0 if no in-scope failure, 1 otherwise.

Usage:
    python tools/validate_ats_wiki.py \
        --wiki docs/ats-knowledge-base/ats-codebase-wiki-42b0e940 \
        --source ~/Desktop/Work/ELM-ATS-RDycore/ats_at_42b0e940 \
        [--commit 42b0e940] [--output docs/a2mc_reference/ats_wiki_validation.md]

    --source must be the PINNED anchor worktree (`ats_at_<commit>`), NOT the sibling
    `ats/` checkout: the latter tracks upstream `master` and drifts away from the wiki
    pin, so validating against it silently checks the wiki against the wrong tree.

Author: Jing Tao with Claude
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path
from typing import Dict, List, Set, Tuple

REPO_ROOT = Path(__file__).resolve().parent.parent
for _p in (REPO_ROOT, REPO_ROOT / "tools"):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

# Reuse the generic V1 machinery (load_spec, source index, routine extraction) + loader.
from validate_wiki_vs_source import (  # noqa: E402
    build_patterns, build_source_index, extract_routine_refs, load_spec,
)
from codebase_wiki_validator import load_wiki  # noqa: E402

MODEL = "ats"

# A factory/type KEY is a backtick-double-quoted string that the wiki presents in a
# PK-type / factory-key / evaluator-type CONTEXT, e.g. "... type string `"simple Carbon"`".
# Scoping to that context (rather than every quoted string) keeps S3 precise: it catches
# load-bearing instantiation keys (a wrong one silently mis-instructs an input deck) while
# ignoring quoted C-API function names, XML parameter names, and prose.
_KEY_CONTEXT_RE = re.compile(
    r"(?:type\s+string|factory\s+key|factory\s+string|PK\s+type|spec\s+type|"
    r"evaluator\s+type|registered(?:\s+as)?|\btype\b)[^\n`]{0,25}`\"([^\"]{2,})\"`",
    re.IGNORECASE,
)
# Double-quoted string literal in C++ source.
_SRC_LIT_RE = re.compile(r"\"([^\"\n]{2,})\"")
# Keys that are not real factory keys even if in a type-ish context (units/trivia).
_KEY_IGNORE = {"-", "--", "[-]", "cell", "face", "none", "domain", "surface"}

# Meta pages that carry a different pin format (the shared preamble) — exempt from the
# per-page Source pin / Last verified header requirement.
_META_PAGES = {"UNIVERSAL_CONTEXT.md"}


# =============================================================================
# S1 — Amanzi-boundary resolution
# =============================================================================

def _is_external_module(name: str, patterns: List[re.Pattern]) -> bool:
    return any(p.search(name) for p in patterns)


def check_boundary(corpus, source, spec, pats) -> Tuple[dict, List[str]]:
    ext_syms = {s.lower() for s in (spec.external_symbol_names or ())}
    ext_mod_pats = [re.compile(p) for p in (spec.external_module_patterns or ())]

    # Unresolved routines across all pages.
    ext_routines: Dict[str, int] = {}
    genuine_routines: Dict[str, int] = {}
    for text in corpus.files.values():
        for name, count in extract_routine_refs(text).items():
            if name.lower() in source.declared_routines:
                continue
            bucket = ext_routines if name.lower() in ext_syms else genuine_routines
            bucket[name] = bucket.get(name, 0) + count

    # Unresolved module-file mentions across all pages.
    mentions: Set[str] = set()
    for text in corpus.files.values():
        for m in pats.module_file.finditer(text):
            mentions.add(m.group(1))
    ext_modules, genuine_modules = [], []
    for mod in sorted(mentions):
        if source.has_basename(mod):
            continue
        (ext_modules if _is_external_module(mod, ext_mod_pats)
         else genuine_modules).append(mod)

    report = [
        "## S1 — Amanzi-boundary resolution",
        "",
        f"- Unresolved routines: {len(ext_routines)} external-expected, "
        f"**{len(genuine_routines)} genuinely unresolved**",
        f"- Unresolved module files: {len(ext_modules)} external-expected, "
        f"**{len(genuine_modules)} genuinely unresolved**",
        "",
    ]
    if genuine_routines:
        report.append("**Genuinely-unresolved routines (verify — possible fabrication):**")
        report += [f"- `{n}` ({c}×)" for n, c in sorted(genuine_routines.items())]
        report.append("")
    if genuine_modules:
        report.append("**Genuinely-unresolved module files (verify):**")
        report += [f"- `{m}`" for m in genuine_modules]
        report.append("")
    if not genuine_routines and not genuine_modules:
        report.append("All unresolved references are declared-external (Amanzi/generated). ✓")
        report.append("")
    if ext_routines or ext_modules:
        report.append(
            f"<sub>Classified external-expected: "
            f"{', '.join(sorted(ext_routines)) or '—'} · "
            f"{', '.join(ext_modules) or '—'}</sub>")
        report.append("")

    n_genuine = len(genuine_routines) + len(genuine_modules)
    return ({"name": "S1 boundary", "pass": n_genuine == 0,
             "detail": f"{n_genuine} genuinely-unresolved"}, report)


# =============================================================================
# S2 — Pin-header completeness
# =============================================================================

def check_pins(wiki_root: Path, commit: str) -> Tuple[dict, List[str]]:
    pages = [p for p in sorted(wiki_root.rglob("*.md")) if p.name not in _META_PAGES]
    missing_pin, missing_verified, wrong_commit = [], [], []
    for pg in pages:
        rel = str(pg.relative_to(wiki_root))
        text = pg.read_text(encoding="utf-8", errors="replace")
        m = re.search(r"\*\*Source pin:\*\*.*?`([0-9a-f]{6,40})`", text)
        if not re.search(r"\*\*Source pin:\*\*", text):
            missing_pin.append(rel)
        elif m and commit and not m.group(1).startswith(commit) \
                and not commit.startswith(m.group(1)):
            wrong_commit.append(f"{rel} (pins `{m.group(1)}`, expected `{commit}`)")
        if not re.search(r"\*\*Last verified:\*\*", text):
            missing_verified.append(rel)

    report = ["## S2 — Pin-header completeness", "",
              f"- Pages: {len(pages)} · expected commit: `{commit or '(unset)'}`",
              f"- Missing `Source pin`: {len(missing_pin)} · "
              f"Missing `Last verified`: {len(missing_verified)} · "
              f"Wrong commit: {len(wrong_commit)}", ""]
    for label, items in (("Missing Source pin", missing_pin),
                         ("Missing Last verified", missing_verified),
                         ("Wrong commit", wrong_commit)):
        if items:
            report.append(f"**{label}:**")
            report += [f"- `{i}`" for i in items]
            report.append("")
    if not (missing_pin or missing_verified or wrong_commit):
        report += ["Every page carries a Source pin + Last verified at the expected commit. ✓", ""]

    ok = not (missing_pin or missing_verified or wrong_commit)
    return ({"name": "S2 pins", "pass": ok,
             "detail": f"{len(missing_pin)+len(missing_verified)+len(wrong_commit)} issues"},
            report)


# =============================================================================
# S3 — Factory-key presence
# =============================================================================

def _source_string_literals(source_root: Path, spec) -> Set[str]:
    exts = {e.lower() for e in (spec.source_extensions or ())}
    lits: Set[str] = set()
    for p in source_root.rglob("*"):
        if not p.is_file() or p.suffix.lower() not in exts:
            continue
        try:
            for m in _SRC_LIT_RE.finditer(p.read_text(encoding="utf-8", errors="replace")):
                lits.add(m.group(1))
        except OSError:
            continue
    return lits


def check_factory_keys(corpus, source_root: Path, spec) -> Tuple[dict, List[str]]:
    literals = _source_string_literals(source_root, spec)
    # Collect quoted keys per page.
    per_page_missing: Dict[str, List[str]] = {}
    checked = 0
    for page, text in corpus.files.items():
        for m in _KEY_CONTEXT_RE.finditer(text):
            key = m.group(1).strip()
            if key.lower() in _KEY_IGNORE or len(key) < 3:
                continue
            checked += 1
            if key not in literals:
                per_page_missing.setdefault(page, []).append(key)

    n_missing = sum(len(v) for v in per_page_missing.values())
    report = ["## S3 — Factory-key / type-string presence", "",
              f"- Quoted key strings checked: {checked} · "
              f"source string-literals indexed: {len(literals)}",
              f"- **Not found in source: {n_missing}**", ""]
    if per_page_missing:
        report.append("**Keys printed in the wiki that do NOT appear as a source literal "
                      "(likely wrong factory key):**")
        for page in sorted(per_page_missing):
            report.append(f"- `{page}`: " +
                          ", ".join(f"`\"{k}\"`" for k in per_page_missing[page]))
        report.append("")
    else:
        report += ["Every quoted key string resolves to a source literal. ✓", ""]

    return ({"name": "S3 factory-keys", "pass": n_missing == 0,
             "detail": f"{n_missing} unresolved keys"}, report)


# =============================================================================
# Driver
# =============================================================================

def main() -> int:
    ap = argparse.ArgumentParser(description="ATS-specific codebase-wiki validator series.")
    ap.add_argument("--wiki", required=True, type=Path)
    ap.add_argument("--source", required=True, type=Path)
    ap.add_argument("--commit", default=None,
                    help="Expected pin commit (default: parsed from wiki dir name "
                         "'…-codebase-wiki-<commit>').")
    ap.add_argument("--output", type=Path, default=None)
    args = ap.parse_args()

    if not args.wiki.exists():
        print(f"ERROR: --wiki not found: {args.wiki}", file=sys.stderr); return 1
    if not args.source.exists():
        print(f"ERROR: --source not found: {args.source}", file=sys.stderr); return 1

    commit = args.commit
    if not commit:
        m = re.search(r"codebase-wiki-([0-9a-fA-F]{6,40})$", args.wiki.name)
        commit = m.group(1) if m else ""

    spec = load_spec(MODEL)
    pats = build_patterns(spec)
    corpus = load_wiki(args.wiki)
    source = build_source_index(args.source, spec, pats)

    results, body = [], [
        f"# ATS Wiki Validator Series — `{args.wiki.name}` vs `{args.source.name}`", "",
        f"Expected commit `{commit}` · {len(corpus.files)} pages · "
        f"{len(source.rel_paths)} source files", "",
    ]
    for check_fn, cargs in (
        (check_boundary, (corpus, source, spec, pats)),
        (check_pins, (args.wiki, commit)),
        (check_factory_keys, (corpus, args.source, spec)),
    ):
        res, rep = check_fn(*cargs)
        results.append(res)
        body += rep

    overall = "PASS" if all(r["pass"] for r in results) else "FAIL"
    summary = ["## Summary", "",
               "| Check | Result | Detail |", "|---|---|---|"]
    summary += [f"| {r['name']} | {'✅ PASS' if r['pass'] else '❌ FAIL'} | {r['detail']} |"
                for r in results]
    summary += ["", f"**Overall: {overall}**", ""]
    report = "\n".join(body[:4] + summary + body[4:])

    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(report, encoding="utf-8")

    print("=" * 60)
    print(f"ATS WIKI VALIDATOR SERIES — {args.wiki.name}")
    print("=" * 60)
    for r in results:
        print(f"  {r['name']:20s} {'PASS' if r['pass'] else 'FAIL'}   ({r['detail']})")
    print(f"\nOVERALL: {overall}")
    return 0 if overall == "PASS" else 1


if __name__ == "__main__":
    sys.exit(main())
