---
**Source pin:** EcoSIM commit `cb243228` (jingtao-lbl/EcoSIM `fix/r2-plant-balance`; upstream `09eb674a` + 2 fix commits) · patched to `0340d71b` (see the wiki `index.md`, Patches applied)
**Scope:** `f90src/Plant_bgc/{StomatesMod,PhotoSynsMod,PlantMathFuncMod,SurfaceRadiationMod,PlantBranchMod,GrosubsMod,UptakesMod,PlantBalMod}.F90`, `f90src/IOutils/PlantInfoMod.F90`, `f90src/Modelpars/PlantBGCPars.F90`
**Last verified:** 2026-10-15
---

# Photosynthesis, Stomata, Canopy Radiation and Plant Respiration

EcoSIM computes leaf CO2 fixation with a Grant (1989) biochemical model in which the enzyme and chlorophyll capacities are not prescribed but derived each hour from a prognostic leaf protein pool. C3 plants fix CO2 with Rubisco in the mesophyll; C4 plants run a two-compartment scheme with PEP carboxylase in the mesophyll and Rubisco re-fixation in the bundle sheath. Stomatal resistance is not a Ball-Berry or Medlyn closure: an unstressed resistance is obtained from the CO2 gradient divided by the carboxylation rate, then raised toward the cuticular resistance by an exponential function of canopy turgor. Autotrophic respiration is maintenance (proportional to structural N) plus growth respiration (oxidation of nonstructural C beyond maintenance, limited by turgor and nonstructural N and P). All temperature responses are Arrhenius curves evaluated at the organ temperature shifted by a PFT thermal-adaptation offset derived from ZTYPI.

Leaf protein itself is built in `GrowLeavesOnBranch` (`f90src/Plant_bgc/PlantBranchMod.F90:3561-3562`) as `LeafProteinC_node += AMIN1(GrowthElms(N)*rProteinC2LeafN_pft, GrowthElms(P)*rProteinC2LeafP_pft)`, where `rProteinC2LeafN_pft` is CNWL and `rProteinC2LeafP_pft` is CPWL; that colimitation belongs to the allocation page (topic 02, mechanism `Leaf_Protein_Colimitation`). This page starts from the protein pool and follows it to GPP, stomatal resistance, transpiration and respiration.

## 1. Call sites and hourly order

The plant model runs once per hour per column in `PlantModel` (`f90src/APIs/PlantMod.F90`). The order matters for two outputs in §12:

```
PlantModel                                      (APIs/PlantMod.F90)
  EnterPlantBalance          :73   -> ZeroGrosub zeroes GrossCO2Fix_pft, GrossResp_pft      (PlantBalMod.F90:734, :503-504)
  RootUptakes                :87   (UptakesMod.F90:51)
    PhotosynsDiag            UptakesMod.F90:143   enzyme and chlorophyll pools per branch, Vcmax25/Jmax25 per PFT
    StomatalDynamics         UptakesMod.F90:149   Ca, Ci = FCO2*Ca, minimum stomatal resistance
      PhotoActivePFT         StomatesMod.F90:272
        PrepPhotosynthesis   StomatesMod.F90:1017 solubilities, Arrhenius factors, Km
        PhenoActiveBranch    StomatesMod.F90:1035 N/P feedback, then LiveBranchPhotosynthesis -> C3/C4Photosynthesis
    CanopyEnergyH2OIter_func canopy energy/water loop; StomatalDynamics re-called at convergence (UptakesMod.F90:1074, :1126)
    SetCanopyGrowthFuncs     UptakesMod.F90:225   growth temperature functions
  GrowPlants                 :88   (GrosubsMod.F90:61)
    GrowOnePlant -> StagePlantForGrowth          TFN5, TFN6_vr, Stomata_Stress  (GrosubsMod.F90:308)
                 -> GrowOneBranch                 (GrosubsMod.F90:314; PlantBranchMod.F90:47)
                      UpdatePhotosynthates        (PlantBranchMod.F90:147)
                        ComputeGPP                (:857)  -> ComputeGPP_C3 or ComputeGPP_C4
                        ComputRAutoAfEmergence    (:862)  or ComputRAutoB4Emergence (:874)
                      C4PhotoProductTransfer      (:159, C4 only)
    Live2DeadTransformation  GrosubsMod.F90:117   NetPrimProduct_pft = GrossCO2Fix_pft + GrossResp_pft (:253)
  ExitPlantBalance           :95   -> CheckPlantBalanceZ -> SumPlantBiome sets GrossResp_pft (PlantBalMod.F90:757, :834, :101)
```

The node-level biochemistry (`Vmax4RubiscoCarboxy_node`, `CO2CompenPoint_node`, `LigthSatCarboxyRate_node`, `RubiscoCarboxyEff_node`, `RubiscoActivity_brch`) is computed inside `RootUptakes` by `StomatalDynamics` and consumed later the same hour by `ComputeGPP` inside `GrowPlants`. `ComputeGPP` runs only after the branch has emerged (`f90src/Plant_bgc/PlantBranchMod.F90:855`, `UpdatePhotosynthates`).

## 2. Photosynthesis type dispatch (C3 vs C4)

`ICTYP` is read into `iPlantPhotosynsType_pft` (`f90src/IOutils/PlantInfoMod.F90:1722`, `ReadPlantTraitTable`; copied at `:714`, `SetPlantTraits`). The two values are `ic4_photo=4` and `ic3_photo=3` (`f90src/Modelconfig/ElmIDMod.F90:47-48`). Four places branch on it:

| where | routine | C4 branch | C3 branch |
|---|---|---|---|
| `StomatesMod.F90:127-155` | `PhotosynsDiag` | bundle-sheath Rubisco, mesophyll PEP, split chlorophyll | mesophyll Rubisco and chlorophyll |
| `StomatesMod.F90:794-799` | `LiveBranchPhotosynthesis` | calls `C4Photosynthesis` | calls `C3Photosynthesis` |
| `PhotoSynsMod.F90:505-523` | `ComputeGPP` | `ComputeGPP_C4` when `Vmax4PEPCarboxy_node > 0` | `ComputeGPP_C3` when `Vmax4RubiscoCarboxy_node > 0` |
| `PlantBranchMod.F90:158-160` | `GrowOneBranch` | `C4PhotoProductTransfer` | nothing |

`O2I_pft` (leaf gaseous O2) is also set by type: 2.10E5 for C3 and 3.96E5 for C4 (`f90src/Plant_bgc/InitPlantMod.F90:193-197`, `InitShootGrowth`). A value of ICTYP other than 3 or 4 matches no branch: no carboxylation routine runs and `ComputeGPP` adds no fixation.

## 3. Leaf protein to enzyme and chlorophyll pools

### 3.1 Read-time rescale of the specific activities

The live reader is `ReadPlantTraitTable` (`PlantInfoMod.F90:1708-1849`); `SetPlantTraits` copies the table row for each PFT (`PlantInfoMod.F90:731-744`), and then `ReadPlantProperties` multiplies four of them (`PlantInfoMod.F90:507-510`):

```
VmaxSpecRubCarboxyRef_pft = 1.92*VmaxSpecRubCarboxyRef_pft   ! VCMX
VmaxRubOxyRef_pft         = 1.92*VmaxRubOxyRef_pft           ! VOMX
VmaxPEPCarboxyRef_pft     = 1.92*VmaxPEPCarboxyRef_pft       ! VCMX4
SpecLeafChlAct_pft        = 1.35*SpecLeafChlAct_pft          ! ETMX
```

