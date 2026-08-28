---
**Source pin:** ATS commit `42b0e940` (`ats-1.7-dev-22-g42b0e940`)
**Last verified:** 2026-07-27
---

# PK Base Classes

## Overview

Every process kernel in ATS — whether a standalone solver for Richards flow or a coupler that orchestrates four sub-PKs — derives from a small number of base classes defined in `src/pks/`. The base classes are provided partly by Amanzi (the abstract `PK` interface and `PK_BDF`, `PK_Explicit`, `PK_Physical_Default`) and partly by ATS (the `*_default` concrete bases). This page documents the ATS-level defaults.

## Abstract PK interface (Amanzi, out-of-scope for deep docs)

`PK` is defined in Amanzi and provides the canonical lifecycle:

```
Setup()          — declare variables, operators, evaluators
Initialize()     — set initial conditions, initialize time-stepper
get_dt()         — propose next time step size
set_dt(dt)       — accept time step size from coordinator
AdvanceStep(t0, t1, reinit) → bool  — attempt time step; return true = fail
CommitStep(t0, t1, tag)     — finalize, copy NEXT → CURRENT
FailStep(t0, t1, tag)       — roll back, restore CURRENT
CalculateDiagnostics(tag)   — diagnostic output hook
ChangedSolutionPK(tag)      — notify DAG that primary variable changed
```

All ATS physics PKs and MPCs override subsets of these methods. The four ATS base classes implement the bulk of this interface, leaving only a few pure-virtual hooks for the concrete physics PK.

---

## PK_BDF_Default

**File:** `src/pks/pk_bdf_default.hh` and `src/pks/pk_bdf_default.cc`

**Inherits:** `PK_BDF` (Amanzi), which inherits `PK`

**Purpose:** Default implementation for PKs that are integrated in time using a Backward Difference Formula (BDF1, i.e. backward Euler with adaptive step control). Both physical PKs (Richards, energy) and MPCs that are solved globally-implicitly inherit from this class.

### Key members

```cpp
class PK_BDF_Default : public PK_BDF {
  bool assemble_preconditioner_;   // whether this PK assembles its own PC
  bool strongly_coupled_;          // if true, skip creating a local time integrator
  double dt_next_;                 // proposed next dt
  Teuchos::RCP<BDF1_TI<TreeVector,TreeVectorSpace>> time_stepper_;  // BDF1 integrator
};
```
(src/pks/pk_bdf_default.hh:115-124)

### Lifecycle implementations

**`Setup()`** (src/pks/pk_bdf_default.cc:31-47): reads `"assemble preconditioner"` (default `true`) and `"strongly coupled PK"` (default `false`) from the parameter list. When `strongly_coupled_` is true, this PK is nested inside a `StrongMPC` and must **not** create its own time integrator; the MPC owns the Newton/BDF loop.

**`Initialize()`** (src/pks/pk_bdf_default.cc:54-79): if not strongly coupled, constructs the `BDF1_TI` time integrator from the `"time integrator"` sublist and sets the initial state. If strongly coupled, skips — the owning MPC initializes the shared time integrator.

**`get_dt()`** (src/pks/pk_bdf_default.cc:87-91): returns `dt_next_`, which is set either from the BDF1 controller's suggestion after the previous step or by `set_dt()`.

**`AdvanceStep(t_old, t_new, reinit)`** (src/pks/pk_bdf_default.cc:116-147): calls `time_stepper_->AdvanceStep(dt, dt_next_, solution_)`. On `TimestepCrash`, wraps the error with PK name and timestep context before rethrowing.

**`CommitStep(t_old, t_new, tag)`** (src/pks/pk_bdf_default.cc:101-109): calls `time_stepper_->CommitSolution(dt, solution_)` only when `tag == tag_next_` (not on diagnostic commits) and only when `dt > 0`.

### Abstract hooks that derived classes must implement

- `ChangedSolution()` / `ChangedSolution(const Tag&)` — notify the DAG evaluator that the primary variable has changed (src/pks/pk_bdf_default.hh:112-113)
- `FunctionalResidual(...)` — the PDE residual function (inherited from `BDFFnBase` via `PK_BDF`)
- `UpdatePreconditioner(...)` / `ApplyPreconditioner(...)` — preconditioner

### The `strongly_coupled_` flag

This is the key mechanism by which a `StrongMPC` suppresses redundant time integrators in its child PKs. During `StrongMPC::parseParameterList()`, it calls:

```cpp
pks_list_->sublist(pk_name).set("strongly coupled PK", true);
```
(src/pks/mpc/strong_mpc.hh:150-152)

so every child PK sees `strongly_coupled_ = true` at Setup time and skips constructing its own `BDF1_TI`. Only the MPC at the top of the strongly-coupled block owns the Newton loop.

---

## PK_Explicit_Default

**File:** `src/pks/pk_explicit_default.hh` and `src/pks/pk_explicit_default.cc`

**Inherits:** `PK_Explicit<TreeVector>` (Amanzi)

