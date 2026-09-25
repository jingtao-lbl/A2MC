---
name: ecosim-trait-check-refine
visibility: public
category: calibration
description: >-
  Check whether EcoSIM per-PFT trait VALUES are physiologically appropriate, then refine them — using
  the EcoSIM developer's ecosim-agent skills (ecosim-plant-trait-sanity-check + ecosim-trait-deriver),
  referenced in place, NOT ported. Run the deterministic checker on a run's `plant_trait.*.desc` dump
  (ranges, `[0,1]` fractions, sign conventions, N/P magnitudes, type-flag identity, cross-param
  consistency), optionally add the web-evidence layer, map flagged `.desc` codes back to the NC pft
  trait vars, refine the input, and re-verify by run. Use when an EcoSIM plant is dead/stunted/anomalous
  and you suspect the parameter VALUES (not missing vars — that's `ecosim-version-drift`), when vetting a
  pft input before an ensemble, or on "are these trait values reasonable / sane-check the plant params".
  EcoSIM-specific.
modes:
  requires_fates: false
  nutrient_pathway: any
  scope: [ecosim, adapter]
  summary: "EcoSIM-only: sanity-check + refine per-PFT trait VALUES via the ecosim-agent skills (referenced, not ported); a diagnostic, not a guaranteed fix."
---

# ecosim-trait-check-refine — sanity-check + refine EcoSIM pft trait VALUES

EcoSIM's `pft_file_in` NC table sets ~120 per-PFT traits. When a run produces a **dead / stunted /
botanically-wrong** plant but the run *technically completes*, the problem is usually **value
appropriateness**, not structure. This skill vets those values against the EcoSIM developer's own
checker and refines them.

**Not this skill (→ `ecosim-version-drift`):** the input is missing vars the binary requires (ENDRUN,
no tape), or a target output is inactive-by-default. That's *structure/completeness*. This skill is
*value appropriateness* — the run finishes and writes a tape, but the plant is wrong.

> **Reference the developer skills in place; do NOT port them** ([[reference_ecosim_agent_skills_by_model_path]]).
> `$MODEL = ${A2MC_MODEL_PATH}` (the EcoSIM checkout root); `$PY` = the a2mc_env python. The ecosim-agent
> skills live at `$MODEL/python_tools/.claude/skills/` (a symlink → `.agents/skills/`).

## The key artifact — `plant_trait.*.desc`

EcoSIM dumps a **human-readable, per-PFT decode of the exact traits it used** when the run namelist has
`disp_planttrait = .true.` — one `plant_trait.<year>.desc` per year, written to the run dir. It is the
**decoded view of the NC `pft_file_in` table**: same codes (VCMX, SLA1, CNLF, RCS…), plus plain-English
descriptions, units, and the integer type-flags spelled out. **It is model OUTPUT** — you check the
`.desc`, but you **refine the NC input** (the `.desc` re-verifies on the next run).

## Recipe

**1 — Get a `.desc`.** Use an existing run's (`<rundir>/plant_trait.2000.desc` — the first year = params
as-read), or if none exists, run a short window with `disp_planttrait = .true.`.

**2 — Deterministic check (local, no web):**
```bash
$PY $MODEL/python_tools/.claude/skills/ecosim-plant-trait-sanity-check/scripts/check_plant_trait_desc.py \
    <rundir>/plant_trait.2000.desc            # add --json for pipelines
```
Findings are ranked `ERROR` → `WARN` (range/fraction/sign/N-P-magnitude/type-flag/cross-param). First
grid only by default. Nonzero exit if any ERROR.

**3 — (optional) web-evidence layer.** For borderline magnitudes, derive literature ranges per PFT with
`ecosim-trait-deriver` (`$MODEL/python_tools/.claude/skills/ecosim-trait-deriver/`), write the evidence
JSON (EcoSIM units; the schema is in that skill), and re-run: `… check_plant_trait_desc.py <desc>
--web-evidence <evidence>.json`. Web findings default to WARN.

**4 — Interpret + map back to the NC input.** Each flagged `.desc` code is a variable in the NC
`pft_file_in`. For a **sign/convention flag**, verify against source *how the param is consumed* before
flipping it (see footguns). For a **type-flag** flag (e.g. IEBTYP/ISNTYP), set the correct categorical.

**5 — Refine + re-verify by run.** Patch the NC input values (`$PY` + netCDF4), re-run on the SAME
binary, and re-check the new `.desc`. **A passing checker ≠ a live plant** — confirm the plant actually
grows (peak `SHOOT_C_pft` toward the site's expected biomass), not just that the checker is green.

## Footguns (all learned the hard way — `20260715a`)

- **Refine the NC input, not the `.desc`.** The `.desc` is a decoded *dump*; editing it does nothing.
- **A checker ERROR is not always the growth-limiter.** The deterministic rules flag *plausibility*, not
  causality. In the BioCON onboarding, `RCS < 0` was a legitimate ERROR (`Stomata_Stress = EXP(-turgor/RCS)`
  — sign flips the stomatal response), but flipping it **had zero effect**. **Diagnose the failure *stage*
  before trusting a leaf-param flag.** Plot **year-by-year peak plant C**, not just year 1: in the onboarding
  the seedling germinated *fine* (comparable to the live reference in year 1) but failed to **compound as a
  perennial** — it regrew *smaller* every spring (net-negative annual carbon balance → decay to extinction),
  while the reference compounded ~10–280×/yr to a mature stand. So the bottleneck was the whole-plant
  **annual carbon balance / overwinter-regrowth** dynamic — upstream of, and invisible to, instantaneous
  leaf-physiology params (RCS/VCMX/CHL). If the plant doesn't compound year-over-year, refining leaf params
  won't save it; the cause is the case not transferring across the binary's physics (→ recalibration).
- **Sign/convention flags can be real old-input↔new-binary breaks.** A value the *old* binary grew with
  (the reference) may be wrong for the *current* binary if the convention changed — verify against source,
  don't assume "the reference used it, so it's fine."
- **This is a diagnostic, not a guaranteed fix.** If refinement of the flagged params doesn't recover the
  plant (as in `20260715a`), the cause is deeper (establishment stage, or the old case not transferring
  across the binary's physics) → **recalibration** against real targets (figshare `31339363` observed
  NPP/PlantC/Fs/SOC) or the developer's binary-matched calibrated input.
- **Never hardcode the checkout path** — `$MODEL/python_tools/.claude/skills/…`, never the host path;
  don't copy these skills into A2MC ([[reference_ecosim_agent_skills_by_model_path]], [[feedback_skills_dir_is_registry]]).

## Cross-references

- `ecosim-version-drift` (the *structure/completeness* sibling: missing vars + output activation)
- Developer skills: `$MODEL/python_tools/.claude/skills/ecosim-plant-trait-sanity-check`,
  `…/ecosim-trait-deriver`; memory `reference_ecosim_agent_skills_by_model_path`
- Worked onboarding: `20260714f` (dead-plant A/B/C ladder), `20260715a` (sanity-check → refine, RCS
  hypothesis falsified — the source of this skill's footguns)

