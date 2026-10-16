---
**Source pin:** EcoSIM commit `cb243228` (jingtao-lbl/EcoSIM `fix/r2-plant-balance`; upstream `09eb674a` + 2 fix commits)
**Scope:** `f90src/Plant_bgc/{RootMod,UptakesMod,NutUptakeMod,PlantNonstElmDynMod,PlantBalMod}.F90`, root parts of `GrosubsMod`, `PlantPhenolMod`, `InitPlantMod`, `f90src/Ecosim_mods/StartqMod.F90`, `f90src/IOutils/PlantInfoMod.F90`, `f90src/APIs/PlantMod.F90`, `f90src/Modelconfig/EcoSIMCtrlMod.F90`
**Last verified:** 2026-10-15
---

# Roots, uptake, shoot-root exchange and the plant mass balance

This page covers everything below the shoot in the dynamic plant model: how the root system is laid out over soil layers, how roots grow, respire and die, how nonstructural C, N and P move between shoot and roots, root hydraulics and water uptake, mineral nutrient uptake, root exudation, root stoichiometry, and the hourly plant mass balance with its two namelist switches. The plant-balance material lives here rather than on a separate balances page, because the balance's root terms and the root clamp it guards are root code. Leaf-level allocation and branch growth are on `growth_and_allocation.md`; canopy photosynthesis on `photosynthesis_and_respiration.md`.

Index convention used below: `N` is the root type (`ipltroot=1` plant roots, `imycorrhz=2` mycorrhizae, looped `1..Myco_pft`), `L` the soil layer, `NR` the structural root axis (`1..NumStructuralRootAxes_pft`), `NZ` the PFT.

## 1. Hourly call order

The plant model runs once per hour per column from `PlantModel` (`f90src/APIs/PlantMod.F90:37`). In dynamic mode (`ldo_sp_mode=.false.`) the root-relevant sequence is:

```
PlantModel                                         APIs/PlantMod.F90:37
  PlantAPISend                                     :71   column -> plt_* copies
  EnterPlantBalance                                :73   PlantBalMod.F90:668  (opens the C/N/P bracket, zeroes hourly fluxes)
  PhenologyUpdate                                  :82
    StagePlantPhenology                            PlantPhenolMod.F90:91   MaxSoilLays4Root_pft = NMaxRootBotLayer_pft (:453)
    root_shoot_branching                           PlantPhenolMod.F90:95   adds structural root axes (PR gate, :374-379)
  RootUptakes                                      :85   UptakesMod.F90:51
    PrepNutrientUptake                             UptakesMod.F90:135
    UpdateRootProperty                             :151  fine-root radius, path length, uptake fractions
    CalcPlantHydroResistance                       :174  radial + axial + soil resistances (only if HydroActivePlant, :165-168)
    CanopyEnergyH2OIter_func                       :197  transpiration and root water uptake (converged)
    PlantNutientO2Uptake                           :227  NutUptakeMod.F90:37 (O2, NH4, NO3, H2PO4, HPO4, exudation)
  GrowPlants                                       :88   GrosubsMod.F90:61
    GrowOnePlant                                   GrosubsMod.F90:104
      StagePlantForGrowth                          :308  TFN6_vr, CNRTW, CPRTW, primary-axis count
      GrowOneBranch (each branch)                  :314
      RootBGCModel                                 :326  RootMod.F90:35
        SummarizeRootSink                          RootMod.F90:98    applies uptake to root pools, builds sinks
        RootBiochemistry                           :114  per N, per L: GrowRootMycoAxes, RepleteLowSeaStorByRoot, DiagRootGeometry
          CytoKininDynamics                        :296
        RootNodulBiochemistry                      :155
      PlantNonstElmTransfer                        :328  PlantNonstElmDynMod.F90:642 (ShootRootElmTransfer at :682)
    RemoveBiomassByDisturbance, ResetDeadPlant, AccumulateStates, Live2DeadTransformation   GrosubsMod.F90:106-117
  EXTRACTs                                         :91
  ReSeedPlants                                     :93
  ExitPlantBalance                                 :95   PlantBalMod.F90:715 -> CheckPlantBalanceZ (aborts on error)
  PlantAPIRecv                                     :97
```

Two consequences of this order matter for interpretation. Uptake RATES are computed in `RootUptakes` but only CREDITED to root nonstructural pools at the start of `RootBGCModel` (`SummarizeRootSink`, `RootMod.F90:5692-5696`), after growth of the branches. And the shoot-root transfer runs after root growth (`GrosubsMod.F90:326-328`), so root growth in hour h uses the root pool left by the transfer of hour h-1. In prescribed-phenology mode (`ldo_sp_mode`) only `PlantUptakeAPISend`, `RootUptakes`, `extracts` and `PlantUPtakeAPIRecv` run (`PlantMod.F90:60-68`) and nutrient uptake is skipped (`UptakesMod.F90:224-229`); there is no root growth and no plant balance.

## 2. Root architecture and layer indices

Each PFT carries `NumStructuralRootAxes_pft` structural axes (incremented by `root_shoot_branching`, `PlantPhenolMod.F90:378`). On each structural axis sit `Num1stAxesPerStructRootX_pft` primary axes per plant; the population total is `Num1stAxesPerStructRootXPOP_pft = Num1stAxesPerStructRootX_pft*PlantPopuLive_pft` (`GrosubsMod.F90:533`). The per-plant count follows a pipe-model power of root C per plant (`GrosubsMod.F90:514-532`, enclosing `StagePlantForGrowth`):

| branch | `Num1stAxesPerStructRootX_pft` | cite |
|---|---|---|
| annual | `AMAX1(1, RootBiomCPerPlant**0.833)/NumStructuralRootAxes` | `GrosubsMod.F90:518` |
| woody vascular, `lcoarseroot=.true.` | `AMIN1(1, AMAX1(1, RootBiomCPerPlant**0.7143)/NumStructuralRootAxes)` | `:522` |
| woody vascular, `lcoarseroot=.false.` | `AMAX1(1, RootBiomCPerPlant**0.7143)/NumStructuralRootAxes` | `:524` |
| other (herbaceous perennial) | `AMAX1(1, RootBiomCPerPlant**1.053)/NumStructuralRootAxes` | `:528` |

Root orders: primary axes (`RootMyco1stStrutElms_rpvr`, split into an active zone `Root1stActStructElms_rpvr` and a lignified zone `Root1stLigStructElms_rpvr`), secondary or fine roots and mycorrhizal hyphae (`RootMyco2ndStrutElms_rpvr`), medium roots (`RootMediumStructElms_rpvr`, woody PFTs with `lcoarseroot` only), plus one nonstructural pool per root type and layer (`RootMycoNonstElms_rpvr`). Each axis also carries an axis-total primary mass `RootMyco1stElm_raxs`, which the fibrous-root respiration and kill use (section 4).

Three layer bounds are in play, and they are not the same:

- `MaxNumRootLays` is grid variable `NJ` (`f90src/IOutils/readimod.F90:454`); `NK_col = MaxNumRootLays_col+1` (`readimod.F90:460`). Root growth loops run `L=NU..MaxNumRootLays+1` (`RootMod.F90:228`, `:288`), but a primary tip is clamped to `MaxNumRootLays` (`RootMod.F90:3273`, `:4733`) and receives no structural mass beyond it (`PrimeRootsExtension` keeps `FGROZ=0` at `L=MaxNumRootLays`, `RootMod.F90:4665-4672`).
- `MaxSoilLays4Root_pft` bounds uptake, exudation, hydraulics and the shoot-root transfer (`UptakesMod.F90:981`, `:1258`, `NutUptakeMod.F90:1541`, `PlantNonstElmDynMod.F90:584`). In dynamic mode it is reset every hour to `NMaxRootBotLayer_pft` (`PlantPhenolMod.F90:453`) and raised to a primary tip's layer, up to `NK`, in `GetInLayerRootDepth` (`RootMod.F90:5455-5460`), which happens when a tip passes the bottom of layer `MaxNumRootLays` (the elongation cap is lifted there, `RootMod.F90:2145-2147`). Only the prescribed-phenology API pins it to `NK_col` (`f90src/APIs/PlantAPI4Uptake.F90:148`).
- `NMaxRootBotLayer_pft` is the deepest tip layer over all axes (`RootMod.F90:1682`); nutrient uptake is computed only for `L<=NMaxRootBotLayer_pft` (`NutUptakeMod.F90:217`).

The temperature function for root maintenance, `TFN6_vr(L) = calc_plant_maint_tempf(TKS_vr(L)+TempOffset_pft)`, is filled only for `L=NU..MaxNumRootLays` (`GrosubsMod.F90:504-507`) although the root loop reaches `MaxNumRootLays+1`; in the normal path the growth routines are not entered in that layer because the tip is clamped first.

