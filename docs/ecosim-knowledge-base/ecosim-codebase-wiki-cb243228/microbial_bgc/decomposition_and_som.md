---
**Source pin:** EcoSIM commit `cb243228` (jingtao-lbl/EcoSIM `fix/r2-plant-balance`; upstream `09eb674a` + 2 fix commits)
**Scope:** `f90src/Microbial_bgc/Box_Micmodel/`, `f90src/Modelpars/{NitroPars,MicBGCPars}.F90`, `f90src/APIs/MicBGCAPI.F90`, with the respiration outputs in `f90src/Balances/RedistMod.F90` and `f90src/IOutils/HistData/`
**Last verified:** 2026-10-15
---

# Decomposition and SOM Dynamics

This page gives the rate laws of EcoSIM's microbial decomposition at cb243228, in the order `SoilBGCOneLayer` evaluates them (`f90src/Microbial_bgc/Box_Micmodel/MicBGCFGMod.F90:74-160`). Paths are relative to the EcoSIM repository root. Every rate is per guild `NGL`, per organic-matter complex `K`, per layer, per hourly call. Pool and group definitions are on [`index.md`](index.md); the mineral N and P exchange and its path to plants are on [`soil_plant_nutrient_coupling.md`](soil_plant_nutrient_coupling.md).

## 1. Environment scalars

### Temperature

`MicrobPhysTempFun` returns separate growth and maintenance scalars with low- and high-temperature inactivation (`f90src/Microbial_bgc/Box_Micmodel/MicrobMathFuncMod.F90:138-143`):

```
RTK = RGASC*TKSO ;  STK = 710*TKSO
ACTV  = 1 + exp((197500-STK)/RTK) + exp((STK-222500)/RTK)
TSensGrowth = exp(25.229 - 62500/RTK) / ACTV
ACTVM = 1 + exp((195000-STK)/RTK) + exp((STK-232500)/RTK)
TSensMaintR = exp(25.214 - 62500/RTK) / ACTVM
```

The input temperature is shifted by the site's thermal-acclimation offset, `TKSO = TKS + TempOffset` (`f90src/Microbial_bgc/Box_Micmodel/MicBGCFGMod.F90:415-417`), with `TempOffset_col = fOFFSET(ATCS_col)` set at start-up (`f90src/Ecosim_mods/StartsMod.F90:156`) and updated in `f90src/Modelforc/WthrMod.F90:474`. In the litter layer `TKS` is the litter/soil blend weighted by litter cover (`f90src/APIs/MicBGCAPI.F90:256`). Evaluating the function shows `TSensGrowth` is 1.0 at 25 C and peaks near 1.91 at about 37 C, so a rate constant times this scalar can be nearly twice its nominal value.

### Water

Per guild, `StageFuncGuild` sets the water scalar from soil matric potential (MPa), with fungi half as sensitive as the other heterotrophs (`f90src/Microbial_bgc/Box_Micmodel/MicrobMathFuncMod.F90:398-408`):

```
WatStressMicb = exp(0.1*max(PSISoilMatricP,-500))   ! fungi
WatStressMicb = exp(0.2*max(PSISoilMatricP,-500))   ! all other heterotrophs
GrowthEnvScalHeter = WSensGroHeter*TSensGroHeter ;  TempMaintRHeter = TSensMaintR
```

Autotrophs use `exp(0.2*PSISoilMatricP)` without the -500 floor (`f90src/Microbial_bgc/Box_Micmodel/MicrobMathFuncMod.F90:477-482`, StageAutotroph). In the litter layer `PSISoilMatricP` is the litter value (`f90src/APIs/MicBGCAPI.F90:258`; the blend on `:257` is overwritten). Below freezing it is replaced by `LtHeatIceMelt*(TKS-Tref)/TKS` (`f90src/APIs/MicBGCAPI.F90:265-267`).

### Autotroph growth scalar (`GrowthEnvScalAutor`)

Each autotroph catabolism routine calls `StageAutotroph` once per guild before its rate law (for example `f90src/Microbial_bgc/Box_Micmodel/NitrifierMod.F90:307`, `AmmoniaOxidizerCatabolism`, and `:486`, `NitriteOxidizerCatabolism`), which sets (`f90src/Microbial_bgc/Box_Micmodel/MicrobMathFuncMod.F90:477-482`, `StageAutotroph`):

```
WatStressMicb           = EXP(0.2*PSISoilMatricP)                        :477   every autotroph group, no -500 floor
WSensGroAutor(NGL)      = WatStressMicb ;  TSensGroAutor(NGL) = TSensGrowth   :478-479
GrowthEnvScalAutor(NGL) = AZMAX1(TSensGroAutor(NGL)*WSensGroAutor(NGL))  :481
TSensMaintRAutor(NGL)   = AZMAX1(TSensMaintR)                            :482
```

`TSensGrowth` and `TSensMaintR` are the layer values the heterotrophs also use: `StageBGCEnvironCondition` evaluates `MicrobPhysTempFun` once per layer and hour at the acclimation-shifted temperature `TKSO` (`f90src/Microbial_bgc/Box_Micmodel/MicBGCFGMod.F90:415-417`; function at `MicrobMathFuncMod.F90:138-143`, `MicrobPhysTempFun`). `PSISoilMatricP` is the matric potential staged in `MicAPISend` (`f90src/APIs/MicBGCAPI.F90:258`, `:262`, replaced below freezing at `:265-267`). The autotroph scalar therefore differs from `GrowthEnvScalHeter` only in its water term. The single-argument `AZMAX1` returns exactly 0 for an argument below `1.e-12` (`f90src/Minimath/MiniMathMod.F90:317`, `AZMAX1_s`; `tiny_val` at `:58`), so with `TSensGrowth` near 1 the autotroph scalar is exactly zero once `PSISoilMatricP` falls below about -138 MPa (`EXP(0.2*PSI) < 1.e-12`), while the heterotroph scalar `GrowthEnvScalHeter` has no such cutoff (`MicrobMathFuncMod.F90:407`, `StageFuncGuild`).

