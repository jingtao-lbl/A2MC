#!/usr/bin/env python3
"""Check a parameter list's `bound_source` column against the canonical vocabulary.

Fourth member of the conformance family (`check_log_conformance`, `check_calibration_log_conformance`,
`check_report_conformance`) and, like them, a separate tool because the contract genuinely differs.

WHAT WOULD MAKE THIS FAIL (named first, per `feedback_a_check_that_cannot_fail`):
  B1  a `bound_source` value not starting with one of the five canonical prefixes   -> ERROR
  B2  a `bound_source` cell left BLANK while the column exists                      -> ERROR
  B3  the `bound_source` column absent from the list entirely                       -> WARN
  B4  a `literature:` / `database:` value carrying no resolvable citation (DOI/URL)  -> WARN
  B5  a `provisional:` bound byte-identical to the same parameter's in round N-1     -> WARN
  B6  no parameter list matched at all (an empty selection reported as success)      -> ERROR

WHY B3 IS A WARNING AND NOT AN ERROR. `tools/param_spec.py` documents `bound_source` as OPTIONAL,
and three live lists predate the column entirely (two FATES lists at 339 rows, PFLOTRAN's miniLEO at
17). Erroring on them would fail work nobody touched, which is how a gate stops being a gate.

WHY THIS DOES NOT USE `load_param_spec`. The obvious implementation binds to the loader, which
already carries `bound_source` onto `ParamSpec`. It cannot: the loader coerces the grouping axis to
an integer (`_parse_pft`), and PFLOTRAN's axis is a MINERAL NAME (`Calcite`, `Glass_FB`). So
`load_param_spec` raises on PFLOTRAN's live list AND on every `parameter_list_template.csv`, since
each ships the PFLOTRAN example rows. A checker built on the loader would silently skip exactly the
models this adapter kit exists for, and pass. This reads the CSV directly and treats the axis as
opaque -- it never needs the axis's meaning to check a provenance string. The singular-axis
limitation is a known interim state documented in the template itself; it is NOT this tool's to fix.

GRANDFATHERING is an in-file marker, not a path list: a pre-contract list may carry
`# a2mc: bound-source-grandfathered` in its comment preamble. In-file means it survives a rename,
is greppable, and is visible to anyone editing the list. The count prints on EVERY run so the
backlog cannot go quiet.

Exit 0 clean / 1 warn / 2 error -- the same convention as the other three.
"""
from __future__ import annotations
import argparse, csv, pathlib, re, subprocess, sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
from tools.param_spec import BOUND_SOURCE_PREFIXES, BOUND_SOURCE_NEEDS_CITATION, _header_offset

#: Where parameter lists live. Both roots, because a model may ship reference bounds beside its
#: adapter (`models/ecosim/reference_bounds/`) as well as under a case.
LIST_GLOBS = ("use_cases/*/parameters/*.csv", "models/*/reference_bounds/*.csv")
GRANDFATHER_MARK = "a2mc: bound-source-grandfathered"
#: A citation is a DOI or a URL. Deliberately permissive: the point is that SOMETHING resolvable is
#: present, not that it is well-formed -- a stricter pattern would fail on legitimate variants.
_CITATION = re.compile(r"doi:|10\.\d{4,}/|https?://", re.I)
_ROUND = re.compile(r"_r(\d+)(?:_|\.)")


def _name_column(cols):
    """The list's identifier column. Two dialects: canonical `name`, FATES legacy `fates_name`."""
    for c in ("name", "fates_name"):
        if c in cols:
            return c
    return None


def read_rows(path: pathlib.Path):
    """(rows, fieldnames, grandfathered). Reads the CSV directly -- see the module docstring.

    Comment lines are dropped BOTH before and after the header. `_header_offset` only skips the
    LEADING `#` preamble, but these files interleave commentary among the data -- PFLOTRAN's live
    list carries 145 comment lines around 17 rows -- so slicing at the header alone reports 115
    rows for a 17-row file. Every count this tool prints would then be wrong, and a count nobody
    can trust is how a checker's output stops being read.
    """
    lines = path.read_text(errors="replace").splitlines(keepends=True)
    grandfathered = any(GRANDFATHER_MARK in l for l in lines if l.lstrip().startswith("#"))
    try:
        body = lines[_header_offset(lines):]
    except ValueError:                       # empty or all-comments file
        return [], [], grandfathered
    header, data = body[:1], body[1:]
    kept = header + [l for l in data if l.strip() and not l.lstrip().startswith("#")]
    reader = csv.DictReader(kept)
    return list(reader), [(c or "").strip() for c in (reader.fieldnames or [])], grandfathered


def _prior_round_values(path: pathlib.Path):
    """{param_name: bound_source} from round N-1's list, or {} if there is no previous round."""
    m = _ROUND.search(path.name)
    if not m:
        return {}
    n = int(m.group(1))
    if n <= 1:
        return {}
    prev = path.with_name(path.name.replace(m.group(0), m.group(0).replace(m.group(1), f"{n-1:02d}"), 1))
    if not prev.exists():
        return {}
    rows, cols, _ = read_rows(prev)
    nc = _name_column(cols)
    if not nc or "bound_source" not in cols:
        return {}
    return {(r.get(nc) or "").strip(): (r.get("bound_source") or "").strip() for r in rows}


