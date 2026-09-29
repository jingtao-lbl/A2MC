#!/usr/bin/env python3
"""Ask the harness what governs a path, what depends on a thing, and where a contract lives.

visibility: public

WHY. `docs/skill_graph/A2MC_Harness_Network.html` draws skill -> checker -> hook for a human. An
agent cannot look at a picture. This is the same derivation as a QUERY, so the answer to "where else
does this contract live?" comes from the repository instead of from recall. A contract here usually
lives in several places, and editing only the instance in front of you is the failure this exists to
prevent. Account: `memory/dev_logs_adapterkit/20260925s_Asking_The_Harness_What_Governs_A_Path.md`.

It derives everything from `generate_harness_graph`, so there is exactly one definition of what the
harness IS and this cannot drift from the picture.

    harness_query.py --touches <path>     what governs this file, and which skill owns it
    harness_query.py --impact <name>      what depends on this checker/skill/artifact
    harness_query.py --contract <token>   every file that mentions a named field or rule
    harness_query.py --audit              structural gaps: enforcement with no procedure, and back

Python 3.6 compatible: the agent-side hook imports it and a bare `python3` here is 3.6.

Author: Jing Tao with Claude on Perlmutter.
"""
import argparse
import os
import re
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))


def _graph():
    """Nodes and edges from the graph generator -- one definition, never a second copy."""
    import generate_harness_graph as H
    try:
        import yaml
    except ImportError:
        return None, None, H
    data_path = os.path.join(ROOT, "docs", "skill_graph", "harness_data.yaml")
    with open(data_path) as fh:
        data = yaml.safe_load(fh)
    nodes, edges, _warn = H.build(data)
    return nodes, edges, H


def _gate_hits(path):
    """Every numbered check whose gate pattern matches `path`. The gate IS the checker's subject."""
    import generate_harness_graph as H
    out = []
    for num, tool, gate in H.hook_checks():
        if not gate or gate == "(always)":
            out.append((num, tool, "always"))
            continue
        try:
            if re.search(gate, path):
                out.append((num, tool, gate))
        except re.error:
            pass
    return out


def _skills_naming(tool_short):
    """Skills whose SKILL.md names this checker -- the procedure behind the enforcement."""
    d = os.path.join(ROOT, ".claude", "skills")
    hits = []
    for name in sorted(os.listdir(d)):
        f = os.path.join(d, name, "SKILL.md")
        if not os.path.isfile(f):
            continue
        with open(f, errors="replace") as fh:
            if re.search(r"tools/(check_|validate_)?" + re.escape(tool_short) + r"\.py", fh.read()):
                hits.append(name)
    return hits


def _owning_skill(path):
    """Which skill's own text points at this path -- a weak but useful ownership signal."""
    d = os.path.join(ROOT, ".claude", "skills")
    hits = []
    for name in sorted(os.listdir(d)):
        f = os.path.join(d, name, "SKILL.md")
        if not os.path.isfile(f):
            continue
        with open(f, errors="replace") as fh:
            body = fh.read()
        for frag in (path, os.path.dirname(path) + "/"):
            if frag and len(frag) > 6 and frag in body:
                hits.append(name)
                break
    return hits


def _reciprocal(shorts):
    """Curated reciprocal pairs touching any of these checkers.

    A reciprocal binding is the one property no single checker can assert: `check_log_conformance`
    requires a log to name the memory it wrote, `check_memory_bucket` requires that memory to name
    the log back, and satisfying either alone leaves a half-written pair that looks finished.
    """
    try:
        import yaml
    except ImportError:
        return []
    with open(os.path.join(ROOT, "docs", "skill_graph", "harness_data.yaml")) as fh:
        pairs = (yaml.safe_load(fh) or {}).get("reciprocal") or []
    out = []
    for a, b, _typ, lab in pairs:
        a2, b2 = re.sub(r"^(check|validate)_", "", a), re.sub(r"^(check|validate)_", "", b)
        if a2 in shorts or b2 in shorts:
            out.append((a2, b2, lab))
    return out


