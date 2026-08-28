# How to fork A2MC for your model

This directory is the **fill-in-the-blanks adapter skeleton** for A2MC. Copy
it to `models/<yourmodel>/` and replace the `# TODO(adapter-kit):` markers to
onboard a new model.

For the full walkthrough — wiki generation, RAG build, curated YAML seed,
validators, run-template selection — use the CLI:

```bash
python scripts/init_adapter.py --model <yourmodel>
```

This README is the short reference. The long version (~800 lines, every
step has a concrete command) is at
`docs/a2mc_reference/forking_a2mc_for_a_new_model.md` (Doc 19 Step F).

---

## What's in this directory

| File | Purpose |
|---|---|
| `__init__.py` | Package init; calls `register_model()` + `register_dataset()` with the adapter's spec/backend/datasets |
| `spec.py` | `ModelSpec` instance — static metadata (parameter regex, output regex, mechanism keywords, validator/version-association class references) |
| `backend.py` | `ModelBackend` subclass — eight executable methods (parse, write, create_case, submit, status, extract, diagnostics) |
| `datasets.py` | `ModelDataset` registry — one entry per registered version of your model |
| `version.py` | `ModelVersion` + `ModelVersionDetector` + `BumpTierClassifier` + `MilestoneMetadata` — version-association classes |
| `parameter_parser.py` | `ParameterParser` — parses model parameter file into uniform records |
| `output_parser.py` | `OutputParser` — parses model output CDL into uniform records |
| `prompts.py` | `DOMAIN_SUMMARY` — model description for AI calibration prompts |
| `curated_seed.yaml` | Minimum-viable curated YAML (3 categories, 3 mechanisms, 5 params, 5 outputs) |
| `runtemplates/` | Six run-template starting points (HPC × CIME × Python matrix per Doc 19 §8) |

---

## The 14-step CLI flow

`init_adapter.py` walks you through these in order. See `docs/19_Adapter_Kit_Implementation_Plan.md` §6.3 for the canonical list and §6.5 for the validator iteration loop.

### Phase A — Adapter scaffold (Steps 1–2)

1. **Scaffold adapter directory.** `cp -r models/_template/ models/<yourmodel>/` and rename `Template*` to `<YourModel>*`.
2. **Adapter conformance validator (V4).** Verifies all required files present, ModelSpec registered, no remaining TODO markers, parser/output_parser produce non-empty output.

### Phase B — Knowledge pipeline (Steps 3–9)

3. **Wiki acquisition.** Per `docs/a2mc_reference/codebase_wiki_generation_roadmap.md`. Workflow A (greenfield) or Workflow B (audit + rewrite at new commit). Output: `docs/<yourmodel>-knowledge-base/<yourmodel>-codebase-wiki-<sha>/`.
4. **Codebase wiki validator (V1).** Wiki ↔ source citations.
5. **Param/output extraction.** `ncdump -h` of your NetCDF files OR copy CDL/JSON/YAML.
6. **Parser regex injection.** Update `parameter_parser.py` / `output_parser.py` with the right regex / format dispatch for your model.
7. **Curated seed (Recipe G1).** Per `docs/a2mc_reference/graphrag_curated_yaml_roadmap.md`. AI-assisted authoring of `curated_seed.yaml` from wiki + param file.
8. **YAML wiki validator (V2).** Curated YAML ↔ wiki + param + CDL.
9. **RAG build.** Per `docs/a2mc_reference/rag_build_roadmap.md`. Produces vector index + Layer 1 graph + Layer 2 overlay.

### Phase C — Execution setup (Steps 10–14)

10. **Memory seeding.** Creates `memory/<yourmodel>/gained_knowledge/` from the curated seed.
11. **Run template select + render.** Pick from the six templates in `runtemplates/`; CLI fills in `{{VARS}}`.
12. **Run template validator (V5).** Static parse + `{{VAR}}` substitution check.
13. **Smoke test.** Dry-run orchestrator phases 0–2.
14. **Next-steps printout.** Pointers to the forking roadmap, Recipe G4 reminder.

---

## Validators iterate to Green (per Doc 19 §6.5)

Validators V1, V2, V4, V5 (and optional V3 RAG profile diff) run inline at the right step boundaries. On Red/Yellow:

- CLI prints categorized findings (real fabrication / validator FP / by-design / threshold mis-calibration)
- User fixes (artifacts or validator improvements)
- Re-run; loop until Green

Convergence target is **Green band on every dimension, with documented residual-FP table** for items that legitimately can't be fixed without making the validators invasive. Per the FATES Phase 3.8 worked example, expect ~1–3 iteration rounds for a typical first build.

---

## After v0.1: iterate during real calibration (Recipe G4)

The seed YAML and the adapter's wiki are v0.1 — expected to grow during real calibration runs. As Phase 3 diagnosis surfaces gaps (wrong parameter context, missing relationships, surprising couplings), update the curated YAML accordingly. This is exactly how the FATES YAML grew over months from its first seed to its current state.

---

## When to ask the maintainer vs fix locally

| Issue | Where to fix |
|---|---|
| Real fabrication / drift in your model's wiki, YAML, or parser | Patch in `models/<yourmodel>/` |
| Validator framework false positives that affect your model | Open issue / PR against A2MC main; the validator filter list lives in `tools/<validator>.py` |
| Run-template doesn't fit your scheduler or invocation pattern | Customize `models/<yourmodel>/runtemplates/<variant>.sh.tmpl`; consider PR-ing back if widely useful |
| Adapter contract (`models/base.py`) needs new fields | Open discussion / PR against A2MC main |

---

## Pointers

- Full implementation plan: `docs/19_Adapter_Kit_Implementation_Plan.md`
- Forking roadmap (long version): `docs/a2mc_reference/forking_a2mc_for_a_new_model.md` *(Step F deliverable; not yet on main)*
- Five pipeline roadmaps: `docs/a2mc_reference/{codebase_wiki_generation,rag_build,graphrag_curated_yaml,rag_validation,version_association}_*.md`
- FATES reference adapter: lives at `models/fates/` after Step E generalization (currently distributed across `tools/`, `rag/`, `scripts/` — being unified)
