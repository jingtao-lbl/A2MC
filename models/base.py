"""Adapter contract types for A2MC.

Defined per `docs/17_Multi_Model_Adapter_Architecture_Plan.md` §5, extended per
Doc 19 §6.5 (validator dispatch fields) and `memory/dev_logs_adapterkit/
20260428b_Version_Association_Adaptation.md` (version-association fields).

Three core types:
    ModelSpec     — frozen dataclass; static metadata
    ModelBackend  — ABC; executable interface (one implementation per model)
    ModelDataset  — frozen dataclass; versioned data bundle

Plus support classes for validators + version association:
    ModelVersion          — abstract dataclass; per-adapter version structure
    ModelVersionDetector  — ABC; reads model commits from a checkout
    BumpTierClassifier    — ABC; decides T1 / T2 / T3 from version distance
    MilestoneMetadata     — ABC; per-adapter opaque milestone metadata
    Tier                  — string-valued enum-ish for bump tiers

This module has NO model-specific content. It provides the abstract scaffolding
that each adapter implements.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


# =============================================================================
# Bump tier — string constants used by version-association layer
# =============================================================================

class Tier:
    """Bump tier labels. Strings (not Enum) so they survive JSON round-trips
    cleanly and match the existing string-based usage in `tools/rag_selector.py`."""

    T1 = "T1"  # metadata refresh only (commit equality, no source diff)
    T2 = "T2"  # parameter-file delta within same epoch — rebuild graph layer 2
    T3 = "T3"  # cross-epoch / new-major bump — full RAG rebuild

    ALL = (T1, T2, T3)


# =============================================================================
# ModelVersion — abstract base for per-adapter version structures
# =============================================================================

class ModelVersion(ABC):
    """Abstract base for adapter-specific version structures.

    Each adapter's `version.py` defines a concrete subclass with the fields
    its version-detector populates. FATES uses `ELMFATESVersion`
    (currently in `tools/model_version.py` for historical reasons; will move
    to `models/fates/version.py` during Doc 19 Step E generalization). EcoSIM
    will declare its own `EcoSIMVersion`, etc.

    Subclasses are typically `@dataclass`. They MUST implement `label` and
    `to_dict`, and SHOULD also implement `__eq__` / `__hash__` if they need
    to be used as dict keys (most adapters get this from `@dataclass(eq=True, frozen=True)`).
    """

    @property
    @abstractmethod
    def label(self) -> str:
        """Human-readable version label used for milestone identification.

        Examples:
            FATES:   'api-43-1'  (built from api.43.1 epoch)
            Semver:  'v1.2.3'
            Date:    '2026-04-28'
        """

    @abstractmethod
    def to_dict(self) -> Dict[str, Any]:
        """Serialize for milestone metadata storage (rag/milestones.json)."""


# =============================================================================
# ModelVersionDetector — abstract base for adapter-specific version detection
# =============================================================================

class ModelVersionDetector(ABC):
    """Abstract base for adapter-specific version detection.

    Each adapter ships a subclass that reads its model's git/source-tree state
    and returns a `ModelVersion` subclass. The framework calls
    `detector.detect_from_checkout(path)` to identify which milestone profile
    matches the user's current checkout.

    For FATES, the detector reads `git describe --tags --long` from both
    `<E3SM>/components/elm/` (ELM commit) and
    `<E3SM>/components/elm/src/external_models/fates/` (FATES commit). For
    a Python-implemented model, it might read `__version__` from a module.
    For a versioned NetCDF dataset, it might read a global attribute.
    """

    @abstractmethod
    def detect_from_checkout(self, checkout_path: Path) -> ModelVersion:
        """Read the model's git/source state at `checkout_path` and return a
        ModelVersion populated for this adapter.

        Raises:
            FileNotFoundError: if `checkout_path` doesn't look like a valid
                checkout for this model.
        """


# =============================================================================
# BumpTierClassifier — abstract base for tier classification
# =============================================================================

class BumpTierClassifier(ABC):
    """Abstract base for adapter-specific bump-tier classification.

    Given a registered milestone version and the user's current version, decide
    whether the milestone can be reused as-is (T1), needs partial rebuild (T2),
    or needs full rebuild (T3).

    For FATES, T1 = same FATES commit; T2 = same api epoch but different
    parameter-file sha; T3 = different api epoch. For semver-versioned models,
    T1 = same patch version; T2 = same major.minor; T3 = different major.
    """

    @abstractmethod
    def classify(
        self,
        milestone_version: ModelVersion,
        current_version: ModelVersion,
    ) -> str:
        """Return one of `Tier.T1`, `Tier.T2`, `Tier.T3`."""


# =============================================================================
# MilestoneMetadata — abstract base for adapter-specific milestone metadata
# =============================================================================

class MilestoneMetadata(ABC):
    """Abstract base for adapter-specific milestone metadata.

    `rag/milestones.json` schema v2 (per `memory/dev_logs_adapterkit/
    20260428b_Version_Association_Adaptation.md`) uses an opaque
    `model_specific` block per milestone. The framework dispatches through
    this class to serialize / deserialize that block.

    Schema v1 (current, FATES-only) uses a flat structure keyed on
    fates-specific field names; subclasses of this class provide the v2-style
    encapsulation as the framework migrates. Until Step E.5 lands, FATES
    bypasses this class and reads the flat schema directly.
    """

    @classmethod
    @abstractmethod
    def from_dict(cls, d: Dict[str, Any]) -> "MilestoneMetadata":
        """Deserialize the model_specific block of a milestone entry."""

    @abstractmethod
    def to_dict(self) -> Dict[str, Any]:
        """Serialize this milestone's adapter-specific metadata."""


