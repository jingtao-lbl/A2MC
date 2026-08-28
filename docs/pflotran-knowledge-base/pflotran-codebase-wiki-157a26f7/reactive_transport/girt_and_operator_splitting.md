**Source pin:** PFLOTRAN commit 157a26f7
**Scope:** reactive transport — GIRT vs OSRT solve structure, `SUBSURFACE_TRANSPORT` `OPTIONS` cards
**Last verified:** 2026-07-31

---

# GIRT and OSRT: the two reactive-transport couplings

This page documents the *transport solve* — how PFLOTRAN advances the reactive-transport
equations in time and how the reaction operator is coupled to the transport operator. The
geochemical reaction network itself (speciation, mineral kinetics, sorption) lives in
`reaction*.F90` and is out of scope here; this page treats `RStep()` /
`RTAccumulation()` as black boxes at their call sites.

> **PETSc is external.** `SNESSolve`, `KSPSolve`, `MatSetValuesLocal`, `VecGetArrayF90`,
> `VecStrideGather`, `MPI_Allreduce` and everything prefixed `Petsc*`/`KSP*`/`SNES*`/`Mat*`/`Vec*`
> come from the PETSc library, not from PFLOTRAN. PFLOTRAN supplies the residual/Jacobian
> callbacks and the matrix/vector assembly; PETSc owns the nonlinear and linear solves.

---

## 1. Where the mode is chosen

The transport mode is read from the `SIMULATION` block:

```
SIMULATION
  SIMULATION_TYPE SUBSURFACE
  PROCESS_MODELS
    SUBSURFACE_TRANSPORT
      MODE GIRT          # or OSRT, or NWT
      OPTIONS
        ...
      /
    /
  /
END
```

`SUBSURFACE_TRANSPORT` is dispatched at `src/pflotran/factory_forward.F90:279-280`, which calls
`FactorySubsurfReadTransportPM()` (`src/pflotran/factory_subsurface_read.F90:140`). The `MODE`
card is a three-way `select case` (`src/pflotran/factory_subsurface_read.F90:176-197`):

| `MODE` | process model created | `option%itranmode` | `option%transport%reaction_coupling` | line |
|---|---|---|---|---|
| `GIRT` | `PMRTCreate()` | `RT_MODE` | `GLOBAL_IMPLICIT` | `factory_subsurface_read.F90:182-185` |
| `OSRT` | `PMOSRTCreate()` | `RT_MODE` | `OPERATOR_SPLIT` | `factory_subsurface_read.F90:186-189` |
| `NWT` | `PMNWTCreate()` | `NWT_MODE` | `GLOBAL_IMPLICIT` | `factory_subsurface_read.F90:190-193` |

Anything else is a fatal `InputKeywordUnrecognized`
(`src/pflotran/factory_subsurface_read.F90:194-196`). `MODE` must be read **before** `OPTIONS`
or the code aborts (`src/pflotran/factory_subsurface_read.F90:199-204`). A bare
`GLOBAL_IMPLICIT` card (the pre-refactor syntax) triggers a printed template and a fatal error
(`src/pflotran/factory_subsurface_read.F90:206-208, 215-236`).

`GLOBAL_IMPLICIT = 0` and `OPERATOR_SPLIT = 1` are integer parameters
(`src/pflotran/pflotran_constants.F90:238-239`).

`pm_osrt_type` **extends** `pm_rt_type` (`src/pflotran/pm_osrt.F90:14`) and differs only by
setting `operator_split = PETSC_TRUE` (`src/pflotran/pm_osrt.F90:82`; the base sets
`PETSC_FALSE` at `src/pflotran/pm_rt.F90:161`) plus three extra Vecs/counters
(`src/pflotran/pm_osrt.F90:15-19`). That single flag selects the process-model *coupler*:

```fortran
    class is(pm_rt_type)
      if (pm%operator_split) then
        pmc_subsurface => PMCSubsurfaceOSRTCreate()
      else
        pmc_subsurface => PMCSubsurfaceCreate()
      endif
```
(`src/pflotran/factory_subsurface_linkage.F90:464-470`)