The copy precedes the multiplication every time `ReadPlantProperties` runs (`PlantInfoMod.F90:489`), so the factor is applied once and does not compound. The comment above the block reads "2.5 converts g enzyme mass into g enzyme C", which matches neither factor. Every equation below uses the rescaled value. The file declares VCMX in `umol C g-1 s-1` (`input_data/ecosim_pftpar_20260915.nc.cdl`).

### 3.2 Branch pools and canopy Vcmax25/Jmax25 (`PhotosynsDiag`)

`PhotosynsDiag` (`f90src/Plant_bgc/StomatesMod.F90:31-200`) loops over branches that are photosynthetically active: evergreen, or leaf-out hours reached, or leaf-off hours not yet reached (`:115-117`). For each node with leaf area and leaf C:

| quantity | C4 branch (`ic4_photo`) | C3 branch (`ic3_photo`) |
|---|---|---|
| Rubisco C | `BundlSheathRubiscoC = LeafProteinC_node*RUBP` (`:128`) | `MesophyllRubiscoC = LeafProteinC_node*RUBP` (`:146`) |
| chlorophyll C | bundle sheath `*CHL*(1-fCHLMESO)/5.5` (`:129`); mesophyll `*CHL*fCHLMESO/3.7` (`:131`) | mesophyll `*CHL/3.5` (`:145`) |
| PEP carboxylase C | `MesophyllPEPC = LeafProteinC_node*PEPC` (`:130`) | none |
| Vcmax25 (Rubisco) | `+= VCMX*BundlSheathRubiscoC` (`:134`) | `+= VCMX*MesophyllRubiscoC` (`:148`) |
| Vomax25 | `+= VOMX*BundlSheathRubiscoC` (`:135`) | `+= VOMX*MesophyllRubiscoC` (`:149`) |
| Vcmax25 (PEP) | `+= VCMX4*MesophyllPEPC` (`:133`) | none |
| Jmax25 | `+= ETMX*MesophyllChlC` (`:156`, both branches; for C4 only the mesophyll chlorophyll) | same line |

Branch sums are totalled per PFT (`:161-170`) and divided by total leaf area when it exceeds 5e-3 (`:174-185`), giving `CanopyVcMaxRubisco25C_pft`, `CanopyVoMaxRubisco25C_pft`, `CanopyVcMaxPEP25C_pft`, `ElectronTransptJmax25C_pft` and `SpecificLeafArea_pft`. These are diagnostics written to `VcMax25C_RUBISCO_pft`, `VoMax25C_RUBISCO_pft`, `VcMax25C_PEP_pft` and `JMax25C_photo_pft` (`f90src/IOutils/HistData/HistUpdatePlant.F90:222-225`); the fixation itself recomputes the same products per node (§6, §7). The divisors 3.5, 3.7 and 5.5 are gC protein per gC chlorophyll per the inline comments.

## 4. Canopy radiation seen by photosynthesis

`PlantCanopyRadsModel` (`f90src/APIs/PlantMod.F90:127-140`) calls `CanopyConditionModel` (`f90src/Plant_bgc/SurfaceRadiationMod.F90:49`), which updates optical properties (`:72`) and then runs `SurfaceRadiation` (`:74`).

**Optical properties** (`UpdateOpticalProperties`, `SurfaceRadiationMod.F90:1616-1827`). The live-leaf clumping factor is `ClumpFactorNow_pft = ClumpFactor_pft*(1-0.025*CanopyLeafArea_pft/AREA3)` (`:1654`), where `ClumpFactor_pft` starts at CFI (`InitPlantMod.F90:187`), and is cut by `1-0.2*fSnowCanopy_pft` under canopy snow (`:1660`). With snow present, leaf SW and PAR albedo and transmittance are blended with snow values (`:1662-1665`); without snow the file values ALBR, ALBP, TAUR, TAUP are used directly (`:1758-1761`). Absorptivity is `1 - albedo - transmittance` (`:1773-1774`), and albedo and transmittance are then divided by absorptivity (`:1782-1785`), so ALBP and TAUP only make sense together.

**Sunlit and shaded fractions** (`DownwellSweep`, `:742-899`). Sweeping top-down, `TAU_DirectSunLit(L) = 1 - FractionDirRadAbsorbtCum` and `TAU_DirectSunSha(L) = 1 - TAU_DirectSunLit(L)` (`:884-885`): the fraction of leaves in layer L reached and not reached by the direct beam. Each layer's interception uses effective areas `LeafAreaZsecLive*ClumpFactorNow_pft` (`:1480`, `DownwellRadiationCanopyZL`) for the leaves and a stem clumping factor fixed by growth habit (`:1655`).

**Absorbed PAR per sector.** For each inclination class N, sky azimuth M and layer L, the shaded leaf absorbs only diffuse PAR (`RadDifPARAbsorption_zsec`, accumulated at `:1559` and rescaled at `:1195`), and the sunlit leaf absorbs direct plus diffuse, `RadDirPAR2Leaf_zsec*LeafPARabsorptivityL_pft + RadDifPARAbsorption_zsec` (`:1196`, `AccumulateRadation4CanopyL`). The leaf area that photosynthesises in each sector is `LeafEffArea_zsec = LeafAreaZsec_brch*ClumpFactorNow_pft` (`:726`, `MultiCanopyLayerRadiation`), and `LeafAreaZsec_brch` is the layer leaf area times the CLASS inclination fraction divided by the number of leaf azimuth sectors (`PlantBranchMod.F90:2025`, `LeafClassAllocation`). WDLF (leaf length:width) sets leaf length, which places each node's leaf area into canopy layers (`PlantBranchMod.F90:1834`, `AllocateLeaf2CanopyLayers`).

**PFT share of PAR.** `FracPARads2LiveCanopy_pft = FRadPARbyLeafT*LeafStalkAreaAct_pft/LeafStalkAreaAll_col` with `FRadPARbyLeafT = 1-EXP(-k*LAIEff)`, k = 0.65 for snow-free and 0.8 for snow-covered canopy (`SurfaceRadiationMod.F90:588-599`, `SurfaceRadiation`). It enters the minimum stomatal resistance (§5). When `ldo_radiation_test` is set the multilayer scheme is skipped (`:545-555`) and `LeafEffArea_zsec` is not updated.

## 5. Stomatal dynamics, CO2 side

`StomatalDynamics` (`f90src/Plant_bgc/StomatesMod.F90:202-280`) works at PFT level:

```
RI                      = RichardsonNumber(RIB, TairK, TKCanopy_pft)                         ! :246
CanopyCO2BndlResist_pft = 1.34*AMAX1(5.56E-03, RawIsoTCanopy2Atm_pft/(1-10*RI))              ! :247
CanopyGasCO2_pft        = CO2E - 8.33E+04*NetCO2Flx2Canopy_col*CanopyCO2BndlResist_pft/AirConc_pft  ! :258
CanopyGasCO2_pft        = AMIN1(CO2E+200, AZMAX1(CO2E-200, CanopyGasCO2_pft))               ! :259
LeafIntracellularCO2_pft = CanopyCi2CaRatio_pft*CanopyGasCO2_pft                              ! :268, FCO2
```

