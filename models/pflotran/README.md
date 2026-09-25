# PFLOTRAN adapter

A2MC adapter for **PFLOTRAN** (`bitbucket.org/pflotran/pflotran`), pinned to commit **`157a26f7`** — the commit the miniLEO binary was built from. Second non-FATES adapter after EcoSIM.

Framework code reaches this adapter through `models.registry.get_model("pflotran")`, never by importing the package directly.

## Why PFLOTRAN is structurally unlike the other adapters

Do not port FATES or EcoSIM assumptions here. Four things differ at the contract level.

| | FATES / EcoSIM | PFLOTRAN |
|---|---|---|
| Parameter surface | one NetCDF/JSON parameter file, bare names | a free-form nested **card deck** (`pflotran.in`), addressed by block path |
| Output surface | NetCDF history tape + CDL registry | a fixed-width **mass-balance tape** (`*-mas.dat`); no NetCDF history, so no CDL |
| Grouping axis | PFT | **mesh region** — there is no PFT axis |
| Second input surface | — | an external **thermodynamic database** that supplies molar volume and molar weight, which the surface-area unit conversion actually reads (`reaction_mineral.F90:1054`) |

The output tape is **not a CSV**. Its header is comma-separated and quoted; its data rows are fixed-width `es16.8` with zero separators. `read_csv(sep=',')` yields one giant column. Use `PFLOTRANOutputParser`.

## Package contents

| File | What it is | State |
|---|---|---|
| `spec.py` | `ModelSpec` — naming conventions, categories, validator dispatch, PETSc/HDF5 external boundary | complete |
| `parameter_parser.py` | deck parser; 121 addressed knobs on the miniLEO deck, each with a line number | complete, one known gap (below) |
| `output_parser.py` | `*-mas.dat` reader; 332 columns, all unique, family/scope/rate decomposition | complete |
| `backend.py` | `ModelBackend` — parsing, extraction, `check_case_status` on `EXIT_FAILURE = 88`, `write_parameter_file`, `create_case`, `submit_ensemble` | **complete and exercised** — a real binary runs the deck end to end (below) |
| `curated_seed.yaml` | GraphRAG layer-2 knowledge: 9 categories, 10 mechanisms, 14 outputs, 27 parameters | v0.2, source-verified + fan-out-corrected, **not yet PI-reviewed** |
| `version.py` | commit + semantic-version detection, bump-tier classification | complete |
| `datasets.py` | `ModelDataset` for `pflotran-157a26f7` | complete |
| `prompts.py` | `DOMAIN_SUMMARY`, `MECHANISM_GLOSSARY`, `CALIBRATION_CAUTIONS` | complete |
| `runtemplates/hpc_standalone.sh.tmpl` | Perlmutter run script | **proven** — executed repeatedly on Perlmutter (V0 gate, first real ensemble-member submission), see "Execution status" below |

## Execution status (updated 2026-08-14)

A PFLOTRAN binary exists at `157a26f7`, built on Perlmutter. The results below come from the first build (`cpe/23.12` / gfortran 12.3 / PETSc 3.21.4); that Cray PE was retired in 2026-09, and the current binary is a rebuild on `cpe/25.09` (gfortran 14.3 / PETSc 3.21.4), whose recipe and reproducibility check are in [`BUILD.md`](BUILD.md). It has been run and scored, not just built:

- **V0 reproducibility gate PASSES.** Our binary vs the team's own reference tape: RMSRE 0.2276 vs 0.2277, max |Δ ratio| 2.9e-05 across the 10 solute targets. The two runs are not bit-for-bit identical (different compiler/PETSc), but the divergence is bounded, does not grow over the 70-day run, and is invisible after each target's own time-averaging.
- **The full case pipeline is wired end to end**: `write_parameter_file` (perturbs the 17 calibration knobs by editing exact deck lines), `create_case` (stages the mesh, thermodynamic database, restart checkpoint, and deck into a case directory), and `submit_ensemble` (writes and submits the Slurm script) have all been implemented and exercised.
- **A real, non-dry-run submission completed**: `miniLEO_case0` (the unperturbed V0 baseline), Slurm job `56826414`, 8 MPI ranks, COMPLETED in 14m20s, re-scored to the same RMSRE 0.2276.
- **Not yet done**: the full 360-member R1 Morris ensemble has not been submitted — only this single baseline case has run.

Toolchain: see [`BUILD.md`](BUILD.md) for the current one. The first build used `module load cpe/23.12` (gfortran 12.3 / cray-mpich 8.1.28 / cray-hdf5-parallel 1.12.2.9) and `PETSC_DIR=/global/common/software/pflotran/petsc-3.21`, both gone since NERSC retired that release. A later test of the newer PETSc 3.24 build against this source pin failed (279 errors, one root cause: PETSc 3.23+ requires `use petscsys`, which upstream master already has and this 523-commit-old pin does not) — a property of the pin's age, not a PFLOTRAN defect. It is why a retired Cray PE is met by rebuilding PETSc 3.21.4, not by upgrading PETSc.

Full narrative, figures, and the 11-target scoreboard this binary now produces: `use_cases/PFLOTRAN_miniLEO/reports/20260814a_MiniLEO_Full_Case_Report_And_Coupling_Roadmap/miniLEO_full_report.md`.

### Known gap: anonymous-block collision

The miniLEO deck has two **anonymous** `FLUID_PROPERTY` blocks (`PHASE LIQUID`, `PHASE GAS`) distinguished only by an inner card. The parser collides them onto the single address `FLUID_PROPERTY/DIFFUSION_COEFFICIENT` and only the LIQUID value survives. PFLOTRAN's own run log shows the same card defaulted twice (`pflotran.out:7-10`), confirming two blocks were read. **Do not sample `DIFFUSION_COEFFICIENT` until a discriminator exists.**

