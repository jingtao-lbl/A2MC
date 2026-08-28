"""`check_setup_ready.py` must use the RIGHT targets validator for the active model.

The bug this locks (audit: `memory/dev_logs_adapterkit/20260816b`): the aggregate "ready for
Phase 0?" gate wrapped `tools/validate_targets_config.py`, which is FATES-shaped. Two of its rules
cannot be satisfied by any adapter target by construction -- R1 wants `PFT<id>_<var>` names, S3 wants
a `time_year`/`time_month` anchor -- so every adapter target produced exactly 2 spurious errors and
the gate could NEVER exit 0 for EcoSIM, PFLOTRAN or ATS. Measured 2026-08-16 and reproduced
2026-08-18: EcoSIM_BioCON 6, EcoSIM_Lusignan 6, PFLOTRAN_miniLEO 22 -- exactly 2 x n_targets.

WHAT WOULD MAKE THESE FAIL (named before writing them, per `feedback_a_check_that_cannot_fail`):
  1. the gate treats a warnings-only adapter result as blocking  -> unreachable gate again
  2. the gate stops blocking on real adapter errors              -> a gate that cannot fail
  3. FATES's contract changes (warnings start blocking, or errors stop)
  4. the FATES validator silently mis-checks an adapter file again instead of refusing
"""
from __future__ import annotations

import os
import pathlib
import re
import subprocess
import sys

import pytest

ROOT = pathlib.Path(__file__).resolve().parent.parent
PY = sys.executable

ADAPTER_CASES = [("EcoSIM_BioCON", "ecosim"),
                 ("EcoSIM_Lusignan", "ecosim"),
                 ("PFLOTRAN_miniLEO", "pflotran")]


def _targets(case):
    return ROOT / "use_cases" / case / "validation" / "targets.yaml"


# --- the normalisation, the half of the fix that dispatching alone does not give ----------

def test_warnings_only_never_blocks_an_adapter_case():
    """Mode 1. `validate_model_targets.py` returns 1 for WARNINGS ONLY, while the FATES validator
    returns 1 for ERRORS. Dispatching without normalising leaves EcoSIM_Lusignan (0 errors, 3
    warnings) still failing the gate."""
    sys.path.insert(0, str(ROOT))
    from tools.check_setup_ready import targets_check_verdict
    blocked, warned = targets_check_verdict("ecosim", 1)
    assert not blocked, "warnings-only must not block Phase 0"
    assert warned, "...but the gate should still say warnings were present"


def test_real_adapter_errors_still_block():
    """Mode 2 -- the anti-'check that cannot fail' guard."""
    sys.path.insert(0, str(ROOT))
    from tools.check_setup_ready import targets_check_verdict
    assert targets_check_verdict("ecosim", 2)[0], "rc>=2 is real errors and must block"


@pytest.mark.parametrize("rc,blocked", [(0, False), (1, True), (2, True)])
def test_fates_contract_is_unchanged(rc, blocked):
    """Mode 3. FATES must keep the exact previous behaviour: anything non-zero blocks."""
    sys.path.insert(0, str(ROOT))
    from tools.check_setup_ready import targets_check_verdict
    assert targets_check_verdict("fates", rc)[0] is blocked


# --- the refusal: the FATES validator must not mis-check an adapter file ------------------

@pytest.mark.parametrize("case,model", ADAPTER_CASES)
def test_fates_validator_refuses_an_adapter_targets_file(case, model):
    """Mode 4. Refusing must ROUTE, not dead-end: the message names the right tool.

    Precedent: the two LOG checkers were made to refuse each other's stream on 2026-08-14.
    """
    tgt = _targets(case)
    if not tgt.exists():
        pytest.skip(f"{case} has no targets.yaml")
    env = dict(os.environ, A2MC_MODEL=model)
    r = subprocess.run([PY, "tools/validate_targets_config.py", "--targets", str(tgt)],
                       cwd=ROOT, capture_output=True, text=True, env=env)
    assert r.returncode == 2, f"expected refusal (2), got {r.returncode}"
    assert "wrong tool" in r.stderr
    assert "validate_model_targets.py" in r.stderr, "refusal must name the right tool"


