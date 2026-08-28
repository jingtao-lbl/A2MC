# EcoSIM BioCON — Parameter-Bounds Literature Refinement (2026-07-15 addendum)

**Scope:** the provisional (`default±50%`) bounds on the params added/left after the 2026-07-12 review
(`bounds_literature_review_20260712.md`) — focused on the 8 perennial-compounding / C4 levers added
2026-07-15 (`20260715d`) + the two remaining photosynthesis provisionals (VOMX, ETMX). Method:
`paper-search-mcp` (Google Scholar) parameter-bounds mode; every adopted value mapped to EcoSIM's TRUE
definition (Grant-1989 protein-normalized kinetics), with validated DOIs.

## Adopted (defensible)

| param | old bound | new bound | basis (validated DOI) |
|---|---|---|---|
| **VOMX** | 7.5–22.5 (±50%) | **11.8–15.1** | Rubisco Vomax:Vcmax = 0.21–0.27 @25°C (Farquhar theory; the model's own ratio 15/56 = 0.27, Grant 1989) × VCMX default 56. A conserved ratio → a tight bound. |
| **DMRSV** | 0.50–0.85 | **0.67–0.92** | NSC reserves have the LOWEST construction cost / highest growth yield (Chiariello et al. 1989, `10.1007/978-94-010-9013-1_15`) — reserves are cheaper to build than structural stalk (default 0.67), so the range skews HIGH above it. |
| **CNRSV** | 0.02–0.06 | **0.01–0.04** | Reserve/storage tissue is LOW-N (NSC); C:N ~25–100 → N:C 0.01–0.04 (Ai et al. 2017 `10.1007/s00344-017-9673-y`, C4-grass NSC stoichiometry; Craine et al. 2002 `10.1046/j.1365-2435.2002.00660.x`, grassland tissue C:N). Default 0.04 = C:N 25 is the N-rich edge. |

## Grounded but KEPT provisional (definition/units unresolved)

| param | why not adopted |
|---|---|
| **VCMX4** (C4 PEP carb.) | C4 Vpmax is high-capacity (Kakani & Reddy 2008 `10.1007/s11099-008-0074-0`, *Andropogon gerardii* = PFT1; Zhou 2023 `10.1111/pce.14506`), but EcoSIM's VCMX4 is **per gC PEP protein**, not the leaf-area Vpmax literature reports — the protein-basis mapping is unverified. Range kept `default±50%` [80,240], now citation-annotated. |
| **PEPC** (PEP protein fraction) | PEP carboxylase is a major C4 leaf protein, but EcoSIM's "fraction of leaf protein" basis (total vs soluble) is unverified — same trap as RUBP in the prior review. Kept provisional. |
| **ETMX** (chl electron transport) | Jmax-analog but per gC chlorophyll (Grant 1989), not the leaf-area Jmax literature reports. Kept provisional. |

## No clean literature analog (model-specific)

- **VRNLI / VRNXI** (spring leafout / autumn leafoff, hours of favorable/senescence conditions) and
  **GROUPX** (maturity group / node number) are EcoSIM phenology controls with no direct measured
  analog. Kept wide-provisional for Morris to explore (the real BioCON uses VRNLI/VRNXI = 10; the analog
  used 240 — a large uncertainty worth spanning).
- The old provisionals **RSRR/RSRA/RTFQ/PTSHT/PR/XRLA/XRNI/UPMX\*** remain model-specific-unit (per the
  2026-07-12 review) — not re-reviewed.

## Takeaway

3 defensible refinements (VOMX, DMRSV, CNRSV) + citation-annotation on VCMX4. The recurring blocker is
EcoSIM's **protein-C-normalized** photosynthetic kinetics (VCMX4/PEPC/ETMX), which need a source-verified
protein-basis conversion before literature Vpmax/Jmax values can be adopted — a follow-on. A Phase-1
Morris μ* ranking will show which of the 40 actually matter before investing more in bounds.
