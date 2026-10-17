""".claude/hooks/require-run-skill-before-submit.py: the run skill, the template run files and an archived copy come before a submission.

visibility: public

Each test builds a throwaway case tree and transcript and runs the hook under the system python3, as
the harness does. The denials come first: if a submission with nothing done passes, every pass below
is vacuous.
"""
import json
import os
import shutil
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
HOOK = ROOT / ".claude" / "hooks" / "require-run-skill-before-submit.py"
CASE, STEM = "EcoSIM_Test", "20261016z_phase5_testing_r01_c01_t"


def tree(tmp):
    c = tmp / "use_cases" / CASE
    (c / "case_template").mkdir(parents=True)
    (c / "case_template" / "README.md").write_text("index")
    (c / "memory" / "phase_results" / STEM / "submit_scripts").mkdir(parents=True)
    run = tmp / "run" / "case1"
    run.mkdir(parents=True)
    (run / "submit.sh").write_text("#!/bin/bash\nsrun x\n")
    (run / "runfile.nml").write_text("&ecosim\n/\n")
    return c, run


def transcript(tmp, events):
    lines = []
    for ev in events:
        if ev == "compact":
            lines.append({"type": "system", "subtype": "compact_boundary"})
        elif ev == "skill":
            lines.append({"type": "assistant", "message": {"content": [
                {"type": "tool_use", "id": "s1", "name": "Skill", "input": {"skill": "ecosim-run-workflow"}}]}})
        elif ev == "readme":
            lines.append({"type": "assistant", "message": {"content": [
                {"type": "tool_use", "id": "r1", "name": "Read",
                 "input": {"file_path": str(tmp / "use_cases" / CASE / "case_template" / "README.md")}}]}})
    p = tmp / "t.jsonl"
    p.write_text("\n".join(json.dumps(l) for l in lines) + "\n")
    return str(p)


def run_hook(tmp, cmd, tpath=None):
    payload = {"tool_name": "Bash", "tool_input": {"command": cmd}, "tool_use_id": "now"}
    if tpath:
        payload["transcript_path"] = tpath
    r = subprocess.run(["python3", str(HOOK)], input=json.dumps(payload), stdout=subprocess.PIPE,
                       stderr=subprocess.PIPE, universal_newlines=True, timeout=60,
                       env=dict(os.environ, CLAUDE_PROJECT_DIR=str(tmp)))
    assert r.returncode == 0, r.stderr
    return json.loads(r.stdout)["hookSpecificOutput"]["permissionDecisionReason"] if r.stdout.strip() else ""


def submit_cmd(run):
    return ("python tools/submit_run.py --case-dir use_cases/%s --round 1 --cycle 1 --case c1 --stem %s "
            "--purpose p --differences d --binary b --run-dir %s -- %s/submit.sh" % (CASE, STEM, run, run))


def archive(c, run):
    for f in ("submit.sh", "runfile.nml"):
        shutil.copy(run / f, c / "memory" / "phase_results" / STEM / "submit_scripts" / ("c1." + f))


def test_nothing_done_is_denied_on_all_three(tmp_path):
    c, run = tree(tmp_path)
    why = run_hook(tmp_path, submit_cmd(run), transcript(tmp_path, []))
    assert "ecosim-run-workflow" in why and "case_template/README.md" in why and "archive" in why


def test_skill_and_readme_before_the_compaction_do_not_count(tmp_path):
    c, run = tree(tmp_path)
    archive(c, run)
    why = run_hook(tmp_path, submit_cmd(run), transcript(tmp_path, ["skill", "readme", "compact"]))
    assert "1." in why and "2." in why and "3." not in why


def test_a_changed_archive_copy_is_denied(tmp_path):
    c, run = tree(tmp_path)
    archive(c, run)
    (c / "memory" / "phase_results" / STEM / "submit_scripts" / "c1.runfile.nml").write_text("&ecosim\n x=1\n/\n")
    why = run_hook(tmp_path, submit_cmd(run), transcript(tmp_path, ["compact", "skill", "readme"]))
    assert "runfile.nml" in why and "1." not in why


def test_everything_done_passes(tmp_path):
    c, run = tree(tmp_path)
    archive(c, run)
    assert run_hook(tmp_path, submit_cmd(run), transcript(tmp_path, ["compact", "skill", "readme"])) == ""


def test_variable_paths_in_the_command_are_resolved(tmp_path):
    c, run = tree(tmp_path)
    archive(c, run)
    cmd = "R=%s && " % run + submit_cmd("$R").replace("--run-dir $R", "--run-dir $R")
    assert run_hook(tmp_path, cmd, transcript(tmp_path, ["compact", "skill", "readme"])) == ""


def test_override_and_unrelated_commands_pass(tmp_path):
    c, run = tree(tmp_path)
    assert run_hook(tmp_path, 'A2MC_RUN_GATE_OVERRIDE="no run skill for this model yet" ' + submit_cmd(run),
                    transcript(tmp_path, [])) == ""
    assert run_hook(tmp_path, "git grep submit_run", transcript(tmp_path, [])) == ""


def test_no_transcript_still_checks_the_archive(tmp_path):
    c, run = tree(tmp_path)
    why = run_hook(tmp_path, submit_cmd(run))
    assert "archive" in why and "ecosim-run-workflow" not in why


def test_full_ensemble_launcher_must_be_in_run_tracking(tmp_path):
    c, run = tree(tmp_path)
    p0 = c / "memory" / "phase_results" / "20261016a_phase0_design_r02_x"
    (p0 / "run_tracking" / "submit_scripts").mkdir(parents=True)
    launcher = c / "case_template" / "submit_ensemble_array.sh"
    launcher.write_text("#!/bin/bash\n#SBATCH --array=0-9\n")
    cmd = 'A2MC_UNTRACKED_JOB="full Phase-0 ensemble; its record is run_tracking" sbatch use_cases/%s/case_template/submit_ensemble_array.sh' % CASE
    events = ["compact", "skill", "readme"]
    assert "run_tracking/submit_scripts" in run_hook(tmp_path, cmd, transcript(tmp_path, events))
    shutil.copy(launcher, p0 / "run_tracking" / "submit_scripts" / "submit_ensemble_array.sh")
    assert run_hook(tmp_path, cmd, transcript(tmp_path, events)) == ""
