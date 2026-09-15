#!/usr/bin/env python3
"""validate_curated_yaml.py - Model-generic curated-relationships YAML validator (V2).

The adapter-kit (Doc 19 §6.5) V2 validator, generalized off the FATES-specific
``tools/yaml_wiki_validator.py``. Where that tool hardwires the FATES parsers and
validates the YAML against the codebase *wiki*, this one is model-agnostic: it
takes ``--model <name>``, loads that model's ``ModelSpec`` from the adapter
registry, and dispatches parameter/output parsing through the spec. It validates
a model's curated relationships YAML against the **real model surfaces**:

    A. Parameter surface  — every parameter name referenced in the YAML exists in
                            the model's parameter file (parsed via
                            ``spec.parameter_parser_class``).
    B. Output surface     — every output/history variable referenced exists in the
                            model's output surface (parsed via
                            ``spec.output_parser_class`` for a CDL/text registry,
                            or directly via netCDF for a ``.nc`` reference tape).
    C. Internal consistency — every mechanism referenced by a category or parameter
                            is defined in ``mechanisms:``; every category referenced
                            by a parameter is defined in ``categories:``; no dangling
                            cross-references.

This is ADDITIVE (adapter-kit branch rule, docs/38): a NEW file that does not
touch the FATES validator, so main merges stay clean. It works for ``--model
ecosim`` today and structurally for ``fates`` (or any future adapter) because all
model-specific behavior is reached through the spec.

Exit codes
----------
    0  PASS  — no errors in any dimension
    1  usage/path error
    2  validation failures found

Usage
-----
    # Defaults resolve from the model's registered ModelDataset + curated_seed.yaml:
    python tools/validate_curated_yaml.py --model ecosim

    # Validate the output surface against the actual reference tape (.nc):
    python tools/validate_curated_yaml.py --model ecosim \\
        --output-file Offline/EcoSIM_sample_files/output/BioCON__test1_ex1.ecosim.h0.2000-01-01-00000.nc

    # Explicit overrides + Markdown report:
    python tools/validate_curated_yaml.py --model ecosim \\
        --yaml models/ecosim/curated_seed.yaml \\
        --param-file <param.nc/.json/.cdl> \\
        --output-file <output.cdl/.nc> \\
        --report docs/a2mc_reference/curated_yaml_validation_ecosim.md

Author: Jing Tao with Claude
"""

from __future__ import annotations

import argparse
import importlib
import sys
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

import yaml

# Import the adapter registry without dragging in rag/__init__.py (needs networkx).
REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


# =============================================================================
# Data classes
# =============================================================================

@dataclass
class DimensionResult:
    """Per-dimension pass/total accounting plus reportable rows and notes."""

    name: str = ""
    pass_count: int = 0
    total: int = 0
    rows: List[Tuple] = field(default_factory=list)      # (ref, ok, detail)
    errors: List[str] = field(default_factory=list)      # human-readable error lines
    notes: List[str] = field(default_factory=list)

    @property
    def fraction(self) -> float:
        return (self.pass_count / self.total) if self.total else 1.0

    @property
    def status(self) -> str:
        return "PASS" if not self.errors else "FAIL"


# =============================================================================
# Reference collection (schema-generic over the curated YAML)
# =============================================================================
#
# The collectors look at a *superset* of the field names used across A2MC curated
# YAMLs (EcoSIM seed + FATES curated_relationships) so the same validator works
# for either schema and degrades gracefully on missing sections.

def _as_list(v) -> List:
    if v is None:
        return []
    if isinstance(v, (list, tuple, set)):
        return list(v)
    return [v]