def cmd_touches(path):
    # `lstrip("./")` would strip a CHARACTER SET, turning `.claude/skills/...` into
    # `claude/skills/...` -- which matched no gate and reported a governed path as ungoverned.
    if path.startswith(ROOT + os.sep):
        path = path[len(ROOT) + 1:]
    while path.startswith("./"):
        path = path[2:]
    gated = [(n, t, g) for n, t, g in _gate_hits(path) if g != "always"]
    always = [(n, t) for n, t, g in _gate_hits(path) if g == "always"]
    print("PATH  %s" % path)
    if gated:
        print("\nGOVERNED BY -- these refuse the commit when the assertion fails:")
        for num, tool, gate in gated:
            skills = _skills_naming(tool.replace("check_", "").replace("validate_", ""))
            if not skills:
                via = "   procedure: NONE -- no skill describes this check"
            elif len(skills) > 6:
                via = "   procedure: %s, ... (%d skills)" % (", ".join(skills[:6]), len(skills))
            else:
                via = "   procedure: " + ", ".join(skills)
            print("  (%2s) tools/%s.py" % (num, tool))
            print(via)
    else:
        print("\nGOVERNED BY -- nothing gated on this path.")
    if always:
        print("\nALSO RUNS ON EVERY COMMIT: %s" % ", ".join("tools/%s.py" % t for _n, t in always))
    shorts = set(re.sub(r"^(check|validate)_", "", t) for _n, t, _g in _gate_hits(path))
    recip = _reciprocal(shorts)
    if recip:
        print("\nRECIPROCAL -- satisfying one half alone leaves a pair that LOOKS finished:")
        for a, b, lab in recip:
            print("  %s <-> %s   %s" % (a, b, lab))
    own = _owning_skill(path)
    if own:
        # A directory-level match is not ownership. Say which it is rather than overstating it.
        if len(own) > 6:
            print("\nNAMED BY %d SKILLS (a directory-level match, not ownership): %s, ..."
                  % (len(own), ", ".join(own[:6])))
        else:
            print("\nSKILLS THAT NAME THIS PATH: %s" % ", ".join(own))
    if re.match(r"^\.claude/skills/[^/]+/SKILL\.md$", path):
        print("\nA SKILL FILE ALSO HAS OFF-PATH READERS, and this is the trap:")
        print("  `visibility:`   read by BOTH sync legs to derive the private-skill exclusion,")
        print("                  and its registry rows must move in/out of the private blocks with it")
        print("  `modes.scope`   read by tools/skill_models.py to decide which projects receive it")
        print("  registry rows   4 places: CLAUDE.md, AGENTS.md, .claude/skills/README.md,")
        print("                  docs/a2mc_reference/skills_catalog.md  (parity is enforced)")
    return 0


def cmd_impact(name):
    nodes, edges, _H = _graph()
    if nodes is None:
        sys.stderr.write("pyyaml unavailable; use the project interpreter\n")
        return 2
    key = name.replace("tools/", "").replace(".py", "").replace("check_", "").replace("validate_", "")
    if key not in nodes:
        near = [n for n in nodes if key in n or n in key]
        print("unknown node %r%s" % (key, ("; did you mean: " + ", ".join(sorted(near)[:6])) if near else ""))
        return 1
    ins = [(s, t, l) for s, t, _ty, l in edges if t == key]
    outs = [(s, t, l) for s, t, _ty, l in edges if s == key]
    print("NODE  %s  (%s)\n  %s" % (key, nodes[key][0], nodes[key][1]))
    print("\nDEPENDS ON IT (%d) -- changing it affects these:" % len(ins))
    for s, _t, l in ins:
        print("  %-28s %s" % (s, l))
    print("\nIT DEPENDS ON (%d):" % len(outs))
    for _s, t, l in outs:
        print("  %-28s %s" % (t, l))
    return 0


def cmd_contract(token):
    """Every tracked file that mentions the token. Index-bounded, never a disk walk."""
    try:
        files = subprocess.check_output(["git", "-C", ROOT, "ls-files"]).decode().split("\n")
    except Exception:
        sys.stderr.write("not a git repository\n")
        return 2
    scope = ("tools/", "scripts/", ".githooks/", ".claude/", "docs/a2mc_reference/",
             "CLAUDE.md", "AGENTS.md", "README.md", "tests/")
    hits = []
    for f in files:
        if not f or not f.startswith(scope):
            continue
        p = os.path.join(ROOT, f)
        if not os.path.isfile(p):
            continue
        try:
            with open(p, errors="replace") as fh:
                n = fh.read().count(token)
        except OSError:
            continue
        if n:
            hits.append((n, f))
    print("CONTRACT  %r appears in %d tracked file(s)\n" % (token, len(hits)))
    for n, f in sorted(hits, key=lambda x: (-x[0], x[1])):
        print("  %3d  %s" % (n, f))
    if len(hits) > 1:
        print("\n  More than one place. Fix every one in ONE commit -- a piecemeal repair is how a")
        print("  five-file drift becomes five separate corrections.")
    return 0


