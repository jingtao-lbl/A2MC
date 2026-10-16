# EcoSIM knowledge graph, as HTML

Self-contained interactive views of the EcoSIM knowledge graph that A2MC's reasoning layer queries. Each page embeds its data and loads d3 7.9.0 from jsdelivr, so it opens in any browser; on a cluster, copy it down and open it locally.

| page | what it shows |
|---|---|
| `ecosim-cb243228_knowledge_graph.html` | every node of the active profile that has at least one edge: parameters, mechanisms, outputs and categories (categories hidden by default, since they are hubs). Search a name, toggle node types, double-click a node to focus on its two-hop neighbourhood, or use the buttons to focus on a calibration target. |

A case can render a second page, `<profile>_tested_parameters.html`, showing the parameters it tests, the mechanisms they control and the outputs reachable from them within three hops, with a coverage table: does each parameter have a node, a `controls` edge and a path to an output, and where the model reads it on the live path. An inert parameter (one the model never reads, or whose value never reaches the physics) is listed as such rather than as a gap, because the graph refuses it a `controls` edge by design. That page belongs to the case, so it is written into the case's own folder, not here.

Isolated nodes (most of the registered history outputs, which no curated relation reaches) are counted on each page and not drawn.

## They are generated

```bash
# the model-level page, here
python tools/render_kg_html.py --profile ecosim-cb243228 \
    --targets ECO_GPP_col ECO_RA_col ECO_RH_col ECO_ET_col CAN_GPP_pft NPP_pft

# a case's tested-parameter page, into that case's folder
python tools/render_kg_html.py --profile ecosim-cb243228 \
    --param-list use_cases/<Model>_<Case>/parameters/<param_list>.csv \
    --case <Model>_<Case> --targets <its scored outputs> \
    --out-dir use_cases/<Model>_<Case>/reports/<stem>
```

`--param-list` is repeatable, so one page can cover several rounds' lists. Regenerate after any graph rebuild (`scripts/build_ecosim_rag.py`). The renderer is model-agnostic: any profile in `rag/milestones.json` works, because every builder writes the same node-link format.

## What the graph does and does not hold

It holds relations true of the model's SOURCE: parameter controls mechanism, mechanism or parameter affects output, parameters coupled in one equation. A case's scored-target labels are not nodes, and a measured sensitivity is never an edge; the curated relations live in `models/ecosim/curated_seed.yaml`, each with a `file:line (Routine)` citation that `tools/check_ecosim_seed_citations.py` resolves at the profile's commit.

Parameter nodes come from three surfaces, each a file the model repository tracks at the profile's commit: plant traits, microbial kinetics, and the soil and site grid file (category `soil_and_site`), plus two fallback files for names the shipped defaults lack (`rag/milestones.json`, `param_files_extra_note`). A variable a surface carries but no source line mentions is dropped; one the source mentions but never reads from the file is kept and flagged `file_backed: false`.
