#!/usr/bin/env python3
"""A model's knowledge-base README names the model commit the knowledge base describes, and every update.

visibility: public

THE RULE. Every knowledge-base update records the commit it was made for, in
`<knowledge_base_dir>/README.md` (e.g. `docs/ecosim-knowledge-base/README.md`). The README carries two
sections this checker reads:

  * `## Current working version of the model`  must name every live (non-legacy) profile of the
                                                model and the commit its knowledge base describes
                                                now: the last patch, else the base (`kb_profile.kb_commit`)
  * `## Update history`                        must name every base commit and every patch commit of
                                                every registered profile of the model, legacy included

Both are checked against `rag/milestones.json`, so registering a patch or a new profile without
recording it fails. Commits are matched on their first 8 characters.

WHEN A README IS REQUIRED. With `--staged`, a commit that changes a model's knowledge base -- its
`knowledge_base_dir`, its curated seed (`models/<model>/curated_seed*.yaml`), a profile's graph,
metadata or vector index, or the model's entries in `rag/milestones.json` -- must stage that model's
README too, and the README must exist. In a full audit a model with no README is reported as
advisory, so a model whose knowledge base predates the rule is not failed until it is next updated.

SCOPE. Models whose milestones carry `knowledge_base_dir` (the adapter models). FATES milestones do
not: its knowledge base spans the ELM and FATES trees and is versioned by api epoch.

Exit 0 clean, 1 a violation (blocking in pre-commit check 34).

Usage:  python3 tools/check_kb_readme.py [--model <model>] [--staged]
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from tools.kb_profile import base_commit, kb_commit, model_of  # noqa: E402

CURRENT_RE = re.compile(r"^##\s+Current working version", re.I)
HISTORY_RE = re.compile(r"^##\s+Update history", re.I)


def section(text: str, heading: re.Pattern) -> str | None:
    """The body under the first `## ` heading matching `heading`, up to the next `## ` heading."""
    out, inside = [], False
    for line in text.splitlines():
        if line.startswith("## "):
            if inside:
                break
            inside = bool(heading.match(line))
            continue
        if inside:
            out.append(line)
    return "\n".join(out) if inside or out else None


def kb_models(milestones: dict) -> dict[str, dict]:
    """model -> {'dir': knowledge_base_dir, 'profiles': {name: entry}} for models that declare a dir."""
    models: dict[str, dict] = {}
    for name, ms in milestones.items():
        d = ms.get("knowledge_base_dir")
        if not d:
            continue
        m = models.setdefault(model_of(ms), {"dir": d, "profiles": {}})
        m["profiles"][name] = ms
    return models


def check_readme(model: str, info: dict, text: str) -> list[str]:
    """Content problems in one model's README text; [] when it is in step with the registry."""
    rel = info["dir"].rstrip("/") + "/README.md"
    errs = []
    current = section(text, CURRENT_RE)
    history = section(text, HISTORY_RE)
    if current is None:
        errs.append(f"{rel}: no '## Current working version of the model' section")
    if history is None:
        errs.append(f"{rel}: no '## Update history' section")
    for name, ms in sorted(info["profiles"].items()):
        if current is not None and not ms.get("legacy"):
            kb = (kb_commit(ms) or "")[:8]
            if name not in current:
                errs.append(f"{rel}: current-version section does not name the live profile {name}")
            if kb and kb not in current:
                errs.append(f"{rel}: current-version section does not name {kb}, the commit "
                            f"{name}'s knowledge base describes now")
        if history is not None:
            commits = [base_commit(ms)] + [p["commit"] for p in (ms.get("patches") or [])]
            for c in filter(None, commits):
                if c[:8] not in history:
                    kind = "base" if c == base_commit(ms) else "patch"
                    errs.append(f"{rel}: update history does not record {c[:8]} ({name} {kind})")
    return errs


def _git(*args: str) -> str:
    r = subprocess.run(["git", "-C", str(ROOT), *args], stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                       universal_newlines=True)
    return r.stdout if r.returncode == 0 else ""


def touched_models(staged: list[str], models: dict, old: dict, new: dict) -> set[str]:
    """Models whose knowledge base this commit changes."""
    hit = set()
    for model, info in models.items():
        prefixes = [info["dir"].rstrip("/") + "/", f"models/{model}/curated_seed"]
        for p in info["profiles"]:
            prefixes += [f"rag/graphs/{p}.json", f"rag/metadata/{p}.json", f"rag/chroma_db/{p}/"]
        readme = info["dir"].rstrip("/") + "/README.md"
        if any(f != readme and any(f.startswith(x) for x in prefixes) for f in staged):
            hit.add(model)
    for name in set(old) | set(new):
        if old.get(name) != new.get(name):
            ms = new.get(name) or old.get(name)
            if ms.get("knowledge_base_dir"):
                hit.add(model_of(ms))
    return hit


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--model", help="check one model only")
    ap.add_argument("--staged", action="store_true",
                    help="check the models this commit's staged changes touch, and require their README staged")
    ap.add_argument("--root", type=Path, default=ROOT, help=argparse.SUPPRESS)
    a = ap.parse_args(argv)

    root = a.root
    new = json.loads((root / "rag/milestones.json").read_text())["milestones"]
    models = kb_models(new)
    if a.model:
        models = {k: v for k, v in models.items() if k == a.model}

    errs, notes = [], []
    if a.staged:
        staged = _git("diff", "--cached", "--name-only", "--diff-filter=ACMRD").split()
        if not staged:
            return 0
        old_raw = _git("show", "HEAD:rag/milestones.json")
        old = json.loads(old_raw)["milestones"] if old_raw else {}
        idx_raw = _git("show", ":rag/milestones.json")
        new = json.loads(idx_raw)["milestones"] if idx_raw else new
        models = {k: v for k, v in kb_models(new).items() if k in models}
        for model in sorted(touched_models(staged, models, old, new)):
            readme = models[model]["dir"].rstrip("/") + "/README.md"
            if not (root / readme).is_file():
                errs.append(f"{readme}: missing; this commit changes the {model} knowledge base, "
                            f"so it must record the update there")
                continue
            if readme not in staged:
                errs.append(f"{readme}: not staged; this commit changes the {model} knowledge base, "
                            f"so add an update-history row (and refresh the current version if it moved)")
            errs += check_readme(model, models[model], _git("show", f":{readme}") or (root / readme).read_text())
    else:
        for model, info in sorted(models.items()):
            if not (root / info["dir"] / "README.md").is_file():
                notes.append(f"{info['dir']}/README.md: missing (advisory until the {model} knowledge "
                             f"base is next updated)")
                continue
            errs += check_readme(model, info, (root / info["dir"] / "README.md").read_text())

    for n in notes:
        print(f"ADVISORY: {n}")
    for e in errs:
        print(f"FAIL: {e}")
    if errs:
        print("Fix: record the update in the model's knowledge-base README "
              "(see docs/ecosim-knowledge-base/README.md, 'Recording an update').")
        return 1
    print("OK: knowledge-base README(s) in step with rag/milestones.json")
    return 0


if __name__ == "__main__":
    sys.exit(main())
