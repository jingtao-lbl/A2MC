**Source pin:** PFLOTRAN commit 157a26f7
**Scope:** Reaction sandbox plug-in mechanism, plus the built-in non-mineral kinetic networks (microbial, inhibition, immobile, general, radioactive decay)
**Last verified:** 2026-07-31

# Reaction Sandbox and the Other Kinetic Networks

Owning files: `src/pflotran/reaction_sandbox.F90` (396 lines, the registry/driver), `src/pflotran/reaction_sandbox_base.F90` (133, the abstract type), 15 `reaction_sandbox_<name>.F90` implementations, `src/pflotran/reaction_microbial.F90` (499), `src/pflotran/reaction_microbial_aux.F90` (425), `src/pflotran/reaction_inhibition.F90` (154), `src/pflotran/reaction_inhibition_aux.F90` (259), `src/pflotran/reaction_immobile.F90` (296), `src/pflotran/reaction_immobile_aux.F90` (417).

Every one of these contributes through the single dispatcher `RReaction` (`src/pflotran/reaction.F90:4104-4193`) and its derivative twin `RReactionDerivative` (`:4197-4254`).

---

## 1. The reaction sandbox plug-in

### 1.1 Deck entry point and the registry

Block keyword literal `REACTION_SANDBOX`, `src/pflotran/reaction.F90:457` (pass 1) → `RSandboxRead(input,option)` (`:458`), and `:1025` (pass 2) → `RSandboxSkipInput` (`:1026`).

The authoritative list of sandbox names is the `select case` in `RSandboxRead2`, `src/pflotran/reaction_sandbox.F90:130`, dispatch at `:162`. Copy these literals verbatim — they are the deck cards.

| Deck literal | Line | Factory function | Implementation file |
|---|---|---|---|
| `BIODEGRADATION_HILL` | `:164` | `BioHillCreate()` | `reaction_sandbox_biohill.F90` |
| `BIOPARTICLE` | `:166` | `BioTH_Create()` | `reaction_sandbox_bioTH.F90` |
| `CALCITE` | `:168` | `CalciteCreate()` | `reaction_sandbox_calcite.F90` |
| `CHROMIUM_REDUCTION` | `:170` | `ChromiumCreate()` | `reaction_sandbox_chromium.F90` |
| `CLM-CN` | `:172` | `CLM_CN_Create()` | `reaction_sandbox_clm_cn.F90` |
| `CYBERNETIC` | `:174` | `CyberCreate()` | `reaction_sandbox_pnnl_cyber.F90` |
| `EXAMPLE` | `:176` | `EXAMPLECreate()` | `reaction_sandbox_example.F90` |
| `EQUILIBRATE` | `:178` | `EquilibrateCreate()` | `reaction_sandbox_equilibrate.F90` |
| `FLEXIBLE_BIODEGRADATION_HILL` | `:180` | `FlexBioHillCreate()` | `reaction_sandbox_flexbiohill.F90` |
| `GAS` | `:182` | `ReactionGasCreateAux()` | `reaction_sandbox_gas.F90` |
| `LAMBDA` | `:184` | `LambdaCreate()` | `reaction_sandbox_pnnl_lambda.F90` |
| `RADON` | `:186` | `RadonCreate()` | `reaction_sandbox_radon.F90` |
| `SIMPLE` | `:188` | `SimpleCreate()` | `reaction_sandbox_simple.F90` |
| `UFD-WP` | `:190` | `WastePackageCreate()` | `reaction_sandbox_ufd_wp.F90` |

Fourteen registered names. Anything else errors with the context string `'CHEMISTRY,REACTION_SANDBOX'` (`:192-194`).

Note the file-to-module naming mismatches: `reaction_sandbox_pnnl_cyber.F90` declares `Reaction_Sandbox_Cyber_class` and `reaction_sandbox_pnnl_lambda.F90` declares `Reaction_Sandbox_Lambda_class`.

**`reaction_sandbox_pnnl_N.F90` is orphaned at this commit.** Its module `Reaction_Sandbox_PNNL_N_class` and factory `PNNL_NCreate` (`:100`) exist, but the file is not in `reaction_sandbox.F90`'s `use` list (`:6-20`), has no `case`, and is absent from the build object list (`src/pflotran/pflotran_object_files.txt:154-169`). It cannot be invoked from a deck.

After creation, `src/pflotran/reaction_sandbox.F90:197` calls the object's own reader:

```fortran
call new_sandbox%ReadInput(input,option)
```

so every sandbox owns its sub-keywords; there is no shared sub-keyword vocabulary.

### 1.2 The base class

`src/pflotran/reaction_sandbox_base.F90:12-21`:

```fortran
type, abstract, public :: reaction_sandbox_base_type
  class(reaction_sandbox_base_type), pointer :: next
contains
  procedure, public :: ReadInput => BaseReadInput
  procedure, public :: Setup => BaseSetup
  procedure, public :: Evaluate => BaseEvaluate
  procedure, public :: UpdateKineticState => BaseUpdateKineticState
  procedure, public :: AuxiliaryPlotVariables => BaseAuxiliaryPlotVariables
  procedure, public :: Destroy => BaseDestroy
end type reaction_sandbox_base_type
```

**None of the bindings is `deferred`.** They all point at concrete default implementations (`BaseSetup` `:27`, `BaseReadInput` `:42`, `BaseAuxiliaryPlotVariables` `:57`, `BaseEvaluate` `:74`, `BaseUpdateKineticState` `:104`, `BaseDestroy` `:125`), all empty no-ops except `BaseEvaluate`, which is the only one that enforces an override at runtime (`:96-98`):

```fortran
option%io_buffer = 'Subroutine BaseEvaluate must be extended by child &
  &Reaction Sandbox classes.'
call PrintErrMsg(option)
```

So `Evaluate` is the sole de-facto-mandatory procedure; everything else is optional. The procedure is named `Evaluate`, not `React` — child classes commonly bind their own `...React` routine to the `Evaluate` name.

### 1.3 Adding a new sandbox

Four edits, in this order:

1. Copy `src/pflotran/reaction_sandbox_example.F90` and rename module, type, and procedures. That file carries a numbered 12-step instruction walkthrough embedded as comments: step 1 at `:6`, 2 at `:20`, 3 at `:28`, 4 at `:57`, 5 at `:116`, 6 at `:118`, 7 at `:122`, 8 at `:125`, 9 at `:167`, 10 at `:257` (residual), 11 at `:272` (analytical Jacobian), 12 at `:304` (deallocate). It also embeds a sample deck snippet at `:118-129`.
2. Add `use <New>_class` to `src/pflotran/reaction_sandbox.F90:6-20`. The placeholder comment is at `:22`: `! Add new reacton sandbox classes here.` (typo is in the source).
3. Add the `case('<NAME>')` + `new_sandbox => <New>Create()` pair to `RSandboxRead2`'s select case at `src/pflotran/reaction_sandbox.F90:163`, under the comment `! Add new cases statements for new reacton sandbox classes here.`
4. Add the object file to `src/pflotran/pflotran_object_files.txt` (sandbox entries at `:154-169`). Note the `makefile` does not list objects itself — it includes that file at `src/pflotran/makefile:245-249`.

The example file's own instructions cover only step 1; steps 2–4 are not documented there. That omission is the usual reason a new sandbox silently fails to appear.

### 1.4 Where a sandbox is evaluated

`RSandboxEvaluate` (`src/pflotran/reaction_sandbox.F90:275`) walks the linked list and calls the polymorphic binding (`:308-310`). The call site inside the residual/Jacobian assembly is `src/pflotran/reaction.F90:4174-4178`:

```fortran
if (associated(rxn_sandbox_list)) then
  call RSandboxEvaluate(Res,Jac,compute_analytical_derivative, &
                        rt_auxvar,global_auxvar,material_auxvar, &
                        reaction,option)
endif
```

sitting between the immobile-decay contribution (`:4168`) and the carbon sandbox (`:4180`). Other lifecycle hooks: `RSandboxInit` (`src/pflotran/reaction.F90:95`), `RSandboxSetup` (`src/pflotran/reaction_setup.F90:775`), `RSandboxUpdateKineticState` (`src/pflotran/reaction.F90:5752`).

### 1.5 Build

**Sandboxes are compiled unconditionally.** `grep -n "#ifdef\|#if \|#ifndef" src/pflotran/reaction_sandbox*.F90` returns zero hits across all 17 files, and the object list at `src/pflotran/pflotran_object_files.txt:154-169` is unguarded. No build flag is needed to use any registered sandbox. (Contrast the double-layer output code, which *is* flag-gated — see `sorption_and_surface_complexation.md` §2.2.)

