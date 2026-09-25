"""The dry propose step on a completed ensemble -- docs/42 stage S3.

WHAT THIS DOES. It loads a completed ensemble (the design matrix, the extracted Y matrix and the
parameter list the design was sampled from), labels every row from the Y matrix's `status`
column, fits the search surrogate (`S1Surrogate` with a GP per target on the viable rows, an RF
viability classifier on every labelled row, `calibration_fraction=0`) and asks
`acquisition.propose_batch` for q parameter sets. It writes them in the matrix format
`scripts/materialize_adapter_ensemble.py` reads, with a per-pick table, a metadata record and the
exact invocation, and stops. Nothing is materialised or submitted. `--dry-run` is required:
running the proposals, refitting and deciding when to stop is the closed loop of stage S4.

HOW A ROW IS LABELLED. Case `i` is design row `X[i - 1]`; the baseline case has no design row and
is dropped (the convention of `bo_replay.build_pool`).

    status                                 label
    COMPLETED, every target value finite   viable when every --viable-if rule holds, else nonviable
    COMPLETED, a target value non-finite   completed_nonfinite: dropped from the fit, counted
    FAILED                                 failed: non-viable
    RUNNING                                failed when the case is in --failed-cases or
                                           --ensemble-drained is given; otherwise REFUSING
    PENDING, UNKNOWN, SCORE_ERROR:*        excluded: counted, never labelled failed
    no status column, or any other status  REFUSING

`--failed-cases` only ever relabels a RUNNING row. A case it lists that is COMPLETED stays an
observation, since a relaunched case can complete after the failure census was taken.

WHAT THE FIT SEES. The classifier trains on the viable, nonviable and failed rows; the GPs on
the viable rows, with `V` as the subsample priority so the best rows are never dropped. Every row
with a design row, whatever its label, is passed to `propose_batch` as an observed position, so
no case that exists in the ensemble is proposed again. The one exception is a cold start without
a surrogate whose labelled rows hold both classes: `propose_batch` then fits its own classifier
on the rows it is given, so the unlabelled rows are withheld and a pick on one is dropped after.

EXIT CODES

    0  a full batch of q proposals, with complete provenance
    1  REFUSING: an input or a check failed, and the message says which
    2  command-line usage error (argparse)
    3  cold_start: too few viable rows for the acquisition, so the picks are maximin
    4  degenerate: the acquisition carried no ranking information at the first pick
    5  no_viable_probability: P(viable) is zero at every candidate
    6  all_out_of_hull: every candidate lies outside the surrogate's hull gate; nothing proposed
    7  shortfall: fewer than q proposals
    8  provenance_incomplete: --round-config or --training-binary is missing, and 3-7 do not apply

The first code in 3-7 that applies is returned.

OUTPUTS, in `--out` (refused when it exists and is not empty, unless `--force`):

    proposal_matrix.txt   native values in parameter-list column order, `np.savetxt` default
                          format; written only when at least one proposal exists
    proposal_table.csv    one row per pick: parameter values, alpha, ei, p_viable, hull distance,
                          the V* used, pick source, candidate set, predicted targets, V of the
                          posterior mean, binding target and per-target sd ratios
    proposal_meta.json    inputs with SHA-256, labels, fit settings, diagnostics, provenance and
                          a materialisation recipe; library versions and runtimes under "run"
    NOTES.md              the exact invocation

Author: Jing Tao with Claude
"""
from __future__ import annotations

import argparse
import csv
import dataclasses
import hashlib
import json
import math
import os
import pathlib
import platform
import re
import shlex
import sys
import time
from typing import Any, Dict, List, Optional, Sequence, Tuple

import numpy as np

REPO = pathlib.Path(__file__).resolve().parents[2]   # tools/bayesian_optimization/ -> repo root
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from tools.bayesian_optimization.acquisition import (  # noqa: E402
    Proposal, min_distance, native_to_unit, propose_batch, score_candidates, sobol_candidates)
from tools.bayesian_optimization.bo_replay import parse_viable_if  # noqa: E402
from tools.bayesian_optimization.objective import (  # noqa: E402
    Target, load_targets, violation_matrix)


#: Statuses that exclude a row from every label: it produced no result and is not a failure.
EXCLUDED_STATUSES = ("PENDING", "UNKNOWN")
SCORE_ERROR_PREFIX = "SCORE_ERROR:"

#: Row labels, in the order `proposal_meta.json` lists them.
LABELS = ("viable", "nonviable", "failed", "completed_nonfinite", "excluded", "baseline")

#: Labels whose rows train the surrogate.
FIT_LABELS = ("viable", "nonviable", "failed")

#: Exit codes for the proposal statuses that are not a full batch.
STATUS_EXIT = {"cold_start": 3, "degenerate": 4, "no_viable_probability": 5,
               "all_out_of_hull": 6}
EXIT_SHORTFALL = 7
EXIT_PROVENANCE_INCOMPLETE = 8
OUTCOMES = {0: "full_batch", 3: "cold_start", 4: "degenerate", 5: "no_viable_probability",
            6: "all_out_of_hull", 7: "shortfall", 8: "provenance_incomplete"}

#: Unit-cube L-inf distance within which a candidate counts as an observed row.
MIN_SEPARATION = 1e-6

#: A design row may sit this fraction of a parameter's range outside its bounds.
BOUND_TOL = 1e-9

#: The SALib problem text writes bounds with 6 significant digits.
SALIB_REL_TOL = 1e-5

#: Random q-point draws from the Sobol' scan behind each plausibility figure's chance baseline.
CHANCE_DRAWS = 200

#: A unit-cube coordinate this close to 0 or 1 counts as on a bound.
NEAR_BOUND = 0.01

#: How a P(viable) from the RF classifier is to be read.
P_VIABLE_IS = ("an uncalibrated random-forest vote fraction, used to rank candidates; it is not a "
               "calibrated probability")

MATRIX_FILE = "proposal_matrix.txt"
TABLE_FILE = "proposal_table.csv"
META_FILE = "proposal_meta.json"
NOTES_FILE = "NOTES.md"

_PER_PICK = ("unit", "native", "alpha", "ei", "p_viable", "hull_distance", "in_hull",
             "predicted", "V_mean", "binding", "pick_source", "candidate_set", "V_star_used",
             "sd_ratio")


def _refuse(msg: str) -> SystemExit:
    return SystemExit(f"REFUSING: {msg}")


# =============================================================================
# Inputs
# =============================================================================

