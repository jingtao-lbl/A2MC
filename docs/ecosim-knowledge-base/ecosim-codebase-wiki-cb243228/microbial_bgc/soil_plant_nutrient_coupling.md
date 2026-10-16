---
**Source pin:** EcoSIM commit `cb243228` (jingtao-lbl/EcoSIM `fix/r2-plant-balance`; upstream `09eb674a` + 2 fix commits)
**Scope:** `f90src/Microbial_bgc/Box_Micmodel/{MicBGCFGMod,MicrobMathFuncMod,MicAutoCplxFGMod}.F90`, `f90src/APIs/MicBGCAPI.F90`, `f90src/Transport/Nonsalt/InitNoSaltTransportMod.F90`, `f90src/Geochem/Layers_chem/SoluteMod.F90`, `f90src/Plant_bgc/{NutUptakeMod,ExtractsMod,RootMod,PlantNonstElmDynMod,PlantBranchMod,StomatesMod}.F90`, `f90src/Balances/RedistMod.F90`, `f90src/Modelforc/Hour1Mod.F90`, `f90src/IOutils/HistData/`
**Last verified:** 2026-10-15
---

# Soil-to-Plant Mineral Nutrient Coupling

Decomposition reaches plant growth in EcoSIM only through the soil mineral N and P pools. Microbes add to those pools when their reserve holds more N or P than their target stoichiometry, take from them when it holds less, and roots take from the same pools in competition with microbes. Root uptake raises plant nonstructural N and P, which set the N:P content of new leaves, their protein, and their Rubisco. This page traces that chain at cb243228, names the Fortran state variables and the history outputs at each step, and lists how each microbial calibration parameter enters it. The decomposition rate laws themselves are on [`decomposition_and_som.md`](decomposition_and_som.md).

## The chain in one view

```
SolidOM / microbial residue / sorbed OM  --hydrolysis (SPOSC, SPORC, DCKM0, VMXO)-->  DON, DOP in DOM
DON, DOP  --guild uptake, in proportion to C uptake-->  reserve N, P  (mBiomeHeter(:, reserve, K))
reserve C  <--net C assimilation (VMXO, RMOM, GO2X)--  DOC, acetate
mortality recycling (SPOMC, RCCZ, RCCY, CKC) returns more N, P than C to the reserve
reserve-to-structural transfer (OMGR) drains reserve C, N, P
RINHP = reserve C x rNCOMC(reserve) - reserve N
   RINHP > 0 : immobilize NH4 then NO3 (Michaelis-Menten, competitive share)
   RINHP <= 0: release NH4 (net mineralization)            likewise RIPOP for H2PO4
layer sums -> micflx%RNH4MicbReliz2Soil, RNO3..., RH2PO4...  -> RNut_MicbRelease_vr
soil solution pools trcs_solml_vr(ids_NH4 | ids_NO3 | ids_H2PO4, L)       history: NH4_vr, NO3_vr, cNH4t_vr, cNO3t_vr, cPO4_vr, tNH4_col, tNO3_col
roots: UptakeNH4 / UptakeNO3 / UptakeH2PO4 -> RootNutUptake_pvr           history: UPTK_NH4_FLX_pft, UPTK_NO3_FLX_pft, UPTK_PO4_FLX_pft, prtUP_*_pvr
-> RootMycoNonstElms_rpvr(ielmn | ielmp)                                    history: Root_NONSTN_pft, Root_NONSTP_pft
-> shoot-root exchange (PTSHT) -> CanopyNonstElms_brch                     history: SHOOT_NONSTN_pft, ShootRoot_XFER_N_pft
-> leaf N:C of new growth (CNLF x status) -> LeafProteinC_node (CNWL, CPWL) history: LEAF_N_pft, LEAF_P_pft
-> Rubisco and Vcmax from leaf protein -> canopy photosynthesis             history: CAN_GPP_pft
```

## Step 1. Organic N and P become dissolved

Hydrolysis moves N and P from colonized solid OM, microbial residue and sorbed OM to DON and DOP. The N and P fluxes follow the C flux divided by the community N and P status (`f90src/Microbial_bgc/Box_Micmodel/MicBGCFGMod.F90:1362-1364`, `:1448-1450`, `:1491-1493`, SolidOMDecomposition):