| consumer of the autotroph scalars | expression | file:line (subroutine) |
|---|---|---|
| NH3 oxidation capacity | `VMXX = VMXNH3Oxi*GrowthEnvScalAutor(NGL)*FBiomNutStoiScalAutor(NGL)*XCO2*OMActAutor(NGL)` | `NitrifierMod.F90:366` (`AmmoniaOxidizerCatabolism`) |
| NO2 oxidation capacity | `VMAX = GrowthEnvScalAutor(NGL)*FBiomNutStoiScalAutor(NGL)*XCO2*OMActAutor(NGL)*VMXNO2Oxi` | `NitrifierMod.F90:525` (`NitriteOxidizerCatabolism`) |
| aerobic CH4 oxidation, AMONC10, ANME-2d | `VMAX = GrowthEnvScalAutor(NGL)*FBiomNutStoiScalAutor(NGL)*...*VMXCH4OxiAero` (`VMX2AMONC10`, `VMX3AMO2D`) | `MethanotrophMod.F90:130` (`AeroMethanotrophCatabolism`), `:326` (`AMONC10Catabolism`), `:468` (`AMOANME2dCatabolism`) |
| hydrogenotrophic methanogenesis | `VMAX = OMActAutor(NGL)*VMXCH4gH2*GrowthEnvScalAutor(NGL)*FBiomNutStoiScalAutor(NGL)*XCO2` | `MethanogenMod.F90:236` (`H2MethanogensCatabolism`) |
| reserve-to-structural growth and mortality | `CGOMZ = GrowthEnvScalAutor(NGL)*OMGR*AZMAX1(mBiomeAutor(ielmc,MID3))`; `SPOMX = SQRT(GrowthEnvScalAutor(NGL))*SPOMC(M)*SPOMK(M)` | `MicAutoCplxFGMod.F90:455`, `:481` (`GatherAutotrophAnabolicFlux`) |
| mineral N and P immobilization caps | `BIOA*OMActAutor(NGL)*GrowthEnvScalAutor(NGL)*Z4MX` (NH4), `*ZOMX` (NO3), `*HPMX` (H2PO4, HPO4) | `MicAutoCplxFGMod.F90:911`, `:949`, `:991`, `:1030`; litter-layer counterparts `:1070`, `:1103`, `:1138`, `:1173` (`BiomNutMinerMobilAutor`) |
| maintenance demand | `RMOMX = RMOM*TSensMaintRAutor(NGL)*FPH` | `MicrobMathFuncMod.F90:536` (`CalcRespMaintAutor`) |
| decay of a fertilizer nitrification inhibitor (temperature only) | `ZNFNI = ZNFNI*(1-RNFNI*TSensGroAutor(NGL))`, then `ZNFN4S = ZNFN0 - ZNFNI/(1+CNH4S/ZHKI)` (band: `CNH4B`) | `NitrifierMod.F90:337-339` (`AmmoniaOxidizerCatabolism`) |

The inhibitor term acts only while `ZNFN0 > ZEROS` (`NitrifierMod.F90:336`), i.e. in the layer where a fertilizer with a nitrification inhibitor set `ZNFN0 = ZNFNI = 1` (`f90src/Disturbances/FertilizerMod.F90:110-111`, `ApplyUreaNitrifierInhibitor`); `ZNFN4S` and `ZNFN4B` multiply the substrate-limited NH3 oxidation (`NitrifierMod.F90:381`, `:383`), so a warmer layer (larger `TSensGroAutor`) removes the inhibition faster. The decrement is applied once per ammonia-oxidizer guild per call.

### Oxygen

Aerobic guilds solve O2 uptake as diffusion-limited Michaelis-Menten, `q = Vmax*S/(Km+S) = D*(S_ext - S)`, by the smaller quadratic root (`TranspBasedsubstrateUptake`, `f90src/Microbial_bgc/Box_Micmodel/MicrobMathFuncMod.F90:172-176`), called inside `AerobicHeterO2Uptake` with Km `OXKM = 0.080 gO m-3` (`f90src/Utils/EcoSimConst.F90:43`). The realized fraction is `OxyLimterHeter = AMIN1(1, RO2UptkHeter/RO2DmndHeter)` (`f90src/Microbial_bgc/Box_Micmodel/MicrobMathFuncMod.F90:334`).

### Biomass density

`GetMicrobDensFactorHeter` scales mortality and maintenance by microbial C relative to the layer's organic C, `COMC = TOMCNK(M)/ORGCL`, `SPOMK(M) = COMC/(COMC+COMKI)`, `RMOMK(M) = COMC/(COMC+COMKM)` (`f90src/Microbial_bgc/Box_Micmodel/MicBGCFGMod.F90:688-693`), with `ORGCL = AMIN1(1.0E+05*SoilMicPMassLayer, ORGC)` (`:798`).

### Stoichiometric status

Each guild's kinetic-biomass N:C and P:C relative to the target ratios gives (`f90src/Microbial_bgc/Box_Micmodel/MicBGCFGMod.F90:503-505`):

```
FCN = AMIN1(1, AMAX1(0.5, SQRT(rCNBiomeActHeter(ielmn)/rNCOMC(iLbiom_kinetic,NGL,K))))
FCP = AMIN1(1, AMAX1(0.5, SQRT(rCNBiomeActHeter(ielmp)/rPCOMC(iLbiom_kinetic,NGL,K))))
FBiomStoiScalarHeter = AMIN1(FCN, FCP)
```

Targets: fungi kinetic N:C 0.15, structural 0.09, P:C 0.015 / 0.009; all other heterotrophs and all autotrophs 0.225 / 0.135 and 0.0225 / 0.0135; reserve ratios are `DOT_PRODUCT(FL, ...)` of the first two (`f90src/Modelpars/MicBGCPars.F90:354-412`).

## 2. The microbial activity proxy

Hydrolysis, colonization, priming and litter mixing are all driven by one number per complex, `ROQC4HeterMicActCmpK(K)`, the sum over guilds of each guild's O2-limited potential catabolic rate (`f90src/Microbial_bgc/Box_Micmodel/MicBGCFGMod.F90:825-831`). For aerobic bacteria it is `ROQC4HeterMicrobAct = RGOCY*OxyLimterHeter` with `RGOCY = AZMAX1(FBiomStoiScalarHeter*OMActHeter)*VMXO*GrowthEnvScalHeter` (`f90src/Microbial_bgc/Box_Micmodel/AerobicBacteriaMod.F90:160`, `:204`); fungi use the same form with VMXO (`f90src/Microbial_bgc/Box_Micmodel/FungiMod.F90:120`, `:162`); fermenters use `RGOFY*OXYI` with VMXF (`f90src/Microbial_bgc/Box_Micmodel/FermenterMod.F90:137`, `:150`); acetoclastic methanogens contribute zero (`f90src/Microbial_bgc/Box_Micmodel/MethanogenMod.F90:127`). The proxy is independent of substrate concentration, so it measures enzyme capacity rather than realized respiration.

