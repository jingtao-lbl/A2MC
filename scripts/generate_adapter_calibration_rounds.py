#!/usr/bin/env python3
"""Generate a calibration_rounds.yaml round entry for an ADAPTER (non-FATES) model.

The adapter analog of tools/generate_calibration_rounds.py, which is FATES-config-coupled (it emits an
ADSP/RGSP/TRANS + SUPLPHOS/SUPLNITRO protocol block and a `fates_source` block via detect_model_version,
and reads the param/trajectory count from generic env defaults). This version is MODEL-AGNOSTIC: it
DERIVES the round block from the two config files (a2mc_noncime_config.sh + the site config, sourced into
the env) + the param-list CSV + targets.yaml + git in the model checkout. It emits:

  - parameters (DERIVED from the CSV data rows, cross-checked vs A2MC_N_PARAMS), trajectories, ensembles
    (= trajectories x (parameters + 1)), sampling scheme;
  - paths (ensemble output, param list, salib, matrix, case pattern) from the env;
  - the scored targets from targets.yaml (name / variable / obs / units / reduce);
  - a MODEL-DISPATCHED protocol block (EcoSIM = single_continuous, not FATES ADSP/RGSP/TRANS);
  - a `<model>_source` block (version/commit/branch/fork/binary/param-format) from git in A2MC_MODEL_PATH;
  - status from the offline workflow state (planned / in_progress / redesign / complete); rationale/changes/outcome TODO.

Usage (source the site config first -- since v2.306 it auto-loads a2mc_noncime_config.sh, and the
ordering still matters for the same reason: the site config sets the REAL
A2MC_N_PARAMS/A2MC_N_TRAJECTORIES that override the noncime generic defaults):
    source use_cases/<site>/config/<site>_config.sh
    python scripts/generate_adapter_calibration_rounds.py --round 1            # print to stdout
    python scripts/generate_adapter_calibration_rounds.py --round 1 --write    # merge into the yaml

Pairs with scripts/check_adapter_calibration_rounds.py (validates the yaml vs the config).
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

import yaml


def _env(name: str, required: bool = True, default: str | None = None) -> str:
    v = os.environ.get(name, default)
    if required and not v:
        sys.exit(f"ERROR: required env var {name} is unset (source a2mc_noncime_config.sh + the site config first).")
    return v or ""


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _rel(path: str, root: Path) -> str:
    try:
        return str(Path(path).resolve().relative_to(root))
    except Exception:
        return path


def _param_count_from_csv(csv: str) -> int:
    """Authoritative param count = non-comment, non-header, non-blank data rows (never the env default)."""
    n = 0
    with open(csv) as f:
        for line in f:
            s = line.strip()
            if not s or s.startswith("#") or s.startswith("name,"):
                continue
            n += 1
    return n


def _derive_targets(targets_file: str) -> list:
    """Scored targets from targets.yaml: name + variable + obs + units + reduce (best-effort)."""
    try:
        doc = yaml.safe_load(open(targets_file)) or {}
    except Exception:
        return ["TODO: list this round's targets (see validation_targets_file)"]
    tgts = doc.get("targets") or {k: v for k, v in doc.items() if isinstance(v, dict)}
    out = []
    for name, spec in tgts.items():
        if not isinstance(spec, dict):
            continue
        out.append({k: spec[k] for k in ("variable", "obs", "observed", "units", "reduce") if k in spec}
                   | {"name": name})
    return out or ["TODO: list this round's targets (see validation_targets_file)"]


def _git(checkout: str, *args: str) -> str:
    try:
        return subprocess.check_output(["git", "-C", checkout, *args], text=True,
                                       stderr=subprocess.DEVNULL).strip()
    except Exception:
        return "TODO"


def _model_blocks(model: str, root: Path) -> tuple:
    """(protocol, source_key, source) -- the model-dispatched, non-FATES bits."""
    checkout = _env("A2MC_MODEL_PATH")
    commit = _git(checkout, "rev-parse", "--short", "HEAD")
    branch = _git(checkout, "branch", "--show-current")
    fork = _git(checkout, "remote", "get-url", "fork")
    y0 = os.environ.get("A2MC_VALIDATION_START_YEAR", "TODO")
    y1 = os.environ.get("A2MC_VALIDATION_END_YEAR", "TODO")
    if model == "ecosim":
        protocol = {
            "run_type": "single_continuous",   # NOT FATES ADSP/RGSP/TRANS
            "sim_years": f"{y0}-{y1}",
            "parallelism": "SLURM job array (--array); each case a serial srun -n 1 (OMP=1, mpi=0)",
        }
        source = {
            "version": os.environ.get("A2MC_ECOSIM_VERSION", branch or commit),
            "checkout": checkout,
            "branch": branch,
            "commit": commit,
            "fork": fork,
            "binary": _env("A2MC_ECOSIM_BINARY", required=False, default="TODO"),
            "param_format": "per-PFT NetCDF pft input",
        }
        return protocol, "ecosim_source", source
    # generic non-FATES fallback
    protocol = {"run_type": os.environ.get("A2MC_RUN_TYPE", "single_continuous"),
                "sim_years": f"{y0}-{y1}"}
    source = {"version": branch or commit, "checkout": checkout, "branch": branch,
              "commit": commit, "fork": fork}
    return protocol, f"{model}_source", source


def _status_from_state(round_num: int) -> str:
    """Round status from the offline resume brain:
      planned    -- pre-Phase-0 (not started)
      in_progress-- running (mid-loop, not yet terminal)
      redesign   -- middle loop exhausted WITHOUT convergence, at/through the Phase 6->0
                    redesign gate (experiment_count >= max_experiments, or an explicit
                    redesign_6to0 decision). The round is closed; a wider round follows.
      complete   -- converged (Phase 7)
    """
    ucd = os.environ.get("A2MC_USE_CASE_DIR", "")
    sf = Path(ucd) / "memory" / f"workflow_state_offline_r{round_num:02d}.json"
    try:
        st = json.load(open(sf))
    except Exception:
        return "planned"
    if st.get("converged"):
        return "complete"
    dec = (st.get("phase6_decision") or {}).get("decision")
    if dec == "redesign_6to0":                      # explicit Phase 6 -> Phase 0 decision
        return "redesign"
    phase = st.get("current_phase", "design")
    # middle loop exhausted without convergence => at the redesign gate (the documented
    # default when experiment cycles reach max; CLAUDE.md 7-phase workflow). Do NOT presume
    # redesign if the human explicitly chose stop_model_dev.
    ec = st.get("experiment_count", 0)
    mx = (st.get("phase6_decision") or {}).get("max_experiments", 10)
    if phase == "refinement" and isinstance(ec, int) and ec >= mx and dec != "stop_model_dev":
        return "redesign"
    return "in_progress" if phase not in ("design", "", None) else "planned"


def build_round(round_num: int) -> dict:
    root = _repo_root()
    model = _env("A2MC_MODEL")
    csv = _env("A2MC_PARAM_LIST_FILE")
    n_params = _param_count_from_csv(csv)                       # authoritative: from the CSV
    env_np = int(_env("A2MC_N_PARAMS", required=False, default="0") or 0)
    if env_np and env_np != n_params:
        print(f"# WARN: A2MC_N_PARAMS={env_np} != CSV data-row count {n_params}; using the CSV count.",
              file=sys.stderr)
    scheme = _env("A2MC_SAMPLING_SCHEME", required=False, default="morris")
    traj = int(_env("A2MC_N_TRAJECTORIES", required=False, default="20"))
    # `trajectories` is a MORRIS concept (paths through the space). Emitting it for every
    # scheme wrote a meaningless 20 into R3's sobol block, where a reader could multiply it
    # by (P+1) and get a case count off by 60x from the real 59,392. Scheme-specific fields
    # are now emitted only for their own scheme (PI catch, 2026-08-18).
    #
    # Sobol's size is N(2P+2) with second-order indices, N(P+2) without -- DERIVED here from
    # A2MC_N_SAMPLES (canonical -- the same N the samplers use for sobol AND lhs; the older
    # A2MC_SOBOL_N_SAMPLES is a deprecated alias, still accepted on read for any config not yet
    # migrated, but no config in this repo sets it) rather than a hand-set A2MC_TOTAL_ENSEMBLE, so the
    # registry cannot disagree with what the sampler will actually produce.
    if scheme == "morris":
        ensembles = traj * (n_params + 1)
    elif scheme == "sobol":
        n_s = int(os.environ.get("A2MC_N_SAMPLES", 0)
                   or os.environ.get("A2MC_SOBOL_N_SAMPLES", 0) or 0)
        second = os.environ.get("A2MC_SOBOL_SECOND_ORDER", "1") not in ("0", "false", "False")
        ensembles = n_s * ((2 * n_params + 2) if second else (n_params + 2))
    elif scheme == "sobol_seq":
        # A raw scrambled Sobol' SEQUENCE: one case per point, no cross-sampling. Added
        # 2026-08-27 with the scheme itself -- without it this fell through to the
        # A2MC_TOTAL_ENSEMBLE branch and wrote `ensembles: 0`, which the checker then PASSED
        # because it had no rule for the new scheme either. A zero that validates is worse than
        # a mismatch that fails ([[feedback_a_check_that_cannot_fail]]).
        ensembles = int(os.environ.get("A2MC_N_SAMPLES", 0) or 0)
    else:
        ensembles = int(os.environ.get("A2MC_TOTAL_ENSEMBLE", 0) or 0)
    # $A2MC_VALIDATION_TARGETS first (a round wrapper, e.g. ecosim_biocon_config_r3.sh, may
    # override it to a round-specific targets file -- see resolve_targets_yaml() in
    # tools/targets_loader.py, the same priority order); else the site default.
    targets_file = _env("A2MC_VALIDATION_TARGETS", required=False, default="") or \
        str(Path(_env("A2MC_USE_CASE_DIR")) / "validation" / "targets.yaml")
    protocol, source_key, source = _model_blocks(model, root)
    out_root = _env("A2MC_OUTPUT_ROOT")
    name = _env("A2MC_ENSEMBLE_NAME")
    block = {
        "parameters": n_params,
        "ensembles": ensembles,
        "sampling_scheme": scheme,
        # The FILE, not the directory. This previously composed <use_case>/config, which is
        # identical for every round and so cannot answer the one question a round registry
        # needs it for: which wrapper produced this round. tools/round_paths.py:105 documents
        # the field as a site config PATH and passes it through at :175, so a directory here
        # reached a real consumer expecting a filename. Prefer the round wrapper; fall back to
        # the site config, which is what the FATES-coupled generator reads.
        "config_file": _rel(_env("A2MC_ROUND_CONFIG", required=False, default="")
                            or _env("A2MC_SITE_CONFIG"), root),
        "paths": {
            "output_root": out_root,
            "ensemble_name": name,
            "ensemble_output": f"{out_root}/{name}",
            "case_name_pattern": _env("A2MC_CASE_NAME_PATTERN"),
            "param_list": _rel(csv, root),
            "salib_problem": _rel(_env("A2MC_SALIB_PROBLEM_FILE"), root),
            "ensemble_matrix": _rel(_env("A2MC_ENSEMBLE_MATRIX_FILE", required=False, default=""), root),
            "base_param_file": _env("A2MC_BASE_PARAM_FILE", required=False, default="TODO"),
        },
        "targets": _derive_targets(targets_file),
        "validation_targets_file": _rel(targets_file, root),
        "protocol": protocol,
        source_key: source,
        "rationale": "TODO: why this round is designed as it is.",
        "changes_from_previous": ["First round on this lineage."] if round_num == 1
                                 else ["TODO: what changed vs the previous round."],
        "outcome": None,
        "status": _status_from_state(round_num),
    }
    if scheme == "morris":
        block["trajectories"] = traj
    return block


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--round", type=int, default=int(os.environ.get("A2MC_CALIBRATION_ROUND", "1")))
    ap.add_argument("--write", action="store_true", help="merge into use_cases/<site>/config/calibration_rounds.yaml")
    args = ap.parse_args()
    block = build_round(args.round)
    if not args.write:
        print("# (derived from the two configs + CSV + targets.yaml + git; TODO fields need a human. "
              "Re-run with --write to merge.)")
        print(yaml.safe_dump({"rounds": {args.round: block}}, sort_keys=False))
        return
    yaml_path = Path(_env("A2MC_USE_CASE_DIR")) / "config" / "calibration_rounds.yaml"
    doc = {}
    header = ""
    if yaml_path.exists():
        text = yaml_path.read_text()
        header = "".join(l for l in text.splitlines(keepends=True) if l.lstrip().startswith("#") or not l.strip())
        doc = yaml.safe_load(text) or {}
    doc.setdefault("model", _env("A2MC_MODEL"))
    doc.setdefault("site", os.path.basename(_env("A2MC_USE_CASE_DIR")))
    doc.setdefault("rounds", {})
    # preserve human-filled narrative fields if the round already exists
    prev = doc["rounds"].get(args.round, {}) if isinstance(doc.get("rounds"), dict) else {}
    for k in ("rationale", "changes_from_previous", "outcome", "notes"):
        if prev.get(k) and str(prev.get(k)).strip() and "TODO" not in str(prev.get(k)):
            block[k] = prev[k]
    doc["rounds"][args.round] = block
    yaml_path.write_text((header if header.strip() else "") + yaml.safe_dump(doc, sort_keys=False))
    print(f"wrote round {args.round} -> {yaml_path}  (status={block['status']}, params={block['parameters']}, "
          f"ensembles={block['ensembles']})")


if __name__ == "__main__":
    main()
