"""ATS ModelSpec.

Static, code-level description of ATS (the Advanced Terrestrial Simulator) for A2MC.
Grounded in the ATS codebase wiki (`docs/ats-knowledge-base/ats-codebase-wiki-42b0e940/`,
commit `42b0e940`) and real input decks under `tests/fixtures/`.

ATS is structurally unlike FATES and EcoSIM: it is C++ (not Fortran), its parameters live
in a nested Teuchos ParameterList XML deck addressed by path (not a single param file), and
its calibration targets come from the deck's `observations` block (not a NetCDF history tape).
The real parameter/output filtering lives in the parser classes; the regexes here are
intentionally permissive.
"""

from __future__ import annotations

from ..base import ModelSpec
from .output_parser import ATSOutputParser
from .parameter_parser import ATSParameterParser
from .prompts import DOMAIN_SUMMARY
from .version import (
    ATSBumpTierClassifier,
    ATSMilestoneMetadata,
    ATSVersionDetector,
)


ATS_SPEC = ModelSpec(
    # ---- Identity ----
    name="ats",
    display_name="ATS",

    # ---- Parameter naming convention ----
    # A knob is a full ParameterList-path address (a/b/c/leaf), so the "name" contains
    # slashes, spaces, and bracketed units. Permissive regex; ATSParameterParser does the
    # real work (numeric-leaf detection, region multiplicity, unit + category extraction).
    param_name_regex=r"^[A-Za-z][\w \-\[\]\^/,.]*$",
    param_categories={
        "water_retention": "Water retention (van Genuchten / Brooks-Corey)",
        "permeability": "Permeability / hydraulic conductivity",
        "porosity": "Porosity / compressibility",
        "surface_flow": "Overland flow (Manning)",
        "evapotranspiration": "Evapotranspiration (Priestley-Taylor / rooting)",
        "thermal": "Subsurface heat transfer (conductivity, heat capacity; needs an energy PK)",
        "freezing_curve": "Soil freezing characteristic + frozen relative permeability",
        "initial_state": "Initial state (water-table depth / hydrostatic head)",
        "radiation": "Surface energy balance (albedo / emissivity / Beer's law extinction)",
        "plant_hydraulics": "Plant hydraulics (rooting profile, xylem / stomatal thresholds)",
        "snow": "Snow (transition depth)",
        "phenology": "Phenology (leaf on/off timing)",
        # NOT calibratable — constants of water, and mass/molar density are coupled through the
        # molar mass. Categorized for metadata only; see _PHYSICAL_CATEGORIES in parameter_parser.py.
        "fluid_property": "Fluid properties (density / viscosity)",
    },

    # ---- Output naming convention ----
    # ATS field names are lower-case with a domain prefix (`surface-`, `snow-`) and
    # underscores (`surface-total_evapotranspiration`, `water_content`). Permissive regex;
    # ATSOutputParser reads the deck's observations block for the real inventory.
    output_name_regex=r"^[A-Za-z][A-Za-z0-9_\-]*$",
    output_categories={
        "water_storage": "Water storage / content",
        "water_flux": "Water flux / source",
        "runoff": "Runoff / surface flux",
        "evapotranspiration": "Evaporation / transpiration",
        "water_table": "Water table",
        "surface_water": "Surface ponded water",
        "saturation": "Saturation",
        "pressure": "Pressure",
        "thermal": "Temperature / energy",
        "snow": "Snow",
        "forcing": "Atmospheric forcing",
    },
    # Standalone ATS writes its own observations; no host-model variables. (Coupled ELM-ATS
    # would add ELM history variables here.)
    key_external_outputs=(),

    # ---- Subgrid grouping axis ----
    # ATS has no PFT axis. Its organizing dimension is the mesh region/material (and, in the
    # coupled ELM-ATS case, the surface column). Observation targets are already reduced over
    # a region by their `functional`, so there is no per-group array indexing to do.
    grouping_axis="region",
    grouping_axis_dim_name="",
    default_groups=(),

    # ---- Mechanism / category framework (used by curated YAML) ----
    mechanism_keyword_map={
        "van genuchten": "Van_Genuchten_WRM",
        "brooks": "Brooks_Corey_WRM",
        "richards": "Richards_Subsurface_Flow",
        "manning": "Manning_Overland_Flow",
        "overland": "Surface_Subsurface_Coupling",
        "priestley": "Priestley_Taylor_ET",
        "rooting": "Rooting_Depth_Transpiration",
        "mpc": "Multi_Process_Coupler",
        "permafrost": "Freeze_Thaw_Energy",
        "elm_ats": "ELM_ATS_Coupling",
    },

    # ---- Domain context for AI prompts ----
    domain_summary=DOMAIN_SUMMARY,

    # ---- Validator dispatch (Doc 19 6.5) ----
    parameter_parser_class=ATSParameterParser,
    output_parser_class=ATSOutputParser,
    # ATS is C++.
    source_extensions=(".cc", ".hh", ".cpp", ".hpp"),
    routine_decl_patterns=(
        r"\b(\w+)::~?(\w+)\s*\(",                       # class method definitions Foo::bar(
        r"\b(?:void|bool|int|double|float|auto|std::\w+|[A-Z][\w:]*)\s+(\w+)\s*\(",  # free functions
    ),
    # Wiki references C++ source files (richards_pk.cc, elm_ats_driver.hh, ...).
    module_file_pattern=r"\w+\.(?:cc|hh|cpp|hpp)",

    # ---- Version association dispatch ----
    version_detector_class=ATSVersionDetector,
    bump_tier_classifier_class=ATSBumpTierClassifier,
    milestone_label_format="ats-{commit_short}",
    milestone_metadata_class=ATSMilestoneMetadata,

    # ---- Input<->binary compat guard ----
    # ATS reads an XML deck (not a var-by-var NetCDF param file), so the NetCDF-read compat
    # guard does not apply. Left empty = graceful no-op.
    input_reader_sources=(),
    input_read_pattern="",

    # ---- Bounds generation heuristics ----
    # Porosity/base_porosity and saturation-like knobs are physically in [0,1].
    fraction_categories=("porosity",),
    # Parameters SOURCE bounds to [0,1]. Declared by full deck address because the fraction set
    # is not category-aligned: `radiation` holds albedo/emissivity (fractions) alongside the
    # Beer's-law extinction coefficients, which are NOT (deck sw=0.6, lw=5.0). Without these,
    # scripts/model_generate_bounds.py produced emissivity 0.98 -> [0.49, 1.47] and surface
    # relative permeability 1.0 -> [0.5, 1.5]; the first is rejected at read time by
    # readZeroOneLandCoverParameter (LandCover.cc:78-81) and the second is unphysical.
    fraction_param_names=(
        "state/model parameters/land cover types/surface domain/albedo of bare ground [-]",
        "state/model parameters/land cover types/surface domain/albedo of canopy [-]",
        "state/model parameters/land cover types/surface domain/emissivity of bare ground [-]",
        "state/model parameters/land cover types/surface domain/emissivity of canopy [-]",
        "state/evaluators/surface-relative_permeability/value",
        "state/model parameters/WRM parameters/all layers/residual saturation [-]",
    ),
    # May legitimately be negative, so the >= 0 clamp must be skipped: the initial water table is
    # expressed as a hydrostatic head BELOW the surface (deck -0.5 m).
    signed_param_names=(
        "PKs/flow/initial conditions/hydrostatic head [m]",
    ),

    # ---- Output alignment ----
    grouping_axis_block_dim_name="",

    # ---- Ensemble run harness ----
    # ATS run length is the "cycle driver" -> "end time [s]" in the deck.
    run_length_control_label="end time",

    # ---- Output activation ----
    # ATS targets are declared as observation entries in the deck (not inactive-by-default
    # history flags), so create_case injects an observations block rather than a hist list.
    hist_activate=(),

    # ---- Secondary parameter surface ----
    # Single XML surface (no separate management/boundary file like EcoSIM's pft_mgmt).
    secondary_namelist_var="",

    # ---- Out-of-scope / external-boundary references (wiki validation) ----
    # ATS is built ON Amanzi; the wiki legitimately references Amanzi-framework symbols
    # and files it does NOT document (out of scope per UNIVERSAL_CONTEXT). These let the
    # wiki validators classify such references as EXPECTED-EXTERNAL, not fabrications, so
    # the verdict reflects real in-scope (ATS-source) accuracy.
    external_symbol_names=(
        # Amanzi framework methods (State / CompositeVector / Mesh / Operators) + CMake.
        "add_test",              # CMake command
        "SetScalarCoefficient", "UpdateMatrices",       # Amanzi PDE operators
        "CreateMFDmassMatrices", "AssembleSchur_", "SetOffDiagonals",  # Amanzi MatrixMFD
        "SetChanged", "WriteVis", "MyLength",           # Amanzi State / CompositeVector
        "getFaceNormal", "getEntityParent", "getCommSelf",  # Amanzi Mesh
    ),
    external_module_patterns=(
        r".*_registration\.hh$",   # generated PK/evaluator registries (ats_*_registration.hh)
        r".*_reg\.hh$",            # generated registries (models_transport_reg.hh, pks_chemistry_reg.hh)
        r"^_\w+\.(?:cc|hh)$",      # wiki wildcard/pattern placeholders (_pk.cc, _ti.cc, _physics.cc)
        r"^MatrixMFD.*\.hh$",      # Amanzi MatrixMFD framework headers
        r"^ats_version\.hh$",      # build-generated from ats_version.hh.in
        r"^pk_factory_ats\.hh$",   # Amanzi legacy PK-factory header (wiki index.md "Known issues")
        r"^pk_physical_base\.hh$", # Amanzi legacy PK-physical base header (wiki index.md "Known issues")
        # Bare-name shorthands the wiki's index.md "Known issues" annotation itself documents
        # as imprecise (real files are richards_pk.cc, overland_pressure_pk.cc,
        # overland_conductivity_model.hh). Listed so the validator does not re-flag a
        # disclosure the wiki already makes.
        r"^richards\.cc$", r"^overland_pressure\.cc$", r"^overland_conductivity_model\.cc$",
    ),

    # ---- Declared non-applicability (tools/validate_adapter_parity.py) ----
    # Fields a sibling adapter populates and ATS leaves empty, each with the reason
    # written down where a tool can read it.
    #
    # NOTE (corrected 2026-08-01): an earlier version of this block left the last three
    # UNDECLARED, calling them "real defects" and citing the "two dead gates" framing of
    # dev log 20260801k. That framing OVERSTATED it, and 20260801k now carries its own
    # correction banner. Both fields already had explicit rationales -- in the prose
    # comments above them, written in v0.1 (8f8c6355), before any of this. What was
    # actually missing was not the decision but its MACHINE-READABILITY: no tool could
    # read a comment, so the feature dispatching through the field degraded to a no-op
    # that printed "nothing to check". Converting those comments into declarations here
    # IS the fix, and it is the whole point of the gate -- whose rule is "an empty field
    # must be a decision somebody wrote down", not "must be proven correct".
    #
    # So each entry below carries its EXPIRY CONDITION: the thing that, if it happens or
    # is discovered, turns the declaration false and requires the field to be populated.
    # A declaration without one is how a rationale that was right in v0.1 quietly stops
    # being right. See [[feedback_param_description_can_lie_verify_in_source]].
    spec_na={
        # ATS is a SINGLE-DECK model. Every calibratable knob is a path into one Teuchos
        # ParameterList XML, so there is no second, third or fourth parameter FILE to declare
        # a namelist input for -- the notion of a surface does not partition anything here.
        # EXPIRES IF: ATS ever reads a separate mesh/subsurface-property file that a round
        # wants to sample, which is the shape EcoSIM's grid file has.
        "quaternary_namelist_var":
            "single-deck model — every calibratable knob is a path into one Teuchos "
            "ParameterList XML, so there is no separate soil/site parameter FILE to repoint "
            "and the notion of a fourth surface partitions nothing. EXPIRES IF: ATS reads a "
            "separate mesh or subsurface-property file that a round wants to sample, which is "
            "the shape EcoSIM's grid file has.",
        "quaternary_axis":
            "no quaternary surface, so no axis to name. EXPIRES IF: quaternary_namelist_var "
            "is ever populated here, at which point its axis must be named in the same commit.",
        "grouping_axis_dim_name":
            "no per-group array axis. ATS's grouping axis is the mesh region, and an "
            "observation is already reduced over its region by the deck's `functional`, "
            "so there is no NetCDF dimension to index and nothing for select_group_series "
            "to slice. EXPIRES IF: a target ever needs per-region array indexing "
            "(coupled ELM-ATS, where the surface column becomes a real group axis).",
        "secondary_namelist_var":
            "single parameter surface. The whole calibration surface is one Teuchos "
            "ParameterList XML deck; there is no second parameter file input to repoint "
            "(contrast EcoSIM's separate pft_mgmt NetCDF). EXPIRES IF: a site input "
            "surface (mesh/forcing) enters the calibration surface -- see the "
            "`write_parameter_file` surface= generalization on adapter-kit.",
        "tertiary_namelist_var":
            "same reason as secondary_namelist_var, one surface further: still one "
            "Teuchos ParameterList XML deck, no third parameter file input to repoint "
            "(contrast EcoSIM's separate MicrobePars.nc, wired 2026-08-13 to run its "
            "soil-BGC rate constants). EXPIRES IF: a second AND third site input surface "
            "both enter the calibration surface -- same generalization as above.",
        "hist_activate":
            "correct for the CURRENT deck-as-registry design: ATS calibration targets are "
            "declared as observation entries in the deck, not as inactive-by-default "
            "history flags, so create_case injects an observations block rather than a "
            "hist list and there is no separate activation step. EXPIRES AT the outputs "
            "repair (dev log 20260801m): once the output registry is source-derived, "
            "'available but unrequested' becomes a real distinction, and this MUST be "
            "populated from the reference deck's observations -- which is what revives "
            "the G3 inactive-output check in validate_model_targets.py. Populate as a "
            "CONSEQUENCE of that repair, not as a separate fix.",
        "input_reader_sources":
            "PLAUSIBLE BUT UNVALIDATED. ATS reads a Teuchos ParameterList XML deck rather "
            "than a var-by-var NetCDF parameter file, so the input-vs-binary compat guard "
            "has no obvious ATS analogue. Two things are NOT established and this "
            "declaration should not be read as claiming them: (a) whether ATS has an "
            "equivalent deck/binary mismatch failure mode at all, or whether Teuchos "
            "rejects an unknown/missing key natively at read time; (b) the ORIGINAL "
            "rationale in the comment above -- 'the NetCDF-read compat guard does not "
            "apply' -- is wrong about the MECHANISM: tools/model_check_input_compat.py is "
            "format-agnostic (regex over source for the names the binary requires, diffed "
            "against backend.parse_parameters), so ATS's `plist.get<T>(\"key\")` reads with "
            "no default ARE scrapeable in principle. What blocks a fill is name "
            "normalization -- source yields BARE leaf names, ATSParameterParser yields FULL "
            "deck paths, so a naive fill reports every key missing. EXPIRES IF: (a) is "
            "answered yes, or a real deck/binary mismatch is ever observed.",
        "input_read_pattern":
            "the two are a pair; the guard is a no-op unless BOTH are set. "
            "EXPIRES: same condition as input_reader_sources.",
    },
)
