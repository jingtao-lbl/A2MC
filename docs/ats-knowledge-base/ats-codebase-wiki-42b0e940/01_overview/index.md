---
**Source pin:** ATS commit `42b0e940` (`ats-1.7-dev-22-g42b0e940`)
**Last verified:** 2026-07-27
---

# Topic 01: Overview

This topic provides orientation to ATS: what it is, how it is built, how tests
are structured, and which peer-reviewed papers correspond to which source
modules.  These files are meta-level documentation; they do not cover any
individual physics module (see topics 02-07 for that).

## Files in this topic

| File | Contents |
|---|---|
| [scope.md](scope.md) | What ATS is, science capabilities, in/out-of-scope for this wiki, and the Amanzi dependency relationship |
| [build.md](build.md) | Build instructions, CMake structure, key variables, and fix-rpath.sh |
| [testing.md](testing.md) | Testing infrastructure, ats-regression-tests submodule (not populated at this commit), how to run tests, sample input deck anatomy |
| [citation_map.md](citation_map.md) | The four README citations and which source modules implement each paper's model |

## Where to start

- New users: read [scope.md](scope.md) first to understand what ATS does, then [build.md](build.md) to get a build going.
- Developers adding physics: read [scope.md](scope.md) for the architectural overview and jump to the topic that covers your physics area (topics 02-07).
- Researchers citing ATS: [citation_map.md](citation_map.md) shows which paper to cite for which application.
- CI / testing: [testing.md](testing.md) documents the test infrastructure and how to run or create regression tests.

## Relationship to other topics

| Topic | Coverage |
|---|---|
| 02_flow_energy | Richards + overland flow PKs, surface energy, snow, ET |
| 03_bgc_transport_deform | Reactive transport, biogeochemistry (Alquimia), deformation |
| 04_pk_base_mpc | PK base class hierarchy, MPC coupling patterns |
| 05_constitutive_relations | EOS, water retention models, surface-subsurface fluxes |
| 06_operators | Advection, div-grad, upwinding, deformation operators |
| 07_executables_elm_ats_api | Driver (main.cc, coordinator), ELM-ATS coupling API |
