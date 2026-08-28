"""Regression tests for the ecosystem-level target reductions in
``tools.model_evaluate_case._reduce_ecosystem`` (plot-scale targets: sum-over-PFT,
per-PFT-rate integration, sign-agnostic flux mean, depth-integral guard).

Synthetic arrays with known answers — no dependency on a real EcoSIM tape.
Distilled from the EcoSIM_BioCON control-target wiring (dev log 20260715c).
"""
import numpy as np
import pytest

from tools.model_evaluate_case import reduce_target, _resolve_backend

SPVAL = 1e30


def _be():
    # any backend with the default select_group_series works; ecosim is registered.
    return _resolve_backend("ecosim")


def test_sum_pft_peak_sums_over_pft_and_vars_masking_spval():
    """Σ over PFTs and vars → per-year peak → MEAN over years (bb48f19), masking spval.

    The fixture spans TWO 365-record blocks because that IS the reduction's current contract:
    it returns the mean of ANNUAL peaks, not a single window maximum (the window-max version
    over-scored any config with a transient spike). A sub-year fixture cannot express that,
    which is why the guard below rejects one.

    NB the 365 here mirrors the implementation, which is itself a KNOWN DEFECT for EcoSIM:
    EcoSIM runs a real Gregorian calendar, so a daily tape has 366 records in a leap year
    (BioCON 2000-2022 = 8401 records, not 8395). See the note in `models/ecosim/backend.py`.
    When that is fixed, this fixture should move to real calendar years.
    """
    b = _be()
    n_yr, ndays = 2, 365                    # matches the implementation's fixed-365 blocking
    # 5 PFT slots; slots 3,4 unused = spval (masking check). Baseline total(t) = 3 + 2 = 5.
    shoot = np.tile(np.array([1, 2, 0, SPVAL, SPVAL], float), (n_yr * ndays, 1))
    root = np.tile(np.array([1, 1, 0, SPVAL, SPVAL], float), (n_yr * ndays, 1))
    # One growing-season peak per year, at different heights, so the mean-of-peaks is testable.
    shoot[200], root[200] = [3, 4, 0, SPVAL, SPVAL], [2, 2, 0, SPVAL, SPVAL]        # yr0 peak = 7+4 = 11
    shoot[565], root[565] = [8, 5, 0, SPVAL, SPVAL], [4, 4, 0, SPVAL, SPVAL]        # yr1 peak = 13+8 = 21

    ex = {"SHOOT_C_pft": shoot, "Root_C_pft": root}
    v = reduce_target(b, ex, {"variable": ["SHOOT_C_pft", "Root_C_pft"], "reduce": "sum_pft_peak",
                            "start_year": 2001})  # 2001+2002: both 365-day, matches the fixture
    assert v == pytest.approx(16.0)         # mean(11, 21) — NOT 21, which a window-max would give


def test_sum_pft_peak_rejects_sub_year_input():
    """The >=365-record guard is deliberate, not an accident of the fixture.

    Relaxing it would re-admit the scoring bug bb48f19 fixed: with a handful of records a
    transient spike becomes "the peak". Pin the behaviour so a future fixture failure gets
    the fixture fixed, not the guard loosened.
    """
    b = _be()
    short = np.array([[1, 2], [3, 4], [2, 1]], float)   # 3 records, well under one year
    with pytest.raises(ValueError, match="needs >=1 full year"):
        reduce_target(b, {"SHOOT_C_pft": short},
                      {"variable": ["SHOOT_C_pft"], "reduce": "sum_pft_peak"})


def test_annual_integrates_rate_over_year_summing_pft():
    b = _be()
    # 1 no-leap year (365 daily recs) × 2 PFTs, constant 0.5 gC/m2/hr each.
    # Σ_pft = 1.0 /hr; annual = 365 days × 1.0 × 24 h/day = 8760.
    rate = np.full((365, 2), 0.5)
    v = reduce_target(b, {"NPP_pft": rate}, {"variable": "NPP_pft", "reduce": "annual", "start_year": 2001})
    assert v == pytest.approx(8760.0)


def _fs_target(**kw):
    t = {"variable": "CO2_SEMIS_FLX_col", "reduce": "growing_season_mean_abs",
         "start_year": 2001}
    t.update(kw)
    return t