Consequence: VMXO is not only a respiration rate. It also scales every hydrolysis flux in Section 3 and the colonization rate in Section 4.

## 3. Hydrolysis (`SolidOMDecomposition`, `MicBGCFGMod.F90:1227-1519`)

### Activity-based hydrolysis scalar

```
COQCK = AMIN1(0.1E+06, ROQC4HeterMicActCmpK(K)/VOLWZ)            (:1322-1326)
DCKD  = DCKM0*(1+COQCK/DCKI)    if litrm (surface litter layer)   (:1327-1328)
DCKD  = DCKML*(1+COQCK/DCKI)    otherwise (every soil layer)      (:1329-1330)
COSC  = BulkSOMC(K)/SoilMicPMassLayer                              (:1333-1338)
DFNS  = COSC/(COSC+DCKD)                                           (:1339)
OQCI  = 1/(1+CDOM(idom_doc,K)/OQKI)                                (:1340)
RHydrolysisScalCmpK(K) = AZMAX1(ROQC4HeterMicActCmpK(K))*DFNS*OQCI/BulkSOMC(K)   (:1357)
```

`BulkSOMC(K) = SolidOMActK + OMBioResduK + SorbedOM(C) + SorbedOM(acetate)` is the colonized, residue and sorbed C of the complex (`f90src/Microbial_bgc/Box_Micmodel/MicBGCFGMod.F90:476-478`). `litrm` is true only for layer 0 (`f90src/APIs/MicBGCAPI.F90:221`). DCKM0 therefore acts only on the surface litter layer and DCKML on all soil layers. Defaults: `DCKM0 = DCKML = 1.0E+03`, `DCKI = 2.5`, `OQKI = 1.2E+03` (`f90src/Modelpars/NitroPars.F90:169`, `:177`, `:185-186`), identical in MicrobePars.20260211.nc.

### Solid organic matter

```
RHydlysSolidOM(ielmc,M,K) = SolidOMAct(M,K)*AMIN1(0.5, SPOSC(M,K)*RHydrolysisScalCmpK(K))   (:1361)
dHyd = AMIN1(1, RHydlysSolidOM(ielmc,M,K)/SolidOM(ielmc,M,K))                              (:1362)
RHydlysSolidOM(ielmn,M,K) = AZERO(SolidOM(ielmn,M,K))*dHyd/FCNK(K)                          (:1363)
RHydlysSolidOM(ielmp,M,K) = AZERO(SolidOM(ielmp,M,K))*dHyd/FCPK(K)                          (:1364)
then each element is capped at its pool                                                    (:1367)
```

`FCNK = AMIN1(1, AMAX1(0.5, TOMEK(ielmn,K)/tMaxNActMicrbK(K)))` is the community's kinetic-biomass N relative to the maximum the target ratio allows (`f90src/Microbial_bgc/Box_Micmodel/MicBGCFGMod.F90:1309-1313`, `:581`). An N-poor community (FCNK < 1) hydrolyses up to twice as much organic N per unit C, which raises DON supply; it does not by itself mineralize anything (mineral exchange is in `BiomassMineralization`, see the coupling page).

`SPOSC(M,K)` comes from `SPOSC_in` and is multiplied by 1.5 for the three litter complexes (`f90src/Modelpars/MicBGCPars.F90:344-346`). Defaults (`f90src/Modelpars/NitroPars.F90:162-166`), before and after the litter boost:

| M | woody, fine, manure (K=1-3) base / used | POM (K=4) | humus (K=5) |
|---|---|---|---|
| 1 protein | 7.5 / 11.25 | 0.05 | 0.05 |
| 2 carbohydrate | 7.5 / 11.25 | 0.0 | 0.0167 |
| 3 cellulose | 1.5 / 2.25 | 0.0 | 0.0 |
| 4 lignin | 0.5 / 0.75 | 0.0 | 0.0 |

Zero entries make that component of POM or humus permanent unless a file supplies non-zero values. Because `RHydrolysisScalCmpK` already has the units of h-1, SPOSC acts as a dimensionless ratio of hydrolysed C to activity-normalized C, whatever its declared units. The `AMIN1(0.5, ...)` cap limits one call to half the colonized pool; where `RHydrolysisScalCmpK` is small, the product stays far below the cap and the flux is linear in SPOSC.

### Humification of litter

In the three litter complexes, the lignin flux sets a POM humification cap and protein, carbohydrate and cellulose are co-humified up to 10 percent of it (`f90src/Microbial_bgc/Box_Micmodel/MicBGCFGMod.F90:1389-1407`):

```
RHumifySolidOM(C,lignin) = AZMAX1(AMIN1(RHydlys(N,lignin)/CNRH(k_POM), RHydlys(P,lignin)/CPRH(k_POM), EPOC*RHydlys(C,lignin)))
RHOSCM = 0.10*RHumifySolidOM(C,lignin)
RDecmpProdDOM = RHydlysSolidOM - RHumifySolidOM
```

`EPOC = 1.0` and `EHUM = 0.200 + 0.333*AMIN1(0.5, CCLAY)` are set per layer in `f90src/Modelforc/Hour1Mod.F90:547-548`. In soil layers the humified product joins POM protein (`f90src/Microbial_bgc/Box_Micmodel/MicBGCFGMod.F90:1635-1640`); in the litter layer it is passed to the soil below (`:1641-1645`). POM and humus complexes send all hydrolysate to DOM (`:1408-1415`).

### Microbial residue (necromass) and sorbed OM

```
dHyd = AMIN1(1, SPORC(M)*RHydrolysisScalCmpK(K))                       (:1447)
RHydlysBioResduOM(ielmc,M,K) = AZERO(OMBioResdu(ielmc,M,K))*dHyd      (:1448)
RHydlysBioResduOM(ielmn) = ...*dHyd/FCNK ;  (ielmp) = ...*dHyd/FCPK   (:1449-1450)
dHyd = AMIN1(1, SPOHC*RHydrolysisScalCmpK(K))  -> sorbed C, N, P      (:1490-1493)
sorbed acetate: AZERO(SorbedOM(acetate))*AZMAX1(AMIN1(1, SPOHA*ROQC4HeterMicActCmpK*DFNS/BulkSOMC))   (:1506-1507)
```

