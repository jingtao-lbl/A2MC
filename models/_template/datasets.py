"""Template ModelDataset registry — copy + fill in for your model.

`TEMPLATE_DATASETS` is a dict keyed on version label that maps to a
`ModelDataset` instance per registered version of the model.

For FATES, the equivalent dict (will live at `models/fates/datasets.py` post-Step E)
holds entries for `api-31-0` and `api-43-1`, each pointing at:
    - The pinned wiki path(s)
    - The pinned parameter file
    - The pinned output CDL
    - The frozen per-milestone curated YAML
    - The per-profile RAG output paths

After copying this template:
    1. Rename `TEMPLATE_DATASETS` → `<YOURMODEL>_DATASETS`
    2. Add at least one entry for an initial version of your model
    3. Each adapter's __init__.py must call `register_dataset()` for each entry
       (see _template/__init__.py for the pattern)
"""

from __future__ import annotations

from pathlib import Path
from typing import Dict

from ..base import ModelDataset


# =============================================================================
# Registered datasets for this adapter
# =============================================================================
#
# TODO(adapter-kit): replace with real entries. Empty dict is intentional for
# the unfilled template — it lets the package import without listing a fake
# version. The first adapter-kit step that requires datasets is Step E (RAG
# build), at which point the user has at least one version of their model
# pinned and ready to register here.
#
# Example shape (FATES api-43-1):
#
#     TEMPLATE_DATASETS = {
#         "v1.0.0": ModelDataset(
#             model_name="_template",
#             version="v1.0.0",
#             wiki_paths=(
#                 Path("docs/_template-knowledge-base/_template-codebase-wiki-<sha>"),
#             ),
#             parameter_file=Path("docs/_template-knowledge-base/_template_params_info_<sha>.cdl"),
#             output_cdl=Path("docs/_template-knowledge-base/_template_output_info_<sha>.cdl"),
#             curated_yaml=Path("rag/data/curated_relationships__template-v1-0-0.yaml"),
#             vector_persist_dir=Path("rag/chroma_db/_template-v1-0-0"),
#             graph_path=Path("rag/graphs/_template-v1-0-0.json"),
#             metadata_path=Path("rag/metadata/_template-v1-0-0.json"),
#             description="Template model v1.0.0 — initial release",
#             upstream_url="https://github.com/<your-org>/<your-model>/tree/v1.0.0",
#             canonical=True,
#         ),
#     }

TEMPLATE_DATASETS: Dict[str, ModelDataset] = {}