The source comment at `:257` reads "how 8.33E+04 is determined", i.e. the constant is undocumented. With the sun up and leaf area present, `PhotoActivePFT` is called (`:270-272`); otherwise the minimum resistance is the cuticular one (`:275`).

`PrepPhotosynthesis` (`:898-980`) converts Ci to aqueous concentrations with temperature-dependent solubilities, `CO2Solubility_pft = EXP(-2.621-0.0317*TCCZ)` and `LeafO2Solubility_pft = EXP(-6.175-0.0211*TCCZ)` (`:939-940`), sets `aquCO2Intraleaf_pft = Ci*CO2Solubility_pft` and `O2L_pft = O2I_pft*LeafO2Solubility_pft` (`:941-942`), and the gradient `DiffCO2Atmos2Intracel_pft = AirConc_pft*(Ca - Ci)` (`:943`). These are computed, not read.

`PhotoActivePFT` (`:983-1069`) runs the node biochemistry for every active branch (§6, §7), summing `CH2O`, the fixation rate evaluated at the FCO2 Ci. Inactive branches get `RubiscoActivity_brch = 0` and zero node capacities (`:1038-1043`). Then (`:1059-1065`):

```
RSX = FracPARads2LiveCanopy_pft*DiffCO2Atmos2Intracel_pft*AREA3/(CH2O*3600)    ! h m-1, to CO2
CanopyMinStomaResistH2O_pft = AMIN1(H2OCuticleResist_pft, AMAX1(RSMY_stomaCO2, RSX/1.56))
```

with `RSX = 1.56*H2OCuticleResist_pft` when nothing is fixed. `RSMY_stomaCO2 = 2.78E-03` h m-1 (`f90src/Modelpars/PlantBGCPars.F90:257`). So the unstressed transpiration resistance falls as fixation capacity rises, and falls as FCO2 rises (a smaller `Ca - Ci` gradient); it is the turgor-free end of the resistance in §8.

## 6. C3 photosynthesis

### 6.1 Node biochemistry (`C3Photosynthesis`, C3 branch)

In `f90src/Plant_bgc/StomatesMod.F90:376-481`, with `ProteinCLeafAreaDensity = LeafProteinC_node/LeafArea_node` (`:785`, `LiveBranchPhotosynthesis`):

```
MesophyllRubiscoSurfDensity = RUBP*ProteinCLeafAreaDensity                                         ! :422
MesophyllChlDensity         = CHL*ProteinCLeafAreaDensity/3.5                                      ! :423
VcMaxRubiscoRef_node        = VCMX*MesophyllRubiscoSurfDensity                                     ! :441
VoMaxRubiscoRef_node        = VOMX*MesophyllRubiscoSurfDensity                                     ! :442
Vmax4RubiscoCarboxy_node    = VcMaxRubiscoRef_node*TFN_Carboxy                                     ! :443
VOGRO                       = VoMaxRubiscoRef_node*TFN_Oxygen                                      ! :444
CO2CompenPoint_node         = 0.5*O2L_pft*VOGRO*Km4LeafaqCO2_pft/(Vmax4RubiscoCarboxy_node*Km4RubOxy)   ! :445
! Eq. (1) of Grant, 1989                                                                            ! :446
CO2lmtRubiscoCarboxyRate_node = AZMAX1(Vmax4RubiscoCarboxy_node*(Cc - Gamma)/(Cc + Km4RubiscoCarboxy_pft))  ! :447-448
ElectronTransptJmaxRef_node = ETMX*MesophyllChlDensity                                             ! :461
LigthSatCarboxyRate_node    = ElectronTransptJmaxRef_node*TFN_eTranspt                             ! :462
RubiscoCarboxyEff_node      = AZMAX1((Cc - Gamma)/(ELEC3*Cc + 10.5*Gamma))                          ! :463-464
```

`Cc` is `aquCO2Intraleaf_pft` (uM) and Gamma the compensation point. The compensation point depends on the VOMX/VCMX ratio and on both Km values. With `TFN_Oxygen/TFN_Carboxy` it also carries the temperature dependence of photorespiration.

**From the node rates to the minimum stomatal resistance (C3).** `C3Photosynthesis` then calls `C3PhotosynsCanopyLayerL` for every canopy layer with leaf area (`StomatesMod.F90:473-477`), which calls `C3FixCO2` for every sunlit and shaded sector with PAR (`:366`, `C3PhotosynsCanopyLayerL`). There, at the FCO2 Ci and without any turgor or water term:

```
EGRO = ETLF*RubiscoCarboxyEff_node                                                   ! :312   (ETLF from the light curve, :309-311)
VL   = AMIN1(CO2lmtRubiscoCarboxyRate_node, EGRO)*RubiscoActivity_brch               ! :324
CH2O = CH2O + VL*LeafEffArea_zsec*TAU_Rad                                            ! :325
```

`CH2O` is summed over sectors, layers, nodes and active branches and returned to `PhotoActivePFT`, which forms `RSX` and `CanopyMinStomaResistH2O_pft` from it (`:1059-1065`; section 5). The full chain is therefore `MesophyllRubiscoSurfDensity` (`:422`) -> `VcMaxRubiscoRef_node` (`:441`) -> `Vmax4RubiscoCarboxy_node` (`:443`) -> `CO2lmtRubiscoCarboxyRate_node` (`:447-448`) -> `VL` and `CH2O` (`:324-325`, `C3FixCO2`) -> `RSX` (`:1060`) -> `CanopyMinStomaResistH2O_pft` (`:1065`, `PhotoActivePFT`): more Rubisco per leaf area gives a larger carboxylation rate and a lower minimum resistance, down to the floor `RSMY_stomaCO2`.

### 6.2 Fixation and the Ci solve (`ComputeGPP_C3`, C3 branch)

`ComputeGPP_C3` (`f90src/Plant_bgc/PhotoSynsMod.F90:25-222`) loops over canopy layers top-down, inclination classes, sky azimuths and the two leaf populations: sunlit uses `RadTotPARAbsorption_zsec` with weight `TAU_DirectSunLit(L+1)`, shaded uses `RadDifPARAbsorption_zsec` with weight `TAU_DirectSunSha(L+1)` (`:95-104`). For PAR > 0:

```
PARX = QNTM*PAR_zsec ; PARJ = PARX + LigthSatCarboxyRate_node                                        ! :121-122
ETLF = (PARJ - SQRT(PARJ**2 - CURV4*PARX*LigthSatCarboxyRate_node))/CURV2                         ! :124
VL   = AMIN1(CO2lmtRubiscoCarboxyRate_node, ETLF*RubiscoCarboxyEff_node)*RubiscoActivity_brch      ! :125-126
RS   = AMIN1(CO2CuticleResist_pft, AMAX1(RCMN, DiffCO2Atmos2Intracel_pft/VL))                       ! :139
RSL  = RS + (CO2CuticleResist_pft - RS)*Stomata_Stress                                              ! :140
GSL  = AirConc_pft/RSL                                                                              ! :141
WFNB = SQRT(RS/RSL)   (vascular)   or   PsiCan4Photosyns   (bryophyte)                              ! :148-152
```

