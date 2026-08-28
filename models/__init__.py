"""A2MC adapter framework — model-agnostic contract types and registry.

This package defines the contract every model adapter must implement for A2MC
to drive it. Three core types per `docs/17_Multi_Model_Adapter_Architecture_Plan.md` §5:

    - ModelSpec     — static, immutable metadata describing a model
    - ModelBackend  — executable interface; one implementation per model
    - ModelDataset  — versioned data bundle (one per model version)

Plus support for validators (V1, V2, V4, V5 per Doc 19 §6.5) and version
association (per `memory/dev_logs_adapterkit/20260428b_Version_Association_Adaptation.md`):

    - ModelVersionDetector  — abstract base; each adapter detects its own version
    - BumpTierClassifier    — abstract base; each adapter classifies T1/T2/T3
    - MilestoneMetadata     — abstract base; each adapter declares its milestone schema

The framework code (orchestrator, validators, RAG, etc.) NEVER imports a specific
model's classes. It calls `models.registry.get_model("fates")` or
`models.registry.get_active_model()` and operates through the returned
ModelSpec / ModelBackend / ModelDataset triple.

The bundled `_template/` is a fill-in-the-blanks skeleton that adapter-kit users
copy + customize to onboard a new model. See `docs/19_Adapter_Kit_Implementation_Plan.md`
for the full pipeline.
"""

from __future__ import annotations

from .base import (
    BumpTierClassifier,
    MilestoneMetadata,
    ModelBackend,
    ModelDataset,
    ModelSpec,
    ModelVersion,
    ModelVersionDetector,
    Tier,
)

from . import registry

__all__ = [
    "BumpTierClassifier",
    "MilestoneMetadata",
    "ModelBackend",
    "ModelDataset",
    "ModelSpec",
    "ModelVersion",
    "ModelVersionDetector",
    "Tier",
    "registry",
]
