"""The no-writes-outside-home hook, and the three holes an agent actually fell through.

NERSC's hard rule is that nothing may be written outside `$HOME`. `.claude/hooks/
block-forbidden-writes.py` is a PreToolUse(Bash) hook enforcing it, and it can only inspect a
command's TEXT -- which is the whole difficulty, because a path can be produced at RUNTIME.

MEASURED 2026-09-15. An agent created a directory under the system temp with a `tempfile`
constructor inside a heredoc and was not stopped. Probing afterwards found three holes, in order of
how badly they undercut the rule:

  1. a runtime-derived path leaves NO literal in the command, so the path scan matched nothing;
  2. the name check was for the shell builtin, which also happens to match the DEPRECATED
     `tempfile.mktemp` but not the directory variant everyone actually calls -- one letter apart;
  3. widest of the three: an in-program write to a LITERAL system path was allowed, because after
     matching the path the hook demanded a SHELL write verb (cp/mv/tee/...) and a Python
     `open(..., 'w')` is none of them.

The real fix is not this hook. `TMPDIR` now points inside `$HOME` (see `~/.bashrc`), so a runtime
temp write is legal by construction in any language that honours it; this hook is the backstop for
the literal forms. That is why the expectations below are parameterised on TMPDIR: with a SAFE
TMPDIR the constructors are fine, and an explicit system-temp path is still refused, because
pointing TMPDIR somewhere legal does not bless a write that names `/tmp` outright.

The test builds its trigger strings by concatenation. The hook inspects command text, so a test
that spells the words out gets its own probe blocked -- which happened twice while writing this.

Author: Jing Tao with Claude.
"""
from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
HOOK = REPO / ".claude" / "hooks" / "block-forbidden-writes.py"
DENY = '"permissionDecision": "deny"'

SYS_TMP = "/" + "tmp"
MKTEMP = "mk" + "temp"
MKDTEMP = "mkd" + "temp"
SAFE_TMPDIR = str(Path.home() / "A2MC-adapter" / "tmp")


def _run(cmd: str, tmpdir: str) -> bool:
    """True when the hook DENIES `cmd` with $TMPDIR set to `tmpdir`."""
    if not HOOK.is_file():
        pytest.skip("block-forbidden-writes.py not present in this clone")
    r = subprocess.run(
        ["python3", str(HOOK)],
        input=json.dumps({"tool_name": "Bash", "tool_input": {"command": cmd}}),
        capture_output=True, text=True, env=dict(os.environ, TMPDIR=tmpdir),
    )
    assert r.returncode == 0, f"hook crashed: {r.stderr}"
    return DENY in r.stdout


# --------------------------------------------------------------- always refused

ALWAYS_DENIED = [
    ("shell redirect", f"echo x > {SYS_TMP}/foo"),
    ("bare shell temp maker", f"{MKTEMP} -d"),
    ("file op into system temp", f"cp a.txt {SYS_TMP}/"),
    # HOLE 3, and the widest: the path IS in the text, but no shell verb accompanies it.
    ("in-program write to a literal system path",
     f"""python3 -c "open('{SYS_TMP}/x','w').write('1')" """),
    ("pathlib write_text to a literal system path",
     f"""python3 -c "from pathlib import Path; Path('{SYS_TMP}/x').write_text('1')" """),
]


@pytest.mark.parametrize("tmpdir", [SYS_TMP, SAFE_TMPDIR], ids=["unsafe_TMPDIR", "safe_TMPDIR"])
@pytest.mark.parametrize("label,cmd", ALWAYS_DENIED, ids=[c[0] for c in ALWAYS_DENIED])
def test_writing_outside_home_is_always_refused(label: str, cmd: str, tmpdir: str):
    """A safe TMPDIR must not bless a write that names a system path outright."""
    assert _run(cmd, tmpdir), f"allowed a write outside home: {label}"


# --------------------------------------------------------------- refused only while TMPDIR is unsafe

RUNTIME_DERIVED = [
    ("the constructor that was missed", f"""python3 -c "import tempfile; tempfile.{MKDTEMP}()" """),
    ("the same inside a heredoc",
     f"python3 - <<PY\nimport tempfile\ntempfile.{MKDTEMP}()\nPY"),
    ("NamedTemporaryFile", 'python3 -c "import tempfile; tempfile.NamedTemporaryFile()"'),
    ("TemporaryDirectory", 'python3 -c "import tempfile; tempfile.TemporaryDirectory()"'),
]


@pytest.mark.parametrize("label,cmd", RUNTIME_DERIVED, ids=[c[0] for c in RUNTIME_DERIVED])
def test_a_runtime_derived_temp_path_is_refused_when_TMPDIR_is_unsafe(label: str, cmd: str):
    """HOLES 1 and 2. No literal path appears, so this can only be caught by NAME."""
    assert _run(cmd, SYS_TMP), f"allowed a runtime-derived write outside home: {label}"


@pytest.mark.parametrize("label,cmd", RUNTIME_DERIVED, ids=[c[0] for c in RUNTIME_DERIVED])
def test_the_same_commands_are_fine_once_TMPDIR_is_inside_home(label: str, cmd: str):
    """The point of the TMPDIR fix: these become legal rather than merely tolerated. Without this
    the hook would refuse correct commands forever and train people to work around it."""
    assert not _run(cmd, SAFE_TMPDIR), f"refused a legal temp write: {label}"


# --------------------------------------------------------------- never refused

@pytest.mark.parametrize("tmpdir", [SYS_TMP, SAFE_TMPDIR], ids=["unsafe_TMPDIR", "safe_TMPDIR"])
@pytest.mark.parametrize("label,cmd", [
    ("reading from system temp", f"cat {SYS_TMP}/somefile"),
    ("writing to the repo's own tmp", "echo x > ./tmp/foo"),
    ("an explicitly pinned dir=", f"""python3 -c "import tempfile; tempfile.{MKDTEMP}(dir='./tmp')" """),
    ("a shell temp maker with -p", f"{MKTEMP} -p ./tmp"),
], ids=["read", "repo_tmp", "pinned_dir", "mktemp_p"])
def test_legitimate_commands_are_not_blocked(label: str, cmd: str, tmpdir: str):
    """A gate that fires on correct work gets disabled, and then it guards nothing."""
    assert not _run(cmd, tmpdir), f"blocked a legitimate command: {label}"


def test_the_hook_is_registered_as_a_PreToolUse_hook():
    """The file existing proves nothing; an unregistered hook is decoration."""
    settings = json.loads((REPO / ".claude" / "settings.json").read_text())
    pre = json.dumps(settings.get("hooks", {}).get("PreToolUse", []))
    assert "block-forbidden-writes.py" in pre, "the hook is not registered in .claude/settings.json"