## Reading the curated seed

`curated_seed.yaml` is the highest-leverage file here — it decides whether Phase 3 diagnosis can recommend parameters at all. Its **v0.1 was rejected** after an adversarial fan-out found ~11 outright errors and ~26 misleading entries in ~50 (~20 % hard-error rate, four times the EcoSIM precedent). The diagnosis was that claims taken from the wiki's *cited* knob tables survived verification while inference layered on wiki prose did not — the split fell exactly along the citation line.

So **v0.2 carries a pointer on every factual claim**: `[src: file.F90:NNN]`, `[deck: pflotran.in:NNN]`, `[db: savannah_river.dat:NNN]`, `[log: pflotran.out:NNN]`, or a measured `[data: …]` statistic. 246 citations across 84 claim-bearing fields. Anyone can check any claim in place instead of re-deriving it.

Two gates, and the first is necessary but **not sufficient**:

```bash
# V2 — names resolve, cross-references cohere. Says NOTHING about truth.
python tools/validate_curated_yaml.py --model pflotran \
  --param-file <case>/pflotran.in --output-file <case>/pflotran-mas.dat

# Every citation resolves, and no claim field is uncited.
python tools/check_pflotran_seed_citations.py \
  --source <checkout>/src/pflotran \
  --deck <case>/pflotran.in \
  --aux <case>/savannah_river.dat --aux <case>/pflotran.out \
  --require-citations
```

Add `--show` to the second to print each cited line. **Do that eyeball pass** — it is what no tool can do, and it caught four wrong line numbers in v0.2 that both gates had passed.

## Traps that survived verification

Read `curated_seed.yaml` for the full statements with citations. The short list, because each is a mistake a competent calibrator would otherwise make:

1. A **negative `RATE_CONSTANT` means log10(k)**, not a negative rate. Sample in log space.
2. `surface_area` **units depend on an optional trailing token**; with a mass token the conversion also multiplies by that row's own `vol_frac`, so the two are not independent knobs. Three of the ten rows omit the token and are read on the bulk-volume basis — confirmed at runtime by the log's defaulted-units messages. **That is NOT why three primary minerals are inert** (an earlier draft claimed it was; a worked counterfactual in `20260801d` shows they stay inert under every reading). The cause is the k·A product. The operational consequence stands either way: sampling those three rate constants moves nothing measurable.
3. With `UPDATE_POROSITY` set, **the `POROSITY` card is not the operative porosity** — it is the reference φ₀ that persists as a denominator in two other formulas.
4. `M` and `LIQUID_RESIDUAL_SATURATION` live at **three deck addresses with separate storage**, and nothing warns you when they disagree.
5. **Bounds must be enforced at sampling time.** `LOOP_INVARIANT` is a deck card, not a build flag, and out-of-range values are not reliably caught.
6. Coupler columns are **positive into the domain**, so outflow is negative — but do not apply that blanket. `east H+` is positive because the total H+ component is itself negative.
7. **Verify an output actually varies** before adopting it as a target. 125 of the 332 columns in the reference run are constant.
8. **A large lifetime timestep-cut count is not a failure.** The reference run completed successfully with 168.

## Version association

`pflotran-157a26f7` is pinned to the team's build commit, not upstream master. The gap to master is 523 commits / ~17 months across a **major version boundary** (6 → 7), with 235 of 331 source files changed. `PFLOTRANBumpTierClassifier.is_distant()` flags a major-version difference so a bump of that size can never auto-rebuild silently.

The commit is **not recoverable from run artifacts**: PFLOTRAN prints `PFLOTRAN Development Version` with no hash whenever `PFLOTRAN_RELEASE` is false. It must come from the checkout.

## What is not done

- **The full 360-member R1 Morris ensemble has not been submitted.** Only the single unperturbed V0 baseline case has actually run (see "Execution status" above); the machinery to submit the rest is built and exercised.
- **The restart question.** The miniLEO deck restarts from a pre-steady-state checkpoint produced under the base parameters. Perturbing porosity, permeability, the retention curve or the mineral assemblage makes that restart silently inconsistent. Each ensemble member may need its own spin-up — which changes the cost model for a ≥10⁴-member ensemble. Settle this before the first large batch.
- **PI review of the curated seed.** It has passed two rounds of adversarial machine verification, not yet a human science review.
- **The rainfall-boundary vs outflow-boundary area inconsistency** (a factor of 10) is unresolved, though it does not affect any of the 11 targets currently scored (all are either concentration ratios, which cancel area, or use the independently-confirmed outflow-face area). See the case README, `use_cases/PFLOTRAN_miniLEO/README.md`, "The blocker you must know about."

## References

- **Full case report (current state, start here): `use_cases/PFLOTRAN_miniLEO/reports/20260814a_MiniLEO_Full_Case_Report_And_Coupling_Roadmap/miniLEO_full_report.md`**
- Branch charter and project context: `memory/dev_logs_adapterkitpflotran/20260730a` (private)
- Wiki generation + validation: `20260731d`
- Curated-seed rejection and method post-mortem: `20260801a`
- Rewrite contract: `20260801b`
- The v0.2 rewrite + second fan-out (13 more hard errors, all fixed): `20260801c`
- Evidence appendix for the two RETRACTED claims: `20260801d`
- Binary built + toolchain resolved: `20260807c` · PETSc 3.24 fallback tested and fails: `20260807h`
- Deck writing / case creation / first real submission: `20260812a` · `20260812c` · `20260812d`
- Onboarding recipe: `.claude/skills/onboard-model/SKILL.md`
