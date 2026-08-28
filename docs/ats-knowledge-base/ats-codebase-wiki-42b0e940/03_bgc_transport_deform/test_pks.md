---
**Source pin:** ATS commit `42b0e940` (`ats-1.7-dev-22-g42b0e940`)
**Last verified:** 2026-07-27
---

# Test PKs

Source directory: `src/pks/test_pks/`

Two lightweight PKs exist solely for operator-level testing in the ATS regression harness.
They are not intended for scientific production runs.

Files:
- `src/pks/test_pks/divgrad_test/` — tests the div-grad (diffusion) operator
- `src/pks/test_pks/test_snow_dist/` — tests snow redistribution logic

---

## 1. `DivGradTest` — diffusion operator test

**Files:**
- `src/pks/test_pks/divgrad_test/divgrad_test.{hh,cc}` — class and implementation
- `src/pks/test_pks/divgrad_test/divgrad_test_reg.hh` — registration
- `src/pks/test_pks/divgrad_test/test_pk_bc_factory.hh` — boundary condition factory stub

### Purpose

Exercises the Mimetic Finite Difference (MFD) `MatrixMFD` operator for a simple
div-grad problem.  Used to verify that the operator and boundary condition infrastructure
work correctly before running full coupled problems.

### Implementation notes

`DivGradTest` inherits from the **old-style** `PKPhysicalBase` base class
(src/pks/test_pks/divgrad_test/divgrad_test.hh:21-22):
```cpp
#include "pk_factory_ats.hh"
#include "pk_physical_base.hh"
```

Note: `pk_factory_ats.hh` and `pk_physical_base.hh` are Amanzi-provided legacy headers,
not present in the ATS source tree itself. They are resolved at build time from Amanzi's
include paths. The modern equivalents within ATS are `src/pks/pk_physical_bdf_default.hh`
(for implicitly integrated PKs) and `src/pks/pk_physical_explicit_default.hh`.

This old API (`pk_factory_ats`, `PKPhysicalBase`, `PKDefaultBase`) is the legacy pre-ATS-1.x
interface.  It uses `setup()`/`initialize()`/`advance()` method names (lowercase) rather
than the modern `Setup()`/`Initialize()`/`AdvanceStep()` pattern.  The old-style
`MatrixMFD` operator is used rather than the current `PDE_Diffusion` / `Operators::Operator`
stack.

The PK builds Dirichlet and Neumann boundary conditions, assembles the MFD matrix, solves,
and checks for regularity of the face values (`TestRegularFaceValues_`).

**Practical note:** This PK is primarily a historical artifact.  Current operator tests
would use the modern `src/operators/` framework directly.  It is registered with
`RegisteredPKFactory_ATS` (the old factory), not the current `RegisteredPKFactory`.

---

## 2. `TestSnowDist` — snow distribution test

**Files:**
- `src/pks/test_pks/test_snow_dist/test_snow_dist.{hh,cc}` — class and implementation
- `src/pks/test_pks/test_snow_dist/test_snow_dist_reg.hh` — registration

### Purpose

Tests the snow redistribution algorithm on a toy problem.  The PK advances snow depth
with a fixed timestep of 86400 s (1 day) (src/pks/test_pks/test_snow_dist/test_snow_dist.hh:50).

Supports an optional sink type and sink value to simulate snow disappearance:
- `"sink type"` — parameter key name for the sink type (default `"none"`)
- `"sink value"` — sink magnitude (default 1.0)
(src/pks/test_pks/test_snow_dist/test_snow_dist.hh:33-34)

The primary variable is `"snow_depth"` [m].

### Implementation notes

Also uses the old-style `PKPhysicalBase` / `RegisteredPKFactory_ATS` API
(src/pks/test_pks/test_snow_dist/test_snow_dist.hh:7,61).  Same legacy pattern as
`DivGradTest`.

---

## How test_pks fits into the regression harness

ATS regression tests live in `testing/ats-regression-tests/` (a separate subrepository).
Each test case is an XML input deck paired with a `test_<name>.py` script or a `CMakeLists.txt`
entry that runs the ATS executable and checks outputs.

The test PKs are registered PKs and can be named in an input deck like any production PK:
```xml
<ParameterList name="cycle driver">
  <ParameterList name="PKs">
    <ParameterList name="divgrad_test">
      <Parameter name="PK type" type="string" value="div-grad operator test"/>
      ...
    </ParameterList>
  </ParameterList>
</ParameterList>
```

They serve a specific purpose: **isolate operator-level correctness** from the full coupled
physics complexity.  By testing `DivGradTest` against an analytical solution, developers
can verify that mesh, operator assembly, and linear solve all work before attempting
coupled flow/energy.

`TestSnowDist` plays the same role for the snow redistribution scheme embedded in the
`ImplicitSubgrid` PK logic, allowing it to be tested on simple geometries.

---

## Summary table

| PK | Type string | Base class style | Primary variable | Timestep |
|---|---|---|---|---|
| `DivGradTest` | `"div-grad operator test"` | Old (PKPhysicalBase) | `"solution"` | `1e99` (static) |
| `TestSnowDist` | `"snow distribution test"` | Old (PKPhysicalBase) | `"snow_depth"` | 86400 s (1 day) |
