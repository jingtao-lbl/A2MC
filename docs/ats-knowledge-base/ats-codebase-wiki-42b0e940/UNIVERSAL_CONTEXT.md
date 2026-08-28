# Universal context — ATS codebase wiki

This block is the shared preamble injected into every ATS topic-rewrite subagent. Keep ≤ 15 bullets; ordered by impact.

- **Pinned commit.** `42b0e940` (`ats-1.7-dev-22-g42b0e940`).
- **Wiki generation date.** 2026-05-06 (originally generated at `b044298a`). **Re-verified against `42b0e940` on 2026-07-27** — content unchanged: of the 6 intervening `master` commits (5 CI/dependabot), the only source delta was an internal refactor of `surface_top_cells_evaluator.cc::EnsureCompatibility_ToDeps_`, which the wiki does not document at line level. All 405 file:line citations validated 100% against `42b0e940`.
- **Build coupling (critical).** ATS is now built as part of Amanzi (see [INSTALL_ATS.md](https://github.com/amanzi/amanzi/blob/master/INSTALL_ATS.md)). Standalone ATS install is not supported. This wiki documents ATS source only; Amanzi internals are out of scope. The Amanzi side provides mesh, data structure, multi-physics APIs, and math libraries.
- **What ATS solves.** Coupled surface-subsurface integrated hydrology. Richards equation in subsurface + surface (overland + Manning) flow. Optionally adds thermal (incl. ice for permafrost), ET, surface energy exchange, snow, deformation, gray and green infrastructure, and reactive transport via the Alquimia interface.
- **Numerics.** Mimetic finite differences on unstructured prismatic meshes. Coupled flow + energy uses block-preconditioned Newton (BDF).
- **Source layout.**
  - `src/pks/` (process kernels: per-physics solver modules) with subdirs `flow`, `energy`, `deform`, `biogeochemistry`, `transport`, `surface_balance`, `mpc`, `test_pks`, plus PK base classes (`pk_*_default.{cc,hh}`) and `bc_factory.{cc,hh}`.
  - `src/constitutive_relations/` (`eos`, `water_retention`, `surface_subsurface_fluxes`, `generic_evaluators`, `column_integrators`).
  - `src/operators/` (`advection`, `deformation`, `divgrad`, `upwinding`).
  - `src/executables/` (driver `ats_driver.cc`/`main.cc`, `coordinator.{cc,hh}`, `ats_mesh_factory.{cc,hh}`, **`elm_ats_api/`** for E3SM coupling).
  - `tools/`, `testing/ats-regression-tests/`, `docs/`.
- **Languages.** 309 `.cc` + 490 `.hh` source files. ~17 Python helpers under `src/` and `tools/`.
- **Process Kernel pattern.** PKs follow a base class hierarchy (`pk_bdf_default` for implicit time-stepped, `pk_explicit_default` for explicit, `pk_physical_*_default` for physical PKs). The Multi-Process Coupler (`pks/mpc/`) glues PKs together (e.g., flow+energy coupled implicit MPC).
- **Inputs.** XML-based input decks (Amanzi spec). See `testing/ats-regression-tests/` for canonical examples.
- **Coupling boundary (critical for ECRP).** `src/executables/elm_ats_api/` is the E3SM/ELM coupling boundary. This is the key entry point for the proposed AI/ML-bridged ELM-ATS coupling and deserves careful documentation.
- **Citations.** `(path/relative/to/ats/Module.{cc|hh}:NNN)` format. Example: `(src/pks/flow/richards_pk.cc:42)`. Always grep the actual source before citing; never copy line numbers from prior wikis or training memory.
- **Honesty.** If an expected routine, parameter, or feature is not present, document the absence. Do not fabricate.
- **Length target.** Roughly proportional to the number of files in the topic. Aim for clarity over completeness; reader should be able to start at the topic index and navigate to the right file:line in two clicks.
