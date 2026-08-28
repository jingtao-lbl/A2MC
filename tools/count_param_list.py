#!/usr/bin/env python3
"""Print the number of sampled parameters (Morris/Sobol columns) in a parameter list.

The **authoritative** source for `A2MC_N_PARAMS` — derive it from the list, never hardcode it, so it
stays in sync as the list changes (and the ensemble *size* is then computed by scheme in
`calculate_ensemble_size()`, which is what varies for Morris trajectories vs Sobol vs LHS).

Handles the explicit-column CSV in BOTH dialects -- canonical `name,...` and FATES legacy
`fates_name,...` (via `load_param_spec`) -- and the legacy shorthand `.txt`.

Never returns a silent 0: an unrecognised file raises rather than reporting "no parameters",
because this feeds `A2MC_N_PARAMS` and a zero there sizes an empty ensemble..

    python tools/count_param_list.py <param_list_file>
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


# First column of an explicit-column CSV header, in either dialect. Testing ONLY for
# `fates_name` returned 0 for EcoSIM's 82-row canonical list -- exit 0, no warning, a silent
# zero straight into A2MC_N_PARAMS (recorded 20260802f, fixed 20260803b).
_CSV_FIRST_COLUMNS = ("fates_name", "name")


def _is_new_format(path):
    with open(path) as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            return "," in line and line.split(",")[0].strip() in _CSV_FIRST_COLUMNS
    return False


def count_params(path):
    if _is_new_format(path):
        from tools.param_spec import load_param_spec
        try:
            return len(load_param_spec(path))
        except ValueError as exc:
            if "is not an integer" not in str(exc):
                raise
            # A NAMED grouping axis (a PFLOTRAN mineral, a microbial guild). param_spec's axis is
            # integer-valued; the adapter loader handles a string id. Counting needs neither, so
            # dispatch rather than fail -- this feeds A2MC_N_PARAMS.
            from scripts.create_adapter_parameter_sample import parse_pft_param_list
            names, _, _ = parse_pft_param_list(path)
            return len(names)
    # legacy .txt: count numbered data rows (No<TAB>fates_name<TAB>shorthand<TAB>...)
    n = 0
    for line in open(path):
        line = line.strip()
        if not line or line.startswith(("#", "=")):
            continue
        first = line.split("\t")[0] if "\t" in line else line.split()[0] if line.split() else ""
        try:
            int(first)
            n += 1
        except ValueError:
            pass
    return n


# Suffixes marking a param list kept for provenance but no longer in use. A retired list must
# never be picked as "the active one" — on 2026-07-28 two lists were renamed to `_NotUsed` /
# `_Old`, and a `sorted(glob(...))[0]` in two test modules silently began resolving to the
# RETIRED para168 file. The tests kept passing their structural checks against the wrong list
# and only their hardcoded count gave it away.
_RETIRED_MARKERS = ("_old", "_notused", "_superseded", "_deprecated", "_archive")


def resolve_param_list(search_dir, pattern="*.csv"):
    """Return the ACTIVE parameter list in `search_dir`.

    Resolution order, so callers agree with the running system:
      1. `$A2MC_PARAM_LIST_FILE` when set and readable — the same variable the site config
         exports and every runtime path already uses. This is the authority.
      2. otherwise the newest non-retired match in `search_dir`, by `paraNNN` when the names
         carry one (so para169 beats para99), else lexicographic.

    Raises FileNotFoundError when nothing qualifies, rather than returning a retired list.
    """
    import os
    import re

    env = os.environ.get("A2MC_PARAM_LIST_FILE")
    if env and Path(env).is_file():
        return Path(env)

    cands = [p for p in Path(search_dir).glob(pattern)
             if not any(m in p.stem.lower() for m in _RETIRED_MARKERS)]
    if not cands:
        raise FileNotFoundError(
            f"no active parameter list in {search_dir} matching {pattern!r} "
            f"(retired markers: {', '.join(_RETIRED_MARKERS)})")

    def _key(p):
        m = re.search(r"para(\d+)", p.stem, re.I)
        return (1, int(m.group(1))) if m else (0, 0)

    return sorted(cands, key=lambda p: (_key(p), p.name))[-1]


if __name__ == "__main__":
    if len(sys.argv) != 2:
        sys.exit("usage: count_param_list.py <param_list_file>")
    print(count_params(sys.argv[1]))
