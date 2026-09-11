#!/usr/bin/env python
"""read_reduced.py -- resolve the CORRECT time-axis reduction for a model output variable.

WHY THIS EXISTS. A history tape carries variables with at least five different temporal semantics,
and one reduction does not fit them. Measured 2026-09-08: a diagnostic pull applied a single
`nanmean` over the last 365 records to six EcoSIM variables.

    NPP_pft                  a per-record C increment; its ANNUAL value is a SUM, so a mean is
                             comparable to nothing
    Uptk_NMin_CumYr_FLX_pft  a sawtooth that RESETS each year; the annual total is the value at
                             year END, so a mean returns roughly half of it and depends on where
                             the reset falls
    CAN_cumGPP_pft           monotone cumulative; a mean reports where the run was on average
                             rather than what it accumulated
    Root_CO2Relez_col        a rate; a mean is right
    Root_N_pft               a stock; a peak or window mean, never a sum
    CAN_GPP_pft              registered `default='inactive'` and, on the tape where it appeared,
                             carried the NPP values. Read as GPP from its name and units, it
                             produced a false alarm that a whole round had scored gross production
                             against a net observation.

Every fact needed to prevent that is in the model's own output registry, which is DERIVED FROM
SOURCE: `docs/<model>-knowledge-base/<model>_output_info_<commit>.cdl` carries `units`, `status`
and -- since 2026-09-08 -- `avgflag`, the history writer's time-aggregation flag.

THE DESIGN RULE: THE REGISTRY HOLDS SOURCE-TRUE FACTS; THE JUDGEMENT LIVES HERE.
`units`, `status` and `avgflag` are what `hist_addfld1d` says. The MAPPING from those to a
reduction is an inference, and it is kept in this one reviewable place rather than baked into the
KB as though the source had stated it.

AND IT REFUSES WHAT IT CANNOT CLASSIFY. `avgflag='A'` with mass units covers BOTH a per-record
increment (`NPP_pft`) and a stock (`Root_N_pft`), and nothing in the registry separates them. Rather
than guess, `classify()` returns AMBIGUOUS and `reduction_for()` raises. That converts the silent
wrong mean into a loud failure, which is the entire point. Resolve an ambiguous variable by either
(a) scoring it through the case's `targets.yaml` entry, which is authoritative and consulted first,
or (b) adding it to `KIND_OVERRIDES` below with the evidence that settles it.

USAGE

    from tools.read_reduced import registry, classify, reduction_for

    reg = registry("ecosim", commit="0366560a")
    classify(reg["Uptk_NMin_CumYr_FLX_pft"])       # -> Kind.CUMULATIVE_YEAR
    reduction_for("Uptk_NMin_CumYr_FLX_pft", reg)  # -> 'year_end'
    reduction_for("NPP_pft", reg)                  # -> raises: AMBIGUOUS, resolve via targets.yaml

    python tools/read_reduced.py --model ecosim --commit 0366560a NPP_pft Root_CO2Relez_col

Author: Jing Tao with Claude on Perlmutter
"""
from __future__ import annotations

import argparse
import enum
import pathlib
import re
import sys

REPO = pathlib.Path(__file__).resolve().parent.parent


class Kind(enum.Enum):
    """What a variable's time axis MEANS. The reduction follows from this, not from the name."""

    RATE = "rate"                        # per unit time; mean over the window, or x dt for a total
    INCREMENT = "increment"              # per-record contribution; SUM over the window
    CUMULATIVE_YEAR = "cumulative_year"  # running total that RESETS; value at each year's end
    CUMULATIVE_RUN = "cumulative_run"    # running total, monotone; difference between endpoints
    STOCK = "stock"                      # a state, not a flux; peak or window mean, never a sum
    AMBIGUOUS = "ambiguous"              # the registry cannot separate INCREMENT from STOCK