def test_growing_season_mean_abs_is_sign_agnostic():
    b = _be()
    # column var (time, 1); model reports <0 into atmosphere → |mean| efflux.
    # One full non-leap year: a growing-season mean is undefined on a partial year, so this
    # asserts the SIGN handling on a valid input rather than on a 3-record stub.
    flux = np.full((365, 1), -4.0)
    assert reduce_target(b, {"CO2_SEMIS_FLX_col": flux}, _fs_target()) == pytest.approx(4.0)


# --- Fs season selection (2026-08-07) -----------------------------------------------
# The reducer used to mean over `win(series)`, which sliced `window` as RAW RECORD INDICES.
# Every targets.yaml writes `window` as a YEAR range, so Fs was scored as an ALL-DAYS mean of
# 11 years against a MAY-SEP observation — understating it 1.74x on the R2 c04 runs, and 1.77
# vs 3.25 on R1's scorecard case. These pin the season selection so it cannot silently revert.

def test_growing_season_mean_abs_selects_the_season_not_the_whole_year():
    """THE regression guard: all-days and season means must be distinguishable, and it picks
    the season."""
    b = _be()
    flux = np.zeros((365, 1))
    flux[120:273] = 10.0                     # May 1 - Sep 30 of a non-leap year, 153 days
    v = reduce_target(b, {"CO2_SEMIS_FLX_col": flux}, _fs_target())
    assert v == pytest.approx(10.0), "did not restrict to the season"
    # the all-days mean of the same series is ~4.2 — the value the old code returned
    assert float(np.mean(flux)) == pytest.approx(10.0 * 153 / 365, rel=1e-6)


def test_legacy_window_selects_years_not_the_season():
    """A leftover `window:` may still pick YEARS (its documented legacy job, read as //365),
    but it must never slice the season out of the series — that is how the bug worked."""
    b = _be()
    flux = np.zeros((365, 1))
    flux[120:273] = 10.0
    plain = reduce_target(b, {"CO2_SEMIS_FLX_col": flux}, _fs_target())
    # window covering year 0 == the whole series; if it were sliced as raw records the season
    # would be cut and the answer would drop below 10.
    with_win = reduce_target(b, {"CO2_SEMIS_FLX_col": flux}, _fs_target(window=[0, 364]))
    assert plain == pytest.approx(10.0)
    assert with_win == pytest.approx(plain), "the raw-record window path is still live"


def test_out_of_range_window_raises_instead_of_scoring_nan():
    """An empty year selection must fail loudly. The `window_years` path already raised; the
    legacy `window` path returned NaN, which scores as a silently missing target."""
    b = _be()
    flux = np.zeros((365, 1))
    flux[120:273] = 10.0
    with pytest.raises(ValueError):
        reduce_target(b, {"CO2_SEMIS_FLX_col": flux}, _fs_target(window=[4380, 8395]))


def test_growing_season_mean_abs_is_leap_aware():
    """May 1 is day 122 in a leap year and 121 otherwise; fixed-365 blocking slips."""
    b = _be()
    # 2000 (leap, 366 recs) then 2001 (365). Season marked with hardcoded indices, so the test
    # does not re-run the implementation's own date arithmetic.
    flux = np.zeros((366 + 365, 1))
    flux[121:274] = 10.0                     # 2000-05-01 .. 2000-09-30 (leap: +1 day offset)
    flux[366 + 120: 366 + 273] = 10.0        # 2001-05-01 .. 2001-09-30
    v = reduce_target(b, {"CO2_SEMIS_FLX_col": flux},
                      _fs_target(start_year=2000, window_years=[2000, 2001]))
    assert v == pytest.approx(10.0), "leap-year season offset was not applied"


def test_growing_season_mean_abs_honours_window_years():
    b = _be()
    flux = np.zeros((365 * 2, 1))
    flux[120:273] = 4.0                      # 2001 season
    flux[365 + 120: 365 + 273] = 8.0         # 2002 season
    both = reduce_target(b, {"CO2_SEMIS_FLX_col": flux},
                         _fs_target(window_years=[2001, 2002]))
    second = reduce_target(b, {"CO2_SEMIS_FLX_col": flux},
                           _fs_target(window_years=[2002, 2002]))
    assert both == pytest.approx(6.0)        # mean of the two per-year season means
    assert second == pytest.approx(8.0)


