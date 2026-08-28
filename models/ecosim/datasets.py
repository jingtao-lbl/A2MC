"""EcoSIM ModelDataset registry.

One entry for the first EcoSIM milestone profile, `ecosim-2dea74d9`, pinned to
upstream commit 2dea74d9 (the commit the codebase wiki was audited against).

Path notes:
    - `output_cdl` is a committed, source-pinned artifact.
    - `parameter_file` points at the staged BioCON pft NetCDF under `Offline/`
      (gitignored). It is present locally for the RAG build + parser runs. A
      committed param CDL is a follow-up (the examples/ suite ships `.nc.cdl`
      companions; extracting one for BioCON is a later task).
    - `curated_yaml` is None until the curated seed is built (scope-doc tasks
      9-10, PI-in-the-loop).
    - The RAG output paths follow the per-profile convention (no clobbering of
      the FATES profiles).
"""

from __future__ import annotations

from pathlib import Path
from typing import Dict

from ..base import ModelDataset


ECOSIM_DATASETS: Dict[str, ModelDataset] = {
    "ecosim-2dea74d9": ModelDataset(
        model_name="ecosim",
        version="ecosim-2dea74d9",
        wiki_paths=(
            Path("docs/ecosim-knowledge-base/ecosim-codebase-wiki-2dea74d9"),
        ),
        parameter_file=Path(
            "Offline/EcoSIM_sample_files/input/ds_input__pft_test__ex1.nc"
        ),
        output_cdl=Path(
            "docs/ecosim-knowledge-base/ecosim_output_info_2dea74d9.cdl"
        ),
        curated_yaml=None,  # built later (scope-doc tasks 9-10)
        vector_persist_dir=Path("rag/chroma_db/ecosim-2dea74d9"),
        graph_path=Path("rag/graphs/ecosim-2dea74d9.json"),
        metadata_path=Path("rag/metadata/ecosim-2dea74d9.json"),
        description=(
            "EcoSIM at upstream commit 2dea74d9 (2026-04-23). First non-FATES "
            "adapter-kit dogfood; BioCON test1_ex1 sample case."
        ),
        upstream_url="https://github.com/jinyun1tang/EcoSIM/tree/2dea74d9",
        canonical=False,   # FATES api-43-1 remains the canonical default
        legacy=False,
    ),
}
