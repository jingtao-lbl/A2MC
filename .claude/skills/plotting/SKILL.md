---
name: plotting
visibility: public
category: authoring
description: Produce a clean, readable, report/manuscript/slide-grade matplotlib figure — right fonts, no legend/annotation overlap, log scale + units, a finding-stating title — and VERIFY it by viewing the saved PNG before shipping. Use when making or fixing any figure — "plot X", "make a figure/chart", "the legend overlaps", "clean up this plot", "make this publication-quality", "the fonts are too small", "the labels are clipped". The HOW-to-make-it-look-right complement to figures>tables>words.
allowed-tools: [Read, Glob, Grep, Write, Edit, Bash]
modes:
  requires_fates: false
  nutrient_pathway: any
  scope: [analysis]
  summary: "Clean, readable, overlap-free matplotlib figures; verify by viewing the PNG. Model-agnostic."
---

# plotting — clean, readable, overlap-free matplotlib figures

A2MC makes claims with figures (figures > tables > words — `<auto-memory>/feedback_figures_over_tables_over_words`).
A figure that overlaps its own legend, uses matplotlib's tiny default fonts, or clips a label **undercuts
the claim it's meant to make**. This skill is the checklist for a report/manuscript/slide-grade figure —
and the one step that actually catches the problems: **look at the rendered PNG.**

## THE LOAD-BEARING RULE — verify by viewing

**After `savefig`, open the PNG and LOOK at it (Read the image file) before you embed it in a report,
ship it, or move on.** Overlaps, clipped labels, unreadable fonts, a legend sitting on the data — **none
of these show up in the code; they show up in the picture.** This is the step that is easy to skip and
the reason figures ship broken. (2026-07-09: an envelope figure's legend sat squarely on top of its own
annotation — the code read fine; only viewing the PNG revealed it. The fix took one look.)

Everything below reduces how often the view-check fails; the view-check is what guarantees it.

## Setup (headless — Perlmutter has no display)

```python
import matplotlib
matplotlib.use("Agg")                     # or export MPLBACKEND=Agg — NEVER plt.show() on a login node
import matplotlib.pyplot as plt
plt.rcParams.update({
    "savefig.dpi": 135,                    # 130–150 is crisp without bloating; >200 rarely needed
    "figure.constrained_layout.use": True, # auto-fits labels/legend — kills most clipping
    "font.size": 11, "axes.titlesize": 13, "axes.labelsize": 12,
    "xtick.labelsize": 10, "ytick.labelsize": 10, "legend.fontsize": 9,
})
# For a SLIDE, scale the four size lines ~1.4× (titlesize 18, labelsize 16, ticks 14, legend 12).
```

**This is the GENERIC starting point, and a REPORT figure uses a different block.** The house style below sets `dpi` 200 with smaller type (9 / 9.5 / 8.5) — which looks like it contradicts both the `>200 rarely needed` note above and rule 1's *if in doubt, bigger*, and does not, because the two are **matched sets rather than independent knobs**: the house style pairs the smaller type with a modest page-width figsize and the higher dpi, so type is comparable on the printed page while thin 0.8 pt axes and panel letters stay crisp. **Do not mix the two blocks** — take one whole. Use this one for a quick working figure; use the house style for anything a person other than you will read.

## Checklist (each item is a common way the view-check fails)

1. **Readable fonts.** matplotlib's defaults are too small for a report page. Set the sizes above
   explicitly (rcParams, or per-element `fontsize=`). If in doubt, bigger.
2. **No overlap — place the legend in the empty region, not on the data.**
   - Find the empty quadrant first. A **monotonic rising** curve leaves the **upper-left** and
     **lower-right** empty; a **falling** curve leaves upper-right / lower-left; a scatter — the
     sparsest corner. `ax.legend(loc="upper left", framealpha=0.95)`.
   - If nothing inside is clear, put it **outside** the axes and let constrained_layout make room:
     `ax.legend(loc="center left", bbox_to_anchor=(1.02, 0.5))`.
3. **No overlap — annotations sit in empty space and POINT to the data.** Never drop text on the curve.
   `ax.annotate("what this point means", xy=(x_pt, y_pt), xytext=(x_clear, y_clear),
   arrowprops=dict(arrowstyle="->"))`. Put the text where there's whitespace; the arrow does the linking.
4. **Log scale when the data spans ≥ ~2 orders of magnitude** (`ax.set_yscale("log")`), and **always put
   units in the axis label** — `"standing plant density (plants/m², log)"`, not `"density"`.
5. **Title states the FINDING, not the axes.** "Option C bounds density ~3 orders lower" beats
   "nplant vs option". The reader should get the point from the title.