So **the mode does not change the discretization or the physics kernels** — GIRT and OSRT call
the same `TDispersion`/`TFluxCoef` machinery. What changes is the *time-stepping driver* and
which terms it retains.

Both `GIRT` and `OSRT` require a `CHEMISTRY` block; without one, `PMRTSetup` aborts with
"SUBSURFACE_TRANSPORT MODE GIRT/OSRT is specified ... without a corresponding CHEMISTRY block"
(`src/pflotran/pm_rt.F90:413-418`), and `factory_subsurface.F90:503-507` issues the parallel check.

---

## 2. GIRT — global implicit reactive transport, as implemented

"Global implicit" means: **one Newton solve per time step over all `ncomp` degrees of freedom
per cell, with transport and reaction terms in the same residual.**

- The coupler is `PMCSubsurfaceCreate()` and the solver is a PETSc `SNES`
  (`src/pflotran/pmc_subsurface.F90:390-391`), with a **block** matrix
  (`MATBAIJ`) whose block size is the number of transport dofs
  (`src/pflotran/pmc_subsurface.F90:392-399`).
- Newton line search is forced to `SNESLINESEARCHBASIC` when `SNESNEWTONLS` is requested,
  with the in-source rationale that a line-search update could drive concentrations negative
  (`src/pflotran/pmc_subsurface.F90:456-464`).
- The residual callback is `PMRTResidual → RTResidual`
  (`src/pflotran/pm_rt.F90:68, 934-951`); the Jacobian is `PMRTJacobian → RTJacobian`
  (`src/pflotran/pm_rt.F90:69, 955-976`).
- The matrix-zeroing array is sized `ndof = reaction%ncomp` under `GLOBAL_IMPLICIT`
  and `ndof = 1` otherwise (`src/pflotran/reactive_transport.F90:469-478`) — a direct
  statement of "one coupled block" vs "one scalar system per component".

`RTResidual` is a two-pass assembly (`src/pflotran/reactive_transport.F90:2083-2171`):

1. `RTResidualFlux` — internal + boundary advective/dispersive fluxes
   (`src/pflotran/reactive_transport.F90:2141, 2175-2412`).
2. `RTResidualNonFlux` — accumulation, secondary continuum, source/sinks, reactions
   (`src/pflotran/reactive_transport.F90:2144, 2416-...`).

The accumulation term subtracts the frozen $k$-level storage and adds the $k{+}1$ storage:

$$
R_{\text{accum}} = \frac{A^{k+1} - A^{k}}{\Delta t_{\text{tran}}}
$$

implemented as `r_p = r_p - accum_p / option%tran_dt`
(`src/pflotran/reactive_transport.F90:2511-2513`) followed by a per-cell `RTAccumulation` call
divided by `option%tran_dt` (`src/pflotran/reactive_transport.F90:2524-2530`). The frozen
$A^{k}$ is built once per step in `RTUpdateFixedAccumulation`
(`src/pflotran/reactive_transport.F90:876, 1060-1165`).

`RTAccumulation` (`src/pflotran/reaction.F90:5464-5526`) sums, per component:

- liquid storage $\phi S_\ell \cdot 1000 \cdot V \cdot T_\ell$
  (`src/pflotran/reaction.F90:5499-5503`),
- immobile species $\times V$ (`src/pflotran/reaction.F90:5505-5511`),
- **gas storage** $\phi S_g \cdot 1000 \cdot V \cdot T_g$ when `nactive_gas > 0`
  (`src/pflotran/reaction.F90:5512-5517`),
- equilibrium-sorbed mass $\times V$ (`src/pflotran/reaction.F90:5518-5523`).

If `global_auxvar%sat(LIQUID_PHASE) < rt_min_saturation` the whole accumulation returns zero
(`src/pflotran/reaction.F90:5494`).

**Trade-off implied by the source:** GIRT carries every coupling term (including gas-phase
storage and gas-phase flux) inside one Newton iteration, so there is no splitting error, but
each iteration requires a block-Jacobian assembly over `ncomp × ncomp` per cell and a nonlinear
solve that can fail globally. The `RTResidualNonFlux`/`RTJacobianNonFlux` pair is where the
reaction terms enter, so reaction stiffness propagates into the global Newton convergence.