def sha256_file(path) -> str:
    h = hashlib.sha256()
    with pathlib.Path(path).open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def read_param_list(path) -> Tuple[List[str], np.ndarray, np.ndarray]:
    """(names, lower, upper) through the parser that generated the design matrix."""
    from scripts.create_adapter_parameter_sample import parse_pft_param_list

    try:
        names, lower, upper = parse_pft_param_list(path)
    except (OSError, ValueError) as exc:
        raise _refuse(f"cannot read the parameter list {path}: {exc}")
    return list(names), np.asarray(lower, dtype=float), np.asarray(upper, dtype=float)


def check_salib_problem(path, names: Sequence[str], lower, upper) -> None:
    """The round's SALib problem file must declare the parameter list's names and bounds."""
    from phases.phase1_exploration.morris_sensitivity_analysis import (
        load_salib_problem_from_file)

    prob = load_salib_problem_from_file(str(path))
    if list(prob["names"]) != list(names):
        raise _refuse(f"--salib-problem {path} declares parameters {list(prob['names'])}, the "
                      f"parameter list declares {list(names)}; the design and the list must "
                      f"describe the same columns in the same order.")
    for name, (lo_p, hi_p), lo, hi in zip(names, prob["bounds"], lower, upper):
        for side, a, b in (("lower", lo_p, lo), ("upper", hi_p, hi)):
            if not math.isclose(float(a), float(b), rel_tol=SALIB_REL_TOL, abs_tol=1e-12):
                raise _refuse(f"--salib-problem {path}: {name} {side} bound {a} differs from the "
                              f"parameter list's {b}; the design was sampled over a different "
                              f"box than the one searched here.")


def read_x_matrix(path, names: Sequence[str], lower, upper) -> np.ndarray:
    """The design matrix, checked against the parameter list's column count and bounds."""
    try:
        X = np.loadtxt(path, ndmin=2)
    except (OSError, ValueError) as exc:
        raise _refuse(f"cannot read the design matrix {path}: {exc}")
    if X.size == 0:
        raise _refuse(f"{path} holds no design rows")
    if X.shape[1] != len(names):
        raise _refuse(f"{path} has {X.shape[1]} columns but the parameter list has {len(names)} "
                      f"parameters; column j of the matrix is parameter j of the list.")
    if not np.all(np.isfinite(X)):
        raise _refuse(f"{path} has non-finite entries")
    tol = BOUND_TOL * (np.asarray(upper) - np.asarray(lower))
    out = np.flatnonzero(np.any((X < lower - tol) | (X > upper + tol), axis=1))
    if len(out):
        raise _refuse(f"{len(out)} row(s) of {path} lie outside the parameter-list bounds (first "
                      f"design rows {(out[:5] + 1).tolist()}, 1-based); the list's bounds are not "
                      f"the box this design was sampled in.")
    return X


def read_y_matrix(path, target_names: Sequence[str]
                  ) -> Tuple[np.ndarray, List[str], np.ndarray]:
    """(cases, status, Y) with Y's columns in `target_names` order; non-numbers read as NaN."""
    p = pathlib.Path(path)
    if not p.is_file():
        raise _refuse(f"the Y matrix {path} does not exist")
    with p.open(newline="") as fh:
        reader = csv.DictReader(fh)
        fields = [f.strip() for f in (reader.fieldnames or [])]
        rows = [{(k or "").strip(): v for k, v in r.items()} for r in reader]
    if "case" not in fields:
        raise _refuse(f"{path} has no `case` column (columns: {fields})")
    if "status" not in fields:
        raise _refuse(f"{path} has no `status` column (columns: {fields}). Rows are labelled "
                      f"from their status: without it a crash cannot be told from a run that "
                      f"never started or is still going.")
    missing = [n for n in target_names if n not in fields]
    if missing:
        raise _refuse(f"{path} has no column for target(s) {missing} (columns: {fields})")
    if not rows:
        raise _refuse(f"{path} has no rows")

    def _num(x):
        try:
            return float(x)
        except (TypeError, ValueError):
            return float("nan")

    try:
        cases = np.array([int(r["case"]) for r in rows], dtype=int)
    except (TypeError, ValueError):
        raise _refuse(f"{path}: every `case` must be an integer")
    uniq, counts = np.unique(cases, return_counts=True)
    if np.any(counts > 1):
        raise _refuse(f"{path} lists case(s) {uniq[counts > 1][:5].tolist()} more than once")
    status = [(r.get("status") or "").strip() for r in rows]
    Y = np.array([[_num(r.get(n)) for n in target_names] for r in rows], dtype=float)
    return cases, status, Y


def read_failed_cases(path) -> set:
    """Case numbers from a CSV with a `case` column."""
    p = pathlib.Path(path)
    if not p.is_file():
        raise _refuse(f"--failed-cases {path} does not exist")
    with p.open(newline="") as fh:
        reader = csv.DictReader(fh)
        fields = [f.strip() for f in (reader.fieldnames or [])]
        if "case" not in fields:
            raise _refuse(f"--failed-cases {path} has no `case` column (columns: {fields})")
        try:
            return {int(r["case"]) for r in ({(k or "").strip(): v for k, v in row.items()}
                                             for row in reader)}
        except (TypeError, ValueError):
            raise _refuse(f"--failed-cases {path}: every `case` must be an integer")


def parse_rules(exprs: Optional[Sequence[str]], finite_only: bool,
                target_names: Sequence[str]) -> List[Tuple[str, str, float]]:
    """Parse every --viable-if rule, then check every rule's target name, before any is applied.

    One of `--viable-if` and `--viable-if-finite-only` is required. Without a rule every finite
    row counts as viable, so a dead run with a finite output would train the GPs.
    """
    exprs = list(exprs or [])
    if exprs and finite_only:
        raise _refuse("give --viable-if rules or --viable-if-finite-only, not both")
    if not exprs and not finite_only:
        raise _refuse("no viability rule. Give at least one --viable-if (for example "
                      "'NPP>1'), or --viable-if-finite-only to count every COMPLETED row with "
                      "finite targets as viable.")
    rules = []
    for e in exprs:
        try:
            r = parse_viable_if(e)
        except ValueError:
            raise _refuse(f"--viable-if {e!r}: the threshold is not a number") from None
        if r is None:
            raise _refuse(f"--viable-if {e!r} is empty")
        if not math.isfinite(r[2]):
            raise _refuse(f"--viable-if {e!r}: the threshold is not a finite number, so the rule "
                          f"would hold for every finite row or for none")
        rules.append(r)
    unknown = [r[0] for r in rules if r[0] not in target_names]
    if unknown:
        raise _refuse(f"--viable-if names {unknown}, which are not among the --only targets "
                      f"{list(target_names)}; no rule has been applied.")
    return rules


