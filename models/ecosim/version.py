"""EcoSIM version-association classes.

EcoSIM has no api-epoch / sci-tag scheme like FATES. It is versioned purely by
git commit. So:
    - EcoSIMVersion carries the commit sha + short hash (+ detection time).
    - The milestone profile label is `ecosim-<short>` (e.g. `ecosim-2dea74d9`).
    - Bump tiers are coarse: same commit → T1 (reuse); any different commit →
      T3 (full rebuild). T2 (parameter-file-only delta within an epoch) has no
      EcoSIM analog yet — EcoSIM parameters live in per-site input NetCDFs, not
      a single default file, so there is no commit-independent "param sha" to
      diff. Revisit if/when EcoSIM ships a canonical default parameter file.

Mirrors the shape of the FATES reference (`tools/model_version.py`), adapted to
a single-component, commit-only model.
"""

from __future__ import annotations

import subprocess
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
# EcoSIMVersion
# =============================================================================

@dataclass
class EcoSIMVersion(ModelVersion):
    """Commit-based version structure for EcoSIM."""

    commit_sha: str = ""            # full 40-char sha
    commit_short: str = ""          # short hash used in the profile label
    detected_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    @property
    def label(self) -> str:
        # Milestone profile label. EcoSIM has no api epoch, so the short hash
        # is the stable identifier: e.g. "ecosim-2dea74d9".
        return f"ecosim-{self.commit_short}" if self.commit_short else "ecosim-unknown"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "commit_sha": self.commit_sha,
            "commit_short": self.commit_short,
            "detected_at": self.detected_at.isoformat(timespec="seconds"),
        }


# =============================================================================
# EcoSIMVersionDetector
# =============================================================================

class EcoSIMVersionDetector(ModelVersionDetector):
    """Reads EcoSIM's git commit from a source checkout."""

    def detect_from_checkout(self, checkout_path: Path) -> EcoSIMVersion:
        checkout_path = Path(checkout_path)
        if not (checkout_path / ".git").exists():
            raise FileNotFoundError(
                f"{checkout_path} does not look like an EcoSIM git checkout "
                f"(no .git/). Point A2MC_MODEL_PATH at the EcoSIM source root."
            )
        try:
            sha = subprocess.check_output(
                ["git", "-C", str(checkout_path), "rev-parse", "HEAD"],
                text=True,
            ).strip()
        except (subprocess.CalledProcessError, FileNotFoundError) as e:
            raise FileNotFoundError(f"git rev-parse failed in {checkout_path}: {e}")
        return EcoSIMVersion(commit_sha=sha, commit_short=sha[:8])


# =============================================================================
# EcoSIMBumpTierClassifier
# =============================================================================

class EcoSIMBumpTierClassifier(BumpTierClassifier):
    """Coarse commit-equality tiering: T1 if same commit, else T3.

    EcoSIM has no epoch/param-sha distinction yet (see module docstring), so
    the middle tier (T2) is not emitted. Any commit change is treated as a
    full-rebuild candidate.
    """

    def classify(
        self,
        milestone_version: EcoSIMVersion,
        current_version: EcoSIMVersion,
    ) -> str:
        if milestone_version.commit_sha and (
            milestone_version.commit_sha == current_version.commit_sha
        ):
            return Tier.T1
        return Tier.T3


# =============================================================================
# EcoSIMMilestoneMetadata
# =============================================================================

@dataclass
class EcoSIMMilestoneMetadata(MilestoneMetadata):
    """EcoSIM-specific `model_specific` block for rag/milestones.json entries.

    EcoSIM parameters are spread across per-site input NetCDFs rather than a
    single default file, so the metadata records the wiki subdir, the sample
    input files used to seed the RAG, and the sample output tape.
    """

    commit_built: str = ""
    wiki_subdir: str = ""
    param_file_format: str = "netcdf"     # EcoSIM ships .nc / .json / .cdl inputs
    input_files: list = field(default_factory=list)
    output_sample: str = ""

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "EcoSIMMilestoneMetadata":
        return cls(
            commit_built=d.get("commit_built", ""),
            wiki_subdir=d.get("wiki_subdir", ""),
            param_file_format=d.get("param_file_format", "netcdf"),
            input_files=list(d.get("input_files", [])),
            output_sample=d.get("output_sample", ""),
        )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "commit_built": self.commit_built,
            "wiki_subdir": self.wiki_subdir,
            "param_file_format": self.param_file_format,
            "input_files": list(self.input_files),
            "output_sample": self.output_sample,
        }
