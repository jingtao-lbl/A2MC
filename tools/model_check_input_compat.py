#!/usr/bin/env python
"""Generic pre-submit input↔binary version-compat guard for ANY onboarded model.

The model-agnostic distillation of `tools/ecosim_check_input_compat.py` (the
EcoSIM-specific original, kept UNTOUCHED because `scripts/run_ecosim_smoke_ensemble.py`
imports from it). Per the adapter-kit additive rule (docs/38 §3): this is a NEW file
that dispatches through the active model's ``ModelSpec`` + ``ModelBackend`` — so it
works for --model ecosim now and any future adapter, without editing the FATES-shaped
originals.

The problem it catches: a model binary reads a fixed set of input-file variables. If
the input file is from an OLDER version than the built binary, it can be missing
variables the binary requires — the run then aborts mid-read after wasting an HPC
submit (EcoSIM's IEBTYP 17-variable mismatch; see `memory/dev_logs_adapterkit/
20260712b`). This guard diffs the binary's required reads against the input file
BEFORE submit.

What it does, dispatched through ``models/<model>/spec.py``:
  1. REQUIRES set — if ``spec.input_reader_sources`` AND ``spec.input_read_pattern``
     are both set, compile the pattern and ``re.findall`` it over each
     (checkout / rel) source file → the set of input vars the binary requires.
     If either field is empty, the model declares no input-reader compat contract:
     print an N/A message and exit 0 (graceful no-op).
  2. HAVE set — ``backend.parse_parameters(param_file).keys()``, which dispatches
     through the adapter's parser and so handles the model's native format
     (EcoSIM .nc AND api-43 .json, etc.).
  3. Diff — ``missing = sorted(requires - have)``.

Exit codes:
    0  COMPATIBLE (or N/A — no compat contract declared)
    1  IO / usage error (checkout, param file, or reader source not found)
    2  INCOMPATIBLE (input missing required vars) OR unknown/un-onboarded model

Usage:
    python tools/model_check_input_compat.py --model ecosim \
        --checkout ~/EcoSIM \
        --param-file Offline/EcoSIM_sample_files/input/ds_input__pft_test__ex1.nc

Author: Jing Tao with Claude
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--model", required=True, help="onboarded model name (e.g. ecosim)")
    ap.add_argument("--checkout", help="model source-tree root (the built version)")
    ap.add_argument("--param-file", help="input/parameter file to check against the binary's reads")
    args = ap.parse_args()

    # ---- Dispatch: import the model package (self-registers its backend) ----
    sys.path.insert(0, str(REPO))
    try:
        import importlib
        from models import registry
    except Exception as e:  # pragma: no cover
        print(f"ERROR: cannot import model registry: {e}", file=sys.stderr)
        return 1
    try:
        importlib.import_module(f"models.{args.model}")
        backend = registry.get_model(args.model)
    except ModuleNotFoundError:
        print(f"ERROR: model '{args.model}' is not onboarded (no models/{args.model}/ package).", file=sys.stderr)
        print("       A brand-new model needs the `onboard-model` skill first.", file=sys.stderr)
        return 2
    except Exception as e:
        print(f"ERROR: model '{args.model}' not onboarded: {e}", file=sys.stderr)
        print("       (a brand-new model needs the `onboard-model` skill first)", file=sys.stderr)
        return 2
    spec = backend.spec

    # ---- 1. REQUIRES set (graceful no-op if the model declares no contract) ----
    if not (spec.input_reader_sources and spec.input_read_pattern):
        print(f"N/A — {spec.display_name} declares no input-reader compat contract "
              f"(spec.input_reader_sources / input_read_pattern empty); nothing to check.")
        return 0

    if not args.checkout or not args.param_file:
        print("ERROR: --checkout and --param-file are both required for the compat check.", file=sys.stderr)
        return 1

    checkout, pf = Path(args.checkout), Path(args.param_file)
    if not checkout.is_dir():
        print(f"ERROR: checkout not found: {checkout}", file=sys.stderr)
        return 1
    if not pf.exists():
        print(f"ERROR: param file not found: {pf}", file=sys.stderr)
        return 1

    try:
        read_re = re.compile(spec.input_read_pattern)
    except re.error as e:
        print(f"ERROR: spec.input_read_pattern is not a valid regex: {e}", file=sys.stderr)
        return 1

    requires: set[str] = set()
    for rel in spec.input_reader_sources:
        src = checkout / rel
        if not src.exists():
            print(f"ERROR: input reader source not found: {src}", file=sys.stderr)
            return 1
        try:
            requires |= set(read_re.findall(src.read_text(errors="ignore")))
        except OSError as e:
            print(f"ERROR: cannot read reader source {src}: {e}", file=sys.stderr)
            return 1

    # ---- 2. HAVE set (dispatches through the adapter parser → handles .nc/.json) ----
    try:
        have = set(backend.parse_parameters(pf).keys())
    except Exception as e:
        print(f"ERROR: cannot parse input file {pf}: {e}", file=sys.stderr)
        return 1

    # ---- 3. Diff + verdict ----
    missing = sorted(requires - have)
    print(f"binary requires {len(requires)} input var(s) "
          f"(from {', '.join(spec.input_reader_sources)}); input file has {len(have)} var(s)")
    if not missing:
        print(f"COMPATIBLE — the input file has every variable the {spec.display_name} binary reads.")
        return 0

    print(f"INCOMPATIBLE — the input is missing {len(missing)} variable(s) the {spec.display_name} binary reads:")
    print("    " + ", ".join(missing))
    print(f"  → The input file is from an older {spec.display_name} than the built binary. The run would")
    print("    abort mid-read ('Variable not found'). Rebuild the binary at the input's commit,")
    print("    or regenerate the input with these variables, before submitting.")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