def apply_rules(Y: np.ndarray, target_names: Sequence[str],
                rules: Sequence[Tuple[str, str, float]]) -> np.ndarray:
    """(n,) bool: every rule holds (ANDed). A non-finite value fails every rule."""
    ok = np.ones(len(Y), dtype=bool)
    names = list(target_names)
    for name, op, thr in rules:
        col = Y[:, names.index(name)]
        with np.errstate(invalid="ignore"):
            ok &= {">": col > thr, ">=": col >= thr, "<": col < thr, "<=": col <= thr}[op]
    return ok


def label_rows(cases: np.ndarray, status: Sequence[str], Y: np.ndarray,
               target_names: Sequence[str], rules: Sequence[Tuple[str, str, float]],
               failed_cases: Optional[set], ensemble_drained: bool,
               baseline_case: int) -> Tuple[np.ndarray, str]:
    """(labels, corroboration): one of `LABELS` per row, by the table in the module docstring.

    `corroboration` names what relabelled RUNNING rows as failed: "ensemble_drained",
    "failed_cases", or "" when no RUNNING row was relabelled.
    """
    n = len(cases)
    finite = np.all(np.isfinite(Y), axis=1)
    passes = apply_rules(Y, target_names, rules)
    labels = np.empty(n, dtype=object)
    unknown, uncorroborated, corroboration = [], [], ""
    for i in range(n):
        s = status[i]
        known = (s in ("COMPLETED", "FAILED", "RUNNING") or s in EXCLUDED_STATUSES
                 or s.startswith(SCORE_ERROR_PREFIX))
        if not known:
            unknown.append((int(cases[i]), s))
            continue
        if cases[i] == baseline_case:
            labels[i] = "baseline"
        elif s == "COMPLETED":
            labels[i] = ("viable" if passes[i] else "nonviable") if finite[i] \
                else "completed_nonfinite"
        elif s == "FAILED":
            labels[i] = "failed"
        elif s == "RUNNING":
            if ensemble_drained:
                labels[i], corroboration = "failed", "ensemble_drained"
            elif failed_cases is not None and int(cases[i]) in failed_cases:
                labels[i], corroboration = "failed", "failed_cases"
            else:
                uncorroborated.append(int(cases[i]))
        else:
            labels[i] = "excluded"
    if unknown:
        raise _refuse(f"{len(unknown)} row(s) carry a status that is not COMPLETED, FAILED, "
                      f"RUNNING, PENDING, UNKNOWN or SCORE_ERROR:* (first (case, status): "
                      f"{unknown[:5]}); an unrecognised status is not guessed at.")
    if uncorroborated:
        raise _refuse(f"{len(uncorroborated)} RUNNING row(s) (first cases "
                      f"{uncorroborated[:5]}) are neither in --failed-cases nor covered by "
                      f"--ensemble-drained. RUNNING means still going or died part-way, and the "
                      f"two cannot be told apart from the Y matrix; say which with one of them.")
    return labels, corroboration


def read_round_config(path) -> Dict[str, Any]:
    """Path, SHA-256 and the `export A2MC_*=` lines of a round config, read as text only."""
    p = pathlib.Path(path)
    if not p.is_file():
        raise _refuse(f"--round-config {path} does not exist")
    lines, exports = [], {}
    pattern = re.compile(r"^\s*export\s+(A2MC_[A-Za-z0-9_]*)=(.*)$")
    for num, line in enumerate(p.read_text().splitlines(), 1):
        m = pattern.match(line)
        if not m:
            continue
        lines.append({"line": num, "text": line.strip()})
        exports[m.group(1)] = _shell_word(m.group(2))
    return {"path": str(path), "sha256": sha256_file(p), "export_lines": lines,
            "exports": exports}


def _shell_word(raw: str) -> str:
    """The first shell word of an assignment's right-hand side, quotes removed, never expanded."""
    raw = raw.strip()
    if raw[:1] in ("'", '"'):
        end = raw.find(raw[0], 1)
        return raw[1:end] if end > 0 else raw[1:]
    parts = raw.split()
    return parts[0] if parts else ""


def resolve_binary(label: str, manifest) -> Dict[str, Any]:
    """The archived binary `label` from a binary archive manifest: sha256, commit, binary name."""
    p = pathlib.Path(manifest)
    if not p.is_file():
        raise _refuse(f"--binary-manifest {manifest} does not exist")
    try:
        doc = json.loads(p.read_text())
    except json.JSONDecodeError as exc:
        raise _refuse(f"--binary-manifest {manifest} is not JSON: {exc}")
    archives = doc.get("archives") if isinstance(doc, dict) else None
    if not isinstance(archives, list):
        raise _refuse(f"--binary-manifest {manifest} has no `archives` list")
    entry = next((a for a in archives if isinstance(a, dict) and a.get("label") == label), None)
    if entry is None:
        known = [a.get("label") for a in archives if isinstance(a, dict)]
        raise _refuse(f"--training-binary {label!r} is not in {manifest} (labels: {known})")
    if not entry.get("sha256"):
        raise _refuse(f"archive {label!r} in {manifest} records no sha256")
    source = str(entry.get("source", ""))
    m = re.search(r"(?:@|commit)\s*([0-9a-fA-F]{7,40})\b", source)
    root = doc.get("_archive_root") or ""
    binary = entry.get("binary", "")
    return {"label": label, "sha256": entry["sha256"], "commit": m.group(1) if m else "",
            "binary": binary, "source": source, "model": entry.get("model", ""),
            "manifest": str(manifest), "manifest_sha256": sha256_file(p),
            "archived_path": f"{root}/{label}/{binary}" if root and binary else ""}


def _targets_model(path) -> str:
    """The model a targets file declares (`model:`), else $A2MC_MODEL, else ""."""
    import yaml

    try:
        doc = yaml.safe_load(pathlib.Path(path).read_text())
    except (OSError, yaml.YAMLError):
        doc = None
    if isinstance(doc, dict) and doc.get("model"):
        return str(doc["model"])
    return os.environ.get("A2MC_MODEL", "")


# =============================================================================
# Fit and proposal
# =============================================================================

def build_spec(names, lower, upper, targets: Sequence[Target], model_name: str,
               model_commit: str = "", ensemble_id: str = ""):
    from models.surrogate.spec import Provenance, SurrogateSpec, TargetSpec, hash_param_list

    return SurrogateSpec(
        name="bo_loop_s3", use_mode="offline_search", tier="S1",
        input_names=tuple(names), input_lower=tuple(float(v) for v in lower),
        input_upper=tuple(float(v) for v in upper),
        targets=tuple(TargetSpec(t.name, lower=t.lo, upper=t.hi, transform="identity")
                      for t in targets),
        provenance=Provenance(model=model_name, model_commit=model_commit,
                              param_list_hash=hash_param_list(list(names), list(lower),
                                                              list(upper)),
                              training_ensemble_id=ensemble_id))