## 3. Root sink strength and uptake crediting (`SummarizeRootSink`)

`SummarizeRootSink` (`RootMod.F90:5482`) runs first in `RootBGCModel`. Per root type and layer it (a) charges the C cost of the hour's mineral uptake, `RecoRootMycoC4Nup = 0.86*sum(RootNutUptake_pvr)` gC per g N or P (`CMassCost4NiUptk`, `RootMod.F90:5519`, `:5641`), rescaling uptake down if the root nonstructural C cannot pay (`:5658-5667`) and booking the cost as root respiration (`:5670-5672`); (b) adds the N and P taken up to `RootMycoNonstElms_rpvr` and to `RootNutUptakeN_pft`/`RootNutUptakeP_pft` (`:5692-5696`); (c) builds the sink strengths that weight root growth and the shoot-root transfer. Sinks are phloem-like conductances: primary `PrimaryRootCd4NonstTP = Num1stAxesPerStructRootXPOP/R1stPholemResist_vr` (`:5732`), fine-root `FineRootCd4NonstTP = Root2ndXNum*Root2ndRadius**2/Root2ndEffLen4uptk` (`:5736`), combined in series and scaled by `(1-fctyok)` (`:5774`, `:5776`), with the tip sink `RTSK(IGTYP)*Num1stAxesPerStructRootXPOP/R1stPholemResist` (`:5802`). `fctyok`, the cytokinin scalar from CYTOS, is non-zero only on woody vascular PFTs with `lcoarseroot` (`:5719-5728`). Normalised profiles are written to `Root2ndSinkWeight_pvr`, `Root1stSinkWeight_pvr` and `RootMSinkWeight_pvr` (`:5822-5851`).

## 4. Root growth and respiration (the DMRT two-channel form)

Per layer, `GrowRootMycoAxes` (`RootMod.F90:1475`, both root types) sets two quantities shared by every root order in that layer:

```
DMRespEff = 1 - RootBiomGrosYld_pft          [RootBiomGrosYld_pft is DMRT]   RootMod.F90:1577 (GrowRootMycoAxes)
VMXCSpec  = VMXC*fTGrowRootP_vr*fRootGrowPSISense*Nutstress4GrossResp*GrainFillDowreg(main branch)   :1599
Nutstress4GrossResp = min(CZ/(CZ+CC*CNKI), CP/(CP+CC*CPKI))   (root nonstructural concentrations)  :1580-1583
fRootGrowPSISense = exp(0.10*max(PSIRoot,-5000))   (bryophyte: 0.05)                                 :250-254
```

with `VMXC=0.015` h-1, `CNKI=0.1`, `CPKI=0.01` (`f90src/Modelpars/PlantBGCPars.F90:217`, `:226-227`). Then, for every structural axis, `Grow2ndRootAxes` grows fine roots and hyphae, and the primary axis grows through `GrowFibrous1stRootAxes` or, for woody vascular PFTs with `lcoarseroot`, `GrowWoodyStructuralRootAxes` (branch at `RootMod.F90:1641-1650`); medium roots grow only on woody PFTs with `lcoarseroot` (`:1666-1673`).

Fine roots (`Grow2ndRootAxes`, `RootMod.F90:567`):

```
Rmaint2nd   = max(0, RmSpecPlant*RootMyco2ndStrutElms(N))*TFN6_vr(L)         :688   (x fRootGrowPSISense if bryophyte or drought-deciduous, :691-693)
RNonstCO2   = nonstC*min(VMXCSpec*FracRoot2ndCSinkL, 1)                        :700   (x RAutoRootO2Limter for the O2-limited version, :704)
RGrowCO2    = max(0, RNonstCO2 - Rmaint2nd)*RespElongWatSens                   :705-708
FNP         = AMIN1(ZPOOLB/CNRTS_pft, PPOOLB/CPRTS_pft)*DMRespEff               :720   growth respiration allowed by nonstructural N, P
RGrowCO2    = min(RGrowCO2, FNP)    (O2-limited: FNP*RAutoRootO2Limter)         :722-733
NonstC4Grow = RGrowCO2/DMRespEff;   biomass C = NonstC4Grow*RootBiomGrosYld     :742-751
biomass N,P = biomass C * CNRTW, CPRTW (capped by the layer's nonstructural N, P share)   :746-753
RCO2Nassim  = 1.70*biomass N                                                    :748, :755
Root2ndExtPot = biomass C*FracRootElmAllocm(C,fine)*Root2ndSpecLen_pft          :758
```

`RmSpecPlant=0.010` gC gN-1 h-1 (`PlantBGCPars.F90:228`); `CNRTS_pft = rNCRoot_pft*RootBiomGrosYld_pft` and `CPRTS_pft = rPCRootr_pft*RootBiomGrosYld_pft` (`StartqMod.F90:513-514`; also `InitPlantMod.F90:594-595` at planting). DMRT therefore enters root growth twice: as the respiration share of consumed nonstructural C (`DMRespEff = 1-DMRT`) and inside the nutrient allowance `FNP`, through `CNRTS = CNRT*DMRT`, so a higher DMRT both lowers growth respiration per unit growth and tightens the N and P allowance. The same three steps repeat in `Grow1stRootElongZoneLayL` (`:1941`, `:1964-1977`), `StructuralRootElongation` (`:2860`, `:2883-2891`) and `GrowMediumRootAxes` (`:1247`, `:1261-1269`). Before a branch emerges, DMRT is also used as the leaf and petiole growth yield of that branch (`PlantBranchMod.F90:503-505`, `UpdateBranchAllometry`). Coarse-root thickening uses the stalk yield instead (`DMRespEff = 1-StalkBiomGrowthYld_pft`, `RootMod.F90:2364`).

New fine-root axes follow a quadratic in RTFQ: `Num2ndRoots = RTFQ*Num1stAxesPerStructRootXPOP`, `Num3rdRoots = RTFQ*Num2ndRoots`, `NumGroFineAxes = (Num2ndRoots+Num3rdRoots)*DLYR3(L)` (on medium roots when `lcoarseroot`, `RootMod.F90:829-840`), capped by `Root2ndLen/Root2ndTipLen4uptk` (`:841-842`, `Root2ndTipLen4uptk=2e-3` m, `PlantBGCPars.F90:232`). Root protein accrues as `RootProteinC_pvr += AMIN1(CNWR*N, CPWR*P)` of the new fine-root structure (`RootMod.F90:845-847`) and of primary-root structure (`:4694-4696`, `:4715-4717`).

Fibrous primary roots (every PFT except woody vascular with `lcoarseroot`; `Grow1stRootElongZoneLayL`, `RootMod.F90:1745`, reached through `GrowFibrous1stRootAxes` for the tip layer only) pay maintenance on the WHOLE axis: `Rmaint1st = RmSpecPlant*RootMyco1stElm_raxs(N,NR)*TFN6_vr(L)` (`:1892`; the active-zone branch at `:1890` cannot run in this routine, see the next paragraph), out of the tip layer's nonstructural pool (`:1909`, `:1993`). Once a tip is below layer `MaxNumRootLays`, nonstructural C oxidation is capped at maintenance, so the tip stops growing (`:1913-1915`). Extension per plant is `NonstC4Grow*FracRootElmAllocm(C,fine)/Num1stAxesPerStructRootXPOP*Root1stSpecLen_pft` (`:1996-1997`), capped at the next layer's thickness above `MaxNumRootLays` (`:2145-2147`). Primary-root respiration is distributed over the young layers the axis passes through (`:2062-2094`).

**Primary-root maintenance respiration (`Rmaint1st_CO2`).** Each of the three primary-root growth routines computes its own local `Rmaint1st_CO2`:

| routine (path) | `Rmaint1st_CO2` | water factor `fRootGrowPSISense` applied to | cite |
|---|---|---|---|
| `Grow1stRootElongZoneLayL` (fibrous, tip layer) | `AZMAX1(RmSpecPlant*RootMyco1stElm_raxs(ielmn,NR,NZ))*TFN6_vr(L)`: N of the whole axis | bryophytes and drought-deciduous PFTs | `RootMod.F90:1892`, `:1895-1897` |
| `StructuralRootElongation` (woody vascular with `lcoarseroot`, tip layer) | `AZMAX1(RmSpecPlant*Root1stActStructElms_rpvr(ielmn,L,NR,NZ))*TFN6_vr(L)`: active-zone N of the tip layer | bryophytes and drought-deciduous PFTs | `:2808`, `:2813-2815` |
| `StructuralRootThickening` (woody, `lcoarseroot`, each layer with `flag2ndGrowth_pvr`) | `RmSpecPlant*TFN6_vr(L)*AZMAX1(Root1stActStructElms_rpvr(ielmn,L,NR,NZ))`, or 0 when `LDoneTip` | drought-deciduous PFTs only | `:2374-2383` |