Necromass hydrolysis is capped twice (`AMIN1(1,...)` and then `AMIN1(flux, pool)`, `:1453`). Defaults `SPORC = (7.5, 1.5)`, `SPOHC = SPOHA = 0.25` (`f90src/Modelpars/NitroPars.F90:244-247`).

All hydrolysis products enter DOM in `RedistDecompProduct` (`f90src/Microbial_bgc/Box_Micmodel/MicBGCFGMod.F90:1622-1629`, `:1654-1659`, `:1673-1677`).

## 4. Colonization

`MicrobialLitterColonization` grows the colonized fraction: `SolidOMAct(M,K) = AMIN1(SolidOM(ielmc,M,K), SolidOMAct(M,K) + DOSA(K)*ROQC4HeterMicActCmpK(K)*SolidOM(ielmc,M,K)/SolidOMCK(K))` (`f90src/Microbial_bgc/Box_Micmodel/MicBGCFGMod.F90:1961-1964`). Hydrolysis does not debit `SolidOMAct` (the decrement at `:1626` is commented out), so the colonized fraction is bounded only by the `AMIN1` with the remaining pool.

## 5. Catabolism (per guild)

### Aerobic heterotrophs and fungi

`AerobicHeteroBactCatabolism` (`f90src/Microbial_bgc/Box_Micmodel/AerobicBacteriaMod.F90:29-215`) and `AerobicFungiCatabolism` (`f90src/Microbial_bgc/Box_Micmodel/FungiMod.F90:27-170`):

```
FSBSTC = CDOM(doc)/(CDOM(doc)+OQKM) ;  FSBSTA = CDOM(acetate)/(CDOM(acetate)+OQKA)       (AerobicBacteriaMod:156-157)
RGOCY  = AZMAX1(FBiomStoiScalarHeter*OMActHeter)*VMXO*GrowthEnvScalHeter                  (:160)
RGOCZ  = RGOCY*FSBSTC*FOCA ;  RGOAZ = RGOCY*FSBSTA*FOAA                                    (:161-162)
RGOCX  = AZMAX1(DOM(doc)*FOQC*EO2Q) ;  RGOAX = AZMAX1(DOM(acetate)*FOQA*EO2A)               (:165-166)
RGOMP  = AMIN1(RGOCX,RGOCZ) + AMIN1(RGOAX,RGOAZ)                                          (:169-171)
RO2Dmnd4RespHeter = 2.667*RGOMP                                                            (:194)
RespGrossHeter = RGOMP*OxyLimterHeter ;  RCO2ProdHeter = RespGrossHeter                    (:205-206)
```

`EO2Q` is `EO2X` (aerobic bacteria), `EO2D` (facultative denitrifiers) or `ENFX` (aerobic N2 fixers) (`:133-141`), `EO2G` for fungi (`f90src/Microbial_bgc/Box_Micmodel/FungiMod.F90:116`). `FOQC`, `FOQA` are the guild's share of the previous hour's ecosystem DOC and acetate demand (`f90src/Microbial_bgc/Box_Micmodel/MicrobMathFuncMod.F90:430-442`). `RGOCX` is the substrate-limited branch: when it binds, respiration is set by the DOC pool, not by VMXO. Defaults `VMXO = 0.125`, `OQKM = OQKA = 12` (`f90src/Modelpars/NitroPars.F90:189`, `:196-197`).

### Fermenters and anaerobic N2 fixers (VMXF)

`AcetogFermentCatabolism` (`f90src/Microbial_bgc/Box_Micmodel/FermenterMod.F90:27-164`) is the only VMXF consumer: `RGOFY = AZMAX1(FBiomStoiScalarHeter*OMActHeter)*VMXF*GrowthEnvScalHeter` (`:137`), O2-inhibited by `OXYI` (`:135`). Of the respired C, 0.667 becomes acetate and the rest CO2, with H2 at 0.111 (`:154-159`). Fungi do NOT use VMXF.

### Other guilds

Denitrification (`HeteroDenitrificCatabolism`, `f90src/Microbial_bgc/Box_Micmodel/DenitrifierMod.F90:26`), acetoclastic methanogenesis (`f90src/Microbial_bgc/Box_Micmodel/MethanogenMod.F90:29`), the autotrophs (index page) and cyanobacteria follow the same pattern: specific rate x active biomass x environment x stoichiometric scalar x Monod substrate terms.

### Growth-efficiency energetics

After the parameter read, `initNitroPars` derives the growth respiration efficiencies (`f90src/Modelpars/NitroPars.F90:251-262`):

```
EO2X = 1/(1+GO2X/EOMC)   aerobic bacteria on DOC    (:254)
EO2G = 1/(1+GO2X/EOMG)   fungi                      (:256)
EO2D = 1/(1+GO2X/EOMD)   denitrifiers (aerobic)     (:257)
ENFX = 1/(1+GO2X/EOMN)   diazotrophs                (:258)
EO2A = 1/(1+GO2A/EOMC),  GO2A = GO2X-GCHX           (:251, :260)
```

`EO2X` is the fraction of each gram of substrate C respired to supply the energy for the rest to become biomass (comment at `:254`). It enters twice: as the substrate-limited cap `RGOCX = DOM*FOQC*EO2Q` and as the divisor that turns growth respiration into uptake (Section 6). A larger GO2X lowers EO2X, which raises the C assimilated per unit respired, and also lowers the substrate-limited respiration cap. Defaults `GO2X = 37.5`, `EOMC = 25`, `EOMG = EOMD = 37.5`, `EOMN = 75` (`:227-233`).

## 6. Respiration partition, maintenance and starvation

### Maintenance demand (RMOM)

`CalcRespMaintHeter` (`f90src/Microbial_bgc/Box_Micmodel/MicrobMathFuncMod.F90:552-592`), called by each catabolism routine before the rate law:

```
FPH   = 1 + AZMAX1(0.25*(6.5-PH))                                                (:577)
RMOMX = RMOM*TempMaintRHeter(NGL,K)*FPH                                          (:578)
RMaintDmndHeter(kinetic)    = mBiomeHeter(ielmn, kinetic, K)*RMOMX*RMOMK(kinetic) (:580)
RMaintDmndHeter(structural) = OMN2(NGL,K)*RMOMX*RMOMK(structural)                 (:581)
RMaintRespHeter = sum of the two                                                  (:589)
```

