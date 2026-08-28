# ATS Knowledge Base

Source-grounded knowledge inputs for the A2MC **ATS** adapter (`models/ats/`). ATS is the
[Advanced Terrestrial Simulator](https://github.com/amanzi/ats) — a C++ integrated
surface-subsurface hydrology model built on the Amanzi multiphysics framework.

## Contents

| Path | What it is |
|---|---|
| `ats-codebase-wiki-42b0e940/` | Commit-pinned codebase wiki (47 Markdown topics) covering flow/energy PKs, constitutive relations, operators, the multi-process coupler, executables, and the **`elm_ats_api` coupling boundary**. |
| `wiki_source_validation_42b0e940.md` | V1 wiki↔source validation record for the wiki. |

## Pin

- **ATS commit:** `42b0e940` (`ats-1.7-dev-22-g42b0e940`)
- **Wiki generated:** 2026-05-06
- **Upstream:** https://github.com/amanzi/ats
- **Coupled workspace:** https://github.com/amanzi/COMPASS-ELM-ATS (ELM-ATS via CIME)

## Notes

- ATS is built as part of Amanzi; this wiki documents **ATS source only** (Amanzi internals are out of scope).
- Start at `ats-codebase-wiki-42b0e940/index.md`; `UNIVERSAL_CONTEXT.md` is the shared preamble.
- The `07_executables_elm_ats_api/elm_ats_api.md` topic documents the ELM→ATS C API (the calibratable soil-hydrology knobs pass through it) and is the key entry point for coupled ELM-ATS work.

## Provenance

Relocated into the repo from `~/Desktop/Work/ELM-ATS-RDycore/ATS-knowledge-base/` on 2026-07-27
as Step 3 of the `onboard-model` arc for ATS. See
`memory/dev_logs_adapterkit/20260727c_Scoping_ATS_Onboarding_Exploration.md`.
