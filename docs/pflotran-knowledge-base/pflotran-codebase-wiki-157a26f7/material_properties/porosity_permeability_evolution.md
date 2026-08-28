**Source pin:** PFLOTRAN commit 157a26f7
**Scope:** porosity-driven permeability and tortuosity evolution (PERMEABILITY_POWER / PERMEABILITY_CRITICAL_POROSITY / PERMEABILITY_MIN_SCALE_FACTOR / TORTUOSITY_POWER)
**Last verified:** 2026-07-31

# Porosity-permeability evolution

## Summary for a calibration agent

Three `MATERIAL_PROPERTY` cards define how permeability responds to a change in porosity:

| Card | Field | Default |
|---|---|---|
| `PERMEABILITY_POWER` | `permeability_pwr` | `1.d0` (`src/pflotran/material.F90:193`) |
| `PERMEABILITY_CRITICAL_POROSITY` | `permeability_crit_por` | `0.d0` (`src/pflotran/material.F90:194`) |
| `PERMEABILITY_MIN_SCALE_FACTOR` | `permeability_min_scale_fac` | `1.d0` (`src/pflotran/material.F90:195`) |

They are read as bare doubles with no unit conversion and no range check (`src/pflotran/material.F90:781-792`). All three are dimensionless.

**They do nothing unless `UPDATE_PERMEABILITY` is present in the `CHEMISTRY` block.** See §3.

---

## 1. The expression, exactly as written

The only consumer of all three parameters is `RealizationUpdatePropertiesTS` (`src/pflotran/realization_subsurface.F90:1927`), inside the `if (reaction%update_permeability)` branch (`:2045`). The complete arithmetic:

```fortran
      critical_porosity = material_property_array(imat)%ptr% &
                            permeability_crit_por
      porosity_base_ = material_auxvars(ghosted_id)%porosity_base
      scale = 0.d0
      if (porosity_base_ > critical_porosity .and. &
          porosity0_p(local_id) > critical_porosity) then
        scale = ((porosity_base_ - critical_porosity) / &
                 (porosity0_p(local_id) - critical_porosity)) ** &
                material_property_array(imat)%ptr%permeability_pwr
      endif
      scale = max(material_property_array(imat)%ptr% &
                    permeability_min_scale_fac,scale)
      material_auxvars(ghosted_id)%permeability(perm_xx_index) = &
          perm0_xx_p(local_id)*scale
```
(`src/pflotran/realization_subsurface.F90:2058-2071`)

In symbols, per cell:

$$
\text{scale} =
\begin{cases}
\left(\dfrac{\phi_{\text{base}} - \phi_c}{\phi_0 - \phi_c}\right)^{p} & \text{if } \phi_{\text{base}} > \phi_c \text{ and } \phi_0 > \phi_c \\[2ex]
0 & \text{otherwise}
\end{cases}
$$

$$
\text{scale} \leftarrow \max\!\left(\text{scale},\; s_{\min}\right)
$$

$$
k_{ii} = k_{ii}^{0}\cdot\text{scale}, \qquad ii \in \{xx,yy,zz\}
$$

with

- $\phi_c$ = `PERMEABILITY_CRITICAL_POROSITY`,
- $p$ = `PERMEABILITY_POWER`,
- $s_{\min}$ = `PERMEABILITY_MIN_SCALE_FACTOR`,
- $\phi_0$ = the cell's **initial** porosity, held in the PETSc vector `field%porosity0` (assigned from the deck's `POROSITY` at `src/pflotran/init_subsurface.F90:488`),
- $\phi_{\text{base}}$ = the cell's current *base* porosity, `material_auxvar%porosity_base` — the porosity prescribed from outside the flow solve, e.g. by mineral precipitation/dissolution or geomechanics (`src/pflotran/material_aux.F90:60-61`),
- $k^0$ = the cell's **initial** permeability, held in `field%perm0_xx/yy/zz` (assigned from the deck's `PERM_ISO`/`PERM_X` at `src/pflotran/init_subsurface.F90:476`).

The same `scale` is applied identically to all three diagonal components (`realization_subsurface.F90:2070-2075`), and to the off-diagonals when `option%flow%full_perm_tensor` is on (`:2076-2083`). **Anisotropy ratios are preserved** — evolution never rotates or reshapes the tensor.

