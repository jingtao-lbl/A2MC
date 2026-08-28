#!/usr/bin/env python3
"""The skill graph — answer "when I invoke skill X, which skills are related, and did I miss one?"

THE QUESTION THIS ANSWERS, AND WHY THE EXISTING CHECK CANNOT. `check_skill_registry.py::
reciprocity_check` validates that every skill named in a `**Reciprocal skills**` bullet names the
declarer back. It is well built and hardcodes no skill name — but it can only walk edges a skill
CHOSE TO DECLARE. It cannot see an edge that should exist and never was declared, and that inverse
question is what every gap in the 2026-08-24 round-boundary audit turned out to be: nothing told
the agent that closing a round relates to `curate-knowledge`, that writing a round report relates
to `summarize-calibration-round`, or that a Phase-3 diagnosis relates to the site knowledge base.

So this reads the edges that are ALREADY THERE in prose — every skill reference in every SKILL.md,
whether or not anyone declared it reciprocal — and reports the shape:

  --skill X      every skill X references, and every skill that references X. The answer to
                 "what should I have loaded?", from the side that matters: the INBOUND list is
                 the one a skill's author never sees.
  --asymmetric   edges declared in one direction only. NOT errors -- most are legitimately
                 one-way (a phase skill routes to `plotting`; `plotting` should not name all
                 nine). It is a ranked place to LOOK, which is the thing that did not exist.
  --orphans      skills nothing references. Either genuinely standalone entry points, or
                 unreachable -- and the difference is worth knowing.
  --stats        coverage of the declared-reciprocity mechanism against the prose graph.

DELIBERATELY NOT A GATE. It exits 0 on everything except an unreadable tree. A one-way reference
is normal, so failing on one would produce a checker that must be silenced to be used — and the
repo already has the enforcement it needs for declared links. This is an instrument for the
question, not a rule.
"""
from __future__ import annotations
import argparse
import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
SKILLS = ROOT / ".claude" / "skills"

#: a reference to another skill: a markdown link to its SKILL.md, or a backticked bare name.
_LINK = re.compile(r"\]\(\.\./([a-z0-9-]+)/SKILL\.md\)")
_TICK = re.compile(r"`([a-z0-9-]+)`")
RECIPROCAL_MARK = "**Reciprocal skills**"


def skills_on_disk():
    out = {}
    if not SKILLS.is_dir():
        return out
    for d in sorted(SKILLS.iterdir()):
        f = d / "SKILL.md"
        if d.is_dir() and f.is_file():
            out[d.name] = f.read_text(errors="replace")
    return out


def build(disk):
    """{name: {"out": set, "declared": set}} — prose edges, and declared-reciprocal edges."""
    names = set(disk)
    g = {}
    for name, text in disk.items():
        refs = {m for m in _LINK.findall(text) if m in names and m != name}
        refs |= {m for m in _TICK.findall(text) if m in names and m != name}
        declared = set()
        lines = text.splitlines()
        for i, line in enumerate(lines):
            if RECIPROCAL_MARK not in line:
                continue
            block = [line]
            for nxt in lines[i + 1:]:
                if not nxt.strip() or nxt.lstrip().startswith(("-", "*", "#")):
                    break
                block.append(nxt)
            declared |= {m for m in _TICK.findall("\n".join(block)) if m in names and m != name}
        g[name] = {"out": refs, "declared": declared}
    return g


def inbound(g, target):
    return {n for n, e in g.items() if target in e["out"]}


def cmd_skill(g, name):
    if name not in g:
        print(f"no such skill: {name}. Known: {', '.join(sorted(g))}", file=sys.stderr)
        return 2
    out, inb = g[name]["out"], inbound(g, name)
    print(f"# {name}\n")
    print(f"REFERENCES ({len(out)}) — skills this one points at:")
    for s in sorted(out):
        mark = " [reciprocal]" if s in g[name]["declared"] else ""
        print(f"    -> {s}{mark}")
    print(f"\nREFERENCED BY ({len(inb)}) — the list a skill's own author never sees, and the one")
    print(f"that answers 'what should have loaded ME?':")
    for s in sorted(inb):
        print(f"    <- {s}" + ("" if name in g[s]["out"] else ""))
    only_in = inb - out
    if only_in:
        print(f"\nONE-WAY INBOUND ({len(only_in)}) — these name {name}, and {name} does not name")
        print(f"them back. Often fine; worth a look when the relationship is load-bearing:")
        for s in sorted(only_in):
            print(f"    <- {s}")
    return 0


def cmd_asymmetric(g, limit):
    pairs = []
    for a, e in g.items():
        for b in e["out"]:
            if a not in g[b]["out"]:
                pairs.append((a, b))
    # rank by how connected the un-naming side is: a hub that names many and is named back by few
    # is where a missing edge is most likely to matter.
    pairs.sort(key=lambda p: (-len(inbound(g, p[1])), p[0], p[1]))
    print(f"{len(pairs)} one-way reference(s). NOT errors — most are legitimately one-way.")
    print("Ranked by how heavily the referenced skill is depended on, since a missing back-edge")
    print("matters most where many skills route INTO one:\n")
    for a, b in pairs[:limit]:
        print(f"  {a}  ->  {b}      ({b} is referenced by {len(inbound(g, b))} skills)")
    if len(pairs) > limit:
        print(f"\n  ... {len(pairs) - limit} more (use --limit)")
    return 0


def cmd_orphans(g):
    orphans = [n for n in g if not inbound(g, n)]
    print(f"{len(orphans)} skill(s) that NOTHING references.\n")
    print("Either a standalone entry point a human invokes directly, or unreachable from any")
    print("other skill — and the difference is the point of asking:\n")
    for n in sorted(orphans):
        print(f"  {n}   (references {len(g[n]['out'])} skills itself)")
    return 0


def cmd_stats(g):
    declarers = [n for n, e in g.items() if e["declared"]]
    edges = sum(len(e["out"]) for e in g.values())
    two_way = sum(1 for a, e in g.items() for b in e["out"] if a in g[b]["out"])
    print(f"skills                     : {len(g)}")
    print(f"prose reference edges      : {edges}")
    print(f"  of which two-way         : {two_way}  ({100*two_way/edges:.0f}%)")
    print(f"declaring **Reciprocal**   : {len(declarers)}  ({100*len(declarers)/len(g):.0f}% of skills)")
    print(f"    {', '.join(sorted(declarers))}")
    print(f"\nThe declared mechanism is ENFORCED (check_skill_registry::reciprocity_check); the")
    print(f"prose graph above is not, and is not meant to be. The gap between the two numbers is")
    print(f"how much of the real structure the enforced check can currently see.")
    return 0


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--skill", help="show one skill's neighbours, both directions")
    ap.add_argument("--asymmetric", action="store_true", help="one-way references, ranked")
    ap.add_argument("--orphans", action="store_true", help="skills nothing references")
    ap.add_argument("--stats", action="store_true", help="graph + reciprocity coverage")
    ap.add_argument("--limit", type=int, default=25)
    a = ap.parse_args()

    disk = skills_on_disk()
    if not disk:
        print(f"no skills found under {SKILLS}", file=sys.stderr)
        return 2
    g = build(disk)
    if a.skill:
        return cmd_skill(g, a.skill)
    if a.asymmetric:
        return cmd_asymmetric(g, a.limit)
    if a.orphans:
        return cmd_orphans(g)
    return cmd_stats(g)


if __name__ == "__main__":
    sys.exit(main())
