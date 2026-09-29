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
OV_DATA = HERE / "harness_overview.yaml"
OV_TEMPLATE = HERE / "overview_template.html"
OV_OUT = HERE / "A2MC_Harness_Overview.html"

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
    """(check number, tool, gate pattern) for every numbered check that invokes a tool.

    Scan the hook IN LINE ORDER and attribute each invocation to the numbered header above it and
    the nearest gate above that invocation. Two earlier versions split the file on the numbered
    comments and searched each section as a blob, which is wrong three ways in this file: the
    numbered comments are NOT in ascending order, so a section runs to whichever number happens to
    come next; a 2600-character window cut four sections off before their gate line and reported
    them as UNGATED; and a checker merely discussed in a comment was attributed as if the check ran
    it. An invocation is therefore matched in its invocation form -- `"$ROOT/tools/x.py"` -- and the
    gate accepts both `grep -qE` and the bare `grep -E` inside a `[[ -n "$(...)" ]]` test, which is
    how checks 15 and 23 are written.

    Reporting a gated check as ungated is the one wrong answer this function must not give, because
    `harness_query.py --touches` turns it into "nothing governs this path".
    """
    # Join shell continuations FIRST, so every gate sits on one logical line and the `--name-only`
    # test below is exact. Both forms appear in this hook: a trailing backslash, and a pipeline whose
    # next line begins with `|`. Ten of the 28 gates are written the second way.
    logical = []
    for raw in HOOK.read_text(errors="replace").splitlines():
        if logical and (logical[-1].rstrip().endswith("\\") or raw.lstrip().startswith("|")):
            logical[-1] = logical[-1].rstrip().rstrip("\\") + " " + raw.strip()
        else:
            logical.append(raw)

    num = gate = ""
    out = []
    for line in logical:
        h = re.match(r"# \((\d+)\)", line)
        if h:
            num, gate = h.group(1), ""
            continue
        # Check 15 expresses its gate as a `sed` EXTRACTION of the site name rather than a grep, so
        # it looked unconditional -- the same false "nothing governs this path" the docstring warns
        # about, arriving by a second route. Take the sed's left-hand side and convert BRE to ERE.
        d = re.search(r"sed -n 's\|(\^[^|]+?)\|", line)
        if d and "--name-only" in line:
            gate = d.group(1).replace("\\(", "(").replace("\\)", ")").rstrip(".*")

        g = re.search(r"grep -q?E '([^']+)'", line)
        if g and "--name-only" in line:
            # A PATH gate, not any grep. Check 10 also greps the diff CONTENT for `^\+`, which is
            # not a statement about which paths the check governs; taking it would have said this
            # check fires on a file whose name starts with a plus.
            gate = g.group(1)
        for t in re.findall(r'\$ROOT/tools/([a-z_]+)\.py', line):
            if (num, t, gate) not in out:
                out.append((num, t, gate))       # a block may name its tool twice -- once in an
    return out                                   # `-f` existence test, once to invoke it


def build(data):
    nodes, edges, warn = {}, [], []
    art = {k: tuple(v) for k, v in (data.get("artifacts") or {}).items()}

    for name, (grp, gloss) in (data.get("extra_nodes") or {}).items():
        nodes[name] = (grp, gloss)

    seen_tools = set()
    for num, tool, gate in hook_checks():
        # EVERY hook-wired tool is a node. The earlier `startswith(("check_", "validate_"))` filter
        # dropped two of the 28 silently -- `config_graph` and `generate_skill_graph`, which enforce
        # as much as any `check_*` does -- so the graph understated the harness and the audit
        # computed its coverage over an incomplete set. An off-convention name is now WARNED rather
        # than used as grounds for exclusion.
        short = re.sub(r"^(check|validate)_", "", tool)
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
        # ANY tools/<name>.py, not only the check_/validate_ ones. The narrower pattern was the same
        # naming filter that hid two hook-wired tools from the node set, surviving in a second place:
        # a skill documenting `tools/harness_query.py` produced no edge, so that tool read as a check
        # nobody had described while two skills described it. The `short in nodes` guard below is what
        # keeps this from drawing an edge for every utility a skill happens to mention.
        for t in sorted(set(re.findall(r"tools/([a-z_]+)\.py", f.read_text(errors="replace")))):
            short = re.sub(r"^(check|validate)_", "", t)
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

