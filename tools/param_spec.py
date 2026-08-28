#!/usr/bin/env python3
"""
Canonical FATES parameter-list loader (docs/37 — parameter-naming refactor).

THE single source of truth for reading a parameter list. Replaces the scattered
shorthand parsers (`build_param_lookup`, `resolve_parameter_name`, `parse_parameter_list`,
`load_parameter_bounds`, the `reasoning/` regex/token extractors, ...).

TWO dialects load here, resolved once from the header (never guessed per row):

  CANONICAL (EcoSIM's; the default since the PI decision 2026-08-02) — use this for a new list:
    name,pft[,organ],lower_bound,upper_bound,default[,description,bound_source,...]
  FATES LEGACY (the live 168-param Kougarok list, not to be rewritten under a running round):
    fates_name,pft,organ,lower,upper,default_api43[,default_api31,description]

Both spellings of a field present is AMBIGUOUS and raises — a half-converted list is exactly
when a silent preference picks the wrong column. Schema + the `bound_source` vocabulary:
`use_cases/TEMPLATE/parameters/parameter_list_template.csv`.

Fields:
  - name / fates_name : official parameter name (must exist in the model param file).
  - pft        : site PFT id (int); blank/`-`/`0` = a global/scalar param.
  - organ      : OPTIONAL (a FATES axis; a model without one omits the column entirely).
                 The FATES organ slot(s) this row's single sampled value is written into —
                 blank (non-organ), a single id (1=leaf,2=fineroot,3=sapwood,4=structure),
                 or a `|`-list like `1|2` (one value broadcast to several organs, e.g. retrans).
  - lower,upper : floats.
  - default : the **operative** default (the value used when a param isn't otherwise set). The column may
                 be named `default_api43` (preferred — the api-43 base value) or plain `default`; the loader
                 reads whichever is present.
  - description: free text.
  - bound_source: OPTIONAL provenance of the bounds (`measured:` / `literature:` with a DOI /
                 `database:` TRY-FRED-FLUXNET / `prior_round:` / `provisional:`). Carried onto
                 ParamSpec so provenance survives the loader instead of dying at it.

Optional extra columns are ignored by the loader. `default_api31` (if present) is a **reference-only**
column holding the legacy api-31 list default (PFT-remapped 7→10/9→11/10→12) for side-by-side drift
comparison — blank where there is no api-31 equivalent (migrated/split or new names). It is NOT read.

Invariant (docs/37 §3.1): **one row = one Morris matrix column = one independently-sampled
value.** The `organ` field never adds rows/columns — it only lists which organ slot(s) the
value is written to (usually one; retrans broadcasts to [1,2]).
"""
from __future__ import annotations

import csv
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional

try:  # normal package import
    from tools.param_transforms import (
        DERIVED_TRANSFORMS, group_for_coord, is_virtual_coord, native_targets,
    )
except ImportError:  # when run directly as `python tools/param_spec.py`
    from param_transforms import (
        DERIVED_TRANSFORMS, group_for_coord, is_virtual_coord, native_targets,
    )

# FATES fates_plant_organs id convention (1-based).
ORGAN_NAME_TO_INDEX = {"leaf": 1, "fineroot": 2, "sapwood": 3, "structure": 4}
ORGAN_INDEX_TO_NAME = {v: k for k, v in ORGAN_NAME_TO_INDEX.items()}

_PREFIXES = ("fates_cnp_eca_", "fates_cnp_", "fates_alloc_", "fates_leaf_", "fates_")


@dataclass
class ParamSpec:
    """One parameter-list row = one independently-sampled Morris dimension."""
    fates_name: str
    pft: int                 # 0 = global/scalar
    organ: List[int]         # [] = non-organ; [1]=leaf; [1,2]=broadcast (retrans)
    lower: float
    upper: float
    default: float
    description: str = ""
    bound_source: str = ""   # provenance of the bounds (canonical format); "" when not recorded
    row_index: int = -1      # 0-based order == Morris matrix column index
    is_virtual: bool = False           # a derived-param virtual sampling coordinate (tools/param_transforms)
    transform_group: Optional[str] = None  # the derived group this coord belongs to (if is_virtual)

    @property
    def canonical_id(self) -> str:
        """Deterministic, unique string id (SALib var name / Morris column / μ* key / ledger).
        Never parsed back for meaning — look it up in the loaded spec list instead."""
        cid = self.fates_name
        if self.pft:
            cid += f"#p{self.pft}"
        if self.organ:
            cid += "#o" + "-".join(str(o) for o in self.organ)
        return cid

    @property
    def is_organ(self) -> bool:
        return bool(self.organ)

    @property
    def short_label(self) -> str:
        """Display-ONLY short label (e.g. for sensitivity-plot axes). NOT a key."""
        base = self.fates_name
        for pre in _PREFIXES:
            if base.startswith(pre):
                base = base[len(pre):]
                break
        lbl = base
        if self.organ:
            lbl += "_" + "_".join(ORGAN_INDEX_TO_NAME.get(o, str(o)) for o in self.organ)
        if self.pft:
            lbl += f"_{self.pft}"
        return lbl

    def organ_slots(self) -> List[Optional[int]]:
        """Organ slot(s) to write this value into ([None] for a non-organ param)."""
        return list(self.organ) if self.organ else [None]