# =============================================================================
# ModelSpec — static, immutable metadata describing a model
# =============================================================================

@dataclass(frozen=True)
class ModelSpec:
    """Static, code-level description of a model. One per model.

    Versioned by code: when a model has new parameter naming conventions or
    a new structural feature, you bump the spec. Stable across data-only
    version bumps (those go on `ModelDataset`).

    Frozen (immutable) so it's safe to share across threads / async contexts.
    """

    # ---- Identity ----

    name: str                            # "fates", "ecosim", "resom"
    display_name: str                    # "ELM-FATES", "EcoSim", "ReSOM"

    # ---- Parameter naming convention ----

    param_name_regex: str                # e.g., r"^fates_\w+$"
    param_categories: Dict[str, str] = field(default_factory=dict)
                                         # {"alloc": "Allocation", "cnp": "CNP cycling", ...}

    # ---- Output naming convention ----

    output_name_regex: str = ""          # e.g., r"^FATES_\w+$"
    output_categories: Dict[str, str] = field(default_factory=dict)
                                         # {"biomass": "Biomass", ...}
    key_external_outputs: Tuple[str, ...] = ()
                                         # e.g., FATES references key ELM variables (TSA, TOTSOMC, etc.)

    # ---- Subgrid grouping axis (model-specific organizing dimension) ----

    grouping_axis: str = "pft"           # as DECLARED by each spec today: "pft" (FATES, EcoSIM),
                                         # "region" (PFLOTRAN, ATS), "group" (_template).
                                         # NB: this line said "plant_type" (EcoSim) until 2026-08-19,
                                         # which no spec has ever declared -- it misled a reader into
                                         # telling the PI EcoSIM has no PFTs. Keep it matching the specs.
    grouping_axis_dim_name: str = ""     # NetCDF/CDL dimension name; e.g., "fates_pft"
    default_groups: Tuple[int, ...] = ()  # e.g., (7, 9, 10) for Kougarok FATES; site-overridable

    # ---- Mechanism / category framework (used by curated YAML) ----

    mechanism_keyword_map: Dict[str, str] = field(default_factory=dict)
                                         # {"pid": "PID_Controller", "eca": "ECA_Competition", ...}

    # ---- Domain context for AI prompts ----

    domain_summary: str = ""             # one-paragraph summary of the model's scope

    # ---- Reasoning / RAG retrieval vocabulary (reasoning/methods.py, dev log
    # memory/dev_logs_adapterkitpflotran/20260807k) ----
    # The AI reasoning loop queries RAG using a target/result key mangled into a
    # GUESSED output name (FATES's own historical convention, e.g. 'outflow_Ca' ->
    # 'FATES_OUTFLOWC_CA'). That guess means nothing for another model's output
    # registry, so `reasoning.retrieval_vocab.resolve_output_names()` looks here
    # FIRST for an explicit override, but prefers a target's own `variable:` field
    # (already present in every onboarded model's targets.yaml, and already the
    # name `tools/validate_model_targets.py` checks against the real output
    # registry) over this map. Empty (the default) degrades to the key UNCHANGED,
    # which is correct for a model whose targets already ARE real column names
    # (PFLOTRAN's `outflow_Ca` is one) -- only populate this for a target/result
    # key whose real name genuinely differs and has no `variable:` field reachable
    # at the call site (e.g. a bare Morris `output_var` string with no targets
    # dict in scope).
    retrieval_output_name_map: Dict[str, str] = field(default_factory=dict)

    # ---- Validator dispatch (Doc 19 §6.5) ----
    #
    # Each validator (V1, V2, V4, V5) reads these fields to dispatch through
    # the right adapter's parsers and language conventions. None values mean
    # "validator falls back to its built-in default" (Fortran-shaped, FATES-style).

    parameter_parser_class: Optional[type] = None
                                         # Subclass of <model>ParameterParser; used by V1, V2
    output_parser_class: Optional[type] = None
                                         # Subclass of <model>OutputParser; used by V1, V2
    source_extensions: Tuple[str, ...] = (".F90", ".f90")
                                         # File extensions to scan for source-vs-wiki validation
    routine_decl_patterns: Tuple[str, ...] = (
        r"\bsubroutine\s+(\w+)",
        r"\bfunction\s+(\w+)",
        r"\b(?:integer|real|logical|character)(?:\([^)]*\))?\s+function\s+(\w+)",
    )                                    # Regexes to detect routine declarations
    module_file_pattern: str = r"\w+Mod\.F90"
                                         # Pattern for module-file references in wiki text

    # ---- Version association dispatch (dev log 20260428b) ----

    version_detector_class: Optional[type] = None
                                         # Subclass of ModelVersionDetector
    bump_tier_classifier_class: Optional[type] = None
                                         # Subclass of BumpTierClassifier
    milestone_label_format: str = "{label}"
                                         # f-string template for milestone names;
                                         # e.g., "api-{major}-{minor}" for FATES
    milestone_metadata_class: Optional[type] = None
                                         # Subclass of MilestoneMetadata

    # ---- Input↔binary compat guard (dev log 20260712f/g; tools/model_check_input_compat) ----
    # The set of input-file variables the BUILT binary requires is discovered by
    # scanning the model source for its param-file read calls. Empty = the model
    # declares no source-read compat contract (the guard is a graceful no-op).
    input_reader_sources: Tuple[str, ...] = ()
                                         # checkout-relative source file(s) with the param-file reads
    input_read_pattern: str = ""         # regex w/ ONE capture group = a required input var name

    # ---- Bounds generation (scripts/model_generate_bounds) ----
    # Heuristics for default-anchored provisional bounds. Fractions clamp to [0,1];
    # signed params skip the >=0 clamp. Empty = no special handling (plain +/-frac).
    fraction_param_names: Tuple[str, ...] = ()   # param names bounded to [0,1]
    fraction_categories: Tuple[str, ...] = ()    # param_categories keys whose members are [0,1]
    signed_param_names: Tuple[str, ...] = ()     # params that may be negative (skip >=0 clamp)

    # ---- Output alignment (tools/model_evaluate_case) ----
    # Names the sub-block dimension folded WITH the grouping axis into a flat output
    # dim (FATES SZPF = size x pft). Empty = the grouping axis is directly indexable
    # (EcoSIM _pft tapes are flat (time, pft)).
    grouping_axis_block_dim_name: str = ""

    # ---- Ensemble run harness (scripts/run_smoke_ensemble) ----
    run_length_control_label: str = ""   # human name of the native run-length control
                                         # (EcoSIM "forc_periods"; FATES "STOP_N/STOP_OPTION")

    # ---- Output activation (backend.create_case) ----
    # Names of calibration output variables that are registered inactive-by-default in the
    # model and must be explicitly activated for the run to write them (EcoSIM: the h0
    # `hist_fincl1` list; 117/179 _pft fields are default='inactive'). create_case injects
    # these into the run config when the staged config doesn't already request them. Empty =
    # the model writes everything needed by default (FATES), so nothing to activate.
    hist_activate: Tuple[str, ...] = ()

    # --- Secondary parameter surface (models with more than one parameter file) ---
    # The namelist/config input a per-case SECONDARY parameter file is repointed at
    # (see ModelBackend.write_parameter_file surface="secondary" + create_case
    # secondary_param_file). Empty = single-surface model (FATES). e.g. EcoSIM =
    # "pft_mgmt_in" (the stand-management NetCDF input line in the runfile namelist).
    secondary_namelist_var: str = ""

    # --- Tertiary parameter surface (models with a third parameter file) ---
    # Same contract as secondary_namelist_var, one surface further (see
    # ModelBackend.write_parameter_file surface="tertiary" + create_case
    # tertiary_param_file). Empty = model has at most two surfaces. e.g. EcoSIM =
    # "micpar_file_in" (the microbial-kinetics NetCDF input line in the runfile
    # namelist — RCCZ/VMXO/RMOM/GO2X/SPORC/SPOMC and the rest of MicrobePars.nc;
    # optional in the model itself, an empty path falls back to hardcoded defaults).
    tertiary_namelist_var: str = ""

    # --- Quaternary parameter surface (models with a fourth parameter file) ---
    # Same contract again, one surface further (see ModelBackend.write_parameter_file
    # surface="quaternary" + create_case quaternary_param_file). Empty = model has at
    # most three surfaces. e.g. EcoSIM = "grid_file_in" (the site/soil-profile NetCDF:
    # texture, bulk density, field capacity, Ksat, pH, CEC, the organic-matter pools,
    # the solute and mineral set, and the surface albedo).
    #
    # THIS SURFACE'S AXIS IS THE SOIL LAYER, not a plant type, and that is the reason
    # it needs its own writer rather than reusing the primary one: its variables are
    # dimensioned (ntopou, nlevs), so the first axis is the topographic unit and the
    # LAYER is the second. A writer that indexed axis 0 would silently edit the wrong
    # dimension. See ModelSpec.quaternary_axis.
    quaternary_namelist_var: str = ""

    # What the trailing `_<n>` of a canonical id means ON THE QUATERNARY SURFACE.
    # The axis column is an ALIAS across A2MC -- plant type on a PFT surface, pool slot
    # on a microbial one -- and naming it here keeps a parameter list readable and a
    # bounds table checkable. Empty when no quaternary surface is declared.
    quaternary_axis: str = ""

    # --- Out-of-scope / external-boundary references (wiki validation) ---
    # A model built ON a framework or coupled INTO a host legitimately references
    # symbols the wiki does NOT document (they live in the host/framework, out of
    # scope). Wiki validators use these to classify an "unresolved" routine or a
    # "missing" module file as EXPECTED-EXTERNAL rather than a fabrication, so the
    # verdict reflects real in-scope accuracy. Empty = self-contained model (FATES,
    # EcoSIM): every referenced symbol should resolve in the model's own source.
    #   external_symbol_names   -- exact routine/method identifiers defined in the
    #       host/framework (e.g. ATS references Amanzi's UpdateMatrices, MyLength).
    #   external_module_patterns -- regexes for module-file mentions that are
    #       framework files, build-generated, or wiki wildcard patterns (e.g. ATS
    #       `.*_registration\.hh` generated registries, `MatrixMFD.*` Amanzi files).
    external_symbol_names: Tuple[str, ...] = ()
    external_module_patterns: Tuple[str, ...] = ()

    # --- Declared non-applicability (tools/validate_adapter_parity.py) ---
    # Maps a ModelSpec field name -> the REASON this model legitimately leaves it
    # empty. Every A2MC feature that dispatches through a spec field degrades to a
    # NO-OP when the field is empty, and an empty field means one of two things that
    # the spec alone cannot distinguish: "not applicable to this model" (correct) or
    # "nobody filled it in" (a silently dead feature). Either way the dispatching
    # feature reports "nothing to check", which reads as a pass. ATS is the worked
    # example: three fields sat empty with their guards doing nothing -- `hist_activate`
    # (the inactive-output check) and `input_reader_sources`/`input_read_pattern` (the
    # input-vs-binary compat gate).
    #
    # They were NOT overlooked. Each carried a written rationale, in a PROSE COMMENT
    # directly above the field, since v0.1. What was missing was that no tool could READ
    # it. So this field is not about forcing anyone to think -- it is about putting the
    # thinking where a check can reach it. See `memory/dev_logs_adapterkitats/20260801l`.
    #
    # An entry states "empty on purpose, for this reason". It is NOT a claim that the
    # field is correctly empty -- it is a claim that someone DECIDED and can be held to
    # it, so a reason may freely record that it is UNVALIDATED, or record a deferral
    # ("filled at onboard step 5"). Each SHOULD state its EXPIRY CONDITION -- what would
    # make it false -- because a rationale that was right once and quietly stopped being
    # right is the failure this mechanism exists to catch; `tests/test_adapter_parity.py`
    # requires the marker. The key "*" is a blanket declaration for an adapter still
    # mid-onboarding: it passes, but the validator prints every field it excuses.
    spec_na: Dict[str, str] = field(default_factory=dict)


