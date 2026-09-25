#!/usr/bin/env python3
"""Regenerate the interactive skill-network graph from the skills on disk.

visibility: public

WHY A GENERATOR. The graph was a hand-built snapshot. By the time anyone checked it was eight
skills behind, with no way to tell without diffing it against the catalogue by hand. Adding a skill
now puts it on the graph; removing one takes it off.

WHAT IS DERIVED AND WHAT IS CURATED, because the split is the whole design:

  derived from .claude/skills/*/SKILL.md      the NODE SET, and each node's group (`category`)
  curated in docs/skill_graph/graph_data.yaml a one-line gloss per skill, the edges and their
                                              labels, and the deliberate exclusions

Edges cannot be derived. They carry meaning a parser cannot recover -- `a2mc-init -> onboard-model`
is labelled "new model", and no amount of reading either file yields that phrase. Node glosses are
editorial too: they are shorter and plainer than the frontmatter summary, which is written for a
different reader.

SILENCE MUST NOT DROP A NODE. A skill with no curated gloss still appears, using its frontmatter
summary and a warning. That is the difference between a graph that goes stale and one that gets
slightly scruffy: the failure this script exists to prevent is a missing skill, not an unpolished
sentence.

Usage:
    python3 tools/generate_skill_graph.py            # regenerate
    python3 tools/generate_skill_graph.py --check    # exit 1 if the committed file is out of date

Author: Jing Tao with Claude on Perlmutter.
"""
import argparse
import html
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SKILLS = ROOT / ".claude" / "skills"
HERE = ROOT / "docs" / "skill_graph"
DATA = HERE / "graph_data.yaml"
TEMPLATE = HERE / "template.html"
OUT = HERE / "A2MC_Skill_Network_Interactive.html"

# `category` frontmatter -> the group the graph draws. The graph's vocabulary predates the enum and
# differs in two places; mapping here rather than renaming either keeps both readable.
GROUP = {"meta": "meta", "phase": "phase", "calibration": "calibration",
         "kb-build": "knowledge", "knowledge": "knowledge",
         "model-dev": "modeldev", "modeldev": "modeldev", "authoring": "authoring"}


def frontmatter(p):
    """name/category/modes.summary, parsed without yaml so this runs on a bare python3."""
    try:
        block = p.read_text(errors="replace").split("---", 2)[1]
    except (OSError, IndexError):
        return {}
    out = {}
    m = re.search(r"^category:\s*(\S+)", block, re.M)
    if m:
        out["category"] = m.group(1).strip().strip('"\'')
    m = re.search(r"^\s+summary:\s*[\"']?(.*?)[\"']?\s*$", block, re.M)
    if m:
        out["summary"] = m.group(1)
    return out


def load_data():
    """The curated half. Hand-parsed for the same reason: no third-party import."""
    text = DATA.read_text(errors="replace")
    exclude, glosses, edges, section = {}, {}, [], None
    pending_key = None
    for raw in text.splitlines():
        if not raw.strip() or raw.lstrip().startswith("#"):
            continue
        if re.match(r"^(exclude|glosses|edges):\s*$", raw):
            section = raw.split(":")[0]
            continue
        line = raw.strip()
        if section == "edges" and line.startswith("- ["):
            parts = [x.strip().strip('"') for x in line[3:line.rindex("]")].split(",")]
            if len(parts) == 4:
                edges.append(parts)
        elif section in ("exclude", "glosses"):
            m = re.match(r"^([A-Za-z0-9_-]+):\s*(.*)$", line)
            if m:
                key, val = m.group(1), m.group(2).strip()
                if val in (">-", ">", "|"):
                    pending_key = key
                    (exclude if section == "exclude" else glosses)[key] = ""
                else:
                    pending_key = None
                    (exclude if section == "exclude" else glosses)[key] = val.strip('"')
            elif pending_key:
                tgt = exclude if section == "exclude" else glosses
                tgt[pending_key] = (tgt[pending_key] + " " + line).strip()
    return exclude, glosses, edges


def build():
    exclude, glosses, edges = load_data()
    disk = sorted(p.parent.name for p in SKILLS.glob("*/SKILL.md"))
    problems, warnings, notes = [], [], []

    kept = []
    for name in disk:
        if name in exclude:
            notes.append("excluded: %-24s %s" % (name, exclude[name]))
            continue
        fm = frontmatter(SKILLS / name / "SKILL.md")
        cat = fm.get("category", "")
        group = GROUP.get(cat)
        if not group:
            problems.append("%s: category %r has no group mapping" % (name, cat))
            continue
        gloss = glosses.get(name)
        if not gloss:
            gloss = (fm.get("summary") or "").split(";")[0].strip() or name
            gloss = gloss[:90].rstrip(" .,") + "."
            warnings.append("%s has no curated gloss; used its frontmatter summary" % name)
        kept.append((name, group, gloss))

    names = {n for n, _, _ in kept}
    for key in exclude:
        if key not in disk:
            warnings.append("exclusion %r names no skill on disk; remove it" % key)
    for key in glosses:
        if key not in disk:
            warnings.append("gloss %r names no skill on disk; remove it" % key)

    live = []
    for src, tgt, typ, label in edges:
        missing = [x for x in (src, tgt) if x not in names]
        if missing:
            warnings.append("edge %s->%s dropped: %s not on the graph" % (src, tgt, ", ".join(missing)))
            continue
        live.append((src, tgt, typ, label))

    linked = {x for e in live for x in e[:2]}
    for n in sorted(names - linked):
        warnings.append("%s is an ISOLATED node: no edge reaches it" % n)

    return kept, live, problems, warnings, notes


def render(kept, live):
    q = lambda s: html.escape(str(s), quote=True).replace("'", "&#x27;")
    nodes = "\n".join("        {id:&#x27;%s&#x27;,g:&#x27;%s&#x27;,s:&#x27;%s&#x27;}," % (q(i), q(g), q(s))
                      for i, g, s in kept)
    links = "\n".join("        {source:&#x27;%s&#x27;,target:&#x27;%s&#x27;,t:&#x27;%s&#x27;,l:&#x27;%s&#x27;}," % (
        q(a), q(b), q(t), q(l)) for a, b, t, l in live)
    return TEMPLATE.read_text().replace("__NODES__", nodes).replace("__LINKS__", links)


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--check", action="store_true",
                    help="do not write; exit 1 if the committed graph differs from a fresh build")
    a = ap.parse_args()

    for f in (DATA, TEMPLATE):
        if not f.is_file():
            sys.stderr.write("missing %s\n" % f)
            return 2

    kept, live, problems, warnings, notes = build()
    if problems:
        sys.stderr.write("\n".join("  ! " + p for p in problems) + "\n")
        return 2

    out = render(kept, live)
    for n in notes:
        print("  " + n)
    for w in warnings:
        print("  [warn] " + w)
    print("  %d node(s), %d edge(s)" % (len(kept), len(live)))

    if a.check:
        if OUT.is_file() and OUT.read_text(errors="replace") == out:
            print("  up to date")
            return 0
        print("  OUT OF DATE -- run: python3 tools/generate_skill_graph.py")
        return 1
    OUT.write_text(out)
    print("  wrote %s" % OUT.relative_to(ROOT))
    return 0


if __name__ == "__main__":
    sys.exit(main())
