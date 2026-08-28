#!/usr/bin/env python3
"""Extract + plot an ADAPTER (non-FATES) model ensemble's trajectories.

The adapter analog of FATES's phases/phase1_exploration/extract_sensitivity_outputs.py +
tools/plot_ensemble_cases.py, done through the model's ModelBackend (docs/38 additive; no
CIME, no shared-file edit). Runs on a PARTIAL ensemble too (only cases with an output tape),
so you can watch progress as an array fills in.

For every completed case it:
  0. records each case's backend.check_case_status, so a STARTED-but-truncated case is never
     reported as a completed one (this script deliberately runs on a partial ensemble; what it must
     not do is call a partial case finished),
  1. extracts a per-PFT carbon-pool time series via backend.extract_history_variables,
  2. reduces it to an ANNUAL-PEAK trajectory (the establishment / perennial-compounding view),
  3. writes a per-case CSV (final-year value, target-window mean, established flag) + an .npz of
     all trajectories, and
  4. plots every case's trajectory on a log axis, highlighting any that ESTABLISH, overlaid on an
     optional reference tape + a target line.

Env defaults (source a2mc_noncime_config.sh + the site config first): A2MC_MODEL, A2MC_OUTPUT_DIR,
A2MC_CASE_NAME_PATTERN. Reference tape + target are optional flags.
"""

from __future__ import annotations

import argparse
import csv
import os
import re
import sys
from pathlib import Path
from typing import Optional

import numpy as np

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

# Imported AFTER the sys.path insert above — this script is run as a file, not as a package
# module, so `tools` is not importable until the repo root is on the path.
from tools.calendar_blocks import growing_season_day_slice, tag_hourly, year_blocks  # noqa: E402
from tools.subdaily_window_reduce import growing_season_window_mean_abs  # noqa: E402


def _pft1_annual_peak(backend, tape_dir: Path, variables, pft_index0: int, start_year: int):
    """Sum `variables` on PFT `pft_index0`, reduce to per-year peak. Returns (years, peaks) or None."""
    try:
        ex = backend.extract_history_variables(tape_dir, list(variables))
    except Exception:
        return None
    series = None
    for v in variables:
        a = np.asarray(ex[v]).astype(float)
        a[np.abs(a) > 1e29] = np.nan
        col = a[:, pft_index0] if a.ndim == 2 else a
        series = col if series is None else series + col
    blocks = year_blocks(len(series), start_year)
    if not blocks:
        return None
    peaks = np.array([np.nanmax(series[lo:hi]) if np.any(~np.isnan(series[lo:hi])) else np.nan
                      for _, lo, hi in blocks])
    return np.array([y for y, _, _ in blocks]), peaks


def _annual_npp(backend, tape_dir: Path, npp_var: str, start_year: int):
    """Annual NPP (gC/m2/yr) per year = Σ_PFT daily NPP_pft rate (gC/m2/hr), summed over the year × 24 h/day.
    (Matches targets.yaml `reduce: annual` on NPP_pft; do NOT diff ECO_NPP_col.) Returns (years, ann) or None."""
    try:
        ex = backend.extract_history_variables(tape_dir, [npp_var])
    except Exception:
        return None
    a = np.asarray(ex[npp_var]).astype(float); a[np.abs(a) > 1e29] = np.nan
    daily = np.nansum(a, axis=1) if a.ndim == 2 else a      # Σ over PFTs -> (time,) daily-mean rate gC/m2/hr
    blocks = year_blocks(len(daily), start_year)
    if not blocks:
        return None
    ann = np.array([np.nansum(daily[lo:hi]) * 24.0 for _, lo, hi in blocks])  # ×24 h/day -> gC/m2/yr
    return np.array([y for y, _, _ in blocks]), ann


