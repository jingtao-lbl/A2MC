# Modeler Questionnaire (Pre-Adapter-Kit)

**Audience:** A modeler (or modeling team) planning to port A2MC to their model.
**Purpose:** Pin down the model + run + calibration setup BEFORE running `scripts/init_adapter.py` so the kit can pre-configure the right runtemplate, parser stubs, and milestone metadata automatically.

---

## How to use it

1. Copy the template:
   ```bash
   cp templates/modeler_questionnaire.yaml ~/my_model_questionnaire.yaml
   ```
2. Open it in any text editor and fill in each field. Multiple-choice fields list valid values inline as `_choices:` comment blocks. Free-text fields are clearly marked.
3. Hand it (and the linked source/wiki/parameter file) to whoever runs the adapter kit. They invoke:
   ```bash
   python scripts/init_adapter.py --model <name> --questionnaire ~/my_model_questionnaire.yaml
   ```
4. The CLI auto-fills Step 1 scaffold values, picks the matching runtemplate, and emits warnings for any choices marked `[supported/code]` (meaning extra adapter code is required) or `[planned]` / `[unsupported]`.

---

## What the six sections cover

| Section | Topic | Drives... |
|---------|-------|-----------|
| Header (`model:`) | Adapter identity, domain tags | Folder names, RAG categorization |
| A — `source:` | Hosting, build system, version pinning | `rag/milestones.json` entry |
| B — `parameters:` / `outputs:` | File formats and patterns | `parameter_parser.py` and `output_parser.py` stubs |
| C — `runtime:` | HPC vs local, scheduler, walltime | Selection from `models/_template/runtemplates/` |
| D — `calibration:` | Targets, metrics, # parameters | Cost function wiring, Morris vs Sobol design |
| E — `resources:` | Compute budget, domain-expert time, AI provider | Default Phase 0 ensemble size, AI config |
| F — `notes:` | Free-text gotchas | Surfaced to the human reviewer at scaffold time |

---

## Support legend used in the template

Each multiple-choice option is annotated with one of:

- `[supported]` — A2MC handles this directly today, no extra work.
- `[supported/code]` — Supported but you (or we) need to write a small parser/glue.
- `[planned]` — On the roadmap, will work once the corresponding step lands.
- `[unsupported]` — Cannot run with current A2MC; would require custom design.

If you pick a `[planned]` or `[unsupported]` option for any required field, `init_adapter.py` will refuse to scaffold and direct you to the matching tracking doc.

---

## What the questionnaire does NOT cover

- The actual contents of the curated YAML — that comes later via `scripts/curated_seed_builder.py` (Recipe G1).
- Validation target values or observed datasets — those are loaded into `use_cases/<site>/` after the adapter is scaffolded.
- HPC machine-specific config (modules, queues, account codes) — those go into your machine config in the same shape as `a2mc_config.sh`.

---

## Related docs

- `docs/19_Adapter_Kit_Implementation_Plan.md` — full 5-step pipeline
- `docs/a2mc_reference/codebase_wiki_generation_roadmap.md` — Step 1 (wiki)
- `docs/a2mc_reference/graphrag_curated_yaml_roadmap.md` — Step 3 (curated YAML, Recipe G1)
- `docs/a2mc_reference/version_association_workflow.md` — Step 5 (milestone registration)
