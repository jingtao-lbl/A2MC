---
**Source pin:** EcoSIM commit `cb243228` (jingtao-lbl/EcoSIM `fix/r2-plant-balance`; upstream `09eb674a` + 2 fix commits)
**Scope:** `f90src/Mesh/{GridConsts,GridMod}.F90`, the vertical layer indices in `f90src/Ecosim_datatype/GridDataType.F90` and `f90src/IOutils/readimod.F90`, and their plant-side mirrors in `f90src/APIData/PlantSiteAPIData.F90`
**Last verified:** 2026-10-15
---

# Grid, mesh and layer conventions

EcoSIM's world is a rectangle of soil columns indexed `(NY,NX)`, each with up to `JP` plant slots `NZ` and a vertical stack of layers `L`. The horizontal part is set by `f90src/Mesh/`; the vertical indices that matter for roots and balances are set by the site reader and moved by soil relayering. Getting the vertical indices right is the main purpose of this page: several root and balance loops use different ones.

## 1. Horizontal mesh

### 1.1 Constants (`f90src/Mesh/GridConsts.F90`)

| name | value | line | meaning |
|---|---|---|---|
| `JX`, `JY` | runtime | `:9-10` | columns in x and y, including a halo cell unless `column_mode` |
| `JX0`, `JY0` | runtime | `:11` | columns without the halo, used by `get_col`/`get_pft` |
| `JZ` | 20 (set in code) | `:12` | soil layers per column; hard-set by `SetMesh` (`GridMod.F90:88`, again `:119`), not read from input |
| `JH`, `JV`, `JD` | runtime | `:13-15` | `JX+halo`, `JY+halo`, `JZ+1` |
| `NMaxRootSegs`, `MaxNumBranches`, `NumGrowthStages`, `NumOfPlantMorphUnits`, `MaxNumRootAxes`, `NumLitterGroups` | set in `InitPlantMorphSize` to 10, 10, 10, 7, 10, 5 | `:16-21` | plant array sizes (`f90src/Ecosim_mods/InitAllocMod.F90:180-191`) |
| `JP` | 5 | `:22` | maximum PFTs per column |
| `NumCanopyLayers` | 10 | `:23` | canopy layers |
| `JS` | 5 | `:24` | snow layers |
| `jroots` | 2 | `:25` | root types: plant root and mycorrhiza (`ipltroot=1`, `imycorrhz=2`, `f90src/Modelconfig/ElmIDMod.F90:98-99`) |
| `NumLeafInclinationClasses`, `NumOfLeafAzimuthSectors`, `NumOfSkyAzimuthSects` | 4, 4, 4 | `:26-28` | radiation geometry (the first was named `NumLeafZenithSectors` at `2dea74d9`) |
| `MaxNodesPerBranch` | 25 | `:29` | nodes per branch |

`MaxNumRootAxes` is commented "maximum number of root layers" (`:20`) but it is the number of root axes `NR`; root layers are `MaxNumRootLays` (§2). One loop also borrows the canopy-layer count as the root-axis bound: `hour1` floors `NRoot1stTipLay_raxes(NR,...)` for `NR=1..NumCanopyLayers` (`f90src/Modelforc/Hour1Mod.F90:232-234`), while the array is allocated with `MaxNumRootAxes` (`f90src/Ecosim_datatype/RootDataType.F90:178`). Both are 10, so the loop is correct only by coincidence.

### 1.2 `bounds_type` (`GridConsts.F90:38-55`)

`bounds` carries the landscape corners `NHW`, `NVN`, `NHE`, `NVS`, the grid, topo-unit, column and PFT ranges (`begg..endg`, `begt..endt`, `begc..endc`, `begp..endp`), the totals `ngrid`, `ntopou`, `ncols`, `npfts`, and the dense id maps `icol(JY,JX)` and `ipft(JP,JY,JX)`.

### 1.3 `SetMesh` (`f90src/Mesh/GridMod.F90:13-125`)

Called once by the driver (`drivers/ecosim/ecosim.F90:98`). It opens `grid_file_in` (`:42`), reads the `ngrid` and `ntopou` dimensions (`:44-46`) and the scalars `NHW`, `NHE`, `NVN`, `NVS`, aborting if any is missing (`:49-71`); copies them into `bounds` (`:76-79`); collapses to one cell if `first_topou` (`:80-87`); sets `JZ=20` (`:88`); computes `JX=(NHE-NHW)+1`, `JY=(NVS-NVN)+1` and their non-halo copies (`:92-93`); sets the column and PFT totals (`:95-98`); allocates and fills `icol`/`ipft` with dense counters (`:100-117`); adds the halo unless `column_mode` (`:103-105`); and sets `JH`, `JV`, `JD` (`:121-123`).

`SetMeshATS` (`:132-206`) does the same with corners supplied by ATS and does not set `JZ`, which the coupler sets from its own cell count (`f90src/ATSUtils/SharedDataMod.F90:97`).

