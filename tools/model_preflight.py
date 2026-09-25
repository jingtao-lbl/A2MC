#!/usr/bin/env python
"""Generic model preflight — version + PFT inventory for ANY onboarded model.

The model-agnostic analog of the FATES-specific steps a2mc-init performs in its
Step 2 (`rag_match.py` for FATES/ELM commit detection + `fates_utils` for the PFT
inventory from `fates_params_default.json`). Per the adapter-kit additive rule
(docs/38 §3, roadmap L3.2): this is a NEW file that dispatches through the active
model's ``ModelSpec``, so it works for --model ecosim now and any future adapter —
without touching the FATES tooling.

What it does, dispatched through ``models/<model>/spec.py``:
  1. Version — ``spec.version_detector_class().detect_from_checkout(checkout)`` and
     match its label against the registered milestones in ``rag/milestones.json``.
  2. PFT / subgrid inventory — parse the param file via
     ``spec.parameter_parser_class`` and read the model's own grouping-axis count
     (``spec.grouping_axis_dim_name``), never assuming a FATES SZPF layout.
  3. Calibratable surface — count non-string parameters.

Usage:
    python tools/model_preflight.py --model ecosim \
        --checkout ~/EcoSIM \
        --param-file Offline/EcoSIM_sample_files/input/ds_input__pft_test__ex1.nc

Exit codes, which a2mc-init Step 2 routes on:
    0  the checkout matches a registered milestone
    3  DRIFT: the model is onboarded, the checkout is at an unregistered commit (proceed; say so)
    2  not onboarded: no models/<model>/ package, or an adapter with no milestone at all
       (onboard-model, or resume it)
    1  usage / IO error, or CANNOT VERIFY (no version could be read from --checkout)
Drift had its own code from 2026-09-23; before that it shared 2 with "unsupported".

Author: Jing Tao with Claude
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent


def _load_milestones() -> dict:
    p = REPO / "rag" / "milestones.json"
    if not p.exists():
        return {}
    return json.loads(p.read_text())


def _match_milestone(label: str, milestones: dict) -> str | None:
    """Find a registered milestone whose key/label matches the detected label."""
    entries = milestones.get("milestones", milestones)
    if isinstance(entries, dict):
        for key, body in entries.items():
            if key == label or (isinstance(body, dict) and body.get("label") == label):
                return key
    return None



def _push_guard_status(checkout: Path) -> tuple[str, list[str]]:
    """Report the model checkout's push-remote posture.

    Model-SOURCE checkouts must not be able to push to the upstream project:
    memory `feedback_model_source_push_fork_only`. The established wiring is a
    `fork` remote pointing at the user's own fork plus `origin`'s push URL set to
    a `DISABLED_*` sentinel so `git push origin` fails immediately.

    This is ADVISORY, not a gate. It never changes the exit code, for two reasons:
    an upstream push almost always fails on credentials anyway (the sentinel is
    defence-in-depth, not the barrier), and "origin already IS my own fork" is a
    legitimate alternative setup. So we report the facts and flag only the case we
    cannot rule out -- a live origin push with no fork remote -- without asserting
    it is wrong.

    Returns (summary_line, advisory_lines).
    """
    import subprocess
    try:
        out = subprocess.run(["git", "-C", str(checkout), "remote", "-v"],
                             capture_output=True, text=True, timeout=10)
    except Exception as e:  # noqa: BLE001
        return f"push guard: could not run git ({e})", []
    if out.returncode != 0:
        return "push guard: not a git checkout (skipped)", []

    push_urls = {}
    for line in out.stdout.splitlines():
        parts = line.split()
        if len(parts) >= 3 and parts[2] == "(push)":
            push_urls[parts[0]] = parts[1]

    origin = push_urls.get("origin", "")
    has_fork = "fork" in push_urls
    disabled = origin.startswith("DISABLED_")

    if disabled and has_fork:
        return f"push guard: OK (origin push disabled, fork -> {push_urls['fork']})", []
    if disabled:
        return "push guard: origin push disabled, but NO fork remote", [
            "     add one before any model-source edit:  git remote add fork <your fork URL>",
        ]
    if has_fork:
        return f"push guard: fork remote present, but origin push is LIVE ({origin})", [
            "     disable it:  git remote set-url --push origin DISABLED_push_to_fork_not_upstream",
        ]
    return f"push guard: UNGUARDED -- origin push is live and there is no fork remote", [
        f"     origin push -> {origin or '(unset)'}",
        "     If that is upstream, wire the fork-only guard before editing model source:",
        "       git remote add fork <your fork URL>   # SSH if your token lacks `workflow` scope",
        "       git remote set-url --push origin DISABLED_push_to_fork_not_upstream",
        "     If origin is already YOUR OWN fork, this is fine -- verify and move on.",
        "     Contract: memory `feedback_model_source_push_fork_only`",
    ]


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--model", required=True, help="onboarded model name (e.g. ecosim)")
    ap.add_argument("--checkout", help="model source-tree root (for version detection)")
    ap.add_argument("--param-file", help="parameter/input file (for the PFT inventory)")
    args = ap.parse_args()

    sys.path.insert(0, str(REPO))
    try:
        import importlib
        from models import registry
    except Exception as e:  # pragma: no cover
        print(f"ERROR: cannot import model registry: {e}", file=sys.stderr)
        return 1
    # Importing the model package self-registers its backend in the registry.
    try:
        importlib.import_module(f"models.{args.model}")
    except ModuleNotFoundError:
        print(f"ERROR: model '{args.model}' is not onboarded (no models/{args.model}/ package).", file=sys.stderr)
        print("       A brand-new model needs the `onboard-model` skill first.", file=sys.stderr)
        return 2
    try:
        backend = registry.get_model(args.model)
    except Exception as e:
        print(f"ERROR: model '{args.model}' not onboarded: {e}", file=sys.stderr)
        print("       (a brand-new model needs the `onboard-model` skill first)", file=sys.stderr)
        return 2
    spec = backend.spec

    print(f"Model:        {spec.name}  ({spec.display_name})")
    matched = None
    detected = False          # a version was actually read from the checkout

    # 1. Version detection + milestone match
    if args.checkout:
        co = Path(args.checkout)
        if not co.exists():
            print(f"  version:    checkout not found: {co}")
        else:
            try:
                ver = spec.version_detector_class().detect_from_checkout(co)
                label = ver.label
                matched = _match_milestone(label, _load_milestones())
                detected = True
                print(f"  version:    {label}")
                print(f"  milestone:  {matched or '(UNMATCHED — see VERDICT: drift or no milestone)'}")
            except Exception as e:
                print(f"  version:    detection failed: {e}")
            # Advisory: model-source push posture (never gates the exit code).
            guard_line, guard_advice = _push_guard_status(co)
            print(f"  {guard_line}")
            for ln in guard_advice:
                print(ln)
    else:
        print("  version:    (skipped — no --checkout)")

    # 2. PFT / subgrid inventory + 3. calibratable surface
    if args.param_file:
        pf = Path(args.param_file)
        if not pf.exists():
            print(f"  PFT count:  param file not found: {pf}")
        else:
            parser = spec.parameter_parser_class()
            params = parser.parse(pf)
            pft_count = parser.get_pft_count() if hasattr(parser, "get_pft_count") else "?"
            calibratable = sum(
                1 for p in params.values()
                if not getattr(p, "is_string", False)
            )
            print(f"  subgrid:    {spec.grouping_axis} axis = {pft_count} ({spec.grouping_axis_dim_name})")
            print(f"  params:     {len(params)} total, {calibratable} non-string (calibratable candidates)")
    else:
        print("  PFT count:  (skipped — no --param-file)")

    if args.checkout and matched is None:
        # By this point the model imported and registered, so a miss is never "unsupported model".
        # It is one of three things, and they route differently (a2mc-init Step 2):
        #   NO MILESTONE -- the adapter registers but its onboarding never reached step 9. Known
        #                   from the registry alone, so it is reported even when no version was read.
        #   CANNOT VERIFY -- no version was read from the checkout (missing path, failed detection).
        #   DRIFT -- the adapter HAS a registered milestone, the checkout is at another commit.
        #            The model is onboarded; calibration can proceed on the registered profile.
        # Until 2026-09-23 all of these printed "NOT a supported version ... run onboard-model", which
        # sent every EcoSIM user off the single registered commit to re-onboard an onboarded model.
        entries = _load_milestones().get("milestones", {})
        mine = sorted(k for k, v in entries.items()
                      if isinstance(v, dict) and v.get("adapter") == args.model)
        if not mine:
            print(f"\nVERDICT: NO MILESTONE — {spec.name}'s adapter registers, but no rag/milestones.json")
            print("         entry names it, so its onboarding stopped before step 9 (RAG build and")
            print("         milestone registration). Resume it with the `onboard-model` skill:")
            print(f"         python3 tools/check_stage_ready.py --model {spec.name}   # first FAIL = resume point")
            return 2
        if not detected:
            print("\nVERDICT: CANNOT VERIFY — no version was read from the checkout (see above).")
            print("         Fix the path, or get and build the model first, then re-run.")
            return 1
        print(f"\nVERDICT: DRIFT — {spec.name} is onboarded (registered: {', '.join(mine)}),")
        print("         but this checkout is at a commit no milestone describes.")
        print("         Calibration can proceed: A2MC reasons with the registered profile, which")
        print("         describes the registered commit, not yours. If your source differs in the")
        print("         mechanisms you calibrate, rebuild the profile (the `rebuild-rag` skill;")
        print("         EcoSIM also has `ecosim-version-drift`) and say which you chose.")
        return 3
    print("\nVERDICT: preflight OK.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