---

## 3. OSRT — operator-split reactive transport, as implemented

"Operator split" here is a **sequential non-iterative split**: transport all components
linearly, then react each cell independently, with no outer iteration between the two.

The whole algorithm is `PMCSubsurfaceOSRTStepDT`
(`src/pflotran/pmc_subsurface_osrt.F90:144-438`). Reading it in order:

1. **The timestepper must be KSP, not SNES.** A non-`timestepper_KSP_type` aborts with
   "A KSP timestepper must be used for operator-split reactive transport"
   (`src/pflotran/pmc_subsurface_osrt.F90:101-108`). The matrix is created `ONEDOF` and
   `MATAIJ` (`src/pflotran/pmc_subsurface_osrt.F90:119-127`) — one scalar system, reused per
   component.

2. **Fixed accumulation, liquid only.** `iphase` is a *hard parameter* equal to 1
   (`src/pflotran/pmc_subsurface_osrt.F90:186`) and the fixed-accumulation loop stores
   $\phi S_\ell \cdot 1000 \cdot V \cdot T_\ell$ over `1:naqcomp` only
   (`src/pflotran/pmc_subsurface_osrt.F90:265-279`). **Gas-phase storage is absent from the
   OSRT accumulation term**, unlike GIRT (§2).

3. **Transport coefficients refreshed at $t^{k+1}$.** `PMRTWeightFlowParameters(...,TIME_TpDT)`
   then `RTUpdateTransportCoefs` (`src/pflotran/pmc_subsurface_osrt.F90:286-288`).

4. **RHS assembly.** `rhs = fixed_accum / tran_dt`, then `RTCalculateRHS_t1` adds inflowing
   boundary and injecting source terms (`src/pflotran/pmc_subsurface_osrt.F90:291-295`).

5. **Species-dependent diffusion is rejected.** If `rt_parameter%ndiffcoef > 1`, OSRT aborts:
   "Operator-split reactive transport is not currently configured to handle species-dependent
   diffusion." (`src/pflotran/pmc_subsurface_osrt.F90:299-303`).

6. **One matrix, `naqcomp` linear solves.** `RTCalculateTransportMatrix(realization,solver%M)`
   (`src/pflotran/pmc_subsurface_osrt.F90:304`), then a loop
   `do idof = 1, rt_parameter%naqcomp` that `VecStrideGather`s the component's RHS and calls
   PETSc `KSPSolve` (`src/pflotran/pmc_subsurface_osrt.F90:308-338`). The solution is written
   straight into `rt_auxvars(ghosted_id)%total(idof,iphase)`
   (`src/pflotran/pmc_subsurface_osrt.F90:326-332`) — i.e. the transport step advances the
   *total aqueous component concentration*, not the free-ion molality.

7. **Reaction step, cell by cell.** `RStep()` is called per local cell with the previous
   free-ion molality as the initial guess (`src/pflotran/pmc_subsurface_osrt.F90:353-383`);
   on success the solution vector is set back to free-ion molality
   (`src/pflotran/pmc_subsurface_osrt.F90:376-382`).

8. **Failure handling: cut and retry the whole step.** `rstep_error` is `MPI_Allreduce`d
   (`src/pflotran/pmc_subsurface_osrt.F90:386-391`); on failure the timestep is cut and the
   entire transport+react sequence repeats (`src/pflotran/pmc_subsurface_osrt.F90:398-416`).
   If the failure occurred with more than one kinetic substep, OSRT gives up with a hard error
   telling the user to switch: *"RStep() failed with > 1 substeps. You must use global implicit
   reactive transport (GIRT)."* (`src/pflotran/pmc_subsurface_osrt.F90:399-403`). Linear
   iterations spent on a cut step are accumulated as
   `sum_wasted_linear_iterations` (`src/pflotran/pmc_subsurface_osrt.F90:404-405`).

9. **Kinetic state is updated inside `RStep`, not at the end of the step.** `PMRTUpdateSolution`
   skips `RTUpdateKineticState` when `reaction_coupling == OPERATOR_SPLIT`, with the comment
   "for operator splitting, kinetic state is updated at the end of each reaction step at each
   grid cell" (`src/pflotran/pm_rt.F90:1552-1556`).