Note the update multiplies the *initial* permeability, not the current one, so it is not path-dependent and cannot drift.

### 1.1 Is this "Kozeny-Carman"?

Not by name. Grepping the entire source tree for `kozeny` or `carman` (case-insensitive) over all 314 `.F90` files returns **zero hits**. What is implemented is a normalized power-law porosity ratio with a percolation-threshold offset. It reduces to the familiar Kozeny-Carman-like form $k/k_0 = (\phi/\phi_0)^p$ only when $\phi_c = 0$ (the default). Describe it as a power-law porosity-permeability relation, not as Kozeny-Carman, when documenting a deck.

---

## 2. `PERMEABILITY_MIN_SCALE_FACTOR`: lower bound, default 1.0 — CONFIRMED

The claim under test: *"MIN_SCALE_FACTOR acts as a LOWER bound defaulting to 1.0, meaning permeability can only increase."*

**Confirmed on both counts, independently verified.**

**(a) It is a lower bound.** The single use site is

```fortran
      scale = max(material_property_array(imat)%ptr% &
                    permeability_min_scale_fac,scale)
```
(`src/pflotran/realization_subsurface.F90:2068-2069`)

`max(...)` with the parameter as one argument makes the parameter a **floor** on `scale`. There is no `min(...)` anywhere in this branch and no other reference to the field: `grep -n "min_scale_fac"` across the tree matches only the declaration (`material.F90:103`), the default (`material.F90:195`), the read (`material.F90:791`), and this one use (`realization_subsurface.F90:2069`). Nothing else can reinterpret it.

**(b) The default is 1.0.**

```fortran
  material_property%permeability_min_scale_fac = 1.d0
```
(`src/pflotran/material.F90:195`, inside `MaterialPropertyCreate`)

**(c) Therefore the consequence holds.** With the default left in place, `scale = max(1.0, scale) >= 1` always, so `k = k0 * scale >= k0`. Permeability can only **increase or stay equal** — the porosity-reduction half of the relation is entirely clipped away. A deck that precipitates minerals and closes pores will show **no permeability decrease at all** unless `PERMEABILITY_MIN_SCALE_FACTOR` is explicitly lowered.

This is almost certainly a silent-surprise default rather than a physical intent, and it is invisible: nothing warns. Note also that `MaterialPropInputRecord` prints `permeability power` and `permeability critical por.` but **never prints `permeability_min_scale_fac`** (`src/pflotran/material.F90:2553-2562`), so the effective floor does not even appear in the input record.

### 2.1 Reading the motivating deck's value

`PERMEABILITY_MIN_SCALE_FACTOR 1.15d-10` sets the floor about ten orders of magnitude below 1. That is the idiom for **"remove the floor"** — it lets permeability fall by up to ~10 orders of magnitude while still preventing an exact zero (which would make the flux Jacobian singular). Read `1.15d-10` as a numerical safety net, not as a physical parameter, and treat it accordingly in a sensitivity study: sweeping it across `[1e-12, 1e-8]` should produce no response at all until it starts to bind.

### 2.2 The hard-zero branch

If $\phi_{\text{base}} \le \phi_c$ **or** $\phi_0 \le \phi_c$, the `if` at `realization_subsurface.F90:2062-2063` is skipped and `scale` stays at the `0.d0` initialized at `:2061` — then immediately raised to $s_{\min}$ by the `max`. So `PERMEABILITY_MIN_SCALE_FACTOR` also sets the **floor for a fully clogged cell**: with the default 1.0, a cell whose porosity drops to the critical value keeps its full initial permeability. This is the sharpest edge of the default.

With the motivating deck's `PERMEABILITY_CRITICAL_POROSITY 0.09` and `POROSITY 0.39`, the initial ratio is $(0.39-0.09)/(0.39-0.09) = 1$, and permeability collapses toward the `1.15d-10` floor as $\phi_{\text{base}} \to 0.09$.

---

## 3. Activation gate: this code is dead without `UPDATE_PERMEABILITY`

`reaction%update_permeability` defaults to `PETSC_FALSE` (`src/pflotran/reaction_aux.F90:517`) and is set true by exactly one deck keyword:

```fortran
      case('UPDATE_PERMEABILITY')
        reaction%update_permeability = PETSC_TRUE
```
(`src/pflotran/reaction.F90:804-805`, inside `ReactionReadPass1`, `src/pflotran/reaction.F90:112` — the `CHEMISTRY` block reader)

Sibling keywords in the same switch: `UPDATE_POROSITY` (`:799-801`, which also sets `option%flow%transient_porosity`), `UPDATE_TORTUOSITY` (`:802-803`), `CALCULATE_INITIAL_POROSITY` (`:797-798`).

`RealizationUpdatePropertiesTS` is only called when at least one of `update_porosity`, `update_tortuosity`, `update_permeability`, or `mineral%update_surface_area` is on — see the guards at `src/pflotran/pm_subsurface_flow.F90:500-506` (timestep setup, additionally skipped on restart) and `:735-741` (each timestep). Other process models call it from `pm_rt.F90:787,794`, `pm_nwt.F90:1015`, `pm_material_transform.F90:496`, `pm_osrt.F90:250`.

**Implication for calibration.** `PERMEABILITY_POWER`, `PERMEABILITY_CRITICAL_POROSITY`, and `PERMEABILITY_MIN_SCALE_FACTOR` are **inert parameters** in a run with no `CHEMISTRY` block, or with a `CHEMISTRY` block lacking `UPDATE_PERMEABILITY`. Before spending samples on them, confirm the keyword is present in the deck. If it is absent, these three appear in the `MATERIAL_PROPERTY` card, are parsed without complaint, and change nothing.

Also note: `porosity_base` only moves if something moves it. If `UPDATE_PERMEABILITY` is on but nothing updates porosity (no mineral reactions with `UPDATE_POROSITY`, no geomechanics), then $\phi_{\text{base}} = \phi_0$, `scale = 1`, and permeability is again constant.

---

## 4. The tortuosity twin

`TORTUOSITY_POWER` (`src/pflotran/material.F90:793-796`, field `tortuosity_pwr`, default `0.d0` at `:211`) drives the analogous update in the same routine:

```fortran
      scale = (material_auxvars(ghosted_id)%porosity_base / &
               porosity0_p(local_id))** &
        material_property_array(patch%imat(ghosted_id))%ptr%tortuosity_pwr
      material_auxvars(ghosted_id)%tortuosity = &
        tortuosity0_p(local_id)*scale
```
(`src/pflotran/realization_subsurface.F90:2027-2031`)

$$\tau = \tau_0 \left(\frac{\phi_{\text{base}}}{\phi_0}\right)^{q}, \qquad q = \texttt{TORTUOSITY\_POWER}$$

Three differences from the permeability version worth noting:

1. **No critical-porosity offset** — the ratio is the bare $\phi_{\text{base}}/\phi_0$.
2. **No min-scale clamp** — nothing floors this scale.
3. **The default `0.d0` makes it identically 1**, i.e. no evolution, whereas the permeability default `1.d0` gives a linear response.

Gated on `reaction%update_tortuosity` (`realization_subsurface.F90:2021`), i.e. the `UPDATE_TORTUOSITY` keyword. `UPDATE_TORTUOSITY` combined with `ANISOTROPIC_TORTUOSITY` is rejected (`src/pflotran/pm_subsurface_flow.F90:373-376`).

---

## 5. Other paths that change permeability (do not confuse them)

