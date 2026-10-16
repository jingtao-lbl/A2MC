#!/usr/bin/env python3
"""PreToolUse hook: a Bash command that reads `$?` after a PIPELINE gets a false pass.

visibility: public

WHY THIS EXISTS
---------------

In a POSIX shell `$?` after `a | b` is **b's** status, not `a`'s. So the common verification
shape

    python3 tools/check_something.py <args> | tail -3 ; echo "exit=$?"

prints `exit=0` whenever `tail` succeeds -- which is always -- no matter what the checker did.
The reading is not merely missing, it is CONFIDENTLY WRONG in the safe direction, which is the
expensive kind: a checker that failed is reported as clean and the run proceeds.

The project already carries `feedback_a_check_that_cannot_fail`, and it is about checks one
WRITES. This is the same failure one layer down: the check was fine and the way its result was
READ could not fail. Nothing in the repo looked at that, because it lives in the shape of a
shell command rather than in a file.

The two measured cases, and why this hook exists at all:
`memory/dev_logs_adapterkit/20261010k_A_Dollar_Question_After_A_Pipe_Is_The_Wrong_Command_s_Status.md`

WHAT IT DOES AND DOES NOT MATCH
-------------------------------

Fires only when BOTH appear in one command: a pipe, and a later read of `$?` (`$?`, `exit=$?`,
`rc=$?`, `[ $? -ne 0 ]`). It stays silent when the command uses a correct form --
`${PIPESTATUS[0]}`, `set -o pipefail`, or `if cmd | ...; then` -- because those are the fixes it
is asking for and flagging them would train the reader to ignore it.

It is a REMINDER, never a block. A pipeline-then-`$?` is legitimate when the status you want
really is the last stage's, and the hook cannot tell which you meant.

Author: Jing Tao with Claude on Perlmutter
"""

import json
import re
import sys

#: A pipe that is a real pipeline, not `||`, not a `|` inside a bracket class or an awk/grep ERE.
#: Crude on purpose: a false POSITIVE here costs one line of advice, a false negative costs a
#: wrong verdict, so the matcher leans toward speaking.
PIPE = re.compile(r"(?<!\|)\|(?!\|)")

#: Reading the status back: `$?` in any of the forms this project actually writes.
READS_STATUS = re.compile(r"\$\?")

#: The correct forms. Their presence means the author already knows, so stay quiet.
ALREADY_CORRECT = re.compile(r"PIPESTATUS|pipefail")

MESSAGE = (
    "PIPELINE + $? -- `$?` after `a | b` is B's status, not A's.\n"
    "  `tool.py ... | tail -3; echo \"exit=$?\"` prints exit=0 whenever tail succeeds, so a\n"
    "  FAILING checker reads as clean. Measured twice on 2026-10-10, once on a tool whose whole\n"
    "  contract is that it exits non-zero (it printed WATCHER DIED beside exit=0).\n"
    "  Use `${PIPESTATUS[0]}`, or `set -o pipefail`, or run the tool unpiped and filter after.\n"
    "  Ignore this when the last stage's status is genuinely the one you want."
)

def main() -> None:
    try:
        payload = json.load(sys.stdin)
    except Exception:
        sys.exit(0)                                   # unparseable -> stay silent
    if payload.get("tool_name") != "Bash":
        sys.exit(0)
    cmd = (payload.get("tool_input") or {}).get("command", "") or ""
    if not cmd:
        sys.exit(0)
    if ALREADY_CORRECT.search(cmd):
        sys.exit(0)
    if not (PIPE.search(cmd) and READS_STATUS.search(cmd)):
        sys.exit(0)
    # Only speak when the $? read comes AFTER a pipe; `cmd; echo $? | tee x` is not the defect.
    if cmd.index("$?") < (PIPE.search(cmd).start() if PIPE.search(cmd) else 0):
        sys.exit(0)
    print(json.dumps({"hookSpecificOutput": {
        "hookEventName": "PreToolUse",
        "additionalContext": MESSAGE,
    }}))
    sys.exit(0)

if __name__ == "__main__":
    main()
