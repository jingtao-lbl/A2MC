---
**Source pin:** EcoSIM commit `cb243228` (jingtao-lbl/EcoSIM `fix/r2-plant-balance`; upstream `09eb674a` + 2 fix commits) · patched to `0340d71b` (see the wiki `index.md`, Patches applied)
**Scope:** `f90src/Plant_bgc/{GrosubsMod,PlantBranchMod,LitterFallMod}.F90`, shoot-side routines of `PlantNonstElmDynMod.F90`, biomass sums of `PlantBalMod.F90`, `f90src/IOutils/PlantInfoMod.F90` (trait reader), `f90src/Modelpars/PlantBGCPars.F90`, `f90src/IOutils/HistData/HistUpdatePlant.F90`
**Last verified:** 2026-10-15
---

# Shoot growth, allocation and tissue stoichiometry

Shoot growth is driven branch by branch from the branch's nonstructural C, N and P pool (`CanopyNonstElms_brch`). Each hour photosynthesis adds C, nonstructural C is oxidised at a rate set by temperature, water status and the pool's own N:C and P:C, maintenance (proportional to structural N) is paid first, and the surplus is growth respiration, which may be cut further by the N and P available for the new tissue. The C that growth consumes is split among seven organs by HARD-CODED, stage-dependent partition fractions; each organ converts consumed C to structure at its own growth yield (the DM* parameters) and takes N and P at prescribed organ ratios (the CN*/CP* parameters). This is a source-driven scheme, not a sink-source allocator.

Roots, root growth, the shoot-root nonstructural exchange, root hydraulics, nutrient uptake and the plant mass balance are on [`roots_and_uptake.md`](roots_and_uptake.md). Photosynthesis and the respiration terms are on [`photosynthesis_and_respiration.md`](photosynthesis_and_respiration.md). Development stages and leaf-out/leaf-off are on [`phenology.md`](phenology.md).

## 1. Call order

`GrowPlants` (`f90src/Plant_bgc/GrosubsMod.F90:61-122`) is called from `PlantModel` after `PhenologyUpdate` and `ROOTUPTAKES` (`f90src/APIs/PlantMod.F90:88`). For each active PFT with live population (`GrosubsMod.F90:102`) it calls `GrowOnePlant` (`:104`), `RemoveBiomassByDisturbance` (`:106`) and `ResetDeadPlant` (`:109`), then `AccumulateStates` for every PFT (`:113`), and finally `Live2DeadTransformation` (`:117`).

`GrowOnePlant` (`:261-337`) calls `StagePlantForGrowth` (`:308-309`), `GrowOneBranch` for every branch (`:312-324`), `RootBGCModel` (`:326`) and `PlantNonstElmTransfer` (`:328`). `GrowOneBranch` (`f90src/Plant_bgc/PlantBranchMod.F90:47-258`) runs, for a live branch:

| Step | Routine | Line |
|---|---|---|
| 1 | `CalcPartitionCoeff` (stage partition fractions) | `PlantBranchMod.F90:134-135` |
| 2 | `UpdateBranchAllometry` (yields, nutrient costs, structural N) | `:141-143` |
| 3 | `UpdatePhotosynthates` (GPP via `ComputeGPP`, then `ComputRAutoAfEmergence` or `ComputRAutoB4Emergence`) | `:147-149` |
| 4 | `C4PhotoProductTransfer` (C4 only) | `:158-160` |
| 5 | `BranchBiomAllocate` (organ C, N, P growth) | `:164-165` |
| 6 | `GrowLeavesOnBranch`, `GrowPetolShethOnBranch`, `GrowStalkOnBranch` | `:167`, `:171`, `:175` |
| 7 | recycling coefficients from nonstructural C:N:P | `:188-207` |
| 8 | `SenescenceBranch` (node-age turnover) | `:218` |
| 9 | `RemobilizeBranch` (maintenance deficit, phenological senescence) | `:220` |
| 10 | woody PFT: branch dies with the main stem | `:228-231` |
| 11 | `WithdrawNutBranchLeaves`, `GrainFillOnBranch`, `ResetBranchPhenology` | `:233`, `:235`, `:236` |
| 12 | `AllocateLeaf2CanopyLayers`, `LeafClassAllocation` | `:240`, `:242` |
| 13 | `BranchElmntTransfer` (storage and reserve exchanges), `CanopyNoduleBiochemistry` | `:248`, `:252` |

The main branch's leaf+petiole partition is passed up as `GrothPART2LeafPetole` (`:137-139`) and modulates the shoot-root exchange (`GrosubsMod.F90:320-322`; see [`roots_and_uptake.md`](roots_and_uptake.md)).

## 2. Organs and pools

Morph-unit ids are module constants of `PlantBranchMod` (`PlantBranchMod.F90:36-42`): 1 leaf, 2 petiole/sheath, 3 stalk, 4 stalk reserve, 5 husk, 6 ear, 7 grain. Each branch holds structural C/N/P per organ (`LeafStrutElms_brch`, `PetolShethStrutElms_brch`, `StalkStrutElms_brch`, `StalkRsrvElms_brch`, `HuskStrutElms_brch`, `EarStrutElms_brch`, `GrainStrutElms_brch`), a nonstructural pool `CanopyNonstElms_brch`, and per-node leaf, petiole, internode and protein masses (up to `MaxNodesPerBranch = 25` nodes per branch, `f90src/Mesh/GridConsts.F90:29`). Seasonal storage `SeasonalNonstElms_pft` is per PFT.

## 3. Woody fractions and growth stoichiometry

