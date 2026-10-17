---
**Source pin:** EcoSIM commit `cb243228` (jingtao-lbl/EcoSIM `fix/r2-plant-balance`; upstream `09eb674a` + 2 fix commits) · patched to `0340d71b` (see the wiki `index.md`, Patches applied)
**Scope:** `f90src/Geochem/Box_chem/{ChemEquilibriaMod,SaltChemEquilibriaMod,InitSoluteMod}.F90`, `f90src/Geochem/Layers_chem/SoluteMod.F90`, `f90src/Modelpars/SoluteParMod.F90`; soil-chemistry inputs in `f90src/IOutils/readimod.F90` and `f90src/Ecosim_mods/StarteMod.F90`
**Last verified:** 2026-10-15
---

# Equilibria and Sorption

This page gives the equations as coded. Concentrations are mol m-3 of water; sorbed and precipitated amounts are mol per Mg of soil in the relevant zone (band or non-band). The solver returns fluxes in mol per grid area per hour, and `UpdateFertilizerBand` converts the dissolved ones to grams (`f90src/Geochem/Layers_chem/SoluteMod.F90:117-132`). Read `index.md` §4-§5 first: pH is prescribed, and on a fresh run the surface sites are zero.

## 1. Solver style and rate constants

The model does not solve a closed equilibrium system. Each reaction moves a fixed fraction per hour of the way toward its equilibrium (a pseudo-transient relaxation). The hourly orchestrator calls the solver once per hour, and `SolveChemEquilibria` iterates `MRXN = 1` times (`f90src/Geochem/Box_chem/SaltChemEquilibriaMod.F90:740`).

| Constant | Value | Units | Used for | Citation |
|---|---|---|---|---|
| `MRXN` | 1 | iterations | salt solver iterations per call | `f90src/Modelpars/SoluteParMod.F90:143` |
| `TPD`, `TPDX = TPD/MRXN` | 2.5e-3 | h-1 | precipitation and dissolution | `:144-145` |
| `TADA`, `TADAX` | 5.0e-2 | h-1 | anion (P) exchange; also Al(OH)2+ and Fe(OH)2+ carboxyl exchange in salt mode | `:146-147` |
| `TADC`, `TADCX` | 5.0e-2 | h-1 | cation exchange | `:148-149` |
| `TADC0` | 5.0e-4 | h-1 | NH4 exchange on the surface litter only (`f90src/Geochem/Layers_chem/SoluteMod.F90:1229`, `UpdateSurfResidueSolute`) | `:150` |
| `TSL`, `TSLX` | 0.5 | h-1 | aqueous dissociation | `:151-152` |

All are compile-time `PARAMETER`s. None is read from a file.

Every quadratic relaxation is written inline, in the form `S0 = A + B + K; S1 = max(0, S0**2 - 4*(A*B - K*C)); rate = T*(S0 - sqrt(S1))` (for example `f90src/Geochem/Box_chem/ChemEquilibriaMod.F90:424-427`). The helpers `A2BC_ChemReact_Quad` and `A2BC_ChemReact_Grad` in `GeoChemMathMod` (`f90src/Geochem/Box_chem/GeoChemMathMod.F90:13-61`) are not used anywhere.

## 2. Water, H+ and OH-

`DPH2O = 6.5e-9 mol2 m-6` (`f90src/Modelpars/SoluteParMod.F90:11`). In both solvers `[H+] = 10**(-(pH-3))` mol m-3 from the prescribed layer pH and `[OH-] = DPH2O/[H+]` (`f90src/Geochem/Box_chem/ChemEquilibriaMod.F90:278-280`; `f90src/Geochem/Box_chem/SaltChemEquilibriaMod.F90:1490-1491`, `:2626-2631`). See `index.md` §4.

## 3. Phosphate sorption: ligand exchange on surface hydroxyl sites

### 3.1 The site model

Anion exchange capacity (`XAEC`, from grid `AEC`) is held as surface hydroxyl sites in three protonation states, plus two sorbed phosphate forms (`f90src/Modelconfig/TracerIDMod.F90:351-356`):

| Tracer | Species | Solver variable |
|---|---|---|
| `idx_OHe` | `X-O-` | `XOH_mole_conc` |
| `idx_OH` | `X-OH` | `XROH1_mole_conc` |
| `idx_OHp` | `X-OH2+` | `XROH2_mole_conc` |
| `idx_HPO4` | `X-HPO4-` | `XHPO4_mole_conc` |
| `idx_H2PO4` | `X-H2PO4` | `XH2PO4_mole_conc` |

