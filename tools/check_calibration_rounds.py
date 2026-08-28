#!/usr/bin/env python3
"""Validate an existing calibration_rounds.yaml round against the LIVE A2MC config.

`calibration_rounds.yaml` duplicates values that also live in a2mc_config.sh + the
site config (param count, ensemble size, artifact paths, targets file, protocol,
milestone). This checker cross-checks the two so a hand-edited YAML can't silently
drift from the config the run actually uses. Also confirms the referenced files
exist. Exit 0 = all pass; exit 1 = at least one mismatch.

Usage (source the site config first -- it auto-loads the machine config, v2.306):
    source use_cases/<site>/config/<site>_config.sh
    python tools/check_calibration_rounds.py --round 1

Pairs with tools/generate_calibration_rounds.py. Author: Jing Tao with Claude.
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path


# The ELM family, for checks that encode CIME concepts (spin-up phases, nutrient supplementation).
# `fates` is A2MC's built-in default model key and runs *under* ELM; there is deliberately no
# `models/fates/` adapter package. `elm` / `elm-fates` are accepted so a future bare-ELM
# registration does not silently lose these checks.
ELM_FAMILY_MODELS = frozenset({"fates", "elm", "elm-fates"})

def _env(name: str, default: str = "") -> str:
    return os.environ.get(name, default) or default


def _root() -> Path:
    ucd = _env("A2MC_USE_CASE_DIR")
    if not ucd:
        sys.exit("ERROR: A2MC_USE_CASE_DIR unset — source a2mc_config.sh + the site config first.")
    return Path(ucd).resolve().parent.parent


def _abs(path: str, root: Path) -> str:
    """Resolve a yaml path (repo-relative or ${VAR}-templated) to an absolute path."""
    if not path:
        return ""
    p = os.path.expandvars(path)
    pp = Path(p)
    return str(pp if pp.is_absolute() else (root / pp))


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--round", type=int, default=None,
                    help="round to check (default: $A2MC_CALIBRATION_ROUND or 1)")
    ap.add_argument("--yaml", default=None, help="override calibration_rounds.yaml path")
    args = ap.parse_args()

    import yaml
    root = _root()
    yaml_path = Path(args.yaml) if args.yaml else (
        Path(_env("A2MC_USE_CASE_DIR")) / "config" / "calibration_rounds.yaml")
    if not yaml_path.exists():
        sys.exit(f"FAIL: calibration_rounds.yaml not found at {yaml_path}")

    round_num = args.round if args.round is not None else int(_env("A2MC_CALIBRATION_ROUND", "1"))
    with open(yaml_path) as f:
        doc = yaml.safe_load(f) or {}
    rounds = doc.get("rounds", {}) or {}
    if round_num not in rounds:
        sys.exit(f"FAIL: round {round_num} not in {yaml_path.name}. Have: {sorted(rounds)}")
    rnd = rounds[round_num]
    paths = rnd.get("paths", {}) or {}

    checks: list[tuple[bool, str, str]] = []  # (ok, label, detail)

    skipped: list[str] = []

    def chk(ok: bool, label: str, detail: str = ""):
        checks.append((bool(ok), label, detail))

    # --- derivable scalar fields ---
    n_params = int(_env("A2MC_N_PARAMS", "0"))
    chk(rnd.get("parameters") == n_params, "parameters == A2MC_N_PARAMS",
        f"yaml={rnd.get('parameters')} config={n_params}")

    traj = int(_env("A2MC_N_TRAJECTORIES", "30"))
    total = _env("A2MC_TOTAL_ENSEMBLE")
    expected_ens = int(total) if total.isdigit() else traj * (n_params + 1)
    chk(rnd.get("ensembles") == expected_ens, "ensembles == trajectories x (params+1)",
        f"yaml={rnd.get('ensembles')} config={expected_ens} (traj={traj})")

    chk(rnd.get("sampling_scheme") == _env("A2MC_SAMPLING_SCHEME"),
        "sampling_scheme == A2MC_SAMPLING_SCHEME",
        f"yaml={rnd.get('sampling_scheme')} config={_env('A2MC_SAMPLING_SCHEME')}")

    chk(paths.get("ensemble_name") == _env("A2MC_ENSEMBLE_NAME"),
        "ensemble_name == A2MC_ENSEMBLE_NAME",
        f"yaml={paths.get('ensemble_name')} config={_env('A2MC_ENSEMBLE_NAME')}")

    chk(paths.get("case_name_pattern") == _env("A2MC_CASE_NAME_PATTERN"),
        "case_name_pattern == A2MC_CASE_NAME_PATTERN",
        f"yaml={paths.get('case_name_pattern')} config={_env('A2MC_CASE_NAME_PATTERN')}")

    # --- path fields: compare by basename + confirm existence ---
    def path_check(yaml_key: str, env_var: str, must_exist: bool):
        yv = _abs(paths.get(yaml_key, ""), root)
        cv = _env(env_var)
        base_ok = bool(yv) and bool(cv) and Path(yv).name == Path(cv).name
        chk(base_ok, f"{yaml_key} basename == {env_var}",
            f"yaml={Path(yv).name if yv else '<none>'} config={Path(cv).name if cv else '<none>'}")
        if must_exist:
            chk(bool(yv) and Path(yv).exists(), f"{yaml_key} file exists", yv or "<none>")

    path_check("param_list", "A2MC_PARAM_LIST_FILE", must_exist=True)
    path_check("salib_problem", "A2MC_SALIB_PROBLEM_FILE", must_exist=False)  # generated by Phase 0

    # validation targets (field is top-level, not under paths)
    vt_yaml = _abs(rnd.get("validation_targets_file", ""), root)
    vt_env = _env("A2MC_VALIDATION_TARGETS")
    chk(bool(vt_yaml) and bool(vt_env) and Path(vt_yaml).name == Path(vt_env).name,
        "validation_targets_file basename == A2MC_VALIDATION_TARGETS",
        f"yaml={Path(vt_yaml).name if vt_yaml else '<none>'} config={Path(vt_env).name if vt_env else '<none>'}")
    chk(bool(vt_yaml) and Path(vt_yaml).exists(), "validation targets file exists", vt_yaml or "<none>")

    # --- output dirs: compare expanded absolute ---
    for yk, ev in (("ensemble_output", "A2MC_ENSEMBLE_OUTPUT"), ("extracted_data", "A2MC_EXTRACTED_DATA")):
        cv = _env(ev)
        if cv:
            chk(_abs(paths.get(yk, ""), root) == os.path.expandvars(cv), f"{yk} == {ev}",
                f"yaml={_abs(paths.get(yk, ''), root)} config={os.path.expandvars(cv)}")

    # --- protocol ---
    #
    # `suplphos` / `suplnitro` are ELM nutrient-supplementation settings, keyed by the CIME spin-up
    # PHASES (ADSP / RGSP / TRANS). They are meaningful only for the ELM family; a standalone-binary
    # adapter model has no CIME phases at all, and the EcoSIM round-record template says so in as
    # many words ("No FATES-style suplphos/suplnitro/elm_options here -- a standalone binary has no
    # CIME phases"). The adapter generator `scripts/generate_adapter_calibration_rounds.py`
    # correspondingly never emits these keys.
    #
    # Checked unconditionally, this compared `yaml=None` against an env default of the STRING
    # "NONE" and produced SIX failures for EVERY adapter case, by construction -- EcoSIM_Lusignan's
    # last readiness-gate blocker was 6 of these plus 8 real ones. Same defect class as
    # `check_setup_ready.py` before 2026-08-18: a FATES-shaped rule applied to a model with a
    # different grammar. See memory/dev_logs_adapterkit/20260818e.
    proto = rnd.get("protocol", {}) or {}
    model = (os.environ.get("A2MC_MODEL", "") or "fates").strip().lower()
    if model in ELM_FAMILY_MODELS:
        for nutrient, key in (("SUPLPHOS", "suplphos"), ("SUPLNITRO", "suplnitro")):
            for phase in ("ADSP", "RGSP", "TRANS"):
                yv = (proto.get(key, {}) or {}).get(phase)
                cv = _env(f"A2MC_{phase}_{nutrient}", "NONE")
                chk(yv == cv, f"protocol.{key}.{phase} == A2MC_{phase}_{nutrient}",
                    f"yaml={yv} config={cv}")
    else:
        # Report the SKIP rather than emitting nothing. A check that silently disappears is
        # indistinguishable from one that passed, which is how a gap survives; `check_setup_ready.py`
        # makes the same distinction with its `N/A` rows.
        skipped.append(f"protocol.suplphos / protocol.suplnitro (6 checks) — ELM-family only; "
                       f"A2MC_MODEL={model} has no CIME spin-up phases")

    # --- report ---
    n_fail = sum(1 for ok, _, _ in checks if not ok)
    print(f"calibration_rounds.yaml round {round_num}  vs  live config ({yaml_path})\n")
    for ok, label, detail in checks:
        mark = "✓" if ok else "✗"
        line = f"  [{mark}] {label}"
        if not ok and detail:
            line += f"   <- {detail}"
        print(line)
    for s in skipped:
        print(f"  [–] {s}")
    print()
    if n_fail:
        print(f"✗ {n_fail} mismatch(es) — the YAML disagrees with the live config. Fix the YAML "
              f"(or regenerate: tools/generate_calibration_rounds.py --round {round_num} --write).")
        sys.exit(1)
    print(f"✓ round {round_num} is consistent with the live config.")


if __name__ == "__main__":
    main()
