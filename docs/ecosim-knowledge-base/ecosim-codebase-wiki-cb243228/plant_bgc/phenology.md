---
**Source pin:** EcoSIM commit `cb243228` (jingtao-lbl/EcoSIM `fix/r2-plant-balance`; upstream `09eb674a` + 2 fix commits)
**Scope:** `f90src/Plant_bgc/PlantPhenolMod.F90`, phenology parts of `PlantBranchMod.F90`, `StomatesMod.F90`, `UptakesMod.F90`, `GrosubsMod.F90`, `PlantDisturbsMod.F90`, `LitterFallMod.F90`, `InitPlantMod.F90`; `f90src/Prescribed_pheno/PrescribePhenolMod.F90`; `f90src/Ecosim_mods/StartqMod.F90`; `f90src/IOutils/PlantInfoMod.F90`; `f90src/Modelforc/WthrMod.F90`
**Last verified:** 2026-10-15
---

# Phenology, branching and the growth-stage calendar

Phenology in EcoSIM is resolved per BRANCH. Each branch carries its own node and leaf counters, its own leaf-out and leaf-off hour accumulators, and its own growth-stage calendar `iPlantCalendar_brch(stage,NB,NZ)`, which stores the day of year on which the branch reached each stage (0 = not reached). The PFT-level type flags select which accumulator rules apply (evergreen, cold deciduous, drought deciduous, cold+drought deciduous; annual or perennial; determinate or indeterminate; day-neutral, short-day or long-day). The leaf-out and leaf-off status then gates node growth, photosynthesis, remobilization, the seasonal reset of perennial branches and the mobilization of seasonal storage, so the phenology parameters reach GPP and biomass through several channels at once (section 9).

Growth, allocation and stoichiometry are on [`growth_and_allocation.md`](growth_and_allocation.md); roots and root-axis growth on [`roots_and_uptake.md`](roots_and_uptake.md); photosynthesis on [`photosynthesis_and_respiration.md`](photosynthesis_and_respiration.md).

## 1. Hourly entry point

`PhenologyUpdate` (`f90src/Plant_bgc/PlantPhenolMod.F90:46-109`) is called once per hour per column from `PlantModel` after `EnterPlantBalance` and before `ROOTUPTAKES` and `GROWPLANTS` (`f90src/APIs/PlantMod.F90:73`, `:82`, `:85`, `:88`). For each PFT with a parameter file (`DATAP .NE. 'NO'`, `PlantPhenolMod.F90:75`) it:

1. clears the hourly reproductive increment `dReproNodeNumNormByMatG_brch` (`:72`) and adds the live population to `PlantPopu_col` (`:79`);
2. calls `set_plant_flags` (`:83`; routine `:175-272`), which on the first hour of the day decides from planting and harvest dates whether the PFT is active and, on the planting day, calls `StartPlants` to initialise it (`:218-228`, `:250-260`);
3. for an active PFT calls `FindMainBranchNumber` (`:89`; `:391-417`, the live branch with the smallest branch id), `StagePlantPhenology` (`:91`; `:420-519`, which sums branch nonstructural C/N/P and computes canopy, branch and root nonstructural concentrations, `:463-516`), `TestPlantEmergence` (`:93`; `:522-566`) and `root_shoot_branching` (`:95`; `:275-388`);
4. if the main branch has emerged or the PFT is flagged for (re)initialisation, calls `Emerged_plant_Phenology` (`:97-99`; `:112-172`), which computes the environmental factors once and loops over branches (`:134-160`).

`StagePlantPhenology` does NOT compute the thermal offset or the maturity group: both are derived elsewhere (section 3).

## 2. Planting, emergence, branches and root axes

**Emergence.** The main branch emerges on the day the hypocotyl reaches the seed depth (with 1e-3 m tolerance) while shoot area is positive, AND the primary root has grown below the seed depth (`PlantPhenolMod.F90:555-557`); the emergence day is stamped in `iPlantCalendar_brch(ipltcal_Emerge,...)` (`:559-561`). Secondary branches are stamped on their first live hour and start with half the main branch's leaf-out hours (`live_branch_phenology`, `:945-951`).

**Branch initiation** (`root_shoot_branching`, `:275-388`). On the first hour of the day, with live population, when root turgor in the seeding layer exceeds `PSIMin4LeafExpansion = 0.1 MPa` (`:33`, `:320-323`), a perennial, or an annual before floral initiation (`:324`), adds a branch when either it has no branch yet and seasonal storage is positive, or canopy nonstructural C concentration exceeds PB, `NonstCMinConc2InitBranch_pft`, and PB is positive (`:327-329`). A new branch is added at the first dead slot if it is the main branch or the main stem has more nodes than `BranchNumber_pft + NumCogrowthNode_pft/FracGroth2Node_pft + XTLI` (`:334-336`). The branch count is capped by `BranchNumMax(0:3) = (5,1,1,1)` indexed by the turnover flag IBTYP (`:40`, `:339`), so only IBTYP 0 PFTs can have more than one branch. An annual tiller's maturity group is the PFT value minus its branch id (`:345-346`); perennials keep the PFT value (`:348`).

