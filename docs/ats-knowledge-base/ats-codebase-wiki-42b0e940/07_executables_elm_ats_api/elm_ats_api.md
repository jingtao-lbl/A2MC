---
**Source pin:** ATS commit `42b0e940` (`ats-1.7-dev-22-g42b0e940`)
**Last verified:** 2026-07-27
---

# ELM-ATS Coupling API

Sources:
- `src/executables/elm_ats_api/elm_ats_api.h` — public C header (the contract)
- `src/executables/elm_ats_api/elm_ats_api.cc` — thin C wrapper implementations
- `src/executables/elm_ats_api/elm_ats_driver.hh` — `ELM_ATSDriver` class declaration
- `src/executables/elm_ats_api/elm_ats_driver.cc` — `ELM_ATSDriver` implementation
- `src/executables/elm_ats_api/Indexer.hh` — array index helpers
- `src/executables/elm_ats_api/test/fortran/ats.f90` — Fortran interface block
- `src/executables/elm_ats_api/test/fortran/ats_mod.f90` — Fortran `libats` module

Authors: Joe Beisman, Fenming Yuan, Ethan Coon

---

## Overview

The ELM-ATS API is the exact coupling boundary between E3SM Land Model (ELM)
and the ATS hydrologic solver. It defines a C language interface (`extern "C"`)
so that ELM (written in Fortran/C++) can call ATS (written in C++) as a
library without C++ name-mangling issues.

The API exposes 14 functions organized into three temporal phases:

- **Lifecycle** — create and destroy the ATS driver object
- **Pre-run** — setup, mesh query, parameter setting, initialization
- **Per-timestep** — set forcing/properties, advance, retrieve state and fluxes

ELM drives the outer time loop; ATS sub-cycles internally if needed to meet
numerical convergence within each ELM timestep.

---

## Opaque pointer pattern

`(src/executables/elm_ats_api/elm_ats_api.h:24-31)`

The C API hides the C++ object behind an opaque pointer:

```c
// in C++ translation units:
class ELM_ATSDriver;
typedef ELM_ATSDriver *ELM_ATSDriver_ptr;

// in pure C translation units (no C++ classes available):
typedef struct ELM_ATSDriver_ptr *ELM_ATSDriver_ptr;
```

Fortran callers store this as `type(c_ptr)`. The pointer is allocated by
`ats_create` and freed by `ats_delete`. Callers must never dereference it.

---

## Expected call order

From `elm_ats_driver.hh` (lines 14-30):

```
ELM_ATSDriver ats;           // via ats_create
ats.setup();                 // via ats_setup
ats.get_mesh_info();         // via ats_get_mesh_info
ats.set_soil_parameters();   // via ats_set_soil_hydrologic_parameters
ats.set_veg_parameters();    // via ats_set_veg_parameters
ats.initialize();            // via ats_initialize

for each ELM timestep:
  ats.set_soil_properties();   // via ats_set_soil_hydrologic_properties
  ats.set_veg_properties();    // via ats_set_veg_properties
  ats.set_sources();           // via ats_set_sources
  ats.advance(dt, ...);        // via ats_advance
  ats.get_waterstate();        // via ats_get_waterstate
  ats.get_water_fluxes();      // via ats_get_water_fluxes

ats_delete(ats);
```

---

## Lifecycle functions {#lifecycle}

### `ats_create`

**Declaration** `(elm_ats_api.h:35)`:
```c
ELM_ATSDriver_ptr ats_create(MPI_Fint *f_comm, const char *input_filename);
```

**Implementation** `(elm_ats_api.cc:27-35)`:

```cpp
ELM_ATSDriver_ptr ats_create(MPI_Fint* f_comm, const char* input_filename)
{
  if (!Kokkos::is_initialized()) {
    Kokkos::initialize();
    ats_kokkos_init = true;
  }
  return reinterpret_cast<ELM_ATSDriver_ptr>(
    ATS::createELM_ATSDriver(f_comm, input_filename));
}
```

`createELM_ATSDriver` `(elm_ats_driver.cc:29-55)`:
1. Converts the Fortran MPI communicator handle (`MPI_Fint`) to a C
   communicator via `MPI_Comm_f2c(*f_comm)`.
