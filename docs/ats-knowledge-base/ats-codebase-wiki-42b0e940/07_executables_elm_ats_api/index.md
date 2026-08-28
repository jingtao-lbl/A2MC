---
**Source pin:** ATS commit `42b0e940` (`ats-1.7-dev-22-g42b0e940`)
**Last verified:** 2026-07-27
---

# Topic 07 — Executables and ELM-ATS API

This topic covers everything under `src/executables/`, which contains the
top-level drivers, the simulation coordinator, the mesh factory, and most
importantly the `elm_ats_api/` subdirectory that forms the E3SM/ELM coupling
boundary.

## File map

| File | What it does | Wiki page |
|---|---|---|
| `main.cc` | Entry point for the standalone `ats` executable | [ats_driver.md](ats_driver.md) |
| `ats_driver.{cc,hh}` | `ATSDriver` class — standalone time-loop driver | [ats_driver.md](ats_driver.md) |
| `coordinator.{cc,hh}` | `Coordinator` base class — owns PK, State, vis/checkpoint | [coordinator.md](coordinator.md) |
| `ats_mesh_factory.{cc,hh}` | Mesh creation for all mesh types | [ats_mesh_factory.md](ats_mesh_factory.md) |
| `ats_registration_files.hh` | Factory self-registration aggregator | [registration_files.md](registration_files.md) |
| `elm_ats_api/elm_ats_api.{h,cc}` | Public C API exposed to ELM/Fortran | [elm_ats_api.md](elm_ats_api.md) |
| `elm_ats_api/elm_ats_driver.{hh,cc}` | `ELM_ATSDriver` C++ class implementing the API | [elm_ats_api.md](elm_ats_api.md) |
| `elm_ats_api/Indexer.hh` | Template helpers for ELM vs ATS array indexing | [elm_ats_api.md](elm_ats_api.md) |
| `elm_ats_api/test/elm_ats_test.cc` | C++ standalone test for the API | [testing.md](testing.md) |
| `elm_ats_api/test/fortran/ats.f90` | Fortran interface declarations | [testing.md](testing.md) |
| `elm_ats_api/test/fortran/ats_mod.f90` | Fortran `libats` module implementation | [testing.md](testing.md) |
| `elm_ats_api/test/fortran/test.f90` | Fortran driver test program | [testing.md](testing.md) |
| `test/executable_mesh_factory.cc` | Unit tests for `ats_mesh_factory` | [testing.md](testing.md) |
| `test/executable_coupled_water.cc` | Unit tests for coupled surface-subsurface PKs | [testing.md](testing.md) |
| `test/executable_mesh.cc` | Helper fixture for mesh factory tests | [testing.md](testing.md) |

## Architecture overview

```
main.cc
  |
  +-- ATSDriver (ats_driver.{cc,hh})           standalone time loop
        |
        +-- Coordinator (coordinator.{cc,hh})  base class: owns State, PK, vis/checkpoint
              |
              +-- ats_mesh_factory              builds meshes from XML/Exodus and registers
              +-- PK (from PKs layer)           top-level physics (usually an MPC)
              +-- ats_registration_files.hh     populates PK/Evaluator factories


  ELM_ATSDriver (elm_ats_api/elm_ats_driver.{hh,cc})   <-- ECRP coupling boundary
        |
        +-- Coordinator (base class)           inherits all of the above
        |
        +-- elm_ats_api.{h,cc}                 C wrapper  (extern "C") called by ELM/Fortran
        +-- ats.f90 / ats_mod.f90              Fortran interface module
```

## API entry-point table

The table below lists every public C function in `elm_ats_api.h`, which are
the exact symbols that ELM (or a Fortran caller via `ats_mod.f90`) calls.

| C Function | Phase | Direction | Wiki |
|---|---|---|---|
| `ats_create` | Lifecycle | ELM→ATS | [elm_ats_api.md](elm_ats_api.md#lifecycle) |
| `ats_delete` | Lifecycle | ELM→ATS | [elm_ats_api.md](elm_ats_api.md#lifecycle) |
| `ats_setup` | Pre-run | ELM→ATS | [elm_ats_api.md](elm_ats_api.md#pre-run) |
| `ats_initialize` | Pre-run | ELM→ATS | [elm_ats_api.md](elm_ats_api.md#pre-run) |
| `ats_get_mesh_info` | Pre-run | ATS→ELM | [elm_ats_api.md](elm_ats_api.md#pre-run) |
| `ats_set_soil_hydrologic_parameters` | Pre-run | ELM→ATS | [elm_ats_api.md](elm_ats_api.md#pre-run) |
| `ats_set_veg_parameters` | Pre-run | ELM→ATS | [elm_ats_api.md](elm_ats_api.md#pre-run) |
| `ats_set_soil_hydrologic_properties` | Per-step | ELM→ATS | [elm_ats_api.md](elm_ats_api.md#per-timestep) |
| `ats_set_veg_properties` | Per-step | ELM→ATS | [elm_ats_api.md](elm_ats_api.md#per-timestep) |
| `ats_set_sources` | Per-step | ELM→ATS | [elm_ats_api.md](elm_ats_api.md#per-timestep) |
| `ats_advance` | Per-step | ELM→ATS | [elm_ats_api.md](elm_ats_api.md#per-timestep) |
| `ats_advance_test` | Per-step | ELM→ATS | [elm_ats_api.md](elm_ats_api.md#per-timestep) |
| `ats_get_waterstate` | Post-step | ATS→ELM | [elm_ats_api.md](elm_ats_api.md#post-timestep) |
| `ats_get_water_fluxes` | Post-step | ATS→ELM | [elm_ats_api.md](elm_ats_api.md#post-timestep) |

## ECRP relevance

`elm_ats_api/` is the precise boundary where an AI/ML emulator would be
inserted to replace or augment the ATS hydrologic solver. The C API functions
listed above define the complete data contract: what ELM must supply (forcing,
soil parameters, vegetation state) and what ATS must return (pressure, water
table, fluxes). Any emulator targeting this boundary must reproduce all
quantities in `ats_get_waterstate` and `ats_get_water_fluxes` given the
inputs from `ats_set_*` and `ats_advance`.
