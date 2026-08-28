# EcoSIM adapter for A2MC

The first non-FATES model adapter, built as the adapter-kit end-to-end dogfood. Onboards **EcoSIM** (the Fortran-90 successor to Grant's `ecosys`) to A2MC's calibration framework.

- **Model source:** https://github.com/jinyun1tang/EcoSIM, pinned at commit `2dea74d9` (2026-04-23).
- **Codebase wiki:** `docs/ecosim-knowledge-base/ecosim-codebase-wiki-2dea74d9/` (41 docs, source-cited).
- **RAG profile:** `ecosim-2dea74d9` (`rag/chroma_db/ecosim-2dea74d9/`, `rag/graphs/ecosim-2dea74d9.json`).
- **Sample case:** BioCON `test1_ex1` (standalone driver, 6 input NetCDFs + a multi-namelist runfile, 2000–2022).

## Files

| File | Role |
|---|---|
| `spec.py` | `ECOSIM_SPEC` (`ModelSpec`) — identity, naming conventions, grouping axis (`pft`), mechanism map, validator/version dispatch |
| `parameter_parser.py` | `EcoSIMParameterParser` — `.nc` + `.json`, prefix-free naming, PFT-axis aware. Contract interface: `parser().parse(path)` |
| `output_parser.py` | `EcoSIMOutputParser` — reads the output-registry CDL; EcoSIM dim-level map + `_pft/_col/_vr/_litr/_brch` suffix convention |
| `version.py` | Commit-based `EcoSIMVersion` + detector + tier classifier + milestone metadata |
| `backend.py` | `EcoSIMBackend` — real parse methods; execution methods deferred to the execution-phase step |
| `prompts.py` | `DOMAIN_SUMMARY` + `MECHANISM_GLOSSARY` (source-grounded) |
| `datasets.py` | `ECOSIM_DATASETS` — the `ecosim-2dea74d9` `ModelDataset` |
| `tools/evolve_pft_input.py` | Remedy a version-drifted pft input: add the per-PFT vars a newer binary reads, sourced from a newer donor table by type-flag functional analog |

## Parameter surfaces — what EcoSIM has, vs what A2MC wires

**These are two different lists, and conflating them is a live trap.** A2MC has three
parameter-file slots; EcoSIM has more parameter-bearing inputs than that. A calibration scoped to
"the three surfaces" silently excludes a proven lever.

The runfile namelist names **eight `*_in` entries**: seven NetCDF input slots plus `clm_factor_in`,
which is a flag rather than a file. **`spec.py` is the authority for the namelist keys A2MC wires** —
it is what the code reads, so consult it rather than trusting a copy here.

| Namelist key | Holds | A2MC slot | Perturbed? |
|---|---|---|---|
| `pft_file_in` | ~123 per-PFT plant traits (VCMX, VRNLI/VRNXI, CNLF …) | primary, `A2MC_BASE_PARAM_FILE` | yes, per ensemble row |
| `grid_file_in` | **~114 soil vars** — `CORGC`/`CORGN`/`CORGP` organic pools, `FC`/`WP`/`PSIFC`/`PSIWP`, `SCNH`/`SCNV` Ksat, `BKDSI`, `CSAND`/`CSILT`/`FHOL`, `PH`/`CEC`/`AEC`, initial litter C/N/P | **none** | **not through the param list** — see below |
| `pft_mgmt_in` | stand management: planting, cuts, fertiliser | secondary, `A2MC_SECONDARY_PARAM_FILE` | staged FIXED by default |
| `soil_mgmt_in` | soil management: tillage, amendments | **none** | no |
| `micpar_file_in` | 76 microbial kinetics: RCCZ, VMXO, RMOM, GO2X, SPORC, SPOMC | tertiary, `A2MC_BASE_PARAM_FILE_3` | yes, when wired |
| `clm_hour_file_in`, `atm_ghg_in` | weather and atmospheric composition | — | forcing, not parameters |

**The grid file is a PROVEN calibration surface, and it has no slot.** BioCON R2 perturbed `CORGC`
(per-layer soil organic carbon, scaled with `CORGN`/`CORGP` for stoichiometry) across ×1-6 and found
it the decisive soil-respiration lever: cycle 4's `CB6` (pool ×6 crossed with a microbial rate ×4)
was the first configuration to reach two of three targets. That was done with purpose-built probe
scripts (`scripts/materialize_adapter_crossed.py` and its per-cycle matrices), **not** through the
param-list machinery, because no `ModelSpec` field or env var reaches `grid_file_in`. So a
soil-carbon calibration is possible on EcoSIM today, but only outside the standard ensemble path.
Evidence: `use_cases/EcoSIM_BioCON/reports/20260721j_R2_ROUND_SUMMARY/R2_round_summary.md` §cycles 3-4.

**A fourth category: parameters in no file at all.** Some EcoSIM constants are compiled in and must
be *promoted* to an input before they can be calibrated. `SPOSC` (specific SOM decomposition rate,
the first-order control on hydrolysis) was hardcoded until it was added to `MicrobePars.nc` as
model-dev work — scoping in `memory/dev_logs_adapterkit/20260721b`, and the guarded optional read it
produced is visible at `NitroPars.F90::ReadPars`. Before assuming a knob is missing, check whether it
exists as a constant and needs promoting rather than wiring.

**The tertiary surface is OPTIONAL IN THE MODEL, and that has a consequence worth knowing before
you plan a soil-BGC calibration.** With `micpar_file_in = ''` the reader returns immediately
(`if (len_trim(micpar_file_in)==0) return`, `f90src/Modelpars/NitroPars.F90:277`) and the run uses
**compiled-in Fortran constants** from `initNitroPars` (`NitroPars.F90:137`). So the microbial
parameters are never absent, they are simply not file-backed, and A2MC perturbs by writing modified
*files* — meaning there is no surface to reach them through until the file is wired. Wiring it is
also not a no-op: measured 2026-08-17, the shipped `input_data/MicrobePars.20260211.nc` matches the
compiled defaults on 72 of 76 entries but differs on 4 (`VMXF` x0.4, `VMXCH4gAcet`/`VMXCH4gH2` x3.2,
`SPOMC` element 2 x10), so switching it on changes the baseline and needs a fresh reference run.

Which cases exercise what: **BioCON** uses all three (its R3 config sets all three env vars);
**Lusignan** uses the primary only. `create_case` repoints `pft_file_in` alone, so the other inputs
are inherited from the base namelist — see `use_cases/EcoSIM_template/config/ecosim_template_config.sh`.

## Version drift — input↔binary compat

An EcoSIM binary reads a fixed set of per-PFT input variables; an input file built against an
**older** EcoSIM is missing vars the newer binary requires, and the run ENDRUNs mid-read
(`ncd_getvar…VAR: Variable not found`) while SLURM still reports `exit 0` — no tape. Workflow:

```bash
# 1. detect (generic guard) — exit 2 = INCOMPATIBLE, names the missing vars
python tools/model_check_input_compat.py --model ecosim --checkout <EcoSIM> --param-file <pft.nc>

# 2. evolve the input from the model's own newer table (donor has the added vars + units)
python models/ecosim/tools/evolve_pft_input.py --input <pft.nc> --checkout <EcoSIM> \
    --donor <ecosim_pftpar_YYYYMMDD.nc> --out <evolved.nc>   # [--analog SRC=DONOR] to override

# 3. re-verify -> COMPATIBLE
python tools/model_check_input_compat.py --model ecosim --checkout <EcoSIM> --param-file <evolved.nc>
```

Worked BioCON example (`2dea74d9`, 17 missing vars) + rationale: `memory/dev_logs_adapterkit/20260713a_EcoSIM_Version_Drift_And_Input_Evolution.md`.

## Status

- ✅ Parsing (`.nc`/`.json`), version association, spec, RAG-facing metadata.
- ⏳ Deferred: `curated_seed.yaml` (curated relationships — pipeline Step 3, PI-in-the-loop), `runtemplates/` (execution phase), backend execution methods (need a compiled binary + run harness).

## Distinctive mechanisms (from the wiki audit)

Campbell hydraulics (not van Genuchten), explicit macropore flow, Johnson-Lewin-Eyring microbial decomposition (not Q10), Langmuir P sorption, Grant-1989 Rubisco photosynthesis with turgor-based stomatal stress, stage-prescribed allocation. See `prompts.py:MECHANISM_GLOSSARY` and `memory/dev_logs/20260424g_EcoSIM_Codebase_Wiki_Rewrite.md`.

Dev logs: `memory/dev_logs_adapterkit/20260707*`.
