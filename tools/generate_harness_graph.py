#!/usr/bin/env python3
"""Regenerate the harness network: what the agent writes, what governs it, what refuses a commit.

visibility: public

A2MC's discipline is not held by instructions. It is held by a chain: a SKILL says how a thing is
done, a CHECKER asserts the result, and a HOOK refuses the commit when the assertion fails. This
draws that chain from the repository rather than from anyone's memory of it.

DERIVED, so it cannot go stale:
  - the CHECKER nodes and the hook -> checker edges, from the numbered checks in .githooks/pre-commit
  - the ARTIFACT each checker governs, from the path pattern that gates it
  - the SKILL -> checker edges, from every SKILL.md that names a `tools/check_*.py`
  - the AGENT HOOK nodes, from .claude/hooks/

CURATED in docs/skill_graph/harness_data.yaml, because no parse yields it:
  - what a gate pattern MEANS (`^memory/(dev_logs|ana_logs)` is "a development log")
  - the glosses
  - the RECIPROCAL bindings, which are a property of two checkers agreeing rather than of either

A gate pattern with no mapping is REPORTED, not dropped silently: an unmapped gate is a checker
whose subject nobody has named, which is exactly the thing this graph exists to make visible.

Usage:
    python3 tools/generate_harness_graph.py [--check]

Author: Jing Tao with Claude on Perlmutter.
"""
import argparse
import html
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
HOOK = ROOT / ".githooks" / "pre-commit"
SKILLS = ROOT / ".claude" / "skills"
AGENT_HOOKS = ROOT / ".claude" / "hooks"
HERE = ROOT / "docs" / "skill_graph"
DATA = HERE / "harness_data.yaml"
TEMPLATE = HERE / "harness_template.html"
OUT = HERE / "A2MC_Harness_Network.html"

G_ART, G_SKILL, G_CHECK, G_GIT, G_AGENT = "meta", "knowledge", "phase", "calibration", "modeldev"
# A checker that verifies a link from BOTH ends gets its own group: neither half alone catches a
# pointer that resolves to a real file containing none of the claimed content.
G_RECIP = "authoring"


def load_yaml(p):
    try:
        import yaml
        return yaml.safe_load(p.read_text())
    except ImportError:
        sys.exit("pyyaml is needed for the curated half; use the project interpreter")


def hook_checks():
    """(check number, tool, gate pattern) for every numbered check that invokes a tool."""
    text = HOOK.read_text(errors="replace")
    parts = re.split(r"\n# \((\d+)\)", text)
    out = []
    for i in range(1, len(parts), 2):
        num, body = parts[i], parts[i + 1][:2600]
        tools = sorted(set(re.findall(r"tools/([a-z_]+)\.py", body)))
        gates = re.findall(r"grep -qE '([^']+)'", body)
        for t in tools:
            out.append((num, t, gates[0] if gates else ""))
    return out


