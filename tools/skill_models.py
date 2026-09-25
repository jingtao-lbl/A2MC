#!/usr/bin/env python3
"""Which models does a skill belong to, and which skills does a model list need?

visibility: public

WHY. `create-project-agent` delivers only the models a project uses: a project investigating one
mechanism in one model has no use for another model's knowledge base, RAG index, adapter or
run-workflow skill. Model-scoped PATHS derive themselves because each is named for its model --
`docs/<model>-knowledge-base/`, `models/<model>/`, `memory/<model>/`. **Skills do not**, so they
declare it in `modes.scope`, and this resolves that declaration.

A skill with no model in its scope is MODEL-AGNOSTIC and travels with every project. That is the
common case and the safe default: the failure to avoid is dropping a skill a project needed, not
carrying one it did not.

Usage:
    python3 tools/skill_models.py --list                    # every skill and its models
    python3 tools/skill_models.py --for ecosim              # skills to KEEP for a model list
    python3 tools/skill_models.py --drop-for ecosim         # skills to DROP (the complement)

Author: Jing Tao with Claude on Perlmutter.
"""
import argparse
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SKILLS = ROOT / ".claude" / "skills"

# The models a project can ask for. `elm` is here because a knowledge base carries that name even
# though no skill declares it today; leaving it out would make a future `--models elm` silently
# match nothing.
MODELS = ("fates", "elm", "ecosim", "pflotran", "ats")

_SCOPE = re.compile(r"^\s*scope:\s*\[([^\]]*)\]", re.M)
_FATES = re.compile(r"^\s*requires_fates:\s*true", re.M)


def skill_models(skill_md: Path) -> set:
    """The models a skill declares. Empty set means model-agnostic."""
    try:
        text = skill_md.read_text(errors="replace")
    except OSError:
        return set()
    m = _SCOPE.search(text)
    scope = {v.strip() for v in m.group(1).split(",")} if m else set()
    models = {s for s in scope if s in MODELS}
    # `requires_fates: true` is an older way of saying the same thing; honour it so a skill that
    # declares FATES only that way is not treated as agnostic and shipped everywhere.
    if _FATES.search(text):
        models.add("fates")
    return models


def all_skills() -> dict:
    return {p.parent.name: skill_models(p) for p in sorted(SKILLS.glob("*/SKILL.md"))}


def keep_for(wanted: set, skills: dict = None) -> list:
    """Skills a project using `wanted` should carry: agnostic ones, plus any that match."""
    skills = all_skills() if skills is None else skills
    return sorted(n for n, m in skills.items() if not m or (m & wanted))


def drop_for(wanted: set, skills: dict = None) -> list:
    """The complement: skills belonging only to models this project did not ask for."""
    skills = all_skills() if skills is None else skills
    return sorted(n for n, m in skills.items() if m and not (m & wanted))


def _parse_models(raw: str) -> set:
    wanted = {v.strip().lower() for v in raw.split(",") if v.strip()}
    unknown = wanted - set(MODELS)
    if unknown:
        sys.stderr.write("unknown model(s): %s — known: %s\n"
                         % (", ".join(sorted(unknown)), ", ".join(MODELS)))
        raise SystemExit(2)
    return wanted


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--list", action="store_true", help="every skill and the models it declares")
    g.add_argument("--for", dest="keep", metavar="MODELS", help="comma-separated; print skills to KEEP")
    g.add_argument("--drop-for", dest="drop", metavar="MODELS", help="comma-separated; print skills to DROP")
    a = ap.parse_args()

    skills = all_skills()
    if a.list:
        for n, m in skills.items():
            print("  %-32s %s" % (n, ",".join(sorted(m)) if m else "(model-agnostic)"))
        agnostic = sum(1 for m in skills.values() if not m)
        print("\n  %d skills: %d model-agnostic, %d model-scoped" % (len(skills), agnostic, len(skills) - agnostic))
        return 0

    wanted = _parse_models(a.keep or a.drop)
    names = keep_for(wanted, skills) if a.keep else drop_for(wanted, skills)
    for n in names:
        print(n)
    return 0


if __name__ == "__main__":
    sys.exit(main())