```
FCNK(K) = AMIN1(1, AMAX1(0.5, TOMEK(ielmn,K)/tMaxNActMicrbK(K)))     (:1310-1312)
tMaxNActMicrbK(K) += OMActHeter(NGL,K)*rNCOMC(iLbiom_kinetic,NGL,K)  (:581)
RHydlysSolidOM(ielmn,M,K) = AZERO(SolidOM(ielmn,M,K))*dHyd/FCNK(K)
```

So a community whose kinetic biomass is below its maximum N:C (FCNK < 1) hydrolyses up to twice as much organic N per unit C. The products enter `DOM(idom_don,K)` and `DOM(idom_dop,K)` in `RedistDecompProduct` (`:1627-1629`, `:1655-1658`, `:1673-1677`). Litter-complex lignin humification can divert part of the hydrolysed N and P to POM first (`:1391-1407`). This step changes only organic pools; it does not by itself put N into the mineral pool.

History: solid-OM C hydrolysis `RDecompC_SOM_vr` (`f90src/IOutils/HistData/HistUpdateSoil.F90:188`), residue `RDecompC_BReSOM_vr` (`:189`), sorbed `RDecompC_SorpSOM_vr` (`:190`), litter `RDecompC_SOM_litr_col` (`f90src/IOutils/HistData/HistUpdateColumn.F90:368`); DON `DON_vr` (`f90src/IOutils/HistData/HistUpdateSoil.F90:77`).

## Step 2. Microbes take up DON and DOP with their carbon

Each guild takes up DON and DOP in proportion to its C uptake, scaled up when its own N or P status is low, and limited by its share of the pool (`f90src/Microbial_bgc/Box_Micmodel/MicBGCFGMod.F90:3265-3269`, GatherHetertrophAnabolicFlux):

```
CGOXC = RMetabDOCUptkHeter + RMetabAcetUptkHeter
DOMUptk4GrothHeter(ielmn) = AZMAX1(AMIN1(DOM(idom_don,K)*FracHeterBiomOfActK, CGOXC*rCNDOM(K)/FCN(NGL,K)))
DOMUptk4GrothHeter(ielmp) = AZMAX1(AMIN1(DOM(idom_dop,K)*FracHeterBiomOfActK, CGOXC*rCPDOM(K)/FCP(NGL,K)))
```

`rCNDOM = DON/DOC` of the complex (`:630-632`). The C uptake `CGOXC` comes from the respiration partition (`:3235-3264`), so everything that sets C uptake (VMXO, RMOM, GO2X, substrate supply) also sets organic N and P uptake. Organic N and P go to the reserve compartment (`f90src/Microbial_bgc/Box_Micmodel/MicBGCFGMod.F90:1900-1905`, HeterotrophAnabolicUpdate); the net C assimilated goes there too (`CGROMC`, `:1868-1869`, `:1899`).

## Step 3. The reserve decides: immobilize or mineralize

`BiomassMineralization` (`f90src/Microbial_bgc/Box_Micmodel/MicBGCFGMod.F90:2544-2976`) runs per guild before the reserve is updated for this call, on the reserve state carried from the previous call.

Nitrogen:

```
RINHP = mBiomeHeter(ielmc,MID3,K)*rNCOMC(iLbiom_reserve,NGL,K) - mBiomeHeter(ielmn,MID3,K)   (:2679)
IF RINHP > 0 (reserve N below target):                                                     (:2682-2693)
   CNH4X = AZMAX1(CNH4S - Z4MN)
   RINHX = AMIN1(RINHP, BIOA*OMActHeter*GrowthEnvScalHeter*Z4MX)
   RNH4DmndSoilHeter = FNH4S*RINHX*CNH4X/(CNH4X+Z4KU)
   RNH4imobilSoilHeter = AMIN1(FNH4X*AZMAX1(ZNH4S - Z4MN*VLWatMicP*FNH4S), RNH4DmndSoilHeter)
ELSE (reserve N at or above target):                                                       (:2695-2700)
   RNH4imobilSoilHeter = RINHP*FNH4S        (negative: release to soil NH4)
RINOP = AZMAX1(RINHP - NH4 immobilized) -> NO3 immobilization with ZOMX, ZOKU, ZOMN          (:2725-2736)
```

