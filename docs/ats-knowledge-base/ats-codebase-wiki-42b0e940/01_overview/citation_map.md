---
**Source pin:** ATS commit `42b0e940` (`ats-1.7-dev-22-g42b0e940`)
**Last verified:** 2026-07-27
---

# Citation Map: Four README Papers and Their Source Modules

The README (README.md:39-51) and the Sphinx index
(docs/documentation/source/index.rst:33-45) list five citations: one primary
code citation and four application-area citations. This file maps each to the
specific source modules that implement the described models.

---

## Primary Code Citation (always cite)

**Coon et al. 2020 (code):** E.T. Coon, M. Berndt, A. Jan, D. Svyatsky, et al.
"Advanced Terrestrial Simulator." U.S. Department of Energy, USA. Version 1.0.
DOI: https://doi.org/10.11578/dc.20190911.1

This is the software release citation for ATS itself. Cite for any use of the
code regardless of application domain. It does not map to a single source
module; the citation covers the entire codebase.

---

## Citation 1: Watershed Hydrology (Coon et al. 2020, AWR)

**Full reference:** Coon, Ethan T., et al. "Coupling surface flow and subsurface
flow in complex soil structures using mimetic finite differences." Advances in
Water Resources 144 (2020): 103701. DOI: https://doi.org/10.1016/j.advwatres.2020.103701

**Cite when:** Your simulation couples subsurface Richards flow to surface overland
flow (diffusion wave / Manning equation) without thermal/freeze-thaw processes.

**Primary source module:**

`src/pks/mpc/mpc_coupled_water.hh` -- The MPC that couples Richards equation
(subsurface flow) to the diffusion wave equation (surface flow) through
continuity of both pressure and flux. The file header contains the governing
equations and an explicit cross-reference (src/pks/mpc/mpc_coupled_water.hh:36):

> This leverages subsurface discretizations that include face-based unknowns
> ... In this approach (see `Coon et al WRR 2020
> <https://doi.org/10.1016/j.advwatres.2020.103701>`_), the surface equations
> are directly assembled into the subsurface discrete operator.

**Implementation mechanism:** The surface pressure unknown is co-located with
subsurface face unknowns at the land surface, allowing the surface equations to
be assembled directly into the subsurface operator (the "DAE elimination"
approach described in the paper). This requires MFD discretizations that carry
face-based unknowns (e.g., `"mfd: *"` methods).

**Related modules:**
- `src/pks/flow/richards.cc/hh` -- the subsurface flow PK
- `src/pks/flow/overland_pressure_pk.cc` / `src/pks/flow/overland_pressure.hh` -- the surface flow PK
- `src/pks/mpc/mpc_coupled_water_split_flux.cc/hh` -- flux-split variant
- `src/pks/mpc/mpc_delegate_water.cc/hh` -- helper for surface-subsurface flux exchanges

---

## Citation 2: Arctic Hydrology (Painter et al. 2016)

**Full reference:** Painter, Scott L., et al. "Integrated surface/subsurface
permafrost thermal hydrology: Model formulation and proof-of-concept simulations."
Water Resources Research 52.8 (2016): 6062-6077. DOI: https://doi.org/10.1002/2015WR018427

**Cite when:** Your simulation includes coupled thermal and hydrological processes
with freeze/thaw (permafrost, active layer dynamics, ice formation in soils).

**Primary source module:**

`src/pks/mpc/mpc_permafrost.hh` -- The MPC that couples surface energy and flow
to subsurface energy and flow for integrated thermal hydrology with freeze/thaw.
The file header states explicitly (src/pks/mpc/mpc_permafrost.hh:23-24):

> This is the implementation of the model described in `Painter et al WRR 2016
> <https://doi.org/10.1002/2015WR018427>`_.

**Implementation mechanism:** The permafrost MPC coordinates four coupled PKs:
subsurface flow, subsurface energy, surface flow, and surface energy. It
enforces continuity of both temperature and diffusive energy flux at the
surface-subsurface boundary, while advected energy fluxes are passed with the
mass flux. The PK type string is `"permafrost model"`.

**Related modules:**
- `src/pks/energy/` -- subsurface and surface energy PKs
- `src/pks/mpc/mpc_subsurface.cc/hh` -- subsurface coupled flow+energy
- `src/pks/mpc/mpc_surface.cc/hh` -- surface coupled flow+energy
- `src/pks/mpc/mpc_permafrost_split_flux.cc/hh` -- flux-split permafrost variant
- `src/pks/flow/constitutive_relations/wrm/wrm_fpd_permafrost_model.hh` -- "freezing point depression" water retention model for permafrost (references Painter in header)
- `src/pks/flow/constitutive_relations/wrm/wrm_fpd_smoothed_permafrost_model.cc/hh` -- smoothed variant

---

## Citation 3: Reactive Transport (Molins et al. 2022)

**Full reference:** Molins, Sergi, et al. "A Multicomponent Reactive Transport
Model for Integrated Surface-Subsurface Hydrology Problems." Water Resources
Research 58.8 (2022): e2022WR032074. DOI: https://doi.org/10.1029/2022WR032074

