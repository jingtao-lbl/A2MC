"""The record-keeping wiring: the run ledger, its table and the offline state follow the work.

visibility: public

Covers every piece added together (account: memory/dev_logs_adapterkit/20261014a_*):

  * tools/record_run_status.py -- the table is rewritten on every save; `settle` resolves an
    open record (here the paths that need no model backend); a submission row covers its cases.
  * tools/submit_run.py -- refuses an incomplete submission and a duplicate record.
  * .claude/hooks/block-unregistered-sbatch.py -- a bare sbatch is denied; mentions, quoted
    patterns, heredoc bodies and the wrapper pass.
  * .claude/hooks/remind-arm-monitoring.py -- fires on the wrapper, not on text that names it.
  * .githooks/commit-msg -- a model-evolution record travels with its state decision.
  * tools/check_workflow_state_offline.py -- the stale-decision window starts at a TIME.
  * tools/workflow_state_offline.py -- a decision dated today carries `at`.
  * .claude/hooks/check-records-on-stop.py -- the state and table checks, and no loop.
  * tools/model_ensemble_status.py -- the on-end command's outcome is reported.

Trigger strings are built by concatenation, because the hooks inspect command TEXT and this
file's own source would otherwise be a submission to them.
"""
import importlib.machinery
import importlib.util
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

from tools import record_run_status as rrs  # noqa: E402

S = "sb" + "atch"
W = "submit" + "_run.py"


def _load(name, path):
    loader = importlib.machinery.SourceFileLoader(name, str(path))
    spec = importlib.util.spec_from_loader(name, loader)
    mod = importlib.util.module_from_spec(spec)
    loader.exec_module(mod)
    return mod


@pytest.fixture
def case_dir(tmp_path):
    d = tmp_path / "use_cases" / "Model_Case"
    (d / "memory").mkdir(parents=True)
    return d


# ---------------------------------------------------------------- the ledger and its table
def test_save_writes_the_table(case_dir):
    data = rrs.load(str(case_dir), 2)
    rrs.upsert(data, 2, "arm_a", cycle=0, status="submitted", job_id="123", purpose="p",
               differences="base EXCEPT x = 1", binary="b md5:0")
    rrs.save(str(case_dir), 2, data)
    table = (case_dir / "memory" / "SIMULATIONS_r02.md").read_text()
    assert "`arm_a`" in table and "| submitted |" in table
    assert table == rrs.render_table(json.loads((case_dir / "memory" / "run_records_r02.json")
                                                .read_text()), 2)


def test_submission_row_shows_its_counts():
    data = {"records": [{"round": 2, "case": "rerun_53", "cycle": 0, "status": "completed",
                         "n_cases": 53, "n_completed": 50, "n_failed": 3}]}
    assert "completed (50/53 ok)" in rrs.render_table(data, 2)


def test_settle_paths_that_need_no_backend():
    data = {"records": [
        {"round": 2, "case": "cancelled", "status": "submitted", "job_id": "1", "run_dir": "/x"},
        {"round": 2, "case": "running", "status": "submitted", "job_id": "2", "run_dir": "/x"},
        {"round": 2, "case": "nowhere", "status": "submitted", "job_id": "3"},
        {"round": 2, "case": "voided", "status": "void", "job_id": "4", "run_dir": "/x"},
    ]}
    rep = rrs.settle_records(data, "ecosim",
                             states={"1": "CANCELLED", "2": "ACTIVE", "3": "COMPLETED", "4": "FAILED"})
    by = {r["case"]: r for r in data["records"]}
    assert by["cancelled"]["status"] == "void" and "void_reason" in by["cancelled"]
    assert by["running"]["status"] == "running"
    assert by["nowhere"]["status"] == "submitted"                 # no location: left open, reported
    assert any("nowhere" in line and "OPEN" in line for line in rep)
    assert by["voided"]["status"] == "void"                        # a human verdict is not touched


def test_settle_leaves_a_model_without_a_backend_open():
    data = {"records": [{"round": 1, "case": "fates_arm", "status": "submitted", "job_id": "5",
                         "run_dir": "/x", "model": "no_such_model"}]}
    rep = rrs.settle_records(data, "ecosim", states={"5": "COMPLETED"})
    assert data["records"][0]["status"] == "submitted"
    assert any("no model verdict" in line for line in rep)


def test_is_terminal():
    assert rrs._is_terminal("COMPLETED") and rrs._is_terminal("CANCELLED+FAILED")
    assert not rrs._is_terminal("ACTIVE") and not rrs._is_terminal("")