#: kind -> the reduction this module recommends.
REDUCTION = {
    Kind.RATE: "mean",
    Kind.INCREMENT: "sum",
    Kind.CUMULATIVE_YEAR: "year_end",
    Kind.CUMULATIVE_RUN: "endpoint_difference",
    Kind.STOCK: "peak_or_window_mean",
}

#: Units whose denominator carries time. Matched on the SUFFIX so `gC/m2/hr` is a rate and
#: `gC/m2` is not.
_RATE_UNITS = re.compile(r"/\s*(s|sec|second|h|hr|hour|d|day|yr|year)\s*$", re.I)

#: A name that declares its own reset period. EcoSIM writes `CumYr` for a within-year accumulator;
#: other models use their own token, which is why this is a per-model table rather than a constant.
_YEAR_RESET_TOKENS = {"ecosim": re.compile(r"CumYr", re.I)}

#: Hand-resolved AMBIGUOUS cases, each with the evidence that settled it. Nothing goes in here on
#: the strength of a name: a claim about a variable is verified the way a claim about a parameter
#: is ([[feedback_param_description_can_lie_verify_in_source]]).
KIND_OVERRIDES = {
    # `NPP_pft` is DELIBERATELY NOT OVERRIDDEN. It stays AMBIGUOUS so that a caller is forced to
    # the case's `targets.yaml`, which is authoritative for it.
    #
    # WITHDRAWN, same day it was written: an earlier entry here classified it INCREMENT with the
    # evidence "sum over the run = 622.6, against ECO_NPP_col = 598.2, so the per-record values ADD
    # to the run total". Both halves were wrong. `models/ecosim/backend.py:829-846` integrates this
    # field as a **RATE**: `sum(rate[year]) * step_hours` with `step_hours` defaulting to 24, so the
    # annual value is 24x a bare sum -- 17.62 versus the scorer's 422.99 on one case, which is
    # exactly the factor. And the comparison used as evidence is the one that source explicitly
    # forbids: *"do NOT diff the cumulative ECO_NPP_col -- its year-boundary diffs are not the
    # annual flux; NPP_pft integration matches obs"*. The agreement was a coincidence of scale.
    #
    # The registry's own `units = "gC/m2"` for this field is WRONG; the backend comment names it
    # `gC/m2/hr`. That is [[feedback_param_description_can_lie_verify_in_source]] reaching an OUTPUT
    # variable's units attribute, which is why `classify()` must never be trusted alone for a
    # variable the case scores.
    ("ecosim", "Root_N_pft"): (
        Kind.STOCK,
        "gN/m2 root nitrogen POOL. Summing it over 8,401 records is meaningless; it is a state "
        "variable read at a peak or over a window. Its trajectory rises and falls within a year."),
}


def registry(model: str, commit: str, repo: pathlib.Path = REPO) -> dict:
    """-> {varname: {units, long_name, status, avgflag, dimensions}} from the source-derived CDL.

    The CDL is the model's OWN registry and is generated by `scripts/extract_<model>_outputs.py
    --from-source`, which refuses to stamp a commit its checkout is not at. Reading it here rather
    than reading a sample tape is deliberate: a tape shows only what one run happened to activate,
    and can come from a different binary than the one under study.
    """
    kb = repo / "docs" / f"{model}-knowledge-base"
    path = kb / f"{model}_output_info_{commit}.cdl"
    if not path.exists():
        have = sorted(p.name for p in kb.glob(f"{model}_output_info_*.cdl")) if kb.is_dir() else []
        raise SystemExit(
            f"ERROR: no output registry at {path}.\n"
            f"  Registries present: {have or 'none'}\n"
            f"  Generate one with: python scripts/extract_{model}_outputs.py "
            f"--from-source $A2MC_MODEL_PATH --commit {commit} --output {path}")
    out, cur = {}, None
    for line in path.read_text().splitlines():
        m = re.match(r"\s*\w+\s+(\w+)\(([^)]*)\)\s*;", line)
        if m:
            cur = m.group(1)
            out[cur] = {"name": cur, "dimensions": [d.strip() for d in m.group(2).split(",")],
                        "units": "", "long_name": "", "status": "", "avgflag": ""}
            continue
        a = re.match(r'\s*:(\w+)\s*=\s*"(.*)"\s*;', line)
        if a and cur:
            out[cur][a.group(1)] = a.group(2)
    return out


