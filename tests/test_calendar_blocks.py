"""Leap-aware blocking, pinned against the exact bug it replaces.

`scripts/extract_and_plot_adapter_ensemble.py` blocked every panel with `n // 365`. These tests
assert the difference is real and in the direction claimed, so nobody "simplifies" it back.
"""
from __future__ import annotations

import numpy as np
import pytest

from tools.calendar_blocks import growing_season_day_slice, tag_hourly, year_blocks

# BioCON: 2000-2022 daily. 23 years containing 6 leap years (2000, 04, 08, 12, 16, 20).
BIOCON_DAYS = 23 * 365 + 6      # 8401


def test_the_fixed_365_bug_is_real_and_this_fixes_it():
    """`n // 365` on 8401 records gives 23 years and DROPS 6 -- and every boundary after 2000
    slips. The leap-aware version consumes all 8401 with the last year ending exactly at the end."""
    assert BIOCON_DAYS // 365 == 23                      # the old code's year count looks right...
    assert BIOCON_DAYS - 23 * 365 == 6                   # ...while silently discarding 6 records

    blocks = year_blocks(BIOCON_DAYS, 2000)
    assert len(blocks) == 23
    assert blocks[-1][2] == BIOCON_DAYS, "the leap-aware blocking must consume every record"
    assert [y for y, _, _ in blocks] == list(range(2000, 2023))


def test_year_boundaries_drift_under_fixed_365():
    """By 2012 the old blocking is 3 days out; by 2022 it is 6. That is why an Fs 'annual growing
    season mean' computed with //365 is averaging a shifted window."""
    blocks = {y: lo for y, lo, _ in year_blocks(BIOCON_DAYS, 2000)}
    for year, expected_drift in ((2004, 1), (2012, 3), (2022, 6)):
        naive = (year - 2000) * 365
        assert blocks[year] - naive == expected_drift, year


def test_leap_year_blocks_are_366_days():
    blocks = {y: (lo, hi) for y, lo, hi in year_blocks(BIOCON_DAYS, 2000)}
    assert blocks[2000][1] - blocks[2000][0] == 366
    assert blocks[2001][1] - blocks[2001][0] == 365


def test_incomplete_trailing_year_is_dropped():
    """A partial year is not a year; averaging one silently changes the statistic. Matches the
    backend, and matters because early-terminating runs are common (9 of 258 in the R3 probe)."""
    blocks = year_blocks(365 + 200, 2001)          # 2001 non-leap, then a stub
    assert [y for y, _, _ in blocks] == [2001]


def test_hourly_blocking_uses_per_day():
    blocks = year_blocks(BIOCON_DAYS * 24, 2000, per_day=24)
    assert len(blocks) == 23
    assert blocks[0][2] - blocks[0][1] == 366 * 24


def test_zero_and_negative_records_are_empty_not_an_exception():
    assert year_blocks(0, 2000) == []
    assert year_blocks(-5, 2000) == []


# ---------------------------------------------------------------------------
# hourly tagging
# ---------------------------------------------------------------------------
def test_tag_hourly_axes_line_up():
    yr, mo, hod = tag_hourly(366 * 24, 2000)          # a leap year exactly
    assert yr[0] == 2000 and yr[-1] == 2000
    assert mo[0] == 1 and mo[-1] == 12
    assert hod[0] == 0 and hod[23] == 23 and hod[24] == 0
    assert (mo == 2).sum() == 29 * 24, "2000 is a leap year: February has 29 days"


def test_tag_hourly_crosses_a_year_boundary_correctly():
    yr, mo, _ = tag_hourly((366 + 365) * 24, 2000)
    assert yr[366 * 24 - 1] == 2000 and yr[366 * 24] == 2001
    assert (yr == 2001).sum() == 365 * 24


def test_a_non_hourly_tape_raises_rather_than_guessing():
    """The h0 daily tape has already averaged the diel cycle away, so a daytime window on it is
    meaningless. Reaching this function with daily data means the caller picked the wrong tape."""
    with pytest.raises(ValueError, match="not an hourly tape"):
        tag_hourly(8401, 2000)


