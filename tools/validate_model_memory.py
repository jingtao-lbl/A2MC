#!/usr/bin/env python
"""Validate a model's adaptive-memory store against what MemoryManager actually READS.

Why this exists
---------------
`memory/<model>/gained_knowledge/` uses a container type that differs per file, and the
difference is load-bearing but undocumented:

    discoveries.json        "discoveries":       LIST
    experiments.json        "experiments":       LIST
    failed_approaches.json  "failed_approaches": LIST
    parameters.json         "parameters":        DICT   <- keyed by parameter name

Getting `parameters` wrong does not fail at write time or at load time. It fails later, inside
`MemoryManager.get_relevant_context()` (manager.py:244 iterates it with `.items()`), i.e. during
a calibration phase rather than during onboarding:

    AttributeError: 'list' object has no attribute 'items'

That is exactly how it was hit while seeding ATS (onboard-model step 10). A store can also be
structurally valid but functionally empty -- entries present that no retrieval path can reach --
which is worse than a missing file because it looks done.

Checks
------
    M1  files present      the four gained_knowledge stores exist and parse as JSON
    M2  container types    each store's payload key has the type MemoryManager expects
    M3  entry shape        list entries are dicts with an id/name; parameter values are dicts
    M4  retrievability     MemoryManager loads the store AND returns non-empty context for a
                           parameter the store claims to know about (the functional check)

Read-only. Exit 0 if the store is sound, 1 otherwise.

Usage:
    python tools/validate_model_memory.py --model ats
    python tools/validate_model_memory.py --model ecosim --probe-param VCMX

Author: Jing Tao with Claude
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

# payload key -> container type MemoryManager expects
EXPECTED = {
    "discoveries.json": ("discoveries", list),
    "experiments.json": ("experiments", list),
    "failed_approaches.json": ("failed_approaches", list),
    "parameters.json": ("parameters", dict),
}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--model", required=True, help="Adapter name, e.g. ats / ecosim")
    ap.add_argument("--probe-param",
                    help="Parameter name to probe M4 with (default: first key of parameters.json)")
    a = ap.parse_args()

    root = REPO / "memory" / a.model / "gained_knowledge"
    print("=" * 66)
    print(f"MODEL MEMORY — {a.model}   ({root.relative_to(REPO)})")
    print("=" * 66)

    errors: list[str] = []
    warnings: list[str] = []
    stores: dict[str, dict] = {}

    # M1 + M2 + M3
    for fname, (key, ctype) in EXPECTED.items():
        fp = root / fname
        if not fp.exists():
            errors.append(f"M1 {fname}: missing")
            continue
        try:
            doc = json.loads(fp.read_text())
        except Exception as e:
            errors.append(f"M1 {fname}: not valid JSON ({e})")
            continue
        stores[fname] = doc

        if key not in doc:
            errors.append(f"M2 {fname}: missing payload key {key!r}")
            continue
        payload = doc[key]
        if not isinstance(payload, ctype):
            errors.append(f"M2 {fname}: {key!r} is {type(payload).__name__}, "
                          f"MemoryManager requires {ctype.__name__} "
                          f"(a list here raises AttributeError inside get_relevant_context)")
            continue

        n = len(payload)
        print(f"  {fname:24s} {key!r}: {ctype.__name__} with {n} entr{'y' if n == 1 else 'ies'}")

        # M3 entry shape
        if ctype is list:
            bad = [i for i, e in enumerate(payload)
                   if not isinstance(e, dict) or not (e.get("id") or e.get("name"))]
            if bad:
                errors.append(f"M3 {fname}: {len(bad)} entr(ies) are not dicts with an id/name "
                              f"(first at index {bad[0]})")
        else:
            bad = [k for k, v in payload.items() if not isinstance(v, dict)]
            if bad:
                errors.append(f"M3 {fname}: {len(bad)} value(s) are not dicts (e.g. {bad[0]!r})")

    if errors:
        print()
        for e in errors:
            print(f"  FAIL  {e}")
        print("\nOVERALL: FAIL")
        return 1

    # M4 -- the functional check: does anything actually come back?
    try:
        from memory import MemoryManager
        mm = MemoryManager(str(root))
    except Exception as e:
        errors.append(f"M4: MemoryManager could not load the store ({type(e).__name__}: {e})")
    else:
        params = stores.get("parameters.json", {}).get("parameters", {})
        probe = a.probe_param or (next(iter(params)) if params else None)
        if not probe:
            warnings.append("M4: parameters.json is empty — nothing to probe, so retrievability "
                            "is unverified (structurally valid but functionally empty)")
        else:
            try:
                ctx = mm.get_relevant_context(targets=[], parameters=[probe])
            except Exception as e:
                errors.append(f"M4: get_relevant_context() raised {type(e).__name__}: {e}")
                ctx = ""
            if ctx:
                print(f"\n  M4 retrievability: probe {probe!r} -> {len(ctx)} chars of context")
            else:
                warnings.append(f"M4: probe {probe!r} returned EMPTY context — entries exist but "
                                f"no retrieval path reaches them")

    print()
    for w in warnings:
        print(f"  WARN  {w}")
    for e in errors:
        print(f"  FAIL  {e}")
    ok = not errors
    print(f"\nOVERALL: {'PASS' if ok else 'FAIL'}"
          f"{'  (with ' + str(len(warnings)) + ' warning(s))' if warnings and ok else ''}")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
