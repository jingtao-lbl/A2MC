"""models.surrogate — learned emulators of a physics model's calibration targets.

NOT a model adapter. See README.md and docs/41 section 6.2: this package does
not implement ``ModelBackend`` and must not be registered in the model registry.

Typical use::

    from models.surrogate import S1Surrogate, SurrogateSpec, TargetSpec, Provenance
    from models.surrogate.validate import run_acceptance

    spec = SurrogateSpec(
        name="ecosim_biocon_r3", use_mode="offline_search", tier="S1",
        input_names=("VRNXI", "PPI"), input_lower=(45.0, 250.0),
        input_upper=(60.0, 420.0),
        targets=(TargetSpec("plant_C", observed=430.0, lower=424.0),
                 TargetSpec("NPP", observed=500.0, upper=529.0)),
        provenance=Provenance(model="ecosim",
                              scoring_convention="leap-calendar-v2.213"))
    model = S1Surrogate(spec).fit(X, Y, viable)
    report = run_acceptance(model, X_test, Y_test, Y_train=Y)
    print(report.summary())

    # The predicted mapping is interface-identical to evaluate_model_case's
    # `simulated`, so it feeds the existing cost layer unchanged:
    from tools.cost_functions import compute_snapshot_cost
    cost, errors = compute_snapshot_cost(model.simulated(x), observed)

Author: Jing Tao with Claude
"""

from .base import (
    BatchPrediction,
    HullGate,
    SurrogateModel,
    apply_transform,
    invert_transform,
)
from .learners import (
    CLASSIFIERS,
    GBMLearner,
    GPLearner,
    KnowledgeGuidedLoss,
    LEARNERS,
    Learner,
    MLPEnsembleClassifier,
    MLPEnsembleLearner,
    RFLearner,
    RidgeLearner,
    explain_recommendation,
    make_classifier,
    make_learner,
    recommend,
    recommend_goals,
)
from .environment import (
    EnvMismatch,
    capture_environment,
    check_environment,
    enforce_environment,
    read_environment,
)
from .splits import (
    SPLITTERS,
    Split,
    axis_split,
    block_split,
    levels_split,
    random_split,
    shell_split,
)
from .spec import (
    Provenance,
    SurrogateSpec,
    TargetSpec,
    hash_file,
    hash_param_list,
)
from .tiers import S0Surrogate, S1Surrogate, S2Surrogate, S3Surrogate, load
# `sequence` imports torch lazily inside its own methods, but importing the MODULE
# is still free, so the package keeps importing with no torch installed.
from .sequence import KGMLEmulator, load_kgml

__all__ = [
    "BatchPrediction",
    "CLASSIFIERS",
    "GBMLearner",
    "GPLearner",
    "HullGate",
    "KnowledgeGuidedLoss",
    "LEARNERS",
    "Learner",
    "MLPEnsembleClassifier",
    "MLPEnsembleLearner",
    "Provenance",
    "RFLearner",
    "RidgeLearner",
    "S0Surrogate",
    "S1Surrogate",
    "S2Surrogate",
    "S3Surrogate",
    "KGMLEmulator",
    "load_kgml",
    "SurrogateModel",
    "SurrogateSpec",
    "TargetSpec",
    "apply_transform",
    "explain_recommendation",
    "hash_file",
    "hash_param_list",
    "invert_transform",
    "load",
    "make_classifier",
    "make_learner",
    "recommend",
    "recommend_goals",
    "EnvMismatch",
    "capture_environment",
    "check_environment",
    "enforce_environment",
    "read_environment",
    "SPLITTERS",
    "Split",
    "axis_split",
    "block_split",
    "levels_split",
    "random_split",
    "shell_split",
]
