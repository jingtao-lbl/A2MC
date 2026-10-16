"""`season_sum` differences a resetting cumulative; it must not average it.

visibility: public

WHY THIS REDUCE EXISTS. EcoSIM's scored ecosystem fluxes -- `ECO_GPP_col`, `ECO_RA_col`,
`ECO_RH_col`, `ECO_ET_col` -- are WITHIN-YEAR CUMULATIVES that reset each 1 January. That is
already why `year_end` picks the last record of each year rather than summing. A seasonal objective
on the same variables therefore has to take a DIFFERENCE at month boundaries, and a mean over the
season's records returns roughly where the run was on average rather than what it accumulated.
The rule is `calibration-discipline` item 3c: pick the reduction from each variable's own temporal
semantics, never from its name or its units.

WHAT MAKES THESE TESTS ABLE TO FAIL, which is the point:

  * `test_seasons_partition_the_year` is the strong one. The four seasons must sum to EXACTLY the
    annual total, because they partition the calendar year. An averaging implementation fails it by
    orders of magnitude, and so does any off-by-one at a month boundary.
  * `test_an_average_would_give_a_different_answer` computes what the wrong implementation would
    return and asserts the right one does NOT return it -- so the suite cannot pass while the reduce
    silently means.
  * `test_leap_year_boundaries_shift` asserts the February boundary MOVES in a leap year. A fixed
    365-day blocking passes every other test here and fails this one.

Author: Jing Tao with Claude Code.
"""
from __future__ import annotations

import calendar
import sys
from pathlib import Path

import numpy as np
import pytest

REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

START_YEAR = 1996
N_YEARS = 3            # 1996 (leap), 1997, 1998


def _daily_increments(year: int) -> np.ndarray:
    """A deliberately non-flat daily increment, so a mean and a difference cannot coincide."""
    n = 366 if calendar.isleap(year) else 365
    doy = np.arange(n, dtype=float)
    # A seasonal cycle plus a floor: large in summer, small in winter, never zero.
    return 1.0 + 9.0 * np.sin(np.pi * doy / n) ** 2


def _cumulative_series() -> tuple[np.ndarray, dict[int, np.ndarray]]:
    """A within-year cumulative that RESETS each 1 January, as EcoSIM writes."""
    chunks, incs = [], {}
    for y in range(START_YEAR, START_YEAR + N_YEARS):
        inc = _daily_increments(y)
        incs[y] = inc
        chunks.append(np.cumsum(inc))        # resets: each year starts from its own first day
    return np.concatenate(chunks), incs


def _expected_season_total(incs: dict[int, np.ndarray], year: int, season: str) -> float:
    """Independent reference: sum the daily increments of the season's months directly."""
    blocks = {"DJF": ((1, 2), (12, 12)), "MAM": ((3, 5),), "JJA": ((6, 8),), "SON": ((9, 11),)}
    lengths = [calendar.monthrange(year, m)[1] for m in range(1, 13)]
    out = 0.0
    for (m0, m1) in blocks[season]:
        lo = sum(lengths[:m0 - 1])
        hi = sum(lengths[:m1])
        out += float(incs[year][lo:hi].sum())
    return out


@pytest.fixture(scope="module")
def backend():
    from models.ecosim.backend import EcoSIMBackend
    return EcoSIMBackend()


def _reduce(backend, series, season, years=(START_YEAR, START_YEAR + N_YEARS - 1)):
    target = {"variable": "ECO_GPP_col", "season": season,
              "window_years": [years[0], years[1]], "start_year": START_YEAR}
    return backend.reduce_ecosystem({"ECO_GPP_col": series}, target, "season_sum")


# --- the reduce returns the season's accumulation ---------------------------------------------
@pytest.mark.parametrize("season", ["DJF", "MAM", "JJA", "SON"])
def test_season_total_matches_an_independent_sum(backend, season):
    series, incs = _cumulative_series()
    got = _reduce(backend, series, season)
    want = float(np.mean([_expected_season_total(incs, y, season)
                          for y in range(START_YEAR, START_YEAR + N_YEARS)]))
    assert got == pytest.approx(want, rel=1e-10), f"{season}: {got} != {want}"


def test_seasons_partition_the_year(backend):
    """The strong invariant: the four seasons sum to the annual total, exactly.

    An averaging implementation misses this by orders of magnitude; an off-by-one at any month
    boundary misses it by a day's increment.
    """
    series, incs = _cumulative_series()
    four = sum(_reduce(backend, series, s) for s in ("DJF", "MAM", "JJA", "SON"))
    annual = float(np.mean([incs[y].sum() for y in range(START_YEAR, START_YEAR + N_YEARS)]))
    assert four == pytest.approx(annual, rel=1e-10), f"seasons {four} != annual {annual}"


def test_it_agrees_with_year_end_on_the_annual_total(backend):
    """Cross-check against the reduce already in production, on the same series."""
    series, _ = _cumulative_series()
    four = sum(_reduce(backend, series, s) for s in ("DJF", "MAM", "JJA", "SON"))
    ye = backend.reduce_ecosystem(
        {"ECO_GPP_col": series},
        {"variable": "ECO_GPP_col", "window_years": [START_YEAR, START_YEAR + N_YEARS - 1],
         "start_year": START_YEAR}, "year_end")
    assert four == pytest.approx(ye, rel=1e-10)


# --- the controls: these fail if the reduce ever means, or ignores leap years ------------------
def test_an_average_would_give_a_different_answer(backend):
    """Without this the suite could pass on an implementation that averages.

    Computes what the WRONG reduce returns and asserts the real one does not return it.
    """
    series, incs = _cumulative_series()
    got = _reduce(backend, series, "JJA")
    # The wrong implementation: mean of the cumulative's records over the season.
    wrong = []
    for y in range(START_YEAR, START_YEAR + N_YEARS):
        lengths = [calendar.monthrange(y, m)[1] for m in range(1, 13)]
        lo, hi = sum(lengths[:5]), sum(lengths[:8])
        off = sum(366 if calendar.isleap(k) else 365 for k in range(START_YEAR, y))
        wrong.append(float(np.mean(series[off + lo:off + hi])))
    wrong_mean = float(np.mean(wrong))
    assert abs(got - wrong_mean) / max(abs(got), 1e-12) > 0.05, (
        f"season_sum returned {got}, indistinguishable from the averaging answer {wrong_mean}")


def test_leap_year_boundaries_shift(backend):
    """A fixed 365-day blocking passes the other tests and fails this one.

    1996 is a leap year and 1997 is not, so the same season has a different number of days and a
    different total. Asserting they DIFFER pins the leap awareness.
    """
    series, incs = _cumulative_series()
    djf_96 = _reduce(backend, series, "DJF", years=(1996, 1996))
    djf_97 = _reduce(backend, series, "DJF", years=(1997, 1997))
    assert calendar.isleap(1996) and not calendar.isleap(1997)
    assert djf_96 != pytest.approx(djf_97, rel=1e-9), (
        "DJF is identical in a leap and a non-leap year -- the blocking is not leap-aware")


def test_an_unknown_season_is_refused(backend):
    series, _ = _cumulative_series()
    with pytest.raises(ValueError, match="season"):
        _reduce(backend, series, "SUMMER")


def test_the_reduce_is_REGISTERED(backend):
    """An unregistered reduce does not error -- it falls through to the snapshot path and returns
    the last record of the WHOLE tape, which for a cumulative is a plausible-looking wrong number.
    """
    from tools.model_evaluate_case import ECOSYSTEM_REDUCES
    assert "season_sum" in ECOSYSTEM_REDUCES