def classify(entry: dict, model: str = "ecosim") -> Kind:
    """-> Kind, from the SOURCE-TRUE fields only. Never from the long_name's prose."""
    units = (entry.get("units") or "").strip()
    avgflag = (entry.get("avgflag") or "").strip().upper()
    name = entry.get("name") or ""

    if _RATE_UNITS.search(units):
        return Kind.RATE
    if avgflag == "I":
        tok = _YEAR_RESET_TOKENS.get(model)
        if tok and tok.search(name):
            return Kind.CUMULATIVE_YEAR
        return Kind.CUMULATIVE_RUN
    # avgflag 'A' with non-rate units: a per-record increment and a stock look identical here.
    return Kind.AMBIGUOUS


def reduction_for(var: str, reg: dict, model: str = "ecosim", targets: dict = None) -> str:
    """-> the reduction to apply. RAISES rather than guessing.

    `targets` is an optional {varname: reduce} map from the case's `validation/targets.yaml`. It is
    consulted FIRST and wins outright: a variable the case SCORES must be reduced the way the
    scorer reduces it, or a figure and its score disagree for a reason no reader can see.
    """
    if targets and var in targets:
        return targets[var]
    if var not in reg:
        raise KeyError(
            f"{var!r} is not in the output registry. Either the name is wrong or the registry is "
            f"from a different commit than the run. Do NOT fall back to reading the tape's own "
            f"attributes: that is what a registry exists to replace.")
    entry = reg[var]
    if (entry.get("status") or "").lower() == "inactive":
        print(f"  [warn] {var} is registered default='inactive': it is not written unless a run "
              f"names it in hist_fincl1, and a tape carrying it may be carrying something else. "
              f"Measured: CAN_GPP_pft carried the NPP_pft values.", file=sys.stderr)
    kind = classify(entry, model)
    if kind is Kind.AMBIGUOUS:
        ov = KIND_OVERRIDES.get((model, var))
        if ov is None:
            raise ValueError(
                f"{var!r} is AMBIGUOUS: avgflag={entry.get('avgflag')!r} with units "
                f"{entry.get('units')!r} covers BOTH a per-record increment and a stock, and the "
                f"registry does not separate them. Resolve it by scoring through the case's "
                f"targets.yaml `reduce:`, or add ('{model}', '{var}') to KIND_OVERRIDES in "
                f"tools/read_reduced.py WITH the evidence that settles it. Refusing to guess.")
        kind = ov[0]
    return REDUCTION[kind]


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("variables", nargs="*", help="variable names to resolve (default: all)")
    ap.add_argument("--model", default="ecosim")
    ap.add_argument("--commit", required=True, help="the commit the RUN's binary was built from")
    a = ap.parse_args()
    reg = registry(a.model, a.commit)
    names = a.variables or sorted(reg)
    print("%-30s %-12s %-8s %-18s %s" % ("variable", "units", "avgflag", "kind", "reduction"))
    for v in names:
        if v not in reg:
            print("%-30s %s" % (v, "NOT IN REGISTRY")); continue
        e = reg[v]
        kind = classify(e, a.model)
        try:
            red = reduction_for(v, reg, a.model)
        except ValueError:
            red = "REFUSED — resolve via targets.yaml or KIND_OVERRIDES"
        flag = "" if (e.get("status") or "") == "active" else "  [INACTIVE]"
        print("%-30s %-12s %-8s %-18s %s%s" % (v, e.get("units", "")[:12],
                                               e.get("avgflag", ""), kind.value, red, flag))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