`StagePlantForGrowth` (`GrosubsMod.F90:340-563`) sets the fine/woody litter fractions and the N:C and P:C used for new growth. For IBTYP 0, non-woody PFTs, or a PFT without stalk, all fine fractions are 1 (`:445-451`); for trees the stalk fine fraction is `AMIN1(SQRT(sapwood/stalk),1)` and the root fine fraction `AMIN1((sapwood/stalk)**(1/6),1)` (`:455-456`). The leaf/sheath fine fraction is 1 in BOTH branches (`:449`, `:454`), so the woody leaf share is 0 (`:459`) and

```
CNLFW = rNCLeaf_pft  (CNLF),   CPLFW = rPCLeaf_pft  (CPLF)      GrosubsMod.F90:463-464
CNSHW = rNCSheath_pft (CNSHE), CPSHW = rPCSheath_pft (CPSHE)    GrosubsMod.F90:465-466
CNRTW = woody*rNCStalk + fine*rNCRoot  (root growth, see roots page)   GrosubsMod.F90:467-468
```

CNSTK therefore does not enter leaf or sheath growth N:C. It enters the N fractions of woody litter (`:472-482`; the stalk N fraction divides by `CNRTW`, `:478`, a root-weighted ratio). `StagePlantForGrowth` also sets the maintenance temperature functions with the thermal offset (`TFN5`, `TFN6_vr`, `:501-507`), the turgor expansion factor `TurgEff4LeafPetolExpansion = AMIN1(1, AZMAX1(PSICanopyTurg - 0.1))` (`:546`; `TurgPSIMin4OrganExtens = 0.1`, `f90src/Modelpars/PlantBGCPars.F90:229`), the growth water factor `exp(0.10*max(PSICanopy,-5000))` (`exp(0.05*...)` for bryophytes) (`GrosubsMod.F90:548-556`) and `TurgEff4CanopyResp = TurgEff**0.25` (`**0.10` bryophytes) (`:558`; `PlantMathFuncMod.F90:333-347`).

## 4. Stage-prescribed partitioning (`CalcPartitionCoeff`)

`CalcPartitionCoeff` (`PlantBranchMod.F90:559-814`) fills `PART(1:7)` from the branch calendar. `FPART1 = 1.00`, `FPART2 = 0.40` (`:574-575`); `PART2LEAF_MIN = 0.05`, `PART2PETOL_MIN = 0.02` (`PlantBGCPars.F90:215-216`).

| Stage | Partition | Lines |
|---|---|---|
| before floral initiation | leaf 0.725, petiole 0.275 | `:624-626` |
| floral init to anthesis | leaf `AMAX1(0.05, 0.725 - TotalNodeNumNormByMatgrp)`, petiole `AMAX1(0.02, 0.275 - 0.40*TotalNodeNumNormByMatgrp)`; of the rest 0.60 stalk, 0.30 reserve, 0.05 husk, 0.05 ear | `:632-640` |
| anthesis to begin seed fill | determinate: leaf = petiole = 0; indeterminate: leaf `AMAX1(0.05,(0.725-1.0)*(1-TotRepro))` = 0.05 and petiole `AMAX1(0.02,(0.275-0.40)*(1-TotRepro))` = 0.02 always, since both coefficients are negative; stalk `0.60*AZMAX1(PARTS*(1-TotRepro))`, reserve `0.30*...`, husk and ear split the rest | `:648-661` |
| during and after grain fill | determinate: grain 1.0; indeterminate annual: leaf 0.05, petiole 0.02, of the rest 0.125 stalk, 0.125 husk, 0.125 ear, 0.625 grain; indeterminate perennial: 0.75 stalk, 0.25 grain | `:668-687` |
| after end of seed fill, IBTYP 0 | annual: reserve, stalk, grain set to 0; perennial: stalk added to reserve, stalk and grain 0 | `:693-704` |

`TotReproNodeNumNormByMatrgrp_brch` grows from 0 after anthesis (`f90src/Plant_bgc/PlantPhenolMod.F90:1157`), so stalk and reserve partition fall and husk and ear rise as reproductive development proceeds. Modifiers applied afterwards:

1. **Reserve buffer, after floral initiation only** (`PlantBranchMod.F90:711-727`): if the stalk reserve is below `XFRX = 0.025` of sapwood C (`PlantBGCPars.F90:221`), 10% of every other organ's partition moves to the reserve; if the reserve exceeds sapwood C, reserve AND grain partition move to stalk.
2. **LAI cap** (`:733-739`): when PFT leaf area per ground area exceeds 5, a fraction `1 - AZMAX1((10 - LAI)/5)` of leaf and petiole partition moves to stalk; at LAI 10 no leaf is grown.
3. **Remobilization redirect** (`:755-788`): a perennial whose leaf-off hours reach `FracHour4LeafoffRemob(IWTYP)*HourReq4LeafOff` (`:758-759`; fractions 0.75, 0.5, 0.5, ..., `PlantBGCPars.F90:214`), or an annual past the seed-number stage (`:757`), is flagged for remobilization; non-evergreen perennials then move half of leaf+petiole partition to stalk and half to reserve (`:780-785`). The hourly activation `LRemob_brch` is unconditional for annuals and evergreens, needs canopy temperature below CTC for cold-deciduous types, and canopy water potential below `PSILY(IGTYP) = (-200,-2,-2,-2)` MPa for drought types (`:604`, `:768-778`).
4. **Normalisation** (`:792-809`): negative entries are clipped, the stalk partition is zero if SNL1 (`NodeLenPergC_pft`) is 0 (`:793-794`), and the vector is rescaled to sum to 1 and stored in `PARTS_brch` (`:811`).

## 5. Yields, nutrient costs and the growth budget

`UpdateBranchAllometry` (`PlantBranchMod.F90:443-556`) chooses the leaf and sheath yields and ratios: after emergence `DMLFB = DMLF`, `DMSHB = DMSHE`, `CNLFB = CNLFW`, `CNSHB = CNSHW` (`:496-502`); before emergence all four take the ROOT values `DMRT` and `CNRTW`/`CPRTW` (`:503-510`). It then forms

