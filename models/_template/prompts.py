"""Template AI-prompt content — copy + fill in for your model.

A2MC's reasoning agents use a model-specific domain summary as a system-prompt
prefix when reasoning about parameter calibration, hypothesis generation, etc.
The summary tells the AI what it's looking at: the model's purpose, scope,
mechanistic structure, key terminology.

For FATES, the equivalent file is currently `reasoning/prompts.py` (will move
to `models/fates/prompts.py` during Step E generalization). The FATES summary
covers: cohort-based vegetation demography, size-structured competition,
PARTEH allocation, CNP cycling, ECA nutrient competition, the major
mechanistic processes by name.

After copying this template:
    1. Replace the TODO blocks with real domain content
    2. Keep the summary to ~150–250 words. AI calibration agents use it as a
       prefix to almost every prompt; verbosity hurts.
"""

from __future__ import annotations


DOMAIN_SUMMARY = """
TODO(adapter-kit): one-paragraph summary of your model.

Should cover:
    - What the model simulates (e.g., 'cohort-based vegetation demography')
    - Major coupled subsystems (e.g., 'photosynthesis, allocation, nutrient
      cycling, hydraulics')
    - Calibration-relevant mechanisms by name (e.g., 'PID controller for C:N:P
      allocation, ECA nutrient competition, cold-deciduous phenology')
    - Coupling context if relevant (e.g., 'runs as a vegetation submodel
      under ELM/CESM Earth system models')

This text is auto-prepended to AI calibration prompts, so be concrete and
mechanism-rich rather than literary.

Target length: 150-250 words. The framework's spec.domain_summary defaults
to this string; for short adapters, the spec field can hold the summary
directly without this dedicated module.
""".strip()


# TODO(adapter-kit): if your model has additional prompt patterns (e.g.,
# pre-canned hypothesis templates, common diagnostic-question framings,
# domain-specific jargon dictionaries), add them as constants here. The
# reasoning module imports them as needed.
