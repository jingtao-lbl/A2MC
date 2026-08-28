#!/usr/bin/env python3
"""Scaffold a new use case directory from use_cases/TEMPLATE (or an existing case).

Replaces the inline bash recipe that `onboard-case` Step 4 used to carry. That recipe
silently produced an EMPTY config/ and reported success on every model, because
``${MODEL,,}`` is bash 4 syntax and macOS ships bash 3.2 (dev log 20260802g). A recipe
in prose cannot be tested; this can.

Naming is ``use_cases/<Prefix>_<Case>/``, matching EcoSIM_BioCON and PFLOTRAN_miniLEO.
The prefix is the model's ``ModelSpec.display_name`` (EcoSIM, PFLOTRAN, ATS); FATES has
no adapter package (it is A2MC's built-in default path) so its prefix is declared below.

NEVER overwrites. There is deliberately no --force: an existing case holds round records,
phase logs and results, and is the longest-lived part of the work. Delete it yourself if
you really mean to.

Usage:
    python tools/create_use_case.py --list
    python tools/create_use_case.py --model ecosim --case BioCON --dry-run
    python tools/create_use_case.py --model ecosim --case BioCON
    python tools/create_use_case.py --model fates --case Kougarok --seed Kougarok

Exit 0 = created (or dry-run OK); 1 = refused, with the reason on stderr.
Pairs with the `onboard-case` skill, which calls this and then fills what it writes.
Author: Jing Tao with Claude.
"""
from __future__ import annotations

import argparse
import importlib
import re
import shutil
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))   # import models.* from the repo root

# Models with no adapter package under models/. FATES is A2MC's built-in default path
# (registry.py defaults A2MC_MODEL to "fates"), so it has no ModelSpec to read a
# display_name from. NOTE: "FATES" not "ELM-FATES" is deliberate and provisional -- FATES
# also runs under CESM/CTSM, not only ELM, so the right prefix is an open question the PI
# deferred on 2026-08-03. Changing it later is a one-line edit here.
# FATES is not a host model -- it runs under ELM, CLM/CTSM and others -- so the case-folder
# prefix names the PAIRING, matching `use_cases/ELM-FATES_Kougarok` and the `ELM-FATES` example
# in `models/base.py`'s own `display_name` docstring. Corrected 2026-08-26: the PI renamed
# `use_cases/FATES_template/` -> `use_cases/ELM-FATES_template/` and this map still said FATES,
# so `case_prefix("fates")` resolved to a directory that no longer exists.
BUILTIN_PREFIXES = {"fates": "ELM-FATES"}

SAFE_COMPONENT = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")

# What makes a file in TEMPLATE/config a template rather than a real config. Matched on
# these exact suffixes, NOT on a "*_template_*" glob: a case may legitimately be named
# "template", and the glob then deletes the config it just created.
TEMPLATE_SUFFIXES = ("_template_config.sh", "_template_calibration_rounds.yaml")

# README.md and validation/targets.yaml have the same "copied byte-identical for every
# model" problem config.sh/calibration_rounds.yaml had -- FATES's PFT<id>_<vartype> framing
# is actively wrong for an adapter model. Same suffix-matching swap, one level outside
# config/: (seed suffix, dir relative to the case root, generic filename it replaces).
# Unlike config.sh (a hard REFUSED error if missing -- a case cannot run without one), a
# missing per-model seed here is soft: the generic TEMPLATE copy is left in place, same as
# calibration_rounds.yaml's existing optional behavior.
EXTRA_TEMPLATE_FILES = (
    ("_template_readme.md", ".", "README.md"),
    ("_template_targets.yaml", "validation", "targets.yaml"),
)


def repo_root() -> Path:
    try:
        out = subprocess.run(
            ["git", "rev-parse", "--show-toplevel"],
            capture_output=True, text=True, check=True,
        ).stdout.strip()
        return Path(out)
    except (subprocess.CalledProcessError, FileNotFoundError):
        return Path(__file__).resolve().parent.parent


def _read_prefix(model: str) -> str | None:
    """The model's display_name, or None if it is not a calibratable model.

    Pure: never raises and never calls known_models(). Those two calling each other is
    how the first version of this file recursed until the traceback was 750 KB.
    """
    if model in BUILTIN_PREFIXES:
        return BUILTIN_PREFIXES[model]
    try:
        mod = importlib.import_module(f"models.{model}.spec")
    except ImportError:
        return None
    specs = [v for v in vars(mod).values()
             if type(v).__name__ == "ModelSpec" and getattr(v, "display_name", "")]
    if not specs:
        return None
    prefix = specs[0].display_name
    return prefix if SAFE_COMPONENT.match(prefix) else None


def known_models() -> list[str]:
    """Model keys that could have a case: built-ins + every adapter with a usable spec."""
    root = repo_root()
    out = set(BUILTIN_PREFIXES)
    for d in sorted((root / "models").glob("*/spec.py")):
        key = d.parent.name
        if not key.startswith("_") and _read_prefix(key):
            out.add(key)      # skips the surrogate module, which declares no ModelSpec
    return sorted(out)


