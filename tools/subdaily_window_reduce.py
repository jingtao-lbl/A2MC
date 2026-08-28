#!/usr/bin/env python
"""Growing-season, fixed-hour-window mean — a model-agnostic array reducer.

Generalizes the one-off analysis in ``use_cases/EcoSIM_BioCON/memory/phase_results/
20260809d_diel_ratio/compute_diel_ratio.py`` (the `Fs` daytime-bias sizing) into a reusable
function: given ANY sub-daily time series plus per-record hour/month/year tags, compute the
mean of |values| within a fixed hour-of-day window and a season, per year, then averaged
across years.

Deliberately takes plain arrays, not a file path or a model's tape format. The caller resolves
its own calendar (a model backend, e.g. ``models/ecosim/backend.py``, knows its own leap-year
handling and record cadence) into the four same-length arrays this function needs; this module
owns none of that and stays reusable for any model with a sub-daily history tape. This is the
"reusable module + thin backend hook" split (PI, 2026-08-09): the model backend's
``reduce_ecosystem`` should call this rather than re-implement the window/season selection
inline for each model.

WHY A FIXED HOUR WINDOW, NOT A PER-SERIES-DERIVED ONE: a window centred on (or derived from)
the very series being reduced is circular -- it is, by construction, close to the highest-mean
window of that width available for that series (see
``use_cases/EcoSIM_BioCON/memory/logs/20260809d_*.md``,
[[feedback_a_check_that_cannot_fail]]). ``window_hours`` here must come from something
independent of the reduced series itself (radiation, a campaign protocol, a fixed clock
convention) -- this module does not care what that source was, it just takes the resulting
hour list as a caller-supplied constant.

Author: Jing Tao with Claude
"""
from __future__ import annotations

from typing import Optional, Sequence, Tuple

import numpy as np


def growing_season_window_mean_abs(
    values: np.ndarray,
    hour_of_day: np.ndarray,
    month: np.ndarray,
    year: np.ndarray,
    *,
    window_hours: Sequence[int],
    season_months: Tuple[int, int] = (5, 9),
    window_years: Optional[Tuple[int, int]] = None,
) -> float:
    """Mean of ``|values|`` over ``window_hours``, within ``season_months``, averaged per
    year then across years -- "a growing-season mean, sampled at these hours, control mean
    over these years", which is what a daytime-sampled observation over a multi-year record is.

    Args:
        values: 1-D array, one value per timestep (sub-daily; any regular cadence).
        hour_of_day, month, year: 1-D arrays, SAME LENGTH as ``values``, one tag per
            timestep. The caller computes these from its own calendar (e.g. leap-aware
            day-of-year -> month, index % records_per_day -> hour_of_day).
        window_hours: the fixed set of hour-of-day values to keep (e.g. ``range(16, 22)``
            for an h16-21 inclusive window). Not derived from ``values`` -- see module
            docstring for why.
        season_months: inclusive ``(first_month, last_month)``, e.g. ``(5, 9)`` for May-Sep.
        window_years: inclusive ``(first_year, last_year)`` to average over; ``None`` uses
            every year present in ``year``.

    Returns:
        The scalar mean. Raises ``ValueError`` if the window+season selects zero records in
        any requested year, or if no years are available at all.
    """
    values = np.asarray(values, dtype=float)
    hour_of_day = np.asarray(hour_of_day)
    month = np.asarray(month)
    year = np.asarray(year)
    if not (values.shape == hour_of_day.shape == month.shape == year.shape):
        raise ValueError(
            f"values/hour_of_day/month/year must be the same shape, got "
            f"{values.shape}, {hour_of_day.shape}, {month.shape}, {year.shape}")

    window_hours = set(int(h) for h in window_hours)
    if not window_hours:
        raise ValueError("window_hours is empty")
    m0, m1 = season_months

    in_window = np.isin(hour_of_day, list(window_hours))
    in_season = (month >= m0) & (month <= m1)
    keep = in_window & in_season

    years_present = sorted(set(int(y) for y in year))
    if window_years is not None:
        y0, y1 = window_years
        scored_years = [y for y in years_present if y0 <= y <= y1]
        if not scored_years:
            raise ValueError(
                f"window_years {window_years} selects no year (data covers "
                f"{years_present[0]}-{years_present[-1]})" if years_present else
                f"window_years {window_years} selects no year (no years in data)")
    else:
        scored_years = years_present
        if not scored_years:
            raise ValueError("no years found in `year`")

    per_year = []
    for y in scored_years:
        seg = values[keep & (year == y)]
        if seg.size == 0:
            raise ValueError(
                f"growing_season_window_mean_abs: window_hours={sorted(window_hours)} x "
                f"season_months={season_months} selects no records in year {y}")
        per_year.append(np.nanmean(np.abs(seg)))

    return float(np.nanmean(per_year))
