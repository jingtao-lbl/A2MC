"""ATS version-association classes.

ATS is released as ``ats-X.Y.Z`` git tags on ``github.com/amanzi/ats`` and built as part
of Amanzi. A checkout is identified by its git commit + ``git describe`` (e.g.
``ats-1.7-dev-22-g42b0e940``). ``ats --print_version`` also prints the baked-in git details.

Provides the four version-association pieces the framework dispatches through
(see ``models/base.py``): ATSVersion, ATSVersionDetector, ATSBumpTierClassifier,
ATSMilestoneMetadata.
"""

from __future__ import annotations

import re
import subprocess
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional

from ..base import (
    BumpTierClassifier,
    MilestoneMetadata,
    ModelVersion,
    ModelVersionDetector,
    Tier,
)

# Parse a `git describe` like "ats-1.7-dev-22-g42b0e940" or "ats-1.6.0-3-gabc1234".
_DESCRIBE_RE = re.compile(
    r"^ats-(?P<major>\d+)\.(?P<minor>\d+)(?:\.(?P<patch>\d+))?"
    r"(?P<pre>-\w+)?(?:-(?P<distance>\d+)-g(?P<sha>[0-9a-f]+))?"
)


@dataclass(eq=True, frozen=True)
class ATSVersion(ModelVersion):
    """ATS version structure: git commit + parsed release tag."""

    commit_sha: str = ""
    commit_short: str = ""
    describe: str = ""
    major: Optional[int] = None
    minor: Optional[int] = None
    patch: Optional[int] = None
    dev_distance: Optional[int] = None
    detected_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat(timespec="seconds")
    )

    @property
    def label(self) -> str:
        # Commit-pinned milestone label (mirrors EcoSIM's "ecosim-{commit_short}").
        return f"ats-{self.commit_short}" if self.commit_short else "ats-unknown"

    @property
    def epoch(self) -> Optional[str]:
        """The X.Y release epoch, used for T2/T3 tier decisions."""
        if self.major is None or self.minor is None:
            return None
        return f"{self.major}.{self.minor}"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "commit_sha": self.commit_sha,
            "commit_short": self.commit_short,
            "describe": self.describe,
            "major": self.major,
            "minor": self.minor,
            "patch": self.patch,
            "dev_distance": self.dev_distance,
            "detected_at": self.detected_at,
        }

    @classmethod
    def from_describe(cls, describe: str, commit_sha: str = "") -> "ATSVersion":
        m = _DESCRIBE_RE.match(describe.strip())
        short = commit_sha[:8] if commit_sha else ""
        major = minor = patch = distance = None
        if m:
            major = int(m.group("major"))
            minor = int(m.group("minor"))
            patch = int(m.group("patch")) if m.group("patch") else None
            distance = int(m.group("distance")) if m.group("distance") else None
            if m.group("sha"):
                short = m.group("sha")
        return cls(
            commit_sha=commit_sha,
            commit_short=short,
            describe=describe.strip(),
            major=major,
            minor=minor,
            patch=patch,
            dev_distance=distance,
        )


class ATSVersionDetector(ModelVersionDetector):
    """Reads ATS git state from a source checkout."""

    def detect_from_checkout(self, checkout_path: Path) -> ATSVersion:
        checkout_path = Path(checkout_path)
        if not (checkout_path / ".git").exists() and not (checkout_path / "src").exists():
            raise FileNotFoundError(
                f"{checkout_path} does not look like an ATS checkout "
                f"(no .git or src/ directory)."
            )
        sha = self._git(checkout_path, "rev-parse", "HEAD")
        describe = self._git(checkout_path, "describe", "--tags", "--long", "--always")
        return ATSVersion.from_describe(describe or "", commit_sha=sha or "")

    @staticmethod
    def _git(path: Path, *args: str) -> str:
        try:
            out = subprocess.run(
                ["git", "-C", str(path), *args],
                capture_output=True, text=True, check=False,
            )
            return out.stdout.strip()
        except (OSError, subprocess.SubprocessError):
            return ""


class ATSBumpTierClassifier(BumpTierClassifier):
    """T1 = same commit; T2 = same X.Y epoch; T3 = different major (or unknown)."""

    def classify(
        self,
        milestone_version: ATSVersion,
        current_version: ATSVersion,
    ) -> str:
        if (
            milestone_version.commit_sha
            and milestone_version.commit_sha == current_version.commit_sha
        ):
            return Tier.T1
        me, ce = milestone_version.epoch, current_version.epoch
        if me is not None and me == ce:
            return Tier.T2
        if (
            milestone_version.major is not None
            and milestone_version.major == current_version.major
        ):
            return Tier.T2
        return Tier.T3


@dataclass
class ATSMilestoneMetadata(MilestoneMetadata):
    """Opaque ``model_specific`` block for an ATS milestone in rag/milestones.json."""

    ats_commit_built: str = ""
    ats_describe: str = ""
    amanzi_commit: str = ""
    wiki_subdir: str = ""
    param_file_format: str = "xml"

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "ATSMilestoneMetadata":
        return cls(
            ats_commit_built=d.get("ats_commit_built", ""),
            ats_describe=d.get("ats_describe", ""),
            amanzi_commit=d.get("amanzi_commit", ""),
            wiki_subdir=d.get("wiki_subdir", ""),
            param_file_format=d.get("param_file_format", "xml"),
        )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "ats_commit_built": self.ats_commit_built,
            "ats_describe": self.ats_describe,
            "amanzi_commit": self.amanzi_commit,
            "wiki_subdir": self.wiki_subdir,
            "param_file_format": self.param_file_format,
        }
