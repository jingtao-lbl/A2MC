# EcoSIM Knowledge Base

Source-grounded knowledge inputs for the A2MC **EcoSIM** adapter (`models/ecosim/`). EcoSIM is a process-based ecosystem model (upstream [jinyun1tang/EcoSIM](https://github.com/jinyun1tang/EcoSIM)); A2MC runs it from the fork [jingtao-lbl/EcoSIM](https://github.com/jingtao-lbl/EcoSIM), which carries the fixes calibration rounds have needed.

This knowledge base is **commit-pinned**: every claim in a codebase wiki cites `path/File.F90:NNN` at one model commit, and a registered profile in `rag/milestones.json` ties that commit to the wiki, the curated seed (`models/ecosim/curated_seed.yaml`), the vector index and the knowledge graph built from them. This README records which model commit the knowledge base describes now, and every time that changed.

## Current working version of the model

| | |
|---|---|
| **Model** | fork `jingtao-lbl/EcoSIM`, branch [`fix/r2-plant-balance`](https://github.com/jingtao-lbl/EcoSIM/tree/fix/r2-plant-balance) at [`0340d71b`](https://github.com/jingtao-lbl/EcoSIM/commit/0340d71b1058e41cbcf303b3dff30c42a4277fe1) (2026-10-15) |
| **What it is** | upstream EcoSIM merged through `09eb674a` (A2MC anchor `a2mc-anchor-0ffe5a06`), plus three plant mass-balance commits: `9669b817` (the plant balance counts the root layers its fluxes reach), `cb243228` (default-off switch `conserve_root_clamp`) and `0340d71b` (the balance sums its bottom-layer root stocks over a fixed range, `MAX(MaxNumRootLays, NK)`; balance-only) |
| **Who runs it** | the EcoSIM_Lusignan round 2 ensemble (R2c), from an archived build `build_archive/fix-r2-plant-balance_0340d71b/ecosim.f90.x`, sha256 prefix `f1995cf8`. The case's round ledger (`config/calibration_rounds.yaml`, `round_binaries`) is the authority for the binary a round runs; this row restates it |
| **Knowledge-base profile** | `ecosim-cb243228`: base commit `cb243228`, with 1 patch, so the knowledge base describes **`0340d71b`** |
| **In step with the model?** | yes: the profile's knowledge-base commit is the commit the working binary was built from |

Check it live rather than trusting this table:

```bash
python tools/kb_profile.py --model ecosim --list     # every profile: base, knowledge-base commit, patches, live/legacy
python tools/kb_profile.py --model ecosim            # the profile covering $A2MC_MODEL_PATH's checked-out commit
```

**When the working model moves ahead of the knowledge base** (a fix lands and a round adopts it before the knowledge base is patched), say so in the last row ("no: the knowledge base describes `<commit>`, the model runs `<commit>`") until the patch or new profile is registered. A calibration agent reasoning from a knowledge base that lags the binary should know which lines it cannot trust.

## Contents

| Path | What it is |
|---|---|
| `ecosim-codebase-wiki-cb243228/` | **Live.** Commit-pinned codebase wiki (46 pages, 14 sections) at base `cb243228`, patched in place to `0340d71b`. Start at its `index.md`; its "Patches applied" table lists every patch |
| `ecosim-codebase-wiki-2dea74d9/` | Legacy wiki at upstream `2dea74d9` (41 pages), kept for the profile `ecosim-2dea74d9` and the rounds that ran on it |
| `ecosim-codebase-wiki/` | The first wiki (2026-02-09), auto-generated against `7b8a4cf6`. Superseded by the source-grounded rewrite at `2dea74d9` because it cited files that do not exist upstream; kept for reference; no registered profile uses it |
| `ecosim_output_info_<commit>.cdl` | History-output registries derived from every `hist_addfld1d/2d` call at that commit (`cb243228`, `2dea74d9`, and `0366560a`, the binary of the EcoSIM_Lusignan round 1) |
| `param_surfaces_cb243228/` | Byte copies of the three parameter files the model repository tracks at `cb243228` (plant, microbial, grid), committed so the profile rebuilds from this repository; they supply names, units and dimensions, and no run reads them |
| `graph_html/` | Rendered views of the knowledge graph |
| `ecosim_plant_parameter_reference.md`, `ecosys_readq_parameter_dictionary.txt` | The ecosys/Grant plant-parameter dictionary and the legacy `readq.f` reader's parameter list |

## Update history

Newest first. One row per change to what the knowledge base describes or how it is built. The model commit is what the knowledge base described **after** the change.

| Date | A2MC version | Profile | Model commit described | Workflow | Change |
|---|---|---|---|---|---|
| 2026-10-16 | v2.546 | `ecosim-cb243228` | `0340d71b` | render | page re-rendered with a deterministic node order (the renderer had iterated a set, so every render reordered the page); same nodes and edges. `tools/check_kg_html_current.py` (pre-commit 35) now holds the page to its graph |
| 2026-10-16 | — | `ecosim-cb243228` | `0340d71b` | render | `graph_html/ecosim-cb243228_knowledge_graph.html` regenerated with `tools/render_kg_html.py`; it had not been after the v2.543 rebuild, so it lacked the new mechanism. Now 553 drawn nodes and 1474 edges (475 isolated nodes not drawn), the mechanism and its seven edges included |
| 2026-10-16 | v2.543 | `ecosim-cb243228` | `0340d71b` | P (patch 1) | `0340d71b` registered as a patch of the profile: 104 citations re-anchored, 7 flagged claims rewritten by hand against the source. The root-layer table in `core/grid_and_mesh.md` §2.5 rewritten by role (every loop that stops at `MaxNumRootLays`, the litter bookkeeping that stops there too); new curated mechanism `Plant_Death_Root_Litterfall_And_Replanting`; three generated reference pages regenerated; graph and index rebuilt (3138 documents, 1028 nodes, 1474 edges) |
| 2026-10-15 | v2.527 | `ecosim-cb243228` | `cb243228` | — | Patch mechanism added (`tools/kb_patch.py`); the wiki `index.md` gained its "Patches applied" section, empty until the first patch |
| 2026-10-15 | v2.526 | `ecosim-cb243228` (new, live) | `cb243228` | B (audit, then rewrite) | New profile for the binary EcoSIM_Lusignan round 2 runs, 323 commits after `2dea74d9`. Each of the 14 sections audited against `cb243228`, then every page rewritten from source; new output registry and committed parameter surfaces. `ecosim-2dea74d9` marked legacy |
| 2026-09-12 | v2.415 | `ecosim-2dea74d9` | `2dea74d9` | seed + graph | Curated seed: the branch a parameter runs in, made visible to the checks |
| 2026-09-11 | v2.413 | `ecosim-2dea74d9` | `2dea74d9` | seed + graph | Curated seed: a mechanism whose citation contradicted its own parameter list, corrected |
| 2026-09-11 | v2.412 | `ecosim-2dea74d9` | `2dea74d9` | seed + graph | Two graph gaps closed: one parameter surface not indexed, one seed key the builder never read |
| 2026-09-08 | v2.404 | `ecosim-2dea74d9` | `2dea74d9` | registry | Output registry at `0366560a` added; output reduction recorded as a property of each variable |
| 2026-09-08 | — | `ecosim-2dea74d9` | `2dea74d9` | wiki + seed | Output traps and the two growth minima, verified on a real history tape |
| 2026-09-08 | v2.400, v2.401 | `ecosim-2dea74d9` | `2dea74d9` | graph | The graph builder reads the seed's `outputs` block and `categories.key_outputs` |
| 2026-09-06 | — | `ecosim-2dea74d9` | `2dea74d9` | seed + graph | `CNLF`/`CPLF` recorded as two branches of one `min()`; the four scored ecosystem targets wired; P-uptake entries restored from source and three phantom outputs removed; site-specific guidance moved out of the model-generic seed |
| 2026-09-01 | — | `ecosim-2dea74d9` | `2dea74d9` | index | Every parameter surface ingested (plant, microbial), not only the plant file |
| 2026-08-28 | — | `ecosim-2dea74d9` | `2dea74d9` | wiki | Authoring-machine paths scrubbed from shipped files |
| 2026-08-19 | — | `ecosim-2dea74d9` | `2dea74d9` | seed | The category `plant_type` renamed `pfts`; index rebuilt |
| 2026-08-12 | v2.235 | `ecosim-2dea74d9` | `2dea74d9` | wiki + seed | Soil biogeochemistry knowledge added to the wiki and the seed; index rebuilt |
| 2026-07-11 to 2026-07-14 | — | `ecosim-2dea74d9` (new) | `2dea74d9` | build | First profile: the knowledge chain built end to end (wiki, output registry, curated seed, index, graph); the seed source-verified and promoted from draft, with 28 parameters' definitions, units and bounds traced to source; two wiki citation errors fixed; plant-parameter dictionary added |
| 2026-07-07 | — | — | `2dea74d9` | registry | First output registry (516 variables) |
| 2026-04-25 | — | — | `2dea74d9` | A (greenfield) | Source-grounded wiki written from upstream `2dea74d9`, replacing the auto-generated one |
| 2026-02-09 | — | — | `7b8a4cf6` | — | First, auto-generated wiki |

## Recording an update

Every change that alters which model commit a profile describes (a new profile, a patch, a profile marked legacy) updates this README **in the same commit**:

1. add a row to the top of "Update history";
2. update "Current working version of the model", including the "In step with the model?" row.

`tools/check_kb_readme.py` enforces both against `rag/milestones.json`: the current-version section must name the live profile and the commit its knowledge base describes, and the history must name every base and patch commit of every registered EcoSIM profile. The commit hook runs it whenever `rag/milestones.json` or this directory is staged.

How each kind of update is made: `generate-codebase-wiki` (Workflow P to patch a profile in place, C or B for a new base), then `rebuild-rag` on the same profile and `validate-rag-chain`.