# ---------------------------------------------------------------------------
# the hardcoded growing season
# ---------------------------------------------------------------------------
def test_growing_season_slice_replaces_the_hardcoded_120_273():
    """`gs=(120, 273)` is May-Sep for a NON-leap year only."""
    assert growing_season_day_slice(2001) == (120, 273)        # non-leap: the old constant
    assert growing_season_day_slice(2000) == (121, 274)        # leap: the old constant is 1 day off


def test_growing_season_slice_length_is_the_may_to_sep_day_count():
    lo, hi = growing_season_day_slice(2001)
    assert hi - lo == 31 + 30 + 31 + 31 + 30                   # May, Jun, Jul, Aug, Sep


# ---------------------------------------------------------------------------
# The consumer must actually USE this module (structural guard)
# ---------------------------------------------------------------------------
def test_the_ensemble_driver_no_longer_blocks_by_fixed_365():
    """`scripts/extract_and_plot_adapter_ensemble.py` had `n // 365` in ALL THREE panels. A
    cheap source check, because the expensive check needs a real ensemble on disk."""
    from pathlib import Path
    src = (Path(__file__).resolve().parents[1] /
           "scripts" / "extract_and_plot_adapter_ensemble.py").read_text()
    assert "// 365" not in src, "fixed-365 blocking is back; use tools.calendar_blocks.year_blocks"
    assert "year_blocks(" in src, "the driver must use the shared leap-aware blocker"

    # Checked via AST, not substring: the docstrings deliberately QUOTE the old `gs=(120, 273)`
    # while explaining why it was wrong, and a substring test flags that prose as a regression.
    # (It did, on first run.) What matters is that no function still takes it as a default.
    import ast
    tree = ast.parse(src)
    for fn in [n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef)]:
        names = [a.arg for a in fn.args.args + fn.args.kwonlyargs]
        assert "gs" not in names, (
            f"{fn.name} still takes a hardcoded growing-season slice; the season must be "
            f"leap-aware via growing_season_day_slice()")


def test_the_ensemble_driver_gets_its_Fs_reduction_from_the_TARGET():
    """The Fs panel must read the target's own `tape`/`daytime_window_hours` and call the scorer's
    reducer, not reimplement one. Verified numerically on 2026-08-16: target-driven Fs reproduced
    the scored value 2.265751 exactly, where the old hardcoded path gave 2.012539."""
    from pathlib import Path
    src = (Path(__file__).resolve().parents[1] /
           "scripts" / "extract_and_plot_adapter_ensemble.py").read_text()
    assert "growing_season_window_mean_abs" in src, "must call the scorer's own reducer"
    assert "daytime_window_hours" in src, "the daytime window must come from the target spec"
    assert "--targets" in src, "the target spec must be an input, not a constant"


def test_the_ensemble_driver_requires_FULL_window_coverage():
    """A window mean over an overlap is a different statistic. Cases 56 and 63 (ending 2015 and
    2018) returned Fs 268.9 and 275.5 against a normal 0.1-8 before this rule, and those two
    values failed GATE_MONOTONE for the entire probe."""
    from pathlib import Path
    src = (Path(__file__).resolve().parents[1] /
           "scripts" / "extract_and_plot_adapter_ensemble.py").read_text()
    assert "full_window_coverage" in src, "the CSV must mark partial-coverage cases"
    assert "need.issubset" in src, "coverage must require the WHOLE window, not an overlap"


def test_shared_blocker_matches_the_hand_written_gregorian_rule_the_backend_used():
    """`models/ecosim/backend.py` spelled the leap rule out by hand as
    `(y % 400 == 0) or (y % 4 == 0 and y % 100 != 0)`; the shared module uses `calendar.isleap`.
    Consolidating them is only safe if they agree EVERYWHERE, including the century cases
    (1900 not a leap year, 2000 is) that a careless rewrite gets wrong. Asserted over 600 years
    rather than argued from two examples."""
    import calendar
    for y in range(1800, 2401):
        hand = (y % 400 == 0) or (y % 4 == 0 and y % 100 != 0)
        assert hand == calendar.isleap(y), y


def test_backend_uses_the_shared_blocker():
    from pathlib import Path
    src = (Path(__file__).resolve().parents[1] / "models" / "ecosim" / "backend.py").read_text()
    assert "from tools.calendar_blocks import year_blocks" in src
    assert "ndays = 366 if" not in src, "the hand-rolled blocking loop is back in the backend"