def test_submission_row_coverage():
    row = {"run_root": "/r", "case_prefix": "Lusignan_case", "case_range": "0-256"}
    assert rrs._row_covers(row, "Lusignan_case17")
    assert not rrs._row_covers(row, "Lusignan_case300")
    assert not rrs._row_covers(row, "Lusignan_valid17")         # another family in the same root
    assert rrs._row_covers({"run_root": "/r"}, "anything")


# ---------------------------------------------------------------- submit_run.py
def _submit(case_dir, *extra):
    return subprocess.run([sys.executable, str(REPO / "tools" / W), "--case-dir", str(case_dir),
                           "--round", "2", "--cycle", "0", "--case", "arm_b", "--purpose", "p",
                           "--differences", "base EXCEPT x = 1", "--binary", "/nonexistent/exe"]
                          + list(extra), capture_output=True, text=True)


def test_submit_run_requires_an_existing_location(case_dir):
    r = _submit(case_dir, "--run-dir", str(case_dir / "absent"), "--dry-run", "--", "x.sh")
    assert r.returncode == 2 and "does not exist" in r.stderr


def test_submit_run_dry_run_writes_nothing(case_dir):
    r = _submit(case_dir, "--run-dir", str(case_dir), "--dry-run", "--", "--qos=debug", "x.sh")
    assert r.returncode == 0 and r.stdout == ""
    assert not (case_dir / "memory" / "run_records_r02.json").exists()


def test_submit_run_refuses_a_duplicate_record(case_dir):
    data = rrs.load(str(case_dir), 2)
    rrs.upsert(data, 2, "arm_b", cycle=0, status="completed", job_id="9")
    rrs.save(str(case_dir), 2, data)
    r = _submit(case_dir, "--run-dir", str(case_dir), "--dry-run", "--", "x.sh")
    assert r.returncode == 2 and "--resubmit" in r.stderr


# ---------------------------------------------------------------- the sbatch hook
HOOK = REPO / ".claude" / "hooks" / "block-unregistered-sbatch.py"
DENY = [f"{S} --parsable x.sh", f"cd /a && J=$({S} --parsable s.sh) && echo $J", f"timeout 60 {S} x.sh",
        f"FOO=1 BAR='a b' {S} x.sh", f"ls; {S} x.sh", f"nohup {S} x.sh &",
        f"python3 - <<'EOF'\nsubprocess.run([\"{S}\", \"x.sh\"])\nEOF", f"echo ok\n{S} y.sh",
        f"x=`{S} y.sh`", f"A2MC_UNTRACKED_JOB=short {S} x.sh", f'J="$({S} --parsable x.sh)"',
        f"cat > f <<'EOF'\nnotes\nEOF\n{S} x.sh"]
ALLOW = [f"git grep -n {S} -- tools", f"echo \"{S} x.sh\"", f"squeue -u me | grep {S}",
         f"python tools/{W} --case-dir d --round 2 -- {S}_args.sh",
         f"A2MC_UNTRACKED_JOB=\"output extraction, not a run\" {S} extract.sh", "#SBATCH --qos=debug",
         f"cat foo_{S}.log", f"grep -n -E '^#+ |{S}|submit' f.md", f"grep -E \"a|{S}|b\" f",
         f"git commit -m \"x\n{S} lines\"", f"git commit -F - <<'EOF'\nsubject\n\n{S} x.sh\nEOF",
         f"cat > doc.md <<EOF\n{S} --parsable x.sh\nEOF",
         f"{S} --test-only --array=0-99 submit_ensemble_array.sh",
         f"python3 - <<'EOF'\nsubprocess.run([\"{S}\", \"--test-only\", \"x.sh\"])\nEOF"]
DENY += [f"{S} --test-only x.sh && {S} x.sh"]          # a test, then a real submission


def _hook(path, payload):
    return subprocess.run([sys.executable, str(path)], input=json.dumps(payload),
                          capture_output=True, text=True).stdout


@pytest.mark.parametrize("cmd", DENY)
def test_bare_sbatch_is_denied(cmd):
    out = json.loads(_hook(HOOK, {"tool_name": "Bash", "tool_input": {"command": cmd}}))
    assert out["hookSpecificOutput"]["permissionDecision"] == "deny"
    assert W in out["hookSpecificOutput"]["permissionDecisionReason"]


