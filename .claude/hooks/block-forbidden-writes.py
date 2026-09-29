#!/usr/bin/env python3
"""PreToolUse(Bash) hook — enforce the NERSC "no writes outside home" hard rule.

Denies a Bash command only when it appears to WRITE to a system temp/scratch path
(/tmp, /scratch, /dev/shm, $SCRATCH, $TMPDIR) or uses bare `mktemp`. READS from those
paths are allowed, and the project's own repo-internal `tmp/` dir (e.g.
.../A2MC/tmp, ./tmp) is NOT flagged — only absolute system paths at a token boundary.

Limit: cannot see writes made *inside a script file* (`python foo.py` where foo.py writes to
/tmp). It now DOES catch the inline forms -- `python -c`, a heredoc, `open(p,'w')`, and the
`tempfile` constructors -- which is how the gap was actually reached.

WHAT THIS MISSED, AND WHY (measured 2026-09-15). An agent created a directory under /tmp with
`tempfile.mkdtemp()` inside a `python3 -` heredoc and was not stopped. Two independent holes:

  * the command text held no `/tmp` literal at all -- `mkdtemp()` derives the path at RUNTIME
    from $TMPDIR -- so ABS_RE matched nothing and the hook exited early; and
  * the name check was `\bmktemp\b`, which matches the shell builtin and the DEPRECATED
    `tempfile.mktemp`, but not `mkdtemp`, one letter away and the function everyone uses.

A third hole surfaced in the same probe and is wider than either: `python3 -c "open('/tmp/x','w')"`
was allowed even though the path IS in the text, because after matching a path the hook demanded a
SHELL write verb (cp|mv|tee|...) and a Python `open(..., 'w')` is none of them.

THE REAL FIX IS NOT THIS FILE. Pattern-matching command text is whack-a-mole: every language has
its own temp API and its own way to build a path at runtime. TMPDIR is pointed at the clone's own
tmp/ -- for the agent's shell by the SessionStart hook, for any other shell by sourcing a machine
config -- so a runtime temp write lands somewhere legal BY CONSTRUCTION, in any language that
honours it. This hook is the backstop for the literal forms, not the guarantee.

Consequently $TMPDIR is no longer denied outright: it is denied only when it does NOT resolve
inside $HOME, because pointing it at a safe directory is exactly the fix above. "It" means the
value the Bash command will actually run with, which is not this hook's own: a SessionStart export
reaches the agent's shell but never a hook process, so the session's export is read back by
session id (tools/session_tmpdir.py). If that read finds nothing, the hook falls back to its own
environment, i.e. it refuses rather than allows.

Schema: reads the tool-call JSON on stdin; denies via
{"hookSpecificOutput": {"hookEventName": "PreToolUse", "permissionDecision": "deny", ...}}.
See feedback_no_writes_outside_home / CLAUDE.md.
"""
import sys, json, re, os

# Absolute system temp/scratch path at a token boundary — excludes .../A2MC/tmp, ./tmp
ABS_RE = re.compile(r"""(?:^|[\s"'=(:|&;])(?:/tmp|/scratch|/dev/shm)(?:$|[/\s"'):|&;])""")
VAR_RE = re.compile(r"""\$\{?SCRATCH\}?""")
TMPDIR_RE = re.compile(r"""\$\{?TMPDIR\}?""")
REDIR_RE = re.compile(r""">>?\s*["']?(?:/tmp|/scratch|/dev/shm|\$\{?(?:SCRATCH|TMPDIR)\}?)""")
FILEOP_RE = re.compile(r"""\b(?:cp|mv|rsync|tee|install|touch|mkdir|dd|ln)\b""")
MKTEMP_RE = re.compile(r"""\bmktemp\b""")
MKTEMP_SAFE_RE = re.compile(r"""\bmktemp\b[^\n]*\s-(?:p|-tmpdir)\b""")

