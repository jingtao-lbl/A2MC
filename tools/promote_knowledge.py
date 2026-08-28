#!/usr/bin/env python3
"""Promote a SITE discovery into the GENERIC knowledge base — the executor the arrow never had.

The two-tier knowledge architecture is documented in the root project instructions:

    Site Discovery -> AI Evaluation -> If generalizable -> Copy to memory/gained_knowledge/

Verified 2026-08-25: that arrow had **no implementation**. No tool, no `MemoryManager` method, no
skill step performed it — `tools/promote_diagnostic_script.py` promotes SCRIPTS, not knowledge. So
the generic store was written by hand or not at all, and a mechanism established at one site could
not reach the next one except through someone remembering it.

WHEN THIS RUNS. At **convergence**, and essentially only there (`round-housekeeping` item C-2).
"Is this discovery generalizable?" is not answerable mid-campaign, because what generalizes is what
SURVIVED, and what survived is not known until the campaign converges. Promoting earlier records a
guess as knowledge.

HUMAN-GATED, PER DISCOVERY, BY CONSTRUCTION. There is no `--all`. A curated write is one of the
four gates (`feedback_no_kb_injection_before_verified_test`), and "generalizes beyond this site" is
a scientific judgement, not a string match — the tool cannot make it and does not try. What it does
is remove the friction and the transcription errors around a judgement a human has already made,
and refuse to proceed when the evidence for that judgement is absent.

WHAT WOULD MAKE A PROMOTION FAIL (named first, per `feedback_a_check_that_cannot_fail`):
  P1  the named discovery is not in the site store                      -> refuse
  P2  it is already in the generic store                               -> refuse (never silently overwrite)
  P3  it is not marked verified, and --allow-unverified was not passed  -> refuse
  P4  no --rationale explaining WHY it generalizes                      -> refuse
  P5  the site store does not exist / holds no discoveries              -> refuse, and say which store

Usage:
    python tools/promote_knowledge.py --list                       # what the site store holds
    python tools/promote_knowledge.py --name X --rationale "..." --dry-run
    python tools/promote_knowledge.py --name X --rationale "..."   # writes, after the dry run
"""
from __future__ import annotations
import argparse
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

GENERIC = ROOT / "memory" / "gained_knowledge"


def _site_dir(explicit=None) -> Path:
    d = explicit or os.environ.get("A2MC_USE_CASE_DIR")
    if not d:
        raise SystemExit(
            "cannot resolve the case: pass --site-dir or set A2MC_USE_CASE_DIR (source "
            "a2mc_config.sh then the case config). Refusing to guess which case's knowledge "
            "would be promoted into the shared store.")
    return Path(d) if Path(d).is_absolute() else ROOT / d


def _load(store: Path, key="discoveries"):
    f = store / f"{key}.json"
    if not f.is_file():
        return {}, {}
    payload = json.loads(f.read_text())
    inner = payload.get(key, {})
    if isinstance(inner, list):                       # both shapes exist in the wild
        inner = {e.get("name", f"entry_{i}"): e for i, e in enumerate(inner)}
    return payload, inner


def cmd_list(site: Path) -> int:
    payload, site_d = _load(site / "memory" / "gained_knowledge")
    if not site_d:                                                                       # P5
        print(f"✘ no discoveries in {site}/memory/gained_knowledge/ — nothing to promote.\n"
              f"  An empty store after a closed round means `round-housekeeping` step 1 never ran.",
              file=sys.stderr)
        return 2
    _, gen_d = _load(GENERIC)
    print(f"site store: {site.name}  ({len(site_d)} discoveries)")
    print(f"generic store: {len(gen_d)} discoveries\n")
    for name, e in sorted(site_d.items()):
        mark = "ALREADY GENERIC" if name in gen_d else ("verified" if e.get("verified") else "UNVERIFIED")
        print(f"  [{mark:>15}]  {name}")
        desc = (e.get("description") or "").strip()
        if desc:
            print(f"                     {desc[:100]}")
    print("\nPromotion is per-discovery and needs a --rationale saying why it generalizes BEYOND")
    print("this site. There is no --all: that judgement is scientific, and the tool cannot make it.")
    return 0