# --- Fs daytime window (2026-08-09, R3) ---------------------------------------------
# growing_season_daytime_mean_abs is growing_season_mean_abs's hourly sibling: same season
# selection, PLUS a fixed hour-of-day window (memory/logs/20260809d_*.md, 20260809e_*.md).
# The actual window math is tested standalone in tests/test_subdaily_window_reduce.py; these
# pin the EcoSIM-side glue (hourly calendar tagging, tape/record-count guards).

def _fs_daytime_target(**kw):
    t = {"variable": "CO2_SEMIS_FLX_col", "reduce": "growing_season_daytime_mean_abs",
         "start_year": 2001, "daytime_window_hours": [16, 17, 18, 19, 20, 21]}
    t.update(kw)
    return t


def test_growing_season_daytime_mean_abs_selects_season_and_hour_window():
    b = _be()
    n = 365 * 24
    flux = np.zeros((n, 1))
    hour = np.arange(n) % 24
    doy = np.arange(n) // 24
    in_season = (doy >= 120) & (doy < 273)          # 2001-05-01 .. 2001-09-30 (non-leap)
    in_window = np.isin(hour, [16, 17, 18, 19, 20, 21])
    flux[in_season & in_window] = 10.0
    flux[in_season & ~in_window] = 999.0            # would inflate the mean if the window leaked
    flux[~in_season] = -999.0                       # would inflate |mean| if the season leaked
    v = reduce_target(b, {"CO2_SEMIS_FLX_col": flux}, _fs_daytime_target())
    assert v == pytest.approx(10.0)


def test_growing_season_daytime_mean_abs_is_sign_agnostic():
    b = _be()
    flux = np.full((365 * 24, 1), -3.0)
    v = reduce_target(b, {"CO2_SEMIS_FLX_col": flux}, _fs_daytime_target())
    assert v == pytest.approx(3.0)


def test_growing_season_daytime_mean_abs_is_leap_aware():
    b = _be()
    n = (366 + 365) * 24
    flux = np.zeros((n, 1))
    hour = np.arange(n) % 24
    # build day-of-year explicitly per year to avoid re-deriving the implementation's own logic
    doy = np.concatenate([np.arange(366).repeat(24), np.arange(365).repeat(24)])
    in_window = np.isin(hour, [16, 17, 18, 19, 20, 21])
    in_season_2000 = (doy[:366 * 24] >= 121) & (doy[:366 * 24] < 274)   # leap: +1 day offset
    in_season_2001 = (doy[366 * 24:] >= 120) & (doy[366 * 24:] < 273)
    in_season = np.concatenate([in_season_2000, in_season_2001])
    flux[in_season & in_window] = 10.0
    v = reduce_target(b, {"CO2_SEMIS_FLX_col": flux},
                      _fs_daytime_target(start_year=2000, window_years=[2000, 2001]))
    assert v == pytest.approx(10.0), "leap-year season offset was not applied at hourly resolution"


def test_growing_season_daytime_mean_abs_requires_window_hours():
    b = _be()
    flux = np.zeros((365 * 24, 1))
    with pytest.raises(ValueError, match="daytime_window_hours"):
        reduce_target(b, {"CO2_SEMIS_FLX_col": flux},
                      _fs_daytime_target(daytime_window_hours=None))


def test_growing_season_daytime_mean_abs_rejects_non_hourly_input():
    """A non-multiple-of-24 record count means this was handed the wrong tape (e.g. h0,
    daily) -- fail loudly rather than silently mis-binning hours."""
    b = _be()
    flux = np.zeros((365, 1))       # daily cadence, not hourly
    with pytest.raises(ValueError, match="hourly tape"):
        reduce_target(b, {"CO2_SEMIS_FLX_col": flux}, _fs_daytime_target())


def test_depth_integral_raises_until_layer_geometry_wired():
    b = _be()
    with pytest.raises(NotImplementedError):
        reduce_target(b, {"tSOC_vr": np.zeros((2, 20, 1))},
                      {"variable": "tSOC_vr", "reduce": "depth_integral", "depth_cm": [0, 10]})


# --- leap-calendar year blocking (v2.213) -------------------------------------------
# EcoSIM advances a REAL Gregorian calendar (ecosim_time_mod.F90: leap_yr = isLeapi(year0),
# doy = mod(doy, 365+leap_yr), get_days_cur_year = 366 on leap years; no no-leap switch in
# the &ecosim_time namelist). A daily tape therefore has 366 records in a leap year.

