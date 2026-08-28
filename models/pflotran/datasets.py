"""PFLOTRAN ModelDataset registry.

One entry for the first PFLOTRAN milestone profile, `pflotran-157a26f7`, pinned
to the commit the miniLEO binary was actually built from.

WHY THIS COMMIT AND NOT MASTER. The pin is the team's build commit, not the
newest upstream one. The gap to master is 523 commits / ~17 months across a
MAJOR version boundary (6 -> 7), with 235 of 331 source files changed
(+45,338/-14,775, ~71 %). A master-pinned wiki would document different code
from the binary behind every miniLEO output, which is the one thing a
version-associated RAG exists to prevent. Full reasoning:
`memory/dev_logs_adapterkitpflotran/20260731c`.

PATH NOTES -- and PFLOTRAN differs structurally from FATES and EcoSIM here:

  - `parameter_file` is the free-form INPUT DECK (`pflotran.in`), not a NetCDF
    or JSON parameter file. `PFLOTRANParameterParser` addresses its cards by
    block path.
  - `output_cdl` is the real MASS-BALANCE FILE (`pflotran-mas.dat`). PFLOTRAN
    ships no NetCDF history tape, so there is no output CDL to generate; the
    authoritative output registry IS the tape the run produced. This follows
    the `onboard-model` rule "if the model ships a real history tape, read THAT"
    -- taken one step further, because here the tape is the only registry.
  - Both live OUTSIDE the repo, under the case directory, and are NOT tracked:
    the case bundle is 99 MB and belongs to the team's own repository
    (`github.com/Janewendo/minileo_pflotran`). They are present locally for the
    RAG build and parser runs. This is the same posture as EcoSIM's staged
    `Offline/` inputs.
  - The thermodynamic DATABASE is a second input surface that the curated seed
    genuinely depends on (the surface-area unit conversion reads molar weight
    and molar volume from it, `reaction_mineral.F90:1054`). `ModelDataset` has
    no field for a second input, so it is recorded in the milestone metadata
    (`PFLOTRANMilestoneMetadata.database_file`) rather than being dropped.

Author: Jing Tao with Claude
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Dict

from ..base import ModelDataset


# The case bundle is not in this repo. Allow an env override so a different
# machine (or Perlmutter) can point at its own copy without editing code --
# same escape hatch EcoSIM needed once the work moved off one laptop.
_DEFAULT_CASE_DIR = Path(
    os.environ.get(
        "A2MC_PFLOTRAN_CASE_DIR",
        # A machine-local fallback for the PI's own workstation layout. Set
        # A2MC_PFLOTRAN_CASE_DIR rather than relying on it.
        str(Path.home() / "Desktop/Work/Subsurface/PFLOTRAN_Case/scenario1_miniLEO"),
    )
)


def _reference_mas(case_dir: Path) -> Path:
    """Locate the reference mass-balance tape under a case directory.

    TWO LAYOUTS ARE REAL. PFLOTRAN writes its tape wherever the run was launched:
    the team's own repository (github.com/Janewendo/minileo_pflotran) has it in an
    ``output/`` SUBDIRECTORY beside the deck, the hand-copied bundle has it flat.
    An explicit ``A2MC_PFLOTRAN_REFERENCE_MAS`` wins over both.

    Probing matters because a missing tape does not fail: ``build_pflotran_rag``
    falls back to "only curated outputs become nodes" and reports a SUCCESSFUL
    build with a smaller graph. Returns the flat path when neither exists, so a
    consumer reports a concrete missing file rather than an empty value.
    """
    explicit = os.environ.get("A2MC_PFLOTRAN_REFERENCE_MAS", "")
    if explicit:
        return Path(explicit)
    flat = case_dir / "pflotran-mas.dat"
    nested = case_dir / "output" / "pflotran-mas.dat"
    return nested if (nested.is_file() and not flat.is_file()) else flat


PFLOTRAN_DATASETS: Dict[str, ModelDataset] = {
    "pflotran-157a26f7": ModelDataset(
        model_name="pflotran",
        version="pflotran-157a26f7",
        wiki_paths=(
            Path("docs/pflotran-knowledge-base/pflotran-codebase-wiki-157a26f7"),
        ),
        # The input deck IS the parameter surface for PFLOTRAN.
        parameter_file=_DEFAULT_CASE_DIR / "pflotran.in",
        # The mass-balance tape IS the output registry (no NetCDF history).
        output_cdl=_reference_mas(_DEFAULT_CASE_DIR),
        curated_yaml=Path("models/pflotran/curated_seed.yaml"),
        vector_persist_dir=Path("rag/chroma_db/pflotran-157a26f7"),
        graph_path=Path("rag/graphs/pflotran-157a26f7.json"),
        metadata_path=Path("rag/metadata/pflotran-157a26f7.json"),
        description=(
            "PFLOTRAN at commit 157a26f7 (2025-02-27, VERSION_MAJOR 6), the "
            "commit the miniLEO binary was built from. Second "
            "non-FATES adapter; miniLEO basalt-weathering lysimeter case."
        ),
        upstream_url="https://bitbucket.org/pflotran/pflotran/commits/157a26f7",
        canonical=False,   # FATES api-43-1 remains the canonical default
        legacy=False,
    ),
}
