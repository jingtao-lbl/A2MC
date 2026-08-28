"""EcoSIM ModelSpec.

Static, code-level description of EcoSIM for A2MC. Content is grounded in the
source-cited audit findings in `memory/dev_logs/20260424g_EcoSIM_Codebase_Wiki_Rewrite.md`
(the 15 calibration-relevant findings) and the EcoSIM codebase wiki at commit
`2dea74d9`.

EcoSIM (the F90 successor to Grant's `ecosys`) is structurally unlike FATES:
parameter names carry no shared prefix, so `param_name_regex` is permissive and
the real parameter/output filtering lives in the parser classes.
"""

from __future__ import annotations

from ..base import ModelSpec
from .output_parser import EcoSIMOutputParser
from .parameter_parser import EcoSIMParameterParser
from .prompts import DOMAIN_SUMMARY
from .version import (
    EcoSIMBumpTierClassifier,
    EcoSIMMilestoneMetadata,
    EcoSIMVersionDetector,
)


ECOSIM_SPEC = ModelSpec(
    # ---- Identity ----
    name="ecosim",
    display_name="EcoSIM",

    # ---- Secondary parameter surface ----
    # EcoSIM has a second parameter file (the stand-management pft_mgmt NetCDF,
    # holding planting density PPI in its pft_pltinfo string). A per-case
    # secondary file is repointed at this namelist input in the runfile.
    secondary_namelist_var="pft_mgmt_in",

    # ---- Tertiary parameter surface ----
    # EcoSIM has a third parameter file (MicrobePars.nc, the microbial-kinetics
    # NetCDF -- RCCZ/VMXO/RMOM/GO2X/SPORC/SPOMC and the rest of the soil-BGC rate
    # constants). Verified real, not guessed: EcoSIMCtrlMod.F90:56 declares
    # `micpar_file_in` (default '', optional -- NitroPars.F90:277 early-returns
    # to hardcoded defaults when empty). A per-case tertiary file is repointed at
    # this namelist input in the runfile, same mechanism as the secondary surface.
    tertiary_namelist_var="micpar_file_in",

    # ---- Parameter naming convention ----
    # EcoSIM parameter names are bare Fortran identifiers with no shared prefix
    # (VCMX, XKCO2, ICTYP). The regex is intentionally permissive; the real
    # filtering (which variables are calibratable parameters) is done by
    # EcoSIMParameterParser (string/metadata vars flagged, PFT axis detected).
    param_name_regex=r"^[A-Za-z][A-Za-z0-9_]*$",
    param_categories={
        # Category keys emitted by EcoSIMParameterParser (inferred from long_name).
        "photosynthesis": "Photosynthesis (Rubisco/PEP kinetics)",
        "stomatal": "Stomatal conductance",
        "radiation": "Leaf optical / radiation",
        "phenology": "Phenology",
        "allocation": "Allocation (stage-prescribed)",
        "turnover": "Turnover",
        "roots": "Root profile",
        "nutrient": "Nutrient acquisition (N2 fix / mycorrhizae)",
        "respiration": "Respiration",
        "pfts": "PFT type flags (ICTYP/IGTYP/... — integer switches per PFT)",
        "temperature": "Thermal adaptation",
    },

    # ---- Output naming convention ----
    # EcoSIM history variables are mixed-case with axis suffixes (_pft, _col,
    # _vr, _litr, _brch) rather than a shared prefix. Permissive regex; the
    # grouping axis is read from dims/suffix by EcoSIMOutputParser.
    output_name_regex=r"^[A-Za-z][A-Za-z0-9_]*$",
    output_categories={
        "carbon_flux": "Carbon flux",
        "carbon_pool": "Carbon pool",
        "nitrogen_pool": "Nitrogen pool",
        "phosphorus_pool": "Phosphorus pool",
        "microbial": "Microbial functional-group pools",
        "soil_nutrient": "Soil mineral nutrient",
        "nutrient": "Plant nutrient uptake",
        "hydrology": "Hydrology",
        "soil_physical": "Soil physical state",
        "atmosphere": "Atmospheric boundary condition",
        "management": "Management (fertilization/tillage)",
        "meteorology": "Meteorology",
        "canopy": "Canopy",
        "biomass": "Biomass",
    },
    # EcoSIM standalone driver writes its own outputs; no host-model variables.
    key_external_outputs=(),

    # ---- Subgrid grouping axis ----
    # The plant axis. Output tape uses `pft`; the pft input file uses `npfts`;
    # JSON inputs use `maxpfts`. EcoSIMParameterParser/OutputParser accept all.
    # Hard cap JP=5 plant species (GridConsts.F90; finding #11).
    grouping_axis="pft",
    grouping_axis_dim_name="pft",
    default_groups=(),   # site config supplies the calibrated PFTs (BioCON has 3)

    # ---- Mechanism / category framework (used by curated YAML) ----
    # Keyword -> mechanism name, drawn from the audit findings. These seed the
    # curated_relationships YAML (pipeline Step 3) and let the reasoning agent
    # dispatch context per mechanism.
    mechanism_keyword_map={
        "campbell": "Campbell_Soil_Retention",          # finding #1
        "macropore": "Explicit_Macropore_Flow",         # finding #3
        "rubisco": "Grant_Rubisco_C3_Kinetics",         # finding #7
        "pep": "PEP_C4_Refixation",                     # finding #7
        "turgor": "Turgor_Based_Stomatal_Stress",       # finding #7
        "jle": "Johnson_Lewin_Eyring_Decomposition",    # finding #5
        "microbial": "Microbially_Explicit_Decomposition",  # finding #5
        "langmuir": "Langmuir_P_Sorption",              # finding #6
        "allocation": "Stage_Prescribed_Allocation",    # finding #8
        "maintresp": "Structural_N_Maintenance_Respiration",  # finding #8
    },

    # ---- Domain context for AI prompts ----
    domain_summary=DOMAIN_SUMMARY,   # single source of truth in prompts.py

    # ---- Validator dispatch (Doc 19 6.5) ----
    parameter_parser_class=EcoSIMParameterParser,
    output_parser_class=EcoSIMOutputParser,
    source_extensions=(".F90", ".f90"),          # EcoSIM is Fortran
    routine_decl_patterns=(
        r"\bsubroutine\s+(\w+)",
        r"\bfunction\s+(\w+)",
        r"\b(?:integer|real|logical|character)(?:\([^)]*\))?\s+function\s+(\w+)",
    ),
    module_file_pattern=r"\w+Mod\.F90",          # EcoSIM uses *Mod.F90 (SoilPhysParaMod.F90, ...)

    # ---- Version association dispatch ----
    version_detector_class=EcoSIMVersionDetector,
    bump_tier_classifier_class=EcoSIMBumpTierClassifier,
    milestone_label_format="ecosim-{commit_short}",
    milestone_metadata_class=EcoSIMMilestoneMetadata,
    # ---- Input↔binary compat guard ----
    input_reader_sources=("f90src/IOutils/PlantInfoMod.F90",),
    input_read_pattern=r"ncd_getvar\(\s*pft_nfid\s*,\s*'([A-Za-z0-9_]+)'",
    # ---- Bounds generation heuristics ----
    fraction_param_names=("RUBP", "CHL", "ETMX", "PEPC", "CHL4", "ALBP", "PORT", "CFI", "FCO2"),
    fraction_categories=("stoichiometry",),
    signed_param_names=("OSMO",),
    # ---- Output alignment (EcoSIM _pft tapes are flat (time, pft) — directly indexable) ----
    grouping_axis_block_dim_name="",
    # ---- Ensemble run harness ----
    run_length_control_label="forc_periods",
    # ---- Output activation (inactive-by-default calibration vars → hist_fincl1) ----
    # These per-PFT calibration outputs are registered default='inactive' in
    # HistDataType.F90 (verified in 2dea74d9 source), so create_case adds them to the
    # h0 hist_fincl1 list. Active-by-default pools (SHOOT_C/Plant_C/Root_C/Root_N/Root_P/
    # NPP/CAN_cumGPP/LeafN/LAIstk) are NOT listed — they write without activation.
    # See memory/dev_logs_adapterkit/20260713c/e.
    hist_activate=(
        "LEAF_C_pft", "LEAF_N_pft", "LEAF_P_pft", "Plant_N_pft", "Plant_P_pft",
        "CAN_GPP_pft", "LAI_xstk_pft", "Root_NONSTC_pft", "GRAIN_C_pft", "LITRf_N_FLX_pft",
    ),

    # ---- Declared non-applicability (tools/validate_adapter_parity.py) ----
    # Fields the ATS and PFLOTRAN adapters populate and EcoSIM legitimately leaves
    # empty, stated here so "not applicable" is distinguishable from "forgotten".
    spec_na={
        "external_symbol_names":
            "self-contained model. EcoSIM is standalone Fortran with no host framework, "
            "so every symbol its wiki names should resolve in EcoSIM's own source and an "
            "unresolved one IS a fabrication. Contrast ATS (built on Amanzi) and PFLOTRAN "
            "(built on PETSc), which must declare their framework boundary or the "
            "wiki-vs-source validator flags the whole framework API as fabricated. "
            "EXPIRES IF: the EcoSIM wiki is ever extended to cover a coupled or host-driven "
            "build whose symbols live outside EcoSIM's own source — at that point an "
            "unresolved reference stops being proof of fabrication and this must be "
            "populated, or every host call becomes a permanent false positive.",
        "external_module_patterns":
            "self-contained model. Every module file the wiki references is an EcoSIM "
            "*Mod.F90. EXPIRES: same condition as external_symbol_names (the two are a "
            "pair; the wiki validator needs both to classify a host reference).",
    },
)