def collect_parameter_refs(curated: dict) -> Dict[str, List[str]]:
    """Map parameter-name -> list of YAML locations that reference it."""
    refs: Dict[str, List[str]] = {}

    def add(name, loc):
        if name:
            refs.setdefault(name, []).append(loc)

    for pk, pv in (curated.get("parameters") or {}).items():
        add(pk, f"parameters.{pk} (key)")
        pv = pv or {}
        for r in _as_list(pv.get("related_to")):
            add(r, f"parameters.{pk}.related_to")
    for mk, mv in (curated.get("mechanisms") or {}).items():
        for p in _as_list((mv or {}).get("parameters")):
            add(p, f"mechanisms.{mk}.parameters")
    for ck, cv in (curated.get("categories") or {}).items():
        for p in _as_list((cv or {}).get("parameters")):
            add(p, f"categories.{ck}.parameters")
    for ok, ov in (curated.get("outputs") or {}).items():
        ov = ov or {}
        for d in _as_list(ov.get("direct_drivers")):
            add(d, f"outputs.{ok}.direct_drivers")
        for d in _as_list(ov.get("indirect_drivers")):
            add(d, f"outputs.{ok}.indirect_drivers")
        for d in _as_list(ov.get("drivers")):
            add(d, f"outputs.{ok}.drivers")
    return refs


def collect_output_refs(curated: dict) -> Dict[str, List[str]]:
    """Map output-name -> list of YAML locations that reference it."""
    refs: Dict[str, List[str]] = {}

    def add(name, loc):
        if name:
            refs.setdefault(name, []).append(loc)

    for ck, cv in (curated.get("categories") or {}).items():
        for o in _as_list((cv or {}).get("key_outputs")):
            add(o, f"categories.{ck}.key_outputs")
    for mk, mv in (curated.get("mechanisms") or {}).items():
        for o in _as_list((mv or {}).get("affects")):
            add(o, f"mechanisms.{mk}.affects")
    for ok, ov in (curated.get("outputs") or {}).items():
        add(ok, f"outputs.{ok} (key)")
    for pk, pv in (curated.get("parameters") or {}).items():
        for o in _as_list((pv or {}).get("affects")):
            add(o, f"parameters.{pk}.affects")
    return refs


def collect_mechanism_refs(curated: dict) -> Dict[str, List[str]]:
    """Map mechanism-name -> list of YAML locations that reference it."""
    refs: Dict[str, List[str]] = {}

    def add(name, loc):
        if name:
            refs.setdefault(name, []).append(loc)

    for ck, cv in (curated.get("categories") or {}).items():
        for m in _as_list((cv or {}).get("mechanisms")):
            add(m, f"categories.{ck}.mechanisms")
    for pk, pv in (curated.get("parameters") or {}).items():
        for m in _as_list((pv or {}).get("controls")):
            add(m, f"parameters.{pk}.controls")
    return refs


def collect_category_refs(curated: dict) -> Dict[str, List[str]]:
    """Map category-name -> list of YAML locations that reference it."""
    refs: Dict[str, List[str]] = {}

    def add(name, loc):
        if name:
            refs.setdefault(name, []).append(loc)

    for pk, pv in (curated.get("parameters") or {}).items():
        pv = pv or {}
        for c in _as_list(pv.get("category")) + _as_list(pv.get("categories")):
            add(c, f"parameters.{pk}.category")
    return refs


# =============================================================================
# Model surface parsing (dispatched through the spec)
# =============================================================================

def load_model_spec_and_dataset(model: str, version: Optional[str]):
    """Import the model's adapter package and return (spec, dataset).

    Returns (spec, dataset). `dataset` may be None if the requested version
    is unavailable but the spec still loads (surfaces then come from CLI args).
    """
    importlib.import_module(f"models.{model}")
    from models import registry

    backend = registry.get_model(model)  # raises ValueError w/ helpful message
    spec = backend.spec

    dataset = None
    dsmap = registry.list_datasets(model).get(model, [])
    if version:
        dataset = registry.get_dataset(model, version)
    elif dsmap:
        # Prefer canonical, else most-recently-registered (registry's own rule).
        try:
            _, dataset = _resolve_default_dataset(registry, model)
        except Exception:
            dataset = registry.get_dataset(model, dsmap[-1])
    return spec, dataset


