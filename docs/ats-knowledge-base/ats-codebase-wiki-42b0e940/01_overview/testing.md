---
**Source pin:** ATS commit `42b0e940` (`ats-1.7-dev-22-g42b0e940`)
**Last verified:** 2026-07-27
---

# Testing: ATS Regression Tests

## Key Finding: ats-regression-tests Is a Separate Submodule

The `testing/ats-regression-tests/` directory is an **unpopulated git
submodule** at this commit. A directory listing confirms it contains only `.`
and `..`. The submodule metadata from `.gitmodules` is:

```
[submodule "testing/ats-regression-tests"]
    path = testing/ats-regression-tests
    url = https://github.com/amanzi/ats-regression-tests.git
    branch = master
```

The pinned submodule SHA is `28ca01bb9c7849284c139d7336c1811bc766e6d3`. The
test suite must be populated separately:

```bash
git submodule update --init testing/ats-regression-tests
```

All knowledge in this file about the regression test structure comes from
`testing/CMakeLists.txt` and the tools in `tools/testing/`, not from
inspecting actual test input decks (which are absent in this checkout).

---

## Testing Infrastructure Overview

### CMake / CTest integration

`testing/CMakeLists.txt` integrates the regression test suite into the ATS
CTest build. When `ENABLE_Regression_Tests` is ON and the
`ats-regression-tests/README.md` exists, the CMakeLists:

1. Copies the regression test directory to the binary tree for out-of-source builds (testing/CMakeLists.txt:11-15).
2. Calls `regression_tests.py --list-tests` to discover available tests (testing/CMakeLists.txt:21-27).
3. Registers each discovered test with `add_test()`, naming it `ats_regression_test-<dir>-<name>` (testing/CMakeLists.txt:41-51).

When `ENABLE_ALQUIMIA` is ON, the suite tagged `testing` is used; otherwise
the suite `testing_no_geochemistry` is used (testing/CMakeLists.txt:20-27).

The test command template is (testing/CMakeLists.txt:42-43):
```
python regression_tests.py -e ${ATS_BINARY_DIR}/src/executables/ats
    --mpiexec=<MPI_EXEC> --mpiexec-global-args=<...> --mpiexec-numprocs-flag=<...>
    <test_dir> -t <test_name>
```

### Python test manager (tools/testing/)

Three Python utilities support the test suite:

| Script | Purpose |
|---|---|
| `tools/testing/test_manager.py` | Core test runner; parses test configs, runs ATS, compares output against stored baselines using configurable tolerances. Modeled after Ben Andre's PFloTran regression test suite (per file header). |
| `tools/testing/generate_new_test.py` | Creates a new regression test entry from a completed run; parses the ATS log file to capture timestep history and generates a fixed-timestep input file to eliminate adaptive-timestep variability in comparisons. |
| `tools/testing/run_demos.py` | Runs demo input files (not regression tests). |
| `tools/testing/ats_h5.py` | HDF5 output reader helper used by the test manager to load and compare field data from ATS visualization files. |

The design note in `generate_new_test.py` explains a key subtlety: adaptive
timestepping means that small floating-point differences can shift the number
of nonlinear iterations in a step, causing the adaptive controller to choose a
different timestep, which then compounds into larger solution differences. New
tests are therefore generated with a **fixed timestep history** derived from
the initial run.

---

## How To Run a Regression Test (once submodule is populated)

```bash
# 1. Populate the submodule
cd /path/to/ats
git submodule update --init testing/ats-regression-tests

# 2. In your Amanzi+ATS build directory, enable regression tests
cmake <amanzi_src> -DENABLE_Regression_Tests=ON ...

# 3. Run all ATS regression tests
ctest -R ats_regression_test

# 4. Run a specific test
ctest -R ats_regression_test-<dir>-<name> -V
```