Phosphorus follows the same pattern with `RIPOP = reserve C*rPCOMC(reserve) - reserve P` (`:2769`): immobilization of H2PO4 with `HPMX`, `HPKU`, `HPMN` (`:2772-2781`), release as H2PO4 when RIPOP <= 0 (`:2783-2787`), and a residual HPO4 demand at 0.1 of what H2PO4 did not meet (`:2812-2823`). Band and non-band zones are split by `VLNH4`, `VLNHB`, `VLPO4`, `VLPOB`. Release goes only to NH4 and H2PO4; NO3 is never released by this routine (the NO3 branch is immobilization only, `:2738-2742`).

Targets: `rNCOMC(reserve) = 0.55*rNCOMC(kinetic) + 0.45*rNCOMC(structural)`, which is 0.1845 for bacteria and 0.123 for fungi from the hard-coded ratios (`f90src/Modelpars/MicBGCPars.F90:348`, `:357-358`, `:370-371`, `:383`). Microbial mineral-uptake kinetics are MicrobePars inputs: `Z4MX = 5.0E-03`, `Z4KU = 0.40`, `Z4MN = 0.0125`, `ZOMX = 5.0E-03`, `ZOKU = 0.35`, `ZOMN = 0.03`, `HPMX = 1.0E-03`, `HPKU = 0.075`, `HPMN = 0.002` (`f90src/Modelpars/NitroPars.F90:206-214`, read at `:317-325`).

The litter-layer microbes may also immobilize from the top soil layer below through `LitterSoilNutrientUptake` (`f90src/Microbial_bgc/Box_Micmodel/MicBGCFGMod.F90:2852-2972`; kinetics `f90src/Microbial_bgc/Box_Micmodel/MicrobMathFuncMod.F90:52-89`); those fluxes are booked into the soil layer through `micfor%tRNH4MicrbImobilSoil` (`f90src/Microbial_bgc/Box_Micmodel/MicBGCFGMod.F90:2196-2205`).

Before the reserve update, `LimitReserveNutrientTransfers` scales growth transfers and any release so that the reserve cannot give out more N or P than it has plus this call's supply (`f90src/Microbial_bgc/Box_Micmodel/MicrobMathFuncMod.F90:27-49`, applied at `f90src/Microbial_bgc/Box_Micmodel/MicBGCFGMod.F90:1786-1813`); it also corrects `NetNH4Mineralize` and `NetPO4Mineralize`. Autotrophs have their own version in `BiomNutMinerMobilAutor` (`f90src/Microbial_bgc/Box_Micmodel/MicAutoCplxFGMod.F90:766-1185`).

## Step 4. Layer totals and the hand-off to the soil

`AggregateTransfOMBioResdue` sums the guild exchanges and flips the sign to "release" (`f90src/Microbial_bgc/Box_Micmodel/MicBGCFGMod.F90:2106-2113`, `:2149-2156`, `:2333-2342`):

```
RNH4MicbReliz2Soil   = -tRNH4MicrbImobilSoil            (minus NH3 oxidized by nitrifiers, :2345-2347)
RNO3MicbReliz2Soil   = -tRNO3MicrbImobilSoil - TReduxNO3Soil + RNO3ProdSoilChemo   (+ nitrite oxidation, :2356)
RH2PO4MicbReliz2Soil = -tRH2PO4MicrbImobilSoil
RH1PO4MicbReliz2Soil = -tRH1PO4MicrbImobilSoil         band versions likewise (:2339-2363)
```

So the soil NH4 term combines heterotroph mineralization/immobilization, autotroph exchange and nitrification; the NO3 term adds denitrification and nitrite oxidation. `MicAPIRecv` copies them to `RNut_MicbRelease_vr(ids_NH4 | ids_NO3 | ids_NO2 | ids_H2PO4 | ids_H1PO4 | band ids, L)` (`f90src/APIs/MicBGCAPI.F90:572-581`) and accumulates `NetNH4Mineralize_CumYr_col`, `NetPO4Mineralize_CumYr_col` (`:588-589`).

## Step 5. The soil mineral solution pools

The pools both microbes and roots read are the solute masses `trcs_solml_vr(ids,L)` [g per grid] and concentrations `trc_solcl_vr(ids,L)` [g m-3], with `ids_NH4`, `ids_NO3`, `ids_H2PO4`, `ids_H1PO4` and their band counterparts. Microbes see `micstt%ZNH4S = AZMAX1(trcs_solml_vr(ids_NH4,L) - trcs_solml_drib_vr(ids_NH4,L))`, `ZNO3S` and `H2PO4` likewise, and `CNH4S = trc_solcl_vr(ids_NH4,L)`, `CNO3S`, `CH2P4` (`f90src/APIs/MicBGCAPI.F90:368-373`, `:394-402`, MicAPISend).

