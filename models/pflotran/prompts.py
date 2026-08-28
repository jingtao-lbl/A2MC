"""PFLOTRAN AI-prompt content.

`DOMAIN_SUMMARY` is prepended to A2MC reasoning prompts as a system-prompt
prefix so the calibration agent knows what model it is reasoning about.
`PFLOTRAN_SPEC` (spec.py) imports it as its `domain_summary`.
`MECHANISM_GLOSSARY` gives the agent concrete, source-grounded names for
PFLOTRAN's distinctive mechanisms; the keys match `mechanisms:` in
`curated_seed.yaml` so the two surfaces cannot drift apart.

`CALIBRATION_CAUTIONS` is deliberately included and is NOT decoration. The
single largest risk to a PFLOTRAN calibration is not a missing mechanism, it is
a plausible-sounding assumption about a knob's units, scope or independence.
The v0.1 curated seed was ~20 % wrong in exactly that way
(`memory/dev_logs_adapterkitpflotran/20260801a`), so the traps that survived
verification are put in front of the agent rather than left for it to rediscover
from retrieved chunks.

Author: Jing Tao with Claude
"""

from __future__ import annotations


DOMAIN_SUMMARY = (
    "PFLOTRAN is a massively parallel, PETSc-based reactive multiphase flow and "
    "transport code for subsurface porous media. It solves variably saturated "
    "flow (GENERAL mode: liquid + gas + energy) coupled to multicomponent "
    "reactive transport, and is configured entirely through a free-form, nested "
    "CARD DECK rather than a namelist or NetCDF parameter file. Distinctive "
    "mechanics: transition-state-theory mineral kinetics with an evolving "
    "reactive surface area that feeds back on porosity and permeability; "
    "global-implicit reactive transport (GIRT) that solves chemistry and "
    "transport together; van Genuchten / Mualem characteristic curves carried as "
    "SEPARATE parameter copies per sub-block; equilibrium aqueous speciation "
    "against an external thermodynamic database that also supplies molar volume "
    "and molar weight; and mass-balance output written as a fixed-width "
    "'*-mas.dat' tape rather than a NetCDF history file. There is no PFT axis -- "
    "the organizing dimension is the mesh REGION, and boundary fluxes are "
    "reported per named coupler."
)


# Mechanism names the reasoning agent should use. Keys mirror `mechanisms:` in
# models/pflotran/curated_seed.yaml.
MECHANISM_GLOSSARY = {
    "TST_Mineral_Kinetics":
        "transition-state-theory rate = -(reactive area) x (affinity factor) x "
        "(rate constant); TWO routines exist (SIMPLE and COMPLEX) and the deck "
        "selects between them implicitly",
    "Reactive_Surface_Area_Evolution":
        "specific surface area evolves with porosity and/or mineral volume "
        "fraction; the porosity factor uses the SOLID fraction, so its sign of "
        "effect is opposite to the naive reading of its name",
    "Porosity_Permeability_Feedback":
        "mineral volume change updates porosity ABSOLUTELY (1 - sum of volume "
        "fractions), and porosity rescales permeability through a thresholded "
        "power law with a lower clamp; it is NOT Kozeny-Carman",
    "Van_Genuchten_WRM":
        "Pc = (Se^(-1/m) - 1)^(1/n) / alpha with n = 1/(1-m) DERIVED from m",
    "Mualem_Relative_Permeability":
        "liquid and gas relative permeability from the retention curve, each "
        "carrying its OWN copies of m and residual saturation",
    "GIRT_Reactive_Transport":
        "global-implicit reactive transport: chemistry and transport solved "
        "together, as opposed to operator-split OSRT",
    "Advection_Dispersion_Diffusion":
        "Darcy advection + mechanical dispersion + molecular diffusion, "
        "optionally scaled by Millington-Quirk tortuosity sat^(7/3) x phi^(1/3)",
    "Seepage_Face_Boundary":
        "DIRICHLET_SEEPAGE one-way outflow face; the clamp is armed by the BC "
        "TYPE, not by any saturation value",
    "Aqueous_Speciation":
        "equilibrium speciation of primary components into secondary species, "
        "setting the ion activity products the rate law compares against",
    "Timestep_Control":
        "timestep sizing and cutting; MAX_TS_CUTS is a PER-TIMESTEP consecutive "
        "budget, and a genuine failure exits with status 88",
}


# Traps that survived adversarial source verification. Each one is a mistake a
# competent calibrator would otherwise make. Full statements + citations live in
# models/pflotran/curated_seed.yaml.
CALIBRATION_CAUTIONS = (
    "A NEGATIVE RATE_CONSTANT means log10(k), not a negative rate. Sample it in "
    "log space; a linear range crossing zero switches interpretation mid-ensemble.",

    "A mineral's surface_area units depend on an OPTIONAL trailing token. With "
    "no token the value is read as m^2 per m^3 BULK; with a mass token it is "
    "converted AND multiplied by that row's own volume fraction, which makes "
    "surface_area and vol_frac dependent rather than independent knobs.",

    "With UPDATE_POROSITY set, the deck's POROSITY card is NOT the operative "
    "porosity. The operative value is 1 - sum(mineral volume fractions); the "
    "card sets the reference phi_0 that persists as a denominator in both the "
    "permeability scaling and the surface-area ratio.",

    "van Genuchten m and residual saturation appear at THREE deck addresses "
    "(saturation function, liquid rel-perm, gas rel-perm) with separate storage. "
    "Write all three together, or decouple them deliberately. Nothing warns you: "
    "the one consistency check composes a message it never prints.",

    "PFLOTRAN does not reliably range-check parameters, and LOOP_INVARIANT is a "
    "deck card rather than a build flag. ENFORCE BOUNDS AT SAMPLING TIME.",

    "Boundary/coupler output columns are POSITIVE INTO the domain, so outflow is "
    "negative -- but do not apply that as a blanket rule. Read each column's "
    "measured sign; a component whose TOTAL is itself negative (H+) exports with "
    "a positive flux.",

    "Before adopting an output as a calibration target, verify the column "
    "actually VARIES, in both distinct-value count and relative range. A "
    "constant column is not a weak target, it is zero information, and it will "
    "score as perfectly fitted.",

    "A large lifetime timestep-cut count is NOT a failed run. MAX_TS_CUTS is a "
    "per-timestep consecutive budget; the real failure signal is exit status 88.",
)
