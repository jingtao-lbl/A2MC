---
**Source pin:** ATS commit `42b0e940` (`ats-1.7-dev-22-g42b0e940`)
**Last verified:** 2026-07-27
---

# BCFactory: Boundary Condition Factory

## Purpose

`BCFactory` is a utility class that reads boundary condition specifications from the XML input deck and constructs `BoundaryFunction` objects that physics PKs can query during `Setup()`. It provides a single reusable pattern for all BCs in ATS regardless of the specific physics PK.

**File:** `src/pks/bc_factory.hh` and `src/pks/bc_factory.cc`

```cpp
class BCFactory {
 public:
  BCFactory(const Teuchos::RCP<const AmanziMesh::Mesh>& mesh,
            const Teuchos::ParameterList& plist);

  Teuchos::RCP<Functions::BoundaryFunction> CreateWithFunction(
    const std::string& list_name, const std::string& function_name) const;

  Teuchos::RCP<Functions::BoundaryFunction> CreateWithoutFunction(
    const std::string& list_name) const;

  Teuchos::RCP<Functions::DynamicBoundaryFunction> CreateDynamicFunction(
    const std::string& list_name) const;

  bool CheckExplicitFlag(const std::string& list_name);
};
```
(src/pks/bc_factory.hh:86-127)

---

## Input XML structure

The factory reads from a `"boundary conditions"` sublist, organized hierarchically by type then by named BC specs. From the header documentation (src/pks/bc_factory.hh:19-72):

```xml
<ParameterList name="boundary conditions">
  <ParameterList name="pressure">           <!-- BC type name (list_name) -->
    <ParameterList name="BC west">          <!-- arbitrary label -->
      <Parameter name="regions" type="Array(string)" value="{west}"/>
      <ParameterList name="boundary pressure">  <!-- function_name -->
        <ParameterList name="function-constant">
          <Parameter name="value" type="double" value="101325.0"/>
        </ParameterList>
      </ParameterList>
    </ParameterList>
  </ParameterList>
  <ParameterList name="water flux">
    <ParameterList name="BC north">
      <Parameter name="regions" type="Array(string)" value="{north}"/>
      <ParameterList name="outward water flux">
        <ParameterList name="function-constant">
          <Parameter name="value" type="double" value="0."/>
        </ParameterList>
      </ParameterList>
    </ParameterList>
  </ParameterList>
  <ParameterList name="zero gradient">
    <ParameterList name="BC south">
      <Parameter name="regions" type="Array(string)" value="{south}"/>
    </ParameterList>
  </ParameterList>
</ParameterList>
```

The `list_name` (e.g., `"pressure"`, `"water flux"`, `"zero gradient"`) and the inner `function_name` (e.g., `"boundary pressure"`, `"outward water flux"`) are chosen by the calling physics PK, not by `BCFactory`. Different PKs use different names for the same abstract BC type.

---

## Factory methods

### `CreateWithFunction(list_name, function_name)`

(src/pks/bc_factory.cc:23-40)

For BCs that carry user-prescribed data (Dirichlet pressure, Neumann flux). Iterates over all named sub-specs within `list_name`, reads the `"regions"` array (mesh region names) and the `function_name` sub-list (a Amanzi `FunctionFactory` spec), and populates a `BoundaryFunction`.

Each BC spec results in a `MultiFunction` wrapping an Amanzi `Function` (constant, linear, tabular, etc.) defined on the listed mesh regions. Multiple specs in the same `list_name` are combined into a single `BoundaryFunction` that covers all their regions.

### `CreateWithoutFunction(list_name)`

(src/pks/bc_factory.cc:45-62)

For BCs that need no user-supplied data value — typically zero-gradient (natural Neumann) conditions. Reads only the `"regions"` array and creates a `BoundaryFunction` with a constant-zero function, signaling to the PK that zero-flux is prescribed on those faces.

### `CreateDynamicFunction(list_name)`

(src/pks/bc_factory.cc:65-151)

