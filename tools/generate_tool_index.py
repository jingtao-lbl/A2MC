#!/usr/bin/env python
"""Generate the index of every script in `tools/` and `scripts/`, and name the ORPHANS.

Author: Jing Tao with Claude on Perlmutter

WHY THIS EXISTS. A2MC's capability surface is indexed asymmetrically, and the unindexed half is
where the agent keeps re-deriving work that already exists:

    memories   126   `.claude_memory/MEMORY.md`, ~2.5k words, LOADED EVERY SESSION
    skills      50   four registries + `check_skill_registry.py` + `check_skill_claims.py`
    tools      124   `docs/a2mc_reference/tools_reference.md` describes 2 of them

Measured on 2026-09-12: a session worked an EcoSIM case for hours without knowing that
`tools/validate_curated_yaml.py` existed or that it was ALREADY FAILING on that model.
`check_graph_coverage.py` and `validate_seed_coverage.py` were each found only because a skill
happened to name them -- `rebuild-rag` says of the latter that it was "previously named by NO
skill". Discovery by skill-mentions-tool is a chain that works only if you enter at the right skill.

**AND THE INDEX IMMEDIATELY CORRECTED ITS OWN AUTHOR.** The first draft of this docstring said the
validator was "named by no onboarding path". The generated `named by` column says
`skill:onboard-model`, `skill:wire-knowledge-graph` -- it IS named, in the onboarding skill, and it
was simply not run. That is a worse finding than an undiscoverable tool and **no index fixes it**;
what the index fixes is the other 18, which are named nowhere at all. Stating the limit here so the
tool is not oversold: being listed is not being read, and being read is not being run.

WHAT IT PRODUCES. `docs/a2mc_reference/tools_index.md`: one line per script -- its summary from its
own module docstring, whether it is a CLI or a library, and **which agent-facing document names
it**. A script named by nothing is flagged `ORPHAN`, and that list is the discoverability debt: it is
the set of tools the agent cannot find when it needs them, so each is a candidate either to be cited
from the skill that should own it or to be retired.

GENERATED, NEVER HAND-EDITED. `tools_reference.md` drifted to 2-of-124 precisely because it was
hand-maintained; an index that must be updated by hand is an index that goes stale silently. Run
with `--check` in CI or a pre-commit hook to fail when the committed file no longer matches the
tree.

NOT a replacement for `tools_reference.md`, which is a hand-written narrative reference (APIs,
worked usage) for a handful of tools. This is the complete one-line lookup; that is the deep dive.

Run:  python tools/generate_tool_index.py            # write the index
      python tools/generate_tool_index.py --check    # exit 1 if the committed index is stale
      python tools/generate_tool_index.py --orphans  # just the orphan list
"""
from __future__ import annotations

import argparse
import ast
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
OUT = REPO / "docs/a2mc_reference/tools_index.md"
SCAN = ("tools", "scripts")

# The agent-facing surfaces. A script named in ANY of these is discoverable; one named in none is
# an orphan. Deliberately excludes other tools and scripts: a tool that only another tool knows
# about is exactly the case this index exists to surface.
DOC_GLOBS = (
    ".claude/skills/*/SKILL.md",
    ".claude_memory/*.md",
    "docs/a2mc_reference/*.md",
    "CLAUDE.md", "AGENTS.md", "README.md", "TODO.md",
)

GROUPS = [
    ("check_",     "Checkers and gates"),
    ("validate_",  "Validators"),
    ("build_",     "Builders (RAG, indexes, cases)"),
    ("extract_",   "Extraction"),
    ("plot_",      "Plotting"),
    ("generate_",  "Generators"),
    ("submit_",    "Submission"),
    ("run_",       "Runners"),
    ("diagnose_",  "Diagnostics"),
    ("promote_",   "Knowledge promotion"),
    ("write_",     "Writers"),
    ("sync_",      "Sync"),
]


def summary_of(path: Path) -> str:
    """First meaningful line of the module docstring -- the author's own one-liner."""
    try:
        doc = ast.get_docstring(ast.parse(path.read_text(errors="replace")))
    except (SyntaxError, ValueError):
        return "_(unparseable)_"
    if not doc:
        return "_(no module docstring)_"
    for line in doc.splitlines():
        line = line.strip()
        if line:
            return re.sub(r"\s+", " ", line).rstrip(".")
    return "_(empty docstring)_"


def is_cli(path: Path) -> bool:
    txt = path.read_text(errors="replace")
    return "argparse" in txt or '__name__ == "__main__"' in txt or "__name__ == '__main__'" in txt


def namers(stem_file: str, corpus_by_doc: dict[str, str]) -> list[str]:
    """Which agent-facing documents name this script. Matches `tools/foo.py` AND a bare `foo.py`,
    because skills legitimately use both forms (measured: 17 path-qualified for one tool, bare
    names for the RAG builders)."""
    hits = []
    for label, txt in corpus_by_doc.items():
        if stem_file in txt:
            hits.append(label)
    return hits


