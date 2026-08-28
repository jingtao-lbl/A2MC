"""PFLOTRAN ModelSpec.

Static, code-level description of PFLOTRAN for A2MC, pinned to commit `157a26f7`
(the commit Jianwen Du's miniLEO build was compiled from — see
`memory/dev_logs_adapterkitpflotran/20260731c`).

**STILL PARTIAL, and the gaps are per-step.** Filled so far: the wiki-validator
fields (`source_extensions`, `routine_decl_patterns`, `module_file_pattern`,
external boundary) at steps 1-4, and the parser classes at steps 5-6
(2026-07-31). Still `None` and due at their own steps: `version_detector_class`,
`bump_tier_classifier_class`, `milestone_metadata_class` (step 9) and
`domain_summary` (from `prompts.py`). `models/ecosim/spec.py` is the completed
reference to mirror.

Note the `onboard-model` arc order matters here: steps 1-2 scaffold
`models/<name>/`, step 3 generates the wiki, step 4 validates it -- so the spec
must exist BEFORE the wiki is validated. The parsers were then deliberately
completed BEFORE the curated seed (step 7), because the V2 curated-YAML
validator dispatches its parameter- and output-surface checks through them
(dev log `20260731h` section 5).

Structurally PFLOTRAN is Fortran like EcoSIM (not C++ like ATS), but unlike
EcoSIM it is built ON PETSc, so it needs the external-boundary declaration that
a self-contained model leaves empty.
"""

from __future__ import annotations

from ..base import ModelSpec
from .output_parser import PFLOTRANOutputParser
from .parameter_parser import PFLOTRANParameterParser
from .prompts import DOMAIN_SUMMARY
from .version import (
    PFLOTRANBumpTierClassifier,
    PFLOTRANMilestoneMetadata,
    PFLOTRANVersionDetector,
)


