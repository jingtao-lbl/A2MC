#!/usr/bin/env python
"""Compare each model adapter's ModelSpec field population against its siblings.

Why this exists
---------------
A ModelSpec field left empty means one of two things, and NOTHING in the spec
distinguishes them:

    "not applicable to this model"    <- correct
    "nobody filled it in"             <- a silently dead feature

Every A2MC feature that dispatches through a spec field degrades to a NO-OP when its
field is empty, and the no-ops announce themselves in language that reads as a pass:

    $ python tools/model_check_input_compat.py --model ats --checkout ... --param-file ...
    N/A - ATS declares no input-reader compat contract
          (spec.input_reader_sources / input_read_pattern empty); nothing to check.

ATS is the worked example. Three of its fields sat empty while the features dispatching
through them silently did nothing: `hist_activate` (the G3 inactive-output check in
validate_model_targets.py) and `input_reader_sources` / `input_read_pattern` (the
Footgun-7 input-vs-binary compat gate -- the gate whose absence once cost EcoSIM a wasted
submit and a mid-read abort).

**They were not overlooked.** Each carried a written rationale -- in a PROSE COMMENT
directly above the field, since v0.1. The rationales were reasonable; one has since been
shown wrong about its mechanism and one is correct only for a design the outputs repair
overturns. What was missing was never the decision. It was that no tool could READ the
decision, so nothing could tell a considered N/A from an oversight, and nothing forced
either to say when it stops being true. See `memory/dev_logs_adapterkitats/20260801k`
(and its correction banner) plus `20260801l`.

The rule
--------
A field that ANY adapter populates is a convention. An adapter that leaves that field
empty must DECLARE why, in `spec.spec_na = {field: reason}`. A declared gap passes and
is printed; an UNDECLARED gap fails.

A declaration is NOT a claim that the field is correctly empty -- it is a claim that
someone decided and can be held to it. So a reason should state its **expiry condition**
(what would falsify it), and may freely record that it is unvalidated. `tests/
test_adapter_parity.py` requires the expiry marker.

`spec_na = {"*": reason}` is a blanket declaration for an adapter still mid-onboarding.
It passes, but every field it excuses is printed, so a half-built adapter cannot
masquerade as a complete one.

Only fields whose ModelSpec DEFAULT is empty participate. Fields with a real default
(`source_extensions`, `routine_decl_patterns`, `module_file_pattern`, `grouping_axis`,
`milestone_label_format`) are never "empty" and carry no parity signal, and the three
mandatory identity fields have no default at all. The participating set is derived from
the dataclass, so it grows automatically as ModelSpec does.

Checks
------
    P1  undeclared gap      field populated by a sibling, empty here, no spec_na entry
    P2  stale declaration   spec_na names a field that IS populated here
    P3  bogus declaration   spec_na names something that is not a ModelSpec field

Read-only. Exit 0 if every in-scope adapter is clean, 1 otherwise.

Usage:
    python tools/validate_adapter_parity.py                  # gate on every adapter
    python tools/validate_adapter_parity.py --model ats      # gate on ats only
    python tools/validate_adapter_parity.py --include-template

Author: Jing Tao with Claude
"""
from __future__ import annotations

import argparse
import importlib
import sys
from dataclasses import MISSING, fields
from pathlib import Path
from typing import Dict, List, Tuple

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from models.base import ModelSpec  # noqa: E402

# Not model adapters. `surrogate` declares its own SurrogateSpec (a learned artifact
# ABOUT a model, not a model); `_template` is the onboarding scaffold and is
# deliberately empty everywhere, so it is opt-in via --include-template.
NOT_ADAPTERS = {"surrogate"}

BLANKET = "*"


# =============================================================================
# Discovery
# =============================================================================

def _default_of(f) -> object:
    """Return a field's default value, or MISSING if it is mandatory."""
    if f.default is not MISSING:
        return f.default
    if f.default_factory is not MISSING:      # type: ignore[misc]
        return f.default_factory()            # type: ignore[misc]
    return MISSING