def _resolve_default_dataset(registry, model: str):
    """Pick canonical dataset, else the last registered one."""
    versions = registry.list_datasets(model).get(model, [])
    for v in versions:
        ds = registry.get_dataset(model, v)
        if getattr(ds, "canonical", False):
            return v, ds
    return versions[-1], registry.get_dataset(model, versions[-1])


def parse_parameter_surface(spec, param_file: Path) -> Set[str]:
    """Parse the model's parameter file into a set of accepted parameter names.

    Dispatched through ``spec.parameter_parser_class`` (adapter contract:
    no-arg constructor + ``parse(path)``).

    Returns the parser's own keys PLUS, for path-addressed models, the leaf
    names -- so a curated seed may reference either an exact instance or the
    card/leaf it belongs to. See the comment in the body for why.
    """
    parser_cls = spec.parameter_parser_class
    if parser_cls is None:
        raise RuntimeError(
            f"Model '{spec.name}' spec has no parameter_parser_class; "
            "cannot validate the parameter surface."
        )
    parser = parser_cls()
    parsed = parser.parse(param_file)
    names: Set[str] = set(parsed.keys())

    # PATH-ADDRESSED MODELS: admit the LEAF name too.
    #
    # For FATES and EcoSIM a parameter's key IS its name, so the loop below adds
    # nothing and this is a no-op. But a model whose knobs are addressed by PATH
    # (PFLOTRAN's deck cards, ATS's Teuchos ParameterList paths) has the same
    # physical parameter recurring at many addresses -- ATS's own spec notes
    # "the same physical parameter (e.g. van Genuchten alpha) recurs once per
    # mesh region/material", and PFLOTRAN's RATE_CONSTANT appears once per
    # mineral. Curated KNOWLEDGE belongs at leaf granularity ("RATE_CONSTANT
    # controls TST dissolution") because it is true of every instance and stays
    # valid across decks; only the INSTANCES are address-specific. Keying a seed
    # on addresses would make it a description of one deck rather than of the
    # model.
    #
    # A parser opts in simply by exposing `leaf` on its records (attribute or
    # dict key) -- no spec flag, no per-model branch here.
    # `field_name` covers sub-address columns: a PFLOTRAN positional row
    # (`Labradorite 0.144 5.2d2`) has leaf="Labradorite" -- the row LABEL -- while
    # the knob is the COLUMN (`vol_frac`, `surface_area`). Both are legitimate
    # things for a seed to describe, so both are admitted. Absent on parsers that
    # have no sub-address concept, so again a no-op for them.
    for rec in parsed.values():
        for attr in ("leaf", "field_name"):
            val = getattr(rec, attr, None)
            if val is None and isinstance(rec, dict):
                val = rec.get(attr)
            if val:
                names.add(str(val))
    return names


def parse_output_surface(spec, output_file: Path) -> Set[str]:
    """Parse the model's output surface into a set of variable names.

    A ``.nc`` reference tape is read directly via netCDF (the authoritative
    output surface). Anything else (a ``.cdl``/text output registry) is
    dispatched through ``spec.output_parser_class``.
    """
    suffix = output_file.suffix.lower()
    if suffix in (".nc", ".nc4", ".netcdf"):
        try:
            import netCDF4
        except ImportError as e:
            raise ImportError(
                "netCDF4 is required to read a .nc reference tape; "
                "install it or point --output-file at a .cdl output registry."
            ) from e
        ds = netCDF4.Dataset(str(output_file), "r")
        try:
            return set(ds.variables.keys())
        finally:
            ds.close()

    parser_cls = spec.output_parser_class
    if parser_cls is None:
        raise RuntimeError(
            f"Model '{spec.name}' spec has no output_parser_class; "
            "cannot validate the output surface from a non-netCDF file."
        )
    parser = parser_cls()
    return set(parser.parse(output_file).keys())


# =============================================================================
# Dimension validators
# =============================================================================

