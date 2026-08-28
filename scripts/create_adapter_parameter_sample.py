#!/usr/bin/env python3
"""Generate a parameter sample for an ADAPTER (non-FATES) model's Phase 0.

Parallel to ``phases/phase0_design/create_parameter_sample.py`` (the FATES/CIME sampler),
for models whose param list uses the model-agnostic **explicit-column** format:

    name, pft, ..., lower_bound, upper_bound, ...

where ``name`` is the BARE variable name and ``pft`` is its OWN column (blank / ``-`` / ``0``
= a global/scalar param). A2MC builds the canonical id ``{name}_{pft}`` — the shape the model
backends already parse (`models/<name>/backend.py`) — so the PI's principle holds: A2MC reads
a variable **and its PFT dimension** from explicit columns, not from a suffix baked into the name.
The matrix column order == the CSV row order.

WHY A PARALLEL SCRIPT (not a branch in the shared sampler): on the adapter-kit branch the FATES
sampler `create_parameter_sample.py` is byte-locked to `main` (docs/38 additive-superset rule —
never rewrite a FATES-shared file). FATES declares per-PFT/organ params through its own loader
`tools/param_spec.py` (`fates_name`/`pft`/`organ` → canonical id); THIS is the adapter analog for
the generic `name`+`pft` format. The SALib sampling itself is model-agnostic, so this script
**imports** (reuses, does not modify) `sample_morris`/`sample_sobol`/`sample_lhs` + the writers
from the shared module.

Usage (same knobs/env defaults as the FATES sampler):
    source a2mc_noncime_config.sh
    source use_cases/<site>/config/<site>_config.sh
    python scripts/create_adapter_parameter_sample.py --method morris --trajectories 20 --seed 123
"""

from __future__ import annotations

import argparse
import os
import re
import sys
from pathlib import Path
from typing import List, Tuple

import numpy as np
import pandas as pd

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

# Reuse (import, never edit) the shared, model-agnostic sampling + writers.
from phases.phase0_design.create_parameter_sample import (  # noqa: E402
    _detect_header_row,
    _detect_delimiter,
    _find_bound_columns,
    sample_morris,
    sample_sobol,
    sample_lhs,
    write_matrix,
    write_problem_text,
)


def canonical_pft_id(name: str, pft) -> str:
    """Canonical id from a bare variable name + an explicit pft cell.

    pft blank / ``-`` / ``0`` (a global/scalar param) → the bare name; else ``{name}_{pft}``.
    """
    nm = str(name).strip()
    raw = str(pft).strip()
    try:
        p = int(float(raw))
        return nm if p == 0 else f"{nm}_{p}"
    except (ValueError, TypeError):
        return nm if raw.lower() in ("", "-", "none", "nan") else f"{nm}_{raw}"


def parse_pft_param_list(path) -> Tuple[List[str], np.ndarray, np.ndarray]:
    """Parse a ``name`` + ``pft`` explicit-column param list → (canonical_ids, lower, upper).

    canonical_ids are ``{name}_{pft}`` (or bare ``name`` for a global param), in CSV row order
    (== Morris matrix column order). Raises on duplicate ids or lower >= upper.
    """
    path = Path(path)
    if not path.is_file():
        raise FileNotFoundError(f"Parameter list file not found: {path}")
    skiprows = _detect_header_row(path)
    header_line = ""
    with path.open() as f:
        for i, line in enumerate(f):
            if i == skiprows:
                header_line = line
                break
    delim = _detect_delimiter(header_line)
    df = pd.read_csv(path, sep=delim, skiprows=skiprows, engine="python")
    df.columns = [c.strip() for c in df.columns]
    if "name" not in df.columns or "pft" not in df.columns:
        raise ValueError(
            f"{path}: adapter param list needs BOTH a `name` and a `pft` column "
            f"(explicit-column format); got {list(df.columns)}"
        )
    lower_col, upper_col = _find_bound_columns(list(df.columns))
    df[lower_col] = pd.to_numeric(df[lower_col], errors="coerce")
    df[upper_col] = pd.to_numeric(df[upper_col], errors="coerce")
    df = df.dropna(subset=[lower_col, upper_col, "name"]).reset_index(drop=True)

    names = [canonical_pft_id(r["name"], r["pft"]) for _, r in df.iterrows()]
    lower = df[lower_col].to_numpy(dtype=float)
    upper = df[upper_col].to_numpy(dtype=float)

    if len(names) == 0:
        raise ValueError(f"No parameters parsed from {path}")
    if len(names) != len(set(names)):
        dupes = sorted({n for n in names if names.count(n) > 1})
        raise ValueError(f"Duplicate canonical ids (same name+pft) in {path}: {dupes}")
    bad = [(n, l, u) for n, l, u in zip(names, lower, upper) if l >= u]
    if bad:
        raise ValueError(f"Found {len(bad)} parameters with lower >= upper. First: {bad[0]}")
    return names, lower, upper


