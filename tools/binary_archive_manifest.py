#!/usr/bin/env python3
"""Generate and VERIFY the manifest of archived model binaries.

WHY THIS EXISTS. `model-evolution` step 3.5 requires that a run bind to an archived,
content-addressed executable rather than the live build path, because a shared CMake tree
(EcoSIM, PFLOTRAN, ATS) has ONE binary that every build overwrites in place. The archives are
therefore **not regenerable**: a recompile can perturb floating point, so a rebuilt binary is a
DIFFERENT artifact, not the same one.

Those archives live outside git — 25 MB each, and putting them in a fork of an upstream
scientific code would bloat its history permanently. But "not in git" had meant *nothing recorded
they existed*: every SHA256 sat only inside a `PROVENANCE.txt` that was itself ignored, so a
deleted or silently altered archive would be discovered by a run failing, and the
`model_change_ledger` entries naming those binaries were assertions nobody could check.

This tracks the MANIFEST, not the binaries: a few KB of text giving, per archive, its label,
source commit, branch, size and SHA256. That buys the three things tracking was for — a permanent
record that each existed, a checksum to detect alteration or swap, and enough provenance to say
which build produced a result — at no cost to repository size.

WHAT WOULD MAKE `--verify` FAIL (named first, per `feedback_a_check_that_cannot_fail`):
  M1  an archive in the manifest is MISSING from disk                  -> ERROR
  M2  a binary's SHA256 differs from the manifest                       -> ERROR (altered or swapped)
  M3  a binary's SHA256 differs from its own PROVENANCE.txt             -> ERROR (internally inconsistent)
  M4  an archive exists on disk but is ABSENT from the manifest         -> WARN (regenerate)
  M5  an archive directory has no binary, or no PROVENANCE.txt          -> WARN
  M6  no archive root found at all                                      -> ERROR (anti-silent-pass)
  M7  a ROUND LEDGER checksum claim does not resolve against the manifest -> ERROR

Usage:
    python tools/binary_archive_manifest.py --generate   # write/refresh the manifest
    python tools/binary_archive_manifest.py --verify     # check disk against it
"""
from __future__ import annotations
import argparse
import hashlib
import json
import os
import pathlib
import re
import sys
from datetime import datetime

ROOT = pathlib.Path(__file__).resolve().parents[1]

#: Per-model archive roots. The manifest is stored under the CASE, beside the round records that
#: cite these binaries, because the provenance chain that matters is round -> binary.
ARCHIVES = {
    "ecosim": {
        "archive_root": "~/EcoSIM/build_archive",
        "manifest": ROOT / "use_cases/EcoSIM_BioCON/config/binary_archive_manifest.json",
        "binary_name": "ecosim.f90.x",
    },
    # PFLOTRAN has the SAME hazard for the same reason: a shared CMake tree whose
    # src/pflotran/pflotran is one executable overwritten in place by every build, and a queued
    # SLURM job resolves its exe at RUN time. Registered 2026-08-27, when R1's first real
    # ensemble was materialized and its submit scripts were found bound to the LIVE build path.
    "pflotran": {
        "archive_root": "~/PFLOTRAN/build_archive",
        "manifest": ROOT / "use_cases/PFLOTRAN_miniLEO/config/binary_archive_manifest.json",
        "binary_name": "pflotran",
    },
}

_SHA_LINE = re.compile(r"^\s*SHA256\s*:\s*([0-9a-f]{64})\s*$", re.I | re.M)
_FIELD = re.compile(r"^\s*(Archived|Source|Change|Binary|Why|V0 pair)\s*:\s*(.+)$", re.I | re.M)


