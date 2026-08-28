"""Tests for tools/validate_model_targets.py — the backend-dispatched targets.yaml gate.

Driven through the real CLI rather than an internal function, because the whole check lives
inside `main()`; a subprocess test pins the actual contract (exit code + rule tags) and stays
valid if the internals are later refactored.

Target docs are BUILT AS DICTS and yaml-dumped rather than assembled from indented string
fragments — a dedent/concat fixture silently produced unparseable YAML while still returning
a plausible-looking exit code, which is exactly the sort of fixture bug that makes a test
report on nothing.

Exit codes under test: 0 clean · 1 warnings only · 2 any error.

Author: Jing Tao with Claude
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest
import yaml

REPO = Path(__file__).resolve().parent.parent
VALIDATOR = REPO / "tools" / "validate_model_targets.py"


def _run(targets_path: Path, model: str = "ecosim"):
    """Run the validator CLI; return (returncode, combined output)."""
    res = subprocess.run(
        [sys.executable, str(VALIDATOR), "--model", model, "--targets", str(targets_path)],
        capture_output=True, text=True, cwd=str(REPO),
    )
    return res.returncode, res.stdout + res.stderr


def _write(tmp_path: Path, target: dict, name: str = "NPP") -> Path:
    """Write a minimal but REAL targets.yaml carrying one target.

    NPP_pft is active-by-default in EcoSIM's registry, so this isolates the time-reduction
    rule (G6) from the variable rules (G2/G3).
    """
    doc = {
        "site": "TestSite",
        "model": "ecosim",
        "start_year": 2006,
        "cost_config": {"error_method": "relative_error", "aggregation_method": "rmsre"},
        "targets": {name: target},
    }
    p = tmp_path / "targets.yaml"
    p.write_text(yaml.safe_dump(doc, sort_keys=False))
    # Fail loudly here rather than let a malformed fixture mimic a validator verdict.
    assert yaml.safe_load(p.read_text())["targets"][name], "fixture did not round-trip"
    return p


def _base(**extra) -> dict:
    t = {"variable": "NPP_pft", "pft": 1, "reduce": "annual", "observed": 500.0,
         "units": "gC/m2/yr"}
    t.update(extra)
    return t


def test_window_years_only_target_is_accepted(tmp_path):
    """A `window_years`-only target must NOT raise G6.

    REGRESSION (2026-08-14): G6 tested only for the literal keys `window` and `time`, so a
    target using `window_years` -- the leap-safe field the EcoSIM backend actually PREFERS
    (`models/ecosim/backend.py::_select_years`: "prefer explicit `window_years` (absolute
    calendar years), else fall back to the legacy timestep `window`") -- was reported as
    having no time reduction at all. That was 7 false errors across the two live EcoSIM
    cases, and it got WORSE the more a targets file was modernised off the legacy field.
    """
    p = _write(tmp_path, _base(window_years=[2006, 2023]))
    rc, out = _run(p)
    assert "[G6]" not in out, f"window_years must satisfy the time-reduction rule:\n{out}"
    assert rc == 0, f"expected a clean pass, got rc={rc}:\n{out}"


def test_legacy_window_still_accepted(tmp_path):
    """The legacy `window` field must keep working — the fix ADDS a field, never replaces one.

    PFLOTRAN's targets use `window` (in hours) and BioCON's older targets carry both.
    """
    p = _write(tmp_path, _base(window=[4380, 8395]))
    rc, out = _run(p)
    assert "[G6]" not in out, out
    assert rc == 0, out


def test_no_time_field_at_all_still_errors(tmp_path):
    """The rule must still FAIL when NO time reduction is given — otherwise the fix would
    turn a real check into one that cannot fail (`feedback_a_check_that_cannot_fail`)."""
    p = _write(tmp_path, _base())
    rc, out = _run(p)
    assert "[G6]" in out, f"a target with no window/time/window_years must raise G6:\n{out}"
    assert rc == 2, out


@pytest.mark.parametrize("bad,why", [
    ([2023, 2006], "lo > hi"),
    ([2006], "not a 2-element list"),
])
def test_malformed_window_years_errors(tmp_path, bad, why):
    """A malformed `window_years` must be caught, not merely accepted for being present.

    Mirrors the shape check the legacy `window` branch already had; without it, adding
    window_years to the accepted set would let `[2023, 2006]` through as "a time reduction
    is defined" and fail later inside the reducer instead.
    """
    p = _write(tmp_path, _base(window_years=bad))
    rc, out = _run(p)
    assert "[G6]" in out, f"malformed window_years ({why}) must raise G6:\n{out}"
    assert rc == 2, out


def test_real_lusignan_targets_have_no_false_G6():
    """The live EcoSIM_Lusignan file must not produce a G6: its targets are window_years-only,
    so before the fix they errored falsely.

    Deliberately asserts ONLY the invariant, not the file's CONTENT. The first version of this
    test also asserted `[G5]` on the strength of that case's `observed: null` placeholders --
    and failed within four minutes, because a concurrent session replaced the placeholder file
    with real observations (mtime 10:42 vs this test's 10:38). A case under active onboarding
    is someone else's moving artifact; binding a test to its current values makes their normal
    progress look like a regression here. G5's own coverage is synthetic, below.
    """
    live = REPO / "use_cases" / "EcoSIM_Lusignan" / "validation" / "targets.yaml"
    if not live.exists():
        pytest.skip("EcoSIM_Lusignan case not present in this checkout")
    rc, out = _run(live)
    assert "[G6]" not in out, f"live Lusignan targets must not trip G6:\n{out}"


def test_missing_observed_still_raises_G5(tmp_path):
    """The RED gate for an unfilled target, pinned synthetically so it does not depend on any
    live case still being mid-onboarding (see the note in the Lusignan test above)."""
    t = _base()
    t["window_years"] = [1, 5]
    t.pop("observed", None)
    p = _write(tmp_path, t)
    rc, out = _run(p)
    assert rc == 2 and "[G5]" in out, f"a target with no scalar `observed` must ERROR:\n{out}"


def test_real_biocon_fs_no_longer_false_G6():
    """EcoSIM_BioCON's `Fs` carries `window_years` only, so it was a FALSE G6 error pre-fix."""
    live = REPO / "use_cases" / "EcoSIM_BioCON" / "validation" / "targets.yaml"
    if not live.exists():
        pytest.skip("EcoSIM_BioCON case not present in this checkout")
    rc, out = _run(live)
    assert "[G6] Fs" not in out, f"Fs is window_years-only and must not trip G6:\n{out}"


def test_biocon_SOC_is_prescribed_initialization_and_never_a_target():
    """SOC is an INPUT, not a target -- the strongest assertion in this file.

    The four SOC_* depth stocks are the observations the run's INITIAL soil-carbon profile was
    built from (use_cases/EcoSIM_BioCON/memory/logs/20260718a_SOC_Prescribed_Initialization_And_-
    Extraction.md: "The initial SOC was built from the site observations ... Scoring it rewards
    the input and penalizes soil-BGC drift"). A model handed a value reproduces it; scoring that
    measures the prescription.

    This is pinned as a test because prose did not hold it. The PI stated it repeatedly, a
    dedicated log recorded it on 2026-07-18, and the entries still sat under `targets:` on
    2026-08-15 -- by which point they were being reasoned about as parked targets awaiting a
    time reduction, i.e. the fix under consideration was to SCORE them. A test fails; a log
    has to be re-read to be obeyed.
    """
    import yaml
    live = REPO / "use_cases" / "EcoSIM_BioCON" / "validation" / "targets.yaml"
    if not live.exists():
        pytest.skip("EcoSIM_BioCON case not present in this checkout")
    doc = yaml.safe_load(live.read_text())
    soc = {"SOC_0_10cm", "SOC_10_20cm", "SOC_20_40cm", "SOC_40_60cm"}

    leaked = soc & set(doc.get("targets", {}))
    assert not leaked, (
        f"{sorted(leaked)} are back under `targets:`. SOC prescribes the initial soil carbon; "
        f"scoring it rewards the input. It belongs in `prescribed_initialization:`.")
    assert soc <= set(doc.get("prescribed_initialization", {})), (
        f"the SOC observations must be PRESERVED under `prescribed_initialization:`, not "
        f"deleted -- they are the provenance of the initial profile. Found: "
        f"{sorted(doc.get('prescribed_initialization', {}))}")
    assert set(doc["targets"]) == {"Fs", "NPP", "plant_C"}, (
        f"BioCON scores exactly three targets; got {sorted(doc['targets'])}")


def test_G14_flags_a_name_in_both_blocks(tmp_path):
    """The mechanical guard: an entry cannot be both an input and a scored target."""
    import yaml
    p = _write(tmp_path, {**_base(), "window_years": [1, 5]})
    doc = yaml.safe_load(p.read_text())
    doc["prescribed_initialization"] = {n: {"observed": 1.0} for n in doc["targets"]}
    p.write_text(yaml.safe_dump(doc))
    rc, out = _run(p)
    assert rc == 2 and "[G14]" in out, f"a name in both blocks must ERROR:\n{out}"


# ---------------------------------------------------------------------------
# G6 and `track:` — a PARKED target is not a broken target (2026-08-15)
# ---------------------------------------------------------------------------
def test_parked_target_without_a_time_field_WARNS_instead_of_erroring(tmp_path):
    """A target explicitly off the scoring path (`track:` set) is not a defect in a live target,
    so it must not inflate the ERROR count -- but it must still be REPORTED (handoff 20260815a
    item 2: these must not be silenced).

    The warning must NOT presume the target is on its way to being scored. BioCON's SOC_* was
    the motivating case and the presumption was wrong there: SOC is a prescribed input, so the
    "wire a time reduction" repair the earlier wording implied was the wrong direction entirely.
    Hence the assertion on `prescribed_initialization` below -- the warning has to raise the
    question (input, or unfinished target?) rather than answer it."""
    p = _write(tmp_path, {**_base(), "track": "soil_bgc"})
    rc, out = _run(p)
    assert rc != 2, f"a parked target should not be an ERROR:\n{out}"
    assert "[G6]" in out and "track: soil_bgc" in out, f"the signal must survive:\n{out}"
    assert "prescribed_initialization" in out, (
        f"the warning must offer the INPUT reading, not just assume unfinished wiring:\n{out}")


def test_a_LIVE_target_without_a_time_field_still_ERRORS(tmp_path):
    """The narrowing must not become a hole: no `track:` means on the scoring path means error."""
    p = _write(tmp_path, _base())
    rc, out = _run(p)
    assert rc == 2 and "[G6]" in out


def test_real_biocon_targets_validate_clean():
    """End-to-end on the live file: no errors.

    The earlier version of this test asserted the four SOC names still APPEARED in the output,
    to prove `track:` had not silenced them. That assertion is now wrong at the root: SOC is not
    a target, so the validator is correct to say nothing about it, and demanding its name in
    target-validation output was demanding the wrong thing loudly. What replaced it is
    test_biocon_SOC_is_prescribed_initialization_and_never_a_target, which checks the file's
    structure directly instead of inferring it from a message."""
    real = REPO / "use_cases/EcoSIM_BioCON/validation/targets.yaml"
    if not real.is_file():
        pytest.skip("BioCON targets file absent")
    rc, out = _run(real)
    assert rc != 2, f"live BioCON file should have no errors:\n{out}"