# =============================================================================
# Multi-surface routing — shared by materialize_adapter_ensemble.py and
# validate_adapter_ensemble.py (a param list can span more than one physical base file, e.g.
# EcoSIM_BioCON R3: 40 plant traits in the primary PFT NetCDF + 8 soil-BGC rates in the tertiary
# MicrobePars NetCDF). Kept here, not duplicated in each script, so the two never drift apart.
# =============================================================================

# The same "NAME_<int>" convention every backend's per-slot writer already parses (e.g. EcoSIM's
# `_MOD_PFT_RE`) — used here ONLY to find a canonical id's bare variable name for surface routing,
# never to do the actual indexed write (that stays inside the backend).
_SUFFIX_RE = re.compile(r"^(?P<base>[A-Za-z][A-Za-z0-9_]*?)_(?P<idx>\d+)$")


def bare_name(cid: str) -> str:
    """Canonical id -> its bare variable name (strips a trailing `_<int>` PFT/slot suffix)."""
    m = _SUFFIX_RE.match(cid)
    return m.group("base") if m else cid


def nc_varnames(path) -> set:
    """The set of variable names actually declared in a NetCDF file."""
    import netCDF4 as nc
    with nc.Dataset(path) as ds:
        return set(ds.variables.keys())


def is_netcdf(path) -> bool:
    """Is this parameter file a NetCDF, i.e. can `nc_varnames` probe it?

    Decided by MAGIC BYTES, not by extension: a classic NetCDF begins ``CDF`` and a NetCDF-4
    (HDF5) file begins ``\x89HDF``. Extensions lie, and a model's base parameter file is
    whatever that model uses.

    WHY THIS EXISTS. `route_surfaces` derives a parameter's surface by probing each base file's
    NetCDF variable names -- which silently assumes every adapter model's primary surface IS a
    NetCDF. EcoSIM's is (a pft file); PFLOTRAN's is a TEXT INPUT DECK, so the probe raised
    `OSError: NetCDF: Unknown file format` on the first real PFLOTRAN materialization
    (2026-08-27) and no PFLOTRAN ensemble could be built at all. A model whose base is not a
    NetCDF routes every parameter to `primary` and relies on its own
    `backend.write_parameter_file` to validate addresses -- which is the stronger check anyway,
    since it resolves against the file's actual grammar rather than a flat name set. PFLOTRAN's
    raises KeyError for an unresolvable id, ValueError for an ambiguous or colliding one, and
    refuses a non-writable DBASE_VALUE reference.
    """
    with open(path, "rb") as fh:
        magic = fh.read(4)
    return magic[:3] == b"CDF" or magic == b"\x89HDF"