def _annual_fs(backend, tape_dir: Path, fs_var: str, start_year: int,
               fs_spec: Optional[dict] = None, season_months=(5, 9)):
    """Annual growing-season mean |Fs| per year, using the reduction the TARGET declares.

    Two paths, chosen by the target's own `tape:` rather than by an assumption here:

    * `tape: h1` (or any non-h0 sub-daily tape) -> extract that tape and hand off to
      `tools.subdaily_window_reduce.growing_season_window_mean_abs`, the SAME function
      `models/ecosim/backend.py` scores with, restricted to the target's `daytime_window_hours`.
    * otherwise -> growing-season mean on the daily tape.

    Why this is not just a wider default: the daily tape has already averaged the diel cycle away,
    so a daytime window is not merely inconvenient on h0, it is meaningless. Computing Fs here in a
    way the scorer does not use produced a live plot that disagreed with the score for reasons no
    reader could see -- 2.0125 on the plot vs 2.266 scored, for the same case (PI catch, 2026-08-16).
    The season window is leap-aware; the old hardcoded ``gs=(120, 273)`` is May-Sep for a NON-leap
    year only.
    """
    fs_spec = fs_spec or {}
    tape = fs_spec.get("tape")
    hours = fs_spec.get("daytime_window_hours")

    if tape and tape != "h0" and hours:
        try:
            ex = backend.extract_history_variables(tape_dir, [fs_var], tape=tape)
        except Exception:
            return None
        a = np.asarray(ex[fs_var]).astype(float); a[np.abs(a) > 1e29] = np.nan
        vals = np.abs(a[:, 0] if a.ndim == 2 else a)
        try:
            yr, mo, hod = tag_hourly(len(vals), start_year)
        except ValueError:
            return None
        out_y, out_v = [], []
        for y in sorted(set(yr.tolist())):
            if (yr == y).sum() < 365 * 24:        # drop an incomplete trailing year, like the backend
                continue
            v = growing_season_window_mean_abs(vals, hod, mo, yr, window_hours=hours,
                                               season_months=season_months, window_years=(y, y))
            out_y.append(y); out_v.append(v)
        return (np.array(out_y), np.array(out_v)) if out_y else None

    try:
        ex = backend.extract_history_variables(tape_dir, [fs_var])
    except Exception:
        return None
    a = np.asarray(ex[fs_var]).astype(float); a[np.abs(a) > 1e29] = np.nan
    fs = a[:, 0] if a.ndim == 2 else a
    blocks = year_blocks(len(fs), start_year)
    if not blocks:
        return None
    ann = []
    for y, lo, hi in blocks:
        d0, d1 = growing_season_day_slice(y, season_months)
        ann.append(np.nanmean(np.abs(fs[lo + d0:lo + d1])))
    return np.array([y for y, _, _ in blocks]), np.array(ann)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--model", default=os.environ.get("A2MC_MODEL"))
    ap.add_argument("--run-root", default=os.environ.get("A2MC_OUTPUT_DIR"))
    ap.add_argument("--case-pattern", default=os.environ.get("A2MC_CASE_NAME_PATTERN", "case{N}"))
    ap.add_argument("--variables", default="SHOOT_C_pft,Root_C_pft",
                    help="comma-list summed into the pool trajectory (default EcoSIM plant C)")
    ap.add_argument("--pft", type=int, default=1, help="1-based PFT id to track (default 1)")
    ap.add_argument("--start-year", type=int, default=2000)
    ap.add_argument("--target-window", default="2012,2022", help="y0,y1 mean window")
    ap.add_argument("--target-value", type=float, default=None, help="observed target for the overlay line")
    ap.add_argument("--establish-frac", type=float, default=0.1,
                    help="a case 'establishes' if its target-window mean >= this fraction of --target-value")
    ap.add_argument("--reference-tape", default=None, help="optional reference h0 tape to overlay")
    ap.add_argument("--out-prefix", default=None, help="output path prefix (default <run-root>/ensemble_trajectories)")
    ap.add_argument("--npp-var", default="NPP_pft", help="per-PFT NPP rate var for the NPP panel ('' to skip)")
    ap.add_argument("--npp-target", type=float, default=389.0, help="observed annual-NPP target (gC/m2/yr)")
    ap.add_argument("--fs-var", default="CO2_SEMIS_FLX_col", help="surface CO2 flux var for the Fs panel ('' to skip)")
    ap.add_argument("--fs-target", type=float, default=6.2, help="observed growing-season Fs target (umol/m2/s)")
    ap.add_argument("--targets", default=None,
                    help="site targets.yaml. When given, the Fs panel uses the REDUCTION THE TARGET "
                         "DECLARES (its `tape` and `daytime_window_hours`) via the same reducer the "
                         "scorer calls, so the plot and the score cannot silently disagree. Without "
                         "it the Fs panel falls back to a growing-season mean on the daily tape.")
    args = ap.parse_args()

    for k, v in [("--model", args.model), ("--run-root", args.run_root)]:
        if not v:
            print(f"ERROR: {k} unset (source the config or pass it).", file=sys.stderr); return 1

    import importlib
    from models import registry
    importlib.import_module(f"models.{args.model}")
    backend = registry.get_model(args.model)

    # The Fs reduction comes from the TARGET SPEC when one is supplied, never from a constant in
    # this file. Without --targets the Fs panel is a growing-season mean on the daily tape, which
    # is a DIFFERENT STATISTIC from a daytime-windowed score -- so say so rather than let a reader
    # assume the plot and the score are the same number.
    fs_spec = {}
    if args.targets:
        import yaml
        tg = yaml.safe_load(Path(args.targets).read_text()).get("targets", {})
        fs_spec = tg.get("Fs", {}) or {}
        if fs_spec.get("tape") and fs_spec["tape"] != "h0" and fs_spec.get("daytime_window_hours"):
            print(f"Fs panel: target-driven — tape={fs_spec['tape']}, "
                  f"hours={fs_spec['daytime_window_hours']}, via the scorer's own reducer.")
        else:
            print(f"Fs panel: {args.targets} declares no sub-daily tape + daytime window for Fs; "
                  f"falling back to a growing-season mean on the daily tape.")
    elif args.fs_var:
        print("Fs panel: NO --targets given, so this is a growing-season mean on the DAILY tape. "
              "If the site scores Fs with a daytime window on an hourly tape, this number is a "
              "different statistic from the score — pass --targets to make them agree.")

    variables = [s.strip() for s in args.variables.split(",")]
    pft0 = args.pft - 1
    run_root = Path(args.run_root)
    y0, y1 = (int(x) for x in args.target_window.split(","))
    out_prefix = Path(args.out_prefix) if args.out_prefix else run_root / "ensemble_trajectories"

    # Discover cases that have STARTED (a tape exists), and separately record which have actually
    # COMPLETED. Those are NOT the same question and this script used to conflate them: the comment
    # here read "a tape = a completed case", but EcoSIM opens its single h0 tape at INITIALISATION,
    # so a tape means the run started and a truncated run leaves identical evidence.
    #
    # Plotting a partial ensemble is this script's PURPOSE -- you watch an array fill in -- so
    # started-but-incomplete cases are still included. What changes is that they are no longer
    # CALLED complete: the status travels into the per-case CSV, and the counts are reported
    # separately, so a truncated trajectory is not read as a converged one.
    pat = re.compile(re.escape(args.case_pattern).replace(r"\{N\}", r"(\d+)"))
    cases, status_of = [], {}
    for d in sorted(run_root.glob(args.case_pattern.replace("{N}", "*"))):
        m = pat.search(d.name)
        if not m:
            continue
        if not (list(d.glob("*.ecosim.h0.*.nc")) or list(d.glob("*.h0.*.nc"))):
            continue
        idx = int(m.group(1))
        try:
            status_of[idx] = backend.check_case_status(d)
        except Exception:
            status_of[idx] = "UNKNOWN"
        cases.append((idx, d))
    cases.sort()
    n_done = sum(1 for i, _ in cases if status_of.get(i) == "COMPLETED")
    print(f"Model {args.model}: {len(cases)} case(s) with output under {run_root} "
          f"— {n_done} COMPLETED, {len(cases) - n_done} started but not finished")
    if not cases:
        print("no cases with output yet — run again once tapes appear.")
        return 0

    rows, trajs, npp_trajs, fs_trajs, established = [], {}, {}, {}, []
    partial = []
    for idx, d in cases:
        res = _pft1_annual_peak(backend, d, variables, pft0, args.start_year)
        if res is None:
            continue
        yrs, peaks = res
        trajs[idx] = (yrs, peaks)
        if args.npp_var:
            r = _annual_npp(backend, d, args.npp_var, args.start_year)
            if r:
                npp_trajs[idx] = r
        if args.fs_var:
            r = _annual_fs(backend, d, args.fs_var, args.start_year, fs_spec=fs_spec)
            if r:
                fs_trajs[idx] = r
        # A window mean requires the WHOLE window, not just an overlap with it. Same rule as
        # `models/ecosim/backend.py::_select_years`, and it must be the same rule or this CSV
        # cannot be used as the scoring extract.
        #
        # Measured on the R3 c00 probe: cases 56 (ran through 2015) and 63 (through 2018) overlap
        # the 2012-2022 window, so an overlap-based mean returned Fs 268.9 and 275.5 against a
        # normal range of ~0.1-8. Those two values then failed GATE_MONOTONE for the whole probe.
        # What goes missing is never random -- a run ends early BECAUSE it went unstable, so the
        # surviving tail is biased toward the blow-up.
        def _window_mean(yy, aa):
            need = set(range(y0, y1 + 1))
            if not need.issubset(set(int(v) for v in yy)):
                return np.nan, False
            m = (yy >= y0) & (yy <= y1)
            return (float(np.nanmean(aa[m])) if m.any() else np.nan), True

        win_mean, full_cov = _window_mean(yrs, peaks)
        est = bool(args.target_value and full_cov and win_mean >= args.establish_frac * args.target_value)
        if est:
            established.append(idx)
        if not full_cov:
            partial.append(idx)

        def _wmean(td):
            if idx not in td:
                return np.nan
            yy, aa = td[idx]
            return _window_mean(yy, aa)[0]
        # `status` carries the backend's verdict into the CSV so a reader can tell a converged
        # trajectory from a truncated one. Without it every row looked equally final.
        rows.append({"case": idx, "status": status_of.get(idx, "UNKNOWN"),
                     "plantC_final": float(peaks[-1]), f"plantC_mean_{y0}_{y1}": win_mean,
                     f"NPP_mean_{y0}_{y1}": _wmean(npp_trajs), f"Fs_mean_{y0}_{y1}": _wmean(fs_trajs),
                     "established": est, "full_window_coverage": full_cov})

    if partial:
        print(f"  {len(partial)} case(s) do NOT cover the whole {y0}-{y1} window and are reported "
              f"as NaN, not as a partial-window mean: {partial[:15]}"
              f"{' ...' if len(partial) > 15 else ''}")

    # write per-case CSV + trajectory npz
    csv_path = Path(f"{out_prefix}.csv")
    with csv_path.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["case", "status", "plantC_final", f"plantC_mean_{y0}_{y1}",
                                          f"NPP_mean_{y0}_{y1}", f"Fs_mean_{y0}_{y1}", "established",
                                          "full_window_coverage"])
        w.writeheader(); w.writerows(rows)
    np.savez(f"{out_prefix}.npz", **{f"case{idx}": np.vstack(t) for idx, t in trajs.items()})

    # plot — one panel per target (plant_C log, NPP, Fs), all cases vs target + reference
    import matplotlib; matplotlib.use("Agg"); import matplotlib.pyplot as plt
    def _ref(fn):
        return fn(backend, Path(args.reference_tape).parent) if (args.reference_tape and Path(args.reference_tape).exists()) else None
    panels = [("plant C (Σpool, ann peak)  [gC/m²]", trajs, args.target_value, "log",
               lambda b, p: _pft1_annual_peak(b, p, variables, pft0, args.start_year))]
    if npp_trajs:
        panels.append(("NPP (annual, ΣPFT)  [gC/m²/yr]", npp_trajs, args.npp_target, "linear",
                       lambda b, p: _annual_npp(b, p, args.npp_var, args.start_year)))
    if fs_trajs:
        panels.append(("Fs (grow-season |mean|)  [µmol/m²/s]", fs_trajs, args.fs_target, "linear",
                       lambda b, p: _annual_fs(b, p, args.fs_var, args.start_year)))
    fig, axes = plt.subplots(len(panels), 1, figsize=(12, 3.1 * len(panels)), sharex=True)
    if len(panels) == 1:
        axes = [axes]
    for ax, (label, td, tgt, scale, reffn) in zip(axes, panels):
        plot = ax.semilogy if scale == "log" else ax.plot
        for i, (yy, aa) in td.items():
            col = "tab:green" if (i in established and label.startswith("plant")) else "0.6"
            plot(yy, np.clip(aa, 1e-8, None) if scale == "log" else aa, lw=0.4, color=col, alpha=0.5)
        r = _ref(reffn)
        if r:
            plot(r[0], np.clip(r[1], 1e-8, None) if scale == "log" else r[1], color="tab:blue", lw=2, label="reference")
        if tgt:
            ax.axhline(tgt, color="k", ls="--", lw=1, label=f"target {tgt:g}")
        ax.axvspan(y0, y1, color="gold", alpha=0.1)
        ax.set_ylabel(label, fontsize=8); ax.grid(True, which="both", alpha=0.3)
        if ax is axes[0] and ax.get_legend_handles_labels()[0]:
            ax.legend(fontsize=8, loc="center right")
    axes[-1].set_xlabel("year")
    axes[0].set_title(f"{args.model} ensemble vs targets — {len(trajs)} cases; {len(established)} establish "
                      f"(plant C ≥ {args.establish_frac:g}× target in {y0}-{y1})")
    png = f"{out_prefix}.png"
    plt.tight_layout(); plt.savefig(png, dpi=120)

    print(f"  established (plant C ≥ {args.establish_frac:g}× target): {len(established)} / {len(trajs)}"
          + (f"  cases {established[:15]}" if established else ""))
    print(f"  panels: plant_C" + (" + NPP" if npp_trajs else "") + (" + Fs" if fs_trajs else ""))
    print(f"  csv:  {csv_path}\n  npz:  {out_prefix}.npz\n  plot: {png}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