def test_fates_validator_still_accepts_a_fates_file():
    """The FATES path must not be collateral damage -- it is the only validator that understands
    SZPF resolution and the PFT<id>_<var> contract."""
    tgt = ROOT / "use_cases/ELM-FATES_Kougarok/validation/targets.yaml"
    if not tgt.exists():
        pytest.skip("Kougarok targets.yaml not present")
    env = dict(os.environ); env.pop("A2MC_MODEL", None)
    r = subprocess.run([PY, "tools/validate_targets_config.py", "--targets", str(tgt)],
                       cwd=ROOT, capture_output=True, text=True, env=env)
    assert "wrong tool" not in r.stderr, "a FATES file must NOT be refused"
    assert r.returncode != 2, "2 means refused/unusable; FATES must be validated"


# --- the audit's own acceptance criterion -------------------------------------------------

@pytest.mark.parametrize("case,model", ADAPTER_CASES)
def test_case_passing_its_own_validator_is_not_failed_by_the_gate(case, model):
    """The one-line test the audit said would have caught this:

        "for each onboarded model, a case that passes its own target validator
         must not fail the aggregate gate on the targets check."
    """
    tgt = _targets(case)
    if not tgt.exists():
        pytest.skip(f"{case} has no targets.yaml")
    sys.path.insert(0, str(ROOT))
    from tools.check_setup_ready import targets_check_verdict
    r = subprocess.run([PY, "tools/validate_model_targets.py", "--model", model,
                        "--targets", str(tgt)], cwd=ROOT, capture_output=True, text=True)
    own_validator_ok = r.returncode < 2          # 0 clean, 1 warnings -- neither is an error
    if not own_validator_ok:
        pytest.skip(f"{case} has REAL target errors; this test is about spurious ones")
    assert not targets_check_verdict(model, r.returncode)[0], (
        f"{case} passes {model}'s own validator but the gate would still block it")


# --- check_calibration_rounds: suplphos/suplnitro are ELM-family only ---------------------

def _rounds(case, env_extra):
    env = dict(os.environ, A2MC_USE_CASE_DIR=str(ROOT / "use_cases" / case), **env_extra)
    env.pop("A2MC_MODEL", None)
    env.update(env_extra)
    return subprocess.run([PY, "tools/check_calibration_rounds.py"],
                          cwd=ROOT, capture_output=True, text=True, env=env).stdout


SUPL = re.compile(r"protocol\.(suplphos|suplnitro)\.")


def test_suplphos_is_skipped_for_an_adapter_model():
    """`suplphos`/`suplnitro` are ELM nutrient settings keyed by CIME spin-up phases
    (ADSP/RGSP/TRANS). A standalone-binary model has no CIME phases, and the adapter generator
    never emits the keys -- so checking them compared `None` against the env default "NONE" and
    failed 6 times for EVERY adapter case. That was EcoSIM_Lusignan's last gate blocker."""
    out = _rounds("EcoSIM_Lusignan", {"A2MC_MODEL": "ecosim"})
    assert not SUPL.search(out), "suplphos/suplnitro must not be CHECKED for an adapter model"


def test_the_skip_is_reported_not_silent():
    """A check that vanishes is indistinguishable from one that passed -- which is how the
    original gap survived. The skip must be visible, with its reason."""
    out = _rounds("EcoSIM_Lusignan", {"A2MC_MODEL": "ecosim"})
    assert "ELM-family only" in out, "the skip must be reported"
    assert "[–]" in out, "and marked N/A, not as a pass"


def test_fates_still_gets_all_six_checks():
    """The FATES path must be untouched: these are correct and load-bearing for Kougarok."""
    if not (ROOT / "use_cases/ELM-FATES_Kougarok/config/calibration_rounds.yaml").exists():
        pytest.skip("Kougarok round record not present")
    out = _rounds("ELM-FATES_Kougarok", {})
    assert len(SUPL.findall(out)) == 6, f"expected 6 suplphos/suplnitro rows, got {len(SUPL.findall(out))}"
    assert "ELM-family only" not in out, "FATES must NOT be skipped"


