#!/usr/bin/env python3
"""Who is this session working with? Resolve it, do not guess it.

A2MC stamps an author on every calibration log it writes. An agent that guesses writes the wrong
name into a header, and a wrong name looks exactly like a right one, so nothing downstream ever
catches it.

A2MC has a sharper version of that risk than a shared team repository does. A case folder is
DELIVERED -- emailed, unpacked under `use_cases/` -- and it arrives full of logs and reports
authored by whoever ran the previous round. So an agent inferring the local convention from
neighbouring files has a plausible wrong answer sitting right there in the same directory. That is
why the last resort here is an error rather than a default.

Resolution order, first hit wins:

  1. $A2MC_USER_NAME            - explicit, per shell. Overrides everything.
  2. <repo>/.me                 - one line, the name to stamp. Gitignored, per clone.
  3. `git config user.name`     - only if it is set to something that is not obviously a
                                  placeholder; reported as a GUESS, and writing `.me` is advised.
  4. nothing                    - EXIT 1 with instructions. It does NOT fall back to a default,
                                  because a default here is a wrong attribution nobody notices.

Why `.me` and not the machine config: `a2mc_config.sh` and `a2mc_noncime_config.sh` are TRACKED,
so a name written into one is committed and travels to everyone who takes that clone, which is
exactly how a stale author propagates. `.me` is per-clone and gitignored.

    python3 tools/whoami.py              # print the name
    python3 tools/whoami.py --verbose    # name, how it was resolved, and what to do about it
    python3 tools/whoami.py --set "Ada Lovelace"    # write .me (refuses to overwrite silently)

Plain stdlib. No config needs to be sourced -- this must work in a clone that has nothing set up.
"""
import argparse
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ME = ROOT / ".me"

# `git config user.name` is a weak signal: it is often a handle, sometimes a hostname, and on a
# shared machine it can belong to whoever configured git first. These are the values seen often
# enough to be worth refusing outright rather than stamping onto someone's logs.
PLACEHOLDERS = {"", "your name", "unknown", "user", "root", "admin", "git", "none"}

HOWTO = """No author name is set, so A2MC cannot stamp the logs it writes.

Set it once for this clone:

    python3 tools/whoami.py --set "Your Name"

or, per shell:

    export A2MC_USER_NAME="Your Name"

This is deliberately not defaulted. The logs already in a delivered case folder carry the name of
whoever ran the previous round, so a guess here is a wrong attribution that reads as a right one."""


def _git_name():
    try:
        out = subprocess.run(["git", "-C", str(ROOT), "config", "user.name"],
                             stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                             universal_newlines=True, timeout=10).stdout.strip()
    except (OSError, subprocess.SubprocessError):
        return ""
    return "" if out.lower() in PLACEHOLDERS else out


def resolve():
    """Return (name, how, is_guess). name is None when nothing resolves."""
    env = os.environ.get("A2MC_USER_NAME", "").strip()
    if env:
        return env, "$A2MC_USER_NAME", False

    if ME.is_file():
        val = ME.read_text().strip().splitlines()
        val = val[0].strip() if val else ""
        if val:
            return val, str(ME.relative_to(ROOT)), False

    git = _git_name()
    if git:
        return git, "git config user.name", True

    return None, None, False


def set_me(name, force=False):
    name = name.strip()
    if not name:
        sys.exit("refusing to write an empty name to .me")
    if ME.is_file() and not force:
        cur = ME.read_text().strip()
        if cur and cur != name:
            sys.exit(".me already says %r. Re-run with --force to change it." % cur)
    ME.write_text(name + "\n")
    print("wrote %s: %s" % (ME.relative_to(ROOT), name))


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--verbose", "-v", action="store_true")
    ap.add_argument("--set", metavar="NAME", help="write NAME to <repo>/.me")
    ap.add_argument("--force", action="store_true", help="with --set, overwrite a different name")
    args = ap.parse_args()

    if args.set:
        set_me(args.set, args.force)
        return 0

    name, how, guess = resolve()
    if name is None:
        print(HOWTO, file=sys.stderr)
        return 1

    if not args.verbose:
        print(name)
        return 0

    print("name:        %s" % name)
    print("resolved by: %s" % how)
    if guess:
        print("\nThis is a GUESS taken from git, which is often a handle rather than the name you")
        print("want on a log. Confirm it with:  python3 tools/whoami.py --set \"%s\"" % name)
    return 0


if __name__ == "__main__":
    sys.exit(main())