### Terms OSRT drops relative to GIRT

These are structural, and they are the practical reason to prefer GIRT for anything
multi-phase:

| Term | GIRT | OSRT | evidence |
|---|---|---|---|
| Gas-phase storage in accumulation | included | **omitted** | `reaction.F90:5512-5517` vs `pmc_subsurface_osrt.F90:186, 272-276` |
| Gas-phase flux at interior faces | included | **omitted** | `transport.F90:443-449` (loop over both phases) vs `reactive_transport.F90:1745-1747` (only `coef_up(1,1)` is passed to `MatSetValuesLocal`) |
| Gas-phase flux at boundaries | included | **omitted** | `reactive_transport.F90:2366-2371` vs `reactive_transport.F90:1428, 1475-1476` (`iphase = 1` hard-set) |
| Species-dependent diffusion | supported | fatal error | `pmc_subsurface_osrt.F90:299-303` |
| MPHASE flow coupling | supported | fatal error | `factory_subsurface.F90:522-528` |
| Reaction/transport coupling error | none | first-order split, non-iterative | structure of `pmc_subsurface_osrt.F90:281-416` |

In `RTCalculateTransportMatrix` the flux coefficient arrays are dimensioned
`(naqcomp, nphase)` (`src/pflotran/reactive_transport.F90:1632-1635`) but are handed to
`MatSetValuesLocal` as a single scalar per (row, col)
(`src/pflotran/reactive_transport.F90:1688-1700, 1726-1731`), i.e. element `(1,1)`. The
accumulation contribution likewise sets `iphase = 1` explicitly
(`src/pflotran/reactive_transport.F90:1740-1752`). This is the concrete sense in which the
OSRT path is liquid-only.

### Accuracy / stability trade-off the source implies

- **Accuracy.** GIRT introduces no operator-splitting error. OSRT's split is *sequential
  non-iterative* — there is no fixed-point loop between the KSP transport solves and `RStep`
  (`src/pflotran/pmc_subsurface_osrt.F90:281-416`), so the splitting error is first order in
  $\Delta t$ and is not measured or controlled anywhere in this routine.
- **Robustness.** OSRT's transport half-step is *linear* (KSP, one scalar system per component)
  and therefore cannot fail nonlinearly; only the per-cell `RStep` can fail, and its failure
  mode is a global timestep cut. GIRT's failure mode is a global Newton failure.
- **Cost.** OSRT assembles one `ONEDOF` matrix and does `naqcomp` scalar solves per attempt
  (`src/pflotran/pmc_subsurface_osrt.F90:304-338`); GIRT assembles an `ncomp`-block matrix and
  does a Newton solve. OSRT builds and factors far less, but repeats the *whole* transport
  sequence on any reaction failure.
- **The source's own escape hatch.** The only in-code guidance on when OSRT is inadequate is
  `pmc_subsurface_osrt.F90:399-403`: multi-substep reaction failure ⇒ use GIRT.

---

## 4. `SUBSURFACE_TRANSPORT` / `OPTIONS` — the complete card list at this commit

The `OPTIONS` block is parsed by `PMRTReadSimOptionsBlock`
(`src/pflotran/pm_rt.F90:175-288`). Each keyword is first offered to the base-class handler
`PMBaseReadSimOptionsSelectCase` (`src/pflotran/pm_rt.F90:216-218`, implementation at
`src/pflotran/pm_base.F90:187-215`), then to the RT-specific `select case`
(`src/pflotran/pm_rt.F90:220-284`). Unrecognized keywords are fatal
(`src/pflotran/pm_rt.F90:281-282`). Because `pm_osrt_type` extends `pm_rt_type` and does not
override `ReadSimulationOptionsBlock`, **this identical list applies to `MODE OSRT`.**

### 4a. Inherited from `PM_Base` (`src/pflotran/pm_base.F90:202-211`)

