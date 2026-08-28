"""C11 (must-invoked skills) and C12 (cumulative reasoning chain).

Every test asserts a way the check must FIRE, or a way it must NOT. A check that cannot fail is not
a check ([[feedback_a_check_that_cannot_fail]]).

Author: Jing Tao with Claude
"""
import json
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
CHECK = REPO / "tools" / "check_calibration_log_conformance.py"

HEAD = """# T

**Site:** S
**Phase:** 3 - Diagnosis
**Round:** 3
**Date:** 2026-08-25

## Iteration Context
```json
{}
```
## Failing Targets
## Likely Causes
## Root Causes (Ranked)
## Key Insights
## AI Reasoning and Deep Analysis
## Parameter Recommendations
## Cross-PFT Conflicts
## Hypotheses Tested
## Conceptual Model
"""

SKILLS = "\n## Skills and memory invoked\n\n- **Skills:** {}\n"


def write(tmp_path, name, body, state=None, figs=()):
    logs = tmp_path / "memory" / "logs"; logs.mkdir(parents=True, exist_ok=True)
    p = logs / name
    p.write_text(body)
    if state is not None:
        (tmp_path / "memory" / f"workflow_state_offline_r03.json").write_text(json.dumps(state))
    if figs:
        d = tmp_path / "memory" / "phase_results" / p.stem
        d.mkdir(parents=True, exist_ok=True)
        for f in figs:
            (d / f).write_bytes(b"\x89PNG")
    return p


def run(p):
    r = subprocess.run([sys.executable, str(CHECK), str(p)], capture_output=True, text=True)
    return r.returncode, r.stdout + r.stderr


NAME = "20260825a_phase3_diagnosis_r03_c01_iter01_x.md"


def test_C11_fires_when_calibration_log_is_not_named(tmp_path):
    p = write(tmp_path, NAME, HEAD + SKILLS.format("`phase3-diagnosis`"))
    rc, out = run(p)
    assert "C11" in out and "calibration-log" in out and rc == 2


def test_C11_fires_when_the_phase_skill_is_not_named(tmp_path):
    p = write(tmp_path, NAME, HEAD + SKILLS.format("`calibration-log`"))
    rc, out = run(p)
    assert "C11" in out and "phase3-diagnosis" in out


def test_C11_passes_when_both_are_named_and_there_is_no_figure(tmp_path):
    p = write(tmp_path, NAME, HEAD + SKILLS.format("`calibration-log`, `phase3-diagnosis`"))
    _rc, out = run(p)
    assert "C11" not in out


def test_C11_requires_plotting_when_the_log_EMBEDS_a_figure(tmp_path):
    body = HEAD + "\n![](../phase_results/x/f.png)\n" + SKILLS.format(
        "`calibration-log`, `phase3-diagnosis`")
    p = write(tmp_path, NAME, body)
    _rc, out = run(p)
    assert "C11" in out and "plotting" in out


def test_C11_requires_plotting_when_the_FOLDER_holds_a_figure(tmp_path):
    """A figure in the folder but unembedded is still a plotting product."""
    p = write(tmp_path, NAME, HEAD + SKILLS.format("`calibration-log`, `phase3-diagnosis`"),
              figs=("f.png",))
    _rc, out = run(p)
    assert "C11" in out and "plotting" in out


def test_C11_reads_a_WRAPPED_skills_bullet(tmp_path):
    """Capturing only the first line is silent under-detection -- the bug already found in
    check_skill_claims.py, where a skill on line two was missed."""
    body = HEAD + "\n## Skills and memory invoked\n\n- **Skills:** `calibration-log`,\n  `phase3-diagnosis`\n"
    p = write(tmp_path, NAME, body)
    _rc, out = run(p)
    assert "C11" not in out


def test_C11_is_non_retroactive(tmp_path):
    old = "20260801a_phase3_diagnosis_r03_c01_iter01_x.md"
    p = write(tmp_path, old, HEAD.replace("2026-08-25", "2026-08-01") + SKILLS.format("`none`"))
    _rc, out = run(p)
    assert "C11" not in out


def test_C12_fires_when_a_chain_decision_is_absent_from_the_state(tmp_path):
    body = (HEAD + SKILLS.format("`calibration-log`, `phase3-diagnosis`")
            + "\n## Reasoning chain — round 03\n\n- 2026-08-22 — A FINDING THE STATE NO LONGER HAS\n")
    p = write(tmp_path, NAME, body, state={"decisions": [{"decision": "something else"}]})
    rc, out = run(p)
    assert "C12" in out and rc == 2


def test_C12_passes_when_every_chain_decision_is_in_the_state(tmp_path):
    body = (HEAD + SKILLS.format("`calibration-log`, `phase3-diagnosis`")
            + "\n## Reasoning chain — round 03\n\n- 2026-08-22 — A REAL FINDING\n")
    p = write(tmp_path, NAME, body, state={"decisions": [{"decision": "A REAL FINDING"}]})
    _rc, out = run(p)
    assert "C12" not in out


def test_C12_is_silent_when_the_state_file_is_MISSING(tmp_path):
    """Absence of the input is not evidence of a lost decision."""
    body = (HEAD + SKILLS.format("`calibration-log`, `phase3-diagnosis`")
            + "\n## Reasoning chain — round 03\n\n- 2026-08-22 — ANYTHING\n")
    p = write(tmp_path, NAME, body)
    _rc, out = run(p)
    assert "C12" not in out


def test_C12_ignores_stem_keyed_evidence_entries(tmp_path):
    """Only DECISION entries live in state['decisions']; stem-keyed ones are evidence."""
    body = (HEAD + SKILLS.format("`calibration-log`, `phase3-diagnosis`")
            + "\n## Reasoning chain — round 03\n\n- `20260822a_phase1_exploration_r03_x` — text\n")
    p = write(tmp_path, NAME, body, state={"decisions": []})
    _rc, out = run(p)
    assert "C12" not in out
