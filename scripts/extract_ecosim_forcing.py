#!/usr/bin/env python
"""Daily meteorological drivers from an EcoSIM hourly climate file, in KGML's feature form.

An emulator conditioned only on parameters learns one site's one weather history and cannot be
given a different year. Conditioning on the DRIVERS is what makes it an emulator of the model
rather than of the run, and it is the arrangement Liu et al. (2024) use.

THE FEATURE SET MIRRORS KGML'S, deliberately, so the two are comparable. Theirs is
`RADN, TMAX_AIR, TDIF_AIR, HMAX_AIR, HDIF_AIR, WIND, PRECN` -- daily radiation, the daily maximum
and DIURNAL RANGE of temperature and humidity, wind and precipitation. The range terms matter:
a daily mean throws away the diurnal amplitude that drives stomatal and respiration responses.

CALENDAR. The file is stored (year, day=366, hour=24) and PADS day 366 in non-leap years, so a
naive read produces 366 days every year and drifts against the model tape. Days are emitted on the
real Gregorian calendar, which is what EcoSIM runs.

Author: Jing Tao with Claude on Perlmutter
"""
from __future__ import annotations

import argparse
import calendar
import datetime as dt
from pathlib import Path

import numpy as np

#: daily feature -> (hourly tape variable, reduction). Names follow KGML's where they correspond.
FEATURES = [
    ("RADN",     "SRADH", "mean"),
    ("LWRAD",    "XRADH", "mean"),
    ("TMAX_AIR", "TMPH",  "max"),
    ("TMIN_AIR", "TMPH",  "min"),
    ("TDIF_AIR", "TMPH",  "range"),
    ("HMAX_AIR", "DWPTH", "max"),
    ("HDIF_AIR", "DWPTH", "range"),
    ("WIND",     "WINDH", "mean"),
    ("PRECN",    "RAINH", "sum"),
]

_RED = {"mean": np.mean, "max": np.max, "min": np.min, "sum": np.sum,
        "range": lambda a, axis: np.max(a, axis=axis) - np.min(a, axis=axis)}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--climate", required=True, help="the hourly clm_hour_file_in NetCDF")
    ap.add_argument("--years", nargs=2, type=int, required=True, metavar=("Y0", "Y1"))
    ap.add_argument("--grid", type=int, default=0)
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    y0, y1 = a.years

    import netCDF4 as nc
    with nc.Dataset(a.climate) as d:
        file_years = [int(v) for v in np.asarray(d.variables["year"][:]).ravel()]
        raw = {v: d.variables[v][:, :, :, a.grid].astype("f8")      # (year, day, hour)
               for _, v, _ in FEATURES if v in d.variables}
    missing = {v for _, v, _ in FEATURES} - set(raw)
    if missing:
        raise SystemExit(f"climate file lacks {sorted(missing)}; has {sorted(raw)}")

    want = [y for y in range(y0, y1 + 1)]
    unknown = [y for y in want if y not in file_years]
    if unknown:
        raise SystemExit(f"years {unknown} are not in the climate file ({file_years[0]}-{file_years[-1]})")

    dates, rows = [], []
    for y in want:
        iy = file_years.index(y)
        ndays = 366 if calendar.isleap(y) else 365     # the pad on day 366 is dropped for non-leap
        day = {}
        for name, var, how in FEATURES:
            day[name] = _RED[how](raw[var][iy, :ndays, :], axis=1)
        for k in range(ndays):
            dates.append(dt.date(y, 1, 1) + dt.timedelta(days=k))
            rows.append([day[name][k] for name, _, _ in FEATURES])

    M = np.asarray(rows, dtype="f4")                    # (n_days, n_features)
    names = [n for n, _, _ in FEATURES]

    # A CONSTANT column carries no information and would be standardised by a zero spread.
    # Lusignan's climate file leaves XRADH (longwave) at zero throughout, so LWRAD is dropped
    # here rather than fed to a network as a dead input. Reported, never silent.
    spread = M.max(axis=0) - M.min(axis=0)
    dead = [names[j] for j in range(len(names)) if spread[j] == 0]
    if dead:
        keep = [j for j in range(len(names)) if spread[j] > 0]
        print(f"DROPPED constant feature(s): {dead}  (no variation in this climate file)")
        M = M[:, keep]
        names = [names[j] for j in keep]
    np.savez_compressed(a.out, met=M, features=np.array(names),
                        dates=np.array([d_.isoformat() for d_ in dates]),
                        years=np.array([d_.year for d_ in dates]))
    print(f"daily forcing : {M.shape}  (days, features)")
    print(f"window        : {dates[0]} .. {dates[-1]}")
    print(f"features      : {names}")
    for j, n in enumerate(names):
        print(f"  {n:9s} min={M[:, j].min():9.3f}  mean={M[:, j].mean():9.3f}  max={M[:, j].max():9.3f}")
    print(f"wrote         : {a.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
