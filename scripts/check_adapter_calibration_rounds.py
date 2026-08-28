#!/usr/bin/env python3
"""Validate an ADAPTER (non-FATES) calibration_rounds.yaml round vs the live config + CSV.

The adapter analog of tools/check_calibration_rounds.py (which is FATES-coupled). Cross-checks the yaml
round block against the two sourced config files + the param-list CSV so a hand-edited or stale round
record can't silently drift. Model-agnostic: no FATES protocol / fates_source assumptions.

Checks: parameters == CSV data-row count; trajectories == A2MC_N_TRAJECTORIES; ensembles ==
trajectories x (parameters+1) for morris; sampling_scheme / ensemble_name / case_name_pattern match the
config; param_list / salib / base_param / validation_targets paths exist. Exit 0 = all pass.

Usage:
    source a2mc_noncime_config.sh
    source use_cases/<site>/config/<site>_config.sh
    python scripts/check_adapter_calibration_rounds.py --round 1
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

import yaml


def _env(name: str, default: str = "") -> str:
    return os.environ.get(name, default) or default


def _root() -> Path:
    return Path(__file__).resolve().parents[1]


def _param_count_from_csv(csv: str) -> int:
    n = 0
    for line in open(csv):
        s = line.strip()
        if s and not s.startswith("#") and not s.startswith("name,"):
            n += 1
    return n


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--round", type=int, default=int(_env("A2MC_CALIBRATION_ROUND", "1")))
    args = ap.parse_args()
    root = _root()
    ypath = Path(_env("A2MC_USE_CASE_DIR")) / "config" / "calibration_rounds.yaml"
    if not ypath.exists():
        sys.exit(f"ERROR: {ypath} not found (generate it: scripts/generate_adapter_calibration_rounds.py --round {args.round} --write).")
    doc = yaml.safe_load(ypath.read_text()) or {}
    rnd = (doc.get("rounds") or {}).get(args.round)
    if not rnd:
        sys.exit(f"ERROR: round {args.round} absent from {ypath}.")

    n_params = _param_count_from_csv(_env("A2MC_PARAM_LIST_FILE"))
    traj = int(_env("A2MC_N_TRAJECTORIES", "20"))
    scheme = _env("A2MC_SAMPLING_SCHEME", "morris")
    paths = rnd.get("paths", {})
    checks = []

    def chk(ok, label, detail=""):
        checks.append((bool(ok), label, detail))

    chk(rnd.get("parameters") == n_params, "parameters == CSV count",
        f"yaml={rnd.get('parameters')} csv={n_params}")
    # Scheme-specific fields are checked ONLY for their own scheme, matching the generator.
    # `trajectories` is a Morris concept; demanding it on a sobol round failed a correct registry
    # (2026-08-18). Generator and checker are a PAIR and must move together -- a checker
    # disagreeing with its generator is a bug in one of them, never a third opinion.
    if scheme == "morris":
        chk(rnd.get("trajectories") == traj, "trajectories == A2MC_N_TRAJECTORIES",
            f"yaml={rnd.get('trajectories')} config={traj}")
        chk(rnd.get("ensembles") == traj * (n_params + 1), "ensembles == traj x (params+1)",
            f"yaml={rnd.get('ensembles')} expect={traj * (n_params + 1)}")
    else:
        chk("trajectories" not in rnd, "trajectories absent for a non-morris scheme",
            f"yaml={rnd.get('trajectories')} (a Morris concept; must not appear on {scheme})")
    if scheme == "sobol":
        n_s = int(os.environ.get("A2MC_N_SAMPLES", 0)
                   or os.environ.get("A2MC_SOBOL_N_SAMPLES", 0) or 0)
        second = os.environ.get("A2MC_SOBOL_SECOND_ORDER", "1") not in ("0", "false", "False")
        expect = n_s * ((2 * n_params + 2) if second else (n_params + 2))
        chk(rnd.get("ensembles") == expect, "ensembles == N(2P+2) for second-order sobol",
            f"yaml={rnd.get('ensembles')} expect={expect} (N={n_s}, P={n_params}, second_order={second})")
    if scheme == "sobol_seq":
        # One case per sequence point. Asserted rather than assumed: a scheme with no rule here
        # passes every check by having nothing to fail, which is how `ensembles: 0` slipped
        # through on the day this scheme was added.
        n_s = int(os.environ.get("A2MC_N_SAMPLES", 0) or 0)
        chk(rnd.get("ensembles") == n_s and n_s > 0, "ensembles == N for sobol_seq",
            f"yaml={rnd.get('ensembles')} expect={n_s} (one case per sequence point)")
    chk(rnd.get("sampling_scheme") == scheme, "sampling_scheme", f"yaml={rnd.get('sampling_scheme')} config={scheme}")
    chk(paths.get("ensemble_name") == _env("A2MC_ENSEMBLE_NAME"), "ensemble_name",
        f"yaml={paths.get('ensemble_name')} config={_env('A2MC_ENSEMBLE_NAME')}")
    chk(paths.get("case_name_pattern") == _env("A2MC_CASE_NAME_PATTERN"), "case_name_pattern",
        f"yaml={paths.get('case_name_pattern')} config={_env('A2MC_CASE_NAME_PATTERN')}")
    # path existence (repo-relative or absolute)
    for key, envv in [("param_list", "A2MC_PARAM_LIST_FILE"), ("salib_problem", "A2MC_SALIB_PROBLEM_FILE")]:
        yv = paths.get(key, "")
        p = Path(yv) if os.path.isabs(yv) else root / yv
        chk(p.exists(), f"{key} exists", str(p))
    base = paths.get("base_param_file", "")
    if base and base != "TODO":
        chk(Path(base).exists(), "base_param_file exists", base)
    tf = rnd.get("validation_targets_file", "")
    chk((root / tf).exists() or Path(tf).exists(), "validation_targets_file exists", tf)
    chk(rnd.get("status") in ("planned", "in_progress", "redesign", "complete"), "status is valid",
        f"status={rnd.get('status')}")

    ok_all = all(ok for ok, _, _ in checks)
    for ok, label, detail in checks:
        print(f"  [{'ok' if ok else 'FAIL'}] {label}" + (f"  ({detail})" if not ok else ""))
    if ok_all:
        detail = f"{traj} traj" if scheme == "morris" else \
                 (f"N={os.environ.get('A2MC_N_SAMPLES') or os.environ.get('A2MC_SOBOL_N_SAMPLES', '?')}" if scheme == "sobol" else scheme)
        print(f"OK: round {args.round} consistent with config + CSV ({n_params} params, {detail}).")
        sys.exit(0)
    print(f"FAIL: {sum(1 for ok, _, _ in checks if not ok)} mismatch(es).")
    sys.exit(1)


if __name__ == "__main__":
    main()