```
DMSHT        = sum_organs PART(i)*DM(i)                          :512-514   (DMLFB, DMSHB, DMSTK, DMRSV, DMHSK, DMEAR, DMGR)
YCO2Gro_brch = 1 - DMSHT                                         :516       growth respiration per unit nonstructural C used
CNLFM = PART(leaf)*DMLFB*ZPLFM*CNLFB,  CNLFX = PART(leaf)*DMLFB*ZPLFD*CNLFB          :517, :519
CNSHX = PART(pet)*DMSHB*CNSHB + PART(stk)*DMSTK*CNSTK + PART(rsv)*DMRSV*CNRSV
      + PART(husk)*DMHSK*CNHSK + PART(ear)*DMEAR*CNEAR + PART(grain)*DMGR*CNRSV        :521-526
(P analogues CPLFM, CPLFX, CPSHX)                                :518, :520, :528-533
ShootStructN = leaf N + petiole N + sapwood C*CNSTK (+ husk, ear, grain N before end of seed fill)   :542-552
```

with `ZPLFM = 0.33`, `ZPLFD = 0.67` (`PlantBGCPars.F90:247-248`). `ShootStructN` is the base of branch maintenance respiration, so CNSTK sets sapwood maintenance. In `ComputRAutoAfEmergence` (`PlantBranchMod.F90:3107-3300`; full respiration treatment on the photosynthesis page) the growth budget is:

```
CNPG = min(CZPOL/(CZPOL+CCPOL*CNKI), CPPOL/(CPPOL+CCPOL*CPKI))    :3165-3170   (CNKI 0.1, CPKI 0.01; PlantBGCPars.F90:226-227)
RCO2NonstC = VMXC*CanopyNonstC*fTCanopyGroth*CNPG*GrainFillDowreg*WaterStress4Groth   :3191-3192   (VMXC 0.015 h-1)
RCO2Maint  = RmSpecPlant*TFN5*ShootStructN  (*WaterStress4Groth for bryophytes, drought deciduous)  :3205-3209  (RmSpecPlant 0.010)
RCO2Y = AZMAX1(RCO2NonstC - RCO2Maint)*TurgEff4CanopyResp;  RMxess = AZMAX1(RCO2Maint - RCO2NonstC)  :3220-3222
RFN1  = ZPOOLB*YCO2Gro/(CNSHX + CNLFM + CNLFX*CNPG)  (RFP1 for P);  RgroCO2_ltd = min(RCO2Y, RFN1, RFP1)   :3237-3246
RNonstC4Groth_brch = RgroCO2_ltd/YCO2Gro_brch                      :3266
N, P used = AZMAX1(AMIN1(pool, RNonstC4Groth*(CNSHX + CNLFM + CNLFX*CNPG)))   :3267-3268
C used    = AMIN1(RCO2Maint,RCO2NonstC) + RNonstC4Groth + AZMAX1(1.70*N used - 0.025*CH2O)  :3269-3270
```

The nonstructural pools are then debited and credited with the hour's fixation (`UpdatePhotosynthates`, `:887-889`). A higher organ yield raises the C fixed in that organ per unit consumed AND lowers `YCO2Gro`, which raises `RNonstC4Groth` for a given growth respiration; a higher organ N:C raises the N cost and can make `RFN1` the limiting term.

## 6. Organ growth (`BranchBiomAllocate`)

`BranchBiomAllocate` (`PlantBranchMod.F90:333-440`) distributes `RNonstC4Groth_brch`:

```
Growth(C,leaf)  = RNonstC4Groth*PART(leaf)*DMLFB          :384      Growth(C,stalk) = ...*PART(stalk)*DMSTK   :386
Growth(C,pet)   = ...*PART(pet)*DMSHB                      :385      Growth(C,rsv)   = ...*PART(rsv)*DMRSV     :387
Growth(C,husk|ear|grain) = ...*DMHSK | DMEAR | DMGR        :388-390
fNCLFW_brch = CNLFB*(ZPLFM + ZPLFD*CNPG);  Growth(N,leaf) = Growth(C,leaf)*fNCLFW_brch     :392-393
Growth(N,pet) = *CNSHB; (N,stalk) = *CNSTK; (N,rsv) = *CNRSV; (N,husk) = *CNHSK; (N,ear) = *CNEAR; (N,grain) = *CNRSV   :394-399
(P analogues with fPCLFW_brch = CPLFB*(ZPLFM + ZPLFD*CNPG), CPSHB, CPSTK, CPRSV, CPHSK, CPEAR, CPRSV)   :401-408
```

So CNLF and CPLF are MAXIMUM leaf ratios: the realised N:C of new leaf is between 0.33 and 1.0 times CNLF according to the branch's nonstructural N and P status `CNPG`; every other organ takes its ratio exactly. Leaf, petiole, stalk, reserve, husk and ear growth are added to the branch pools (`:410-417`). The grain partition is NOT added to grain: `GrainFillOnBranch` adds it to the stalk RESERVE (`:2266`) and fills grain from the reserve (section 10), which is why it is priced at the reserve ratios CNRSV/CPRSV. The etiolation coefficient `EtiolationCoeff = AMAX1(1 + min(N, P nonstructural saturation), 1)` (`:426-429`) multiplies the expansion laws below; leaf growth starts at node 0 on the main branch until the hypocotyl reaches the seed depth (`:433-437`). The hourly canopy structural-C growth is written as CAN_GROWTH_pft (`:162`; `f90src/IOutils/HistData/HistUpdatePlant.F90:158`).

## 7. Leaf, sheath and internode expansion; the leaf-protein co-limitation

