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


def _is_list_numeric(body: bytes) -> bool:
    """True when a record is the comma-separated numeric kind a list-directed READ consumes."""
    if b"," not in body:
        return False
    fields = body.decode(errors="replace").split(",")
    parsed = 0
    for f in fields:
        try:
            float(f)
        except ValueError:
            return False      # one non-numeric field and it is not a numeric record
        parsed += 1
    return parsed >= 2


def _mixed_char_padding(path: Path) -> list[str]:
    """Character variables in a NetCDF input whose records disagree about the pad byte.

    A Fortran model reads a fixed-length character record and ``trim()``s it, and ``trim()``
    removes trailing BLANKS only -- a NUL survives into the last field, so the list-directed
    read of a NUL-padded record fails with "Bad real number in item N of list input". This is
    model-agnostic: no Fortran ``trim()`` strips a NUL.

    The check is for DISAGREEMENT rather than for NULs as such, because a uniformly NUL-padded
    file may be what its author intended and its reader may handle. A variable whose records
    use both conventions was written by two tools, and the records departing from the file's
    own convention are the ones the binary cannot read.

    It is also restricted to records a LIST-DIRECTED READ consumes -- comma-separated numeric
    fields -- because only those break. A plain name string tolerates a NUL: it is read whole
    and never scanned for a numeric field, so a shipped parameter file can carry a NUL-padded
    name beside a space-padded one and run correctly. Judging padding alone condemns such a
    file, which is worse than silence: it sends the next session after a defect that is not
    there. The discriminator is read off the record's own content, not declared anywhere.

    Reconstruct every record with ``.tobytes()``: numpy's ``'S'`` dtype treats a NUL as
    padding, so ``b"".join(arr.tolist())`` silently erases the very bytes under test.
    """
    try:
        import netCDF4 as nc
        import numpy as np
    except ImportError:
        return []
    problems: list[str] = []
    try:
        ds = nc.Dataset(path)
    except Exception:
        return []            # not NetCDF (e.g. an api-43 .json param file) -- nothing to check
    try:
        ds.set_auto_mask(False)
        for name, var in ds.variables.items():
            if var.dtype != np.dtype("S1") or var.ndim < 1:
                continue
            nchar = var.shape[-1]
            flat = np.asarray(var[:]).reshape(-1, nchar)
            if flat.shape[0] > 200_000:          # keep a pathological file cheap
                flat = flat[:200_000]
            nul = space = 0
            first_nul = None
            for i in range(flat.shape[0]):
                rec = flat[i].tobytes()
                if not rec.strip(b"\x00 "):
                    continue                      # an unused slot, never read
                body = rec.rstrip(b" ")
                if not _is_list_numeric(body.rstrip(b"\x00")):
                    continue                      # a name string; a NUL in it is harmless
                if body.endswith(b"\x00"):
                    nul += 1
                    if first_nul is None:
                        first_nul = (i, body.rstrip(b"\x00")[:60])
                elif len(body) < nchar:
                    space += 1
            if nul and space:
                idx, sample = first_nul
                problems.append(
                    f"{name}: {space} record(s) space-padded but {nul} NUL-padded, so the "
                    f"NUL-padded ones survive trim() and fail the read. First at flat index "
                    f"{idx}: {sample.decode(errors='replace')!r}")
    finally:
        ds.close()
    return problems


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--model", required=True, help="onboarded model name (e.g. ecosim)")
    ap.add_argument("--checkout", help="model source-tree root (the built version)")
    ap.add_argument("--param-file", help="input/parameter file to check against the binary's reads")
    ap.add_argument("--padding-only", action="store_true",
                    help="run ONLY the char-record padding check and skip the variable-compat "
                         "contract. Use this for any surface other than the primary one: the "
                         "compat contract is declared against the primary surface's reader, so "
                         "pointing it at a management or microbial file reports every primary "
                         "variable as missing. Padding applies to every surface.")
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

    # ---- 0. Char-record padding. Runs before the compat contract, because a model that
    # declares no REQUIRES contract is just as unable to read a NUL-padded record. ----
    if args.param_file and Path(args.param_file).exists():
        pad_problems = _mixed_char_padding(Path(args.param_file))
        if pad_problems:
            print(f"UNREADABLE — {len(pad_problems)} character variable(s) in the input are padded "
                  f"inconsistently, and the binary aborts on the records that disagree:")
            for p in pad_problems:
                print(f"    {p}")
            print("  → Pad every record with the byte the file's own records use (derive it from a "
                  "record, do not choose one), then read the file back and confirm each record "
                  "parses before submitting.")
            return 2
        if args.padding_only:
            print(f"PADDING OK — every LIST-READ character record in {Path(args.param_file).name} "
                  f"uses one pad convention, so the binary's trim() reaches a clean field. A "
                  f"name string is not checked, because a NUL in one is harmless.")
            return 0
    elif args.padding_only:
        print("ERROR: --padding-only needs --param-file.", file=sys.stderr)
        return 1

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
