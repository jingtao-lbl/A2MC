"""Template ModelSpec — copy + fill in for your model.

The `TEMPLATE_SPEC` instance below has placeholders. Replace each
`# TODO(adapter-kit):` marker with model-specific content.

After copying this template to `models/<yourmodel>/spec.py`:
    1. Rename `TEMPLATE_SPEC` → `<YOURMODEL>_SPEC`
    2. Update each field per the comments
    3. Make sure the parser/detector/classifier classes referenced are
       imported from your adapter's siblings (parameter_parser.py,
       output_parser.py, version.py)
"""

from __future__ import annotations

from ..base import ModelSpec
from .output_parser import TemplateOutputParser
from .parameter_parser import TemplateParameterParser
from .version import TemplateBumpTierClassifier, TemplateMilestoneMetadata, TemplateVersionDetector


TEMPLATE_SPEC = ModelSpec(
    # ---- Identity ----
    name="_template",
    # TODO(adapter-kit): change to your model name (e.g., "ecosim", "resom").
    # The leading underscore in "_template" marks this as a non-real adapter.

    display_name="Template Model",
    # TODO(adapter-kit): human-readable name (e.g., "EcoSim", "ReSOM").

    # ---- Parameter naming convention ----
    param_name_regex=r"^_template_\w+$",
    # TODO(adapter-kit): regex matching your model's parameter names.
    # FATES uses r"^fates_\w+$"; semver-named params might be r"^[a-z][a-zA-Z0-9_]*$".

    param_categories={
        # TODO(adapter-kit): map prefix → category-display-name.
        # FATES example:  {"alloc": "Allocation", "cnp": "CNP cycling", ...}
        # Used by the curated YAML's `categories:` block (Step 3 of pipeline).
    },

    # ---- Output naming convention ----
    output_name_regex=r"^TEMPLATE_\w+$",
    # TODO(adapter-kit): regex matching your model's output variable names.
    # FATES uses r"^FATES_\w+$".

    output_categories={
        # TODO(adapter-kit): map prefix → output-category-name.
        # Used by V1's Dim 5 module-file presence check.
    },

    key_external_outputs=(),
    # TODO(adapter-kit): if your model writes outputs from a host model
    # (e.g., FATES uses some ELM variables like TSA, TOTSOMC), list them
    # here. The validators will treat these as out-of-scope cross-references
    # rather than fabrications. Most standalone models leave this empty.

    # ---- Subgrid grouping axis ----
    grouping_axis="group",
    # TODO(adapter-kit): your model's organizing dimension (e.g., "pft" for
    # FATES and EcoSIM both declare "pft"; PFLOTRAN and ATS declare "region"; "cohort" for an
    # individual-based model). EcoSIM DOES have PFTs; its per-PFT integer type flags
    # (ICTYP/IGTYP/...) live in a PARAMETER CATEGORY named `pfts`, which is not the axis.
    # Read the axis from the spec, never infer it from a category name or from prose.

    grouping_axis_dim_name="",
    # TODO(adapter-kit): NetCDF/CDL dimension name for the grouping axis.
    # FATES: "fates_pft". Leave empty if not applicable.

    default_groups=(),
    # TODO(adapter-kit): default group IDs to calibrate (e.g., (7, 9, 10)
    # for Kougarok FATES PFTs). Site configs can override. Empty tuple is fine.

    # ---- Mechanism / category framework (used by curated YAML) ----
    mechanism_keyword_map={
        # TODO(adapter-kit): map AI-prompt keywords → mechanism names that
        # appear in your curated YAML. FATES example:
        #     {"pid": "PID_Controller", "eca": "ECA_Competition", ...}
        # The CLI's curated_seed_builder.py uses these to dispatch the
        # right context to per-category subagents.
    },

    # ---- Domain context for AI prompts ----
    domain_summary=(
        "TODO(adapter-kit): one-paragraph summary of the model's scope. "
        "Used as a system-prompt prefix when AI calibration agents reason "
        "about the model. FATES example: 'FATES is a cohort-based vegetation "
        "demography model coupled to ELM/CESM, simulating size-structured "
        "competition with integrated CNP cycling and PARTEH allocation.'"
    ),

    # ---- Validator dispatch (Doc 19 §6.5) ----
    parameter_parser_class=TemplateParameterParser,
    output_parser_class=TemplateOutputParser,
    source_extensions=(".F90", ".f90"),
    # TODO(adapter-kit): file extensions to scan in V1 source-vs-wiki
    # validation. Fortran defaults shown. For Python: (".py",). For C++:
    # (".cpp", ".cc", ".h", ".hpp"). For Julia: (".jl",).

    routine_decl_patterns=(
        r"\bsubroutine\s+(\w+)",
        r"\bfunction\s+(\w+)",
        r"\b(?:integer|real|logical|character)(?:\([^)]*\))?\s+function\s+(\w+)",
    ),
    # TODO(adapter-kit): regexes to detect routine declarations. Fortran
    # defaults shown. For Python: (r"\bdef\s+(\w+)",). For C++:
    # (r"\b(?:[a-zA-Z_][\w:]*\s+)+(\w+)\s*\(",) — looser, more false positives.

    module_file_pattern=r"\w+Mod\.F90",
    # TODO(adapter-kit): pattern for module-file references in wiki text.
    # FATES uses r"\w+Mod\.F90". For Python modules: r"\w+\.py".

    # ---- Version association dispatch (dev log 20260428b) ----
    version_detector_class=TemplateVersionDetector,
    bump_tier_classifier_class=TemplateBumpTierClassifier,
    milestone_label_format="{label}",
    # TODO(adapter-kit): f-string template for milestone profile names.
    # FATES uses "api-{major}-{minor}". Semver might use "v{major}.{minor}.{patch}".

    milestone_metadata_class=TemplateMilestoneMetadata,

    # ---- Input↔binary compat guard (optional; tools/model_check_input_compat) ----
    # If your model reads its input/param file variable-by-variable in source (so an
    # older input file can be missing variables a newer binary requires), declare the
    # reader source + read regex so a pre-submit guard can fail fast. Leave empty to skip.
    # EcoSIM example: input_reader_sources=("f90src/IOutils/PlantInfoMod.F90",),
    #                 input_read_pattern=r"ncd_getvar\(\s*pft_nfid\s*,\s*'([A-Za-z0-9_]+)'"
    input_reader_sources=(),
    input_read_pattern="",

    # ---- Bounds generation heuristics (scripts/model_generate_bounds) ----
    # Params bounded to [0,1] (fractions) and params that may be negative (skip >=0 clamp).
    fraction_param_names=(),
    fraction_categories=(),
    signed_param_names=(),

    # ---- Output alignment (tools/model_evaluate_case) ----
    # Set only if a sub-block dim is folded WITH the grouping axis into a flat output
    # dim (e.g. FATES SZPF = size x pft). Empty = grouping axis directly indexable.
    grouping_axis_block_dim_name="",

    # ---- Ensemble run harness (scripts/run_smoke_ensemble) ----
    run_length_control_label="",   # e.g. EcoSIM "forc_periods", FATES "STOP_N/STOP_OPTION"
)