def declared_surfaces(path) -> dict:
    """Optional ``surface`` column of a param list -> {canonical id: declared surface}.

    Returns {} when the column is absent, so a list that does not declare surfaces is valid and
    unchanged. The column is DOCUMENTATION FOR A HUMAN READER, never an input to routing: a
    reader of the CSV otherwise cannot tell which parameter file a row targets, because routing
    is derived by probing the files. `route_surfaces(..., declared=...)` cross-checks it, so the
    two cannot silently disagree.

    Deliberately holds the SURFACE ROLE ("primary"/"tertiary"), not a filename. The file behind a
    role is set per round by the config ($A2MC_BASE_PARAM_FILE, $A2MC_BASE_PARAM_FILE_3) and
    changes between rounds -- R3 introduced a tertiary surface that R1/R2 had no equivalent of --
    so a filename baked into the list would be stale on the next round while still looking
    authoritative.
    """
    import csv as _csv
    text = Path(path).read_text().splitlines()
    body = [l for l in text if l.strip() and not l.lstrip().startswith("#")]
    if not body:
        return {}
    rdr = _csv.DictReader(body)
    cols = [c.strip() for c in (rdr.fieldnames or [])]
    if "surface" not in cols:
        return {}
    out = {}
    for r in rdr:
        r = {(k.strip() if k else k): v for k, v in r.items()}
        val = (r.get("surface") or "").strip().lower()
        if val:
            out[canonical_pft_id(r["name"], r["pft"])] = val
    return out


def route_surfaces(names, primary_vars: set, tertiary_vars: set, tertiary_given: bool,
                   declared: dict = None) -> dict:
    """canonical id -> "primary" | "tertiary", by PROBING each base file's own variable names
    (never assumed or hand-listed). Refuses loudly (raises ValueError) if a name resolves to
    neither or both surfaces, or would-be-tertiary but no tertiary base was supplied.

    `declared` is an optional {id: surface} map from the list's own ``surface`` column. It is
    CHECKED against the probe, never used in place of it: a disagreement raises. That keeps the
    column honest documentation rather than a second source of truth that can drift from the
    files it describes.
    """
    routing = {}
    problems = []
    for cid in names:
        bare = bare_name(cid)
        in_primary = bare in primary_vars
        in_tertiary = tertiary_given and bare in tertiary_vars
        if in_primary and in_tertiary:
            problems.append(f"{cid}: '{bare}' exists in BOTH the primary and tertiary base files")
        elif in_primary:
            routing[cid] = "primary"
        elif in_tertiary:
            routing[cid] = "tertiary"
        else:
            where = "the primary base file" if not tertiary_given else "either supplied base file"
            problems.append(f"{cid}: '{bare}' not found in {where}")
    if problems:
        raise ValueError(
            "Cannot route " + str(len(problems)) + " parameter(s) to a surface:\n  "
            + "\n  ".join(problems[:20])
            + ("\n  ..." if len(problems) > 20 else "")
        )

    # Cross-check the list's own `surface` column, if it has one. The probe wins; a mismatch is
    # an error rather than a silent correction, because the two disagreeing means either the CSV
    # is stale or the base file is not the one the list was written against -- and both of those
    # are things a run must stop for, not paper over.
    if declared:
        wrong = [f"{cid}: list says '{declared[cid]}', the base files say '{routing[cid]}'"
                 for cid in sorted(set(declared) & set(routing))
                 if declared[cid] != routing[cid]]
        unknown = sorted(set(declared) - set(routing))
        if wrong or unknown:
            msg = "The param list's `surface` column disagrees with the actual base files:\n  "
            msg += "\n  ".join(wrong[:20])
            if unknown:
                msg += ("\n  declared for row(s) not in the sampled set: " + ", ".join(unknown[:10]))
            raise ValueError(msg)
    return routing