def test_annual_uses_real_calendar_year_lengths_when_start_year_known():
    """2000 is a leap year: its block must be 366 records, 2001's must be 365."""
    b = _be()
    # Constant 1.0 gC/m2/hr in 2000, 2.0 in 2001. 366+365 = 731 daily records.
    rate = np.concatenate([np.full((366, 1), 1.0), np.full((365, 1), 2.0)])
    v = reduce_target(b, {"NPP_pft": rate},
                      {"variable": "NPP_pft", "reduce": "annual", "start_year": 2000})
    # yr2000 = 366 d x 1.0 x 24 h = 8784 ; yr2001 = 365 d x 2.0 x 24 h = 17520
    assert v == pytest.approx((8784.0 + 17520.0) / 2)


def test_annual_fixed_365_would_bleed_across_the_leap_boundary():
    """Guards the actual defect: with fixed 365-blocking, block 0 would miss 2000-12-31
    and block 1 would start a day early, mixing the two years' rates."""
    b = _be()
    rate = np.concatenate([np.full((366, 1), 1.0), np.full((365, 1), 2.0)])
    leap_aware = reduce_target(b, {"NPP_pft": rate},
                               {"variable": "NPP_pft", "reduce": "annual", "start_year": 2000})
    naive_yr0 = 365 * 1.0 * 24                      # what fixed-365 blocking would give for yr 2000
    assert leap_aware != pytest.approx(naive_yr0)   # the two disagree — that is the bug
    assert reduce_target(b, {"NPP_pft": rate[:366]},
                         {"variable": "NPP_pft", "reduce": "annual",
                          "start_year": 2000}) == pytest.approx(8784.0)


def test_window_years_selects_absolute_calendar_years():
    b = _be()
    # 2000(leap,366) + 2001(365) + 2002(365); rate 1.0, 2.0, 3.0 gC/m2/hr
    rate = np.concatenate([np.full((366, 1), 1.0), np.full((365, 1), 2.0), np.full((365, 1), 3.0)])
    v = reduce_target(b, {"NPP_pft": rate},
                      {"variable": "NPP_pft", "reduce": "annual",
                       "start_year": 2000, "window_years": [2001, 2002]})
    assert v == pytest.approx((365 * 2.0 * 24 + 365 * 3.0 * 24) / 2)


def test_incomplete_trailing_year_is_dropped():
    b = _be()
    rate = np.concatenate([np.full((366, 1), 1.0), np.full((100, 1), 9.0)])   # 2000 + a partial 2001
    v = reduce_target(b, {"NPP_pft": rate},
                      {"variable": "NPP_pft", "reduce": "annual", "start_year": 2000})
    assert v == pytest.approx(8784.0)     # only the complete year 2000 is scored


def test_sum_pft_peak_is_leap_aware_and_warns_without_a_start_year():
    b = _be()
    shoot = np.zeros((731, 2))            # 2000 (366) + 2001 (365)
    shoot[100] = [5.0, 5.0]               # peak 10 inside 2000
    shoot[366 + 100] = [10.0, 10.0]       # peak 20 inside 2001
    spec = {"variable": ["SHOOT_C_pft"], "reduce": "sum_pft_peak", "start_year": 2000}
    assert reduce_target(b, {"SHOOT_C_pft": shoot}, spec) == pytest.approx(15.0)

    # No start year anywhere -> fixed-365 fallback, but it must WARN, never silently degrade.
    import os
    saved = os.environ.pop("A2MC_VALIDATION_START_YEAR", None)
    try:
        with pytest.warns(RuntimeWarning, match="fixed 365"):
            reduce_target(b, {"SHOOT_C_pft": shoot},
                          {"variable": ["SHOOT_C_pft"], "reduce": "sum_pft_peak"})
    finally:
        if saved is not None:
            os.environ["A2MC_VALIDATION_START_YEAR"] = saved


# ---------------------------------------------------------------------------
# `year_end` — annual total of a WITHIN-YEAR CUMULATIVE (2026-08-15)
# ---------------------------------------------------------------------------
# EcoSIM writes several outputs as cumulatives that reset each 1 January, and the registry
# says so in its own long_name ("cumulative ecosystem GPP", "cumulative total
# evapotranspiration"). Their ANNUAL value is the year-END reading, which no existing reduce
# computes: `annual` integrates a RATE (x step_hours, summed over the year) and would inflate
# a cumulative by ~8760x, silently. Verified on real tapes for ECO_GPP_col / ECO_ET_col /
# ECO_RA_col / ECO_RH_col and for the two harvest variables. Needed by EcoSIM_Lusignan's
# GPP / Reco / ET targets.

