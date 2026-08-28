---
**Source pin:** ATS commit `42b0e940` (`ats-1.7-dev-22-g42b0e940`)
**Last verified:** 2026-07-27
---

# Column Integrators

**Source tree:** `src/constitutive_relations/column_integrators/`

## Overview

Column integrators are a family of evaluators that scan down a subsurface column (top-to-bottom
or bottom-to-top), accumulating a quantity that is then reported as a single scalar on the
corresponding surface cell.  Examples include active-layer thickness, thaw depth, and water
table depth.  These are essential permafrost diagnostics.

All concrete integrators use a common **template framework** (`EvaluatorColumnIntegrator`) that
handles the mesh traversal.  Users provide two policy structs: a **Parser** that declares
dependencies, and an **Integrator** functor that does the cell-by-cell accumulation.

---

## 1. Template Framework -- `EvaluatorColumnIntegrator<Parser, Integrator>`

**File:** `column_integrators/EvaluatorColumnIntegrator.hh:30`

```cpp
template<class Parser, class Integrator>
class EvaluatorColumnIntegrator : public EvaluatorSecondaryMonotypeCV
```

**Evaluate loop** (`EvaluatorColumnIntegrator.hh:116-147`):
```
for each surface cell (col):
    initialize val = (0., 0.)
    for each subsurface cell in col (top to bottom):
        completed = integrator.scan(col, cell_id, val)
        if (completed) break
    result[col] = integrator.coefficient(col) * val[0] / val[1]
                  (or * val[0] if val[1] == 0, no denominator)
```

`val` is an `AmanziGeometry::Point(2)` where `val[0]` accumulates the numerator (depth,
temperature-weighted depth, etc.) and `val[1]` accumulates the denominator (total depth,
volume, etc.).  The `scan()` method returns -1 (truthy in the broken sense; actually uses
int: 0=continue, nonzero=stop) to signal early termination.

**No derivatives:** `IsDifferentiableWRT()` always returns false (`EvaluatorColumnIntegrator.hh:103-110`).
Column-integrated quantities such as thaw depth are not differentiable in a way that is useful
for the Newton solver, and they are only used as diagnostic outputs, not as primary unknowns.

**Mesh requirement:** The result lives on the surface mesh; dependencies live on the subsurface
(parent) mesh.  The `EnsureCompatibility_ToDeps_` override sets up the correct mesh / ghosting
for each (`EvaluatorColumnIntegrator.hh:80-99`).

---

## 2. `ThawDepthEvaluator`

**File:** `column_integrators/thaw_depth_evaluator.hh:56`, `thaw_depth_evaluator.cc`
**Factory key:** `"thaw depth"`

Scans from the top of each column downward, summing cell heights until the cell temperature
drops below the transition temperature (default 273.15 K = 0 degC).

```
thaw_depth[col] = sum_{cells with T > T_trans} cell_height
```

where `cell_height = cell_volume / surface_area`.

**Dependencies:**
- `"temperature"` (subsurface domain)
- `"subsurface cell volume"`
- `"surface cell volume"`

The `IntegratorThawDepth::scan()` method (`thaw_depth_evaluator.cc`) accumulates
`val[0] += cv[c] / surf_cv[col]` while `temp[c] > trans_temp_`, breaking on the first frozen
cell.

---

## 3. `ActiveLayerAverageTempEvaluator`

**File:** `column_integrators/activelayer_average_temp_evaluator.hh:55`, `activelayer_average_temp_evaluator.cc`
**Factory key:** `"active layer average temperature"`

Computes the volume-averaged temperature within the active layer (thawed zone at top of
permafrost column):

```
T_avg_AL = sum_{cells with T > T_trans} (T[c] * cv[c]) / sum_{cells with T > T_trans} cv[c]
```

**Parameters:**
- `"transition width [K]"` default 0.2 -- smoothing half-width around the 273.15 K threshold
  (uses a linear ramp rather than a hard cutoff)

**Dependencies:** `"temperature"` (subsurface).  `coefficient()` returns 1, so the result is
computed directly from `val[0]/val[1]` (volume-weighted sum / total volume).

---

## 4. `WaterTableDepthEvaluator`

**File:** `column_integrators/water_table_depth_evaluator.hh:66`, `water_table_depth_evaluator.cc`
**Factory key:** `"water table depth"`

Finds the depth to the water table by scanning from the bottom of each column upward, locating
the topmost continuously saturated cell.

Default mode (no interpolation): depth is the top face of the deepest unsaturated cell.

Interpolation mode (`"interpolate depth from pressure"` = true): Uses a linear interpolation
between the cell centroids of the last saturated and first unsaturated cells, weighted by
pressure, to sub-cell-resolve the water table position.

**Dependencies:**
- `"saturation of gas"` -- uses gas saturation to identify unsaturated cells (sat_gas > 0)
- `"pressure"`
- `"subsurface cell volume"`, `"surface cell volume"`

Note: This evaluator uses `WaterTableColumnIntegrator` (`column_integrators/WaterTableColumnIntegrator.hh`)
as its base template, a variant of `EvaluatorColumnIntegrator` that scans bottom-to-top.

---

## 5. `PerchedWaterTableDepthEvaluator`

**File:** `column_integrators/perched_water_table_depth_evaluator.hh:66`,
           `perched_water_table_depth_evaluator.cc`
**Factory key:** `"perched water table depth"`

Finds the depth to a perched water table by scanning from the top downward, locating the first
continuously unsaturated cell and reporting its bottom face as the base of the perched zone.

Uses `PerchedWaterTableColumnIntegrator` as the template base.  Same dependency set as
`WaterTableDepthEvaluator`.

---

## 6. `ColumnSumEvaluator`

**File:** `column_integrators/ColumnSumEvaluator.hh:82`, `ColumnSumEvaluator.cc`
**Factory key:** `"column sum evaluator"`

General-purpose vertical summation of any subsurface cell field onto the surface:

```
result[col] = sum_cells [integrand[c] * volume_weight] / surf_cv[col]   (if volume_factor=true)
result[col] = sum_cells  integrand[c]                                    (if volume_factor=false)
```

With optional division by liquid molar density to convert molar to volumetric quantities.

**Parameters:**
- `"include volume factor"` (default true) -- multiply by cell volume and divide by surface area
- `"divide by density"` (default true) -- divide by molar density (converts mol/s to m/s)
- `"column domain name"` -- subsurface domain (rarely set manually)

**Dependencies:**
- `"summed"` -- the integrand
- `"cell volume"`, `"surface cell volume"`
- `"molar density"` (only if `divide_by_density_=true`)

**Use cases:** Converting column transpiration (mol/m^3/s in each cell) to a total surface
flux (m/s); summing soil moisture over depth to get total soil water storage.

---

## Summary Table

| Evaluator | Scan Direction | Key Output | Notes |
|---|---|---|---|
| `ThawDepthEvaluator` | top to bottom | depth [m] to first frozen cell | permafrost ALT |
| `ActiveLayerAverageTempEvaluator` | top to bottom | vol-avg T in thawed zone | permafrost thermal |
| `WaterTableDepthEvaluator` | bottom to top | depth [m] to water table | hydrology diagnostic |
| `PerchedWaterTableDepthEvaluator` | top to bottom | depth [m] to perched WT | hydrology diagnostic |
| `ColumnSumEvaluator` | top to bottom | arbitrary sum projected to surface | general purpose |

All are diagnostic-only (no Newton derivatives), all produce surface-domain (cell) outputs.
