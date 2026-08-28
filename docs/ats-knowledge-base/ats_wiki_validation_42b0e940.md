# ATS Wiki Validator Series — `ats-codebase-wiki-42b0e940` vs `ats`

Expected commit `42b0e940` · 47 pages · 851 source files

## Summary

| Check | Result | Detail |
|---|---|---|
| S1 boundary | ✅ PASS | 0 genuinely-unresolved |
| S2 pins | ✅ PASS | 0 issues |
| S3 factory-keys | ✅ PASS | 0 unresolved keys |

**Overall: PASS**

## S1 — Amanzi-boundary resolution

- Unresolved routines: 12 external-expected, **0 genuinely unresolved**
- Unresolved module files: 29 external-expected, **0 genuinely unresolved**

All unresolved references are declared-external (Amanzi/generated). ✓

<sub>Classified external-expected: AssembleSchur_, CreateMFDmassMatrices, MyLength, SetChanged, SetOffDiagonals, SetScalarCoefficient, UpdateMatrices, WriteVis, add_test, getCommSelf, getEntityParent, getFaceNormal · MatrixMFD.hh, MatrixMFD_Coupled_Surf.hh, _physics.cc, _pk.cc, _reg.hh, _registration.hh, _ti.cc, ats_bgc_registration.hh, ats_deformation_registration.hh, ats_energy_pks_registration.hh, ats_energy_relations_registration.hh, ats_flow_pks_registration.hh, ats_flow_relations_registration.hh, ats_mpc_registration.hh, ats_relations_registration.hh, ats_sediment_transport_registration.hh, ats_surface_balance_registration.hh, ats_transport_registration.hh, ats_transport_relations_registration.hh, ats_version.hh, models_transport_reg.hh, my_pk_registration.hh, overland_conductivity_model.cc, overland_pressure.cc, pk_factory_ats.hh, pk_physical_base.hh, pks_chemistry_reg.hh, richards.cc, state_evaluators_registration.hh</sub>

## S2 — Pin-header completeness

- Pages: 46 · expected commit: `42b0e940`
- Missing `Source pin`: 0 · Missing `Last verified`: 0 · Wrong commit: 0

Every page carries a Source pin + Last verified at the expected commit. ✓

## S3 — Factory-key / type-string presence

- Quoted key strings checked: 63 · source string-literals indexed: 4106
- **Not found in source: 0**

Every quoted key string resolves to a source literal. ✓