# Column aliases. TWO dialects load here:
#   canonical (EcoSIM's; PI decision 2026-08-02)  name       + lower_bound / upper_bound
#   FATES legacy (the live 168-param Kougarok list) fates_name + lower       / upper
# Resolved ONCE from the header, so a file is read in whichever dialect it declares — never
# guessed per row. Both spellings present is AMBIGUOUS and raises: a half-converted list is
# exactly when a silent preference picks the wrong column.
_DIALECT_ALIASES = {
    "name":  ("fates_name", "name"),
    "lower": ("lower", "lower_bound"),
    "upper": ("upper", "upper_bound"),
}


def _resolve_dialect_column(cols: set, field: str) -> Optional[str]:
    present = [c for c in _DIALECT_ALIASES[field] if c in cols]
    if len(present) > 1:
        raise ValueError(
            f"Ambiguous parameter list: columns {present} both present for '{field}'. "
            f"Use ONE dialect — canonical (`name`/`lower_bound`/`upper_bound`) or FATES legacy "
            f"(`fates_name`/`lower`/`upper`).")
    return present[0] if present else None


#: The `bound_source` vocabulary — THE single machine-readable definition.
#: Prose copies live in `use_cases/TEMPLATE/parameters/parameter_list_template.csv` (the human
#: source of truth, with per-prefix guidance) and in `.claude/skills/phase0-design/SKILL.md`.
#: Those two and this tuple drifted apart once already: the skill listed THREE prefixes while
#: claiming to quote the template's FIVE, and a checker built from the skill would have errored on
#: every correct `measured:` and `prior_round:` row (2026-08-25). Read this tuple; do not re-type
#: the list (`feedback_bind_derived_facts_to_their_source`).
BOUND_SOURCE_PREFIXES = ("measured:", "literature:", "database:", "prior_round:", "provisional:")

#: Prefixes that must carry a resolvable citation: a claim without a DOI is not a literature bound.
BOUND_SOURCE_NEEDS_CITATION = ("literature:", "database:")


def _header_offset(lines: List[str]) -> int:
    """Index of the header row, skipping a leading `#` comment preamble.

    The canonical template ships a long preamble (schema, the axis rule, the bound_source
    vocabulary). csv.DictReader takes line 0 as the header, so without this every canonical
    list is read with a comment line as its header and reports every column missing.
    The FATES legacy list has no preamble, so this is a no-op there.
    """
    for i, line in enumerate(lines):
        s = line.strip()
        if s and not s.startswith("#"):
            return i
    raise ValueError("no header row found — the file is empty or entirely comments")


def _parse_pft(s: str) -> int:
    s = (s or "").strip()
    if s in ("", "-", "none", "None"):
        return 0
    try:
        return int(s)
    except ValueError:
        raise ValueError(
            f"pft={s!r} is not an integer. This loader's grouping axis is integer-valued "
            f"(a FATES PFT id / EcoSIM plant type). A model whose axis is NAMED (a PFLOTRAN "
            f"mineral, a microbial guild) currently carries that name in `pft` as a documented "
            f"stopgap for the singular ModelSpec.grouping_axis (models/base.py:199), and is read "
            f"by scripts/create_adapter_parameter_sample.py::parse_pft_param_list instead. "
            f"Use that loader until multi-axis ids land."
        ) from None


def _parse_organ(s: str) -> List[int]:
    s = (s or "").strip()
    if s in ("", "-", "0", "none", "None"):
        return []
    return [int(x) for x in s.replace(",", "|").split("|") if x.strip()]


