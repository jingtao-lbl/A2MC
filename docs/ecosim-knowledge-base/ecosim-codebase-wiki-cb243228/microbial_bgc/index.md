---
**Source pin:** EcoSIM commit `cb243228` (jingtao-lbl/EcoSIM `fix/r2-plant-balance`; upstream `09eb674a` + 2 fix commits) · patched to `0340d71b` (see the wiki `index.md`, Patches applied)
**Scope:** `f90src/Microbial_bgc/{Box_Micmodel,Layers_Micmodel}/`, `f90src/Modelpars/{NitroPars,MicBGCPars,MicrobeConfigMod}.F90`, `f90src/APIs/MicBGCAPI.F90`
**Last verified:** 2026-10-15
---

# Microbial Biogeochemistry Subsystem

EcoSIM's soil biogeochemistry is microbially explicit: living heterotroph and autotroph biomass are prognostic state variables in every soil layer and in the surface litter layer, and the decomposition, mineralization and gas-production rates are proportional to that biomass. There is no first-order decay term that acts without microbes. This page is the map of the subsystem; the rate laws are on [`decomposition_and_som.md`](decomposition_and_som.md) and the path from decomposition to plant nutrition is on [`soil_plant_nutrient_coupling.md`](soil_plant_nutrient_coupling.md).

## What changed since the `2dea74d9` wiki

- The per-guild catabolism routines left `MicBGCFGMod.F90` and now live in eight modules (table below); `MicBGCFGMod.F90` is 3,435 lines and keeps the layer driver, hydrolysis, sorption, mineralization, respiration bookkeeping and mortality.
- An eighth heterotroph group, mixotrophic cyanobacteria, was added (`f90src/Modelpars/MicBGCPars.F90:199`), with PAR attenuation through litter and soil (`f90src/APIs/MicBGCAPI.F90:133-146`).
- `SPOSC` became an optional MicrobePars input (`f90src/Modelpars/NitroPars.F90:363-364`).
- Microbial mortality is clamped to the standing pool (`f90src/Microbial_bgc/Box_Micmodel/MicBGCFGMod.F90:3345`), so the "unclamped mortality" hazard of the prior wiki no longer applies.

## Source files

### `f90src/Microbial_bgc/Box_Micmodel/` (one layer at a time)

| File | Lines | Role |
|---|---|---|
| `MicBGCFGMod.F90` (module `MicBGCMod`) | 3,435 | Layer driver `SoilBGCOneLayer`; environment staging; heterotroph dispatch; chemodenitrification; priming; DOM sorption; solid-OM, necromass and sorbed-OM hydrolysis; redistribution of products; anabolic update; litter colonization; aggregation into layer fluxes; heterotroph mineralization/immobilization; respiration partition; mortality and recycling |
| `MicAutoCplxFGMod.F90` | 1,449 | Autotroph dispatch (`ActiveAutotrophs`), substrate competition, O2 uptake, nutrient mineralization (`BiomNutMinerMobilAutor`), respiration, anabolic flux and update |
| `MicrobMathFuncMod.F90` | 594 | Shared kinetics: `MicrobPhysTempFun`, `TranspBasedsubstrateUptake`, `AerobicHeterO2Uptake`, `StageFuncGuild`, `StageAutotroph`, `CalcRespMaintHeter`, `CalcRespMaintAutor`, `LimitReserveNutrientTransfers`, `LitterSoilNutrientUptake`, `ReserveDenitrifMaintenance` |
| `AerobicBacteriaMod.F90` | 217 | `AerobicHeteroBactCatabolism` (aerobic heterotrophs, facultative denitrifiers in aerobic mode, aerobic N2 fixers) |
| `FungiMod.F90` | 174 | `AerobicFungiCatabolism` |
| `FermenterMod.F90` | 165 | `AcetogFermentCatabolism` (fermenters and anaerobic N2 fixers) |
| `DenitrifierMod.F90` | 370 | `HeteroDenitrificCatabolism` |
| `MethanogenMod.F90` | 275 | `AcetoMethanogenCatabolism`, `H2MethanogensCatabolism` |
| `MethanotrophMod.F90` | 524 | `AeroMethanotrophCatabolism`, `AMONC10Catabolism`, `AMOANME2dCatabolism` |
| `NitrifierMod.F90` | 563 | `AmmoniaOxiDenitCatabolism`, `AmmoniaOxidizerCatabolism`, `NitriteOxidizerCatabolism` |
| `CyanoBacteriaMod.F90` | 264 | `CyanoBacteriaCatabolism`, `fPAR_func` |
| `MicStateTraitTypeMod.F90`, `MicFluxTypeMod.F90`, `MicForcTypeMod.F90`, `MicrobeDiagTypes.F90` | 157 / 493 / 180 / 1,004 | The `micstt` / `micflx` / `micfor` transfer types and the per-guild/per-complex scratch types |

