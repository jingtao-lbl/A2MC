---
**Source pin:** ATS commit `42b0e940` (`ats-1.7-dev-22-g42b0e940`)
**Last verified:** 2026-07-27
---

# Building ATS

## Critical First Point: ATS Is Not Standalone

ATS cannot be built independently. The CMakeLists.txt states this explicitly:

```cmake
# NOTE: ATS is not standalone code, and this is not a stand-alone
#       CMakeLists.txt.  Instead, it must be built as a subrepo of
#       Amanzi.  See ATS/INSTALL.md
```
(CMakeLists.txt:3-6)

The INSTALL.md (all 4 lines) redirects to the Amanzi-hosted instructions:

> ATS is now built as a part of Amanzi directly. Please see the ATS
> installation instructions located at:
> https://github.com/amanzi/amanzi/blob/master/INSTALL_ATS.md

(INSTALL.md:1-4)

Do **not** attempt `cmake .` from inside the ATS source directory. The build
will fail because `AMANZI_SOURCE_DIR`, Amanzi TPL paths, and Amanzi CMake
macros are all required prerequisites.

---

## Build Procedure (summary from ATS-side files)

### 1. Obtain Amanzi with ATS as a submodule

ATS lives at `src/physics/ats/` inside the Amanzi tree (inferred from
CMakeLists.txt:20):

```cmake
set(ATS_MODULE_PATH "${AMANZI_SOURCE_DIR}/src/physics/ats/tools/cmake")
```

The two git submodules declared in ATS's own `.gitmodules` are:

```
[submodule "docs/documentation/source/ats_demos"]
    url = https://github.com/amanzi/ats-demos.git
[submodule "testing/ats-regression-tests"]
    url = https://github.com/amanzi/ats-regression-tests.git
```

Neither is populated in this local checkout (both directories contain only `.`
and `..`). They are optional for building but required for regression tests and
demo notebooks.

### 2. Build via the Amanzi bootstrap system

See https://github.com/amanzi/amanzi/blob/master/INSTALL_ATS.md for the full
procedure. From the ATS source, the only guidance is the redirect in INSTALL.md.

### 3. Key CMake variables (ATS-side)

The following CMake variables are referenced or set in ATS CMake files:

| Variable | Set by | Purpose |
|---|---|---|
| `AMANZI_SOURCE_DIR` | Amanzi parent build | Root of the Amanzi source tree; used to locate ATS tools/cmake |
| `ATS_SOURCE_DIR` | Amanzi parent build | Root of ATS source (i.e., `${AMANZI_SOURCE_DIR}/src/physics/ats`) |
| `ATS_BINARY_DIR` | Amanzi parent build | Out-of-source build directory for ATS |
| `ENABLE_Regression_Tests` | User CMake option | Enables building/running ATS regression tests via CTest |
| `ENABLE_ALQUIMIA` | User CMake option | Enables reactive transport through the Alquimia geochemical interface; controls which test suites are registered (testing/CMakeLists.txt:20-27) |
| `PYTHON_EXECUTABLE` | Amanzi/CMake | Python interpreter used to enumerate and run regression tests |
| `MPI_EXEC`, `MPI_EXEC_GLOBAL_ARGS`, `MPI_EXEC_NUMPROCS_FLAG` | Amanzi/CMake | MPI launch configuration for CTest regression runs |
| `TESTS_REQUIRE_MPIEXEC` | User CMake option | Forces `mpiexec` even for serial tests (testing/CMakeLists.txt:43-45) |
| `ATS_VERSION` | tools/cmake/ATSVersion.cmake | Version string derived from git tags/hash; baked into `ats_version.hh` (generated from `tools/cmake/ats_version.hh.in`) at build time |

#### Version string construction

`tools/cmake/ATSVersion.cmake` queries `git tag -l ats-*` and `git rev-parse
--short HEAD` to assemble a version string of the form:

```
<major>.<minor>.<patch-or-dev>_<hash>
```

For release branches, it matches tags `ats-X.Y.Z`. For the master/dev branch,
it matches `ats-*-dev` tags. If git is unavailable or the `.git` directory is
absent, it falls back to static values (major=1, minor=0, patch=0)
(tools/cmake/ATSVersion.cmake:138-163).

The CMake template `tools/cmake/ats_version.hh.in` is configured by CMake into `ats_version.hh` in the build directory at build time. It exposes:
```cpp
#define ATS_VERSION     @ATS_VERSION@
#define ATS_GIT_BRANCH  @ATS_GIT_BRANCH@
#define ATS_GIT_GLOBAL_HASH @ATS_GIT_GLOBAL_HASH@
```
(tools/cmake/ats_version.hh.in:10-13)

At runtime, `ats --version` and `ats --print_version` print these values
(src/executables/main.cc:108-128).

#### Registration of CMake modules

CMakeLists.txt appends the ATS tools/cmake directory to `CMAKE_MODULE_PATH`
(CMakeLists.txt:20-21) and then calls `include(ATSVersion)` to trigger version
header generation (CMakeLists.txt:24).

---

## fix-rpath.sh

A single-line shell helper for macOS:

```bash
for i in system filesystem program_options regex; do
  install_name_tool -change @rpath/libboost_${i}.dylib \
    ${AMANZI_TPLS_DIR}/lib/libboost_${i}.dylib \
    ${ATS_DIR}/bin/ats
done
```
(fix-rpath.sh:1)

This patches the Boost shared-library rpaths baked into the `ats` binary on
macOS when the dynamic linker cannot find the Boost libraries at the default
`@rpath`. It requires two environment variables to be set before running:

- `AMANZI_TPLS_DIR` -- path to the Amanzi third-party libraries installation
- `ATS_DIR` -- path to the ATS installation prefix (containing `bin/ats`)

This file is relevant only on macOS builds; Linux builds typically use
`-Wl,-rpath` flags set by the Amanzi build system and do not need this step.

---

## Source Tree Entry Points

After a successful Amanzi+ATS build, the primary build products from ATS are:

- `${ATS_BINARY_DIR}/src/executables/ats` -- the main simulation executable (from src/executables/main.cc + ats_driver.cc/hh + coordinator.cc/hh)
- Physics libraries compiled from `src/pks/`, `src/constitutive_relations/`, `src/operators/` (registered via `src/executables/ats_registration_files.hh`)
- The ELM-ATS coupling library from `src/executables/elm_ats_api/` (see topic 07)

The top-level CMakeLists.txt adds only two subdirectories:
```cmake
add_subdirectory(src)
add_subdirectory(testing)
```
(CMakeLists.txt:16-17)

All physics targets are therefore built through `src/CMakeLists.txt` (not
read for this topic but referenced for completeness).