### 1.4 Linear ids

`get_col(NY,NX) = (NX-1)*JY0 + NY` (`:210-217`) and `get_pft(NZ,NY,NX) = (NX-1)*(JP*JY0) + (NY-1)*JP + NZ` (`:219-227`): y varies fastest among columns and the PFT index fastest among PFTs, matching `icol(JY,JX)` and `ipft(JP,JY,JX)`.

## 2. Vertical layer indices

### 2.1 Layer 0 and the stacks

Layer `L=0` is the surface residue (litter) layer: arrays are allocated from 0 (for example `CumDepz2LayBottom_vr(0:JZ,...)`, `AREA_3D(3,0:JZ,...)`, `GridDataType.F90:41`, `:48`), the microbial loop runs `L=0..NL` and treats `L=0` and `L>=NU` as active (`f90src/APIs/MicBGCAPI.F90:120-122`), and plant litterfall into layer 0 is surface litter. Soil layers are `NU..NL`. Snow has its own stack `1..JS`; the canopy has `1..NumCanopyLayers`.

### 2.2 The indices

| index | declared | set | changes during the run | meaning |
|---|---|---|---|---|
| `NUI_col` | `GridDataType.F90:21` "initial soil surface layer number" | read from grid variable `NUI` (`readimod.F90:453`, in `readTopoNC`) | no | the first soil layer at start |
| `NU_col` | `:20` "soil surface layer number" | `= NUI_col` (`readimod.F90:459`) | yes: soil relayering raises or resets it (`f90src/Balances/SoilLayerDynMod.F90:284`, `:983`, `:1013`) | current uppermost soil layer |
| `NUM_col` | `:27` "new surface layer number" | `= NU_col` at the start of each `watsub` (`LocalCopySoilVars`, `WatsubMod.F90:398`) | moves down within the hour when the top layer has no soil and too little heat capacity (`UpdateStateFluxAtM`, `WatsubMod.F90:1498-1504`); set to 1 on the ATS path (`SurfPhysMod.F90:130`) | the top layer the hydrology actually uses |
| `MaxNumRootLays_col` | `:23` "maximum root layer number" | read from grid variable **`NJ`** (`readimod.F90:454`) | no | deepest layer roots are designed to occupy |
| `NK_col` | `:24` "additional soil lower boundary layers" | `= MaxNumRootLays_col + 1` (`readimod.F90:460`) | no (also copied for every cell of a topo-unit, `:570`); on the ATS path `NK_col = a_NL` (`ATSEcoSIMAdvanceMod.F90:121`) | one layer below the designed root zone; upper bound of the root-uptake loops |
| `NM` (local) | `readimod.F90:374` | `= MaxNumRootLays_col + NL1` (`:461`) | no | last layer with soil data in the file |
| `NL1`, `NL2` | `readimod.F90:54-55` | read (`:455-456`); `NL2 = min(JZ-NM, NL2)` (`:466`) | no | "number of additional layers below NJ with, without data in file" (`readimod.F90:548`) |
| `NLI_col` | `:25` "initial lowest soil layer number" | `= NM + NL2` (`:467`) | no | bottom layer at start |
| `NL_col` | `:26` "lowest soil layer number" | `= NLI_col` (`:468`) | yes: relayering moves it (`SoilLayerDynMod.F90:206`, `:214`) | current bottom layer |
| `NLF_col` | `:22` "id of the frozen layer" | `watsub` (`WatsubMod.F90:184-187`) | each hour | first layer with ice fraction > 0.9 |

So with `NL1 >= 1` the column holds `NUI..NJ` (rootable), `NJ+1 = NK` (first layer below the root zone, still with data), `NK..NM` (data), `NM+1..NLI` (extra layers without data, filled by `SetDeepSoil`, `readimod.F90:757`). `NK` is fixed for the whole run even though `NU` and `NL` can move.

### 2.3 Plant-side copies

The plant code sees the column through `plt_site` (`f90src/APIData/PlantSiteAPIData.F90:35-40`). On the dynamic path `SendPlantColumnInputs` copies `NL = NL_col`, `MaxNumRootLays = MaxNumRootLays_col`, `NU = NUM_col` and `NK = NK_col` (`f90src/APIs/PlantColumnTransferMod.F90:192-197`); note that the plant `NU` is the hydrology's `NUM_col`, not `NU_col`. On the prescribed-phenology path `PlantUptakeAPISend` copies `NL = NL_col`, **`MaxNumRootLays = NL_col`** ("assume roots exist in all layers"), `NU = NU_col` and `NK = NK_col` (`f90src/APIs/PlantAPI4Uptake.F90:69-74`), and sets `MaxSoilLays4Root_pft = NK_col` for every PFT (`:148`). The canopy-radiation path copies `NU = NU_col` (`f90src/APIs/PlantCanAPI.F90:63`).