`RS` is the unstressed resistance (CO2 gradient at the FCO2 Ci divided by the first fixation estimate), bounded by `RCMN = 15.6` s m-1 (`PlantBGCPars.F90:230`) and the cuticular resistance; `RSL` moves it toward the cuticular value as turgor falls (§8). Ci is then solved by fixed-point iteration, at most 100 passes, until carboxylation and diffusion agree within 0.5% (`PhotoSynsMod.F90:171-192`):

```
CO2C  = CO2X*CO2Solubility_pft ;  CO2Y = AZMAX1(CO2C - Gamma)
VGROX = Vmax4RubiscoCarboxy_node*CO2Y/(CO2C + Km4RubiscoCarboxy_pft)          ! CO2-limited
EGROX = ETLF*CO2Y/(ELEC3*CO2C + 10.5*Gamma)                                    ! light-limited
VL    = AMIN1(VGROX, EGROX)*WFNB*RubiscoActivity_brch*VLScal                   ! VLScal = 1 (PhotoSynsMod.F90:19)
VG    = (CanopyGasCO2_pft - CO2X)*GSL
CO2X  = CanopyGasCO2_pft - (0.95*VG + 0.05*VL)/GSL                              ! damped update
```

At convergence (`:194-212`) the sector adds `VL*LeafEffArea_zsec*TAU` to the node product, `VGROX*...` and `EGROX*...` to the CO2-limited and light-limited diagnostics, and `CO2X*clscal` to the Ci accumulator that becomes `DynCi2CaRatio_pft` (§12). `QNTM = 0.45`, `CURV = 0.70`, `ELEC3 = 4.5` (`PlantBGCPars.F90:234-238`).

## 7. C4 photosynthesis

### 7.1 Node biochemistry (`C4Photosynthesis`, C4 branch)

In `StomatesMod.F90:484-662`, mesophyll first:

```
CC4M = AZMAX1(0.021E+09*CPOOL4_node/(LeafC*FWCMesophyll))                                     ! :549
CCBS = AZMAX1(0.083E+09*CMassCO2BundleSheath_node/(LeafC*FWCBundlSheath))                     ! :550
NutrientCtrlonC4Carboxy_node = GrainFillDowreg_brch/(1 + CC4M/C4KI_pepcarboxy)                   ! :552-553
MesophyllPEPSurfDensity = ProteinCLeafAreaDensity*PEPC                                          ! :563
MesophyllChlDensity     = ProteinCLeafAreaDensity*CHL*fCHLMESO/3.7                              ! :564
Vmax4PEPCarboxy_node      = VCMX4*MesophyllPEPSurfDensity*TFN_Carboxy                           ! :577-578
CO2lmtPEPCarboxyRate_node = AZMAX1(Vmax4PEPCarboxy*(Cc - COMP4)/(Cc + Km4PEPCarboxy_pft))         ! :579-580, Km = XKCO24
LigthSatC4CarboxyRate_node = ETMX*MesophyllChlDensity*TFN_eTranspt                              ! :594-595
C4CarboxyEff_node          = AZMAX1((Cc - COMP4)/(ELEC4*Cc + 10.5*COMP4))                       ! :596
```

then the bundle sheath, driven by the bundle-sheath CO2 `CCBS` instead of Ci:

```
BundlSheathRubiscoSurfDensity = ProteinCLeafAreaDensity*RUBP                                    ! :619
BundlSheathChlDensity         = ProteinCLeafAreaDensity*CHL*(1-fCHLMESO)/5.5                     ! :620
VcMaxRubiscoRef_node = VCMX*BundlSheathRubiscoSurfDensity ; VoMaxRubiscoRef_node = VOMX*...     ! :639, :641
CO2lmtRubiscoCarboxyRate_node = AZMAX1(Vmax4RubiscoCarboxy*(CCBS - Gamma)/(CCBS + Km4RubiscoCarboxy_pft))  ! :644-645
LigthSatCarboxyRate_node = ETMX*TFN_eTranspt*BundlSheathChlDensity                              ! :658
RubiscoCarboxyEff_node   = AZMAX1((CCBS - Gamma)/(ELEC3*CCBS + 10.5*Gamma))                       ! :659
```

`COMP4 = 0.5` uM, `ELEC4 = 3.0`, `FWCMesophyll = 0.8*FWCLeaf`, `FWCBundlSheath = 0.2*FWCLeaf`, `FWCLeaf = 6.0`, `C4KI_pepcarboxy = 5.0E6` (`PlantBGCPars.F90:239-246`, `:258`). In a C4 PFT, VCMX, VOMX, RUBP and XKCO2 act only in the bundle sheath, and fCHLMESO divides CHL between the compartments; CHL has no fCHLMESO term in the C3 branch.

### 7.2 Fixation (`ComputeGPP_C4`, C4 branch)

`ComputeGPP_C4` (`PhotoSynsMod.F90:225-451`) uses the same light curve with `LigthSatC4CarboxyRate_node` and the same `RS/RSL/GSL` construction (`:325-344`), but the non-stomatal factor differs by compartment: `WFN4 = RS/RSL` for the PEP step and `WFNB = SQRT(RS/RSL)` for the bundle sheath, both `PsiCan4Photosyns` for bryophytes (`:351-357`). The Ci iteration solves the PEP rate with `COMP4`, `ELEC4` and XKCO24 (`:376-395`). The bundle-sheath rate is not iterated: `VL = AMIN1(CO2lmtRubiscoCarboxyRate_node, EGRO)*WFNB*RubiscoActivity_brch` (`:430-433`), accumulated into `CH2O3K` (`:441`).

### 7.3 Product transfer and leakage (`C4PhotoProductTransfer`, C4 only)

Per node (`f90src/Plant_bgc/PlantBranchMod.F90:896-989`): bundle-sheath fixation leaves `CPOOL3_node` and mesophyll fixation enters `CPOOL4_node` (`:933-934`); C4 product moves down a water-weighted gradient (`:935-937`); bundle-sheath decarboxylation `CPL3K = 2.5E-02*CPOOL3_node/(1+CCBS/CO2KI)` feeds `CMassCO2BundleSheath_node` and `CMassHCO3BundleSheath_node` in proportion 0.02:0.98 (`:951-954`); leakage `5.0E-07*(CCBS - aquCO2Intraleaf_pft)*LeafC*FWCBundlSheath` (`:966`) is charged as autotrophic respiration to `CanopyGrosRCO2_pft`, `CO2NetFix_pft`, `ECO_ER_col` and `Eco_AutoR_CumYr_col` (`:979-984`).

## 8. Turgor, stomatal stress and transpiration

**Turgor.** `update_osmo_turg_pressure` (`f90src/Plant_bgc/PlantMathFuncMod.F90:52-75`) computes, from organ water potential `PSIOrgan`, total nonstructural concentration `CCPOLT` and OSMO:

```
FDMP    = 0.16 + 0.10*|PSIOrgan|/(0.05*|PSIOrgan| + 2.0)    ; FDMP0 = 0.16           ! :46-47 (get_FDM)
OSWT    = 36.0 + 840.0*AZMAX1(CCPOLT)                                                ! :70
PSIOsmo = FDMP*(OSMO/FDMP0 - RGASC*TKP*CCPOLT/OSWT)                                  ! :71
PSITurg = AZMAX1(PSIOrgan - PSIOsmo)                                                 ! :72
```