2. Checks that `input_filename` is non-empty and exists on disk.
3. Parses the ATS XML input deck via
   `Teuchos::getParametersFromXmlFile(input_filename)`.
4. Constructs and returns a heap-allocated `ELM_ATSDriver` object.
   The `ELM_ATSDriver` constructor runs the full `Coordinator` constructor
   (mesh creation, PK instantiation, vis/checkpoint setup).

**Memory:** The caller owns the returned pointer. It must be freed by
`ats_delete`.

**Kokkos:** If Kokkos was not yet initialized by the calling code (ELM does
not yet initialize Kokkos), the API initializes it here and sets the
module-level flag `ats_kokkos_init = true` so that `ats_delete` knows to
finalize it. `(elm_ats_api.cc:18-20)`

---

### `ats_delete`

**Declaration** `(elm_ats_api.h:38)`:
```c
void ats_delete(ELM_ATSDriver_ptr ats);
```

**Implementation** `(elm_ats_api.cc:38-49)`:

```cpp
void ats_delete(ELM_ATSDriver_ptr ats)
{
  auto ats_ptr = reinterpret_cast<ATS::ELM_ATSDriver*>(ats);
  ats_ptr->finalize();
  delete ats_ptr;
  if (ats_kokkos_init && Kokkos::is_initialized()) {
    Kokkos::finalize();
    ats_kokkos_init = false;
  }
}
```

`ELM_ATSDriver::finalize()` `(elm_ats_driver.cc:493)` calls
`WriteStateStatistics`, `report_memory()`, `Teuchos::TimeMonitor::summarize`,
and `Coordinator::finalize()` (which writes the final checkpoint).

---

## Pre-run functions {#pre-run}

### `ats_setup`

**Declaration** `(elm_ats_api.h:66)`:
```c
void ats_setup(ELM_ATSDriver_ptr ats);
```

**C++ method** `ELM_ATSDriver::setup()` `(elm_ats_driver.cc:163-272)`:

Registers all ELM-specific fields with the `State` object before delegating
to `Coordinator::setup()`. Fields registered here fall into four categories:

**ELM→ATS potential sources (surface, 1D per column):**
- `pot_infilt_key_` — potential infiltration rate [mol m⁻² s⁻¹]
- `pot_evap_key_` — potential evaporation rate [mol m⁻² s⁻¹]
- `pot_trans_key_` — potential transpiration rate [mol m⁻² s⁻¹]

**ELM→ATS soil parameters (3D per cell):**
- `base_poro_key_` — base porosity [-]
- `perm_key_` — permeability [m²]
- `ch_b_key_` — Clapp-Hornberger b [-]
- `ch_smpsat_key_` — Clapp-Hornberger matric potential at saturation [Pa]
- `ch_sr_key_` — Clapp-Hornberger residual saturation [-]

**Dynamic soil properties (3D per cell):**
- `poro_key_` — effective porosity (uses base + compressibility model)
- `root_frac_key_` — rooting depth fraction [-]

**ATS→ELM water state:**
- `pd_key_` — ponded depth [m]
- `wtd_key_` — water table depth [m]
- `pc_key_` — capillary pressure gas-liquid [Pa]
- `sat_key_` — liquid saturation [-]

**Internal density fields (for unit conversion):**
- `surf_mol_dens_key_`, `surf_mass_dens_key_` — surface water density
- `subsurf_mol_dens_key_`, `subsurf_mass_dens_key_` — subsurface water density
- `surf_cv_key_` — surface cell volume (= area per column) [m²]
- `cv_key_` — subsurface cell volume [m³]

**ATS→ELM flux fields:**
- `infilt_key_` — actual surface-subsurface flux [mol m⁻² s⁻¹]
- `evap_key_` — actual evaporation [mol m⁻² s⁻¹]
- `trans_key_` — actual transpiration [mol m⁻³ s⁻¹]
- `total_trans_key_` — total transpiration [mol m⁻² s⁻¹]

**Primary state field:**
- `pres_key_` — subsurface pressure [Pa], owned by the flow PK

---

### `ats_get_mesh_info`

**Declaration** `(elm_ats_api.h:54-63)`:
```c
void ats_get_mesh_info(ELM_ATSDriver_ptr ats,
                       int * const ncols_local,
                       int * const ncols_global,
                       double * const lat,
                       double * const lon,
                       double * const elev,
                       double * const surf_area,
                       int * const pft,
                       int * const nlevgrnd,
                       double * const depth);
```

