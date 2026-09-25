"""`tools/model_preflight.py` must tell DRIFT from NOT ONBOARDED, because they route differently.

Until 2026-09-23 every miss exited 2 with "Run the `onboard-model` skill". The miss is only
reached after the model has imported and registered, so it was never "unsupported": it was an
onboarded model at an unregistered commit (drift), or an adapter whose onboarding stopped before
its milestone. The first case sent every EcoSIM user off the one registered commit to re-onboard
an onboarded model (audit 20260923b, finding F35).

Author: Jing Tao with Claude.
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
TOOL = REPO / "tools" / "model_preflight.py"


def run(*args):
    r = subprocess.run([sys.executable, str(TOOL), *args], capture_output=True, text=True,
                       timeout=120, cwd=str(REPO))
    return r.returncode, r.stdout + r.stderr


def _adapters_with_milestones():
    ms = json.loads((REPO / "rag" / "milestones.json").read_text()).get("milestones", {})
    return {v.get("adapter") for v in ms.values() if isinstance(v, dict)} - {None}


def test_an_unknown_model_is_not_onboarded():
    rc, out = run("--model", "no_such_model_xyz")
    assert rc == 2, out


def test_a_missing_checkout_cannot_be_verified_rather_than_called_drift():
    """A path that does not exist must not be reported as drift: nothing was read."""
    model = sorted(_adapters_with_milestones())[0]
    rc, out = run("--model", model, "--checkout", "/nonexistent/checkout/path")
    assert rc == 1, out
    assert "CANNOT VERIFY" in out, out
    assert "DRIFT" not in out, out


def test_an_adapter_with_no_milestone_says_so_even_without_a_version():
    """ATS registers but has no milestone on this branch; that is known from the registry alone."""
    if "ats" in _adapters_with_milestones():
        pytest.skip("ATS now has a milestone; pick another milestone-less adapter to test this")
    rc, out = run("--model", "ats", "--checkout", "/nonexistent/checkout/path")
    assert rc == 2, out
    assert "NO MILESTONE" in out, out
    assert "check_stage_ready.py --model ats" in out, "must name the resume command: " + out


def test_drift_is_its_own_verdict_and_does_not_send_the_user_to_onboard_model(tmp_path):
    """A real git checkout at a commit no milestone registers is DRIFT (exit 3), not 'unsupported'.

    EcoSIM's detector reads `git rev-parse HEAD`, so a throwaway one-commit repo is a genuinely
    unregistered EcoSIM commit -- no monkeypatching of the code under test.
    """
    if "ecosim" not in _adapters_with_milestones():
        pytest.skip("no EcoSIM milestone registered")
    co = tmp_path / "EcoSIM"
    co.mkdir()
    env = {"GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@t", "GIT_COMMITTER_NAME": "t",
           "GIT_COMMITTER_EMAIL": "t@t", "PATH": "/usr/bin:/bin"}
    for cmd in (["git", "init", "-q"], ["git", "commit", "-q", "--allow-empty", "-m", "x"]):
        subprocess.run(cmd, cwd=str(co), check=True, env=env, capture_output=True)
    rc, out = run("--model", "ecosim", "--checkout", str(co))
    assert rc == 3, out
    assert "DRIFT" in out and "onboarded" in out, out
    assert "Run the `onboard-model` skill to onboard it" not in out, out