# =============================================================================
# ModelBackend — executable interface (one implementation per model)
# =============================================================================

class ModelBackend(ABC):
    """Executable methods for driving a model. One implementation per model.

    Backend instances are stateless (or read-only stateful). Methods take a
    `ModelDataset` parameter when they need to know which version to operate on.

    The framework calls these methods. It does NOT know what's inside
    `create_case()` — for FATES, it shells out to `tools/create_case.sh`;
    for EcoSim, it might call a Python launcher; for a JAX-based BGC model,
    it might dispatch a SLURM job directly.
    """

    spec: ModelSpec  # Each subclass declares its spec as a class-level attribute.

    # ---- Parameter and output parsing ----

    @abstractmethod
    def parse_parameters(self, param_file: Path) -> Dict[str, Any]:
        """Parse the parameter file into a dict keyed on parameter name.

        Format detection (CDL / JSON / YAML / NetCDF) is the adapter's
        responsibility — typically via `spec.parameter_parser_class`.
        """

    @abstractmethod
    def parse_outputs(self, output_cdl: Path) -> Dict[str, Any]:
        """Parse the output variable file (typically CDL) into a dict keyed
        on output variable name."""

    # ---- Parameter file I/O ----

    def read_secondary_param(self, path, name: str) -> float:
        """Read back ONE secondary-surface parameter from a staged file.

        The counterpart of ``write_parameter_file(..., surface="secondary")``, and it exists so a
        sampled secondary value can be VERIFIED before submission rather than trusted. A surface
        that is written but never checked is how a materializer that silently skipped one becomes
        indistinguishable from a scientific result.

        Raises NotImplementedError by default: a model declaring no secondary names never needs it.
        """
        raise NotImplementedError(
            f"{type(self).__name__} declares no readable secondary surface (asked for '{name}')")

    def secondary_param_names(self) -> set:
        """Bare parameter names this model's SECONDARY surface can write. Empty = none.

        DECLARED, not probed, and deliberately so. The secondary surface need not be a NetCDF
        whose variable names can be listed: EcoSIM's is a management file whose writable knob
        (`PPI`) is a whitespace token inside a fixed-width character array, invisible to
        `nc_varnames()`. An adapter that supports `write_parameter_file(surface="secondary")`
        should return the SAME key set its writer accepts, so the router and the writer cannot
        drift apart. Default empty keeps every single-surface model's behaviour unchanged.
        """
        return set()

    @abstractmethod
    def write_parameter_file(
        self,
        base_param_file: Path,
        modifications: Dict[str, Any],
        output_path: Path,
        surface: str = "primary",
    ) -> None:
        """Apply parameter modifications to a base file and write the result.

        Modifications dict maps parameter name → new value. The adapter
        decides how to express modifications in the model's native format.

        ``surface`` selects WHICH parameter surface to write when a model has
        more than one (a model may expose a primary parameter file plus one or
        more additional files — e.g. a separate stand-management / boundary-input
        file, or a separate microbial-kinetics file). ``"primary"`` (default) is
        the main parameter file and is the only surface most models have; an
        adapter that supports a second surface handles ``surface="secondary"``,
        a third handles ``surface="tertiary"`` and a fourth ``surface="quaternary"`` (each writes ``base_param_file``
        = that surface's own base). Adapters with fewer surfaces should raise on
        any ``surface`` they don't support. The mapping of a surface to its base
        file and the namelist input it repoints is model-specific and stays
        inside the adapter; the calibration layer only passes the generic
        surface name (from the param list's ``surface`` column, default
        ``primary``).
        """

    # ---- Case creation and submission ----

    @abstractmethod
    def create_case(
        self,
        case_name: str,
        param_file: Path,
        config: Dict[str, Any],
        secondary_param_file: Optional[Path] = None,
        tertiary_param_file: Optional[Path] = None,
        quaternary_param_file: Optional[Path] = None,
    ) -> Path:
        """Create a model run case directory. Returns the case path.

        `config` is the merged machine + site config (parsed from
        `a2mc_config.sh` + `use_cases/<site>/config/<site>_config.sh`).

        `param_file` is the PRIMARY parameter file (repointed in the model's
        native input). `secondary_param_file`, if given, is a SECONDARY surface
        file (see `write_parameter_file` surface="secondary"); the adapter stages
        it and repoints `spec.secondary_namelist_var` at the staged copy.
        `tertiary_param_file` is the same contract one surface further
        (`spec.tertiary_namelist_var`), and `quaternary_param_file` one
        further again (`spec.quaternary_namelist_var`). Both are ignored by models with fewer
        surfaces; a model that stages an ensemble's shared secondary/tertiary
        files itself (rather than per-case) may instead repoint the case's
        runfile directly after `create_case` returns — see
        `scripts/materialize_adapter_crossed.py`'s `_repoint_secondary`.
        """

    @abstractmethod
    def submit_ensemble(
        self,
        case_paths: List[Path],
        config: Dict[str, Any],
    ) -> List[str]:
        """Submit an ensemble of cases to the HPC scheduler. Returns job IDs.

        For local/non-HPC runs, returns synthetic IDs. For CIME-based models,
        invokes `case.submit`. For standalone-binary models, invokes the
        scheduler's submit command directly.
        """

    @abstractmethod
    def check_case_status(self, case_path: Path) -> str:
        """Return status: 'PENDING' | 'RUNNING' | 'COMPLETED' | 'FAILED'."""

    # ---- Output extraction ----

    @abstractmethod
    def extract_history_variables(
        self,
        case_path: Path,
        variables: List[str],
        time_range: Optional[tuple] = None,
        tape: str = "h0",
    ) -> Any:
        """Extract requested history variables from a completed case.

        ``tape`` selects among multiple history outputs for an adapter that has more than
        one (e.g. EcoSIM's ``hist_fincl1``/``hist_fincl2`` daily/hourly tapes, keyed ``h0``/
        ``h1``). An adapter with a single output file (ATS, PFLOTRAN) accepts and ignores it.

        Returns: typically `xarray.Dataset`, but the framework treats this
        opaquely until a generic extraction layer is defined. Adapter docs
        the returned type for its use cases.
        """

    # ---- Output alignment: group (subgrid) selection ----
    #
    # NON-abstract: ships a default so most adapters need not implement it. Used
    # by the generic `tools/model_evaluate_case.reduce_target()`, which delegates
    # the model-specific GROUP-SELECT here and then does the (model-agnostic)
    # time reduction itself.

    def select_group_series(self, data: Any, target: Dict[str, Any]) -> Any:
        """Select a target's grouping-axis (e.g. PFT) time series from an
        extracted variable array, returning a 1-D ``(time,)`` series.

        Default: FLAT indexing — this is EcoSIM's behavior. When the spec
        declares no block sub-dimension (``spec.grouping_axis_block_dim_name``
        empty), a per-group variable is ``(time, group)`` and the group column
        is ``data[:, pft-1]``. A column-level (``ndim == 1``) variable is
        returned as-is, and a ``pft``-less multi-dim var collapses to its first
        column. A block-structured model (FATES SZPF = size × pft, where the
        grouping axis is folded into a flat block dim) OVERRIDES this to sum the
        size block belonging to the pft.

        ``data``   : ndarray for one history variable (``(time,)`` or ``(time, group)``).
        ``target`` : target spec; ``target['pft']`` is the 1-based group slot.
        """
        import numpy as np
        arr = np.asarray(data)
        var = target.get("variable", "<var>")
        pft = target.get("pft")
        if pft is not None and arr.ndim >= 2:
            idx = int(pft) - 1
            if idx < 0 or idx >= arr.shape[1]:
                raise IndexError(f"{var}: PFT {pft} out of range (1..{arr.shape[1]})")
            return arr[:, idx]
        return arr.reshape(arr.shape[0], -1)[:, 0] if arr.ndim >= 2 else arr

    def reduce_ecosystem(self, extracted: Dict[str, Any],
                         target: Dict[str, Any], how: str) -> float:
        """Model-specific ecosystem-level (plot-scale) target reduction.

        Handles reductions the generic per-PFT max/mean/last path in
        ``tools.model_evaluate_case.reduce_target`` cannot — Σ-over-group,
        per-year rate integration, depth integrals — because they depend on the
        model's group axis, calendar, timestep and soil geometry. Each adapter
        implements its own (mirrors ``select_group_series``); there is NO
        model-agnostic default. ``how`` is one of
        ``tools.model_evaluate_case.ECOSYSTEM_REDUCES``.
        """
        raise NotImplementedError(
            f"{type(self).__name__} does not implement ecosystem reduce '{how}'")

    # Reduce keywords THIS model defines beyond the generic max/mean/last and the
    # shared ECOSYSTEM_REDUCES set. An adapter declares its own here rather than
    # having the generic layer enumerate every model's vocabulary, so adding a
    # model does not require editing tools/model_evaluate_case.py. Dispatched to
    # ``reduce_derived`` below. (PFLOTRAN's ``outflow_concentration`` is the
    # first instance: a RATIO of two output columns, which no per-variable reduce
    # can express.)
    MODEL_REDUCES: frozenset = frozenset()

    def reduce_derived(self, extracted: Dict[str, Any],
                       target: Dict[str, Any], how: str) -> float:
        """Model-specific DERIVED target reduction — a target that is not any one
        output column.

        Distinct from ``reduce_ecosystem`` (which reduces ONE variable over the
        model's group axis / calendar / geometry): a derived reduce composes
        SEVERAL columns, so it runs before the generic single-variable path can
        apply. ``how`` is one of this backend's ``MODEL_REDUCES``.
        """
        raise NotImplementedError(
            f"{type(self).__name__} does not implement derived reduce '{how}'")

    # ---- Diagnostic tooling ----

    @abstractmethod
    def list_diagnostic_tools(self) -> List[Path]:
        """Return paths to model-specific diagnostic `test_*.py` scripts.

        Phase 3 of A2MC's calibration workflow auto-discovers these for
        hypothesis testing against the existing ensemble.
        """