def validate_parameter_surface(curated: dict, param_names: Set[str],
                               param_files: List[Path]) -> DimensionResult:
    """Dimension A: every referenced parameter exists on SOME parameter surface.

    A MODEL CAN HAVE MORE THAN ONE PARAMETER SURFACE, and checking one of them turns this
    dimension into noise. Measured on EcoSIM 2026-09-12: it reported `[FAIL] 71/92` with 21 flagged
    parameters, of which 20 -- SPOSC, RMOM, VMXO, RCCZ, GO2X, OQKA, DCKI and the rest -- were
    microbial parameters that legitimately live on the TERTIARY surface (`micpar_file_in`) the
    validator did not know existed. A wall of 20 known-bogus lines is why the output went unread,
    and a real hit inside that list would have been invisible. So the check now takes the UNION of
    every surface it is given, and `main` says loudly which declared surfaces it was NOT given.
    """
    res = DimensionResult(name="A. Parameter surface")
    refs = collect_parameter_refs(curated)
    shown = ", ".join(p.name for p in param_files) or "<none>"
    for name in sorted(refs):
        res.total += 1
        ok = name in param_names
        if ok:
            res.pass_count += 1
        else:
            locs = ", ".join(sorted(set(refs[name]))[:4])
            res.errors.append(
                f"parameter '{name}' on NONE of the {len(param_files)} surface(s) "
                f"[{shown}] (referenced at: {locs})"
            )
        res.rows.append((name, ok, ", ".join(sorted(set(refs[name]))[:3])))
    res.notes.append(
        f"{len(refs)} distinct parameters referenced; "
        f"{len(param_names)} across {len(param_files)} surface(s): {shown}."
    )
    return res


def validate_output_surface(curated: dict, output_names: Set[str],
                            output_file: Path) -> DimensionResult:
    """Dimension B: every referenced output exists in the output surface."""
    res = DimensionResult(name="B. Output surface")
    refs = collect_output_refs(curated)
    for name in sorted(refs):
        res.total += 1
        ok = name in output_names
        if ok:
            res.pass_count += 1
        else:
            locs = ", ".join(sorted(set(refs[name]))[:4])
            res.errors.append(
                f"output '{name}' not in {output_file.name} "
                f"(referenced at: {locs})"
            )
        res.rows.append((name, ok, ", ".join(sorted(set(refs[name]))[:3])))
    res.notes.append(
        f"{len(refs)} distinct outputs referenced; "
        f"{len(output_names)} in the output surface."
    )
    return res


def validate_internal_consistency(curated: dict) -> DimensionResult:
    """Dimension C: mechanism/category cross-references all resolve.

    - Every mechanism referenced (categories.mechanisms, parameters.controls)
      is defined in the top-level ``mechanisms:`` block.
    - Every category referenced (parameters.category) is defined in the
      top-level ``categories:`` block.
    """
    res = DimensionResult(name="C. Internal consistency")

    defined_mechs = set((curated.get("mechanisms") or {}).keys())
    defined_cats = set((curated.get("categories") or {}).keys())

    mech_refs = collect_mechanism_refs(curated)
    cat_refs = collect_category_refs(curated)

    for name in sorted(mech_refs):
        res.total += 1
        ok = name in defined_mechs
        if ok:
            res.pass_count += 1
        else:
            locs = ", ".join(sorted(set(mech_refs[name]))[:4])
            res.errors.append(
                f"mechanism '{name}' referenced but not defined in mechanisms: "
                f"(at: {locs})"
            )
        res.rows.append((f"mechanism:{name}", ok,
                         ", ".join(sorted(set(mech_refs[name]))[:3])))

    for name in sorted(cat_refs):
        res.total += 1
        ok = name in defined_cats
        if ok:
            res.pass_count += 1
        else:
            locs = ", ".join(sorted(set(cat_refs[name]))[:4])
            res.errors.append(
                f"category '{name}' referenced but not defined in categories: "
                f"(at: {locs})"
            )
        res.rows.append((f"category:{name}", ok,
                         ", ".join(sorted(set(cat_refs[name]))[:3])))

    res.notes.append(
        f"{len(defined_mechs)} mechanisms defined / {len(mech_refs)} referenced; "
        f"{len(defined_cats)} categories defined / {len(cat_refs)} referenced."
    )
    return res