def test_every_check_prints_a_row():
    """Regression for a bug introduced WHILE adding the skip: the new `for s in skipped:` loop was
    inserted between the check loop and its `print(line)`, so the check loop built rows it never
    printed and `print(line)` ran only inside the skip loop. Kougarok then reported '10
    mismatch(es)' with ZERO rows shown. A report that hides its own rows is worse than the bug it
    was added to fix."""
    if not (ROOT / "use_cases/ELM-FATES_Kougarok/config/calibration_rounds.yaml").exists():
        pytest.skip("Kougarok round record not present")
    out = _rounds("ELM-FATES_Kougarok", {})
    rows = [l for l in out.splitlines() if l.strip().startswith(("[✓]", "[✗]", "[–]"))]
    assert len(rows) >= 10, f"report printed {len(rows)} rows; the check loop is not printing"


# --- the ROUND RECORD check needed the same dispatch, and had not been given it ------------
#
# Found 2026-08-26 while auditing how calibration_rounds.yaml and binary_archive_manifest.json are
# triggered. `check_setup_ready.py` dispatched the TARGETS validator by model (above) and then ran
# the FATES round-record checker unconditionally. That pair is FATES-config-coupled: it asserts CIME
# spin-up phases an adapter round correctly lacks, so it reported "2 mismatch(es)" on EcoSIM_BioCON
# R3 -- a round the adapter checker passes clean -- and told the user to regenerate with the FATES
# generator, which would have overwritten a correct file with a FATES-shaped one.
#
# WHAT WOULD MAKE THESE FAIL:
#   1. an adapter model routed back to the FATES checker      -> the false mismatch returns
#   2. FATES routed to the adapter checker                    -> a real regression for the ELM line
#   3. the checker/generator pair drifting apart              -> "regenerate with X" naming the wrong X

@pytest.mark.parametrize("model", ["ecosim", "pflotran", "ats", "EcoSIM"])
def test_an_adapter_model_gets_the_ADAPTER_round_checker(model):
    sys.path.insert(0, str(ROOT))
    from tools.check_setup_ready import rounds_tools_for
    checker, generator = rounds_tools_for(model)
    assert "adapter" in checker, f"{model} routed to the FATES round checker: {checker}"
    assert "adapter" in generator, f"{model} pointed at the FATES generator: {generator}"


@pytest.mark.parametrize("model", ["fates", "FATES", "", None])
def test_fates_and_the_default_keep_the_FATES_round_checker(model):
    """Mode 2 -- the ELM line must be byte-for-byte unchanged, including the unset default."""
    sys.path.insert(0, str(ROOT))
    from tools.check_setup_ready import rounds_tools_for
    checker, generator = rounds_tools_for(model)
    assert checker == "tools/check_calibration_rounds.py"
    assert generator == "tools/generate_calibration_rounds.py"


@pytest.mark.parametrize("model", ["fates", "ecosim"])
def test_both_tools_named_actually_exist(model):
    """Mode 3. A gate that tells you to run a file that is not there is worse than a silent one."""
    sys.path.insert(0, str(ROOT))
    from tools.check_setup_ready import rounds_tools_for
    for rel in rounds_tools_for(model):
        assert (ROOT / rel).is_file(), f"{model}: {rel} does not exist"


def test_the_adapter_case_actually_passes_its_own_checker():
    """The regression that motivated the fix: EcoSIM_BioCON R3 is a CLEAN round.

    If this ever fails, the round record and the config really have drifted -- which is the finding
    the gate is supposed to surface, rather than the false one it was surfacing before.
    """
    cfg = ROOT / "use_cases/EcoSIM_BioCON/config/ecosim_biocon_config_r3.sh"
    if not cfg.is_file():                                   # pragma: no cover - case-specific
        pytest.skip("EcoSIM_BioCON R3 config not present")
    r = subprocess.run(["bash", "-c",
                        f'source "{cfg}" >/dev/null 2>&1; '
                        f'"{PY}" scripts/check_adapter_calibration_rounds.py'],
                       cwd=ROOT, capture_output=True, text=True)
    assert r.returncode == 0, r.stdout + r.stderr