**Purpose:** Base for PKs integrated with explicit Runge-Kutta methods. Used primarily for transport and some surface-energy-balance PKs.

### Key members

```cpp
class PK_Explicit_Default : public PK_Explicit<TreeVector> {
  double dt_;                                              // current timestep
  Teuchos::RCP<Explicit_TI::RK<TreeVector>> time_stepper_; // RK integrator
  Teuchos::RCP<TreeVector> solution_old_;                  // solution at t_old
};
```
(src/pks/pk_explicit_default.hh:55-63)

**`AdvanceStep`** calls the RK integrator, which in turn calls the PK's `FunctionalResidual` (the right-hand-side function) once per stage.

---

## PK_PhysicalBDF_Default

**File:** `src/pks/pk_physical_bdf_default.hh` and `src/pks/pk_physical_bdf_default.cc`

**Inherits:** `PK_BDF_Default` and `PK_Physical_Default` (multiple inheritance, diamond resolved through virtual `PK` base)

**Purpose:** The workhorse base for nearly all ATS conservation-equation PKs (Richards, energy, transport equations on subsurface or surface). Combines the time-integration machinery of `PK_BDF_Default` with the mesh/domain awareness of `PK_Physical_Default`, and adds:

1. A **conserved-quantity error norm** suited for conservation equations
2. A **boundary condition container** (`Operators::BCs`)
3. A **preconditioner operator** slot
4. `ChangedSolution()` implementation via the DAG evaluator
5. `IsValid()` check via `max_valid_change`

### Key members

```cpp
class PK_PhysicalBDF_Default
  : public PK_BDF_Default
  , public PK_Physical_Default {
  Teuchos::RCP<Operators::Operator> preconditioner_;
  Teuchos::RCP<Operators::BCs>      bc_;
  double                            max_valid_change_;
  Key                               conserved_key_;   // e.g. "water_content"
  Key                               cell_vol_key_;
  double atol_, rtol_, fluxtol_;
};
```
(src/pks/pk_physical_bdf_default.hh:119-133)

### Error norm

The default `ErrorNorm` (src/pks/pk_physical_bdf_default.cc:98-174) implements:

```
ENORM(u, du) = |h * du| / (atol * cell_volume + rtol * |conserved_quantity_old|)
```

For face unknowns (fluxes), `fluxtol` is used as an additional scaling. This norm is physics-aware: `conserved_quantity_old` is the actual extensive quantity (e.g., moles of water in a cell) from the previous accepted timestep, so the norm has physical units and reasonable absolute scales without tuning.

### `ChangedSolution(const Tag& tag)`

(src/pks/pk_physical_bdf_default.cc:232-238): retrieves the `EvaluatorPrimaryCV` for the primary variable key and calls `SetChanged()`, which marks the evaluator as dirty in the DAG so dependent evaluators (saturation, density, etc.) are recomputed on next access.

### `CommitStep`

(src/pks/pk_physical_bdf_default.cc:204-215): calls both `PK_BDF_Default::CommitStep` (commits the BDF1 controller) and `PK_Physical_Default::CommitStep` (copies state), then copies the conserved quantity from NEXT to CURRENT tag.

---

## PK_Physical_Default_Explicit_Default

**File:** `src/pks/pk_physical_explicit_default.hh` (header-only, no .cc)

**Inherits:** `PK_Explicit_Default` and `PK_Physical_Default`

**Purpose:** The explicit analog of `PK_PhysicalBDF_Default`, for PKs that are advanced with explicit Runge-Kutta (e.g., some surface-energy-balance formulations, snow). Much simpler than the implicit version: `Setup` and `Initialize` just call both base class versions in order, and `AdvanceStep` delegates to `PK_Explicit_Default` then calls `ChangedSolutionPK`.

(src/pks/pk_physical_explicit_default.hh:42-66)

---

## Lifecycle sequence diagram

```
Coordinator
  │
  ├─ Setup()          ─── parseParameterList() then Setup() on each PK
  │                       (declare State fields, register evaluators, build operators)
  │
  ├─ Initialize()     ─── Initialize() on each PK
  │                       (read ICs, init time stepper, initial evaluator updates)
  │
  └─ [ time loop ]
       ├─ get_dt()    ─── proposed dt from each PK; coordinator takes min
       ├─ set_dt(dt)  ─── broadcast chosen dt to each PK
       ├─ AdvanceStep(t0, t1, reinit)
       │    ├── success → CommitStep(t0, t1, tag_next)
       │    └── fail    → FailStep(t0, t1, tag_next), cut dt, retry
       └─ CalculateDiagnostics(tag)  (output hook, after successful step)
```

## Inheritance rules summary

| Scenario | Base to use |
|---|---|
| Implicit PDE with conserved quantity (flow, energy) | `PK_PhysicalBDF_Default` |
| Explicit PDE (transport, some SEB) | `PK_Physical_Default_Explicit_Default` |
| Globally-implicit MPC | `StrongMPC<PK_t>` (which also inherits `PK_BDF_Default`) |
| Sequential or weakly coupled MPC | `WeakMPC` or `MPCSubcycled` |