Both elongation routines branch on `lcoarseroot .and. is_plant_woody_vascular(...)` (`:1889`, `:2807`), the same test `GrowRootMycoAxes` uses to choose between them (`:1641-1650`): `Grow1stRootElongZoneLayL` is reached only through `GrowFibrous1stRootAxes` (`:3190`), called when the test is false, and `StructuralRootElongation` only through `GrowWoodyStructuralRootAxes` (`:2220`), called when it is true. So the active-zone branch at `:1890` and the whole-axis branch at `:2810` never execute, and a fibrous axis always pays maintenance on its axis total, at the tip layer's temperature `TFN6_vr(L)` and, for bryophytes and drought-deciduous PFTs, the tip layer's root water potential. The zeroing at `:2376` acts on `StructuralRootThickening`'s own local copy: `GrowWoodyStructuralRootAxes` sets `LDoneTip = .true.` when it has just run `StructuralRootElongation` in that layer (`:2217-2222`) and passes the flag to the thickening call in the same layer (`:2226-2228`), so the woody tip layer is not charged twice; it does not touch the fibrous path. Inputs: `RmSpecPlant = 0.010` gC gN-1 h-1 (`f90src/Modelpars/PlantBGCPars.F90:228`, `InitVegPars`); `TFN6_vr(L) = calc_plant_maint_tempf(TKS_vr(L)+TempOffset_pft)` for `L=NU..MaxNumRootLays` (`GrosubsMod.F90:504-507`, `StagePlantForGrowth`; Arrhenius form on `photosynthesis_and_respiration.md` section 9); `fRootGrowPSISense = exp(0.10*max(PSIRoot,-5000))`, 0.05 for bryophytes (`RootMod.F90:250-254`, `RootBiochemistry`).

On the fibrous path, maintenance first sets the growth budget, `RCO2PotGroth = RNonstCO2 - Rmaint1st_CO2` (`:1924-1925`); a negative remainder is added to `RootMaintDef_CO2_pvr` (`:1928`) and paid from structure by `RemobilizePrimeActRoots` (`:2028-2032`; section 5), which adds that payoff to the respiration total (`:4579-4580`). Below layer `MaxNumRootLays` the oxidation is capped at `Rmaint1st_CO2` (`:1913-1915`). The hour's total `RCO2T1st_Oltd = AMIN1(Rmaint1st_CO2,RNonstCO2_Oltd) + RGrowCO2_Oltd + RCO2Nonst4Nassim_Oltd` (`:1989-1990`) is debited from the tip layer's nonstructural C (`:1993`) and booked, negative, to `RootCO2Autor_pvr` over the young layers of the axis (`:2084-2087`, or the tip layer alone at `:2090-2093`). `RootCO2Autor_pvr` is summed into `RootAutoCO2_pft` (`PlantBalMod.F90:167-171`, `SumRootAR`) and `GrossResp_pft` (`:99`, `SumPlantBiome`), and added to `ECO_ER_col` and `Eco_AutoR_CumYr_col` (`PlantNonstElmDynMod.F90:442-443`, `ShootRootElmTransfer`), which is `ECO_RA_col` ([`photosynthesis_and_respiration.md`](photosynthesis_and_respiration.md) section 12).

Woody vascular PFTs with `lcoarseroot` add radial thickening (`StructuralRootThickening`, `RootMod.F90:2238`), whose N and P cost uses the live coarse-root ratios `rECLiveCRoot_pft` (CNLCRT, CPLCRT; `:2367`, `:2420-2430`), radius update from active-zone volume (`:2563-2564`), and a live-to-dead transfer once the radius passes `dmax=0.015` m (`CRootsLive2DeadTransformation`, `:3789-3807`), which returns the N and P difference between live and dead ratios (CNDCRT, CPDCRT) to the nonstructural pool (`:3798-3807`). The explicit lignification block of `StructuralRootThickening` (`:2467-2495`) is unreachable: `RootMycoNonstC4Lig_Oltd` is zeroed at `:2451` and only rescaled afterwards (`:2461`), consistent with the comment at `:2373`. `SecondaryGrowthZone` (`:3348`) has no live caller (its call is commented out at `:3218`).

## 5. Root starvation, death and the root clamp

Maintenance deficits are paid by remobilising structure. Fine roots: `DiagSenes2ndRootAxes` (`RootMod.F90:864`) kills `Frac2Senes2` of the fine-root structure, recycles the remobilisable part (`RCCE` from `RCCZR, RCCYR, RCCXR, RCCQR`, `:932-937`) and sends the rest to litter (`:995-1023`). Primary roots: `RemobilizePrimeActRoots` (`:4315`). On the non-coarse branch (`lcoarseroot=.false.`, `:4403`) the payoff and the kill are sized from the axis total `RootMyco1stElm_raxs` (`:4406-4409`, `:4446`) and the kill is subtracted from the net growth (`:4466`), which `PrimeRootsExtension` then adds to the TIP layer (`:4686-4690`). Because the kill is sized from the whole axis but taken from one layer, the tip layer's structural pool can go negative.

`GrowFibrous1stRootAxes` (`RootMod.F90:3088`) removes such negative pools after the tip update: a negative fine-root pool (`:3252-3259`) and a negative primary pool (`:3262-3271`) are folded into the layer's nonstructural pool through `AZMAX1(nonst + strut)`. Whatever the nonstructural pool cannot cover is discarded by `AZMAX1`, which creates mass because the litterfall and respiration that drove the pool negative were already booked. With `conserve_root_clamp=.true.`, `ChargeRootDeficitUpAxis` (`RootMod.F90:3309-3345`) is called first, element by element (`:3255` with `LS=L` for the fine-root clamp, `:3265` with `LS=L-1` for the primary clamp):

```
remain = -(RootMycoNonstElms_rpvr(NE,N,L) + strut)           :3326   (return if <= 0, :3327)
DO LL = LS, NGTopRootLayer_pft, -1                            :3328   walk UP the same axis
  take = min(remain, max(0, Root1stActStructElms_rpvr(NE,LL,NR)))   :3329
  Root1stActStructElms_rpvr, RootMyco1stStrutElms_rpvr, RootMyco1stElm_raxs -= take   :3331-3333
any remainder -> negative fine-root litterfall in layer L     :3338-3342
```

So the deficit is taken from the active zone of the same axis's primary roots, keeping primary = active + lignified, and the axis total drops by the same amount. With no deficit the routine changes nothing and the clamp gives the old result. Root length is not reduced with the mass (stated in the header comment, `RootMod.F90:3307-3308`). The switch is a default-`.false.` logical (`f90src/Modelconfig/EcoSIMCtrlMod.F90:46`) read through namelist group `/ecosim/` (`drivers/ecosim/EcoSIMAPI.F90:180-182`, routine `readnamelist`); a runfile that omits it keeps `.false.`. It gates only the two calls above; the woody path (`GrowWoodyStructuralRootAxes`) has no such clamp.

Whole-plant root death: if the PFT has no structural axes, or a perennial's seasonal storage C is exhausted, both root and shoot are flagged dead (`RootMod.F90:147-151`).

## 6. Shoot-root nonstructural exchange (PTSHT)

`ShootRootElmTransfer` (`PlantNonstElmDynMod.F90:322`, called last in `PlantNonstElmTransfer`, `:682`) exchanges nonstructural C, N and P between each live branch and each root layer `L=NU..MaxSoilLays4Root_pft`. The conductance is

```
PTSHTR = PTSHT * GrothPART2LeafPetole**0.167      annuals          :548-549
PTSHTR = PTSHT                                    otherwise        :550-551
PTSHTR = PTSHTR*(AreaTranspt/Aphol_ref)*(L0_phol/Leff_phol)   woody vascular with lcoarseroot   :554-566
PTSHTR = AMIN1(PTSHTR, 1)                                          :567
```

