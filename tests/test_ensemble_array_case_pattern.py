"""The ensemble array script must resolve A2MC_CASE_NAME_PATTERN, and leave no stray brace.

WHY THIS FILE EXISTS. The case-dir line in `submit_ensemble_array.sh` hardcoded the round's own
pattern on purpose, because a `${PATTERN/{N}/...}` substitution leaves a trailing `}` under bash's
brace parsing and once failed every task of a round. The hardcoding then silently broke every
EXPERIMENT, whose cases use a different pattern: the validator's submit dry-check reported
`no case dir <default>0` against a run root holding the experiment's own cases, and two cycles
worked around it with `--no-submit-check`.

Both failure modes are asserted here, because the fix reproduced the ORIGINAL bug on its first
attempt: writing `${A2MC_CASE_NAME_PATTERN:-Lusignan_case{N}}` ends the parameter expansion at the
`{N}`'s closing brace and yields `Lusignan_exp_c10_1}`. The script's own placeholder assertion
caught it before any job ran, and this test keeps both halves nailed down.

Author: Jing Tao with Claude on Perlmutter
"""
from __future__ import annotations

import hashlib
import os
import subprocess
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
SCRIPT = REPO / "use_cases" / "EcoSIM_Lusignan" / "case_template" / "submit_ensemble_array.sh"


def _run(tmp_path, pattern, task_id, case_dirs):
    """Run the array script far enough to print its resolved case dir, then let it fail there.

    The script hard-exits 2 with `ERROR: no case dir <path>` when the directory is missing, which is
    exactly the line under test: it names the path the script RESOLVED. Creating the directory
    instead would run the model, so the error path is the assertion surface.
    """
    root = tmp_path / "runs"
    root.mkdir(exist_ok=True)
    for d in case_dirs:
        (root / d).mkdir(exist_ok=True)
    # The script verifies the binary's sha256 BEFORE resolving the case dir, so a fake path aborts
    # ahead of the line under test -- which made one of these assertions unable to fail on the
    # first run. Give it a real stub file and its real hash.
    exe = tmp_path / "ecosim.f90.x"
    exe.write_text("#!/bin/bash\nexit 0\n")
    exe.chmod(0o755)
    env = dict(os.environ)
    env.update(A2MC_OUTPUT_DIR=str(root),
               A2MC_ECOSIM_BINARY=str(exe),
               A2MC_ECOSIM_BINARY_SHA256=hashlib.sha256(exe.read_bytes()).hexdigest(),
               SLURM_ARRAY_TASK_ID=str(task_id))
    if pattern is None:
        env.pop("A2MC_CASE_NAME_PATTERN", None)
    else:
        env["A2MC_CASE_NAME_PATTERN"] = pattern
    r = subprocess.run(["bash", str(SCRIPT)], env=env, cwd=str(root),
                       capture_output=True, text=True, timeout=60)
    return r.stdout + r.stderr


@pytest.mark.skipif(not SCRIPT.exists(), reason="case template not present on this branch")
def test_resolves_a_non_default_pattern(tmp_path):
    """The experiment pattern must reach the case dir. This is the bug that cost two cycles."""
    out = _run(tmp_path, "Lusignan_exp_c10_{N}", 3, [])
    assert "Lusignan_exp_c10_3" in out, out
    assert "Lusignan_case3" not in out, out


@pytest.mark.skipif(not SCRIPT.exists(), reason="case template not present on this branch")
def test_leaves_no_stray_brace(tmp_path):
    """The resolved name must carry no `{` or `}`. The first fix attempt produced `..._3}`."""
    out = _run(tmp_path, "Lusignan_exp_c10_{N}", 3, [])
    assert "Lusignan_exp_c10_3}" not in out, out
    assert "still holds a placeholder" not in out, out


@pytest.mark.skipif(not SCRIPT.exists(), reason="case template not present on this branch")
def test_placeholder_assertion_fires_on_an_unsubstituted_pattern(tmp_path):
    """A pattern whose placeholder is spelled differently must ABORT, not run the wrong case.

    A check that cannot fail is not a check, so this asserts the guard's positive case: `{CASE}` is
    not the `{N}` the substitution knows, so the name still holds braces and the script must refuse.
    """
    out = _run(tmp_path, "Lusignan_exp_c10_{CASE}", 3, [])
    assert "still holds a placeholder" in out, out


@pytest.mark.skipif(not SCRIPT.exists(), reason="case template not present on this branch")
def test_falls_back_to_the_round_pattern_when_unset(tmp_path):
    """With no pattern in the environment the script keeps the round's own default."""
    out = _run(tmp_path, None, 7, [])
    assert "Lusignan_case7" in out, out
    assert "still holds a placeholder" not in out, out
