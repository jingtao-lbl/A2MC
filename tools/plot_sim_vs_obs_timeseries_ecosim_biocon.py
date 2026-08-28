#!/usr/bin/env python3
"""Sim-vs-obs TIME SERIES for one EcoSIM **BioCON** case, driven by the site's `targets.yaml`.

★ THE NAME IS LOAD-BEARING, AND IT HAS BEEN NARROWED TWICE (PI, 2026-08-14 and 2026-08-17).
First promoted as `tools/plot_sim_vs_obs_timeseries.py` — as if generic. Renamed to `..._ecosim`
when that proved false. Renamed again to `..._ecosim_biocon` when THAT proved false too: the
target names below are hardcoded to `plant_C` / `NPP` / `Fs`, which is BioCON's set, so pointing
it at **EcoSIM_Lusignan** (targets `ET` / `GPP` / `Reco`, the other EcoSIM case in this repo)
prints "none of plant_C/NPP/Fs found in the targets file" and exits 2. Verified by running it,
2026-08-17. "EcoSIM-specific" was still one level too generous.

There is no generic single-case counterpart, and that is deliberate: the nearest generic thing,
`scripts/extract_and_plot_adapter_ensemble.py`, does a different job (whole ensemble, one figure).
**To support another case, COPY THIS FILE and adapt it** rather than starting over or trying to
generalize this one in place — the structure, the leap-aware tagging, the target-driven Fs panel
and the window shading all transfer; only the names and panel semantics change.

It is not generic in three ways, only the shallowest of which is parameterized:

  1. It reads the history tape DIRECTLY with `netCDF4.Dataset` and assumes EcoSIM's layout
     (`var[:, pft]` with PFT on axis 1, `[:, 0]` for a column variable). The generic sibling
     `scripts/extract_and_plot_adapter_ensemble.py` goes through
     `backend.extract_history_variables` precisely to avoid this.
  2. The TARGET NAMES `plant_C` / `NPP` / `Fs` are hardcoded, as is the `units` map keyed on them.
     This is the one that forced the second rename: it excludes not just a FATES site but the
     other ECOSIM site, so the coupling is to the CASE's target set, not to the model.
  3. The panel semantics — peak / annual-sum / seasonal-mean — are assigned BY those names rather
     than read from each target's own `reduce`.
  Only the VARIABLE names are CLI-overridable (`--plantc-vars`, `--npp-var`, `--fs-var`).

Making it genuinely generic means routing extraction through the model backend and driving the
panels from each target's `reduce`/`units` — deliberately NOT done (PI chose to rename rather than
refactor), so the file name states the truth today instead of a checker or a reader discovering it
later. This is `feedback_per_model_scripts_not_generic`: A2MC's own machinery is generic, but a
script that touches per-model ARTIFACTS is parallel, not generic.

Promoted from `use_cases/EcoSIM_BioCON/memory/phase_results/20260719g_phase3_diagnosis_r02_c00_iter01_*/
diagnose_timeseries_r02.py` (2026-08-14) — promotion is copy-then-generalize
(`calibration-discipline` item 12): the original hardcoded one tape path, one set of observations,
one settled window, one growing-season slice, and R2-specific conclusions in its panel titles. Those
are fixed; the model coupling above is not.

WHY THIS IS A TOOL AND NOT A ONE-OFF. `feedback_timeseries_plots_during_diagnosis` requires a
sim-vs-obs trajectory comparison *during* Phase 3, not deferred to reporting, because the shape of
the trajectory is usually the diagnosis (does biomass plateau, decline, overshoot-then-crash?). A
single scalar at the observation month hides all of it. Every round needs this figure and every
round was rebuilding it.

WHAT IT READS FROM targets.yaml (so it cannot drift from what is actually scored):
  observed, uncertainty  -> the obs line and its band
  window_years           -> the settled window shading and the window means
  season_months          -> the growing-season mask for a seasonal reduction
  daytime_window_hours   -> the DAYTIME sub-selection, which only applies to a sub-daily tape
  reduce                 -> which annual reduction to draw (peak / annual sum / seasonal mean)

TAPE CADENCE IS DETECTED, NOT ASSUMED. EcoSIM writes a real Gregorian calendar including leap days
([[reference_ecosim_uses_real_leap_calendar]]), so a fixed `//365` is wrong; and R3 writes an HOURLY
tape where R1/R2 wrote daily. The record count per year is derived from the tape length and the
year span, and `daytime_window_hours` is applied only when the cadence is sub-daily. A daily tape
with a daytime window requested is reported, not silently averaged over whole days -- that mismatch
is exactly how an Fs definition change becomes an invisible scoring error.

Usage:
    python tools/plot_sim_vs_obs_timeseries.py --tape <h0.nc> --targets <targets.yaml> \
        --outdir <phase_results/{stem}/> [--title "..."] [--start-year 2000]

Author: Jing Tao with Claude.
"""
from __future__ import annotations

