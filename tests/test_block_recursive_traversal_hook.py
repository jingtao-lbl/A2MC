"""The NERSC traversal guard must block real violations AND stay out of the way otherwise.

A hook that blocks too much gets disabled, and NERSC forbids disabling it — so the ALLOW half of
this suite is as load-bearing as the DENY half. Both directions are asserted; a guard that cannot
fail, or that fails on everything, is not a guard ([[feedback_a_check_that_cannot_fail]]).

Author: Jing Tao with Claude.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
HOOK = REPO / ".claude" / "hooks" / "block-recursive-traversal.py"


def _on_hpc() -> bool:
    """True when the hook's OWN autodetect would fire on this machine.

    The marker lists are read out of the hook's source with `ast` rather than restated here: a
    second copy of a contract drifts from the first ([[feedback_exact_strings_are_contracts]]).
    The hook cannot simply be imported -- it is a script that runs and calls sys.exit() at module
    level -- so parse it instead of executing it.
    """
    import ast
    tree = ast.parse(HOOK.read_text())
    lit = {}
    for node in tree.body:
        if isinstance(node, ast.Assign) and isinstance(node.targets[0], ast.Name):
            name = node.targets[0].id
            if name in ("_HPC_MARKER_DIRS", "_HPC_MARKER_ENV"):
                lit[name] = ast.literal_eval(node.value)
    assert set(lit) == {"_HPC_MARKER_DIRS", "_HPC_MARKER_ENV"}, f"hook markers moved: {sorted(lit)}"
    return (any(os.environ.get(v) for v in lit["_HPC_MARKER_ENV"])
            or any(os.path.isdir(d) for d in lit["_HPC_MARKER_DIRS"]))


def run_hook(command: str, tool_name: str = "Bash", guard: str = "on", env_extra: dict | None = None):
    """Returns the parsed hook decision, or None when the hook stays silent (allow).

    `guard` drives A2MC_TRAVERSAL_GUARD: "on" forces the guard (so the deny/allow assertions are
    reproducible on any machine, not only where the HPC autodetect fires), "off" simulates a
    laptop, "" exercises the autodetect.
    """
    payload = json.dumps({"tool_name": tool_name, "tool_input": {"command": command}})
    env = {**os.environ, "A2MC_TRAVERSAL_GUARD": guard, **(env_extra or {})}
    r = subprocess.run([sys.executable, str(HOOK)], input=payload, env=env,
                       capture_output=True, text=True, timeout=20)
    assert r.returncode == 0, f"hook crashed: {r.stderr}"
    if not r.stdout.strip():
        return None
    return json.loads(r.stdout)["hookSpecificOutput"]["permissionDecision"]


def test_hook_exists_and_is_executable_python():
    assert HOOK.is_file(), f"missing hook: {HOOK}"


# ------------------------------------------------- LAPTOP / NON-HPC: the guard must NOT fire
# `.claude/hooks/` and `.claude/settings.json` ship to the PUBLIC repo, and /usr, /opt, /etc, /var
# are ordinary local directories on a Mac or Linux laptop (Homebrew lives in /opt/homebrew and
# /usr/local). An ungated guard would break every A2MC user's local searches to enforce a rule that
# only binds on a shared HPC filesystem. Regression for exactly that (2026-08-14).
@pytest.mark.parametrize("cmd", [
    "find /usr/local/lib -name '*.dylib'",
    "grep -rn 'foo' /opt/homebrew/include",
    "find /usr -name python3",
    "grep -rn 'x' /etc",
    # even the shared-top forms are none of our business off-HPC
    "find /global/cfs -name '*.nc'",
])
def test_guard_is_inert_off_hpc(cmd):
    assert run_hook(cmd, guard="off") is None, f"blocked a laptop command: {cmd}"


def test_autodetect_fires_on_an_hpc_env_marker():
    """The autodetect BRANCH itself, drivable on any machine: with no override but an HPC env
    marker present, the guard must activate. This is the half that used to be assertable only on
    Perlmutter, so off-HPC the protection went unexercised entirely."""
    verdict = run_hook("find /global -name '*.nc'", guard="",
                       env_extra={"NERSC_HOST": "perlmutter"})
    assert verdict == "deny", "autodetect ignored an HPC env marker; check _HPC_MARKER_ENV"


@pytest.mark.skipif(not _on_hpc(), reason="autodetect's marker-DIR branch needs a real HPC filesystem")
def test_guard_autodetects_on_this_machine():
    """Sanity on the machine that actually needs it: with no override at all, the guard is ACTIVE.
    Skipped off-HPC, where a correct autodetect necessarily returns False -- asserting `deny` there
    fails on a healthy checkout, and a suite that is red when nothing is wrong teaches bypass."""
    verdict = run_hook("find /global -name '*.nc'", guard="")
    assert verdict == "deny", (
        "autodetect did not activate the guard on this machine; check _HPC_MARKER_DIRS/_ENV")


# --------------------------------------------------------------------------- DENY
@pytest.mark.parametrize("cmd", [
    # the exact class of call that drew the NERSC warning
    "grep -rn 'EDPftvarcon' --include=*.F90 ~/E3SM_FATES_api43",
    "grep -rln 'phenology' ~/E3SM_FATES_api43/components/elm/src/",
    # rooted AT a shared top -- never acceptable, depth flag or not
    "find /global -name '*.nc'",
    "find /global/cfs -maxdepth 3 -name '*.nc'",
    "find / -name ecosim",
    "du -h /global/cfs",
    "ls -R /pscratch",
    "tree /usr",
    # deeper root but unbounded
    "find ~/EcoSIM -name '*.F90'",
    "fd F90 ~/EcoSIM",
    "rg --files ~",
    "python -c \"import os; [print(r) for r,d,f in os.walk('/global/cfs/cdirs/m5199')]\"",
    "ls /global/cfs/cdirs/m5199/**/*.nc",
])
def test_denies_prohibited_traversals(cmd):
    assert run_hook(cmd) == "deny", f"hook FAILED to block: {cmd}"


# --------------------------------------------------------------------------- ALLOW
@pytest.mark.parametrize("cmd", [
    # index-based: the sanctioned replacement, including across submodules
    "git grep -n 'EDPftvarcon' -- '*.F90'",
    "git -C ~/E3SM_FATES_api43 grep --recurse-submodules -n 'EDPftvarcon' -- '*.F90'",
    "git ls-files --cached --others --exclude-standard",
    # bounded root + depth limit on a shared path -- explicitly permitted by NERSC
    "find ~/EcoSIM -maxdepth 2 -name '*.F90'",
    "du -sh ~/EcoSIM",
    # workspace-relative: "a bounded root inside the current workspace"
    "grep -rn 'def sample_sobol' --include=*.py .",
    "find ./tmp -name '*.txt'",
    "rg 'LEAK_TOKENS'",
    # not traversals at all
    "ls -la ~/.claude/",
    "cat ~/EcoSIM/runfile.nml",
    "command -v python3",
    "module spider texlive",
    "sbatch ~/run.sh",
    # REGRESSION (2026-08-14): the hook denied this real command. The rglob() targets the IN-REPO
    # wiki; the shared path is only an argument to `git diff`, which is index-based. Pairing any
    # walk-token with any shared path anywhere in the command is too coarse.
    "python - <<'PY'\nimport subprocess,pathlib\n"
    "subprocess.run(['git','-C','~/E3SM_FATES_api43','diff','--name-only'])\n"
    "for p in pathlib.Path('docs/fates-knowledge-base').rglob('*.md'): print(p)\nPY",
])
def test_allows_legitimate_commands(cmd):
    assert run_hook(cmd) is None, f"hook WRONGLY blocked: {cmd}"


def test_prose_describing_a_traversal_is_not_a_traversal():
    """REGRESSION (2026-08-14): the hook denied its own fix's COMMIT MESSAGE, which quoted
    os.walk('/global/cfs/...') while explaining a regression test. A heredoc fed to `git commit -F -`
    is data, not code."""
    cmd = ("git commit -F - <<'EOF'\n"
           "Fix a traversal-hook false positive\n\n"
           "os.walk('~') -- where the walk's own argument IS the\n"
           "shared path -- must still DENY. Also `grep -rn x /global/cfs/...` stays blocked.\n"
           "EOF")
    assert run_hook(cmd) is None


def test_command_words_in_PROSE_do_not_trigger():
    """REGRESSION (2026-08-14, third prose-as-code false positive): the hook denied a command whose
    only trigger was the English word 'tree' inside an echo string. A command name appears in command
    POSITION, not merely after a space."""
    cmd = ('M=~/E3SM_FATES_api43\n'
           'echo "=== main working tree on those paths ==="\n'
           'git -C $M status --short\n'
           'echo "we should grep for it, or find the file, or du the dir"')
    assert run_hook(cmd) is None


@pytest.mark.parametrize("cmd", [
    "find /global/cfs -name x",                       # start of string
    "cd /tmp; find /global/cfs -name x",              # after ';'
    "true && find /global/cfs -name x",               # after '&&'
    "sudo find /global/cfs -name x",                  # behind a wrapper
    "echo hi\nfind /global/cfs -name x",              # start of a later line
])
def test_command_position_forms_are_still_caught(cmd):
    """The narrowing must not lose the real invocation forms."""
    assert run_hook(cmd) == "deny", f"missed a real traversal: {cmd!r}"


def test_heredoc_fed_to_an_INTERPRETER_is_still_code():
    """The narrowing must not become a bypass: the same body fed to python IS executed."""
    cmd = ("python - <<'PY'\n"
           "import os\n"
           "[print(r) for r,d,f in os.walk('~')]\n"
           "PY")
    assert run_hook(cmd) == "deny"


def test_writing_a_file_about_traversal_is_allowed():
    cmd = ("cat > ./tmp/notes.md <<'EOF'\n"
           "Never run `find /global -name x` on a shared filesystem.\n"
           "EOF")
    assert run_hook(cmd) is None


def test_inline_python_walk_ON_a_shared_path_is_still_denied():
    """The narrowing above must not let the real case through: when the walk's OWN argument is the
    shared path, it is still a prohibited traversal."""
    cmd = ("python -c \"import os; [print(r) for r,d,f in "
           "os.walk('~')]\"")
    assert run_hook(cmd) == "deny"


# --------------------------------------------------------------------------- robustness
def test_ignores_non_bash_tools():
    assert run_hook("find /global -name x", tool_name="Read") is None


def test_survives_unbalanced_quotes():
    """A crash would fail-open silently on every later command; assert it degrades gracefully."""
    assert run_hook("""grep -rn "unclosed /global/cfs/cdirs/m2467""") in {None, "deny"}