Growth is spread evenly over the concurrently growing nodes from `KHiestGroLeafNode_brch - NumCogrowthNode_pft + 1` to `KHiestGroLeafNode_brch` (`PlantBranchMod.F90:3537-3545`); `NumCogrowthNode_pft` and `FracGroth2Node_pft` come from the type flags, GROUPX and XRLA (`f90src/Ecosim_mods/StartqMod.F90:412-429`; [`phenology.md`](phenology.md) section 3). At each node (`GrowLeavesOnBranch`, `:3504-3587`):

```
LeafProteinC_node += AMIN1(GrowthElms(N)*rProteinC2LeafN_pft, GrowthElms(P)*rProteinC2LeafP_pft)   :3561-3562
dMC = AZMAX1(1e-12, LeafC_node/(PlantPopu*ALLOCL*FracGroth2Node*NumCogrowthNode))                  :3547, :3578
SpecAreaLeafGrowth = EtiolationCoeff*SLA1*dMC**SLA2*TurgEff4LeafPetolExpansion   (SLA2 = -0.33)    :3579; PlantBGCPars.F90:276
LeafAreaGrowth = GrowthElms(C)*SpecAreaLeafGrowth;  LeafAreaLive_brch += LeafAreaGrowth              :3580-3582
```

SLA1 is the coefficient of a power law in per-plant node leaf mass, so its effective units are m2 gC^-0.67, not the file's m2 gC-1; the operative specific area falls as a node's leaf mass grows, rises with etiolation and is zero without turgor above 0.1 MPa. Sheath length uses SSL1 with `SSL2 = -0.50` and is scaled by the sheath angle (`:3662-3665`; `PlantBGCPars.F90:277`); sheath protein uses the LEAF protein ratios (`:3644-3645`). Internode length uses SNL1 with `SNL2 = -0.67` on stalk C per plant and the branch angle (`:3731-3733`, `:3753`; `PlantBGCPars.F90:278`).

**Leaf protein co-limitation.** The N and P supplies are the leaf growth N and P of section 6, set by CNLF and CPLF (times `ZPLFM + ZPLFD*CNPG`) and by the hour's C growth; CNWL and CPWL convert them to protein C. Leaf protein accumulates at the SMALLER of the two products (`:3561-3562`), so only the binding branch has leverage. Downstream, protein per leaf area `LeafProteinC_node/LeafArea_node` (`f90src/Plant_bgc/StomatesMod.F90:785`, `LiveBranchPhotosynthesis`) sets the Rubisco surface density `LeafRubisco2Protein_pft*ProteinCLeafAreaDensity` (`:422`, `C3Photosynthesis`) and hence `VcMaxRubiscoRef_node` and `Vmax4RubiscoCarboxy_node` (`:441-443`); C4 branches use the same protein pool for PEPC, chlorophyll and bundle-sheath Rubisco (`StomatesMod.F90:127-143`). SLA1 is therefore also a protein-dilution lever: more area per C means less protein per m2. Protein is removed asymmetrically, at the LARGER product: nutrient withdrawal subtracts `AMAX1(XFRE(N)*CNWL, XFRE(P)*CPWL)` (`PlantBranchMod.F90:323-324`, `WithdrawNutBranchLeaves`), leaf remobilization `Frac2fall*AMAX1(leafN*CNWL, leafP*CPWL)` (`:1124-1126`, `RemobizeLeafNodes`; petiole `:1253-1255`) and node-age kill `AMAX1(killN*CNWL, killP*CPWL)` (`:4080`, petiole `:4181`, `SenescenceBranch`).

**Excess-nutrient withdrawal.** `WithdrawNutBranchLeaves` (`:261-330`) moves leaf N and P back to the nonstructural pool when the leaf is richer than the pool, at `1e-3` of the concentration gradient, never below `ZPLFM*CNLFB` (or `CPLFB`) times leaf C (`:310-313`), with N and P withdrawals tied by factors 10 and 0.1 (`:315-316`). Under `guard_floor_dying_stand` the gradient's denominator is floored (`:308-309`; switch default-off, see [`roots_and_uptake.md`](roots_and_uptake.md) section 13).

## 8. Senescence, remobilization and recycling

**Recycling fractions** (`PlantBranchMod.F90:188-207`): from the branch nonstructural saturations `CCC`, `CNC`, `CPC`, the remobilised fractions are `RCCC = RCCZ + CCC*RCCY`, `RCCN = CNC*RCCX`, `RCCP = CPC*RCCQ`, indexed by IGTYP (`RCCZ = (0.167,0.167,0.167,0.056)`, `RCCY = (0.333,0.333,0.167,0.333)`, `RCCX = RCCQ = (0.417,0.833,0.833,0.833)`, `PlantBGCPars.F90:305-308`).

**Node-age turnover** (`SenescenceBranch`, `:3939-4186`). Only when development is active (`doSenescence_brch`, set with node growth, `PlantPhenolMod.F90:957-962`) and the highest growing node exceeds `MaxNodesPerBranch1 = 25` (`:3994-3997`), the oldest node is killed at `RSpecKillLeafPetol = fTCanopyGroth*XRLA` per hour (`:3999`), clipped to what remains (`:4029-4040`); the recycled share returns to the nonstructural pool and the rest goes to fine and woody litter (`:4052-4085`). XRLA thus sets leaf turnover as well as leaf appearance.

**Maintenance deficit and phenological senescence** (`RemobilizeBranch`, `:3766-3936`). Outside remobilization the deficit `RMxess_brch` is first respired from the stalk reserve at up to `VMXC*reserve*fTCanopyGroth` (`:3818-3832`). During remobilization of perennials, phenological senescence adds `RateK4ShootSeaStoreNonstEXfer(IBTYP)*leaf+sheath C*AMIN1(1, HoursDoingRemob/240)` (`:3848-3853`; `Hours4FullSenes = 240`, `PlantBGCPars.F90:220`). The total is taken from other branches' nonstructural pools (woody main branch only, `:3868-3919`) and then from leaf layers by `RemobilizeLeafLayers` (`:3922`), which drops leaves to litter and returns recycled C, N, P.

