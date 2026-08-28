#!/usr/bin/env python
"""Validate a backend-dispatched calibration targets.yaml against a model's output registry.

The model-generic parallel of `tools/validate_targets_config.py` (which is FATES-shaped —
`PFT<id>_<var>` names + SZPF). Adapter models (EcoSIM, …) drive screening through their
ModelBackend + `phases/phase2_screening/screen_ensemble.py`'s backend branch, where each
target names its history `variable` + grouping-axis `pft` + a time `window`/`time`
explicitly (`tools/targets_loader.py` reads them onto `Target`). This validator catches the
pitfalls BEFORE an ensemble runs — every one of these silently drops or NaN-poisons a target:

    G1  target has no `variable`                                        ERROR
    G2  `variable` not in the model's output registry (CDL)             ERROR (extraction KeyError)
    G3  `variable` is inactive-by-default AND not in spec.hist_activate ERROR (never on the tape)
    G4  no `pft` (grouping-axis slot) on a per-group variable           WARN  (collapses to col 0)
    G5  no scalar `observed`                                            ERROR (relative error needs it)
    G6  no `window`/`time`/`window_years`; or a malformed range         ERROR (empty/undefined reduce)
    G7  observed <= 0                                                   ERROR (relative metric ÷ ~0)
    G8  description flags a PLACEHOLDER observed value                  WARN  (not validated science)
    G9  `denominator` not in the model's output registry                ERROR (extraction KeyError,
                                                                                same class as G2)
    G10 `denominator` is inactive-by-default AND not activated          ERROR (never on the tape,
                                                                                same class as G3)
    G11 `reduce` needs a companion observed-series file                 ERROR (missing field, file
        (REDUCE_REQUIRES_SERIES_FILE) but it's absent/unreadable/                not found, or not a
        not a >=1-row two-column numeric table                                  readable 2-col table)
    G12 `reduce` needs a companion series file AND uses the SENTINEL    ERROR (wrong `observed` value
        convention (REDUCE_SENTINEL_OBSERVED) but `observed` != the             silently mis-scores —
        required sentinel                                                       see backend docstring)
    G13 `reduce` is explicitly set but is none of: this model's         ERROR (the model-agnostic
        MODEL_REDUCES, the shared ECOSYSTEM_REDUCES, or the generic             time-reduce branch in
        {last,mean,max} — AND the target has no `window`                       reduce_target() only
                                                                                  applies `reduce`
                                                                                  INSIDE the window
                                                                                  branch; without a
                                                                                  window it is SILENTLY
                                                                                  IGNORED and the last
                                                                                  time step is returned
                                                                                  regardless)
    G14 a name appears in BOTH `prescribed_initialization:` and      ERROR (the run is BUILT FROM it,
        `targets:`                                                          so scoring it rewards
                                                                            the input, not the model)

Exit: 0 clean · 1 warnings only · 2 any error.

Usage:
    python tools/validate_model_targets.py --model ecosim \
        --targets use_cases/EcoSIM_BioCON/validation/targets.yaml

Author: Jing Tao with Claude
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent

# Table-driven, not per-model branching (CLAUDE.md "keep generic"): a derived reduce
# that scores against a full companion series (PFLOTRAN's `outflow_flux`, the only
# member today) needs `target[<field>]` to resolve to a readable numeric table. A
# future adapter's own full-series reduce adds itself here without touching the
# checks below.
REDUCE_REQUIRES_SERIES_FILE = {
    "outflow_flux": "observed_series_file",
}

# The SENTINEL CONVENTION (see `PFLOTRANBackend._reduce_outflow_flux`'s docstring):
# a reduce that returns `sentinel + <normalized error>` so it can share the generic
# `relative_error` outer aggregation must declare `observed` as exactly this value —
# any other `observed` silently changes what the recovered metric means, with no
# crash to flag it.
REDUCE_SENTINEL_OBSERVED = {
    "outflow_flux": 1.0,
}


def _resolve_registry(model: str):
    """(var set, {var: 'active'|'inactive'}) from the model's output registry.

    The registry is normally a CDL. It is NOT always: a model with no NetCDF
    history tape has some other authoritative output surface, and for that model
    the CDL parser below silently yields an EMPTY var set — which then reports
    every target as a nonexistent variable, i.e. a false failure that looks
    exactly like a real one. (Found on the PFLOTRAN onboarding, where the
    registry is the fixed-width `*-mas.dat` mass-balance tape.)

    So: if the dataset's `output_cdl` is not a `.cdl`, dispatch through the
    model's own `spec.output_parser_class`, which is the object that already
    knows how to inventory that surface. Model-generic — no per-model branch.
    Status is 'active' for every column such a parser returns, because a column
    present on a real tape is by definition active.
    """
    sys.path.insert(0, str(REPO))
    import importlib
    importlib.import_module(f"models.{model}")
    from models import registry
    # Find the model's ModelDataset (carries output_cdl); take the canonical/first.
    datasets = registry._DATASETS.get(model, {})
    if not datasets:
        raise SystemExit(f"model '{model}' has no registered dataset (no output_cdl to validate against)")
    ds = next(iter(datasets.values()))
    cdl = Path(getattr(ds, "output_cdl"))
    if not cdl.is_absolute():
        cdl = REPO / cdl
    if not cdl.exists():
        raise SystemExit(f"output registry not found: {cdl}")

    if cdl.suffix.lower() != ".cdl":
        parser_cls = getattr(registry.get_model(model).spec, "output_parser_class", None)
        if parser_cls is None:
            raise SystemExit(
                f"output registry {cdl.name} is not a CDL and model '{model}' "
                f"declares no output_parser_class to read it with"
            )
        variables = parser_cls().parse(cdl)
        varset = set(variables.keys())
        return varset, {v: "active" for v in varset}, cdl

    text = cdl.read_text()
    # variable set
    varset = set(re.findall(r"^\s+(?:float|double|int)\s+([A-Za-z0-9_]+)\(", text, re.M))
    # per-var status (from the :status attr the --from-source CDL emits; default 'active')
    status = {}
    cur = None
    for line in text.splitlines():
        m = re.match(r"^\s+(?:float|double|int)\s+([A-Za-z0-9_]+)\(", line)
        if m:
            cur = m.group(1); status.setdefault(cur, "active")
        elif cur:
            s = re.match(r'^\s+:status\s*=\s*"([^"]+)"', line)
            if s:
                status[cur] = s.group(1)
    return varset, status, cdl


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--model", required=True, help="onboarded model name (e.g. ecosim)")
    ap.add_argument("--targets", required=True, help="path to the calibration targets.yaml")
    args = ap.parse_args()

    import yaml
    sys.path.insert(0, str(REPO))
    import importlib
    importlib.import_module(f"models.{args.model}")
    from models import registry
    backend = registry.get_model(args.model)
    spec = backend.spec
    activate = set(getattr(spec, "hist_activate", ()) or ())
    model_reduces = getattr(backend, "MODEL_REDUCES", frozenset())
    from tools.model_evaluate_case import ECOSYSTEM_REDUCES  # single source of truth, not re-listed here
    # ECOSYSTEM_REDUCES/MODEL_REDUCES dispatch unconditionally (before the window
    # check) so they don't need a `window` to have effect. The three generic literal
    # keywords ("last"/"mean"/"max") do — reduce_target() only reads `reduce` INSIDE
    # the `if "window" in target` branch — so they belong on the "needs a window"
    # side of G13, not the exempt side.
    window_independent_reduces = ECOSYSTEM_REDUCES | model_reduces

    varset, status, cdl = _resolve_registry(args.model)
    with open(args.targets) as fh:
        doc = yaml.safe_load(fh)
    targets = doc.get("targets", {})

    errors, warns = [], []

    # G14 -- an entry the run is BUILT FROM must not also be scored against.
    # `prescribed_initialization:` holds observations used to PRESCRIBE the model's initial
    # state (BioCON's four SOC_* depth stocks build the initial soil-carbon profile). Scoring
    # such an entry rewards the input: the model reproduces it because it was handed it, so a
    # good "score" measures the prescription, not the model. This check exists because the
    # opposite mistake was made and repeated -- the SOC stocks sat under `targets:` for weeks
    # and were still being reasoned about as unfinished targets on 2026-08-15.
    for name in sorted(set(doc.get("prescribed_initialization", {})) & set(targets)):
        errors.append(f"[G14] {name}: listed in BOTH `prescribed_initialization:` and `targets:`. "
                      f"It is an input the run is built from, so scoring it rewards the input. "
                      f"Keep it in `prescribed_initialization:` only.")
    for name, t in targets.items():
        var = t.get("variable")
        if not var:
            errors.append(f"[G1] {name}: no `variable` (backend targets need an explicit history var)")
            continue
        # `variable` may be a LIST — a target summed over several history vars
        # (EcoSIM's plant_C is [SHOOT_C_pft, Root_C_pft]). The scalar-only form
        # crashed with `TypeError: unhashable type: 'list'` before any target
        # was reported, so a real config silently produced a stack trace instead
        # of a verdict. Check every member.
        for v in (var if isinstance(var, list) else [var]):
            if v not in varset:
                errors.append(f"[G2] {name}: variable '{v}' not in {cdl.name} (extraction would KeyError)")
            elif status.get(v, "active") == "inactive" and v not in activate:
                errors.append(f"[G3] {name}: '{v}' is inactive-by-default and NOT in "
                              f"{args.model} spec.hist_activate — it will never be on the tape "
                              f"(add it to hist_fincl1 / <MODEL>_SPEC.hist_activate)")
        if t.get("pft") is None:
            warns.append(f"[G4] {name}: no `pft` slot — a per-group var collapses to column 0")
        obs = t.get("observed")
        if obs is None:
            errors.append(f"[G5] {name}: no scalar `observed` (relative error needs it)")
        elif float(obs) <= 0:
            errors.append(f"[G7] {name}: observed={obs} <= 0 (relative metric divides by ~0)")
        # `window_years` is a FIRST-CLASS time reduction, not an extra: the EcoSIM backend
        # PREFERS it over the legacy `window` (models/ecosim/backend.py::_select_years —
        # "prefer explicit `window_years` (absolute calendar years), else fall back to the
        # legacy timestep `window` reading"). It exists because `window` slices raw record
        # indices assuming 365-day years, which is wrong on EcoSIM's true Gregorian calendar.
        # Omitting it here produced 7 FALSE errors across the two live EcoSIM cases, and got
        # worse the more a targets file was modernised off the legacy field.
        if not ({"window", "time", "window_years"} & t.keys()):
            # A target carrying `track:` is explicitly off the scoring path, so "no time
            # reduction" is not a defect in a live target and must not inflate the ERROR count.
            # It is still REPORTED, because the signal must survive (handoff 20260815a item 2).
            #
            # But the warning deliberately does NOT say "this will be wired later". That framing
            # is what this rule got wrong on 2026-08-15: BioCON's four SOC_* entries were WARNed
            # as parked targets awaiting a time reduction, when in fact SOC is not a target at
            # all -- it is the PRESCRIBED INITIAL soil-carbon profile the run is built from
            # (use_cases/EcoSIM_BioCON/memory/logs/20260718a_SOC_Prescribed_Initialization_And_Extraction.md:
            # "Scoring it rewards the input"). Wiring it would have been the wrong repair, and a
            # warning that presumes the repair steers the reader straight at it.
            #
            # So the question this warning asks is the one whose wrong answer caused the error:
            # does this belong under `targets:` at all? An input the run CONSUMES belongs in
            # `prescribed_initialization:` (checked by G14 below); a genuine but unfinished
            # target needs both a time reduction and a supported `reduce`.
            #
            # Deliberately NOT fixed by giving such a target a window_years: that would make it
            # pass G6 while an unsupported `reduce` still raises (e.g. `depth_integral` ->
            # NotImplementedError, models/ecosim/backend.py:737), i.e. make an unscoreable target
            # look ready. Passing a check by editing the data it inspects is the wrong direction.
            track = t.get("track")
            if track:
                warns.append(f"[G6] {name}: no `window`/`time`/`window_years`, but `track: {track}` "
                             f"-- off the scoring path, so this is not a broken live target. "
                             f"Decide which it is: a model INPUT the run is built from belongs in "
                             f"`prescribed_initialization:`, not `targets:` (scoring an input "
                             f"rewards the input); a genuine unfinished target needs BOTH a time "
                             f"reduction and a supported `reduce`.")
            else:
                errors.append(f"[G6] {name}: no `window`, `time` or `window_years` "
                              f"(no time reduction defined)")
        else:
            # Shape-check whichever range fields are present. Both are [lo, hi] with
            # lo <= hi; only `window` accepts the hi == -1 "to the end" sentinel
            # (`window_years` names absolute calendar years, where -1 is meaningless).
            if "window" in t:
                w = t["window"]
                if not (isinstance(w, list) and len(w) == 2) or (w[1] != -1 and w[0] > w[1]):
                    errors.append(f"[G6] {name}: window {w} invalid ([lo,hi], lo<=hi, or hi==-1)")
            if "window_years" in t:
                wy = t["window_years"]
                if not (isinstance(wy, list) and len(wy) == 2) or wy[0] > wy[1]:
                    errors.append(f"[G6] {name}: window_years {wy} invalid "
                                  f"([first_year, last_year], first<=last)")
        desc = str(t.get("description", "")).upper()
        if "PLACEHOLDER" in desc:
            warns.append(f"[G8] {name}: observed value is a PLACEHOLDER — ranking is not validated science")

        # G9/G10 — `denominator` (a ratio reduce's second column, e.g. PFLOTRAN's
        # `outflow_concentration`) is extracted right alongside `variable`
        # (tools/model_evaluate_case.py::evaluate_model_case), so a bad name here
        # KeyErrors at extraction exactly like a bad `variable` — but G2/G3 never
        # looked at it. Same registry, same two failure modes.
        den = t.get("denominator")
        if den:
            if den not in varset:
                errors.append(f"[G9] {name}: denominator '{den}' not in {cdl.name} "
                              f"(extraction would KeyError)")
            elif status.get(den, "active") == "inactive" and den not in activate:
                errors.append(f"[G10] {name}: denominator '{den}' is inactive-by-default and NOT in "
                              f"{args.model} spec.hist_activate — it will never be on the tape")

        how = t.get("reduce")
        series_field = REDUCE_REQUIRES_SERIES_FILE.get(how)
        if series_field:
            # G11 — the companion series file this reduce requires must actually
            # resolve to a readable, non-empty two-column numeric table (mirrors
            # exactly what the backend's own reduce does with it, e.g.
            # `PFLOTRANBackend._reduce_outflow_flux`'s `np.loadtxt`).
            series_val = t.get(series_field)
            if not series_val:
                errors.append(f"[G11] {name}: reduce '{how}' requires '{series_field}' "
                              f"(a path to a two-column observed series) but it is not set")
            else:
                series_path = Path(series_val)
                if not series_path.is_absolute():
                    series_path = REPO / series_path
                if not series_path.is_file():
                    errors.append(f"[G11] {name}: {series_field} {series_path} does not exist")
                else:
                    try:
                        import numpy as np
                        arr = np.loadtxt(series_path)
                        if arr.ndim != 2 or arr.shape[1] < 2 or arr.shape[0] < 1:
                            errors.append(f"[G11] {name}: {series_field} {series_path} is not a "
                                          f"readable >=1-row two-column numeric table (shape {arr.shape})")
                    except Exception as exc:
                        errors.append(f"[G11] {name}: {series_field} {series_path} failed to parse "
                                      f"as a numeric table ({exc})")
            # G12 — the SENTINEL CONVENTION: `observed` must be exactly the value
            # this reduce's `1.0 + <normalized error>` contract expects, or the
            # recovered metric silently means something else (no crash to flag it).
            want = REDUCE_SENTINEL_OBSERVED.get(how)
            if want is not None and t.get("observed") is not None and float(t["observed"]) != want:
                errors.append(f"[G12] {name}: reduce '{how}' requires the observed={want} SENTINEL "
                              f"(not a physical value) — got observed={t['observed']!r}, which "
                              f"silently changes what the recovered metric means")
        elif how is not None and how not in window_independent_reduces and "window" not in t:
            # G13 — reduce_target()'s model-agnostic time-reduce only applies `reduce`
            # INSIDE the `if "window" in target` branch; without a window this value
            # is silently ignored and the last time step is returned regardless,
            # whether `how` is a typo or a legitimate keyword just missing its window.
            errors.append(f"[G13] {name}: reduce='{how}' but no `window` — reduce_target() only "
                          f"applies `reduce` inside the window branch, so this is SILENTLY IGNORED "
                          f"and the target reduces to the last time step regardless")

    print(f"validated {len(targets)} targets against {cdl.name} "
          f"({len(varset)} registry vars, {sum(1 for v in status.values() if v=='inactive')} inactive; "
          f"spec.hist_activate={len(activate)})")
    for w in warns:
        print("  WARN  " + w)
    for e in errors:
        print("  ERROR " + e)
    if errors:
        print(f"\n✗ {len(errors)} error(s), {len(warns)} warning(s)")
        return 2
    if warns:
        print(f"\n⚠ {len(warns)} warning(s), 0 errors")
        return 1
    print("\n✓ targets valid")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
