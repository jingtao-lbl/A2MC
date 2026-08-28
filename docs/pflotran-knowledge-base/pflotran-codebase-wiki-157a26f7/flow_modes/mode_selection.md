**Source pin:** PFLOTRAN commit 157a26f7
**Scope:** Flow-mode selection, registration, and the `SUBSURFACE_FLOW` / `OPTIONS` / `NEWTON_SOLVER` keyword routing
**Last verified:** 2026-07-31

---

## 1. Where `MODE` is parsed

The flow mode is chosen inside the `SIMULATION` → `PROCESS_MODELS` → `SUBSURFACE_FLOW` block. The reader is `FactorySubsurfReadFlowPM` (`src/pflotran/factory_subsurface_read.F90:29`). It accepts exactly **two** cards, matched as upper-cased string literals (`src/pflotran/factory_subsurface_read.F90:71-126`):

| Card | Line | Effect |
|---|---|---|
| `MODE` | `factory_subsurface_read.F90:72` | Reads the next word, upper-cases it, and allocates the matching process model |
| `OPTIONS` | `factory_subsurface_read.F90:117` | Dispatches to the selected PM's `ReadSimulationOptionsBlock` |

`OPTIONS` before `MODE` is a fatal error: *"MODE keyword must be read first"* (`factory_subsurface_read.F90:118-122`). Omitting `MODE` entirely is also fatal (`factory_subsurface_read.F90:130-134`).

```
SIMULATION
  SIMULATION_TYPE SUBSURFACE
  PROCESS_MODELS
    SUBSURFACE_FLOW flow
      MODE GENERAL
      OPTIONS
        ISOTHERMAL
      /
    /
  /
END
```

## 2. Complete list of valid `MODE` strings at this commit

Every string below is a literal `case(...)` in `factory_subsurface_read.F90:85-115`. Nothing else parses.

| Deck string | Line | Constructor | Notes |
|---|---|---|---|
| `GENERAL` | `:86` | `PMGeneralCreate()` | Two-phase (liquid + gas), water + air + energy. The mode used by the basalt-weathering column. |
| `HYDRATE` | `:88` | `PMHydrateCreate()` | Methane-hydrate extension of GENERAL |
| `WIPP_FLOW` | `:90` | `PMWIPPFloCreate()` | BRAGFLO-lineage two-phase |
| `BRAGFLO` | `:92` | — | **Not a mode.** Fatal error directing the user to `WIPP_FLOW` (`:93-95`) |
| `MPHASE` | `:96` | `PMMphaseCreate()` | Supercritical-CO2 / water, 3 dof |
| `RICHARDS` | `:98` | `PMRichardsCreate()` | Single-phase variably saturated water |
| `TH` | `:100` | `PMTHCreate()` | Thermal-hydrologic (water + energy) |
| `RICHARDS_TS` | `:102` | `PMRichardsTSCreate()` | Richards with PETSc `TS` time integration (external PETSc framework) |
| `TH_TS` | `:104` | `PMTHTSCreate()` | TH with PETSc `TS` |
| `ZFLOW` | `:106` | `PMZFlowCreate()` | Configurable single-phase (liquid / heat / solute processes selected individually) |
| `PORE_FLOW` | `:108` | `PMPNFCreate()` | Pore-network flow |
| `STOMP-CO2` or `SCO2` | `:110` | `PMSCO2Create()` | Two literals, one mode |

Any other word reaches `case default` and calls `InputKeywordUnrecognized` (`:112-114`).

### Derivative default set at parse time

`GENERAL`, `HYDRATE`, and `WIPP_FLOW` set `option%flow%numerical_derivatives = PETSC_TRUE` immediately after the mode word is read (`factory_subsurface_read.F90:77-84`), overriding the framework-wide default of `PETSC_FALSE` set in `OptionFlowInitRealization` (`src/pflotran/option_flow.F90:158`). The in-source comment at `factory_subsurface_read.F90:78-82` explains this is deliberate. **Consequence for GENERAL: the Jacobian is numerical unless you explicitly ask for analytical** (see §4).

## 3. Mode → integer id and dof count

`option%iflowmode` is an integer set from the PM class. The enumeration is in `src/pflotran/pflotran_constants.F90:164-177`:

| Constant | Value | Line |
|---|---|---|
| `NULL_MODE` | 0 | `:164` |
| `MPH_MODE` | 1 | `:167` |
| `RICHARDS_MODE` | 2 | `:168` |
| `G_MODE` | 3 | `:169` |
| `TH_MODE` | 4 | `:170` |
| `WF_MODE` | 5 | `:171` |
| `RICHARDS_TS_MODE` | 6 | `:172` |
| `TH_TS_MODE` | 7 | `:173` |
| `H_MODE` | 8 | `:174` |
| `ZFLOW_MODE` | 9 | `:175` |
| `PNF_MODE` | 10 | `:176` |
| `SCO2_MODE` | 11 | `:177` |