import argparse
import csv
import sys
from pathlib import Path

import numpy as np

# Importable when run as a script from anywhere: the Fs path imports tools.* for the backend and
# the authoritative sub-daily reducer, and `python tools/foo.py` puts tools/ (not the repo root) on
# sys.path.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

SPVAL = 1.0e29


def _mask(a):
    a = np.asarray(a, dtype=float)
    return np.where(np.abs(a) > SPVAL, np.nan, a)


def _load_targets(path: Path, names=("plant_C", "NPP", "Fs")):
    import yaml
    tg = yaml.safe_load(path.read_text())["targets"]
    out = {}
    for n in names:
        if n in tg:
            out[n] = tg[n]
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--tape", help="daily history tape (.nc) for ONE case (plant_C / NPP)")
    ap.add_argument("--case-dir", help="case directory; REQUIRED when a target sets `tape:` "
                                       "(e.g. Fs `tape: h1`) so its own tape can be read")
    ap.add_argument("--targets", required=True, help="site validation/targets.yaml")
    ap.add_argument("--outdir", required=True)
    ap.add_argument("--start-year", type=int, default=2000)
    ap.add_argument("--title", default="")
    ap.add_argument("--plantc-vars", default="SHOOT_C_pft,Root_C_pft")
    ap.add_argument("--npp-var", default="NPP_pft")
    ap.add_argument("--fs-var", default="CO2_SEMIS_FLX_col")
    a = ap.parse_args()

    import netCDF4 as nc
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    outdir = Path(a.outdir); outdir.mkdir(parents=True, exist_ok=True)
    tg = _load_targets(Path(a.targets))
    if not tg:
        print("ERROR: none of plant_C/NPP/Fs found in the targets file", file=sys.stderr)
        return 2

    d = nc.Dataset(a.tape)
    parts = [_mask(d.variables[v][:]) for v in a.plantc_vars.split(",") if v in d.variables]
    plantc_t = sum(np.nansum(p, axis=1) for p in parts) if parts else None
    npp_t = np.nansum(_mask(d.variables[a.npp_var][:]), axis=1) if a.npp_var in d.variables else None
    fsv = _mask(d.variables[a.fs_var][:]) if a.fs_var in d.variables else None
    fs_t = np.abs(fsv[:, 0] if (fsv is not None and fsv.ndim > 1) else fsv) if fsv is not None else None

    n = len(plantc_t if plantc_t is not None else (npp_t if npp_t is not None else fs_t))
    win = tg.get("plant_C", tg.get("NPP", {})).get("window_years") or [a.start_year, a.start_year]
    # Cadence from the record count, NOT a hardcoded 365: EcoSIM uses a real leap calendar and R3
    # writes hourly where R1/R2 wrote daily.
    span_years = max(1, (win[1] - a.start_year) + 1)
    per_day = max(1, int(round(n / (span_years * 365.25))))
    per_year = int(round(n / span_years))
    nyr = max(1, n // per_year)
    years = a.start_year + np.arange(nyr)
    t_yr = a.start_year + np.arange(n) / float(per_year)
    print(f"tape records={n}  inferred ~{per_day}/day  ~{per_year}/yr  -> {nyr} years")

    def yearly(arr, how, season=None, hours=None):
        out = []
        for y in range(nyr):
            seg = arr[y * per_year:(y + 1) * per_year]
            if season:
                doy = np.arange(len(seg)) / max(per_day, 1)
                m0 = (doy >= (season[0] - 1) * 30.4) & (doy <= season[1] * 30.4)
                seg = seg[m0]
            if hours and per_day >= 24:
                hod = (np.arange(len(seg)) % per_day) * (24.0 / per_day)
                seg = seg[np.isin(np.floor(hod).astype(int), hours)]
            if len(seg) == 0:
                out.append(np.nan); continue
            out.append(np.nanmax(seg) if how == "peak"
                       else (np.nansum(seg) * (24.0 / per_day) if how == "sum" else np.nanmean(seg)))
        return np.array(out)

    series = {}
    if plantc_t is not None:
        series["plant_C"] = (plantc_t, yearly(plantc_t, "peak"), "annual peak")
    if npp_t is not None:
        series["NPP"] = (npp_t, yearly(npp_t, "sum"), "annual total")
    # ---- Fs: read ITS OWN tape and use the AUTHORITATIVE reducer, never an approximation ----
    # R3's Fs is `growing_season_daytime_mean_abs` on `tape: h1` (hourly, one file per year), with
    # a fixed hour-of-day window. The backend's own comment is explicit that this reduction is
    # "meaningless on the h0 daily tape, which has already averaged the diel cycle away", so
    # computing it from h0 -- as the promoted script did -- is the wrong tape AND the wrong
    # reduction. Approximating it here (30.4-day months, hour-of-day from index) would also mean a
    # figure that disagrees with the score for reasons no reader could see. So: extract via the
    # backend using the target's own `tape`, tag the records leap-aware, and hand off to
    # `tools.subdaily_window_reduce.growing_season_window_mean_abs` -- the same function
    # `models/ecosim/backend.py` calls. One reduction, one implementation. (PI catch, 2026-08-14.)
    fs_spec = tg.get("Fs", {})
    fs_tape = fs_spec.get("tape")
    if fs_spec and fs_tape and fs_tape != "h0":
        if not a.case_dir:
            print(f"ERROR: Fs target sets `tape: {fs_tape}` but --case-dir was not given, so its "
                  f"tape cannot be located. Refusing to draw Fs from the daily tape.", file=sys.stderr)
        else:
            import calendar
            from tools.model_evaluate_case import _resolve_backend
            from tools.subdaily_window_reduce import growing_season_window_mean_abs
            backend = _resolve_backend("ecosim")
            ex = backend.extract_history_variables(Path(a.case_dir), [a.fs_var], tape=fs_tape)
            vals = np.abs(_mask(np.asarray(ex[a.fs_var])).squeeze())
            nrec = len(vals)
            if nrec % 24:
                print(f"ERROR: {fs_tape} tape has {nrec} records, not a multiple of 24 — not hourly.",
                      file=sys.stderr)
            else:
                ndays = nrec // 24
                yr_t = np.empty(nrec, int); mo_t = np.empty(nrec, int); hod = np.empty(nrec, int)
                day = 0
                y = a.start_year
                while day < ndays:                       # leap-aware, like the backend's _year_blocks
                    dpy = 366 if calendar.isleap(y) else 365
                    take = min(dpy, ndays - day)
                    cum = np.cumsum([0] + [calendar.monthrange(y, m)[1] for m in range(1, 13)])
                    mpd = np.searchsorted(cum, np.arange(take), side="right")
                    sl = slice(day * 24, (day + take) * 24)
                    yr_t[sl] = y
                    mo_t[sl] = np.repeat(mpd, 24)
                    hod[sl] = np.tile(np.arange(24), take)
                    day += take; y += 1
                yrs_present = np.unique(yr_t)
                ann_fs = np.array([
                    growing_season_window_mean_abs(
                        vals, hod, mo_t, yr_t,
                        window_hours=fs_spec["daytime_window_hours"],
                        season_months=tuple(fs_spec.get("season_months", (5, 9))),
                        window_years=(int(yy), int(yy)))
                    for yy in yrs_present])
                # pad/trim onto the common `years` axis so the panels share an x-axis
                ann_al = np.full(nyr, np.nan)
                for k, yy in enumerate(yrs_present):
                    if a.start_year <= yy < a.start_year + nyr:
                        ann_al[yy - a.start_year] = ann_fs[k]
                series["Fs"] = (vals, ann_al,
                                "growing-season DAYTIME mean (h%s, %s tape)"
                                % ("".join(str(h) for h in fs_spec["daytime_window_hours"][:1]) + "-"
                                   + str(fs_spec["daytime_window_hours"][-1]), fs_tape))
                per_day_fs = 24
                t_fs = a.start_year + np.arange(nrec) / (365.25 * per_day_fs)
                series["Fs"] = (vals, ann_al, series["Fs"][2], t_fs)
    elif fs_t is not None:
        spec = fs_spec
        hrs = spec.get("daytime_window_hours")
        if hrs:
            print(f"WARNING: targets ask for daytime_window_hours={hrs} on a tape with "
                  f"~{per_day}/day records. Drawing a seasonal mean over WHOLE days; this is NOT "
                  f"the scored Fs definition.")
            hrs = None
        series["Fs"] = (fs_t, yearly(fs_t, "mean", spec.get("season_months"), hrs),
                        "growing-season mean (daily tape)")

    w0, w1 = win
    wmask = (years >= w0) & (years <= w1)
    rows = []
    print(f"\n=== window {w0}-{w1} means (should reproduce the scored values) ===")
    for k, entry in series.items():
        ann, lab = entry[1], entry[2]
        obs = float(tg[k]["observed"]); unc = float(tg[k].get("uncertainty", 0.2))
        got = float(np.nanmean(ann[wmask])) if wmask.any() else float("nan")
        flag = "IN BAND" if obs * (1 - unc) <= got <= obs * (1 + unc) else "out of band"
        print(f"  {k:8} {lab:26} = {got:9.3f}   obs {obs:g} "
              f"[{obs*(1-unc):.4g},{obs*(1+unc):.4g}]  {flag}")
        rows.append((k, lab, got, obs, obs * (1 - unc), obs * (1 + unc), flag))

    with (outdir / "sim_vs_obs_window_means.csv").open("w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["target", "reduction", "sim_window_mean", "observed", "band_lo", "band_hi", "verdict"])
        w.writerows(rows)

    fig, axes = plt.subplots(len(series), 1, figsize=(13, 3.7 * len(series)), sharex=True)
    axes = np.atleast_1d(axes)
    units = {"plant_C": "gC/m$^2$", "NPP": "gC/m$^2$/yr", "Fs": "umol CO$_2$/m$^2$/s"}
    for ax, (k, entry) in zip(axes, series.items()):
        raw, ann, lab = entry[0], entry[1], entry[2]
        t_raw = entry[3] if len(entry) > 3 else t_yr      # Fs on its own tape has its own time axis
        obs = float(tg[k]["observed"]); unc = float(tg[k].get("uncertainty", 0.2))
        if k != "NPP":
            ax.plot(t_raw[:len(raw)], raw, lw=0.6, alpha=0.75, color="#3b7dd8", label="sim (raw cadence)")
            ax.plot(years + 0.5, ann, "o-", color="#12457a", lw=1.6, ms=4, label=lab)
        else:
            ax.bar(years, ann, width=0.7, color="#e0913a", label=lab)
        ax.axhspan(obs * (1 - unc), obs * (1 + unc), color="#d1495b", alpha=0.13, zorder=0)
        ax.axhline(obs, color="#d1495b", ls="--", lw=1.8, label=f"obs {obs:g} +/- {unc*100:.0f}%")
        ax.axvspan(w0, w1 + 1, color="#888", alpha=0.07, zorder=0)
        ax.set_ylabel(f"{k}  ({units.get(k,'')})")
        ax.legend(fontsize=9, loc="upper left")
        ax.grid(alpha=0.3)
    axes[-1].set_xlabel("year")
    fig.suptitle(a.title or f"sim vs obs — {Path(a.tape).parent.name}  (grey = scored window {w0}-{w1})",
                 fontsize=13)
    fig.tight_layout(rect=[0, 0, 1, 0.975])
    out = outdir / "sim_vs_obs_timeseries.png"
    fig.savefig(out, dpi=130); plt.close(fig)
    print(f"\nfigure -> {out}")
    print(f"csv    -> {outdir / 'sim_vs_obs_window_means.csv'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