Band versions (`idx_OHeB` ... `idx_H2PO4B`) are tracked separately (`:358-362`). Concentrations are pool / soil mass of the zone (`f90src/Geochem/Layers_chem/SoluteMod.F90:424-428`, `:461-465`).

### 3.2 Equations (no-salt solver, `NoSaltChemEquilibria`)

With `VLWatMicPBK = min(1, SoilMass/WaterVolume)` (`f90src/Geochem/Box_chem/ChemEquilibriaMod.F90:267`) and the gate `XAEC > ZEROS` (`:377`):

```fortran
SPH2P = SXH2P*DPH2O                                                     ! :392
! X-H2PO4 + H2O <-> X-OH2+ + H2PO4-
H2PO4_1e_to_XH2PO4_ROH2_flx = TADA*(XROH2*[H2PO4-] - SPH2P*XH2PO4) &
                              /(XROH2 + SPH2P)*VLWatMicPBK               ! :393
! X-H2PO4 + OH- <-> X-OH + H2PO4-
H2PO4_to_XH2PO4_ROH_flx     = TADA*(XROH1*[H2PO4-] - SXH2P*[OH-]*XH2PO4) &
                              /(XROH1 + SXH2P)*VLWatMicPBK               ! :394
SPH1P = SXH1P*DPH2O/DPH2P                                               ! :404
! X-HPO4- + OH- <-> X-OH + HPO4--
H1PO4_to_XHPO4_ROH_flx      = TADA*(XROH1*[HPO4--] - SPH1P*XHPO4) &
                              /(XROH1 + SPH1P)*VLWatMicPBK               ! :405
```

A positive flux is sorption. The net site and sorbed-P changes are `RXH1 = -(H2PO4_to_XH2PO4_ROH + H1PO4_to_XHPO4_ROH)`, `RXH2 = -H2PO4_1e_to_XH2PO4_ROH2`, `RX1P = H1PO4_to_XHPO4_ROH`, `RX2P = H2PO4_1e_to_XH2PO4_ROH2 + H2PO4_to_XH2PO4_ROH` (`:714-717`), multiplied by the zone water volume (`:751-754`). The band zone uses the same forms with band concentrations (`:513-525`).

`SXH2P = SXH1P = 2.0e7` mol m-3 (`f90src/Modelpars/SoluteParMod.F90:23-24`). So `SPH2P = 0.13` mol m-3 and `SPH1P = SXH1P*DPH2O/DPH2P = 2.06e3` mol m-3 (with `DPH2P = 6.3e-5`, `:50`).

How to read this. It is mass-action ligand exchange on a finite pool of sites, and the denominator is (free sites + K). There is no Langmuir maximum or affinity coefficient to tune; the sorption capacity is the site pool that came from `AEC`, and the affinities are the compile-time `SXH2P`, `SXH1P`. **If the free sites `XROH1` and `XROH2` are zero, all three fluxes are zero whatever the solution P.** On a non-restart run at cb243228 they are zero in every layer (`index.md` §5).

The no-salt solver has no surface protonation step. It never converts `X-OH` to `X-OH2+` or `X-O-` as pH changes. Since pH is constant, the site speciation stays wherever initialisation left it.

### 3.3 Salt solver differences (`PhospAnionExchNoBand`, `PhospAnionExchBand`)

The salt solver uses activities in place of concentrations and the per-iteration rate `TADAX`. It also adds surface protonation, `X-OH2+ <-> X-OH + H+` with `SXOH2 = 4.5e-5` and `X-OH <-> X-O- + H+` with `SXOH1 = 1.1e-6` (`f90src/Modelpars/SoluteParMod.F90:21-22`):

```fortran
RXOH2 = TADAX*(XROH1*{H+} - SXOH2*XROH2)/(XROH1 + SXOH2)*VLWatMicPBK   ! SaltChemEquilibriaMod.F90:2004
RXOH1 = TADAX*(XOH*{H+}   - SXOH1*XROH1)/(XOH + SXOH1)*VLWatMicPBK     ! :2005
```

The P exchange forms match §3.2 with activities (`:2014-2026`; band `:2051-2073`). Both are gated on `VLWatMicPPO > ZEROS2 .and. XAEC > ZEROS` (`:2003`).

### 3.4 Initial site speciation (if it were reached)