**Cite when:** Your simulation includes solute transport (reactive or passive)
in coupled surface-subsurface flow, including wetting-and-drying dynamics on
the surface.

**Primary source module:**

`src/pks/mpc/mpc_coupled_transport.hh` -- The MPC that couples surface and
subsurface transport. The header states (src/pks/mpc/mpc_coupled_transport.hh:12-14):

> This MPC couples surface and subsurface transport. It is implemented as
> described in `Molins et al WRR 2022
> <https://doi.org/10.1029/2022WR032074>`_, and deals with the conservation of
> advected fluxes as they are transported laterally, infiltrate, etc,
> including wetting and drying of surface cells.

The PK type string is `"surface subsurface transport"`. PKs must be ordered as
`{subsurface transport, surface transport}` in the input deck.

**Related modules:**
- `src/pks/transport/` -- subsurface and surface transport PKs
- `src/pks/biogeochemistry/` -- biogeochemical reaction source/sink terms
- `src/pks/mpc/mpc_reactivetransport.cc/hh` -- couples transport to geochemistry (single domain)
- `src/pks/mpc/mpc_coupled_reactivetransport.cc/hh` -- coupled surface-subsurface reactive transport
- The Alquimia interface (external geochemical engine coupling) is referenced from `src/pks/chem_pk_helpers.cc/hh` and the biogeochemistry subdirectory

---

## Citation 4: Multiphysics Modeling Framework (Coon et al. 2016)

**Full reference:** Coon, Ethan T., J. David Moulton, and Scott L. Painter.
"Managing complexity in simulations of land surface and near-surface processes."
Environmental Modelling & Software 78 (2016): 134-149.
DOI: https://doi.org/10.1016/j.envsoft.2015.12.017

**Cite when:** Your work focuses on or relies on the multi-physics coupling
framework itself (the PK/MPC architecture, operator-split vs. globally-implicit
coupling, or the general ATS software design), rather than a specific physics
application.

**Primary source modules (framework-level):**

This paper describes the PK/MPC architecture. No single source file carries an
explicit inline citation to this paper (verified by grep); the citation appears
only in README.md:51 and docs/documentation/source/index.rst:45. The
implementation is distributed across the base class hierarchy:

| Module | Role |
|---|---|
| `src/pks/pk_bdf_default.cc/hh` | Base class for all implicitly time-integrated PKs (BDF/backward difference formula). Provides the time integrator hook and preconditioner assembly flag. |
| `src/pks/pk_explicit_default.cc/hh` | Base class for explicitly time-integrated PKs. |
| `src/pks/pk_physical_bdf_default.cc/hh` | Base class for physical PKs with BDF integration; adds field-key registration and error norm. |
| `src/pks/pk_physical_explicit_default.hh` | Explicit variant for physical PKs. |
| `src/pks/mpc/mpc.hh` | Abstract MPC base: holds a list of sub-PKs, loops over them for setup/initialize/advance, instantiates sub-PKs via `PKFactory`. |
| `src/pks/mpc/strong_mpc.hh` | Globally implicit coupling: all sub-PKs solved as a single block-preconditioned Newton system. PK type `"strong MPC"`. |
| `src/pks/mpc/weak_mpc.cc/hh` | Sequential (operator-split) coupling: calls each sub-PK's AdvanceStep in order. PK type `"weak MPC"`. |
| `src/pks/mpc/mpc_subcycled.cc/hh` | Weakly coupled with optional subcycling of any sub-PK. |
| `src/executables/coordinator.cc/hh` | Top-level time loop: calls the root PK's setup/initialize/advance/visualize/checkpoint sequence. |
| `src/executables/ats_registration_files.hh` | Aggregates all `#include "*_reg.hh"` registration headers that plug PKs and evaluators into the factory system at static-initialization time. |

**Factory pattern:** Each PK registers itself via a `RegisteredPKFactory<T>`
instantiation in its corresponding `*_reg.hh` header (e.g.,
`src/pks/mpc/weak_mpc_reg.hh` registers `WeakMPC` under the string `"weak MPC"`).
The `Amanzi::PKFactory` is invoked at runtime in `coordinator.cc:149-150` to
instantiate the root PK from the input deck's PK type string.

---

## Quick-Reference Table

| Application | Paper | Primary module with inline citation |
|---|---|---|
| Any use of ATS | Coon et al. 2020 (software) | (entire codebase) |
| Surface-subsurface flow coupling | Coon et al. 2020 (AWR) | `src/pks/mpc/mpc_coupled_water.hh:36` |
| Permafrost / freeze-thaw thermal hydrology | Painter et al. 2016 | `src/pks/mpc/mpc_permafrost.hh:23` |
| Reactive transport in coupled flow | Molins et al. 2022 | `src/pks/mpc/mpc_coupled_transport.hh:12` |
| Multiphysics framework / PK architecture | Coon et al. 2016 | README.md:51 (no inline source citation found) |
