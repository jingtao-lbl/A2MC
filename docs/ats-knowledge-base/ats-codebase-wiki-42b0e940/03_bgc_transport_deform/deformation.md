---
**Source pin:** ATS commit `42b0e940` (`ats-1.7-dev-22-g42b0e940`)
**Last verified:** 2026-07-27
---

# Deformation

Source directory: `src/pks/deform/`

This is a small but scientifically critical module.  A single PK, `VolumetricDeformation`,
implements **vertical ground subsidence** driven by thaw-induced ice loss and/or water
saturation changes.  It is the primary computational mechanism for simulating
**thermokarst and permafrost ground instability** in ATS — directly relevant to the
Arctic case study in the ECRP proposal where ground instability is the cascading mechanism
linking extreme heat events to infrastructure damage.

Files:
- `src/pks/deform/volumetric_deformation.hh` — class declaration and full spec documentation
- `src/pks/deform/volumetric_deformation.cc` — full implementation (~758 lines)
- `src/pks/deform/volumetric_deformation_reg.hh` — registration

---

## `VolumetricDeformation` PK

**PK type string:** `"volumetric deformation"`

### Physics overview

The PK implements explicit (old-time) subsidence.  In each timestep it:
1. Calculates a per-cell target volume change `δV` from a chosen **deformation mode**.
2. Translates `δV` into nodal coordinate displacements via a chosen **deformation strategy**.
3. Calls the Amanzi mesh deformation API (`AmanziMesh::deform`) to move mesh nodes downward.
4. Recalculates cell volumes from the deformed mesh.
5. Updates **base porosity** to conserve solid (grain) volume:
   `φ_new = 1 - (1 - φ_old) * V_old / V_new`
   (src/pks/deform/volumetric_deformation.cc:677-679).
6. Commits or reverts vertex coordinates on success or failure.

All deformation is **purely vertical** and requires a **columnar subsurface mesh** with
`build_columns` enabled (src/pks/deform/volumetric_deformation.hh:32).

The primary variable stored in State is `base_porosity`, which serves as a record of the
reference (undeformed) solid volume fraction.  The working mesh itself is obtained as a
non-const `Teuchos::RCP<AmanziMesh::Mesh> mesh_nc_` via `S_->GetDeformableMesh(domain_)`
(src/pks/deform/volumetric_deformation.cc:115).

Vertex coordinates are stored in State (field `vertex_loc_key_`) so that deformed
positions survive checkpointing and restart.

---

## Deformation modes (how `δV` is computed)

Set by `"deformation mode"` parameter.

### Mode 1: `"prescribed"` (enum `DEFORM_MODE_DVDT`)

Volume change per unit time is prescribed as a space-time function via
`"deformation function"` (a `CompositeVectorFunction`).  Useful for testing or imposing
externally computed subsidence rates.  `δV = f(t, x, y, z) * dt`
(src/pks/deform/volumetric_deformation.cc:347).

### Mode 2: `"structural"` (enum `DEFORM_MODE_STRUCTURAL`)

Simulates ice-propped soil structure collapse.  A cell subsides when the combined solid +
ice volume fraction falls below a threshold `structural_vol_frac_` (default 0.45):

```
f_s = 1 - φ         (solid fraction)
f_i = φ * S_ice     (ice fraction)
if (f_s + f_i < structural_vol_frac_) and (pressure not over-limit):
    frac = (structural_vol_frac_ - (f_s + f_i)) * (dt / time_scale_)
    δV = -frac * V
```

(src/pks/deform/volumetric_deformation.cc:438-451)

This is the most physically relevant mode for permafrost ground instability modeling.  As
ice melts (S_ice decreases), the ice fraction f_i drops below the structural threshold and
the cell volume decreases, creating a downward displacement.  The `time_scale_` parameter
controls how fast collapse occurs relative to the thermal forcing.

An overpressure guard `overpressured_limit_` prevents deformation when liquid pressure is
still very high relative to the base porosity (prevents destabilizing flow numerical
solutions) (src/pks/deform/volumetric_deformation.cc:445-447).

### Mode 3: `"saturation"` (enum `DEFORM_MODE_SATURATION`)

A heuristic based directly on liquid saturation.  Deformation occurs when `S_liq > min_S_liq_`
(the ice has thawed enough to release liquid water) and the current porosity exceeds a
minimum structural porosity `min_porosity_` (default 0.5):