`InitEquilibria` partitions `XAEC/BulkSoilMass` and the initial solution P between sites, sorbed P and solution by a closed-form quadratic. It uses the protonation fractions `FXH2`, `FXH1`, `FXH0` and the sorbed-form fractions `FXP2`, `FXP1` (`f90src/Geochem/Box_chem/InitSoluteMod.F90:507-536`, `K.EQ.micpar%k_POM` branch). `InitSoluteModel` then iterates `SolubilityEquilibriaNoSalt` or `SolubilityEquilibiriaSalt` 1000 times (`MRXN1`, `:220`, `:353-365`). This is the only code that creates surface sites, and `STARTE` never calls it with `K = k_POM` (`index.md` §5). In the salt initialiser, the HPO4 exchange uses the H2PO4 activity (`f90src/Geochem/Box_chem/InitSoluteMod.F90:1255`, `SolubilityEquilibiriaSalt`). This is a latent error that cannot matter while the branch is unreachable.

## 4. Phosphate precipitation and dissolution

### 4.1 No-salt solver

Al3+, Fe3+ and Ca2+ are not tracked; they come from mineral equilibria at the prescribed pH, capped by the grid inputs `CAL`, `CFE`, `CCA` when those are non-negative (`f90src/Geochem/Box_chem/ChemEquilibriaMod.F90:282-306`):

```fortran
[Al3+] = min(CAL, SPALO/[OH-]**3)          ! gibbsite          :285
[Fe3+] = min(CFE, SPFEO/[OH-]**3)          ! Fe(OH)3           :291
[CO3--] = [H2CO3]*DPCO3/[H+]**2                                 :297
[Ca2+] = min(CCA, SPCAC/[CO3--])           ! calcite (CCAMX if CCA<0)  :302-306
```

For each P mineral the equilibrium H2PO4- concentration is computed, and the flux is a relaxation of the current H2PO4- toward it:

| Mineral | Equilibrium H2PO4- | Constant (derived from) | Citation |
|---|---|---|---|
| AlPO4 (variscite) | `SYA0P2/([Al3+][OH-]**2)` | `SYA0P2 = SPALP/DPH1P/DPH2P*DPH2O**2` | `ChemEquilibriaMod.F90:322`; `SoluteParMod.F90:83`, `:92-93` |
| FePO4 (strengite) | `SYF0P2/([Fe3+][OH-]**2)` | from `SPFEP` | `ChemEquilibriaMod.F90:333`; `SoluteParMod.F90:102`, `:111-112` |
| CaHPO4 | `SYCAD2/([Ca2+][OH-])` | `SYCAD2 = SPCAD/DPH2P*DPH2O` | `ChemEquilibriaMod.F90:343`; `SoluteParMod.F90:120-121` |
| Ca5(PO4)3OH (apatite) | `(SYCAH2/([Ca2+]**5[OH-]**7))**0.333` | from `SPCAH` | `ChemEquilibriaMod.F90:355`; `SoluteParMod.F90:122-125` |
| Ca(H2PO4)2 | `sqrt(SPCAM/[Ca2+])` | `SPCAM` | `ChemEquilibriaMod.F90:366` |

```fortran
H2PO4_1e_AlPO4_dissol_flx = AMAX1(-Precp_AlPO4, TPD*([H2PO4-] - H2PO4_1e_AlPO4_eqv))   ! :323
```

Despite the name `..._dissol_flx`, a **positive value is precipitation**: it is subtracted from solution H2PO4 (`RHP2`, `:708-710`) and added to the precipitate (`TRChem_AlPO4_precip_soil`, `:756`). Dissolution is floored at minus the existing precipitate; for Ca(H2PO4)2 the floor is `-Precp*SPPO4` (`:367`). Apatite releases 3 H2PO4 per unit and Ca(H2PO4)2 releases 2 (`:710`). Precipitation needs no initial precipitate, so this pathway is live on a fresh run whenever solution P exceeds an equilibrium concentration. The band zone repeats every mineral with band H2PO4 and shares Al3+, Fe3+, Ca2+ and OH- with the non-band zone (`:452-489`).

### 4.2 Salt solver

`PhospPrecipDissolNonBand` (`f90src/Geochem/Box_chem/SaltChemEquilibriaMod.F90:984-1339`) and `PhospPrecipDissolBand` (`:1658-1978`) pick the dominant (highest-activity) metal species and the dominant phosphate species (HPO4 or H2PO4), then select the matching equilibrium constant (for AlPO4, `:993-1058`). The flux is a quadratic relaxation:

```fortran
SPX = SP*R1**NR1/P3**NP3;  S0 = P1 + P2;  S1 = max(0, S0**2 - 4*(P1*P2 - SPX))
H2PO4_1e_AlPO4_dissol_flx = AMAX1(-Precp_AlPO4, TPDX*(S0 - sqrt(S1)))      ! :1068-1071
```

The salt solver also handles gibbsite, ferric hydroxide, calcite and gypsum with the same dominant-species approach (`:748-921`).

### 4.3 Solubility products

| Name | Value | Reaction | Citation |
|---|---|---|---|
| `SPALO` | 6.5e-22 | Al(OH)3(s) = Al3+ + 3OH- | `f90src/Modelpars/SoluteParMod.F90:12` |
| `SPFEO` | 6.5e-27 | Fe(OH)3(s) = Fe3+ + 3OH- | `:13` |
| `SPCAC` | 3.8e-3 | CaCO3(s) = Ca2+ + CO3-- | `:14` |
| `SPCAS` | 14 | CaSO4(s) = Ca2+ + SO4-- | `:15` |
| `SPALP` | 1.0e-15 | AlPO4(s) = Al3+ + PO4--- | `:16` |
| `SPFEP` | 1.0e-20 | FePO4(s) = Fe3+ + PO4--- | `:17` |
| `SPCAM` | 7.0e7 | Ca(H2PO4)2(s) = Ca2+ + 2H2PO4- | `:18` |
| `SPCAD` | 0.1 | CaHPO4(s) = Ca2+ + HPO4-- | `:19` |
| `SPCAH` | 2.3e-31 | Ca5(PO4)3OH(s) = 5Ca2+ + 3PO4--- + OH- | `:20` |
| `CCAMX` | 10 mol m-3 | maximum Ca2+ | `:131` |

The derived constants for every protonation and hydroxo branch (`SHA*`, `SYA*`, `SHF*`, `SYF*`, `SHCA*`, `SYCA*`) are defined at `:62-125`.

## 5. Aqueous dissociation

| Reaction | No-salt form | Salt form | Constant |
|---|---|---|---|
| H2PO4- = H+ + HPO4-- | quadratic, rate `TSL` non-band (`f90src/Geochem/Box_chem/ChemEquilibriaMod.F90:424-427`), `TSLX` band (`:538-541`) | `SoluteDissociation` with activities | `DPH2P = 6.3e-5` (`f90src/Modelpars/SoluteParMod.F90:50`) |
| NH4+ = NH3 + H+ | `RNH4 = ([H+][NH3] - DPN4[NH4+])/(DPN4 + [H+])`, no rate constant (full step), capped by availability (`ChemEquilibriaMod.F90:672-689`) | same, times `TSLX` (`f90src/Geochem/Box_chem/SaltChemEquilibriaMod.F90:2208-2215`) | `DPN4 = 5.7e-7` (`SoluteParMod.F90:27`) |
| carbonate | `[CO3--] = [H2CO3]*DPCO3/[H+]**2` only to set [Ca2+] | full CO2-HCO3-CO3 set | `DPCO2 = 4.2e-4`, `DPHCO = 5.6e-8` (`:25-26`) |
| Al, Fe hydrolysis; Al, Fe, Ca, Mg, Na, K sulfate, carbonate and phosphate complexes; carboxyl exchange | none | `SoluteDissociation` (`f90src/Geochem/Box_chem/SaltChemEquilibriaMod.F90:2178-2466`); carboxyl `COOH = COO- + H+` and Al(OH)2+, Fe(OH)2+ on carboxyl sites (`:2192-2202`) | `SoluteParMod.F90:28-60` |

`TSL` and `TSLX` are equal only while `MRXN = 1`. The no-salt NH4/NH3 step applies the full equilibrium shift each hour, while the salt step applies half (`TSLX = 0.5`).

## 6. Activity corrections (salt solver only)

Ionic strength `I = 0.5e-3*(9*(C3+A3) + 4*(C2+A2) + (C1+A1))`, where the `1e-3` converts mol m-3 to mol L-1 (`f90src/Geochem/Box_chem/SaltChemEquilibriaMod.F90:1571-1572`). The activity coefficients are

```fortran
A1 = min(1, 10**(-0.509*1*sqrt(I)/(1+sqrt(I)) + 0.20*sqrt(I)))      ! :1579
A2 = min(1, 10**(-0.509*4*sqrt(I)/(1+sqrt(I)) + 0.20*sqrt(I)))      ! :1580
A3 = min(1, 10**(-0.509*9*sqrt(I)/(1+sqrt(I)) + 0.20*sqrt(I)))      ! :1581
```

