#!/usr/bin/env python
"""Check that every parameter a case TESTS is covered by the EcoSIM knowledge base, from source to wiki.

visibility: public
Author: Jing Tao with Claude on Perlmutter

WHY. A case samples parameters; diagnosis then asks the knowledge base how each one reaches the
scored outputs. On 2026-10-15 six of EcoSIM_Lusignan R2's 59 parameters had no graph node at all
(the profile's commit did not read them), sixteen more had a node and no route to any output, and
the wiki cited nothing at the binary the round runs. Each of those was silent: a missing node is
skipped, an unconnected node answers with nothing, and a stale citation still reads correctly.

WHAT IT CHECKS for every name in the given parameter list(s), against the active EcoSIM profile
(rag/milestones.json) and its knowledge-base commit (`tools/kb_profile.py kb_commit`: the base, or its
last in-place patch):
  S1  SOURCE  the name is read on the LIVE path at the commit (tools/ecosim_param_source_map.py;
              a read inside a routine nothing calls does not count), and its variable reaches
              physics. A name that is not read, or read but unused, must be declared in the seed
              (`parameters.<P>.inert: true` with a reason in `calibration_notes`).
  G1  GRAPH   the name is a Parameter node in the profile graph and carries `read_site`;
  G2  GRAPH   it has >=1 `controls` edge to a Mechanism -- unless the seed declares it `inert`,
              in which case it must carry NO `controls` edge and its node must carry `inert`;
  G3  GRAPH   an Output node is reachable from it in <=3 directed hops (P->O or P->M->O ...),
              never passing through a Category node (skipped for an inert parameter);
  K1  SEED    it has a `parameters.<P>` entry with a `code_location` whose citations name their
              routine and resolve at the commit (same rules as tools/check_ecosim_seed_citations.py);
  W1  WIKI    the profile wiki has a table row naming it whose `File.F90:NNN` citations all resolve
              and include at least one routine, named on the same row in backticks, that encloses
              a cited line;
  W2  WIKI    the generated pages reference/calibration_parameter_source_map.md,
              curated_output_source_map.md and curated_mechanism_index.md are current: each is
              byte-identical to what tools/ecosim_param_source_map.py produces now.
Exit 1 on any failure. --only S1,G1,... restricts the checks (e.g. before the wiki exists).

Run:
  python tools/check_ecosim_tested_params_in_kb.py \\
      --param-list use_cases/EcoSIM_Lusignan/parameters/ecosim_lusignan_param_list_r02b.csv [...]

The cb243228 re-anchor and the defects behind the dated notes above: `memory/dev_logs_adapterkit/20261015a_The_EcoSIM_Knowledge_Base_Moves_To_The_Binary_R2_Runs.md`.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from collections import deque
from pathlib import Path

import yaml

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
from tools.kb_profile import kb_commit  # noqa: E402
from tools.ecosim_param_source_map import (Source, active_ecosim_profile, build, file_reads,  # noqa: E402
                                           find_citations, markdown, param_names, resolve_citation,
                                           seed_param_names, annotate_from_seed, outputs_markdown,
                                           mechanisms_markdown)

SOURCE_MAP_PAGE = "reference/calibration_parameter_source_map.md"
OUTPUT_MAP_PAGE = "reference/curated_output_source_map.md"
MECH_INDEX_PAGE = "reference/curated_mechanism_index.md"
ALL_CHECKS = ("S1", "G1", "G2", "G3", "K1", "W1", "W2")


def graph_index(path: Path):
    g = json.loads(path.read_text())
    nodes = {n["id"]: n for n in g["nodes"]}
    out: dict = {}
    for e in g["links"]:
        out.setdefault(e["source"], []).append((e["relation_type"], e["target"]))
    return nodes, out


def reaches_output(nodes, out, start: str, max_hops: int = 3) -> str | None:
    q, seen = deque([(start, 0, [start])]), {start}
    while q:
        n, d, path = q.popleft()
        if d and nodes.get(n, {}).get("node_type") == "Output":
            return " -> ".join(p.split(":", 1)[-1] for p in path)
        if d == max_hops:
            continue
        for _rel, t in out.get(n, []):
            if t in seen or nodes.get(t, {}).get("node_type") == "Category":
                continue
            seen.add(t)
            q.append((t, d + 1, path + [t]))
    return None


def wiki_rows(wiki: Path) -> list[tuple[str, int, str]]:
    rows = []
    for md in sorted(wiki.rglob("*.md")):   # bounded root: the repo's own wiki directory
        for i, ln in enumerate(md.read_text(errors="replace").splitlines(), 1):
            if ln.lstrip().startswith("|") and ".F90:" in ln:
                rows.append((str(md.relative_to(wiki)), i, ln))
    return rows


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--param-list", action="append", default=[], required=True)
    ap.add_argument("--profile")
    ap.add_argument("--model-path", default=os.environ.get("A2MC_MODEL_PATH"))
    ap.add_argument("--only", help="comma-separated subset of " + ",".join(ALL_CHECKS))
    a = ap.parse_args()
    only = set((a.only or ",".join(ALL_CHECKS)).split(","))
    if not a.model_path:
        print("ERROR: no --model-path and $A2MC_MODEL_PATH is unset", file=sys.stderr)
        return 2
    if a.profile:
        prof, ms = a.profile, json.loads((REPO / "rag/milestones.json").read_text())["milestones"][a.profile]
    else:
        prof, ms = active_ecosim_profile(REPO, a.model_path)
    commit = kb_commit(ms)          # the base binary's commit, or its last in-place patch
    names = param_names(a.param_list)
    src = Source(a.model_path, commit)
    smap = build(a.model_path, commit, names)
    seed = yaml.safe_load((REPO / ms["curated_yaml_path"]).read_text())
    seedp = seed.get("parameters") or {}
    nodes, out = graph_index(REPO / "rag/graphs" / f"{prof}.json")
    wiki = REPO / ms["knowledge_base_dir"] / ms["model_wiki_subdir"]
    rows = wiki_rows(wiki) if wiki.is_dir() else []
    fails: dict = {}

    def fail(n, code, msg):
        fails.setdefault(n, []).append(f"{code} {msg}")

    for n in names:
        e = smap["params"][n]
        pid = f"parameter:{n}"
        if "S1" in only and e["status"] != "used" and not seedp.get(n, {}).get("inert"):
            fail(n, "S1", f"status `{e['status']}` at {smap['commit_short']} and the seed does not declare it "
                          f"`inert: true`")
        if "G1" in only:
            if pid not in nodes:
                fail(n, "G1", "no Parameter node in the graph")
            elif not nodes[pid].get("read_site") and e["status"] != "dead-read":
                fail(n, "G1", "node carries no `read_site`")
        inert = bool(seedp.get(n, {}).get("inert"))
        if inert and pid in nodes and not nodes[pid].get("inert"):
            fail(n, "G1", "the seed declares it inert but the graph node does not carry `inert`")
        if inert and any(r == "controls" for r, _t in out.get(pid, [])):
            fail(n, "G2", "declared inert but still has a `controls` edge: retrieval would present it as a live lever")
        if inert:
            pass
        elif "G2" in only and pid in nodes:
            if not any(r == "controls" and nodes.get(t, {}).get("node_type") == "Mechanism"
                       for r, t in out.get(pid, [])):
                fail(n, "G2", "no `controls` edge to a Mechanism")
        if "G3" in only and pid in nodes and not inert and not reaches_output(nodes, out, pid):
            fail(n, "G3", "no Output reachable within 3 directed hops (Category nodes excluded)")
        if "K1" in only:
            p = seedp.get(n)
            if not p:
                fail(n, "K1", "no `parameters` entry in the curated seed")
            else:
                cits = find_citations(str(p.get("code_location") or ""))
                if not any(c.get("routine") for c in cits):
                    fail(n, "K1", "`code_location` has no `File.F90:NNN (Routine)` citation")
                for c in cits:
                    for err in resolve_citation(src, c)["errors"]:
                        fail(n, "K1", err)
        if "W1" in only:
            mine = [r for r in rows if re.search(rf"\|\s*`?{re.escape(n)}`?\s*\|", r[2])]
            if not mine:
                fail(n, "W1", f"no wiki table row names `{n}` with a .F90 citation")
            else:
                good = False
                for page, ln, row in mine:
                    cits = find_citations(row)
                    named = {m.lower() for m in re.findall(r"`([A-Za-z_]\w*)`", row)}
                    row_ok = True
                    for c in cits:
                        r = resolve_citation(src, c)
                        if r["errors"]:
                            row_ok = False
                            fail(n, "W1", f"{page}:{ln}: " + "; ".join(r["errors"]))
                        elif r["routine_at"] and r["routine_at"].lower() in named:
                            good = good or row_ok
                if not good:
                    fail(n, "W1", "no wiki row cites a line together with the routine that encloses it")
    if "W2" in only:
        page = wiki / SOURCE_MAP_PAGE
        if not page.exists():
            fail("(wiki)", "W2", f"{SOURCE_MAP_PAGE} missing")
        else:
            head = page.read_text().split("Parameters covered:")[1].splitlines()[0]
            seeds = re.findall(r"curated seed `([^`]+)`", head)
            lists = re.findall(r"`([^`]+\.csv)`", head)
            extra = re.findall(r"`--param ([A-Za-z0-9_]+)`", head)
            names_ = [n for sd in seeds for n in seed_param_names(str(REPO / sd))]
            built = build(a.model_path, commit,
                          list(dict.fromkeys(names_ + param_names(lists) + extra)))
            for sd in seeds:
                annotate_from_seed(built, str(REPO / sd))
            want = markdown(built, [f"seed:{sd}" for sd in seeds] + lists + [f"--param {x}" for x in extra])
            if page.read_text() != want:
                fail("(wiki)", "W2", f"{SOURCE_MAP_PAGE} is stale: regenerate it with "
                                     "tools/ecosim_param_source_map.py")
            # the two companion pages, generated from the same seed at the same commit
            for rel_page, flag in ((OUTPUT_MAP_PAGE, "--outputs-markdown"), (MECH_INDEX_PAGE, "--mechanisms-markdown")):
                cp = wiki / rel_page
                if not cp.exists():
                    fail("(wiki)", "W2", f"{rel_page} missing: generate it with tools/ecosim_param_source_map.py {flag}")
                    continue
                for sd in seeds:
                    seed_d = yaml.safe_load((REPO / sd).read_text())
                    want_c = (outputs_markdown(src, seed_d, sd) if rel_page == OUTPUT_MAP_PAGE
                              else mechanisms_markdown(seed_d, sd, src.full[:8]))
                    if cp.read_text() != want_c:
                        fail("(wiki)", "W2", f"{rel_page} is stale: regenerate it with "
                                             f"tools/ecosim_param_source_map.py {flag}")

    n_fail = sum(len(v) for v in fails.values())
    print(f"EcoSIM KB coverage of {len(names)} tested parameters, profile {prof} at {smap['commit_short']}, "
          f"checks {','.join(c for c in ALL_CHECKS if c in only)}: "
          f"{len(names) - len([k for k in fails if k in names])} clean, {n_fail} failure(s)")
    for n, msgs in fails.items():
        for m in msgs:
            print(f"  {n:8s} {m}")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
