"""SurrogateSpec — the declaration seam for a learned emulator.

A surrogate is NOT a model adapter. It is a learned artifact *about* a model,
bound to a specific (model version, parameter list, base parameter file,
bounds, scoring convention) tuple. Change any element of that tuple and the
artifact is invalid, exactly as a RAG profile is invalid against the wrong
source commit.

The spec exists because two very different consumers share this machinery
(docs/41 section 6.1):

  offline_search    the A2MC calibration surrogate. Emulates calibration-target
                    outputs from calibration parameters. Used between rounds to
                    steer the search. Bar: good enough to rank and to rule out.

  online_inference  a surrogate that replaces a process model inside a coupled
                    runtime, in frozen-weights inference, so its prediction is
                    consumed step by step rather than reviewed. Bar: high
                    pointwise accuracy and a large speedup. This is a DOWNSTREAM
                    use case, not the calibration loop's.

Hard-coding either would strand the other, so use_mode is a declared field and
the acceptance battery keys off it.

Author: Jing Tao with Claude
"""

from __future__ import annotations

import hashlib
import json
import warnings
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Tuple

# Transforms applied to a target BEFORE fitting and inverted after predicting.
# Prefer a transform over a soft physics penalty wherever it can carry the
# constraint structurally: a transform enforces admissibility under ANY fitted
# weights, a penalty only discourages violation on average (docs/41 section 4.1).
VALID_TRANSFORMS = ("identity", "log", "logit")

VALID_USE_MODES = ("offline_search", "online_inference")

# The tier axis. S0-S3 here are SURROGATE TIERS -- what is emulated -- and are
# UNRELATED to the S0-S6 STAGE labels in docs/42 (the Bayesian-optimization plan),
# which happen to share the letters. They no longer share a FILE: docs/42 stage S2
# once delivered `models/surrogate/acquisition.py` into this package, and was moved
# to `tools/bayesian_optimization/acquisition.py` on 2026-08-27 (PI) because acquisition is search, not
# emulation. So "S2" inside this package is always the tier.
#
# TWO tuples on purpose, because one was a check that could not fail.
#   VALID_TIERS       the ROADMAP -- every tier the design admits.
#   IMPLEMENTED_TIERS the REGISTRY -- every tier with a class behind it today.
# Validating against the roadmap let `tier="S3"` construct cleanly and fail much
# later at `load()`, which reads like a constraint and is not
# ([[feedback_a_check_that_cannot_fail]]). Construction validates against the
# REGISTRY; the roadmap is kept so the error can say what is planned and what it
# would take to enable it.
VALID_TIERS = ("S0", "S1", "S2", "S3")

# Gated ascent (docs/41 section 4, restated in tiers.py): a tier may not be built
# until the tier below has FAILED a WRITTEN acceptance test. So this tuple grows
# by recording a failure, never by wanting a feature.
IMPLEMENTED_TIERS = ("S0", "S1", "S2", "S3")


# =============================================================================
# Provenance — what this artifact is bound to
# =============================================================================

def _finite(x: Any) -> bool:
    """True when x is a real number and neither NaN nor an infinity."""
    try:
        f = float(x)
    except (TypeError, ValueError):
        return False
    return f == f and f not in (float("inf"), float("-inf"))


@dataclass(frozen=True)
class Provenance:
    """The tuple a trained surrogate is valid against.

    Every field here can silently invalidate a surrogate if it changes. The
    scoring convention is the easiest to overlook: a change in how targets are
    reduced (a calendar convention, an aggregation window) means any artifact
    trained under the previous convention scores against a different objective
    than the one now in force.

    ``created`` is passed in rather than stamped from the clock so that building
    the same artifact from the same inputs is reproducible.
    """

    model: str                      # physics model emulated, by its model-registry name
    model_commit: str = ""          # source commit of that model
    param_list_hash: str = ""       # hash of the parameter list (names + bounds)
    base_param_file_hash: str = ""  # hash of the base parameter file
    scoring_convention: str = ""    # e.g. "reduction-convention-v2"
    training_ensemble_id: str = ""  # which ensemble produced (X, Y)
    a2mc_version: str = ""
    created: str = ""               # ISO date, caller-supplied

    def mismatches(self, other: "Provenance") -> List[str]:
        """Field names that differ and are populated on BOTH sides.

        An empty string means "not recorded", which we treat as unknown rather
        than as a mismatch: refusing to load an artifact because a field was
        never filled in would make the check unusable on early artifacts. The
        cost of that leniency is that an unstamped artifact is not protected,
        which is why ``require_stamped`` exists.
        """
        out: List[str] = []
        for k, v in asdict(self).items():
            w = getattr(other, k)
            if v and w and v != w:
                out.append(k)
        return out

    def unstamped_fields(self) -> List[str]:
        return [k for k, v in asdict(self).items() if not v]