**C++ method** `ELM_ATSDriver::get_mesh_info` `(elm_ats_driver.cc:279-320)`:

| Output parameter | Meaning | Status |
|---|---|---|
| `ncols_local` | Number of surface columns on this rank | Implemented |
| `ncols_global` | Global total columns across all ranks | Implemented |
| `lat[ncols_local]` | Latitude of each column [degrees] | Hard-coded: 41.65 (Toledo OH) |
| `lon[ncols_local]` | Longitude of each column [degrees] | Hard-coded: -83.54 |
| `elev[ncols_local]` | Surface elevation [m] | Not implemented (commented out) |
| `surf_area[ncols_local]` | Surface cell area [m²] | Not implemented (commented out) |
| `pft[ncols_local]` | Plant functional type index | Hard-coded: 1 for all columns |
| `nlevgrnd` | Number of vertical cells per column | Implemented |
| `depth[nlevgrnd]` | Mid-point depth of each layer below surface [m] | Implemented from mesh geometry |

**Important notes:** Latitude, longitude, elevation, surface area, and PFT are
all hard-coded placeholders. These are known limitations documented in inline
comments `(elm_ats_driver.cc:292-319)`. A real ELM-ATS integration must map
ATS land-cover types to ELM PFT indices and read coordinates from the mesh.

`depth` is computed by walking down column 0's faces:
```cpp
double top_face_z = mesh_subsurf_->getFaceCentroid(
    mesh_subsurf_->columns.getFaces(0)[0])[2];   // (elm_ats_driver.cc:304)
for (int i = 0; i != ncells_per_col_; ++i) {
    double bottom_face_z = ...getFaceCentroid(getFaces(0)[i+1])[2];
    double dz = top_face_z - bottom_face_z;
    ldepth += dz / 2.;
    depth[i] = ldepth;
    ...
}
```

---

### `ats_set_soil_hydrologic_parameters`

**Declaration** `(elm_ats_api.h:75-80)`:
```c
void ats_set_soil_hydrologic_parameters(ELM_ATSDriver_ptr ats,
        double const * const base_porosity,
        double const * const hydraulic_conductivity,
        double const * const clapp_horn_b,
        double const * const clapp_horn_smpsat,
        double const * const clapp_horn_sr);
```

**C++ method** `(elm_ats_driver.cc:503-524)`:

All arrays have length `ncols_local * nlevgrnd` in Fortran column-major
layout: element `[j * ncols + i]` is column `i`, layer `j`.

| Input | ATS key | Notes |
|---|---|---|
| `base_porosity` | `base_poro_key_` | Written directly |
| `hydraulic_conductivity` | `perm_key_` | Converted: `K_sat [m/s] * (mu/rho/g) = perm [m²]`; factor = 8.9e-4 / (1000 * 9.80665) |
| `clapp_horn_b` | `ch_b_key_` | Clapp-Hornberger b exponent |
| `clapp_horn_smpsat` | `ch_smpsat_key_` | Matric potential at saturation |
| `clapp_horn_sr` | `ch_sr_key_` | Residual saturation |

Each field is marked as initialized in `State` after writing so the
`Coordinator::initialize()` consistency check passes.

---

### `ats_set_veg_parameters`

**Declaration** `(elm_ats_api.h:83-85)`:
```c
void ats_set_veg_parameters(ELM_ATSDriver_ptr ats,
        double const * const mafic_potential_full_turgor,
        double const * const mafic_potential_wilt_point);
```

**C++ method** `(elm_ats_driver.cc:527-532)`: Currently a no-op (`// pass for
now! FIXME --etc`). The turgor and wilt-point parameters are accepted but not
stored. This is a known gap — plant water stress thresholds are needed for
water-limited transpiration.

---

### `ats_initialize`

**Declaration** `(elm_ats_api.h:69-72)`:
```c
void ats_initialize(ELM_ATSDriver_ptr ats,
                    double const * const t,
                    double const * const patm,
                    double const * const soilp);
```

**C++ method** `ELM_ATSDriver::initialize` `(elm_ats_driver.cc:323-350)`:

Parameters — **the C header arg names do NOT match how the driver consumes them** (see ⚠):
- `t` — start time [s], scalar pointer
- `patm` (C header name) — **positionally consumed by the driver as `elm_water_content`**:
  initial ELM water content [kg m⁻²], array of length `ncols_local * nlevgrnd` in Fortran
  column-major layout. Passed to `init_pressure_from_wc_` (`elm_ats_driver.cc:335`).
- `soilp` (C header name; driver parameter `elm_pressure`) — **accepted but never used** by
  the current driver.

> ⚠ **Parameter-name mismatch (latent ATS bug).** The C header (`elm_ats_api.h:69-72`) names
> the 2nd/3rd args `patm`/`soilp`, and `elm_ats_driver.hh:71` names them `p_atm`/`pressure`,
> but the driver *definition* (`elm_ats_driver.cc:324`) names them `elm_water_content`/
> `elm_pressure` and uses them accordingly: the **2nd slot carries the water content** (used),
> the **3rd slot is unused**. Atmospheric pressure is **not read from any argument** — it is
> hardwired to 101325 Pa inside `init_pressure_from_wc_` (`elm_ats_driver.cc:359`). A coupling
> written to the header names would put water content in `soilp` (silently ignored) and
> atmospheric pressure in `patm` (misread as water content).

Execution:
1. Sets `t0_ = *t` on the `Coordinator`.
2. Calls `Coordinator::initialize()` which calls `pk_->Initialize()` and
   sets up all field evaluators.
3. Calls `init_pressure_from_wc_(elm_water_content)` — the C header's `patm` slot — to
   convert ELM water content to ATS pressure fields.
4. Calls `initZero_()` on all ELM flux fields (rooting fraction, potential
   sources, actual fluxes).
5. Writes initial visualization and checkpoint.

#### `init_pressure_from_wc_` `(elm_ats_driver.cc:354-424)`:

This is the most complex initialization step. It converts ELM's volumetric
water content (expressed as kg m⁻²) into ATS's native pressure state.

Algorithm per column per cell:
```
satl = elm_wc[j,i] / (dz * porosity * mass_density)
if satl < 1.0:
    pressure = p_atm - capillaryPressure(satl)   # unsaturated, WRM lookup
else:
    pressure = p_atm + rho * g * sat_depth        # hydrostatic, saturated zone
```

Where:
- `dz` = cell thickness from mesh geometry
- `mass_density` from the `subsurf_mass_dens` evaluator
- `capillaryPressure(satl)` from the WRM evaluator (obtained by
  `dynamic_cast<Flow::WRMEvaluator*>`)
- `sat_depth` = cumulative thickness of saturated cells above this cell

Only one WRM region is supported at this time
`(elm_ats_driver.cc:385)`.

After writing pressure, the method:
- Marks the pressure field as changed via `changedEvaluatorPrimary`
- Derives face values from cell values via `DeriveFaceValuesFromCellValues`
- Marks the field as initialized
- Updates saturation and water content evaluators

---

## Per-timestep functions {#per-timestep}

### `ats_set_soil_hydrologic_properties`

**Declaration** `(elm_ats_api.h:91-93)`:
```c
void ats_set_soil_hydrologic_properties(ELM_ATSDriver_ptr ats,
        double const * const effective_porosity);
```

**C++ method** `(elm_ats_driver.cc:535-539)`: Currently a no-op
(`// this isn't well defined -- pass for now --etc`). Effective porosity
(accounting for ice) is a time-varying quantity that would enable freeze-thaw
coupling.

---

### `ats_set_veg_properties`

**Declaration** `(elm_ats_api.h:95-97)`:
```c
void ats_set_veg_properties(ELM_ATSDriver_ptr ats,
        double const * const rooting_fraction);
```

**C++ method** `(elm_ats_driver.cc:543-546)`:

Copies `rooting_fraction[ncols * nlevgrnd]` (Fortran column-major) into the
ATS field `root_frac_key_` in subsurface cell order using `copyToSub_`.
Rooting fraction determines how transpiration demand is partitioned across
soil layers.

---

### `ats_set_sources`

**Declaration** `(elm_ats_api.h:101-104)`:
```c
void ats_set_sources(ELM_ATSDriver_ptr ats,
        double const * const surface_infiltration,
        double const * const surface_evaporation,
        double const * const subsurface_transpiration);
```