Maintenance scales with biomass N (kinetic N plus active structural N, `OMN2` from `f90src/Microbial_bgc/Box_Micmodel/MicBGCFGMod.F90:515-522`), so RMOM's units gC gN-1 h-1 are exact. Acidity below pH 6.5 raises it. Autotrophs: `f90src/Microbial_bgc/Box_Micmodel/MicrobMathFuncMod.F90:535-538` (CalcRespMaintAutor). Default `RMOM = 0.010` (`f90src/Modelpars/NitroPars.F90:246`).

### How maintenance shapes uptake and growth

Maintenance is a demand, not a second CO2 stream. Gross respiration `RespGrossHeter` is set by catabolism (Section 5) and is the CO2 flux. `GatherHeterotrophRespiration` computes `RGrowthRespHeter = AZMAX1(RespGrossHeter - RMaintRespHeter)` (`f90src/Microbial_bgc/Box_Micmodel/MicBGCFGMod.F90:3035`) and the maintenance deficit after any denitrification support (`ReserveDenitrifMaintenance`, `:3049-3050`; `f90src/Microbial_bgc/Box_Micmodel/MicrobMathFuncMod.F90:92-125`). `GatherHetertrophAnabolicFlux` then converts respiration into substrate uptake, giving maintenance and N2-fixation respiration no growth credit (`f90src/Microbial_bgc/Box_Micmodel/MicBGCFGMod.F90:3211-3239`):

```
OrganicMaint = AMIN1(RMaintRespHeter, RespGrossHeter)
PrimaryDOCUptake  = FGOCP*(OrganicMaint + OrganicNFixResp + (OrganicGrowthResp-OrganicNFixResp)/DOCRespFrac)
PrimaryAcetUptake = FGOAP*(OrganicMaint + OrganicNFixResp + (OrganicGrowthResp-OrganicNFixResp)/AcetRespFrac)
```

with `DOCRespFrac = EO2X, EO2D, EO2G, ENFX` by group (`:3218-3232`). The net C added to the reserve is `CGROMC = DOMUptk4GrothHeter(ielmc) - RespGrossHeter - denitrification respiration` (`:1868-1869`), applied at `:1899`. So, at a given catabolic rate, a larger RMOM moves respiration from the growth share to the maintenance share and lowers net C assimilation; it does not raise that hour's CO2.

### Starvation

When maintenance exceeds supply, biomass is killed to cover the deficit (`f90src/Microbial_bgc/Box_Micmodel/MicBGCFGMod.F90:3382-3405`):

```
FracMaintDeficit = RMaintDefcitcitHeter/RMaintRespHeter
RMaintDefcitKillOMHeter(ielmc,M) = AMIN1(AvailableBiomass(ielmc), AZMAX1(FracMaintDeficit*RMaintDmndHeter(M)/RCCC))
RMaintDefcitRecycOMHeter = RMaintDefcitKillOMHeter*RCCE(NE)
```

The recycled C of starving biomass is respired as CO2 (`:1896`) while recycled N and P return to the reserve (`:1885-1887`); the unrecycled part goes to residue or humus by `EHUM` (`:3404-3405`). This is the only path by which RMOM raises CO2 within the same call.

## 7. Reserve-to-structural growth (OMGR)

```
CGOMZ = GrowthEnvScalHeter*OMGR*AZMAX1(mBiomeHeter(ielmc, reserve, K))                         (:3292)
NonstX2stBiomHeter(ielmc,M) = FL(M)*CGOMZ                                                      (:3297)
NonstX2stBiomHeter(N or P,M) = AZMAX1(reserve N or P)*AMIN1(FL(M), NonstX2stBiomHeter(ielmc,M)/reserve C)   (:3300-3301)
```

The C transfer is not capped by the reserve, while N and P are: if `GrowthEnvScalHeter*OMGR > 1`, the C withdrawn exceeds reserve C. With `TSensGrowth` reaching about 1.9 near 37 C, the default `OMGR = 0.25` (`f90src/Modelpars/NitroPars.F90:176`) keeps the product below 1; values above roughly 0.5 can cross it in warm layers. N and P transfers pass through `LimitReserveNutrientTransfers` before the update (`f90src/Microbial_bgc/Box_Micmodel/MicBGCFGMod.F90:1786-1813`). Kinetic biomass gained here raises `OMActHeter` and therefore every rate in Sections 2-5. OMGR also caps N2-fixation respiration for aerobic and anaerobic N2 fixers and cyanobacteria, `Resp4NFixHeter = AMIN1(..., OMGR*mBiomeHeter(ielmc, reserve, K))` (`:3068-3073`). Autotroph twin: `f90src/Microbial_bgc/Box_Micmodel/MicAutoCplxFGMod.F90:455-467`.

## 8. Mortality and recycling (SPOMC, RCCZ, RCCY, CKC)

For each live compartment M (kinetic, structural) of each guild (`f90src/Microbial_bgc/Box_Micmodel/MicBGCFGMod.F90:3318-3363`, GatherHetertrophAnabolicFlux):

```
CCC = AZMAX1(AMIN1(1, N3/(N3 + C3*rNCOMC(reserve)), P3/(P3 + C3*rPCOMC(reserve))))   (:3321-3323)
CXC = C3/C1                    reserve C over kinetic C                              (:3324)
C3C = 1/(1+CXC/CKC)                                                                   (:3325)
CNC = AZMAX1(AMIN1(1, C3/(C3 + N3/rNCOMC(reserve))))  ;  CPC likewise with P          (:3327-3328)
RCCC = RCCZ + AMAX1(CCC,C3C)*RCCY ;  RCCN = CNC*RCCX ;  RCCP = CPC*RCCQ                (:3329-3331)
RCCE(C) = RCCC ;  RCCE(N) = RCCN+(1-RCCN)*RCCC ;  RCCE(P) = RCCP+(1-RCCP)*RCCC         (:3338-3340)
SPOMX = SQRT(GrowthEnvScalHeter)*SPOMC(M)*SPOMK(M)                                    (:3343)
RKillOMHeter(NE,M) = AZMAX1(AMIN1(mBiomeHeter(NE,MID,K), mBiomeHeter(NE,MID,K)*SPOMX)) (:3345)
RkillRecycOMHeter = RKillOMHeter*RCCE(NE)                                             (:3347)
RkillLitfalOMHeter = AZMAX1(RKillOMHeter - RkillRecycOMHeter)                         (:3349)
-> to humus: *EHUM ; to microbial residue: the rest                                   (:3358-3362)
```