| Card | Line | Effect |
|---|---|---|
| `STEADY_STATE` | `pm_base.F90:203-204` | sets `this%steady_state = PETSC_TRUE` |
| `SKIP_RESTART` | `pm_base.F90:205-206` | sets `this%skip_restart = PETSC_TRUE` |
| `LOGGING_VERBOSITY <int>` | `pm_base.F90:207-209` | sets `this%logging_verbosity` |

**`SKIP_RESTART` in detail.** The flag means *do not read this process model's state out of the
checkpoint file*. It is honoured only on the HDF5 restart path:
`PMCBaseRestartHDF5` skips opening the PMC's HDF5 group and skips
`timestepper%RestartHDF5` when the flag is set
(`src/pflotran/pmc_base.F90:1450-1455, 1457-1460`). Two hard constraints follow:

1. **Binary checkpoints forbid it.** `PMCBaseRestartBinary` aborts: "Due to sequential nature of
   binary files, skipping restart for binary formatted files is not allowed."
   (`src/pflotran/pmc_base.F90:1207-1215`).
2. **The run must restart at time 0.** If `SKIP_RESTART` is set and
   `option%restart_time` is uninitialized, the code aborts: "Restarted simulations that
   SKIP_RESTART on checkpointed process models must restart at time 0."
   (`src/pflotran/pmc_base.F90:1465-1471`).

There is a commented-out `skip_restart` branch inside `pm_rt.F90` itself
(`src/pflotran/pm_rt.F90:583`), i.e. RT adds no extra behaviour beyond the base handling.
Note also `src/pflotran/factory_subsurface_read.F90:1723-1726`, which redirects an older
input pattern to "please use SKIP_RESTART in the SUBSURFACE_TRANSPORT" block.

### 4b. RT-specific cards (`src/pflotran/pm_rt.F90:220-284`)

| Card | Line | Effect |
|---|---|---|
| `INCLUDE_GAS_PHASE` | `pm_rt.F90:221-224` | **deprecated — fatal error.** |
| `MINIMUM_SATURATION <real>` | `pm_rt.F90:225-227` | sets module-global `rt_min_saturation` (default `1.d-40`, `reactive_transport_aux.F90:20`). Below this liquid saturation a cell/connection is skipped by dispersion, flux, source/sink and accumulation. |
| `MULTIPLE_CONTINUUM` | `pm_rt.F90:228-229` | `option%use_sc = PETSC_TRUE` (dual-continuum secondary transport) |
| `MULTIPLE_CONTINUUM_FIXED_DENSITY` | `pm_rt.F90:230-231` | `option%transport%sc_fixed_water_density = PETSC_TRUE` |
| `NERNST_PLANCK` | `pm_rt.F90:232-233` | `option%transport%use_np = PETSC_TRUE`; switches interior/boundary flux to `TNPFlux`/`TNPFluxBC` (`reactive_transport.F90:2302-2315, 2373-2386`) and zeroes the ordinary diffusion coefficient to `1.d-40` (`reactive_transport.F90:353-360`) |
| `TEMPERATURE_DEPENDENT_DIFFUSION` | `pm_rt.F90:234-236` | **deprecated** → use `TRANSPORT_TEMPERATURE_DEPENDENCE ANISOTHERMAL` |
| `USE_MILLINGTON_QUIRK_TORTUOSITY` | `pm_rt.F90:237-238` | `this%millington_quirk_tortuosity = PETSC_TRUE` — see §5 |
| `PRINT_EKG` | `pm_rt.F90:239-241` | `option%print_ekg` and `this%print_ekg` |
| `DEBUG_UPDATE` | `pm_rt.F90:242-243` | `this%debug_update` |
| `DEBUG_DERIVATIVES` | `pm_rt.F90:244-245` | `option%transport%debug_derivatives`; also drives allocation of perturbation auxvars (`reactive_transport.F90:289-290`) |
| `DEBUG_DERIVATIVES_RTOL <real>` | `pm_rt.F90:246-248` | `this%debug_derivatives_rtol` |
| `DEBUG_DERIVATIVES_ROW_RTOL <real>` | `pm_rt.F90:249-251` | `this%debug_derivatives_row_rtol` |
| `REFACTORED_CONVERGENCE` | `pm_rt.F90:252-254` | sets `this%refactored_convergence` **and** `this%check_post_convergence` |
| `TRANSPORT_TEMPERATURE_DEPENDENCE ISOTHERMAL\|ANISOTHERMAL` | `pm_rt.F90:255-266` | sets `this%transport_temperature_dependence` |
| `REACTION_TEMPERATURE_DEPENDENCE ISOTHERMAL\|ANISOTHERMAL` | `pm_rt.F90:267-278` | sets `this%reaction_temperature_dependence` |
| `REFERENCE_TEMPERATURE <real>` | `pm_rt.F90:279-281` | `this%reference_temperature` |

