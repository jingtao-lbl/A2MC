"""EcoSIM adapter for A2MC — the first non-FATES adapter.

Registers the EcoSIM backend + dataset(s) with the A2MC registry at import time,
following the same pattern as `models/_template/__init__.py`. Framework code
reaches EcoSIM via `models.registry.get_model("ecosim")` /
`get_active_model()` (with `A2MC_MODEL=ecosim`), never by importing this package
directly.

Status: parsing + version-association + RAG-facing metadata are implemented;
the execution methods on the backend are deferred (see backend.py). Built as the
adapter-kit end-to-end dogfood — see memory/dev_logs_adapterkit/ (20260707*).
"""

from __future__ import annotations

from .backend import EcoSIMBackend
from .datasets import ECOSIM_DATASETS
from .spec import ECOSIM_SPEC

from .. import registry

registry.register_model(EcoSIMBackend())
for _ds in ECOSIM_DATASETS.values():
    registry.register_dataset(_ds)

__all__ = [
    "ECOSIM_SPEC",
    "EcoSIMBackend",
    "ECOSIM_DATASETS",
]
