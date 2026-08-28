"""ATS AI-prompt context — single source of truth for the domain summary.

Imported by spec.py (`domain_summary=DOMAIN_SUMMARY`) so the reasoning agent and
the curated-YAML bootstrap share one description of ATS's scope.

Grounded in the ATS codebase wiki (`docs/ats-knowledge-base/ats-codebase-wiki-42b0e940/`,
commit `42b0e940`) and the upstream input spec (amanzi.github.io/ats).
"""

from __future__ import annotations

DOMAIN_SUMMARY = (
    "ATS (the Advanced Terrestrial Simulator) is a C++ integrated surface-subsurface "
    "hydrology model built on the Amanzi multiphysics framework. It solves the Richards "
    "equation in the variably-saturated subsurface coupled to overland (Manning) flow at "
    "the surface, on unstructured prismatic meshes via mimetic finite differences, with a "
    "block-preconditioned Newton (BDF) time integrator. Optional physics add thermal energy "
    "(including freeze-thaw for permafrost), evapotranspiration, snow, surface energy balance, "
    "deformation, and reactive transport. The model is organized as Process Kernels (PKs) glued "
    "by a Multi-Process Coupler (MPC); physical behavior is set by constitutive relations "
    "(water-retention/WRM, equations of state) and their parameters. Configuration is a nested "
    "Trilinos/Teuchos ParameterList XML input deck (the 'Amanzi spec'): calibration-relevant "
    "knobs — van Genuchten/Brooks-Corey water-retention parameters, porosity, permeability, "
    "Manning's roughness, and Priestley-Taylor ET parameters — are named <Parameter> entries "
    "scattered across the deck and keyed per mesh region, with physical units embedded in the "
    "parameter name (e.g. 'van Genuchten alpha [Pa^-1]'). Calibration targets are exposed through "
    "the deck's 'observations' block as comma-delimited time series (water content, runoff, "
    "evaporation/transpiration partition, water-table depth). ATS can also be driven as a library "
    "by ELM through the elm_ats_api C interface for coupled ELM-ATS land-hydrology simulations."
)

# ATS-specific reasoning hints, appended to diagnosis/hypothesis prompts when relevant.
CALIBRATION_HINTS = (
    "- Water-retention (van Genuchten alpha/n, residual saturation), porosity, and permeability "
    "are the primary controls on subsurface water storage and drainage.\n"
    "- Manning's coefficient controls surface/overland flow velocity and thus runoff timing.\n"
    "- Priestley-Taylor alpha and rooting-depth max control the ET partition.\n"
    "- Parameters are region-keyed: the same physical knob appears once per mesh region/material, "
    "so a calibration knob must be addressed by its full ParameterList path, not just its leaf name.\n"
    "- A perturbed parameter set can break BDF/Richards solver convergence; a non-converged run is a "
    "solver failure, not a model result, and must be distinguished from a completed run.\n"
    "- A target must be pre-declared in the deck's observations block or ATS will not emit it."
)
