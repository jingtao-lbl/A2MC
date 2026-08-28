"""Bayesian optimization for A2MC -- the SEARCH layer (`docs/42`).

A2MC ranks a completed ensemble. It has never had a way to ASK for the next point to run. This
package is that: propose the parameter sets most likely to put every validation target inside its
observational band at once, confirm them on the physics model, repeat.

WHAT IT IS NOT. It is not the surrogate (`models/surrogate/`), which EMULATES the model; this
decides where to spend the next run. It reuses that module's per-target GPs and viability
classifier rather than building a second modelling layer. And it is not the composite ranking in
`tools/optimize_function.py`, which answers "which completed case scored best" -- a different
question, kept for reporting.

MODULES, in the order `docs/42` section 6 builds them:

    objective.py   S0  the objective: v_i = |sim_i - obs_i| / (u_i * obs_i), V = max_i v_i,
                       where V <= 1 iff EVERY target is in band. Also the free disagreement
                       check against the composite A2MC ranks by today.
    bo_replay.py   S1  the GO/NO-GO gate: replay the propose loop against a COMPLETED ensemble
                       and measure whether it rediscovers a known optimum faster than random.
    acquisition.py S2  feasibility-weighted expected improvement (not built -- gated on S1)
    bo_loop.py     S3  propose -> run -> refit, with the three stopping rules (not built)

Nothing here is wired into `orchestrator.py`. `docs/42` section 6 S6 places the Phase-6 hook at
the END of the build, "only at this stage, when the capability is real".

Author: Jing Tao with Claude
"""
from .objective import (  # noqa: F401
    Target,
    compare_rankings,
    composite_rmsre,
    load_targets,
    violation,
    violation_matrix,
)

__all__ = [
    "Target",
    "compare_rankings",
    "composite_rmsre",
    "load_targets",
    "violation",
    "violation_matrix",
]