where `GrothPART2LeafPetole` is the main branch's allocation to leaf and petiole (`GrosubsMod.F90:320-322`). For C, the flux to roots is `XFRE = PTSHTR*(CPOOLBranch*RootActVL - CPOOLRootS*CanopyActVNB)/(CanopyActVNB+RootActVL)` (`PlantNonstElmDynMod.F90:594-595`), where the two "volumes" are branch leaf+sheath C weighted by the layer's root sink weight and by `FWTC`, and root active C weighted by the branch weight and by `FWTS`, each floored at `FSNK=0.05` of the other (`:585-588`; `FWTC`, `FWTS` at `:491-502`; `FSNK` at `PlantBGCPars.F90:223`). N and P follow the N:C or P:C gradient (`:610-611`) with a daytime root-to-shoot enhancement proportional to sap velocity while transpiring (`:613-616`). Every flux passes `ExchFluxLimiter`, which caps it at 0.9999 of the donor pool (`PlantMathFuncMod.F90:350-361`). PTSHT is a transfer conductance in h-1; it does not enter photosynthesis. Transfers are recorded in `ShootRootXferElm_pft` and `RootShootExch_pvr` (`:599-602`, `:620-623`). Separately, `RepleteLowSeaStorByRoot` (`PlantNonstElmDynMod.F90:913`, called per layer from `RootMod.F90:272`) moves root nonstructural C into seasonal storage when storage is below `XFRX*RootElms_pft(C)` (`:942-956`). Two more exchanges reach the root nonstructural pools outside this routine, both driven by the N:C and P:C gradient `NonstGradt`: seasonal storage to roots in perennials (`DevelopMainBranch`, `PlantBranchMod.F90:3051-3058`) and, in annuals after the seed-number stage, roots to the stalk reserve (`StalkRsrvRootNonstTransfer`, `PlantNonstElmDynMod.F90:855-865`). Their form, rate constants and sign rules are on [`growth_and_allocation.md`](growth_and_allocation.md) section 9.

## 7. Root hydraulics

`CalcPlantHydroResistance` (`UptakesMod.F90:1160`) builds, per root type and rooted layer, a soil resistance, a radial root resistance and an axial resistance in series; layers act in parallel (`:1335`).

```
RSSL          = ln(RadialMeanLen/FineRootRadius)/(RootEffLen4Absorption*PP);  SoilResist = RSSL/HYCDMicP4RootUptake   :1279-1280
RootRadial    = RSRR*VLMicP/(2*pi*Root2ndRadius*RootAbsorbLenPerPlant*PP*VLWatMicPM)                              :1290-1291
FRADW         = 1e4*(max(0.5, 1+PSICanopy/EMODW))**4          stalk conducting elements, EMODW=50 MPa             :1247
StalkAxial    = max(0, RSSA*0.8*CanopyHeightLive/(FRADW*Root1stXNumL))                                              :1243, :1309
FRAD1         = max(CRootLumenArea_pvr/RootSingleVesselArea, 1)                                                     :1302
Root1stAxial  = StalkAxial + RootSingleVesselRstaxial*CumSoilThickMidL/FRAD1                                        :1310
FRAD2         = (Root2ndRadius/RRAD2M)**2  (roots), **4 (hyphae)                                                    :1304-1308
Root2ndAxial  = Root2ndAxialResist_pft*Root2ndEffLen4uptk/(FRAD2*Root2ndXNumL)                                      :1316
```

The single-vessel and fine-root axial resistivities are built once, in STARTQ (`StartqMod.F90:580-583`, routine `InitPlantPhenoMorphoBio`):

```
RootSingleVesselRstAxial_pft = ARSRA*Rax_ref*(1e-6/RVSR)**4         Rax_ref = 7.11e11 MPa h m-4 (PlantBGCPars.F90:120)
RootSingleVesselArea_pft     = pi*RVSR**2
NumVessels                   = 0.2*pi*RRAD2M**2/RootSingleVesselArea_pft
Root2ndAxialResist_pft(root) = RootSingleVesselRstAxial_pft/NumVessels
```

Algebraically `Root2ndAxialResist_pft = 5*ARSRA*Rax_ref*1e-24/(RVSR**2*RRAD2M**2)` (only pi cancels), and `FRAD1` counts vessels of radius RVSR in the lumen area, so the primary axial term also scales as `ARSRA/RVSR**2`. Because the fine-root radius is `AMAX1(RRAD2M, (1+PSIRoot/EMODR)*RRAD2M)` (`RootMod.F90:530`, with `Root2ndMaxRadius1_pft = Root2ndMaxRadius_pft`, `StartqMod.F90:546`), it equals RRAD2M whenever `PSIRoot<=0`, so `FRAD2=1` and RRAD2M stays in the fine-root axial term as `RRAD2M**-2`. The lumen area is recomputed every hour in `CytoKininDynamics` (`RootMod.F90:5048-5108`): non-woody PFTs use `pi*Root1stRadius**2*Num1stAxesPerStructRootXPOP*xylemPhi_mean_pft` (`:5104`), so the STARTQ value from RRAD1M (`StartqMod.F90:585`) is only the initial state. Mycorrhizae use fixed values, radial 1e4 and fine axial 1e12 (`StartqMod.F90:527-528`). In prescribed-phenology mode coupled to ATS, RSRR is overwritten with 4e5 and the fine axial resistivity with 500 (`UptakesMod.F90:476-485`).

RSRA is not part of this chain: it is read only in `ReadPlantTraitsNC` (`f90src/IOutils/PlantInfoMod.F90:625`), which has no caller at cb243228; the live trait reader is `ReadPlantTraitTable` (`PlantInfoMod.F90:1708`, called from `f90src/Main/InitEcoSIM.F90:37`) with per-PFT copies in `SetPlantTraits` (`PlantInfoMod.F90:696`), and it reads ARSRA (`:1797`) but not RSRA. The shipped `input_data/ecosim_pftpar_20260915.nc` has no RSRA variable. Note also that in that shipped file RVSR is 4e+09 for `lich32` and 1e+09 for `alfa43` (equal to their RSSA entries), which by the formulas above drives both axial resistivities to effectively zero for those two PFTs.

**Absorbing length, fine-root radius and radial path (`UpdateRootProperty`).** The geometry in `RSSL` above, and in the nutrient and O2 diffusion terms of section 9, is set each hour per root type and layer `L=NU..MaxSoilLays4Root_pft` by `UpdateRootProperty` (`UptakesMod.F90:427`, called at `:151`, `RootUptakes`):

```
FracSoilLBy1stRoots_pvr(L) = 1                     L = NU (dynamic mode), every layer in ldo_sp_mode              :504, :480
                           = RootLocDepz/DLYR3(L)  deeper layers; 0 if DLYR3(L) <= ZERO                          :509, :511
  RootDepZ    = max over structural axes of Root1stDepz_raxes                                                    :498-500
  RootLocDepz = AZMAX1(AMIN1(DLYR3, AZMAX1(RootDepZ-CumSoilThickness(L-1))) - AZMAX1(SeedDepth-CumSoilThickness(L-1)-HypocotHeight))   :507-508
IF RootAbsorbLenPerPlant_pvr(N,L) > ZERO .AND. FracSoilLBy1stRoots_pvr(L) > ZERO .AND. .NOT.ldo_sp_mode         :527
  FineRootRadius_rvr        = max(Root2ndMaxRadius1_pft, sqrt(RootVH2O/((1-PORT)*pi*RootAbsorbLenPerPlant*PP)))  :528-529
  RadialMeanLen_rvr         = max(1.001*FineRootRadius, sqrt(FracSoilLBy1stRoots*FracSoiAsMicP/(pi*RootAbsorbLenPerPlant)))   :532-533
  RootEffLen4Absorption_pvr = TwoPiCON*RootAbsorbLenPerPlant_pvr/FracSoilLBy1stRoots_pvr                        :535
ELSE
  FineRootRadius_rvr = Root2ndMaxRadius_pft ;  RadialMeanLen_rvr = 1.001*FineRootRadius_rvr                      :538-539
  RootEffLen4Absorption_pvr = TwoPiCON*RootAbsorbLenPerPlant_pvr                                                :540
```

`FracSoilLBy1stRoots_pvr` is the fraction of the layer's thickness that the deepest primary tip has reached. In a partly penetrated layer the whole absorbing length is credited to the occupied part, so `RootEffLen4Absorption_pvr` rises by `1/FracSoilLBy1stRoots_pvr` and the half-spacing `RadialMeanLen_rvr` shrinks by `sqrt(FracSoilLBy1stRoots_pvr)`; both lower the soil-to-root resistance per unit root. The undivided branch applies in prescribed-phenology mode, in a layer with no absorbing length, and in a layer wholly below the primary root depth.

