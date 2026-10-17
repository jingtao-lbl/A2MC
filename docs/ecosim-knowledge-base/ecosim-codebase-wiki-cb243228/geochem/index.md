---
**Source pin:** EcoSIM commit `cb243228` (jingtao-lbl/EcoSIM `fix/r2-plant-balance`; upstream `09eb674a` + 2 fix commits) · patched to `0340d71b` (see the wiki `index.md`, Patches applied)
**Scope:** `f90src/Geochem/` (`Box_chem/`, `Layers_chem/`), `f90src/APIs/GeochemAPI.F90`, `f90src/Modelpars/SoluteParMod.F90`, and the soil-chemistry initialisation in `f90src/Ecosim_mods/StarteMod.F90`
**Last verified:** 2026-10-15
---

# Geochemistry: Overview

The geochemistry code computes, for every soil layer each hour, the abiotic reactions among dissolved, exchangeable and precipitated N and P (and, in salt mode, Al, Fe, Ca, Mg, Na, K, SO4, Cl and the carbonate system). It also applies fertilizer dissolution, urea hydrolysis and the growth of fertilizer bands. It returns reaction fluxes that `REDIST` adds to the soil pools. Every source file in `f90src/Geochem/` is byte-identical between 2dea74d9 and cb243228, apart from two `PrintInfo` calls added to `UpdateSurfResidueSolute`.

Three facts matter most for calibration:

1. **pH is prescribed, never computed.** Both solvers take [H+] from the grid-file pH of the layer (section 4).
2. **Phosphate sorption is a ligand exchange on finite surface sites**, relaxed toward mass-action equilibrium at a fixed hourly rate. There is no Langmuir Qmax or affinity parameter, and every constant is a compile-time `PARAMETER` (`equilibria_and_sorption.md`).
3. **On a non-restart run at cb243228 the soil chemical initial state is never written.** The surface sites, sorbed P, and the grid file's inorganic P and mineral pools stay at zero, and CEC and AEC exist only in soil layer 1. P sorption is therefore inert, and the grid-file P inputs have no effect (section 5, run-verified).

## 1. When the geochemistry runs

`soluteModel` is called from the hourly orchestrator only when `soichem_model` is true (`drivers/ecosim/EcoSIMAPI.F90:80-84`). `soichem_model` defaults to `.true.` (`:212`). It is forced off in prescribed-phenology mode (`:310`) and under ATS (`f90src/ATSUtils/ATSEcoSIMInitMod.F90:59`). `salt_model` selects the full solver; it is forced off when `soichem_model` is off (`drivers/ecosim/EcoSIMAPI.F90:302-304`).

## 2. Source files

| File | Lines | Role |
|---|---|---|
| `f90src/APIs/GeochemAPI.F90` | 371 | `soluteModel` (`:23-150`) layer loop; `GeochemAPISend` (`:154-256`) grid state into `chem_var_type`; `GeochemAPIRecv` (`:260-369`) fluxes back to grid arrays |
| `f90src/Geochem/Layers_chem/SoluteMod.F90` | 1298 | `GeoChemEquilibria` dispatcher (`:43-56`), `UpdateFertilizerBand` (`:61-135`), `UreaHydrolysis` (`:139-215`), `UpdateSoilFertlizer` (`:218-508`), band updaters for NH3 (`:512-612`), PO4 (`:615-842`), NO3 (`:845-938`), `UpdateSurfResidueSolute` (`:941-1296`) |
| `f90src/Geochem/Box_chem/ChemEquilibriaMod.F90` | 835 | `NoSaltChemEquilibria` (`:22-775`): P minerals, P ligand exchange, H2PO4 dissociation, Gapon NH4 exchange, NH4/NH3 at prescribed pH |
| `f90src/Geochem/Box_chem/SaltChemEquilibriaMod.F90` | 2782 | `SaltChemEquilibria` (`:299-535`) -> `PrepIonConcentrations` (`:538-731`), `SolveChemEquilibria` (`:733-981`, `MRXN` iterations), `SummarizeIonFluxes` (`:1342-1478`) |
| `f90src/Geochem/Box_chem/InitSoluteMod.F90` | 1745 | `InitSoluteProperty` (`:154-207`), `InitSoluteModel` (`:210-366`), `InitEquilibria` (`:369-612`), `SolubilityEquilibiriaSalt` (`:615-1606`), `SolubilityEquilibriaNoSalt` (`:1609-1743`) |
| `f90src/Geochem/Box_chem/SoluteChemDataType.F90` | 609 | `solutedtype` (`:9-136`, initialisation bag), `solute_flx_type` (`:138-237`), `chem_var_type` (`:239-372`) |
| `f90src/Geochem/Box_chem/GeoChemMathMod.F90` | 62 | `A2BC_ChemReact_Quad`, `A2BC_ChemReact_Grad` (`:13-61`). **Dead code**: no module in the repository `use`s `GeoChemMathMod`; the same quadratic relaxation is written inline in every solver routine. |
| `f90src/Modelpars/SoluteParMod.F90` | 155 | every equilibrium constant, solubility product and rate constant, all `PARAMETER`s (`:10-152`) |