@pytest.mark.parametrize("cmd", ALLOW)
def test_non_submissions_pass(cmd):
    assert _hook(HOOK, {"tool_name": "Bash", "tool_input": {"command": cmd}}).strip() == ""


@pytest.mark.parametrize("cmd,fires", [(f"python tools/{W} --case-dir d --round 2 -- x.sh", True),
                                       (f"{S} x.sh", True),
                                       (f"python3 - <<'EOF'\ns = 'tools/{W}'\nEOF", False),
                                       (f"grep -E '{S}|{W}' f", False)])
def test_monitoring_reminder(cmd, fires):
    out = _hook(REPO / ".claude" / "hooks" / "remind-arm-monitoring.py",
                {"tool_name": "Bash", "tool_input": {"command": cmd}, "tool_response": {"stdout": "ok"}})
    assert bool(out.strip()) == fires


# ---------------------------------------------------------------- commit-msg: record + state
@pytest.fixture
def cm():
    return _load("commit_msg_hook", REPO / ".githooks" / "commit-msg")


def _case_with_state(root, converged=False):
    mem = root / "use_cases" / "C" / "memory"
    (mem / "model_evolution").mkdir(parents=True)
    (mem / "workflow_state_offline_r02.json").write_text(json.dumps({"converged": converged}))
    return "use_cases/C/memory/workflow_state_offline_r02.json"


def test_record_without_state_is_blocked(cm, tmp_path):
    _case_with_state(tmp_path)
    rec = "use_cases/C/memory/model_evolution/20261014d_x.md"
    assert "offline state" in cm.state_with_findings("subject\n", {rec}, str(tmp_path))


def test_record_with_state_or_reason_passes(cm, tmp_path):
    state = _case_with_state(tmp_path)
    rec = "use_cases/C/memory/model_evolution/20261014d_x.md"
    assert cm.state_with_findings("subject\n", {rec, state}, str(tmp_path)) == ""
    body = "subject\n\nState-Unchanged: a typo in a cross-reference only\n"
    assert cm.state_with_findings(body, {rec}, str(tmp_path)) == ""
    assert "offline state" in cm.state_with_findings("s\n\nState-Unchanged: short\n", {rec},
                                                     str(tmp_path))


def test_commit_msg_runs_under_the_python_git_uses(tmp_path):
    """git runs the hook with the `python3` on PATH, which on some machines is 3.6; a keyword that
    interpreter lacks crashes every commit. Run it that way, in a real repository, both outcomes."""
    repo = tmp_path / "r"
    me = repo / "use_cases" / "C" / "memory"
    (me / "model_evolution").mkdir(parents=True)
    (me / "workflow_state_offline_r01.json").write_text("{}")
    (me / "model_evolution" / "20261014d_x.md").write_text("finding")
    subprocess.run(["git", "init", "-q", str(repo)], check=True)
    subprocess.run(["git", "-C", str(repo), "add", "use_cases/C/memory/model_evolution/20261014d_x.md"],
                   check=True)
    msg = tmp_path / "msg"
    hook = str(REPO / ".githooks" / "commit-msg")
    msg.write_text("subject\n")
    blocked = subprocess.run(["python3", hook, str(msg)], cwd=repo, capture_output=True, text=True)
    assert blocked.returncode == 1 and "offline state" in blocked.stderr, blocked.stderr
    msg.write_text("subject\n\nState-Unchanged: a cross-reference fix only\n")
    ok = subprocess.run(["python3", hook, str(msg)], cwd=repo, capture_output=True, text=True)
    assert ok.returncode == 0, ok.stderr


def test_record_rule_exemptions(cm, tmp_path):
    _case_with_state(tmp_path, converged=True)
    rec = "use_cases/C/memory/model_evolution/20261014d_x.md"
    assert cm.state_with_findings("s\n", {rec}, str(tmp_path)) == ""          # closed round
    readme = "use_cases/C/memory/model_evolution/README.md"
    assert cm.state_with_findings("s\n", {readme}, str(tmp_path)) == ""       # not a record
    assert cm.state_with_findings("s\n", {"use_cases/D/memory/model_evolution/a.md"},
                                  str(tmp_path)) == ""                        # no state at all


# ---------------------------------------------------------------- the state's decision time
def test_newest_decision_time():
    from tools.check_workflow_state_offline import newest_decision_time
    decs = [{"date": "2026-10-13"}, {"date": "2026-10-14", "at": "2026-10-14T16:10:53"},
            {"date": "2026-10-14"}]
    assert newest_decision_time(decs) == "2026-10-14T16:10:53"
    assert newest_decision_time([{"date": "2026-10-13"}]) == "2026-10-13T00:00:00"
    assert newest_decision_time([]) == ""


