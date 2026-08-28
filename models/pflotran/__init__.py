"""PFLOTRAN adapter for A2MC — the second non-FATES adapter.

Registers the PFLOTRAN backend + dataset(s) with the A2MC registry at import
time, following `models/ecosim/__init__.py`. Framework code reaches PFLOTRAN via
`models.registry.get_model("pflotran")` / `get_active_model()` (with
`A2MC_MODEL=pflotran`), never by importing this package directly.

Status: parsing (deck + mass-balance), output extraction, case-status,
version-association and RAG-facing metadata are implemented. The EXECUTION
methods on the backend remain deferred until a binary exists at the pinned
commit `157a26f7` (see backend.py and README.md).
"""

from __future__ import annotations

from .backend import PFLOTRANBackend
from .datasets import PFLOTRAN_DATASETS
from .spec import PFLOTRAN_SPEC

from .. import registry

registry.register_model(PFLOTRANBackend())
for _ds in PFLOTRAN_DATASETS.values():
    registry.register_dataset(_ds)

__all__ = [
    "PFLOTRAN_SPEC",
    "PFLOTRANBackend",
    "PFLOTRAN_DATASETS",
]