## 3. Call chain each hour

```
Run_EcoSIM_one_step                                   drivers/ecosim/EcoSIMAPI.F90:80-84 (if soichem_model)
  soluteModel(I,J,...)                                f90src/APIs/GeochemAPI.F90:23
    for each column, each layer L = NU..NL            :95-97
      if pore volume and water volume > ZEROS2         :98
        band/non-band water volumes and soil masses   :108-130
        UpdateSoilFertlizer(I,J,L,NY,NX,chemvar)      :132  -> UreaHydrolysis, fertilizer dissolution,
                                                             solution concentrations incl. plant uptake
                                                             and microbial release (SoluteMod.F90:218-508)
        GeochemAPISend(L,NY,NX,chemvar,solflx)        :134  -> CEC, AEC, pH, Gapon coefficients, pools
        GeoChemEquilibria(I,J,L,NY,NX,chemvar,solflx) :136  -> SaltChemEquilibria | NoSaltChemEquilibria
                                                             (SoluteMod.F90:50-54)
        GeochemAPIRecv(L,NY,NX,solflx)                :138  -> mol fluxes into trcn_/trcx_/trcp_ arrays
        UpdateFertilizerBand(L,NY,NX)                 :140  -> band geometry; mol -> g for solutes
    UpdateSurfResidueSolute(NX,NY)                    :146  -> litter-layer (L = 0) chemistry
REDIST (later in the same hour) adds the fluxes to the pools
  f90src/Balances/RedistMod.F90:963-974 (UpdateChemInSoilLays) for soil, :360-370 (UpdateSurfaceTracers) for litter
```

`SaltChemEquilibria` runs `PrepIonConcentrations`, then `SolveChemEquilibria`, which loops `M = 1..MRXN` with `MRXN = 1` (`f90src/Modelpars/SoluteParMod.F90:143`) over: `GetSoluteConcentrations`, `IonStrengthActivity`, gibbsite, ferric hydroxide, calcite and gypsum, `PhospPrecipDissolNonBand`, `PhospPrecipDissolBand`, `PhospAnionExchNoBand`, `PhospAnionExchBand`, `CationExchange`, `SoluteDissociation`, `UpdateIonFluxCurentIter`, `UpdateIonConcCurrentIter`, `AccumulateIonFlux` (`f90src/Geochem/Box_chem/SaltChemEquilibriaMod.F90:740-960`). It then calls `SummarizeIonFluxes` (`:533`).

## 4. pH: prescribed in both solvers

| Where pH enters | What the code does | Citation |
|---|---|---|
| Grid file | `PH` (layers) and `PH0` (litter) read into `PH_vr` | `f90src/IOutils/readimod.F90:483`, `:441` (`readTopoNC`) |
| Run time | `PH_vr` is never written by chemistry. Its only run-time writes are layer remapping and deep-layer fill. | `f90src/Balances/SoilLayerDynMod.F90:1966` (`MoveFertMinerals`); `f90src/HydroTherm/PhysData/SoilPhysParaMod.F90:152` (`SetDeepSoil`) |
| No-salt solver | `[H+] = 10**(-(PH-3))` mol m-3, `[OH-] = DPH2O/[H+]` | `f90src/Geochem/Box_chem/ChemEquilibriaMod.F90:278-280` |
| Salt solver | [H+] reset from `PH` at the start of each iteration, and H+ and OH- pulled back to the prescribed values at the end of each iteration (`RHHY`, `RHOH`). The H+ built from the `ZHY + RProd_Hp` tracer in `PrepIonConcentrations` is overwritten. | `f90src/Geochem/Box_chem/SaltChemEquilibriaMod.F90:1490-1491` (`GetSoluteConcentrations`); `:2626-2631` (`UpdateIonConcCurrentIter`); `:565` |
| Litter layer | same `10**(-(PH_vr(0)-3))` | `f90src/Geochem/Layers_chem/SoluteMod.F90:1106` (`UpdateSurfResidueSolute`) |
| Microbes | `micfor%PH = PH_vr(L)` | `f90src/APIs/MicBGCAPI.F90:243` (`MicAPISend`) |
| Boundary solutions | rain pH `pH_rain_col`, irrigation pH `PHQ` | `f90src/Ecosim_mods/StarteMod.F90:99`, `:93` |