Dimensioning happens in `FactorySubsurfaceSetFlowMode` (`src/pflotran/factory_subsurface.F90:187-272`), which branches on the *Fortran class* of the allocated PM, not on the deck string:

| Mode | `nphase` | `nflowdof` | `nflowspec` | `isothermal` default | Source |
|---|---|---|---|---|---|
| `WIPP_FLOW` | 2 | 2 | 2 | (unset here) | `factory_subsurface.F90:189-196` |
| `GENERAL` | 2 (3 with `SOLUTE`) | 3 (4 with `SOLUTE`) | 2 (3) | `PETSC_FALSE` | delegated to `PMGeneralSetFlowMode`, `pm_general.F90:167-207` |
| `MPHASE` | 2 | 3 | 2 | `PETSC_FALSE` (`:208`) | `factory_subsurface.F90:201-210` |
| `RICHARDS` | 1 | 1 | 1 | **`PETSC_TRUE`** (`:216`) | `factory_subsurface.F90:211-216` |
| `ZFLOW` | 1 | 0…3 (per enabled process) | 0…1 | `PETSC_TRUE` if no heat eq (`:229`) | `factory_subsurface.F90:217-239` |
| `PORE_FLOW` | 1 | 1 | 1 | `PETSC_TRUE` (`:245`) | `factory_subsurface.F90:240-245` |
| `TH` | 1 | 2 | 1 | `PETSC_FALSE` (`:251`) | `factory_subsurface.F90:246-252` |
| `RICHARDS_TS` | 1 | 1 | 1 | `PETSC_TRUE` (`:258`) | `factory_subsurface.F90:253-258` |
| `TH_TS` | 1 | 2 | 1 | `PETSC_FALSE` (`:264`) | `factory_subsurface.F90:259-265` |
| `SCO2` | — | — | — | delegated to `PMSCO2SetFlowMode` | `factory_subsurface.F90:266-267` |

`nflowdof == 0` or `nphase == 0` after this switch is fatal (`factory_subsurface.F90:274-280`).

## 4. Which `OPTIONS` keywords are visible in which mode

Each mode's `OPTIONS` reader first delegates to two shared select-cases, then falls through to its own mode-specific list. The chain (for GENERAL, `pm_general.F90:353-484`) is:

1. `PMBaseReadSimOptionsSelectCase` (`src/pflotran/pm_base.F90:187-214`) — available in **every** mode:

   | Keyword | Line | Effect |
   |---|---|---|
   | `STEADY_STATE` | `pm_base.F90:203` | `pm%steady_state = PETSC_TRUE` |
   | `SKIP_RESTART` | `pm_base.F90:205` | `pm%skip_restart = PETSC_TRUE` |
   | `LOGGING_VERBOSITY <int>` | `pm_base.F90:207` | verbosity level |

2. `PMSubsurfFlowReadSimOptionsSC` (`src/pflotran/pm_subsurface_flow.F90:143-192`) — available in every **flow** mode:

   | Keyword | Line | Effect |
   |---|---|---|
   | `COUNT_UPWIND_DIRECTION_FLIP` | `pm_subsurface_flow.F90:173` | `count_upwind_direction_flip = PETSC_TRUE` |
   | `FIX_UPWIND_DIRECTION` | `:175` | freeze upwind direction between updates |
   | `MULTIPLE_CONTINUUM` | `:177` | `option%use_sc = PETSC_TRUE` (secondary continuum) |
   | `REPLACE_INIT_PARAMS_ON_RESTART` | `:179` | |
   | `REVERT_PARAMETERS_ON_RESTART` | `:181` | |
   | `UNFIX_UPWIND_DIRECTION` | `:183` | `fix_upwind_direction = PETSC_FALSE` |
   | `UPWIND_DIR_UPDATE_FREQUENCY <int>` | `:185` | |

3. The mode's own list (GENERAL: `pm_general.F90:357-484`, documented in `general_mode.md` §5; RICHARDS/TH/MPHASE: `richards_and_th.md` §5).

## 5. `ANALYTICAL_JACOBIAN` is **not** an `OPTIONS` sub-card

