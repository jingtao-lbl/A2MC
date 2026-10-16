#!/usr/bin/env python
"""Check that every source citation in the EcoSIM curated seed RESOLVES at the profile's commit.

visibility: public
Author: Jing Tao with Claude on Perlmutter

EcoSIM-SPECIFIC BY DESIGN, the sibling of `tools/check_pflotran_seed_citations.py` (same reason:
each model's seed has its own citation conventions, and a generic `--model` flag would promise a
portability nobody has tested).

WHY. `tools/validate_curated_yaml.py` checks that seed NAMES resolve; nothing checked that its
`file:line` POINTERS do. They drift silently: on 2026-10-15 the seed's citations were all written
against `2dea74d9` while the model had moved 323 commits, and several were pseudo-paths such as
`f90src/Plant_bgc/photosynthesis_and_respiration` that name no file at all. A citation that does
not resolve is a claim nobody can audit, and one that resolves to the wrong routine is worse.

WHAT IT CHECKS, at the knowledge-base commit of the EcoSIM profile covering the commit in use
(tools/kb_profile.py: the milestone's base, or its last in-place patch):
  E1  every citation `[path/]File.F90:NNN[-MMM] (Routine)` names a file that exists at the commit
      (a bare basename must be unique), and its lines are in range;
  E2  a NAMED routine encloses the cited line(s) (walking backwards to the routine header);
  E3  every `parameters.<P>.code_location`, `mechanisms.<M>.code_reference` and
      `outputs.<O>.code_location` has at least one citation WITH a routine name (a Fortran submodule
      `module procedure` body counts as a routine);
  W1  (warning) a parameter citation whose lines (+-2) mention none of that parameter's Fortran
      variables, `associate` aliases or one-hop derived variables (two hops, from
      tools/ecosim_param_source_map.py) -- it resolves, but may point at the wrong code.
Exit 1 on any error (E*). Warnings never fail the run; print them with --verbose.

Run:  python tools/check_ecosim_seed_citations.py [--profile <name>] [--model-path $A2MC_MODEL_PATH] [-v]

The cb243228 re-anchor and the defects behind the dated notes above: `memory/dev_logs_adapterkit/20261015a_The_EcoSIM_Knowledge_Base_Moves_To_The_Binary_R2_Runs.md`.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path

import yaml

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
from tools.kb_profile import kb_commit  # noqa: E402
from tools.ecosim_param_source_map import (Source, active_ecosim_profile, assigned_lhs,  # noqa: E402
                                           file_reads,
                                           find_citations, resolve_citation, resolve_param,
                                           sites_of)


def expected_names(src: Source, reads: dict, name: str, cache: dict) -> set:
    if name not in cache:
        e = resolve_param(src, name, reads)
        names = set(e["vars"]) | set(e.get("derived", [])) | {name}
        names |= {s["var"] for s in e["sites"] if s.get("alias_of")}
        # one more hop: ZTYPI reaches every Arrhenius function through TempOffset_pft, which is
        # computed from a variable ZTYPI sets, so a correct citation of its physics names neither
        for d in e.get("derived", []):
            for s_ in sites_of(src, d):
                lhs = assigned_lhs(s_["text"])
                if lhs and s_["kind"] in ("use", "assign"):
                    names.add(lhs)
        cache[name] = names
    return cache[name]


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--profile", help="milestone name (default: the single non-legacy EcoSIM profile)")
    ap.add_argument("--model-path", default=os.environ.get("A2MC_MODEL_PATH"))
    ap.add_argument("--seed", help="override the seed path from the milestone")
    ap.add_argument("--commit", help="check at this commit instead of the profile's knowledge-base commit")
    ap.add_argument("-v", "--verbose", action="store_true")
    a = ap.parse_args()
    if not a.model_path:
        print("ERROR: no --model-path and $A2MC_MODEL_PATH is unset", file=sys.stderr)
        return 2
    if a.profile:
        ms = json.loads((REPO / "rag/milestones.json").read_text())["milestones"][a.profile]
        prof = a.profile
    else:
        prof, ms = active_ecosim_profile(REPO, a.model_path)
    src = Source(a.model_path, a.commit or kb_commit(ms))
    seed = yaml.safe_load((REPO / (a.seed or ms["curated_yaml_path"])).read_text())
    reads = file_reads(src)
    cache: dict = {}
    errors, warnings, n_cit = [], [], 0

    def check(where: str, text: str, need_routine: bool, expect: set | None):
        nonlocal n_cit
        cits = find_citations(text)
        if not cits:
            errors.append(f"E3 {where}: no `File.F90:NNN` citation in {text!r:.90}")
            return
        if need_routine and not any(c.get("routine") for c in cits):
            errors.append(f"E3 {where}: no citation names its routine, e.g. `File.F90:NNN (Routine)`")
        for c in cits:
            n_cit += 1
            r = resolve_citation(src, c, expect)
            errors.extend(f"E1/E2 {where}: {e}" for e in r["errors"])
            warnings.extend(f"W1 {where}: {w}" for w in r["warnings"])

    for name, p in (seed.get("parameters") or {}).items():
        if p.get("code_location"):
            check(f"parameters.{name}.code_location", str(p["code_location"]), True,
                  expected_names(src, reads, name, cache))
        g = p.get("guard") or {}
        if isinstance(g, dict) and g.get("dispatch"):
            for c in find_citations(str(g["dispatch"])):
                n_cit += 1
                r = resolve_citation(src, c)
                errors.extend(f"E1/E2 parameters.{name}.guard.dispatch: {e}" for e in r["errors"])
    for name, m in (seed.get("mechanisms") or {}).items():
        if m.get("code_reference"):
            check(f"mechanisms.{name}.code_reference", str(m["code_reference"]), True, None)
        else:
            errors.append(f"E3 mechanisms.{name}: no code_reference")
    for name, o in (seed.get("outputs") or {}).items():
        if o.get("code_location"):
            # An output cites the code that PRODUCES it, whose lines name model variables rather than the
            # tape name, so the W1 "mentions the variable" test does not apply: E1/E2 still do.
            check(f"outputs.{name}.code_location", str(o["code_location"]), True, None)

    print(f"EcoSIM seed citations, profile {prof} at {src.full[:8]}: {n_cit} citations checked, "
          f"{len(errors)} error(s), {len(warnings)} warning(s)")
    for e in errors:
        print("  " + e)
    if a.verbose:
        for w in warnings:
            print("  " + w)
    elif warnings:
        print(f"  ({len(warnings)} warnings; -v to list)")
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