Microbial release and root uptake enter the same pools in the same routine. In `StageSoilFluxes` (`f90src/Transport/Nonsalt/InitNoSaltTransportMod.F90:374`) the microbial term becomes a source or sink, `RBGCSrcSoluteM_vr(ids,L) = RNut_MicbRelease_vr(ids,L)*dts_HeatWatTP` when positive, else a sink (`:433-457`), and the plant term a sink, `RBGCSinkSoluteM_vr(ids,L) += trcs_Soil2plant_uptake_vr(ids,L)*dts_HeatWatTP` (`:459-466`). The litter layer uses `StageSurfaceFluxes` (`:222-233`). The geochemical equilibrium also starts from the net of the two, `REcoReleaz_NH4X = (RNut_MicbRelease_vr(ids_NH4,L) - trcs_Soil2plant_uptake_vr(ids_NH4,L) + natomw*RFertReleaz_NH4)/VLWatMicPNX` (`f90src/Geochem/Layers_chem/SoluteMod.F90:364`, UpdateSoilFertlizer; P at `:418-419`; litter layer in UpdateSurfResidueSolute `:1051`, `:1069-1070`).

History outputs that report these pools (all registered at cb243228):

| Output | What it is | Producer |
|---|---|---|
| `NH4_vr` | dissolved NH4 concentration, gN m-3 | `trc_solcl_vr(ids_NH4,L)` (`f90src/IOutils/HistData/HistUpdateSoil.F90:99`) |
| `NO3_vr` | dissolved NO3 concentration, gN m-3 | `trc_solcl_vr(ids_NO3,L)` (`f90src/IOutils/HistData/HistUpdateSoil.F90:98`) |
| `cNH4t_vr` | solution + band + exchangeable NH4 per soil mass, gN Mg-1 (inactive by default) | `f90src/IOutils/HistData/HistUpdateSoil.F90:125-127` |
| `cNO3t_vr` | NO3 + NO2, solution + band, per soil mass, gN Mg-1 | `f90src/IOutils/HistData/HistUpdateSoil.F90:129-131` |
| `cPO4_vr` | H1PO4 + H2PO4, solution + band, per water volume, gP m-3 (labelled gP/Mg soil; inactive by default) | `f90src/IOutils/HistData/HistUpdateSoil.F90:133-135` |
| `tNH4_col` | column NH4 + NH3 (micro- and macropore solution, band, exchangeable), gN m-2 | `f90src/Balances/RedistMod.F90:1061`, `:1079-1098`; history `f90src/IOutils/HistData/HistUpdateColumn.F90:128` |
| `tNO3_col` | column NO3 + NO2, gN m-2 | `f90src/Balances/RedistMod.F90:1064`, `:1082-1105`; history `f90src/IOutils/HistData/HistUpdateColumn.F90:129` |
| `NET_N_MIN_col` | cumulative net microbial N mineralization, positive = release (inactive by default) | `-NetNH4Mineralize_CumYr_col/AREA` (`f90src/IOutils/HistData/HistUpdateColumn.F90:81`) |
| `NET_P_MIN_col` | the same for P | `f90src/IOutils/HistData/HistUpdateColumn.F90:123` |
| `tMICROB_N_col`, `tMICROB_P_col` | column microbial N, P | `f90src/IOutils/HistData/HistUpdateColumn.F90:135`, `:116` |

## Step 6. Microbes and roots compete for the same pools

Neither side is served first. Each takes a share of the available pool equal to its share of the previous hour's total demand. The totals are accumulated per layer from the root demands (`REcoNH4DmndSoil_vr(L) += RootNH4DmndSoil_pvr`, `f90src/Plant_bgc/ExtractsMod.F90:294-296`, TotalGasandSoluteUptake) and the microbial demands (`f90src/Balances/RedistMod.F90:1471-1473`, SumMicBGCFluxes), then copied to "previous" at the start of the next hour (`RNH4EcoDmndSoilPrev_vr = REcoNH4DmndSoil_vr`, `f90src/Modelforc/Hour1Mod.F90:1249-1250`, `:1254`, Prep4PlantMicrobeUptake).

