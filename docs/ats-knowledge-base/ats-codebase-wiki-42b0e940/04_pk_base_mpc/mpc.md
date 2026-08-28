---
**Source pin:** ATS commit `42b0e940` (`ats-1.7-dev-22-g42b0e940`)
**Last verified:** 2026-07-27
---

# Multi-Process Coupler (MPC)

## Design principle: MPCs are PKs

The central architectural idea is that an MPC is itself a PK. This enables recursive composition: an MPC can contain other MPCs as children, building arbitrarily deep coupling hierarchies from a uniform interface. The coordinator only ever calls PK lifecycle methods; it does not know or care whether a given PK is a leaf physics solver or a tree of coupled sub-PKs.

---

## MPC<PK_t> — the template base

**File:** `src/pks/mpc/mpc.hh`

```cpp
template<class PK_t>
class MPC : virtual public PK {
 protected:
  typedef std::vector<Teuchos::RCP<PK_t>> SubPKList;
  SubPKList sub_pks_;
  ...
};
```
(src/pks/mpc/mpc.hh:53-117)

The template parameter `PK_t` constrains what type of sub-PK is allowed:
- `MPC<PK>` allows any PK (used by `WeakMPC`, `MPCSubcycled`, `MPCWeakSubdomain`)
- `MPC<PK_PhysicalBDF_Default>` allows only physical-BDF sub-PKs (used by `StrongMPC<PK_PhysicalBDF_Default>` and derived coupled MPCs)
- `MPC<PK_BDF_Default>` is used by `MPCCoupledDualMediaWater`

`MPC<PK_t>` does **not** supply `AdvanceStep()`. It is abstract and must be subclassed. Everything else (Setup, Initialize, CommitStep, FailStep, CalculateDiagnostics, State_to_Solution, Solution_to_State, ChangedSolutionPK) is implemented as a loop over `sub_pks_`.

### Sub-PK construction: `init_()`

(src/pks/mpc/mpc.hh:266-284)

```cpp
void MPC<PK_t>::init_(Comm_ptr_type comm) {
  PKFactory pk_factory;
  auto pk_order = plist_->get<Teuchos::Array<std::string>>("PKs order");
  for (int i = 0; i != npks; ++i) {
    Teuchos::RCP<TreeVector> pk_soln = Teuchos::rcp(new TreeVector(comm));
    solution_->PushBack(pk_soln);           // extend global solution vector
    Teuchos::RCP<PK> pk_notype = pk_factory.CreatePK(name_i, ...);
    Teuchos::RCP<PK_t> pk = Teuchos::rcp_dynamic_cast<PK_t>(pk_notype, true);
    sub_pks_.push_back(pk);
  }
}
```

The `"PKs order"` array in the input XML specifies both the order and the names of sub-PKs. Each sub-PK gets its own slice of the composite `TreeVector` solution. The `PKFactory` looks up the PK by the `"PK type"` string in the sub-PK's parameter sublist. This is the only place where PK objects are constructed.

### TreeVector structure

Because `Solution_to_State` and `State_to_Solution` use `soln.SubVector(i)`, the solution `TreeVector` must have exactly as many sub-vectors as there are sub-PKs, in the same order. `init_()` appends them in `pk_order` order, so the vector structure mirrors the PK tree.

---

## WeakMPC — sequential (non-iterative) coupling

**File:** `src/pks/mpc/weak_mpc.hh` and `src/pks/mpc/weak_mpc.cc`

**PK type string:** `"weak MPC"`

```cpp
class WeakMPC : public MPC<PK> { ... };
```
(src/pks/mpc/weak_mpc.hh:34)

`WeakMPC::AdvanceStep` (not shown in header, implemented in `weak_mpc.cc`) simply calls each sub-PK's `AdvanceStep` in order. If any sub-PK fails, the whole step fails. `get_dt()` returns the minimum of all sub-PK `get_dt()` values.