`RootAbsorbLenPerPlant_pvr` (m per plant) is formed in `DiagRootGeometry` as the per-plant length of the primary axes that are not in secondary growth plus the population fine-root length per plant, `RootAbsorbLenPerPlant_pvr = TotFineRoot1stLlenAxesPP + TotPopuRoot2ndLlenAxes/PlantPopuLive_pft` (`RootMod.F90:488`), with the fine-root sum at `:401` and the primary sum at `:435` (axes with `flag2ndGrowth_pvr` count as coarse and are left out, `:430-435`); it is 0 where the layer has no roots (`:543`) and gains the seed length in the seeding layer (`:130`, `RootBGCModel`). `Root2ndSpecLen_pft` does not enter `UpdateRootProperty`: it is the fine-root length per unit growth C, `FineRootVolPerMassC_pft/(pi*RRAD2M**2)` (`f90src/Ecosim_mods/StartqMod.F90:543`, `InitDimensionsandUptake`; `InitPlantMod.F90:624` at planting), which converts fine-root growth into length, `Root2ndExtPot = RootMycoNonst4Grow_Oltd(C)*FracRootElmAllocm(C,fine)*Root2ndSpecLen_pft` (`RootMod.F90:758`, `Grow2ndRootAxes`), less senescence (`:1023`, `DiagSenes2ndRootAxes`), added to `Root2ndLen_rpvr` (`:824`), which `:401` sums.

| consumer of `RootEffLen4Absorption_pvr` | expression | file:line (subroutine) |
|---|---|---|
| soil-to-root water resistance | `RSSL = LOG(RadialMeanLen_rvr/FineRootRadius_rvr)/(RootEffLen4Absorption_pvr*PlantPopuLive_pft)` | `UptakesMod.F90:1279` (`CalcPlantHydroResistance`) |
| NH4 and NO3 diffusion conductance | `DIFFL = ZNSGX*safe_adb(RootEffLen4Absorption_pvr, LOG(PATHL/FineRootRadius))` (`ZOSGX` for NO3), with `PATHL = AMIN1(RadialMeanLen_rvr, FineRootRadius+SQRT(2*ZNSGX))` | `NutUptakeMod.F90:752-754` (`UptakeNH4`), `:566` (`UptakeNO3`) |
| phosphate diffusion conductance | `DIFFL = POSGX*safe_adb(RootEffLen4Absorption_pvr, LOG(PATHL/FineRootRadius))` | `NutUptakeMod.F90:489` (`UptakeMineralPhosporhus`) |
| root-soil gas exchange | `RTARRX = RootEffLen4Absorption_pvr/RootRaidus_rpft` (and `/RRADS`) | `RootGasMod.F90:293`, `:343` (`RootSoilGasExchange`) |

## 8. Root water uptake and its link to ET

Inside the canopy energy-water iteration, when the canopy temperature converges or every tenth iteration, each rooted layer takes up (or loses) water (`UptakesMod.F90:985-993`, `CanopyEnergyH2OIter_func`):

```
psi_H2O_flx              = (PSICanopy + rho*g*h - TotalSoilPSIMPa(L))/SoilRootResist4H2O(N,L)
RPlantRootH2OUptk_pvr     = max(-WatAvail4Uptake*FracPRoot4Uptake, min(psi_H2O_flx, AirMicPore4Fill*FracPRoot4Uptake))
```

The iteration adjusts canopy water potential until transpiration minus root uptake matches the change in canopy water. Transpiration is `Transpiration_pft = EX*RawCanopy2Atm/(RawCanopy2Atm+CanPStomaResistH2O)` (`UptakesMod.F90:899`); `ExtractCanopyFluxes` adds it and canopy evaporation to `QVegET_col` (`f90src/Plant_bgc/ExtractsMod.F90:398`); `HandleSurfaceBoundary` subtracts ground plus vegetation vapour flux from `QEvap_CumYr_col` (`f90src/Balances/RedistMod.F90:408-410`); and the history variable is `ECO_ET_col = m2mm*QEvap_CumYr_col/AREA` (`f90src/IOutils/HistData/HistUpdateColumn.F90:213`). Root hydraulic parameters therefore reach `ECO_ET_col` through `SoilRootResist4H2O_pvr` and the canopy water potential that stomata respond to. The plant is hydraulically active only after emergence, with active leaf area, PAR and a primary root below the seed (`UptakesMod.F90:162-169`); otherwise `HandleBareSoil` zeroes uptake (`:216`).

## 9. Mineral nutrient uptake

`RootMycoO2NutrientUptake` (`NutUptakeMod.F90:149`) loops layers `NU..NK` but acts only where `L<=NMaxRootBotLayer_pft` and the layer has water (`:216-217`), and per root type only where absorbing length, root water volume and root C exist (`:221-222`). Uptake is attempted only when O2 limitation, C limitation, transporter density and root length are all positive (`:288-289`). Shared factors (`GetUptakeCapcity`, `:1298`):

```
FSatNutTransporter = RootProteinConc/0.05,  RootProteinConc = min(RootProteinCMax_pft, RootProteinC/ActiveRootC)   :1349-1355
FCUP = max(0, min(1, 0.25*RootNonstC/RootCO2EmisPot))                                                      :1364-1368
FZUP = min(CC/(CC+CZ/ZCKI), CP/(CP+CZ/ZPKI));  FPUP = min(CC/(CC+CP/PCKI), CZ/(CZ+CP/PZKI))               :1378-1386
```

with `ZCKI=0.05`, `PCKI=0.005` (`f90src/Plant_bgc/UptakePars.F90:51-54`). Per-plant capacity is the Vmax times root surface area per plant and these factors:

```
NH4:   VmaxNH4RootPerPlant = UPMXZH*RootSAreaPerPlant*FSatNutTransporter*fTgrowRootP*min(FCUP,FZUP)         :765-766  (UptakeNH4)
NO3:   VmaxNO3RootPerPlant = UPMXZO*RootSAreaPerPlant*FSatNutTransporter*fTgrowRootP*min(FCUP,FZUP)         :577-578  (UptakeNO3)
H2PO4: UPMXP = UPMXPO*RootSAreaPerPlant*FSatNutTransporter*fTgrowRootP*VLN*min(FCUP,FPUP)                    :1117-1118 (UptakeH2PO4)
HPO4:  UPMXP = 0.1*UPMXPO*RootSAreaPerPlant*FSatNutTransporter*fTgrowRootP*VLN*min(FCUP,FPUP)                :956-957  (UptakeHPO4)
```

NH4 and NO3 capacity is further multiplied by the zone's volume fraction (`:784`). Each zone (non-band, band) is solved only when its concentration exceeds the Cmin partner (`:770`, `:832`). The solver `SoluteUptakeByPlantRoots` (`PlantMathFuncMod.F90:180`) combines mass flow `q` (root water uptake per plant), diffusion conductance `D = ZNSGX*RootEffLen4Absorption/ln(PATHL/FineRootRadius)` (`NutUptakeMod.F90:752-754`) and Michaelis-Menten uptake through the quadratic `Q**2 - (v+X-Y+D*K)Q + (X-Y)v = 0` with `X=(q+D)C`, `Y=D*Cmin` (`PlantMathFuncMod.F90:190-194`, solved at `:225-250`), where `v` is capacity times O2 limitation and `K` is the Km partner. Population uptake is capped by the available mass above Cmin allocated by the previous hour's demand share (`ZNH4X = max(0, FNH4X*(mass - Cmin*VLWat*VLN))`, `NutUptakeMod.F90:802-803`; `FNH4X` from `UptakeMineralNitrogen`, `:1255-1259`). N uptake is skipped entirely when `FZUP<=ZERO2` (`:1282`). Uptake costs root C in `SummarizeRootSink` (section 3). Root length and area come from RRAD1M, RRAD2M, PORT and RTFQ through `DiagRootGeometry` (`RootMod.F90:303`): `RootSAreaPerPlant = (2*pi*Root1stRadius*primary length + 2*pi*Root2ndRadius*fine length)/PP` (`:522`, `:530-540`).

Units: the file long-names and the trait display give Km and Cmin in uM (`PlantInfoMod.F90:1315-1329`), but the declarations say g m-3 (`f90src/Ecosim_datatype/RootDataType.F90:42-49`) and the solver compares them with `trc_solcl_vr` in g m-3 (`PlantMathFuncMod.F90:218-220`); no conversion exists between read and use, so the file values are used as g element m-3.

## 10. Exudation and DOM uptake

`RootExudates` (`NutUptakeMod.F90:1414`) exchanges C, N and P between root nonstructural pools and each DOM complex in proportion to their concentration difference: `XFRE(C) = (DOC*RootVH2O - min(1250*RootVH2O, nonstC)*VLWatK)/(VLWatK+RootVH2O)` and `Soil2RootMycoExudE = FEXUDE*XFRE` (`:1462-1466`), with N and P from the DON:DOC and DOP:DOC versus 0.1x root N:C and P:C gradients (`:1468-1474`); `FEXUDE = 5e-4, 1e-2, 1e-2` for C, N, P (`UptakePars.F90:55-57`). Exudation is scaled down if it would empty the pool (`:1490-1497`). `SumNutrientUptake` books it to soil DOM and to root pools over `L=MaxSoilLays4Root_pft..NU` (`:1541-1568`).