**Root-axis initiation** (`:370-382`) uses the same turgor gate, the node threshold `NumStructuralRootAxes/FracGroth2Node + XTLI` and PR, `NonstCMinCon2InitRoot_pft` (`:374-375`), capped at `MaxNumRootAxes` (`:378`). Root growth itself is documented on [`roots_and_uptake.md`](roots_and_uptake.md).

## 3. Derived phenology thresholds (read and initialisation time)

The live plant reader is `ReadPlantTraitTable` (`f90src/IOutils/PlantInfoMod.F90:1708-1849`), whose tables `SetPlantTraits` copies per PFT (`:696-868`). `ReadPlantProperties` (`:472-537`) runs every year (it is called from `READQ` for every PFT, `:98`) and derives:

| Derived variable | Equation at cb243228 | Citation |
|---|---|---|
| `MatureGroup_pft` (node number required for floral initiation) | `GROUPX - XTLI` | `PlantInfoMod.F90:514-515` |
| XRNI, XRLA, MatureGroup, XTLI when IBTYP is not 0 | each divided by `MaxNodesPerBranch = 25` | `PlantInfoMod.F90:517-522`, `f90src/Mesh/GridConsts.F90:29` |
| `HourReq4LeafOut_brch(NB)` | `AMIN1(4380, VRNLI + 144*ZTYPI*(NB-1))` for perennial evergreen, else `VRNLI` | `PlantInfoMod.F90:524-533` |
| `HourReq4LeafOff_brch(NB)` | `AMIN1(4380, VRNXI + 144*ZTYPI*(NB-1))` for perennial evergreen, else `VRNXI` | `PlantInfoMod.F90:528`, `:531` |
| `CriticPhotoPeriod_pft` | XDL, or the site maximum day length if XDL < 0 | `PlantInfoMod.F90:763`, `:852-854` |

At initialisation (`startq` at the start of the first year, `drivers/ecosim/EcoSIMAPI.F90:437`; `StartPlants` on every planting day, `PlantPhenolMod.F90:225`) `PFTThermalAcclimation` sets the thermal-adaptation offset and the leaf-out/leaf-off temperatures (`f90src/Ecosim_mods/StartqMod.F90:434-466`; same arithmetic in `f90src/Plant_bgc/InitPlantMod.F90:458-503`):

```
rPlantThermoAdaptZone = ZTYPI                                   StartqMod.F90:450
TempOffset_pft        = 2.667*(2.5 - rPlantThermoAdaptZone)     StartqMod.F90:451
TC4LeafOut_pft        = TCZD - TempOffset         (TCZD = 5 oC) StartqMod.F90:438, :452
TC4LeafOff_pft        = AMIN1(15, TCXD - TempOffset) (TCXD = 12) StartqMod.F90:439, :453
HighTempLimitSeed_pft = 27 + 3*ZTYPI (C3 non-soybean and C4), 30 + 3*ZTYPI (soybean)  StartqMod.F90:454-464
```

ZTYPI is labelled a zone (1 arctic/boreal ... 5 tropical, `f90src/Modelconfig/ElmIDMod.F90:171-175`), and the display routine bands it into those labels (`PlantInfoMod.F90:1092-1105`, `pft_display`), but the physics uses the real value: a fractional ZTYPI moves every threshold above linearly. A lower ZTYPI gives a larger `TempOffset_pft`, which is ADDED to canopy and soil temperatures before every Arrhenius growth and maintenance function (`UptakesMod.F90:1619`, `:1623`; `GrosubsMod.F90:501`, `:505`; `PlantPhenolMod.F90:1056`; `StomatesMod.F90:957`) and LOWERS the leaf-out and leaf-off temperature thresholds. Under a warming scenario (`ICLM = 2` with nonzero `TDTPX/TDTPN`) `CorrectClimate` shifts the zone by `0.30/2.667*DTA` and the maturity group by `0.30*DTA` (`f90src/Modelforc/WthrMod.F90:470-489`); that path uses 27 + 3Z for C3 and 30 + 3Z for C4 seed limits (`:480-484`), the reverse of the initialisation assignment.

Two node-growth constants are set at initialisation from the type flags (`StartqMod.F90:412-429`, `PlantLitterFractions`; `InitPlantMod.F90:436-452`, `PlantLitterFraction`): for IBTYP 0 or non-woody PFTs `FracGroth2Node_pft = 1` and the number of concurrently growing nodes is 2, 3, 4 or 5 for `MatureGroup_pft` up to 6, 10, 15 or above; for woody non-deciduous PFTs `FracGroth2Node_pft = AMAX1(1, 0.04/XRLA)` and 24 nodes grow at once.

## 4. Environmental factors on development

`CalcPhenolEnvfactor` (`PlantPhenolMod.F90:1034-1069`) returns, once per PFT per hour:

```
TKCO = TKGroth_pft + TempOffset_pft                          :1056
TFNP = calc_leave_grow_tempf(TKCO)                            :1057
       = exp(24.269 - 60000/(R*T)) / (1 + exp((197500-710T)/(R*T)) + exp((710T-218500)/(R*T)))
                                                              PlantMathFuncMod.F90:151-164
annual:    WFNG = exp(0.025*max(PSICanopy,-1000)),  OFNG = sqrt(PlantO2Stress)   :1058-1060
perennial: WFNG = 1, OFNG = 1                                 :1061-1064
```