6. **Semantic, colorblind-safe colors, used consistently.** red = fail/crash/bad, green = good/fixed/healthy,
   grey = baseline/reference. Avoid red↔green as the *only* distinction; add markers/linestyles too.
   **For A2MC biomass-vs-targets time-series specifically, the colors are FIXED semantic roles — use the
   ensemble figure template below, not free choices.**
   **And for a REPORT figure the report-figure house style below fixes them too, differently:** reference
   is **black**, not grey, and grey demotes to a passive band. Vermillion `#D55E00` is the bad/problem role
   — it is the colourblind-safe red this rule asks for, named exactly so it is not re-picked by eye.
6b. **Before writing an rcParams block, look in `use_cases/{Model}_{Case}/scripts/` for a figure template — and ask for the house STYLE, not for a script that plots your quantity.** A throughput figure and a flux time series share the style and share nothing else, so searching by figure type finds nothing and concludes wrongly that nothing is there. Measured 2026-09-04: a case's publication-figure template existed, was searched for by figure type, was not found, and the style was re-derived from the original source — arriving at an rcParams block **byte-identical** to the template's, which is what makes the miss provable rather than arguable. See the report-figure house style below.
7. **Layout + save.** `constrained_layout=True` (set above) or `fig.tight_layout()` before `savefig`;
   both prevent clipped tick labels and titles. Save PNG at the rcParams DPI.
8. **VERIFY BY VIEWING** (the load-bearing rule) — Read the PNG and eyeball it. Fix and re-render until
   it's clean. Only then embed/ship.
9. **Regenerable.** Read data from a durable file (CSV/NetCDF), not hardcoded numbers where avoidable, and
   **ship the plotting script next to the figure** so it can be regenerated. Name the file per
   `<auto-memory>/feedback_plot_filename_convention` (round + axis-mode + case count).

## The A2MC ensemble figure template (biomass vs targets)

Every biomass-vs-targets **time-series** figure in A2MC — the whole-ensemble screening/round plot
(`tools/plot_ensemble_cases.py`), the per-round and cross-round summaries, and the Phase-6 variant-comparison
overlays (`tools/extract_and_plot_selected_cases.py plot`) — shares **one visual language**, so a reader
learns it once and every figure reads the same way. **`tools/plot_ensemble_cases.py` is the reference
implementation: reuse it when you can; when you must hand-roll a related figure, match this scheme rather
than inventing colors.**

**Semantic color scheme (fixed roles — memorize):**

| Element | Style | Meaning |
|---|---|---|
| ensemble cloud | light purple `[0.7, 0.6, 1.0]`, `alpha=0.05`, `lw=0.3` | every case — the achievable envelope |
| **best-fit case** | **red**, `lw=3` | lowest composite error (the figure calls it "Best NRMSE") |
| **most-targets case** | **blue**, `lw=3` | most targets within ±20% — drawn **only when ≠ the red case** |
| baseline / control | **black dashed**, drawn on top | the unchanged reference (variant plots: `--baseline`) |
| observation | black diamond `kd`, `markersize=12` | the field target value |
| ±20% acceptance band | yellow fill / darkorange edge, `alpha=0.4` | the "target met" tolerance |
| obs uncertainty | black `k-` bar, `lw=3` | ±1 SD, when available |
| phase boundaries | gray dashed `axvline` + gray `ADSP`/`RGSP`/`TRANS` labels | spin-up → transient segments |

**Layout + axes.** 3 PFT rows (the calibrated PFTs — Kougarok api-43: PFT10 evergreen shrub, PFT11 deciduous
shrub, PFT12 graminoid) × 2 organ columns (leaf, fineroot); y-unit `Leaf/Fineroot C (g C m$^{-2}$)`; x-label
`Simulation Year (ADSP, RGSP) / Calendar Year (TRANS)` for the `--combined` 519-yr axis, calendar years for
the TRANS-only view; `suptitle` states the best case + its NRMSE.

**zorder law (the observation must stay readable on top of everything).** cloud (50) < best/most-targets
(99–100) < ±20% band (200) < obs uncertainty bar (201) < obs diamond (202). Draw in that order or set
`zorder=` explicitly.

**Footgun — alpha scales with case count.** With ~2,700+ cases the cloud saturates to solid purple at
`alpha=0.5`; `plot_ensemble_cases.py` uses **`alpha=0.05`** so density gradients stay legible. Dial alpha
DOWN as the ensemble grows — but a small **selected-case comparison** (a handful of variant lines) wants the
opposite: solid, opaque colored lines (`alpha=1.0`), one distinct color per variant, control black-dashed.

This template **overrides generic rule 6** for these figures — red / blue / purple / black-dashed are fixed
semantic roles here (best-fit / most-targets / cloud / control), not free color choices.

## The A2MC report-figure house style (everything that is NOT the ensemble figure)