def render(nodes, edges, template=None, heading=None, desc=None):
    """Heading and description are PARAMETERS, not defaults baked in here.

    They were hardcoded, so the overview's own heading was replaced before its generator could set
    it -- the token was already gone. A default that silently wins over an explicit value is the
    same defect twice."""
    template = template or TEMPLATE
    n = "\n".join(_emit([("id", k), ("g", v[0]), ("s", v[1])]) for k, v in sorted(nodes.items()))
    l = "\n".join(_emit([("source", a), ("target", b), ("t", t), ("l", x)])
                  for a, b, t, x in edges)
    if desc is None:
        desc = ("A directed network of %d nodes: what the A2MC agent writes, the checkers that "
                "assert it, and the hooks that refuse a commit. Solid arrows show enforcement "
                "routing. Dashed arrows show what a checker governs." % len(nodes))
    return (template.read_text().replace("__NODES__", n).replace("__LINKS__", l)
            .replace("__HEADING__", heading or "A2MC harness network")
            .replace("__DESC__", desc))


def counts():
    """The live numbers the overview's labels carry, so even a concept diagram cannot drift."""
    checks = len(re.findall(r"^# \(\d+\)", HOOK.read_text(errors="replace"), re.M))
    tools = sorted(set(re.findall(r"tools/([a-z_]+)\.py", HOOK.read_text(errors="replace"))))
    skills = sorted(SKILLS.glob("*/SKILL.md"))
    with_checker = [f for f in skills
                    if re.search(r"tools/(check|validate)_[a-z_]+\.py", f.read_text(errors="replace"))]
    mem = [x for x in (ROOT / ".claude_memory").glob("*.md") if x.name != "MEMORY.md"]
    return {"skills": len(skills), "checks": checks, "checkers": len(tools),
            "skills_with_checker": len(with_checker), "agenthooks": len(list(AGENT_HOOKS.glob("*.py"))),
            "memories": len(mem), "devlogs": len(list((ROOT / "memory" / "dev_logs_adapterkit").glob("*.md"))),
            "tools": len(list((ROOT / "tools").glob("*.py")))}


def build_overview(data, c):
    fill = lambda s: str(s).format(**c)
    nodes = {k: (v[0], fill(v[1])) for k, v in data["nodes"].items()}
    edges, warn = [], []
    for src, tgt, typ, lab in data["edges"]:
        if src in nodes and tgt in nodes:
            edges.append((src, tgt, typ, fill(lab)))
        else:
            warn.append("overview edge %s->%s dropped: endpoint missing" % (src, tgt))
    linked = {x for e in edges for x in e[:2]}
    warn += ["%s is an ISOLATED node" % n for n in sorted(set(nodes) - linked)]
    return nodes, edges, warn


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--check", action="store_true", help="exit 1 if the committed graph is stale")
    ap.add_argument("--overview", action="store_true",
                    help="build the concept-level overview instead of the full network")
    a = ap.parse_args()
    for f in ((OV_DATA, OV_TEMPLATE, HOOK) if a.overview else (DATA, TEMPLATE, HOOK)):
        if not f.is_file():
            sys.stderr.write("missing %s\n" % f)
            return 2
    out_path = OV_OUT if a.overview else OUT
    if a.overview:
        d = load_yaml(OV_DATA)
        nodes, edges, warn = build_overview(d, counts())
        out = render(nodes, edges, OV_TEMPLATE,
                     heading=d["heading"], desc=" ".join(d["desc"].split()))
    else:
        nodes, edges, warn = build(load_yaml(DATA))
        out = render(nodes, edges)
    for w in warn:
        print("  [warn] " + w)
    kinds = {}
    for g, in ((v[0],) for v in nodes.values()):
        kinds[g] = kinds.get(g, 0) + 1
    print("  %d node(s), %d edge(s)  %s" % (len(nodes), len(edges), kinds))
    if a.check:
        if out_path.is_file() and out_path.read_text(errors="replace") == out:
            print("  up to date")
            return 0
        print("  OUT OF DATE -- run: python3 tools/generate_harness_graph.py")
        return 1
    out_path.write_text(out)
    print("  wrote %s" % out_path.relative_to(ROOT))
    return 0


if __name__ == "__main__":
    sys.exit(main())
