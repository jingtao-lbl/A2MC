**Source pin:** PFLOTRAN commit 157a26f7
**Scope:** reactive transport — gas-phase transport, `ACTIVE_GAS_SPECIES`, and the `GAS_TRANSPORT_IS_UNVETTED` acknowledgement
**Last verified:** 2026-07-31

---

# Gas-phase transport in GIRT/OSRT

Split out of [`advection_dispersion_diffusion.md`](advection_dispersion_diffusion.md), which
covers the phase-agnostic dispersion/diffusion/advection kernels. This page is specifically
about the **second mobile phase** that `ACTIVE_GAS_SPECIES` introduces, and about the
undocumented `GAS_TRANSPORT_IS_UNVETTED` card that guards it.

> **PETSc is external.** `Mat`/`Vec` types and `MatSetValuesLocal`, `VecGetArrayF90` etc. are
> PETSc library calls, not PFLOTRAN code.

---

## 1. Active vs passive gases

Two `CHEMISTRY` blocks declare gases (`src/pflotran/reaction.F90:264-286`):

| Block | itype | Transport consequence |
|---|---|---|
| `PASSIVE_GAS_SPECIES` | `PASSIVE_GAS = 2` (`reaction_gas_aux.F90:16`) | diagnostic only — does **not** raise `nphase` |
| `ACTIVE_GAS_SPECIES` | `ACTIVE_GAS = 1` (`reaction_gas_aux.F90:15`) | sets `option%transport%nphase = 2` (`reaction.F90:103-105`), so a second mobile phase is transported |

The deprecated `GAS_SPECIES` card is redirected to `PASSIVE_GAS_SPECIES`
(`src/pflotran/reaction.F90:281-282`).

With `nphase = 2`, the gas contribution to the total component concentration is computed from
equilibrium partial pressures via the ideal-gas law: $c_g = p\cdot 10^5 / (R\,T_K)$ in mol/m³,
scaled by `1.d-3` to mol/L gas (`src/pflotran/reaction_gas.F90:140-153, 179-199`). That
$T_g$ then feeds `TFlux` (`src/pflotran/transport.F90:443-449`) and `RTAccumulation`
(`src/pflotran/reaction.F90:5512-5517`).

## 2. What `GAS_TRANSPORT_IS_UNVETTED` gates

This is a **mandatory acknowledgement token, not a switch.** It must be the *first* card inside
the `ACTIVE_GAS_SPECIES` block, and its absence is a fatal error:

```fortran
      case('ACTIVE_GAS_SPECIES')
        call InputReadPflotranString(input,option)
        call InputReadCard(input,option,word)
        call InputErrorMsg(input,option,'keyword', &
                           'CHEMISTRY,GAS_TRANSPORT_IS_UNVETTED')
        call StringToUpper(word)
        if (.not.StringCompare(word,'GAS_TRANSPORT_IS_UNVETTED')) then
          option%io_buffer = 'Before using gas transport capability, &
            &please acknowledge that gas transport is &
            &unvetted by adding the card GAS_TRANSPORT_IS_UNVETTED to the &
            &top of ACTIVE_GAS_SPECIES block.'
          call PrintErrMsg(option)
        endif
```
(`src/pflotran/reaction.F90:264-276`)

It sets **no variable**. The parser consumes the line and immediately calls
`ReactionGasReadGas(..., ACTIVE_GAS, ...)` (`src/pflotran/reaction.F90:277-280`). Grepping the
whole tree, `unvetted` appears **only** at `reaction.F90:268, 270, 273` — there is no flag, no
branch, no downstream consumer. Therefore:

> **`GAS_TRANSPORT_IS_UNVETTED` gates nothing computationally. It gates only the user: it is a
> compulsory opt-in string that makes the deck author state, in the deck, that they know active
> gas transport is not a verified capability at this commit.**

## 3. What is actually "unvetted" — the concrete gaps in the source

The keyword is undocumented upstream, so the source is the only authority. These are the
specific, citable limitations that a user is acknowledging:

1. **OSRT drops gas transport entirely.** The OSRT fixed accumulation is liquid-only
   (`iphase` is a hard parameter `= 1`, `src/pflotran/pmc_subsurface_osrt.F90:186, 272-276`);
   `RTCalculateRHS_t1` sets `iphase = 1` (`src/pflotran/reactive_transport.F90:1428`) and only
   adds `coef_up(:,1)` at boundaries (`src/pflotran/reactive_transport.F90:1475-1476`); and
   `RTCalculateTransportMatrix` passes only the first element of the `(naqcomp,nphase)`
   coefficient arrays to PETSc `MatSetValuesLocal`
   (`src/pflotran/reactive_transport.F90:1632-1635, 1688-1700, 1726-1731`) with a liquid-only
   accumulation term (`src/pflotran/reactive_transport.F90:1740-1752`). **No error is raised** —
   `MODE OSRT` with active gases silently transports only the aqueous phase.

2. **Under a single-phase flow mode there is no gas velocity.** `RICHARDS_MODE` assigns only
   `patch%internal_velocities(1,...)` and `patch%boundary_velocities(1,...)`
   (`src/pflotran/richards.F90:1523, 1688`). Those arrays are allocated with
   `nphase = max(option%nphase, option%transport%nphase)` and zeroed
   (`src/pflotran/patch.F90:781-785, 809-810`), so the gas-phase Darcy flux **stays exactly
   zero**. Meanwhile gas saturation *is* populated as $S_g = 1 - S_\ell$
   (`src/pflotran/richards_aux.F90:369-371`) and is flagged for update when
   `transport%nphase > 1` (`src/pflotran/global.F90:824-830`). Net effect: gas transport under
   Richards is **diffusion-only**, silently. Gas *density* is meanwhile an unsupported output
   variable for Richards (`src/pflotran/patch.F90:6517-6518`).