# Python/Perl/Node temp constructors that DERIVE a path at runtime, so no literal appears in the
# command text. `dir=` / `-p` pins the location explicitly, and is the documented safe form.
TEMPFILE_RE = re.compile(
    r"""\b(?:mkdtemp|mkstemp|NamedTemporaryFile|TemporaryDirectory|TemporaryFile|gettempdir)\b""")
TEMPFILE_SAFE_RE = re.compile(r"""\bdir\s*=""")
# An in-program write: `open(path, 'w'|'a'|'x'|'wb'…)`, or a writing helper taking a path.
INPROG_WRITE_RE = re.compile(
    r"""\bopen\s*\([^)]*["'][wax]b?\+?["']|"""
    r"""\b(?:write_text|write_bytes|savefig|to_csv|np\.save|json\.dump|shutil\.(?:copy\w*|move))\s*\(""")


def _inside_home(td) -> bool:
    if not td:
        return False
    home = os.path.realpath(os.path.expanduser("~"))
    try:
        return os.path.commonpath([os.path.realpath(td), home]) == home
    except ValueError:                   # different drives / unresolvable
        return False


def _session_export(session_id):
    """The TMPDIR this session's SessionStart hook exported, or None. Any failure is None."""
    try:
        import importlib.util
        root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        spec = importlib.util.spec_from_file_location(
            "_session_tmpdir", os.path.join(root, "tools", "session_tmpdir.py"))
        m = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(m)
        return m.session_tmpdir(session_id)
    except Exception:
        return None


def _tmpdir_is_safe(session_id=None) -> bool:
    """True when the TMPDIR the command will run with points inside $HOME, which is the whole
    point of setting it. A session export wins over the inherited value, as it does in the shell."""
    return _inside_home(_session_export(session_id) or os.environ.get("TMPDIR", ""))


def deny(reason):
    print(json.dumps({"hookSpecificOutput": {
        "hookEventName": "PreToolUse",
        "permissionDecision": "deny",
        "permissionDecisionReason": reason}}))
    sys.exit(0)


def main():
    try:
        data = json.load(sys.stdin)
    except Exception:
        sys.exit(0)                      # unparseable → don't block
    if data.get("tool_name") != "Bash":
        sys.exit(0)
    cmd = (data.get("tool_input") or {}).get("command", "") or ""

    # bare mktemp defaults to /tmp (a write outside home)
    if MKTEMP_RE.search(cmd) and not MKTEMP_SAFE_RE.search(cmd):
        deny("`mktemp` defaults to /tmp (write outside home). Use a repo-internal temp, "
             "e.g. `mktemp -p ./tmp`, or write under the project dir.")

    # Runtime-derived temp paths (tempfile.mkdtemp and friends). No literal appears in the text,
    # so this must be caught by NAME. Safe when $TMPDIR is inside $HOME, or when `dir=` pins it.
    safe_tmpdir = _tmpdir_is_safe(data.get("session_id"))
    if TEMPFILE_RE.search(cmd) and not TEMPFILE_SAFE_RE.search(cmd) and not safe_tmpdir:
        deny("A tempfile constructor (mkdtemp/mkstemp/NamedTemporaryFile/…) derives its path from "
             "$TMPDIR, which currently resolves OUTSIDE $HOME. NERSC HARD RULE: no writes outside "
             "home. Pass an explicit `dir=` inside the repo (e.g. dir='./tmp'), or set TMPDIR to a "
             "directory under $HOME.")

    if not (ABS_RE.search(cmd) or VAR_RE.search(cmd)
            or (TMPDIR_RE.search(cmd) and not safe_tmpdir)):
        sys.exit(0)                      # no forbidden temp/scratch path referenced

    if REDIR_RE.search(cmd) or FILEOP_RE.search(cmd) or INPROG_WRITE_RE.search(cmd):
        deny("Command appears to WRITE to a forbidden system path "
             "(/tmp, /scratch, /dev/shm, $SCRATCH, $TMPDIR). NERSC HARD RULE: no writes "
             "outside home. Reads are fine — write to a repo-internal dir (e.g. ./tmp) "
             "instead. If this is read-only, rephrase to avoid the write-like token.")
    sys.exit(0)


main()