Individual tests can also be invoked directly:
```bash
cd testing/ats-regression-tests
python regression_tests.py -e /path/to/ats_binary <test_dir> -t <test_name>
```

---

## Known Test Suite Structure (from submodule metadata and CMake logic)

The regression test runner (`regression_tests.py`) organizes tests into
**suites** (e.g., `testing`, `testing_no_geochemistry`). Each suite is a
directory containing:
- An XML or YAML ATS input deck
- A stored baseline output (HDF5 or text observation files)
- A test configuration file specifying which variables to compare and with
  what tolerance

This structure is inferred from `test_manager.py` (which reads config files)
and `generate_new_test.py` (which creates them). The actual directory layout
is not verifiable in this checkout.

---

## Sample Input Deck Anatomy

A sample ATS XML input deck is available in the tools directory at
`tools/meshing/meshing_ats/four-polygon-test/test1-fv-four-polygon.xml`.
While this is a meshing example rather than a regression test, it illustrates
the top-level XML structure of all ATS input decks:

```xml
<ParameterList name="Main">
  <!-- 1. Native unstructured mode flag -->
  <Parameter name="Native Unstructured Input" type="bool" value="true"/>

  <!-- 2. Mesh specification -->
  <ParameterList name="Mesh" type="ParameterList">
    <Parameter name="Framework" type="string" value="MSTK" />
    <ParameterList name="Read Mesh File" ...>
      <Parameter name="File" type="string" value="../four_polygon.exo" />
      <Parameter name="Format" type="string" value="Exodus II" />
    </ParameterList>
    <ParameterList name="Surface Mesh" ...>
      <!-- Extracts surface mesh from subsurface mesh -->
    </ParameterList>
  </ParameterList>

  <!-- 3. Domain spatial dimension -->
  <ParameterList name="Domain">
    <Parameter name="Spatial Dimension" type="int" value="3"/>
  </ParameterList>

  <!-- 4. Regions (named geometric regions for boundary conditions, ICs) -->
  <ParameterList name="Regions"> ... </ParameterList>

  <!-- 5. Coordinator (time loop, visualization, checkpoint, observation) -->
  <ParameterList name="coordinator"> ... </ParameterList>

  <!-- 6. State (initial conditions, evaluators, field specs) -->
  <!-- 7. PK tree (physics process kernels; nested structure) -->
</ParameterList>
```

Key structural notes:
- The `"Mesh"` block specifies the subsurface mesh (Exodus II `.exo` format)
  and optionally declares a surface mesh extracted from a labeled sideset.
- `"Regions"` define named geometric regions (boxes, planes, labeled sets from
  the mesh file) used throughout for BCs and ICs.
- `"coordinator"` controls the time loop, output, and checkpointing.
- The `"state"` block holds initial conditions and evaluator (constitutive
  relation) specifications.
- The `"PK tree"` block defines the nested PK hierarchy: which MPC couples
  which sub-PKs, and their per-PK parameter lists.

This nested XML structure is the concretization of the MPC/PK multiphysics
framework described in Coon et al. 2016 (see citation_map.md).

---

## Input Version Migration

ATS input format has evolved through multiple spec versions. The
`tools/input_converters/` directory contains Python migration scripts for each
major transition:

```
xml-0.83-0.86.py
xml-0.86-0.87.py
xml-0.87-0.88.py
xml-0.88-1.0.py
xml-1.0-1.1.py   (+ xml-1.0-1.1.xml helper)
xml-1.1-1.2.py
xml-1.2-1.3.py
xml-1.3-1.4.py
xml-1.4-1.5.py
xml-1.5-1.6.py
xml-linear_op-nka_to_gmres.py
```

The most recent converter (`xml-1.5-1.6.py`) migrates from spec version 1.5 to
the current master-branch spec. It imports `amanzi_xml` utilities from
`$AMANZI_SRC_DIR/tools/amanzi_xml` (tools/input_converters/xml-1.5-1.6.py:6-9).
