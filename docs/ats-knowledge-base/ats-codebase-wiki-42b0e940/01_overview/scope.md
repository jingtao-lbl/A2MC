---
**Source pin:** ATS commit `42b0e940` (`ats-1.7-dev-22-g42b0e940`)
**Last verified:** 2026-07-27
---

# Scope: What ATS Is and Is Not

## What ATS Is

The Advanced Terrestrial Simulator (ATS) is a multi-physics code for solving
watershed-to-river-basin-scale integrated ecohydrology problems, including
applications to the built environment.

From the README (README.md:1-8):

> ATS is a suite of physics processes built for Amanzi. Amanzi includes the
> underlying mesh, data structure, multi-physics APIs, and math libraries for
> defining and solving the physics implemented in ATS.

The canonical self-description in the Sphinx documentation
(docs/documentation/source/index.rst:1-10) is identical.

### Science targets and capabilities

| Capability | Notes |
|---|---|
| **Variably-saturated subsurface flow** | Richards equation solved on unstructured prismatic meshes using mimetic finite differences |
| **Surface (overland) flow** | Diffusion-wave / Manning equation; coupled to subsurface through continuity of pressure and flux (Coon et al. 2020, see citation_map.md) |
| **Thermal hydrology with freeze/thaw** | Ice formation in soils, permafrost active-layer dynamics; coupled surface-subsurface energy and flow (Painter et al. 2016, see citation_map.md) |
| **Evapo-transpiration (ET)** | Multiple canopy-level ET parameterizations |
| **Surface energy exchange** | Snow, albedo, surface energy balance (SEB) |
| **Snow** | Snow accumulation, melt, compaction |
| **Reactive transport** | Surface and subsurface transport of solutes; coupling to external geochemical engines through the Alquimia interface (Molins et al. 2022, see citation_map.md) |
| **Deformation** | Mesh deformation for subsidence and thaw settlement |
| **Gray and green infrastructure** | Pipes, green roofs, and similar built-environment features |
| **Multi-physics coupling** | Hierarchical PK (process kernel) pattern and MPC (Multi-Process Coupler) framework (Coon et al. 2016, see citation_map.md) |

Capabilities are stated in README.md:1-8 and repeated verbatim in
docs/documentation/source/index.rst:1-10.

### Numerical approach

- **Discretization:** Mimetic Finite Difference (MFD) on unstructured prismatic meshes (subsurface) and 2D surface meshes.
- **Time integration:** BDF (Backward Difference Formula) / implicit for coupled flow+energy (via `pk_bdf_default`); explicit option available (via `pk_explicit_default`).
- **Nonlinear solve:** Block-preconditioned Newton for strongly coupled systems managed by `strong_mpc`; sequential (operator-split) coupling via `weak_mpc`.
- **Scale:** Watershed to river basin; column-scale to 3D unstructured grids.

### Input format

ATS uses XML-based input decks conforming to the Amanzi input specification.
YAML input is also accepted as of this development line; the driver's main.cc
dispatches on file extension (src/executables/main.cc:221-225). Historically,
input decks have gone through converter scripts for each spec version jump
(tools/input_converters/xml-0.83-0.86.py through xml-1.5-1.6.py).

### Community and documentation

- **Online documentation (input spec):** https://amanzi.github.io/ats/ (README.md:24)
- **Demo notebooks:** https://github.com/amanzi/ats-demos (not populated in this checkout; see .gitmodules)
- **User forum:** Google Group `ats-users` (README.md:12)
- **Short course:** https://github.com/amanzi/ats-short-course (README.md:26)
- **Watershed Workflow tool:** https://environmental-modeling-workflows.github.io/watershed-workflow/ (README.md:28-29) -- downloads/adapts open geospatial data for ATS mesh setup

---

## The Amanzi Dependency

ATS provides **physics only**. It depends entirely on Amanzi for:

- Unstructured mesh data structures (MSTK/MOAB backends)
- State management and field data structures
- Multi-physics API (PK base classes and factory, Evaluator framework)
- Math libraries (linear algebra, preconditioners, nonlinear solvers)
- MPI communication layer (Epetra/Kokkos abstractions)
- Build system integration

This dependency is stated explicitly in:
- README.md:8: "ATS is a suite of physics processes built for Amanzi."
- INSTALL.md:3-4: "ATS is now built as a part of Amanzi directly. Please see the ATS installation instructions located at: https://github.com/amanzi/amanzi/blob/master/INSTALL_ATS.md"
- CMakeLists.txt:4-6: "NOTE: ATS is not standalone code, and this is not a stand-alone CMakeLists.txt. Instead, it must be built as a subrepo of Amanzi. See ATS/INSTALL.md"

ATS is structured as a **git submodule** inside the Amanzi repository. The
ATS CMakeLists.txt itself is invoked as a subdirectory of the parent Amanzi
build; it begins with `project(ATS)` and calls `add_subdirectory(src)` and
`add_subdirectory(testing)` (CMakeLists.txt:11-17).

The ATS module path is set as:
```
set(ATS_MODULE_PATH "${AMANZI_SOURCE_DIR}/src/physics/ats/tools/cmake")
```
(CMakeLists.txt:20), confirming that Amanzi expects to find ATS at
`src/physics/ats/` within its own source tree.

**What this wiki covers:** ATS source only (everything under the ATS repository
root, pinned at the commit in this wiki's directory name). Amanzi internals -- mesh
libraries, linear solvers, evaluator base classes, Teuchos/Trilinos infrastructure
-- are out of scope.

---

## License and Copyright

- **License:** Three-clause BSD License (LICENSE).
- **Copyright holders:** Multiple national laboratories contributed code. Named institutions include Los Alamos National Laboratory (2011-2014) and Oak Ridge National Laboratory; the COPYRIGHT file states "Copyright 2010-202x held jointly by participating institutions" (as seen in every source file header). The top-level COPYRIGHT file gives the full multi-lab copyright text.

---

## What This Wiki Does NOT Cover

- Amanzi internals (mesh, linear algebra, evaluator base, MPI layer)
- The ats-demos submodule (not populated at commit 42b0e940; see .gitmodules)
- The ats-regression-tests submodule (not populated at commit 42b0e940; see testing.md for what is known from the CMakeLists and submodule metadata)
- Detailed input spec documentation (covered by the online Sphinx site)
- Amanzi's INSTALL_ATS.md or third-party library installation
