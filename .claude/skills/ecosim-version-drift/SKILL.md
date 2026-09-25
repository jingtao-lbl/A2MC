---
name: ecosim-version-drift
visibility: public
category: calibration
description: >-
  Get usable calibration data out of a drifted/current EcoSIM checkout — fixes the two ways a run
  fails to yield what you need. (A) INPUT DRIFT: the built binary is NEWER than the staged pft input,
  so it ENDRUNs mid-read ("ncd_getvar…VAR: Variable not found") and writes NO tape while Slurm
  reports COMPLETED — detect, EVOLVE the input from a newer donor pft table (type-flag analog),
  re-verify, confirm by run. (B) MISSING OUTPUTS: the run succeeds but a calibration variable
  (LEAF_C_pft, LEAF_N/P_pft, CAN_GPP_pft, …) is absent from the tape because it is registered
  default='inactive' — activate it via hist_fincl1. Use when an EcoSIM run produced no tape, on
  "Variable not found"/"IEBTYP" ENDRUN, after rebuilding EcoSIM at a newer commit, when
  evaluate/extract KeyErrors on a target variable, or before an ensemble on a drifted checkout.
  EcoSIM-specific (per-PFT table reads + inactive-by-default outputs); NOT for other models.
modes:
  requires_fates: false
  nutrient_pathway: any
  scope: [ecosim, adapter]
  summary: "EcoSIM-only: evolve a drifted pft input AND activate inactive-by-default calibration outputs; not model-generic."
---

# ecosim-version-drift — make a drifted EcoSIM input run with a newer binary

EcoSIM reads a fixed set of **per-PFT variables** from its `pft_file_in` table. When the built
binary is from a newer commit than the staged input, the input is **missing variables the binary
requires**, and the run **ENDRUNs mid-read** (`ncd_getvar…: Variable not found`) — writing **no
tape**, while Slurm reports `COMPLETED exit 0` (EcoSIM's ENDRUN is a clean stop → the classic
"Slurm success ≠ model success" trap).

The fix is **not** to rebuild the binary at the input's commit — it is to **evolve the input**:
add the missing per-PFT vars, sourced from EcoSIM's *own* newer parameter table, matched to each
PFT's functional analog. No fabricated values.

**Two failure modes, both "the run technically worked but your data isn't there":**
- **(A) input drift** — the run can't even start (ENDRUN, no tape). Recipe §A.
- **(B) missing outputs** — the run finishes and writes a tape, but a variable you calibrate
  against isn't on it. EcoSIM registers **117 of 179 `_pft` output fields `default='inactive'`**
  (`hist_addfld1d(…,default='inactive')` in `HistDataType.F90`) — they never reach the h0 tape
  unless named in `hist_fincl1`. The tell: `evaluate`/`extract` KeyErrors on a valid variable
  (`LEAF_C_pft` etc.). Recipe §B. This is NOT a schema rename — the var is a real field, just off.

> EcoSIM-specific by design (per-PFT `ncd_getvar(pft_nfid,…)` table reads + inactive-by-default
> outputs). Other models don't share these contracts — do NOT generalize into `onboard-model`.
> Backing tools: `tools/model_check_input_compat.py` (generic guard) +
> `models/ecosim/tools/evolve_pft_input.py` (EcoSIM input remedy).

## When to fire

- (A) An EcoSIM run **produced no tape** but Slurm says `COMPLETED` / the job "finished" in seconds.
- (A) Log shows `ncd_getvar…IEBTYP: Variable not found` (or any per-PFT var) → `ENDRUN`.
- (A) You just **rebuilt EcoSIM at a newer commit** and are reusing an older input.
- (B) A run **finished with a tape**, but `evaluate_ecosim_case`/`extract_history_variables`
  **KeyErrors on a target variable** (`LEAF_C_pft`, `CAN_GPP_pft`, …) that you know is a real field.
- **Before** submitting a calibration ensemble on a checkout whose binary may outrun its inputs, or
  whose h0 tape may not carry the target variables.

## Recipe §A — input drift (run won't start)

Anchor at the repo root. `$CO` = the EcoSIM source tree of the BUILT binary (e.g.
`<CFS>/<proj>/<user>/EcoSIM` on the HPC filesystem); `$PY` = the a2mc_env python.

**1 — Detect (generic guard).** Exit 2 = INCOMPATIBLE and names the missing vars:
```bash
$PY tools/model_check_input_compat.py --model ecosim --checkout "$CO" --param-file <pft.nc>
```
If exit 0 (COMPATIBLE / N/A), the drift is not the problem — stop here and look elsewhere.

**2 — Get a donor table that carries the missing vars.** Use the newest `ecosim_pftpar_*.nc`;
if the checkout's bundled tables also lag (they often do — the checkout can be internally
inconsistent), pull one from upstream by commit:
```bash
git -C "$CO" show origin/main:input_data/ecosim_pftpar_YYYYMMDD.nc > tmp/ecosim_donor.nc   # newest one
```
Confirm the donor has ALL the missing vars (the evolve tool errors if not).