### 2.4 Four descriptions of `NK`

| where | comment |
|---|---|
| `GridDataType.F90:24` | "additional soil lower boundary layers" |
| `PlantSiteAPIData.F90:40` | "current hydrologically active layer" |
| `PlantAPI4Uptake.F90:74` and `f90src/Plant_bgc/PlantBalMod.F90:186` | "total layers with roots, can be set to NL_col" |
| `f90src/Plant_bgc/RootMod.F90:5444` | "current soil root bottom layer number" |

None matches the code exactly. What the code does: `NK = NJ + 1`, constant, and it bounds the layers in which roots may exist and take up water and nutrients.

### 2.5 Which loops use which bound

| routine | file:line | loop | consequence |
|---|---|---|---|
| `RootMycoO2NutrientUptake` | `f90src/Plant_bgc/NutUptakeMod.F90:216` | `L=NU,NK` | nutrient and O2 uptake include layer `NK` |
| `GetInLayerRootDepth` | `RootMod.F90:5455-5459` | `L=1,NK` | a primary-root tip can enter layer `NK`; `MaxSoilLays4Root_pft` is raised to the tip layer |
| `StagePlantPhenology` | `f90src/Plant_bgc/PlantPhenolMod.F90:453` | | `MaxSoilLays4Root_pft = NMaxRootBotLayer_pft` each hour (dynamic path) |
| `TotalGasandSoluteUptake` | `f90src/Plant_bgc/ExtractsMod.F90:224` | `L=NU,MIN(MaxNumRootLays+1,NK)` | column uptake totals include `NK` |
| `StagePlantForGrowth` | `f90src/Plant_bgc/GrosubsMod.F90:421`, `:504` | `L=1,NK`; `L=NU,MaxNumRootLays` | mixed within one routine |
| `LiterFallRootShootStorage` | `f90src/Plant_bgc/LitterFallMod.F90:358` | `L=NU,MaxNumRootLays` | root litterfall stops at `NJ` |
| `RemoveBiomByHarvest` | `f90src/Plant_bgc/PlantDisturbsMod.F90:942` | `L=NU,MaxNumRootLays` | thinning and harvest root removal stop at `NJ` |
| `RemoveDeadAnnual` | `PlantDisturbsMod.F90:189` | `L=NU,MaxNumRootLays` | annual death sends roots to litter only to `NJ` |
| `SumLitfallBlg` | `PlantBalMod.F90:141` | `L=1,MaxNumRootLays` | |
| `SumRootPoolsForBalance` | `PlantBalMod.F90:640-663` | `L=MaxNumRootLays+1,LBAL`, `LBAL = MAX(MaxNumRootLays, MaxSoilLays4Root_pft)` | the plant balance counts root pools below `NJ` (fix commit `9669b817`) |
| `PlantAPIRecv` | `f90src/APIs/PlantAPI.F90:58` | `L=NUI_col,NK_col` | |

Material can therefore enter layer `NK` (uptake, root growth) but some removal paths (litterfall, harvest thinning, annual death) never visit it. The plant balance accounts for that layer through `LBAL`; how this interacts with `MaxSoilLays4Root_pft` on the dynamic path is detailed in [../plant_bgc/roots_and_uptake.md](../plant_bgc/roots_and_uptake.md).

## 3. Iteration idioms

```fortran
DO NX = NHW, NHE              ! columns, x outer
  DO NY = NVN, NVS
    DO NZ = 1, NP_col(NY,NX)  ! active PFT slots
    DO L = NU_col(NY,NX), NL_col(NY,NX)   ! soil layers; add L=0 for litter
```

Neighbours are addressed by index arithmetic `NX±1`, `NY±1`, with flux directions `iWestEastDirection=1`, `iNorthSouthDirection=2`, `iVerticalDirection=3` (`f90src/Modelconfig/ElmIDMod.F90`). `grid_mode` (default 3, vertical only) is copied to `FlowDirIndicator_col` by `readsiteNC` (`readimod.F90:323`).

## 4. Practical consequences

- `JZ=20` and `JP=5` are compile-time limits. A grid file whose `NJ+NL1+NL2` exceeds 20 has `NL2` silently truncated (`readimod.F90:466`).
- Choosing `NJ` sets both the designed root zone and `NK = NJ+1`. Roots can grow one layer deeper than `NJ`, and uptake reaches that layer; litterfall, thinning and annual death do not.
- When the surface layer changes (`NU` up after subsidence or erosion), plant loops starting at `NU` skip the abandoned layers; `hour1` floors the plant root-layer indices at `NU` every hour (`Hour1Mod.F90:230-234`).

## Calibration parameters

None. `NJ`, `NL1`, `NL2` and `NUI` are grid-file inputs, not parameter-file calibration levers.