**Temperature-dependence resolution.** The two `*_TEMPERATURE_DEPENDENCE` cards are three-valued
internally: `RT_TEMPERATURE_FOLLOW_FLOW = 1`, `RT_TEMPERATURE_ISOTHERMAL = 2`,
`RT_TEMPERATURE_ANISOTHERMAL = 3` (`src/pflotran/pm_rt.F90:26-28`). Defaults are
`transport_temperature_dependence = RT_TEMPERATURE_ISOTHERMAL` and
`reaction_temperature_dependence = RT_TEMPERATURE_FOLLOW_FLOW`
(`src/pflotran/pm_rt.F90:157-158`) — i.e. **transport diffusion is isothermal by default even
when the flow mode is non-isothermal**, whereas reactions inherit the flow mode's setting.
The resolution to booleans happens in `factory_subsurface.F90:471-494`
(`FOLLOW_FLOW` maps to `option%flow%isothermal`). `option%transport%isothermal_transport` and
`isothermal_reaction` both default `PETSC_TRUE` (`src/pflotran/option_transport.F90:131-132`).

Setting `TRANSPORT_TEMPERATURE_DEPENDENCE ANISOTHERMAL` makes
`rt_parameter%temperature_dependent_diffusion = .not. isothermal_transport` true
(`src/pflotran/pm_rt.F90:431-432`) and then **requires** a `DIFFUSION_ACTIVATION_ENERGY` for
every phase, aborting otherwise (`src/pflotran/pm_rt.F90:437-452`).

---

## 5. `USE_MILLINGTON_QUIRK_TORTUOSITY` — the flag path and its guard

The card sets a flag on the process model (`src/pflotran/pm_rt.F90:237-238`, default
`PETSC_FALSE` at `src/pflotran/pm_rt.F90:156`), which is copied into the transport parameter
struct *after* `RTSetup` (`src/pflotran/pm_rt.F90:434-436`; the struct default is also
`PETSC_FALSE`, `src/pflotran/reactive_transport_aux.F90:192`).

**Hard guard.** `PMRTSetup` then verifies that every cell's `TORTUOSITY` equals exactly 1. It
pulls the tortuosity field into a work Vec, shifts by $-1$, takes the absolute value, and takes
the max via PETSc `VecShift`/`VecAbs`/`VecMax`; if the max exceeds `1.d-40` it aborts:

> `TORTUOSITY must be set to the default value of 1 in MATERIAL_PROPERTY when using USE_MILLINGTON_QUIRK_TORTUOSITY.`

(`src/pflotran/pm_rt.F90:469-484`). So the two tortuosity mechanisms are mutually exclusive in
practice: either you supply a constant `TORTUOSITY` factor, or you use Millington-Quirk with
`TORTUOSITY` left at its default of 1 (`src/pflotran/material.F90:209`).

The formulation itself is documented in
[`advection_dispersion_diffusion.md`](advection_dispersion_diffusion.md) §3.

---

## 6. Calibration knobs on this page

Units are as coded. "Default" is the value in force when the card is absent.