(N3, P3, C3 are the reserve element masses and C1 the kinetic C.) If either the reserve or kinetic C is negligible, `RCCC = RCCZ` and N and P are not preferentially recycled (`:3332-3336`).

What this means:

- Mortality is clamped to the standing compartment, so at most the whole compartment dies in one call. This clamp was added between `2dea74d9` and `cb243228` (commit `318eda41`); the "unclamped mortality" hazard of the prior wiki no longer applies.
- SPOMC is labelled gC gN-1 h-1 but multiplies every element pool, so it acts as h-1 per hourly call. Defaults: compiled `(/1.0E-02, 0.1E-02/)` (`f90src/Modelpars/NitroPars.F90:248`), shipped MicrobePars.20260211.nc `[0.01, 0.01]`.
- Because `RCCE(N) >= RCCE(C)` and `RCCE(P) >= RCCE(C)`, recycling returns proportionally more N and P than C to the reserve (`f90src/Microbial_bgc/Box_Micmodel/MicBGCFGMod.F90:1883-1887`). Faster turnover therefore raises the reserve N:C and P:C, which pushes `BiomassMineralization` toward releasing mineral N and P (coupling page).
- `C3C` competes with `CCC` inside `AMAX1`; CKC changes RCCC only where `C3C > CCC`. `CCC` is at most 0.5 when the reserve sits exactly at its target ratio (`N3 = C3*rNCOMC`), so whether CKC matters depends on the reserve C:kinetic C ratio relative to CKC.
- RCCC also divides the starvation kill (Section 6), so RCCZ, RCCY and CKC set how much biomass dies to pay a maintenance deficit.

Defaults `RCCZ = 0.167`, `RCCY = 0.833`, `RCCX = RCCQ = 0.833`, `CKC = 1.0E-03` (`f90src/Modelpars/NitroPars.F90:170-173`, `:182`). Autotroph twin: `f90src/Microbial_bgc/Box_Micmodel/MicAutoCplxFGMod.F90:422-497`.

## 9. DOM sorption (TSORP, HSORP)

`RDOMSorption` (`f90src/Microbial_bgc/Box_Micmodel/MicBGCFGMod.F90:1137-1224`):

```
AECX = 0.5E+03 (litter layer) else AEC                                       (:1182-1186)
VLSoilPoreMicPX = SoilMicPMassLayer*AECX*HSORP*FracBulkSOMC(K)              (:1194)
VLSoilPoreMicPW = VLWatMicPM(NPH)*FracBulkSOMC(K)                            (:1195)
VOLCX = FOCA*VLSoilPoreMicPX ;  VOLCW = FOCA*VLSoilPoreMicPW                  (:1197-1198)
RDOMSorp(doc) = TSORP*(OQEX(doc)*VOLCX - OHEX(doc)*VOLCW)/(VOLCX+VOLCW)      (:1199)
(acetate with FOAA, DON and DOP with the unweighted volumes)                (:1204-1212)
DOM -= RDOMSorp ;  SorbedOM += RDOMSorp                                      (:1218-1221)
```

The bracket is the transfer that would bring solution and sorbed concentrations to the partition `sorbed/solution = VOLCX/VOLCW`. HSORP scales the sorbent side together with soil mass and anion exchange capacity, so a larger HSORP moves more DOM onto the solid phase. TSORP is the fraction of that gap closed per call: 1 lands on the equilibrium, above 1 it overshoots, and the exchange has no limiter, so values well above 1 make the DOM and sorbed pools oscillate. Defaults `TSORP = 0.5`, `HSORP = 1.0` (`f90src/Modelpars/NitroPars.F90:242-243`).

## 10. Priming and litter mixing

`OMTransferForPriming` moves activity, DOM and biomass between complexes K and KK toward equal per-BulkSOMC concentrations (`f90src/Microbial_bgc/Box_Micmodel/MicBGCFGMod.F90:1055-1100`): `XFRK = FPRIM*TScal4Difsvity*(ROQC4(K)*BulkSOMC(KK) - ROQC4(KK)*BulkSOMC(K))/OSRT` (`:1060`), DOM likewise (`:1062`), biomass with `FPRIMM*GrowthEnvScalHeter` (`:1090`). Layer activity `TMicHeterActivity` is accumulated here (`:1116`) and reported as `MicrobAct_vr` (`f90src/IOutils/HistData/HistUpdateSoil.F90:191`). `DownwardMixOM` mixes litter into the soil at `FracLitrMix = FOSCZ0/OMLitrC*TMicHeterActivity` (surface) or `FOSCZL*FOSCXD*TMicHeterActivity/VGeomLayer` (subsurface) (`f90src/Microbial_bgc/Layers_Micmodel/SoilBGCNLayMod.F90:95`, `:122`).

## 11. From catabolism to `ECO_RH_col` and `CO2_SEMIS_FLX_col`

Production side, per layer:

1. Guild CO2: `RCO2ProdHeter = RespGrossHeter` for aerobes (`f90src/Microbial_bgc/Box_Micmodel/AerobicBacteriaMod.F90:206`), one third of fermented C for fermenters (`f90src/Microbial_bgc/Box_Micmodel/FermenterMod.F90:156`), plus starvation respiration (`f90src/Microbial_bgc/Box_Micmodel/MicBGCFGMod.F90:1896`).
2. Layer sum (`AggregateTransfOMBioResdue`): `tRCO2MicrbProd += RCO2ProdHeter` (`:2116`) and `+= RCO2ProdAutor` (`:2158`); `RCO2NetUptkMicb = tRCO2GrothAutor - tRCO2MicrbProd - tRNOxMicrbRedux` (`:2239`), minus the CO2 from aerobic CH4 oxidation (`:2247`). Negative means release.
3. API: `trcs_RMicbUptake_vr(idg_CO2,L) = micflx%RCO2NetUptkMicb` (`f90src/APIs/MicBGCAPI.F90:556`).

`ECO_RH_col`:

4. `ECO_HR_CO2_vr(L) = trcs_RMicbUptake_vr(idg_CO2,L) - TProd_CO2_geochem_soil_vr(L)` for soil layers (`f90src/Balances/RedistMod.F90:956`, UpdateChemInSoilLays), so soil-layer geochemical CO2 production is counted as heterotrophic respiration; `ECO_HR_CO2_vr(0) = trcs_RMicbUptake_vr(idg_CO2,0)` for litter (`f90src/Balances/RedistMod.F90:553`, HandleSurfaceBoundary).
5. `ECO_HR_CO2_col = sum(ECO_HR_CO2_vr(0:JZ))`; `Eco_HR_CumYr_col += ECO_HR_CO2_col + ECO_HR_CH4_col` (`f90src/Balances/RedistMod.F90:232-234`, UpdateOutputVars), reset each year (`f90src/Modelforc/YearMod.F90:83`).
6. `ECO_RH_col = Eco_HR_CumYr_col/AREA` (`f90src/IOutils/HistData/HistUpdateColumn.F90:205`), a cumulative-since-1-January quantity (`avgflag='I'`, negative into the atmosphere); `ECO_HR_CO2_col` is the hourly rate (`:206`), `HR_CO2_vr` the layer rate (`f90src/IOutils/HistData/HistUpdateSoil.F90:63`), `HR_CO2_litr_col` the litter layer (`f90src/IOutils/HistData/HistUpdateColumn.F90:378`).

Known defect in step 5: the litter-layer CH4 term is written to `ECO_HR_CH4_vr(L,...)` (`f90src/Balances/RedistMod.F90:554`) where `L` is the leftover index of the snow loop `DO L=1,JS` (`:421-423`), i.e. 6 (`JS = 5`, `f90src/Mesh/GridConsts.F90:24`), and the soil-layer loop later overwrites layer 6 (`f90src/Balances/RedistMod.F90:957`). The litter-layer CH4 contribution therefore does not reach `ECO_HR_CH4_col` or `ECO_RH_col`.

`CO2_SEMIS_FLX_col`:

7. Transport source: `RBGCSrceGasMM_vr(idg_CO2,L) = -trcs_RMicbUptake_vr*dts_gas` when microbes release CO2 (`f90src/Transport/Nonsalt/InitNoSaltTransportMod.F90:394-397`, StageSoilFluxes; litter `:204-207`, StageSurfaceFluxes), with root-to-soil CO2 and geochemical CO2 added in the same routine (`:407-411`).
8. After gas transport, `CO2_SEMIS_FLX_col = SurfGasEmiss_all_flx_col(idg_CO2)/AREA*GramPerHr2umolPerSec` (`f90src/IOutils/HistData/HistUpdateColumn.F90:242`). Diffusion, ebullition and dissolution between production and the surface belong to the transport pages.

## 12. Numerical behavior relevant to calibration

| Rate law | Guard at cb243228 | What can go wrong |
|---|---|---|
| Solid-OM hydrolysis | `AMIN1(0.5, ...)` then pool cap (`MicBGCFGMod.F90:1361`, `:1367`) | none |
| Necromass hydrolysis | `AMIN1(1, ...)` then pool cap (`:1447`, `:1453`) | none |
| Mortality | `AMIN1(pool, pool*SPOMX)` (`:3345`) | none (whole compartment at most) |
| DOM sorption | none (`:1199-1221`) | TSORP > 1 overshoots the equilibrium each call |
| Reserve-to-structural C | none on C (`:3292-3297`) | `GrowthEnvScalHeter*OMGR > 1` withdraws more C than the reserve holds |

## Calibration parameters: source map