### `f90src/Microbial_bgc/Layers_Micmodel/` (column level)

| File | Lines | Role |
|---|---|---|
| `SoilBGCNLayMod.F90` | 229 | `DownwardMixOM` (litter mixing driven by `FOSCZ0`, `FOSCZL` and heterotroph activity, `f90src/Microbial_bgc/Layers_Micmodel/SoilBGCNLayMod.F90:95`, `:122`) and `ApplyVerticalMix` |
| `InitSOMBGCMod.F90` | 873 | Initial SOC partition and microbial seeding (`InitSOMVars`, `f90src/Microbial_bgc/Layers_Micmodel/InitSOMBGCMod.F90:68`), cyanobacteria inoculation (`:438`), litterfall colonization (`MicrobeByLitterFall`, `:799`) |
| `SoilPARAttenuationMod.F90` | 139 | `CalcKSoilPAR` (soil PAR extinction for the cyanobacteria guild, `f90src/Microbial_bgc/Layers_Micmodel/SoilPARAttenuationMod.F90:11`) |

### Parameters and configuration

| File | Role |
|---|---|
| `f90src/Modelpars/NitroPars.F90` | Scalar microbial constants. `initNitroPars` (`:139-266`) sets the compiled fallbacks; `ReadPars` (`:269-370`) reads the MicrobePars NetCDF |
| `f90src/Modelpars/MicBGCPars.F90` | `MicParType`: group IDs, complexes, kinetic components, `SPOSC`, `rNCOMC`/`rPCOMC`, `FL`, `DOSA`, `CNRH`/`CPRH` (`SetPars`, `:265-415`) |
| `f90src/Modelpars/MicrobeConfigMod.F90` | Namelist `&Microbes` with guild counts per functional group (`ReadMicrobeNamelist`, `f90src/Modelpars/MicrobeConfigMod.F90:17-41`) |

## Entry point and call order

The time stepper calls `MicrobeModel` (`f90src/APIs/MicBGCAPI.F90:84-176`). For each column it loops `L = 0 .. NL` and, where the layer has micropore volume, calls `MicBGC1Layer` for the litter layer (`L = 0`) and for every soil layer from the top active layer down (`IF(L.EQ.0 .OR. L.GE.NU_col(NY,NX))`, `f90src/APIs/MicBGCAPI.F90:120-125`); layers it skips get zeroed gas and nutrient exchange (`:148-158`). After the layer loop it mixes litter downward (`:162-165`) and applies disturbance SOM removal (`:169`). `MicBGC1Layer` packs state with `MicAPISend`, calls `SoilBGCOneLayer` and unpacks with `MicAPIRecv` (`f90src/APIs/MicBGCAPI.F90:189-193`).

```
MicrobeModel (MicBGCAPI.F90:84)
  -> MicBGC1Layer -> MicAPISend / SoilBGCOneLayer / MicAPIRecv
SoilBGCOneLayer (MicBGCFGMod.F90:74-160)
  StageBGCEnvironCondition (:110)      temperature, water, pools, N/P status, DOC concentrations
  ActiveMicrobeCatabolism (:115)       per complex K, per group N:
     GetMicrobDensFactorHeter            SPOMK, RMOMK (biomass-density scalars)
     ActiveHeterotrophsK -> {AerobicFungiCatabolism | CyanoBacteriaCatabolism | AerobicHeteroBactCatabolism
                             [+ HeteroDenitrificCatabolism] | AcetogFermentCatabolism | AcetoMethanogenCatabolism}
        then per guild: SubstrateAttenf4Compet, BiomassMineralization,
                        GatherHeterotrophRespiration, GatherHetertrophAnabolicFlux
     ActiveAutotrophs (MicAutoCplxFGMod.F90:33) for the 6 autotroph groups
  ChemoDenitrification (:119)
  OMTransferForPriming (:123)
  SolidOMDecomposition (:134)          SOM, necromass and sorbed-OM hydrolysis
  RedistDecompProduct (:136)           products into DOM; microbial uptake debited
  RDOMSorption (:138)
  AutotrophAnabolicUpdate (:140), HeterotrophAnabolicUpdate (:142)
  MicrobialLitterColonization (:144)
  AggregateTransfOMBioResdue (:148)    layer CO2, CH4, N2O and mineral N/P exchange
```