def build(data):
    nodes, edges, warn = {}, [], []
    art = {k: tuple(v) for k, v in (data.get("artifacts") or {}).items()}

    for name, (grp, gloss) in (data.get("extra_nodes") or {}).items():
        nodes[name] = (grp, gloss)

    seen_tools = set()
    for num, tool, gate in hook_checks():
        if tool.startswith(("check_", "validate_")):
            short = tool.replace("check_", "").replace("validate_", "")
            nodes.setdefault(short, (G_CHECK, "Check (%s): %s" % (num, tool)))
            if tool not in seen_tools:
                edges.append(("pre-commit", short, "route", "check " + num))
                seen_tools.add(tool)
            if gate in art:
                a, gl = art[gate]
                nodes.setdefault(a, (G_ART, gl))
                edges.append((short, a, "support", "governs"))
            elif gate and gate != "(always)":
                warn.append("no artifact mapped for gate %r (check %s, %s)" % (gate[:46], num, tool))

    # skills that name a checker present on the graph
    for f in sorted(SKILLS.glob("*/SKILL.md")):
        for t in sorted(set(re.findall(r"tools/(check_[a-z_]+|validate_[a-z_]+)\.py",
                                       f.read_text(errors="replace")))):
            short = t.replace("check_", "").replace("validate_", "")
            if short in nodes:
                nodes.setdefault(f.parent.name, (G_SKILL, "Skill: %s" % f.parent.name))
                edges.append((f.parent.name, short, "route", "enforced by"))

    for name, gloss in (data.get("agent_hooks") or {}).items():
        if (AGENT_HOOKS / (name + ".py")).is_file():
            nodes[name] = (G_AGENT, gloss)
        else:
            warn.append("agent hook %r is in the data file but not on disk" % name)
    for src, tgt, typ, lab in (data.get("agent_hook_edges") or []):
        if src in nodes and tgt in nodes:
            edges.append((src, tgt, typ, lab))
        else:
            warn.append("agent-hook edge %s->%s dropped: endpoint missing" % (src, tgt))

    for a, b, typ, lab in (data.get("reciprocal") or []):
        a2 = a.replace("check_", "")
        b2 = b.replace("check_", "")
        if a2 in nodes and b2 in nodes:
            edges.append((a2, b2, typ, lab))
        else:
            warn.append("reciprocal %s<->%s dropped: endpoint missing" % (a, b))

    # promote the reciprocal participants into their own group, so the legend has no empty entry
    # and the distinction the graph exists to show is visible as a colour
    for a, b, _typ, _lab in (data.get("reciprocal") or []):
        for endp in (a.replace("check_", ""), b.replace("check_", "")):
            if endp in nodes and nodes[endp][0] == G_CHECK:
                nodes[endp] = (G_RECIP, nodes[endp][1] + " Verifies the link from both ends.")

    linked = {x for e in edges for x in e[:2]}
    warn += ["%s is an ISOLATED node" % n for n in sorted(set(nodes) - linked)]
    return nodes, edges, warn



def _emit(fields):
    """One node/link literal, with a guard that it cannot break the script.

    The data arrays live in HTML-escaped JavaScript, so every string is delimited by `&#x27;`.
    An apostrophe in a value escapes to that SAME sequence and terminates the string early,
    killing the whole script -- the page then renders blank with no error visible in the file.
    Values therefore use the typographic apostrophe, and this asserts the invariant rather than
    trusting it: a literal must contain exactly two delimiters per field.
    """
    parts = []
    for key, val in fields:
        v = html.escape(str(val), quote=True).replace("&#x27;", "&#8217;")
        # BOTH forms break the script: the escaped delimiter, and a raw quote that survives
        # unescaping in the browser. Checking only the first passes a neutered escaper.
        assert "&#x27;" not in v and "'" not in v, "quote leaked into a value: %r" % val
        parts.append("%s:&#x27;%s&#x27;" % (key, v))
    lit = "{%s}," % ",".join(parts)
    assert lit.count("&#x27;") == 2 * len(fields), "malformed literal: %s" % lit
    return "        " + lit

def render(nodes, edges):
    n = "\n".join(_emit([("id", k), ("g", v[0]), ("s", v[1])]) for k, v in sorted(nodes.items()))
    l = "\n".join(_emit([("source", a), ("target", b), ("t", t), ("l", x)])
                  for a, b, t, x in edges)
    desc = ("A directed network of %d nodes: what the A2MC agent writes, the checkers that "
            "assert it, and the hooks that refuse a commit. Solid arrows show enforcement "
            "routing. Dashed arrows show what a checker governs." % len(nodes))
    return (TEMPLATE.read_text().replace("__NODES__", n).replace("__LINKS__", l)
            .replace("__HEADING__", "A2MC harness network").replace("__DESC__", desc))


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--check", action="store_true", help="exit 1 if the committed graph is stale")
    a = ap.parse_args()
    for f in (DATA, TEMPLATE, HOOK):
        if not f.is_file():
            sys.stderr.write("missing %s\n" % f)
            return 2
    nodes, edges, warn = build(load_yaml(DATA))
    out = render(nodes, edges)
    for w in warn:
        print("  [warn] " + w)
    kinds = {}
    for g, in ((v[0],) for v in nodes.values()):
        kinds[g] = kinds.get(g, 0) + 1
    print("  %d node(s), %d edge(s)  %s" % (len(nodes), len(edges), kinds))
    if a.check:
        if OUT.is_file() and OUT.read_text(errors="replace") == out:
            print("  up to date")
            return 0
        print("  OUT OF DATE -- run: python3 tools/generate_harness_graph.py")
        return 1
    OUT.write_text(out)
    print("  wrote %s" % OUT.relative_to(ROOT))
    return 0


if __name__ == "__main__":
    sys.exit(main())
