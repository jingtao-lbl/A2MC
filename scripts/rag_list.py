#!/Library/Frameworks/Python.framework/Versions/3.10/bin/python3
"""
rag_list.py - List registered RAG milestones.

Reads `rag/milestones.json` and prints a tabular summary. Marks the active
profile (from $A2MC_RAG_ACTIVE) and indicates which milestones are
canonical / legacy / available locally.

Usage:
    python scripts/rag_list.py
    python scripts/rag_list.py --json

Author: Jing Tao with Claude
"""

import argparse
import json
import os
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_REPO_ROOT))
sys.path.insert(0, str(_REPO_ROOT / "tools"))

from rag_manifest import load_manifest, mark_available_locally  # noqa: E402



def _raw_adapter(manifest_path, profile):
    """The `adapter` key straight from milestones.json, because Milestone does not model it."""
    try:
        import json
        with open(manifest_path) as fh:
            return json.load(fh).get("milestones", {}).get(profile, {}).get("adapter")
    except Exception:
        return None


def main():
    parser = argparse.ArgumentParser(
        description="List registered RAG milestones."
    )
    parser.add_argument(
        "--manifest", type=Path,
        default=_REPO_ROOT / "rag" / "milestones.json",
        help="Manifest path (default: rag/milestones.json)",
    )
    parser.add_argument(
        "--rag-dir", type=Path,
        default=os.environ.get("A2MC_RAG_DIR") or str(_REPO_ROOT / "rag"),
        help="RAG storage root (default: $A2MC_RAG_DIR or repo/rag)",
    )
    parser.add_argument(
        "--json", action="store_true",
        help="Emit JSON instead of human-readable summary.",
    )
    args = parser.parse_args()

    manifest = load_manifest(args.manifest)
    if not manifest.milestones:
        print(f"No registered milestones at {args.manifest}.")
        print(
            "Use `python scripts/build_rag_index.py --rebuild` to build a "
            "milestone, then register it (Phase 4 Step 4.14)."
        )
        sys.exit(0)

    # Refresh availability
    for name in manifest.milestones:
        mark_available_locally(manifest, name, args.rag_dir)

    active = os.environ.get("A2MC_RAG_ACTIVE")

    if args.json:
        out = manifest.to_dict()
        out["_active_profile"] = active
        print(json.dumps(out, indent=2))
        return

    print(f"RAG milestones registry: {args.manifest}")
    print(f"RAG storage root:        {args.rag_dir}")
    print(f"Active profile:          {active or '(none — A2MC_RAG_ACTIVE unset)'}")
    print()
    print(f"  {'profile':18s}  {'fates tag / adapter':33s}  {'epoch':6s}  {'flags'}")
    print(f"  {'-' * 18}  {'-' * 33}  {'-' * 6}  {'-' * 30}")
    for name, m in manifest.milestones.items():
        flags = []
        if m.canonical:
            flags.append("canonical")
        if m.legacy:
            flags.append("legacy")
        if m.available_locally:
            flags.append("local")
        else:
            flags.append("not built")
        if name == active:
            flags.append("ACTIVE")
        # `fates_tag_built` is FATES-only. An adapter profile (EcoSIM, PFLOTRAN, ...) has none,
        # and printing "(unbuilt)" there read as "the index is not built" -- directly contradicting
        # the `local` flag on the same row, which is the field that actually says whether it is
        # built. Show the adapter instead. (2026-08-20)
        # Read `adapter` from the RAW json: Milestone (tools/rag_manifest.py) predates multi-model
        # support and has no such field, so the typed view drops it. See the audit in 20260820a --
        # the same gap makes to_dict() lossy, which is the real bug; this is the display half.
        adapter = _raw_adapter(args.manifest, name)
        tag = m.fates_tag_built or (f"adapter: {adapter}" if adapter else "-")
        print(f"  {name:18s}  {tag:33s}  {m.fates_api_epoch:6s}  {', '.join(flags)}")
    print()
    if active and active in manifest.milestones:
        m = manifest.milestones[active]
        if m.published_at:
            print(f"Active profile published: {m.published_at}")


if __name__ == "__main__":
    main()
