#!/usr/bin/env python3
"""Merge the framework's Claude Code hook registrations into a project repo's settings file.

visibility: public

`.claude/settings.json` is the one file both halves of a wrapped project repo must write: Claude
Code reads a repository's committed hook registrations from the repo root and nowhere else, so the
framework's hooks and the project's own hooks have to share it. Copying the framework's file would
delete the project's registrations; not carrying it leaves every framework hook file present and
none of them registered, which is silent -- the write guard, the traversal guard and the session
snapshot simply never run.

The rule is the one A2MC's project-repository sync leg uses: start from the FRAMEWORK's file as it is, then add
every entry of the destination's whose command does NOT contain the framework's hooks path. A
project hook is registered as `${CLAUDE_PROJECT_DIR}/<Project>/.claude/hooks/...`, which never
contains `${CLAUDE_PROJECT_DIR}/.claude/hooks/`, so it is always kept; a framework hook the
framework has since retired is not re-added, because the destination's copy of it is discarded.
Top-level keys the destination has and the framework does not are kept too.

Usage:  _wrap_merge_settings.py <framework settings.json> <destination settings.json>
Writes the destination file in place; prints what it kept. Exit 1 on invalid JSON, since merging
around an unreadable file would delete every registration in it.

Author: Jing Tao with Claude on Perlmutter.
"""
import json
import os
import sys

FRAMEWORK = "${CLAUDE_PROJECT_DIR}/.claude/hooks/"


def load(path, label):
    if not os.path.isfile(path):
        return None
    try:
        with open(path) as f:
            return json.load(f)
    except ValueError as e:
        sys.stderr.write("ERROR: %s %s is not valid JSON (%s); refusing to merge around it.\n"
                         % (label, path, e))
        sys.exit(1)


def merge(ours, theirs):
    """Return (merged, kept): the framework's settings plus every non-framework entry of theirs."""
    merged = json.loads(json.dumps(ours or {}))
    kept = []
    if not theirs:
        return merged, kept
    for key, value in theirs.items():
        if key != "hooks" and key not in merged:
            merged[key] = value
            kept.append("top-level key %r" % key)
    hooks = merged.setdefault("hooks", {})
    for event, groups in (theirs.get("hooks") or {}).items():
        for group in groups or []:
            mine = [h for h in (group.get("hooks") or []) if FRAMEWORK not in h.get("command", "")]
            if not mine:
                continue
            target = next((g for g in hooks.setdefault(event, [])
                           if g.get("matcher") == group.get("matcher")), None)
            if target is None:
                target = dict((k, v) for k, v in group.items() if k != "hooks")
                target["hooks"] = []
                hooks[event].append(target)
            have = set(h.get("command") for h in target["hooks"])
            for h in mine:
                if h.get("command") not in have:
                    target["hooks"].append(h)
                    have.add(h.get("command"))
                    kept.append("%s: %s" % (event, h.get("command")))
    return merged, kept


def main(argv):
    if len(argv) != 3:
        sys.stderr.write("usage: _wrap_merge_settings.py <framework settings.json> "
                         "<destination settings.json>\n")
        return 2
    ours = load(argv[1], "the framework's")
    if ours is None:
        sys.stderr.write("ERROR: the framework has no %s; nothing to register.\n" % argv[1])
        return 1
    merged, kept = merge(ours, load(argv[2], "the destination's"))
    os.makedirs(os.path.dirname(os.path.abspath(argv[2])), exist_ok=True)
    with open(argv[2], "w") as f:
        f.write(json.dumps(merged, indent=2) + "\n")
    n = sum(len(g.get("hooks") or []) for gs in merged.get("hooks", {}).values() for g in gs)
    print("  .claude/settings.json: %d hook registration(s); kept %d of the project's" % (n, len(kept)))
    for k in kept:
        print("      %s" % k)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
