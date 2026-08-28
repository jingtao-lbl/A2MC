---
**Source pin:** ATS commit `42b0e940` (`ats-1.7-dev-22-g42b0e940`)
**Last verified:** 2026-07-27
---

# Upwinding Strategies (`upwinding/`)

The upwinding layer is responsible for one specific task: given a cell-centered nonlinear coefficient (e.g., relative permeability `kr`, Manning conductivity), compute a face-centered value that is appropriate for use in the div-grad operator `MatrixMFD`. This face value must account for flow direction to avoid oscillations and instability.

All upwinding classes implement the `Upwinding` abstract interface (`src/operators/upwinding/upwinding.hh`). The factory `UpwindFactory::Create()` selects the concrete class from the input deck.

## The Upwinding interface

```cpp
class Upwinding {
  virtual void Update(const CompositeVector& data,
                      CompositeVector& uw_data,
                      const State& S, ...) = 0;

  virtual void UpdateDerivatives(...,
    std::vector<Teuchos::RCP<Teuchos::SerialDenseMatrix<int,double>>>* Jpp_faces) const;

  virtual std::string CoefficientLocation() const = 0;
};
```

`Update` maps cell-centered coefficients to face-centered coefficients; `UpdateDerivatives` computes the Jacobian contribution from the nonlinear upwinding for use in Newton iteration (not all strategies implement this); `CoefficientLocation` returns a tag string (`"upwind: face"` or `"standard: cell"`) that tells the div-grad operator where to look for the coefficient (`src/operators/upwinding/upwinding.hh:36`).

## UpwindMethod enum

The following numeric values are declared but exist only for documentation; the factory uses string keys (`src/operators/upwinding/upwinding.hh:36`):

```
UPWIND_METHOD_CENTERED           = 0
UPWIND_METHOD_GRAVITY            = 1
UPWIND_METHOD_TOTAL_FLUX         = 2
UPWIND_METHOD_NO_DENOMINATOR     = 3
UPWIND_METHOD_ARITHMETIC_MEAN    = 4
UPWIND_METHOD_POTENTIAL_DIFFERENCE = 5
```

## Concrete strategies

### 1. UpwindTotalFlux (`upwind_total_flux.{hh,cc}`)

**Input key:** `"manning upwind"` (via `UpwindFluxFactory`)

**CoefficientLocation:** `"upwind: face"`

Standard first-order upwind based on the sign of the pre-computed Darcy/total flux vector. For each face, identifies the upwind cell (`flux * face_dir > 0`) and assigns its cell-centered coefficient to the face. Near zero flux (within `flux_eps_`, default `1e-8`), applies a smooth linear blend between upwind and downwind values using parameter `param = |flux| / (2*flux_eps) + 0.5` (`src/operators/upwinding/upwind_total_flux.cc:158`).

`UpdateDerivatives` computes `dK/dp` contributions per face for Newton linearization, accounting for the smooth transition region (`src/operators/upwinding/upwind_total_flux.cc:181`). This is the primary Richards/overland upwinding method.

### 2. UpwindFluxHarmonicMean (`upwind_flux_harmonic_mean.{hh,cc}`)

**Input key:** `"manning harmonic mean"`

**CoefficientLocation:** `"upwind: face"`

Uses the harmonic mean of neighboring cell coefficients as the face value. The factory comment warns this is dangerous because harmonic mean can give zero face conductivity when one neighbor has zero conductivity (dry cell), which almost never gives the physically correct answer (`src/operators/upwinding/UpwindFluxFactory.cc:46`). It remains available but is not recommended.

### 3. UpwindFluxSplitDenominator (`upwind_flux_split_denominator.{hh,cc}`)

**Input key:** `"manning split denominator"`

**CoefficientLocation:** `"upwind: face"`

Splits the Manning conductivity into a numerator (ponded depth) and denominator (Manning coefficient, slope) and upwinds them separately. This is useful for overland flow where the Manning coefficient varies spatially: the numerator (depth-dependent) uses the total flux direction for upwinding, while the denominator terms (slope, Manning n) may use different averaging. Requires additional keys: `slope`, `manning_coef` (`src/operators/upwinding/UpwindFluxFactory.cc:67`).

### 4. UpwindElevationStabilized (`upwind_elevation_stabilized.{hh,cc}`)

**Input key:** `"manning elevation stabilized"`

**CoefficientLocation:** `"upwind: face"`

A stability-enhanced upwinding scheme for overland flow on steep terrain. Incorporates `slope`, `manning_coef`, `ponded_depth`, `elevation`, and `molar_density_liquid` fields. The Manning exponent (default `2/3`) is tunable via input parameter `"Manning exponent"` (`src/operators/upwinding/UpwindFluxFactory.cc:95`). The elevation gradient is used to stabilize upwinding near wetting fronts.

### 5. UpwindFluxFOCont (`upwind_flux_fo_cont.{hh,cc}`)

**Input key:** `"manning ponded depth passthrough"`

