---
**Source pin:** ATS commit `42b0e940` (`ats-1.7-dev-22-g42b0e940`)
**Last verified:** 2026-07-27
---

# Topic 03: Biogeochemistry, Transport, Deformation, and Surface Balance

This topic documents four physics module groups that sit "above" the flow/energy core
(`src/pks/flow/`, `src/pks/energy/`, topic 02) and couple to it through operator-split or
weak-coupling schemes managed by the MPC layer (topic 04).  A fifth module, `test_pks/`,
provides lightweight PKs used in the regression-test harness.

## Module overview

| Module | Directory | Physics | Key PKs |
|---|---|---|---|
| Biogeochemistry | `src/pks/biogeochemistry/` | Carbon cycling, vegetation, optional FATES interface | `BGC simple`, `simple Carbon`, `FATES` |
| Transport | `src/pks/transport/` | Solute advection-dispersion-reaction, sediment transport | `transport ATS`, `sediment transport` |
| Deformation | `src/pks/deform/` | Thaw-driven subsidence (ice loss / porosity change) | `volumetric deformation` |
| Surface balance | `src/pks/surface_balance/` | Snow, ET, surface energy balance (SEB), CLM interface | `surface balance implicit subgrid`, `surface balance CLM`, `general surface balance` |
| Test PKs | `src/pks/test_pks/` | Operator-level and snow-distribution tests | `div-grad operator test`, `snow distribution test` |

## Science overview

### Biogeochemistry
ATS implements a self-contained **Century-based soil carbon decomposition** scheme
(`bgc_simple`) coupled to a multi-PFT big-leaf canopy model.  It produces transpiration
and leaf-shaded radiation as outputs consumed by the flow and surface-energy PKs.  A
second PK (`CarbonSimple`) offers an explicit ODE solver for multi-pool carbon with
bioturbation diffusion and source/decomposition terms.  An experimental **FATES** interface
(`src/pks/biogeochemistry/fates/`) wraps the Functionally Assembled Terrestrial Ecosystem
Simulator Fortran library via ISO C Fortran interoperability; it is present in source but
is underdocumented and partially commented-out.  **Alquimia reactive chemistry is not
implemented inside the BGC PKs**; reactive transport uses Alquimia through the Transport
PK (see `transport.md`).

### Transport
The `Transport_ATS` PK solves multi-component advection-dispersion of solutes in mole
fraction units.  It is operator-split explicit for advection and optionally implicit for
dispersion-diffusion.  The `SedimentTransport_PK` subclass adds erosion/trapping/settling
source terms for sediment.  Reactive chemistry is coupled via the **Alquimia** interface:
`Transport_ATS` holds an `Alquimia_PK` pointer and a `ChemistryEngine` pointer (both
guarded by `#ifdef ALQUIMIA_ENABLED`) and calls the geochemical engine between transport
subcycles.  The MPC layer in `src/pks/mpc/` (`MPCReactiveTransport`, `MPCFlowTransport`)
performs the operator-splitting between flow, transport, and chemistry.

### Deformation
A single PK, `VolumetricDeformation`, implements **vertical subsidence** driven by ice
loss and/or liquid saturation thresholds.  It modifies the Amanzi unstructured mesh
in-place (through the `AmanziMesh::deform` API) and recalculates base porosity to conserve
solid volume.  This is the primary mechanism for simulating **thermokarst and permafrost
ground instability** in ATS, making it a critical component for the Arctic case study in
the ECRP proposal.

### Surface balance
The surface balance PKs close the surface energy budget.  They compute snow, evaporation,
transpiration, and surface energy fluxes as source terms fed into the surface flow and
energy PKs.  Three variants exist: a two-component SEB evaluator (bare ground + snow),
a three-component evaluator (snow + water + tundra), and a CLM-based interface that
uses an old ParFlow-maintained CLM fork for all surface processes.  The rich library of
`constitutive_relations/land_cover/` evaluators provides building blocks for PET (Priestley-
Taylor), rooting-depth transpiration distribution, interception, radiation balance, and
albedo.

## Cross-references

- **Topic 02** (`02_flow_energy`): `VolumetricDeformation` and `BGCSimple` are slaved to
  flow PKs; deformation results in updated mesh geometry that flow uses.  SEB PKs produce
  water and energy sources that feed `OverlandFlow` and `EnergyBase`.
- **Topic 04** (`04_pk_base_mpc`): `MPCReactiveTransport`, `MPCFlowTransport`, and
  `MPCCoupledReactiveTransport` orchestrate transport-chemistry operator splitting.
- **Topic 05** (`05_constitutive_relations`): Surface balance evaluators in
  `src/pks/surface_balance/constitutive_relations/` depend on EOS and water-retention
  evaluators in `src/constitutive_relations/`.
- **Topic 06** (`06_operators`): Transport uses `src/operators/advection/` and
  `src/operators/divgrad/` for advective and diffusive fluxes.

## Files in this topic

- [biogeochemistry.md](biogeochemistry.md) — BGC PKs and evaluators
- [transport.md](transport.md) — advection-dispersion transport and sediment transport
- [deformation.md](deformation.md) — volumetric deformation (subsidence / thermokarst)
- [surface_balance.md](surface_balance.md) — SEB, snow, ET, CLM interface
- [test_pks.md](test_pks.md) — test PKs for operators and snow distribution