A more negative OSMO lowers the osmotic potential and raises turgor at a given water potential. The canopy call is inside the energy-water iteration (`f90src/Plant_bgc/UptakesMod.F90:832-833`, `CanopyEnergyH2OIter_func`); roots use the same routine with root water potential (`UptakesMod.F90:640`, `HandlingDivergence`; `:1557`, `UpdatePlantWaterVars`).

**Stomatal stress.** Two routines evaluate `Stomata_Stress = EXP(-PSICanopyTurg_pft/RCS)`: `StagePlantForGrowth` for photosynthesis (`f90src/Plant_bgc/GrosubsMod.F90:554`), where bryophytes get 1 (`:548-551`), and `CalcStomataResist4H2O` for transpiration (`PlantMathFuncMod.F90:569`). Full turgor drives the stress toward 0 (open, unstressed resistance); zero turgor gives 1 (cuticular resistance). A larger RCS slows that decay, so more turgor is needed to open the stomata. The value is written to `STOMATAL_STRESS_pft` (`HistUpdatePlant.F90:258`).

**Transpiration resistance and flux.**

```
CanPStomaResistH2O_pft = CanopyMinStomaResistH2O_pft + (H2OCuticleResist_pft - CanopyMinStomaResistH2O_pft)*Stomata_Stress   ! PlantMathFuncMod.F90:570
Transpiration_pft      = EX*RawCanopy2Atm_pft/(RawCanopy2Atm_pft + CanPStomaResistH2O_pft)                                   ! UptakesMod.F90:899
```

`EX` is the canopy-air vapour gradient times the aerodynamic conductance (`UptakesMod.F90:857`). The two cuticular resistances come from RSMX: `H2OCuticleResist_pft = RSMX/3600` (h m-1) and `CO2CuticleResist_pft = RSMX*1.56` (s m-1, 1.56 = sqrt(44/18)) (`f90src/Plant_bgc/InitPlantMod.F90:189-190`, `InitShootGrowth` on planting day; the same lines run in the first model year at `f90src/Ecosim_mods/StartqMod.F90:176-177`, reached from `drivers/ecosim/EcoSIMAPI.F90:437`). When the canopy water balance converges, `StomatalDynamics` is called again with the converged state and the loop makes one more pass (`UptakesMod.F90:1071-1075`, `:1123-1126`). Resistance outputs: `STOML_RSC_CO2_pft = 1.56*3600*CanPStomaResistH2O_pft` and `STOML_MinRSC_CO2_pft` from the minimum (`HistUpdatePlant.F90:163-164`).

## 9. Temperature functions and the ZTYPI offset

**Thermal-adaptation offset.** `rPlantThermoAdaptZone_pft = ZTYPI` and `TempOffset_pft = 2.667*(2.5 - rPlantThermoAdaptZone_pft)` °C (`InitPlantMod.F90:485-487`, `PFTThermalAcclimation`, on planting day; `StartqMod.F90:450-451` in the first model year). ZTYPI is a coded zone (the display labels bands 1 arctic/boreal to 5 tropical, `f90src/IOutils/PlantInfoMod.F90:1092-1103` with constants `ElmIDMod.F90:171-175`), but every physics use treats it as a real number and the shipped file carries 1.2, 1.5 and 2.5; ZTYPI = 1 gives +4.0 °C, 2.5 gives 0, 5 gives -6.67. When `ICLM.EQ.2` the zone drifts with the climate anomaly, `rPlantThermoAdaptZone_pft = ZTYPI + 0.30/2.667*DTA` (`f90src/Modelforc/WthrMod.F90:476-477`, `CorrectClimate`). The same offset sets the leaf-out and leaf-off thresholds and a seed heat limit (`InitPlantMod.F90:488-499`; phenology page, topic 02).

**Photosynthesis** (`StomatesMod.F90:957-977`, `PrepPhotosynthesis`), with `TKCO = TKCanopy_pft + TempOffset_pft` and `RTK = 8.3143*TKCO`:

```
ACTV         = 1 + EXP((197500 - 710*TKCO)/RTK) + EXP((710*TKCO - 222500)/RTK)
TFN_Carboxy  = EXP(26.237 - 65000/RTK)/ACTV
TFN_Oxygen   = EXP(24.220 - 60000/RTK)/ACTV
TFN_eTranspt = EXP(17.362 - 43000/RTK)/ACTV
Km4LeafaqCO2_pft      = XKCO2*EXP(16.136 - 40000/RTK)          ! no inactivation term
Km4RubOxy             = XKO2*EXP(8.067 - 20000/RTK)            ! no inactivation term
Km4RubiscoCarboxy_pft = Km4LeafaqCO2_pft*(1 + O2L_pft/Km4RubOxy)   ! "Eq.(1) of Grant, 1989" (:976)
```

**Respiration and growth.** Maintenance uses `calc_plant_maint_tempf`, `EXP(25.214-62500/RTK)/(1+EXP((195000-STK)/RTK)+EXP((STK-232500)/RTK))` (`PlantMathFuncMod.F90:166-177`), at `TKCM = TKC_pft + TempOffset_pft` for the shoot (`TFN5`, `GrosubsMod.F90:501-502`) and `TKSM = TKS_vr(L) + TempOffset_pft` per soil layer (`TFN6_vr`, `:504-507`). Growth uses `calc_canopy_grow_tempf` and `calc_root_grow_tempf` (62500 activation, 197500/222500 inactivation; `PlantMathFuncMod.F90:118-148`) at `TKGroth_pft + TempOffset_pft` and `TKS_vr + TempOffset_pft` (`UptakesMod.F90:1619-1624`, `SetCanopyGrowthFuncs`), giving `fTCanopyGroth_pft` and `fTgrowRootP_vr`. All are 1 at 25 °C after the offset.

## 10. Nutrient, phenology and grain-fill down-regulation

`PhenoActiveBranch` (`StomatesMod.F90:811-895`) sets the multiplier on every C3 and bundle-sheath rate:

```
CNS = Ncon/(Ncon + Ccon*CNKI_rubisco) ; CPS = Pcon/(Pcon + Ccon*CPKI_rubisco)   ! branch nonstructural concentrations
RubiscoActivity_brch = AMIN1(CNS, CPS)                                          ! :845-850 (1 if no nonstructural C)
RubiscoActivity_brch *= AZMAX1(AMIN1(1, Hours2LeafOut_brch/(0.9*276.9)))         ! :866-869, non-evergreen with IBTYP >= 2
GrainFillDowreg_brch = AZMAX1(1 - HourFailGrainFill_brch/Hours2KillAnuals(IWTYP)) ! :877-878, annuals after grain-fill failure
RubiscoActivity_brch *= GrainFillDowreg_brch                                     ! :882
```

`CNKI_rubisco = 0.01`, `CPKI_rubisco = 0.001` (`PlantBGCPars.F90:255-256`), `Hours2KillAnuals = (336, 672, 672, 672, 672, 672)` (`StomatesMod.F90:24`). C4 mesophyll carboxylation uses `NutrientCtrlonC4Carboxy_node` (§7.1) instead. `ComputeGPP` returns zero fixation for a branch whose `RubiscoActivity_brch` is 0 (`PhotoSynsMod.F90:485`).

## 11. Maintenance and growth respiration

### 11.1 Shoot branch after emergence (`ComputRAutoAfEmergence`)

In `f90src/Plant_bgc/PlantBranchMod.F90:3107-3300`:

```
CNPG = AMIN1(CN/(CN + CC*CNKI), CP/(CP + CC*CPKI))                                   ! :3165-3170, CNKI 0.10, CPKI 0.01
RCO2NonstC_brch = AZMAX1(VMXC*CanopyNonstElms_brch(C)*fTCanopyGroth_pft)*CNPG*GrainFillDowreg_brch*WaterStress4Groth   ! :3191-3192
RCO2Maint_brch  = AZMAX1(RmSpecPlant*TFN5*ShootStructN_brch)  (*WaterStress4Groth for bryophytes and drought-deciduous)  ! :3205-3209
RCO2X = RCO2NonstC_brch - RCO2Maint_brch ; RCO2Y = AZMAX1(RCO2X)*TurgEff4CanopyResp ; RMxess_brch = AZMAX1(-RCO2X)      ! :3220-3222
RgroCO2_ltd = AMIN1(RCO2Y, ZPOOL*YCO2Gro_brch/(CNSHX+CNLFM+CNLFX*CNPG), PPOOL*YCO2Gro_brch/(CPSHX+CPLFM+CPLFX*CNPG))   ! :3237-3246
RCO2NonstC4Nassim_brch = AZMAX1(1.70*CanopyNonstElm4Gros(N) - 0.025*CH2O)                                              ! :3269
Rauto_brch = AMIN1(RCO2Maint_brch, RCO2NonstC_brch) + RgroCO2_ltd + RCO2NonstC4Nassim_brch                              ! :3288
```

`VMXC = 0.015` h-1, `RmSpecPlant = 0.010` gC gN-1 h-1, `CNKI = 0.10`, `CPKI = 0.01` (`PlantBGCPars.F90:217`, `:226-228`). `WaterStress4Groth = EXP(0.10*AMAX1(PSICanopy_pft,-5000))` (0.05 for bryophytes) and `TurgEff4CanopyResp = (AMIN1(1, AZMAX1(PSICanopyTurg_pft - 0.1)))**0.25` (`**0.10` for bryophytes) (`GrosubsMod.F90:546-558`; `PlantMathFuncMod.F90:333-346`), so OSMO reaches growth respiration through turgor. `YCO2Gro_brch = 1 - sum(PART*growth yield)` over leaf, sheath, stalk, reserve, husk, ear and grain (`PlantBranchMod.F90:512-516`, `UpdateBranchAllometry`); the yields (DMLF, DMSHE, DMSTK, ...) belong to topic 02. The source comment calls the 0.025 term "1/4 newly fixed C is used for N-assimilation (where is this number from?)" (`:3263`). Results are accumulated at `:3289-3296`: `GrossCO2Fix_pft += CO2F`, `CanopyGrosRCO2_pft -= Rauto_brch`, `CO2NetFix_pft += CO2F - Rauto_brch`, `ECO_ER_col -= Rauto_brch`, `Eco_AutoR_CumYr_col -= Rauto_brch`, `RCanMaintDef_CO2_pft -= RMxess_brch`.

A positive `RMxess_brch` (maintenance exceeding nonstructural oxidation) drives remobilization: stalk reserve is oxidised at `RCO2V = AMIN1(RMxess_brch, VMXC*StalkReserveC*fTCanopyGroth_pft)` and leaf remobilization releases `RCO2e`, both charged to the same accumulators (`PlantBranchMod.F90:3820-3829`, `:3925-3931`, `RemobilizeBranch`).

### 11.2 Shoot branch before emergence (`ComputRAutoB4Emergence`)

The same structure applied to a branch still below ground (`PlantBranchMod.F90:3303-3501`): nonstructural oxidation uses the root growth function at the planting layer and the root O2 limiter (`:3381-3384`), maintenance uses `TFN6_vr` at that layer (`:3395`), and the respiration is written into the root pools `RootRespPotent_pvr`, `RootCO2EmisPot_pvr` and `RootCO2Autor_pvr` at `NGTopRootLayer_pft` (`:3495-3497`), reaching the column through the root path below. It is not a root-respiration routine.

### 11.3 Roots and nodules

Root maintenance is `RmSpecPlant*TFN6_vr(L)` times structural root N (for example `f90src/Plant_bgc/RootMod.F90:688`, `Grow2ndRootAxes`), and root respiration is held, negative, in `RootCO2Autor_pvr` (`RootMod.F90:804`). It is added to the column in `ShootRootElmTransfer`: `Eco_AutoR_CumYr_col += RootCO2Autor_pvr` over mycorrhizal types and layers (`f90src/Plant_bgc/PlantNonstElmDynMod.F90:442-443`). Canopy nodules pay `RmSpecPlant*TFN5*nodule N` (`f90src/Plant_bgc/NoduleBGCMod.F90:184`) and charge `Eco_AutoR_CumYr_col` directly (`:326`, `CanopyNoduleBiochemistry`). Root growth respiration, DMRT and the root O2 limiter are on the roots page (topic 03); primary-root maintenance `Rmaint1st_CO2`, including which of its two branches can run on each growth path and how it reaches `RootCO2Autor_pvr`, is in [`roots_and_uptake.md`](roots_and_uptake.md) section 4.

## 12. Producing chains for the scored outputs

**CAN_GPP_pft and CAN_cumGPP_pft.** `GrossCO2Fix_pft` is zeroed each hour (`PlantBalMod.F90:504`, `ZeroGrosub`) and accumulates `CO2F` per branch (`PlantBranchMod.F90:3289`). `CO2F` is mesophyll fixation for C4 and Rubisco fixation for C3 (`PhotoSynsMod.F90:508`, `:520`), converted with `umol2gC_hr = 0.0432` (`:20`, `:531`). `CAN_GPP_pft = GrossCO2Fix_pft/area`, units gC m-2 h-1, `default='inactive'` (`f90src/IOutils/HistData/HistRegisterPlant.F90:33-34`; value at `HistUpdatePlant.F90:155`); `CAN_cumGPP_pft` is the yearly sum `GrossCO2Fix_CumYr_pft` (`f90src/APIs/PlantStateTransferMod.F90:124`; `HistUpdatePlant.F90:83`). Diagnostics `dCAN_GPP_CLIM_pft` and `dCAN_GPP_eLIM_pft` are the CO2-limited and light-limited sums minus actual GPP (`HistUpdatePlant.F90:135-136`), fed by `CO2FixCL_pft`/`CO2FixLL_pft` (`PlantBranchMod.F90:866-867`).

**ECO_GPP_col.** `Eco_GPP_CumYr_col += AZERO(GrossCO2Fix_pft)` per PFT per hour (`PlantStateTransferMod.F90:58`, `ReceivePlantState`), reset each year (`f90src/Modelforc/YearMod.F90:84`, `SetAnnualAccumlators`), written as `ECO_GPP_col` = `Eco_GPP_CumYr_col/area`, gC m-2, `avgflag='I'` (`f90src/IOutils/HistData/HistRegisterColumn.F90:508`; `HistUpdateColumn.F90:202`). It is a within-year running total, not a rate.