`TKGroth_pft` is the soil-surface temperature before emergence and the instantaneous canopy temperature after (`UptakesMod.F90:1599-1605`, `SetCanopyGrowthFuncs`); it is not time-averaged. `WFNG*OFNG` and `TFNP` are written to the history as `CanPhenol_WSTRESS_pft` and `CanPhenol_TSTRESS_pft` (`PlantPhenolMod.F90:1065-1066`; `f90src/IOutils/HistData/HistUpdatePlant.F90:172-173`). Perennial development is deliberately insensitive to water and O2 stress (comment dated Mar 25 2026, `PlantPhenolMod.F90:1121-1129`).

## 5. Node initiation and leaf appearance

`UpdateBranchNodeNumber` (`PlantPhenolMod.F90:1072-1161`) advances a branch's node and leaf counters:

```
NodeInitRate   = max(0, XRNI*TFNP)                            :1104
LeafAppearRate = max(0, XRLA*TFNP)                            :1105
annual only: *OFNG before floral initiation, *WFNG before anthesis   :1110-1120
ShootNodeNum_brch += NodeInitRate;  NumOfLeaves_brch += LeafAppearRate   :1137-1138
after floral init: NodeNumNormByMatgrp = (ShootNodeNum - ShootNodeNumAtInitFloral)/MatureGroup   :1149
                   TotalNodeNumNormByMatgrp += NodeInitRate/(MatureGroup*2.0)                   :1150-1151
after anthesis:    ReprodNodeNumNormByMatrgrp = (ShootNodeNum - ShootNodeNumAtAnthesis)/MatureGroup :1155
                   dReproNodeNumNormByMatG = NodeInitRate/(MatureGroup*0.667)                   :1156-1157
```

XRNI and XRLA are rates per hour at 25 oC (`h-1` in `ecosim_pftpar_20260915.nc.cdl`), already divided by 25 for IBTYP not 0 (section 3). The counters are only advanced for evergreens or while `Hours4LeafOff_brch < HourReq4LeafOff_brch` (`PlantPhenolMod.F90:957-962`), which also sets `doSenescence_brch`, the switch for node-age turnover on [`growth_and_allocation.md`](growth_and_allocation.md) section 8. The hourly sums `RNodeInitiate_pft` and `RLeafAppear_pft` (`:1135-1136`) are written as RNodeAppear_pft and RLeafAppear_pft in per-day units (`HistUpdatePlant.F90:194-195`). `KHiestGroLeafNode_brch`, the index of the highest growing leaf, is the leaf count plus one, frozen at the floral-initiation leaf number for determinate annuals (`PlantPhenolMod.F90:144-156`).

## 6. Growth-stage calendar

Stage ids are declared in `f90src/Modelconfig/ElmIDMod.F90:130-140`. `live_branch_phenology` (`PlantPhenolMod.F90:915-1032`) tests only the first stage not yet reached each hour (`:972-1029`). The node-number tests are in `CheckBranchNodeState` (`:1164-1218`), with `GrothStageNorm4VegetaPheno = 2.0` and `GrothStageNorm4ReprodPheno = 0.667` (`:35-36`).

| Stage (id) | Routine | Node test (OR the forced path) |
|---|---|---|
| floral init (2) | `InitiateBranchFloral` `:1446-1531` | `ShootNodeNum > MatureGroup + ShootNodeNumAtInitFloral` (`:1189`) AND (leaf-out reached OR on/after the planting day with lengthening days) (`:1485-1486`, `:1495`); forced for perennial cold-deciduous and annual evergreen ("crop") PFTs on shortening days when the canopy is above the snow (`:1487-1494`); then the photoperiod test below |
| jointing (3) | `BranchStemJointing` `:1407-1443` | `NodeNumNormByMatgrp > 0.25*2.0` (`:1192`) |
| elongation (4) | `BranchStemElongation` `:1356-1404` | `> 0.50*2.0` (`:1195`); indeterminate annuals freeze `LeafNumberAtFloralInit` here (`:1398-1400`) |
| heading (5) | `BranchFlowerHeading` `:1309-1353` | `> 1.00*2.0` (`:1198`) |
| anthesis (6) | `BranchAnthesis` `:1258-1306` | leaves appeared exceed nodes at floral init (`:1201`); any perennial after heading (`:1294`); secondary branches wait for the main branch (`:1299`) |
| begin seed fill (7) | `BeginBranchSeedFill` `:1221-1255` | `ReprodNodeNumNormByMatrgrp > 0.50*0.667` (`:1204`) |
| seed number set (8) | inline `:1013-1018` | `> 1.00*0.667` (`:1207`) |
| seed mass set (9) | inline `:1024-1028` | `> 1.50*0.667` (`:1210`) |
| end seed fill (10) | `GrainFillOnBranch` | after `Hours4PhyslMature = 168` h without grain fill (`PlantBranchMod.F90:2289-2291`; `f90src/Modelpars/PlantBGCPars.F90:219`) |

