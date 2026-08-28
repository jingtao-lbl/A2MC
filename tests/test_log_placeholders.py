"""Tests for tools/check_log_placeholders.py.

Every test asserts a way the check must FAIL, or a way it must NOT fire. A check that cannot fail
is not a check ([[feedback_a_check_that_cannot_fail]]), and this one was written after a rendered
"#N/A" passed the entire pre-commit gate.

Author: Jing Tao with Claude
"""
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
CHECK = REPO / "tools" / "check_log_placeholders.py"


def run(tmp_path, name, body):
    p = tmp_path / name
    p.write_text(body)
    r = subprocess.run([sys.executable, str(CHECK), str(p)], capture_output=True, text=True)
    return r.returncode, r.stdout + r.stderr


def test_it_fails_on_the_na_bullet_that_started_this(tmp_path):
    rc, out = run(tmp_path, "20260901a_phase3_diagnosis_x.md",
                  "## Comparative Case Analysis\n\n- **Best case (targets):** #N/A\n")
    assert rc == 1
    assert "N/A" in out


def test_it_fails_on_the_unknown_parameter_stub(tmp_path):
    rc, _ = run(tmp_path, "20260901b_phase4_hypothesis_x.md",
                "## Parameters to Modify\n\n### Unknown\n- **Current:** N/A\n- **Proposed:** N/A\n")
    assert rc == 1


def test_it_fails_on_the_empty_reasoning_stub(tmp_path):
    rc, _ = run(tmp_path, "20260901c_phase3_diagnosis_x.md",
                "## AI Reasoning and Deep Analysis\n\n*No AI reasoning recorded*\n")
    assert rc == 1


def test_it_fails_on_none_and_tbd_bullets(tmp_path):
    for val in ("None", "TBD", "{}", "[]"):
        rc, _ = run(tmp_path, f"20260901d_phase3_diagnosis_{val.strip('{}[]') or 'x'}.md",
                    f"## Section\n\n- **Something:** {val}\n")
        assert rc == 1, val


def test_it_fails_when_comparative_analysis_has_no_recognised_key(tmp_path):
    rc, _ = run(tmp_path, "20260901e_phase3_diagnosis_x.md",
                "## Comparative Case Analysis\n\n_(comparative_analysis was supplied but carried "
                "no recognised key — expected `selected_base_cases`.)_\n")
    assert rc == 1


def test_it_does_NOT_fire_inside_the_sections_not_provided_block(tmp_path):
    """PhaseLogger's own trailing list of empty sections is the honest, deliberate output."""
    rc, _ = run(tmp_path, "20260901f_phase3_diagnosis_x.md",
                "## Root Causes\n\n- **Cause:** something real\n\n"
                "## Sections not provided\n\n- Cross-PFT Conflicts — _(not provided)_\n"
                "- **Anything:** N/A\n")
    assert rc == 0


def test_a_stub_ABOVE_that_block_is_still_caught(tmp_path):
    """Slicing at 'Sections not provided' must not blind the check to everything before it."""
    rc, _ = run(tmp_path, "20260901g_phase3_diagnosis_x.md",
                "## Comparative Case Analysis\n\n- **Best case (targets):** #N/A\n\n"
                "## Sections not provided\n\n- Cross-PFT Conflicts — _(not provided)_\n")
    assert rc == 1


def test_prose_that_MENTIONS_a_placeholder_is_not_flagged(tmp_path):
    """A log explaining this very defect quotes the stub; quoting is not rendering."""
    rc, _ = run(tmp_path, "20260901h_phase3_diagnosis_x.md",
                "## Notes\n\nThe section rendered `- **Best case (targets):** #N/A` because the "
                "renderer read the wrong key.\n")
    assert rc == 0


def test_logs_before_the_effective_date_are_exempt_and_COUNTED(tmp_path):
    rc, out = run(tmp_path, "20260716d_phase4_hypothesis_x.md",
                  "## Parameters to Modify\n\n### Unknown\n- **Current:** N/A\n")
    assert rc == 0
    assert "exempt" in out and "1 log(s) predate" in out


def test_a_clean_log_passes(tmp_path):
    rc, _ = run(tmp_path, "20260901i_phase3_diagnosis_x.md",
                "## Comparative Case Analysis\n\n- **Case #7329** — satisfies NPP\n  - because\n")
    assert rc == 0


def test_a_stub_inside_a_FENCED_BLOCK_is_not_flagged(tmp_path):
    """A log documenting this defect necessarily reproduces it; a fence is quoted, not rendered.

    Found by the check firing on the dev log that documents it, which is the most likely place
    for a verbatim stub to appear.
    """
    rc, _ = run(tmp_path, "20260901j_phase3_diagnosis_x.md",
                "## Notes\n\nIt rendered:\n\n```markdown\n### Unknown\n- **Current:** N/A\n"
                "- **Proposed:** N/A\n```\n\nand that is the bug.\n")
    assert rc == 0


def test_a_real_stub_AFTER_a_fence_is_still_flagged_at_the_right_line(tmp_path):
    """Blanking a fence must preserve line numbers, or the report points at the wrong place."""
    rc, out = run(tmp_path, "20260901k_phase3_diagnosis_x.md",
                  "## Notes\n\n```\n### Unknown\n- **Current:** N/A\n```\n\n"
                  "## Comparative Case Analysis\n\n- **Best case (targets):** #N/A\n")
    assert rc == 1
    assert "line 9" in out, out


def test_a_tilde_fence_counts_too(tmp_path):
    rc, _ = run(tmp_path, "20260901l_phase3_diagnosis_x.md",
                "## Notes\n\n~~~\n- **Current:** N/A\n~~~\n")
    assert rc == 0