**ECO_RA_col.** `Eco_AutoR_CumYr_col` is stored negative and has seven writers: branch respiration after emergence (`PlantBranchMod.F90:3295`), stalk-reserve and leaf remobilization (`:3829`, `:3931`), C4 bundle-sheath leakage (`:984`), canopy nodules (`NoduleBGCMod.F90:326`), roots and pre-emergence branches through `RootCO2Autor_pvr` (`PlantNonstElmDynMod.F90:443`) and grazing (`f90src/Plant_bgc/PlantDisturbByGrazingMod.F90:76`). It is copied to the column (`f90src/APIs/PlantColumnTransferMod.F90:64`, `ReceivePlantColumns`), reset yearly (`YearMod.F90:86`) and written as `ECO_RA_col` (`HistRegisterColumn.F90:512`; `HistUpdateColumn.F90:203`). `ECO_NPP_col` is `Eco_GPP_CumYr_col + Eco_AutoR_CumYr_col` (`f90src/Balances/RedistMod.F90:226`, `UpdateOutputVars`; `HistRegisterColumn.F90:516`), a correct net production.

**NPP_pft carries gross fixation, not net production.** `NetPrimProduct_pft = GrossCO2Fix_pft + GrossResp_pft` is formed in `Live2DeadTransformation` (`GrosubsMod.F90:253`) during `GrowPlants` (`PlantMod.F90:88`). At that point `GrossResp_pft` still holds the zero set by `ZeroGrosub` (`PlantBalMod.F90:503`) in `EnterPlantBalance` (`PlantMod.F90:73`); it is filled with `RootAutoCO2_pft + CanopyGrosRCO2_pft` only later, in `SumPlantBiome` (`PlantBalMod.F90:101`), called from `CheckPlantBalanceZ` (`:834`) in `ExitPlantBalance` (`PlantMod.F90:95`). The only earlier writer is the grazing decrement (`PlantDisturbByGrazingMod.F90:71`). Hence `NPP_pft = NetPrimProduct_pft/area` (`HistUpdatePlant.F90:94`) equals `CAN_GPP_pft` except on grazing hours, as observed on a real tape at 2dea74d9, where the same ordering held. Use `ECO_NPP_col` for net production; a per-PFT net needs `CAN_GPP_pft` plus `CAN_RA_pft` (canopy-only, `HistUpdatePlant.F90:156`) plus the PFT's root respiration.

**DynCi2CaRatio_pft (new at cb243228).** `CO2Intra_pft` and `CO2IntraScal_pft` are zeroed hourly (`PlantBalMod.F90:458-459`) and accumulate the converged Ci weighted by `LeafEffArea_zsec*TAU` (`PhotoSynsMod.F90:195-196`, `:397-398`); `DynCi2CaRatio_pft = (CO2Intra_pft/CO2IntraScal_pft)/CanopyGasCO2_pft`, or FCO2 when the weight is below 1e-5 (`PlantBalMod.F90:829-833`, `CheckPlantBalanceZ`). For C4 it is the mesophyll Ci.

## 13. Hard-coded constants (`PlantBGCPars.F90:217-259`)

| name | value | line | role |
|---|---|---|---|
| `VMXC` | 0.015 h-1 | `:217` | nonstructural C oxidation rate |
| `CNKI`, `CPKI` | 0.10, 0.01 | `:226-227` | N, P limitation of growth respiration |
| `RmSpecPlant` | 0.010 gC gN-1 h-1 | `:228` | maintenance per structural N at 25 °C |
| `TurgPSIMin4OrganExtens` | 0.1 MPa | `:229` | turgor threshold for expansion |
| `RCMN` | 15.6 s m-1 | `:230` | minimum leaf CO2 resistance |
| `QNTM`, `CURV` | 0.45, 0.70 | `:234-235` | quantum yield, light-curve shape |
| `ELEC3`, `ELEC4` | 4.5, 3.0 | `:238-239` | e- per CO2, Rubisco and PEP |
| `CO2KI` | 1.0E3 uM | `:240` | bundle-sheath decarboxylation inhibition |
| `FCMassCO2BundleSheath_node` | 0.02 | `:241` | CO2 share of decarboxylation |
| `COMP4` | 0.5 uM | `:243` | C4 compensation point |
| `FWCLeaf` | 6.0 | `:244` | leaf water per C; mesophyll 0.8, sheath 0.2 shares |
| `CNKI_rubisco`, `CPKI_rubisco` | 0.01, 0.001 | `:255-256` | N, P feedback on Rubisco |
| `RSMY_stomaCO2` | 2.78E-03 h m-1 | `:257` | floor of minimum stomatal resistance |
| `C4KI_pepcarboxy` | 5.0E6 uM | `:258` | C4 product inhibition of PEP carboxylation |
| `Hours4ConiferSpringDeharden` | 276.9 h | `:259` | spring dehardening |

`resp_downreg` is now 0.1 (`:251`) and is not referenced anywhere at cb243228.

## 14. Literature cited in source

Grant (1989) is cited for the Rubisco rate (`StomatesMod.F90:446`), the Km with O2 competition (`:976`) and the sky-zone geometry (`f90src/Plant_bgc/InitVegBGC.F90:42`, `:56`, `InitIrradianceGeometry`). No Farquhar, Ball-Berry or Medlyn citation appears in these routines.

## Calibration parameters: source map

All reads are bare `ncd_getvar` calls in `ReadPlantTraitTable` (a missing name aborts the run) and are copied per PFT in `SetPlantTraits`. The per-PFT reader `ReadPlantTraitsNC` (`PlantInfoMod.F90:540-694`) has no caller.

