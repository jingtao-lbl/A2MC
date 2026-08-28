#!/usr/bin/env python3
"""
extract_pflotran_outputs.py — Build pflotran_output_info_<commit>.json, the
committed, version-pinned registry of PFLOTRAN's mass-balance output surface.

PFLOTRAN's parallel of `extract_ecosim_outputs.py` / `extract_elm_outputs.py`
(gap matrix, dev log 20260802c). It differs from both in FORMAT and in what it
can honestly claim, for reasons that are properties of the model:

WHY JSON AND NOT A CDL
----------------------
EcoSIM and ELM write NetCDF history tapes, so their registry is a CDL that
`rag/output_parser.py:FATESOutputParser` reads. PFLOTRAN ships no NetCDF
history: its calibration surface is a fixed-width mass-balance text file
(`*-mas.dat`, see `models/pflotran/output_parser.py`). Emitting a CDL here would
assert a format the model does not have. The registry is therefore JSON holding
`PFLOTRANOutputVariable`'s own decomposition — the same fields the parser
produces, so the artifact is exactly what a consumer would have computed.

READ THIS BEFORE TRUSTING THE CONTENTS — IT IS DECK-SCOPED, NOT MODEL-SCOPED
---------------------------------------------------------------------------
EcoSIM learned the tape-vs-source lesson the expensive way: a history TAPE only
reflects what was ACTIVE in one run, and the BioCON reference tape carried 52
phantom variables absent from the pinned commit while missing 117 real fields
(dev log 20260713e). That is why `extract_ecosim_outputs.py` grew a
`--from-source` mode, which is authoritative.

**PFLOTRAN HAS NO EQUIVALENT SOURCE MODE, and this is not an omission.** Its
mass-balance columns are not a static registry like EcoSIM's `hist_addfld1d/2d`
calls; they are ASSEMBLED AT RUNTIME from deck-defined entities — one group per
COUPLER (`east`, `top_vent`, `top_recharge` are names the miniLEO deck chose)
and one column per reactive-transport SPECIES the deck declares
(`output_observation.F90`). Scanning source would yield the column TEMPLATE, not
the column SET.

So this registry is: **the output surface of the deck it was extracted from, at
the pinned commit.** A different deck at the same commit has different columns.
That is recorded in the artifact's own header, not just here, because the value
of a registry is destroyed by a reader who over-trusts it.

WHY IT IS WORTH COMMITTING ANYWAY
---------------------------------
`scripts/build_pflotran_rag.py` reads the reference tape live to create its
output nodes, and the tape is a 99 MB team bundle
(github.com/Janewendo/minileo_pflotran) that lives outside this repo. When it is
absent the RAG build does not fail — it falls back to "only curated outputs
become nodes" and reports a SUCCESSFUL build with all 332 column nodes silently
missing (measured 2026-08-06, when this repo's Perlmutter clone had no PFLOTRAN
data at all). A committed registry makes the build reproducible on any machine
and makes the output surface diffable across commits.

Usage
-----
    python scripts/extract_pflotran_outputs.py \\
        --from-tape "$A2MC_PFLOTRAN_REFERENCE_MAS" \\
        --output docs/pflotran-knowledge-base/pflotran_output_info_157a26f7.json \\
        --commit 157a26f7 --deck-name scenario1_miniLEO

With no arguments it resolves the tape the same way the rest of the adapter does
(`A2MC_PFLOTRAN_REFERENCE_MAS`, else the case dir, probing both layouts).

Exit codes: 0 wrote the registry, 1 input/path error.

Author: Jing Tao with Claude
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Dict

REPO = Path(__file__).resolve().parent.parent
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from models.pflotran.output_parser import PFLOTRANOutputParser  # noqa: E402

DEFAULT_COMMIT = "157a26f7"
REGISTRY_SCHEMA_VERSION = 1


def default_registry_path(commit: str = DEFAULT_COMMIT) -> Path:
    """Where the committed registry lives, by convention."""
    return REPO / "docs/pflotran-knowledge-base" / f"pflotran_output_info_{commit}.json"


def resolve_tape() -> Path:
    """The reference tape, resolved the way the rest of the adapter resolves it."""
    from models.pflotran.datasets import PFLOTRAN_DATASETS
    return Path(PFLOTRAN_DATASETS[f"pflotran-{DEFAULT_COMMIT}"].output_cdl)


def build_registry(tape: Path, commit: str, deck_name: str) -> Dict[str, Any]:
    """Inventory a `*-mas.dat` header into the registry structure.

    Stores each column's CONSTRUCTOR fields (which a consumer reconstructs the
    dataclass from) alongside its DERIVED properties. The derived values are
    redundant by construction, deliberately: they make the artifact readable and
    diffable on its own, and they let a test assert that today's parser still
    derives what was recorded — so parser drift shows up as a registry diff
    instead of as silently different RAG chunk text.
    """
    inventory = PFLOTRANOutputParser().parse(tape)

    columns = []
    for name, ov in inventory.items():
        columns.append({
            # constructor fields — a consumer rebuilds PFLOTRANOutputVariable from these
            "name": ov.name,
            "variable": ov.variable,
            "units": ov.units,
            "scope": ov.scope,
            "family": ov.family,
            "column_index": ov.column_index,
            # derived properties — redundant, and checked against the parser by tests
            "is_rate": ov.is_rate,
            "is_cumulative": ov.is_cumulative,
            "positive_is_into_domain": ov.positive_is_into_domain,
            "dimension_level": ov.dimension_level,
            "category": ov.category,
            "long_name": ov.long_name,
        })
    columns.sort(key=lambda c: c["column_index"])

    families: Dict[str, int] = {}
    for c in columns:
        families[c["family"]] = families.get(c["family"], 0) + 1
    couplers = sorted({c["scope"] for c in columns if c["family"] == "coupler"})

    return {
        "registry_schema_version": REGISTRY_SCHEMA_VERSION,
        "model": "pflotran",
        "model_commit": commit,
        "generated": datetime.now().strftime("%Y-%m-%d"),
        "source_tape": tape.name,
        "source_deck": deck_name,
        "scope_warning": (
            "DECK-SCOPED, NOT MODEL-SCOPED. PFLOTRAN's mass-balance columns are "
            "assembled at runtime from deck-defined couplers and the deck's "
            "reactive-transport species list (output_observation.F90), so this is the "
            f"output surface of the '{deck_name}' deck at commit {commit} — a different "
            "deck at the same commit has different columns. There is no source-derived "
            "mode for this model: scanning source yields the column TEMPLATE, not the "
            "column SET."
        ),
        "format_note": (
            "The tape is NOT a CSV: the header is comma-separated and quoted, the data "
            "rows are fixed-width with zero separators. Cumulative vs rate is decided by "
            "the UNITS BRACKET, not the column name, so the FULL header is the key."
        ),
        "n_columns": len(columns),
        "family_counts": families,
        "couplers": couplers,
        "columns": columns,
    }


def load_registry(path: Path) -> Dict[str, Any]:
    """Read a committed registry back into ``{full_header: PFLOTRANOutputVariable}``.

    The counterpart of :func:`build_registry` — this is what lets a consumer
    (`scripts/build_pflotran_rag.py`) work without the 99 MB case bundle. Only the
    CONSTRUCTOR fields are used; every derived property is recomputed by the
    dataclass, so a stale derived value in the file can never reach a consumer.
    """
    from models.pflotran.output_parser import PFLOTRANOutputVariable
    data = json.loads(Path(path).read_text())
    out = {}
    for c in data["columns"]:
        out[c["name"]] = PFLOTRANOutputVariable(
            name=c["name"], variable=c["variable"], units=c["units"],
            scope=c["scope"], family=c["family"], column_index=c["column_index"])
    return out


def parse_args() -> argparse.Namespace:
    ap = argparse.ArgumentParser(
        description="Extract PFLOTRAN's mass-balance output registry to JSON",
        formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--from-tape", type=Path, default=None, metavar="MAS",
                    help="reference *-mas.dat (default: the adapter's resolved tape)")
    ap.add_argument("--output", type=Path, default=None,
                    help=f"output JSON (default: {default_registry_path().relative_to(REPO)})")
    ap.add_argument("--commit", default=DEFAULT_COMMIT,
                    help=f"PFLOTRAN source commit for the pin (default: {DEFAULT_COMMIT})")
    ap.add_argument("--deck-name", default="scenario1_miniLEO",
                    help="the deck this tape came from — recorded in the artifact, "
                         "because the registry is deck-scoped (default: scenario1_miniLEO)")
    return ap.parse_args()


def main() -> int:
    args = parse_args()
    tape = args.from_tape or resolve_tape()
    out_path = args.output or default_registry_path(args.commit)

    if not tape.is_file():
        print(f"ERROR: reference tape not found: {tape}", file=sys.stderr)
        print("       Set A2MC_PFLOTRAN_REFERENCE_MAS (or A2MC_PFLOTRAN_CASE_DIR), "
              "or pass --from-tape.", file=sys.stderr)
        return 1

    print(f"Reading PFLOTRAN mass-balance header: {tape}")
    registry = build_registry(tape, args.commit, args.deck_name)
    print(f"  {registry['n_columns']} columns  "
          f"({', '.join(f'{k} {v}' for k, v in sorted(registry['family_counts'].items()))})")
    print(f"  couplers: {', '.join(registry['couplers']) or '(none)'}")
    print(f"Writing {out_path}")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(registry, indent=2) + "\n")
    print(f"Done. Registry is DECK-SCOPED (deck: {args.deck_name}, commit: {args.commit}).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
