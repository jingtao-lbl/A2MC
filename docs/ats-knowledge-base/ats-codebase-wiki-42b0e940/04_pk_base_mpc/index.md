---
**Source pin:** ATS commit `42b0e940` (`ats-1.7-dev-22-g42b0e940`)
**Last verified:** 2026-07-27
---

# Topic 04: PKs and How They Connect

This topic documents the Process Kernel (PK) base class hierarchy and the Multi-Process Coupler (MPC) pattern that glues PKs together. These are the architectural spine of ATS: every physical solver and every coupling strategy derives from the classes described here.

## Why this topic matters for ECRP

The integrated hydrology capability that makes ATS unique for permafrost research is implemented entirely through the MPC composition pattern. The famous surface-subsurface coupling (Richards + overland flow) is `MPCCoupledWater`, which is a `StrongMPC<PK_PhysicalBDF_Default>`. The full thermal-hydrology permafrost model (`MPCPermafrost`) is built by stacking a further MPC on top of that. Understanding this hierarchy is the entry point to understanding how ELM-ATS coupling works.

## Files in this topic

| File | Contents |
|---|---|
| [pk_base_classes.md](pk_base_classes.md) | PK abstract interface and the four concrete base classes; lifecycle methods; time-stepping roles |
| [mpc.md](mpc.md) | MPC template, WeakMPC, StrongMPC, MPCSubcycled; composition pattern; complete type inventory |
| [mpc_subsurface.md](mpc_subsurface.md) | MPCSubsurface: coupled subsurface flow + energy (permafrost Richards + three-phase energy) |
| [mpc_surface_subsurface.md](mpc_surface_subsurface.md) | MPCCoupledWater and MPCPermafrost: the integrated surface-subsurface hydrology coupling |
| [bc_factory.md](bc_factory.md) | BCFactory: how boundary conditions are read from XML and dispatched to physics PKs |
| [chem_pk_helpers.md](chem_pk_helpers.md) | Chemistry helper functions: unit conversion between transport and chemistry PKs |

## PK type strings (input-deck registry)

Every concrete PK registers under a string that appears in the XML input under `"PK type"`. The full set for this topic:

| PK type string | C++ class |
|---|---|
| `"weak MPC"` | `WeakMPC` |
| `"strong MPC"` | `StrongMPC<PK_t>` (template instantiation) |
| `"subcycling MPC"` | `MPCSubcycled` |
| `"domain set weak MPC"` | `MPCWeakSubdomain` |
| `"coupled flow and transport"` | `MPCFlowTransport` |
| `"subsurface permafrost"` | `MPCSubsurface` |
| `"icy surface"` | `MPCSurface` |
| `"coupled water"` | `MPCCoupledWater` |
| `"operator split coupled water"` | `MPCCoupledWaterSplitFlux` |
| `"permafrost model"` | `MPCPermafrost` |
| `"operator split permafrost"` | `MPCPermafrostSplitFlux` |
| `"reactive transport"` | `MPCReactiveTransport` |
| `"surface subsurface transport"` | `MPCCoupledTransport` |
| `"surface subsurface reactive transport"` | `MPCCoupledReactiveTransport` |
| `"mpc coupled cells"` | `MPCCoupledCells` |

## Inheritance diagram (abbreviated)

```
PK  (Amanzi abstract base, provided by Amanzi not ATS)
├── PK_BDF_Default               [implicit time-integration base]
│   └── PK_PhysicalBDF_Default   [physical PK with conserved-quantity error norm]
│       ├── Richards, EnergyBase, ...  [physics PKs, topics 02-03]
│       └── (base for several MPCs below)
├── PK_Explicit_Default          [explicit time-integration base]
│   └── PK_Physical_Default_Explicit_Default
│       └── (surface energy balance, snow, ...)
└── MPC<PK_t>                    [template, abstract — no AdvanceStep]
    ├── WeakMPC                  [sequential, one AdvanceStep per sub-PK]
    │   ├── MPCCoupledTransport
    │   ├── MPCReactiveTransport
    │   └── MPCCoupledReactiveTransport
    ├── MPCSubcycled             [weak + optional subcycling per child]
    │   ├── MPCFlowTransport
    │   ├── MPCCoupledWaterSplitFlux
    │   └── MPCPermafrostSplitFlux
    │       └── Morphology_PK
    ├── MPCWeakSubdomain         [weak, over a domain-set of identical PKs]
    └── StrongMPC<PK_t>          [globally-implicit, inherits PK_BDF_Default too]
        ├── MPCCoupledCells      [cell-block coupling]
        ├── MPCSubsurface        [subsurface flow+energy, approximate Jacobian]
        │   └── MPCPermafrost    [full 4-PK surface+subsurface permafrost]
        ├── MPCSurface           [surface flow+energy, icy surface]
        ├── MPCCoupledWater      [integrated hydrology: Richards + overland]
        └── MPCCoupledDualMediaWater [macropore + matrix + surface]
```

## Quick navigation

- **I want to understand the Newton solve for integrated hydrology** → [mpc_surface_subsurface.md](mpc_surface_subsurface.md)
- **I want to understand the full permafrost thermal-hydrology coupling** → [mpc_subsurface.md](mpc_subsurface.md) then [mpc_surface_subsurface.md](mpc_surface_subsurface.md)
- **I want to add a new PK and plug it into an MPC** → [pk_base_classes.md](pk_base_classes.md) then [mpc.md](mpc.md)
- **I want to add a new boundary condition** → [bc_factory.md](bc_factory.md)