For BCs that switch type dynamically at runtime (e.g., a face that is Dirichlet in one condition and Neumann in another). Reads a `"bcs"` sub-list containing `"bc types"` and `"bc functions"` arrays, and a `"switch function"` that determines which BC is active at each evaluation time. Returns a `DynamicBoundaryFunction` that dispatches to the appropriate `BoundaryFunction` based on the switch function's value.

### `CheckExplicitFlag(list_name)`

(src/pks/bc_factory.cc:154-163)

Checks for an `"explicit time index"` boolean parameter within the BC list. If `true`, the BC is evaluated at the old time rather than the new time. This flag is consumed and removed from the parameter list on first access.

---

## BC types used by physics PKs

Each physics PK calls `BCFactory` in its `Setup()` with the appropriate `list_name` and `function_name` strings. The following mapping comes from usage in the flow and energy PKs (topic 02):

| Physics PK | BC type | `list_name` | `function_name` |
|---|---|---|---|
| Richards | Dirichlet pressure | `"pressure"` | `"boundary pressure"` |
| Richards | Neumann flux | `"water flux"` | `"outward water flux"` |
| Richards | Seepage face (pressure) | `"seepage face pressure"` | `"boundary pressure"` |
| Richards | Seepage face (head) | `"seepage face head"` | `"boundary head"` |
| Richards | Zero-gradient | `"zero gradient"` | — (no function) |
| Overland flow | Dirichlet head | `"head"` | `"boundary head"` |
| Overland flow | Fixed level | `"fixed level"` | `"fixed level"` |
| Energy | Dirichlet temperature | `"temperature"` | `"boundary temperature"` |
| Energy | Neumann heat flux | `"diffusive flux"` | `"outward diffusive flux"` |
| Energy | Enthalpy flux (advective) | `"enthalpy flux"` | `"outward enthalpy flux"` |

The `list_name` strings in the left column are what appear in the XML input deck under `"boundary conditions"`.

---

## Processing pipeline

For `CreateWithFunction`:
1. `ProcessListWithFunction_` iterates over named sub-specs in the list (src/pks/bc_factory.cc:170-189)
2. `ProcessSpecWithFunction_` reads `"regions"` and `function_name` from each sub-spec (src/pks/bc_factory.cc:195-252)
3. Constructs an Amanzi `Function` via `FunctionFactory` (supports constants, linears, composite, tabular, polynomial, ...)
4. Wraps it in a `MultiFunction`
5. Calls `bc->Define(regions, func)` and `bc->Finalize()` to register it on the mesh

For `CreateWithoutFunction`, steps 3-4 are replaced with a `FunctionConstant(0.)`.

---

## BoundaryFunction and how PKs use it

`BoundaryFunction` (Amanzi class, not ATS) maps mesh face entity IDs to double values. PKs call it as:

```cpp
// in PK Setup():
bc_pressure_ = BCFactory(mesh, plist).CreateWithFunction("pressure", "boundary pressure");

// in PK AdvanceStep() or UpdatePreconditioner():
bc_pressure_->Compute(t_new);  // evaluate all functions at time t
for (auto it = bc_pressure_->begin(); it != bc_pressure_->end(); ++it) {
  int face = it->first;
  double value = it->second;
  // set bc_markers and bc_values arrays
}
```

The result is consumed by the `Operators::BCs` object (stored in `PK_PhysicalBDF_Default::bc_`) which marks faces in the discrete operator as Dirichlet, Neumann, or interior.

---

## Dynamic BCs

`DynamicBoundaryFunction` is used for seepage-face BCs (a common permafrost/wetland feature): whether a face is a seepage face (Dirichlet at atmospheric pressure) or an impermeable boundary (Neumann zero flux) depends on whether the computed pressure at that face exceeds atmospheric. The `CreateDynamicFunction` path creates a `DynamicBoundaryFunction` that can switch between these two modes face-by-face at each Newton iteration.