def case_prefix(model: str) -> str:
    """Resolve a model key to its use-case directory prefix, or raise ValueError.

    Reads ModelSpec.display_name so the prefix cannot drift from the adapter's identity.
    """
    prefix = _read_prefix(model)
    if prefix is None:
        raise ValueError(
            f"unknown model {model!r} -- no usable models/{model}/spec.py and not built-in. "
            f"Run the `onboard-model` skill first. Known: {', '.join(known_models())}"
        )
    return prefix


def template_pair(root: Path, model: str) -> tuple[Path, Path]:
    """This model's (config, calibration_rounds) template paths inside TEMPLATE/config."""
    cfg = root / "use_cases/TEMPLATE/config" / f"{model}_template_config.sh"
    yml = root / "use_cases/TEMPLATE/config" / f"{model}_template_calibration_rounds.yaml"
    return cfg, yml


def _swap_extra_template_file(dest: Path, model: str, seed_suffix: str,
                               subdir: str, dest_name: str) -> None:
    """Swap this model's README/targets seed into place, deleting the other models' seeds.

    Soft-optional: if this model has no authored seed for this file, the generic copy that
    `shutil.copytree` already placed is left as-is (mirrors calibration_rounds.yaml's
    existing soft-optional behavior -- only config.sh is a hard requirement).
    """
    d = dest if subdir == "." else dest / subdir
    seed_name = f"{model}{seed_suffix}"
    for other in sorted(d.glob(f"*{seed_suffix}")):
        if other.name != seed_name:
            other.unlink()
    seed_path = d / seed_name
    if seed_path.is_file():
        generic = d / dest_name
        if generic.is_file():
            generic.unlink()
        seed_path.rename(generic)


def resolve_seed(root: Path, model: str, seed: str | None) -> str:
    """Which directory under use_cases/ to copy. ARCHITECTURE B (PI, 2026-08-17).

    An explicit --seed always wins. Otherwise prefer the model's OWN authored template
    directory `use_cases/<Prefix>_template/`, falling back to the shared `TEMPLATE/` for a
    model that has not authored one yet.

    Under B those per-model dirs are AUTHORED SOURCE, not generated snapshots. That is the
    reversal: previously they were regenerated from TEMPLATE/ and a drift test enforced it,
    so a per-model file (an EcoSIM run namelist, say) could not live in one -- the next
    regeneration deleted it. Adding a per-model file is now just adding a file, with no
    `EXTRA_TEMPLATE_FILES` row and no suffix convention. Audit of both options:
    `memory/dev_logs_adapterkit/20260816a`.
    """
    if seed:
        return seed
    own = f"{case_prefix(model)}_template"
    return own if (root / "use_cases" / own).is_dir() else "TEMPLATE"