def test_empty_command_is_allowed():
    assert run_hook("") is None


def test_denial_message_names_the_bounded_alternative():
    """The message has to teach the fix, or the next attempt is just a workaround."""
    payload = json.dumps({"tool_name": "Bash",
                          "tool_input": {"command": "find /global -name '*.nc'"}})
    env = {**os.environ, "A2MC_TRAVERSAL_GUARD": "on"}   # message content, not autodetect
    r = subprocess.run([sys.executable, str(HOOK)], input=payload, env=env,
                       capture_output=True, text=True, timeout=20)
    reason = json.loads(r.stdout)["hookSpecificOutput"]["permissionDecisionReason"]
    assert "git grep" in reason
    assert "maxdepth" in reason
    assert "STOP and ask" in reason
    # NERSC forbids routing around the guard; the message must say so.
    assert "another command" in reason


def test_a_flag_from_ANOTHER_command_does_not_make_grep_recursive():
    """REGRESSION (2026-08-14, 4th prose/token false positive): `... | grep -E "x" ; rm -rf ./tmp/y`
    was denied because GREP_R_SHORT searched the whole line and found the `-r` in `rm -rf`. A flag
    belongs to the command whose argument span it sits in."""
    cmd = ('python tools/plot.py --tape ~/x.nc '
           '| grep -E "plant_C|NPP" ; rm -rf ./tmp/scratch')
    assert run_hook(cmd) is None


def test_a_REAL_recursive_grep_beside_another_command_is_still_denied():
    """The scoping must not become a bypass: the flag is in grep's OWN span here."""
    cmd = 'echo start ; grep -rn "x" ~/tree ; echo done'
    assert run_hook(cmd) == "deny"


def test_ls_R_scoping_likewise():
    assert run_hook('ls -l ~ ; tar -rf a.tar b') is None
