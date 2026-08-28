#!/usr/bin/env python
"""Validate curated-seed COVERAGE: every category has a mechanism, every parameter is reachable.

The curated seed decides what Phase 3 diagnosis is able to recommend. A category with no
mechanism, or a calibratable parameter no mechanism mentions, is invisible downstream -- the
seed builder prints "[SKIP] category X has no assigned mechanisms" and then exits 0, so a
partial seed reads as a finished one. This is the gate that makes that loud.

Two checks, mirroring the bar set by the EcoSIM seed (9/9 categories, 32/32 parameters):

    C1  category coverage    -- every category with parameters has >=1 mechanism
    C2  parameter coverage   -- every calibratable parameter is named by >=1 mechanism

Works on EITHER shape:
  * builder work-in-progress -- a stage_b_categories.yaml + stage_c_mechanisms.yaml pair
    (mechanisms carry `_assigned_category`)
  * an assembled seed -- models/<model>/curated_seed.yaml
    (categories carry a `mechanisms:` list)

Read-only. Exit 0 if fully covered, 1 otherwise.

Usage:
    python tools/validate_seed_coverage.py --seed models/ecosim/curated_seed.yaml
    python tools/validate_seed_coverage.py \
        --categories Offline/seed_builder_ats/stage_b_categories.yaml \
        --mechanisms Offline/seed_builder_ats/stage_c_mechanisms.yaml

Author: Jing Tao with Claude
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

import yaml


# Leaf tokens that carry no identity of their own; the meaningful name is the parent list.
_GENERIC_LEAVES = {"value", "values", "constant"}
# Container/wrapper segments to skip when walking back for that meaningful parent.
_STRUCTURAL_SEGMENTS = {
    "state", "evaluators", "field evaluators", "function", "function-constant",
    "domain", "model parameters", "pks",
}


def _load(p: Path) -> dict:
    with open(p) as f:
        return yaml.safe_load(f) or {}


def _norm(param: str) -> str:
    """Normalize a parameter reference to a deck-independent identity key.

    A mechanism is a property of the MODEL; a parameter address is a property of one DECK. The
    same knob appears under different addresses across decks, so an exact-string match makes a
    correct mechanism inventory look uncovered. Three real differences seen between the ATS
    fixture deck and the coupled flow-energy deck:

      PK nesting / region   .../WRM parameters/all layers/van Genuchten alpha [Pa^-1]
                            .../WRM parameters/peat/van Genuchten alpha
      unit spelling         thermal conductivity of soil [W m^-1 K^-1]
                            thermal conductivity of soil [W/(m-K)]
      units present at all  van Genuchten alpha [Pa^-1]   vs   van Genuchten alpha

    So: take the last path segment, drop any bracketed unit, collapse whitespace, lowercase.
    Region multiplicity collapses too, which is what we want -- one mechanism covers a knob
    however many material regions repeat it.
    """
    # ORDER MATTERS: strip bracketed units BEFORE splitting on "/". ATS addresses are "/"-joined
    # but unit strings themselves contain slashes ([J/kg-K], [W/(m-K)]), so splitting first
    # severs the leaf mid-unit and yields garbage like "kg-k]".
    s = re.sub(r"\[[^\]]*\]", " ", param)         # strip [Pa^-1], [W/(m-K)], [J/kg-K], [-] ...
    parts = [p.strip() for p in s.split("/") if p.strip()]
    if not parts:
        return ""
    leaf = parts[-1]
    # A GENERIC leaf carries no identity -- ATS names many knobs `<meaningful parent>/value`, so
    # `permeability/.../value`, `surface-manning_coefficient/value` and
    # `surface-relative_permeability/value` would all collapse to "value" and be treated as the
    # SAME parameter. Qualify with the nearest meaningful ancestor, skipping structural wrappers.
    # Qualify with the EVALUATOR name -- the FIRST non-structural segment, walking left to right.
    # Walking right-to-left instead would pick up the region slot in
    # `permeability/function/<region>/function/function-constant/value`, giving "peat/value" vs
    # "domain/value" for the same knob in two decks. Left-to-right lands on "permeability" for
    # both, so region multiplicity still collapses as intended.
    if leaf.lower() in _GENERIC_LEAVES:
        for anc in parts[:-1]:
            if anc.lower() not in _STRUCTURAL_SEGMENTS:
                leaf = f"{anc}/{leaf}"
                break
    return re.sub(r"\s+", " ", leaf).strip().lower()


def _from_pair(cat_path: Path, mech_path: Path):
    """Builder work-in-progress: mechanisms point at a category via _assigned_category."""
    cats, mechs = _load(cat_path), _load(mech_path)
    by_cat: dict[str, list[str]] = {}
    for name, m in mechs.items():
        c = (m or {}).get("_assigned_category")
        if c:
            by_cat.setdefault(c, []).append(name)
    members = {c: list(d.get("_members", [])) for c, d in cats.items()}
    return cats, mechs, by_cat, members


def _from_seed(seed_path: Path):
    """Assembled seed: categories carry an explicit mechanisms list."""
    d = _load(seed_path)
    cats, mechs = d.get("categories", {}), d.get("mechanisms", {})
    by_cat = {c: list(cd.get("mechanisms", [])) for c, cd in cats.items()}
    members: dict[str, list[str]] = {c: [] for c in cats}
    # An assembled seed lists parameters globally; attribute each to its category when it says so,
    # otherwise fall back to "every parameter must be reachable" (C2) without a per-category split.
    for pname, pd in (d.get("parameters") or {}).items():
        c = (pd or {}).get("category")
        if c in members:
            members[c].append(pname)
    if not any(members.values()):
        members = {c: [] for c in cats}
        members.setdefault("_all", list((d.get("parameters") or {}).keys()))
    return cats, mechs, by_cat, members


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--seed", type=Path, help="assembled curated_seed.yaml")
    ap.add_argument("--categories", type=Path, help="stage_b_categories.yaml")
    ap.add_argument("--mechanisms", type=Path, help="stage_c_mechanisms.yaml")
    a = ap.parse_args()

    if a.seed:
        cats, mechs, by_cat, members = _from_seed(a.seed)
        label = str(a.seed)
    elif a.categories and a.mechanisms:
        cats, mechs, by_cat, members = _from_pair(a.categories, a.mechanisms)
        label = f"{a.categories} + {a.mechanisms}"
    else:
        ap.error("give --seed, or both --categories and --mechanisms")

    print("=" * 62)
    print(f"SEED COVERAGE — {label}")
    print("=" * 62)

    # C1: every category holding parameters must have at least one mechanism.
    c1_bad = [c for c, ms in ((c, by_cat.get(c, [])) for c in cats)
              if not ms and members.get(c)]
    # A category with no parameters at all is vacuous, not a failure -- report it separately.
    empty = [c for c in cats if not members.get(c) and not by_cat.get(c)]

    # C2: every parameter named by some mechanism.
    covered = {_norm(p) for m in mechs.values() for p in (m or {}).get("parameters", [])}
    c2_bad: list[tuple[str, str]] = []
    for c, ps in members.items():
        for p in ps:
            if _norm(p) not in covered:
                c2_bad.append((c, p))

    print(f"\n  categories : {len(cats)}")
    print(f"  mechanisms : {len(mechs)}")
    print(f"  parameters : {sum(len(v) for v in members.values())}")

    print(f"\n  C1 category coverage   {'PASS' if not c1_bad else 'FAIL'}"
          f"   ({len(cats) - len(c1_bad)}/{len(cats)} covered)")
    for c in c1_bad:
        print(f"       UNCOVERED  {c}  ({len(members.get(c, []))} parameters, 0 mechanisms)")
    for c in empty:
        print(f"       (note) category {c!r} has no parameters and no mechanisms")

    ntot = sum(len(v) for v in members.values())
    print(f"  C2 parameter coverage  {'PASS' if not c2_bad else 'FAIL'}"
          f"   ({ntot - len(c2_bad)}/{ntot} reachable)")
    for c, p in c2_bad:
        print(f"       UNREACHABLE  [{c}] {p}")

    # Orphans are a wiring error rather than a coverage hole: warn, do not fail.
    orphans = sorted(set(mechs) - {m for ms in by_cat.values() for m in ms})
    if orphans:
        print(f"\n  [WARN] {len(orphans)} mechanism(s) not attached to any category: {orphans}")

    ok = not c1_bad and not c2_bad
    print(f"\nOVERALL: {'PASS' if ok else 'FAIL'}")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
