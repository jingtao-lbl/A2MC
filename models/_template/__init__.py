"""Template adapter for A2MC. Copy this directory + fill in TODOs.

To onboard a new model:

    1. Copy this directory to `models/<yourmodel>/`:
           cp -r models/_template models/<yourmodel>

       (This is what `scripts/init_adapter.py --model <yourmodel>` does
       under the hood.)

    2. Rename the spec / backend / dataset class names from `Template*` to
       `<YourModel>*` throughout the new package.

    3. Replace every `# TODO(adapter-kit):` marker. Find them with:
           grep -rn "TODO(adapter-kit)" models/<yourmodel>/

    4. Run `python scripts/init_adapter.py --model <yourmodel>` to walk
       through the 14-step CLI flow per `docs/19_Adapter_Kit_Implementation_Plan.md`.

This template's package init registers a stub `_template` model with the
A2MC registry — useful for testing the framework's registration plumbing
without a real adapter, but NOT useful for actual calibration. Any attempt
to call backend methods raises `NotImplementedError` with a pointer back
here.

The stub registration uses the name `_template` so it never collides with a
real adapter.
"""

from __future__ import annotations

from .backend import TemplateBackend
from .datasets import TEMPLATE_DATASETS
from .spec import TEMPLATE_SPEC

from .. import registry

# Register the stub adapter with the A2MC registry. Real adapters do the same
# from their __init__.py, with their actual spec/backend/datasets.
registry.register_model(TemplateBackend())
for _ds in TEMPLATE_DATASETS.values():
    registry.register_dataset(_ds)

__all__ = [
    "TEMPLATE_SPEC",
    "TemplateBackend",
    "TEMPLATE_DATASETS",
]