def test_stale_check_asks_git_for_a_time_not_a_bare_date(monkeypatch, tmp_path):
    """The bug: `git log --since 2026-10-14` means that date AT THE CURRENT CLOCK TIME, so one
    decision dated today hid every earlier commit of the same day. The window must be a time."""
    import tools.check_workflow_state_offline as cw
    case = tmp_path / "use_cases" / "C"
    (case / "memory").mkdir(parents=True)
    p = case / "memory" / "workflow_state_offline_r02.json"
    p.write_text("{}")
    seen = {}

    def fake_run(args, **kw):
        seen["since"] = args[args.index("--since") + 1]
        return subprocess.CompletedProcess(args, 0, stdout="a\n" * 20, stderr="")

    monkeypatch.setattr(cw.subprocess, "run", fake_run)
    warns = cw._check_decisions_current(str(p), {"decisions": [{"date": "2026-10-14"}]})
    assert seen["since"] == "2026-10-14 00:00:00"
    assert warns and warns[0].startswith("C: 20 commit(s) touching this case")


def test_add_decision_stamps_today_only(tmp_path):
    from datetime import datetime
    from tools.workflow_state_offline import WorkflowStateOffline
    (tmp_path / "memory").mkdir()
    st = WorkflowStateOffline.load(calibration_round=1, site_dir=str(tmp_path))
    st.add_decision("today's finding").add_decision("an old one", date="2020-01-01")
    today, old = st.data["decisions"]
    assert today["at"].startswith(datetime.now().strftime("%Y-%m-%d"))
    assert "at" not in old


# ---------------------------------------------------------------- the Stop hook
@pytest.fixture
def stop(tmp_path, monkeypatch):
    monkeypatch.setenv("CLAUDE_PROJECT_DIR", str(tmp_path))
    return _load("stop_hook", REPO / ".claude" / "hooks" / "check-records-on-stop.py")


def test_stop_flags_a_record_newer_than_the_newest_decision(stop, tmp_path):
    mem = tmp_path / "use_cases" / "C" / "memory"
    (mem / "model_evolution").mkdir(parents=True)
    (mem / "workflow_state_offline_r02.json").write_text(json.dumps(
        {"decisions": [{"date": "2020-01-01", "at": "2020-01-01T00:00:00"}]}))
    (mem / "model_evolution" / "20261014d_x.md").write_text("finding")
    assert any("20261014d_x.md" in p for p in stop.check_state({"C"}, None))
    st = json.loads((mem / "workflow_state_offline_r02.json").read_text())
    st["decisions"].append({"date": "2099-01-01", "at": "2099-01-01T00:00:00"})
    (mem / "workflow_state_offline_r02.json").write_text(json.dumps(st))
    assert stop.check_state({"C"}, None) == []


def test_stop_flags_a_hand_edited_table(stop, tmp_path):
    case = tmp_path / "use_cases" / "C"
    (case / "memory").mkdir(parents=True)
    data = rrs.load(str(case), 1)
    rrs.upsert(data, 1, "arm", cycle=0, status="completed", job_id="1")
    rrs.save(str(case), 1, data)
    assert stop.check_runs_and_tables({"C"}) == []
    t = case / "memory" / "SIMULATIONS_r01.md"
    t.write_text(t.read_text().replace("| completed |", "| failed |"))
    assert any("no longer matches" in p for p in stop.check_runs_and_tables({"C"}))


def test_stop_never_blocks_twice(tmp_path):
    out = _hook(REPO / ".claude" / "hooks" / "check-records-on-stop.py",
                {"stop_hook_active": True, "transcript_path": str(tmp_path / "none.jsonl")})
    assert out.strip() == ""


# ---------------------------------------------------------------- watcher on-end hooks
def test_on_end_outcomes(capsys):
    from tools.model_ensemble_status import run_on_end
    assert run_on_end("echo settled", 10) == "OK"
    assert run_on_end("exit 3", 10) == "FAILED"
    assert run_on_end("sleep 3", 1) == "TIMEOUT"
    assert "[ON_END] settled" in capsys.readouterr().out


def test_watch_slurm_array_parses():
    r = subprocess.run(["bash", "-n", str(REPO / "tools" / "watch_slurm_array.sh")],
                       capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