def fit_surrogate(spec, X, Y, viable, V, n_restarts: int, max_points: int, keep_best: int,
                  subsample_seed: int, seed: int):
    from models.surrogate.learners import GPLearner
    from models.surrogate.tiers import S1Surrogate

    model = S1Surrogate(spec, learner=GPLearner(n_restarts=n_restarts, max_points=max_points,
                                                random_state=subsample_seed),
                        classifier="rf", calibration_fraction=0, random_state=seed)
    return model.fit(X, Y, viable, priority=V, keep_best=keep_best)


def drop_picks_near(proposal: Proposal, U_anchor: np.ndarray,
                    min_separation: float) -> Tuple[Proposal, int]:
    """Remove every pick within `min_separation` (unit-cube L-inf) of an anchor row."""
    if len(proposal.unit) == 0 or len(U_anchor) == 0:
        return proposal, 0
    near = min_distance(proposal.unit, U_anchor, "linf") <= min_separation
    n_near = int(near.sum())
    if not n_near:
        return proposal, 0
    keep = ~near
    changed = {f: getattr(proposal, f)[keep] for f in _PER_PICK}
    notes = list(proposal.notes) + [
        f"{n_near} pick(s) dropped: within {min_separation:g} of a case that has a design row "
        f"but no label (excluded or COMPLETED with a non-finite target)."]
    return dataclasses.replace(proposal, shortfall=proposal.shortfall + n_near, notes=notes,
                               **changed), n_near


def exit_code(status: str, shortfall: int, provenance_complete: bool) -> int:
    if status in STATUS_EXIT:
        return STATUS_EXIT[status]
    if shortfall > 0:
        return EXIT_SHORTFALL
    if not provenance_complete:
        return EXIT_PROVENANCE_INCOMPLETE
    return 0


# =============================================================================
# Plausibility
# =============================================================================

def _min_pairwise_linf(U: np.ndarray) -> float:
    if len(U) < 2:
        return float("nan")
    d = np.abs(U[:, None, :] - U[None, :, :]).max(axis=2)
    np.fill_diagonal(d, np.inf)
    return float(d.min())


def plausibility(proposal: Proposal, U_scan: np.ndarray, U_anchor: np.ndarray, model,
                 targets, lower, upper, seed: int) -> Dict[str, Any]:
    """Each figure of the proposals beside its chance value: the median and 5-95% range over
    `CHANCE_DRAWS` random draws, of as many points as were proposed, from the Sobol' scan."""
    U = proposal.unit
    k = len(U)
    out: Dict[str, Any] = {"n_proposals": k, "chance_draws": CHANCE_DRAWS,
                           "chance_source": "sobol_scan", "chance_draw_size": k}
    if k == 0:
        return out
    rng = np.random.default_rng(seed)
    draws = [rng.choice(len(U_scan), k, replace=k > len(U_scan)) for _ in range(CHANCE_DRAWS)]
    D = np.vstack([U_scan[d] for d in draws])
    d_obs_all = min_distance(D, U_anchor, "linf").reshape(CHANCE_DRAWS, k)
    d_obs = min_distance(U, U_anchor, "linf")

    def figure(value, chance):
        chance = np.asarray(chance, dtype=float)
        ok = chance[np.isfinite(chance)]
        return {"proposals": value,
                "chance_median": float(np.median(ok)) if len(ok) else float("nan"),
                "chance_p05": float(np.quantile(ok, 0.05)) if len(ok) else float("nan"),
                "chance_p95": float(np.quantile(ok, 0.95)) if len(ok) else float("nan")}

    inside = lambda A: float(np.mean(np.all((A >= 0) & (A <= 1), axis=-1)))  # noqa: E731
    near = lambda A: float(np.mean((A < NEAR_BOUND) | (A > 1 - NEAR_BOUND)))  # noqa: E731
    out["fraction_inside_bounds"] = figure(inside(U), [inside(U_scan[d]) for d in draws])
    out["min_pairwise_linf"] = figure(_min_pairwise_linf(U),
                                      [_min_pairwise_linf(U_scan[d]) for d in draws])
    out["nearest_observed_linf_min"] = figure(float(d_obs.min()), d_obs_all.min(axis=1))
    out["nearest_observed_linf_median"] = figure(float(np.median(d_obs)),
                                                 np.median(d_obs_all, axis=1))
    out["fraction_coords_within_1pct_of_bound"] = figure(near(U), [near(U_scan[d])
                                                                   for d in draws])
    Vm = np.asarray(proposal.V_mean, dtype=float)
    fin = Vm[np.isfinite(Vm)]
    if model is None or not np.isfinite(proposal.V_star) or not len(fin):
        # A cold-start pick is not scored by a posterior, so it has no V of the mean to set
        # beside the chance draws'.
        out["V_mean_note"] = ("not computed: the proposals carry no V of the posterior mean "
                              "(no surrogate, no finite V*, or cold-start picks, which are not "
                              "scored)")
        return out
    sc = score_candidates(model, targets, D, lower, upper, proposal.V_star)
    Vd = sc["V_mean"].reshape(CHANCE_DRAWS, k)
    out["V_star"] = float(proposal.V_star)
    out["V_mean_min"] = figure(float(fin.min()), Vd.min(axis=1))
    out["V_mean_max"] = figure(float(fin.max()), Vd.max(axis=1))
    return out


# =============================================================================
# Outputs
# =============================================================================

def _jsonable(obj):
    """Plain JSON types; non-finite floats become the strings "nan", "inf" and "-inf"."""
    if isinstance(obj, dict):
        return {str(k): _jsonable(v) for k, v in obj.items()}
    if isinstance(obj, np.ndarray):
        return _jsonable(obj.tolist())
    if isinstance(obj, (list, tuple)):
        return [_jsonable(v) for v in obj]
    if isinstance(obj, (bool, np.bool_)):
        return bool(obj)
    if isinstance(obj, (int, np.integer)):
        return int(obj)
    if isinstance(obj, (float, np.floating)):
        f = float(obj)
        if math.isfinite(f):
            return f
        return "nan" if math.isnan(f) else ("inf" if f > 0 else "-inf")
    if obj is None or isinstance(obj, str):
        return obj
    return str(obj)


