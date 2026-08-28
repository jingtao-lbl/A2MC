"""Any tool that reports a SCORED TARGET must agree with the backend's reducer.

WHY THIS TEST EXISTS. On 2026-08-14 a promoted plotting tool computed Fs from the DAILY history
tape with an approximate season mask, while the scored definition is
`growing_season_daytime_mean_abs` on the HOURLY tape. It produced a plausible number
(6.550) that was not the scored quantity (6.979). Nothing failed; the figure simply disagreed with
the score for a reason no reader could see. The same session's scorer separately read
`evaluate_model_case`'s ERRORS array where it meant SIMULATED, which would have reported
"Fs not reachable, retire R3's premise" on every possible dataset.

Neither was a knowledge failure -- the definition was written in 15 calibration logs, a report
authored that morning, and a config comment. It was a BINDING failure: nothing forced the
comparison at the point of use. This test is that binding.

THE CONTRACT: `models/<model>/backend.py::reduce_ecosystem` (through
`tools.model_evaluate_case.evaluate_model_case`) is the ONLY implementation of a scored-target
reduction. Anything else that reports one must reproduce it. A tool that "just plots" is not
exempt: a figure IS a claim about the scored quantity.

Skips when the reference case is absent (a fresh clone, or the public repo), like the other
reference-data tests here — but see `test_reference_case_is_present_on_perlmutter`, which fails
rather than skips where the data is supposed to exist, so a silent skip cannot hide a real break.

Author: Jing Tao with Claude.
"""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

# A COMPLETE hourly case: the only kind on which the daytime reduction is even defined.
REF_CASE = Path("~/EcoSIM_BioCON_fe075014/DIEL_hourly/HR_BEST")
TARGETS = REPO / "use_cases/EcoSIM_BioCON/validation/targets.yaml"
TOOL = REPO / "tools/plot_sim_vs_obs_timeseries_ecosim_biocon.py"
ON_PERLMUTTER = Path("/global/cfs").is_dir()

pytestmark = pytest.mark.skipif(
    not (REF_CASE.is_dir() and TARGETS.is_file()),
    reason="EcoSIM_BioCON reference hourly case not present")


def _scored_targets():
    import yaml
    tg = yaml.safe_load(TARGETS.read_text())["targets"]
    return [dict(name=k, **v) for k, v in tg.items() if v.get("track") != "soil_bgc"]


@pytest.fixture(scope="module")
def backend_values():
    """The authoritative values, straight from the backend reducer."""
    os.environ.setdefault("A2MC_VALIDATION_START_YEAR", "2000")
    from tools.model_evaluate_case import evaluate_model_case
    _cost, _errors, simulated = evaluate_model_case(REF_CASE, _scored_targets(), model="ecosim")
    return simulated


def test_reference_case_is_present_on_perlmutter():
    """A skip must not be able to hide a break on the machine that has the data."""
    if ON_PERLMUTTER:
        assert REF_CASE.is_dir(), f"reference case missing on a machine with /global/cfs: {REF_CASE}"


def test_backend_returns_the_three_scored_targets(backend_values):
    assert set(backend_values) == {"plant_C", "NPP", "Fs"}
    for k, v in backend_values.items():
        assert v == v and v > 0, f"{k} is not a finite positive value: {v}"


def test_Fs_is_the_DAYTIME_reduction_not_the_all_hours_one(backend_values):
    """Pins the distinction the tooling got wrong. If these ever coincide, either the targets file
    lost its daytime window or the reducer stopped honouring it — both are silent failures."""
    import yaml
    from tools.model_evaluate_case import evaluate_model_case
    r1r2 = REPO / "use_cases/EcoSIM_BioCON/validation/targets_R1R2.yaml"
    if not r1r2.is_file():
        pytest.skip("R1/R2 targets file absent")
    tg = yaml.safe_load(r1r2.read_text())["targets"]
    old = [dict(name="Fs", **tg["Fs"])]
    _, _, sim_old = evaluate_model_case(REF_CASE, old, model="ecosim")
    assert abs(backend_values["Fs"] - sim_old["Fs"]) > 0.1, (
        "the daytime and all-hours Fs are indistinguishable — the daytime window is not being "
        f"applied (daytime={backend_values['Fs']:.4f}, all-hours={sim_old['Fs']:.4f})")


def test_plotting_tool_reproduces_the_backend(tmp_path, backend_values):
    """THE BINDING. The figure's numbers must be the scored numbers."""
    env = {**os.environ, "A2MC_VALIDATION_START_YEAR": "2000"}
    h0 = sorted(REF_CASE.glob("*.ecosim.h0.*.nc"))
    assert h0, "no daily tape in the reference case"
    r = subprocess.run(
        [sys.executable, str(TOOL), "--tape", str(h0[0]), "--case-dir", str(REF_CASE),
         "--targets", str(TARGETS), "--outdir", str(tmp_path)],
        capture_output=True, text=True, env=env, timeout=900)
    assert r.returncode == 0, f"tool failed:\n{r.stdout[-2000:]}\n{r.stderr[-2000:]}"

    import csv
    rows = list(csv.DictReader((tmp_path / "sim_vs_obs_window_means.csv").open()))
    got = {row["target"]: float(row["sim_window_mean"]) for row in rows}
    assert set(got) == set(backend_values), f"tool reported {set(got)}, backend {set(backend_values)}"
    for k, ref in backend_values.items():
        assert abs(got[k] - ref) <= max(1e-6, abs(ref) * 1e-4), (
            f"{k}: tool reports {got[k]:.6g} but the backend scores {ref:.6g}. A tool that reports "
            f"a scored target must reproduce the backend reduction, not approximate it "
            f"(tools/plot_sim_vs_obs_timeseries_ecosim_biocon.py).")