The dispatch in `ActiveHeterotrophsK` (`f90src/Microbial_bgc/Box_Micmodel/MicBGCFGMod.F90:876-903`) routes aerobic groups to fungi, cyanobacteria or bacteria catabolism, adds denitrification for facultative denitrifiers outside the litter layer (`:890-893`), sends the two anaerobic groups to fermentation (`:895-898`) and acetoclastic methanogens to `AcetoMethanogenCatabolism` (`:900-902`).

## Microbial functional groups

Group identifiers are set in `MicParType%Init` (`f90src/Modelpars/MicBGCPars.F90:192-207`). There are `NumMicbHFunGrupsPerCmplx = 8` heterotroph groups per organic-matter complex and `NumMicbAFunGrupsPerCmplx = 6` autotroph groups per layer (`f90src/Modelconfig/EcoSIMConfig.F90:24-25`). Each group holds `NumGuild_*` guilds (default 1, `f90src/Modelpars/MicBGCPars.F90:14-27`), which the `&Microbes` namelist can change for eleven of the groups (`f90src/Modelpars/MicrobeConfigMod.F90:17-22`).

Heterotrophs (one set per complex K):

| ID | Symbol | Name | Catabolism routine | Specific rate constant |
|---|---|---|---|---|
| 1 | `mid_HeterAerobBacter` | aerohetrob | `AerobicHeteroBactCatabolism` | `VMXO` (`f90src/Microbial_bgc/Box_Micmodel/AerobicBacteriaMod.F90:160`) |
| 2 | `mid_Facult_DenitBacter` | faculdenit | aerobic bacteria + `HeteroDenitrificCatabolism` | `VMXO`; denitrification rates in `f90src/Microbial_bgc/Box_Micmodel/DenitrifierMod.F90:192` |
| 3 | `mid_Aerob_Fungi` | aerofungi | `AerobicFungiCatabolism` | `VMXO` (`f90src/Microbial_bgc/Box_Micmodel/FungiMod.F90:120`), NOT `VMXF` |
| 4 | `mid_fermentor` | aneroferm | `AcetogFermentCatabolism` | `VMXF` (`f90src/Microbial_bgc/Box_Micmodel/FermenterMod.F90:137`) |
| 5 | `mid_HeterAcetoCH4GenArchea` | acetmethg | `AcetoMethanogenCatabolism` | `VMXCH4gAcet` (`f90src/Microbial_bgc/Box_Micmodel/MethanogenMod.F90:116`) |
| 6 | `mid_HeterAerobN2Fixer` | aeron2fix | `AerobicHeteroBactCatabolism` | `VMXO` |
| 7 | `mid_HeterAnaerobN2Fixer` | aneron2fix | `AcetogFermentCatabolism` | `VMXF` |
| 8 | `mid_HeterMixtCynoBacter` | mixocyanob | `CyanoBacteriaCatabolism` | `VMXO` (`f90src/Microbial_bgc/Box_Micmodel/CyanoBacteriaMod.F90:173`) |

Flags: `is_aerobic_hetr` for groups 1, 2, 3, 6, 8 and `is_anaerobic_hetr` for groups 4, 7 (`f90src/Modelpars/MicBGCPars.F90:229-235`).

Autotrophs (one set per layer):

