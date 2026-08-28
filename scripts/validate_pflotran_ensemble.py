#!/usr/bin/env python3
"""Validate a materialized PFLOTRAN ensemble before submission — a hard pre-submit gate.

The PFLOTRAN-specific parallel of `scripts/validate_adapter_ensemble.py`, which is written for a
model whose parameter surface is a **NetCDF PFT file** and cannot describe this one. Two things in
that script are structural, not incidental:

  * it probes surfaces with `nc_varnames`, so it raises `OSError: NetCDF: Unknown file format` on a
    text input deck, and
  * its canonical-id regex is `^(name)_(\\d+)$` — an INTEGER PFT index — while PFLOTRAN's grouping
    axis is a NAME (`PERM_ISO_Bolitic`, `RATE_CONSTANT_Glass_FB`, `M_all3`), so not one miniLEO
    parameter would parse.

Hence a parallel script rather than a flag on the shared one ([[feedback_per_model_scripts_not_generic]]:
A2MC's own machinery stays generic; a per-model ARTIFACT script is parallel). Nothing here edits
the adapter validator.

WHAT IT CHECKS, per case
------------------------
  1. STRUCTURE   — the case dir exists and holds its deck, `submit.sh`, and every static input the
                   deck needs beside it (mesh, side sets, restart checkpoint, rainfall, database).
  2. DECK VALUES — for every calibrated (leaf, sub-address): the case deck's value equals the
                   matrix cell, exponentiated for the log10-sampled names, to the writer's own
                   `%.10g` precision. Catches a wrong value, a wrong parameter, or a wrong column.
  3. NOTHING ELSE — the set of lines differing from the BASE deck is EXACTLY the set the expected
                   edits touch. For a text deck this single check subsumes the adapter validator's
                   separate "other PFTs untouched" and "non-calibrated sample unchanged" passes,
                   and it is stronger: it is exhaustive rather than sampled.
  4. BOUNDS      — every sampled value lies inside the param list's own [lower, upper].
  5. BASELINE    — the V0 case's deck is BYTE-IDENTICAL to the base deck.
  6. SUBMIT      — `submit.sh` names an existing binary and this case's own deck.

Exit 0 = all green. Exit 1 = at least one case failed (the first offenders are printed).

Usage (source the site config first — it supplies every default):
    ~/a2mc_env/bin/python scripts/validate_pflotran_ensemble.py [--expect-baseline]
    ... [--start N] [--end M] [--run-root DIR] [--base-param DECK]

Author: Jing Tao with Claude
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

import numpy as np

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from scripts.create_adapter_parameter_sample import parse_pft_param_list  # noqa: E402
from models.pflotran.backend import PFLOTRANBackend  # noqa: E402
from models.pflotran.parameter_parser import PFLOTRANParameterParser  # noqa: E402

# Static inputs the miniLEO deck resolves RELATIVE TO THE WORKING DIRECTORY, so each must sit in
# the case dir. A missing one aborts part-way through a run that Slurm may still call COMPLETED
# (the run template warns about the same thing at launch time; this catches it before submission).
REQUIRED_INPUTS = (
    "savannah_river.dat",
    "rainfall_PERTH_spinup3224h.txt",
    "mesh_rotated10_0.025_ugi.h5",
    "pflotran-presteadystate_restart_1-11.h5",
)


def _case_name(pattern: str, n) -> str:
    return pattern.replace("{N}", str(n))


def _expected_edits(backend, names, row, base_params):
    """canonical id -> {deck address: expected token}, mirroring write_parameter_file exactly."""
    out = {}
    for cid, value in zip(names, row):
        leaf, subaddr = backend._split_canonical_id(cid)
        addrs = backend._resolve_addresses(leaf, subaddr, base_params)
        if not addrs:
            raise KeyError(f"{cid!r} resolved to no deck address")
        val = 10.0 ** float(value) if leaf in backend._LOG10_LEAF_NAMES else float(value)
        out[cid] = {a: f"{val:.10g}" for a in addrs}
    return out


def _check_case(case_dir: Path, deck_name: str, base_text: str, base_params, expected, binary):
    """Return a list of failure strings (empty = the case is clean)."""
    bad = []
    deck = case_dir / deck_name

    # 1. STRUCTURE
    if not case_dir.is_dir():
        return [f"case dir missing: {case_dir}"]
    if not deck.is_file():
        return [f"deck missing: {deck}"]
    for f in REQUIRED_INPUTS:
        if not (case_dir / f).is_file():
            bad.append(f"static input not staged: {f}")
    submit = case_dir / "submit.sh"
    if not submit.is_file():
        bad.append("submit.sh missing")

    case_params = PFLOTRANParameterParser().parse(deck)

    # 2. DECK VALUES
    touched_lines = set()
    for cid, addr_tokens in expected.items():
        for addr, token in addr_tokens.items():
            prm = case_params.get(addr)
            if prm is None:
                bad.append(f"{cid}: address {addr} absent from the case deck")
                continue
            if prm.raw.strip() != token:
                bad.append(f"{cid}: {addr} is {prm.raw.strip()!r}, expected {token!r}")
            touched_lines.add(base_params[addr].line)

    # 3. NOTHING ELSE WRITTEN — exhaustive line diff against the base deck
    case_lines = deck.read_text(errors="replace").splitlines()
    base_lines = base_text.splitlines()
    if len(case_lines) != len(base_lines):
        bad.append(f"deck has {len(case_lines)} lines, base has {len(base_lines)} "
                   "— a line was added or removed, not just edited")
    else:
        differing = {i + 1 for i, (a, b) in enumerate(zip(case_lines, base_lines)) if a != b}
        unexpected = differing - touched_lines
        if unexpected:
            bad.append(f"lines differ from the base that no calibrated parameter addresses: "
                       f"{sorted(unexpected)[:8]}")

    # 6. SUBMIT — parse the ASSIGNMENTS, never a substring search.
    #
    # This check was written as `if deck.name not in txt` and SILENTLY PASSED a mutation test that
    # repointed DECK= at /nonexistent/other.in (2026-08-27): the rendered template mentions
    # "pflotran.in" in its own comments, so the bare substring matched regardless of what the
    # script would actually run. A check that cannot fail is not a check
    # ([[feedback_a_check_that_cannot_fail]]) -- so resolve the real values instead.
    if submit.is_file():
        assigns = {}
        for line in submit.read_text(errors="replace").splitlines():
            t = line.strip()
            if t.startswith("#") or "=" not in t:
                continue
            k, _, v = t.partition("=")
            if k.strip() in ("EXE", "DECK", "WORK") and k.strip() not in assigns:
                assigns[k.strip()] = v.split("#")[0].strip().strip('"')
        for key in ("EXE", "DECK", "WORK"):
            if key not in assigns:
                bad.append(f"submit.sh has no {key}= assignment")
        if "DECK" in assigns and Path(assigns["DECK"]).resolve() != deck.resolve():
            bad.append(f"submit.sh DECK={assigns['DECK']} is not this case's deck ({deck})")
        if "WORK" in assigns and Path(assigns["WORK"]).resolve() != case_dir.resolve():
            bad.append(f"submit.sh WORK={assigns['WORK']} is not this case dir ({case_dir})")
        if "EXE" in assigns:
            exe = Path(assigns["EXE"])
            if not exe.is_file():
                bad.append(f"submit.sh EXE={exe} does not exist")
            elif binary and exe.resolve() != Path(binary).resolve():
                bad.append(f"submit.sh EXE={exe} is not the configured binary ({binary})")
    return bad


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    env = os.environ.get
    ap.add_argument("--param-list", default=env("A2MC_PARAM_LIST_FILE"))
    ap.add_argument("--matrix", default=env("A2MC_ENSEMBLE_MATRIX_FILE"))
    ap.add_argument("--run-root", default=env("A2MC_OUTPUT_DIR"))
    ap.add_argument("--base-param", default=env("A2MC_BASE_PARAM_FILE"))
    ap.add_argument("--case-pattern", default=env("A2MC_CASE_NAME_PATTERN", "miniLEO_case{N}"))
    ap.add_argument("--start", type=int, default=1)
    ap.add_argument("--end", type=int, default=0, help="0 = every row in the matrix")
    ap.add_argument("--baseline-index", type=int, default=0)
    ap.add_argument("--expect-baseline", action="store_true",
                    help="require the V0 baseline case and assert its deck is byte-identical "
                         "to the base. A round whose V0 exists only as a matrix row cannot "
                         "answer 'does the base still reproduce?'")
    args = ap.parse_args()

    for name, val in (("--param-list", args.param_list), ("--matrix", args.matrix),
                      ("--run-root", args.run_root), ("--base-param", args.base_param)):
        if not val:
            print(f"ERROR: {name} not set (source the site config first)", file=sys.stderr)
            return 2

    base = Path(args.base_param)
    run_root = Path(args.run_root)
    base_text = base.read_text(errors="replace")
    base_params = PFLOTRANParameterParser().parse(base)
    backend = PFLOTRANBackend()
    binary = os.environ.get("A2MC_PFLOTRAN_BINARY", "")

    names, lo, hi = parse_pft_param_list(args.param_list)[:3]
    X = np.loadtxt(args.matrix)
    if X.ndim == 1:
        X = X.reshape(1, -1)
    if X.shape[1] != len(names):
        print(f"ERROR: matrix has {X.shape[1]} columns, param list has {len(names)} names",
              file=sys.stderr)
        return 2

    end = args.end if args.end > 0 else X.shape[0]
    start = max(1, args.start)
    end = min(end, X.shape[0])

    print(f"Run root:    {run_root}")
    print(f"Base deck:   {base} ({len(base_params)} addressable cards)")
    print(f"Param list:  {len(names)} params  |  matrix {X.shape[0]} x {X.shape[1]}")
    print(f"Validating:  cases {start}..{end}"
          + (f" + V0 baseline (case {args.baseline_index})" if args.expect_baseline else ""))
    print()

    failures = {}

    # 5. BASELINE — byte-identical, which is the whole point of a V0 reference.
    #
    # Run it through the SAME _check_case as every other case, with an empty expected-edits map:
    # that gives it the structure, staged-input and submit.sh checks for free, and the line-diff
    # check then asserts ZERO differing lines, which IS the byte-identity requirement. Written
    # first as a bespoke three-line branch, which silently exempted the baseline from the
    # submit.sh checks -- caught 2026-08-27 when binding the config to the archived binary
    # flagged cases 1-3 and left case 0 green. The V0 case's binary binding matters MORE than a
    # member's, not less: it is the case every other result is measured against.
    if args.expect_baseline:
        bl = run_root / _case_name(args.case_pattern, args.baseline_index)
        bad = _check_case(bl, base.name, base_text, base_params, {}, binary)
        if (bl / base.name).is_file() and (bl / base.name).read_text(errors="replace") != base_text:
            bad.append("baseline deck is NOT byte-identical to the base deck")
        if bad:
            failures[bl.name] = bad

    # 4. BOUNDS — checked once over the whole matrix rather than per case.
    for j, (n, a, b) in enumerate(zip(names, lo, hi)):
        col = X[start - 1:end, j]
        if col.size and (col.min() < a - 1e-12 or col.max() > b + 1e-12):
            failures.setdefault("__bounds__", []).append(
                f"{n}: sampled [{col.min():.6g}, {col.max():.6g}] outside [{a}, {b}]")

    # 1/2/3/6 — per case.
    for i in range(start, end + 1):
        cname = _case_name(args.case_pattern, i)
        try:
            expected = _expected_edits(backend, names, X[i - 1], base_params)
        except (KeyError, ValueError) as e:
            failures[cname] = [f"cannot derive expected edits: {e}"]
            continue
        bad = _check_case(run_root / cname, base.name, base_text, base_params, expected, binary)
        if bad:
            failures[cname] = bad

    n_checked = (end - start + 1) + (1 if args.expect_baseline else 0)
    if not failures:
        print(f"✓ {n_checked} case(s) validated — decks, staged inputs, bounds and submit "
              f"scripts all match the design. Ready to submit.")
        return 0

    print(f"✗ {len(failures)} case(s)/check(s) FAILED of {n_checked} checked:\n")
    for cname in list(failures)[:12]:
        print(f"  {cname}:")
        for b in failures[cname][:6]:
            print(f"      {b}")
    if len(failures) > 12:
        print(f"  ... and {len(failures) - 12} more")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