BASELINE = os.path.join(ROOT, "docs", "skill_graph", "audit_baseline.json")


def audit_data():
    """The three structural gaps, as MEMBERSHIP. A count is the wrong unit: one checker gaining a
    skill while another loses one leaves the count identical and the harness changed."""
    nodes, edges, _H = _graph()
    if nodes is None:
        return None
    checkers = set(n for n, v in nodes.items() if v[0] in ("phase", "authoring"))
    skills_on_graph = set(n for n, v in nodes.items() if v[0] == "knowledge")
    arts = set(n for n, v in nodes.items() if v[0] == "meta")
    named = set(t for s, t, _ty, _l in edges if s in skills_on_graph and t in checkers)
    governed = set(t for s, t, _ty, _l in edges if s in checkers and t in arts)
    d = os.path.join(ROOT, ".claude", "skills")
    all_skills = set(x for x in os.listdir(d) if os.path.isfile(os.path.join(d, x, "SKILL.md")))
    return {
        "orphan_checks": sorted(checkers - named),
        "ungoverned_artifacts": sorted(arts - governed),
        "skills_without_checker": sorted(all_skills - skills_on_graph),
        "skills_total": len(all_skills),
    }


def cmd_audit(baseline=None):
    a = audit_data()
    if a is None:
        sys.stderr.write("pyyaml unavailable; use the project interpreter\n")
        return 2

    real = {}
    import generate_harness_graph as HG
    for _num, tool, _gate in HG.hook_checks():
        real[re.sub(r"^(check|validate)_", "", tool)] = "tools/%s.py" % tool

    if baseline == "update":
        import json
        with open(BASELINE, "w") as fh:
            json.dump(a, fh, indent=2, sort_keys=True)
            fh.write("\n")
        print("baseline written: %s" % os.path.relpath(BASELINE, ROOT))
        return 0

    if baseline == "check":
        # Report only what MOVED, and fail on a new gap. A standing audit that reprints the same
        # twelve names every time is one nobody reads by the third commit.
        import json
        try:
            with open(BASELINE) as fh:
                base = json.load(fh)
        except (OSError, ValueError):
            print("  harness audit: no baseline; run harness_query.py --audit --baseline update")
            return 0
        rc = 0
        for key, label in (("orphan_checks", "check with no skill describing it"),
                           ("ungoverned_artifacts", "artifact no checker governs")):
            new = sorted(set(a[key]) - set(base.get(key) or []))
            gone = sorted(set(base.get(key) or []) - set(a[key]))
            for n in new:
                print("  harness audit: NEW %s -- %s" % (label, real.get(n, n)))
                rc = 1
            for n in gone:
                print("  harness audit: resolved -- %s (refresh the baseline)" % real.get(n, n))
        if rc == 0:
            print("  harness audit: no new structural gap")
        return rc

    print("HARNESS AUDIT\n")
    print("  artifacts no checker governs            %d" % len(a["ungoverned_artifacts"]))
    for x in a["ungoverned_artifacts"]:
        print("      %s" % x)
    print("  ENFORCEMENT WITH NO PROCEDURE           %d" % len(a["orphan_checks"]))
    print("      a check nobody described is one you meet by tripping it")
    for c in a["orphan_checks"]:
        f = real.get(c, "tools/%s.py" % c)
        missing = "" if os.path.isfile(os.path.join(ROOT, f)) else "   <-- NOT ON DISK"
        print("      %s%s" % (f, missing))
    print("  skills with no hook-wired checker       %d of %d"
          % (len(a["skills_without_checker"]), a["skills_total"]))
    print("      not all need one; a procedure with no assertion is a habit")
    return 1 if a["ungoverned_artifacts"] else 0


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--touches", metavar="PATH")
    g.add_argument("--impact", metavar="NAME")
    g.add_argument("--contract", metavar="TOKEN")
    g.add_argument("--audit", action="store_true")
    ap.add_argument("--baseline", choices=["check", "update"],
                    help="with --audit: compare against (or rewrite) the committed baseline")
    a = ap.parse_args()
    if a.touches:
        return cmd_touches(a.touches)
    if a.impact:
        return cmd_impact(a.impact)
    if a.contract:
        return cmd_contract(a.contract)
    return cmd_audit(a.baseline)


if __name__ == "__main__":
    sys.exit(main())