| ID | Symbol | Name | Rate constant (use site) |
|---|---|---|---|
| 1 | `mid_AutoAmmoniaOxidBacter` | amoniaoxib | `VMXNH3Oxi` (`f90src/Microbial_bgc/Box_Micmodel/NitrifierMod.F90:366`) |
| 2 | `mid_AutoNitriteOxidBacter` | nititeoxib | `VMXNO2Oxi` (`f90src/Microbial_bgc/Box_Micmodel/NitrifierMod.F90:525`) |
| 3 | `mid_AutoAeroCH4OxiBacter` | aeromethtp | `VMXCH4OxiAero` (`f90src/Microbial_bgc/Box_Micmodel/MethanotrophMod.F90:130`) |
| 4 | `mid_AutoAMOANME2D` | anme2d | `VMX3AMO2D` (`f90src/Microbial_bgc/Box_Micmodel/MethanotrophMod.F90:468`) |
| 5 | `mid_AutoH2GenoCH4GenArchea` | hydromethg | `VMXCH4gH2` (`f90src/Microbial_bgc/Box_Micmodel/MethanogenMod.F90:236`) |
| 6 | `mid_AutoAMONC10` | anmenc10 | `VMX2AMONC10` (`f90src/Microbial_bgc/Box_Micmodel/MethanotrophMod.F90:326`) |

`is_CO2_autotroph` marks groups 1, 2, 5 and 6, the ones whose biomass C comes from CO2 (`f90src/Modelpars/MicBGCPars.F90:257-260`).

## Organic-matter pool structure

Five organo-microbial complexes K (`jcplxc = 5`, `f90src/Modelconfig/EcoSIMConfig.F90:22`), defined in `f90src/Modelpars/MicBGCPars.F90:143-167`:

| K | Symbol | Name | Litter? |
|---|---|---|---|
| 1 | `k_woody_comp` | woodylitr | yes |
| 2 | `k_fine_comp` | folialitr | yes (`is_finelitter`) |
| 3 | `k_manure` | manure | yes |
| 4 | `k_POM` | pom | no |
| 5 | `k_humus` | humus | no |

`NumOfLitrCmplxs = k_manure = 3` (`:155`). The surface litter layer computes only the three litter complexes (`KL = NumOfLitrCmplxs`, `f90src/Microbial_bgc/Box_Micmodel/MicBGCFGMod.F90:387`); soil layers compute all five (`:399`).

Each complex holds `jskenc = 4` kinetic components M of solid OM (protein, carbohydrate, cellulose, lignin; `f90src/Modelpars/MicBGCPars.F90:150-162`), stored as `SolidOM(NE,M,K)` for C, N and P with a colonized C fraction `SolidOMAct(M,K)` that is the only part hydrolysis acts on (`f90src/Microbial_bgc/Box_Micmodel/MicBGCFGMod.F90:1361`). The other pools per complex are microbial residue `OMBioResdu(NE,1:2,K)` (kinetic, recalcitrant; `NumDeadMicrbCompts = 2`), sorbed OM `SorbedOM(idom,K)`, dissolved OM `DOM(idom,K)` for DOC, DON, DOP and acetate, and live heterotroph biomass `mBiomeHeter(NE,MID,K)` with three compartments per guild (kinetic, structural, reserve; `iLbiom_kinetic = 1`, `iLbiom_struct = 2`, `iLbiom_reserve = 3`, `f90src/Modelconfig/ElmIDMod.F90:13-15`). Autotroph biomass `mBiomeAutor(NE,MID)` is per layer.

The active biomass that drives every rate is `OMActHeter = mBiomeHeter(ielmc, kinetic)/FL(kinetic)` with `FL = (0.55, 0.45)` (`f90src/Microbial_bgc/Box_Micmodel/MicBGCFGMod.F90:502`; `f90src/Modelpars/MicBGCPars.F90:348`).

## Pool transitions at a glance

