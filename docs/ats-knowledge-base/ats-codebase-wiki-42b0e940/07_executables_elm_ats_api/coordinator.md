---
**Source pin:** ATS commit `42b0e940` (`ats-1.7-dev-22-g42b0e940`)
**Last verified:** 2026-07-27
---

# Coordinator

Sources: `src/executables/coordinator.{cc,hh}`

## Purpose

`Coordinator` is the base class for all ATS top-level drivers. It owns the
`State`, the top-level PK, the solution `TreeVector`, and all visualization,
checkpoint, and observation objects. Both the standalone `ATSDriver` and the
ELM coupling `ELM_ATSDriver` inherit from it.

## Constructor

`(src/executables/coordinator.cc:63)`

Takes four arguments:

| Argument | Type | Role |
|---|---|---|
| `plist` | `Teuchos::RCP<ParameterList>` | Entire input deck |
| `wallclock_timer` | `Teuchos::RCP<Teuchos::Time>` | Wallclock monitor |
| `teuchos_comm` | `Teuchos::RCP<const Teuchos::Comm<int>>` | Teuchos communicator (for Teuchos timers) |
| `comm` | `Amanzi::Comm_ptr_type` | Epetra/MPI communicator |

The constructor runs two timed stages before returning:

### Stage 0 — create mesh `(coordinator.cc:104-116)`

- Creates an `Amanzi::State` from the `"state"` sublist.
- Creates a `GeometricModel` from the `"regions"` sublist.
- Calls `ATS::Mesh::createMeshes(plist, comm, gm, *S_)` which dispatches to
  `ats_mesh_factory`.

### Stage 1 — create run `(coordinator.cc:123-271)`

- Calls `initializeFromPlist_()` to read `t0_`, `t1_`, `max_dt_`, `min_dt_`,
  `cycle0_`, `cycle1_`, `duration_`, `subcycled_ts_`, and restart settings
  from the `"cycle driver"` sublist.
- Creates the top-level PK using `Amanzi::PKFactory` and the name found in
  `"cycle driver" -> "PK tree"`. The PK is stored in `pk_`.
- Creates an `Amanzi::Checkpoint` from the `"checkpoint"` sublist.
- Registers deformable mesh vertex coordinate fields in `State`.
- Runs `InputAnalysis::RegionAnalysis()` if `"analysis"` is present.
- Loops over `"visualization"` sublists and creates `Amanzi::Visualization`
  objects, handling both standard domains and domain-set collectives.
- Creates `UnstructuredObservations` objects from the `"observations"` sublist.
- Creates a `TimeStepManager` and registers checkpoint, observation, and
  visualization events with it.

## Protected data members

| Member | Type | Meaning |
|---|---|---|
| `pk_` | `Teuchos::RCP<Amanzi::PK>` | Top-level PK (usually an MPC) |
| `S_` | `Teuchos::RCP<Amanzi::State>` | The entire model state |
| `soln_` | `Teuchos::RCP<Amanzi::TreeVector>` | Solution vector passed to PK |
| `tsm_` | `Teuchos::RCP<TimeStepManager>` | Timestep-event manager |
| `t0_`, `t1_` | `double` | Simulation start and end times (seconds) |
| `max_dt_`, `min_dt_` | `double` | Timestep bounds |
| `cycle0_`, `cycle1_` | `int` | Cycle bounds |
| `duration_` | `double` | Wallclock limit (hours, -1 = unlimited) |
| `visualization_` | vector of `Visualization` | Per-domain vis writers |
| `failed_visualization_` | vector of `Visualization` | Written on step failure |
| `checkpoint_` | `Teuchos::RCP<Checkpoint>` | Checkpoint writer |
| `observations_` | vector of `UnstructuredObservations` | Time-series outputs |
| `comm_` | `Amanzi::Comm_ptr_type` | Parallel communicator |
| `vo_` | `Teuchos::RCP<VerboseObject>` | Logging |

## Public methods

### `setup()` `(coordinator.cc:276)`

Calls `pk_->set_tags()`, `pk_->parseParameterList()`, `pk_->Setup()`,
`obs->Setup()`, and finally `S_->Setup()`. This must be called before
`initialize()`. In ELM coupling mode `ELM_ATSDriver::setup()` calls
`Coordinator::setup()` at the end after registering the ELM-specific fields.

### `initialize()` `(coordinator.cc:299)`

Sets simulation time on the `State`, calls `pk_->Initialize()`, handles
optional restart from checkpoint, then calls `S_->InitializeEvaluators()`,
`S_->InitializeFieldCopies()`, `S_->CheckAllFieldsInitialized()`.

### `advance()` `(coordinator.cc:554)` → returns `bool` (fail flag)

Calls `pk_->AdvanceStep(t_old, t_new, false)`. On success calls
`pk_->CommitStep()`. On failure calls `pk_->FailStep()` and, for deformable
meshes, recovers old node positions.

### `get_dt(bool after_fail)` `(coordinator.cc:526)`

Asks the PK for its preferred timestep, caps it at `max_dt_`, then passes
it to `tsm_->TimeStep()` so that visualization, checkpoint, and
`"required times"` events can force smaller steps.

### `visualize(bool force=false)` `(coordinator.cc:612)`

Checks whether any vis writer requests a dump at the current cycle/time;
if so (or if `force`), calls `pk_->CalculateDiagnostics()` and then
`WriteVis()` for each writer.

### `checkpoint(bool force=false)` `(coordinator.cc:648)`

Calls `checkpoint_->Write(*S_)` if a dump is requested or forced.

### `observe()` `(coordinator.cc:639)`

Calls `obs->MakeObservations(S_.ptr())` for all observation objects.

### `finalize()` `(coordinator.cc:374)`

Calls `pk_->CalculateDiagnostics()`, writes a final checkpoint, flushes
observations, and calls `report_memory()`.

### `report_memory()` `(coordinator.cc:411)`

Collects per-rank RSS usage via `getrusage` and logs min/mean/max across
ranks.

## Time management

`State` stores two time tags: `Tags::CURRENT` (committed state) and
`Tags::NEXT` (proposed state). The coordinator sets `NEXT = CURRENT + dt`
before calling `pk_->AdvanceStep`, then either commits (`CURRENT = NEXT`) or
reverts (`NEXT = CURRENT`) depending on success or failure.

## Relationship to ELM_ATSDriver

`ELM_ATSDriver` overrides `setup()` to register ELM-specific fields before
delegating to `Coordinator::setup()`. It overrides `initialize()` to accept
initial water content from ELM and convert it to ATS pressure fields. It
does not override `advance()` — instead it wraps `Coordinator::advance()` in
a subcycle loop inside its own `advance(dt, checkpoint, vis)` method.
