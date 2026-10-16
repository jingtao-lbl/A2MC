#!/usr/bin/env python
"""Resolve which registered knowledge-base profile describes the model commit in use.

visibility: public
Author: Jing Tao with Claude on Perlmutter

A profile in `rag/milestones.json` is the knowledge base (wiki, curated seed, graph, vector index) for
one BASE commit of a model, the binary a calibration round is built on, plus any small fixes
PATCHED into it in place (`tools/kb_patch.py`). The milestone records the base as
`model_commit_built` and each patch in a `patches` list, oldest first. The commit the knowledge base
describes NOW is the last patch, or the base when there is none: `kb_commit()`.

Nothing that needs a profile should name one. A skill, a builder or a checker asks this module, which
matches the commit actually in use against the registry:

  adapter models (EcoSIM, PFLOTRAN, ATS)
    1. the commit: `--commit`, else what the MODEL'S OWN version detector reads from the checkout at
       `--model-path` / `$A2MC_MODEL_PATH` (`models/<model>/version.py`; this module never decides how
       a model is versioned, it only matches the answer against the registry);
    2. the milestone of that model whose base OR any patch IS that commit;
    3. otherwise an error that names the nearest milestone and how far the commit is from its
       knowledge base, with the two remedies: register the commits as a patch, or a new milestone.
  FATES / ELM
    delegated to `tools/rag_selector.py`, the existing version association by api epoch and sci tag.

`resolve_or_default()` is for callers that may legitimately run with no checkout at all (a golden-
query check on a fresh clone): with neither a commit nor a checkout it returns the model's single
non-legacy milestone and says that it did. It never guesses when a checkout IS given.

Run:
  python tools/kb_profile.py --model ecosim                 # the profile for $A2MC_MODEL_PATH's HEAD
  python tools/kb_profile.py --model ecosim --name-only     # just the name, for $(...)
  python tools/kb_profile.py --model ecosim --commit <sha>  # the profile for a given binary's commit
  python tools/kb_profile.py --model pflotran --list        # every registered profile: live/legacy, canonical
Exit 0 resolved; 1 no registered milestone covers the commit; 2 bad usage.
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from dataclasses import asdict, dataclass
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]


class NoMatch(Exception):
    """No registered milestone covers the commit in use. The message says what is nearest."""


@dataclass
class Resolution:
    profile: str
    model: str
    commit: str | None        # the commit that was matched (None for a default)
    via: str                  # 'base', 'patch', 'fates-selector' or 'default'
    kb_commit: str | None     # the commit the profile's knowledge base describes
    note: str = ""


def registry(repo: Path = REPO) -> dict:
    return json.loads((repo / "rag/milestones.json").read_text())["milestones"]


def model_of(ms: dict) -> str:
    """The model a milestone belongs to: adapter entries name it, FATES entries predate the key."""
    return ms.get("adapter") or "fates"


def base_commit(ms: dict) -> str | None:
    return ms.get("model_commit_built") or ms.get("fates_commit_built")


def kb_commit(ms: dict) -> str | None:
    """The commit the profile's knowledge base describes now: its last patch, else its base."""
    patches = ms.get("patches") or []
    return patches[-1]["commit"] if patches else base_commit(ms)


def chain(ms: dict) -> list[str]:
    """Every commit the profile covers: the base, then each patch in order."""
    return [c for c in [base_commit(ms)] + [p["commit"] for p in (ms.get("patches") or [])] if c]


def profiles(model: str, repo: Path = REPO) -> list[str]:
    return [k for k, v in registry(repo).items() if model_of(v) == model]


def _git(path, *args) -> str | None:
    r = subprocess.run(["git", "-C", str(path), *args], capture_output=True, text=True)
    return r.stdout.strip() if r.returncode == 0 else None


def full_sha(path, rev: str) -> str | None:
    return _git(path, "rev-parse", "--verify", "--quiet", f"{rev}^{{commit}}")


