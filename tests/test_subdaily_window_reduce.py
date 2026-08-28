"""Tests for the model-agnostic sub-daily window reducer (tools/subdaily_window_reduce.py).

Synthetic hourly series with a known answer -- no dependency on a real EcoSIM tape. See
use_cases/EcoSIM_BioCON/memory/logs/20260809d_*.md / 20260809e_*.md for the analysis this
generalizes and why the window must be a caller-supplied constant, not derived from the series.
"""
import numpy as np
import pytest

from tools.subdaily_window_reduce import growing_season_window_mean_abs


def _hourly_tags(n_years, start_year=2000):
    """(hour_of_day, month, year) for a synthetic 24-record/day, 365-day/year series."""
    n = n_years * 365 * 24
    idx = np.arange(n)
    hour = idx % 24
    doy = (idx // 24) % 365          # 0-based day-of-year, fixed 365 for simplicity
    year = start_year + (idx // 24) // 365
    # crude month-of-year from day-of-year (non-leap, good enough for a synthetic test)
    month_bounds = np.cumsum([0, 31, 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31])
    month = np.searchsorted(month_bounds, doy, side="right")
    return hour, month, year


def test_basic_mean_matches_hand_computed_value():
    hour, month, year = _hourly_tags(n_years=2)
    # value = hour_of_day itself (deterministic, easy to hand-check); |values| irrelevant here.
    values = hour.astype(float)
    result = growing_season_window_mean_abs(
        values, hour, month, year,
        window_hours=range(16, 22),          # h16..h21 inclusive -> mean = 18.5
        season_months=(5, 9),
        window_years=(2000, 2001),
    )
    assert result == pytest.approx(18.5)


def test_abs_value_is_taken():
    hour, month, year = _hourly_tags(n_years=1)
    values = -np.ones_like(hour, dtype=float) * 7.0
    result = growing_season_window_mean_abs(
        values, hour, month, year, window_hours=[12], season_months=(5, 9))
    assert result == pytest.approx(7.0)


def test_season_and_window_both_filter():
    hour, month, year = _hourly_tags(n_years=1)
    # value = 100 only in-season AND in-window; 0 otherwise. Mean over the selection must be 100.
    in_season = (month >= 5) & (month <= 9)
    in_window = np.isin(hour, [16, 17, 18, 19, 20, 21])
    values = np.where(in_season & in_window, 100.0, 0.0)
    result = growing_season_window_mean_abs(
        values, hour, month, year, window_hours=range(16, 22), season_months=(5, 9))
    assert result == pytest.approx(100.0)


def test_window_years_restricts_years():
    hour, month, year = _hourly_tags(n_years=3, start_year=2010)   # 2010, 2011, 2012
    # year 2012 gets a different value so a wrong year selection is caught.
    values = np.where(year == 2012, 1.0, 5.0)
    result = growing_season_window_mean_abs(
        values, hour, month, year, window_hours=[18], season_months=(5, 9),
        window_years=(2010, 2011))
    assert result == pytest.approx(5.0)


def test_window_years_outside_data_raises():
    hour, month, year = _hourly_tags(n_years=1, start_year=2000)
    with pytest.raises(ValueError, match="selects no year"):
        growing_season_window_mean_abs(
            np.ones_like(hour, dtype=float), hour, month, year,
            window_hours=[18], window_years=(1990, 1991))


def test_empty_window_hours_raises():
    hour, month, year = _hourly_tags(n_years=1)
    with pytest.raises(ValueError, match="empty"):
        growing_season_window_mean_abs(
            np.ones_like(hour, dtype=float), hour, month, year, window_hours=[])


def test_selection_with_no_records_in_a_year_raises():
    hour, month, year = _hourly_tags(n_years=1)
    # an hour that never occurs in this synthetic calendar (there is no hour 99)
    with pytest.raises(ValueError, match="selects no records"):
        growing_season_window_mean_abs(
            np.ones_like(hour, dtype=float), hour, month, year, window_hours=[99])


def test_mismatched_shapes_raise():
    hour, month, year = _hourly_tags(n_years=1)
    with pytest.raises(ValueError, match="same shape"):
        growing_season_window_mean_abs(
            np.ones(5), hour, month, year, window_hours=[18])