| Path | Trigger | Source | Interacts? |
|---|---|---|---|
| `PERM_FACTOR` ramp | `PERM_FACTOR` sub-block in `MATERIAL_PROPERTY` | `src/pflotran/material.F90:748-780` | pressure-driven multiplier, independent of the porosity ratio |
| `WIPP-FRACTURE` | `WIPP-FRACTURE` sub-block | `src/pflotran/material.F90:524-531` | pressure-induced fracture perm/porosity (BRAGFLO 6.02 UM Eq. 136) |
| `GEOMECHANICS_SUBSURFACE_PROPS` | sub-block; sets `option%flow%transient_porosity` | `src/pflotran/material.F90:510-517` | changes `porosity_base`, which *feeds* the expression in §1 |
| `MATERIAL_TRANSFORM` / illitization | `MATERIAL_TRANSFORM <name>` + a `MATERIAL_TRANSFORM` block with `SHIFT_PERM` | `src/pflotran/material.F90:373-375`; `src/pflotran/material_transform.F90:523` | separate temperature-driven smectite→illite permeability shift |
| dataset scaling | `PERMEABILITY_SCALING_FACTOR` | `src/pflotran/init_subsurface.F90:1030-1039` | one-off scaling of dataset-read perms at initialization, not evolution |
| soil compressibility | `SOIL_COMPRESSIBILITY_FUNCTION` | `src/pflotran/material.F90:1061-1092`, models listed at `:1691-1699` | changes `porosity` (`POROSITY_CURRENT`), **not** `porosity_base` — so it does *not* feed §1 |

That last row is the subtle one. `MaterialCompressSoil` acts on the current porosity used by the flow solve; the permeability evolution in §1 reads `porosity_base`. Pressure-driven pore compression therefore does **not** propagate into permeability through this path.

---

## 6. Calibration-knobs summary

| Keyword | Source line | Units | Default | Valid range | What it controls |
|---|---|---|---|---|---|
| `PERMEABILITY_POWER` | `material.F90:781-784` | – | `1.d0` (`:193`) | typically `[1, 5]`; not code-checked | exponent $p$ in $(\Delta\phi/\Delta\phi_0)^p$ (`realization_subsurface.F90:2064-2066`). Higher = sharper permeability response to porosity change |
| `PERMEABILITY_CRITICAL_POROSITY` | `material.F90:785-788` | – | `0.d0` (`:194`) | `[0, \phi_0)`; not code-checked | percolation threshold $\phi_c$ subtracted from both porosities. At $\phi_{\text{base}} \le \phi_c$ the analytic branch is skipped and `scale` falls to the floor (`:2062-2067`) |
| `PERMEABILITY_MIN_SCALE_FACTOR` | `material.F90:789-792` | – | `1.d0` (`:195`) | `> 0` | **LOWER** clamp on `scale` (`:2068-2069`). Default 1.0 forbids any permeability decrease. Set to a tiny value (e.g. `1.15d-10`) to allow decrease while avoiding exactly zero |
| `TORTUOSITY_POWER` | `material.F90:793-796` | – | `0.d0` (`:211`) | any | exponent $q$ in $\tau = \tau_0(\phi_{\text{base}}/\phi_0)^q$ (`:2027-2029`). Default 0 = no evolution |
| `UPDATE_PERMEABILITY` (CHEMISTRY block) | `reaction.F90:804-805` | flag | off (`reaction_aux.F90:517`) | on/off | **master switch** — without it the three cards above are inert |
| `UPDATE_TORTUOSITY` (CHEMISTRY block) | `reaction.F90:802-803` | flag | off | on/off | master switch for `TORTUOSITY_POWER` |
| `UPDATE_POROSITY` (CHEMISTRY block) | `reaction.F90:799-801` | flag | off | on/off | recomputes `porosity_base` from mineral volume fractions (`realization_subsurface.F90:1989-1992`); usually a prerequisite for the above to do anything |

### Pre-flight checklist before calibrating these

1. Is `UPDATE_PERMEABILITY` in the `CHEMISTRY` block? If not, all three cards are inert (§3).
2. Is anything actually moving `porosity_base`? Mineral reactions with `UPDATE_POROSITY`, or geomechanics. If not, `scale ≡ 1` (§3).
3. Is `PERMEABILITY_MIN_SCALE_FACTOR` left at its default 1.0? If so, only permeability *increases* are representable, and a sensitivity study on `PERMEABILITY_POWER` will show a one-sided response (§2).
4. Is `PERMEABILITY_CRITICAL_POROSITY` below the smallest porosity the run will reach? If not, cells will hit the hard-zero branch and clamp to the floor (§2.2).

---

## Related

- `material_property_card.md` — the full `MATERIAL_PROPERTY` card, including `POROSITY`, `PERMEABILITY`, and soil compressibility.
- `characteristic_curves.md` — `CHARACTERISTIC_CURVES`, van Genuchten, and Mualem relative permeability.