| Keyword | Block | Source line | Units | Default | Controls |
|---|---|---|---|---|---|
| `MODE GIRT` | `SUBSURFACE_TRANSPORT` | `factory_subsurface_read.F90:182-185` | — | none (a `MODE` is mandatory, `factory_subsurface_read.F90:238-242`) | fully coupled Newton solve; gas phase active |
| `MODE OSRT` | `SUBSURFACE_TRANSPORT` | `factory_subsurface_read.F90:186-189` | — | — | sequential split; liquid-only transport matrix |
| `SKIP_RESTART` | `OPTIONS` | `pm_base.F90:205-206` | — | off | skip this PM's HDF5 checkpoint read; forces restart at $t=0$ |
| `STEADY_STATE` | `OPTIONS` | `pm_base.F90:203-204` | — | off | steady-state PM flag |
| `LOGGING_VERBOSITY` | `OPTIONS` | `pm_base.F90:207-209` | integer | unchanged | PM log verbosity |
| `MINIMUM_SATURATION` | `OPTIONS` | `pm_rt.F90:225-227` | – (saturation) | `1.d-40` (`reactive_transport_aux.F90:20`) | dry-cell cutoff for flux, dispersion, accumulation, src/sink |
| `USE_MILLINGTON_QUIRK_TORTUOSITY` | `OPTIONS` | `pm_rt.F90:237-238` | — | off (constant `TORTUOSITY` used instead) | $S^{7/3}\phi^{1/3}$ scaling of $D_m$; requires `TORTUOSITY` = 1 |
| `NERNST_PLANCK` | `OPTIONS` | `pm_rt.F90:232-233` | — | off | replaces Fickian flux with Nernst-Planck; zeroes `diffusion_coefficient` |
| `MULTIPLE_CONTINUUM` | `OPTIONS` | `pm_rt.F90:228-229` | — | off | enables secondary-continuum transport; multiplies accumulation by $\epsilon$ (`reactive_transport.F90:1155-1158`) |
| `MULTIPLE_CONTINUUM_FIXED_DENSITY` | `OPTIONS` | `pm_rt.F90:230-231` | — | off | fixes secondary water density |
| `TRANSPORT_TEMPERATURE_DEPENDENCE` | `OPTIONS` | `pm_rt.F90:255-266` | — | `ISOTHERMAL` (`pm_rt.F90:157`) | Arrhenius / $T^{1.8}$ scaling of $D_m$ |
| `REACTION_TEMPERATURE_DEPENDENCE` | `OPTIONS` | `pm_rt.F90:267-278` | — | `FOLLOW_FLOW` (`pm_rt.F90:158`) | temperature dependence of reaction coefficients |
| `REFERENCE_TEMPERATURE` | `OPTIONS` | `pm_rt.F90:279-281` | °C (compared against database temperatures at `reaction_aux.F90:1244-1248`) | `UNINITIALIZED_DOUBLE` (`pm_rt.F90:159`); falls back to `option%flow%reference_temperature` (`factory_subsurface.F90:495-500`) | reference $T$ used to initialize reaction coefficients and to pick the database temperature |
| `REFACTORED_CONVERGENCE` | `OPTIONS` | `pm_rt.F90:252-254` | — | off | alternate GIRT convergence test + post-convergence check |
| `EXPLICIT_ADVECTION [limiter]` | `CHEMISTRY` (not `OPTIONS`) | `reaction.F90:841-866` | — | off | switches `option%itranmode` to `EXPLICIT_ADVECTION` (TVD). Errors if `nphase > 1`, if `ncomp /= naqcomp`, or if mass balance is on (`reactive_transport.F90:4367-4381`). Limiters: `UPWIND`/`MINMOD`/`MC`/`SUPERBEE`/`VANLEER` (`reaction.F90:847-861`) |

**Motivating-case note.** For a deck with `MODE GIRT` and
`OPTIONS: SKIP_RESTART / USE_MILLINGTON_QUIRK_TORTUOSITY`, exactly two option cards are active:
one restart-behaviour switch with no physics effect, and one that changes the effective
diffusion coefficient by the factor $S^{7/3}\phi^{1/3}$ while forbidding any non-unit
`TORTUOSITY` in every `MATERIAL_PROPERTY`.

---

## 7. Related pages

- [`advection_dispersion_diffusion.md`](advection_dispersion_diffusion.md) — `TDispersion`,
  Millington-Quirk, dispersivity, upwinding, gas-phase transport and
  `GAS_TRANSPORT_IS_UNVETTED`.
- [`transport_boundary_conditions.md`](transport_boundary_conditions.md) — BC types and their
  exact outflow-face semantics, plus how Darcy velocities reach transport.
