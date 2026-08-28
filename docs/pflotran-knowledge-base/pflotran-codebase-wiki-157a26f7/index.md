**Source pin:** PFLOTRAN commit 157a26f7
**Scope:** Index — PFLOTRAN codebase wiki
**Last verified:** 2026-07-31

# PFLOTRAN Codebase Wiki — commit `157a26f7`

Source-grounded reference for PFLOTRAN, written by reading the source at a single pinned commit. Every substantive claim carries a `(src/pflotran/<file>.F90:NNN)` citation.

## The pin, and why this commit

| | |
|---|---|
| Commit | **`157a26f7`** (2025-02-27, "Merged in michael/geothermal-well (PR #1150)") |
| Branch | `master` of `bitbucket.org/pflotran/pflotran` |
| Version | `PFLOTRAN_VERSION_MAJOR = 6`, `PFLOTRAN_RELEASE = PETSC_FALSE` (a development build) |
| PETSc required | ≥ 3.21 |
| Tree size | 314 `.F90` files, 518,568 lines |

**This is deliberately NOT current upstream master.** It is the commit the miniLEO case study's binary was compiled from, so the wiki describes the code that produced the results A2MC is calibrating against. Upstream master is 523 commits and ~17 months ahead, across a major-version boundary (v7, PETSc ≥ 3.24.3), with 235 of 331 files changed — a wiki pinned there would document different code. Rationale: `memory/dev_logs_adapterkitpflotran/20260731c`.

A future bump creates a parallel `pflotran-codebase-wiki-<newhash>/`; this directory is never overwritten.

## Topics

| Topic | Files | Lines | Covers |
|---|---|---|---|
| [`geochemistry/`](geochemistry/) | 4 | 1247 | TST mineral kinetics, rate constants + surface-area evolution, aqueous speciation, database format, sorption, the reaction-sandbox plug-in |
| [`input_deck/`](input_deck/) | 3 | 1578 | Deck grammar and the reader, block termination, context-sensitive keywords, constraints/regions/strata, units |
| [`output_io/`](output_io/) | 7 | 2900 | Mass-balance file + column catalogue, observation/snapshot, Tecplot, HDF5/XDMF, checkpoint/restart, output timing |
| [`reactive_transport/`](reactive_transport/) | 4 | 1333 | GIRT vs OSRT, advection/dispersion/diffusion, gas-phase transport, transport BCs |
| [`flow_modes/`](flow_modes/) | 4 | 943 | GENERAL mode, boundary conditions incl. seepage face, Richards/TH, mode selection |
| [`solvers_timestepping/`](solvers_timestepping/) | 3 | 984 | Timestep control and cuts, Newton/linear solvers, process-model coupling |
| [`grid_discretization/`](grid_discretization/) | 3 | 873 | Unstructured grids + `.ugi`/`.ss` formats, structured grids, patch/discretization |
| [`material_properties/`](material_properties/) | 3 | 774 | Characteristic curves (van Genuchten/Mualem), `MATERIAL_PROPERTY` cards, porosity-permeability evolution |

**31 files, 10,632 lines.**

## Deliberately out of scope

Documented as absent rather than covered thinly, because they are irrelevant to the miniLEO basalt-weathering case and individually large:

WIPP/GDSA (`pm_wipp*`, `wipp_*`), waste form (`pm_waste_form.F90`, 9,746 lines), well models (`pm_well.F90`, 9,752 lines), geomechanics, geophysics/ERT, hydrate, SCO2, and the inversion subsystem. `patch.F90` (12,115 lines) is covered by role and entry points, not line by line.

## Validation

Verified with the generic wiki-vs-source validator, which dispatches through `models/pflotran/spec.py`:

```bash
python tools/validate_wiki_vs_source.py --model pflotran \
  --wiki  docs/pflotran-knowledge-base/pflotran-codebase-wiki-157a26f7 \
  --source <PFLOTRAN checkout at 157a26f7>
```

| Check | Result |
|---|---|
| A. File-citation existence | **2392/2392** |
| B. Line-bound validity | **2392/2392** |
| C. Routine-reference presence | **123/123** |
| D. Module-file presence | **169/169** |
| Red pages | **0** |

**Verdict: Green.** Report: `docs/a2mc_reference/wiki_source_validation_pflotran_157a26f7.md`.

PETSc/HDF5 symbols are classified as expected-external via `spec.external_symbol_names` / `external_module_patterns` rather than counted as unresolved — PFLOTRAN is built ON PETSc, so those references are correct, not fabrications.

## Reading notes

- **Deck keywords are matched in source as exact string literals** (`case('RATE_CONSTANT')`). Where this wiki names a keyword, it exists as a literal at this commit.
- **PFLOTRAN sometimes composes an error/warning into `option%io_buffer` and never prints it.** At least two independent instances are documented here (the `Sr` consistency check in `characteristic_curves.F90`, and a multi-species active-gas message in `reactive_transport.F90`). **A silent run is therefore not proof of a consistent deck.**
- Several cards parse but are inert at this commit (e.g. `GRID/FILE`, `GRID/INVERT_Z`, `AFFINITY_POWER` on the SIMPLE rate path). These are flagged in the relevant topic rather than presented as working knobs.
- Where a unit or default could not be established from source, the page says so instead of guessing.