This is an extended Debye-Hückel form, not the Davies equation: the correction term is `0.20*sqrt(I)`, not multiplied by `z**2`, where Davies uses `0.3*z**2*I`. Neutral species use `A0 = 1` (`f90src/Modelpars/SoluteParMod.F90:129`). The no-salt solver uses concentrations, with no activity correction.

## 7. Cation exchange (Gapon)

Both solvers compute an equilibrium exchangeable Ca from CEC and the Gapon selectivities against Ca:

```fortran
! no-salt, concentrations (ChemEquilibriaMod.F90:608-613)
XCAX = CEC_conc/(1 + (GKC4*[NH4+]*VLNH4 + GKC4*[NH4+]band*VLNHB + GKCH*[H+]
                      + GKCA*[Al3+]**0.333 + GKCA*[Fe3+]**0.333 + GKCM*[Mg2+]**0.5
                      + GKCN*[Na+] + GKCK*[K+])/[Ca2+]**0.5)
XN4Q = XCAX*[NH4+]*GKC4                                        ! :617
RXN4 = TADC*max(min((XN4Q - XNH4)*[NH4+]/XN4Q, [NH4+]), -XNH4)  ! :652, after FX = CEC_conc/XTLQ rescaling :639-645
```

The no-salt solver computes an exchange flux only for NH4 (band and non-band, `:652-653`). The salt solver uses activities, divides the Al and Fe equilibria by 3 and Ca and Mg by 2 after rescaling, and computes fluxes for H, Al, Fe, Ca, Mg, Na and K as well (`f90src/Geochem/Box_chem/SaltChemEquilibriaMod.F90:2107-2159`). Ca-Al and Ca-Fe share `GKCA` (`:2113-2114`).

The Gapon coefficients `GKC4`, `GKCH`, `GKCA`, `GKCM`, `GKCN`, `GKCK` are per-layer grid inputs (`f90src/IOutils/readimod.F90:516-521`), passed in by `GeochemAPISend` (`f90src/APIs/GeochemAPI.F90:224-230`). They act only where `XCEC > ZEROS` (`ChemEquilibriaMod.F90:558`). On a fresh run that is soil layer 1 only (`index.md` §5).

## 8. Fertilizer bands

`UpdateFertilizerBand` (`f90src/Geochem/Layers_chem/SoluteMod.F90:61-135`) computes the net vertical water flux per area, `FLWD = 0.5*(WaterFlowSoiMicP_3D(3,L) + WaterFlowSoiMicP_3D(3,L+1))/AREA_3D(3,L)` (`:78`), and updates the NH4, NO3 and PO4 bands (`:82-90`). For PO4 (`UpdatePO4FertilizerBandinfo`, `:615-842`), when a band exists and reaches the layer (`:630-631`):

- Width grows by `DWPO4 = 0.5*sqrt(SoluteDifusvtyT_vr(ids_H1PO4))*TortMicPM_vr` per hour, capped at the row spacing (`:639-640`).
- Depth moves by `FLWD + DWPO4` (`:647-650`). Excess thickness spills to the layer below (`:651-654`), and negative thickness is handed to the layer above (`:655-659`).
- Band volume fraction is `min(0.999, width/rowspacing*thickness/DLYR)`; the non-band fraction is the complement (`:672-679`).
- As the band grows, solution, sorbed and precipitated P move from non-band to band in proportion to `FVLPO4 = min(0, (VLN_new - VLN_old)/VLN_old)` (`:680`, transfers `:688-785`; salt-tracer variant `:688-753`).
- When the band disappears, band pools are merged back into the non-band pools (`:786-840`).

## 9. Calibration-relevant inputs: source map

No calibration parameters are assigned to this topic; the solver constants are compile-time. The file-read inputs that feed the geochemistry are all grid-file variables read in `readTopoNC` (`f90src/IOutils/readimod.F90:483-521`, unit conversions `:800-820`):