# =============================================================================
# Targets and inputs
# =============================================================================

@dataclass(frozen=True)
class TargetSpec:
    """One calibration target the surrogate predicts.

    ``lower``/``upper`` are the acceptance band used by reachability and
    equifinality questions ("is this configuration in the target box?"). They
    are NOT the training objective; the surrogate regresses the raw reduced
    value and the band is applied afterwards, so that changing the band does not
    require refitting.
    """

    name: str
    observed: Optional[float] = None
    lower: Optional[float] = None
    upper: Optional[float] = None
    transform: str = "identity"

    def __post_init__(self) -> None:
        if self.transform not in VALID_TRANSFORMS:
            raise ValueError(
                f"target {self.name!r}: transform {self.transform!r} not in {VALID_TRANSFORMS}")
        if (self.lower is not None and self.upper is not None
                and self.lower > self.upper):
            raise ValueError(f"target {self.name!r}: lower {self.lower} > upper {self.upper}")

    def in_band(self, value: float) -> bool:
        if self.lower is not None and value < self.lower:
            return False
        if self.upper is not None and value > self.upper:
            return False
        return True


# =============================================================================
# SurrogateSpec
# =============================================================================

@dataclass(frozen=True)
class SurrogateSpec:
    """Static description of what a surrogate maps, and what it is bound to."""

    name: str
    use_mode: str
    tier: str

    # Ordered input parameter names. Order IS the X column order; a reordering
    # silently permutes the design matrix, so it is validated on load.
    input_names: Tuple[str, ...] = ()
    input_lower: Tuple[float, ...] = ()
    input_upper: Tuple[float, ...] = ()

    # Ordered outputs. Order IS the Y column order.
    targets: Tuple[TargetSpec, ...] = ()

    provenance: Provenance = field(default_factory=lambda: Provenance(model=""))

    notes: str = ""

    def __post_init__(self) -> None:
        if self.use_mode not in VALID_USE_MODES:
            raise ValueError(f"use_mode {self.use_mode!r} not in {VALID_USE_MODES}")
        if self.tier not in VALID_TIERS:
            raise ValueError(f"tier {self.tier!r} not in {VALID_TIERS}")
        if self.tier not in IMPLEMENTED_TIERS:
            raise ValueError(
                f"tier {self.tier!r} is on the ROADMAP ({VALID_TIERS}) but has no "
                f"implementation; built tiers are {IMPLEMENTED_TIERS}. Tiers are "
                f"gated: a tier may not be built until the tier below it has "
                f"FAILED a written acceptance test "
                f"and that failure is on record (docs/41 section 4). If you have "
                f"that record, add the class in tiers.py and this tier to "
                f"IMPLEMENTED_TIERS in the same commit.")
        n = len(self.input_names)
        if len(self.input_lower) != n or len(self.input_upper) != n:
            raise ValueError(
                f"{self.name}: input_names/lower/upper length mismatch "
                f"({n}/{len(self.input_lower)}/{len(self.input_upper)})")
        for nm, lo, hi in zip(self.input_names, self.input_lower, self.input_upper):
            if lo > hi:
                raise ValueError(f"{self.name}: input {nm!r} lower {lo} > upper {hi}")
        if len(set(self.input_names)) != n:
            raise ValueError(f"{self.name}: duplicate input names")
        tn = [t.name for t in self.targets]
        if len(set(tn)) != len(tn):
            raise ValueError(f"{self.name}: duplicate target names")

    # ---- Convenience ----

    @property
    def n_inputs(self) -> int:
        return len(self.input_names)

    @property
    def target_names(self) -> List[str]:
        return [t.name for t in self.targets]

    def target(self, name: str) -> TargetSpec:
        for t in self.targets:
            if t.name == name:
                return t
        raise KeyError(f"{self.name}: no target {name!r}")

    def all_in_band(self, values: Mapping[str, float]) -> bool:
        """True when every target with a declared band is inside it."""
        return all(t.in_band(values[t.name]) for t in self.targets if t.name in values)

    # ---- Persistence ----

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["targets"] = [asdict(t) for t in self.targets]
        d["provenance"] = asdict(self.provenance)
        return d

    @classmethod
    def from_dict(cls, d: Mapping[str, Any]) -> "SurrogateSpec":
        d = dict(d)
        # LENIENT ON READ, strict on write. Artifacts written before 2026-09-22 can carry a
        # non-finite `observed`, and refusing them here would make an already-delivered bundle
        # unloadable -- punishing the reader for the writer's mistake. Normalise to None, which is
        # what the value meant, and say so once.
        cleaned = []
        for t in d.get("targets", ()):
            t = dict(t)
            if t.get("observed") is not None and not _finite(t["observed"]):
                warnings.warn(
                    "target %r has a non-finite `observed` (%r) in this spec; reading it as None. "
                    "The file is not standard JSON and a strict parser will refuse it; rewrite it "
                    "with SurrogateSpec.write to correct that." % (t.get("name"), t["observed"]),
                    RuntimeWarning)
                t["observed"] = None
            cleaned.append(TargetSpec(**t))
        d["targets"] = tuple(cleaned)
        d["provenance"] = Provenance(**d.get("provenance", {"model": ""}))
        for k in ("input_names", "input_lower", "input_upper"):
            if k in d:
                d[k] = tuple(d[k])
        return cls(**d)

    def write(self, path: Path) -> None:
        """Write the spec as STANDARD JSON, refusing the non-standard tokens Python allows.

        `json.dumps` emits bare `NaN` and `Infinity` by default. Those are not JSON: a strict
        parser rejects them, which for a bundle handed to a collaborator means the artifact's own
        description cannot be read by whatever they use. Measured 2026-09-13 on a bundle already
        delivered -- its `spec.json` carried three `NaN` observed values, and the audit found it
        only because a reviewer tried to parse the file with a strict reader.

        A NaN observation is also meaningless on its own terms: `observed=None` is how a target
        says it has no observation, and NaN is how one says it by accident. The refusal names the
        targets so the caller fixes the cause rather than the symptom.
        """
        try:
            text = json.dumps(self.to_dict(), indent=2, allow_nan=False)
        except ValueError:
            bad = [t.name for t in self.targets
                   if t.observed is not None and not _finite(t.observed)]
            raise ValueError(
                "spec %r cannot be written as standard JSON because %s. Use observed=None for a "
                "target with no observation; NaN is not JSON and a strict parser refuses the "
                "file." % (self.name,
                           ("targets %s carry a non-finite `observed`" % bad) if bad
                           else "it contains a non-finite number"))
        Path(path).write_text(text)

    @classmethod
    def read(cls, path: Path) -> "SurrogateSpec":
        return cls.from_dict(json.loads(Path(path).read_text()))


# =============================================================================
# Hashing helpers — used to populate Provenance
# =============================================================================

def hash_file(path: Path) -> str:
    """SHA-256 of a file's bytes, first 16 hex chars."""
    h = hashlib.sha256(Path(path).read_bytes())
    return h.hexdigest()[:16]


def hash_param_list(names: List[str], lower: List[float], upper: List[float]) -> str:
    """Stable hash of a parameter list including its bounds.

    Bounds are part of the identity: the same names sampled over different
    bounds is a different design, and a surrogate trained on one does not
    transfer to the other. Bounds that miss the viable region are the cautionary
    case: the names are unchanged and the design is uninformative.
    """
    payload = json.dumps(
        [[n, float(lo), float(hi)] for n, lo, hi in zip(names, lower, upper)],
        sort_keys=False)
    return hashlib.sha256(payload.encode()).hexdigest()[:16]