**Seasonal and terminal resets** are described on [`phenology.md`](phenology.md) section 8 (`ResetNonAnnualBranch`, `ResetBranchPhenology`, `RemoveDeadAnnual`).

## 9. Shoot nonstructural transfers

`BranchElmntTransfer` (`PlantBranchMod.F90:2731-2860`): at leaf-out the main branch draws seasonal storage through `DevelopMainBranch` (`:2795-2797`; routine `:2863-3104`), at `GVMX(ISTYP)*fTCanopyGroth*turgor` of storage C per hour for the first `HourReq2InitSStor4LeafOut(ISTYP) = (68.96, 276.9)` growing hours, split shoot:root `FX2SH = (0.50, 0.75)` (`:2928-2969`; `PlantBGCPars.F90:314`, `:318`); secondary branches equalise with the main branch (`:2806-2819`). During remobilization perennials return leaf and reserve nonstructural C, N, P to seasonal storage (`SeasonStoreShootTransfer`, `:2826-2828`; `f90src/Plant_bgc/PlantNonstElmDynMod.F90:690-766`). After the seed-number stage (annuals) or jointing (perennials) the leaf pool exchanges with the stalk reserve at `FXFY = (0.025, 0.005)` h-1 for C and `FXFZ = (0.25, 0.05)` for N and P (`PlantBranchMod.F90:2840-2850`; `PlantNonstElmDynMod.F90:769-811`; `PlantBGCPars.F90:316`). `RepleteSeaStoreByStalk` refills storage from the reserve (`PlantBranchMod.F90:2855`). The shoot-root exchange controlled by PTSHT and the root-side transfers are on [`roots_and_uptake.md`](roots_and_uptake.md) section 6.

**N and P gradient transfers (`NonstGradt`).** Three routines move N and P (never C; the loops run `NE=2..NumPlantChemElms`) between two nonstructural pools A and B with the same form. With C masses `A_C`, `B_C` and element masses `A_E`, `B_E`,

```
NonstGradt = (A_E*B_C - B_E*A_C)/(A_C + B_C) = [A_C*B_C/(A_C + B_C)]*(A_E/A_C - B_E/B_C)
flux A -> B = rate constant * NonstGradt
```

so the sign is set by which pool has the higher N:C (or P:C), and the magnitude by that ratio difference times the series combination of the two C masses. None of them is a direct shoot-root gradient; that exchange is `ShootRootElmTransfer` with PTSHT ([`roots_and_uptake.md`](roots_and_uptake.md) section 6).

| routine and when it runs | A -> B | rate constant (h-1) | sign kept | file:line |
|---|---|---|---|---|
| `DevelopMainBranch`, main branch of a perennial (ISTYP 1) with seasonal storage C above `ZERO4Groth_pft` | `SeasonalNonstElms_pft` -> `CanopyNonstElms_brch` of the main branch; denominator guarded, `NonstGradt = 0` when `CPOOLT = 0` | `FRSV(IBTYP)` = 0.025 for IBTYP 0 and 1, 0.001 for 2 and 3 | positive only (`AZMAX1`) | `PlantBranchMod.F90:2982-2985`, `:3011-3019`; `PlantBGCPars.F90:315` |
| same | `SeasonalNonstElms_pft` -> `TotalRootNonstElms`, the plant-root nonstructural pools summed over `L=NU..MaxSoilLays4Root_pft` (`:3044-3049`); denominator floored at `ZERO4Groth_pft` | `FRSV(IBTYP)` | positive only | `:3051-3058` |
| `StalkRsrvShootNonstTransfer`, every branch after the seed-number stage (annuals) or jointing (perennials) | `CanopyNonstElms_brch` -> `StalkRsrvElms_brch` | `FXFZ(ISTYP)` = 0.25, 0.05 | both signs (`AZERO` only zeroes `abs < 1e-10`), capped at 0.9999 of the donor by `ExchFluxLimiter` | `PlantNonstElmDynMod.F90:799-807`; `PlantBGCPars.F90:316`; `PlantMathFuncMod.F90:350-361` |
| `StalkRsrvRootNonstTransfer`, annuals after the seed-number stage, per root layer with pore volume | plant-root `RootMycoNonstElms_rpvr(NE,ipltroot,L)` -> `StalkRsrvElms_brch` | `FXFZ(ISTYP)` | positive only, then `ExchFluxLimiter` | `PlantNonstElmDynMod.F90:855-865` |

`BranchElmntTransfer` calls `DevelopMainBranch` for the main branch inside its leaf-out and remobilization gate (`PlantBranchMod.F90:2771`, `:2795-2797`) and the two stalk-reserve routines at `:2840-2850`. In `DevelopMainBranch` the N and P block (`:2982-3069`) sits outside the leaf-out timing test that limits the C draw `CH2OH` (`:2933`), so for perennials the two gradient transfers run every hour the routine is called while storage C remains. Annuals instead move N and P in proportion to the C draw, `FX2SH*CH2OH*storage E:C` to the shoot and `FX2RT*CH2OH*storage E:C` to the roots (`:3022-3025`, `:3060-3063`), and once storage C is gone every growth habit moves `FX2SH` and `FX2RT` of the remaining storage N and P per hour (`:3029-3031`, `:3066-3068`). The root share is spread over layers by each layer's share of root nonstructural C, or put in the top root layer when the roots hold none (`:3087-3099`). The C exchanges of the two stalk-reserve routines are concentration gradients per unit structural C rather than `NonstGradt`: shoot side `CPOOLD = (CanopyNonst_C*SapwoodBiomassC - StalkRsrv_C*CanopyLeafSheathC)/(CanopyLeafSheathC + SapwoodBiomassC)` at `FXFY(ISTYP)` = 0.025, 0.005, both signs (`PlantNonstElmDynMod.F90:788-797`); root side the same with the root's woody active C `WTRTRX` in place of leaf and sheath C, positive only, root to reserve (`:841-852`). In each stalk routine the N and P gradient is evaluated after its C transfer. What these transfers drive: they set the N:C and P:C of the branch pool, which `CNPG` reads (section 5), and of the root pools, which the root growth allowance `FNP` and the uptake feedbacks `FZUP`, `FPUP` read ([`roots_and_uptake.md`](roots_and_uptake.md) sections 4 and 9).