**Implementation** dispatches to `set_potential_sources`
`(elm_ats_api.cc:134-141)`.

**C++ method** `ELM_ATSDriver::set_potential_sources` `(elm_ats_driver.cc:549-583)`:

Input units (from ELM) are mm s⁻¹. ATS native units are mol m⁻² s⁻¹.

Conversion:
```
ATS_flux = ELM_flux_mm_s * 0.001 * surf_mol_density
```

Where `surf_mol_density` is updated from the evaluator immediately before
conversion `(elm_ats_driver.cc:570-572)`.

| Input | Array length | ATS field |
|---|---|---|
| `surface_infiltration` | `ncols_local` | `pot_infilt_key_` |
| `surface_evaporation` | `ncols_local` | `pot_evap_key_` |
| `subsurface_transpiration` | `ncols_local` | `pot_trans_key_` |

Note: the comment in `elm_ats_api.h` (line 100) says transpiration is
`ncells` long, but the implementation at `(elm_ats_driver.cc:566-568)` asserts
all three arrays have `MyLength() == ncolumns_`. The surface PK aggregates
column-level transpiration internally — this may change in future work.

After writing all three fields, each is marked changed via
`changedEvaluatorPrimary` so ATS evaluators downstream pick up the new values.

---

### `ats_advance`

**Declaration** `(elm_ats_api.h:41-44)`:
```c
void ats_advance(ELM_ATSDriver_ptr ats,
                 double const * const dt,
                 bool const * const checkpoint,
                 bool const * const visualize);
```

**C++ method** `ELM_ATSDriver::advance` `(elm_ats_driver.cc:428-477)`:

This is the core time-stepping call. ELM provides the target timestep `dt`;
ATS may sub-cycle internally.

**Sub-cycle loop:**
```
t_end = current_time + dt
while current_time < t_end and dt_subcycle > 0:
    S_->Assign("dt", dt_subcycle)
    S_->advance_time(NEXT, dt_subcycle)
    fail = Coordinator::advance()
    if fail:
        reset t_new = t_current
    else:
        t_current = t_next
        S_->advance_cycle()
        make observations
        visualize(do_vis)
        checkpoint(do_chkp)
    dt_subcycle = Coordinator::get_dt(fail)
```

ATS internally chooses its own sub-timestep via the PK's `get_dt()` method
and the `TimeStepManager`. The outer ELM timestep bounds the total subcycled
interval.

**Failure handling:** If the final step fails after all sub-cycles, ATS:
1. Forces a visualization dump for debugging.
2. Flushes observations.
3. Writes a `post_mortem` checkpoint.
4. Throws `Errors::Message("ELM_ATSDriver: advance(dt) failed.")`
   `(elm_ats_driver.cc:474)`.

The `checkpoint` and `visualize` bool flags allow ELM to request output at
specific timesteps independently of ATS's own output schedule
`(elm_ats_driver.cc:455-456)`.

---

### `ats_advance_test`

**Declaration** `(elm_ats_api.h:47)`:
```c
void ats_advance_test(ELM_ATSDriver_ptr ats);
```

**C++ method** `(elm_ats_driver.cc:482-490)`:

Runs a complete time loop from the current time to `t1_` using ATS's own
timestep recommendations. Used for testing without an ELM driver:

```cpp
while (S_->get_time() < t1_) {
  double dt = Coordinator::get_dt(false);
  advance(dt, false, false);
}
```

---

## Post-timestep functions {#post-timestep}

### `ats_get_waterstate`

**Declaration** `(elm_ats_api.h:113-119)`:
```c
void ats_get_waterstate(ELM_ATSDriver_ptr ats,
                        double * const surface_ponded_depth,
                        double * const water_table_depth,
                        double * const soil_pressure,
                        double * const soil_psi,
                        double * const sat_liq,
                        double * const sat_ice);
```

**C++ method** `ELM_ATSDriver::get_waterstate` `(elm_ats_driver.cc:588-651)`:

| Output | Array size | Units | How computed |
|---|---|---|---|
| `surface_ponded_depth` | `ncols_local` | mm | ATS ponded depth [m] × 1000 |
| `water_table_depth` | `ncols_local` | [ATS native] | `copyFromSurf_` of `wtd_key_` |
| `soil_pressure` | — | — | Not implemented (commented out block) |
| `soil_psi` | — | — | Not implemented (commented out block) |
| `sat_liq` | `ncols_local * nlevgrnd` | kg m⁻² | saturation × porosity × mass_density × dz |
| `sat_ice` | — | — | Not implemented (argument accepted but not written) |

**sat_liq conversion** `(elm_ats_driver.cc:609-617)`:
```cpp
for each column i, layer j:
    dz = face[j].z - face[j+1].z
    sat_liq[j * ncols + i] = satl[cell] * por[cell] * dens[cell] * dz
```

This converts ATS's dimensionless liquid saturation (0 to 1) to the ELM
convention of kg m⁻² (liquid water equivalent per unit area).

**Partially implemented:** `soil_pressure` (ATS Pa → ELM units) and
`soil_psi` (ATS capillary pressure Pa → mm H₂O) are computed in a commented-
out block `(elm_ats_driver.cc:633-650)`. The code shows the intended
conversion but is not active.

**sat_ice** is accepted as an argument but never written. ATS's thermal
energy module would supply ice saturation when enabled.

---

### `ats_get_water_fluxes`

**Declaration** `(elm_ats_api.h:121-126)`:
```c
void ats_get_water_fluxes(ELM_ATSDriver_ptr ats,
                          double * const soil_infiltration,
                          double * const evaporation,
                          double * const transpiration,
                          double * net_subsurface_fluxes,
                          double * net_runon);
```

**C++ method** `ELM_ATSDriver::get_water_fluxes` `(elm_ats_driver.cc:654-712)`:

| Output | Array size | Units | How computed |
|---|---|---|---|
| `soil_infiltration` | `ncols_local` | mm s⁻¹ | infilt [mol m⁻² s⁻¹] / surf_mol_dens × 1000 |
| `evaporation` | `ncols_local` | mm s⁻¹ | evap [mol m⁻² s⁻¹] / surf_mol_dens × 1000 |
| `transpiration` | `ncols_local * nlevgrnd` | mm s⁻¹ | trans [mol m⁻³ s⁻¹] × dz / subsurf_mol_dens × 1000 |
| `net_subsurface_fluxes` | — | — | Not implemented (acknowledged in comment) |
| `net_runon` | — | — | Not implemented (acknowledged in comment) |

**Surface flux conversion** `(elm_ats_driver.cc:681-686)`:
```cpp
double mm_per_mol = 1000.0 / surfdens[0][i];
surf_subsurf_flx[i] = infilt[0][i] * mm_per_mol;
evaporation[i] = evap[0][i] * mm_per_mol;
```

**Transpiration conversion** `(elm_ats_driver.cc:700-709)`:
ATS stores transpiration as a volumetric sink [mol m⁻³ s⁻¹]. ELM expects
[mm s⁻¹] per layer. Conversion multiplies by layer thickness and divides
by molar density:
```cpp
factor = dz * 1000.0 / subsurfdens[cell]
transpiration[j * ncols + i] = trans[cell] * factor
```

---

## Data structures at the interface

### Array layout: Fortran column-major

All 2D arrays (per-column, per-layer) use Fortran column-major ordering:
element `[layer * ncols + col]` is the value at layer `layer`, column `col`.
This is the native layout for ELM (Fortran) arrays. ATS internally uses
cell-based indexing; the `copyToSub_` and `copyFromSub_` helper methods
handle the conversion `(elm_ats_driver.cc:743-787)`.

### `copyToSub_` `(elm_ats_driver.cc:743-758)`:
```cpp
for col i in [0, ncolumns_):
    cells = mesh_subsurf_->columns.getCells(i)
    for layer j in [0, ncells_per_col_):
        vec[cells[j]] = in[j * ncolumns_ + i]
```

### `copyFromSub_` `(elm_ats_driver.cc:775-787)`:
Reverse of `copyToSub_`: reads ATS cell ordering and writes Fortran
column-major.

### `copyToSurf_` / `copyFromSurf_` `(elm_ats_driver.cc:724-768)`:
Simpler variants for surface (1D) arrays where `vec[i] = in[i]` directly.

---

## Private member fields

`ELM_ATSDriver` stores the following key private members
`(elm_ats_driver.hh:109-152)`:

| Member | Type | Meaning |
|---|---|---|
| `ncolumns_` | `int` | Local (per-rank) number of surface columns |
| `ncells_per_col_` | `int` | Number of vertical cells per column |
| `npfts_` | `int` | Number of PFTs (default 17, passed to factory) |
| `domain_subsurf_` | `Key` | Name of subsurface domain (usually `"domain"`) |
| `domain_surf_` | `Key` | Name of surface domain (usually `"surface"`) |
| `mesh_subsurf_` | `RCP<const Mesh>` | Subsurface mesh |
| `mesh_surf_` | `RCP<const Mesh>` | Surface mesh |
| `*_key_` | `Key` (many) | State field keys for all coupling variables |

All `Key` variables are resolved in the constructor from the input deck using
`Keys::readKey(*plist_, domain, "human name", "default_key_name")`. This
allows the user to override field names in the XML input if needed.

---

## `Indexer.hh` — array index utilities

`(src/executables/elm_ats_api/Indexer.hh)`

Provides three template specializations for indexing 1D or 2D arrays in
different layouts:

| `Indexer_kind` | Surface get | Subsurface get |
|---|---|---|
| `SCALAR` | returns `*val_` | returns `*val_` |
| `ELM` | `val[i]` | `val[col * ncells_per_col_ + cic]` |
| `ATS` | `val[i]` | `val[mesh.cells_of_column(col)[cic]]` |

These templates are defined but not used in the current `ELM_ATSDriver`
implementation. They appear intended as building blocks for future generic
copy utilities that could replace the hand-written `copyToSub_`/`copyFromSub_`
methods.

---

## Fortran interface {#fortran-interface}

### `ats.f90` — interface declarations `(test/fortran/ats.f90)`

Declares the C-interoperable Fortran interface block that maps to the C API.
Each C function is bound by name:

| Fortran name | C binding | Notes |
|---|---|---|
| `ats_create_c` | `"ats_create"` | Returns `type(c_ptr)` |
| `ats_delete_c` | `"ats_delete"` | |
| `ats_setup_c` | `"ats_setup"` | |
| `ats_initialize_c` | `"ats_initialize"` | Note: no `t`, `patm`, `soilp` args here |
| `ats_advance_test_c` | `"ats_advance_test"` | |
| `ats_advance_c` | `"ats_advance"` | Only `dt` (no `checkpoint`/`visualize`) |
| `ats_set_sources_c` | `"ats_set_sources"` | Includes `ncols`, `ncells` size args |
| `ats_get_waterstate_c` | `"ats_get_waterstate"` | Includes `ncols`, `ncells` size args |
| `ats_get_mesh_info_c` | `"ats_get_mesh_info"` | Different argument order than C header |

**Important divergence:** The Fortran interface in `ats.f90` does not match
the current C header exactly. Specifically:
- `ats_initialize_c` takes no arguments — but the C API `ats_initialize` takes
  `t`, `patm`, `soilp`.
- `ats_set_sources_c` and `ats_get_waterstate_c` include extra `ncols` and
  `ncells` size arguments not present in the current C header.
- `ats_advance_c` takes only `dt` — the C header takes `dt`, `checkpoint`,
  `visualize`.
- `ats_get_mesh_info_c` has a different argument order and does not include
  `pft`.

The Fortran interface is from an older version of the API and has not been
updated to match the current C header. It should be treated as a reference
for the binding pattern, not as a production-ready interface.

### `ats_mod.f90` — Fortran `libats` module `(test/fortran/ats_mod.f90)`

Wraps the C interface in a Fortran derived type:

```fortran
module libats
  type ats
    private
    type(c_ptr) :: ptr
  contains
    final :: ats_delete
    procedure :: setup => ats_setup
    procedure :: initialize => ats_initialize
    procedure :: advance => ats_advance
    procedure :: advance_test => ats_advance_test
    procedure :: set_sources => ats_set_sources
    procedure :: get_waterstate => ats_get_waterstate
    procedure :: get_mesh_info => ats_get_mesh_info
  end type

  interface ats
    procedure ats_create  ! constructor
  end interface
```

The `final` destructor calls `ats_delete_c` automatically when the `ats`
object goes out of scope in Fortran.