def detected_commit(model: str, model_path) -> str | None:
    """The commit a checkout is at, read by the MODEL'S OWN version detector
    (`models/<model>/version.py`, declared as the spec's `version_detector_class`). How a model's
    version is read is that model's business: one repository for EcoSIM and PFLOTRAN, the ATS source
    within Amanzi, ELM plus its FATES submodule for FATES. This module only matches the result
    against the registry."""
    sys.path.insert(0, str(REPO))
    sys.path.insert(0, str(REPO / "tools"))
    from validate_wiki_vs_source import load_spec  # noqa: E402  the shared ModelSpec loader
    try:
        spec = load_spec(model)
    except SystemExit as e:
        raise NoMatch(f"no ModelSpec for {model!r} (models/{model}/spec.py): {e}")
    det_cls = getattr(spec, "version_detector_class", None)
    if det_cls is None:
        raise NoMatch(f"models/{model}/spec.py declares no version_detector_class, so the commit in use "
                      f"cannot be read; pass --commit")
    try:
        version = det_cls().detect_from_checkout(Path(model_path))
    except (FileNotFoundError, OSError) as e:
        raise NoMatch(f"{model} version detector could not read {model_path}: {e}")
    return getattr(version, "commit_sha", None) or None


def _is_ancestor(path, a: str, b: str) -> bool:
    return subprocess.run(["git", "-C", str(path), "merge-base", "--is-ancestor", a, b],
                          capture_output=True).returncode == 0


def _distance(path, a: str, b: str) -> int | None:
    n = _git(path, "rev-list", "--count", f"{a}..{b}")
    return int(n) if n is not None and n.isdigit() else None


def _resolve_fates(model_path: Path) -> Resolution:
    sys.path.insert(0, str(REPO / "tools"))
    from model_version import ModelPathError, detect_model_version  # noqa: E402
    from rag_manifest import load_manifest  # noqa: E402
    from rag_selector import select_rag  # noqa: E402
    try:
        version = detect_model_version(model_path)
    except ModelPathError as e:
        raise NoMatch(str(e))
    sel = select_rag(version, load_manifest())
    if not sel.profile_name:
        raise NoMatch(sel.reason)
    ms = registry()[sel.profile_name]
    return Resolution(sel.profile_name, "fates", version.fates.commit, "fates-selector",
                      kb_commit(ms), f"mode {sel.mode}; {sel.reason}")


def resolve(model: str, commit: str | None = None, model_path=None, repo: Path = REPO) -> Resolution:
    """The registered profile covering the commit in use. Raises NoMatch with the nearest profile."""
    model_path = model_path or os.environ.get("A2MC_MODEL_PATH")
    if model == "fates":
        if not model_path:
            raise NoMatch("FATES resolution needs the E3SM checkout: --model-path or $A2MC_MODEL_PATH")
        return _resolve_fates(Path(model_path))
    if not model_path:
        raise NoMatch(f"no checkout to read: pass --model-path, or set $A2MC_MODEL_PATH to the {model} "
                      f"checkout that holds the commit in use")
    if commit:
        sha = full_sha(model_path, commit)
        if not sha:
            raise NoMatch(f"{commit} is not a commit in {model_path}")
    else:
        sha = detected_commit(model, model_path)
        if not sha:
            raise NoMatch(f"the {model} version detector found no commit in {model_path}")
    reg = registry(repo)
    mine = {k: v for k, v in reg.items() if model_of(v) == model}
    if not mine:
        raise NoMatch(f"no {model} milestone is registered in rag/milestones.json")
    hits = []
    for name, ms in mine.items():
        full = [full_sha(model_path, c) or c for c in chain(ms)]
        if sha in full:
            hits.append((name, ms, "base" if sha == full[0] else "patch"))
    if hits:
        hits.sort(key=lambda h: bool(h[1].get("legacy")))          # a live profile before a legacy one
        name, ms, via = hits[0]
        note = "legacy profile" if ms.get("legacy") else ""
        return Resolution(name, model, sha, via, kb_commit(ms), note)
    raise NoMatch(_nearest(model, sha, mine, model_path))


