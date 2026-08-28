---
**Source pin:** ATS commit `42b0e940` (`ats-1.7-dev-22-g42b0e940`)
**Last verified:** 2026-07-27
---

# MPCSubsurface: Coupled Subsurface Flow and Energy

## Purpose

`MPCSubsurface` is the globally-implicit MPC that couples the three-phase Richards equation (permafrost flow, `src/pks/flow/`) to the three-phase energy equation (`src/pks/energy/`). It provides an approximate Jacobian (preconditioner) that captures the dominant cross-variable coupling terms arising from phase change.

**File:** `src/pks/mpc/mpc_subsurface.hh` and `src/pks/mpc/mpc_subsurface.cc`

**PK type string:** `"subsurface permafrost"`

**Inherits:** `StrongMPC<PK_PhysicalBDF_Default>`

```cpp
class MPCSubsurface : public StrongMPC<PK_PhysicalBDF_Default> { ... };
```
(src/pks/mpc/mpc_subsurface.hh:165)

---

## The coupled equations

The two conservation equations (from the header doc, src/pks/mpc/mpc_subsurface.hh:19-34):

```
∂Θ/∂t − ∇·(k_r n_l/μ) K (∇p + ρg ẑ) = Q_w             [Richards / water content]
∂E/∂t − ∇·κ ∇T + ∇·q e(T) = Q_w e(T) + Q_e             [Energy]
```

Both Θ (volumetric water content) and E (energy) depend on both p (pressure) and T (temperature). The full 2×2 Jacobian has four blocks; `MPCSubsurface` assembles an approximation to all four.

---

## Preconditioner structure

The `TreeOperator` preconditioner (src/pks/mpc/mpc_subsurface.hh:207) represents the block 2×2 system:

```
[ ∂F₁/∂p   ∂F₁/∂T ]   [ Richards block    |  dWC/dT block  ]
[ ∂F₂/∂p   ∂F₂/∂T ] = [ dE/dp block       |  Energy block  ]
```

**On-diagonal blocks** are provided by the individual sub-PKs (Richards and energy) and are assembled by their own operators.

**Off-diagonal blocks** are assembled by `MPCSubsurface`:

### ∂F₁/∂T (dWC/dT block) — water content equation, T derivative

Two terms:
- `dWC_dT_` (`PDE_Accumulation`): cell-local ∂Θ/∂T term
- `ddivq_dT_` (`PDE_DiffusionWithGravity`): derivative of the Darcy divergence w.r.t. T, dominated by ∂k_r/∂T through the freeze-equals-drying approximation

(src/pks/mpc/mpc_subsurface.hh:219-225)

### ∂F₂/∂p (dE/dp block) — energy equation, p derivative

Three terms:
- `dE_dp_` (`PDE_Accumulation`): cell-local ∂E/∂p term
- `ddivKgT_dp_` (`PDE_Diffusion`): derivative of thermal diffusion ∇·κ∇T w.r.t. p, dominated by ∂κ/∂p through phase change
- `ddivhq_dp_` (`PDE_DiffusionWithGravity`): derivative of the enthalpy advection ∇·hq w.r.t. p

(src/pks/mpc/mpc_subsurface.hh:227-236)

### Additional ∂F₂/∂T terms

- `ddivhq_dT_` (`PDE_DiffusionWithGravity`): derivative of enthalpy advection w.r.t. T (upwinded)

(src/pks/mpc/mpc_subsurface.hh:239-241)

---

## Preconditioner type options

The `"preconditioner type"` parameter (src/pks/mpc/mpc_subsurface.hh:199-205) selects which blocks are included:

| Type string | `PreconditionerType` enum | Description |
|---|---|---|
| `"none"` | `PRECON_NONE` | No preconditioner (never works) |
| `"block diagonal"` | `PRECON_BLOCK_DIAGONAL` | Only diagonal blocks (like `StrongMPC` default) |
| `"no flow coupling"` | `PRECON_NO_FLOW_COUPLING` | Accumulation terms only, no off-diagonal diffusion |
| `"picard"` | `PRECON_PICARD` | **Default.** All available cross-variable terms |
| `"ewc"` | `PRECON_EWC` | Picard + energy-water content variable transform (currently disabled) |
| `"smart ewc"` | `PRECON_EWC` | Smart version of EWC (currently disabled) |

