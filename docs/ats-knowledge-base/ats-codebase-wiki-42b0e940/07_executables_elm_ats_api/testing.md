---
**Source pin:** ATS commit `42b0e940` (`ats-1.7-dev-22-g42b0e940`)
**Last verified:** 2026-07-27
---

# Testing

Sources:
- `src/executables/test/Main.cc`
- `src/executables/test/executable_mesh_factory.cc`
- `src/executables/test/executable_mesh.cc`
- `src/executables/test/executable_coupled_water.cc`
- `src/executables/elm_ats_api/test/elm_ats_test.cc`
- `src/executables/elm_ats_api/test/fortran/test.f90`
- `src/executables/elm_ats_api/test/fortran/ats_mod.f90`
- `src/executables/elm_ats_api/test/fortran/ats.f90`
- XML input files in `test/` and test data: `hillslope.exo`,
  `double_open_book.exo`, `subdomain_coloring.h5`, `coloring.bin`

---

## Executables-level unit tests (`src/executables/test/`)

These tests are built via `add_amanzi_test` when `BUILD_TESTS` is enabled
`(src/executables/CMakeLists.txt:150-177)`. They use the UnitTest++ framework.

### `executable_mesh_factory` tests `(test/executable_mesh_factory.cc)`

Built as `executable_mesh_factory` and run at 1, 2, and 4 MPI ranks. Tests
the `ATS::Mesh::createMeshes` / `ATS::Mesh::createMesh` pipeline using XML
input files.

The test suite is `ATS_MESH_FACTORY` with a `Runner` fixture
`(test/executable_mesh.cc:22-40)` that loads an XML file via
`Teuchos::getParametersFromXmlFile`, creates a `GeometricModel`, a `State`,
and calls `ATS::createMeshes`.

Test cases and their XML input files:

| Test name | XML file | What it tests |
|---|---|---|
| `EXTRACT_SURFACE` | `executable_mesh_extract_surface.xml` | Lifting a 2D surface from a 3D domain |
| `EXTRACT_SUBDOMAINS` | `executable_mesh_extract_subdomains.xml` | Extracted sub-meshes from a volume mesh |
| `EXTRACT_SUBDOMAINS_SURFACE` | `executable_mesh_extract_subdomains_surface.xml` | Surface mesh over extracted subdomains |
| `SUBDOMAINS` | `executable_mesh_subdomains.xml` | Domain set mesh construction |
| `CONSTRUCT_COLUMNS` | `executable_mesh_construct_columns.xml` | Column building on a structured mesh |

The mesh test fixture `Runner::go()` calls `ATS::createMeshes(plist->sublist("mesh"), comm, gm, *S)` `(test/executable_mesh.cc:34)`.

Mesh input files reference the Exodus files `hillslope.exo` and
`double_open_book.exo` that are copied to the build directory.

### `executable_coupled_water` tests `(test/executable_coupled_water.cc)`

Tests the coupled `MPCCoupledWater` PK (coupled overland + Richards flow)
through setup, initialization, and several timestep manipulations. Uses the
`CoupledWaterProblem` fixture which directly instantiates the MPC and its
two sub-PKs (`Flow::Richards`, `Flow::OverlandPressureFlow`). Tests exercise:
- PK setup and initialization
- Residual evaluation
- Preconditioner application
- Jacobian finite-difference checks

Three XML input files (`executable_coupled_water1.xml`,
`executable_coupled_water2.xml`, `executable_coupled_water3.xml`) correspond
to different mesh and solver configurations.

---

## ELM-ATS API C++ test (`elm_ats_api/test/elm_ats_test.cc`)

A standalone C++ driver that tests the API end-to-end using the C++ class
directly (not the C wrapper). The test directory is currently commented out
of the CMake build (`##add_subdirectory(test)` in
`elm_ats_api/CMakeLists.txt:47`).

The test program `(elm_ats_test.cc:31-131)`:

1. Parses command-line arguments (same interface as the standalone `ats`
   executable, including `--xml_file` and verbosity options).