---

## 2. `MICROBIAL_REACTION`

Reader: `ReactionMicrobReadMicrobial`, `src/pflotran/reaction_microbial.F90`, entered from `src/pflotran/reaction.F90:466-467`. Rate evaluation: `ReactionMicrobRate`, `src/pflotran/reaction_microbial.F90:232-…`.

| Keyword | Line | Meaning |
|---|---|---|
| `REACTION` | `:65` | the stoichiometric equation as a free-form string |
| `CONCENTRATION_UNITS` → `MOLALITY` / `ACTIVITY` / `MOLARITY` | `:74`, `:80`/`:82`/`:84` | which concentration measure feeds the Monod and inhibition terms; must be consistent across all microbial reactions (`:91-96`) |
| `RATE_CONSTANT` | `:100` | see the warning below |
| `ACTIVATION_ENERGY` | `:106` | J/mol, converted (`:109-111`) |
| `MONOD` (block) | `:112` | one Monod term |
| `MONOD` / `SPECIES_NAME` | `:124` | the limiting species |
| `MONOD` / `HALF_SATURATION_CONSTANT` | `:129` | $K$ |
| `MONOD` / `THRESHOLD_CONCENTRATION` | `:133` | $C_{th}$ |
| `INHIBITION` (block) | `:152` | see §3 |
| `BIOMASS` (block) | `:165` | biomass coupling |
| `BIOMASS` / `SPECIES_NAME` | `:180` | aqueous or immobile biomass species |
| `BIOMASS` / `YIELD` | `:185` | mol biomass per mol reaction |

The rate (`src/pflotran/reaction_microbial.F90:385-396`):

$$R = k\,f_{\mathrm{Arr}}(T)\;\prod_{i}\frac{C_i - C_{th,i}}{K_i + C_i - C_{th,i}}\;\prod_{j} I_j\;\times B$$

```fortran
monod(ii) = (conc - microbial%monod_Cth(imonod)) / &
            (microbial%monod_K(imonod) + conc - microbial%monod_Cth(imonod))
...
rate = effective_rate_constant*monod_terms*inhibition_terms*biomass_term
do i = 1, ncomp
  icomp = microbial%specid(i,irxn)
  Res(icomp) = Res(icomp) - microbial%stoich(i,irxn)*rate
enddo
```

The biomass term $B$ carries the unit bookkeeping (`:355-381`): with no biomass it is `L_water` (mol L⁻¹ s⁻¹ → mol s⁻¹), with aqueous biomass it is `biomass_conc*L_water`, and with immobile biomass it is `biomass_conc*material_auxvar%volume`. `L_water = porosity * saturation * volume * 1.d3` (`:297-298`). So `RATE_CONSTANT` is in mol L⁻¹ s⁻¹ without biomass and mol (mol biomass)⁻¹ s⁻¹ with it — the in-source comments at `:305-307` and `:359-380` state exactly this. Arrhenius reference temperature is again hard-coded at 25 °C (`:278`).

**Source bug worth flagging.** `src/pflotran/reaction_microbial.F90:100-105`:

```fortran
case('RATE_CONSTANT')
  call InputReadDouble(input,option,microbial_rxn%rate_constant)
  call InputErrorMsg(input,option,word,'CHEMISTRY,MICROBIAL_REACTION')
  call InputReadAndConvertUnits(input,microbial_rxn%activation_energy, &
               '1/sec|mol/L-sec', &
               'CHEMISTRY,MICROBIAL_REACTION,RATE_CONSTANT',option)
```

The unit conversion is applied to `activation_energy`, not to `rate_constant`. Consequences: (a) a units word written after a microbial `RATE_CONSTANT` is **silently ignored** for the rate constant — the number is used raw, in internal units; (b) if `ACTIVATION_ENERGY` appears *before* `RATE_CONSTANT` in the same block, its value is multiplied by the rate-constant conversion factor and corrupted. `activation_energy` defaults to `0.d0` (`src/pflotran/reaction_microbial_aux.F90:151`), so the ordering hazard is inert unless activation energy is actually used. Compare the correct pattern in the same file at `:106-111` and in `reaction_immobile.F90:127-135`. Write microbial rate constants in internal units and put `ACTIVATION_ENERGY` after `RATE_CONSTANT`.