This is the simplest MPC: physics are decoupled in time — each PK advances using the state left by the previous PK in that step. Appropriate when coupling error is negligible or when subcycling separates the timescales.

**Used by:**
- `MPCCoupledTransport` (surface + subsurface transport, weak coupling between domains)
- `MPCReactiveTransport` (transport then chemistry, operator split)
- `MPCCoupledReactiveTransport` (integrated transport then integrated chemistry)

---

## StrongMPC<PK_t> — globally implicit coupling

**File:** `src/pks/mpc/strong_mpc.hh` (header-only implementation)

**PK type string:** `"strong MPC"`

```cpp
template<class PK_t>
class StrongMPC
  : public MPC<PK_t>
  , public PK_BDF_Default { ... };
```
(src/pks/mpc/strong_mpc.hh:42-44)

`StrongMPC` is both an MPC (holds sub-PKs) and a BDF PK (owns a Newton/BDF1 time integrator). The BDF1 integrator calls the MPC's `FunctionalResidual`, `UpdatePreconditioner`, and `ApplyPreconditioner`, which in turn fan out to all sub-PKs.

### The strongly-coupled flag

`StrongMPC::parseParameterList()` (src/pks/mpc/strong_mpc.hh:144-156) sets `"strongly coupled PK" = true` on every sub-PK's parameter list before their `Setup()` runs. This ensures that no sub-PK creates its own time integrator (see [pk_base_classes.md](pk_base_classes.md)).

### FunctionalResidual

(src/pks/mpc/strong_mpc.hh:222-261)

Calls each sub-PK's `FunctionalResidual` with the corresponding sub-vector of `u_old`, `u_new`, and `g`. The sub-PK residual contributions are assembled into the composite global residual in place.

### Block-diagonal preconditioner

`ApplyPreconditioner` (src/pks/mpc/strong_mpc.hh:267-293) applies each sub-PK's preconditioner to its own sub-vector independently, producing a block-diagonal approximation. For coupled problems where the off-diagonal blocks matter (e.g., flow-energy coupling), specialized MPCs override this (see `MPCSubsurface`, `MPCCoupledWater`).

### ErrorNorm

(src/pks/mpc/strong_mpc.hh:300-327): takes the maximum of all sub-PKs' error norms, so convergence requires all sub-PKs to converge simultaneously.

### ModifyPredictor and ModifyCorrection

Both loop over sub-PKs and OR the results (src/pks/mpc/strong_mpc.hh:433-482). This allows any sub-PK (or MPC delegate, see EWC below) to modify the predictor or correction globally.

---

## MPCSubcycled — weak coupling with subcycling

**File:** `src/pks/mpc/mpc_subcycled.hh` and `src/pks/mpc/mpc_subcycled.cc`

**PK type string:** `"subcycling MPC"`

```cpp
class MPCSubcycled : public MPC<PK> { ... };
```
(src/pks/mpc/mpc_subcycled.hh:39)

Extends `WeakMPC` behavior by allowing individual sub-PKs to take multiple internal timesteps (subcycle) within the outer MPC timestep. Each sub-PK maintains its own tags (CURRENT, NEXT), distinct from the outer MPC's tags.

Key parameters (src/pks/mpc/mpc_subcycled.hh:10-28):
- `"subcycle"` — `Array(bool)` of length N; `true` = that sub-PK subcycles
- `"subcycling target timestep [s]"` — maximum synchronization interval

**Used by:** `MPCFlowTransport`, `MPCCoupledWaterSplitFlux`, `MPCPermafrostSplitFlux`

---

## MPCWeakSubdomain — weak coupling over a domain set

**File:** `src/pks/mpc/mpc_weak_subdomain.hh`

**PK type string:** `"domain set weak MPC"`

```cpp
class MPCWeakSubdomain : public MPC<PK> { ... };
```
(src/pks/mpc/mpc_weak_subdomain.hh:45)

