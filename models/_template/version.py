"""Template version-association classes — copy + fill in for your model.

Each adapter ships:
    - A ModelVersion subclass (the dataclass that detector populates)
    - A ModelVersionDetector subclass (reads source state from a checkout)
    - A BumpTierClassifier subclass (decides T1/T2/T3 from version distance)
    - A MilestoneMetadata subclass (rag/milestones.json schema v2 opaque block)

For FATES (the reference adapter), see `tools/model_version.py` for the
existing `ELMFATESVersion` etc. — those will move to `models/fates/version.py`
during Step E generalization. The shape there is what to mirror for new adapters.

After copying this template:
    1. Rename `Template*` → `<YourModel>*`
    2. Replace each `# TODO(adapter-kit):` marker
    3. Update spec.py to reference the renamed classes
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict

from ..base import (
    BumpTierClassifier,
    MilestoneMetadata,
    ModelVersion,
    ModelVersionDetector,
    Tier,
)


# =============================================================================
# TemplateVersion
# =============================================================================

@dataclass
class TemplateVersion(ModelVersion):
    """Per-adapter version structure.

    TODO(adapter-kit): add fields appropriate to your model's versioning scheme.
    Common patterns:
        - git: commit_sha, commit_short, describe, nearest_tag
        - semver: major, minor, patch, prerelease
        - date: release_date
        - submodule: separate ComponentVersion per coupled component
    """

    # TODO(adapter-kit): replace with your model's version fields.
    raw_label: str = ""               # placeholder; e.g., "v1.0.0" or "abc1234"
    detected_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    @property
    def label(self) -> str:
        # TODO(adapter-kit): construct the milestone profile label from version
        # fields. FATES example: f"api-{major}-{minor}" from the api epoch.
        return self.raw_label

    def to_dict(self) -> Dict[str, Any]:
        return {
            "raw_label": self.raw_label,
            "detected_at": self.detected_at.isoformat(timespec="seconds"),
        }


# =============================================================================
# TemplateVersionDetector
# =============================================================================

class TemplateVersionDetector(ModelVersionDetector):
    """Reads model version from a checkout path.

    For git-based models: shell out to `git -C <path>` for SHA + describe.
    For Python packages: read `__version__` or `pyproject.toml`.
    For NetCDF datasets: read a global attribute.

    TODO(adapter-kit): implement detect_from_checkout() for your model.
    """

    def detect_from_checkout(self, checkout_path: Path) -> TemplateVersion:
        # TODO(adapter-kit): replace with real detection.
        #
        # FATES reference (see tools/model_version.py):
        #     - git -C <path>/components/elm/ rev-parse HEAD
        #     - git -C <path>/components/elm/src/external_models/fates/ describe --tags --long
        #     - parse api.X.Y from describe
        #     - construct ELMFATESVersion
        #
        # Stub raises so callers fail fast if they instantiate the detector
        # without filling this in.
        raise NotImplementedError(
            "TemplateVersionDetector.detect_from_checkout is a stub. "
            "Fill it in for your model. See models/_template/version.py "
            "and the FATES reference (tools/model_version.py)."
        )


# =============================================================================
# TemplateBumpTierClassifier
# =============================================================================

class TemplateBumpTierClassifier(BumpTierClassifier):
    """Decides T1/T2/T3 from milestone vs current version distance.

    TODO(adapter-kit): implement classify() for your model. Common rules:
        - T1: same commit / version → metadata refresh only
        - T2: same epoch (api.X.Y / major.minor) but different patch / commit
              → parameter-file delta possible; rebuild graph layer 2 only
        - T3: different epoch → full rebuild needed
    """

    def classify(
        self,
        milestone_version: TemplateVersion,
        current_version: TemplateVersion,
    ) -> str:
        # TODO(adapter-kit): replace with real classification.
        # FATES reference: see tools/rag_selector.classify_bump_tier.
        raise NotImplementedError(
            "TemplateBumpTierClassifier.classify is a stub. "
            "Fill it in for your model. Return one of Tier.T1, Tier.T2, Tier.T3."
        )


# =============================================================================
# TemplateMilestoneMetadata
# =============================================================================

@dataclass
class TemplateMilestoneMetadata(MilestoneMetadata):
    """Per-adapter opaque block of `rag/milestones.json` schema v2 entries.

    Schema v2 (per memory/dev_logs_adapterkit/20260428b_*) has a `model_specific`
    dict per milestone. Each adapter declares its schema via this class.

    TODO(adapter-kit): add fields specific to your model's milestone metadata
    (e.g., commit hashes for coupled components, parameter-file format flag,
    coupling-host pinned commit, etc.).

    For FATES: fates_commit_built, fates_tag_built, fates_param_file_format,
    elm_commit_built, elm_wiki_subdir, fates_wiki_subdir, covers_sci_tags.
    """

    # TODO(adapter-kit): replace with your model-specific milestone fields.
    raw: Dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "TemplateMilestoneMetadata":
        return cls(raw=dict(d))

    def to_dict(self) -> Dict[str, Any]:
        return dict(self.raw)