def create(model: str, case: str, seed: str | None = None, dry_run: bool = False,
           root: Path | None = None) -> Path:
    root = root or repo_root()
    if not (root / "a2mc_config.sh").is_file():
        raise SystemExit(f"not an A2MC clone: {root}")
    if not SAFE_COMPONENT.match(case):
        raise SystemExit(
            f"case name {case!r} is not a usable directory component "
            f"(needs [A-Za-z0-9][A-Za-z0-9._-]*, no spaces or slashes)"
        )

    prefix = case_prefix(model)
    seed = resolve_seed(root, model, seed)
    dest = root / "use_cases" / f"{prefix}_{case}"
    src = root / "use_cases" / seed

    # --- preconditions -------------------------------------------------------------
    if dest.exists():
        raise SystemExit(
            f"REFUSED: {dest.relative_to(root)} already exists.\n"
            f"  An existing case holds round records, phase logs and results. This tool "
            f"never overwrites one.\n"
            f"  Pick another case name, or remove that directory yourself first."
        )
    if not src.is_dir():
        raise SystemExit(f"seed {src.relative_to(root)} does not exist")

    from_template = seed == "TEMPLATE"          # the SHARED dir -> per-model file surgery
    from_own_template = seed == f"{prefix}_template"   # this model's AUTHORED dir -> verbatim
    tpl_cfg, tpl_yml = template_pair(root, model)
    if from_template and not tpl_cfg.is_file():
        raise SystemExit(
            f"REFUSED: no case template for {prefix} "
            f"(expected {tpl_cfg.relative_to(root)}).\n"
            f"  Authoring it is `onboard-model` step 14. Run that skill for this model first."
        )

    cfg_name = f"{model}_{case.lower()}_config.sh"
    if dry_run:
        print(f"[dry-run] {src.relative_to(root)} -> {dest.relative_to(root)}")
        print(f"[dry-run]   config/{cfg_name}")
        print(f"[dry-run]   config/calibration_rounds.yaml")
        return dest

    # --- copy ----------------------------------------------------------------------
    # Filter editor/interpreter droppings out of the seed. They are gitignored, so they never
    # reach git -- but copytree still places them in every scaffolded case, where a stale
    # `validation/.ipynb_checkpoints/targets-checkpoint.yaml` sits beside the real targets.yaml
    # and reads as a second source of truth. Found 2026-08-26 scaffolding EcoSIM_Kougarok, which
    # inherited three such dirs from EcoSIM_template.
    shutil.copytree(src, dest, ignore=shutil.ignore_patterns(
        ".ipynb_checkpoints", "__pycache__", "*.pyc", ".DS_Store"))
    for junk in dest.rglob(".DS_Store"):
        junk.unlink()

    cfg_dest = dest / "config" / cfg_name
    if from_template:
        # Drop the OTHER models' templates BEFORE renaming ours, so the cleanup cannot
        # reach a file that renaming is about to create.
        keep = {tpl_cfg.name, tpl_yml.name}
        for other in sorted((dest / "config").iterdir()):
            if other.name not in keep and other.name.endswith(TEMPLATE_SUFFIXES):
                other.unlink()
        (dest / "config" / tpl_cfg.name).rename(cfg_dest)
        if tpl_yml.is_file():
            (dest / "config" / tpl_yml.name).rename(dest / "config/calibration_rounds.yaml")
        for seed_suffix, subdir, dest_name in EXTRA_TEMPLATE_FILES:
            _swap_extra_template_file(dest, model, seed_suffix, subdir, dest_name)
    else:
        # Seeded from a filled case (e.g. Kougarok): rename its config, keep its values.
        existing = [p for p in (dest / "config").glob("*_config.sh")]
        if len(existing) != 1:
            shutil.rmtree(dest)
            raise SystemExit(
                f"REFUSED: seed {seed} has {len(existing)} *_config.sh files; expected exactly 1"
            )
        existing[0].rename(cfg_dest)

    # --- postcondition: the bug that motivated this script --------------------------
    if not cfg_dest.is_file():
        shutil.rmtree(dest)
        raise SystemExit(f"SCAFFOLD FAILED: {cfg_name} was not produced; {dest} removed")
    leftovers = sorted(p.name for p in (dest / "config").iterdir()
                       if p != cfg_dest and p.name.endswith(TEMPLATE_SUFFIXES))
    for seed_suffix, subdir, _dest_name in EXTRA_TEMPLATE_FILES:
        d = dest if subdir == "." else dest / subdir
        if d.is_dir():
            leftovers += sorted(f"{subdir}/{p.name}" if subdir != "." else p.name
                                for p in d.glob(f"*{seed_suffix}"))
    if leftovers:
        shutil.rmtree(dest)
        raise SystemExit(f"SCAFFOLD FAILED: templates left behind: {leftovers}; {dest} removed")

    rel = dest.relative_to(root)
    print(f"created {rel}  (seed: {seed})")
    for p in sorted((dest / "config").iterdir()):
        print(f"  config/{p.name}")
    print("\nnext:")
    print(f"  1. replace every <PLACEHOLDER> in {rel}/config/{cfg_name}")
    if from_template or from_own_template:
        print(f"  2. write {rel}/research_plan.md and get it confirmed (GATE 1)")
        print(f"  3. build the parameter list (GATE 2), then generate_calibration_rounds.py")
    else:
        print(f"  2. the values are {seed}'s -- edit them for this site, do not assume they transfer")
    print(f"  -> the `onboard-case` skill drives all of it")
    return dest


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--model", help="model key, e.g. fates / ecosim / pflotran / ats")
    ap.add_argument("--case", help="site / project / scenario name, e.g. BioCON")
    ap.add_argument("--seed", default=None,
                    help="directory under use_cases/ to copy "
                         "(default: this model's <Prefix>_template/, else TEMPLATE)")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--list", action="store_true",
                    help="list models, their case prefix, and whether a template exists")
    args = ap.parse_args()

    if args.list:
        root = repo_root()
        print(f"{'model':12s} {'prefix':12s} template")
        for m in known_models():
            # Report the seed that `create` would ACTUALLY use, not just the shared-TEMPLATE
            # half. Before 2026-08-26 this asked only `template_pair(...).is_file()`, so ATS
            # -- which scaffolds perfectly from its own authored `ATS_template/` -- was listed
            # as "NO -- run onboard-model". A column headed `template` that answers a narrower
            # question than it appears to is worse than no column.
            seed = resolve_seed(root, m, None)
            if (root / "use_cases" / seed).is_dir():
                kind = "own" if seed != "TEMPLATE" else "shared"
                has = f"yes ({kind}: {seed})"
            else:
                has = "NO -- run onboard-model"
            print(f"{m:12s} {case_prefix(m):12s} {has}")
        return 0

    if not args.model or not args.case:
        ap.error("--model and --case are required (or use --list)")
    try:
        create(args.model, args.case, args.seed, args.dry_run)
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
