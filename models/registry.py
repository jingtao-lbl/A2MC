"""Adapter registry: register, look up, and resolve the active model.

Each adapter's package (`models/<name>/__init__.py`) calls `register_model()`
and `register_dataset()` at import time. Framework code calls
`get_model(name)`, `get_dataset(name, version)`, or `get_active_model()` to
retrieve them.

Active-model resolution reads three env vars (in priority order):
    - A2MC_RAG_ACTIVE     milestone profile name; set by orchestrator alignment
                          hook from A2MC_MODEL_PATH detection. Highest priority.
    - A2MC_MODEL_VERSION  explicit version override (rare; for dev/test)
    - A2MC_MODEL          model name (default: "fates")

If no version is specified, picks the canonical dataset (or the most-recently-
registered if no canonical flag is set).
"""

from __future__ import annotations

import os
from typing import Dict, List, Optional, Tuple

from .base import ModelBackend, ModelDataset


# =============================================================================
# Module-level state
# =============================================================================
#
# In-memory registries. Populated at import time by each adapter's __init__.py.

_MODELS: Dict[str, ModelBackend] = {}
_DATASETS: Dict[str, Dict[str, ModelDataset]] = {}  # {model_name: {version: dataset}}


# =============================================================================
# Registration (called by adapters at import time)
# =============================================================================

def register_model(backend: ModelBackend) -> None:
    """Register a `ModelBackend` instance. Called by each adapter's package init.

    Idempotent: re-registering the same model overwrites the previous
    registration (useful for hot-reload during development).
    """
    _MODELS[backend.spec.name] = backend


def register_dataset(dataset: ModelDataset) -> None:
    """Register a `ModelDataset`. One per (model_name, version) tuple.

    Idempotent: re-registering the same (name, version) overwrites the
    previous registration.
    """
    _DATASETS.setdefault(dataset.model_name, {})[dataset.version] = dataset


# =============================================================================
# Lookup
# =============================================================================

def get_model(name: str) -> ModelBackend:
    """Return the registered `ModelBackend` for `name`.

    Raises `ValueError` if no adapter is registered under that name. The
    error message names the registered models so the user knows what's
    available.
    """
    if name not in _MODELS:
        raise ValueError(
            f"Unknown model: {name!r}. "
            f"Registered: {sorted(_MODELS.keys())!r}. "
            f"Did you import the model's package (e.g. `import models.fates`)?"
        )
    return _MODELS[name]


def get_dataset(model_name: str, version: str) -> ModelDataset:
    """Return the registered `ModelDataset` for (model_name, version)."""
    versions = _DATASETS.get(model_name, {})
    if version not in versions:
        available = sorted(versions.keys())
        raise ValueError(
            f"Unknown version {version!r} for model {model_name!r}. "
            f"Available: {available!r}"
        )
    return versions[version]


# The model a run uses when A2MC_MODEL is unset. FATES is A2MC's built-in path, and the FATES
# site configs rely on this default rather than setting A2MC_MODEL themselves.
DEFAULT_MODEL = "fates"


def active_model_name() -> str:
    """Return the active model's name: `$A2MC_MODEL`, else `DEFAULT_MODEL`.

    The one place the default lives. `get_active_model()` and the model-layer knowledge-store
    resolver (`tools/model_knowledge_store.py`) both read it, so they cannot disagree about
    which model an unset `A2MC_MODEL` means. Needs no adapter registered, unlike
    `get_active_model()`.
    """
    return os.environ.get("A2MC_MODEL", DEFAULT_MODEL)


def get_active_model() -> Tuple[ModelBackend, ModelDataset]:
    """Resolve `(backend, dataset)` from environment variables.

    Reads:
        A2MC_RAG_ACTIVE     Highest priority. Set by the orchestrator
                            alignment hook from A2MC_MODEL_PATH detection.
        A2MC_MODEL_VERSION  Explicit override. Rare (mostly for dev/test).
        A2MC_MODEL          Model name. Default: 'fates' (`DEFAULT_MODEL`).

    Falls back to the canonical dataset (or most-recently-registered) if no
    version is specified.

    Raises `ValueError` if the model or version isn't registered.
    """
    model_name = active_model_name()

    if model_name not in _MODELS:
        raise ValueError(
            f"Unknown model: {model_name!r}. "
            f"Registered: {sorted(_MODELS.keys())!r}. "
            f"Did you import the model's package?"
        )
    backend = _MODELS[model_name]

    # Version resolution: A2MC_RAG_ACTIVE > A2MC_MODEL_VERSION > canonical
    version = (
        os.environ.get("A2MC_RAG_ACTIVE")
        or os.environ.get("A2MC_MODEL_VERSION")
    )

    if version is None:
        versions = _DATASETS.get(model_name, {})
        if not versions:
            raise ValueError(
                f"No datasets registered for model {model_name!r}. "
                f"Did you import the model's datasets module?"
            )
        canonical = [v for v, ds in versions.items() if ds.canonical]
        version = canonical[0] if canonical else list(versions.keys())[-1]

    if version not in _DATASETS.get(model_name, {}):
        available = sorted(_DATASETS.get(model_name, {}).keys())
        raise ValueError(
            f"Unknown version {version!r} for model {model_name!r}. "
            f"Available: {available!r}. "
            f"(Resolved from "
            f"{'A2MC_RAG_ACTIVE' if os.environ.get('A2MC_RAG_ACTIVE') else 'A2MC_MODEL_VERSION'}.)"
        )

    return backend, _DATASETS[model_name][version]


# =============================================================================
# Listing
# =============================================================================

def list_models() -> List[str]:
    """Return registered model names, sorted."""
    return sorted(_MODELS.keys())


def list_datasets(model_name: Optional[str] = None) -> Dict[str, List[str]]:
    """Return `{model_name: [version, ...]}` for all (or one) model."""
    if model_name is None:
        return {m: sorted(versions.keys()) for m, versions in _DATASETS.items()}
    return {model_name: sorted(_DATASETS.get(model_name, {}).keys())}