# =============================================================================
# Reporting
# =============================================================================

def _table(header: List[str], rows: List[Tuple]) -> List[str]:
    out = ["| " + " | ".join(header) + " |",
           "|" + "|".join(["---"] * len(header)) + "|"]
    for r in rows:
        out.append("| " + " | ".join(str(c) for c in r) + " |")
    return out


def build_markdown(model: str, yaml_path: Path, param_file: Path,
                   output_file: Path, curated: dict,
                   dims: List[DimensionResult], verdict: str) -> str:
    n_params = len(curated.get("parameters") or {})
    n_mechs = len(curated.get("mechanisms") or {})
    n_cats = len(curated.get("categories") or {})
    n_outs = len(curated.get("outputs") or {})

    out: List[str] = [
        f"# Curated-YAML Validation (V2): {model}",
        "",
        f"**Generated:** {datetime.utcnow().isoformat(timespec='seconds')}Z",
        "",
        f"**Model:** `{model}`",
        f"**YAML:** `{yaml_path}`",
        f"**Parameter file:** `{param_file}`",
        f"**Output surface:** `{output_file}`",
        "",
        "---",
        "",
        "## Summary",
        "",
        f"- categories: {n_cats}, mechanisms: {n_mechs}, "
        f"parameters: {n_params}, outputs: {n_outs}",
        "",
    ]
    out += _table(
        ["Dimension", "Status", "Pass / Total", "Errors"],
        [(d.name, d.status, f"{d.pass_count}/{d.total}", len(d.errors))
         for d in dims],
    )
    out += ["", f"**Overall verdict: {verdict}**", "", "---", ""]

    for d in dims:
        out += [f"## {d.name} — {d.status} ({d.pass_count}/{d.total})", ""]
        for n in d.notes:
            out.append(f"- {n}")
        out.append("")
        if d.errors:
            out.append("### Errors")
            out.append("")
            for e in d.errors:
                out.append(f"- {e}")
            out.append("")
        else:
            out += ["All references resolve.", ""]

    return "\n".join(out)


def print_console_report(model: str, dims: List[DimensionResult],
                         verdict: str) -> None:
    print("")
    print(f"=== Curated-YAML Validation (V2): {model} ===")
    for d in dims:
        mark = "PASS" if d.status == "PASS" else "FAIL"
        print(f"  [{mark}] {d.name}: {d.pass_count}/{d.total}")
        for n in d.notes:
            print(f"         - {n}")
        for e in d.errors[:20]:
            print(f"         ! {e}")
        if len(d.errors) > 20:
            print(f"         ! ... and {len(d.errors) - 20} more errors")
    print(f"\nOverall verdict: {verdict}\n")


# =============================================================================
# CLI
# =============================================================================

def parse_args() -> argparse.Namespace:
    ap = argparse.ArgumentParser(
        description="Model-generic curated-relationships YAML validator (V2)."
    )
    ap.add_argument("--model", required=True,
                    help="Adapter name (e.g. 'ecosim', 'fates').")
    ap.add_argument("--version", default=None,
                    help="Milestone/version to resolve default surfaces from "
                         "(default: canonical/last registered).")
    ap.add_argument("--yaml", type=Path, default=None,
                    help="Curated relationships YAML "
                         "(default: dataset.curated_yaml or "
                         "models/<model>/curated_seed.yaml).")
    ap.add_argument("--param-file", type=Path, default=None, action="append",
                    help="Parameter file. REPEATABLE -- pass it once per parameter "
                         "SURFACE the model has (EcoSIM has three: pft_file_in, "
                         "pft_mgmt_in, micpar_file_in). Default: dataset.parameter_file "
                         "only, which under-reports any model with more than one.")
    ap.add_argument("--output-file", type=Path, default=None,
                    help="Output surface: .nc reference tape or .cdl registry "
                         "(default: dataset.output_cdl).")
    ap.add_argument("--report", type=Path, default=None,
                    help="Optional path to write a Markdown report.")
    return ap.parse_args()