2. Allocates dummy arrays for 1 column × 100 cells (not used — lines are
   commented out).
3. Creates the driver directly: `ATS::createELM_ATSDriver(&comm, input_filename.data())`
   `(elm_ats_test.cc:109)`.
4. Calls `driver->setup()`, `driver->initialize()`, `driver->advance_test()`,
   `driver->finalize()` in order.

Commented-out lines show the intended full workflow: `get_mesh_info`,
`set_potential_sources`, `get_waterstate`. The test also has a commented-out
block that exercises the C API wrapper functions (`ats_create_c`,
`ats_setup_c`, etc.) with the `_c` suffix that no longer matches the current
API naming.

To re-enable this test: uncomment `add_subdirectory(test)` in
`elm_ats_api/CMakeLists.txt` and provide an appropriate XML input file.

---

## ELM-ATS Fortran test (`elm_ats_api/test/fortran/`)

Three Fortran files implement a test driver for the Fortran binding:

### `ats.f90` — interface declarations

Declares C-interoperable Fortran function interfaces bound to the C API
symbols by name (see `elm_ats_api.md` for the detailed listing and
divergence notes).

### `ats_mod.f90` — `libats` module

Wraps the C interface in a Fortran derived type `ats` with object-oriented
method bindings and a constructor interface. Handles Fortran-to-C string
conversion (null termination) for the input filename.

### `test.f90` — Fortran test program

`(elm_ats_api/test/fortran/test.f90:1-65)`

A minimal program that exercises the Fortran binding:

```fortran
program elm_test
  use libats
  type(ats) :: ats_driver

  ! 1 column, 100 cells dummy arrays
  call MPI_INIT(ierror)
  ats_driver = ats(MPI_COMM_WORLD, infile_name)   ! constructor
  call ats_driver%setup()
  call ats_driver%initialize()
  call ats_driver%advance_test()
  ! destructor called automatically via final :: ats_delete
  call MPI_FINALIZE(ierror)
```

Lines calling `get_mesh_info` and `set_sources` are commented out,
consistent with the C++ test. The test verifies that Fortran can link against
the `elm_ats` shared library and call through the C API without crashing.

The Fortran test subdirectory also has its own `CMakeLists.txt` that was
presumably enabled at some point during development but is not currently
active due to the parent `add_subdirectory(test)` being commented out.

---

## Test data files

Located in `src/executables/test/`:

| File | Used by |
|---|---|
| `hillslope.exo` | Mesh factory tests |
| `double_open_book.exo` | Mesh factory tests |
| `subdomain_coloring.h5` | Subdomain mesh tests |
| `coloring.bin` | Domain set coloring tests |
| `executable_mesh_extract_surface.xml` | EXTRACT_SURFACE test |
| `executable_mesh_extract_subdomains.xml` | EXTRACT_SUBDOMAINS test |
| `executable_mesh_extract_subdomains_surface.xml` | EXTRACT_SUBDOMAINS_SURFACE test |
| `executable_mesh_subdomains.xml` | SUBDOMAINS test |
| `executable_mesh_construct_columns.xml` | CONSTRUCT_COLUMNS test |
| `executable_coupled_water1-3.xml` | Coupled water PK tests |

The CMakeLists copies these files to the build directory for out-of-source
builds `(src/executables/CMakeLists.txt:156-163)`.

---

## Re-enabling the ELM API tests

To restore the ELM API test suite:

1. Uncomment `add_subdirectory(test)` in
   `src/executables/elm_ats_api/CMakeLists.txt:47`.
2. Update the Fortran interface in `test/fortran/ats.f90` to match the current
   C header (add `t`, `patm`, `soilp` to `ats_initialize_c`; remove extra size
   arguments from `ats_set_sources_c` and `ats_get_waterstate_c`; add
   `checkpoint` and `visualize` to `ats_advance_c`).
3. Provide an ATS XML input file that produces a columnar mesh suitable for the
   1-column, 100-layer dummy data in the test programs.
4. Enable `ENABLE_ELM_ATS_API` in the CMake configuration.