## 10. Seed set and grain fill

`GrainFillOnBranch` (`PlantBranchMod.F90:2060-2313`): between jointing and anthesis, potential seed sites grow with stalk C growth times STMX (`:2118`); from anthesis to the seed-number stage the seed number grows with `SDMX*sites*SeedSET*dReproNodeNumNormByMatG` minus a temperature loss `FGRNX*seeds` (`:2166-2168`), where `FGRNX = SeedTempSens*(CTC - Tcanopy)` below CTC or `SeedTempSens*(Tcanopy - HighTempLimitSeed)` above the ZTYPI-based limit, before the seed-number stage (`:2144-2161`); seed size grows toward GRMX (`:2178-2183`). From begin-seed-fill the grain draws from the stalk reserve at up to `GFILL*seeds*sqrt(fTCanopyGroth)` (below-ground storage uses the root temperature function) and only while grain N:C and P:C stay above `ZPGRM` times CNGR/CPGR (`:2198-2223`); N and P move with the reserve's own saturation, bounded by CNGR/CPGR (`:2240-2256`). The reserve receives the grain partition growth and loses the transfer (`:2266-2267`).

## 11. Standing dead and litter

`Live2DeadTransformation` (`GrosubsMod.F90:125-258`) decays standing dead to surface litter at `StandingDeadKd_decid = 1.5814e-4 h-1` for IBTYP 0 or non-woody PFTs and `StandingDeadKd_other = 1.5814e-5 h-1` otherwise, times `fTCanopyGroth` (`:131-132`, `:181-185`, `:206-219`), and sums litterfall over layers 0 to `MaxNumRootLays` (`:237-250`). Litter partitions among protein, carbohydrate, cellulose and lignin are fixed per PFT class at initialisation (`StartqMod.F90:190-404`, `PlantLitterFractions`).

## 12. Producing equations of the biomass and NPP outputs

| Output | Producing chain at cb243228 |
|---|---|
| LEAF_C_pft | `LeafStrutElms_pft(ielmc)/AREA` (`HistUpdatePlant.F90:196`); `LeafStrutElms_pft = AZMAX1(sum over branches of LeafStrutElms_brch)` (`PlantBalMod.F90:293`, `SumCanopyBiome`); `LeafStrutElms_brch += Growth(C,leaf)` (`PlantBranchMod.F90:411`) with `Growth(C,leaf) = RNonstC4Groth*PART(leaf)*DMLF` (`:384`), minus withdrawal, remobilization, node-age kill and seasonal reset (`:320`, `:1128`, `:1194`, `:4083`, `:2457`). Structural leaf only; nonstructural C is not included |
| LAI_xstk_pft | `CanopyLeafArea_pft/AREA` (`HistUpdatePlant.F90:214`); `CanopyLeafArea_pft = sum of LeafAreaLive_brch` (`GrosubsMod.F90:644`, `:653`, `AccumulateStates`); `LeafAreaLive_brch += GrowthC*EtiolationCoeff*SLA1*dMC**SLA2*TurgEff` (`PlantBranchMod.F90:3579-3581`), minus `:1121`, `:4078`, zeroed at `:2456` and when a branch has no leaf+sheath C (`GrosubsMod.F90:634-638`) |
| SHOOT_C_pft | `ShootElms_pft(ielmc)/AREA` (`HistUpdatePlant.F90:191`); `ShootElms_pft = AZMAX1(sum of ShootElms_brch)` (`PlantBalMod.F90:292`); `ShootElms_brch = leaf + petiole + stalk + reserve + husk + ear + grain + branch nonstructural` (`:379-382`, `SumPlantBranchBiome`), plus C4 bundle-sheath and mesophyll pools (`:386-393`). Excludes seasonal storage, standing dead and canopy nodules |
| Plant_C_pft | `(ShootElms_pft(ielmc) + RootElms_pft(ielmc))/AREA` (`HistUpdatePlant.F90:192-193`); root sum on [`roots_and_uptake.md`](roots_and_uptake.md). Excludes seasonal storage `SeasonalNonstElms_pft` (SSTORED_C_pft, `:212`) and standing dead |
| STALK_C_pft, RESERVE_C_pft, PetolSheth_C_pft | `StalkStrutElms_pft`, `StalkRsrvElms_pft`, `PetolShethStrutElms_pft` over AREA (`HistUpdatePlant.F90:197-199`; sums at `PlantBalMod.F90:294-296`) |
| NPP_pft | `NetPrimProduct_pft/AREA` (`HistUpdatePlant.F90:94`); `NetPrimProduct_pft = GrossCO2Fix_pft + GrossResp_pft` (`GrosubsMod.F90:253`, `Live2DeadTransformation`). See the caveat below |