The "picard" option is recommended and almost always used. Individual off-diagonal terms can be suppressed via:
- `"supress Jacobian terms: d div hq / dp,T"` (suppress enthalpy advection coupling)
- `"supress Jacobian terms: d div q / dT"` (suppress flow-temperature coupling)
- `"supress Jacobian terms: d div K grad T / dp"` (suppress thermal conductivity-pressure coupling)

---

## EWC globalization delegate

`MPCSubsurface` holds an `MPCDelegateEWCSubsurface` (src/pks/mpc/mpc_subsurface.hh:269):

```cpp
Teuchos::RCP<MPCDelegateEWCSubsurface> ewc_;
```

The EWC delegate is invoked in `ModifyPredictor` (before the Newton solve starts) and optionally in the preconditioner. It is most useful in the predictor: rather than extrapolating (p, T) linearly from previous timesteps, it extrapolates (water content, energy) linearly and then inverts locally to find the (p, T) that matches, which gives a better initial guess near freeze-thaw fronts. See [mpc.md](mpc.md) for the EWC algorithm description.

The thermodynamics model used by the EWC delegate for the subsurface is `PermafrostModel` (src/pks/mpc/constitutive_relations/permafrost_model.hh), which encapsulates the Θ(p, T) and E(p, T) functions for the three-phase (liquid water, ice, gas) system.

---

## Sub-PK order and field keys

`MPCSubsurface` expects exactly two sub-PKs in this order (src/pks/mpc/mpc_subsurface.hh:113 in the PK type doc):
1. Sub-PK 0: three-phase Richards (flow), `"domain name"` = the subsurface domain
2. Sub-PK 1: three-phase energy

Key fields tracked (src/pks/mpc/mpc_subsurface.hh:243-266):
- `temp_key_`, `pres_key_` — primary variables T and p
- `e_key_`, `wc_key_` — conserved quantities (energy, water content)
- `tc_key_`, `uw_tc_key_` — thermal conductivity and its upwinded version
- `kr_key_`, `uw_kr_key_` — relative permeability and upwinded version
- `enth_key_`, `hkr_key_`, `uw_hkr_key_` — enthalpy and enthalpy-conductance products
- `energy_flux_key_`, `water_flux_key_` — face-based fluxes
- `duw_krdT_key_`, `duw_tcdp_key_` — upwinded derivatives for off-diagonal blocks

---

## MPCSurface: surface analog

**File:** `src/pks/mpc/mpc_surface.hh`

**PK type string:** `"icy surface"`

```cpp
class MPCSurface : public StrongMPC<PK_PhysicalBDF_Default> { ... };
```
(src/pks/mpc/mpc_surface.hh:67)

`MPCSurface` provides the same block-2×2 approximate Jacobian structure as `MPCSubsurface` but for the two-phase surface system: the diffusion-wave overland flow equation plus the surface energy equation ("icy surface"). The off-diagonal blocks are simpler because the Darcy flux is replaced by the Manning-based overland conductance:
- `ddivq_dT_` — derivative of overland conductivity w.r.t. T (can be suppressed)
- `dE_dp_` — ∂E_s/∂p accumulation term

(src/pks/mpc/mpc_surface.hh:117-126)

`MPCSurface` also holds an `MPCDelegateEWCSurface` and uses the `SurfaceIceModel` for EWC globalization.

---

## How MPCSubsurface is used by MPCPermafrost

`MPCPermafrost` inherits from `MPCSubsurface` (not from `StrongMPC` directly) and adds the surface sub-PKs on top. This inheritance chain means `MPCPermafrost` reuses the full subsurface 2×2 Jacobian machinery and extends it to a 4×4 block system. See [mpc_surface_subsurface.md](mpc_surface_subsurface.md) for details.