def parity_fields() -> List[str]:
    """ModelSpec fields whose default is EMPTY -- the ones where "unset" is a real,
    observable state and therefore carries parity signal. Excludes `spec_na` itself."""
    out = []
    for f in fields(ModelSpec):
        if f.name == "spec_na":
            continue
        dflt = _default_of(f)
        if dflt is MISSING:      # mandatory (name, display_name, param_name_regex)
            continue
        if dflt:                 # has a real default -- never observably "empty"
            continue
        out.append(f.name)
    return out


def discover_specs(include_template: bool) -> Dict[str, ModelSpec]:
    """Import every `models/<name>/spec.py` and collect its ModelSpec instance.

    Discovery is by DIRECTORY, not by the runtime registry, on purpose: an adapter
    mid-onboarding has a spec long before it has a backend to register (PFLOTRAN
    today), and those are exactly the adapters whose gaps matter most.
    """
    specs: Dict[str, ModelSpec] = {}
    for pkg_dir in sorted((REPO / "models").iterdir()):
        if not pkg_dir.is_dir() or not (pkg_dir / "spec.py").exists():
            continue
        name = pkg_dir.name
        if name in NOT_ADAPTERS or name == "__pycache__":
            continue
        if name.startswith("_") and not include_template:
            continue
        mod = importlib.import_module(f"models.{name}.spec")
        found = [v for v in vars(mod).values() if isinstance(v, ModelSpec)]
        if not found:
            print(f"  WARN  models/{name}/spec.py declares no ModelSpec instance; skipped")
            continue
        if len(found) > 1:
            print(f"  WARN  models/{name}/spec.py declares {len(found)} ModelSpec "
                  f"instances; using the first ({found[0].name!r})")
        specs[found[0].name] = found[0]
    return specs


# =============================================================================
# Comparison
# =============================================================================

def analyze(specs: Dict[str, ModelSpec], pfields: List[str]):
    """Return (populated_by, findings) where populated_by maps field -> set of adapters,
    and findings maps adapter -> list of (check, field, detail)."""
    populated_by: Dict[str, List[str]] = {
        fld: [m for m, s in specs.items() if getattr(s, fld)] for fld in pfields
    }

    valid_names = {f.name for f in fields(ModelSpec)}
    findings: Dict[str, List[Tuple[str, str, str]]] = {m: [] for m in specs}
    excused: Dict[str, List[Tuple[str, str]]] = {m: [] for m in specs}
    blanket_hits: Dict[str, List[str]] = {}
    blanket_reason: Dict[str, str] = {}

    for model, spec in specs.items():
        na = dict(getattr(spec, "spec_na", {}) or {})
        blanket = na.pop(BLANKET, None)
        if blanket is not None:
            blanket_reason[model] = blanket

        # P3 -- a declaration that names nothing real (a typo silences nothing, but it
        # also silences nothing it was MEANT to, which is the dangerous half).
        for key in na:
            if key not in valid_names:
                findings[model].append(
                    ("P3", key, "spec_na names a field that does not exist on ModelSpec"))

        for fld in pfields:
            mine = bool(getattr(spec, fld))
            others = [m for m in populated_by[fld] if m != model]

            if mine:
                # P2 -- a declaration that has been overtaken by the field being filled.
                if fld in na:
                    findings[model].append(
                        ("P2", fld, f"declared not-applicable but IS populated "
                                    f"(stale reason: {na[fld]!r})"))
                continue

            if not others:
                continue  # nobody populates it -- not a convention, no signal

            peers = ", ".join(sorted(others))
            if fld in na:
                excused[model].append((fld, na[fld]))
            elif blanket is not None:
                blanket_hits.setdefault(model, []).append(fld)
            else:
                findings[model].append(
                    ("P1", fld, f"empty here, populated by {peers}"))

    return populated_by, findings, excused, blanket_hits, blanket_reason


# =============================================================================
# Report
# =============================================================================

MARKS = {"pop": "*", "empty": ".", "na": "NA", "blanket": "~"}