The template above governs biomass-vs-target time series. **Everything else — a report figure, an analysis figure, a provenance or throughput figure — follows a second, separate house style**, and a case that has adopted it carries a template at `use_cases/{Model}_{Case}/scripts/`. The two do not compete: they answer different questions and fix different palettes, so adopting this one is not license to restyle an ensemble plot.

| element | value |
|---|---|
| palette | Okabe-Ito, colourblind-safe **and legible in greyscale**: reference/observation black `#000000`, model/problem vermillion `#D55E00`, passive band `#BBBBBB`, secondary blue `#0072B2` |
| spines | top and right removed; `axes.linewidth` 0.8, tick widths 0.8 |
| gridlines | none |
| legend | frameless (`legend.frameon: False`), and often unnecessary — a two-series figure with semantic colour does not need one |
| panel letters | bold lowercase, `ax.text(-0.14, 1.06, s, transform=ax.transAxes, fontsize=11, fontweight="bold", va="top")` |
| axes | units on **every** axis |
| statistics | reported **IN-PANEL** (≈7.6 pt, `color="0.25"`) rather than pushed into the caption, and placed by **where the curve is**, not by habit — per panel, not once for the figure |
| title | `suptitle` states the **FINDING as a sentence**, often two clauses |
| sizes | `savefig.dpi` 200; font 9, `axes.labelsize` 9.5, ticks 8.5, legend 8.5 |

```python
plt.rcParams.update({
    "savefig.dpi": 200,
    "figure.constrained_layout.use": True,
    "font.size": 9, "axes.titlesize": 10, "axes.labelsize": 9.5,
    "xtick.labelsize": 8.5, "ytick.labelsize": 8.5, "legend.fontsize": 8.5,
    "axes.spines.top": False, "axes.spines.right": False,
    "axes.linewidth": 0.8, "xtick.major.width": 0.8, "ytick.major.width": 0.8,
    "legend.frameon": False,
})
```

Like the ensemble template, this **overrides generic rule 6** within its scope: black / vermillion / grey are fixed roles here, not free choices. It does **not** override rule 1 — see the note under Setup for why smaller type is not a step backwards.

**Reference implementation:** `use_cases/EcoSIM_Lusignan/memory/phase_results/20260816a_obs_vs_sim_publication_figures/make_publication_figures.py`, which states the contract in its own docstring. Its generalized form — the shared SHAPE, with paths and scored variables resolved from the environment rather than hardcoded — is what a case carries in `scripts/`.

**Why this section exists, and it is a coverage failure rather than a preference.** The style was invented in one case, produced five figures across two folders, was promoted to a case template on a second occasion, and was then **missed twice**: once by a session that made three sets of figures without ever loading this skill, and once by a session that DID load this skill, could not find the template because it searched by figure type, and re-derived the whole style from the original source. Nothing in this file named any of it. The conventions appeared in six files across two cases while the words *Okabe-Ito*, *panel letter*, *spines* and *in-panel* appeared in this skill **zero** times.

## Footguns

- **Legend/annotation drawn last but placed by habit** (`loc="best"` or a fixed corner) lands on the data
  when the data shape changes. Re-check placement whenever the data changes — and view the PNG (rule above).
- **`plt.show()` / no Agg backend on Perlmutter** → hang or error on the login node. Always Agg + savefig.
- **`tight_layout` after adding an outside-axes legend** can still clip it; prefer `constrained_layout` +
  `bbox_to_anchor`, and view the result.
- **Tiny default fonts** look fine at the interactive size but are unreadable in an embedded report page —
  set sizes explicitly.
- **Not viewing the PNG** — the #1 footgun. The code compiling ≠ the figure being readable.
- **Viewing the PNG but only checking LAYOUT.** The view-check catches false CLAIMS too, and those are the more expensive kind. Measured 2026-09-04 on a single figure: an in-panel annotation read *"then monotonic decline"* while the last four bars visibly rose; a title claimed a ratio stronger than its own final bar supported; and a colour rule marked the decline as starting two blocks before it did. Three false statements, none visible in the code, all obvious in the picture. **Read the figure as a reader would and ask whether each word on it is true**, not just whether anything overlaps.
- **Searching `scripts/` for a matching FIGURE TYPE instead of for the house STYLE** — see checklist 6b; it concludes "no template" while one is sitting there.

## Cross-references

- Why figures at all + captioning: `<auto-memory>/feedback_figures_over_tables_over_words`,
  `feedback_plot_filename_convention`.