def sha256(path: pathlib.Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def read_provenance(p: pathlib.Path):
    """(claimed_sha, {field: value}) from a PROVENANCE.txt, or (None, {}) if unreadable."""
    if not p.is_file():
        return None, {}
    text = p.read_text(errors="replace")
    m = _SHA_LINE.search(text)
    fields = {k.strip().lower().replace(" ", "_"): v.strip() for k, v in _FIELD.findall(text)}
    return (m.group(1).lower() if m else None), fields


def scan(model: str):
    """Walk one model's archive root. Returns (entries, problems)."""
    cfg = ARCHIVES[model]
    root = pathlib.Path(cfg["archive_root"])
    entries, problems = [], []
    if not root.is_dir():
        problems.append(f"{model}: archive root does not exist: {root}")
        return entries, problems
    # os.scandir, not a glob walk: this lives on a shared filesystem where recursive traversal is
    # prohibited, and one level is all that is needed (feedback_nersc_no_recursive_traversal).
    for d in sorted(os.scandir(root), key=lambda e: e.name):
        if not d.is_dir():
            continue
        binp = pathlib.Path(d.path) / cfg["binary_name"]
        provp = pathlib.Path(d.path) / "PROVENANCE.txt"
        if not binp.is_file():
            problems.append(f"{model}/{d.name}: no {cfg['binary_name']} -- not a binary archive")
            continue
        claimed, fields = read_provenance(provp)
        if claimed is None:
            problems.append(f"{model}/{d.name}: PROVENANCE.txt missing or carries no SHA256 line")
        actual = sha256(binp)
        if claimed and claimed != actual:
            problems.append(f"{model}/{d.name}: SHA256 disagrees with its OWN PROVENANCE.txt "
                            f"(provenance {claimed[:12]}..., actual {actual[:12]}...) -- the "
                            f"archive is internally inconsistent")
        entries.append({
            "label": d.name,
            "model": model,
            "binary": cfg["binary_name"],
            "bytes": binp.stat().st_size,
            "sha256": actual,
            "provenance_sha256": claimed,
            "source": fields.get("source", ""),
            "change": fields.get("change", ""),
            "archived": fields.get("archived", ""),
        })
    return entries, problems


def cmd_generate(models, stamp):
    rc = 0
    for model in models:
        entries, problems = scan(model)
        for p in problems:
            print(f"  WARN  {p}")
        if not entries:
            print(f"✘ {model}: no archives found at {ARCHIVES[model]['archive_root']}", file=sys.stderr)
            rc = max(rc, 2)
            continue
        out = ARCHIVES[model]["manifest"]
        out.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "_comment": (
                "Manifest of ARCHIVED model binaries. The binaries themselves are NOT in git -- "
                "25 MB each, and not regenerable (a recompile can perturb floating point, so a "
                "rebuild is a different artifact). This file is the record that they existed and "
                "the checksum to prove one has not been altered or swapped. Regenerate and verify "
                "with tools/binary_archive_manifest.py. Losing the archive directory breaks the "
                "provenance of every completed round that cites one of these labels."),
            "_archive_root": ARCHIVES[model]["archive_root"],
            "_generated": stamp,
            "_tool": "tools/binary_archive_manifest.py",
            "archives": entries,
        }
        out.write_text(json.dumps(payload, indent=2) + "\n")
        total = sum(e["bytes"] for e in entries) / 1e6
        print(f"✔ {model}: {len(entries)} archive(s), {total:.0f} MB on disk -> "
              f"{out.relative_to(ROOT)}")
    return rc


def check_round_ledger(model, manifest_path, recorded):
    """M7 -- a round that CLAIMS a checksum must be checkable against the manifest.

    `calibration_rounds.yaml` records, per round, the `archived_build` path and a `sha256_prefix`.
    Until this check existed those two numbers were an assertion nobody verified: the cross-check
    that v2.305 reported was done ONCE, by hand, and nothing re-ran it. A ledger claim that cannot
    be resolved is exactly the "assertions nobody could check" state the manifest was built to end
    (`feedback_verify_derived_numbers_not_just_citations`).

    The ledger lives beside the manifest, because the provenance chain is round -> binary.
    """
    ledger = manifest_path.parent / "calibration_rounds.yaml"
    if not ledger.is_file():
        return []                       # a case with no round ledger is not an error here
    try:
        import yaml
        doc = yaml.safe_load(ledger.read_text()) or {}
    except Exception as exc:                                     # pragma: no cover - malformed yaml
        return [f"{model}: cannot read {ledger.name} to cross-check round checksums ({exc})"]

    # `round_binaries` hangs off `model_change_ledger`, NOT off each round. The first version of
    # this check walked `rounds` and therefore matched nothing -- it reported a clean pass while
    # verifying zero claims, which is why both mutations of the ledger were run before trusting it
    # ([[feedback_a_check_that_cannot_fail]]).
    binaries = ((doc.get("model_change_ledger") or {}).get("round_binaries")) or {}
    if not isinstance(binaries, dict):
        return [f"{model}: model_change_ledger.round_binaries is not a mapping in {ledger.name}"]

    out = []
    for n, rec in binaries.items():
        if not isinstance(rec, dict):
            continue
        build, prefix = rec.get("archived_build"), rec.get("sha256_prefix")
        if not build or not prefix:
            continue                    # `archived_build: null` is a stated fact, not a gap
        label = pathlib.PurePath(build).parent.name
        entry = recorded.get(label)
        if entry is None:
            out.append(f"{model}: round {n} cites archived_build '{build}' but the manifest "
                       f"has no archive labelled '{label}' -- that round's provenance claim "
                       f"cannot be resolved")
        elif not entry["sha256"].startswith(str(prefix)):
            out.append(f"{model}: round {n} claims sha256_prefix '{prefix}' for '{label}', "
                       f"but the manifest records {entry['sha256'][:12]}... -- the ledger and "
                       f"the manifest disagree about which binary that round ran")
    return out