def _cumulative(years, per_year_total, start_year=2006):
    """A synthetic within-year cumulative: rises linearly to `per_year_total`, resets each year."""
    out = []
    for i, y in enumerate(years):
        nd = 366 if (y % 400 == 0 or (y % 4 == 0 and y % 100 != 0)) else 365
        tot = per_year_total[i]
        out.append(np.arange(1, nd + 1) / nd * tot)
    return np.concatenate(out)


def test_year_end_takes_the_last_record_of_each_year_and_means_them():
    b = _be()
    years = [2006, 2007, 2008]          # 2008 is a leap year: 366 records
    totals = [1000.0, 2000.0, 3000.0]
    cum = _cumulative(years, totals)
    assert len(cum) == 365 + 365 + 366
    v = reduce_target(b, {"ECO_GPP_col": cum},
                      {"variable": "ECO_GPP_col", "reduce": "year_end", "start_year": 2006})
    assert v == pytest.approx(2000.0)   # mean of 1000/2000/3000


def test_year_end_is_leap_aware():
    """Fixed-365 blocking would read the WRONG record once a leap year has passed.

    2008 has 366 records; blocking by 365 puts the year boundary a day early from then on, so
    the 2008 'year end' would be read one record short of the true annual total.
    """
    b = _be()
    years, totals = [2006, 2007, 2008], [1000.0, 2000.0, 3000.0]
    cum = _cumulative(years, totals)
    v = reduce_target(b, {"ECO_GPP_col": cum},
                      {"variable": "ECO_GPP_col", "reduce": "year_end",
                       "start_year": 2006, "window_years": [2008, 2008]})
    assert v == pytest.approx(3000.0)   # exact only if the 366-day block is used


def test_year_end_honours_window_years():
    b = _be()
    years, totals = [2006, 2007, 2008], [1000.0, 2000.0, 3000.0]
    cum = _cumulative(years, totals)
    v = reduce_target(b, {"ECO_GPP_col": cum},
                      {"variable": "ECO_GPP_col", "reduce": "year_end",
                       "start_year": 2006, "window_years": [2006, 2007]})
    assert v == pytest.approx(1500.0)


def test_year_end_sums_several_variables_then_negates():
    """Reco = -(ECO_RA_col + ECO_RH_col): both are stored as NEGATIVE cumulatives, so the
    target sums them and flips the sign to match a positive observation."""
    b = _be()
    years = [2006, 2007]
    ra = -_cumulative(years, [600.0, 700.0])
    rh = -_cumulative(years, [400.0, 500.0])
    v = reduce_target(b, {"ECO_RA_col": ra, "ECO_RH_col": rh},
                      {"variable": ["ECO_RA_col", "ECO_RH_col"], "reduce": "year_end",
                       "negate": True, "start_year": 2006})
    assert v == pytest.approx(1100.0)   # mean of 1000 and 1200


def test_year_end_without_negate_keeps_the_models_sign():
    """`negate` must be opt-in — a target that does not ask for it gets the raw sign."""
    b = _be()
    ra = -_cumulative([2006], [600.0])
    v = reduce_target(b, {"ECO_RA_col": ra},
                      {"variable": "ECO_RA_col", "reduce": "year_end", "start_year": 2006})
    assert v == pytest.approx(-600.0)


def test_year_end_masks_spval():
    b = _be()
    cum = _cumulative([2006], [1000.0])
    cum[10] = SPVAL                      # a spval mid-year must not poison the year-end read
    v = reduce_target(b, {"ECO_GPP_col": cum},
                      {"variable": "ECO_GPP_col", "reduce": "year_end", "start_year": 2006})
    assert v == pytest.approx(1000.0)


def test_year_end_rejects_a_sub_year_tape():
    """Fewer records than one complete year must raise, not silently score a partial total."""
    b = _be()
    with pytest.raises(ValueError, match="year_end"):
        reduce_target(b, {"ECO_GPP_col": np.arange(100.0)},
                      {"variable": "ECO_GPP_col", "reduce": "year_end", "start_year": 2006})
