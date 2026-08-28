---
**Source pin:** ATS commit `42b0e940` (`ats-1.7-dev-22-g42b0e940`)
**Last verified:** 2026-07-27
---

# ATS Standalone Driver

Sources: `src/executables/main.cc`, `src/executables/ats_driver.{cc,hh}`

## Purpose

The standalone ATS executable (`ats input.xml`) is the primary user-facing
entry point. It parses command-line arguments and an XML (or YAML) input deck,
constructs an `ATSDriver`, and calls `run()` which executes the full
setup-initialize-timeloop-finalize lifecycle.

## Class hierarchy

```
Coordinator  (coordinator.{cc,hh})   <-- base class
    |
ATSDriver    (ats_driver.{cc,hh})    <-- standalone driver, adds cycle_driver()
```

`ATSDriver` inherits all constructor logic from `Coordinator` (mesh creation,
PK instantiation, checkpoint/vis setup) and adds only two methods of its own:
`cycle_driver()` and `run()`.

## `main.cc` — entry point

`main.cc` is responsible for:

1. Initializing MPI (`Teuchos::GlobalMPISession`) and Kokkos
   (`Kokkos::initialize()`) (line 51).
2. Parsing command-line options via `Teuchos::CommandLineProcessor`. Supported
   flags include `--xml_file`, `--input_file`, `--version`, `--print_version`,
   `--verbosity`, `--write_on_rank`, `--list_evaluators`, `--list_pks`.
3. Parsing the input file — XML via `Teuchos::getParametersFromXmlFile` or
   YAML via `Teuchos::YAMLParameterList::parseYamlFile` (lines 221-226).
4. Constructing `ATSDriver` on the stack (line 251) and calling `driver.run()`.
5. Finalizing Kokkos (line 268) and returning.

The communicator is created from `Amanzi::getDefaultComm()` (line 216), which
wraps `MPI_COMM_WORLD`.

## `ATSDriver::cycle_driver()` — the time loop

`(src/executables/ats_driver.cc:56)`

Runs the complete simulation in four phases:

### Phase 1 — setup

Calls `Coordinator::setup()`. This registers fields and allocates memory for
all PKs and evaluators.

### Phase 2 — initialize

Calls `Coordinator::initialize()`. This sets the start time on the `State`
object, calls `pk_->Initialize()`, writes initial visualization, observations,
and checkpoint.

### Phase 3 — timestepping

The while-loop `(src/executables/ats_driver.cc:129)` continues until one of
these conditions is met: simulation time >= `t1_`, cycle count >= `cycle1_`,
wallclock duration exceeded, or `dt <= 0`.

Each iteration:
- Assigns the new timestep `dt` to State.
- Calls `Coordinator::advance()` which calls `pk_->AdvanceStep()`.
- On success: commits the step, calls `visualize()`, `observe()`, `checkpoint()`.
- On failure: resets `t_new` to `t_current`; obtains a smaller `dt` from
  `get_dt(true)`.

A `TimestepCrash` exception (when `DEBUG_MODE` is false) triggers a forced
visualization and post-mortem checkpoint before re-throwing.

### Phase 4 — finalize

Calls `Coordinator::finalize()`: writes final checkpoint, flushes
observations, and reports memory usage and Teuchos timer summaries.

## Input deck structure

The XML input file is parsed into a single Teuchos `ParameterList` whose
top-level sublists map to major components. The spec is documented in
`ats_driver.hh` (lines 18-99):

| Sublist | Content |
|---|---|
| `"cycle driver"` | `start time`, `end time`, `end cycle`, `PK tree`, `required times`, `restart from checkpoint file` |
| `"mesh"` | One or more mesh specs (see `ats_mesh_factory.md`) |
| `"regions"` | Region specs for boundary conditions and mesh extraction |
| `"visualization"` | One sublist per domain to visualize |
| `"observations"` | Time-series observation specs |
| `"checkpoint"` | Checkpoint frequency and filename base |
| `"PKs"` | One sublist per PK, keyed by the PK name in the `"PK tree"` |
| `"state"` | Initial conditions, evaluator specs |

The `"PK tree"` contains exactly one root node, whose `"PK type"` key selects
a registered PK from the Amanzi `PKFactory`. For coupled surface-subsurface
simulations this is typically an MPC type.

## Build target

`main.cc` links against the `ats_executable` library (which contains
`coordinator.cc`, `ats_mesh_factory.cc`, `ats_driver.cc`) plus all ATS and
Amanzi PK/evaluator libraries. The executable is named `ats` and is placed in
`${ATS_BINARY_DIR}`. `(src/executables/CMakeLists.txt:181-185)`

## Verbosity control

Global verbosity can be set at the command line (`--verbosity none|low|medium|
high|extreme`) or via a `"verbose object"` sublist in the input deck. In ELM
coupling mode the constructor forces `VERB_NONE` to suppress output
`(src/executables/elm_ats_api/elm_ats_driver.cc:70)`.