- Microbial guild share: `FNH4X = AMAX1(FMN, RNH4DmndSoilHeterPrev(NGL,K)/RNH4EcoDmndSoilPrev)` (`f90src/Microbial_bgc/Box_Micmodel/MicBGCFGMod.F90:2452-2453`, SubstrateAttenf4Compet; NO3 `:2462-2463`, H2PO4 `:2472-2473`), with `FMN = 5.0E-03` (`f90src/Modelpars/NitroPars.F90:145`).
- Root share: `FNH4X = AMAX1(FracMinRoot4Uptake_rpvr, RootNH4DmndSoilPrev_pvr/RNH4EcoDmndSoilPrev_vr)` (`f90src/Plant_bgc/NutUptakeMod.F90:1255-1256`, UptakeMineralNitrogen; NO3 `:1266-1267`).

The share multiplies the pool above the uptaker's minimum concentration, `ZNH4X = AZMAX1(FNH4X*(trcs_solml_vr(ids_NH4,L) - ZNH4M))` for roots (`f90src/Plant_bgc/NutUptakeMod.F90:802-803`) and `FNH4X*AZMAX1(ZNH4S - ZNH4M)` for microbes (`f90src/Microbial_bgc/Box_Micmodel/MicBGCFGMod.F90:2690-2692`). Higher microbial demand last hour therefore lowers the roots' accessible share this hour, and vice versa.

## Step 7. Root uptake

Root uptake per root type N, layer L and plant NZ (`f90src/Plant_bgc/NutUptakeMod.F90`):

- NH4 (`UptakeNH4`, `:701-890`): `VmaxNH4RootPerPlant = VmaxNH4Root_pft*RootSAreaPerPlant_pvr*FSatNutTransporter*fTgrowRootP_vr*AMIN1(FCUP,FZUP)` (`:765-766`); uptake only where `trc_solcl_vr(ids_NH4,L) > CMinNH4Root_pft` (`:770`); mass flow `RMFNH4` plus diffusion `DIFNH4` (`:771-772`); the quadratic transport-uptake solution in `SoluteUptakeByPlantRoots` with Km `KmNH4Root_pft` and capped at `ZNH4X` (`:802-818`).
- NO3 (`UptakeNO3`, `:501-698`): the same form (`:577`, `:580`, `:613-626`).
- H2PO4 (`UptakeH2PO4`, `:1056-1216`): `UPMXP = VmaxPO4Root_pft*RootSAreaPerPlant_pvr*...` (`:1117`), capped at `H2POX = AZMAX1(FPO4X*(trcs_solml_vr(ids_H2PO4,L) - H2POM))` (`:1136`). HPO4 uptake uses 0.1 of the H2PO4 Vmax (`:956`, UptakeHPO4).
- Feedbacks from plant status: `FCUP` from root nonstructural C (`:1364-1365`), `FZUP` and `FPUP` from root nonstructural N:C and P:C (`:1378-1382`), and `FSatNutTransporter` from root protein (`:1349-1351`), all in GetUptakeCapcity. A root already rich in nonstructural N takes up less.

The Vmax, Km and minimum-concentration parameters (`UPMXZH`, `UPKMZH`, `UPMNZH`, `UPMXZO`, ..., `UPMNPO`) are read and documented on the plant roots page (topic 03).

Uptake leaves the soil through `trcs_Soil2plant_uptake_vr(ids,L) += RootNutUptake_pvr(ids,N,L,NZ)` (`f90src/Plant_bgc/ExtractsMod.F90:273`, TotalGasandSoluteUptake), which is the sink in Step 5. It enters the plant in `SummarizeRootSink` (`f90src/Plant_bgc/RootMod.F90:5482`):

```
dUptakeN = RootNutUptake_pvr(ids_NH4) + (ids_NH4B) + (ids_NO3) + (ids_NO3B)         (:5682-5683)
dUptakeP = RootNutUptake_pvr(ids_H2PO4) + (ids_H2PO4B) + (ids_H1PO4) + (ids_H1PO4B) (:5684-5685)
RootMycoNonstElms_rpvr(ielmn,N,L,NZ) += dUptakeN ;  (ielmp) += dUptakeP               (:5692-5693)
```

after charging the C cost of uptake to root nonstructural C and scaling uptake down if that C is short (`:5641-5671`).

