# EcoSIM Plant Parameter Reference — grounded in ECOSYS + Grant 2013

**Purpose:** the authoritative dictionary + provenance for EcoSIM's per-PFT plant parameters,
extracted from the original **ECOSYS** model and **Grant (2013)**. Use this to interpret pft-input
variables, decode PFT identity (type flags), and choose/verify calibration parameter values —
instead of guessing from a variable name.

## Provenance (consult these, don't guess)

- **ECOSYS `f77src/ecosys_core/readq.f`** — the original plant-file reader and the canonical
  **parameter dictionary** (each trait defined in an inline `C ` comment). EcoSIM (jinyuntang's F90
  rewrite) ports these; the NetCDF `ecosim_pftpar_*.nc` tables are the modern carrier. Repo:
  `https://github.com/jinyun1tang/ECOSYS`.
- **Grant, R.F. (2013), Biogeosciences — supplemental** (`Offline/Grant 2013 Biogeosciences
  supplemental.pdf`, 84 pp): the model equations +
  **Table 1 = all input parameter values**. Physiology of the traits below (C4 mesophyll/bundle-
  sheath Eqs C29–C49, chlorophyll/protein/lignin), building on Grant (2001).

## PFT identity — the type-flag system (readq.f)

The first line of a PFT definition is the integer type flags. **PFT ids are NOT stable across files;
map by these flags, not by name/position.**

| Flag | Meaning | Codes |
|---|---|---|
| `ICTYP` | photosynthesis type | 3 = C3, 4 = C4 |
| `IGTYP` | root profile | 0 = shallow (bryophytes), 1 = intermediate (herbs), 2 = deep (trees) |
| `ISTYP` | growth habit | 0 = annual, 1 = perennial |
| `IDTYP` | growth habit | 0 = determinate, 1 = indeterminate |
| `INTYP` | **N₂ fixation** | 1,2,3 = rapid→slow root symbiosis (legumes); 0 = none |
| `IWTYP` | phenology | 0 = evergreen, 1 = cold-decid, 2 = drought-decid, 3 = 1+2 |
| `IPTYP` | photoperiod | 0 = day-neutral, 1 = short-day, 2 = long-day |
| `IBTYP` | turnover | (IGTYP 0/1) 0,1 = rapid(decid), 2 = very slow(evergreen), 3 = slow |
| `IRTYP` | storage organ | 0 = above-ground, 1 = below-ground |
| `MY` | mycorrhizal | 1 = no, 2 = yes |
| `ZTYPI` | thermal adaptation zone | 1 = arctic/boreal, 2 = cool-temperate, … |

### BioCON test PFTs decoded (verified vs ECOSYS example flags)

| BioCON PFT | ICTYP | INTYP | identity | ECOSYS reference | master-table analog |
|---|---|---|---|---|---|
| `c4gr42` | 4 | 0 | C4 grass | `maiz31` (ICTYP=4) | `gr4s26` |
| `c3gr42` | 3 | 0 | C3 grass | `grass33` (ICTYP=3,INTYP=0) | `gr3s32` |
| `c3gn42` | 3 | 3 | C3 legume (slow N-fixer) | `soyb31` (INTYP=1, faster) | `clvs35` |

## Parameter dictionary (from `readq.f`)

Verbatim definitions of the per-PFT plant traits (the calibratable surface; units where given):

```
VCMX4 = specific PEP carboxylase activity (umol g-1 s-1)      [C4]
ETMX  = specific chlorophyll activity (umol e- g-1 s-1)
CHL   = fraction of leaf protein in mesophyll(C3)/bundle-sheath(C4) chlorophyll
CHL4  = fraction of leaf protein in mesophyll chlorophyll (C4)   <-- EcoSIM `fCHLMESO`; low for C4
FCO2  = intercellular:atmospheric CO2 ratio
CTC   = chilling temperature for CO2 fixation / seed loss (oC)
WDLF  = leaf length:width ratio
PB    = nonstructural C concn needed for branching
XDL   = critical photoperiod (h); <0 = max daylength from site file (sentinel)
CLASS = fraction of leaf area in 0-22.5/45/67.5/90deg inclination classes
CFI   = initial clumping factor
STMX/SDMX/GRMX/GRDM/GFILL = seed number/size/fill parameters
PORT  = root porosity
PR    = nonstructural C concn for root branching ;  RTFQ = root branching frequency (m-1)
OSMO  = leaf osmotic potential at zero leaf water potential (MPa)   (can be negative)
RCS   = shape param, stomatal resistance vs leaf turgor ;  RSMX = cuticular resistance (s m-1)
PPI/SDPTHI = planting density (m-2) / seeding depth (m)
IHVST/JHVST/HVST/THIN = harvest/grazing/fire/herbivory management
```
(Full 55-entry extraction: `docs/ecosim-knowledge-base/ecosys_readq_parameter_dictionary.txt`. Not every ECOSYS trait maps 1:1 to a modern
EcoSIM NetCDF name; verify the true read in `EcoSIM/f90src/IOutils/PlantInfoMod.F90`.)

## The 17-variable input drift (why old inputs fail)

The `2dea74d9` binary reads 17 per-PFT vars the frozen sample input lacks; they were added
incrementally in official EcoSIM **2025-11 → 2026-04** (9 commits), each a plant-physics feature/bug
fix, and **each also bumped `input_data/ecosim_pftpar_*.nc` in lockstep**. Several are re-exposed
ECOSYS traits (protein C:N `CNWL/CNWR`, C:P `CPWL/CPWR`, mesophyll chl `fCHLMESO`↔`CHL4`); others are
new EcoSIM physics (sapflow `PhiMAX/MEAN/MIN`, root maturation `ROOTMAGE`, morphogen `MOPHGEN`).
Timeline + commit descriptions: `memory/dev_logs_adapterkit/20260714b_*`.

## Correct migration — regenerate, don't graft

The developer's intended fix is to **regenerate the input from the current `ecosim_pftpar` table**
(his `python_tools/ExtractSelectedPft` subsets *whole* PFT rows). Grafting the new vars from a
*different* plant onto an old input yields an **internally-inconsistent PFT** that fails to establish
(the BioCON graft germinated then decayed to death; a consistent whole-PFT replace is the fix —
`Offline/ecosim_repro/regenerate_pft_input.py`, `20260714b`).

## Cross-references

- `memory/dev_logs_adapterkit/20260714b` — drift root cause, graft failure, regeneration
- `models/ecosim/curated_seed.yaml`, `docs/ecosim-knowledge-base/ecosim-codebase-wiki-2dea74d9/plant_bgc/`
- `ecosim-version-drift` skill — the operational fix for a drifted input