| file name | Fortran variable | read at (file:line, subroutine) | every use site at cb243228 (subroutine, file:line, branch) | what it does (the equation, quoted) |
|---|---|---|---|---|
| `SPOSC` (MicrobePars, optional) | `SPOSC_in` -> `micpar%SPOSC` | `f90src/Modelpars/NitroPars.F90:363-364` (ReadPars), only if the variable exists; default `:162-166` (initNitroPars) | copy `f90src/Modelpars/MicBGCPars.F90:344` and x1.5 on K=1-3 `:346` (SetPars); `f90src/Microbial_bgc/Box_Micmodel/MicBGCFGMod.F90:1361` (SolidOMDecomposition; all layers, litter layer computes K=1-3 only) | `RHydlysSolidOM(ielmc,M,K) = SolidOMAct(M,K)*AMIN1(0.5_r8,SPOSC(M,K)*RHydrolysisScalCmpK(K))`; N and P follow via `dHyd/FCNK`, `dHyd/FCPK` (`:1362-1364`). Absent from MicrobePars.20260211.nc, so the default applies with that file |
| `SPOMC` | `SPOMC(2)` | `f90src/Modelpars/NitroPars.F90:355` (ReadPars) | `f90src/Microbial_bgc/Box_Micmodel/MicBGCFGMod.F90:3343` (GatherHetertrophAnabolicFlux, heterotrophs); `f90src/Microbial_bgc/Box_Micmodel/MicAutoCplxFGMod.F90:481` (GatherAutotrophAnabolicFlux, autotrophs) | `SPOMX = SQRT(GrowthEnvScalHeter(NGL,K))*SPOMC(M)*SPOMK(M)`; `RKillOMHeter(NE,M,NGL,K)=AZMAX1(AMIN1(mBiomeHeter(NE,MID,K),mBiomeHeter(NE,MID,K)*SPOMX))`. Element 1 kinetic, 2 structural. Compiled `(0.01, 0.001)`, shipped file `(0.01, 0.01)` |
| `SPORC` | `SPORC(2)` | `f90src/Modelpars/NitroPars.F90:354` (ReadPars) | `f90src/Microbial_bgc/Box_Micmodel/MicBGCFGMod.F90:1447` (SolidOMDecomposition) | `dHyd=AMIN1(1._r8,SPORC(M)*RHydrolysisScalCmpK(K))`; `RHydlysBioResduOM(ielmc,M,K) = AZERO(OMBioResdu(ielmc,M,K))*dHyd` |
| `RMOM` | `RMOM` | `f90src/Modelpars/NitroPars.F90:353` (ReadPars) | `f90src/Microbial_bgc/Box_Micmodel/MicrobMathFuncMod.F90:578` (CalcRespMaintHeter, heterotrophs); `:536` (CalcRespMaintAutor, autotrophs) | `RMOMX = RMOM*TempMaintRHeter(NGL,K)*FPH`; `RMaintDmndHeter(iLbiom_kinetic,NGL,K) = mBiomeHeter(ielmn,MID1,K)*RMOMX*RMOMK(iLbiom_kinetic)`; structural `= OMN2(NGL,K)*RMOMX*RMOMK(iLbiom_struct)`. A demand that partitions gross respiration (Section 6) |
| `VMXO` | `VMXO` (NitroPars) | `f90src/Modelpars/NitroPars.F90:300` (ReadPars) | `f90src/Microbial_bgc/Box_Micmodel/AerobicBacteriaMod.F90:160` (AerobicHeteroBactCatabolism: groups 1, 2, 6); `f90src/Microbial_bgc/Box_Micmodel/FungiMod.F90:120` (AerobicFungiCatabolism: group 3); `f90src/Microbial_bgc/Box_Micmodel/CyanoBacteriaMod.F90:173` (CyanoBacteriaCatabolism: group 8). The `VMXO` in `NoduleBGCMod` is `PlantBGCPars::VMXO`, a different compiled constant | `RGOCY = AZMAX1(FBiomStoiScalarHeter(NGL,K)*OMActHeter(NGL,K))*VMXO*GrowthEnvScalHeter(NGL,K)`; feeds respiration (`RGOCZ = RGOCY*FSBSTC*FOCA`) and the hydrolysis proxy `ROQC4HeterMicrobAct = RGOCY*OxyLimterHeter` (`AerobicBacteriaMod.F90:204`) |
| `DCKM0` | `DCKM0` | `f90src/Modelpars/NitroPars.F90:298` (ReadPars) | `f90src/Microbial_bgc/Box_Micmodel/MicBGCFGMod.F90:1328` (SolidOMDecomposition, `litrm` branch: surface litter layer only; soil layers use DCKML at `:1330`) | `DCKD=DCKM0*(1.0_r8+COQCK/DCKI)`; `DFNS = COSC/(COSC+DCKD)`; `RHydrolysisScalCmpK = AZMAX1(ROQC4HeterMicActCmpK)*DFNS*OQCI/BulkSOMC` |
| `OMGR` | `OMGR` | `f90src/Modelpars/NitroPars.F90:291` (ReadPars) | `f90src/Microbial_bgc/Box_Micmodel/MicBGCFGMod.F90:3292` (GatherHetertrophAnabolicFlux, all heterotrophs); `:3073` (GatherHeterotrophRespiration, N2-fixer and cyanobacteria branch); `f90src/Microbial_bgc/Box_Micmodel/MicAutoCplxFGMod.F90:455` (GatherAutotrophAnabolicFlux) | `CGOMZ = GrowthEnvScalHeter(NGL,K)*OMGR*AZMAX1(mBiomeHeter(ielmc,MID3,K))`; `NonstX2stBiomHeter(ielmc,M,NGL,K)=FL(M)*CGOMZ`; N2 fixation `Resp4NFixHeter = AMIN1(RGrowthRespHeter*RGN2P/(RGrowthRespHeter+RGN2P)*CZ2GS/(CZ2GS+ZFKM), OMGR*mBiomeHeter(ielmc,MID3,K))`. Hourly rate applied per call; C side unclamped |
| `CKC` | `CKC` | `f90src/Modelpars/NitroPars.F90:295` (ReadPars) | `f90src/Microbial_bgc/Box_Micmodel/MicBGCFGMod.F90:3325` (GatherHetertrophAnabolicFlux); `f90src/Microbial_bgc/Box_Micmodel/MicAutoCplxFGMod.F90:428` (GatherAutotrophAnabolicFlux) | `C3C = 1.0_r8/(1.0_r8+CXC/CKC)`; `RCCC = RCCZ+AMAX1(CCC,C3C)*RCCY`; inert where `CCC >= C3C` |

All eight are read on the live path whenever `micpar_file_in` is set (`f90src/Modelpars/NitroPars.F90:280`); with no file they take the compiled fallbacks of `initNitroPars`. None is read and then overwritten, and none is unused.

### Related parameters re-verified

| file name | read at | use site at cb243228 | what it does |
|---|---|---|---|
| `RCCZ`, `RCCY` | `f90src/Modelpars/NitroPars.F90:287-288` (ReadPars) | `f90src/Microbial_bgc/Box_Micmodel/MicBGCFGMod.F90:3329`, `:3333`, divisor `:3388` (GatherHetertrophAnabolicFlux); `f90src/Microbial_bgc/Box_Micmodel/MicAutoCplxFGMod.F90:433`, `:437`, `:527` (GatherAutotrophAnabolicFlux) | `RCCC = RCCZ+AMAX1(CCC,C3C)*RCCY`; starvation kill `/RCCC` |
| `VMXF` | `f90src/Modelpars/NitroPars.F90:301` (ReadPars) | `f90src/Microbial_bgc/Box_Micmodel/FermenterMod.F90:137` (AcetogFermentCatabolism: fermenters, anaerobic N2 fixers) | `RGOFY = AZMAX1(FBiomStoiScalarHeter*OMActHeter)*VMXF*GrowthEnvScalHeter` |
| `GO2X` | `f90src/Modelpars/NitroPars.F90:342` (ReadPars) | `f90src/Modelpars/NitroPars.F90:251-258` (initNitroPars) -> `EO2X`, `EO2G`, `EO2D`, `ENFX`, `EO2A`, `EN2X` | `EO2X = 1/(1+GO2X/EOMC)` |
| `TSORP`, `HSORP` | `f90src/Modelpars/NitroPars.F90:349-350` (ReadPars) | `f90src/Microbial_bgc/Box_Micmodel/MicBGCFGMod.F90:1194-1212` (RDOMSorption) | `RDOMSorp = TSORP*(OQEX*VOLCX-OHEX*VOLCW)/(VOLCX+VOLCW)`, `VOLCX` contains `HSORP` |
| `RNFNI` | `f90src/Modelpars/NitroPars.F90:331` (ReadPars); compiled fallback `2.0E-04` at `:222` (initNitroPars) | `f90src/Microbial_bgc/Box_Micmodel/NitrifierMod.F90:337` (AmmoniaOxidizerCatabolism, only while `ZNFN0 > ZEROS`) | `ZNFNI=ZNFNI*(1.0_r8-RNFNI*TSensGroAutor(NGL))`: hourly decay of a fertilizer nitrification inhibitor, scaled by the autotroph temperature term (Section 1) |
