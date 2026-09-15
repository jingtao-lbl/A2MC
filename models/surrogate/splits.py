"""How a surrogate's held-out set is CHOSEN, and what each choice can and cannot prove.

THE GAP THIS CLOSES. Every surrogate built for A2MC so far was scored on a uniform random hold-out
from the same scrambled Sobol' lattice it trained on. That measures INTERPOLATION INSIDE ONE POINT
SET and nothing else: train and test are draws from an identical distribution, so a model that has
memorised the lattice's local structure scores as well as one that has learned the response. The
number is not wrong, it answers an easier question than the one a reader assumes it answers, and
nothing in the code said so. The split kind was a hand-typed string in one driver script.

So every splitter here RETURNS ITS OWN DESCRIPTION, including what it is optimistic about, and that
string is what belongs in `acceptance.json["split_kind"]`. A description nobody can forget to write
is the point of the module.

WHAT EACH ONE ACTUALLY TESTS

    random      interpolation within the lattice. The easiest question. Optimistic, always.
    block       a contiguous run of the sequence. Intended as a neutral CONTROL and MEASURED NOT
                TO BE ONE: a tail block is EASIER than a random hold-out (see block_split).
    axis        extrapolation along ONE NAMED parameter: train on the lower part of its range,
                predict the top quintile. This is the question a calibration search actually asks
                when it pushes a parameter past where it has sampled.
    shell       extrapolation away from the centre of the whole cube, by mean absolute deviation.
    levels      whole values of a label are withheld -- the years of a driver series, a site, a
                treatment. For a driver-conditioned emulator this is THE test, because it is the
                only one that asks about conditions the model never saw.

A CAVEAT ON `shell` THAT IS EASY TO MISS AND WOULD MAKE IT MEANINGLESS. The natural definition of
an outer shell is the Chebyshev radius, max_j |x_j - 1/2|. In 54 dimensions essentially every point
has one coordinate near an edge, so that radius is about 1/2 for the entire ensemble and the split
degenerates into a random one while LOOKING like an extrapolation test. `shell` therefore uses the
MEAN absolute deviation across coordinates, which still concentrates (its spread falls as
1/sqrt(d)) but retains a real ordering. Even so, in high dimensions `shell` is a weak
extrapolation test and `axis` is the honest one. Both are provided; the docstring is the warning.

Author: Jing Tao with Claude on Perlmutter
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Optional, Sequence, Tuple

import numpy as np


@dataclass(frozen=True)
class Split:
    """Train and test row indices, plus the sentence that must go in the acceptance report."""

    train: np.ndarray
    test: np.ndarray
    kind: str
    description: str
    #: What this split CANNOT rule out. Never empty: every split is optimistic about something.
    optimistic_about: str

    def __post_init__(self) -> None:
        if len(np.intersect1d(self.train, self.test)):
            raise ValueError(f"{self.kind}: train and test overlap, which makes the score a lie")
        if len(self.test) == 0:
            raise ValueError(f"{self.kind}: empty test set")
        if len(self.train) == 0:
            raise ValueError(f"{self.kind}: empty training set")

    @property
    def n_train(self) -> int:
        return len(self.train)

    @property
    def n_test(self) -> int:
        return len(self.test)

    def to_dict(self) -> Dict[str, Any]:
        return {"kind": self.kind, "description": self.description,
                "optimistic_about": self.optimistic_about,
                "n_train": self.n_train, "n_test": self.n_test}

    def __str__(self) -> str:
        return f"{self.kind}: {self.n_train} train / {self.n_test} test -- {self.description}"


def _check_fraction(f: float) -> None:
    if not 0.0 < f < 1.0:
        raise ValueError(f"test_fraction must be in (0, 1), got {f}")


def random_split(n: int, test_fraction: float = 0.2, seed: int = 0) -> Split:
    """Uniform random hold-out. What every A2MC surrogate has used, and the weakest of these."""
    _check_fraction(test_fraction)
    perm = np.random.default_rng(seed).permutation(n)
    k = max(1, int(round(n * test_fraction)))
    # NOT sorted. `fit_ensemble_surrogate.py` produced its splits as raw permutation slices, and
    # a tree ensemble's bootstrap draws row INDICES, so re-ordering the training rows changes the
    # fitted trees. Sorting here would have silently invalidated every acceptance report already
    # on disk while looking like a tidy-up.
    return Split(train=perm[k:], test=perm[:k], kind="random",
                 description=(f"uniform random hold-out of {test_fraction:.0%} from the same "
                              f"lattice, seed {seed}"),
                 optimistic_about=("everything outside the sampled lattice. Train and test are "
                                   "draws from one distribution, so this measures interpolation "
                                   "inside the design and says nothing about extrapolation"))


def block_split(n: int, test_fraction: float = 0.2, position: str = "tail") -> Split:
    """A contiguous run of the sequence. Intended as a neutral control; measured to be EASIER.

    THE REASONING THIS WAS WRITTEN WITH, AND WHY IT WAS WRONG. A scrambled Sobol' sequence is
    constructed so that any prefix is itself well distributed, so a tail block was expected to score
    about the same as a random hold-out and to serve as the control that shows the harder splits are
    measuring a real shift.

    MEASURED on EcoSIM_Lusignan R1b (4,096 points, 54 parameters, RF, seed 20260912), Spearman rho
    of predicted against true distance-to-observation, random against tail block:

        GPP   0.582 -> 0.655        Reco  0.584 -> 0.634        ET  0.491 -> 0.518

    The tail block is EASIER on all three targets, by 0.03 to 0.07. The explanation is the same
    property that makes the sequence extensible: each new point fills a gap between existing ones,
    so the LAST 20% of a Sobol' sequence is the subset most thoroughly surrounded by the first 80%.
    Holding it out is close to the easiest hold-out available, not a neutral one.

    So do not read a good block score as reassurance, and do not use this as the control it was
    built to be. It remains useful for one narrow question: whether anything in the pipeline depends
    on sequence POSITION, which nothing else here would reveal.
    """
    _check_fraction(test_fraction)
    if position not in ("head", "tail"):
        raise ValueError(f"position must be 'head' or 'tail', got {position!r}")
    k = max(1, int(round(n * test_fraction)))
    idx = np.arange(n)
    test = idx[-k:] if position == "tail" else idx[:k]
    train = idx[:-k] if position == "tail" else idx[k:]
    return Split(train=train, test=test, kind=f"block_{position}",
                 description=(f"contiguous {position} block of {test_fraction:.0%} of the "
                              f"sequence"),
                 optimistic_about=("MORE than a random split, not the same: a Sobol' sequence's "
                                   "later points fill gaps between its earlier ones, so a tail "
                                   "block is the subset most surrounded by training data. Measured "
                                   "0.03-0.07 HIGHER rank correlation than random on "
                                   "EcoSIM_Lusignan R1b. Not an extrapolation test and not a "
                                   "neutral control"))


def axis_split(X: np.ndarray, axis: int, test_fraction: float = 0.2,
               side: str = "upper", axis_name: Optional[str] = None) -> Split:
    """Withhold the extreme tail of ONE parameter. The honest extrapolation test in high dimensions.

    Train on the rest of the range of parameter ``axis`` and predict its top (or bottom) tail. This
    is the question a calibration search asks the moment it proposes a value beyond what has been
    run, and it is the one question a random hold-out cannot answer at all.
    """
    _check_fraction(test_fraction)
    if side not in ("upper", "lower"):
        raise ValueError(f"side must be 'upper' or 'lower', got {side!r}")
    X = np.atleast_2d(np.asarray(X, dtype=float))
    if not 0 <= axis < X.shape[1]:
        raise ValueError(f"axis {axis} out of range for {X.shape[1]} parameters")
    col = X[:, axis]
    q = np.quantile(col, 1.0 - test_fraction if side == "upper" else test_fraction)
    mask = col >= q if side == "upper" else col <= q
    name = axis_name or f"parameter {axis}"
    return Split(train=np.flatnonzero(~mask), test=np.flatnonzero(mask),
                 kind=f"axis_{side}",
                 description=(f"withheld the {side} {test_fraction:.0%} of {name} "
                              f"(cut at {q:.6g}); the model never saw that part of its range"),
                 optimistic_about=(f"extrapolation along every parameter OTHER than {name}, and "
                                   f"any interaction that only appears there"))


def shell_split(X: np.ndarray, test_fraction: float = 0.2,
                lower: Optional[Sequence[float]] = None,
                upper: Optional[Sequence[float]] = None) -> Split:
    """Train on the interior of the cube, predict the outer shell.

    Read the module docstring before using this in high dimensions: the radius is the MEAN absolute
    deviation from the centre, not the Chebyshev radius, because the latter is about 1/2 for every
    point once there are tens of parameters and would silently degrade into a random split.
    """
    _check_fraction(test_fraction)
    X = np.atleast_2d(np.asarray(X, dtype=float))
    lo = np.asarray(lower, dtype=float) if lower is not None else X.min(axis=0)
    hi = np.asarray(upper, dtype=float) if upper is not None else X.max(axis=0)
    span = np.where(hi > lo, hi - lo, 1.0)
    U = (X - lo) / span
    radius = np.abs(U - 0.5).mean(axis=1)
    q = np.quantile(radius, 1.0 - test_fraction)
    mask = radius >= q
    return Split(train=np.flatnonzero(~mask), test=np.flatnonzero(mask), kind="shell",
                 description=(f"outer {test_fraction:.0%} by mean |x - 1/2| over {X.shape[1]} "
                              f"normalised parameters (cut at {q:.4f}); trained on the interior"),
                 optimistic_about=("less than a random split, but in high dimensions this radius "
                                   "concentrates, so the shift between interior and shell is "
                                   "small. Prefer axis_split for a decisive extrapolation test"))


def levels_split(labels: Sequence[Any], held: Sequence[Any]) -> Split:
    """Withhold whole values of a label: years, sites, treatments.

    For a driver-conditioned emulator this is the test that matches its claim. An emulator says it
    has learned the model's response to weather rather than one weather history; holding out entire
    YEARS of the driver series and predicting them is the only split that asks that directly.
    """
    labels = np.asarray(labels)
    held_arr = np.asarray(list(held))
    if held_arr.size == 0:
        raise ValueError("levels_split needs at least one level to withhold")
    unknown = [h for h in held_arr if h not in set(labels.tolist())]
    if unknown:
        raise ValueError(f"levels {unknown} do not appear in labels; nothing would be withheld")
    mask = np.isin(labels, held_arr)
    shown = ", ".join(str(h) for h in held_arr)
    return Split(train=np.flatnonzero(~mask), test=np.flatnonzero(mask), kind="levels",
                 description=(f"withheld whole levels [{shown}] of the label; they appear nowhere "
                              f"in training"),
                 optimistic_about=("levels outside the range of those present. Withholding a year "
                                   "inside the record tests interpolation between years, not a "
                                   "climate the record does not contain"))


#: Every splitter, so a driver can loop over them and a report can name them consistently.
SPLITTERS = {
    "random": random_split,
    "block": block_split,
    "axis": axis_split,
    "shell": shell_split,
    "levels": levels_split,
}