Unlike the mineral reader, there is **no negative-value-means-log₁₀ reinterpretation** for microbial, immobile, general, or radioactive-decay rate constants. That convention is unique to `ReactionMnrlReadRateConstant` (`src/pflotran/reaction_mineral.F90:561-564`).

Fixed array limits: `MAX_NUM_MONOD_TERMS` and `MAX_NUM_INHIBITION_TERMS` (`src/pflotran/reaction_microbial.F90:273-274`).

---

## 3. `INHIBITION` blocks

Shared by microbial reactions and some sandboxes. Reader: `ReactionInhibitionRead`, `src/pflotran/reaction_inhibition.F90`. Functions: `src/pflotran/reaction_inhibition_aux.F90`.

| Keyword | Line | Meaning |
|---|---|---|
| `SPECIES_NAME` | `reaction_inhibition.F90:57` | the inhibiting species |
| `TYPE MONOD` | `:66` | Monod-form inhibition |
| `TYPE THRESHOLD` | `:72` | arctangent step |
| `TYPE SMOOTHSTEP` | `:82` | smoothstep in log-concentration |
| `TYPE INVERSE_MONOD` | `:69` | **deprecated** → use `TYPE MONOD` + `INHIBIT_BELOW_THRESHOLD` |
| `THRESHOLD_CONCENTRATION` | `:96` | $C_{th}$ (stored in `inhibition_constant`) |
| `SCALING_FACTOR`, `SMOOTHSTEP_INTERVAL` | `:99` | second parameter (`inhibition_constant2`) |
| `INHIBIT_BELOW_THRESHOLD` | `:102` | direction |
| `INHIBIT_ABOVE_THRESHOLD` | `:104` | direction |
| `INHIBITION_CONSTANT` | `:106` | **deprecated** |

**The direction is encoded in the sign of the stored constant** (`src/pflotran/reaction_inhibition.F90:124-130`): `INHIBIT_ABOVE` negates it, `INHIBIT_BELOW` takes the absolute value. Every evaluator then branches on `threshold_concentration < 0.d0`. A direction card is **mandatory** for all three types (`:116-122`).

Forms as coded:

- **Monod** (`reaction_inhibition_aux.F90:92-101`): inhibit-above gives $I = C_{th}/(C_{th}+C)$; inhibit-below gives $I = C/(C_{th}+C)$.
- **Threshold** (`:154-162`): $I = 0.5 \mp \arctan\bigl[(C-C_{th})\,s\bigr]/\pi$, with $s$ = `SCALING_FACTOR`, defaulting to $10^5/|C_{th}|$ (`reaction_inhibition.F90:145-146`, and `reaction_inhibition_aux.F90:125`).
- **Smoothstep** (`:218-232`): a `Smoothstep` over $\log_{10}C$ across an interval centred on $\log_{10}|C_{th}|$, with `SMOOTHSTEP_INTERVAL` defaulting to `3.d0` log units (`reaction_inhibition.F90:148`, `reaction_inhibition_aux.F90:184`).

Smoothstep is the numerically friendliest of the three (continuous first derivative); the arctangent threshold with the default $s = 10^5/C_{th}$ is extremely stiff.

---

## 4. `IMMOBILE_SPECIES` and `IMMOBILE_DECAY_REACTION`

`IMMOBILE_SPECIES` (`src/pflotran/reaction.F90:287-288`) declares non-transported solid-phase species (biomass, sorbed inventories) carried per cell in `rt_auxvar%immobile`, in mol/m³ bulk.

`IMMOBILE_DECAY_REACTION` (`src/pflotran/reaction.F90:289-290` → `ReactionImDecayRxnRead`, `src/pflotran/reaction_immobile.F90`):

| Keyword | Line | Units |
|---|---|---|
| `SPECIES_NAME` | `reaction_immobile.F90:123` | — |
| `RATE_CONSTANT` | `:127` | `1/sec` internal, units word honoured correctly (`:130-133`) |
| `HALF_LIFE` | `:136` | `sec` internal; converted to a rate constant by $k=-\ln(0.5)/t_{1/2}$ (`:144-145`) |

One of `RATE_CONSTANT` or `HALF_LIFE` is mandatory (`:151-155`).

---

## 5. `RADIOACTIVE_DECAY_REACTION` and `GENERAL_REACTION`

Both parsed inline in `src/pflotran/reaction.F90`.

