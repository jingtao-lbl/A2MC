"""The template-index hooks: list a case's templates for a new phase script, and flag a stale index.

visibility: public

Both hooks run under the system `python3`, which on the development machine is 3.6, so the tests run
them under whatever `python3` is on PATH rather than this interpreter. Each builds a throwaway git
clone holding the hook, the index module and one case. The first test is the positive control: a new
template missing from the index must be reported, or the silence asserted below means nothing.
"""
import json
import shutil
import subprocess
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
PY = shutil.which("python3") or "python3"


def clone(tmp, templates=("plot_a.py",), indexed=True):
    subprocess.run(["git", "init", "-q", str(tmp)], check=True)
    (tmp / ".claude" / "hooks").mkdir(parents=True)
    for f in ("remind-template-index.py", "remind-governing-checks.py"):
        shutil.copy(REPO / ".claude" / "hooks" / f, tmp / ".claude" / "hooks" / f)
    (tmp / "tools").symlink_to(REPO / "tools")      # the governing-checks hook imports half of tools/
    (tmp / "docs").symlink_to(REPO / "docs")        # ...and reads the harness graph data
    scripts = tmp / "use_cases" / "M_C" / "scripts"
    scripts.mkdir(parents=True)
    (scripts / "README.md").write_text("# scripts\n")
    for t in templates:
        (scripts / t).write_text('"""TEMPLATE: draw %s."""\n' % t)
    if indexed:
        subprocess.run([PY, "-c", "import sys; sys.path.insert(0, %r); import case_script_index as I; "
                        "I.write(I.Path(%r), I.Path(%r))" % (str(REPO / "tools"), str(tmp / "use_cases" / "M_C"),
                                                            str(tmp))], check=True, capture_output=True)
    return tmp


def run(tmp, hook, payload):
    out = subprocess.run([PY, str(tmp / ".claude" / "hooks" / hook)], input=json.dumps(payload),
                         capture_output=True, text=True, env={"CLAUDE_PROJECT_DIR": str(tmp), "PATH": "/usr/bin:/bin"})
    assert out.returncode == 0
    return json.loads(out.stdout)["hookSpecificOutput"]["additionalContext"] if out.stdout.strip() else ""


def test_new_template_missing_from_index_is_reported(tmp_path):
    t = clone(tmp_path)
    (t / "use_cases/M_C/scripts/plot_b.py").write_text('"""Draw b."""\n')
    msg = run(t, "remind-template-index.py",
              {"tool_name": "Bash", "tool_input": {"command": "cp x use_cases/M_C/scripts/plot_b.py"}})
    assert "plot_b.py" in msg and "--write" in msg            # fails if a stale index passes


def test_reading_a_template_is_silent(tmp_path):
    t = clone(tmp_path)
    assert run(t, "remind-template-index.py",
               {"tool_name": "Bash", "tool_input": {"command": "cp use_cases/M_C/scripts/plot_a.py elsewhere/"}}) == ""


def test_new_phase_script_lists_the_templates(tmp_path):
    t = clone(tmp_path, templates=("plot_a.py", "score_b.py"))
    path = t / "use_cases/M_C/memory/phase_results/20261020a_phase2_x/plot_new.py"
    msg = run(t, "remind-governing-checks.py",
              {"session_id": "t", "tool_name": "Write", "tool_input": {"file_path": str(path)}})
    assert "NEW PHASE SCRIPT" in msg and "plot_a.py" in msg and "score_b.py" in msg
    assert "Template:" in msg


def test_existing_phase_script_gets_no_template_list(tmp_path):
    t = clone(tmp_path)
    path = t / "use_cases/M_C/memory/phase_results/20261020a_phase2_x/plot_old.py"
    path.parent.mkdir(parents=True)
    path.write_text("x = 1\n")
    msg = run(t, "remind-governing-checks.py",
              {"session_id": "t", "tool_name": "Edit", "tool_input": {"file_path": str(path)}})
    assert "NEW PHASE SCRIPT" not in msg


def test_new_run_file_missing_from_case_template_index_is_reported(tmp_path):
    t = clone(tmp_path)
    ct = t / "use_cases/M_C/case_template"
    ct.mkdir()
    (ct / "README.md").write_text("# run files\n")
    (ct / "submit.sh").write_text("#!/bin/bash\n# Runner.\n")
    subprocess.run([PY, "-c", "import sys; sys.path.insert(0, %r); import case_script_index as I; "
                    "I.write(I.Path(%r), I.Path(%r), ['case_template'])"
                    % (str(REPO / "tools"), str(t / "use_cases" / "M_C"), str(t))], check=True)
    (ct / "run.nml").write_text("&x\n/\n")
    msg = run(t, "remind-template-index.py",
              {"tool_name": "Bash", "tool_input": {"command": "cp a use_cases/M_C/case_template/run.nml"}})
    assert "run.nml" in msg and "--tier case_template" in msg