History: `UPTK_NH4_FLX_pft = RootNH4Uptake_pft/AREA`, `UPTK_NO3_FLX_pft`, `UPTK_PO4_FLX_pft = RootH2PO4Uptake_pft/AREA` (H2PO4 only) (`f90src/IOutils/HistData/HistUpdatePlant.F90:181-187`; accumulated at `f90src/Plant_bgc/RootMod.F90:5687-5690`); per layer `prtUP_NH4_pvr`, `prtUP_NO3_pvr`, `prtUP_PO4_pvr` (`f90src/IOutils/HistData/HistUpdatePlant.F90:389-393`); `Root_NONSTN_pft = RootMycoNonstElms_pft(ielmn,ipltroot)` (`:128`); `Plant_N_pft = (ShootElms + RootElms)(ielmn)/AREA` (`:238-239`).

## Step 8. From root nonstructural N and P to leaf protein and Rubisco

- Root to shoot: `ShootRootElmTransfer` moves nonstructural N and P down the concentration gradient between each branch and each rooted layer, `XFRE = PTSHTR*NonstElmGradt` (`f90src/Plant_bgc/PlantNonstElmDynMod.F90:610-611`), updating `CanopyNonstElms_brch(NE)` and `RootMycoNonstElms_rpvr(NE)` (`:618-623`). History `SHOOT_NONSTN_pft = CanopyNonstElms_pft(ielmn)` (`f90src/IOutils/HistData/HistUpdatePlant.F90:131`) and `ShootRoot_XFER_N_pft` (`:270`).
- N status of the branch: `CNG = N/(N + C*CNKI)`, `CPG` likewise, `CNPG = AMIN1(CNG, CPG)` from the branch nonstructural concentrations `LeafPetoNonstElmConc_brch` (`f90src/Plant_bgc/PlantBranchMod.F90:3165-3170`, ComputRAutoAfEmergence).
- Leaf N and P of new growth: `fNCLFW_brch = CNLFB*(ZPLFM + ZPLFD*CNPG)`, `Growth_brch(ielmn,leaf) = Growth_brch(ielmc,leaf)*fNCLFW_brch`; P with `CPLFB` (`f90src/Plant_bgc/PlantBranchMod.F90:392-393`, `:401-402`, BranchBiomAllocate). Low nonstructural N or P lowers the N:C and P:C of every new leaf.
- Leaf protein: `LeafProteinC_node += AMIN1(GrowthElms(ielmn)*rProteinC2LeafN_pft, GrowthElms(ielmp)*rProteinC2LeafP_pft)` (`f90src/Plant_bgc/PlantBranchMod.F90:3561-3562`, GrowLeavesOnBranch), with `rProteinC2LeafN_pft` from `CNWL` and `rProteinC2LeafP_pft` from `CPWL`.
- Rubisco and Vcmax: C3 `MesophyllRubiscoC = LeafProteinC_node*LeafRubisco2Protein_pft`, `VcMaxRubiscoRef_brch += VmaxSpecRubCarboxyRef_pft*MesophyllRubiscoC` (`f90src/Plant_bgc/StomatesMod.F90:144-148`, PhotosynsDiag); C4 builds PEP carboxylase and bundle-sheath Rubisco from the same protein (`:127-134`). History `LEAF_N_pft = LeafStrutElms_pft(ielmn)/AREA` (`f90src/IOutils/HistData/HistUpdatePlant.F90:242`), `LEAF_P_pft` (`:259`); canopy photosynthesis is reported as `CAN_GPP_pft`.

The leaf, protein and photosynthesis details are on the plant pages; what matters here is that the soil mineral pools reach Vcmax only through this nonstructural-N route.

## How each microbial calibration parameter reaches the mineral pools

Every relation below is a source relation at cb243228; the direction of the net effect depends on the state of the reserve and of the soil, so no fixed sign is implied.