**`RADIOACTIVE_DECAY_REACTION`** (`:291`): sub-cards `REACTION` (`:307`), `RATE_CONSTANT` (`:316`, internal `unitless/sec`), `HALF_LIFE` (`:324`, internal `sec`, converted to $k = -\ln(0.5)/t_{1/2}$ at `:333-334`). One of the two is mandatory (`:340-344`).

**`GENERAL_REACTION`** (`:355`): sub-cards `REACTION`, `FORWARD_RATE` (`:429`) and `BACKWARD_RATE` (`:435`). The accepted unit family is a multi-alternative string (`:432-434`, `:438-440`):

```
'mol/L-sec|1/sec|L/mol-sec|L^2/mol^2-sec|L^3/mol^3-sec'
```

which reflects that the rate constant's dimensions depend on the reaction order. PFLOTRAN does **not** verify that the chosen unit matches the stoichiometry; picking the wrong alternative gives a silently wrong rate.

---

## 6. Calibration knobs summary

| Deck keyword | Source line | Units | Default | Physically controls |
|---|---|---|---|---|
| `MICROBIAL_REACTION` / `RATE_CONSTANT` | `reaction_microbial.F90:100` | mol L⁻¹ s⁻¹ (no biomass) or mol (mol biomass)⁻¹ s⁻¹ | `0.d0` (`reaction_microbial_aux.F90:150`) | overall microbial rate. **Units word is ignored — see §2** |
| `MICROBIAL_REACTION` / `ACTIVATION_ENERGY` | `reaction_microbial.F90:106` | J/mol | `0.d0` | Arrhenius T-sensitivity about 25 °C |
| `MONOD` / `HALF_SATURATION_CONSTANT` | `reaction_microbial.F90:129` | same measure as `CONCENTRATION_UNITS` | none | substrate limitation half-saturation |
| `MONOD` / `THRESHOLD_CONCENTRATION` | `reaction_microbial.F90:133` | same | 0 | concentration below which the term goes non-positive |
| `BIOMASS` / `YIELD` | `reaction_microbial.F90:185` | mol biomass per mol reaction | 0 | growth coupling |
| `CONCENTRATION_UNITS` | `reaction_microbial.F90:74` | enum | `MICROBIAL_MOLARITY` (`reaction_microbial.F90:224-225`) | whether Monod/inhibition see molality, molarity, or activity |
| `INHIBITION` / `THRESHOLD_CONCENTRATION` | `reaction_inhibition.F90:96` | concentration | none (required) | where the inhibition switch sits |
| `INHIBITION` / `SCALING_FACTOR` | `reaction_inhibition.F90:99` | 1/concentration | $10^5/\lvert C_{th}\rvert$ | sharpness of the arctangent threshold |
| `INHIBITION` / `SMOOTHSTEP_INTERVAL` | `reaction_inhibition.F90:99` | log₁₀ units | `3.d0` | width of the smoothstep transition |
| `IMMOBILE_DECAY_REACTION` / `RATE_CONSTANT` | `reaction_immobile.F90:127` | 1/s | none | first-order immobile decay |
| `IMMOBILE_DECAY_REACTION` / `HALF_LIFE` | `reaction_immobile.F90:136` | s | none | equivalent to the above |
| `RADIOACTIVE_DECAY_REACTION` / `RATE_CONSTANT` | `reaction.F90:316` | 1/s | none | decay rate |
| `RADIOACTIVE_DECAY_REACTION` / `HALF_LIFE` | `reaction.F90:325` | s | none | equivalent |
| `GENERAL_REACTION` / `FORWARD_RATE` | `reaction.F90:429` | order-dependent, see §5 | none | forward kinetic rate |
| `GENERAL_REACTION` / `BACKWARD_RATE` | `reaction.F90:434` | order-dependent | none | reverse kinetic rate |
| `REACTION_SANDBOX` / `<name>` | `reaction_sandbox.F90:164-191` | — | none | selects a plug-in; its own sub-keywords are defined by the implementation file |

## 7. Things I could not verify

- Whether the `RATE_CONSTANT` unit-conversion bug in `reaction_microbial.F90:103` is known upstream. It is present and unambiguous at this commit; I have not checked master.
- Sub-keyword vocabularies of the 14 individual sandboxes. Each owns its own `ReadInput` and would need to be read file by file; per the scope of this topic they are documented as a group only.
- Whether `reaction_sandbox_pnnl_N.F90` is deliberately parked or accidentally dropped from the registry and the build. Static reading shows only that it is unreachable.
