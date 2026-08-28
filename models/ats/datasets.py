"""ATS ModelDataset registry.

One entry for the first ATS milestone profile, `ats-42b0e940`, pinned to upstream ATS
commit `42b0e940` (`ats-1.7-dev-22-g42b0e940`) — the commit the codebase wiki was generated
against.

Path notes:
    - `wiki_paths` points at the committed, commit-pinned ATS codebase wiki.
    - `parameter_file` points at a real input deck fixture (the COMPASS single-column
      oakharbor case). ATS has no single canonical param file; a deck IS the parameter
      surface, so a representative deck stands in here for parser + RAG runs.
    - `output_cdl` points at the transect deck, which carries an `observations` block (the
      ATS output/target surface). ATS writes no NetCDF history tape, so there is no `.cdl`.
    - `curated_yaml` is None until the curated seed is built (onboard-model step 7).
    - RAG output paths follow the per-profile convention (no clobbering of the FATES/EcoSIM profiles).
"""

from __future__ import annotations

from pathlib import Path
from typing import Dict

from ..base import ModelDataset


ATS_DATASETS: Dict[str, ModelDataset] = {
    "ats-42b0e940": ModelDataset(
        model_name="ats",
        version="ats-42b0e940",
        wiki_paths=(
            Path("docs/ats-knowledge-base/ats-codebase-wiki-42b0e940"),
        ),
        parameter_file=Path(
            "models/ats/tests/fixtures/oakharbor_column.xml"
        ),
        output_cdl=Path(
            "models/ats/tests/fixtures/oakharbor_transect.xml"
        ),
        curated_yaml=None,  # built later (onboard-model step 7)
        vector_persist_dir=Path("rag/chroma_db/ats-42b0e940"),
        graph_path=Path("rag/graphs/ats-42b0e940.json"),
        metadata_path=Path("rag/metadata/ats-42b0e940.json"),
        description=(
            "ATS at upstream commit 42b0e940 (ats-1.7-dev-22-g42b0e940, wiki 2026-05-06). "
            "First hydrology-model adapter; standalone-ATS target with COMPASS oakharbor decks."
        ),
        upstream_url="https://github.com/amanzi/ats/tree/42b0e940",
        canonical=False,   # FATES api-43-1 remains the canonical default
        legacy=False,
    ),
}