def cmd_verify(models):
    errors, warnings = [], []
    for model in models:
        man = ARCHIVES[model]["manifest"]
        if not man.is_file():
            errors.append(f"{model}: no manifest at {man} -- run --generate")
            continue
        recorded = {e["label"]: e for e in json.loads(man.read_text())["archives"]}
        on_disk, problems = scan(model)
        warnings.extend(problems)
        seen = {e["label"]: e for e in on_disk}

        for label, e in recorded.items():                                          # M1, M2
            if label not in seen:
                errors.append(f"{model}/{label}: in the manifest but MISSING from disk. Every "
                              f"round citing this binary now has unverifiable provenance.")
                continue
            if seen[label]["sha256"] != e["sha256"]:
                errors.append(f"{model}/{label}: SHA256 CHANGED "
                              f"(manifest {e['sha256'][:12]}..., disk "
                              f"{seen[label]['sha256'][:12]}...) -- an archived binary is supposed "
                              f"to be immutable; it has been altered or swapped")
        for label in seen:                                                          # M4
            if label not in recorded:
                warnings.append(f"{model}/{label}: on disk but not in the manifest -- "
                                f"run --generate after archiving a new build")

        errors.extend(check_round_ledger(model, man, recorded))                      # M7

    if not any(ARCHIVES[m]["manifest"].is_file() or
               pathlib.Path(ARCHIVES[m]["archive_root"]).is_dir() for m in models):  # M6
        errors.append("no archive root and no manifest found for any model -- nothing was "
                      "checked, which is not a pass")

    n = sum(len(json.loads(ARCHIVES[m]["manifest"].read_text())["archives"])
            for m in models if ARCHIVES[m]["manifest"].is_file())
    print(f"binary archive verification — {n} archive(s) in manifest(s)")
    for w in warnings:
        print(f"  WARN  {w}")
    for e in errors:
        print(f"  ERROR {e}", file=sys.stderr)
    if errors:
        print(f"\n{len(errors)} error(s), {len(warnings)} warning(s)", file=sys.stderr)
        return 2
    if warnings:
        print(f"\n{len(warnings)} warning(s)")
        return 1
    print("\n✔ every archived binary is present and matches its recorded checksum")
    return 0


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--generate", action="store_true", help="write/refresh the manifest from disk")
    ap.add_argument("--verify", action="store_true", help="check disk against the manifest")
    ap.add_argument("--model", default=None, help=f"one of {sorted(ARCHIVES)} (default: all)")
    ap.add_argument("--stamp", default=None,
                    help="generation timestamp; defaults to now. Pass one for a reproducible file.")
    a = ap.parse_args()
    models = [a.model] if a.model else sorted(ARCHIVES)
    for m in models:
        if m not in ARCHIVES:
            print(f"unknown model {m!r}; known: {sorted(ARCHIVES)}", file=sys.stderr)
            return 2
    if a.generate:
        return cmd_generate(models, a.stamp or datetime.now().strftime("%Y-%m-%d"))
    if a.verify:
        return cmd_verify(models)
    ap.print_usage(sys.stderr)
    print("\nGive --generate or --verify.", file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main())