def _one_line(reason: str, limit: int = 96) -> str:
    """First sentence of a reason, clipped. The full text lives in the spec, which is
    where someone deciding whether the declaration still holds should be reading."""
    text = " ".join(reason.split())
    head = text.split(". ")[0].rstrip(".")
    return head if len(head) <= limit else head[:limit - 1].rstrip() + "…"


def print_matrix(specs: Dict[str, ModelSpec], pfields: List[str],
                 populated_by: Dict[str, List[str]]) -> None:
    models = list(specs)
    width = max(len(f) for f in pfields) + 2
    colw = max(max((len(m) for m in models), default=6), 6) + 2

    print(f"\n  FIELD POPULATION   ('{MARKS['pop']}' populated  '{MARKS['empty']}' empty  "
          f"'{MARKS['na']}' declared n/a  '{MARKS['blanket']}' blanket-declared)\n")
    print("  " + " " * width + "".join(m.ljust(colw) for m in models))
    for fld in pfields:
        if not populated_by[fld]:
            continue  # nobody populates it -- no convention exists, so nothing to show
        row = "  " + fld.ljust(width)
        for m in models:
            spec = specs[m]
            if getattr(spec, fld):
                mark = MARKS["pop"]
            else:
                na = getattr(spec, "spec_na", {}) or {}
                if fld in na:
                    mark = MARKS["na"]
                elif BLANKET in na:
                    mark = MARKS["blanket"]
                else:
                    mark = MARKS["empty"]
            row += mark.ljust(colw)
        print(row)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--model", action="append", default=None,
                    help="Scope the EXIT CODE to this adapter (repeatable). "
                         "All adapters are still compared and reported.")
    ap.add_argument("--include-template", action="store_true",
                    help="Include models/_template/ in the comparison (off by default: "
                         "the scaffold is empty everywhere by design)")
    a = ap.parse_args()

    print("=" * 78)
    print("ADAPTER SPEC PARITY")
    print("=" * 78)

    specs = discover_specs(a.include_template)
    if len(specs) < 2:
        print(f"\n  Only {len(specs)} adapter spec found — parity needs at least two "
              f"to compare against. Nothing to check.")
        return 0

    pfields = parity_fields()
    print(f"\n  adapters: {', '.join(specs)}")
    print(f"  fields compared: {len(pfields)} "
          f"(ModelSpec fields whose default is empty)")

    populated_by, findings, excused, blanket_hits, blanket_reason = analyze(specs, pfields)
    print_matrix(specs, pfields, populated_by)

    scope = a.model or list(specs)
    unknown = [m for m in scope if m not in specs]
    if unknown:
        print(f"\n  FAIL  unknown adapter(s) in --model: {', '.join(unknown)}")
        return 1

    n_fail = 0
    for model in specs:
        rows = findings[model]
        exc = excused[model]
        blank = blanket_hits.get(model, [])
        gated = model in scope
        if not rows and not exc and not blank:
            print(f"\n  {model}: parity clean" + ("" if gated else "  (not gated)"))
            continue

        print(f"\n  {model}:" + ("" if gated else "  (reported only, not gated)"))
        for fld, why in exc:
            print(f"    ok    {fld:28s} {_one_line(why)}")
        if blank:
            # Print the blanket reason ONCE, then the fields it excuses. Repeating the
            # reason per field buries the list, and the list is the point: it is what
            # keeps a half-built adapter from reading as a complete one.
            print(f"    ok    BLANKET declaration excuses {len(blank)} field(s) — "
                  f"{_one_line(blanket_reason[model])}")
            for i in range(0, len(blank), 3):
                print(f"            {', '.join(blank[i:i + 3])}")
        for check, fld, detail in rows:
            label = "FAIL" if gated else "warn"
            print(f"    {label}  {check} {fld:26s} {detail}")
        if rows and gated:
            n_fail += len(rows)

    print()
    if n_fail:
        print(f"OVERALL: FAIL — {n_fail} undeclared/stale spec gap(s) in scope "
              f"({', '.join(scope)}).")
        print("Fix by populating the field, or declare it in spec.spec_na with the "
              "reason it is empty.")
        return 1
    print(f"OVERALL: PASS — every gap in scope ({', '.join(scope)}) is declared.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