The salt path does carry an H+ tracer (`trcSalt_solml_vr(idsalt_Hp)`) and returns an H+ flux, but the chemistry never uses the tracer as pH. Run evidence: in a site probe's 2006 restart, `PH` equals the grid file's `PH` layer by layer after 10 simulated years (6.81, 6.81, 6.81, 6.80, 6.79, ...).

## 5. Initial state: why sorption and the grid-file P pools are inert on a fresh run

`STARTE` runs in the first year when `soichem_model` is true (`drivers/ecosim/EcoSIMAPI.F90:441-450`). It loops `I = 1..366`, layers `L = NU..NL`, and litter complexes `K = k_fine_comp..k_POM`, which is 2..4 (`f90src/Ecosim_mods/StarteMod.F90:71-73`; `k_fine_comp = 2`, `k_manure = 3`, `k_POM = 4`, `f90src/Modelpars/MicBGCPars.F90:143-156`). The branches (routine `starte`):

| `(K, L, I)` | Branch taken | Citation |
|---|---|---|
| `(k_manure, 1, any)` | irrigation chemistry for day `I` | `f90src/Ecosim_mods/StarteMod.F90:77-94` |
| `(k_fine_comp, 1, 1)` | rainfall chemistry, then the soil-water block for layer 1, which sets `trcx_solml_vr(idx_CEC)` and `(idx_AEC)` and overwrites the rain values in `solutevar` with layer-1 soil values | `:97-155` |
| anything else | `cycle` | `:156-161` |

The `ELSEIF(K.EQ.micpar%k_POM ...)` that once separated the soil block from the rain block is commented out (`:114`; since commit `d4838af1`, Jan 2025). Two consequences follow:

- `InitSoluteConcs` writes the soil state only in its `K.EQ.micpar%k_POM` branch (`f90src/Ecosim_mods/StarteMod.F90:323`). That covers solution NH4, NO3 and PO4 (`:415-425`), exchangeable cations, surface sites `idx_OHe`, `idx_OH`, `idx_OHp`, and sorbed `idx_HPO4`, `idx_H2PO4` in band and non-band zones (`:452-470`), and the P precipitates (`:481` onward). `STARTE` never calls it with `K = k_POM`, so none of this is written.
- CEC and AEC capacities are written only for layer 1 (`:124-125`).

Nothing creates surface sites later. The only other writers move existing pools between band and non-band zones or between layers (`f90src/Disturbances/FertilizerMod.F90:637-657`; `f90src/Balances/SoilLayerDynMod.F90:1078-1079`). With zero sites, every phosphate exchange flux is zero (`equilibria_and_sorption.md` §3).

Run evidence (a site probe run on binary `09eb674a`, whose geochem, `StarteMod` and init code are identical to cb243228). Restart files for 1997 and 2006, variable `trcx_solml_vr(levsoi1=21, xtracers=24)`:

| Tracer | Layer 0 (litter) | Layer 1 | Layers 2-20 |
|---|---|---|---|
| `idx_CEC` | 0 | 0.524 | 0 |
| `idx_NH4` | 0.0033 (1997), 9.3e-5 (2006) | 0.0077, 5.8e-4 | 0 |
| `idx_AEC` | 0 | 0.114 | 0 |
| `idx_OHe`, `idx_OH`, `idx_OHp`, `idx_HPO4`, `idx_H2PO4` and their band forms | 0 | 0 | 0 |

The same restart has `trcp_saltpml_vr` for AlPO4 of about 1e-12 mol, and apatite of 0.0039, 0.0024 and 0.0005 mol in layers 1-3, although the grid file `grid-input.nc` gives `CALPO = 100` and `CCAPH = 100` in every layer. The history output `cEXCH_P_vr`, which is `patomw*(X-HPO4 + X-H2PO4 + band forms)` per soil mass (`f90src/IOutils/HistData/HistUpdateSoil.F90:136`), is zero by construction on such a run.

