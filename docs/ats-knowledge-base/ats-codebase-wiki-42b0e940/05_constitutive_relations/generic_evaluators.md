---
**Source pin:** ATS commit `42b0e940` (`ats-1.7-dev-22-g42b0e940`)
**Last verified:** 2026-07-27
---

# Generic Evaluators

**Source tree:** `src/constitutive_relations/generic_evaluators/`

These evaluators perform algebraic combinations of other fields, time-tracking operations, and
subgrid domain scatter/gather.  They do not implement any physical constitutive law; instead
they serve as the "wiring" of the evaluator DAG, allowing composite fields to be assembled
without writing new C++ for every combination.

All classes are `EvaluatorSecondaryMonotypeCV` subclasses registered with the Amanzi
`Evaluator_Factory`.

---

## 1. `AdditiveEvaluator`

**File:** `generic_evaluators/AdditiveEvaluator.hh:42`, `AdditiveEvaluator.cc`
**Factory key:** `"additive evaluator"`

Computes a weighted sum of dependency fields plus an optional constant:

```
result = shift + sum_i (coef_i * dep_i)
```

Each dependency gets a scalar coefficient read from the input deck as
`"DEPENDENCY coefficient"`.  Default coefficient is 1.0.  Optional `"enforce positivity"` flag
clamps the result to zero from below.

**Derivatives:** Each partial derivative is just the corresponding coefficient.

**Use cases:** Summing rain + snowmelt to form total precipitation source; adding a constant
background contribution to a flux.

---

## 2. `MultiplicativeEvaluator`

**File:** `generic_evaluators/MultiplicativeEvaluator.hh:45`, `MultiplicativeEvaluator.cc`
**Factory key:** `"multiplicative evaluator"`

Computes the product of all dependency fields, scaled by a constant prefix:

```
result = coef * prod_i dep_i
```

Optional `"DEPENDENCY dof"` selects which degree-of-freedom to use if a dependency has
multiple DOFs.  `"enforce positivity"` available.  Derivatives computed via the usual
product-rule quotient.

**Use cases:** Combining relative permeability, absolute permeability, and density to form
effective hydraulic conductivity; multiplying a volumetric source by a molar density.

---

## 3. `ReciprocalEvaluator`

**File:** `generic_evaluators/ReciprocalEvaluator.hh:24`, `ReciprocalEvaluator.cc`
**Factory key:** `"reciprocal evaluator"`

Computes:
```
result = coef / reciprocal_field
```

The field to be inverted is specified by `reciprocal_key_`.  The remaining dependencies are
multiplied into the numerator.  Useful for e.g. converting molar flux to volumetric flux
without writing a custom evaluator.

---

## 4. `ExtractionEvaluator`

**File:** `generic_evaluators/ExtractionEvaluator.hh:25`, `ExtractionEvaluator.cc`
**Factory key:** `"extraction evaluator"`

Restricts a field defined on a parent mesh to a child mesh using parent entity relationships:

```
result[child_entity] = dependency[parent_entity_of(child_entity)]
```

Used when a variable is defined on the full subsurface mesh but only needs to be accessed on a
sub-domain (e.g., a fracture network or a lake bed mesh embedded in the subsurface).

No derivatives implemented.

---

## 5. `InitialTimeEvaluator`

**File:** `generic_evaluators/InitialTimeEvaluator.hh:35`, `InitialTimeEvaluator.cc`
**Factory key:** `"initial value"`

Captures the value of a dependency field at a prescribed initial time and holds it constant
thereafter:

```
result = dep[t == t_initial]
```

**Parameters:**
- `"initial time"` -- time to snapshot, default 0
- `"initial time units"` -- units, default `"s"`

The result must be checkpointed because it cannot be reconstructed from the current state alone
(`InitialTimeEvaluator.cc:EnsureCompatibility_Flags_`).

**Use cases:** Recording initial soil moisture for relative-change diagnostics; capturing
initial ALT as a baseline for permafrost change metrics.

---

## 6. `TimeMaxEvaluator`

**File:** `generic_evaluators/TimeMaxEvaluator.hh:33`, `TimeMaxEvaluator.cc`
**Factory key:** `"max in time"` (a single evaluator; min vs max is selected via the `"operator"` parameter, `"min"` or `"max"` — there is no separate `"time min evaluator"` key)

Maintains a pointwise running maximum (or minimum) of a dependency field over simulation time:

```
result[c] = max_{t' <= t} dep[c, t']   (or min)
```

The `"operator"` parameter selects `"max"` (default) or `"min"`.  State is accumulated across
time steps; it cannot be reconstructed on restart without checkpointing.

**Use cases:** Tracking maximum thaw depth reached, maximum inundation depth, maximum near-
surface temperature.  Used in permafrost diagnostics.

---

## 7. `SubgridAggregateEvaluator`

**File:** `generic_evaluators/SubgridAggregateEvaluator.hh:34`, `SubgridAggregateEvaluator.cc`
**Factory key:** `"subgrid aggregate evaluator"`

Aggregates (area-averages) a field defined on a subgrid domain set back to the parent domain:

```
result[parent_cell] = sum_i (dep[subgrid_i] * area_i) / total_area
```

**Source domain:** specified by `"source domain name"`.  The evaluator loops over all subgrid
patches that correspond to each parent cell and area-weights the values.

**Use cases:** Returning sub-column (e.g., snow column or vegetation patch) results to the
surface grid for coupling with overland flow or output.

---

## 8. `SubgridDisaggregateEvaluator`

**File:** `generic_evaluators/SubgridDisaggregateEvaluator.hh:37`, `SubgridDisaggregateEvaluator.cc`
**Factory key:** `"subgrid disaggregate evaluator"`

The inverse of SubgridAggregateEvaluator.  Copies a value from the parent domain into one
subgrid patch:

```
result[subgrid_patch_k] = source[parent_cell_of(patch_k)]
```

There is one evaluator instance per subgrid patch (identified by `domain_index_`).

**Use cases:** Broadcasting a surface pressure or temperature to all sub-columns in a hillslope
decomposition so that each sub-column PK sees the correct atmospheric boundary condition.

---

## Summary

| Class | Key | Operation |
|---|---|---|
| `AdditiveEvaluator` | `"additive evaluator"` | weighted sum + shift |
| `MultiplicativeEvaluator` | `"multiplicative evaluator"` | scaled product |
| `ReciprocalEvaluator` | `"reciprocal evaluator"` | coef / field |
| `ExtractionEvaluator` | `"extraction evaluator"` | restrict to child mesh |
| `InitialTimeEvaluator` | `"initial value"` | snapshot at t0 |
| `TimeMaxEvaluator` | `"max in time"` | running max/min over time (min via `"operator"` param) |
| `SubgridAggregateEvaluator` | `"subgrid aggregate evaluator"` | subgrid -> parent |
| `SubgridDisaggregateEvaluator` | `"subgrid disaggregate evaluator"` | parent -> one patch |