This is a common misreading and worth stating flatly. Grepping the tree, the literal `'ANALYTICAL_JACOBIAN'` appears exactly once, at `src/pflotran/pm_subsurface_flow.F90:305`, inside `PMSubsurfaceFlowReadNewtonSelectCase` (`pm_subsurface_flow.F90:257-322`) — the **`NEWTON_SOLVER`** reader, not the `OPTIONS` reader. Putting it in `SUBSURFACE_FLOW/OPTIONS` reaches `case default` in `PMGeneralReadSimOptionsBlock` and aborts with `InputKeywordUnrecognized` (`pm_general.F90:482-483`).

The correct placement is the `NUMERICAL_METHODS FLOW` → `NEWTON_SOLVER` block, routed by `PMCBaseReadNumericalMethods` (`src/pflotran/pmc_base.F90:174-273`; the `NEWTON_SOLVER` case is `pmc_base.F90:261-264`, which calls `pm_list%ReadNewtonBlock` first and only then the generic `SolverReadNewtonSelectCase`):

```
NUMERICAL_METHODS FLOW
  NEWTON_SOLVER
    ANALYTICAL_JACOBIAN
  /
END
```

Jacobian-selection keywords in that block:

| Keyword | Line | Effect |
|---|---|---|
| `NUMERICAL_JACOBIAN` | `pm_subsurface_flow.F90:302` | `option%flow%numerical_derivatives = PETSC_TRUE` |
| `ANALYTICAL_JACOBIAN` | `pm_subsurface_flow.F90:305` | `option%flow%numerical_derivatives = PETSC_FALSE` |
| `ANALYTICAL_DERIVATIVES` | `pm_subsurface_flow.F90:308` | **Deprecated**; `InputKeywordDeprecated` redirects to `ANALYTICAL_JACOBIAN` |

Also in that same shared Newton block (`pm_subsurface_flow.F90:286-320`): `PRESSURE_DAMPENING_FACTOR`, `SATURATION_CHANGE_LIMIT`, `PRESSURE_CHANGE_LIMIT`, `TEMPERATURE_CHANGE_LIMIT`, `USE_INFINITY_NORM_CONVERGENCE`, `USE_EUCLIDEAN_NORM_CONVERGENCE`.

Note that `NUMERICAL_METHODS` is a `SUBSURFACE`-level card (`factory_subsurface_read.F90:1547`), and that the old top-level `TIMESTEPPER` / `NEWTON_SOLVER` / `LINEAR_SOLVER` cards now abort with a refactor message (`factory_subsurface_read.F90:1522-1527`).

**GENERAL-mode caveat on analytical derivatives.** `general_analytical_derivatives` is simply `.not.option%flow%numerical_derivatives` (`src/pflotran/general.F90:82`). Several GENERAL code paths refuse to run analytically: surface tension and the Kelvin equation abort (`general_aux.F90:701-708`), and `HYDROSTATIC_SEEPAGE_BC` / `HYDROSTATIC_CONDUCTANCE_BC` / `DIRICHLET_SEEPAGE_BC` abort with *"needs to be verified in GeneralBCFlux()"* if the seepage clamp actually fires (`general_common.F90:2716-2722`, `2729-2733`). For a seepage-face deck, keep the default numerical Jacobian.

## 6. Which flow-condition reader each mode uses

`FLOW_CONDITION` blocks are parsed by different subroutines depending on `option%iflowmode` (`factory_subsurface_read.F90:1204-1213`):

| Mode(s) | Reader | Location |
|---|---|---|
| `G_MODE`, `WF_MODE` | `FlowConditionGeneralRead` | `src/pflotran/condition.F90:2024-2634` |
| `H_MODE` | `FlowConditionHydrateRead` | `condition.F90:3170-3774` |
| `SCO2_MODE` | `FlowConditionSCO2Read` | `condition.F90:2638-3166` |
| everything else (RICHARDS, TH, MPHASE, ZFLOW, PNF, …) | `FlowConditionRead` | `condition.F90:1061-2020` |

The two readers accept **different BC-type vocabularies**. See `boundary_conditions.md` §1 for the side-by-side list.

## 7. Absence notes

- There is no `immis*.F90` file in this tree. `ls src/pflotran | grep -i immis` returns nothing. "Immiscible" in PFLOTRAN 6 is an **option of GENERAL mode** (`IMMISCIBLE`, `pm_general.F90:382-383`), not a mode of its own. Do not expect a standalone immiscible flow mode.
- There is no `MODE TH_FREEZING`. Freezing is an `OPTIONS` sub-card of `MODE TH` (`FREEZING`, `pm_th.F90:157`).
- The mode switch is dispatched on a Fortran `select type` over PM classes in `factory_subsurface.F90:187`, so adding a mode requires touching both `factory_subsurface_read.F90` (string → constructor) and `factory_subsurface.F90` (class → dof counts).