3. **The dry-cell test is on the liquid phase for both phases.** `TFluxCoef` returns zero for
   *both* phases if liquid saturation is below `rt_min_saturation`, with the explicit comment
   "as long as gas phase chemistry is a function of aqueous, skip both phases"
   (`src/pflotran/transport.F90:560-569`). In a nearly dry cell, gas transport is switched off
   because the *water* is gone.

4. **One-to-one gas↔primary mapping is required** whenever species-dependent diffusion is on:
   *"Active gas transport is not supported when gas species are not defined as a one to one
   match with the primary species [e.g. O2(aq) <-> O2(g)]."*
   (`src/pflotran/reactive_transport.F90:446-453`). Independently, `RTSetup` contains a check for
   an active gas associated with more than one aqueous species
   (`src/pflotran/reactive_transport.F90:325-334`) — but that block **composes
   `option%io_buffer` and never calls `PrintErrMsg`/`PrintMsg`**, so the condition is detected
   and then silently discarded. (The message text also contains a typo, `"Acdtive gas species"`,
   `src/pflotran/reactive_transport.F90:329`, which is further evidence the branch has never
   fired in practice.)

5. **`GAS_DIFFUSION_COEFFICIENTS` requires two transport phases** — declaring it without an
   active gas is fatal (`src/pflotran/reactive_transport.F90:409-414`) — and, symmetrically,
   `RTSetup` aborts if active gases exist while `nphase == 1`, telling the user to email the
   developers: *"The number of transport phases is set incorrectly for transport with active
   gases. Please email your input deck to pflotran-dev@googlegroups.com"*
   (`src/pflotran/reactive_transport.F90:161-169`). An error message that asks the user to mail
   the deck to the developers is itself a marker of an unvetted path.

6. **`EXPLICIT_ADVECTION` is incompatible**: `nphase > 1` is fatal
   (`src/pflotran/reactive_transport.F90:4367-4371`).

7. **The gas diffusion coefficient scaling is empirical and hard-coded** — the $T^{1.8}$
   exponent and the 101325 Pa reference are literals with no citation in-source
   (`src/pflotran/transport.F90:110, 144-154`), and the branch assumes `%pres(GAS_PHASE)` is
   total pressure (`src/pflotran/transport.F90:145-146`).

8. **`ACTIVE_GAS_SPECIES` is mandatory for certain databases** — `reaction_database.F90:1798`
   states "An ACTIVE_GAS_SPECIES block must be specified in ..." — so a user can be forced onto
   this path.

**Not verifiable statically:** whether these gaps have been exercised in the regression suite.
Decks under `regression_tests/` that contain the token (e.g.
`regression_tests/default/column/multiphase_transport_pulse.in`,
`regression_tests/default/batch/radon.in`,
`regression_tests/default/multicontinuum/1D_slab_gas.in`) confirm the capability is tested at
*some* level, but nothing in the source records which combinations are trusted.

---

## 4. Calibration knobs on this page

| Keyword | Block | Source line | Units | Default | Controls |
|---|---|---|---|---|---|
| `ACTIVE_GAS_SPECIES` | `CHEMISTRY` | `reaction.F90:264-280` | – | absent | raises `option%transport%nphase` to 2 (`reaction.F90:103-105`) — enables gas advection + diffusion + storage under GIRT |
| `GAS_TRANSPORT_IS_UNVETTED` | first card inside `ACTIVE_GAS_SPECIES` | `reaction.F90:270-276` | – | **mandatory whenever `ACTIVE_GAS_SPECIES` is present** | nothing computational — pure acknowledgement token |
| `PASSIVE_GAS_SPECIES` | `CHEMISTRY` | `reaction.F90:283-285` | – | absent | diagnostic gases only; does not add a transport phase |
| `GAS_SPECIES` | `CHEMISTRY` | `reaction.F90:281-282` | – | – | **deprecated**, redirected to `PASSIVE_GAS_SPECIES` |
| `GAS_DIFFUSION_COEFFICIENTS` | `CHEMISTRY` | `reaction.F90:236-262` | m²/s | absent | per-species gas $D^m$; fatal without an active gas (`reactive_transport.F90:409-414`); sets `ndiffcoef = naqcomp` |
| `DIFFUSION_COEFFICIENT` under `PHASE GAS` | `FLUID_PROPERTY` | `fluid.F90:106-115` | m²/s (converted) | `1.d-9` (`fluid.F90:58`) | the **only** `FLUID_PROPERTY` route to a gas-phase $D^m$ for RT |
| `GAS_DIFFUSION_COEFFICIENT` | `FLUID_PROPERTY` | `fluid.F90:131-134` | m²/s (no conversion) | `2.13d-5` (`fluid.F90:59`) | **not read by GIRT/OSRT** — only `sco2.F90:215`, `mphase_aux.F90:450` |

---

## 5. Related pages

- [`advection_dispersion_diffusion.md`](advection_dispersion_diffusion.md) — the dispersion and
  diffusion kernels these gas terms flow through.
- [`girt_and_operator_splitting.md`](girt_and_operator_splitting.md) — why OSRT drops the gas
  phase entirely.
