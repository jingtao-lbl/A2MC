#!/usr/bin/env python3
"""A changed skill carries a dev log in the same commit.

visibility: public

Public because the shipped pre-commit invokes it; in a tree with no dev-log stream it reports
not-applicable and exits 0.

WHY. A `SKILL.md` is the contract the agent follows, so changing one changes behaviour, and the
reason has to be findable afterwards. The skill's own `## Changelog` line is not that record: it is
stripped from every shipped copy and holds one paragraph, not the evidence. The capability check
(pre-commit 5c) never looked under `.claude/skills/`, and it is advisory by design, so a skill change
with no log went through silently. Pre-commit check (28) runs this and BLOCKS.

WHAT COUNTS. A staged skill that is added, deleted, renamed, or modified in content. A modification
that only moves line breaks or blockquote `>` markers -- a reflow -- is exempt: with whitespace and
line-leading `>` removed, the old and new text are identical.

WHAT SATISFIES IT. A dated dev log (`memory/dev_logs*/.../YYYYMMDD*.md`) added or modified in the
same commit.

Usage:
    python3 tools/check_skill_change_logged.py --staged        # what the pre-commit runs
    python3 tools/check_skill_change_logged.py --commit <rev>  # audit one commit

Exit 0 clean or not applicable; 1 a skill changed with no dev log beside it.

Author: Jing Tao with Claude on Perlmutter.
"""
import argparse
import os
import re
import subprocess
import sys

SKILL = re.compile(r"^\.claude/skills/[^/]+/SKILL\.md$")
DEV_LOG = re.compile(r"^memory/dev_logs[^/]*/(?:.*/)?\d{8}[^/]*\.md$")


def git(root, *args):
    try:
        return subprocess.check_output(["git", "-C", root] + list(args),
                                       stderr=subprocess.DEVNULL).decode("utf-8", "replace")
    except subprocess.CalledProcessError:
        return None


def norm(text):
    """Text with line-leading '>' and every whitespace character removed."""
    return re.sub(r"\s+", "", re.sub(r"(?m)^>", "", text or ""))


def changes(root, rev):
    """[(status, path, old_spec, new_spec)] for the staged index, or for one commit."""
    if rev is None:
        out = git(root, "diff", "--cached", "--name-status", "-M") or ""
        old_of, new_of = "HEAD:%s", ":%s"
    else:
        out = git(root, "diff-tree", "--no-commit-id", "-r", "--name-status", "-M", rev) or ""
        old_of, new_of = rev + "^:%s", rev + ":%s"
    rows = []
    for line in out.splitlines():
        parts = line.split("\t")
        status, path = parts[0][:1], parts[-1]
        rows.append((status, path, old_of % parts[1] if len(parts) > 1 else None, new_of % path))
    return rows


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--staged", action="store_true")
    g.add_argument("--commit")
    args = ap.parse_args(argv)

    root = (git(os.getcwd(), "rev-parse", "--show-toplevel") or "").strip()
    if not root:
        print("check_skill_change_logged: not in a git repository (skip)")
        return 0
    mem = os.path.join(root, "memory")
    if not (os.path.isdir(mem) and any(d.startswith("dev_logs") for d in os.listdir(mem))):
        print("check_skill_change_logged: no dev-log stream in this tree (skip)")
        return 0

    rows = changes(root, args.commit)
    logged = any(s in "AM" and DEV_LOG.match(p) for s, p, _o, _n in rows)
    changed = []
    for status, path, old, new in rows:
        if not SKILL.match(path):
            continue
        if status == "M" and norm(git(root, "show", old)) == norm(git(root, "show", new)):
            continue                                   # line breaks only: a reflow
        changed.append((status, path))

    if not changed or logged:
        print("check_skill_change_logged: %s" % (
            "%d skill change(s), logged" % len(changed) if changed else "no skill content changed"))
        return 0
    print("check_skill_change_logged: %d skill change(s) with NO dev log in the same commit:" % len(changed))
    for status, path in changed:
        print("  %s %s" % (status, path))
    print("A skill is the agent's contract; its change needs a record a reader can find. Write the log")
    print("(the `log` skill), stage it with the skill, and commit again. A reflow that only moves line")
    print("breaks is exempt and was already let through.")
    return 1


if __name__ == "__main__":
    sys.exit(main())
