**Source pin:** PFLOTRAN commit 157a26f7
**Scope:** reactive transport — transport boundary/source conditions, their exact face semantics, and the flow→transport velocity handoff
**Last verified:** 2026-07-31

---

# Transport boundary conditions and the coupling to flow

This page covers how a `TRANSPORT_CONDITION` becomes a residual/matrix contribution at a face,
what each `TYPE` actually does at an inflow vs outflow face, and how Darcy velocities computed
by the flow process model reach the transport kernels. Geochemical *constraints* (the
`CONSTRAINT` block's speciation) are handled by the reaction modules and are treated here only
at their call sites.

> **PETSc is external.** `Vec`, `Mat`, `VecGetArrayF90`, `MatSetValuesLocal` and similar are
> PETSc library types/calls, not PFLOTRAN code.

---

## 1. Deck structure and the parse path

```
TRANSPORT_CONDITION <name>
  TYPE DIRICHLET_ZERO_GRADIENT       # one of 7, see §2
  CONSTRAINT_LIST
    0.d0  <constraint_name>
  /
END

BOUNDARY_CONDITION <name>
  TRANSPORT_CONDITION <name>
  REGION <region>
END
```

- `TRANSPORT_CONDITION` blocks are read at
  `src/pflotran/factory_subsurface_read.F90:1218-1226`; declaring one without a transport mode
  is fatal (`src/pflotran/factory_subsurface_read.F90:1219-1223`).
- The `TYPE` card is a 7-way `select case`
  (`src/pflotran/condition.F90:3927-3949`).
- The condition carries either a single `CONSTRAINT`
  (`src/pflotran/condition.F90:4014`) or a time-indexed `CONSTRAINT_LIST`
  (`src/pflotran/condition.F90:3963-4012`). Having **neither** is fatal:
  *"No CONSTRAINT or CONSTRAINT_LIST defined in TRANSPORT_CONDITION"*
  (`src/pflotran/condition.F90:4084-4086`).
- A `BOUNDARY_CONDITION` (or `SOURCE_SINK`) names its transport condition via the
  `TRANSPORT_CONDITION` card inside the coupler
  (`src/pflotran/coupler.F90:236-237`, field declared at `src/pflotran/coupler.F90:29`).
- Per-constraint, `EQUILIBRATE_AT_EACH_CELL` / `DO_NOT_EQUILIBRATE_AT_EACH_CELL`
  (`src/pflotran/transport_constraint_base.F90:123-127`) decide whether the constraint is
  re-speciated against every boundary cell's temperature/pressure or speciated once.

## 2. The seven `TYPE` values

`src/pflotran/condition.F90:3927-3949`, with integer ids from
`src/pflotran/pflotran_constants.F90:192-207`:

| Deck `TYPE` | `condition%itype` | id | line |
|---|---|---|---|
| `DIRICHLET` | `DIRICHLET_BC` | 1 | `condition.F90:3931-3932` |
| `DIRICHLET_ZERO_GRADIENT` | `DIRICHLET_ZERO_GRADIENT_BC` | 3 | `condition.F90:3933-3936` |
| `EQUILIBRIUM` | `EQUILIBRIUM_SS` | — | `condition.F90:3937-3938` |
| `NEUMANN` | `NEUMANN_BC` | 2 | `condition.F90:3939-3940` |
| `MEMBRANE_FILTER` | `MEMBRANE_BC` | — | `condition.F90:3941-3942` |
| `MOLE` / `MOLE_RATE` | `MASS_RATE_SS` | 7 | `condition.F90:3943-3944` |
| `ZERO_GRADIENT` | `ZERO_GRADIENT_BC` | 4 | `condition.F90:3945-3946` |

Anything else is fatal (`src/pflotran/condition.F90:3947-3951`). The printout mapping in
`TranConditionPrint` (`src/pflotran/condition.F90:5236-5249`) confirms the same seven.

`EQUILIBRIUM`, `MOLE`/`MOLE_RATE` and `MEMBRANE_FILTER` are source/sink types — they are handled
by `TSrcSinkCoef` (`src/pflotran/transport.F90:676-702`), not by the boundary-face path.

---

## 3. What each BC does at a face

A boundary face contributes through **two** independent pieces, and each BC type is filtered
separately in each. Understanding a BC requires reading both.

### Piece A — the dispersive/diffusive coefficient (`TDispersionBC`)

`src/pflotran/transport.F90:378-396`:

```fortran
    select case(ibndtype)
      case(DIRICHLET_BC,DIRICHLET_ZERO_GRADIENT_BC)
        ! if outflow, skip
        if (ibndtype == DIRICHLET_ZERO_GRADIENT_BC .and. q < 0.d0) cycle
        hydrodynamic_dispersion(:) = &
          max(mechanical_dispersion + &
              epsilon_dn * sat_up * material_auxvar_dn%porosity * tort_dn * &
              molecular_diffusion(:), &
              1.d-40)
        tran_coefs_over_dist(:,iphase) =  &
          hydrodynamic_dispersion(:)/dist_dn(0)
      case(CONCENTRATION_SS,NEUMANN_BC,ZERO_GRADIENT_BC,MEMBRANE_BC)
    end select
```

Read literally:

- **`DIRICHLET`** — always gets a dispersive coefficient, computed with the *boundary* face's
  saturation `sat_up` (the source comments this choice: "yes, sat_up due to boundary saturation
  governing, but perhaps we could use an average in the future",
  `src/pflotran/transport.F90:386-387`), and divided by `dist_dn(0)`, the cell-centre-to-face
  distance (`src/pflotran/transport.F90:391-394`). Note there is **no harmonic average** here,
  unlike the interior `TDispersion`.
- **`DIRICHLET_ZERO_GRADIENT`** — identical to `DIRICHLET` when $q \ge 0$ (inflow), and
  **skipped entirely when $q < 0$** (`src/pflotran/transport.F90:381`). Skipping leaves the
  coefficient at the zero set on entry (`src/pflotran/transport.F90:314`).
- **`NEUMANN`, `ZERO_GRADIENT`, `MEMBRANE_FILTER`, `CONCENTRATION_SS`** — the `case` body is
  *empty* (`src/pflotran/transport.F90:395`). The coefficient stays zero. **These BCs carry no
  diffusive/dispersive flux at all, in either flow direction.**

Sign convention: `q = qdarcy(iphase)` (`src/pflotran/transport.F90:352`), and the code treats
`q < 0` as outflow at a boundary (`src/pflotran/transport.F90:380-381`) — i.e. the connection
normal points into the domain.

### Piece B — the advective coefficient (`TFluxCoefBC` → `TFluxCoef`)

`src/pflotran/transport.F90:604-644`:

```fortran
  select case(bctype)
    case(MEMBRANE_BC)
      T_up = 0.d0
      T_dn = 0.d0
    case default
      call TFluxCoef(..., PETSC_FALSE, T_up,T_dn)
  end select
```

So **every BC type except `MEMBRANE_FILTER` gets the full upwinded advective coefficient**
(`src/pflotran/transport.F90:632-642`), using the same `TFluxCoef` upwinding as an interior face
(`src/pflotran/transport.F90:584-597`):

$$
q \ge 0:\quad T_{up} = (D/\Delta x + q)A\cdot 10^3,\;\; T_{dn} = -(D/\Delta x)A\cdot 10^3
$$
$$
q < 0:\quad\; T_{up} = (D/\Delta x)A\cdot 10^3,\;\; T_{dn} = (-D/\Delta x + q)A\cdot 10^3
$$

The `check_upwind_saturation` argument is `PETSC_FALSE` at boundaries
(`src/pflotran/transport.F90:641`), so a dry boundary auxvar does not zero the face.

### Piece C — what boundary concentration is used

`RTUpdateAuxVars` fills `rt_auxvars_bc` before each residual
(`src/pflotran/reactive_transport.F90:3690-3856`). The non-CO2 branch is
`src/pflotran/reactive_transport.F90:3756-3780`:

- **`DIRICHLET`, `NEUMANN`, `CONCENTRATION_SS`** — the boundary molality is set from the
  constraint's `basis_molarity`, converted molarity→molality by the boundary water density
  (`src/pflotran/reactive_transport.F90:3758-3764`).
- **`DIRICHLET_ZERO_GRADIENT`, `ZERO_GRADIENT`, `MEMBRANE_FILTER`** — same assignment
  (`src/pflotran/reactive_transport.F90:3765-3778`), **but** when
  `patch%boundary_velocities(iphase,sum_connection) < 0` the constraint is *not* re-equilibrated
  (`equilibrate_constraint = PETSC_FALSE`, `src/pflotran/reactive_transport.F90:3766-3771`).
  The source is explicit that on outflow the values are cosmetic:

  > `! with outflow, these boundary concentrations are ignored, for zero-gradient, but we still have to set them as other PMs such as salinity use the concentrations for calculating boundary densities. however, no need to equilibrate`
  > (`src/pflotran/reactive_transport.F90:3767-3770`)
  >
  > `! xxbc concentration will be ignored on outflow. if there is any doubt, set xxbc = 1.d-9 for vdarcy < 0 to check`
  > (`src/pflotran/reactive_transport.F90:3773-3774`)

The separate `option%transport%couple_co2` branch
(`src/pflotran/reactive_transport.F90:3800-3840`) instead copies the *interior cell's*
`xx_loc_p` into the boundary auxvar for `ZERO_GRADIENT`/`MEMBRANE` and for
`DIRICHLET_ZERO_GRADIENT` on outflow — a genuinely different implementation of the same
semantics.

### Semantics summarised, at an **outflow** face ($q < 0$)

| `TYPE` | dispersive coefficient | advective coefficient | net effect at outflow |
|---|---|---|---|
| `DIRICHLET` | **nonzero** (`transport.F90:379, 384-394`) | nonzero (`transport.F90:636-641`) | domain concentration advected out **plus** a diffusive exchange driven by the difference between the interior cell and the prescribed boundary value. Can *inject* mass back into the domain against the flow. |
| `DIRICHLET_ZERO_GRADIENT` | **zero** (`transport.F90:381` `cycle`) | nonzero | pure advective outflow at the *interior* concentration ($T_{up}$ multiplies the boundary total but with $D/\Delta x = 0$, so the outgoing term is $qA\cdot10^3 \cdot T^{\text{tot}}_{dn}$). This is the textbook "outflow / zero-gradient on the diffusive part" condition. On **inflow** it reverts to a full `DIRICHLET`. |
| `ZERO_GRADIENT` | zero, in **both** directions (`transport.F90:395`) | nonzero | pure advection in both directions. On inflow this advects the *constraint* concentration in (because `T_up` multiplies `rt_auxvars_bc%total`, which was set from the constraint, `reactive_transport.F90:3775-3780`) — **not** the interior value. |
| `NEUMANN` | zero (`transport.F90:395`) | nonzero (falls to `default`, `transport.F90:636`) | **advection-only**, with the boundary concentration taken from the constraint. There is no separate flux-magnitude input path in the RT code — grep shows `NEUMANN_BC` appears in the RT transport path only at `transport.F90:395` and `reactive_transport.F90:3758, 3803`. A user expecting a prescribed *mass flux* should use a `SOURCE_SINK` with `TYPE MOLE_RATE` instead. |
| `MEMBRANE_FILTER` | zero (`transport.F90:395`) | **zero** (`transport.F90:633-635`) | face completely closed to transport. |

**Motivating-case note.** For a deck using `DIRICHLET_ZERO_GRADIENT`: on an inflow face it is a
full Dirichlet condition (advection + dispersion at the constraint concentration); on an outflow
face the dispersive coupling is switched off (`transport.F90:381`) and the constraint is not
re-equilibrated (`reactive_transport.F90:3766-3771`), leaving pure advective export. This is the
standard choice for a domain outlet where you do not want the prescribed inlet chemistry to
diffuse back in.

---

## 4. How the boundary terms enter the system

**GIRT.** `RTResidualFlux` walks `patch%boundary_condition_list`, calls `TFluxCoefBC` then
`TFlux`, and **subtracts** the result from the cell's residual
(`src/pflotran/reactive_transport.F90:2342-2407`, subtraction at
`src/pflotran/reactive_transport.F90:2388-2390`). Fluxes are stashed in
`patch%boundary_tran_fluxes` when allocated
(`src/pflotran/reactive_transport.F90:2401-2404`) and accumulated into
`mass_balance_delta` when `compute_mass_balance_new` is on
(`src/pflotran/reactive_transport.F90:2392-2399`).

**OSRT.** The boundary term is split in two: the *inflow* part goes to the RHS in
`RTCalculateRHS_t1` (`src/pflotran/reactive_transport.F90:1444-1480`, contribution at
`src/pflotran/reactive_transport.F90:1471-1476`, "add in inflowing boundary conditions",
`src/pflotran/reactive_transport.F90:1444-1445`), and the *outflow* part goes to the matrix
diagonal in `RTCalculateTransportMatrix` ("add in outflowing boundary conditions",
`src/pflotran/reactive_transport.F90:1705-1740`). Both are liquid-only — see
[`girt_and_operator_splitting.md`](girt_and_operator_splitting.md) §3. Boundary mass balance for
OSRT is computed separately by `RTComputeBCMassBalanceOS`
(`src/pflotran/reactive_transport.F90:1824`, called at
`src/pflotran/pmc_subsurface_osrt.F90:340-343`).

---

## 5. Coupling to flow: how Darcy velocities reach transport

Transport never computes a velocity. It reads two arrays owned by the patch:

```fortran
    PetscReal, pointer :: internal_velocities(:,:)
    PetscReal, pointer :: boundary_velocities(:,:)
```
(`src/pflotran/patch.F90:47-48`), allocated with
`nphase = max(option%nphase, option%transport%nphase)` and **zero-initialized**
(`src/pflotran/patch.F90:781-785, 809-810`).

**Who writes them.** Each flow mode's flux routine stores its computed `v_darcy` there:

| Flow mode | internal | boundary | phases written |
|---|---|---|---|
| `RICHARDS` | `richards.F90:1523` | `richards.F90:1688` | **index 1 only** |
| `TH` | `th.F90:3774` | `th.F90:3923` | index 1 only |
| `ZFLOW` | `zflow.F90:975` | `zflow.F90:1049` | all (`:`) |
| `GENERAL` | `general.F90:1516` | `general.F90:1579` | all (`:`) |
| `WIPP_FLOW` | `wipp_flow.F90:1095` | `wipp_flow.F90:1184` | all (`:`) |
| `PNF` | `pm_pnf.F90:587` | `pm_pnf.F90:618` | index 1 only |

**Transport-only runs.** With no flow process model, `SPECIFIED_VELOCITY`
(`src/pflotran/factory_subsurface_read.F90:1092-1180`) supplies a uniform or dataset velocity
field; `PatchUpdateUniformVelocity` projects the Cartesian vector onto each connection's unit
direction for every transport phase:

```fortran
      do iphase = 1, option%transport%nphase
        vdarcy = dot_product(phase_velocity(:,iphase), &
                             cur_connection_set%dist(1:3,iconn))
        patch%internal_velocities(iphase,sum_connection) = vdarcy
```
(`src/pflotran/patch.F90:6294-6329`). It is refreshed each step through
`RealizUpdateUniformVelocity` when a `uniform_velocity_dataset` is associated
(`src/pflotran/pm_rt.F90:1546-1548`). `SPECIFIED_VELOCITY` fields cannot be combined with a flow
mode (`src/pflotran/factory_subsurface_read.F90:1092-1096`).

**Who reads them.** Three places, all in the transport layer:

1. `RTUpdateTransportCoefs` → `TDispersion(..., patch%internal_velocities(:,sum_connection), ...)`
   and `TDispersionBC(..., patch%boundary_velocities(:,sum_connection), ...)`
   (`src/pflotran/reactive_transport.F90:1308, 1349`) — for the mechanical dispersion term.
2. `RTResidualFlux` → `TFluxCoef`/`TFluxCoefBC`
   (`src/pflotran/reactive_transport.F90:2289, 2362`) — for the advective term and the
   upwind decision.
3. `RTUpdateAuxVars` → the sign test that selects zero-gradient behaviour
   (`src/pflotran/reactive_transport.F90:3766, 3819`).

**Time-level weighting.** Densities, saturations and (optionally) porosity are weighted to
$t^{k+1}$ before the coefficients are built: `PMRTWeightFlowParameters(this,TIME_TpDT)` in
`PMRTPreSolve` (`src/pflotran/pm_rt.F90:722`) and in the OSRT step loop
(`src/pflotran/pmc_subsurface_osrt.F90:286`); `PMOSRTPreSolve` weights the material and global
auxvars by `tran_weight_t1` (`src/pflotran/pm_osrt.F90:176-188`). The velocities themselves are
**not** weighted — they are whatever the flow solve last wrote.

**Source/sink volumetric fluxes** arrive through a different array,
`patch%ss_flow_vol_fluxes` (`src/pflotran/reactive_transport.F90:2625-2626, 1519-1520`), passed
to `TSrcSinkCoef` (`src/pflotran/transport.F90:648-708`), whose default branch converts
m³/s → L/s with a factor 1000 and splits injection (`qsrc > 0` ⇒ external concentration) from
extraction (`qsrc < 0` ⇒ cell concentration)
(`src/pflotran/transport.F90:691-701`).

### Consequence: single-phase flow + active gas

Because `RICHARDS_MODE` writes only index 1
(`src/pflotran/richards.F90:1523, 1688`) while the arrays are sized for two transport phases
(`src/pflotran/patch.F90:781-785`), the gas-phase Darcy velocity remains exactly zero. Gas
saturation is still populated as $S_g = 1 - S_\ell$
(`src/pflotran/richards_aux.F90:369-371`), so gas-phase molecular diffusion is active but gas
advection is not. No warning is issued. See
[`advection_dispersion_diffusion.md`](advection_dispersion_diffusion.md) §7.3.

---

## 6. Calibration knobs on this page

| Keyword | Block | Source line | Units | Default | Controls |
|---|---|---|---|---|---|
| `TYPE DIRICHLET` | `TRANSPORT_CONDITION` | `condition.F90:3931-3932` | – | none (`TYPE` is effectively required for a BC) | advection + dispersion at the constraint concentration, both directions |
| `TYPE DIRICHLET_ZERO_GRADIENT` | `TRANSPORT_CONDITION` | `condition.F90:3933-3936` | – | – | as `DIRICHLET` on inflow; dispersion disabled on outflow (`transport.F90:381`) |
| `TYPE ZERO_GRADIENT` | `TRANSPORT_CONDITION` | `condition.F90:3945-3946` | – | – | advection only, both directions (`transport.F90:395`) |
| `TYPE NEUMANN` | `TRANSPORT_CONDITION` | `condition.F90:3939-3940` | – | – | advection only; no separate flux-magnitude input in the RT path |
| `TYPE MEMBRANE_FILTER` | `TRANSPORT_CONDITION` | `condition.F90:3941-3942` | – | – | face closed: both coefficients zero (`transport.F90:395, 633-635`) |
| `TYPE EQUILIBRIUM` | `TRANSPORT_CONDITION` (src/sink) | `condition.F90:3937-3938` | L water/s | – | hard-coded equilibration rate `T_in = 1.d-3` (`transport.F90:677-683`) |
| `TYPE MOLE` / `MOLE_RATE` | `TRANSPORT_CONDITION` (src/sink) | `condition.F90:3943-3944` | mol/s | – | `rt_auxvar_bc%total` reinterpreted as a mass rate; `T_in = 0`, `T_out = -1` (`transport.F90:684-687`) |
| `CONSTRAINT <name>` | `TRANSPORT_CONDITION` | `condition.F90:4014` | – | required (fatal if absent with no `CONSTRAINT_LIST`, `condition.F90:4084-4086`) | which geochemical constraint supplies the boundary concentrations |
| `CONSTRAINT_LIST` | `TRANSPORT_CONDITION` | `condition.F90:3963-4012` | time + name | – | time-varying constraint sequence |
| `TIME_UNITS` | `TRANSPORT_CONDITION` | `condition.F90:3952-3962` | `s\|min\|hr\|d\|y` (validated at `condition.F90:3956`) | – | default units for the constraint list |
| `EQUILIBRATE_AT_EACH_CELL` | `CONSTRAINT` | `transport_constraint_base.F90:124-125` | – | see `DO_NOT_...` counterpart | re-speciate the constraint per boundary cell |
| `DO_NOT_EQUILIBRATE_AT_EACH_CELL` | `CONSTRAINT` | `transport_constraint_base.F90:126-127` | – | – | speciate once and reuse |
| `TRANSPORT_CONDITION <name>` | `BOUNDARY_CONDITION` / `SOURCE_SINK` | `coupler.F90:236-237` | – | `""` (`coupler.F90:101`) | binds a condition to a region |
| `SPECIFIED_VELOCITY` | `SUBSURFACE` | `factory_subsurface_read.F90:1092-1180` | m/s per component | absent | prescribes Darcy velocity for transport-only runs; incompatible with a flow mode |

---

## 7. Things that could not be verified statically

- Whether `NEUMANN` is ever intended to carry a prescribed flux *magnitude* for reactive
  transport. In this tree it behaves as advection-only with a constraint concentration; there is
  no code path reading a flux value for `NEUMANN_BC` in `transport.F90` or
  `reactive_transport.F90`. (`nw_transport.F90:471-497` shows the NWT mode restricting itself to
  `DIRICHLET` / `DIRICHLET_ZERO_GRADIENT` only — the RT mode imposes no such restriction.)
- The divide-by-`v_dn` in `TDispersionBC`'s transverse branch has no zero guard
  (`src/pflotran/transport.F90:356-359`); whether any shipped deck reaches it with a stagnant
  boundary cell cannot be determined from source alone.
- Whether the checks that compose `option%io_buffer` without printing it (e.g.
  `src/pflotran/reactive_transport.F90:325-334`) are dead by design or by oversight.

---

## 8. Related pages

- [`girt_and_operator_splitting.md`](girt_and_operator_splitting.md) — mode dispatch, GIRT vs
  OSRT algorithms, the `OPTIONS` card list.
- [`advection_dispersion_diffusion.md`](advection_dispersion_diffusion.md) — dispersion tensor,
  Millington-Quirk, diffusion coefficients, gas-phase transport.