def collect():
    corpus_by_doc: dict[str, str] = {}
    for g in DOC_GLOBS:
        for p in sorted(REPO.glob(g)):
            # THE OUTPUT MUST NOT BE PART OF THE INPUT. `docs/a2mc_reference/*.md` is in the corpus
            # and the index lands there, so on the second run every script was "named by"
            # tools_index.md and the orphan count fell 18 -> 0. A detector matching text the tool
            # itself wrote -- the third instance of that shape in one day, after a `pgrep -f`
            # self-match and an abort check that matched its own echoed namelist comment. Caught
            # here only because `--check` was negative-controlled instead of assumed.
            if p.resolve() == OUT.resolve():
                continue
            try:
                txt = p.read_text(errors="replace")
            except OSError:
                continue
            if g.startswith(".claude/skills"):
                label = f"skill:{p.parent.name}"
            elif g.startswith(".claude_memory"):
                label = f"memory:{p.stem}"
            else:
                label = p.name
            corpus_by_doc[label] = txt

    rows = []
    for d in SCAN:
        for p in sorted((REPO / d).glob("*.py")):
            if p.name == "__init__.py":
                continue
            rel = f"{d}/{p.name}"
            rows.append({
                "rel": rel, "dir": d, "name": p.name,
                "summary": summary_of(p),
                "cli": is_cli(p),
                "namers": namers(p.name, corpus_by_doc),
            })
    return rows


def render(rows) -> str:
    orphans = [r for r in rows if not r["namers"]]
    n_cli = sum(1 for r in rows if r["cli"])
    out = [
        "# A2MC Tool Index (GENERATED — do not hand-edit)",
        "",
        "**Regenerate:** `python tools/generate_tool_index.py` · **Verify:** `--check` (exit 1 if stale)",
        "",
        "Every script in `tools/` and `scripts/`, with its own module docstring's first line, and "
        "**which agent-facing document names it**. A script named by no skill, memory, or top-level "
        "doc is flagged **ORPHAN** — that is the discoverability debt, not a bug: each orphan is a "
        "candidate either to be cited from the skill that should own it, or to be retired.",
        "",
        "This is the complete one-line lookup. `tools_reference.md` is the hand-written narrative "
        "reference (APIs, worked usage) for a handful of them — the two are complementary.",
        "",
        f"**{len(rows)} scripts** ({n_cli} CLI, {len(rows) - n_cli} library) · "
        f"**{len(orphans)} orphans** ({100 * len(orphans) // max(1, len(rows))} %)",
        "",
        "---",
        "",
        "## Orphans — named by no skill, memory or top-level doc",
        "",
    ]
    if orphans:
        out += ["| script | summary |", "|---|---|"]
        out += [f"| `{r['rel']}` | {r['summary']} |" for r in orphans]
    else:
        out.append("_None — every script is named by at least one agent-facing document._")
    out += ["", "---", "", "## All scripts, by purpose", ""]

    used = set()
    for prefix, title in GROUPS:
        grp = [r for r in rows if r["name"].startswith(prefix)]
        if not grp:
            continue
        used |= {r["rel"] for r in grp}
        out += [f"### {title}", "", "| script | | summary | named by |", "|---|---|---|---|"]
        for r in grp:
            kind = "CLI" if r["cli"] else "lib"
            nm = ", ".join(f"`{x}`" for x in r["namers"][:3]) or "**ORPHAN**"
            if len(r["namers"]) > 3:
                nm += f" +{len(r['namers']) - 3}"
            out.append(f"| `{r['rel']}` | {kind} | {r['summary']} | {nm} |")
        out.append("")

    rest = [r for r in rows if r["rel"] not in used]
    if rest:
        out += ["### Other", "", "| script | | summary | named by |", "|---|---|---|---|"]
        for r in rest:
            kind = "CLI" if r["cli"] else "lib"
            nm = ", ".join(f"`{x}`" for x in r["namers"][:3]) or "**ORPHAN**"
            if len(r["namers"]) > 3:
                nm += f" +{len(r['namers']) - 3}"
            out.append(f"| `{r['rel']}` | {kind} | {r['summary']} | {nm} |")
        out.append("")
    return "\n".join(out) + "\n"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--check", action="store_true", help="exit 1 if the committed index is stale")
    ap.add_argument("--orphans", action="store_true", help="print only the orphan list")
    a = ap.parse_args()

    rows = collect()
    orphans = [r for r in rows if not r["namers"]]

    if a.orphans:
        print(f"{len(orphans)} orphan(s) of {len(rows)} script(s) — named by no skill, memory or top-level doc:")
        for r in orphans:
            print(f"  {r['rel']:52s} {r['summary'][:80]}")
        return 0

    new = render(rows)
    if a.check:
        old = OUT.read_text() if OUT.exists() else ""
        if old != new:
            print(f"STALE: {OUT.relative_to(REPO)} does not match the tree.")
            print("Regenerate with: python tools/generate_tool_index.py")
            return 1
        print(f"index up to date ({len(rows)} scripts, {len(orphans)} orphans)")
        return 0

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(new)
    print(f"wrote {OUT.relative_to(REPO)}: {len(rows)} scripts, {len(orphans)} orphans "
          f"({100 * len(orphans) // max(1, len(rows))} %)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