| file name | Fortran variable | read at (file:line, subroutine) | every use site at cb243228 (subroutine, file:line, branch) | what it does (the equation, quoted) |
|---|---|---|---|---|
| VCMX | `VmaxSpecRubCarboxyRef_pft` | `PlantInfoMod.F90:1736` (`ReadPlantTraitTable`); copy `:731` (`SetPlantTraits`); rescaled `:507` (`ReadPlantProperties`) | `PhotosynsDiag` `StomatesMod.F90:134` (C4) and `:148` (C3); `C3Photosynthesis` `:441` (C3); `C4Photosynthesis` `:639` (C4, bundle sheath) | `VmaxSpecRubCarboxyRef_pft = 1.92*VmaxSpecRubCarboxyRef_pft`; `VcMaxRubiscoRef_node = VmaxSpecRubCarboxyRef_pft(NZ)*MesophyllRubiscoSurfDensity` (C3) or `*BundlSheathRubiscoSurfDensity` (C4); then `*TFN_Carboxy` |
| VOMX | `VmaxRubOxyRef_pft` | `PlantInfoMod.F90:1737`; copy `:732`; rescaled `:508` | `PhotosynsDiag` `StomatesMod.F90:135` (C4), `:149` (C3); `C3Photosynthesis` `:442` (C3); `C4Photosynthesis` `:641` (C4) | `VmaxRubOxyRef_pft = 1.92*VmaxRubOxyRef_pft`; `VOGRO = VoMaxRubiscoRef_node*TFN_Oxygen`; `CO2CompenPoint_node = 0.5*O2L_pft*VOGRO*Km4LeafaqCO2_pft/(Vmax4RubiscoCarboxy_node*Km4RubOxy)` (`:445`, `:643`) |
| ETMX | `SpecLeafChlAct_pft` | `PlantInfoMod.F90:1746`; copy `:740`; rescaled `:510` | `PhotosynsDiag` `StomatesMod.F90:156` (both); `C3Photosynthesis` `:461` (C3); `C4Photosynthesis` `:594` (C4 mesophyll) and `:658` (C4 bundle sheath) | `SpecLeafChlAct_pft = 1.35*SpecLeafChlAct_pft`; `ElectronTransptJmaxRef_node = SpecLeafChlAct_pft(NZ)*MesophyllChlDensity`; `LigthSatCarboxyRate_node = SpecLeafChlAct_pft(NZ)*TFN_eTranspt*BundlSheathChlDensity` |
| RUBP | `LeafRubisco2Protein_pft` | `PlantInfoMod.F90:1743`; copy `:738` | `PhotosynsDiag` `StomatesMod.F90:128` (C4), `:146` (C3); `C3Photosynthesis` `:422` (C3); `C4Photosynthesis` `:619` (C4) | `MesophyllRubiscoSurfDensity = LeafRubisco2Protein_pft(NZ)*ProteinCLeafAreaDensity` (C3); `BundlSheathRubiscoSurfDensity = ProteinCLeafAreaDensity*LeafRubisco2Protein_pft(NZ)` (C4); scales both Vcmax and Vomax |
| CHL | `LeafProtein2Chl_pft` | `PlantInfoMod.F90:1747`; copy `:742` | `PhotosynsDiag` `StomatesMod.F90:129`, `:131` (C4), `:145` (C3); `C3Photosynthesis` `:423` (C3); `C4Photosynthesis` `:564` (C4 mesophyll), `:620` (C4 bundle sheath) | C3: `MesophyllChlDensity = LeafProtein2Chl_pft(NZ)*ProteinCLeafAreaDensity/3.5`; C4: `*fMesophyllChlProtein_pft(NZ)/3.7` and `*(1-fMesophyllChlProtein_pft(NZ))/5.5`; sets Jmax only |
| XKCO2 | `XKCO2_pft` | `PlantInfoMod.F90:1739`; copy `:734` | `PrepPhotosynthesis` `StomatesMod.F90:974` (both); its derived Km is used in `C3Photosynthesis` `:445`, `:448` (C3), `C4Photosynthesis` `:643`, `:645` (C4 bundle sheath only), `ComputeGPP_C3` `PhotoSynsMod.F90:177` (C3) | `Km4LeafaqCO2_pft(NZ) = XKCO2_pft(NZ)*EXP(16.136-40000/RTK)`; `Km4RubiscoCarboxy_pft = Km4LeafaqCO2_pft*(1+O2L_pft/Km4RubOxy)`; C4 mesophyll uses XKCO24 instead |
| FCO2 | `CanopyCi2CaRatio_pft` | `PlantInfoMod.F90:1749`; copy `:744` | `StomatalDynamics` `StomatesMod.F90:268` (both); diagnostic fallback in `CheckPlantBalanceZ` `PlantBalMod.F90:832` | `LeafIntracellularCO2_pft(NZ)=CanopyCi2CaRatio_pft(NZ)*CanopyGasCO2_pft(NZ)`; fixes the Ci at which `DiffCO2Atmos2Intracel_pft` (`:943`), the minimum stomatal resistance `RSX` (`:1060`) and the first `RS` (`PhotoSynsMod.F90:139`, `:342`) are evaluated; the Ci iteration starts there (`:171`, `:376`) |
| RSMX | `CuticleResist_pft` | `PlantInfoMod.F90:1813`; copy `:815` | `InitShootGrowth` `InitPlantMod.F90:189-190` and `StartqMod.F90:176-177`; via `CO2CuticleResist_pft` in `ComputeGPP_C3` `PhotoSynsMod.F90:139-140` (C3) and `ComputeGPP_C4` `:342-343` (C4); via `H2OCuticleResist_pft` in `PhotoActivePFT` `StomatesMod.F90:1062-1065`, `StomatalDynamics` `:275`, `CalcStomataResist4H2O` `PlantMathFuncMod.F90:570` | `H2OCuticleResist_pft = CuticleResist_pft/3600.0`; `CO2CuticleResist_pft = CuticleResist_pft*1.56`; `RSL = RS+(CO2CuticleResist_pft(NZ)-RS)*Stomata_Stress`; caps the minimum resistance |
| RCS | `RCS_pft` | `PlantInfoMod.F90:1812`; copy `:814` | `StagePlantForGrowth` `GrosubsMod.F90:554` (vascular; bryophytes bypass it); `CalcStomataResist4H2O` `PlantMathFuncMod.F90:569` | `Stomata_Stress = EXP(-PSICanopyTurg_pft(NZ)/RCS_pft(NZ))`; photosynthesis (`RSL`, `WFNB`, `WFN4`) and transpiration resistance |
| OSMO | `OrganOsmoPsi0pt_pft` | `PlantInfoMod.F90:1811`; copy `:813` | `update_osmo_turg_pressure` calls in `HandlingDivergence` `UptakesMod.F90:624`, `:640`; `CanopyEnergyH2OIter_func` `:832`, `:1141`; `HandleBareSoil` `:1430`, `:1449`; `UpdatePlantWaterVars` `:1557`; initial values `InitPlantHeatWater` `InitPlantMod.F90:971`, `InitRootMychorMorphoBio` `:1050`, `StartqMod.F90:152`, `:819` | `PSIOsmo = FDMP*(OSMO/FDMP0-RGASC*TKP*CCPOLT/OSWT)`; `PSITurg = AZMAX1(PSIOrgan-PSIOsmo)` (`PlantMathFuncMod.F90:71-72`); reaches `Stomata_Stress` and `TurgEff4CanopyResp`. Associated but unused in `ShootRootElmTransfer` (`PlantNonstElmDynMod.F90:399`) |
| ZTYPI | `PlantInitThermoAdaptZone_pft` | `PlantInfoMod.F90:1735`; copy `:725` | `PFTThermalAcclimation` `InitPlantMod.F90:485-489` and `StartqMod.F90:450-453`; `CorrectClimate` `WthrMod.F90:476-477` (`ICLM.EQ.2`); `ReadPlantProperties` `PlantInfoMod.F90:527-528` (perennial evergreen only); display `:1092-1103`. Offset consumers: `PrepPhotosynthesis` `StomatesMod.F90:957`; `StagePlantForGrowth` `GrosubsMod.F90:501`, `:505`; `SetCanopyGrowthFuncs` `UptakesMod.F90:1619`, `:1623`; `CalcPhenolEnvfactor` `PlantPhenolMod.F90:1056` | `TempOffset_pft = 2.667*(2.5-rPlantThermoAdaptZone_pft)`, added to canopy and soil temperatures before every Arrhenius function; `HourReq4LeafOut_brch = AMIN1(4380, VRNLI+144*PlantInitThermoAdaptZone_pft*(NB-1))` (phenology, topic 02) |

None of the eleven is inert: every one is read on the live path and used. Three carry a hidden transformation a calibrator must know: VCMX and VOMX enter at 1.92 times and ETMX at 1.35 times the file value, and FCO2 is not a dynamic Ci (it sets the prior and the stomatal target; the converged Ci is reported separately as `DynCi2CaRatio_pft`).

## Cross-links

- Leaf protein colimitation (CNWL, CPWL, CNLF, CPLF), growth yields and allocation: `plant_bgc/growth_and_allocation.md` (topic 02).
- Phenology use of ZTYPI, VRNLI, VRNXI and the leaf-out/leaf-off thresholds: `plant_bgc/phenology.md` (topic 02).
- Root respiration, DMRT, root O2 limitation and the plant mass balance: `plant_bgc/roots_and_uptake.md` (topic 03).