**3 — Evolve the input.** Review the auto analog mapping (printed), then run for real. Override
any domain-wrong pick with `--analog SRC=DONOR`:
```bash
$PY models/ecosim/tools/evolve_pft_input.py --input <pft.nc> --checkout "$CO" \
    --donor tmp/ecosim_donor.nc --out <evolved.nc> --dry-run     # inspect the mapping first
$PY models/ecosim/tools/evolve_pft_input.py --input <pft.nc> --checkout "$CO" \
    --donor tmp/ecosim_donor.nc --out <evolved.nc> [--analog c3gn42=clvs35]
```

**4 — Re-verify (guard → COMPATIBLE).**
```bash
$PY tools/model_check_input_compat.py --model ecosim --checkout "$CO" --param-file <evolved.nc>
```

**5 — CONFIRM BY RUN (hard gate).** The guard checks var **presence**, NOT correctness — a
COMPATIBLE input can still fail. Stage the evolved input + the other inputs and run a **short
(1-year) window** (`forc_periods = <y0>, <y0>, 1`); it must (a) clear the plant-trait read with no
`ENDRUN`, (b) **write an h0 tape with records**, and (c) **contain the variables you will calibrate
against** (→ §B). Only then trust it for a full run/ensemble. Note: a login-node run SIGKILLed
mid-write leaves a **0-record / corrupt** tape — run to completion (or via SLURM) before judging.

## Recipe §B — missing outputs (run finished, target var not on the tape)

**6 — Confirm the miss is inactivity, not a rename.** Grep the binary source for the field; if it's
registered `default='inactive'`, it's valid and just needs activating (do NOT rename the target):
```bash
grep -n "hist_addfld1d(fname='<VAR>'" "$CO"/f90src/IOutils/HistDataType.F90   # shows default='inactive'
```
Build the authoritative active/inactive registry from source when in doubt: parse every
`hist_addfld[12]d(... fname='X' ... [default='inactive'])` in `$CO/f90src/**/*.F90`.

**7 — Activate via `hist_fincl1`.** Add the inactive calibration outputs (the ones your targets /
`models/ecosim/curated_seed.yaml` reference) to `hist_fincl1` in the run namelist — `hist_fincl1`
feeds tape stream 1 (the h0 tape). The base namelist
`Offline/EcoSIM_sample_files/runfile/__runfile__test1_ex1.nml` already activates the BioCON set:
```
hist_fincl1 = 'LEAF_C_pft','LEAF_N_pft','LEAF_P_pft','Plant_N_pft','Plant_P_pft',
              'CAN_GPP_pft','LAI_xstk_pft','Root_NONSTC_pft','GRAIN_C_pft','LITRf_N_FLX_pft'
```
Active-by-default pools (`SHOOT_C`/`Plant_C`/`Root_C`/`Root_N`/`Root_P`/`NPP`/`CAN_cumGPP`/
`LeafN`/`LAIstk`) need no activation. `backend.create_case` copies the base namelist through, so the
activation reaches every staged case. **Re-run and confirm the variables now appear** (§5c).

## Footguns

- **Guard COMPATIBLE ≠ runs.** Never skip step 5. Slurm `COMPLETED` with no tape = the model
  ENDRUN'd — key on **tape presence**, not job state.
- **Never fabricate values.** Every added var must come from a real donor table (the model's own
  newer parameter file), carried with its dtype/units/long_name.
- **Review the analog mapping.** The tool auto-picks by a type-flag score (ICTYP photosynthesis,
  INTYP N-fixation, IGTYP/ISTYP); the top score can be domain-wrong (e.g. it picks an N-fixing
  *bush* over a herbaceous *clover* for a grassland legume). Override with `--analog` when growth
  form or botany argues otherwise.
- **The reference tape may predate the binary.** If the staged reference output was made by an
  older EcoSIM, a bit-for-bit match is impossible — compare as scientific *trends*, not identity.
- **Don't fast-forward the pinned checkout.** The checkout is pinned to the RAG/adapter anchor
  commit; evolve the *input* to the binary, don't advance the binary/checkout.
- **A target var missing from the tape is (usually) inactive, not renamed.** Before "fixing" a
  target or the curated seed, grep the binary source — most EcoSIM `_pft` outputs are
  `default='inactive'`. Renaming a valid field is the wrong fix; activate it via `hist_fincl1`.

## Cross-references

- Input remedy tool: `models/ecosim/tools/evolve_pft_input.py` · guard: `tools/model_check_input_compat.py`
- Output activation: `Offline/EcoSIM_sample_files/runfile/__runfile__test1_ex1.nml` (`hist_fincl1`)
- Workflow doc: `models/ecosim/README.md` ("Version drift — input↔binary compat")
- Worked examples: `memory/dev_logs_adapterkit/20260713a_*` (input evolution, 17-var BioCON case),
  `20260713c_EcoSIM_Output_Activation_Fix.md` (output activation, inactive-by-default), and
  `20260712b_*` (first diagnosis).
- Generic detection footgun lives in `onboard-model` (Footgun 7); this skill is the EcoSIM remedy.