def _cell(x) -> str:
    if x is None:
        return ""
    if isinstance(x, (bool, np.bool_)):
        return str(bool(x))
    if isinstance(x, (int, np.integer)):
        return str(int(x))
    if isinstance(x, (float, np.floating)):
        return repr(float(x))
    return str(x)


def write_table(path, proposal: Proposal, names, targets) -> None:
    tn = [t.name for t in targets]
    header = (["pick"] + list(names)
              + ["alpha", "ei", "p_viable", "hull_distance", "in_hull", "V_star_used",
                 "pick_source", "candidate_set"]
              + [f"predicted_{n}" for n in tn] + ["V_mean", "binding"]
              + [f"sd_ratio_{n}" for n in tn])
    with pathlib.Path(path).open("w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(header)
        for i in range(len(proposal.unit)):
            w.writerow([_cell(i + 1)]
                       + [_cell(v) for v in proposal.native[i]]
                       + [_cell(proposal.alpha[i]), _cell(proposal.ei[i]),
                          _cell(proposal.p_viable[i]), _cell(proposal.hull_distance[i]),
                          _cell(proposal.in_hull[i]), _cell(proposal.V_star_used[i]),
                          _cell(proposal.pick_source[i]), _cell(proposal.candidate_set[i])]
                       + [_cell(v) for v in proposal.predicted[i]]
                       + [_cell(proposal.V_mean[i]), _cell(proposal.binding[i])]
                       + [_cell(v) for v in proposal.sd_ratio[i]])


def _classifier_record(model) -> Dict[str, Any]:
    clf = getattr(model, "_clf", None)
    rec: Dict[str, Any] = {"registry_name": "rf", "p_viable_is": P_VIABLE_IS,
                           "fitted": clf is not None}
    if clf is None:
        rec["note"] = ("no classifier was fitted: every labelled row is viable, so P(viable) is 1 "
                       "at every candidate")
        return rec
    rec["estimator"] = type(clf).__name__
    rec["settings"] = {k: v for k, v in sorted(clf.get_params().items())
                       if v is None or isinstance(v, (bool, int, float, str))}
    return rec


def _cold_start_classifier_record(proposal: Proposal) -> Optional[Dict[str, Any]]:
    """The classifier `propose_batch` fitted for a cold start without a surrogate, or None."""
    name = proposal.diagnostics.get("classifier") if proposal.status == "cold_start" else None
    if name is None:
        return None
    return {"registry_name": name, "p_viable_is": P_VIABLE_IS,
            "fitted_by": "propose_batch, on the rows passed to it as observed"}


def _hull_record(model, U_scan, lower, upper, applied: bool) -> Dict[str, Any]:
    """The surrogate's hull gate and where the Sobol' scan falls against it. `applied` is False
    for a cold start, whose picks are not gated: the record then describes the fitted gate only."""
    from tools.bayesian_optimization.acquisition import unit_to_native

    gate = getattr(model, "_gate", None)
    dist, inside = model.hull(unit_to_native(U_scan, lower, upper))
    qs = (0.0, 0.05, 0.25, 0.5, 0.75, 0.95, 1.0)
    note = ("the threshold is a quantile of the viable training rows' own k-NN distances; on a "
            "design with one-coordinate neighbours (a Saltelli design) it is set by those "
            "neighbours, so compare it with the scan's distances")
    if not applied:
        note = ("NOT APPLIED: a cold start gates no pick, so the threshold and the scan's "
                "position against it did not constrain this proposal. " + note)
    return {"applied": bool(applied),
            "threshold": getattr(gate, "threshold", float("nan")),
            "k": getattr(gate, "k", None), "quantile": getattr(gate, "quantile", None),
            "sobol_scan_distance_quantiles": {f"q{int(round(100 * q)):02d}":
                                              float(np.quantile(dist, q)) for q in qs},
            "sobol_scan_fraction_inside": float(np.mean(inside)),
            "note": note}


def _recipe(out: pathlib.Path, n_proposed: int, param_list, round_cfg, binary) -> Dict[str, Any]:
    pattern = (round_cfg or {}).get("exports", {}).get("A2MC_CASE_NAME_PATTERN")
    run_root = f"${{A2MC_OUTPUT_DIR}}_BO_{out.name}"
    matrix = str(out / MATRIX_FILE) if n_proposed else None
    # The materializer's case name replaces `{N}` and nothing else. `${...}` is a shell variable.
    extra_placeholders = sorted(set(re.findall(r"(?<!\$)\{[^{}]*\}", pattern or "")) - {"{N}"})
    cmd, cmd_note = None, None
    if matrix is None:
        cmd_note = "nothing was proposed, so there is nothing to materialise"
    elif not round_cfg:
        # The run root and the case pattern come from the round config; without it the run root
        # would expand to a relative `_BO_...` directory.
        cmd_note = ("no command: the recipe needs --round-config, which sets A2MC_OUTPUT_DIR "
                    "(the run root's prefix) and the case pattern")
    elif extra_placeholders:
        cmd_note = (f"no command: the case pattern {pattern!r} carries {extra_placeholders} "
                    f"besides {{N}}, and scripts/materialize_adapter_ensemble.py replaces only "
                    f"{{N}}, so every case name would keep them literally")
    else:
        parts = ["python", "scripts/materialize_adapter_ensemble.py",
                 "--param-list", str(param_list), "--matrix", matrix,
                 "--run-root", run_root, "--start", "1"]
        if pattern and "$" in pattern:
            # A quoted argument would pass the variable unexpanded. The sourced round config
            # exports the expanded pattern, which the materializer takes as its default.
            cmd_note = ("--case-pattern is left out: the pattern contains a shell variable, "
                        "so the command relies on the A2MC_CASE_NAME_PATTERN the sourced round "
                        "config exports, which the materializer reads as its default")
        elif pattern:
            parts += ["--case-pattern", pattern]
        cmd = " ".join(shlex.quote(p) if p != run_root else f'"{p}"' for p in parts)
        cmd = (f"source {shlex.quote(round_cfg['path'])} && "
               f'test -n "${{A2MC_OUTPUT_DIR}}" && test ! -e "{run_root}" && {cmd}')
    return {
        "matrix": matrix,
        "run_root": run_root,
        "run_root_must_not_exist": True,
        "case_name_pattern": pattern,
        "case_name_pattern_source": ("round config A2MC_CASE_NAME_PATTERN" if pattern
                                     else "not recorded: pass --round-config"),
        "start": 1,
        "baseline": False,
        "binary": (None if binary is None else
                   {"label": binary["label"], "sha256": binary["sha256"],
                    "path": binary["archived_path"],
                    "instruction": ("point the model's binary setting at this archived path "
                                    "before materialising, and check its sha256 before "
                                    "submitting")}),
        "command": cmd,
        "command_note": cmd_note,
        "warning": ("do not materialise into the round's own run root (the round config's "
                    "A2MC_OUTPUT_DIR): scripts/materialize_adapter_ensemble.py does not refuse "
                    "an existing case directory, so proposal case N overwrites the round's "
                    "completed case N. Use the fresh run_root above, which must not exist."),
    }


# =============================================================================
# CLI
# =============================================================================

def _versions() -> Dict[str, str]:
    import scipy
    import sklearn

    return {"python": platform.python_version(), "numpy": np.__version__,
            "scipy": scipy.__version__, "scikit-learn": sklearn.__version__,
            "platform": platform.platform()}


def main(argv=None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    t_start = time.perf_counter()
    ap = argparse.ArgumentParser(
        description="docs/42 stage S3 -- propose the next batch from a completed ensemble, "
                    "without materialising or submitting it.")
    ap.add_argument("--x-matrix", required=True, help="design matrix; case i is row i-1")
    ap.add_argument("--y-matrix", required=True, help="extracted CSV: case,status,<targets>")
    ap.add_argument("--param-list", required=True, help="explicit-column parameter list")
    ap.add_argument("--targets", default=os.environ.get("A2MC_VALIDATION_TARGETS"),
                    help="targets.yaml (default: $A2MC_VALIDATION_TARGETS)")
    ap.add_argument("--only", required=True, help="comma-separated target names")
    ap.add_argument("--viable-if", action="append",
                    help="repeatable, ANDed; e.g. 'NPP>1' -- what counts as a run that lived")
    ap.add_argument("--viable-if-finite-only", action="store_true",
                    help="count every COMPLETED row with finite targets as viable")
    ap.add_argument("--baseline-case", type=int, default=0)
    ap.add_argument("--failed-cases", help="CSV with a `case` column; relabels RUNNING rows")
    ap.add_argument("--ensemble-drained", action="store_true",
                    help="every RUNNING row is a run that died")
    ap.add_argument("--round-config", help="the round's config script, recorded as text")
    ap.add_argument("--training-binary", help="archive label of the binary behind the Y matrix")
    ap.add_argument("--binary-manifest", help="binary archive manifest that resolves the label")
    ap.add_argument("--salib-problem", help="SALib problem file to check names and bounds against")
    ap.add_argument("--q", type=int, default=8)
    ap.add_argument("--n-cand", type=int, default=4096)
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--subsample-seed", type=int, default=0)
    ap.add_argument("--max-points", type=int, default=None,
                    help="GP row cap (default: no cap, at least the viable row count)")
    ap.add_argument("--keep-best", type=int, default=50)
    ap.add_argument("--n-restarts", type=int, default=0)
    ap.add_argument("--out", required=True)
    ap.add_argument("--force", action="store_true", help="write into a non-empty --out")
    ap.add_argument("--dry-run", action="store_true",
                    help="required: propose and write, never materialise or submit")
    a = ap.parse_args(argv)

    if not a.dry_run:
        raise _refuse("--dry-run is required. This command proposes and stops; running the "
                      "proposals and refitting is the closed loop of docs/42 stage S4.")
    if not a.targets:
        raise _refuse("no --targets and $A2MC_VALIDATION_TARGETS unset")
    if a.q < 1:
        raise _refuse(f"--q is {a.q}; propose at least one parameter set")
    if a.n_cand < 1 or a.n_cand & (a.n_cand - 1):
        raise _refuse(f"--n-cand is {a.n_cand}; a Sobol' scan needs a power of two")
    if a.keep_best < 0 or a.n_restarts < 0:
        raise _refuse("--keep-best and --n-restarts must be >= 0")
    if a.max_points is not None and a.max_points < max(1, a.keep_best):
        raise _refuse(f"--max-points {a.max_points} is below --keep-best {a.keep_best}")
    out = pathlib.Path(a.out)
    if out.exists() and not out.is_dir():
        raise _refuse(f"--out {out} exists and is not a directory")
    if out.is_dir() and any(out.iterdir()) and not a.force:
        raise _refuse(f"--out {out} is not empty; choose a new directory or pass --force")
    if bool(a.training_binary) != bool(a.binary_manifest):
        raise _refuse("--training-binary and --binary-manifest go together: the manifest "
                      "resolves the label to its sha256")

    only = [s.strip() for s in a.only.split(",") if s.strip()]
    rules = parse_rules(a.viable_if, a.viable_if_finite_only, only)
    targets = load_targets(a.targets, only)
    tnames = [t.name for t in targets]

    names, lower, upper = read_param_list(a.param_list)
    if a.salib_problem:
        check_salib_problem(a.salib_problem, names, lower, upper)
    X = read_x_matrix(a.x_matrix, names, lower, upper)
    cases, status, Y = read_y_matrix(a.y_matrix, tnames)
    failed_cases = read_failed_cases(a.failed_cases) if a.failed_cases else None
    labels, corroboration = label_rows(cases, status, Y, tnames, rules, failed_cases,
                                       a.ensemble_drained, a.baseline_case)

    known = labels != "baseline"
    idx = cases[known] - 1
    bad = cases[known][(idx < 0) | (idx >= len(X))]
    if len(bad):
        raise _refuse(f"{len(bad)} case number(s) fall outside the {len(X)}-row design matrix "
                      f"under the 1-based convention (first few: {bad[:5].tolist()}). Either the "
                      f"matrix is the wrong round's or the baseline case is not "
                      f"{a.baseline_case}.")

    round_cfg = read_round_config(a.round_config) if a.round_config else None
    binary = resolve_binary(a.training_binary, a.binary_manifest) if a.training_binary else None

    # Every case with a design row is an observed POSITION, whatever its label, so no case that
    # already exists in the ensemble can be proposed again. Only the fit labels carry a result.
    kcases, klabels = cases[known], labels[known]
    X_known = X[idx]
    V_all, _, _ = violation_matrix(Y, tnames, targets)
    V_known = np.where(np.isin(klabels, ("viable", "nonviable")), V_all[known], np.nan)
    Y_known = np.where(np.isin(klabels, ("viable", "nonviable"))[:, None], Y[known], np.nan)
    fit = np.isin(klabels, FIT_LABELS)
    viable_known = klabels == "viable"
    n_viable = int(viable_known.sum())

    model_name = binary["model"] if binary and binary.get("model") else _targets_model(a.targets)
    ens = (round_cfg or {}).get("exports", {}).get("A2MC_ENSEMBLE_NAME", "")
    spec = build_spec(names, lower, upper, targets, model_name,
                      model_commit=binary["commit"] if binary else "",
                      ensemble_id="" if "$" in ens else ens)
    max_points = a.max_points if a.max_points is not None else max(n_viable, a.keep_best, 1)

    model, t_fit = None, 0.0
    if n_viable >= 2:
        t0 = time.perf_counter()
        try:
            model = fit_surrogate(spec, X_known[fit], Y_known[fit], viable_known[fit],
                                  V_known[fit], a.n_restarts, max_points, a.keep_best,
                                  a.subsample_seed, a.seed)
        except ValueError as exc:
            raise _refuse(f"the surrogate fit refused its inputs: {exc}")
        t_fit = time.perf_counter() - t0

    # Without a surrogate, propose_batch fits its own viability classifier on the rows it is
    # given, with viable_obs as the labels, whenever both labels occur among them. A row with a
    # design row but no label must never become one of those labels.
    #   - The labelled rows share one class (or there are none): the unlabelled rows are given
    #     that class. No second class appears, so no classifier is fitted, and every known
    #     position still anchors the maximin. Their V is NaN, so none can be the incumbent.
    #   - The labelled rows hold both classes: a classifier is fitted whatever the unlabelled rows
    #     are given, so they are withheld from propose_batch, and so from the maximin anchors; a
    #     pick within MIN_SEPARATION of one is dropped afterwards.
    # With a surrogate, propose_batch fits no classifier and every known row is passed as is.
    unlabelled = ~fit
    viable_obs = viable_known.copy()
    withhold, unlabelled_handling = False, "none"
    if unlabelled.any():
        unlabelled_handling = "observed_positions"
        classes = np.unique(viable_known[fit])
        if model is None and len(classes) == 2:
            withhold, unlabelled_handling = True, "withheld"
        elif model is None:
            cls = bool(classes[0]) if len(classes) else False
            viable_obs[unlabelled] = cls
            unlabelled_handling = f"given_the_labelled_class:{'viable' if cls else 'nonviable'}"
    obs = fit if withhold else np.ones(len(kcases), dtype=bool)
    t0 = time.perf_counter()
    try:
        proposal = propose_batch(model, targets, lower, upper, X_known[obs], V_known[obs],
                                 viable_obs[obs], a.q, n_cand=a.n_cand, seed=a.seed,
                                 min_separation=MIN_SEPARATION)
    except ValueError as exc:
        raise _refuse(f"propose_batch refused its inputs: {exc}")
    n_dropped = 0
    if withhold:
        proposal, n_dropped = drop_picks_near(
            proposal, native_to_unit(X_known[unlabelled], lower, upper), MIN_SEPARATION)
        proposal = dataclasses.replace(proposal, notes=list(proposal.notes) + [
            f"{int(unlabelled.sum())} case(s) with a design row but no label were withheld from "
            f"the cold-start classifier, and so from the maximin anchors; only a pick within "
            f"{MIN_SEPARATION:g} of one is dropped."])
    t_propose = time.perf_counter() - t0

    U_known = native_to_unit(X_known, lower, upper)
    U_scan = sobol_candidates(len(names), a.n_cand, a.seed)
    plaus = plausibility(proposal, U_scan, U_known, model, targets, lower, upper, a.seed)
    obs_cases = kcases[obs]
    V_star_case = (None if proposal.V_star_index is None
                   else int(obs_cases[proposal.V_star_index]))

    missing_prov = [k for k, v in (("round_config", round_cfg), ("training_binary", binary))
                    if v is None]
    prov_complete = not missing_prov
    n_proposed = len(proposal.unit)
    code = exit_code(proposal.status, proposal.shortfall, prov_complete)

    surrogate = None
    if model is not None:
        i_star = int(np.flatnonzero(kcases == V_star_case)[0]) if V_star_case is not None \
            else None
        in_train = (model.trains_on(X_known[i_star:i_star + 1]) if i_star is not None
                    else [None] * len(targets))
        surrogate = {
            "tier": "S1", "calibration_fraction": 0,
            "learner": {"family": "gp",
                        "n_restarts": {t.name: int(lr.n_restarts)
                                       for t, lr in zip(targets, model._models)},
                        "max_points_requested": a.max_points, "max_points": max_points,
                        "keep_best": a.keep_best, "subsample_seed": a.subsample_seed,
                        "priority": "V"},
            "n_fit_rows": int(fit.sum()),
            "n_used": {t.name: int(len(r)) for t, r in zip(targets, model.train_rows_)},
            "incumbent_in_training": {t.name: (None if v is None else bool(v))
                                      for t, v in zip(targets, in_train)},
            "classifier": _classifier_record(model),
            "spec_provenance": dataclasses.asdict(spec.provenance)}

    counts = {lab: int(np.sum(labels == lab)) for lab in LABELS}
    status_counts: Dict[str, int] = {}
    for s in status:
        status_counts[s] = status_counts.get(s, 0) + 1
    failed_from = {s: int(sum(1 for st, lab in zip(status, labels)
                              if st == s and lab == "failed")) for s in ("FAILED", "RUNNING")}

    inputs = {"x_matrix": a.x_matrix, "y_matrix": a.y_matrix, "param_list": a.param_list,
              "targets": a.targets, "failed_cases": a.failed_cases,
              "salib_problem": a.salib_problem, "round_config": a.round_config,
              "binary_manifest": a.binary_manifest}
    meta: Dict[str, Any] = {
        "stage": "docs/42 S3 dry run",
        "outcome": OUTCOMES[code], "exit_code": code,
        "proposal_status": proposal.status, "batching": proposal.batching,
        "q": a.q, "n_proposed": n_proposed, "shortfall": proposal.shortfall,
        "n_dropped_near_unlabelled": n_dropped,
        "unlabelled_rows": {"n": int(unlabelled.sum()), "handling": unlabelled_handling},
        "counts": proposal.counts, "r_sep": proposal.r_sep, "min_separation": MIN_SEPARATION,
        "V_star": {"value": proposal.V_star, "case": V_star_case},
        "inputs": {k: (None if v is None else {"path": v, "sha256": sha256_file(v)})
                   for k, v in inputs.items()},
        "targets": [{"name": t.name, "observed": t.observed, "uncertainty": t.uncertainty,
                     "lo": t.lo, "hi": t.hi} for t in targets],
        "parameters": [{"name": n, "lower": lo, "upper": hi}
                       for n, lo, hi in zip(names, lower, upper)],
        "viability": {"rules": list(a.viable_if or []),
                      "parsed": [list(r) for r in rules],
                      "finite_only": bool(a.viable_if_finite_only), "combined": "AND"},
        "status_counts": dict(sorted(status_counts.items())),
        "labels": {"counts": counts,
                   "failed_from_status": failed_from,
                   "running_corroboration": corroboration or None,
                   "cases": {lab: sorted(int(c) for c in cases[labels == lab])
                             for lab in LABELS}},
        "n_viable": n_viable,
        "surrogate": surrogate,
        "cold_start_classifier": _cold_start_classifier_record(proposal),
        "hull": (_hull_record(model, U_scan, lower, upper,
                              applied=proposal.status != "cold_start")
                 if model is not None else None),
        "scan_vs_local": proposal.diagnostics.get("scan_vs_local"),
        "diagnostics": proposal.diagnostics,
        "seeds": {"seed": a.seed, "sobol_seed": a.seed, "classifier_random_state": a.seed,
                  "subsample_seed": a.subsample_seed, "plausibility_seed": a.seed},
        "plausibility": plaus,
        "provenance": {"status": "complete" if prov_complete else "provenance_incomplete",
                       "missing": missing_prov, "round_config": round_cfg,
                       "training_binary": binary},
        "materialisation_recipe": _recipe(out, n_proposed, a.param_list, round_cfg, binary),
        "notes": list(proposal.notes),
        "outputs": {"proposal_matrix": MATRIX_FILE if n_proposed else None,
                    "proposal_table": TABLE_FILE, "proposal_meta": META_FILE,
                    "notes": NOTES_FILE},
    }

    out.mkdir(parents=True, exist_ok=True)
    matrix_path = out / MATRIX_FILE
    if n_proposed:
        np.savetxt(matrix_path, proposal.native)
    elif matrix_path.exists():
        # Only reachable under --force: a matrix left by an earlier run must not sit beside a
        # record that says nothing was proposed.
        matrix_path.unlink()
    write_table(out / TABLE_FILE, proposal, names, targets)
    meta["run"] = {"argv": argv, "cwd": os.getcwd(), "versions": _versions(),
                   "runtime_s": {"fit": t_fit, "propose": t_propose,
                                 "total": time.perf_counter() - t_start}}
    (out / META_FILE).write_text(json.dumps(_jsonable(meta), indent=2) + "\n")
    (out / NOTES_FILE).write_text(
        "# BO S3 dry proposal\n\n"
        "Exact invocation, run from `" + os.getcwd() + "`:\n\n"
        "```\n" + shlex.join(["python", "tools/bayesian_optimization/bo_loop.py", *argv])
        + "\n```\n\n"
        f"Outcome: {OUTCOMES[code]} (exit {code}), {n_proposed} of {a.q} proposals, provenance "
        f"{meta['provenance']['status']}. Nothing was materialised or submitted; the "
        f"materialisation recipe is in `{META_FILE}`.\n")

    _print_summary(meta, proposal, targets, out)
    return code


def _fmt(x, spec=".4g") -> str:
    try:
        f = float(x)
    except (TypeError, ValueError):
        return str(x)
    return format(f, spec) if math.isfinite(f) else str(f)


def _print_summary(meta, proposal: Proposal, targets, out) -> None:
    lc = meta["labels"]["counts"]
    print(f"\nrows: {lc['viable']} viable, {lc['nonviable']} nonviable, {lc['failed']} failed, "
          f"{lc['completed_nonfinite']} completed with a non-finite target, {lc['excluded']} "
          f"excluded, {lc['baseline']} baseline")
    print(f"V* = {_fmt(meta['V_star']['value'])} (case {meta['V_star']['case']})")
    sv = meta["surrogate"]
    if sv is not None:
        print(f"GP rows used per target: {sv['n_used']}; incumbent in training: "
              f"{sv['incumbent_in_training']}")
    print(f"status {proposal.status}, batching {proposal.batching}, "
          f"{meta['n_proposed']} of {meta['q']} proposed; counts {proposal.counts}; "
          f"r_sep {_fmt(proposal.r_sep)}")
    svl = meta["scan_vs_local"]
    if svl:
        print(f"best alpha: scan {_fmt(svl['sets']['sobol']['best_alpha'])}, local "
              f"{_fmt(svl['sets']['local']['best_alpha'])} (ratio "
              f"{_fmt(svl['ratio_local_to_scan'])})")
    if len(proposal.unit):
        print("\n  pick  source              set             alpha       p_viable  V_mean   "
              "binding")
        for i in range(len(proposal.unit)):
            print(f"  {i + 1:4d}  {proposal.pick_source[i]:18s}  {proposal.candidate_set[i]:14s}  "
                  f"{_fmt(proposal.alpha[i], '.3e'):>10s}  {_fmt(proposal.p_viable[i], '.3f'):>8s}"
                  f"  {_fmt(proposal.V_mean[i], '.3f'):>7s}  {proposal.binding[i]}")
    pl = meta["plausibility"]
    if pl.get("n_proposals"):
        print(f"\n  plausibility: proposals | chance median [5%, 95%] over {CHANCE_DRAWS} draws "
              f"of {pl['chance_draw_size']} Sobol' scan points")
        for key in ("fraction_inside_bounds", "min_pairwise_linf", "nearest_observed_linf_min",
                    "nearest_observed_linf_median", "fraction_coords_within_1pct_of_bound",
                    "V_mean_min", "V_mean_max"):
            if key in pl:
                f = pl[key]
                print(f"    {key:38s} {_fmt(f['proposals']):>9s} | {_fmt(f['chance_median'])} "
                      f"[{_fmt(f['chance_p05'])}, {_fmt(f['chance_p95'])}]")
        if "V_star" in pl:
            print(f"    (V* = {_fmt(pl['V_star'])})")
        if "V_mean_note" in pl:
            print(f"    V_mean range: {pl['V_mean_note']}")
    hull = meta["hull"]
    if hull is not None and not hull["applied"]:
        print(f"  hull gate threshold {_fmt(hull['threshold'])} recorded but not applied "
              f"(cold start)")
    for note in proposal.notes:
        print(f"  note: {note}")
    if meta["provenance"]["status"] != "complete":
        bar = "!" * 78
        print(f"\n{bar}\n  PROVENANCE INCOMPLETE: missing {meta['provenance']['missing']}. The "
              f"proposals cannot be tied\n  to the round config and model binary that produced "
              f"the training data.\n{bar}")
    print(f"\nwrote {out} -- outcome {meta['outcome']}, exit {meta['exit_code']}")


if __name__ == "__main__":
    sys.exit(main())