**NPP_pft is gross fixation at cb243228.** `ZeroGrosub` zeroes `GrossResp_pft` and `GrossCO2Fix_pft` at the start of every hour (`PlantBalMod.F90:503-504`; called from `EnterPlantBalance`, `:734`, at `PlantMod.F90:73`). `GrossCO2Fix_pft` accumulates during `GROWPLANTS` (`PlantBranchMod.F90:3289`), but `GrossResp_pft = RootAutoCO2_pft + CanopyGrosRCO2_pft` is assigned only in `SumPlantBiome` (`PlantBalMod.F90:101`), which runs inside `ExitPlantBalance` (`PlantMod.F90:95`) AFTER `Live2DeadTransformation` has evaluated NPP. NPP_pft therefore equals CAN_GPP_pft (`HistUpdatePlant.F90:155`) except in hours with grazing, where grazing subtracts its respiration first (`PlantDisturbByGrazingMod.F90:71`). The same ordering existed at 2dea74d9. An hourly PFT NPP is CAN_GPP_pft + AUTO_RESP_pft (`HistUpdatePlant.F90:215`, written after the balance sum); the stand total ECO_NPP_col is computed correctly as cumulative `Eco_GPP_CumYr_col + Eco_AutoR_CumYr_col` (`f90src/Balances/RedistMod.F90:226`).

## 13. Constants used here (`PlantBGCPars`)

| Constant | Value | Line | Role |
|---|---|---|---|
| `PART2LEAF_MIN`, `PART2PETOL_MIN` | 0.05, 0.02 | `PlantBGCPars.F90:215-216` | partition floors |
| `VMXC` | 0.015 h-1 | `:217` | nonstructural C oxidation rate |
| `XFRX` | 0.025 | `:221` | reserve buffer threshold (reserve/sapwood) |
| `CNKI`, `CPKI` | 0.1, 0.01 | `:226-227` | nonstructural N, P saturation constants |
| `RmSpecPlant` | 0.010 gC gN-1 h-1 | `:228` | maintenance per structural N |
| `ZPLFM`, `ZPLFD` | 0.33, 0.67 | `:247-248` | minimum and range of realised leaf N:C, P:C |
| `SLA2`, `SSL2`, `SNL2` | -0.33, -0.50, -0.67 | `:276-278` | expansion exponents |
| `FracHour4LeafoffRemob(0:5)` | 0.75, 0.5, 0.5, 0.5, 0.5, 0.5 | `:214` | remobilization start fraction of VRNXI |
| `FX2SH(0:1)`, `FX2RT = 1 - FX2SH` | 0.50, 0.75 | `:314` | shoot and root shares of the storage C draw at leaf-out (by ISTYP) |
| `FRSV(0:3)` | 0.025, 0.025, 0.001, 0.001 h-1 | `:315` | storage-to-shoot and storage-to-root N, P gradient transfer of perennials, `DevelopMainBranch` (by IBTYP) |
| `FXFY(0:1)`, `FXFZ(0:1)` | 0.025, 0.005; 0.25, 0.05 h-1 | `:316` | leaf-reserve and root-reserve C and N, P exchange (by ISTYP) |

## 14. Calibration parameters: source map

All reads are the live reads in `ReadPlantTraitTable` (`f90src/IOutils/PlantInfoMod.F90:1708-1849`) with per-PFT copies in `SetPlantTraits` (`:696-868`); the duplicate reads in `ReadPlantTraitsNC` (`:540-694`) have no caller.

