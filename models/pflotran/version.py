"""PFLOTRAN version-association classes.

PFLOTRAN, like EcoSIM and unlike FATES, has no api-epoch / sci-tag scheme, so
it is versioned by git commit and the profile label is `pflotran-<short>`
(e.g. `pflotran-157a26f7`). `models/ecosim/version.py` is the reference shape.

TWO THINGS DIFFER FROM ECOSIM, and both come from real evidence on this
onboarding rather than from symmetry:

1.  PFLOTRAN *does* carry a semantic version, in `pflotran_constants.F90:15-17`
    (`PFLOTRAN_VERSION_MAJOR/MINOR/PATCH`), so the detector reads it alongside
    the commit. That matters here: the team's pinned commit
    `157a26f7` is `VERSION_MAJOR = 6` while upstream master has moved to 7 --
    a 523-commit, ~17-month, major-version gap in which 235 of 331 source files
    changed (`memory/dev_logs_adapterkitpflotran/20260731c`). A commit-equality
    check alone would report that as "just a different commit"; carrying the
    major version lets the classifier say how far apart they are.

2.  Consequently the tier rule is NOT flat. Same commit -> T1. Different commit
    but same major version -> T3 (rebuild), because PFLOTRAN's own tagging does
    not promise parameter-surface stability within a major. Different MAJOR
    version -> T3 as well, but flagged `distant`, which is the signal
    `A2MC_RAG_T3_AUTO_DISTANCE` exists to gate on: a major bump must never
    auto-rebuild silently.

A NOTE ON WHY THE VERSION BANNER IS NOT ENOUGH. A PFLOTRAN run log prints
`PFLOTRAN Development Version` whenever the compile-time `PFLOTRAN_RELEASE`
flag is false (declared `pflotran_constants.F90:14`, branched on at `:594`;
false in this tree and on master) and carries NO
commit hash. The commit is therefore NOT recoverable from run artifacts --
it has to come from the checkout, which is why `detect_from_checkout` is the
only detector offered and why the pinned commit had to be obtained from the
person who built the binary (`20260731c`).

Author: Jing Tao with Claude
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


# Anchor on the PFLOTRAN_ prefix: the same file also mentions PETSC_VERSION_MAJOR
# in preprocessor guards (pflotran_constants.F90:22-25), and a bare
# `VERSION_MAJOR` pattern would be one edit away from matching those instead.
_VERSION_RE = {
    "major": re.compile(r"PFLOTRAN_VERSION_MAJOR\s*=\s*(-?\d+)"),
    "minor": re.compile(r"PFLOTRAN_VERSION_MINOR\s*=\s*(-?\d+)"),
    "patch": re.compile(r"PFLOTRAN_VERSION_PATCH\s*=\s*(-?\d+)"),
}
_CONSTANTS_REL = Path("src/pflotran/pflotran_constants.F90")


# =============================================================================
# PFLOTRANVersion
# =============================================================================

@dataclass
class PFLOTRANVersion(ModelVersion):
    """Commit + semantic version for a PFLOTRAN checkout."""

    commit_sha: str = ""            # full 40-char sha
    commit_short: str = ""          # short hash used in the profile label
    version_major: Optional[int] = None
    version_minor: Optional[int] = None
    version_patch: Optional[int] = None
    detected_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    @property
    def label(self) -> str:
        return f"pflotran-{self.commit_short}" if self.commit_short else "pflotran-unknown"

    @property
    def semver(self) -> str:
        parts = [self.version_major, self.version_minor, self.version_patch]
        return ".".join(str(p) for p in parts if p is not None) or "unknown"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "commit_sha": self.commit_sha,
            "commit_short": self.commit_short,
            "version_major": self.version_major,
            "version_minor": self.version_minor,
            "version_patch": self.version_patch,
            "semver": self.semver,
            "detected_at": self.detected_at.isoformat(timespec="seconds"),
        }


# =============================================================================
# PFLOTRANVersionDetector
# =============================================================================

class PFLOTRANVersionDetector(ModelVersionDetector):
    """Reads commit + semantic version from a PFLOTRAN source checkout.

    A git worktree is supported: `.git` is a FILE there, not a directory, which
    is exactly how the pinned tree is materialised on this machine
    (`20260731c`), so the check must accept both.
    """

    def detect_from_checkout(self, checkout_path: Path) -> PFLOTRANVersion:
        checkout_path = Path(checkout_path)
        git_marker = checkout_path / ".git"
        if not git_marker.exists():          # dir (clone) OR file (worktree)
            raise FileNotFoundError(
                f"{checkout_path} does not look like a PFLOTRAN git checkout "
                f"(no .git). Point A2MC_MODEL_PATH at the PFLOTRAN source root."
            )
        try:
            sha = subprocess.check_output(
                ["git", "-C", str(checkout_path), "rev-parse", "HEAD"],
                text=True,
            ).strip()
        except (subprocess.CalledProcessError, FileNotFoundError) as e:
            raise FileNotFoundError(f"git rev-parse failed in {checkout_path}: {e}")

        major = minor = patch = None
        constants = checkout_path / _CONSTANTS_REL
        if constants.is_file():
            text = constants.read_text(errors="replace")
            m = _VERSION_RE["major"].search(text)
            n = _VERSION_RE["minor"].search(text)
            p = _VERSION_RE["patch"].search(text)
            major = int(m.group(1)) if m else None
            minor = int(n.group(1)) if n else None
            patch = int(p.group(1)) if p else None

        return PFLOTRANVersion(
            commit_sha=sha,
            commit_short=sha[:8],
            version_major=major,
            version_minor=minor,
            version_patch=patch,
        )


# =============================================================================
# PFLOTRANBumpTierClassifier
# =============================================================================

class PFLOTRANBumpTierClassifier(BumpTierClassifier):
    """Commit equality first, then major-version distance.

    Returns a plain `Tier` string so the orchestrator's existing drift policy
    applies unchanged. `is_distant()` is the extra signal: a MAJOR bump is the
    case that must never auto-rebuild, because a 6->7 move changed 71 % of the
    source tree (`20260731c`).
    """

    def classify(
        self,
        milestone_version: PFLOTRANVersion,
        current_version: PFLOTRANVersion,
    ) -> str:
        if milestone_version.commit_sha and (
            milestone_version.commit_sha == current_version.commit_sha
        ):
            return Tier.T1
        return Tier.T3

    @staticmethod
    def is_distant(
        milestone_version: PFLOTRANVersion,
        current_version: PFLOTRANVersion,
    ) -> bool:
        """True when the two checkouts differ in MAJOR version.

        Advisory, and deliberately conservative: unknown major versions count as
        distant, because "I could not read the version" is not evidence of
        closeness.
        """
        a, b = milestone_version.version_major, current_version.version_major
        if a is None or b is None:
            return True
        return a != b


# =============================================================================
# PFLOTRANMilestoneMetadata
# =============================================================================

@dataclass
class PFLOTRANMilestoneMetadata(MilestoneMetadata):
    """PFLOTRAN-specific `model_specific` block for rag/milestones.json.

    PFLOTRAN has NO parameter file in the FATES/EcoSIM sense: its calibration
    surface is the free-form input DECK, and part of that surface (mineral
    log-K, stoichiometry, molar volume/weight) lives in a separate
    thermodynamic DATABASE file. Both are recorded, because the curated seed's
    surface-area unit conversion reads the database
    (`reaction_mineral.F90:1054`) -- it is not optional context.
    """

    commit_built: str = ""
    version_major: Optional[int] = None
    wiki_subdir: str = ""
    param_file_format: str = "deck"       # free-form card deck, not nc/json
    deck_file: str = ""
    database_file: str = ""
    output_sample: str = ""

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "PFLOTRANMilestoneMetadata":
        return cls(
            commit_built=d.get("commit_built", ""),
            version_major=d.get("version_major"),
            wiki_subdir=d.get("wiki_subdir", ""),
            param_file_format=d.get("param_file_format", "deck"),
            deck_file=d.get("deck_file", ""),
            database_file=d.get("database_file", ""),
            output_sample=d.get("output_sample", ""),
        )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "commit_built": self.commit_built,
            "version_major": self.version_major,
            "wiki_subdir": self.wiki_subdir,
            "param_file_format": self.param_file_format,
            "deck_file": self.deck_file,
            "database_file": self.database_file,
            "output_sample": self.output_sample,
        }
