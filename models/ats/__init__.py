"""ATS adapter for A2MC — the first surface-subsurface hydrology model.

Registers the ATS backend + dataset(s) with the A2MC registry at import time, following
the same pattern as `models/ecosim/__init__.py`. Framework code reaches ATS via
`models.registry.get_model("ats")` / `get_active_model()` (with `A2MC_MODEL=ats`), never by
importing this package directly.

Status (v0.1, standalone-ATS target): parameter/output parsing (XML ParameterList in,
observation surface out), parameter-file writing, and version-association are implemented;
the backend's run-execution methods are functional-minimal (see backend.py). The curated seed
and RAG index are follow-ups (onboard-model steps 7-9). See
`memory/dev_logs_adapterkit/` (20260727*) and `docs/ats-knowledge-base/`.
"""

from __future__ import annotations

from .backend import ATSBackend
from .datasets import ATS_DATASETS
from .spec import ATS_SPEC

from .. import registry

registry.register_model(ATSBackend())
for _ds in ATS_DATASETS.values():
    registry.register_dataset(_ds)

__all__ = [
    "ATS_SPEC",
    "ATSBackend",
    "ATS_DATASETS",
]