def sample_sobol_sequence(problem: dict, n_samples: int, seed: int) -> np.ndarray:
    """A SCRAMBLED SOBOL' SEQUENCE — space-filling, WITHOUT Saltelli cross-sampling.

    NOT the same thing as `--method sobol`, and conflating the two is the point of this
    function. "Sobol sampling" names two different designs:

      * the Sobol' SEQUENCE  — a low-discrepancy quasi-random sequence, which is what this is;
      * the SALTELLI DESIGN  — built FROM that sequence, then cross-sampled into A, B and 2P
        AB_i matrices where each AB_i differs from A in EXACTLY ONE column. That is what
        SALib's `sobol.sample` emits and what `--method sobol` gives you.

    The Saltelli construction exists so S_i and S_Ti are estimable. It is a poor TRAINING set
    for a surrogate, and misleadingly so: of N*(2P+2) points only 2N are independent (A and B),
    the other 2NP being one-coordinate perturbations of those. Every held-out AB_i point
    therefore has a training neighbour one coordinate away, so cross-validation scores
    OPTIMISTICALLY while interior coverage stays thin. An error estimate that is wrong in the
    reassuring direction is worse than none.

    Measured (scipy `qmc.discrepancy`, lower is better) — and note it is DIMENSION-DEPENDENT, so
    quote the row that matches your round rather than the headline:

        d=4,  n=256    sequence 1.13e-04   LHS 1.02e-03    9.0x better
        d=16, n=4096   sequence 2.21e-03   LHS 5.55e-03    2.5x better

    **The 9x figure is a 4-dimensional result and flatters a real round.** At PFLOTRAN miniLEO R1's
    actual 16 dimensions the advantage is 2.5x — still a genuine improvement, and still the right
    choice here, but not the order of magnitude the low-dimensional number suggests. The gap
    narrows with dimension because low-discrepancy constructions lose ground to the curse of
    dimensionality like everything else. Quoting the 4-D number for a 16-D round would be the
    derived-fact-detached-from-its-source failure ([[feedback_bind_derived_facts_to_their_source]]).

    Two properties that matter beyond the discrepancy number:
      * EXTENSIBLE — adding points in powers of two preserves the low-discrepancy property, so a
        training set can grow later without discarding what exists. Classic LHS cannot: adding
        points breaks its stratification.
      * SCRAMBLE SEED IS THE INDEPENDENCE KNOB — a validation set must be drawn with a DIFFERENT
        seed, or it lands on the same underlying lattice as the training set and stops being an
        independent test.

    N should be a power of two; scipy warns otherwise and the balance properties degrade.
    """
    from scipy.stats import qmc                                  # lazy import

    d = problem["num_vars"]
    if n_samples & (n_samples - 1) != 0:
        print(f"  WARNING: n_samples={n_samples} is not a power of 2; the Sobol' sequence's "
              f"balance properties degrade. Prefer 1024 / 2048 / 4096.")
    engine = qmc.Sobol(d=d, scramble=True, seed=seed)
    unit = engine.random(n_samples)
    lo = np.array([b[0] for b in problem["bounds"]], dtype=float)
    hi = np.array([b[1] for b in problem["bounds"]], dtype=float)
    return qmc.scale(unit, lo, hi)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--method", default=os.environ.get("A2MC_SAMPLING_SCHEME", "morris"),
                    choices=["morris", "sobol", "sobol_seq", "lhs"],
                    help="sobol = SALTELLI cross-sampled design, for variance decomposition. "
                         "sobol_seq = the scrambled Sobol' SEQUENCE, space-filling, for "
                         "SURROGATE TRAINING. They are different designs; see sample_sobol_sequence.")
    ap.add_argument("--param-list-file", default=os.environ.get("A2MC_PARAM_LIST_FILE"))
    ap.add_argument("--output-matrix", default=os.environ.get("A2MC_ENSEMBLE_MATRIX_FILE"))
    ap.add_argument("--output-problem", default=os.environ.get("A2MC_SALIB_PROBLEM_FILE"))
    ap.add_argument("--trajectories", type=int, default=int(os.environ.get("A2MC_N_TRAJECTORIES", 30)))
    ap.add_argument("--num-levels", type=int, default=8)
    # ENV-DEFAULTED so the config, not a remembered command line, defines the design.
    # A2MC_N_SAMPLES is the CANONICAL name -- both machine configs set it and
    # a2mc_noncime_config.sh says so in as many words. A2MC_SOBOL_N_SAMPLES is a legacy
    # spelling `check_adapter_calibration_rounds.py` still accepts, read second so an old
    # config keeps working. Do NOT add a third: on 2026-08-27 a fourth spelling
    # (A2MC_N_SOBOL_SAMPLES) was introduced here and the round-record checker went on
    # reading N=1000 from the canonical one while the config said 256, so the two disagreed
    # about the size of the round ([[feedback_bind_derived_facts_to_their_source]]). The
    # pre-commit "two names for one quantity" hook flagged it at birth and was waved off.
    ap.add_argument("--n-samples", type=int,
                    default=int(os.environ.get("A2MC_N_SAMPLES")
                                or os.environ.get("A2MC_SOBOL_N_SAMPLES") or 1024))
    ap.add_argument("--seed", type=int, default=123)
    # SECOND ORDER IS A CONFIG DECISION, NOT A FLAG YOU REMEMBER TO PASS. It doubles-and-then-some
    # the case count -- N*(2P+2) against N*(P+2) -- and decides whether the round can compute the
    # pairwise S_ij at all. Left CLI-only it is a buried choice: the config would describe a design
    # the command line silently overrode, and a reader of the round record could not tell which was
    # run. Caught 2026-08-27 by the PI, who asked why the config named no such variable after the
    # case count changed by a factor of two ([[feedback_no_buried_choices_in_a_menu]]).
    # A2MC_SOBOL_SECOND_ORDER=true|false; the flag still wins when passed explicitly.
    _so_env = os.environ.get("A2MC_SOBOL_SECOND_ORDER", "true").strip().lower()
    ap.add_argument("--no-second-order", action="store_true",
                    default=_so_env in ("0", "false", "no", "off"),
                    help="skip S_ij (N*(P+2) instead of N*(2P+2)). Defaults from "
                         "A2MC_SOBOL_SECOND_ORDER (currently: "
                         f"{'second order ON' if _so_env not in ('0','false','no','off') else 'OFF'})")
    args = ap.parse_args()

    for req, val in [("--param-list-file", args.param_list_file),
                     ("--output-matrix", args.output_matrix),
                     ("--output-problem", args.output_problem)]:
        if not val:
            print(f"ERROR: {req} is unset (source the machine+site config or pass it).", file=sys.stderr)
            return 1

    print(f"Reading adapter parameter list: {args.param_list_file}")
    names, lower, upper = parse_pft_param_list(args.param_list_file)
    problem = {"num_vars": len(names), "names": names,
               "bounds": [[l, u] for l, u in zip(lower, upper)]}

    if args.method == "morris":
        X = sample_morris(problem, args.trajectories, args.num_levels, args.seed)
        method_args = {"trajectories": args.trajectories, "num_levels": args.num_levels, "seed": args.seed}
    elif args.method == "sobol":
        X = sample_sobol(problem, args.n_samples, args.seed, not args.no_second_order)
        method_args = {"n_samples": args.n_samples, "calc_second_order": not args.no_second_order, "seed": args.seed}
    elif args.method == "sobol_seq":
        X = sample_sobol_sequence(problem, args.n_samples, args.seed)
        method_args = {"n_samples": args.n_samples, "seed": args.seed,
                       "construction": "scrambled Sobol' sequence (NO Saltelli cross-sampling)"}
    else:  # lhs
        X = sample_lhs(problem, args.n_samples, args.seed)
        method_args = {"n_samples": args.n_samples, "seed": args.seed}

    write_matrix(X, Path(args.output_matrix))
    write_problem_text(Path(args.output_problem), args.method, method_args, names, lower, upper)
    print(f"  -> generated {X.shape[0]} cases x {X.shape[1]} parameters")
    print(f"  matrix:  {args.output_matrix}")
    print(f"  problem: {args.output_problem}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