def _nearest(model: str, sha: str, mine: dict, model_path) -> str:
    rows = []
    for name, ms in mine.items():
        kb = full_sha(model_path, kb_commit(ms) or "") if kb_commit(ms) else None
        if not kb:
            continue
        if _is_ancestor(model_path, kb, sha):
            n = _distance(model_path, kb, sha)
            rows.append((n if n is not None else 10**9, f"{name}: the commit is {n} commit(s) AHEAD of its "
                         f"knowledge base ({kb[:8]})"))
        elif _is_ancestor(model_path, sha, kb):
            n = _distance(model_path, sha, kb)
            rows.append((n if n is not None else 10**9, f"{name}: the commit is {n} commit(s) BEHIND its "
                         f"knowledge base ({kb[:8]})"))
        else:
            mb = _git(model_path, "merge-base", kb, sha)
            n = (_distance(model_path, mb, sha) or 0) + (_distance(model_path, mb, kb) or 0) if mb else None
            rows.append((n if n is not None else 10**9, f"{name}: diverged from its knowledge base "
                         f"({kb[:8]}), {n} commit(s) apart through their merge base"))
    rows.sort()
    near = "\n  ".join(r[1] for r in rows) or "(no milestone commit is present in this checkout)"
    return (f"no registered {model} milestone covers {sha[:8]}. Nearest first:\n  {near}\n"
            f"Remedies: a small fix on top of a round's base binary is registered as a PATCH of that "
            f"profile (python tools/kb_patch.py plan/apply); a new base binary is a NEW milestone.")


def resolve_or_default(model: str, commit: str | None = None, model_path=None,
                       repo: Path = REPO) -> Resolution:
    """`resolve()`, except that with no commit and no checkout at all it returns the model's single
    non-legacy milestone and says so. A checkout that IS given and matches nothing still raises."""
    model_path = model_path or os.environ.get("A2MC_MODEL_PATH")
    if commit or (model_path and Path(model_path).exists()):
        return resolve(model, commit, model_path, repo)
    reg = registry(repo)
    live = [k for k, v in reg.items() if model_of(v) == model and not v.get("legacy")]
    if len(live) != 1:
        raise NoMatch(f"no checkout to match, and {len(live)} non-legacy {model} milestones to choose "
                      f"from ({', '.join(live) or 'none'}): pass --model-path or --commit")
    return Resolution(live[0], model, None, "default", kb_commit(reg[live[0]]),
                      "no checkout given: the only non-legacy milestone of this model")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--model", default=os.environ.get("A2MC_MODEL", "fates"))
    ap.add_argument("--commit", help="the commit in use, e.g. the one an archived binary was built from")
    ap.add_argument("--model-path", help="the model checkout (default $A2MC_MODEL_PATH)")
    ap.add_argument("--default-ok", action="store_true",
                    help="with no commit and no checkout, fall back to the single non-legacy milestone")
    ap.add_argument("--list", action="store_true", help="list every registered profile of the model")
    ap.add_argument("--name-only", action="store_true")
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args()
    if a.list:
        reg = registry()
        for name in profiles(a.model):
            ms = reg[name]
            marks = ["legacy" if ms.get("legacy") else "live"] + (["canonical"] if ms.get("canonical") else [])
            print(f"{name}\tbase {(base_commit(ms) or '')[:8]}\tkb {(kb_commit(ms) or '')[:8]}\t"
                  f"patches {len(ms.get('patches') or [])}\t" + "\t".join(marks))
        return 0
    try:
        fn = resolve_or_default if a.default_ok else resolve
        r = fn(a.model, a.commit, a.model_path)
    except NoMatch as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 1
    if a.name_only:
        print(r.profile)
    elif a.json:
        print(json.dumps(asdict(r), indent=1))
    else:
        print(f"{r.profile}  ({r.model}; matched {r.via}{' ' + r.commit[:8] if r.commit else ''}; "
              f"knowledge base at {(r.kb_commit or '')[:8]}){'; ' + r.note if r.note else ''}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