For stages 3 to 7, perennial cold-deciduous PFTs that are not short-day, and annual drought-deciduous PFTs, are also pushed to the stage once leaf-off has completed (`Hours4LeafOff > HourReq4LeafOff` with leaf-out disabled) on shortening days (`PlantPhenolMod.F90:1244-1250`, `:1288-1297`, `:1339-1348`, `:1385-1394`, `:1429-1437`), so a deciduous perennial always reaches the late stages by autumn.

**Photoperiod at floral initiation** (`:1509-1527`). Day-neutral PFTs (IPTYP 0) pass. Otherwise `PPD = AZMAX1(XDL - DayLength)`, set to 0 for short-day PFTs while days lengthen (`:1512-1513`); short-day PFTs initiate when `PPD > XPPD`, long-day PFTs when `PPD < XPPD` (`:1516-1518`). Floral initiation records the node number, and for determinate annuals the final leaf number (`:1521-1526`). XDL and XPPD have no other live effect: the long-day drought-deciduous factor in `DevelopMainBranch` is `ATRPPD = EXP(-0.0*PPDX) = 1` (`PlantBranchMod.F90:2915-2920`).

## 7. Leaf-out and leaf-off accumulators by phenology type

`branch_specific_phenology` (`PlantPhenolMod.F90:569-684`) first updates the photoperiod counters: `Hours4LenthenPhotoPeriod_brch` grows by 1 each hour while today's day length is at least yesterday's and resets otherwise, and `Hours4ShortenPhotoPeriod_brch` the reverse (`:601-607`). It then dispatches on IWTYP, `iPlantPhenolType_pft` (`ElmIDMod.F90:158-161`):

**Evergreen (IWTYP 0), `CropEvergreenPhenology` (`:773-826`).** The accumulators are ASSIGNED, not accumulated: on lengthening days `Hours4Leafout_brch = Hours4LenthenPhotoPeriod_brch` (`:797-798`), so VRNLI counts hours since day length began to lengthen, i.e. since the winter solstice; when it reaches `HourReq4LeafOut_brch`, or on DOY 173 (north) / 355 (south), leaf-off hours reset and leaf-off is enabled (`:800-805`). On shortening days `Hours4LeafOff_brch = Hours4ShortenPhotoPeriod_brch` and the converse reset happens at `HourReq4LeafOff_brch` or DOY 355 / 173 (`:815-823`).

**Cold deciduous (IWTYP 1), `ColdDeciduousBranchPhenology` (`:829-912`).** While leaf-out is enabled and days lengthen (or shorten before leaf-off hours reach their requirement) (`:859-861`), each hour with `TCGroth >= TC4LeafOut` adds one leaf-out hour (`:864-866`); before the requirement is met, each hour colder than CTC removes one (`:868-873`); leaf-off hours reset when the requirement is met or on the solstice fallback day (`:874-878`). Leaf-off is enabled after floral initiation or on shortening days shorter than 12 h (`:881-885`), but leaf-off hours accrue only on shortening days, with leaf-off enabled AND floral initiation reached, for each hour with `TCGroth <= TC4LeafOff` (`:898-903`); reaching `HourReq4LeafOff` re-enables leaf-out and resets leaf-out hours (`:904-908`).

