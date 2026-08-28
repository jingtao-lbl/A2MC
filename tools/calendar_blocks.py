"""Leap-aware calendar blocking for model history tapes — one implementation, shared.

Models that run a REAL Gregorian calendar write 366 records in a leap year. Blocking such a tape
with a fixed 365 slips a day per leap year and silently drops the tail: over 2000-2022 that is 6
records lost and every year boundary after 2000 off by up to 6 days. Nothing crashes; the numbers
are just quietly attributed to the wrong years.

EcoSIM is such a model (`reference_ecosim_uses_real_leap_calendar`): `EcoSIMTimeMod` sets
`leap_yr = isLeapi(year0)` and steps `doy = mod(doy, 365+leap_yr)`, and there is no no-leap switch
in the `&ecosim_time` namelist. (`get_days_per_year()` hardwires 365 but is DEAD CODE with no
caller — do not cite it as evidence of a no-leap calendar.) ELM/FATES, by contrast, genuinely uses
a 365-day no-leap calendar, so a caller for those models should NOT use this module.

Written 2026-08-16 because the logic existed in three places and one of them was wrong:
  * `models/ecosim/backend.py::_year_blocks` — correct, but a NESTED function, so unimportable.
  * `tools/plot_sim_vs_obs_timeseries_ecosim_biocon.py` — correct, inline, ~20 lines.
  * `scripts/extract_and_plot_adapter_ensemble.py` — `n // 365` in ALL THREE panels, i.e. wrong.
The third is what this module exists to fix without adding a fourth copy.
"""
from __future__ import annotations

import calendar
from typing import List, Optional, Sequence, Tuple

import numpy as np


def year_blocks(n_records: int, start_year: int, per_day: int = 1
                ) -> List[Tuple[int, int, int]]:
    """Split `n_records` into whole calendar years as ``(year, lo, hi)`` index triples.

    `per_day` is records per day (1 daily, 24 hourly). An incomplete trailing year is DROPPED,
    matching `models/ecosim/backend.py`: a partial year is not a year, and averaging one silently
    changes the statistic.
    """
    if n_records <= 0 or per_day <= 0:
        return []
    blocks, lo, y = [], 0, int(start_year)
    while True:
        n = (366 if calendar.isleap(y) else 365) * per_day
        if lo + n > n_records:
            break
        blocks.append((y, lo, lo + n))
        lo += n
        y += 1
    return blocks


def tag_hourly(n_records: int, start_year: int
               ) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Label each record of an HOURLY series with ``(year, month, hour_of_day)``.

    Feeds `tools.subdaily_window_reduce.growing_season_window_mean_abs`, which needs those three
    axes to select a growing-season daytime window. Raises if the record count is not a multiple
    of 24, because a non-hourly tape reaching this function means the caller picked the wrong tape
    and would otherwise get a plausible-looking wrong answer.
    """
    if n_records % 24:
        raise ValueError(f"{n_records} records is not a multiple of 24, so this is not an hourly "
                         f"tape. Check the target's `tape:` — an h0 daily tape has already "
                         f"averaged the diel cycle away, so a daytime window is meaningless on it.")
    ndays = n_records // 24
    yr = np.empty(n_records, dtype=int)
    mo = np.empty(n_records, dtype=int)
    hod = np.empty(n_records, dtype=int)
    day, y = 0, int(start_year)
    while day < ndays:
        dpy = 366 if calendar.isleap(y) else 365
        take = min(dpy, ndays - day)
        cum = np.cumsum([0] + [calendar.monthrange(y, m)[1] for m in range(1, 13)])
        month_per_day = np.searchsorted(cum, np.arange(take), side="right")
        sl = slice(day * 24, (day + take) * 24)
        yr[sl] = y
        mo[sl] = np.repeat(month_per_day, 24)
        hod[sl] = np.tile(np.arange(24), take)
        day += take
        y += 1
    return yr, mo, hod


def growing_season_day_slice(year: int, season_months: Tuple[int, int] = (5, 9)
                             ) -> Tuple[int, int]:
    """Day-of-year [lo, hi) for `season_months` in `year`, leap-aware.

    Replaces the hardcoded ``gs=(120, 273)`` default, which is May-Sep for a NON-leap year only
    and is off by one day in every leap year.
    """
    m0, m1 = season_months
    lengths = [calendar.monthrange(year, m)[1] for m in range(1, 13)]
    lo = sum(lengths[:m0 - 1])
    hi = sum(lengths[:m1])
    return lo, hi