```
frac = min(
    (φ₀ - min_porosity_) / (1 - min_porosity_),
    deform_scaling_ * ((1 - S_ice) - min_S_liq_) * φ₀
)
δV = -frac * V
```

(src/pks/deform/volumetric_deformation.cc:386-393)

The `deform_scaling_` parameter controls the sensitivity.

---

## Deformation strategies (how `δV` → nodal displacements)

Set by `"deformation strategy"` parameter.

### Strategy 1: `"average"` (enum `DEFORM_STRATEGY_AVERAGE`)

Recommended for columnar (1D/column) problems.  For each column, iterates bottom-to-top
accumulating face displacements from fractional volume losses, then averages nodal
displacements across neighboring faces:

```
face_displacement += -dz * (δV_cell / V_cell)
```

(src/pks/deform/volumetric_deformation.cc:562-587)

Then uses `AmanziMesh::deform(*mesh_nc_, node_ids, new_positions)` to apply the moves
(src/pks/deform/volumetric_deformation.cc:617).

The surface mesh (`domain_surf_3d_`) is updated to follow the subsurface node positions
(src/pks/deform/volumetric_deformation.cc:629-648).

### Strategy 2: `"mstk implementation"` (enum `DEFORM_STRATEGY_MSTK`)

Uses MSTK's iterative local node-repositioning algorithm.  In principle better for 2D/3D
problems.  **Currently throws an error** at runtime because the Amanzi mesh deformation
call is commented out (src/pks/deform/volumetric_deformation.cc:536-538):
```cpp
Errors::Message mesg("Volumetric Deformation not implemented in Amanzi");
Exceptions::amanzi_throw(mesg);
```
This strategy is not functional at this commit.

### Strategy 3: `"global optimization"` (enum `DEFORM_STRATEGY_GLOBAL_OPTIMIZATION`)

Also **disabled at this commit**.  The parse code immediately throws an error
(src/pks/deform/volumetric_deformation.cc:77-78):
```cpp
Errors::Message mesg("Deformation strategy \"global optimization\" is no longer supported.");
Exceptions::amanzi_throw(mesg);
```

**Practical conclusion:** Only `"average"` strategy is functional at this commit.

---

## Key evaluated fields consumed

| Field | Unit | Used in |
|---|---|---|
| `saturation_ice` | — | structural and saturation modes |
| `saturation_liquid` | — | saturation mode |
| `saturation_gas` | — | saturation mode |
| `porosity` | — | all modes except prescribed |
| `cell_volume` | m³ | all modes |

All these are consumed at `tag_current_` (old time) — the PK is fully explicit.

---

## Coupling to flow

The deformation PK is described as "slaved to the flow PK" and must be advanced first
within a coupled step (src/pks/deform/volumetric_deformation.hh:18-20).  After deformation
moves nodes, the `cell_volume` evaluator (which uses the `"deforming cell volume"` evaluator
type) recomputes cell volumes from the new mesh geometry.  The flow PK then sees the
updated geometry in its next solve.

The `"deforming cell volume"` evaluator type is injected automatically if `cv_eval_list`
is empty (src/pks/deform/volumetric_deformation.cc:197-204).

---

## ECRP relevance

For the Arctic case study in the proposed AI-enhanced hierarchical modeling framework,
`VolumetricDeformation` is the ATS mechanism that represents **permafrost thaw-driven
ground instability**.  In the ECRP modeling chain:

1. ELM provides large-scale permafrost state (ground temperature, active layer depth).
2. ATS + `VolumetricDeformation` resolves fine-scale thaw-driven subsidence at hyper-
   resolution, computing how ice-rich permafrost cells lose volume as ice melts.
3. The resulting mesh deformation alters surface topography, drainage patterns, and
   ponding — which are the signals that cascade to infrastructure exposure.

The `"structural"` deformation mode is most physically grounded for this application.
The key limitation is that only the `"average"` strategy is currently functional,
making 3D lateral heterogeneity of subsidence difficult to capture; this is an area
where MSTK or other strategies would be needed for full 2D/3D thermokarst simulations.

---

## Class hierarchy

```
PK_Physical_Default
  └── VolumetricDeformation
```

Registration: `src/pks/deform/volumetric_deformation_reg.hh`.