The `ats_create` function handles the Fortran string-to-C-string conversion
(null-termination) `(ats_mod.f90:40-51)`:
```fortran
do i = 1, n_char
    c_str_infile(i) = infile(i:i)
end do
c_str_infile(n_char + 1) = C_NULL_CHAR
ats_create%ptr = ats_create_c(comm, c_str_infile)
```

---

## Build configuration

The `elm_ats_api` subdirectory is built only when `ENABLE_ELM_ATS_API` is
set in CMake `(src/executables/CMakeLists.txt:189-192)`:

```cmake
if (ENABLE_ELM_ATS_API)
  message("building elm_ats api")
  add_subdirectory(elm_ats_api)
endif()
```

The `elm_ats_api/CMakeLists.txt` `(elm_ats_api/CMakeLists.txt:1-47)` builds a
shared library named `elm_ats` that includes:
- `coordinator.cc`
- `ats_mesh_factory.cc`
- `elm_ats_driver.cc`
- `elm_ats_api.cc`

The test subdirectory (`elm_ats_api/test/`) is commented out
(`##add_subdirectory(test)`) and not built by default.

Fortran compatibility is verified at configure time via
`FortranCInterface_VERIFY(CXX)`.

---

## Memory ownership and lifetime

| Object | Allocated by | Freed by |
|---|---|---|
| `ELM_ATSDriver*` | `ats_create` via `new` | `ats_delete` via `delete` |
| `State`, `PK`, meshes | `Coordinator` constructor via Teuchos RCP | Destroyed when `ELM_ATSDriver` is deleted |
| ELM-side arrays (`lat`, `lon`, `depth`, etc.) | ELM / caller | Caller |
| Kokkos runtime | `ats_create` (if not pre-initialized) | `ats_delete` |

The `ELM_ATSDriver` object must outlive all data it returns (e.g., mesh
dimensions from `get_mesh_info` are stable as long as the driver exists).

---

## Known gaps and limitations

These are documented in the source code and are relevant to ECRP AI/ML
integration planning:

1. **Lat/lon/elev/PFT hard-coded** `(elm_ats_driver.cc:299,316-319)`: Real
   spatial coordinates and vegetation types must be mapped from the mesh.

2. **Only one WRM supported** `(elm_ats_driver.cc:385)`: The pressure
   initialization code asserts `wrms_->second.size() == 1`. Multi-region or
   heterogeneous WRM is not supported at initialization.

3. **Effective porosity no-op** `(elm_ats_driver.cc:537)`: Freeze-thaw
   coupling requires time-varying effective porosity (ice fraction reduces
   pore space). This is the main gap for permafrost coupling.

4. **Veg parameters no-op** `(elm_ats_driver.cc:531)`: Mafic potential
   thresholds for plant water stress are accepted but unused.

5. **net_subsurface_fluxes and net_runon not implemented**
   `(elm_ats_driver.cc:711)`: These would capture lateral subsurface flow and
   surface runon between columns.

6. **soil_pressure and soil_psi commented out** `(elm_ats_driver.cc:633-650)`:
   The conversion code exists but is inactive; ELM currently receives zeros
   for these fields.

7. **Fortran interface outdated** `(test/fortran/ats.f90)`: Argument lists
   diverge from the current C header.

---

## ECRP AI/ML emulator insertion point

The ELM-ATS coupling API defines the complete data contract for the proposed
AI/ML emulator in the ECRP proposal. An emulator targeting this boundary
would:

1. Receive the same ELM inputs: soil parameters (porosity, Ksat,
   Clapp-Hornberger coefficients), vegetation state (rooting fraction), and
   per-timestep forcing (infiltration, evaporation, transpiration rates).
2. Replace (or augment) the `ats_advance` call by running a learned surrogate
   of ATS's Richards equation + overland flow solver.
3. Return the same ATS outputs: liquid saturation (as kg m⁻²), ponded depth
   (mm), water table depth, actual infiltration, evaporation, and transpiration
   fluxes in ELM units.

The physical emulation domain is per-column (each column is independent in
the current coupling — lateral flow between columns is not exchanged). An
emulator for `n` columns and `k` layers per column must handle an input
feature vector of size roughly `5k + 3` (soil params per layer, three surface
fluxes) and an output vector of size `k + 2` (saturation per layer, ponded
depth, water table depth).