def check(path: pathlib.Path, repo: pathlib.Path):
    errs, warns, info = [], [], []
    rel = path.relative_to(repo).as_posix() if path.is_absolute() else path.as_posix()
    rows, cols, grandfathered = read_rows(path)
    if not rows:
        return [], [f"{rel}: no data rows (empty or all-comments)"], []

    name_col = _name_column(cols)
    if name_col is None:
        return [f"{rel}: no `name` or `fates_name` column -- not a parameter list, or the header "
                f"row was not found"], [], []

    if "bound_source" not in cols:                                                        # B3
        return [], [f"{rel}: no `bound_source` column ({len(rows)} rows). Bounds carry no "
                    f"provenance, so a re-centred range silently discards where it came from. "
                    f"Add the column (vocabulary: {', '.join(BOUND_SOURCE_PREFIXES)})"], []

    bad, blank, nocite, stale = [], [], [], []
    prior = _prior_round_values(path)
    for r in rows:
        nm = (r.get(name_col) or "").strip()
        if not nm or nm.startswith("#"):
            continue
        bs = (r.get("bound_source") or "").strip()
        if not bs:                                                                        # B2
            blank.append(nm)
            continue
        if not bs.startswith(BOUND_SOURCE_PREFIXES):                                      # B1
            bad.append((nm, bs))
            continue
        if bs.startswith(BOUND_SOURCE_NEEDS_CITATION) and not _CITATION.search(bs):        # B4
            nocite.append((nm, bs))
        if bs.startswith("provisional:") and prior.get(nm) == bs:                          # B5
            stale.append(nm)

    def _ex(pairs, n=3):
        """First n (name, value) pairs, values truncated -- for a one-line error message."""
        return "; ".join(f"{name} -> {value[:60]!r}" for name, value in pairs[:n])

    sev = warns if grandfathered else errs
    if bad:
        sev.append(f"{rel}: {len(bad)}/{len(rows)} `bound_source` value(s) do not start with one of "
                   f"{', '.join(BOUND_SOURCE_PREFIXES)}. e.g. {_ex(bad)}")
    if blank:
        sev.append(f"{rel}: {len(blank)} blank `bound_source` cell(s) (e.g. {', '.join(blank[:5])}). "
                   f"A blank reads as 'not recorded', which the next reader cannot distinguish from "
                   f"a published range -- use `provisional:` and say what the basis is")
    if nocite:
        warns.append(f"{rel}: {len(nocite)} `literature:`/`database:` bound(s) carry no DOI or URL. "
                     f"A claim without a resolvable citation is not a literature bound. e.g. {_ex(nocite)}")
    if stale:
        warns.append(f"{rel}: {len(stale)} `provisional:` bound(s) byte-identical to the previous "
                     f"round's -- the debt was CARRIED, not paid: {', '.join(stale[:5])}"
                     + (f" (+{len(stale)-5} more)" if len(stale) > 5 else ""))
    if grandfathered and (bad or blank):
        info.append(f"{rel}: GRANDFATHERED ({len(bad)} non-conforming, {len(blank)} blank) -- "
                    f"downgraded to warnings by the in-file `{GRANDFATHER_MARK}` marker")
    return errs, warns, info


def discover(repo: pathlib.Path):
    out = []
    for g in LIST_GLOBS:
        out.extend(sorted(repo.glob(g)))
    return out


def staged(repo: pathlib.Path):
    out = subprocess.run(["git", "diff", "--cached", "--name-only", "--diff-filter=ACM"],
                         cwd=repo, capture_output=True, text=True).stdout.split("\n")
    keep = []
    for p in out:
        p = p.strip()
        if p.endswith(".csv") and any(pathlib.PurePath(p).match(g) for g in LIST_GLOBS):
            keep.append(repo / p)
    return keep


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("paths", nargs="*", type=pathlib.Path)
    ap.add_argument("--staged", action="store_true", help="check staged parameter lists only")
    a = ap.parse_args()
    repo = pathlib.Path(__file__).resolve().parents[1]

    targets = ([repo / p if not p.is_absolute() else p for p in a.paths] if a.paths
               else staged(repo) if a.staged else discover(repo))
    if a.staged and not targets:
        print("check_bound_source: no staged parameter lists")
        return 0
    if not targets:                                                                       # B6
        print("check_bound_source: ERROR -- no parameter list matched. An empty selection is not a "
              "pass. Expected files under " + " or ".join(LIST_GLOBS), file=sys.stderr)
        return 2

    errs, warns, info, gf = [], [], [], 0
    for t in targets:
        if not t.exists():
            errs.append(f"{t}: does not exist")
            continue
        e, w, i = check(t, repo)
        errs += e; warns += w; info += i
        gf += bool(i)

    print(f"bound_source conformance — {len(targets)} parameter list(s) checked")
    for i in info:
        print(f"  GRANDFATHERED {i}")
    for w in warns:
        print(f"  WARN  {w}")
    for e in errs:
        print(f"  ERROR {e}", file=sys.stderr)
    if gf:
        print(f"\n  {gf} list(s) grandfathered by an in-file `{GRANDFATHER_MARK}` marker. "
              f"This count prints every run so the backlog stays visible.")
    if errs:
        print(f"\n{len(errs)} error(s), {len(warns)} warning(s)", file=sys.stderr)
        print("Vocabulary: use_cases/TEMPLATE/parameters/parameter_list_template.csv "
              "(source of truth) / tools/param_spec.py::BOUND_SOURCE_PREFIXES", file=sys.stderr)
        return 2
    if warns:
        print(f"\n{len(warns)} warning(s)")
        return 1
    print("\n✔ every bound_source conforms to the canonical vocabulary")
    return 0


if __name__ == "__main__":
    sys.exit(main())