| File name | Fortran variable | Read at (file:line, subroutine) | Every use site at cb243228 (subroutine, file:line, branch) | What it does (the equation, quoted) |
|---|---|---|---|---|
| DMLF | `LeafBiomGrowthYld_tab` -> `LeafBiomGrowthYld_pft` | `PlantInfoMod.F90:1814` (`ReadPlantTraitTable`); copy `:817` | `UpdateBranchAllometry` `PlantBranchMod.F90:497` (after emergence only; `DMLFB=RootBiomGrosYld_pft` before) -> `DMLFB` used in `:512` (`DMSHT`), `:517-520` (leaf N/P costs), `BranchBiomAllocate` `:384` | `DMLFB = LeafBiomGrowthYld_pft(NZ)`; `Growth_brch(ielmc,ibrch_leaf)=RNonstC4Groth_brch*PART(ibrch_leaf)*DMLFB`; enters `YCO2Gro_brch=1.0_r8-DMSHT`. A yield, not a partition fraction: DM* values do not sum to 1 |
| DMSTK | `StalkBiomGrowthYld_tab` -> `StalkBiomGrowthYld_pft` | `PlantInfoMod.F90:1816`; copy `:819` | `BranchBiomAllocate` `PlantBranchMod.F90:386`; `UpdateBranchAllometry` `:512`, `:522`, `:529`; `StructuralRootThickening` `RootMod.F90:2364`, `:2367`, `:2424` (woody, `flag2ndGrowth`); `SecondaryGrowthZone` `RootMod.F90:3475`, `:3478`, `:3528` (dead: call commented out at `:3218`) | `Growth_brch(ielmc,ibrch_stalk)=RNonstC4Groth_brch*PART(ibrch_stalk)*StalkBiomGrowthYld_pft(NZ)`; stalk N cost `PART(ibrch_stalk)*StalkBiomGrowthYld_pft*rNCStalk_pft`; woody root thickening `DMRespEff=1._r8-StalkBiomGrowthYld_pft` |
| DMRSV | `ReserveBiomGrowthYld_tab` -> `ReserveBiomGrowthYld_pft` | `PlantInfoMod.F90:1817`; copy `:820` | `BranchBiomAllocate` `PlantBranchMod.F90:387`; `UpdateBranchAllometry` `:513`, `:523`, `:530` | `Growth_brch(ielmc,ibrch_resrv)=RNonstC4Groth_brch*PART(ibrch_resrv)*ReserveBiomGrowthYld_pft(NZ)`; reserve N cost `PART(ibrch_resrv)*ReserveBiomGrowthYld_pft*rNCReserve_pft` |
| SLA1 | `SLA1_tab` -> `SLA1_pft` | `PlantInfoMod.F90:1769`; copy `:766` | `GrowLeavesOnBranch` `PlantBranchMod.F90:3579` only | `SpecAreaLeafGrowth=EtiolationCoeff*SLA1_pft(NZ)*dMC**SLA2*TurgEff4LeafPetolExpansion`, `LeafAreaGrowth=GrowthElms(ielmc)*SpecAreaLeafGrowth`; coefficient of a power law (SLA2 = -0.33), effective units m2 gC^-0.67 |
| CNLF | `rNCLeaf_tab` -> `rNCLeaf_pft` | `PlantInfoMod.F90:1825`; copy `:828` | `StagePlantForGrowth` `GrosubsMod.F90:463` only -> `CNLFW` -> `CNLFB` (`PlantBranchMod.F90:499`) -> `fNCLFW_brch` (`:392`), leaf N costs (`:517`, `:519`), withdrawal floor (`:311`) | `CNLFW=...*rNCStalk_pft+FracLeafShethElmAlloc2Litr(ielmc,k_fine_comp)*rNCLeaf_pft` with the woody share 0, so `CNLFW = rNCLeaf_pft`; realised `fNCLFW_brch=CNLFB*(ZPLFM+ZPLFD*CNPG)`. MAXIMUM leaf N:C; it is the N SUPPLY into the leaf-protein AMIN1 |
| CPLF | `rPCLeaf_tab` -> `rPCLeaf_pft` | `PlantInfoMod.F90:1838`; copy `:842` | `StagePlantForGrowth` `GrosubsMod.F90:464` only -> `CPLFW` -> `CPLFB` (`PlantBranchMod.F90:501`) -> `fPCLFW_brch` (`:401`), leaf P costs (`:518`, `:520`), withdrawal floor (`:313`) | `fPCLFW_brch=CPLFB*(ZPLFM+ZPLFD*CNPG)`, `Growth_brch(ielmp,ibrch_leaf)=Growth_brch(ielmc,ibrch_leaf)*fPCLFW_brch`; MAXIMUM leaf P:C; P SUPPLY into the leaf-protein AMIN1 |
| CNWL | `rProteinC2LeafN_tab` -> `rProteinC2LeafN_pft` | `PlantInfoMod.F90:1824`; copy `:826` | `GrowLeavesOnBranch` `PlantBranchMod.F90:3562`; `GrowPetolShethOnBranch` `:3645`; `WithdrawNutBranchLeaves` `:324`; `RemobizeLeafNodes` `:1125`, `:1254`; `SenescenceBranch` `:4080`, `:4181` | `LeafProteinC_node=LeafProteinC_node+AMIN1(GrowthElms(ielmn)*rProteinC2LeafN_pft,GrowthElms(ielmp)*rProteinC2LeafP_pft)`; removals use `AMAX1(...*rProteinC2LeafN_pft, ...*rProteinC2LeafP_pft)` |
| CPWL | `rProteinC2LeafP_tab` -> `rProteinC2LeafP_pft` | `PlantInfoMod.F90:1837`; copy `:840` | same sites as CNWL: `PlantBranchMod.F90:3562`, `:3645`, `:324`, `:1126`, `:1255`, `:4080`, `:4181` | P branch coefficient of the same AMIN1; leaf protein then sets `ProteinCLeafAreaDensity=LeafProteinC_node/LeafArea_node` (`StomatesMod.F90:785`) and `MesophyllRubiscoSurfDensity` (`:422`) |
| CNSHE | `rNCSheath_tab` -> `rNCSheath_pft` | `PlantInfoMod.F90:1826`; copy `:829` | `StagePlantForGrowth` `GrosubsMod.F90:465` only -> `CNSHW` -> `CNSHB` (`PlantBranchMod.F90:500`) -> `:394`, `:521`; woody petiole litter N fraction `GrosubsMod.F90:475` | `Growth_brch(ielmn,ibrch_petole)=Growth_brch(ielmc,ibrch_petole)*CNSHB`; exact (not a maximum) sheath N:C after emergence |
| CNSTK | `rNCStalk_tab` -> `rNCStalk_pft` | `PlantInfoMod.F90:1827`; copy `:830` | `BranchBiomAllocate` `PlantBranchMod.F90:395`; `UpdateBranchAllometry` `:522`, `:543` (sapwood structural N for maintenance); `StagePlantForGrowth` `GrosubsMod.F90:463`, `:465` (multiplied by a woody share that is always 0), `:467` (root growth, woody PFTs), `:472`, `:475`, `:478` (woody litter N fractions); `InitStandingDead` `StartqMod.F90:132` | `Growth_brch(ielmn,ibrch_stalk)=Growth_brch(ielmc,ibrch_stalk)*rNCStalk_pft(NZ)`; `ShootStructE_brch(ielmn)=...+SapwoodBiomassC_brch*rNCStalk_pft`, the base of `RCO2Maint_brch=AZMAX1(RmSpecPlant*TFN5*ShootStructN_brch)`; does NOT reach leaf or sheath N:C |
| CNRSV | `rNCReserve_tab` -> `rNCReserve_pft` | `PlantInfoMod.F90:1829`; copy `:832` | `BranchBiomAllocate` `PlantBranchMod.F90:396` (reserve), `:399` (grain partition); `UpdateBranchAllometry` `:523`, `:526` | `Growth_brch(ielmn,ibrch_resrv)=Growth_brch(ielmc,ibrch_resrv)*rNCReserve_pft(NZ)` and `Growth_brch(ielmn,ibrch_grain)=Growth_brch(ielmc,ibrch_grain)*rNCReserve_pft(NZ)`: the grain partition is added to the reserve (`:2266`), so CNRSV prices both |
