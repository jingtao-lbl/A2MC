#!/usr/bin/env python3
"""PreToolUse(Bash) hook -- refuse a bare `sbatch`; a run is submitted through tools/submit_run.py.

visibility: public

WHY. A run that is submitted and not registered is invisible to the run ledger, the table generated
from it, and every check over them; registering it later depends on someone remembering, and the
account in `memory/dev_logs_adapterkit/20261014a_*` is what that looks like in practice.
`tools/submit_run.py` submits AND registers in one step, so the reliable route is to make it the
only route the agent takes.

WHAT IS DENIED. A Bash command that invokes `sbatch` as a command: at the start of the command, after
`;`, `&&`, `||`, `|`, `(`, a newline or inside `$( ... )` / backticks, optionally behind environment
assignments and the wrappers `timeout N`, `nohup`, `env`, `command`, `exec`; and the list form
`["sbatch", ...]` that a Python heredoc passes to subprocess. Text that merely MENTIONS sbatch (`git
grep sbatch`, an echo, a comment, a quoted search pattern such as 'a|sbatch|b') is not a submission
and passes: quoted text is removed before the command-position match, keeping only the `$( ... )`
and backtick substitutions that still execute inside double quotes.

WHAT IS ALLOWED.
  * any command that runs `tools/submit_run.py`;
  * `sbatch --test-only ...`, which validates a request and creates no job (checked per invocation,
    so a command that tests and then submits is still refused);
  * a job the ledger deliberately does not record -- not a simulation (an output extraction, a
    build, a transfer), or a full config-generated Phase-0 ensemble, whose full record is the
    `run_tracking/` subfolder of the round's Phase-0 stem (PI; phase0-design Step 3): declare it on
    the command with
    `A2MC_UNTRACKED_JOB="<why the ledger does not record it>"` (at least 10 characters). The reason
    lands in the transcript, which is the record.

LIMIT. It reads the command text, so an `sbatch` inside a script file the command runs is not seen;
`tools/submit_ensemble.sh`, `submit_phase0.py`, `submit_experiments.py` and CIME's `case.submit` are
ensemble launchers with their own records and are not in scope.

Schema: denies via {"hookSpecificOutput": {"hookEventName": "PreToolUse", "permissionDecision":
"deny", "permissionDecisionReason": ...}}.

Author: Jing Tao with Claude
"""
import json
import re
import sys

_WRAP = r"(?:(?:timeout\s+(?:-\S+\s+)*\S+|nohup|env|command|exec|time)\s+)*"
_ENV = r"(?:[A-Za-z_][A-Za-z0-9_]*=(?:\"[^\"]*\"|'[^']*'|\S*)\s+)*"
SBATCH_CMD = re.compile(r"(?:^|[;&|(\n`]|\$\()\s*" + _ENV + _WRAP + r"sbatch(?=\s|$|[;&|)`])",
                        re.M)
SBATCH_LIST = re.compile(r"""[\[(,]\s*["']sbatch["']""")
WRAPPER = re.compile(r"\btools/submit_run\.py\b")
UNTRACKED = re.compile(r"""\bA2MC_UNTRACKED_JOB=(?:"([^"]*)"|'([^']*)'|(\S+))""")


_SQ = re.compile(r"'[^']*'")
_DQ = re.compile(r'"(?:[^"\\]|\\.)*"')
_SUB = re.compile(r"\$\([^()]*\)|`[^`]*`")


_HEREDOC = re.compile(r"<<-?\s*(['\"]?)([A-Za-z_][A-Za-z0-9_]*)\1")


def _drop_heredocs(cmd: str) -> str:
    """Remove heredoc BODIES: they are input to a command (a Python script, a commit message, a
    file being written), not shell commands. An unterminated body is dropped to the end."""
    out, i = [], 0
    while True:
        m = _HEREDOC.search(cmd, i)
        eol = cmd.find("\n", m.end()) if m else -1
        if not m or eol < 0:
            out.append(cmd[i:])
            return "".join(out)
        out.append(cmd[i:eol + 1])
        end = re.compile(r"^[ \t]*" + re.escape(m.group(2)) + r"[ \t]*$", re.M).search(cmd, eol + 1)
        if not end:
            return "".join(out)
        i = end.end()


def _unquoted(cmd: str) -> str:
    """The command with heredoc bodies and quoted TEXT removed, so a `|` or newline inside a grep
    pattern, an echo, a commit message or a script fed on stdin is not read as a command separator.
    Single quotes are fully literal to the shell; inside double quotes only `$( ... )` and
    backticks still execute, so those are kept."""
    cmd = _SQ.sub("''", _drop_heredocs(cmd))
    return _DQ.sub(lambda m: " ".join(_SUB.findall(m.group(0))) or '""', cmd)


_SEGMENT_END = re.compile(r"[;&|\n)`]")


def _submits(text: str, pattern, end) -> bool:
    """True if any match of `pattern` is a real submission: `--test-only` asks the scheduler to
    validate a request and creates no job, so an invocation carrying it is not one."""
    for m in pattern.finditer(text):
        stop = end.search(text, m.end())
        if "--test-only" not in text[m.end():stop.start() if stop else len(text)]:
            return True
    return False


def is_bare_submission(cmd: str) -> bool:
    if WRAPPER.search(cmd):
        return False
    # The list form is matched on the RAW text: it lives inside quotes by construction.
    return (_submits(cmd, SBATCH_LIST, re.compile(r"[\])]"))
            or _submits(_unquoted(cmd), SBATCH_CMD, _SEGMENT_END))


def untracked_reason(cmd: str) -> str:
    m = UNTRACKED.search(cmd)
    if not m:
        return ""
    return next((g for g in m.groups() if g is not None), "").strip()


REASON = (
    "A bare `sbatch` submits a run the run ledger never sees. Submit through the wrapper, which "
    "registers it in the same step:\n"
    "  python tools/submit_run.py --case-dir use_cases/<Model>_<Case> --round R --cycle C \\\n"
    "      --case <record name> --purpose \"...\" --differences \"<base> EXCEPT <what> = <value>\" \\\n"
    "      --binary <archived exe> --run-dir <its directory>   (or --run-root <root> for one row\n"
    "      covering a whole submission) [--stem <stem>] [--job-id-file <dir>/job_id.txt] \\\n"
    "      -- <the sbatch arguments and script, unchanged>\n"
    "stdout is only the job id, so J=$(python tools/submit_run.py ...) works.\n"
    "If the ledger deliberately does not record this job (an extraction, a build, a transfer, or a "
    "full Phase-0 ensemble, whose full record is the run_tracking/ subfolder of the round's Phase-0 "
    "stem), say so on the "
    "command: "
    "A2MC_UNTRACKED_JOB=\"<why the ledger does not record it>\" sbatch ...   "
    "Contract: .claude/hooks/block-unregistered-sbatch.py"
)


def main() -> int:
    try:
        payload = json.load(sys.stdin)
    except Exception:
        return 0
    if payload.get("tool_name") != "Bash":
        return 0
    cmd = (payload.get("tool_input") or {}).get("command") or ""
    if "sbatch" not in cmd or not is_bare_submission(cmd):
        return 0
    why = untracked_reason(cmd)
    if len(why) >= 10:
        return 0
    reason = REASON
    if why:
        reason = (f"A2MC_UNTRACKED_JOB is set but its reason is too short to be one ({why!r}); "
                  f"say why this job is not a run.\n\n" + REASON)
    json.dump({"hookSpecificOutput": {"hookEventName": "PreToolUse",
                                      "permissionDecision": "deny",
                                      "permissionDecisionReason": reason}}, sys.stdout)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