def _resolve_paths(args, spec, dataset):
    """Fill in default YAML/param/output paths from the dataset + conventions."""
    model = args.model

    yaml_path = args.yaml
    if yaml_path is None:
        if dataset is not None and getattr(dataset, "curated_yaml", None):
            yaml_path = Path(dataset.curated_yaml)
        else:
            yaml_path = REPO_ROOT / "models" / model / "curated_seed.yaml"

    param_files = args.param_file or []
    if not param_files and dataset is not None and dataset.parameter_file:
        param_files = [dataset.parameter_file]
    output_file = args.output_file
    if output_file is None and dataset is not None:
        output_file = dataset.output_cdl

    # Resolve relative paths against the repo root.
    def _abs(p):
        if p is None:
            return None
        p = Path(p)
        return p if p.is_absolute() else (REPO_ROOT / p)

    return _abs(yaml_path), [_abs(p) for p in param_files], _abs(output_file)


def main() -> int:
    args = parse_args()

    try:
        spec, dataset = load_model_spec_and_dataset(args.model, args.version)
    except Exception as e:
        print(f"ERROR: could not load model '{args.model}': {e}",
              file=sys.stderr)
        return 1

    yaml_path, param_files, output_file = _resolve_paths(args, spec, dataset)

    missing = []
    if not param_files:
        missing.append("--param-file (no default available; pass explicitly)")
    for pf in param_files:
        if not Path(pf).exists():
            missing.append(f"--param-file not found: {pf}")
    for label, p in (("yaml", yaml_path), ("output-file", output_file)):
        if p is None:
            missing.append(f"--{label} (no default available; pass explicitly)")
        elif not Path(p).exists():
            missing.append(f"--{label} not found: {p}")
    if missing:
        for m in missing:
            print(f"ERROR: {m}", file=sys.stderr)
        return 1

    print(f"Model:        {args.model}  ({spec.display_name})")
    print(f"YAML:         {yaml_path}")
    for i, pf in enumerate(param_files):
        print(f"Param file:   {pf}" if i == 0 else f"              {pf}")
    print(f"Output file:  {output_file}")

    # A model may declare surfaces this invocation was not given. Say so BEFORE the results, so a
    # dimension-A failure is attributable to a missing surface rather than read as a curation error.
    declared = [v for v in ("secondary_namelist_var", "tertiary_namelist_var")
                if getattr(spec, v, None)]
    if declared and len(param_files) < 1 + len(declared):
        print(f"\nNOTE: {spec.display_name} declares {1 + len(declared)} parameter surfaces "
              f"({', '.join(['the primary'] + [getattr(spec, v) for v in declared])}) but only "
              f"{len(param_files)} was checked. Parameters living on an unchecked surface WILL be "
              f"reported missing and are false alarms. Pass --param-file once per surface.")

    curated = yaml.safe_load(Path(yaml_path).read_text(encoding="utf-8"))

    param_names: Set[str] = set()
    for pf in param_files:
        try:
            param_names |= parse_parameter_surface(spec, Path(pf))
        except Exception as e:
            print(f"ERROR: parameter parsing failed on {pf}: {e}", file=sys.stderr)
            return 1
    try:
        output_names = parse_output_surface(spec, Path(output_file))
    except Exception as e:
        print(f"ERROR: output parsing failed: {e}", file=sys.stderr)
        return 1

    dim_a = validate_parameter_surface(curated, param_names,
                                       [Path(p) for p in param_files])
    dim_b = validate_output_surface(curated, output_names, Path(output_file))
    dim_c = validate_internal_consistency(curated)
    dims = [dim_a, dim_b, dim_c]

    verdict = "PASS" if all(d.status == "PASS" for d in dims) else "FAIL"
    print_console_report(args.model, dims, verdict)

    if args.report:
        md = build_markdown(args.model, Path(yaml_path), Path(param_files[0]),
                            Path(output_file), curated, dims, verdict)
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(md, encoding="utf-8")
        print(f"Wrote report: {args.report}")

    return 0 if verdict == "PASS" else 2


if __name__ == "__main__":
    sys.exit(main())