- **Reciprocal skills** — the skills that produce figures. **Every skill named in this bullet must
  name `plotting` back, and `tools/check_skill_registry.py::reciprocity_check` enforces it**, so
  adding one here without the reciprocal pointer fails the pre-commit gate rather than rotting
  quietly. That is the whole point: a one-directional claim is how this surface failed before (see
  Changelog). Keep the names inside THIS bullet — the checker reads the bullet, not the section.
  **All seven phase skills** — `phase0-design`, `phase1-exploration`, `phase2-screening`,
  `phase3-diagnosis`, `phase4-hypothesis`, `phase5-testing`, `phase6-refinement` — plus
  `calibration-discipline`, `calibration-goal`, `calibration-log`, `offline-testing-workflow`,
  `scientific-analysis`, `summarize-calibration-round`, `compare-calibration-rounds`.
- Downstream of a figure, and NOT part of the reciprocal set above (they consume figures rather
  than produce them, so they carry no obligation to name this skill): `markdown-to-pdf` renders the
  doc that embeds them, `write-report` is the report that embeds them. The biomass time-series
  figures follow the ensemble template above; reference implementation `tools/plot_ensemble_cases.py`.

## Notes

- **Branch fit:** generic matplotlib conventions — applies on any branch and any model configuration.

## Changelog

- 2026-09-04: **Adds the A2MC report-figure house style, and a footgun about what the view-check is FOR.** PI-directed, after pointing at a figure and asking that its style be followed. The style was invented in one case, produced five figures across two folders, was promoted to a case template on a second occasion — and was then missed TWICE, once by a session that never loaded this skill and once by a session that did load it but searched `scripts/` for a matching figure TYPE rather than for the STYLE, then re-derived the whole thing from source to a **byte-identical** rcParams block. The conventions lived in six files across two cases while *Okabe-Ito*, *panel letter*, *spines* and *in-panel* appeared here zero times, so the skill could not have helped either session. New: the house-style section (scoped explicitly to NON-ensemble figures, so it cannot be read as overriding the fixed ensemble palette), checklist item 6b (look in `scripts/` for the style, not the quantity), and two footguns — searching by figure type, and treating the view-check as a layout check when its more valuable catch is a false CLAIM on the figure (three of them on one figure the same day). **Reconciled in the same pass (refine-skill step 5), because the edit contradicted three things it did not touch:** the Setup block's `dpi` 135 and its `>200 rarely needed` note, rule 1's *if in doubt, bigger* against the house style's smaller type, and rule 6's *grey = baseline/reference* against the house style's black. The first two are answered by saying the two rcParams blocks are **matched sets, not independent knobs** — take one whole, do not mix — and the third by a carve-out beside the one the ensemble template already needed. **No trigger change:** `description` is untouched, so when this skill fires is unaffected.
- 2026-08-16 (later): **The reciprocity invariant is now ENFORCED, not just written down.**
  `tools/check_skill_registry.py::reciprocity_check` reads the `**Reciprocal skills**` bullet and
  fails the pre-commit gate if any skill named there does not name `plotting` back. The bullet was
  split so it carries ONLY the reciprocal names — `markdown-to-pdf` and `write-report` moved to a
  separate bullet, since they consume figures rather than produce them and carry no obligation.
  7 tests, each asserting a way the check must FAIL. Details: `20260816d_*`.
- 2026-08-16: **Cross-references made BIDIRECTIONAL, and the list widened to all seven phase skills
  plus `calibration-discipline` / `calibration-goal` / `calibration-log`.** This section previously
  claimed `phase0-design`, `phase3-diagnosis` and `scientific-analysis` applied these conventions
  while none of the three mentioned this skill — a one-directional link, the same shape as the
  memory-to-log provenance gap `.claude_memory/CLAUDE.md` documents. Consequence, measured: an
  EcoSIM_Lusignan session produced three sets of figures across two days without ever loading this
  skill, and the first invocation immediately caught a statistics box drawn over the data — exactly
  what the view-the-rendered-PNG rule exists for. PI-directed, and PI-widened from the three skills
  originally proposed to every phase ("every phase needs the plotting skill").
- 2026-07-16: Added **"The A2MC ensemble figure template (biomass vs targets)"** — the fixed semantic color
  scheme (purple cloud / red best-fit / blue most-targets / black-dashed control / black obs diamond / yellow
  ±20% band / gray phase boundaries), the 3-PFT×2-organ layout + `g C m$^{-2}$` units, the zorder law (obs on
  top), and the alpha-scales-with-case-count footgun, with `tools/plot_ensemble_cases.py` as the reference
  implementation; rule 6 defers to it. Cross-refs name the ensemble-figure-producing skills. Ported from demo
  `e247330`; PFT layout labels adapted to api-43 (10/11/12) — main's `plot_ensemble_cases.py` carries the same
  style constants (verified).
- 2026-07-09: Ported to `main` from demo `5ef9cc7` (v3.13) — distilled from the R5 mass-balance report
  figures (demo branch), where a legend-on-annotation overlap was caught only by viewing the rendered PNG.
  The "verify by viewing" step is the load-bearing rule. Added main's `modes:` block.