PFLOTRAN_SPEC = ModelSpec(
    # ---- Identity ----
    name="pflotran",
    display_name="PFLOTRAN",

    # ---- Parameter naming convention ----
    # A PFLOTRAN "parameter" is an input-deck card addressed by its block path
    # (CHEMISTRY/MINERAL_KINETICS/Glass_FB/RATE_CONSTANT), not a bare name, so the
    # regex is permissive; the real addressing scheme is specified in
    # `memory/dev_logs_adapterkitpflotran/20260730d` and its prototype parser.
    param_name_regex=r"^[A-Za-z][A-Za-z0-9_\[\]/#+\-]*$",
    param_categories={
        "mineral_kinetics": "Mineral kinetics (rate constants, surface area)",
        "water_retention": "Characteristic curves (van Genuchten / Brooks-Corey)",
        "permeability": "Permeability / porosity-permeability coupling",
        "porosity": "Porosity",
        "transport": "Dispersivity / diffusion",
        "chemistry": "Aqueous speciation + database",
        "boundary": "Flow / transport boundary conditions",
        "solver": "Numerical methods (NOT calibration knobs)",
    },

    # ---- Output naming convention ----
    # Targets come from the mass-balance file (quoted CSV headers like
    # "east Water Mass [kg/h]") and Tecplot snapshots, not a NetCDF history tape.
    output_name_regex=r"^[A-Za-z][A-Za-z0-9_ ()\[\]/+\-]*$",
    output_categories={
        "water_flux": "Water mass flux (boundary / global)",
        "solute": "Aqueous component mass",
        "mineral": "Mineral inventory / volume fraction",
        "state": "Saturation / pressure / porosity / permeability",
        "gas": "Gas-phase species",
    },
    key_external_outputs=(),

    # ---- Subgrid grouping axis ----
    # PFLOTRAN has no PFT axis. Its organizing dimension is the mesh region, and
    # mass-balance targets are already reduced over a region by the writer.
    grouping_axis="region",
    grouping_axis_dim_name="",
    default_groups=(),

    # ---- Mechanism / category framework (used by curated YAML, step 7) ----
    mechanism_keyword_map={
        "transition state": "TST_Mineral_Kinetics",
        "mineral": "Mineral_Precipitation_Dissolution",
        "surface area": "Reactive_Surface_Area",
        "van genuchten": "Van_Genuchten_WRM",
        "richards": "Richards_Subsurface_Flow",
        "general": "General_Multiphase_Flow",
        "girt": "GIRT_Reactive_Transport",
        "seepage": "Seepage_Face_Boundary",
        "speciation": "Aqueous_Speciation",
    },

    # ---- Domain context for AI prompts ----
    domain_summary=DOMAIN_SUMMARY,   # single source of truth in prompts.py

    # ---- Validator dispatch (Doc 19 6.5) ----
    # Filled at onboard steps 5-6 (2026-07-31). These are what
    # tools/validate_curated_yaml.py dimensions A (parameter surface) and
    # B (output surface) dispatch through -- without them the V2 validator
    # degrades to internal-consistency-only, which is why the parsers were
    # deliberately done BEFORE the curated seed (dev log 20260731h section 5).
    parameter_parser_class=PFLOTRANParameterParser,
    output_parser_class=PFLOTRANOutputParser,
    source_extensions=(".F90", ".f90"),          # PFLOTRAN is Fortran, like EcoSIM
    routine_decl_patterns=(
        r"\bsubroutine\s+(\w+)",
        r"\bfunction\s+(\w+)",
        r"\b(?:integer|real|logical|character)(?:\([^)]*\))?\s+function\s+(\w+)",
        # PFLOTRAN is OBJECT-ORIENTED Fortran: process models and couplers expose
        # their API as TYPE-BOUND PROCEDURES, e.g.
        #     procedure, public :: AcceptSolution => PMBaseFunctionThisOnly
        # (src/pflotran/pm_base.F90:52). The three patterns above match only the
        # implementation name (PMBaseFunctionThisOnly), so the BOUND name that the
        # wiki naturally cites (`AcceptSolution`, `InitializeTimestep`, `PreSolve`,
        # `FinalizeTimestep`, `Reset`) resolved as "unfound" and looked like a
        # fabrication. EcoSIM and FATES are procedural and never exposed this gap.
        r"\bprocedure\s*(?:,\s*[\w()]+)*\s*::\s*(\w+)",
    ),
    # PFLOTRAN does NOT use EcoSIM's *Mod.F90 convention -- files are bare
    # lower_snake_case (reaction_mineral.F90, characteristic_curves_common.F90,
    # patch.F90), so the module-file pattern must be general.
    module_file_pattern=r"\w+\.F90",

    # ---- Version association dispatch ----
    # Filled at onboard step 9. PFLOTRAN carries a semantic version alongside its
    # commit (pflotran_constants.F90:15-17), so unlike EcoSIM the classifier can
    # tell a same-major commit move from a MAJOR bump -- the distinction that
    # matters here, since this profile's commit and upstream master straddle 6->7.
    version_detector_class=PFLOTRANVersionDetector,
    bump_tier_classifier_class=PFLOTRANBumpTierClassifier,
    milestone_metadata_class=PFLOTRANMilestoneMetadata,
    milestone_label_format="pflotran-{commit_short}",

    # ---- Out-of-scope / external-boundary references (wiki validation) ----
    # PFLOTRAN is built ON PETSc and calls HDF5 directly. The wiki legitimately
    # names those symbols, which do NOT resolve in PFLOTRAN's own source. Without
    # this declaration the validator flags every one as unresolved, and the noise
    # buries genuine fabrications -- the failure the ATS/Amanzi boundary fields
    # were added for. EcoSIM leaves these empty because it is self-contained.
    external_symbol_names=(
        # PETSc solvers / nonlinear + linear algebra
        "SNESSolve", "SNESSetFunction", "SNESSetJacobian", "SNESGetConvergedReason",
        "KSPSolve", "KSPSetOperators", "TSSolve",
        # PETSc Vec / Mat / DM
        "VecGetArrayF90", "VecRestoreArrayF90", "VecCreate", "VecDuplicate",
        "VecSet", "VecNorm", "VecScatterBegin", "VecScatterEnd",
        "MatSetValues", "MatAssemblyBegin", "MatAssemblyEnd", "MatZeroEntries",
        "DMCreateGlobalVector", "DMDACreate3d",
        # PETSc options / bag / logging / init
        "PetscBagRegisterInt", "PetscBagRegisterReal", "PetscBagGetData",
        "MatZeroRowsLocal",
        "SNESSetFromOptions", "KSPSetFromOptions", "PCSetFromOptions",
        "PetscOptionsSetValue",
        "PetscOptionsGetString", "PetscOptionsGetInt", "PetscInitialize",
        "PetscFinalize", "PetscLogEventBegin", "PetscLogEventEnd",
        "PetscViewerHDF5Open", "PetscPrintf", "MPI_Comm_rank", "MPI_Comm_size",
        # HDF5 Fortran API (h5*_f) is matched by pattern below, not name-by-name.
    ),
    external_module_patterns=(
        r"^petsc.*\.(?:h|h90|F90)$",   # petscsys.h, petscsnes.h90, ...
        r"^hdf5\.F90$",                # HDF5 Fortran module
        r"^mpif?\.h$",                 # MPI headers
    ),
    # ---- Declared non-applicability (tools/validate_adapter_parity.py) ----
    # BLANKET declaration: this spec is partial ON PURPOSE (see the module docstring),
    # so the parity gate would otherwise report ~15 fields the onboarding arc has not
    # reached yet. The blanket passes but the validator PRINTS every field it excuses,
    # so the half-built state stays visible rather than reading as complete. Replace
    # this with per-field entries (or populate the fields) as the arc proceeds; two
    # of the excused fields are already known NOT to be deferrals:
    #   grouping_axis_dim_name  -- genuinely N/A (region-reduced mass-balance targets,
    #                              no per-group array axis), same as ATS.
    #   secondary_namelist_var  -- PFLOTRAN is a REAL two-surface model (pflotran.in
    #                              card deck AND the hand-modified thermodynamic
    #                              database .dat); see memory/dev_logs_adapterkitpflotran/
    #                              20260730c. It needs populating, not declaring.
    spec_na={
        "*": "onboarding in progress — parsers (steps 5-6), version detection (step 9) "
             "and the bounds/run-harness fields are filled at their own steps; "
             "models/ecosim/spec.py is the completed reference. "
             "See memory/dev_logs_adapterkitpflotran/20260731d.",
    },
)