- Colonization: `SolidOMAct(M,K)` grows at `DOSA(K)*ROQC4HeterMicActCmpK(K)` distributed by component share, capped by `SolidOM` (`f90src/Microbial_bgc/Box_Micmodel/MicBGCFGMod.F90:1961-1964`); `DOSA = (0.25E-03, 0.25, 0.25, 0.25, 0.25)` (`f90src/Modelpars/MicBGCPars.F90:332`).
- Hydrolysis: colonized solid OM, microbial residue and sorbed OM go to DOM at rates scaled by the microbial activity proxy (`SolidOMDecomposition`, `:1227-1519`). In litter complexes part of the hydrolysed C, N and P is humified to POM (`:1389-1407`).
- Uptake: guilds take up DOC, acetate, DON and DOP (`GatherHetertrophAnabolicFlux`, `:3257-3269`; debited from DOM in `RedistDecompProduct`, `:1686-1692`).
- Mineral exchange: the reserve compartment immobilizes or releases NH4, NO3 and phosphate (`BiomassMineralization`, `:2544-2976`); see `soil_plant_nutrient_coupling.md`.
- Growth: reserve to kinetic and structural biomass at `OMGR` (`:3292-3304`).
- Death: live biomass dies at `SPOMC`; a fraction is recycled to the reserve and the rest goes to microbial residue or humus (`:3318-3363`).
- Sorption: DOM exchanges with sorbed OM toward a partition equilibrium (`RDOMSorption`, `:1137-1224`).
- Priming: activity, DOM and biomass are exchanged between complexes (`OMTransferForPriming`, `:1015-1134`).
- Litter mixing: `DownwardMixOM` moves litter-layer OM into the soil (`f90src/Microbial_bgc/Layers_Micmodel/SoilBGCNLayMod.F90:55`).

## The MicrobePars file: what is read, and what is not

`ReadPars` returns false and the compiled fallbacks apply only when `micpar_file_in` is empty (`f90src/Modelpars/NitroPars.F90:280`, fallbacks `:168-249`). With a file, every name in `ReadPars` is a bare `ncd_getvar` and a missing variable aborts, except `SPOSC`, which is guarded by `check_var` and read only if present (`:363-364`). Facts verified at cb243228 against the shipped `input_data/MicrobePars.20260211.nc`:

- The file and the compiled fallbacks agree on every shared value except `SPOMC`: the file has `[0.01, 0.01]`, the code `(/1.0E-02, 0.1E-02/)` (`f90src/Modelpars/NitroPars.F90:248`). Wiring the shipped file therefore makes structural-biomass mortality ten times faster than a run with no file.
- `SPOSC` is absent from MicrobePars.20260211.nc, so the default `SPOSC_in` (`f90src/Modelpars/NitroPars.F90:162-166`) applies. The older 20251009 and 20251015 files carry a `SPOSC(jsken,jcplx)` whose flat order equals that default.
- `EAMO10`, `EAMO2D`, `GC2HX` and `GN3CX` are assigned only in the fallback branch (`f90src/Modelpars/NitroPars.F90:217-218`, `:238`, `:240`) and are not read by `ReadPars`, so with any MicrobePars file they keep their uninitialized module value. `GN3CX` is used by `AMOANME2dCatabolism` (`f90src/Microbial_bgc/Box_Micmodel/MethanotrophMod.F90:496`) and in `EN2D` (`f90src/Modelpars/NitroPars.F90:261`).
- `H2KI` and `OAKI` are set unconditionally before the read (`f90src/Modelpars/NitroPars.F90:146-147`) and `ReadPars` never reads them, so the `H2KI` variable that MicrobePars.20260211.nc carries is a silent no-op.
- The derived efficiencies (`EO2X`, `EO2G`, `EO2D`, `ENFX`, `EN2X`, ...) are computed after the read (`f90src/Modelpars/NitroPars.F90:251-264`), so they always follow the file values of `GO2X`, `EOMC`, `EOMG`, `GN2X` and the rest.

Boot order: `initNitro1Layer` calls `initNitroPars` (`f90src/Microbial_bgc/Box_Micmodel/MicBGCFGMod.F90:68`) before `MicParType%SetPars` copies `SPOSC_in` into `micpar%SPOSC` and multiplies the litter complexes by 1.5 (`f90src/Modelpars/MicBGCPars.F90:344-346`).

## Where to go next

- [`decomposition_and_som.md`](decomposition_and_som.md): rate laws, environment scalars, respiration partition, mortality and recycling, sorption, the producing chains of `ECO_RH_col` and `CO2_SEMIS_FLX_col`, numerical hazards, and the calibration-parameter source map.
- [`soil_plant_nutrient_coupling.md`](soil_plant_nutrient_coupling.md): microbial N/P mineralization and immobilization, the soil NH4/NO3/H2PO4 pools and their history outputs, microbe-root competition, root uptake, and the path to leaf protein and Rubisco.
- `f90src/APIs/MicBGCAPI.F90` is the only coupling surface between this subsystem and the rest of the model (`MicAPISend` `:198-486`, `MicAPIRecv` `:491-687`).
