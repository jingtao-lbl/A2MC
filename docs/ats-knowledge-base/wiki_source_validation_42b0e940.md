# Wiki source validation — ATS 42b0e940

**Wiki root:** `docs/ats-knowledge-base/ats-codebase-wiki-42b0e940`
**Source root:** `amanzi/ats` @ `42b0e940` (`ats-1.7-dev-22-g42b0e940`)
**Re-verified:** 2026-07-27 (originally generated + validated at `b044298a`, 2026-05-07)
**Validator:** `tools/validate_wiki_vs_source.py --model ats`

## Version-bump context

The wiki was generated at `b044298a` (`ats-1.7-dev-16`). Upstream `master` advanced **6 commits** to `42b0e940` (`ats-1.7-dev-22`, 2026-07-17). Five of the six commits are CI / Dependabot / workflow changes (`.github/`); **one** touches source: `src/constitutive_relations/surface_subsurface_fluxes/surface_top_cells_evaluator.cc` — an internal refactor of `EnsureCompatibility_ToDeps_` (rename a local `CompositeVectorSpace`, add an `S.Require` mesh-component block). That method is **not documented at line level** by the wiki, so no page content changed. This update is therefore a **re-pin + full re-verification**, not a regeneration.

## Result (against 42b0e940)

- Wiki pages: 47 · Source files: 851 · Declared routines indexed: 1435

| Check | Status | Pass / Total |
|---|---|---|
| A. File-citation existence | **Green** | 405/405 (100%) |
| B. Line-bound validity | **Green** | 405/405 (100%) |
| C. Routine-reference presence | Yellow | 138/154 |
| D. Module-file presence | Green | 266/295 |

**Every file:line citation in every page resolves in the latest source (A + B = 100%).**

## The C / D shortfalls are validator false-positives (not wiki errors)

- **C — 16 "unresolved routines":** all are **Amanzi-framework** symbols the wiki correctly references but which live outside the ATS source tree the validator indexes — `SetScalarCoefficient`, `UpdateMatrices`, `SetChanged`, `getFaceNormal`, `getEntityParent`, `getCommSelf`, `CreateMFDmassMatrices`, `AssembleSchur_`, `SetOffDiagonals`, `WriteVis`, `MyLength` — plus the CMake command `add_test`. `UNIVERSAL_CONTEXT.md` explicitly declares Amanzi internals out of scope; the wiki documents ATS calling into these APIs.
- **D — 29 "missing module files":** generated registration headers (`ats_*_registration.hh`, `*_reg.hh`), wildcard/pattern names (`_pk.cc`, `_ti.cc`, `_physics.cc`, `_registration.hh`), the build-generated `ats_version.hh`, and Amanzi's `MatrixMFD.hh` / `MatrixMFD_Coupled_Surf.hh`. None are ATS source files the wiki misrepresents.
- **Red page `01_overview/testing.md`:** flagged red only because its single "routine" reference is the CMake `add_test` (0 C++ routines, 0 file citations). Not real drift.

## Verdict (citation validation)

Against the latest ATS (`42b0e940`), **all source citations validated 100%**; the residual Yellow is entirely Amanzi-out-of-scope references and generated/pattern filenames, unchanged in character from the `b044298a` baseline. The **re-pin** (b044298a → 42b0e940) required no citation changes.

## ⚠ Semantic audit (2026-07-27) — citation-clean is not defect-free

Citation validation (this file) confirms every `file:line` resolves, but **cannot** detect a defect where the prose misdescribes behavior, a factory-key string is wrong, or a class name is corrupted. A subsequent **Workflow B semantic audit** (7 subagents, one per section, verifying prose against source at `42b0e940`) found and **fixed** real defects that had been present since the original `b044298a` generation:

- **9 wrong factory / PK-type / evaluator keys** (input-deck-breaking): `"carbon simple"`→`"simple Carbon"`, `"divgrad test"`→`"div-grad operator test"`, `"test snow dist"`→`"snow distribution test"`, `"surface top cells"`→`"surface from top cell evaluator"`, `"top cells from surface"`→`"top cell from surface evaluator"`, `"overland source from subsurface flux"`→`"…via flux"`, `"initial time evaluator"`→`"initial value"`, `"time max evaluator"`→`"max in time"`, plus stating the FATES key `"FATES"`.
- **1 corrupted class name:** `RichardsStealthyState` → `RichardsSteadyState`.
- **1 wrong friend-class:** Permafrost's friend is `MPCCoupledFlowEnergy`, not `MPCSubsurface`.
- **1 coupling-boundary inversion (high-stakes):** `elm_ats_api.md`'s `ats_initialize` had `patm`/`soilp` roles reversed — the driver consumes the 2nd C-API slot as water content and ignores the 3rd; atm pressure is hardwired 101325 Pa.
- Plus a suppress-flag string, a garbled implicit-model formula, and a factory-namespace name.

These are now corrected in the wiki. The mechanizable classes (factory keys, the Amanzi boundary, pin headers) are additionally gated going forward by **`tools/validate_ats_wiki.py`** (the ATS wiki validator series: S1 boundary, S2 pin-header, S3 factory-key), which passes on the corrected wiki. See `ats_wiki_validation_42b0e940.md` and `memory/dev_logs_adapterkitats/`.
