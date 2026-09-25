#!/usr/bin/env python3
"""UserPromptSubmit hook: a new user's first request to set up A2MC is met with ONE sentence.

PI, 2026-09-23: after a user says "help set up A2MC", the agent must say GREETING, literally, and
only the first time: "this should only work the first time the new user interact with the agent".
The `a2mc-init` skill (Step 0) carries the same sentence, but a skill is text the agent reads once
it has decided to load it, and a reply can begin before that. This hook hands the sentence to the
agent together with the user's prompt, so it is the first thing said.

It fires AT MOST ONCE PER CLONE, when all three hold:
  - the prompt asks to set up A2MC, in the first-run phrases the `a2mc-init` skill's own
    description lists (set up, get started, onboard, first time) with A2MC named, or it names
    `a2mc-init` itself, counting only what the user typed, not text they pasted;
  - this clone has not recorded its user: `.me` is missing or empty. A clone that knows its user
    has no new user in it, and this is also what keeps the hook quiet where a developer talks
    ABOUT the setup flow ("after users say help set up A2MC ...");
  - the greeting has not been said here yet: `.greeted` does not exist.
Firing CREATES `.greeted`, with an exclusive create, so the check and the claim are one step: two
sessions opened at once cannot both greet, and every later setup request, in this session or any
other, answered or not, is silent. A prompt that is not a setup request does not use it up. If
`.greeted` cannot be created the hook does not fire, because at most once is the contract. To see
the greeting again (testing), delete `.greeted` in a clone without `.me`.

The clone root is three directories up from this file (`<root>/.claude/hooks/<this file>`), the
same file-relative rule `tools/whoami.py` uses to find `.me`, so it holds whatever the cwd is.

Runs as `python3`, which on Perlmutter is the system 3.6, so nothing newer than 3.6 is used. A hook
must never break a session, so every failure exits 0 with no output.

Contract (code.claude.com/docs/en/hooks): "UserPromptSubmit input" puts the user's text in
`prompt`; "UserPromptSubmit decision control" takes `hookSpecificOutput.additionalContext`, which
Claude reads and the user does not see; a hook's context is capped at 10,000 characters.
Test: tests/test_greet_on_setup.py.

Author: Jing Tao with Claude on Perlmutter.
"""
import json
import os
import re
import sys
import time

# The one copy the code uses. The a2mc-init skill, the interview questionnaire and the tutorial
# quote it, and tests/test_greet_on_setup.py fails if any copy stops matching this one.
GREETING = ("Hi! I'm your A2MC agent, and I'll work with you as your science assistant to "
            "calibrate your model. What's your name, and how should I address you?")

# Written at the clone root when the greeting is handed out; gitignored, per clone, like `.me`.
MARKER = ".greeted"

# Pasted text arrives expanded inside `prompt`, between these marker lines (per the docs above).
_PASTED = re.compile(r'<pasted_content id="[^"]*">.*?</pasted_content id="[^"]*">', re.S)
_SETUP = re.compile(r"\bset(?:ting)?[\s-]*up\b|\bget(?:ting)?\s+started\b"
                    r"|\bonboard(?:ing)?\b|\bfirst\s+time\b", re.I)
_A2MC = re.compile(r"\ba2mc\b", re.I)
_INIT = re.compile(r"\ba2mc-init\b", re.I)

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def is_setup_request(prompt):
    """True when the user's OWN words ask to set up A2MC. A pasted log that mentions setup is not
    a request, so pasted blocks are removed before matching."""
    typed = _PASTED.sub(" ", prompt or "")
    return bool(_INIT.search(typed) or (_SETUP.search(typed) and _A2MC.search(typed)))


def user_known(root):
    """True when `.me` names someone. Read as bytes, so a non-ASCII name cannot raise under the
    C locale a login node's system python3 may run with."""
    try:
        with open(os.path.join(root, ".me"), "rb") as f:
            return bool(f.read().strip())
    except (IOError, OSError):
        return False


def claim_greeting(root):
    """Create `.greeted` and say whether THIS call created it. The exclusive create is the check
    and the claim at once, so of two sessions started together exactly one greets. Any failure,
    a clone that cannot be written included, is "not claimed": a greeting that cannot be recorded
    is not given, since recording it is what keeps it from being given twice."""
    try:
        fd = os.open(os.path.join(root, MARKER), os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o644)
    except OSError:
        return False
    try:
        os.write(fd, ("said %s by .claude/hooks/greet-on-setup.py\n"
                      % time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())).encode("ascii"))
    except OSError:
        pass                            # the file existing is the claim; its text is only a note
    finally:
        os.close(fd)
    return True


def instruction():
    return ("The user is asking to set up A2MC, and this clone has not recorded who its user is "
            "(no .me). Begin your reply with this sentence, word for word, as plain text with no "
            "quotation marks, and put nothing before it:\n\n"
            + GREETING + "\n\n"
            "The setup tutorial shows new users this exact sentence as the first thing the agent "
            "says, so do not paraphrase it. This is the one time it is said in this clone. It "
            "opens Step 0 of the `a2mc-init` skill: follow that skill from here, but do not greet "
            "again when you reach its Step 0; go on to recording the answer with "
            "python3 tools/whoami.py --set \"<name>\". If the start-up snapshot asked you to tell "
            "the user something, say it after the greeting, in one short line. Then wait for "
            "their answer.")


def main():
    try:
        data = json.loads(sys.stdin.read() or "{}")
        prompt = data.get("prompt", "") if isinstance(data, dict) else ""
        # Order matters: the claim comes last, so only a greeting actually handed out uses it up.
        if (not isinstance(prompt, str) or not is_setup_request(prompt) or user_known(ROOT)
                or not claim_greeting(ROOT)):
            return
        print(json.dumps({"hookSpecificOutput": {"hookEventName": "UserPromptSubmit",
                                                 "additionalContext": instruction()}}))
    except Exception:
        return                          # a hook must never break a session


if __name__ == "__main__":
    main()
