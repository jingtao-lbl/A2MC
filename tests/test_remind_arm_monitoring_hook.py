"""remind-arm-monitoring.py: fires on a real submission, stays quiet on text that only mentions one.

visibility: public

The hook runs under the system `python3`, so the tests do too. The first test is the positive
control: a real `sbatch` must fire, or the silences asserted below mean nothing.
"""
import json
import shutil
import subprocess
from pathlib import Path

HOOK = Path(__file__).resolve().parent.parent / ".claude" / "hooks" / "remind-arm-monitoring.py"
PY = shutil.which("python3") or "python3"


def run(cmd, stdout="Submitted batch job 1"):
    payload = {"tool_name": "Bash", "tool_input": {"command": cmd}, "tool_response": {"stdout": stdout}}
    out = subprocess.run([PY, str(HOOK)], input=json.dumps(payload), capture_output=True, text=True)
    assert out.returncode == 0
    return json.loads(out.stdout)["hookSpecificOutput"]["additionalContext"] if out.stdout.strip() else ""


def test_real_submission_fires():
    assert "HPC JOBS SUBMITTED" in run("sbatch run.sh")


def test_grep_for_sbatch_directives_is_silent():
    assert run("grep -m3 -E '^#' submit.sh | grep -v SBATCH", stdout="# a comment") == ""


def test_untracked_ensemble_adds_the_run_tracking_paragraph():
    msg = run('A2MC_UNTRACKED_JOB="full Phase-0 ensemble; its record is run_tracking/" sbatch arr.sh')
    assert "UNTRACKED SUBMISSION" in msg


def test_ledger_routed_submission_has_no_run_tracking_paragraph():
    msg = run("python3 tools/submit_run.py --run-dir d -- run.sh")
    assert msg and "UNTRACKED SUBMISSION" not in msg
