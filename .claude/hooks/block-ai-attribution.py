#!/usr/bin/env python3
"""PreToolUse(Bash) hook — block git commits whose message carries AI attribution.

Matches only the literal attribution-trailer signatures (Co-Authored-By, the
"Generated with [Claude Code]" line, 🤖 Generated with) — NOT bare "Claude"/"Anthropic",
which would false-positive on legitimate messages mentioning CLAUDE.md or .claude/.
Covers commits whose MESSAGE TEXT is visible in the command string, which `-m` is and
`-F -` (a heredoc on stdin) is not: this hook inspects the command, so a message piped in
is invisible to it no matter how good the pattern list is. That blind spot, and
editor-based commits, are covered by `.githooks/commit-msg`, which git hands the final
message on disk. Activate it per clone: git config core.hooksPath .githooks
CLAUDE.md critical rule #1.
"""
import sys, json, re

# Literal AI-attribution trailer signatures (case-insensitive)
PATTERNS = [
    r"co-authored[- ]by",
    r"\U0001f916\s*generated with",     # 🤖 Generated with
    r"generated with \[?claude",
    # Session/authorship trailers. A harness may append a `Claude-Session:` URL, which is an
    # authorship trailer in everything but name and was not matched by the patterns above.
    # Kept unanchored because the message reaches us inside a shell command string, where a
    # line start is not reliably a line start.
    r"claude[- ]session\s*:",
    r"\b(assistant|ai)[- ](session|author)\s*:",
    r"https?://claude\.ai/\S*",
]


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
        sys.exit(0)
    if data.get("tool_name") != "Bash":
        sys.exit(0)
    cmd = (data.get("tool_input") or {}).get("command", "") or ""
    # Require the `commit` subcommand adjacent to `git ` (whitespace) — so this does
    # NOT match `.git/hooks/commit-msg`, `git log`, or `echo commit`. We always use
    # `git commit -m`; `git -C x commit` (rare here) is caught by the commit-msg fallback.
    # `git` and `commit` in the same command segment, allowing flags in between: the old
    # `\bgit\s+commit\b` missed `git -c core.foo=bar commit` and `git -C <dir> commit`,
    # which is how seven attributed commits got past this hook on 2026-09-04.
    if not re.search(r"\bgit\b[^|;&\n]*\bcommit\b", cmd):
        sys.exit(0)
    low = cmd.lower()
    for p in PATTERNS:
        if re.search(p, low):
            deny("Commit message contains AI attribution (matched /%s/). CLAUDE.md "
                 "rule #1 forbids Co-Authored-By / 'Generated with Claude' trailers. "
                 "Remove the attribution and retry." % p)
    sys.exit(0)


main()