Coordinates the same PK across many subdomains (a "domain set") — for example, running a Richards PK independently on each vertical column in the intermediate-scale columnar model. The number of sub-PKs is not known at input-parse time; it is determined from the domain set at runtime (src/pks/mpc/mpc_weak_subdomain.hh:67, calling `init_()`). Supports optional internal subcycling per subdomain.

---

## MPC delegate objects

Some specialized MPCs use delegate helper objects rather than sub-class overrides for globalization strategies:

### MPCDelegateEWC — energy-water content globalization

**File:** `src/pks/mpc/mpc_delegate_ewc.hh`

(src/pks/mpc/mpc_delegate_ewc.hh:97-165)

Handles the strong nonlinearity associated with phase change (the "latent heat cliff"). When a Newton iterate tries to cross the freeze-thaw front, small changes in pressure/temperature correspond to large changes in water content and energy. The EWC delegate:

1. Takes the Newton correction in (p, T) space
2. Multiplies by the local Jacobian ∂(Θ, E)/∂(p, T) to get corrections in (water content, energy) space
3. Inverts Θ(p, T) and E(p, T) locally to find the (p, T) that corresponds to the corrected (Θ, E)

This "change of variables" globalization makes the Newton iteration more robust across phase transitions. Used in `MPCSubsurface` and `MPCSurface` via `MPCDelegateEWCSubsurface` and `MPCDelegateEWCSurface`.

The EWC model (concrete thermodynamics) is provided by subclasses of `EWCModel` defined in `src/pks/mpc/constitutive_relations/`: `permafrost_model`, `liquid_ice_model`, `surface_ice_model`, `thermal_richards_model`.

### MPCDelegateWater — pressure/flux globalization

**File:** `src/pks/mpc/mpc_delegate_water_decl.hh` + `mpc_delegate_water_impl.hh` (included by `mpc_delegate_water.hh`)

Used by `MPCCoupledWater` and `MPCPermafrost` to handle globalization of the surface-subsurface water flux exchange. Three strategies are available ("pressure", "flux", "hybrid") for how the surface pressure is communicated to the subsurface Newton solve.

---

## Operator-splitting MPCs

Two MPCs implement a more elaborate two-phase operator split rather than pure weak or strong coupling:

### MPCCoupledWaterSplitFlux

**File:** `src/pks/mpc/mpc_coupled_water_split_flux.hh`

**PK type string:** `"operator split coupled water"`

(src/pks/mpc/mpc_coupled_water_split_flux.hh:122)

Splits the integrated hydrology problem into:
1. **Star system**: lateral overland flow only (surface diffusion wave)
2. **Primary system**: surface sources + subsurface Richards (no lateral surface flow)

Three coupling variants ("pressure", "flux", "hybrid") control how the star pressure communicates to the primary solve. "Hybrid" is recommended: pressure-based for runoff cells, flux-based for run-on cells.

Also supports a "domain set" mode where the primary system solves many independent 1D columns rather than a full 3D subsurface, enabling coarser-scale or column-model configurations.

### MPCPermafrostSplitFlux

**File:** `src/pks/mpc/mpc_permafrost_split_flux.hh`

**PK type string:** `"operator split permafrost"`

(src/pks/mpc/mpc_permafrost_split_flux.hh:63)

The thermal analog of `MPCCoupledWaterSplitFlux`. Extends the two-phase operator split to include energy transport: the star system advances lateral surface flow AND energy transport/diffusion, then the primary system solves integrated thermal hydrology (flow + energy) without lateral surface fluxes. Reference: Jan et al., Comp. Geosci., 2018.

---

## Specialized MPCs

### MPCFlowTransport

**File:** `src/pks/mpc/mpc_flow_transport.hh`

**PK type string:** `"coupled flow and transport"`

(src/pks/mpc/mpc_flow_transport.hh:55)

