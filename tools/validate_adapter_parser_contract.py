#!/usr/bin/env python
"""Validate an adapter's parser CONTRACT: call shape, record shape, and field completeness.

Why this exists
---------------
The adapter contract (`models/_template/`, V4) pins the CALL shape -- a no-arg constructor plus
`parse(file_path)` -- but says nothing about the RECORD shape that `parse()` returns. In practice
the two shipped adapters disagree:

    EcoSIM  ->  {name: <dataclass>}   consumers read  par.units
    ATS     ->  {name: <dict>}        consumers read  par["units"]

This is why the per-model build scripts stay parallel (`build_rag_index.py` /
`build_ecosim_rag.py` / `build_ats_rag.py`) rather than merged: each reads its own model's record
shape directly, so no shared dual-shape accessor is needed. The check still matters for the tools
that ARE model-generic by design -- one written against a single record shape is a latent break
for the next adapter.

This validator therefore checks the FIELDS a generic consumer needs, not the type -- so either
shape passes as long as the information is actually there. It is the missing half of V4.

Checks
------
    P1  call shape        parser_class() takes no args; .parse(path) accepts a path
    P2  return shape      parse() returns a non-empty mapping {str: record}
    P3  record access     every record answers the required fields via attr OR key
    P4  field population  required fields are not universally None/empty (a field that is
                          present but never populated is indistinguishable from a missing one
                          to a consumer, and silently degrades RAG chunk text)

Read-only. Exit 0 if the contract holds, 1 otherwise.

Usage:
    python tools/validate_adapter_parser_contract.py --model ats
    python tools/validate_adapter_parser_contract.py --model ecosim --param-file <f> --output-file <f>

Author: Jing Tao with Claude
"""
from __future__ import annotations

import argparse
import importlib
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

# Fields a generic consumer (RAG chunk builder, graph builder, bounds generator) needs.
# `required` must be readable AND populated for at least one record; `optional` must merely be
# readable -- absence is tolerated because not every model has the concept.
PARAM_REQUIRED = ("category", "units", "long_name")
PARAM_OPTIONAL = ("dimensions", "is_string", "is_pft_specific")
OUTPUT_REQUIRED = ("category", "units", "long_name")
OUTPUT_OPTIONAL = ("dimensions", "dimension_level")


def _get(rec, name):
    """Read a field off a dataclass OR dict record. Returns (found, value)."""
    if isinstance(rec, dict):
        return (name in rec), rec.get(name)
    return hasattr(rec, name), getattr(rec, name, None)


def _resolve_files(model: str, param_file, output_file):
    """Fall back to the model's ModelDataset registry when files are not given."""
    if param_file and output_file:
        return Path(param_file), Path(output_file)
    try:
        ds_mod = importlib.import_module(f"models.{model}.datasets")
        registry = next(v for k, v in vars(ds_mod).items() if k.endswith("_DATASETS"))
        ds = next(iter(registry.values()))
        return (Path(param_file) if param_file else REPO / ds.parameter_file,
                Path(output_file) if output_file else REPO / ds.output_cdl)
    except Exception as e:
        sys.exit(f"ERROR: could not resolve input files for '{model}' ({e}). "
                 f"Pass --param-file and --output-file explicitly.")


def check_surface(kind: str, parser, path: Path, required, optional, errors, warnings):
    print(f"\n  {kind} parser: {type(parser).__name__}  <- {path.name}")

    # P1/P2 -- call shape and return shape
    try:
        recs = parser.parse(str(path))
    except TypeError as e:
        errors.append(f"{kind}: parse(file_path) rejected a path argument ({e}). The contract is "
                      f"a no-arg constructor + parse(file_path); the legacy FATES shape "
                      f"(path-in-constructor + no-arg parse) is grandfathered, not the contract.")
        return
    except Exception as e:
        errors.append(f"{kind}: parse() raised {type(e).__name__}: {e}")
        return

    if not isinstance(recs, dict) or not recs:
        errors.append(f"{kind}: parse() returned {type(recs).__name__} "
                      f"(expected a non-empty mapping {{name: record}})")
        return
    sample = next(iter(recs.values()))
    shape = "dict" if isinstance(sample, dict) else type(sample).__name__
    print(f"    records: {len(recs)}   record shape: {shape}")

    # P3 -- every record answers the required fields somehow
    for field in required + optional:
        missing = [n for n, r in recs.items() if not _get(r, field)[0]]
        if missing and field in required:
            errors.append(f"{kind}: {len(missing)}/{len(recs)} records cannot answer required "
                          f"field {field!r} (e.g. {missing[0]!r})")
        elif missing and len(missing) == len(recs):
            print(f"    [note] optional field {field!r} absent on all records")

    # P4 -- required fields are actually populated somewhere
    for field in required:
        vals = [_get(r, field)[1] for r in recs.values()]
        if all(v in (None, "", [], {}) for v in vals):
            warnings.append(f"{kind}: required field {field!r} is present but NEVER populated "
                            f"across {len(recs)} records — a consumer cannot distinguish this "
                            f"from a missing field, and RAG chunk text degrades silently")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--model", required=True, help="Adapter name, e.g. ats / ecosim")
    ap.add_argument("--param-file", help="Override the ModelDataset parameter file")
    ap.add_argument("--output-file", help="Override the ModelDataset output file")
    a = ap.parse_args()

    importlib.import_module(f"models.{a.model}")
    from models import registry
    spec = registry.get_model(a.model).spec

    print("=" * 66)
    print(f"ADAPTER PARSER CONTRACT — {a.model}")
    print("=" * 66)

    errors: list[str] = []
    warnings: list[str] = []

    for attr in ("parameter_parser_class", "output_parser_class"):
        if getattr(spec, attr, None) is None:
            errors.append(f"spec.{attr} is None — the adapter has no parser to validate")
    if errors:
        for e in errors:
            print(f"  FAIL  {e}")
        print("\nOVERALL: FAIL")
        return 1

    pfile, ofile = _resolve_files(a.model, a.param_file, a.output_file)
    check_surface("parameter", spec.parameter_parser_class(), pfile,
                  PARAM_REQUIRED, PARAM_OPTIONAL, errors, warnings)
    check_surface("output", spec.output_parser_class(), ofile,
                  OUTPUT_REQUIRED, OUTPUT_OPTIONAL, errors, warnings)

    print()
    for w in warnings:
        print(f"  WARN  {w}")
    for e in errors:
        print(f"  FAIL  {e}")
    ok = not errors
    print(f"\nOVERALL: {'PASS' if ok else 'FAIL'}"
          f"{'  (with ' + str(len(warnings)) + ' warning(s))' if warnings and ok else ''}")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
