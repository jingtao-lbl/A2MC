---
**Source pin:** ATS commit `42b0e940` (`ats-1.7-dev-22-g42b0e940`)
**Last verified:** 2026-07-27
---

# ATS Codebase Wiki — `42b0e940`

Source-grounded codebase reference for the **Advanced Terrestrial Simulator (ATS)** at commit `42b0e940` (`ats-1.7-dev-22`). Originally generated 2026-05-06 at `b044298a` with the A2MC `codebase_wiki_generation_roadmap.md` Workflow A (greenfield), 7 parallel rewrite subagents; re-verified against `42b0e940` on 2026-07-27 (content unchanged, all 405 citations validated).

## Scope

Documents the ATS source tree only. ATS is built as part of [Amanzi](https://github.com/amanzi/amanzi), which provides mesh, data structure, multi-physics APIs, and math libraries. Amanzi internals are out of scope.

What ATS solves: integrated surface-subsurface coupled hydrology. Richards equation in subsurface plus surface (overland, Manning) flow. Optional thermal (incl. ice for permafrost), ET, surface energy exchange, snow, ground deformation, and reactive transport via the Alquimia interface. Mimetic finite differences on unstructured prismatic meshes.

For the universal context block injected into every topic, see [`UNIVERSAL_CONTEXT.md`](UNIVERSAL_CONTEXT.md).

## Topic map

| # | Topic | Files | Lines | Description |
|---|---|---|---|---|
| 01 | [`01_overview/`](01_overview/index.md) | 5 | ~676 | Scope, build, regression-test layout, citation map |
| 02 | [`02_flow_energy/`](02_flow_energy/index.md) | 7 | ~1227 | Flow PKs (Richards, surface, permafrost), energy PKs (TwoPhase, ThreePhase), thermal-Richards coupling, snow |
| 03 | [`03_bgc_transport_deform/`](03_bgc_transport_deform/index.md) | 6 | ~1071 | Biogeochem (Alquimia), transport, ground deformation, surface balance, test PKs |
| 04 | [`04_pk_base_mpc/`](04_pk_base_mpc/index.md) | 7 | ~1188 | PK base classes, Multi-Process Coupler taxonomy, BC factory, chem helpers |
| 05 | [`05_constitutive_relations/`](05_constitutive_relations/index.md) | 6 | ~1158 | EOS, water retention (lives under `pks/flow/`), surface-subsurface fluxes, generic and column evaluators |
| 06 | [`06_operators/`](06_operators/index.md) | 5 | ~471 | Mimetic FD div-grad, advection (donor upwind), upwinding strategies, deformation operators |
| 07 | [`07_executables_elm_ats_api/`](07_executables_elm_ats_api/index.md) | 7 | ~1590 | ATS driver, Coordinator, mesh factory, **ELM-ATS C API (14 functions)**, registration files, test programs |
| **Total** | | **43** | **~7381** | |

## Entry-point cheat sheet

For ECRP / methodology purposes, these are the highest-leverage citation points.

| Concept | First citation |
|---|---|
| ELM-ATS C API surface | `src/executables/elm_ats_api/elm_ats_api.h:35-126` (14 `extern "C"` functions) |
| `ats_create` / `ats_delete` lifecycle | `src/executables/elm_ats_api/elm_ats_api.cc:27,38` |
| `ats_advance` (per-step coupling driver) | `src/executables/elm_ats_api/elm_ats_api.cc:52` |
| Permafrost MPC (Painter 2016 model) | `src/pks/mpc/mpc_permafrost.hh:23` |
| Coupled water (Coon 2020 surface-subsurface) | `src/pks/mpc/mpc_coupled_water.hh:36` |
| Coupled transport (Molins 2022) | `src/pks/mpc/mpc_coupled_transport.hh:12` |
| Permafrost PK (inherits from Richards) | `src/pks/flow/permafrost_pk.cc` (only ~98 lines override) |
| Five WRM permafrost models (FPD, implicit Painter, McKenzie, SUTRA-Ice, Interfrost) | `src/pks/flow/constitutive_relations/wrm/wrm_*` |
| Single functional deformation strategy | `src/pks/deform/volumetric_deformation.cc` (`"average"` only; `MSTK` and `GLOBAL_OPTIMIZATION` throw) |
| Coordinator (top-level PK driver) | `src/executables/coordinator.cc/hh` |
| Single advection scheme (donor upwind) | `src/operators/advection/advection_factory.cc:29` |

## What changed at this commit (notes for future regen)

- Both `testing/ats-regression-tests/` and `docs/.../ats_demos/` are git submodules and **empty** in this checkout. Run `git submodule update --init --recursive` to populate.
- Five output fields in the ELM-ATS API (`soil_pressure`, `soil_psi`, `sat_ice`, `net_subsurface_fluxes`, `net_runon`) accept pointer arguments but are **never written**. Documented in [`07_executables_elm_ats_api/elm_ats_api.md`](07_executables_elm_ats_api/elm_ats_api.md).
- The Fortran wrapper (`ats.f90`) is materially out of sync with the C header (`elm_ats_api.h`).
- `ats_get_mesh_info` hard-codes lat/lon to Toledo, OH (placeholder).
- `Indexer.hh` is unused.
- The ELM API test suite is disabled in the build (`add_subdirectory(test)` commented out).

These are the kinds of structural facts that the ECRP narrative methodology section can lean on: they show the existing direct-coupling pathway is genuinely under-developed at the API layer, which sharpens the case for an AI/ML emulator-bridged approach.

## How to use this wiki

Start with [`01_overview/index.md`](01_overview/index.md) for orientation, then jump to the topic relevant to your question. Every substantive claim in every file carries a `(path/Module.{cc|hh}:NNN)` citation back to the source. If you find a claim that doesn't verify, please flag it; this wiki is regenerable per the A2MC roadmap.

## Provenance

- Generation method: A2MC `codebase_wiki_generation_roadmap.md` Workflow A (greenfield), 7 parallel `general-purpose` Sonnet subagents.
- Dispatch plan: `~/Documents/Grant/2026_DOE_ECRP/Full-proposal/Memory/20260506a_ATS_RDycore_Wiki_Dispatch_Plan.md`
- Verification: spot-checks on 5 random `(file:line)` citations all verified exactly.

## Validation status

Multi-dimensional validation 2026-05-07 with `validate_wiki.py` (language-agnostic adaptation of A2MC `tools/codebase_wiki_validator.py`). Run twice: initial generation, then post-fix-up after surgical edits to remove real fabrications.

| Dimension | Final pass rate |
|---|---|
| D1 file-citation existence | **100%** (431/431) |
| D2 line-bound validity | **100%** (431/431) |
| D3 ident grep-in-source | 98% (1 false positive — the SHA in source-pin headers) |
| D5 file-mention existence | 90% (residual is intentional documentation of non-source-tree mentions, not fabrication) |

Full report: [`../wiki_source_validation_42b0e940.md`](../wiki_source_validation_42b0e940.md)
Validation analysis: [`Memory/20260507a_ATS_RDycore_Wiki_Validation.md`](~/Documents/Grant/2026_DOE_ECRP/Full-proposal/Memory/20260507a_ATS_RDycore_Wiki_Validation.md)

**Verdict.** Every `(file:line)` citation in this wiki resolves to a real file with a valid line number. Safe to cite from in downstream documents.

**The 28 D5 residuals are all legitimate non-source-tree references that the wiki annotates intentionally:**
- 14 per-category `ats_*_registration.hh` files are **CMake-generated** (`HEADERFILE` directives in `src/*/CMakeLists.txt`).
- `ats_version.hh` is **CMake-generated** from `tools/cmake/ats_version.hh.in`.
- `MatrixMFD.hh`, `MatrixMFD_Coupled_Surf.hh`, `pk_factory_ats.hh`, `pk_physical_base.hh` are **Amanzi-side headers** (not in ATS source); the ATS `.cc` files include them from the Amanzi include path.
- `INSTALL_ATS.md`, `codebase_wiki_generation_roadmap.md` are **cross-repository references**.
- `ISO_Fortran_binding.h` is the **Fortran standard library header**.
- `richards.cc`, `overland_pressure.cc`, `overland_conductivity_model.cc`, `my_pk_registration.hh` appear in the wiki's own "Known issues" annotation prose explaining that those bare names are wrong; the real citations elsewhere in the wiki use the correct file names.