Thin subclass of `MPCSubcycled` that sets up aliased/time-interpolated evaluators so transport sees the correct piecewise-constant flux from flow. Flow is never subcycled; transport can be. Handles surface-only, subsurface-only, or integrated configurations automatically. Base class for `Morphology_PK`.

### MPCCoupledCells

**File:** `src/pks/mpc/mpc_coupled_cells.hh`

**PK type string:** `"mpc coupled cells"`

(src/pks/mpc/mpc_coupled_cells.hh:78)

A `StrongMPC<PK_PhysicalBDF_Default>` that adds cell-local off-diagonal blocks to the preconditioner. For two PDEs on the same mesh with unknowns y₁ and y₂, it adds ∂A/∂y₂ and ∂B/∂y₁ blocks (accumulation operators). Simpler than `MPCSubsurface`; lacks the non-local diffusion coupling terms.

### MPCCoupledDualMediaWater

**File:** `src/pks/mpc/mpc_coupled_dualmedia_water.hh`

**PK type string:** registered but labeled "TODO: document me" in header

(src/pks/mpc/mpc_coupled_dualmedia_water.hh:10)

Couples surface flow, macropore Richards flow, and matrix Richards flow as a three-way `StrongMPC<PK_BDF_Default>`. Uses a `TreeOperator` for the block-structured preconditioner. This is an experimental PK for dual-porosity/dual-permeability flow.

### Morphology_PK

**File:** `src/pks/mpc/mpc_morphology_pk.hh`

**PK type string:** registered via `mpc_morphology_reg.hh`

(src/pks/mpc/mpc_morphology_pk.hh:41)

Extends `MPCFlowTransport` with mesh deformation: at each `CommitStep`, it updates surface mesh vertex coordinates based on sediment transport fluxes (erosion/deposition). Requires the surface and subsurface meshes to be declared as `"deformable mesh"`.

---

## Reactive transport MPCs

Three MPCs handle the transport-chemistry operator split:

| Class | File | PK type | Description |
|---|---|---|---|
| `MPCReactiveTransport` | `mpc_reactivetransport.hh` | `"reactive transport"` | Single-domain transport then chemistry (Alquimia or Amanzi native) |
| `MPCCoupledTransport` | `mpc_coupled_transport.hh` | `"surface subsurface transport"` | Integrated (surface + subsurface) transport, weak coupling |
| `MPCCoupledReactiveTransport` | `mpc_coupled_reactivetransport.hh` | `"surface subsurface reactive transport"` | Integrated reactive transport: integrated transport then integrated chemistry |

Between the transport and chemistry steps, unit conversion is required because transport uses mole fraction [mol-C mol-H₂O⁻¹] while chemistry uses molar concentration [mol-C L⁻¹]. This conversion is done by the helpers in `chem_pk_helpers.cc` (see [chem_pk_helpers.md](chem_pk_helpers.md)).

---

## MPC composition: a worked example

A typical permafrost simulation uses the following PK tree (simplified):

```xml
"PK type" = "permafrost model"          ← MPCPermafrost
  "PKs order" = [subsurface_flow, subsurface_energy, surface_flow, surface_energy]
    "PK type" = "three phase flow"      ← Richards (leaf physics PK)
    "PK type" = "three phase energy"    ← EnergyThreePhase (leaf physics PK)
    "PK type" = "overland flow with ice" ← OverlandFlowIce (leaf physics PK)
    "PK type" = "overland energy with ice" ← OverlandEnergyIce (leaf physics PK)
```

At runtime, `MPCPermafrost` constructs all four leaf PKs via `PKFactory`, marks them all `strongly_coupled_ = true`, and drives them through a single BDF1-Newton loop. The Newton iteration calls `MPCPermafrost::FunctionalResidual`, which calls each leaf PK's `FunctionalResidual` in turn, assembling the four-component residual into the composite `TreeVector`. The preconditioner is the `TreeOperator` with the 4x4 block structure described in [mpc_subsurface.md](mpc_subsurface.md).
