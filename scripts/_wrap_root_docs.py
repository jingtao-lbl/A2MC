#!/usr/bin/env python3
"""Compose a calibrating project's root CLAUDE.md, README.md and AGENTS.md: its banner on top, the
framework's own document below.

visibility: public

When calibration is one part of a project, A2MC's own root documents are still the reference an
agent needs -- the operating contract, the 7-phase loop, the skill catalog -- so they are COPIED, and
the project writes its banner ABOVE them (create-project-agent Step 5b). A project with no
calibration does not come here: it hand-writes its own three documents.

A marker line separates the two halves. Everything above it is the project's and is never touched;
everything below it is replaced from the release on every refresh, like every other framework path.

  * marker present   -> keep the banner above it, replace what is below.
  * marker absent    -> the whole current file is the banner (a project created before this rule);
                        the reference is appended once.
  * marker absent but the framework document is already in the file -> REFUSE: appending would
                        duplicate it, and guessing where the banner ends could delete project text.

Usage:  _wrap_root_docs.py <framework root> <destination> [--dry-run]
Exit 1 on a refusal or a missing framework document.

Author: Jing Tao with Claude on Perlmutter.
"""
import os
import sys

DOCS = ("CLAUDE.md", "README.md", "AGENTS.md")
MARKER = ("<!-- A2MC FRAMEWORK REFERENCE BELOW. Everything under this line is replaced by "
          "scripts/wrap_for_project_agent.sh --refresh. Write the project banner ABOVE it. -->")


def first_heading(text):
    for line in text.splitlines():
        if line.startswith("#"):
            return line.strip()
    return None


def compose(banner_file, framework_text, doc, version):
    """Return the composed text, or raise ValueError on a refusal."""
    current = banner_file or ""
    if MARKER in current:
        banner = current.split(MARKER, 1)[0]
    else:
        head = first_heading(framework_text)
        if head and head in current.splitlines():
            raise ValueError("%s already contains the framework's document (%r) but no marker line; "
                             "add the marker under the project banner by hand, then re-run" % (doc, head))
        banner = current
    reference = ("---\n\n# A2MC reference — the framework this project uses\n\n"
                 "> Below is A2MC's own `%s` from the release (A2MC %s), kept because calibration is "
                 "part of this project. It is replaced on every `--refresh`: write the project's "
                 "banner above the marker line, never below it.\n\n" % (doc, version))
    return banner.rstrip() + "\n\n" + MARKER + "\n\n" + reference + framework_text.lstrip()


def main(argv):
    if len(argv) not in (3, 4):
        sys.stderr.write("usage: _wrap_root_docs.py <framework root> <destination> [--dry-run]\n")
        return 2
    src, dst, dry = argv[1], argv[2], len(argv) == 4 and argv[3] == "--dry-run"
    try:
        version = open(os.path.join(src, "VERSION")).read().strip() or "unknown"
    except OSError:
        version = "unknown"
    out = {}
    for doc in DOCS:
        fsrc = os.path.join(src, doc)
        if not os.path.isfile(fsrc):
            sys.stderr.write("ERROR: the framework has no %s to copy\n" % doc)
            return 1
        fdst = os.path.join(dst, doc)
        current = open(fdst).read() if os.path.isfile(fdst) else ""
        try:
            out[doc] = compose(current, open(fsrc).read(), doc, version)
        except ValueError as e:
            sys.stderr.write("ERROR: %s\n" % e)
            return 1
    for doc, text in out.items():            # write only after all three composed cleanly
        if dry:
            print("  [dry] %s: banner kept, framework reference refreshed" % doc)
            continue
        with open(os.path.join(dst, doc), "w") as f:
            f.write(text)
        print("  %s: banner kept above the marker; framework reference below it" % doc)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
