"""EcoSIM AI-prompt content.

`DOMAIN_SUMMARY` is prepended to A2MC reasoning prompts as a system-prompt prefix
so the calibration agent knows what model it is reasoning about. `ECOSIM_SPEC`
(spec.py) imports it as its `domain_summary`. `MECHANISM_GLOSSARY` gives the agent
concrete, source-grounded names for EcoSIM's distinctive mechanisms (from the
codebase-wiki audit findings at commit 2dea74d9).
"""

from __future__ import annotations


DOMAIN_SUMMARY = (
    "EcoSIM is a process-rich, microbially-explicit terrestrial ecosystem "
    "model (the Fortran-90 successor to Grant's ecosys), coupling soil-plant "
    "water, heat, and C/N/P cycling. Distinctive mechanisms: Campbell soil "
    "water retention with explicit Poiseuille macropore flow; Johnson-Lewin-"
    "Eyring (not Q10) microbial decomposition over a 5-complex x 4-kinetic-"
    "component SOM structure with 7 heterotroph + 6 autotroph functional "
    "groups; Langmuir (not Freundlich) P sorption; Grant-1989 Rubisco-kinetic "
    "photosynthesis with turgor-based stomatal stress and C4 PEP-to-bundle-"
    "sheath refixation; and stage-prescribed C allocation where maintenance "
    "respiration scales with structural N. Standalone Fortran driver; "
    "compile-time caps JZ=20 soil layers and JP=5 plant species."
)


# Concrete mechanism names the reasoning agent should use, mapped to a
# one-line description. Grounded in the 15 audit findings
# (memory/dev_logs/20260424g_EcoSIM_Codebase_Wiki_Rewrite.md).
MECHANISM_GLOSSARY = {
    "Campbell_Soil_Retention": "log-log Campbell water retention; SRP_vr exponent switches mineral/semi-organic/organic by C_org threshold",
    "Explicit_Macropore_Flow": "Poiseuille flow through explicit macropores (0.5 mm radius, T-dependent viscosity)",
    "Johnson_Lewin_Eyring_Decomposition": "Arrhenius decomposition with low/high-T inactivation (NOT Q10)",
    "Microbially_Explicit_Decomposition": "7 heterotroph + 6 autotroph functional groups over a 5-complex x 4-kinetic-component SOM pool",
    "Langmuir_P_Sorption": "Langmuir (not Freundlich) P sorption with both exchange sides in the denominator",
    "Grant_Rubisco_C3_Kinetics": "Grant-1989 Rubisco carboxylase/oxygenase kinetics for C3 photosynthesis",
    "PEP_C4_Refixation": "two-compartment C4 pathway with PEP-to-bundle-sheath CO2 refixation",
    "Turgor_Based_Stomatal_Stress": "stomatal stress via exp(-PSICanopyTurg/RCS_pft) turgor term, not Ball-Berry/Medlyn",
    "Stage_Prescribed_Allocation": "hard-coded partition fractions across 5 growth stages (not sink-source)",
    "Structural_N_Maintenance_Respiration": "maintenance respiration scales with structural N; non-structural reserves don't pay maintenance",
}
