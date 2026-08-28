---
**Source pin:** ATS commit `42b0e940` (`ats-1.7-dev-22-g42b0e940`)
**Last verified:** 2026-07-27
---

# Transport

Source directory: `src/pks/transport/`

Two PKs implement solute and sediment transport: `Transport_ATS` (the base class, handles
multi-component dissolved-phase transport) and `SedimentTransport_PK` (a subclass that
adds erosion/trapping/settling for a single sediment component).  Reactive geochemistry
is coupled through the **Alquimia** interface, activated at compile time.

---

## 1. `Transport_ATS` — multi-component advection-dispersion

**PK type string:** `"transport ATS"`

**Files:**
- `src/pks/transport/transport_ats.hh` — class declaration (with embedded spec doc)
- `src/pks/transport/transport_ats_pk.cc` — Setup, Initialize, AdvanceStep, CommitStep
- `src/pks/transport/transport_ats_ti.cc` — core advection time-integration routines
- `src/pks/transport/transport_ats_dispersion.cc` — diffusion-dispersion assembly
- `src/pks/transport/transport_ats_henrylaw.cc` — Henry's law air-water partitioning (stub)
- `src/pks/transport/transport_ats_vandv.cc` — verification/validation diagnostics
- `src/pks/transport/transport_ats_reg.hh` — PK registration

### Governing equation

For each aqueous component *i*:

```
∂(Θ χᵢ)/∂t = -∇·(q χᵢ) + ∇·(Θ (D*_l + τ Dᵢ) ∇χᵢ) + Qₛ
```

where `χᵢ` is **mole fraction** [mol C mol H₂O⁻¹], `Θ` is the liquid water content
[mol], `q` is the water flux [mol H₂O s⁻¹] on faces, `D*_l` is the mechanical
dispersion tensor, and `Dᵢ` is molecular diffusivity scaled by tortuosity
(src/pks/transport/transport_ats.hh:18-22).

Note: the primary variable is **mole fraction, not concentration**.  Total concentration
`Cᵢ = n_l χᵢ` [mol L⁻¹] is a diagnostic.  The code enforces this naming; calling the
field `"total_component_concentration"` now throws an error
(src/pks/transport/transport_ats_pk.cc:86-92).

### Time discretization

Two explicit Runge-Kutta options (src/pks/transport/transport_ats.hh:347-351):
- `"temporal discretization order" = 1` — forward Euler (`AdvanceAdvectionSources_RK1_`)
- `"temporal discretization order" = 2` — predictor-corrector Runge-Kutta (`AdvanceAdvectionSources_RK2_`)

Timestep is CFL-limited.  The CFL number defaults to 1.0 and can be reduced
(`"cfl"` parameter).  `ComputeStableTimeStep_()` computes the CFL-limited timestep from
the water flux and liquid water content fields.

### Spatial discretization (advection)

Two spatial orders (src/pks/transport/transport_ats.hh:91-93):
- First-order: donor upwind (src/pks/transport/transport_ats_ti.cc:35-40)
- Second-order: a limiter scheme using `ReconstructionCellLinear` and `LimiterCell`

For first-order upwind, the core loop (src/pks/transport/transport_ats_ti.cc:53-80):
- For each face, identify upwind cell `c1` and downwind cell `c2` from precomputed
  `upwind_cell_` and `downwind_cell_` integer vectors.
- Flux contribution to `c_qty` (total component moles) is `dt * u * tcc[c1]`.

### Dispersion-diffusion (implicit)

`AdvanceDispersionDiffusion_` assembles a global diffusion operator using
`PDE_Diffusion` and `PDE_Accumulation` from `src/operators/`.  The diffusion tensor `D_`
combines mechanical dispersion and molecular diffusivity scaled by tortuosity.  This solve
is implicit (a linear system per component); the CFL constraint does not limit it.
(src/pks/transport/transport_ats.hh:376-381)

### Alquimia reactive chemistry coupling

Controlled by `#ifdef ALQUIMIA_ENABLED` throughout the header and implementation:

```cpp
// From transport_ats.hh:339-344
#ifdef ALQUIMIA_ENABLED
  Teuchos::RCP<AmanziChemistry::Alquimia_PK> chem_pk_;
  Teuchos::RCP<AmanziChemistry::ChemistryEngine> chem_engine_;
#else
  Teuchos::RCP<bool> chem_pk_;
  Teuchos::RCP<bool> chem_engine_;
#endif
```

When enabled, the chemistry engine is injected via `setChemEngine()`, which retrieves the
`ChemistryEngine` from `Alquimia_PK` and reads primary species names to set
`component_names_` (src/pks/transport/transport_ats_pk.cc:220-228).