| Parameter | First relation in the chain | Where it meets the mineral exchange |
|---|---|---|
| `SPOSC` | `RHydlysSolidOM(ielmc) = SolidOMAct*AMIN1(0.5, SPOSC*RHydrolysisScalCmpK)` sets the N and P hydrolysis through `dHyd` (`f90src/Microbial_bgc/Box_Micmodel/MicBGCFGMod.F90:1361-1364`) | more DON, DOP -> guild organic N, P uptake (`:3268-3269`) -> reserve N, P (`:1900-1905`) -> `RINHP`, `RIPOP` (`:2679`, `:2769`) |
| `SPORC` | `dHyd = AMIN1(1, SPORC*RHydrolysisScalCmpK)` on microbial residue C, N, P (`:1447-1450`) | as SPOSC |
| `DCKM0` | `DCKD = DCKM0*(1+COQCK/DCKI)` in the surface litter layer only (`:1327-1328`) | litter-layer hydrolysis; litter microbes release to layer 0 and immobilize from the top soil layer (`:2852-2972`, `:2196-2205`) |
| `VMXO` | `RGOCY = ...*VMXO*...` sets both catabolic C uptake and the hydrolysis proxy (`f90src/Microbial_bgc/Box_Micmodel/AerobicBacteriaMod.F90:160`, `:204`) | C uptake sets reserve C and organic N uptake (`f90src/Microbial_bgc/Box_Micmodel/MicBGCFGMod.F90:3265-3269`, `:1899`); hydrolysis sets DON supply (`:1357`) |
| `RMOM` | maintenance demand from biomass N (`f90src/Microbial_bgc/Box_Micmodel/MicrobMathFuncMod.F90:578-581`) | shifts uptake from growth to maintenance and lowers net C assimilation `CGROMC` (`f90src/Microbial_bgc/Box_Micmodel/MicBGCFGMod.F90:3235-3238`, `:1868`), hence reserve C and `RINHP`; under a deficit, starvation recycles N and P to the reserve while the C is respired (`:1885-1887`, `:1896`) |
| `SPOMC` | `RKillOMHeter = AMIN1(pool, pool*SPOMX)` (`:3343-3345`) | recycling returns `RCCE(N) >= RCCE(C)` of the killed mass to the reserve (`:3338-3347`, `:1883`), raising reserve N:C; the rest becomes residue for Step 1 (`:3358-3362`) |
| `RCCZ`, `RCCY`, `CKC` | `RCCC = RCCZ + AMAX1(CCC, C3C)*RCCY`, `C3C = 1/(1+CXC/CKC)` (`:3325`, `:3329`) | set `RCCE(C, N, P)` and so the reserve's share of killed N, P vs C (`:3338-3340`); divide the starvation kill (`:3388`) |
| `OMGR` | `CGOMZ = GrowthEnvScalHeter*OMGR*reserve C` (`:3292`) | drains reserve C, N, P into active biomass (`:3297-3301`, `:1883`), which changes reserve size and `OMActHeter`, the cap on immobilization `RINHX = AMIN1(RINHP, BIOA*OMActHeter*GrowthEnvScalHeter*Z4MX)` (`:2686`); also caps N2-fixation respiration (`:3073`) |

## Knowledge-graph encoding

The curated seed expresses this chain with three mechanisms that share real output nodes, so the graph has a path from decomposition parameters to plant photosynthesis:

- `Microbial_N_P_Mineralization_Immobilization` (parameters SPOSC, SPORC, DCKM0, VMXO, RMOM, SPOMC, RCCZ, RCCY, CKC, OMGR) affects `NET_N_MIN_col`, `NET_P_MIN_col`, `NH4_vr`, `NO3_vr`, `cNH4t_vr`, `cNO3t_vr`, `cPO4_vr`, `tNH4_col`, `tNO3_col`, `tMICROB_N_col`.
- `Soil_Mineral_N_P_Supply_To_Roots` (the root-uptake kinetic parameters) affects the same soil-pool outputs (uptake removes from them) plus `UPTK_NH4_FLX_pft`, `UPTK_NO3_FLX_pft`, `UPTK_PO4_FLX_pft`, `prtUP_NH4_pvr`, `Root_NONSTN_pft`, `Root_NONSTP_pft`, `Plant_N_pft`, `Plant_P_pft`.
- `Plant_Nonstructural_N_P_To_Leaf_Protein` (PTSHT, CNLF, CPLF, CNWL, CPWL) affects `Root_NONSTN_pft`, `SHOOT_NONSTN_pft`, `ShootRoot_XFER_N_pft`, `LEAF_N_pft`, `LEAF_P_pft` and `CAN_GPP_pft`.

The shared soil-pool outputs are the join between the microbial and the root mechanisms, `Root_NONSTN_pft` the join between root uptake and the leaf, and `CAN_GPP_pft` the join with the photosynthesis mechanisms.