**Drought deciduous (IWTYP 2; 4 and 5 are subtropical/tropical placeholders), inline (`:620-675`).** While leaf-out is enabled, an hour with `PSICanopy >= PSIMin4LeafOut(IEBTYP)` adds one hour (`:626-629`), and before the requirement an hour with `PSICanopy < PSIMin4LeafOff(IEBTYP)` removes 12 (`:631-635`). Leaf-off hours accrue for each hour below `PSIMin4LeafOff` once leaf-out is disabled and leaf-off enabled (`:656-659`); for type 4 (5) leaf-off hours are also set to the shortening (lengthening) photoperiod counter once it exceeds `MaxPhotoHour4LeafOutOff = 3600` h (`:37`, `:661-669`). Thresholds: `PSIMin4LeafOut(2:4) = (-0.5, -1.5, -0.5) MPa` (`:34`), `PSIMin4LeafOff(0:4) = (-200, -2, -2, -2, -2) MPa` (`:39`; the declaration comment's unit `[h]` is wrong). Because `PSIMin4LeafOut` exists only for IEBTYP 2-4, `ReadPlantProperties` aborts the run for a drought-deciduous PFT with any other embryophyte type (`PlantInfoMod.F90:491-500`).

**Cold + drought deciduous (IWTYP 3), `ColdDroughtDeciduPhenology` (`:687-770`).** Leaf-out hours accrue when lengthening (or within 2 h of the maximum day length) AND warm AND turgid (`:721-726`); the penalty is 1.5 h when cold OR turgor is low (`:729-733`). Leaf-off hours accrue on shortening days (or day length below `24 - DayLenMax + 2`) when cold OR dry (`:756-761`). Leaf-out is AND, leaf-off is OR.

`Emerged_plant_Phenology` also counts hours with `PSICanopy < PSIMin4LeafOff` in `HoursTooLowPsiCan_pft` (`PlantPhenolMod.F90:167-169`); that counter is diagnostic only (written as WTR_STRESS_pft, `HistUpdatePlant.F90:220`).

## 8. Seasonal resets, maturity and termination

**Perennial (and annual drought-deciduous) reset.** When leaf-out completes, or leaf-off completes, `ResetBranchPhenology` calls `ResetNonAnnualBranch` (`PlantBranchMod.F90:2607-2616`; routine `:2316-2537`). At leaf-out a perennial branch restarts its calendar at emergence (`:2395-2406`); for IBTYP 0 it also drops all leaf and petiole to litter and restarts its node count at XTLI (`:2435-2466`), and husk, ear and grain go to litter (`:2473-2493`); for IBTYP 0 or non-woody PFTs the stalk goes to litter too (`:2494-2513`). The routine then toggles leaf-out/leaf-off enabling (`:2522-2534`).

**Post-maturity litterfall.** After the leaf-off toggle `Prep4Literfall_brch` drives a first-order litterfall of husk, ear and grain at `RSpecLiterFall = 2.884e-3 h-1` for `HoursReq4LiterfalAftMature = 960` h (`PlantBranchMod.F90:2620-2655`; `PlantBGCPars.F90:218`, `:302`); an annual non-evergreen's grain goes to seasonal storage instead of litter (`:2634-2638`).

**Annual termination.** Once the seed number is set, a branch counts hours without reserve-to-grain transfer (`PlantBranchMod.F90:2283-2287`); after 168 h it stamps end-of-seed-fill (`:2289-2291`) and after `168 + Hours4SenesAftMature(IWTYP)` h (`360, 1440, 720, 720`, `PlantBGCPars.F90:317`) it forces leaf-off for annual non-evergreens (`PlantBranchMod.F90:2306-2307`). The same counter ramps photosynthesis down: `GrainFillDowreg_brch = AZMAX1(1 - HourFailGrainFill/Hours2KillAnuals(IWTYP))` with `Hours2KillAnuals = (336, 672, 672, 672, 672, 672)` h (`StomatesMod.F90:24`, `:877-882`, `PhenoActiveBranch`). During the post-maturity litterfall window, `ResetBranchPhenology` turns an annual non-evergreen main branch into a terminate-and-reseed grain harvest that removes grain and drops leaves and stalk as litter (`PlantBranchMod.F90:2703-2723`); that window is opened only by the leaf-off toggle in `ResetNonAnnualBranch` (`:2528-2533`), which runs only for perennials and annual drought or cold+drought deciduous PFTs (`:2607-2608`), so an annual evergreen or cold-deciduous crop ends through its management harvest instead.

**False break of annual drought-deciduous plants.** `RemoveBiomassByDisturbance` calls `RemoveDeadAnnual` (`PlantDisturbsMod.F90:320`; routine `:116-219`), active only for annual IWTYP 2 or 3 (`:160-162`). At the last hour of each day, `eval_annual_false_break_death` (`:221-243`) flags a false break when the canopy has nonstructural C but zero height, seasonal storage C equals its daily mean, and storage mobilisation has run past `HourReq2InitSStor4LeafOut` (`:238-241`); after `Days2CallFalseBreak = 10` consecutive days the whole plant goes to litter and is reinitialised (`:173-213`; `PlantBGCPars.F90:304`).

**Dormant-seed activation.** For a PFT flagged for initialisation, the first branch that reaches its leaf-out requirement sets the planting date to today (`GrosubsMod.F90:189-199`, `Live2DeadTransformation`).

**Liveness flags.** `isPlantShootAlive_pft`/`isPlantRootAlive_pft` are set true by `root_shoot_branching` (`PlantPhenolMod.F90:341`, `:379`) and false by `SetDeadPlant` when every branch is dead (`LitterFallMod.F90:179-218`); `set_plant_flags` only sets `IsPlantActive_pft` and `iPlantStateLive_pft` (`PlantPhenolMod.F90:203-268`).

## 9. What the leaf-out and leaf-off status gates

| Gate | Condition | Citation |
|---|---|---|
| Photosynthesis (`PhotosynsDiag`, `PhotoActivePFT`) | evergreen OR `Hours4Leafout >= HourReq4LeafOut` OR `Hours4LeafOff < HourReq4LeafOff` | `StomatesMod.F90:115-117`, `:1031-1033` |
| Node initiation and leaf appearance; node-age senescence switch | evergreen OR `Hours4LeafOff < HourReq4LeafOff` | `PlantPhenolMod.F90:957-962` |
| Perennial remobilization and leaf-to-stalk/reserve partition redirect | `Hours4LeafOff >= FracHour4LeafoffRemob(IWTYP)*HourReq4LeafOff` (fractions 0.75, 0.5, ...) | `PlantBranchMod.F90:758-759`, `:780-785`; `PlantBGCPars.F90:214` |
| Storage mobilisation for leaf-out (`DevelopMainBranch`) | main-branch leaf-out reached (or annual, or planting) AND leaf-off below the remobilization fraction | `PlantBranchMod.F90:2766-2771`, `:2795-2797` |
| Perennial branch reset | leaf-out or leaf-off requirement reached | `PlantBranchMod.F90:2607-2616` |
| Floral initiation | leaf-out reached (or planting day) | `PlantPhenolMod.F90:1485`, `:1495` |
| Dormant-seed activation | leaf-out reached | `GrosubsMod.F90:191` |
| Cut-branch reset after harvest | non-evergreen with leaf-off below the remobilization fraction | `PlantDisturbsMod.F90:1028-1036` |

VRNLI and VRNXI therefore reach CAN_GPP_pft directly through the first row, as well as through leaf area.

## 10. PFT type flags used by phenology

All are read in `ReadPlantTraitTable` and copied in `SetPlantTraits`.

| File name | Variable | Read / copy | Values |
|---|---|---|---|
| IWTYP | `iPlantPhenolType_pft` | `PlantInfoMod.F90:1728`, `:719` | 0 evergreen, 1 cold deciduous, 2 drought deciduous, 3 both (`ElmIDMod.F90:158-161`); 4, 5 placeholders |
| ISTYP | `iPlantPhenolPattern_pft` | `:1725`, `:716` | 0 annual, 1 perennial (`ElmIDMod.F90:118-119`) |
| IDTYP | `iPlantDevelopPattern_pft` | `:1726`, `:717` | 0 determinate (`ElmIDMod.F90:128`), else indeterminate |
| IPTYP | `iPlantPhotoperiodType_pft` | `:1729`, `:720` | 0 neutral, 1 short, 2 long (`ElmIDMod.F90:142-144`) |
| IBTYP | `iPlantTurnoverPattern_pft` | `:1730`, `:721` | 0 all above ground, 1 leaf+petiole, 2 none, 3 between (comment `PlantInfoMod.F90:890-891`) |
| IGTYP | `iPlantRootProfile_pft` | `:1724`, `:715` | 0 bryophyte, 1 grass-like, 2 tree-like (`ElmIDMod.F90:121-123`) |
| IEBTYP | `iEmbryophyteType_pft` | `:1723`, `:713` | indexes `PSIMin4LeafOut/Off` |
| I2EXP | `iPlant2ndGrothPattern_pft` | `:1731`, `:722` | secondary growth; with IGTYP selects woody vascular (`PlantMathFuncMod.F90:270`) |

## 11. Prescribed-phenology mode

With `ldo_sp_mode = .true.` (`f90src/Modelconfig/EcoSIMCtrlMod.F90:80`) `PlantModel` skips `PhenologyUpdate`, `GROWPLANTS` and the balance bracket and only runs uptake and `extracts` (`PlantMod.F90:60-68`). `PrescribePhenologyInterp` (`f90src/Prescribed_pheno/PrescribePhenolMod.F90:185-320`) is called daily (`f90src/Modelforc/DayMod.F90:85`; under ATS from `f90src/ATSUtils/ATSEcoSIMAdvanceMod.F90:286`). It forces one PFT (`:216`) with hard-coded monthly LAI and SAI (`:201-202`), 17 m height (`:221`) and uniform leaf angle (`:222`), uses the ATS calendar when `ats_cpl_mode` and otherwise always interpolates from January (`kmo = 1`, `dofmon = 1`, `:227-238`), with weights `timwt(1) = it(1) + 0.5 - t` (`:240-249`). LAI and SAI are divided equally among canopy layers (`:270-271`) and leaf/stem area among zenith sectors in `SetCanopyProfile` (`:132-182`, called from `SurfaceRadiationMod.F90:61-63`). Roots come from the Jackson et al. (1997) beta profile in `SetRootProfileZ` (`:322-365`), whose totals are the kg m-2 values times 0.488 with no conversion to grams (`:345-348`); population is fixed at 0.6 (`:256`).

## 12. Calibration parameters: source map

All reads below are the LIVE reads in `ReadPlantTraitTable`; the duplicate reads in `ReadPlantTraitsNC` (`PlantInfoMod.F90:540-694`) are dead code with no caller.

| File name | Fortran variable | Read at (file:line, subroutine) | Every use site at cb243228 (subroutine, file:line, branch) | What it does (the equation, quoted) |
|---|---|---|---|---|
| VRNLI | `VRNLI_tab` -> local `VRNLI` -> `HourReq4LeafOut_brch` | `f90src/IOutils/PlantInfoMod.F90:1757` (`ReadPlantTraitTable`); copy `:754` (`SetPlantTraits`) | derive `PlantInfoMod.F90:527` (perennial evergreen) / `:530` (all others) (`ReadPlantProperties`); compared in `CropEvergreenPhenology` `PlantPhenolMod.F90:800` (IWTYP 0), `ColdDeciduousBranchPhenology` `:868`, `:874` (IWTYP 1), drought block of `branch_specific_phenology` `:631`, `:637` (IWTYP 2, 4, 5), `ColdDroughtDeciduPhenology` `:729`, `:735` (IWTYP 3), `InitiateBranchFloral` `:1485`; `ResetNonAnnualBranch` `PlantBranchMod.F90:2397`, `:2436`, `:2474`, `:2522`; `ResetBranchPhenology` `:2610`; `BranchElmntTransfer` `:2768`; `PhotosynsDiag` `StomatesMod.F90:116`; `PhotoActivePFT` `:1032`; `Live2DeadTransformation` `GrosubsMod.F90:191` | `HourReq4LeafOut_brch=AMIN1(4380.0_r8,VRNLI+144.0_r8*PlantInitThermoAdaptZone_pft*(NB-1))` (perennial evergreen) else `=VRNLI`: hours of leaf-out credit required. For evergreens the credit is hours since day length began to lengthen (`:798`); for cold deciduous hours with `TCGroth>=TC4LeafOut`; for drought deciduous hours with `PSICanopy>=PSIMin4LeafOut`. Gates photosynthesis, floral initiation, storage mobilisation, perennial reset |
| VRNXI | `VRNXI_tab` -> `VRNXI` -> `HourReq4LeafOff_brch` | `PlantInfoMod.F90:1758` (`ReadPlantTraitTable`); copy `:755` | derive `:528`, `:531`; `PlantPhenolMod.F90:671` (drought), `:762` (cold+drought), `:817` (evergreen), `:860`, `:904` (cold deciduous), `:957` (`live_branch_phenology`), `:1242`, `:1288`, `:1339`, `:1385`, `:1434` (stage forcing); `CalcPartitionCoeff` `PlantBranchMod.F90:759`; `GrainFillOnBranch` `:2307`; `ResetBranchPhenology` `:2611`; `BranchElmntTransfer` `:2767`; `StomatesMod.F90:117`, `:1033`; `ResetCutBranch` `PlantDisturbsMod.F90:1031` | `HourReq4LeafOff_brch=VRNXI` (or the evergreen branch formula): leaf-off hours that end the season. Node growth runs only while `Hours4LeafOff_brch<HourReq4LeafOff_brch` (`:957`); perennial remobilization starts at `FracHour4LeafoffRemob*HourReq4LeafOff_brch` (`PlantBranchMod.F90:759`) |
| XRLA | `RefLeafAppearRate_tab` -> `RateRefLeafAppearance_pft` | `PlantInfoMod.F90:1755` (`ReadPlantTraitTable`); copy `:752` | `/MaxNodesPerBranch` if IBTYP not 0, `ReadPlantProperties` `:519`; `UpdateBranchNodeNumber` `PlantPhenolMod.F90:1105`; `SenescenceBranch` `PlantBranchMod.F90:3999`; `PlantLitterFractions` `StartqMod.F90:427` and `PlantLitterFraction` `InitPlantMod.F90:451` (woody non-deciduous only) | `LeafAppearRate=AZMAX1(RateRefLeafAppearance_pft(NZ)*TFNP)`; also the node-age kill rate `RSpecKillLeafPetol=fTCanopyGroth_pft(NZ)*RateRefLeafAppearance_pft(NZ)` and, for woody non-deciduous PFTs, `FracGroth2Node_pft=AMAX1(1.0_r8,0.04_r8/RateRefLeafAppearance_pft)` |
| XRNI | `RefNodeInitRate_tab` -> `RefNodeInitRate_pft` | `PlantInfoMod.F90:1754`; copy `:751` | `/MaxNodesPerBranch` if IBTYP not 0, `:518`; `UpdateBranchNodeNumber` `PlantPhenolMod.F90:1104` | `NodeInitRate=AZMAX1(RefNodeInitRate_pft(NZ)*TFNP)`, times OFNG/WFNG for annuals; drives every node-number stage test and, through `dReproNodeNumNormByMatG`, seed set and seed size |
| XTLI | `ShootNodeNumAtPlanting_tab` -> `ShootNodeNumAtPlanting_pft` | `PlantInfoMod.F90:1766`; copy `:762` | `ReadPlantProperties` `:515`, `:521`; `InitPlantPhenoMorphoBio` `StartqMod.F90:593`, `InitPlantMod.F90:729`; `root_shoot_branching` `PlantPhenolMod.F90:334`, `:372`; `ResetNonAnnualBranch` `PlantBranchMod.F90:2438` (IBTYP 0); `LiterFallDeadBranches` `LitterFallMod.F90:735`; `CorrectClimate` `WthrMod.F90:489` | node count of the seed: `ShootNodeNum_brch=ShootNodeNumAtPlanting_pft` at start and at each IBTYP-0 perennial leaf-out; subtracted from GROUPX in `MatureGroup_pft=MatureGroup_pft-ShootNodeNumAtPlanting_pft`; offsets the branch and root-axis initiation node thresholds |
| XPPD | `PhotoPeriodSens_tab` -> `PhotoPeriodSens_pft` | `PlantInfoMod.F90:1768`; copy `:764` | `InitiateBranchFloral` `PlantPhenolMod.F90:1516` (IPTYP 1), `:1517` (IPTYP 2); `DevelopMainBranch` `PlantBranchMod.F90:2916` (inert, `ATRPPD=EXP(-0.0_r8*PPDX)`, `:2917`) | `PhotoShortCheck=(... iphotop_short .AND. PPD.GT.PhotoPeriodSens_pft)`, `PhotoLongCheck=(... iphotop_long .AND. PPD.LT.PhotoPeriodSens_pft)` with `PPD=AZMAX1(CriticPhotoPeriod_pft-DayLenthCurrent)`; no effect for day-neutral PFTs; units in the pft file say node h-1 but it is an hour difference |
| GROUPX | `GROUPX_tab` -> `GROUPX_pft` -> `MatureGroup_pft` | `PlantInfoMod.F90:1765`; copy `:761` | `ReadPlantProperties` `:514`; `CorrectClimate` `WthrMod.F90:485`; via `MatureGroup_pft`: `UpdateBranchNodeNumber` `PlantPhenolMod.F90:1149-1156`, `CheckBranchNodeState` `:1189`, `root_shoot_branching` `:346`, `:348`, `PlantLitterFractions` `StartqMod.F90:416-420`, `PlantLitterFraction` `InitPlantMod.F90:440-444`, branch resets `PlantBranchMod.F90:2399`, `PlantDisturbsMod.F90:1034`, `:1049`, `LitterFallMod.F90:734` | `MatureGroup_pft=GROUPX_pft` then `-ShootNodeNumAtPlanting_pft` (then /25 for IBTYP not 0): nodes to floral initiation (`ShootNodeNum>MatureGroup+ShootNodeNumAtInitFloral`) and the normaliser of every later stage; also selects 2-5 concurrently growing nodes for IBTYP 0 or non-woody PFTs |
| CTC | `TCChill4Seed_tab` -> `TCChill4Seed_pft` | `PlantInfoMod.F90:1756`; copy `:753` | `ColdDroughtDeciduPhenology` `PlantPhenolMod.F90:730` (IWTYP 3); `ColdDeciduousBranchPhenology` `:870` (IWTYP 1); `CalcPartitionCoeff` `PlantBranchMod.F90:772` (cold-deciduous perennial remobilization); `GrainFillOnBranch` `:2144-2148`; `SetCanopyGrowthFuncs` `UptakesMod.F90:1635` | removes leaf-out credit, `Hours4Leafout_brch=AZMAX1(Hours4Leafout_brch-1.0_r8)` (IWTYP 1) or `-1.5_r8` (IWTYP 3, also on low turgor), each hour with `TCGroth_pft<TCChill4Seed_pft`; starts remobilization hours of cold-deciduous perennials; seed loss `FGRNX=SeedTempSens_pft*(TCChill4Seed_pft-TdegCCanopy_pft)`; counts `ChillHours_pft` (photosynthesis, topic 01) |
| PB | `NonstCMinConc2InitBranch_tab` -> `NonstCMinConc2InitBranch_pft` | `PlantInfoMod.F90:1764`; copy `:759` | `root_shoot_branching` `PlantPhenolMod.F90:328-329` only | a new branch needs `CanopyNonstElmConc_pft(ielmc).GT.NonstCMinConc2InitBranch_pft .AND. NonstCMinConc2InitBranch_pft.GT.0` (or no branch and positive storage); PB = 0 disables branching beyond the first; inert for IBTYP not 0 beyond one branch because `BranchNumMax=1` (`:339`) |
| ZTYPI | `PlantInitThermoAdaptZone_tab` -> `PlantInitThermoAdaptZone_pft` -> `rPlantThermoAdaptZone_pft` | `PlantInfoMod.F90:1735`; copy `:725` | `ReadPlantProperties` `:527-528` (perennial evergreen, NB>1); `PFTThermalAcclimation` `StartqMod.F90:450-464`, `InitPlantMod.F90:485-499`; `CorrectClimate` `WthrMod.F90:476-483`; `pft_display` `PlantInfoMod.F90:1092-1103` (labels only); via `TempOffset_pft`: `CalcPhenolEnvfactor` `PlantPhenolMod.F90:1056`, `SetCanopyGrowthFuncs` `UptakesMod.F90:1619`, `:1623`, `StagePlantForGrowth` `GrosubsMod.F90:501`, `:505`, `StomatesMod.F90:957`; via `HighTempLimitSeed_pft`: `GrainFillOnBranch` `PlantBranchMod.F90:2152-2156` | `TempOffset_pft=2.667_r8*(2.5_r8-rPlantThermoAdaptZone_pft)`, `TC4LeafOut_pft=TCZD-TempOffset_pft`, `TC4LeafOff_pft=AMIN1(15.0,TCXD-TempOffset_pft)`, `HighTempLimitSeed_pft=27.0_r8+3.0_r8*rPlantThermoAdaptZone_pft`, `HourReq4LeafOut_brch=AMIN1(4380,VRNLI+144*ZTYPI*(NB-1))`; zone-labelled but used as a continuous real |
| XDL (seed re-verify; not assigned) | `CriticPhotoPeriod_tab` -> `CriticPhotoPeriod_pft` | `PlantInfoMod.F90:1767`; copy `:763` | `SetPlantTraits` `:852-854`; `InitiateBranchFloral` `PlantPhenolMod.F90:1512`; `DevelopMainBranch` `PlantBranchMod.F90:2916` (inert) | `PPD=AZMAX1(CriticPhotoPeriod_pft-DayLenthCurrent)`; a negative XDL is replaced by the site maximum day length, not "disabled"; no effect for IPTYP 0 |
