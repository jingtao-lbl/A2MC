# EcoSIM Parameter Bounds — Literature Review

**Date:** July 12, 2026
**Author:** Jing Tao with Claude on Perlmutter
**Scope:** Literature-based refinement of the *tractable* EcoSIM calibratable parameters
(those whose EcoSIM units map cleanly to published measurements). Produced with the repo
`literature-review` skill (parameter-bounds mode). The remaining parameters keep the provisional
default-anchored bounds in `ecosim_biocon_param_list.csv` (rubisco-mass-based Vcmax, root
resistivities, uptake-rate maxima — model-specific units that do not map cleanly to literature).

**DOI validation.** Every citation is a real paper with a resolvable DOI, rendered as a clickable
link. The reviewing agents validated all 36 DOIs via Crossref; **4 were independently re-validated
by the human-in-the-loop agent** (Ma 2018 `10.5194/bg-15-693-2018`; Bartlett 2012
`10.1111/j.1461-0248.2012.01751.x`; Zhou 2013 cloudberry `10.1080/01904167.2013.780610`; Galmés
2016 `10.1093/jxb/erw267`) — all resolved to the cited paper. No fabricated references.

**Headline caveat for the modeler.** For the leaf/stem N:C and leaf P:C parameters (`CNLF`,
`CNSTK`, `CPLF`) the current EcoSIM defaults sit **~3–5× above** the measured literature range once
mapped into gN·gC⁻¹ / gP·gC⁻¹. This may mean those defaults are encoded as maxima, or reflect a
unit/interpretation difference — the literature bounds below are the *measured* window; **do not
silently overwrite the defaults without confirming the parameter's exact definition in source.**

---

## Tissue stoichiometry (C:N, C:P)

This section refines EcoSIM's tissue-stoichiometry parameters — the leaf, root and stalk/stem nitrogen-to-carbon and phosphorus-to-carbon ratios (`CNLF`, `CNRT`, `CNSTK`, `CPLF`, `CPRT`) — against measured plant nutrient concentrations. The target context is arctic tundra (graminoids, deciduous and evergreen shrubs); the BioCON test case is a C3 grassland/forb system, which is bracketed by the temperate-herbaceous end of the same literature.

**Unit-mapping key (used throughout).** The literature almost universally reports tissue N and P as **mass concentrations** (mg element g⁻¹ dry mass, equivalently % of dry mass), whereas EcoSIM's parameters are **element-to-carbon mass ratios** (gN gC⁻¹, gP gC⁻¹). The bridge is the tissue carbon mass fraction *f*_C (gC g⁻¹ dry mass):

> N:C = (N concentration in mg g⁻¹ ÷ 1000) ÷ *f*_C  ;  P:C = (P concentration in mg g⁻¹ ÷ 1000) ÷ *f*_C