Practical consequences at cb243228, non-restart runs:

- Grid inputs `AEC`, `CPO4`, `CALPO`, `CFEPO`, `CCAPD`, `CCAPH`, `CALOH`, `CFEOH`, `CCACO`, `CCASO`, and `CEC` below layer 1, do not affect the simulation. The Gapon coefficients act only in layer 1.
- Phosphate sorption constants (`SXH2P`, `SXH1P`, `SXOH2`, `SXOH1`, `TADA`) cannot change any output. They are compile-time constants anyway.
- Rainfall NH4, HPO4 and H2PO4 concentrations are initialised from soil layer 1 solution values, because the soil block overwrites `solutevar` before `InitSoluteConcs` writes the rain concentrations (`f90src/Ecosim_mods/StarteMod.F90:143-155`, then `:213`, `:257-258`). This is from code reading and has not been checked against a run.
- A restart from a file written by an earlier binary that did initialise these pools carries them forward, because `restFile('read')` replaces the state (`drivers/ecosim/EcoSIMAPI.F90:491-507`).

## 6. Coupling to the rest of the model

**What the solver sees.** `UpdateSoilFertlizer` builds the solution concentrations from the pool masses plus this hour's microbial release minus plant uptake (`f90src/Geochem/Layers_chem/SoluteMod.F90:364-367` for NH4 and NH3, `:418-422` for HPO4 and H2PO4, `:455-459` for the band). Plant P uptake therefore draws on the same solution P that precipitation and sorption act on. Sorbed and precipitated concentrations are per unit soil mass of the zone (`:424-434`). `GeochemAPISend` adds CEC, AEC, pH, `CAL`, `CFE`, `CCA`, the Gapon coefficients and, in salt mode, every salt tracer (`f90src/APIs/GeochemAPI.F90:161-254`).

**What comes back, and units.** `GeochemAPIRecv` stores fluxes in mol per grid area per hour (comment `f90src/APIs/GeochemAPI.F90:268`). NH4 fluxes are added (`+=`, `:269-272`), and P and sorbed fluxes are assigned (`=`, `:273-296`). The mol-to-gram conversion for dissolved N and P and for CO2 is done afterwards in `UpdateFertilizerBand` (`f90src/Geochem/Layers_chem/SoluteMod.F90:117-132`). Exchangeable and precipitated fluxes stay in mol (`f90src/Ecosim_datatype/AqueChemDatatype.F90:77`, `:81`). `REDIST` adds them to `trcx_solml_vr` and `trcp_saltpml_vr` (`f90src/Balances/RedistMod.F90:963-974`).

**Hourly reset.** `HOUR1` zeroes the reaction-flux arrays every hour (`f90src/Modelforc/Hour1Mod.F90:860-861`, `:1590-1606`).

## 7. Fertilizer and urea

- Broadcast and banded NH4, NH3, urea and NO3 dissolve first-order at 1.0 h-1 (urea 0.1 h-1), scaled by soil relative water content `THETW_vr` and the band and non-band volume fractions (`f90src/Geochem/Layers_chem/SoluteMod.F90:334-348`; constants `f90src/Modelpars/SoluteParMod.F90:132-135`).
- Superphosphate and rock phosphate enter as monocalcium phosphate and hydroxyapatite precipitates and dissolve through the P mineral reactions (comment `SoluteMod.F90:313-317`; `SPPO4 = 5e-2` scales the Ca(H2PO4)2 dissolution floor, `ChemEquilibriaMod.F90:367`).
- Urea hydrolysis is Michaelis-Menten in urea with a microbial-activity-dependent Km, `DUKD = DUKM*(1 + COMA/DUKI)` (`SoluteMod.F90:160`), times `RFertUreaSpecHydrol * TMicHeterActivity_vr * TSens4MicbGrwoth_vr`, reduced by inhibitor activity `ZNHUI` (`:191-193`). The inhibitor decays at a type-dependent rate (`:167-169`; `RUreaInhibtorConst`, `SoluteParMod.F90:10`).
- Band geometry and the transfer of solute, sorbed and precipitated P from non-band to band as a band widens: `equilibria_and_sorption.md` §6.

## 8. Litter layer