## 11. Root stoichiometry

| quantity | formula / role | cite |
|---|---|---|
| root growth N:C, P:C | `CNRTW = FracRootElmAllocm(C,woody)*CNSTK + FracRootElmAllocm(C,fine)*CNRT` (CPRTW likewise); fine fraction is 1 for non-woody PFTs | `GrosubsMod.F90:449-451`, `:467-468` |
| N, P allowance per unit growth | `CNRTS_pft = CNRT*DMRT`, `CPRTS_pft = CPRT*DMRT` | `StartqMod.F90:513-514` |
| max root protein | STARTQ: `RootProteinCMax_pft = CNRT*CNWR`; planting path: `AMIN1(CNRT*CNWR, CPRT*CPWR)` | `StartqMod.F90:181`; `InitPlantMod.F90:192` |
| live coarse root N:C, P:C | thickening cost and live-to-dead N, P return (woody, `lcoarseroot`) | `RootMod.F90:2367`, `:2420-2430`, `:3798-3800` |
| dead coarse root N:C, P:C | retained in the lignified zone after live-to-dead | `RootMod.F90:3800-3804` |
| lignified root N:C, P:C | only in the unreachable lignification block and dead `SecondaryGrowthZone` | `RootMod.F90:2472-2473` |

## 12. Initialisation and readers

Root traits are copied from the live table reader in `SetPlantTraits` (`PlantInfoMod.F90:782-849`). STARTQ (`StartqMod.F90:34`, called once in the start year from `drivers/ecosim/EcoSIMAPI.F90:434-439`) then derives growth yields, mycorrhizal copies of the uptake kinetics (`StartqMod.F90:517-526`), specific lengths `Root1stSpecLen = FineRootVolPerMassC/(pi*RRAD1M**2)`, `Root2ndSpecLen = FineRootVolPerMassC/(pi*RRAD2M**2)` with `FineRootVolPerMassC = 1/(50e3*(1-PORT))` (`:541-543`), gas tortuosity `PORT**1.33` and radial diffusion path `ln(1/sqrt(max(0.01,PORT)))` (`:539-540`), and the axial resistivities (`:580-583`). A PFT planted during the run goes through `StartPlants` (`InitPlantMod.F90:38`, called from `PlantPhenolMod.F90:225`, `:256`), whose `InitDimensionsandUptake` repeats the derivations with two differences: `RootProteinCMax_pft` also uses P (`InitPlantMod.F90:192`) and mycorrhizal radii are 5e-6 m instead of 8e-6/2e-6 m (`InitPlantMod.F90:596-597` versus `StartqMod.F90:515-516`). The axial resistivities are not re-derived at planting. Root traits are stored in single precision at column level (`RootDataType.F90:21-61`).

## 13. Plant mass balance

`EnterPlantBalance` (`PlantBalMod.F90:668`) snapshots, per PFT, `TotBegVegE = RootElms + ShootElms + SeasonalNonstElms + StandDeadStrutElms + ShootNoduleElms + nodulE + beyondE` (`:684-686`, `:698`) and zeroes hourly fluxes (`ZeroGrosub`, `:709`). `CheckPlantBalanceZ` (`:738`), run for every PFT every hour by `ExitPlantBalance` (`:731-733`), recomputes the same total (`:817-818`) and forms the residual

```
balE(NE) = TotEnd - TotBeg - NodulInfect - Soil2RootMycoExudE + Litrfall + DistLoss - SeedPlanted      :820-822
balE(C) -= GrossCO2Fix + GrossResp + beyondAR                                                            :827
balE(N) -= RootNutUptakeN + CanopyN2Fix + RootN2Fix + NH3Dep2Can                                         :828
balE(P) -= RootNutUptakeP                                                                                :829
```

(Respiration is carried with a negative sign: `GrossResp_pft = RootAutoCO2_pft + CanopyGrosRCO2_pft`, `PlantBalMod.F90:99`, with root terms built by decrementing `RootCO2Autor_pvr`, e.g. `RootMod.F90:804`; subtracting it therefore adds the respiration loss back.) Tests and aborts:

| element | abort condition | line |
|---|---|---|
| C | `abs(balE)>1e-6 .and. (lveg_too_small_for_relative_test .or. abs(err_rel)>1e-3)` | `:852`, `endrun` at `:878` |
| N | `abs(balE)>1e-6 .and. abs(err_rel)>1e-3` | `:888`, `:910` |
| P | same, skipped on the planting or harvest day | `:919`, `:937-938` |

with `err_rel = balE/max(TotEnd, TotBeg)` (`:832-836`). Diagnostics go to Fortran unit 888 (`:854-876`). The residual accumulates into `PlantElmBalCum_pft` (`:941-943`), output as `Plant_BALANCE_C_pft` (`f90src/IOutils/HistData/HistUpdatePlant.F90:89`).

The model's own root totals cover fewer layers than the root fluxes: `SumRootBiome` sums root pools over `L=1..MaxNumRootLays` (`PlantBalMod.F90:570-586`), `SumRootAR` sums root respiration over `1..NMaxRootBotLayer_pft` (`:167-171`), while uptake, exudation and the shoot-root transfer act on `NU..MaxSoilLays4Root_pft`. `SumRootPoolsForBalance` (`:617-665`, fix commit `9669b817`) closes that gap for the balance only, with `LBAL = MAX(MaxNumRootLays, MaxSoilLays4Root_pft)` (`:640`): `beyondE` adds root pools in layers `MaxNumRootLays+1..LBAL` (`:644-653`), `nodulE` replaces `RootNoduleElms_pft` with nodules over `NU..LBAL` (`:654-658`), and `beyondAR` adds root respiration over `NMaxRootBotLayer_pft+1..LBAL` (`:659-663`). `RootElms_pft` itself is unchanged, so `Root_C_pft` still omits layer `MaxNumRootLays+1` (section 14). `LBAL` is evaluated separately at entry and exit; because `MaxSoilLays4Root_pft` can change within the hour (section 2), a root pool left in layer `NK` is counted at both ends only while `MaxSoilLays4Root_pft` stays at `NK`.

`guard_floor_dying_stand` (default `.false.`, `EcoSIMCtrlMod.F90:41`, read through `/ecosim/`, `EcoSIMAPI.F90:182`) changes two things. In `CheckPlantBalanceZ` it sets `lveg_too_small_for_relative_test` when `max(TotEnd, TotBeg) < VEGC_BAL_FLOOR_dying = 1.0` gC (`PlantBalMod.F90:849-851`; floor at `EcoSIMCtrlMod.F90:61`); in that regime the C abort no longer needs `abs(err_rel)>1e-3` and fires on the absolute test alone (`:852`). Off, the condition reduces to the original `abs(balE)>1e-6 .and. abs(err_rel)>1e-3`. It does not touch the N or P tests. In `WithdrawNutBranchLeaves` it floors the C-pool denominator at `CPOOL_DIV_FLOOR_dying = 1e-12` (`PlantBranchMod.F90:308-312`; `EcoSIMCtrlMod.F90:53`). `conserve_root_clamp` (section 5) is the companion switch for the root clamp; both are read from the same namelist group and both default off, so a runfile without them reproduces the earlier behaviour.

## 14. Producing equations owned here

- `Root_C_pft = RootElms_pft(C)/AREA` (`HistUpdatePlant.F90:203`), with `RootElms_pft = massr1st + massr2nd + nonst` summed over `L=1..MaxNumRootLays` and all root types (`PlantBalMod.F90:567-586`, `SumRootBiome`); primary includes medium roots (`:576`, `:579`). Nodules are excluded (`:591-594`).
- `ECO_ET_col`: see section 8.

## 15. Which root levers are live, by branch

Several root parameters act only on one branch. The default `lcoarseroot=.false.` (`EcoSIMCtrlMod.F90:75`; namelist default `drivers/ecosim/EcoSIMAPI.F90:215`) switches the whole coarse and medium root system off even for woody PFTs.

| parameter | non-woody PFT (e.g. C3 grass, clover) | woody vascular, `lcoarseroot=.false.` | woody vascular, `lcoarseroot=.true.` | prescribed-phenology mode |
|---|---|---|---|---|
| DMRT, CNRT, CPRT, RTFQ, PR, PTSHT, PORT, RRAD1M, RRAD2M | live | live | live (thickening uses DMSTK instead of DMRT) | DMRT, PR, PTSHT, RTFQ not used (no growth); geometry fixed by the prescribed profile |
| RSRR, ARSRA, RVSR, RSSA | live (only once the plant is hydraulically active) | live | live | RSRR overwritten with 4e5 under ATS coupling |
| UPMXZH, UPMXZO, UPMXPO and partners, CNWR | live | live | live | not used (`UptakesMod.F90:224-229`) |
| MRTFQ, CYTOS, CNLCRT, CPLCRT, CNDCRT, CPDCRT | no effect | no effect | live | no effect |
| CNRTLIG, CPRTLIG, RSRA | inert | inert | inert | inert |