def load_param_spec(param_list_file) -> List[ParamSpec]:
    """Load a param-list CSV into an ordered list of ParamSpec (order == Morris columns)."""
    p = Path(param_list_file)
    if not p.exists():
        raise FileNotFoundError(f"Parameter list file not found: {p}")

    specs: List[ParamSpec] = []
    with open(p, newline="") as f:
        lines = f.readlines()
    if True:  # keep the original indentation of the block below
        reader = csv.DictReader(lines[_header_offset(lines):])
        cols = {(c or "").strip() for c in (reader.fieldnames or [])}
        name_col = _resolve_dialect_column(cols, "name")
        lower_col = _resolve_dialect_column(cols, "lower")
        upper_col = _resolve_dialect_column(cols, "upper")
        # `organ` is OPTIONAL: it is a FATES axis, and a canonical list for a model without one
        # simply omits the column. Absent -> every row is non-organ. (It is still never
        # row-expanding: one row stays one Morris column either way.)
        organ_col = "organ" if "organ" in cols else None
        # operative default: `default_api43` (preferred, post-rename) or plain `default`.
        # PRECEDENCE, not ambiguity — unlike the dialect aliases above, this pair is deliberate
        # (the api-43 value wins over a generic default) and predates the canonical format.
        # `default_api31` is reference-only and never read.
        default_col = next((c for c in ("default_api43", "default") if c in cols), None)
        missing = [f for f, c in (("name/fates_name", name_col), ("pft", "pft" if "pft" in cols else None),
                                  ("lower/lower_bound", lower_col), ("upper/upper_bound", upper_col),
                                  ("default_api43/default", default_col)) if not c]
        if missing:
            raise ValueError(
                f"{p}: parameter list is missing required column(s) {missing}; got {sorted(cols)}. "
                f"Canonical format: name,pft[,organ],lower_bound,upper_bound,default[,description,bound_source]")
        for row in reader:
            fates = (row[name_col] or "").strip()
            if not fates or fates.startswith("#"):
                continue
            dval = (row.get(default_col) or "").strip()
            if dval == "":
                raise ValueError(
                    f"{p}: row '{fates}' pft={row.get('pft')} has an empty {default_col} — every "
                    f"parameter needs an operative default")
            spec = ParamSpec(
                fates_name=fates,
                pft=_parse_pft(row["pft"]),
                organ=_parse_organ(row.get(organ_col) if organ_col else ""),
                lower=float(row[lower_col]),
                upper=float(row[upper_col]),
                default=float(dval),
                description=(row.get("description") or "").strip(),
                bound_source=(row.get("bound_source") or "").strip(),
                row_index=len(specs),
            )
            if is_virtual_coord(spec.fates_name):
                spec.is_virtual = True
                spec.transform_group = group_for_coord(spec.fates_name)
                if spec.organ:
                    raise ValueError(
                        f"virtual coord '{spec.fates_name}' (pft{spec.pft}) must have no organ; got {spec.organ}")
            specs.append(spec)

    ids = [s.canonical_id for s in specs]
    seen, dupes = set(), set()
    for i in ids:
        (dupes if i in seen else seen).add(i)
    if dupes:
        raise ValueError(f"Duplicate canonical ids in {p}: {sorted(dupes)}")

    _check_derived_groups(specs, p)
    return specs


def _check_derived_groups(specs: List[ParamSpec], p) -> None:
    """Derived-parameter invariants (only fire when virtual coords are actually present):
      - every group is complete per PFT (all its coords present) — all-or-nothing;
      - no native write-target of an active group also appears as its own direct row for that PFT
        (that would write the same param twice / ambiguously)."""
    present = defaultdict(set)         # (group, pft) -> {coord names present}
    native_by_pft = defaultdict(set)   # pft -> {direct (non-virtual) fates_names}
    for s in specs:
        if s.is_virtual:
            present[(s.transform_group, s.pft)].add(s.fates_name)
        else:
            native_by_pft[s.pft].add(s.fates_name)
    for (group, pft), names in present.items():
        t = DERIVED_TRANSFORMS[group]
        required = set(t.coords)
        if names != required:
            raise ValueError(
                f"{p}: derived group '{group}' incomplete for pft{pft}: "
                f"missing {sorted(required - names)} (have {sorted(names)}) — groups are all-or-nothing")
        conflict = native_by_pft.get(pft, set()) & set(t.native_names())
        if conflict:
            raise ValueError(
                f"{p}: derived group '{group}' pft{pft} writes {sorted(conflict)}, "
                f"but those also appear as direct param-list rows — remove the direct rows")


if __name__ == "__main__":
    import sys
    specs = load_param_spec(sys.argv[1])
    print(f"{len(specs)} params, {len({s.fates_name for s in specs})} unique fates_names")
    for s in specs[:8]:
        print(f"  {s.canonical_id:42s} organ={s.organ or '-'} label={s.short_label}")