`UpdateSurfResidueSolute` (`f90src/Geochem/Layers_chem/SoluteMod.F90:941-1296`) runs a simplified version of the same chemistry on the surface residue (`L = 0`) when it holds water. It uses the litter pH (`:1106`) and does its own mol-to-gram conversion (`:1291-1292`). `STARTE` zeroes the litter's sorbed and precipitated pools in the first year (`f90src/Ecosim_mods/StarteMod.F90:512-538`).

## 9. History outputs for soil inorganic N and P

| Output | Meaning (CDL `long_name`) |
|---|---|
| `cPO4_vr`, `cPO4_LITR_col` | dissolved PO4 concentration, soil layers and litter |
| `cEXCH_P_vr`, `cEXCH_P_LITR_col`, `tEXCH_PO4_col` | exchangeable (sorbed) inorganic P; zero on a fresh run (section 5) |
| `NH4_vr`, `NO3_vr`, `cNH4t_vr`, `cNO3t_vr`, `tNH4_col`, `tNO3_col` | mineral N |
| `UPTK_PO4_FLX_pft`, `prtUP_PO4_pvr` | plant PO4 uptake |

Names from `docs/ecosim-knowledge-base/ecosim_output_info_cb243228.cdl`; `cEXCH_P_vr` is registered at `f90src/IOutils/HistData/HistRegisterSoilPhysRoot.F90:180-181` in gP Mg-1 soil.

## 10. Routine map of the salt solver

| Routine | Lines in `f90src/Geochem/Box_chem/SaltChemEquilibriaMod.F90` | Role |
|---|---|---|
| `SaltChemEquilibria` | `:299-535` | pointer set-up, then the three calls below |
| `PrepIonConcentrations` | `:538-731` | masses to concentrations; H+ from `ZHY + RProd_Hp` (overwritten later) |
| `SolveChemEquilibria` | `:733-981` | `MRXN` loop; hydroxides, calcite, gypsum inline |
| `PhospPrecipDissolNonBand` | `:984-1339` | P minerals, non-band, dominant-species branches |
| `SummarizeIonFluxes` | `:1342-1478` | iteration totals into `solflx` |
| `GetSoluteConcentrations` | `:1481-1545` | clamps, and resets [H+] from pH |
| `IonStrengthActivity` | `:1548-1655` | ionic strength, A1-A3, activities |
| `PhospPrecipDissolBand` | `:1658-1978` | P minerals, band |
| `PhospAnionExchNoBand`, `PhospAnionExchBand` | `:1981-2034`, `:2037-2084` | surface protonation and P ligand exchange |
| `CationExchange` | `:2087-2175` | Gapon exchange for NH4, H, Al, Fe, Ca, Mg, Na, K |
| `SoluteDissociation` | `:2178-2466` | carboxyl exchange, NH4/NH3, complexes, carbonate, phosphate protonation |
| `UpdateIonFluxCurentIter`, `UpdateIonConcCurrentIter` | `:2469-2555`, `:2558-2677` | net fluxes; concentrations updated, H+/OH- pulled back to pH |
| `AccumulateIonFlux` | `:2680-2780` | running totals |

## 11. The two data bags

`chem_var_type` (`f90src/Geochem/Box_chem/SoluteChemDataType.F90:239-372`) carries one layer's inputs: CEC (`XCEC`), AEC (`XAEC`), pH, the `CAL`, `CFE`, `CCA` caps, the Gapon coefficients, zone water volumes and soil masses (`VLWatMicP*`, `BKVL*`), band volume fractions (`VLNH4`, `VLNHB`, `VLPO4`, `VLPOB`, `VLNO3`, `VLNOB`), solution, exchangeable and precipitated concentrations, and, in salt mode, every salt tracer. `solute_flx_type` (`:138-237`) carries the outputs, all named `TRChem_*`, plus `TBION_soil` (ion balance), `TRH2O_soil` (water from reactions) and `TRAquaChem_CO2_soil`. `solutedtype` (`:9-136`) is the separate bag `STARTE` uses for initialisation. `SetZero` (`:507-608`) clears `solflx` at the start of `NoSaltChemEquilibria` (`f90src/Geochem/Box_chem/ChemEquilibriaMod.F90:147`).

## Pages

- `equilibria_and_sorption.md`: rate laws, constants, activity corrections, P minerals, P ligand exchange, Gapon cation exchange, fertilizer bands, and the source map of the file-read soil-chemistry inputs with their live or inert status.