`conserve_root_clamp` acts only through `GrowFibrous1stRootAxes`, i.e. on the first three columns' fibrous primary roots (all non-woody PFTs, and woody PFTs when `lcoarseroot=.false.`). `guard_floor_dying_stand` acts in every dynamic-mode configuration.

## Calibration parameters: source map

All reads below are in `ReadPlantTraitTable` (`f90src/IOutils/PlantInfoMod.F90:1708`), the live reader; the per-PFT copy is in `SetPlantTraits`. The dead `ReadPlantTraitsNC` also contains reads of most of these names (`PlantInfoMod.F90:617-678`) but never runs.

| file name | Fortran variable | read at (file:line, subroutine) | every use site at cb243228 (subroutine, file:line, branch) | what it does (the equation, quoted) |
|---|---|---|---|---|
| DMRT | `RootBiomGrosYld_pft` | `PlantInfoMod.F90:1821` (ReadPlantTraitTable); copy `:824` (SetPlantTraits) | `CNRTS_pft`,`CPRTS_pft`: InitDimensionsandUptake `StartqMod.F90:513-514`, `InitPlantMod.F90:594-595`; GrowRootMycoAxes `RootMod.F90:1577`; Grow2ndRootAxes `:745`, `:751`; Grow1stRootElongZoneLayL `:1967`, `:1972` (non-woody tip); StructuralRootElongation `:2886`, `:2891` (woody, `lcoarseroot`); GrowMediumRootAxes `:1264`, `:1269` (woody, `lcoarseroot`); UpdateBranchAllometry `PlantBranchMod.F90:504-505` (branch not yet emerged) | `DMRespEff = 1.0_r8-RootBiomGrosYld_pft(NZ)`; `FNP = AMIN1(ZPOOLB/CNRTS_pft(NZ),PPOOLB/CPRTS_pft(NZ))*DMRespEff`; `RootMycoNonst4Grow_Oltd(ielmc) = RootMycoNonst4GrowC_Oltd*RootBiomGrosYld_pft(NZ)` |
| PR | `NonstCMinCon2InitRoot_pft` | `:1794`; copy `:792` | root_shoot_branching `PlantPhenolMod.F90:375` (first hour of day, root turgor above `PSIMin4LeafExpansion`) | `(CanopyNonstElmConc_pft(ielmc,NZ).GT.NonstCMinCon2InitRoot_pft(NZ) .AND. NonstCMinCon2InitRoot_pft(NZ).GT.0.0_r8)` adds a structural root axis; compared with CANOPY nonstructural C concentration |
| PTSHT | `ShootRootNonstElmConduts_pft` | `:1798` (into `ShutRutNonstElmntConducts_tab`); copy `:797` | ShootRootElmTransfer `PlantNonstElmDynMod.F90:549` (annual), `:551` (perennial); scaled `:554-566` (woody, `lcoarseroot`); cap `:567`; used `:595`, `:611`, `:615` | `PTSHTR=ShootRootNonstElmConduts_pft(NZ)*GrothPART2LeafPetole**0.167_r8`; `XFRE = PTSHTR*NonstElmGradt1(L)`; `PTSHTR=AMIN1(PTSHTR,1._r8)` |
| RRAD1M | `Root1stMaxRadius_pft` | `:1785`; copy `:787` | InitDimensionsandUptake `StartqMod.F90:542`, `:544`, `InitPlantMod.F90:623`, `:625`; InitPlantPhenoMorphoBio `StartqMod.F90:585` (initial lumen area); DiagRootGeometry `RootMod.F90:424`, `:516`, `:521`, `:552`, `:554`; PrimeRootsExtension `:4692`; SummarizeRootSink `:5714`; ShootRootElmTransfer `PlantNonstElmDynMod.F90:561-562` (woody, `lcoarseroot`) | `Root1stSpecLen_pft = FineRootVolPerMassC_pft/(PICON*Root1stMaxRadius_pft**2)`; `Root1stRadius_pvr = AMAX1(Root1stMaxRadius1_pft,(1.0_r8+PSIRoot_pvr/EMODR)*Root1stMaxRadius_pft)` |
| RRAD2M | `Root2ndMaxRadius_pft` | `:1786`; copy `:788` | InitDimensionsandUptake `StartqMod.F90:543`, `:546`; InitPlantPhenoMorphoBio `StartqMod.F90:582` (NumVessels); DiagRootGeometry `RootMod.F90:530`, `:553`; UpdateRootProperty `UptakesMod.F90:528` (via `Root2ndMaxRadius1_pft` floor), `:538`; CalcPlantHydroResistance `UptakesMod.F90:1305`, `:1307` | `Root2ndSpecLen_pft = FineRootVolPerMassC_pft/(PICON*Root2ndMaxRadius_pft**2)`; `NumVessels = 0.2_r8*PICON*Root2ndMaxRadius_pft**2/RootSingleVesselArea_pft`; `FineRootRadius_rvr = AMAX1(Root2ndMaxRadius1_pft, SQRT(RootVH2O/((1-PORT)*PICON*RootAbsorbLen*PP)))` |
| RTFQ | `FineRootBranchFreq_pft` | `:1799`; copy `:798` | Grow2ndRootAxes `RootMod.F90:831-832` (`lcoarseroot` with medium roots), `:837-838` (otherwise) | `Num2ndRoots = FineRootBranchFreq_pft(NZ)*Num1stAxesPerStructRootXPOP_pft(NZ)`; `Num3rdRoots = FineRootBranchFreq_pft(NZ)*Num2ndRoots`; `Root2ndXNum_rpvr = AMIN1(NumGroFineAxes,MaxNumGroFineAxes)` |
| MRTFQ | `MediumRootBranchFreq_pft` | `:1800`; copy `:799` | SummarizeRootSink `RootMod.F90:5740`; GrowMediumRootAxes `:1211` | `PotentialMediumAxes = AZMAX1(MediumRootBranchFreq_pft(NZ)*Root1stLenPP_rpvr(L,NR,NZ)*Num1stAxesPerStructRootXPOP_pft(NZ))`. Effective only for woody vascular PFTs with `lcoarseroot` (medium roots grow only there, `:1666-1673`); otherwise it feeds only the diagnostic `RootMSinkWeight_pvr` |
| PORT | `RootPorosity_pft` | `:1787`; copy `:789` | InitDimensionsandUptake `StartqMod.F90:517`, `:536-541`, `InitPlantMod.F90:598`, `:619-622`; RootBGCModel `RootMod.F90:142-143`; DiagRootGeometry `:403`, `:526-527`; UpdateRootProperty `UptakesMod.F90:529`; RootSoilGasExchange `RootGasMod.F90:312` | `FineRootVolPerMassC_pft = 1._r8/(50.e3_r8*(1.0_r8-RootPorosity_pft))`; `RootPoreTortu4Gas_pft = RootPorosity_pft**1.33_r8`; `RootPoreVol_pvr = RootPorosity_pft*TotAbsorbRootVol` |
| RSRR | `RootRadialResist_pft` | `:1795`; copy `:793` | CalcPlantHydroResistance `UptakesMod.F90:1291`; overwritten with 4e5 in UpdateRootProperty `UptakesMod.F90:485` (only `ldo_sp_mode .and. ats_cpl_mode`) | `RootRadialResist_rvr(N,L) = RootRadialResist_pft(N,NZ)*VLMicP_vr(L)/(Root2ndSurfArea*VLWatMicPM_vr(NPH,L))` |
| RSRA | `RootSingleVesselRstaxial_pft` | NOT READ on the live path: only `PlantInfoMod.F90:625` in dead `ReadPlantTraitsNC`; absent from the shipped plant file | none from RSRA; the variable is derived from ARSRA in InitPlantPhenoMorphoBio `StartqMod.F90:580` | INERT. Use ARSRA/RVSR instead |
| ARSRA | `AlphaVesselAxialResist_pft` | `:1797`; copy `:794` | InitPlantPhenoMorphoBio `StartqMod.F90:580` (once, STARTQ only); downstream CalcPlantHydroResistance `UptakesMod.F90:1310`, `:1312`, `:1316` | `RootSingleVesselRstAxial_pft = AlphaVesselAxialResist_pft*Rax_ref*(1.e-6_r8/RootVesselRadius_pft)**4`; `Root2ndAxialResist_pft = RootSingleVesselRstAxial_pft/NumVessels` |
| RVSR | `RootVesselRadius_pft` | `:1796`; copy `:795` | InitPlantPhenoMorphoBio `StartqMod.F90:580-582`; downstream `UptakesMod.F90:1302-1303` (vessel count `FRAD1`, `FRADM`) | `RootSingleVesselArea_pft = PICON*RootVesselRadius_pft**2`; net axial dependence `ARSRA/RVSR**2` |
| RSSA | `StalkAxialResist_pft` | `:1783`; copy `:757` | CalcPlantHydroResistance `UptakesMod.F90:1309` | `StalkAxialResist = AZMAX1(StalkAxialResist_pft(NZ)*CanopyHeight4WatUptake_pft(NZ)/(FRADW*Root1stXNumL_pvr(L,NZ)))` |
| CNRT | `rNCRoot_pft` | `:1833`; copy `:836` | StagePlantForGrowth `GrosubsMod.F90:467`, `:481`; InitShootGrowth `StartqMod.F90:181`, `InitPlantMod.F90:192`; InitDimensionsandUptake `StartqMod.F90:513`, `InitPlantMod.F90:594` | `CNRTW=FracRootElmAllocm(ielmc,k_woody_comp)*rNCStalk_pft(NZ)+FracRootElmAllocm(ielmc,k_fine_comp)*rNCRoot_pft(NZ)`; `CNRTS_pft = rNCRoot_pft*RootBiomGrosYld_pft` |
| CNWR | `rProteinC2RootN_pft` | `:1823`; copy `:827` | InitShootGrowth `StartqMod.F90:181`, `InitPlantMod.F90:192`; Grow2ndRootAxes `RootMod.F90:846`; PrimeRootsExtension `:4695`, `:4716` | `RootProteinCMax_pft = rNCRoot_pft*rProteinC2RootN_pft` (STARTQ); `RootProteinC_pvr += AMIN1(rProteinC2RootN_pft*N, rProteinC2RootP_pft*P)`; feeds `FSatNutTransporter = RootProteinConc/0.05` (`NutUptakeMod.F90:1350-1351`) |
| CNRTLIG | `rNCLigRoot_pft` | `:1828`; copy `:831` | StructuralRootThickening `RootMod.F90:2472` (unreachable block); SecondaryGrowthZone `:3597`, `:3601`, `:3642` (no live caller) | INERT at cb243228: `RootMycoNonst4Lig_Oltd(ielmn) = -Rlignif_Oltd*(rECLiveCRoot_pft(ielmn,NZ)-rNCLigRoot_pft(NZ)*...)` never executes |
| CNLCRT | `rECLiveCRoot_pft(ielmn)` | `:1790`; copy `:782` | StructuralRootThickening `RootMod.F90:2367`, `:2420`, `:2429`; CRootsLive2DeadTransformation `:3798`, `:3800` (woody, `lcoarseroot`) | `RootMycoNonst4Thick_OUltd(ielmn) = RootMycoNonst4Thick_OUltd(ielmc)*rECLiveCRoot_pft(ielmn,NZ)`; `FNP = AMIN1(ZPOOLB/rECLiveCRoot_pft(ielmn,NZ),PPOOLB/rECLiveCRoot_pft(ielmp,NZ))*...` |
| CNDCRT | `rECDeadCRoot_pft(ielmn)` | `:1791`; copy `:784` | CRootsLive2DeadTransformation `RootMod.F90:3800` (woody, `lcoarseroot`, radius > `dmax`) | `Act2DeadElms2 = Act2DeadElms1*rECDeadCRoot_pft(NE,NZ)/rECLiveCRoot_pft(NE,NZ)` |
| CPLCRT | `rECLiveCRoot_pft(ielmp)` | `:1792`; copy `:783` | as CNLCRT (`RootMod.F90:2367`, `:2421`, `:2430`, `:3798`, `:3800`) | P analogue of CNLCRT (file units label says gN gC-1; it is a P:C ratio) |
| CPDCRT | `rECDeadCRoot_pft(ielmp)` | `:1793`; copy `:785` | CRootsLive2DeadTransformation `RootMod.F90:3800` | P analogue of CNDCRT |
| UPMXZH | `VmaxNH4Root_pft` | `:1801`; copy `:800` | UptakeNH4 `NutUptakeMod.F90:765`; mycorrhizal copy `StartqMod.F90:518`, `InitPlantMod.F90:599` | `VmaxNH4RootPerPlant=VmaxNH4Root_pft(N,NZ)*RootSAreaPerPlant_pvr(N,L,NZ)*FSatNutTransporter*fTgrowRootP_vr(L,NZ)*AMIN1(FCUP,FZUP)` |
| UPMXZO | `VmaxNO3Root_pft` | `:1805`; copy `:805` | UptakeNO3 `NutUptakeMod.F90:577`; copies `StartqMod.F90:521`, `InitPlantMod.F90:602` | `VmaxNO3RootPerPlant=VmaxNO3Root_pft(N,NZ)*RootSAreaPerPlant_pvr(N,L,NZ)*FSatNutTransporter*fTgrowRootP_vr(L,NZ)*AMIN1(FCUP,FZUP)` |
| UPMXPO | `VmaxPO4Root_pft` | `:1808`; copy `:809` | UptakeH2PO4 `NutUptakeMod.F90:1117`, `:1178`; UptakeHPO4 `:956`, `:1016` (x0.1); copies `StartqMod.F90:524`, `InitPlantMod.F90:605` | `UPMXP=VmaxPO4Root_pft(N,NZ)*RootSAreaPerPlant_pvr(N,L,NZ)*FSatNutTransporter*fTgrowRootP_vr(L,NZ)*trcs_VLN_vr(ids_H1PO4,L)*AMIN1(FCUP,FPUP)` |
| CYTOS | `enh_cyto_pft` | `:1782`; copy `:756` | func_cyto `RootMod.F90:5478`, called from GrowMediumRootAxes `:1306` and SummarizeRootSink `:5725` (both only woody vascular with `lcoarseroot`) | `fctyok = enh_cyto_pft*cyto_conc/(Km_cyto+cyto_conc*(1._r8+cyto_conc/Ki_cyto))`, capped at 1; splits medium-root growth between thickening and elongation and scales fine-root sinks by `(1-fctyok)` |