def cmd_promote(site: Path, name: str, rationale: str, allow_unverified: bool, dry: bool) -> int:
    _, site_d = _load(site / "memory" / "gained_knowledge")
    if not site_d:                                                                       # P5
        print(f"✘ {site}/memory/gained_knowledge/discoveries.json holds no discoveries",
              file=sys.stderr)
        return 2
    if name not in site_d:                                                               # P1
        print(f"✘ '{name}' is not in the site store. Available: {', '.join(sorted(site_d))}",
              file=sys.stderr)
        return 2
    entry = dict(site_d[name])

    gen_payload, gen_d = _load(GENERIC)
    if name in gen_d:                                                                    # P2
        print(f"✘ '{name}' is already in the generic store. Refusing to overwrite: the generic "
              f"entry may have been curated since, and a silent overwrite would discard that.",
              file=sys.stderr)
        return 2
    if not entry.get("verified") and not allow_unverified:                               # P3
        print(f"✘ '{name}' is not marked verified. A discovery that has not been verified at its "
              f"OWN site cannot be asserted as general (`feedback_no_kb_injection_before_verified_"
              f"test`). Pass --allow-unverified only with a reason recorded in --rationale.",
              file=sys.stderr)
        return 2

    entry["source"] = f"promoted_from:{site.name}"
    entry["promoted_from_site"] = site.name
    entry["generalization_rationale"] = rationale
    if entry.get("confidence") is not None:
        # A single site is one observation of generality. Carrying the site confidence unchanged
        # would assert the same certainty about a broader claim than the evidence supports.
        entry["confidence"] = round(min(float(entry["confidence"]), 0.7), 2)

    print(f"{'DRY RUN — would promote' if dry else 'promoting'} '{name}'")
    print(f"  from : {site.name}/memory/gained_knowledge/discoveries.json")
    print(f"  to   : memory/gained_knowledge/discoveries.json")
    print(f"  why  : {rationale}")
    print(f"  confidence: {site_d[name].get('confidence')} -> {entry.get('confidence')} "
          f"(capped: one site is one observation of generality)")
    if dry:
        print("\nRe-run without --dry-run to write. The site entry is left untouched either way —")
        print("promotion COPIES; the site store remains the record of where the finding came from.")
        return 0

    GENERIC.mkdir(parents=True, exist_ok=True)
    inner = gen_payload.get("discoveries")
    if isinstance(inner, list):
        inner.append(entry)
    else:
        gen_payload.setdefault("discoveries", {})[name] = entry
    gen_payload["_last_updated"] = __import__("datetime").datetime.now().strftime("%Y-%m-%d")
    (GENERIC / "discoveries.json").write_text(json.dumps(gen_payload, indent=2) + "\n")
    print(f"\n✔ written. Review the diff before committing — this is a curated Tier-3 write.")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--site-dir", help="the case dir (default: $A2MC_USE_CASE_DIR)")
    ap.add_argument("--list", action="store_true", help="show the site store and what is promotable")
    ap.add_argument("--name", help="the discovery to promote (one at a time, by design)")
    ap.add_argument("--rationale", default="", help="WHY it generalizes beyond this site")
    ap.add_argument("--allow-unverified", action="store_true",
                    help="promote a discovery not marked verified; say why in --rationale")
    ap.add_argument("--dry-run", action="store_true", help="show the promotion without writing")
    a = ap.parse_args()

    site = _site_dir(a.site_dir)
    if a.list or not a.name:
        if not a.name and not a.list:
            ap.print_usage(sys.stderr)
            print("\nGive --list, or --name with --rationale.", file=sys.stderr)
            return 2
        return cmd_list(site)
    if not a.rationale.strip():                                                          # P4
        print("✘ --rationale is required: state WHY this generalizes beyond this site. Promotion "
              "without a recorded reason is how a site-specific finding becomes a general claim "
              "nobody can re-judge.", file=sys.stderr)
        return 2
    return cmd_promote(site, a.name, a.rationale.strip(), a.allow_unverified, a.dry_run)


if __name__ == "__main__":
    sys.exit(main())
