#!/usr/bin/env python3
"""The TMPDIR a Claude Code session in this clone hands to the agent's shell -- one definition, read
by the SessionStart hook that sets it, the PreToolUse hook that trusts it, and the clone checker
that reports it.

visibility: public

WHY. NERSC forbids writes outside $HOME, and its system login profile exports TMPDIR=/tmp for every
user, so any path a program derives at RUNTIME (a tempfile constructor, a library's own scratch
file) breaks the rule unless something points TMPDIR elsewhere. The layer that does it has to be
one that git carries, that reaches only THIS repository's sessions, and that yields an absolute path
correct on whichever machine the clone sits on.

WHY THIS LAYER. A SessionStart hook may append `export` lines to $CLAUDE_ENV_FILE, which the harness
sources before every Bash tool command of that session, and the hook can build the path from
$CLAUDE_PROJECT_DIR. The layers that look closer do not work: an `env` block in the project's
.claude/settings.json (or settings.local.json) has TMPDIR dropped, even as an absolute path, and
`${CLAUDE_PROJECT_DIR}` is not expanded in an env value; a shell profile reaches every repository on
the account, so all of them write into one clone's tmp/. The measurements are in
memory/dev_logs_adapterkit/20260929a_*.

WHY THE READER. Hook processes never see the exported value -- they keep the launching shell's
TMPDIR -- and only SessionStart hooks are given $CLAUDE_ENV_FILE. The file it names lives under
<claude config dir>/session-env/<session id>/, and every hook receives the session id, so a later
hook can read back what was exported. That location belongs to the harness, not to a documented
contract: if it moves, `session_tmpdir()` finds nothing and a guard that relies on it falls back to
refusing, never to allowing.

Standard library only, and Python 3.6-compatible: the hooks run under whatever `python3` is first
on PATH, which on Perlmutter can be the system 3.6.

Public because the two shipped hooks import it.

Author: Jing Tao with Claude.
"""
import glob
import os
import re
import shlex

_SESSION_ID_RE = re.compile(r"[A-Za-z0-9_-]+")
_EXPORT_RE = re.compile(r"^\s*export\s+TMPDIR=(.+?)\s*$")


def applies(environ=None):
    """The $HOME-only write rule is NERSC's; off NERSC nothing here acts."""
    return bool((os.environ if environ is None else environ).get("NERSC_HOST"))


def inside_home(path):
    """True when `path` resolves inside the invoking user's $HOME."""
    if not path:
        return False
    home = os.path.realpath(os.path.expanduser("~"))
    try:
        real = os.path.realpath(os.path.expandvars(path))
        return os.path.commonpath([real, home]) == home
    except ValueError:                   # different drives / unresolvable
        return False


def repo_tmpdir(root):
    """The clone's own gitignored tmp/, as an absolute path."""
    return os.path.join(os.path.realpath(str(root)), "tmp")


def export_for_session(root, env_file, environ=None):
    """Append `export TMPDIR=<root>/tmp` to the session's env file. Returns (path, None) when it
    exported, or (None, reason) when it did not. Never raises."""
    if not applies(environ):
        return None, "not a NERSC machine (NERSC_HOST unset)"
    if not env_file:
        return None, ("CLAUDE_ENV_FILE is unset, so this Claude Code cannot pass a variable from a "
                      "SessionStart hook to the agent's shell")
    target = repo_tmpdir(root)
    if not inside_home(target):
        return None, "this clone is outside $HOME, so its tmp/ is not a legal place either"
    try:
        os.makedirs(target, exist_ok=True)
        with open(env_file, "a") as fh:
            fh.write("export TMPDIR=%s\n" % shlex.quote(target))
    except OSError as exc:
        return None, "could not export it: %s" % exc
    return target, None


def session_tmpdir(session_id, environ=None):
    """The TMPDIR a SessionStart hook exported for `session_id`, or None if none was found."""
    environ = os.environ if environ is None else environ
    if not session_id or not _SESSION_ID_RE.fullmatch(str(session_id)):
        return None
    config = environ.get("CLAUDE_CONFIG_DIR") or os.path.expanduser("~/.claude")
    found = None
    for path in sorted(glob.glob(os.path.join(config, "session-env", str(session_id), "*.sh"))):
        try:
            with open(path) as fh:
                for line in fh:
                    m = _EXPORT_RE.match(line)
                    if m:
                        try:
                            parts = shlex.split(m.group(1))
                        except ValueError:
                            continue
                        if len(parts) == 1:
                            found = parts[0]
        except OSError:
            continue
    return found


def effective_tmpdir(session_id=None, environ=None):
    """The TMPDIR the agent's Bash tool actually runs with: a session export, which the harness
    sources before every command, wins over the inherited value."""
    environ = os.environ if environ is None else environ
    return session_tmpdir(session_id, environ) or environ.get("TMPDIR", "")