# =============================================================================
# ModelDataset — versioned data bundle
# =============================================================================

@dataclass(frozen=True)
class ModelDataset:
    """A specific version of a model's reference data.

    Multiple datasets exist for the same model (e.g., FATES at api-43-1 and
    FATES at api-31-0). The active dataset is selected at runtime via the
    orchestrator alignment hook reading `A2MC_MODEL_PATH` and matching against
    `rag/milestones.json`. The hook sets `A2MC_RAG_ACTIVE` to the matched
    profile name; framework code reads through the dataset returned by
    `registry.get_active_model()`.
    """

    model_name: str                  # "fates"
    version: str                     # "api-43-1" — milestone profile label

    # ---- Knowledge inputs (commit-pinned) ----

    wiki_paths: Tuple[Path, ...] = ()  # one or more wiki Markdown roots
    parameter_file: Optional[Path] = None
                                       # parameter CDL/JSON/YAML/namelist
    output_cdl: Optional[Path] = None  # output variable CDL
    curated_yaml: Optional[Path] = None
                                       # frozen per-milestone curated relationships YAML

    # ---- RAG output paths (per-profile, no clobbering) ----

    vector_persist_dir: Optional[Path] = None
                                       # rag/chroma_db/<profile>/
    graph_path: Optional[Path] = None  # rag/graphs/<profile>.json
    metadata_path: Optional[Path] = None
                                       # rag/metadata/<profile>.json

    # ---- Optional metadata ----

    description: str = ""              # human-readable note about this version
    upstream_url: str = ""             # link to upstream commit/release
    canonical: bool = False            # default version when no override is set
    legacy: bool = False               # pinned for reproducibility (e.g., manuscript)