For *f*_C I use the global, organ-resolved synthesis of [Ma 2018](https://doi.org/10.5194/bg-15-693-2018) (4,318 species): **leaf 46.9%, stem 47.9%, root 45.6%** — all below the canonical 50% and consistent with the 45–48% range given in the task context. Equivalently, N:C = 1/(C:N mass ratio) when a paper reports C:N directly. Every converted value below shows this arithmetic explicitly.

**Headline finding for the modeler.** When the literature is mapped into EcoSIM units, the measured leaf, stem and leaf-P ratios fall **well below** the current defaults (`CNLF` 0.2, `CNSTK` 0.1, `CPLF` 0.02 are ~3–5× the literature upper bounds), while the root defaults (`CNRT` 0.016, `CPRT` 0.0016) sit inside the literature window. This suggests the leaf/stem defaults may be encoded as maxima, or reflect a unit/interpretation mismatch — flagged for review, not silently overwritten.

---

### CNLF — leaf N:C ratio

**Physical meaning & units.** `CNLF` is the nitrogen-to-carbon mass ratio of leaf/foliar biomass, **gN gC⁻¹** (current default 0.2). Physically it sets how N-rich green foliage is, which couples leaf construction to N demand and (in most land models) to photosynthetic capacity.

**How the literature maps.** The measurable is green-leaf N concentration (mg g⁻¹ or % mass). Conversion: N:C = (leaf N mg g⁻¹ ÷ 1000) ÷ 0.469. Example (arctic/alpine shrub mean of [Zhao 2018](https://doi.org/10.5194/bg-15-2033-2018)): 18.6 mg g⁻¹ ÷ 1000 = 0.0186 gN g⁻¹; ÷ 0.469 = **0.0397 gN gC⁻¹**. This matches the reciprocal of their measured leaf C:N (25.3 → 1/25.3 = 0.0395), a useful internal check. Arctic graminoids and forbs tend to carry somewhat higher leaf N than woody evergreens, and leaf N is elevated at cold, high latitudes ([Reich 2004](https://doi.org/10.1073/pnas.0403588101)), so the upper bound is set by N-rich deciduous/graminoid foliage.

**Reported values.**

| Value (as reported) | Units as reported | Converted (gN gC⁻¹) | PFT / species | Site / biome | Citation |
|---|---|---|---|---|---|
| leaf N = 18.6 (geom. mean); C:N 11.7–46.9 | mg g⁻¹ ; mass ratio | 0.040 (range 0.021–0.085) | shrubs (alpine/valley, evergreen + deciduous, 125 sites) | Tibetan Plateau, 523–4685 m | [Zhao 2018](https://doi.org/10.5194/bg-15-2033-2018) |
| leaf N higher toward cold, high latitudes; grasses/herbs/shrubs distinguished | mg g⁻¹ (global synthesis, 1,280 spp.) | pattern (upper tail for graminoid/forb) | grasses, herbs, shrubs, trees, conifers | global, 452 sites | [Reich 2004](https://doi.org/10.1073/pnas.0403588101) |
| aboveground tissue N by growth form (graminoid / deciduous / evergreen) | mg g⁻¹ | supports growth-form spread | 7 tundra vascular spp., 3 growth forms | low-arctic tundra, Canada | [Gu 2017](https://doi.org/10.1139/as-2016-0032) |
| tundra leaf economics traits fall within global leaf-N space | — | corroborates window | tundra graminoid/shrub/forb | circumarctic (TTT database) | [Thomas 2020](https://doi.org/10.1038/s41467-020-15014-4) |

**Derived bound.** **[0.020, 0.080] gN gC⁻¹, central 0.040.** Lower bound = N-poor evergreen-shrub foliage (C:N ≈ 47 → 0.021); upper bound = N-rich deciduous-shrub/graminoid foliage at cold latitudes (leaf N ≈ 3.5% → 0.035/0.469 = 0.075, rounded to 0.08). Central 0.040 is the direct Zhao 2018 shrub anchor. Decision: **literature**. Note the current default (0.2) is ~2.5× the upper bound.

---

### CNRT — root N:C ratio

**Physical meaning & units.** `CNRT` is the N:C mass ratio of (fine) root biomass, **gN gC⁻¹** (current default 0.016). It governs the N cost of building the belowground absorptive system, which in tundra holds the majority of plant biomass ([Iversen 2014](https://doi.org/10.1111/nph.13003)).

**How the literature maps.** The measurable is fine-root N concentration (mg g⁻¹). Conversion uses root *f*_C = 0.456 (Ma 2018): N:C = (root N mg g⁻¹ ÷ 1000) ÷ 0.456. Global fine-root anchor from [Wang 2019](https://doi.org/10.1111/1365-2435.13434) (1,890 obs, 763 species, 433 sites): 10.84 mg g⁻¹ ÷ 1000 = 0.01084; ÷ 0.456 = **0.0238 gN gC⁻¹**.

**Reported values.**

| Value (as reported) | Units as reported | Converted (gN gC⁻¹) | PFT / species | Site / biome | Citation |
|---|---|---|---|---|---|
| fine-root N = 10.84 (geom. mean) | mg g⁻¹ | 0.024 | all terrestrial plants (global synthesis) | global, 433 sites | [Wang 2019](https://doi.org/10.1111/1365-2435.13434) |
| fine-root N spread ≈ 6–16 across groups (within/among ecosystems) | mg g⁻¹ | 0.013–0.035 | graminoids, shrubs, forbs, trees | global | [Wang 2019](https://doi.org/10.1111/1365-2435.13434) |
| tundra fine-root chemistry sparse but quantified for few spp.; roots dominate biomass | qualitative + compiled | window support | tundra graminoid/shrub | arctic tundra (review) | [Iversen 2014](https://doi.org/10.1111/nph.13003) |

**Derived bound.** **[0.013, 0.030] gN gC⁻¹, central 0.024.** Bounds span the fine-root N range (≈6–16 mg g⁻¹) around the global geometric mean; central 0.024 is the Wang 2019 anchor. Decision: **literature**. The current default (0.016 → root N ≈ 0.73%) sits at the low-N end of this window (it corresponds to ≈7.3 mg g⁻¹), i.e. defensible but on the conservative side; the refined window recentres it upward.

---

### CNSTK — stalk/stem N:C ratio

**Physical meaning & units.** `CNSTK` is the N:C mass ratio of stalk/stem (structural, support/transport) biomass, **gN gC⁻¹** (current default 0.1). This is the most heterogeneous parameter of the group: in EcoSIM "stalk/stem" must cover both **woody shrub stems** (very low N) and **graminoid culms** (moderate N), which differ by roughly an order of magnitude.

**How the literature maps.** The measurable is stem/branch/culm N concentration, converted with stem *f*_C = 0.479 (Ma 2018): N:C = (stem N mg g⁻¹ ÷ 1000) ÷ 0.479. The open-access, organ-resolved literature I could validate reports the **allocation pattern** rather than a single site-matched absolute value in mappable units:

- Across 335 woody species, twig-stem N is consistently a **fraction of leaf N**, and the leaf-N : stem-N ratio **increases toward cold, high latitudes** (twig-stem N grows more slowly than leaf N as plant N rises; scaling exponent αN falls from >1 to <1 with latitude) — [Yan 2016](https://doi.org/10.1038/srep20099).
- Across 803 species in China's forests, elemental homeostasis and C:N:P are ordered **leaves > branches > roots > trunks**, i.e. trunks/stems are the most C-rich, lowest-N organ — [Zhang 2017](https://doi.org/10.1111/1365-2435.12979).
- In tall deciduous-shrub tundra, warming/fertilization shifts C and N allocation into **woody stems** that have low N per unit C and long residence time — [DeMarco 2014](https://doi.org/10.1890/es13-00281.1).

**Reported values.**

| Value (as reported) | Units as reported | Converted (gN gC⁻¹) | PFT / species | Site / biome | Citation |
|---|---|---|---|---|---|
| stem N ≪ leaf N; leaf:stem N ratio rises at high latitude | scaling exponents (dimensionless) | qualitative (stem N a small fraction of leaf N) | 335 woody species | eastern China, 12 forests | [Yan 2016](https://doi.org/10.1038/srep20099) |
| organ order leaves > branches > roots > trunks for N and homeostasis | mass ratios (values paywalled) | not extractable in mappable form | 803 species (leaves/branches/trunks/roots) | China, 9 forests | [Zhang 2017](https://doi.org/10.1111/1365-2435.12979) |
| allocation to low-N woody stems under warming/fertilization | tissue C, N pools | qualitative | deciduous shrub tundra | Alaska (Toolik) | [DeMarco 2014](https://doi.org/10.1890/es13-00281.1) |

**Derived bound (provisional).** Literature-informed guidance: woody shrub stem/branch C:N is typically ~100–350 (→ N:C 0.003–0.010), whereas graminoid culms are far less C-rich (C:N ~40–100 → N:C 0.010–0.025). A pooled provisional window is therefore **[0.003, 0.025] gN gC⁻¹, central ≈ 0.010**. **Decision: keep_provisional** — no single measured stem/culm N value for the target PFTs could be extracted in mappable units from an open-access source (the two organ-resolved datasets with absolute numbers, [Zhang 2017](https://doi.org/10.1111/1365-2435.12979) and Yang et al. 2014's shrubland organ tables, are paywalled here). The one firm, citable conclusion is directional: the current default (0.1 → C:N ≈ 10, more N-rich than leaves) is **implausibly high** for structural tissue and should be revised down once site-matched stem-N measurements are digitized.

---

### CPLF — leaf P:C ratio

**Physical meaning & units.** `CPLF` is the P:C mass ratio of leaf biomass, **gP gC⁻¹** (current default 0.02). It sets foliar P demand, central in the arctic where N–P co-limitation is common.

**How the literature maps.** Measurable: green-leaf P concentration (mg g⁻¹), converted with leaf *f*_C = 0.469: P:C = (leaf P mg g⁻¹ ÷ 1000) ÷ 0.469. Shrub anchor from [Zhao 2018](https://doi.org/10.5194/bg-15-2033-2018): 1.50 mg g⁻¹ ÷ 1000 = 0.00150; ÷ 0.469 = **0.0032 gP gC⁻¹** (equivalently 1/C:P = 1/312 = 0.0032). Their C:P range 113.8–646.5 maps to P:C 0.0088–0.0015.

**Reported values.**

| Value (as reported) | Units as reported | Converted (gP gC⁻¹) | PFT / species | Site / biome | Citation |
|---|---|---|---|---|---|
| leaf P = 1.50 (geom. mean); C:P 113.8–646.5 | mg g⁻¹ ; mass ratio | 0.0032 (range 0.0015–0.0088) | shrubs (evergreen + deciduous) | Tibetan Plateau | [Zhao 2018](https://doi.org/10.5194/bg-15-2033-2018) |
| leaf P declines toward warm/low latitudes; higher at cold high latitudes | mg g⁻¹ (global) | pattern support | grasses, herbs, shrubs | global | [Reich 2004](https://doi.org/10.1073/pnas.0403588101) |

**Derived bound.** **[0.0015, 0.006] gP gC⁻¹, central 0.0032.** Lower bound = P-poor foliage (C:P ≈ 640); upper bound trimmed to ~0.006 (P-rich foliage; the 0.0088 valley extreme is not representative of P-limited arctic soils). Central 0.0032 is the Zhao 2018 anchor. Decision: **literature**. The current default (0.02 → leaf P ≈ 0.94%) is ~3× the literature upper bound and implausibly P-rich for tundra foliage.

---

### CPRT — root P:C ratio

**Physical meaning & units.** `CPRT` is the P:C mass ratio of (fine) root biomass, **gP gC⁻¹** (current default 0.0016).

**How the literature maps.** Measurable: fine-root P concentration (mg g⁻¹), converted with root *f*_C = 0.456: P:C = (root P mg g⁻¹ ÷ 1000) ÷ 0.456. Global anchor from [Wang 2019](https://doi.org/10.1111/1365-2435.13434): 0.94 mg g⁻¹ ÷ 1000 = 0.00094; ÷ 0.456 = **0.0021 gP gC⁻¹**.

**Reported values.**

| Value (as reported) | Units as reported | Converted (gP gC⁻¹) | PFT / species | Site / biome | Citation |
|---|---|---|---|---|---|
| fine-root P = 0.94 (geom. mean) | mg g⁻¹ | 0.0021 | all terrestrial plants (global) | global, 433 sites | [Wang 2019](https://doi.org/10.1111/1365-2435.13434) |
| fine-root P spread ≈ 0.5–1.5 across groups | mg g⁻¹ | 0.0011–0.0033 | graminoids, shrubs, forbs, trees | global | [Wang 2019](https://doi.org/10.1111/1365-2435.13434) |
| tundra roots dominate biomass; root nutrient data sparse | compiled | window support | tundra | arctic (review) | [Iversen 2014](https://doi.org/10.1111/nph.13003) |

**Derived bound.** **[0.0011, 0.0033] gP gC⁻¹, central 0.0021.** Bounds span the fine-root P range (≈0.5–1.5 mg g⁻¹); central 0.0021 is the Wang 2019 anchor. Decision: **literature**. The current default (0.0016 → root P ≈ 0.073%) already falls **inside** this window (low-P end), so this is the best-supported of the five defaults; the refined window recentres it slightly upward.

---

### References (this group)

- Iversen, C. M. et al. (2014). The unseen iceberg: plant roots in arctic tundra. *New Phytologist* 205(1):34–58. [https://doi.org/10.1111/nph.13003](https://doi.org/10.1111/nph.13003)
- Ma, S. et al. (2018). Variations and determinants of carbon content in plants: a global synthesis. *Biogeosciences* 15(3):693–702. [https://doi.org/10.5194/bg-15-693-2018](https://doi.org/10.5194/bg-15-693-2018)
- DeMarco, J. et al. (2014). Long-term experimental warming and nutrient additions increase productivity in tall deciduous shrub tundra. *Ecosphere* 5(6):1–22. [https://doi.org/10.1890/es13-00281.1](https://doi.org/10.1890/es13-00281.1)
- Gu, Q., Zamin, T. J. & Grogan, P. (2017). Stoichiometric homeostasis: a test to predict tundra vascular plant species and community-level responses to climate change. *Arctic Science* 3(2):320–333. [https://doi.org/10.1139/as-2016-0032](https://doi.org/10.1139/as-2016-0032)
- Reich, P. B. & Oleksyn, J. (2004). Global patterns of plant leaf N and P in relation to temperature and latitude. *PNAS* 101(30):11001–11006. [https://doi.org/10.1073/pnas.0403588101](https://doi.org/10.1073/pnas.0403588101)
- Thomas, H. J. D. et al. (2020). Global plant trait relationships extend to the climatic extremes of the tundra biome. *Nature Communications* 11:1351. [https://doi.org/10.1038/s41467-020-15014-4](https://doi.org/10.1038/s41467-020-15014-4)
- Wang, Z. et al. (2019). The scaling of fine root nitrogen versus phosphorus in terrestrial plants: A global synthesis. *Functional Ecology* 33(11):2081–2094. [https://doi.org/10.1111/1365-2435.13434](https://doi.org/10.1111/1365-2435.13434)
- Yan, Z. et al. (2016). Nutrient allocation strategies of woody plants: an approach from the scaling of nitrogen and phosphorus between twig stems and leaves. *Scientific Reports* 6:20099. [https://doi.org/10.1038/srep20099](https://doi.org/10.1038/srep20099)
- Zhang, J. et al. (2017). C:N:P stoichiometry in China's forests: From organs to ecosystems. *Functional Ecology* 32(1):50–60. [https://doi.org/10.1111/1365-2435.12979](https://doi.org/10.1111/1365-2435.12979)
- Zhao, W. et al. (2018). Shrub type dominates the vertical distribution of leaf C : N : P stoichiometry across an extensive altitudinal gradient. *Biogeosciences* 15(7):2033–2053. [https://doi.org/10.5194/bg-15-2033-2018](https://doi.org/10.5194/bg-15-2033-2018)

*DOI-validation note: all 11 DOIs cited in this section were verified via Crossref (`get_crossref_paper_by_doi`) on 2026-07-12; returned titles, authors and years match the citations above.*

---

## Leaf & root morphology

This group covers one leaf-morphology parameter (`SLA1`) and three root-morphology parameters (`RRAD1M`, `RRAD2M`, `PORT`) for an Arctic/cold-climate herbaceous + shrub system (Kougarok-type wet-to-mesic tundra: sedges/graminoids, deciduous shrubs, evergreen shrubs). Literature was drawn preferentially from arctic/tundra sources; where arctic data are thin the review widens to global/temperate syntheses and says so explicitly.

Two unit conventions recur below:
- **SLA on a carbon basis.** EcoSIM stores SLA per unit leaf **carbon** (m² gC⁻¹). Field SLA is reported either per unit leaf **dry mass** (m² kg⁻¹ or m² g⁻¹ dry) or, in some land-surface models, already per unit **C** (m² kg⁻¹ C). Dry-mass → carbon conversion uses a leaf carbon fraction *C*_frac ≈ 0.45–0.48 gC g⁻¹ dry (midpoint 0.47): **m² gC⁻¹ = (m² g⁻¹ dry) / *C*_frac**. Per-C values in m² kg⁻¹ C convert by ÷1000.
- **Root radius vs. the reported morphology.** Field root morphology is almost never reported as a radius. It is reported as **mean diameter** (radius = diameter/2) or as **specific root length** SRL (m g⁻¹). SRL maps to radius only through an assumed root tissue density *ρ*: for a cylinder, SRL = 1/(π *r*² *ρ*), so **r = √(1 / (π · SRL · ρ))**. This density dependence is why the two radius parameters below end up *provisional*.

---

### SLA1 — specific leaf area (leaf-area growth per unit leaf C)

**Physical meaning & units.** `SLA1` is the leaf area produced per unit leaf carbon, m² gC⁻¹ (EcoSIM default 0.00333 m² gC⁻¹, i.e. 3.33 m² kgC⁻¹). It sets how much light-intercepting area a PFT builds per unit C invested in leaves, so it is a first-order control on canopy LAI and GPP.

**How the literature maps.** The measurable quantity is specific leaf area. Two arctic land-model parameterizations report SLA in directly mappable units:
- **van der Kolk et al. (2016)** (NUCOM-tundra) report SLA on a **dry-mass** basis (their Table A1, sourced from Shaver & Chapin's Alaskan tussock-tundra measurements): graminoid 0.0060 m² g⁻¹ dry, dwarf shrub 0.0139 m² g⁻¹ dry. Converting with *C*_frac = 0.47: graminoid = 0.0060 / 0.47 = **0.0128 m² gC⁻¹**; shrub = 0.0139 / 0.47 = **0.0296 m² gC⁻¹** (the *C*_frac 0.45–0.48 window moves these only in the third decimal: 0.0125–0.0133 and 0.0290–0.0309).
- **Meyer et al. (2021)** (CLASSIC, Canada's Southern Arctic dwarf-shrub tundra) report SLA already on a **carbon** basis (their Table 2): broadleaf evergreen shrub 15, broadleaf deciduous cold shrub 20, sedge 25, C3 grass 25 m² kg⁻¹ C. Dividing by 1000: **0.015, 0.020, 0.025, 0.025 m² gC⁻¹**.

The two independent arctic sources bracket a consistent range of ≈ **0.013–0.030 m² gC⁻¹** across graminoid/sedge and shrub PFTs. **Thomas et al. (2018)** confirm, from a 295-species tundra trait database, that SLA is one of the "economic" traits that separates cleanly by growth form (evergreen shrub < deciduous shrub ≈ graminoid), consistent with the ordering above (tough evergreen/tussock leaves at the low end, deciduous shrubs and lax graminoids higher). Note that the EcoSIM default (0.00333 m² gC⁻¹) sits a factor of ≈ 4–9 **below** this arctic literature range; on a dry-mass basis it implies ≈ 0.0016 m² g⁻¹ dry (16 cm² g⁻¹), a value typical only of extremely sclerophyllous foliage, not of arctic graminoids or deciduous shrubs.

**Reported values**

| value | units as reported | converted to m² gC⁻¹ | PFT/species | site | citation |
|---|---|---|---|---|---|
| 0.0060 | m² g⁻¹ leaf dry mass | 0.013 | graminoid (tussock tundra, e.g. *Eriophorum*) | Alaskan tussock tundra (via Shaver & Chapin) | [van der Kolk 2016](https://doi.org/10.5194/bg-13-6229-2016) |
| 0.0139 | m² g⁻¹ leaf dry mass | 0.030 | dwarf shrub | Alaskan tundra | [van der Kolk 2016](https://doi.org/10.5194/bg-13-6229-2016) |
| 15 | m² kg⁻¹ C | 0.015 | broadleaf evergreen shrub | Canada Southern Arctic | [Meyer 2021](https://doi.org/10.5194/bg-18-3263-2021) |
| 20 | m² kg⁻¹ C | 0.020 | broadleaf deciduous cold shrub | Canada Southern Arctic | [Meyer 2021](https://doi.org/10.5194/bg-18-3263-2021) |
| 25 | m² kg⁻¹ C | 0.025 | sedge | Canada Southern Arctic | [Meyer 2021](https://doi.org/10.5194/bg-18-3263-2021) |
| 25 | m² kg⁻¹ C | 0.025 | C3 grass | Canada Southern Arctic | [Meyer 2021](https://doi.org/10.5194/bg-18-3263-2021) |
| — | qualitative (SLA separates by growth form) | — | 295 tundra vascular species | pan-Arctic (ITEX/TRY) | [Thomas 2018](https://doi.org/10.1111/geb.12783) |

**Derived bound.** [0.010, 0.030] m² gC⁻¹, central 0.020. The lower edge is pulled slightly below the lowest cited value (0.013) to admit low-SLA evergreen tundra shrubs; the upper edge is the deciduous-shrub/sedge value (~0.030). Decision: **literature** — two independent arctic parameterizations plus a tundra-biome trait synthesis, all in mappable units. The current EcoSIM default (0.00333) lies below this range and is flagged for revision.

---

### RRAD1M — primary (coarse) root radius

**Physical meaning & units.** `RRAD1M` is the radius of the primary/axial root class, in metres (default 0.0002 m = 0.20 mm radius, i.e. 0.40 mm diameter).

**How the literature maps.** No arctic study reports a "primary root radius" directly; **Iversen et al. (2015)** explicitly note that tundra root morphological traits have been quantified for only a small fraction of species, so arctic data are thin. The available anchors are (i) directional and (ii) morphological-via-SRL:
- **Freschet et al. (2017)**, a global fine-root dataset (1115 species), establish that plant functional type and temperature are the dominant controls on fine-root diameter: herbaceous species have finer roots (higher SRL) than woody species, and higher temperature favours thicker roots / lower SRL — i.e., cold-climate roots trend *fine*. This constrains the *direction* but not an absolute radius.
- **van der Kolk et al. (2016)** report SRL for arctic PFTs (Table A1): graminoid 37.5 m g⁻¹, dwarf shrub 141.0 m g⁻¹. Converting SRL to radius via r = √(1/(π·SRL·ρ)) requires an assumed root tissue density ρ. Taking ρ = 0.1–0.3 g cm⁻³ (the typical fine-root range): graminoid radius ≈ 0.17–0.29 mm; shrub radius ≈ 0.086–0.15 mm. The **graminoid** (thicker, lower-SRL) class brackets the `RRAD1M` default of 0.20 mm.

**Reported values**

| value | units as reported | converted to root radius (m) | PFT/species | site | citation |
|---|---|---|---|---|---|
| 37.5 | m g⁻¹ (SRL) | ≈ 1.7–2.9 ×10⁻⁴ (ρ = 0.1–0.3 g cm⁻³) | graminoid | arctic tundra | [van der Kolk 2016](https://doi.org/10.5194/bg-13-6229-2016) |
| woody > herbaceous diameter; cold → finer | qualitative (diameter, SRL) | — | global growth forms | global (1115 spp.) | [Freschet 2017](https://doi.org/10.1111/1365-2745.12769) |
| "quantified for few tundra species" | — | — | tundra roots (review) | pan-Arctic | [Iversen 2015](https://doi.org/10.1111/nph.13003) |

**Derived bound.** **keep_provisional.** The default (0.20 mm radius) is *consistent* with the coarser (graminoid) arctic root class under a plausible tissue density, but the only mappable arctic datum (SRL) converts to a radius only through an assumed ρ, so the units do not map cleanly to a directly measured radius. Retain the default provisionally; a defensible numeric bound needs a directly measured mean root diameter for the site's PFTs (or a measured root tissue density to close the SRL→radius conversion).

---

### RRAD2M — secondary (fine/lateral) root radius

**Physical meaning & units.** `RRAD2M` is the radius of the secondary/lateral (finer) root class, in metres (default 0.0001 m = 0.10 mm radius, i.e. 0.20 mm diameter). It should be finer than `RRAD1M`.

**How the literature maps.** Same evidence base and same limitation as `RRAD1M`. The finer class corresponds to absorptive/lateral roots. From the SRL conversion above, the higher-SRL (finer) arctic class — here the dwarf shrub at SRL 141 m g⁻¹ — converts to a radius of ≈ 0.086–0.15 mm (ρ = 0.1–0.3 g cm⁻³), which brackets the `RRAD2M` default of 0.10 mm. **Freschet et al. (2017)** independently support that the finer/absorptive roots of these growth forms fall at the low end of the global diameter spectrum, and that cold climates push toward finer roots. **Iversen et al. (2015)** again caution that arctic absorptive-root radii are sparsely measured.

**Reported values**

| value | units as reported | converted to root radius (m) | PFT/species | site | citation |
|---|---|---|---|---|---|
| 141.0 | m g⁻¹ (SRL) | ≈ 0.86–1.5 ×10⁻⁴ (ρ = 0.1–0.3 g cm⁻³) | dwarf shrub (finer/absorptive class) | arctic tundra | [van der Kolk 2016](https://doi.org/10.5194/bg-13-6229-2016) |
| herbaceous/absorptive roots finest; cold → finer | qualitative (diameter, SRL) | — | global growth forms | global (1115 spp.) | [Freschet 2017](https://doi.org/10.1111/1365-2745.12769) |
| arctic absorptive-root traits sparsely quantified | — | — | tundra roots (review) | pan-Arctic | [Iversen 2015](https://doi.org/10.1111/nph.13003) |

**Derived bound.** **keep_provisional.** The default (0.10 mm radius) is consistent with the finer arctic root class under a plausible tissue density and with the global direction (cold-climate absorptive roots are fine), but as for `RRAD1M` the only mappable arctic datum is SRL, which requires an assumed ρ to become a radius. Retain the default provisionally pending a directly measured absorptive-root diameter or root tissue density for the site's PFTs.

---

### PORT — root porosity (aerenchyma volume fraction)

**Physical meaning & units.** `PORT` is the gas-filled (aerenchyma) volume fraction of the root, m³ m⁻³ (dimensionless 0–1; default 0.33). It controls internal aeration / radial O₂ loss and, in a wet-tundra context, is directly tied to sedge-mediated CH₄ transport.

**How the literature maps.** The measurable quantity — root porosity as a percentage of root volume — maps 1:1 onto `PORT` after dividing by 100 (e.g. 55 % → 0.55 m³ m⁻³):
- **Colmer (2003)**, the standard synthesis of root internal aeration, states that roots of **many wetland species contain large aerenchyma volumes, with porosity reaching up to 55 %**, whereas non-wetland roots have much lower porosity. This gives a clean ceiling (0.55) and establishes the wetland-vs-non-wetland contrast that spans the Kougarok PFT mix (aerenchymatous sedges vs. lower-porosity shrubs).
- **Striker et al. (2007)** show, for a graminaceous (grass) type and a **cyperaceous (sedge) type** among others, that root porosity rises with root diameter and under flooding, and that grass/sedge root structures maintain mechanical strength even at high porosity — i.e. sedges/graminoids, the arctic wetland dominants, are structurally suited to high aerenchyma fractions.
- **Iversen et al. (2015)** highlight that root aeration/aerenchyma is a functionally important but under-quantified trait in tundra, where *Eriophorum*/*Carex* aerenchyma is the principal conduit for soil CH₄ — consistent with a **high** representative porosity for a sedge-dominated wet tundra.

**Reported values**

| value | units as reported | converted to m³ m⁻³ | PFT/species | site | citation |
|---|---|---|---|---|---|
| up to 55 | % of root volume | 0.55 (ceiling) | many wetland species | global synthesis | [Colmer 2003](https://doi.org/10.1046/j.1365-3040.2003.00846.x) |
| wetland ≫ non-wetland | % | wetland high, non-wetland low | wetland vs non-wetland roots | global | [Colmer 2003](https://doi.org/10.1046/j.1365-3040.2003.00846.x) |
| rises with diameter/flooding; strength retained | % | — | *Cyperus* (sedge), *Paspalidium* (grass) | greenhouse | [Striker 2007](https://doi.org/10.1111/j.1365-3040.2007.01639.x) |
| aerenchyma = key CH₄ conduit (sedges) | qualitative | high for wet-tundra sedges | *Eriophorum*/*Carex* tundra | pan-Arctic | [Iversen 2015](https://doi.org/10.1111/nph.13003) |

**Derived bound.** [0.05, 0.50] m³ m⁻³, central 0.30. The upper edge sits just under Colmer's 0.55 wetland ceiling (appropriate for aerenchymatous arctic sedges); the lower edge (~0.05) represents the much lower porosity of non-wetland dwarf-shrub roots. The EcoSIM default (0.33) falls squarely within this range and is well justified for a sedge-dominated wet tundra. Decision: **literature** — a canonical aeration synthesis with an explicit numeric ceiling plus corroborating sedge/grass anatomy. (Caveat: the low edge is inferred from the wetland-vs-non-wetland contrast rather than a species-specific arctic-shrub porosity measurement.)

---

### References (this group)

- Colmer, T. D. (2003). Long-distance transport of gases in plants: a perspective on internal aeration and radial oxygen loss from roots. *Plant, Cell & Environment* 26(1), 17–36. [https://doi.org/10.1046/j.1365-3040.2003.00846.x](https://doi.org/10.1046/j.1365-3040.2003.00846.x)
- Freschet, G. T. et al. (2017). Climate, soil and plant functional types as drivers of global fine-root trait variation. *Journal of Ecology* 105(5), 1182–1196. [https://doi.org/10.1111/1365-2745.12769](https://doi.org/10.1111/1365-2745.12769)
- Iversen, C. M. et al. (2015). The unseen iceberg: plant roots in arctic tundra. *New Phytologist* 205(1), 34–58. [https://doi.org/10.1111/nph.13003](https://doi.org/10.1111/nph.13003)
- Meyer, G. et al. (2021). Simulating shrubs and their energy and carbon dioxide fluxes in Canada's Low Arctic with CLASSIC. *Biogeosciences* 18(11), 3263–3283. [https://doi.org/10.5194/bg-18-3263-2021](https://doi.org/10.5194/bg-18-3263-2021)
- Striker, G. G. et al. (2007). Trade-off between root porosity and mechanical strength in species with different types of aerenchyma. *Plant, Cell & Environment* 30(5), 580–589. [https://doi.org/10.1111/j.1365-3040.2007.01639.x](https://doi.org/10.1111/j.1365-3040.2007.01639.x)
- Thomas, H. J. D. et al. (2018). Traditional plant functional groups explain variation in economic but not size-related traits across the tundra biome. *Global Ecology and Biogeography* 28(2), 78–95. [https://doi.org/10.1111/geb.12783](https://doi.org/10.1111/geb.12783)
- van der Kolk, H.-J. et al. (2016). Potential Arctic tundra vegetation shifts in response to changing temperature, precipitation and permafrost thaw. *Biogeosciences* 13(22), 6229–6245. [https://doi.org/10.5194/bg-13-6229-2016](https://doi.org/10.5194/bg-13-6229-2016)

---

## Water relations

*Scope: C3 herbaceous / tundra plant functional type. Where arctic-specific measurements were thin, the review widens to temperate herbaceous, graminoid, and mesic/moist-habitat woody species and says so explicitly. All DOIs verified via Crossref on 2026-07-12; each returned a title/authors/year matching the citation below.*

### OSMO — leaf osmotic potential at zero turgor / at full hydration

**Physical meaning & units.** In EcoSIM, `OSMO` sets the leaf solute (osmotic) potential that anchors the plant's water-relations / turgor calculation. The parameter description conflates two distinct but tightly-linked pressure–volume (P–V) curve quantities: the **osmotic potential at full turgor / full hydration** (π_o, the y-intercept of the P–V curve at saturation) and the **leaf water potential at turgor loss point** (π_tlp, the water potential at which cell turgor reaches zero and the leaf wilts). Both are expressed in **MPa** (negative sign; more negative = more solute-concentrated / more drought-tolerant). EcoSIM's default is **−1.8 MPa**.

**How the literature maps.** Both π_o and π_tlp are routinely measured by the P–V curve method or the rapid vapour-pressure-osmometer method ([Bartlett 2012](https://doi.org/10.1111/j.1461-0248.2012.01751.x); [Griffin-Nolan 2019](https://doi.org/10.1007/s00442-019-04336-w)), and both are reported directly in **MPa** — the same unit EcoSIM uses — so **no unit conversion is required**; the only mapping decision is *which* of the two the parameter represents. This matters because they are offset from each other. The global meta-analysis of [Bartlett 2012](https://doi.org/10.1111/j.1461-0248.2012.01751.x) (317 species, 72 studies) established that π_o is the dominant driver of π_tlp, with the empirical relationship π_tlp ≈ 0.832·π_o − 0.631 (MPa). Arithmetically this means π_tlp is roughly **0.4–0.5 MPa more negative** than π_o over the range of interest (e.g. π_o = −1.2 → π_tlp = 0.832×(−1.2) − 0.631 = −1.63 MPa; π_o = −1.5 → π_tlp = −1.88 MPa). So a value tabulated as π_tlp sits at the more-negative edge of the plausible OSMO window and a value tabulated as π_o at the less-negative edge; the adopted bound is taken as the **union** of both.

Tundra and moist-graminoid systems are mesic (high water availability), and in [Bartlett 2012](https://doi.org/10.1111/j.1461-0248.2012.01751.x) π_tlp scaled with water availability across biomes — wet/moist habitats occupy the **less negative** (−1 to −2 MPa) part of the global range, while arid/sclerophyll biomes reach −3 to −4 MPa. This places C3 herbaceous/tundra plants in the moderate-to-less-negative band, consistent with the moist-habitat measurements below.

**Reported values.**

| Value (as reported) | Units as reported | Converted to OSMO units (MPa) | PFT / species | Site / biome | Citation |
|---|---|---|---|---|---|
| π_tlp −1.70 to −1.76 (wet-habitat spp.); native-species mean −2.33 ± 0.33 | MPa | −1.70 to −2.33 (direct) | Woody trees/shrubs, moist-habitat spp. (*Ilex aquifolium* −1.75, *Alnus glutinosa* −1.76) | Central Europe (temperate; moist-habitat proxy) | [Kunert 2020](https://doi.org/10.1093/jpe/rtaa059) |
| π_o = major driver of π_tlp; π_tlp = 0.832·π_o − 0.631; wet biomes least negative | MPa | framework: π_tlp ≈ π_o − 0.4 to 0.5 | 317 species across biomes (incl. tundra/mesic) | Global meta-analysis | [Bartlett 2012](https://doi.org/10.1111/j.1461-0248.2012.01751.x) |
| Osmometer π_tlp method validated for **herbaceous** spp. (grassland forbs & grasses) | MPa | direct (MPa) | Herbaceous (grassland) | US Great Plains grassland (temperate herbaceous) | [Griffin-Nolan 2019](https://doi.org/10.1007/s00442-019-04336-w) |
| Graminoids more drought-tolerant (more negative π_tlp) than forbs; π_tlp coordinated with stomatal-closure & embolism thresholds | MPa | direct (MPa) | 9 herbs (graminoid + forb) | Pot study (herbaceous PFT) | [Huang 2025](https://doi.org/10.1111/1365-2435.70036) |
| Ψ_tlp of 166 vascular spp. spanning alpine→Mediterranean; alpine/high-elevation spp. less negative | MPa | direct (MPa) | 159 angiosperms + 7 gymnosperms | NE Italy, alpine to Mediterranean | [Tordoni 2022](https://doi.org/10.1111/gcb.16400) |

**Derived bound.** **[−2.5, −1.0] MPa, central −1.7 MPa (decision: literature).** The moist-habitat / herbaceous measurements cluster near −1.0 to −1.8 MPa for π_o and near −1.7 to −2.3 MPa for π_tlp; taking the union across the two P–V quantities the parameter can represent, and restricting to the mesic (tundra/moist-graminoid) end of the global gradient rather than arid extremes (which reach −3 to −4 MPa), gives a window of roughly −2.5 (drought-tolerant graminoid, π_tlp) to −1.0 MPa (wet-habitat, π_o). The central estimate −1.7 MPa coincides with the global π_tlp mean band and with the moist-habitat measurements of [Kunert 2020](https://doi.org/10.1093/jpe/rtaa059). **The EcoSIM default of −1.8 MPa falls within this window** and is well-supported for a moist C3 tundra PFT; the bound mainly serves to prevent excursions toward arid-sclerophyll (< −2.5) or hydrophyte-succulent (> −1.0) territory. Window is deliberately moderately wide because (a) the parameter's π_o-vs-π_tlp identity is ambiguous and (b) arctic-specific P–V data are sparse, so temperate-herbaceous and moist-habitat proxies were used. `bound_source: literature (Bartlett 2012; Kunert 2020)`.

### FCO2 — intercellular : atmospheric CO2 ratio (Ci/Ca)

**Physical meaning & units.** `FCO2` is the ratio of intercellular (substomatal) CO2 partial pressure to ambient/atmospheric CO2 partial pressure, C_i/C_a, applied in EcoSIM as a **fixed dimensionless fraction** (0–1). It effectively encodes the plant's stomatal water-use strategy: a higher C_i/C_a means stomata hold intercellular CO2 close to ambient (less diffusive drawdown, lower water-use efficiency), a lower value means a larger CO2 drawdown (tighter stomata, higher intrinsic WUE). EcoSIM's default is **0.45**.

**How the literature maps.** C_i/C_a is **dimensionless** and reported directly as a ratio in gas-exchange studies, so it maps to `FCO2` with **no conversion**. It is measured two ways, both of which land in the same units: (1) directly by infrared gas analysis (measure C_i and C_a, take the ratio); (2) inferred from leaf/tree-ring stable-carbon-isotope discrimination Δ¹³C via the simplified Farquhar model **C_i/C_a = (Δ − a)/(b − a)**, with a = 4.4‰ (diffusional fractionation) and b = 27‰ (Rubisco fractionation) — e.g. a C3 leaf discrimination of Δ ≈ 20‰ gives C_i/C_a = (20 − 4.4)/(27 − 4.4) = 15.6/22.6 = **0.69** ([Keller 2017](https://doi.org/10.5194/bg-14-2641-2017)). The key photosynthetic-pathway contrast — and the reason the default warrants scrutiny — is that **C3 plants operate at C_i/C_a ≈ 0.6–0.9 while C4 plants operate at ≈ 0.3–0.5** ([Morison & Gifford 1983](https://doi.org/10.1104/pp.71.4.789)). For a **C3** herbaceous/tundra PFT the EcoSIM default of **0.45 lies in the C4 range and is therefore too low**.

**Reported values.**

| Value (as reported) | Units as reported | Converted to FCO2 units | PFT / species | Site / conditions | Citation |
|---|---|---|---|---|---|
| C_i/C_a ≈ 0.8–0.9 at low VPD, declining to ≈ **0.7** at high VPD (C3); ≈ 0.5 at high VPD (C4) | dimensionless ratio | 0.7–0.9 (C3, direct) | 2 C3 + 2 C4 grass species (graminoid) | Controlled gas exchange, VPD gradient | [Morison & Gifford 1983](https://doi.org/10.1104/pp.71.4.789) |
| Global C3-leaf c_i/c_a compilation ≈ 0.7–0.8; near-constant over 20th century | dimensionless ratio | ~0.7–0.8 (C3, direct/isotope) | C3 trees (global) | Global leaf-δ¹³C + tree-ring compilation | [Keller 2017](https://doi.org/10.5194/bg-14-2641-2017) |
| Optimal-stomatal g1 parameter implies a near-constant C_i/C_a set-point that rises with growth temperature (cold climates → moderate C_i/C_a) | dimensionless (g1 in kPa^0.5) | supports C3 C_i/C_a ~0.6–0.8 | Trees, tropical→boreal PFTs | Global synthesis | [Medlyn 2010](https://doi.org/10.1111/j.1365-2486.2010.02375.x) |

**Derived bound.** **[0.60, 0.85], central 0.75 (decision: literature).** Directly-measured C3 grass values span ~0.7 (high VPD) to ~0.9 (low VPD) ([Morison & Gifford 1983](https://doi.org/10.1104/pp.71.4.789)), and global C3 compilations centre on ~0.7–0.8 ([Keller 2017](https://doi.org/10.5194/bg-14-2641-2017)); the CONTEXT guidance (C3 typically 0.6–0.8) agrees. Arctic/tundra plants experience low VPD and cool temperatures (favouring the higher-C_i/C_a end) but also nutrient limitation on carboxylation (which can pull C_i/C_a down), so a central set-point of **0.75** with a window of **0.60–0.85** captures the C3 herbaceous/tundra range without straying into the C4 band. **The EcoSIM default of 0.45 sits well below this literature-supported C3 window and appears mis-set for a C3 PFT** — it corresponds to C4 stomatal behaviour ([Morison & Gifford 1983](https://doi.org/10.1104/pp.71.4.789)); raising it into [0.60, 0.85] is recommended. Note: no arctic-specific direct C_i/C_a measurement was found for graminoids/sedges, so the bound rests on C3-grass and global-C3 measurements plus the optimal-stomatal framework; it is flagged as temperate/global-C3-derived rather than tundra-endemic. `bound_source: literature (Morison & Gifford 1983; Keller 2017)`.

### References (this group)

- Bartlett MK, Scoffoni C, Sack L (2012). The determinants of leaf turgor loss point and prediction of drought tolerance of species and biomes: a global meta-analysis. *Ecology Letters* 15(5):393–405. [https://doi.org/10.1111/j.1461-0248.2012.01751.x](https://doi.org/10.1111/j.1461-0248.2012.01751.x)
- Griffin-Nolan RJ, Ocheltree TW, Mueller KE, Blumenthal DM, Kray JA, Knapp AK (2019). Extending the osmometer method for assessing drought tolerance in herbaceous species. *Oecologia* 189(2):353–363. [https://doi.org/10.1007/s00442-019-04336-w](https://doi.org/10.1007/s00442-019-04336-w)
- Huang R, Wu H, Sun J, Di N, Duan J, Xi B, Li X, Jansen S, Choat B, Tissue DT (2025). Hydraulic traits are coordinated but decoupled from carbon traits in herbaceous species. *Functional Ecology* 39(5):1302–1317. [https://doi.org/10.1111/1365-2435.70036](https://doi.org/10.1111/1365-2435.70036)
- Kunert N, Tomaskova I (2020). Leaf turgor loss point at full hydration for 41 native and introduced tree and shrub species from Central Europe. *Journal of Plant Ecology* 13(6):754–756. [https://doi.org/10.1093/jpe/rtaa059](https://doi.org/10.1093/jpe/rtaa059)
- Tordoni E, Petruzzellis F, Di Bonaventura A, Pavanetto N, Tomasella M, Nardini A, Boscutti F, Martini F, Bacaro G (2022). Projections of leaf turgor loss point shifts under future climate change scenarios. *Global Change Biology* 28(22):6640–6652. [https://doi.org/10.1111/gcb.16400](https://doi.org/10.1111/gcb.16400)
- Morison JIL, Gifford RM (1983). Stomatal Sensitivity to Carbon Dioxide and Humidity. *Plant Physiology* 71(4):789–796. [https://doi.org/10.1104/pp.71.4.789](https://doi.org/10.1104/pp.71.4.789)
- Keller KM, Lienert S, Bozbiyik A, Stocker TF, Churakova (Sidorova) OV, Frank DC, Klesse S, Koven CD, Leuenberger M, Riley WJ, Saurer M, Siegwolf R, Weigt RB, Joos F (2017). 20th century changes in carbon isotopes and water-use efficiency: tree-ring-based evaluation of the CLM4.5 and LPX-Bern models. *Biogeosciences* 14(10):2641–2673. [https://doi.org/10.5194/bg-14-2641-2017](https://doi.org/10.5194/bg-14-2641-2017)
- Medlyn BE, Duursma RA, Eamus D, Ellsworth DS, Prentice IC, Barton CVM, Crous KY, De Angelis P, Freeman M, Wingate L (2010/2011). Reconciling the optimal and empirical approaches to modelling stomatal conductance. *Global Change Biology* 17(6):2134–2144. [https://doi.org/10.1111/j.1365-2486.2010.02375.x](https://doi.org/10.1111/j.1365-2486.2010.02375.x)

---

## Enzyme & uptake kinetics (Km)

This group covers two half-saturation (Michaelis) constants that set the substrate affinity of two very different reactions in EcoSIM: the carboxylation of CO2 by Rubisco (`XKCO2`) and the acquisition of orthophosphate by roots (`UPKMPO`). Both are expressed by the model in **aqueous micromolar (uM)**, so the central methodological task is to (a) find *measured* affinities and (b) convert every reported value onto an aqueous-uM basis, being explicit about the gas-phase-vs-liquid-phase distinction flagged in the task context.

---

### XKCO2 — Michaelis constant Kc for Rubisco CO2 carboxylation

**Physical meaning & units.** `XKCO2` is the concentration of CO2 at which the Rubisco carboxylase reaction runs at half its maximum rate (Vcmax/2). In the Farquhar–von Caemmerer–Berry biochemistry that EcoSIM's C-fixation term follows, it is the affinity of Rubisco for its gaseous substrate CO2. EcoSIM states it as **aqueous CO2 concentration in uM** (i.e. the dissolved-CO2 concentration at the chloroplast/stroma, not a partial pressure). Current default: **40**.

**How the literature maps.** Rubisco kinetics are reported two incompatible ways, and conflating them is the classic error the task warns about:

1. **Gas / partial-pressure form** (ubar, Pa, or umol mol⁻¹): the CO2 *partial pressure* in equilibrium with the reaction. This is the convention of the widely used in-vivo parameterization of [Bernacchi et al. (2001)](https://doi.org/10.1111/j.1365-3040.2001.00668.x), whose Kc(25 °C) = **39.97 Pa** (≈ 400 ubar).
2. **Aqueous form** (uM, liquid phase): the *dissolved* CO2 concentration at the active site — the quantity EcoSIM's parameter actually is.

To place the partial-pressure value on EcoSIM's aqueous axis, apply Henry's law at 25 °C with a CO2 solubility of K_H ≈ 0.034 mol L⁻¹ atm⁻¹:

> [CO2]aq = pCO2 × K_H = (39.97 Pa ÷ 101 325 Pa atm⁻¹) × 0.034 mol L⁻¹ atm⁻¹
> = 3.945×10⁻⁴ atm × 0.034 mol L⁻¹ atm⁻¹ = 1.34×10⁻⁵ mol L⁻¹ ≈ **13.6 uM**.

So the Bernacchi in-vivo standard, expressed the way EcoSIM wants it, is ≈ 13–14 uM aqueous CO2. Independently, the two large in-vitro compilations report Kc *already in liquid-phase uM*: [Hermida-Carrera et al. (2016)](https://doi.org/10.1104/pp.16.01846) tabulate cool-season C3 cereals (wheat 11.3 ± 0.4, oat 10.8 ± 0.9, barley 9.0 ± 0.6 uM), and the standardized compendium of [Galmés et al. (2016)](https://doi.org/10.1093/jxb/erw267) gives an all-C3 mean of 20.0 ± 0.8 uM (cool-climate C3 subset 18.8 ± 1.2 uM; species range ≈ 11.9–25.6 uM). The 28-species survey of [Galmés et al. (2014)](https://doi.org/10.1111/pce.12335) corroborates that C3 Kc varies severalfold with habitat but stays within this liquid-phase band, and [Prins et al. (2016)](https://doi.org/10.1093/jxb/erv574) confirms that Kc in Triticeae roughly doubles between 25 °C and 35 °C — relevant because an arctic/tundra C3 canopy operates *cold*, which pushes the effective Kc toward the low end of the measured range rather than the high end.

**Reasoning chain to the bound.** Every independent aqueous estimate for C3 higher plants lands between ≈ 9 uM (cool-season cereals, in vitro) and ≈ 26 uM (warm-adapted C3, standardized compendium), with the in-vivo modeling standard at ≈ 13.6 uM. The arctic-relevant subset (cool-climate C3, cold operating temperature) sits at the *lower* half of that band. The EcoSIM default of 40 is ≈ 2× the C3 in-vitro mean and ≈ 3× the in-vivo aqueous value. Notably, 40 is almost exactly Bernacchi's **39.97 Pa** partial-pressure value — a strong tell that the default is a gas-phase number that was carried over as if it were aqueous uM; converted properly it should be ≈ 13.6 uM, not 40. Units map cleanly to uM, so this is a `literature` decision, with the caveat that the model developer should confirm the phase convention before adopting the tighter range.

**Reported values**

| Value | Units as reported | Converted to EcoSIM units (uM aq. CO2, 25 °C) | PFT/species | Site/context | Citation |
|---|---|---|---|---|---|
| 39.97 | Pa (partial pressure) | ≈ 13.6 uM (Henry's law, K_H=0.034) | Tobacco, in vivo (C3 standard) | Gas-exchange parameterization | [Bernacchi 2001](https://doi.org/10.1111/j.1365-3040.2001.00668.x) |
| 11.3 ± 0.4 | uM (liquid phase) | 11.3 | Wheat (Triticum aestivum), C3 | In-vitro crop survey | [Hermida-Carrera 2016](https://doi.org/10.1104/pp.16.01846) |
| 10.8 ± 0.9 | uM (liquid phase) | 10.8 | Oat (Avena sativa), C3 cool-season | In-vitro crop survey | [Hermida-Carrera 2016](https://doi.org/10.1104/pp.16.01846) |
| 9.0 ± 0.6 | uM (liquid phase) | 9.0 | Barley (Hordeum vulgare), C3 cool-season | In-vitro crop survey | [Hermida-Carrera 2016](https://doi.org/10.1104/pp.16.01846) |
| 20.0 ± 0.8 | uM (liquid phase, standardized) | 20.0 | All C3 higher plants (mean) | Compendium, 49 species | [Galmés 2016](https://doi.org/10.1093/jxb/erw267) |
| 18.8 ± 1.2 | uM (liquid phase, standardized) | 18.8 | Cool-climate C3 subset | Compendium | [Galmés 2016](https://doi.org/10.1093/jxb/erw267) |
| ≈ 11.9–25.6 | uM (liquid phase, standardized) | 11.9–25.6 | C3 species range | Compendium | [Galmés 2016](https://doi.org/10.1093/jxb/erw267) |

**Derived bound.** **[9, 26] uM, central ≈ 15 uM.** Spans the measured aqueous Kc for C3 higher plants (in-vitro cool-season cereals ≈ 9–11, in-vivo standard ≈ 13.6, standardized compendium ≈ 12–26), weighted toward the cool-climate/cold-operating end appropriate to a tundra C3 canopy. The current default of 40 falls outside this range and most likely reflects a gas-phase (Pa/ubar) value mis-carried as aqueous uM.

---

### UPKMPO — half-saturation constant Km for root H2PO4/phosphate uptake

**Physical meaning & units.** `UPKMPO` is the soil-solution orthophosphate concentration at which root Pi influx reaches half of its maximum (Vmax/2) — the affinity of the root's high-affinity phosphate transport system for H2PO4⁻ at the root surface. Units: **uM**. Current default: **0.05** (i.e. 50 nM).

**How the literature maps.** The measurable quantity is the apparent Km from Michaelis–Menten fits to Pi-depletion or ³²P-influx experiments on intact roots or excised root systems, and Km from heterologously expressed high-affinity Pi transporters. All are reported directly in uM (or umol L⁻¹), so **no unit conversion is needed** — the mapping is one-to-one. The interpretive caveat is the *concentration basis*: a whole-root depletion Km integrates transporter affinity, root architecture and diffusion, whereas a single-transporter Km (yeast/oocyte expression) is the molecular affinity; a root-surface Michaelis–Menten uptake term like EcoSIM's corresponds most closely to the whole-root apparent Km.

The measured evidence, arctic-first:

- **Arctic/boreal.** [Chapin (1974)](https://doi.org/10.2307/1935449) established along a latitudinal gradient that cold-adapted (tundra) roots have *higher* affinity (lower apparent Km) for phosphate than warm-adapted counterparts, and that apparent Km *rises* with measurement temperature — i.e. arctic roots operating cold sit toward the low-Km end. The companion Barrow-tundra chapter [Chapin (1978)](https://doi.org/10.1007/978-1-4612-6307-4_21) documents the same for Barrow sedges/grasses. Counter to that, the actual arctic/boreal species cloudberry (*Rubus chamaemorus*) shows *distinctively high* Km: [Zhou et al. (2013)](https://doi.org/10.1080/01904167.2013.780610) resolve P uptake into a two-component system with a low-affinity component Km of **50–330 uM** and note that cloudberry Km values exceeded those reported for most other species. The arctic signal is therefore genuinely mixed.
- **Whole-root (woody).** [Kavka & Polle (2016)](https://doi.org/10.1186/s12870-016-0892-3) measured Pi uptake Km of the intact poplar (*Populus × canescens*) root system at **19.9 ± 8.1 uM** (low-P plants) and **25.9 ± 9.9 uM** (medium-P plants).
- **Molecular high-affinity transporter.** [Liu et al. (2014)](https://doi.org/10.1186/1471-2229-14-18) report the chrysanthemum high-affinity transporter CmPT1 with Km = **35.2 uM** (yeast complementation); Arabidopsis PHT1-family high-affinity systems reach the low-uM end (≈ 1.5–3 uM under P starvation).
- **Grass/graminoid.** [McNaughton & Chapin (1985)](https://doi.org/10.2307/1938024) grew C4 Serengeti graminoids at 10 and 100 umol L⁻¹ P and found defoliation raised uptake rate chiefly by *lowering* Km — confirming that graminoid Pi Km is a plastic, low-uM-scale affinity, though they did not tabulate a single value.

**Reasoning chain to the bound.** Across intact-root and transporter studies the measured phosphate-uptake Km spans roughly **1.5 uM** (molecular high-affinity, P-starved) to **35 uM** (whole-root/transporter, mesic), with well-constrained whole-root values clustering at ≈ 20–26 uM and one arctic species (cloudberry) running higher still. The EcoSIM default of **0.05 uM is 1–3 orders of magnitude below every validated measurement** — below even the highest-affinity molecular transporter. Units map exactly (uM→uM) and multiple measured, validated values exist, so this is a `literature` decision. The strong caveat: 0.05 uM would keep roots effectively saturated at all realistic soil-solution P concentrations, which contradicts the measured kinetics; if the model deliberately uses a root-surface (post-depletion-zone) concentration basis this could partly explain the gap, but even so the default sits far outside the physiological affinity range and should be revisited.

**Reported values**

| Value | Units as reported | Converted to EcoSIM units (uM) | PFT/species | Site/context | Citation |
|---|---|---|---|---|---|
| 19.9 ± 8.1 | uM | 19.9 | Poplar (Populus × canescens), tree | Whole-root system, low-P | [Kavka & Polle 2016](https://doi.org/10.1186/s12870-016-0892-3) |
| 25.9 ± 9.9 | uM | 25.9 | Poplar, tree | Whole-root system, medium-P | [Kavka & Polle 2016](https://doi.org/10.1186/s12870-016-0892-3) |
| 35.2 | uM | 35.2 | Chrysanthemum CmPT1 transporter | High-affinity transporter, yeast | [Liu et al. 2014](https://doi.org/10.1186/1471-2229-14-18) |
| 50–330 | uM (low-affinity component) | 50–330 | Cloudberry (Rubus chamaemorus), arctic/boreal forb | Two-component uptake kinetics | [Zhou et al. 2013](https://doi.org/10.1080/01904167.2013.780610) |
| Cold → lower Km (higher affinity); Km rises with T | apparent Km, umol L⁻¹ (qualitative) | low-uM scale | Tundra sedges/grasses vs warm ecotypes | Latitudinal gradient, Barrow AK | [Chapin 1974](https://doi.org/10.2307/1935449); [Chapin 1978](https://doi.org/10.1007/978-1-4612-6307-4_21) |
| Defoliation lowers Km | apparent Km, umol L⁻¹ (qualitative) | low-uM scale | C4 graminoids (Kyllinga, Digitaria) | Serengeti, 10 & 100 uM P | [McNaughton & Chapin 1985](https://doi.org/10.2307/1938024) |

**Derived bound.** **[1.5, 35] uM, central ≈ 10 uM.** Encompasses molecular high-affinity systems (≈ 1.5–3 uM), whole-root apparent Km (≈ 20–26 uM), and mesic transporter Km (≈ 35 uM); arctic evidence is mixed (Chapin: cold → lower Km; cloudberry: notably high Km), so the interval is kept broad. The current default of 0.05 uM is ≈ 30–700× below all measured affinities and is flagged for re-examination — either it encodes a non-standard concentration basis or it is an unphysiological placeholder.

---

### References (this group)

1. Bernacchi C.J., Singsaas E.L., Pimentel C., Portis A.R. Jr, Long S.P. (2001) Improved temperature response functions for models of Rubisco-limited photosynthesis. *Plant, Cell & Environment* 24(2), 253–259. https://doi.org/10.1111/j.1365-3040.2001.00668.x
2. Galmés J., Kapralov M.V., Andralojc P.J., Conesa M.À., Keys A.J., Parry M.A.J., Flexas J. (2014) Expanding knowledge of the Rubisco kinetics variability in plant species: environmental and evolutionary trends. *Plant, Cell & Environment* 37(9), 1989–2001. https://doi.org/10.1111/pce.12335
3. Prins A., Orr D.J., Andralojc P.J., Reynolds M.P., Carmo-Silva E., Parry M.A.J. (2016) Rubisco catalytic properties of wild and domesticated relatives provide scope for improving wheat photosynthesis. *Journal of Experimental Botany* 67(6), 1827–1838. https://doi.org/10.1093/jxb/erv574
4. Hermida-Carrera C., Kapralov M.V., Galmés J. (2016) Rubisco catalytic properties and temperature response in crops. *Plant Physiology* 171(4), 2549–2561. https://doi.org/10.1104/pp.16.01846
5. Galmés J., Hermida-Carrera C., Laanisto L., Niinemets Ü. (2016) A compendium of temperature responses of Rubisco kinetic traits: variability among and within photosynthetic groups and impacts on photosynthesis modeling. *Journal of Experimental Botany* 67(17), 5067–5091. https://doi.org/10.1093/jxb/erw267
6. Chapin F.S. III (1974) Morphological and physiological mechanisms of temperature compensation in phosphate absorption along a latitudinal gradient. *Ecology* 55(6), 1180–1198. https://doi.org/10.2307/1935449
7. Chapin F.S. III (1978) Phosphate uptake and nutrient utilization by Barrow tundra vegetation. *Ecological Studies*, 483–507. https://doi.org/10.1007/978-1-4612-6307-4_21
8. McNaughton S.J., Chapin F.S. III (1985) Effects of phosphorus nutrition and defoliation on C4 graminoids from the Serengeti Plains. *Ecology* 66(5), 1617–1629. https://doi.org/10.2307/1938024
9. Zhou J., Desjardins Y., Lapointe L. (2013) Nutrient uptake kinetics of cloudberry. *Journal of Plant Nutrition* 36(8), 1219–1233. https://doi.org/10.1080/01904167.2013.780610
10. Kavka M., Polle A. (2016) Phosphate uptake kinetics and tissue-specific transporter expression profiles in poplar (Populus × canescens) at different phosphorus availabilities. *BMC Plant Biology* 16, 206. https://doi.org/10.1186/s12870-016-0892-3
11. Liu P., Chen S., Song A., Zhao S., Fang W., Guan Z., Liao Y., Jiang J., Chen F. (2014) A putative high affinity phosphate transporter, CmPT1, enhances tolerance to Pi deficiency of chrysanthemum. *BMC Plant Biology* 14, 18. https://doi.org/10.1186/1471-2229-14-18

---

## Source-trace corrections (2026-07-12) — the flagged params, resolved in the Fortran

The 6 parameters flagged above (default outside the measured range) were traced in the EcoSIM
source (6-agent fan-out) — the netCDF `long_name`s proved unreliable; the **usage in the equations**
is the truth (A2MC Calibration Rule #2). Findings:

| Param | long_name | Source-verified truth | Resolution |
|---|---|---|---|
| **CNLF** | leaf N:C | **MAXIMUM** N:C ceiling (`rNCLeaf_pft`, "maximum leaf N:C"); realized = `CNLF·(0.33+0.67·CNPG)` (PlantBranchMod.F90:371) | Measured range is the model *output*, not this input. Calibrate as a ceiling `[0.08, 0.20]` gN/gC; do NOT clamp to `[0.02,0.08]`. |
| **CPLF** | leaf P:C | **MAXIMUM** P:C ceiling (`rPCLeaf_pft`); realized = `CPLF·(0.33..1)` (PlantBranchMod.F90:380) | Set the ceiling so `0.33·CPLF..CPLF` overlaps the measured `[0.0015,0.006]` → `[0.005, 0.02]` gP/gC. |
| **FCO2** | "intercellular" | genuinely **Ci:Ca ratio** `[-]`, used directly (`LeafIntracellularCO2 = FCO2·CanopyGasCO2`, StomatesMod.F90:260) | Name/def correct; default 0.45 genuinely C4-low. Adopt C3 lit `[0.6, 0.85]`. |
| **SLA1** | SLA (m²·gC⁻¹) | **power-law coefficient** (`SLA1·dMC^SLA2`, SLA2≈−0.33), true units **m²·gC⁻⁰·⁶⁷** | Not bulk SLA — measured SLA does not map. Keep provisional coefficient range `[0.00167, 0.005]`. |
| **UPKMPO** | Km, **µM** | Km in **g P m⁻³** (`KmPO4Root_pft`) — the netCDF `units=uM` attribute is **WRONG**; 0.05 g P m⁻³ = 1.6 µM | Convert the lit: `[1.5,35] µM → [0.046, 1.08]` g P m⁻³ (the model's native units). |
| **XKCO2** | Km µM | genuinely aqueous Rubisco **Kc @25 °C, µM** (Arrhenius factor = 1 at 25 °C by construction) | Name/units/def all match. Lit applies; default 40 is on the high side → `[9, 40]` µM. |

**Takeaways for the modeler:** (1) `CNLF`/`CPLF` are *maxima*, evaluated against the model's
*realized* N:C/P:C output — a classic input-vs-output confusion the long_name invites. (2) `UPKMPO`'s
unit attribute in the input file is wrong (g P m⁻³, not µM) — worth fixing in the input. (3) `SLA1` is
an allometric coefficient, not a trait. The seed `calibration_notes` for these four were corrected to
the source truth. Evidence: `PlantInfoMod.F90` (reads), `PlantTraitDataType.F90`/`CanopyDataType.F90`
(declarations), `PlantBranchMod.F90`/`StomatesMod.F90` (usage).


---

# Remaining parameters — source-trace + literature/FRED (2026-07-12)

The 22 previously-provisional params, each source-traced to its true definition/units first (Rule #2),
then given a literature/FRED bound where the true quantity maps to a measurable, else kept provisional
with the source truth documented. More units traps found: VCMX's netCDF/CDL units AND its API comment
are both wrong (true: µmol CO2 (gC rubisco)⁻¹ s⁻¹); RSRR/RSRA carry 3 conflicting in-source unit
annotations; XDL = −1 is a disabled sentinel (not sweepable).

## Root morphology

### RRAD1M
**Source-verified definition & units.** Internal var `Root1stMaxRadius_pft(ipltroot,...)`, read from the PFT file at `f90src/IOutils/PlantInfoMod.F90:584`; echoed as `writefixl(...,'RRAD1M','Maximum radius of young primary roots [m]',...)` at `PlantInfoMod.F90:1181`. This is the **radius (not diameter) of the primary / first-order axial (transport) root, in metres** — proven by the cross-section usage `Root1stXSecArea_pft = PICON*Root1stMaxRadius1_pft**2` (π·r²) at `Plant_bgc/InitPlantMod.F90:578` and `Ecosim_mods/StartqMod.F90:477`, and specific-root-length `Root1stSpecLen_pft = FineRootVolPerMassC_pft/(PICON*Root1stMaxRadius_pft**2)` at `InitPlantMod.F90:572`. It is a **reference/minimum** radius, not a hard cap: the realized layer radius `Root1stRadius_pvr = AMAX1(Root1stMaxRadius1_pft, (1+PSI/EMODR)*Root1stMaxRadius_pft, coarse-volume estimate)` at `Plant_bgc/RootMod.F90:396` lets primary roots thicken via secondary growth. (Note: some inline `_pft` comments at `InitPlantMod.F90:484-486` mislabel it "diameter" — the equations show radius; netCDF `m` is correct.) Default 0.0002 m = 0.2 mm radius (0.4 mm diameter).
**Bound.** Maps to a measurable: the radius of coarser first-order/transport (axial) roots. FRED ([Iversen et al. 2017, *New Phytologist* 215:15-26](https://doi.org/10.1111/nph.14486); roots.ornl.gov) fine/first-order root **diameters** span ~0.1-1.0 mm; the coarser transport end → radius ≈ 1e-4 to 5e-4 m. Keep default 2e-4 as central; bound **1e-4 to 5e-4 m** (radius). Decision: **literature (FRED)**.

### RRAD2M
**Source-verified definition & units.** Internal var `Root2ndMaxRadius_pft(ipltroot,...)`, read at `f90src/IOutils/PlantInfoMod.F90:585`; echoed as `writefixl(...,'RRAD2M','Maximum radius of fine roots [m]',...)` at `PlantInfoMod.F90:1183`. **Radius (not diameter) of the secondary / absorptive fine root, in metres** — cross-section `Root2ndXSecArea_pft = PICON*Root2ndMaxRadius1_pft**2` (π·r²) at `InitPlantMod.F90:579` / `StartqMod.F90:478`. This is the radius actually used for nutrient/water uptake geometry: `FineRootRadius_rvr(N,L) = Root2ndMaxRadius_pft(N,NZ)` at `Plant_bgc/UptakesMod.F90:523`, then consumed as the uptake `FineRootRadius` path-length term in `Plant_bgc/NutUptakeMod.F90:455,527,709` (`PATHL = min(PathLen, FineRootRadius + sqrt(2·D·t))`). Realized fine-root radius `Root2ndRadius_rpvr = AMAX1(Root2ndMaxRadius1_pft, (1+PSI/EMODR)*Root2ndMaxRadius_pft)` at `RootMod.F90:415` ≈ RRAD2M (fine roots do not thicken much). Default 0.0001 m = 0.1 mm radius (0.2 mm diameter).
**Bound.** Maps to a measurable: absorptive fine-root radius. FRED ([Iversen et al. 2017](https://doi.org/10.1111/nph.14486)) absorptive first-order diameters ~0.1-0.5 mm; arctic graminoids/sedges are among the finest (~0.1-0.2 mm diameter). Radius → **5e-5 to 3e-4 m**, central 1e-4 (consistent with the guidance envelope 5e-5..5e-4 m). Decision: **literature (FRED)**.

### CNSTK
**Source-verified definition & units.** Internal var `rNCStalk_pft(NZ,...)`, read at `f90src/IOutils/PlantInfoMod.F90:628`; declared `stalk N:C ratio, [gN gC-1]` at `APIData/PlantAPIData.F90:503`; echoed `'CNSTK','Plant stalk NC mass ratio [gN (gC)-1]'` at `PlantInfoMod.F90:1315`. **Realized N:C stoichiometry of the stalk (culm/sapwood) structural pool, gN gC-1 — NOT a maximum.** It is applied as a direct multiplier converting stalk C growth to N demand: `Growth_brch(ielmn,ibrch_stalk) = Growth_brch(ielmc,ibrch_stalk)*rNCStalk_pft(NZ)` at `Plant_bgc/PlantBranchMod.F90:374`; N growth-cost `+PART(ibrch_stalk)*StalkBiomGrowthYld_pft*rNCStalk_pft` at `:501`; and sapwood N mass `SapwoodBiomassC_brch*rNCStalk_pft` at `:522`. This contrasts with the CNLF trap (leaf `rNCLeaf`/`CNLFB` enters through the modulated form `fNCLFW = CNLFB*(ZPLFM+ZPLFD*CNPG)` at `:371`); CNSTK has no such modulation — it is the tissue's actual N:C. Default 0.1 gN gC-1 (C:N = 10).
**Bound.** Maps to a measurable: stem/culm/sapwood N:C. Global plant stoichiometry ([Kerkhoff et al. 2005, *Global Ecology and Biogeography* 14:585-598](https://doi.org/10.1111/j.1466-822x.2005.00187.x)) gives stem N far below leaf N: woody sapwood/stem N:C ≈ 0.003-0.01 gN gC-1 (C:N 100-350); herbaceous graminoid culms higher, ≈ 0.01-0.05 (C:N 20-100). Bound **0.005 to 0.05 gN gC-1**, central ~0.02. Note: EcoSIM's "stalk" is a pooled compartment (culm + sapwood) spanning graminoid→woody PFTs, so the appropriate value is functional-type dependent; the **default 0.1 sits above the whole-tissue literature range** and is flagged as likely too N-rich for a structural-stalk pool. Decision: **literature**.

## Photosynthesis (rubisco/chl)

**Cross-cutting source finding (the units trap).** The netCDF `units` attributes are the *wrong* ones. The CDL declares VCMX/VOMX/ETMX as `umol C|O|e- g-1 s-1` (a bare per-gram basis) at `input_data/ecosim_pftpar_20260303.nc.cdl:64,67,88`, and the `PlantAPIData.F90` pointer comments carry a stale **`h-1`** (per-hour) unit (`f90src/APIData/PlantAPIData.F90:98,104,105`). Both are contradicted by the model's own runtime label writer (`writefixl`) and by the equation trace:

- `PlantInfoMod.F90:1051` writes VCMX as **`[umol CO2 (gC rubisco)-1 s-1]`** (carbon mass of rubisco, per *second*).
- The carboxylation rate is built as `VcMaxRubiscoRef_node = VmaxSpecRubCarboxyRef_pft(NZ) * MesophyllRubiscoSurfDensity` (`f90src/Plant_bgc/StomatesMod.F90:433`), where `MesophyllRubiscoSurfDensity = LeafRubisco2Protein_pft * ProteinCLeafAreaDensity` (`:414`), with the comment stating `[gC rubisco (gC protein)-1] * [gC protein m-2 leaf]` (`:409`). The product is a **per-second, area-based** `[umol m-2 s-1]` rate (output units at `:400-401`).

So the true basis is **per gram CARBON of enzyme, per second** — NOT per g leaf, not per g protein-mass, not per hour. A user who took the CDL attribute literally would be off by the rubisco carbon fraction (~1.9×) and by 3600× on time.

**Default-value discrepancy.** The defaults quoted in the task do not match the shipped parameter file. Actual per-PFT CDL defaults: `VCMX = 45,45,35,65…` (`:440`), `VOMX = 9.5,10,12…` (`:446`), `RUBP = 0.125,0.2,0.1…` (`:478`), `ETMX = 405,300,1000…` (`:492`). The task's RUBP=0.025 in particular is ~5–8× below the file; bounds below are anchored to the file values.

### VCMX
**Source-verified definition & units.** Internal var `VmaxSpecRubCarboxyRef_pft` (loaded at `f90src/IOutils/PlantInfoMod.F90:535`; runtime label `PlantInfoMod.F90:1051`). Saturated **specific Rubisco carboxylation rate at 25 °C, per gram carbon of Rubisco**: `umol CO2 (gC rubisco)-1 s-1`. Usage: `VcMaxRubiscoRef_node = VmaxSpecRubCarboxyRef_pft * MesophyllRubiscoSurfDensity` (`StomatesMod.F90:433`), i.e. it is the mass-specific turnover that, multiplied by rubisco areal density, yields area-based Vcmax. This is a per-active-site turnover expressed per unit enzyme mass — a genuine measurable (Rubisco *kcat*).

**Bound.** Maps to Rubisco carboxylase *kcat*. [Sage 2002](https://doi.org/10.1093/jexbot/53.369.609) reports C3 Rubisco kcat at 25 °C ≈ **2.5–4.0 mol CO2 mol-site⁻¹ s⁻¹** (median ~3.3). Convert to the model's per-gC basis: Rubisco holoenzyme ~550 kDa with 8 catalytic sites → sites per g protein = 8/550000 = 1.455×10⁻⁵ mol g⁻¹; per g protein rate = kcat × 14.5 µmol s⁻¹ g⁻¹ (kcat 3.3 → ~48 µmol s⁻¹ g⁻¹ ≈ 2.9 µmol min⁻¹ mg⁻¹, matching the textbook specific activity). Divide by the protein carbon fraction (~0.53) → per gC = kcat × 27.4 µmol (gC)⁻¹ s⁻¹. kcat 2.0–4.5 → **VCMX ≈ 55–125**, central ~90. The file defaults (45–65) sit at/below this (implied kcat ~1.6–2.4), i.e. conservative/low-activation but same order. **Bound: 50–125, central 90 µmol CO2 (gC rubisco)⁻¹ s⁻¹** — carrying the stated MW/site/C-fraction conversion assumptions.

### VOMX
**Source-verified definition & units.** Internal var `VmaxRubOxyRef_pft` (`PlantInfoMod.F90:536`; label `:1053`). Saturated **specific Rubisco oxygenation rate at 25 °C, per gram carbon of Rubisco**: `umol O2 (gC rubisco)-1 s-1`. Usage `VoMaxRubiscoRef_node = VmaxRubOxyRef_pft * MesophyllRubiscoSurfDensity` (`StomatesMod.F90:434`), feeding the CO2 compensation point / photorespiration term (`:436-437`).

**Bound — keep provisional.** The true quantity (oxygenase turnover per gC rubisco) is real, but oxygenase *kcat* is rarely measured directly; it is normally *derived* from carboxylase kcat and the Sc/o specificity factor. The file pins VOMX to VCMX at a ratio of 9.5/45 ≈ **0.21** (consistent with the FvCB Vomax/Vcmax ≈ 0.21–0.27). Forcing an absolute per-gC number would require a doubly-indirect chain (ratio × kcat_c × mass conversion), so the honest call is `keep_provisional`: **treat VOMX as ~0.21–0.27 × VCMX** rather than an independently measured value, and document the true def above.

### ETMX
**Source-verified definition & units.** Internal var `SpecLeafChlAct_pft` (`PlantInfoMod.F90:544`; label `:1061`). **Specific chlorophyll (electron-transport) activity at 25 °C, per gram carbon of chlorophyll**: `umol e- (gC chl)-1 s-1`. Usage `ElectronTransptJmaxRef_node = SpecLeafChlAct_pft * MesophyllChlDensity` (`StomatesMod.F90:453`), where `MesophyllChlDensity = LeafProtein2Chl_pft * ProteinCLeafAreaDensity / 3.5` (`:415`); the product is the reference light-saturated electron-transport (Jmax-analog) rate `[umol m-2 s-1]`.

**Bound — keep provisional.** This is a reference *scaling constant* mapping mesophyll chlorophyll-carbon density to Jmax, expressed on a **carbon-mass-of-chlorophyll** basis that has no standard literature counterpart (chlorophyll is reported per mol or per g pigment, not per gC; chlorophyll-a is C55H72MgN4O5, MW ~893, C-fraction ~0.74). Electron transport per unit chlorophyll varies widely with light acclimation and is normally captured as Jmax:Vcmax (~1.6–2.0) or Jmax per chlorophyll, not as a per-gC turnover. `keep_provisional`: document the true def/units; if a bound is later needed, anchor it through the Jmax:Vcmax ratio, not a direct pigment-activity measurement.

### RUBP
**Source-verified definition & units.** Internal var `LeafRubisco2Protein_pft` (`PlantInfoMod.F90:542`; label `:1059` = "Fraction of total leaf protein is Rubisco enzyme `[gC rubisco/(gC protein)]`"). Usage `MesophyllRubiscoC = LeafProteinC_node * LeafRubisco2Protein_pft` (`StomatesMod.F90:138`, `:414`) — it partitions the modeled leaf protein-C pool into the Rubisco-C fraction. **Dimensionless mass fraction, `gC rubisco (gC leaf protein)-1`** (the CDL `units="none"` is fine here; only its numeric default 0.025 in the task is wrong vs the file's 0.1–0.2). Because numerator and denominator are both protein carbon, the carbon fractions cancel, so this equals the ordinary mass fraction "Rubisco as a fraction of leaf protein."

**Bound.** Maps cleanly to a measurable. [Evans 1989](https://doi.org/10.1007/bf00377192) — the canonical N-partitioning reference — reports Rubisco holds ~**25 % of leaf N** (and ~50 % of *soluble* protein) in well-lit C3 leaves, with a broad across-species/light range. As a fraction of *total* leaf protein (the model's denominator, which includes structural/membrane protein), Rubisco is typically **~0.10–0.30**, lower in shade and graminoids, higher in high-light herbs. The file defaults (0.10–0.20) sit squarely in this envelope. **Bound: 0.08–0.35, central 0.20 (gC/gC)**; caveat that the model's "total leaf protein" pool scope must match the literature "total protein" denominator for the mapping to be exact.

## Root hydraulics & growth

All five parameters in this subsystem are EcoSIM-internal normalizing constants (resistivities), phenomenological phenology rates/thresholds, or a composite geometric frequency. None maps cleanly onto a directly-measured literature quantity, and the two hydraulic resistivities carry **three mutually contradictory unit annotations** in the source (proof the netCDF/attribute units are unreliable, per Calibration Rule #2). Decision for every param: `keep_provisional`, with the source-verified true definition documented and an order-of-magnitude working range for the sweep.

### RSRR
**Source-verified definition & units.** Internal var `RootRadialResist_pft` (read at `f90src/IOutils/PlantInfoMod.F90:590`). It is a per-PFT **root radial hydraulic resistivity** that is converted into an actual resistance by root/soil geometry — `f90src/Plant_bgc/UptakesMod.F90:1229`: `RootRadialResist_rvr = RootRadialResist_pft * VLMicP_vr/(Root2ndSurfArea*VLWatMicPM_vr)` (Grant 1998 eq. 31), producing a resistance the model treats as `[MPa h m-3]` for volumetric water uptake. **Units are unreliable in-source — three annotations disagree:** `[MPa h m-1]` at PlantInfoMod.F90:1208 (writefixl) and UptakesMod.F90:443; `[MPa h m-2]` at `f90src/Ecosim_datatype/RootDataType.F90:35`, `f90src/APIData/PlantAPIData.F90:335`, `f90src/Plant_bgc/InitPlantMod.F90:502`; and the **inverse (a conductivity) `m2 MPa-1 h-1`** at InitPlantMod.F90:524. The value is also not physically anchored: alternate hardcoded values appear for the ATS-coupled path (`400000` at UptakesMod.F90:468) and mycorrhizae (`1.0E+04` at StartqMod.F90:456). The dividing geometry factors (`Root2ndSurfArea` = root surface area per ground area ≈ m2 m-2 dimensionless; `VLMicP/VLWatMicPM` = volume ratio ≈ dimensionless) are model normalizations that make the raw value's units genuinely ambiguous.
**Bound.** keep_provisional: model-specific normalized resistivity with self-contradictory source units; does not map to a standard measured Lp/resistivity. Working range provisional ±1 order of magnitude around default (10000).

### RSRA
**Source-verified definition & units.** Internal var `RootAxialResist_pft` (read at `PlantInfoMod.F90:591`). Per-PFT **axial (Hagen–Poiseuille) resistivity per m root length**, defined at the secondary max radius `Root2ndMaxRadius_pft`; used at `UptakesMod.F90:1252-1254` to build primary/secondary/stalk axial resistances, e.g. `Root1stAxialResist_rvr = ... + RootAxialResist_pft*CumSoilThickMidL_vr/(FRAD1*Root1stXNumL_pvr)`. Dimensional check: `[MPa h m-4]·[m] = [MPa h m-3]`, matching the radial resistance it is summed with (UptakesMod.F90:1264) — so **`[MPa h m-4]` is internally consistent** (PlantInfoMod.F90:1210, UptakesMod.F90:442/1237, RootDataType.F90:36 all agree), but InitPlantMod.F90:524 again mislabels it `m2 MPa-1 h-1`. Not physically anchored: alternate values `500.0` (UptakesMod.F90:467, ATS path) and `1.0E+12` (StartqMod.F90:457, mycorrhizae). The `[MPa h m-4]` form (∝ N_vessel·r_vessel⁴ per Poiseuille, PlantInfoMod.F90:1216 comment) is model-specific and not a tabulated measurable.
**Bound.** keep_provisional: model-specific Poiseuille-form axial resistivity; units `[MPa h m-4]` internally consistent but not a directly measurable literature quantity. Working range provisional ±1 order of magnitude around default (4e9).

### RTFQ
**Source-verified definition & units.** Internal var `RootBranchFreq_pft` (read at `PlantInfoMod.F90:593`). Per the writefixl description (`PlantInfoMod.F90:1216`) it is the **square root of (fine-root branching frequency on 1st-order roots) × (root-hair frequency on fine roots), `[m-1]`** — i.e. a geometric-mean composite of two different frequencies, not a single measured branching density. Usage in `f90src/Plant_bgc/RootMod.F90:732-733`: `RTN2X = RootBranchFreq_pft*NumAxesPerPrimRoot_pft` (generates secondary/fine roots) and `RTN2Y = RootBranchFreq_pft*RTN2X` (generates root hairs). Because it is a √(f₁·f_hair) composite feeding a discrete root/hair-count generator, the raw value cannot be equated to a literature lateral-root branching density (branches cm⁻¹) even though such data exist.
**Bound.** keep_provisional: composite √(1st-order branching × root-hair frequency); model-specific geometric quantity, does not map cleanly to a single measured branching density. Working range provisional 100–2000 m⁻¹ around default (800).

### PR
**Source-verified definition & units.** Internal var `NonstCMinCon2InitRoot_pft` (read at `PlantInfoMod.F90:589`). writefixl (`PlantInfoMod.F90:1205-1206`) defines it as **"Nonstructural C concentration needed for root branching (gC nonst / gC structl)"** — a threshold on the nonstructural:**structural** C ratio (note: per structural C, not per total dry mass, so it differs from the usual NSC-as-%-dry-mass reporting). Used only as a discrete gate: `f90src/Plant_bgc/PlantPhenolMod.F90:356` initiates a new prime root axis when `CanopyNonstElmConc_pft(ielmc) > NonstCMinCon2InitRoot_pft` (and >0). This is a **reference/threshold** parameter for a discrete event, not the NSC pool itself. Root NSC concentrations are measurable (roughly 2–15% of dry mass in the literature, ≈0.02–0.18 gNSC/gStructural, which brackets the default 0.05 for plausibility) but the threshold value is a model calibration choice and its per-structural denominator is nonstandard.
**Bound.** keep_provisional (reference/threshold; nonstandard per-structural denominator). Root-NSC literature gives a plausibility bracket (~0.02–0.18) but not a validated threshold value; working range provisional 0.01–0.15 around default (0.05).

### PTSHT
**Source-verified definition & units.** Internal var `ShootRootNonstElmConduts_pft` (read at `PlantInfoMod.F90:592`). writefixl (`PlantInfoMod.F90:1212-1213`) defines it as a **"Rate scalar (<1) for equilibrating shoot–root nonstructural elemental concentrations, `[h-1]`"**. Usage `f90src/Plant_bgc/PlantNonstElmDynMod.F90:509`: `PTSHTR = ShootRootNonstElmConduts_pft * GrothPART2LeafPetole**0.167` (annuals) or `= ShootRootNonstElmConduts_pft` (line 511), i.e. a first-order exchange rate constant governing nonstructural C/N/P transfer between shoot and root pools. This is a phenomenological model rate constant with no direct measurable analogue.
**Bound.** keep_provisional: phenomenological shoot–root nonstructural exchange rate constant `[h-1]`, constrained only to be a rate scalar <1; no measurable literature counterpart. Working range provisional 0.01–0.5 around default (0.05).

## Nutrient uptake maxima & stomatal

### UPMXPO
**Source-verified definition & units** — Read into `VmaxPO4Root_pft(ipltroot,NZ,NY,NX)` at `f90src/IOutils/PlantInfoMod.F90:603` (per-PFT read) / `:1705` (trait table). Self-documenting write-out `f90src/IOutils/PlantInfoMod.F90:1241`: *"Maximum rate for root uptake of H2PO4 or H1PO4 [gP m-2 absorption area h-1]"*. USAGE: `f90src/Plant_bgc/NutUptakeMod.F90:1069` and `:1130` compute `UPMXP = VmaxPO4Root_pft(N,NZ) * RootSAreaPerPlant_pvr(N,L,NZ) * FSatNutTransporter * fTgrowRootP_vr * ...`, and the secondary HPO4 species pathway at `:908`/`:968` prepends a `0.1` factor. `RootSAreaPerPlant_pvr` is **root SURFACE area per plant [m2 plant-1]** (`f90src/Plant_bgc/RootMod.F90:425` = RootArea1stPP + RootArea2ndPP; declared `f90src/APIData/PlantAPIData.F90:351`). **True units: gP per m2 ROOT-SURFACE area per hour** — the `m-2` is absorption (root) area, NOT ground area (the netCDF/long_name "gP m-2 h-1" is ambiguous and misreads as ground-area). It is a **potential input maximum**, not realized uptake (scaled by transporter-protein saturation, root temperature, nonstructural-C and O2 limits downstream).
**Bound — keep provisional.** The quantity (biochemical Vmax of the root high-affinity Pi transport system) is measurable, but published root Pi-uptake Vmax is almost universally per root **mass** (µmol g⁻¹ root DW h⁻¹), whereas EcoSIM's basis is per root **surface area**. Converting requires a specific-root-area (m² g⁻¹) that itself spans ~an order of magnitude across fine-root diameter classes, so a literature number cannot be pinned without importing that uncertainty on top of the input-max-vs-realized gap. Recommend a provisional calibration range of ~default ÷5 … ×5 (0.0004–0.01 gP m⁻² h⁻¹) pending a site-specific SRA + per-area Pi-influx pairing.

### UPMXZH
**Source-verified definition & units** — Read into `VmaxNH4Root_pft(ipltroot,NZ,NY,NX)` at `f90src/IOutils/PlantInfoMod.F90:595` / table `:1698`. Write-out `f90src/IOutils/PlantInfoMod.F90:1229`: *"Maximum rate for root uptake of NH4 [gN m-2 absorption area h-1]"*. USAGE: `f90src/Plant_bgc/NutUptakeMod.F90:721`: `VmaxNH4Root_pvr(N,L,NZ) = VmaxNH4Root_pft(N,NZ) * RootSAreaPerPlant_pvr(N,L,NZ) * FSatNutTransporter * fTgrowRootP_vr * AMIN1(FCUP,FZUP)`. Same per-root-surface-area basis as UPMXPO (see RootMod.F90:425). **True units: gN per m2 ROOT-SURFACE area per hour**; a potential input max (the netCDF units "g m-2 h-1" both omit the element and hide that m-2 = root area).
**Bound — keep provisional.** Same conversion barrier as UPMXPO: high-affinity NH4 influx Vmax in the literature (e.g. Kronzucker/Glass-lineage HATS studies) is reported per root FW/DW (µmol g⁻¹ h⁻¹, order 1–40), not per root surface area; the SRA conversion + input-max caveat prevents a defensible fixed number. Provisional range ~default ÷5 … ×5 (0.002–0.05 gN m⁻² h⁻¹).

### UPMXZO
**Source-verified definition & units** — Read into `VmaxNO3Root_pft(ipltroot,NZ,NY,NX)` at `f90src/IOutils/PlantInfoMod.F90:599` / table `:1702`. Write-out `f90src/IOutils/PlantInfoMod.F90:1235`: *"Maximum rate for root uptake of NO3 [gN m-2 absorption area h-1]"*. USAGE: `f90src/Plant_bgc/NutUptakeMod.F90:539`: `VmaxNO3Root_pvr(N,L,NZ) = VmaxNO3Root_pft(N,NZ) * RootSAreaPerPlant_pvr(N,L,NZ) * FSatNutTransporter * fTgrowRootP_vr * AMIN1(FCUP,FZUP)`. Identical per-root-surface-area, input-max structure to UPMXZH. **True units: gN per m2 ROOT-SURFACE area per hour.**
**Bound — keep provisional.** Same as UPMXZH (NO3 HATS Vmax reported per root mass; SRA conversion unresolved). Provisional range ~default ÷5 … ×5 (0.002–0.05 gN m⁻² h⁻¹).

### RSMX
**Source-verified definition & units** — Read into `CuticleResist_pft(NZ,NY,NX)` at `f90src/IOutils/PlantInfoMod.F90:609` / table `:1710`. Write-out `f90src/IOutils/PlantInfoMod.F90:1262`: *"Cuticular resistance for H2O [s m-1]"* — units attribute here is CORRECT (unlike the uptake params). USAGE: converted to a per-hour vapor resistance `H2OCuticleResist_pft = CuticleResist_pft/3600` (`f90src/Plant_bgc/InitPlantMod.F90:154`; CO2 analog `×1.56` at `:155`), then adopted as the **maximum leaf resistance / minimum conductance at full stomatal closure**: `CanopyMinStomaResistH2O_pft(NZ) = H2OCuticleResist_pft(NZ)` (`f90src/Plant_bgc/StomatesMod.F90:267`) and `Stomata_Resist = CanopyMinStomaResistH2O + (H2OCuticleResist - CanopyMinStomaResistH2O)*Stomata_Stress` (`f90src/Plant_bgc/PlantMathFuncMod.F90:580`). So RSMX = 1/g_min (leaf minimum/cuticular conductance to water vapor). It is a genuine leaf-surface resistance, single-surface, s m⁻¹.
**Bound — literature.** Maps cleanly to the measured leaf minimum conductance g_min. Duursma et al. (2018) g_min compilation and Márquez et al. (2021) cuticular-conductance work give g_min ≈ 1–10 mmol m⁻² s⁻¹ (median ~3–4). Converting g_min → resistance with the 25 °C molar volume (0.024465 m³ mol⁻¹): R = 1/(g_min·V_m). g_min=10 mmol m⁻² s⁻¹ → R≈4,100 s m⁻¹; g_min=1 mmol m⁻² s⁻¹ → R≈40,900 s m⁻¹; median g_min≈4 → R≈10,200 s m⁻¹. The EcoSIM default 5000 s m⁻¹ ⇔ g_min≈8 mmol m⁻² s⁻¹ (high-conductance/herbaceous end, plausible for graminoids). **Bound: 4,000–41,000 s m⁻¹, central ~10,000 s m⁻¹.** [Duursma et al. 2018](https://doi.org/10.1111/nph.15395); [Márquez et al. 2021](https://doi.org/10.1111/nph.17588).

## Phenology & allocation

Source: `~/EcoSIM/f90src/`. Every parameter was traced from its netCDF read in `PlantInfoMod.F90` → internal `*_pft` variable → equation usage. Temperature normalizer `TFNP = calc_leave_grow_tempf(TKCO)` verified ≈ 1.0000 at 298.15 K (`PlantMathFuncMod.F90:148-160`), so the two rate params are genuine 25 °C reference rates.

### XRLA
**Source-verified definition & units** — Internal var `RateRefLeafAppearance_pft`. Read at `PlantInfoMod.F90:555`; self-documented as *"Rate of leaf (dis)appearance at 25oC [h-1]"* (`PlantInfoMod.F90:1108`). Used as the reference leaf-appearance rate: `LeafAppearRate = AZMAX1(RateRefLeafAppearance_pft(NZ)*TFNP)` (`PlantPhenolMod.F90:1080`), then further modulated by turgor/water factors `OFNG`/`WFNG` for annuals (`PlantPhenolMod.F90:1082-1090`). Also sets node-growth coupling `FracGroth2Node_pft = max(1, 0.04/XRLA)` (`InitPlantMod.F90:401`, `StartqMod.F90:355`) and leaf-turnover `RSpecKillLeafPetol = fTCanopyGroth·XRLA` (`PlantBranchMod.F90:3936`). Units **h⁻¹** are correct. The reciprocal is a phyllochron: at constant 25 °C real time, 1/(0.009·24) = **4.63 d leaf⁻¹**.
**Bound** — keep provisional. Although 1/XRLA maps to a phyllochron (a measurable), the realized rate is `XRLA·TFNP·turgor` integrated over *real* hours, not the thermal-time (°Cd) phyllochron reported in the field literature; converting a °Cd phyllochron to `h⁻¹`-at-25 °C requires integrating the specific `TFNP` deactivation curve over the site temperature regime, so no clean literature value exists. Documented true meaning: reference (25 °C, well-watered) leaf appearance rate, h⁻¹; grass/graminoid phyllochrons of ~3–5 d bracket the default but are not a defensible Morris bound without the thermal-time conversion.

### XRNI
**Source-verified definition & units** — Internal var `RefNodeInitRate_pft`. Read at `PlantInfoMod.F90:554`; *"Rate of node initiation at 25oC [h-1]"* (`PlantInfoMod.F90:1106`). Used identically to XRLA: `NodeInitRate = AZMAX1(RefNodeInitRate_pft(NZ)*TFNP)` (`PlantPhenolMod.F90:1079`), then turgor-modulated. Units **h⁻¹** correct. Reciprocal is a plastochron: at 25 °C real time, 1/(0.015·24) = **2.78 d node⁻¹**.
**Bound** — keep provisional. Same reasoning as XRLA (inverse-plastochron maps to a measurable, but the h⁻¹-at-25 °C / real-hour integration is model-specific and not directly comparable to °Cd plastochrons). Documented: reference node-initiation rate at 25 °C, h⁻¹; XRNI > XRLA (node initiation faster than leaf appearance) is consistent with plastochron < phyllochron.

### XDL
**Source-verified definition & units** — Internal var `CriticPhotoPeriod_pft`. Read at `PlantInfoMod.F90:564`; *"Critical photoperiod for leaf and flora development (<= maximum daylength; **<0 = maximum**) [h]"* (`PlantInfoMod.F90:1122`). **The default −1 is a SENTINEL, not a physical daylength:** `IF(CriticPhotoPeriod_pft(NZ,NY,NX).LT.0.0) CriticPhotoPeriod_pft = DayLenthMax_col` (`PlantInfoMod.F90:806-807`), i.e. −1 is replaced at init by the site's maximum daylength. When active it drives floral initiation via `PPD = AZMAX1(CriticPhotoPeriod_pft - DayLenthCurrent)` (`PlantPhenolMod.F90:1488`) and `PPDX = AZMAX1(CriticPhotoPeriod_pft - DayLenthCurrent - PhotoPeriodSens_pft)` (`PlantBranchMod.F90:2883`). Units **h** correct.
**Bound** — keep provisional. The default value is a sentinel that must not be swept as a continuous number (−1 ≠ a −1 h daylength; it means "no critical photoperiod, use site max"). Documented true meaning: critical photoperiod in hours, physically constrained to `[0, DayLenthMax_col]` of the site. If a modeler activates it (positive value), arctic critical-photoperiod literature for growth cessation / floral induction (~15–24 h at high latitude) would define the bound, but for the −1 default the correct action is to leave it as the photoperiod-insensitive sentinel.

### DMLF
**Source-verified definition & units** — Internal var `LeafBiomGrowthYld_pft`. Read at `PlantInfoMod.F90:611`; *"Leaf dry matter C production yield [gC leaf g-1 nonstrucal C]"* (`PlantInfoMod.F90:1275`). Used as a **growth-yield efficiency (Yg)**: `DMLFB = LeafBiomGrowthYld_pft` (`PlantBranchMod.F90:476`), summed with the other organ yields into `DMSHT` (`PlantBranchMod.F90:491`), and the complement is growth respiration — `YCO2Gro_brch = 1.0 - DMSHT` (`PlantBranchMod.F90:492`). Units **gC gC⁻¹** correct (dimensionless conversion efficiency; substrate = *nonstructural* C, not glucose).
**Bound** — literature. Growth conversion efficiency is a measurable quantity; [Amthor 2000](https://doi.org/10.1006/anbo.2000.1175) (*Annals of Botany* 86:1–20, DOI validated via crossref) reviews Yg ≈ 0.7–0.85 whole-plant, with leaves at the **low** end because high protein/lipid/secondary-compound content raises construction cost. Bound 0.60–0.80, central 0.72 (default). Caveat carried in note: EcoSIM's substrate is nonstructural C, so this is Yg exactly (1−Yg = growth CO₂), not a glucose-based cost.

### DMRT
**Source-verified definition & units** — Internal var `RootBiomGrosYld_pft`. Read at `PlantInfoMod.F90:618`; *"Root dry matter C production yield [gC root g-1 nonstrucal C]"* (`PlantInfoMod.F90:1289`). Used as Yg with the units confirmed **in code comment**: `DMRespEff = 1.0 - RootBiomGrosYld_pft(NZ)  !1-[gC root/gC nonst] = [gC resp/gC nonst]` (`RootMod.F90:1027`); also scales root growth `RootMycoNonst4Grow = ...·RootBiomGrosYld_pft` (`RootMod.F90:632,638`) and sets root C:N/C:P growth demand (`StartqMod.F90:442-443`). Units **gC gC⁻¹** correct.
**Bound** — literature. Same measurable (Yg); roots sit at the **high** end (less protein, more cheap carbohydrate) per [Amthor 2000](https://doi.org/10.1006/anbo.2000.1175). Bound 0.75–0.92, central 0.88 (default). DMRT > DMLF ordering (root cheaper than leaf) is mechanistically consistent.

### DMSTK
**Source-verified definition & units** — Internal var `StalkBiomGrowthYld_pft`. Read at `PlantInfoMod.F90:613`; *"Stalk dry matter C production yield [gC stalk g-1 nonstrucal C]"* (`PlantInfoMod.F90:1279`). Used as Yg: `DMRespEff = 1. - StalkBiomGrowthYld_pft(NZ)  ![gC CO2/gC nonst]` (`RootMod.F90:1810`), stalk growth `Growth_brch(...stalk) = RNonstC4Groth·PART·StalkBiomGrowthYld_pft` (`PlantBranchMod.F90:365`), and weighted into `DMSHT` (`PlantBranchMod.F90:491`). Units **gC gC⁻¹** correct.
**Bound** — literature. Same measurable (Yg); [Amthor 2000](https://doi.org/10.1006/anbo.2000.1175) supports a wide organ range. Bound 0.60–0.85, central 0.67 (default). The default (lowest of the three) is plausible for lignified structural tissue; kept literature but with the widest interval given ontogenic construction-cost variability in stems.