Boundary conditions and source terms can be specified as **geochemical conditions**
(strings naming Alquimia constraints) via `TransportBoundaryFunction_Alquimia` and
`TransportSourceFunction_Alquimia` objects assembled during `Initialize`
(src/pks/transport/transport_ats_pk.cc:527, 684).

The operator-split orchestration (transport step then chemistry step) is done in the MPC
layer (`src/pks/mpc/mpc_reactivetransport.cc`, `mpc_coupled_reactivetransport.cc`), not
inside `Transport_ATS` itself.

### Key state fields consumed

| Field key | Unit | Role |
|---|---|---|
| `water_flux_key_` | mol H₂O s⁻¹ on faces | advecting flux |
| `lwc_key_` (liquid water content) | mol H₂O | accumulation multiplier |
| `molar_dens_key_` | mol H₂O m⁻³ | concentration conversion |
| `source_key_` | mol C m⁻³ s⁻¹ or m⁻² s⁻¹ | solute source/sink |

### Solid residue tracking

`solid_residue_mass_key_` tracks solute mass that was "stranded" by non-advecting water
sinks (freezing, evaporation) that carried no dissolved species.  This keeps mass
conservation correct when liquid saturations change
(src/pks/transport/transport_ats.hh:323-325).

### Class hierarchy

```
PK_Physical_Default
  └── Transport_ATS
        └── SedimentTransport_PK
```

---

## 2. `SedimentTransport_PK` — sediment transport

**PK type string:** `"sediment transport"`

**Files:**
- `src/pks/transport/sediment_transport_pk.{hh,cc}`
- `src/pks/transport/sediment_transport_reg.hh`

### What it adds

`SedimentTransport_PK` inherits all of `Transport_ATS` and overrides:
- `SetupPhysicalEvaluators_()` — adds sediment-specific evaluator keys
- `AddSourceTerms_()` — replaces generic source addition with erosion/trapping/settling

The single sediment component is called `"sediment"`.  The advection-diffusion equation
is the same as in `Transport_ATS` but the net source adds three physical terms
(src/pks/transport/sediment_transport_pk.hh:17-23):
- `Q_e` — erosion rate [m s⁻¹]
- `Q_t` — trapping rate [m s⁻¹]
- `Q_s` — settling rate [m s⁻¹]

Sediment density is a scalar parameter (`sediment_density_`).  The following additional
keys are read from state (src/pks/transport/sediment_transport_pk.hh:129-133):
- `sd_trapping_key_`, `sd_settling_key_`, `sd_erosion_key_` — source evaluators
- `horiz_mixing_key_` — horizontal mixing coefficient
- `sd_organic_key_` — organic matter sediment fraction
- `elevation_increase_key_` — net elevation change due to sediment deposition
- `plant_area_key_`, `stem_diameter_key_`, `stem_height_key_`, `stem_density_key_` — plant
  properties that affect drag and settling

---

## 3. Sediment transport constitutive evaluators

Directory: `src/pks/transport/constitutive_relations/sediment_transport/`

| File | Evaluator type string | Physics |
|---|---|---|
| `erosion_evaluator.{hh,cc}` | `"erosion rate"` | Erosion flux from bed shear stress: `Q_e = Q_e0 * (τ₀/τ_e - 1)` if `τ₀ > τ_e`, else 0.  Parameters: `tau_e_` (critical shear stress), `Qe_0_` (empirical coefficient), `Cf_` (drag coefficient).  Depends on `"velocity"`. |
| `trapping_evaluator.{hh,cc}` | `"trapping rate"` | Sediment trapping by vegetation canopy. |
| `settlement_evaluator.{hh,cc}` | `"settlement rate"` | Gravitational settling of sediment. |
| `biomass_evaluator.{hh,cc}` | `"biomass"` | Plant biomass (vegetation density) for drag effects. |
| `organic_matter_evaluator.{hh,cc}` | `"organic matter"` | Organic fraction of sediment. |

All are `EvaluatorSecondaryMonotypeCV` subclasses.

---

## 4. Transport source evaluators

Directory: `src/pks/transport/constitutive_relations/sources/`

| File | Purpose |
|---|---|
| `qc_relation_field_evaluator.{hh,cc}` | Concentration-flux relationship evaluator for field (subsurface) domain. |
| `qc_relation_overland_evaluator.{hh,cc}` | Concentration-flux relationship for overland flow domain. |

These implement `q-C` source relationships where solute injection rate is proportional to
a water source times a concentration.

---

## 5. MPC coupling for transport (cross-reference)

The transport PK does not couple itself to flow or chemistry.  That coupling is done by
MPCs in `src/pks/mpc/`:
- `mpc_flow_transport.cc` — sequential coupling of flow + transport
- `mpc_reactivetransport.cc` — operator-split transport + Alquimia chemistry
- `mpc_coupled_reactivetransport.cc` — flow + transport + reactive chemistry

These are documented in topic 04 (`04_pk_base_mpc`).