Kinetic partners (read in `ReadPlantTraitTable`, copied in `SetPlantTraits`):

| file name | Fortran variable | read | used in | role |
|---|---|---|---|---|
| UPKMZH | `KmNH4Root_pft` | `PlantInfoMod.F90:1802` | UptakeNH4 `NutUptakeMod.F90:814`, `:876` | `SoluteKM` (K) in the quadratic |
| UPMNZH | `CMinNH4Root_pft` | `:1803` | UptakeNH4 `:770`, `:802`, `:805`, `:832`, `:864` | zone gate, reserve `ZNH4M`, `SoluteConcMin` |
| UPKMZO | `KmNO3Root_pft` | `:1806` | UptakeNO3 `:624`, `:684` | K |
| UPMNZO | `CminNO3Root_pft` | `:1807` | UptakeNO3 `:580`, `:612`, `:615`, `:641`, `:672` | gate, reserve, Cmin |
| UPKMPO | `KmPO4Root_pft` | `:1809` | UptakeHPO4 `:986`, `:1046`; UptakeH2PO4 `:1147`, `:1209` | K |
| UPMNPO | `CMinPO4Root_pft` | `:1810` | UptakeHPO4 `:942`, `:974`, `:1002`, `:1034`; UptakeH2PO4 `:1103`, `:1135`, `:1164`, `:1197` | gate, reserve, Cmin |
| CPRT | `rPCRootr_pft` | `:1845` | as CNRT for P (`GrosubsMod.F90:468`, `:482`; `StartqMod.F90:514`) | root P:C |
| CPWR | `rProteinC2RootP_pft` | `:1836` | `InitPlantMod.F90:192`; `RootMod.F90:847`, `:4696`, `:4717` | protein C per root P (not used in the STARTQ `RootProteinCMax_pft`) |

Hard-coded constants that meet these parameters: `VMXC=0.015`, `CNKI=0.1`, `CPKI=0.01`, `RmSpecPlant=0.010`, `EMODR=5`, `Root2ndTipLen4uptk=2e-3`, `FSNK=0.05`, `dmax=0.015`, `Rax_ref=7.11e11` (`PlantBGCPars.F90:15`, `:120`, `:217-233`); `CMassCost4NiUptk=0.86` (`RootMod.F90:5519`); `EMODW=50`, `ZCKI=0.05`, `PCKI=0.005`, `FEXUDE` (`UptakePars.F90:50-57`).
