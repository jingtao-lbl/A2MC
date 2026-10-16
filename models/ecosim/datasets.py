"""EcoSIM ModelDataset registry.

Two entries. `ecosim-cb243228` (active since 2026-10-15) is pinned to the binary EcoSIM_Lusignan R2
runs, the fork branch `fix/r2-plant-balance`. `ecosim-2dea74d9` is the first EcoSIM milestone,
pinned to upstream commit 2dea74d9, now legacy and frozen with its own copy of the curated seed.

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

The cb243228 re-anchor and the defects behind the dated notes above: `memory/dev_logs_adapterkit/20261015a_The_EcoSIM_Knowledge_Base_Moves_To_The_Binary_R2_Runs.md`.
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
        legacy=True,       # superseded by ecosim-cb243228 on 2026-10-15
    ),
    "ecosim-cb243228": ModelDataset(
        model_name="ecosim",
        version="ecosim-cb243228",
        wiki_paths=(
            Path("docs/ecosim-knowledge-base/ecosim-codebase-wiki-cb243228"),
        ),
        parameter_file=Path(
            "docs/ecosim-knowledge-base/param_surfaces_cb243228/ecosim_pftpar_20260915.nc"
        ),
        output_cdl=Path(
            "docs/ecosim-knowledge-base/ecosim_output_info_cb243228.cdl"
        ),
        curated_yaml=Path("models/ecosim/curated_seed.yaml"),
        vector_persist_dir=Path("rag/chroma_db/ecosim-cb243228"),
        graph_path=Path("rag/graphs/ecosim-cb243228.json"),
        metadata_path=Path("rag/metadata/ecosim-cb243228.json"),
        description=(
            "EcoSIM at cb243228 (jingtao-lbl/EcoSIM fix/r2-plant-balance = upstream-merged "
            "09eb674a + 2 plant mass-balance fixes), the binary EcoSIM_Lusignan R2 runs."
        ),
        upstream_url="https://github.com/jingtao-lbl/EcoSIM/tree/cb2432285b3b31a40461fc1ab7cb74a3f5ed94e1",
        canonical=False,
        legacy=False,
    ),
}