**CoefficientLocation:** `"upwind: face"`

First-order continuous (FO-Cont) scheme for Manning overland flow. Uses flux direction, slope, Manning coefficient, and elevation to compute the face conductivity. Passes the ponded depth through (as the name implies) without re-averaging. Requires `flux`, `slope`, `manning_coef`, `elevation` keys; `slope_regularization` and `Manning exponent` are tunable (`src/operators/upwinding/UpwindFluxFactory.cc:121`).

### 6. UpwindGravityFlux (`upwind_gravity_flux.{hh,cc}`)

**Input key:** not in `UpwindFluxFactory` (instantiated directly)

**CoefficientLocation:** `"upwind: face"`

Upwinds based on the sign of `K * g` dotted with the face normal (i.e., the gravity-driven flux component alone, not the total Darcy flux). Pulls gravity from `State` as `AmanziGeometry::Point("gravity", Tags::DEFAULT)` and uses the intrinsic permeability tensor `K` (passed at construction) to compute `K * g` per cell. Near zero gravity flux, takes the arithmetic mean (`src/operators/upwinding/upwind_gravity_flux.cc:93`). Used for gravity-dominated flow problems or as a fallback.

### 7. UpwindArithmeticMean (`upwind_arithmetic_mean.{hh,cc}`)

**Input key:** not in `UpwindFluxFactory` (instantiated directly)

**CoefficientLocation:** `"upwind: face"`

Simple arithmetic mean of the two neighboring cell coefficients. Flow-direction-independent; symmetric. Implements `UpdateDerivatives` so it can contribute to Newton Jacobian assembly. Used when physical reasoning favors averaging over upwinding (e.g., symmetric thermal conductivity).

### 8. UpwindCellCentered (`upwind_cell_centered.{hh,cc}`)

**Input key:** `"manning cell centered"` (via `UpwindFluxFactory`)

**CoefficientLocation:** `"standard: cell"`

Does not interpolate to faces at all. Instead, returns `"standard: cell"` as the coefficient location, which signals `MatrixMFD::CreateMFDstiffnessMatrices` to use the cell-centered value directly (scaling the entire row of the local mass matrix by the cell coefficient, not the face coefficient). This is the simplest possible option and incurs no parallelism overhead. Used for problems where the coefficient varies smoothly at the cell scale.

### 9. UpwindPotentialDifference (`upwind_potential_difference.{hh,cc}`)

**Input key:** not in `UpwindFluxFactory` (instantiated directly)

**CoefficientLocation:** `"upwind: face"`

Upwinds based on the sign of the potential difference across a face (rather than the pre-computed flux). Supports an optional `overlap` field. Implements `UpdateDerivatives` for Newton Jacobian. Used in specialized formulations where flux is not pre-computed or where the potential difference is the more reliable direction indicator.

## Factory: UpwindFluxFactory

`UpwindFactory::Create()` (`src/operators/upwinding/UpwindFluxFactory.cc:28`) is the public entry point. It reads `"upwind type"` and `"upwind flux epsilon"` from the operator parameter list, then registers required State fields with `S.Require<>()` before constructing the concrete class.

Strategies available through the factory (`src/operators/upwinding/UpwindFluxFactory.cc:39`):

| `"upwind type"` value | Class created |
|---|---|
| `"manning upwind"` (default) | `UpwindTotalFlux` |
| `"manning harmonic mean"` | `UpwindFluxHarmonicMean` |
| `"manning split denominator"` | `UpwindFluxSplitDenominator` |
| `"manning elevation stabilized"` | `UpwindElevationStabilized` |
| `"manning ponded depth passthrough"` | `UpwindFluxFOCont` |
| `"manning cell centered"` | `UpwindCellCentered` |

`UpwindGravityFlux`, `UpwindArithmeticMean`, and `UpwindPotentialDifference` are not in the factory and must be instantiated directly by the PK.

## Newton Jacobian support (UpdateDerivatives)

Four strategies implement `UpdateDerivatives`: `UpwindTotalFlux`, `UpwindFluxHarmonicMean`, `UpwindArithmeticMean`, and `UpwindPotentialDifference`. The output is a per-face vector of 2x2 dense matrices (`Jpp_faces`) representing the derivative of the face coefficient with respect to the two neighboring cell potentials. These are used by PKs that apply a Newton correction at the operator level. The base class `UpdateDerivatives` asserts and aborts (`src/operators/upwinding/upwinding.hh:64`), so PKs must not call it on classes that do not override it.

## Integration with MatrixMFD

After `Update()` produces the face-centered coefficient in a `CompositeVector`, the PK passes it as `Krel` to `MatrixMFD::CreateMFDstiffnessMatrices(Krel)`. The `CoefficientLocation()` return value determines whether the PK should look in the `"face"` or `"cell"` component of that vector when invoking `CreateMFDstiffnessMatrices` (`src/operators/divgrad/MatrixMFD.cc:268`).