| File name | Fortran variable | Read at | Use sites at cb243228 | Live? |
|---|---|---|---|---|
| `PH` (and `PH0`, litter) | `PH_vr` | `readimod.F90:483` (`:441`) | `GeochemAPISend` (`f90src/APIs/GeochemAPI.F90:162`) -> `[H+]` in both solvers; `MicAPISend` (`f90src/APIs/MicBGCAPI.F90:243`) | **live** in every layer; constant in time |
| `CEC` | `CEC_vr` (x10, `readimod.F90:800`) | `:485` | `trcx_solml_vr(idx_CEC) = max(CNH4, CEC)*mass`, layer 1 only (`f90src/Ecosim_mods/StarteMod.F90:124`, `starte`) | **live only in soil layer 1** on a fresh run |
| `AEC` | `AEC_vr` (x10, `:801`) | `:486` | `trcx_solml_vr(idx_AEC) = max(CPO4, AEC)*mass`, layer 1 only (`StarteMod.F90:125`); in the solvers only as the gate `XAEC > ZEROS` | **inert**: sites are never created (`index.md` §5) |
| `GKC4`, `GKCH`, `GKCA`, `GKCM`, `GKCN`, `GKCK` | `GKC*_vr` | `:516-521` | `GeochemAPISend` (`GeochemAPI.F90:224-230`) -> `NoSaltChemEquilibria` (`ChemEquilibriaMod.F90:608-613`) or `CationExchange` (`SaltChemEquilibriaMod.F90:2111-2124`); litter uses layer `NU` (`SoluteMod.F90:1205-1209`) | live where CEC > 0 (layer 1 on a fresh run; litter) |
| `CAL`, `CFE`, `CCA` | `CAL_vr` (/27), `CFE_vr` (/56), `CCA_vr` (/40) | `:497-499` | caps on [Al3+], [Fe3+], [Ca2+] in the no-salt solver (`ChemEquilibriaMod.F90:282-306`); not used by the salt solver | **live in no-salt mode**: they set the P-mineral equilibria. Units: the cap is compared with a mol m-3 water concentration, but `CAL_vr` is mol per Mg soil after conversion. |
| `CPO4` | `CPO4_vr` (/patomw) | `:495` | AEC floor and the layer-1 solution value that is copied into rain chemistry (`StarteMod.F90:125`, `:145`) | **inert for soil P** on a fresh run |
| `CNH4`, `CNO3` | `CNH4_vr`, `CNO3_vr` | `:493-494` | CEC floor and layer-1 rain chemistry (`StarteMod.F90:124`, `:126`, `:144`) | inert for soil N on a fresh run |
| `CALPO`, `CFEPO`, `CCAPD`, `CCAPH` | `CALPO_vr` ... (/patomw; apatite /3patomw) | `:507-510` | `solutevar%CALPOX` ... (`StarteMod.F90:135-138`) -> `InitEquilibria` precipitates, `K = k_POM` branch only (`InitSoluteMod.F90:571-579`) | **inert** on a fresh run |
| `CALOH`, `CFEOH`, `CCACO`, `CCASO` | `CALOH_vr` ... | `:511-514` | `StarteMod.F90:139-142` -> same unreachable branch | **inert** on a fresh run |

"Fresh run" means `continue_run = .false.` and empty `finidat`. A restart carries whatever pools its restart file holds.

## 10. Known code issues

| Issue | Citation |
|---|---|
| Soil chemistry initial state unreachable in `STARTE` (commented `ELSEIF`) | `f90src/Ecosim_mods/StarteMod.F90:96-161`, `:323` |
| `GeoChemMathMod` helpers never used | `f90src/Geochem/Box_chem/GeoChemMathMod.F90:13-61` |
| No-salt H2PO4 dissociation uses `TSL` non-band and `TSLX` band | `f90src/Geochem/Box_chem/ChemEquilibriaMod.F90:427`, `:541` |
| Salt initialiser HPO4 exchange uses H2PO4 activity | `f90src/Geochem/Box_chem/InitSoluteMod.F90:1255` |
| `GeochemAPIRecv` adds NH4 fluxes but assigns P fluxes | `f90src/APIs/GeochemAPI.F90:269-276` |
| Header comment: the no-salt model omits H3PO4 | `f90src/Geochem/Box_chem/ChemEquilibriaMod.F90:6-7` |
| AEC and CEC conversion comment says cmol kg-1; x10 of meq/100 g gives mmol kg-1 (= mol Mg-1) | `f90src/IOutils/readimod.F90:484`, `:800-801` |

## Cross-references

- Call chain, pH sources, the initialisation evidence: `index.md`.
- One-box harness for this solver: `../drivers/aquachem.md`.
- Plant P uptake that draws on the same solution P: `../plant_bgc/roots_and_uptake.md`.
