#!/usr/bin/env python
"""Bundle a trained surrogate into something a person who does not have A2MC can actually load.

THE GAP THIS CLOSES. A saved surrogate is a directory of `spec.json`, `tier.json` and a pickle or a
`state_dict`. None of it loads without `models.surrogate` importable AT THAT EXACT MODULE PATH,
because the joblib blobs hold references to classes by their dotted name. So the artifact directory,
on its own, is not the deliverable: handing it to a collaborator hands them a file they cannot open.

WHAT GOES IN, AND WHAT DELIBERATELY DOES NOT.

  in    the artifact's declarations (`spec.json`, `tier.json`, `environment.json`), its verdicts
        (`acceptance.json`, `promotion.json`), and its weights.
  in    a copy of `models/surrogate/*.py`, because that is the code the pickles name.
  in    a `models/__init__.py` STUB, not the repo's. The repo's imports `.base` and `.registry`,
        which are the adapter framework and have nothing to do with a surrogate; copying it makes
        the bundle fail on import for a dependency it does not need. This is the one non-obvious
        step in the whole tool.
  in    FIGURES named with `--figure`, each with its caption if one sits beside it. A bundle whose
        purpose is REVIEW that shows the reviewer nothing is asking them to audit a number they
        cannot see. Figures live in the phase-results stem rather than the artifact directory, so
        they are named explicitly: the artifact does not know which stem produced it, and guessing
        is how a bundle acquires a figure of something else.
  out   training data, held-out arrays, logs. A held-out prediction array can run to hundreds of
        megabytes and is evidence, not payload; `--include` takes it if a recipient needs to
        re-verify.

THE PROMOTION GATE APPLIES HERE TOO. Packaging is the act of handing the surrogate to someone else,
which is exactly when `promotion.json` matters, so an unpromoted artifact is refused by default.
`--allow-unpromoted` exists because an unpromoted artifact is legitimately shared for REVIEW, and
it stamps the bundle's README so the recipient cannot mistake one for the other.

Usage::

    python tools/package_surrogate.py <artifact_dir> --out <bundle_dir> [--tar]
    python tools/package_surrogate.py <artifact_dir> --out <bundle_dir> --allow-unpromoted
    python tools/package_surrogate.py <artifact_dir> --out <bundle_dir> --include heldout.npz
    python tools/package_surrogate.py <artifact_dir> --out <bundle_dir> --figure ../fit_figure.png

Author: Jing Tao with Claude on Perlmutter
"""
from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import sys
import tarfile
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

OK, REFUSED, USAGE = 0, 10, 2

#: Files every bundle carries when present. A missing `spec.json` or `tier.json` is fatal (the
#: bundle would not load); a missing `acceptance.json` is fatal for a different reason, below.
DECLARATION_FILES = ("spec.json", "tier.json", "environment.json",
                     "acceptance.json", "promotion.json")

#: Weight files by the class named in `tier.json`. Explicit rather than a glob, so a new tier that
#: saves its weights under a new name FAILS here instead of shipping a bundle with no weights in it.
WEIGHTS_BY_CLASS = {
    "S0Surrogate": ("s0.joblib",),
    "S1Surrogate": ("s1.joblib",),
    "S2Surrogate": ("s2.joblib",),
    "S3Surrogate": ("s3.joblib",),
    "KGMLEmulator": ("kgml.pt", "history.json"),
    "VectorSurrogate": ("vector.joblib",),
    "FieldEmulator": ("field.pt", "history.json"),
    "SpatioTemporalEmulator": ("spatiotemporal.pt", "history.json"),
    "GraphEmulator": ("graph.pt", "history.json"),
    "DeepONetEmulator": ("deeponet.pt", "history.json"),
}

#: The stub that replaces the repo's `models/__init__.py` inside the bundle.
MODELS_STUB = '''"""Namespace stub for a packaged A2MC surrogate.

This is NOT A2MC's `models/__init__.py`. The real one imports the adapter framework and its model
registry, neither of which a surrogate needs and neither of which is in this bundle. The joblib and
torch artifacts name their classes as `models.surrogate.*`, so this package must exist under that
name for them to load, and this file is the smallest thing that makes it exist.
"""
'''

LOADER = '''#!/usr/bin/env python
"""Load the surrogate in this bundle. Run it to check the bundle works; import `load_bundle` to use it.

    python load_surrogate.py                 # loads, prints the spec, predicts one point
    from load_surrogate import load_bundle   # -> (model, spec)
"""
from __future__ import annotations

import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))          # so `models.surrogate` resolves to the copy in here

ARTIFACT = HERE / "artifact"


def load_bundle(strict: bool = True):
    """Return (model, spec). `strict=False` downgrades an environment mismatch to a warning."""
    from models.surrogate.tiers import load

    model = load(ARTIFACT, strict=strict)   # every surrogate class, dispatched from tier.json
    return model, model.spec


if __name__ == "__main__":
    import numpy as np

    model, spec = load_bundle()
    print(f"loaded {spec.name}  tier={spec.tier}  use_mode={spec.use_mode}")
    print(f"  inputs  : {spec.n_inputs} -> {list(spec.input_names)[:6]}...")
    print(f"  targets : {spec.target_names}")
    mid = (np.asarray(spec.input_lower) + np.asarray(spec.input_upper)) / 2.0
    if spec.tier in ("S0", "S1"):
        print(f"  midpoint prediction: {model.simulated(mid)}")
    else:
        # A TRAJECTORY MODEL NEEDS DRIVERS, and the recipient has no way to guess their names,
        # order or units. Print the contract this artifact itself declares, so "how do I predict"
        # is answered by the bundle rather than by asking the sender.
        drv = list(getattr(model, "driver_names", []) or [])
        if drv:
            print(f"  drivers required: {len(drv)} columns, IN THIS ORDER -> {drv}")
            print(f"  predict with    : model.predict_trajectories(X, drivers)   "
                  f"# X (n, {spec.n_inputs}), drivers (T, {len(drv)})")
        else:
            print("  this model predicts trajectories; see 'How to predict' in the README")
'''


# ---------------------------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------------------------

def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for block in iter(lambda: fh.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def _read_json(path: Path) -> Optional[Dict[str, Any]]:
    return json.loads(path.read_text()) if path.is_file() else None


def _refuse(msg: str) -> None:
    raise SystemExit(f"REFUSING: {msg}")


def _human_bytes(n: int) -> str:
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024 or unit == "GB":
            return f"{n:.0f} {unit}" if unit == "B" else f"{n:.1f} {unit}"
        n /= 1024.0
    return f"{n:.1f} GB"


# ---------------------------------------------------------------------------------------------
# the bundle
# ---------------------------------------------------------------------------------------------

def _copy_figures(figures, out: Path, written: List[Path],
                  figure_pairs: List[Tuple[Path, Optional[Path]]]) -> None:
    """Copy each --figure (and its caption) into the bundle, refusing name collisions.

    A FUNCTION rather than an inline loop so the collision refusal can be tested directly:
    the behaviour it replaces was found by a reviewer running the CLI twice, which is not a
    check anything keeps running.
    """
    # BASENAME COLLISIONS ARE REFUSED, not silently resolved. Two --figure arguments from
    # different directories can share a name (`fig.png` beside `fig.png`), and the copy below
    # would overwrite the first with the second while `written` listed the path TWICE -- so the
    # manifest carried two entries with one file's hash under both, `shasum -c` passed, and the
    # bundle shipped a figure the recipient never sees with a caption that describes it. A
    # deliberate rename by the caller is the fix; guessing one here would put a name in the
    # manifest that matches nothing the caller asked for.
    seen: Dict[str, str] = {}
    for name in figures or []:
        src = Path(name)
        if not src.is_file():
            _refuse(f"--figure {name}: no such file")
        prior = seen.get(src.name)
        if prior is not None and Path(prior).resolve() != src.resolve():
            _refuse(f"--figure {name}: a different file is already being packaged as "
                    f"'figures/{src.name}' (from {prior}). Two figures cannot share a basename "
                    f"inside the bundle -- the second would overwrite the first and the manifest "
                    f"would list the name twice with one file's hash. Rename one before packaging.")
        if prior is not None:
            continue                       # the same file named twice: copy once, list once
        seen[src.name] = str(src)
        dst = out / "figures" / src.name
        shutil.copy2(src, dst)
        written.append(dst)
        cap = _caption_for(src)
        if cap is not None:
            cdst = out / "figures" / cap.name
            if cdst.exists() and cdst.read_bytes() != cap.read_bytes():
                _refuse(f"--figure {name}: its caption '{cap.name}' collides with a different "
                        f"caption already packaged. Rename one before packaging.")
            shutil.copy2(cap, cdst)
            written.append(cdst)
        figure_pairs.append((dst, (out / "figures" / cap.name) if cap else None))


def _caption_for(figure: Path) -> Optional[Path]:
    """The caption file beside a figure, or None when there is no unambiguous one.

    The lookup follows the caption conventions of results folders: a bare `caption.md` is the
    common form, with `caption_<topic>.md` used where one folder holds several figures. The topic
    is named after the SUBJECT, not the figure's filename (`caption_emulator.md` beside
    `run1_emulator_fit.png`), so a stem-matching rule alone finds nothing in the common case.

    The last rule is the one that needs care. A folder holding several `caption_*.md` and no
    stem match is AMBIGUOUS, and this returns None rather than picking one: a bundle carrying a
    caption for a different figure is worse than one carrying no caption, because the README
    presents it as describing what the reader is looking at.
    """
    parent = figure.parent
    for cand in (parent / f"caption_{figure.stem}.md",
                 figure.with_suffix(".md"),
                 parent / f"{figure.stem}_caption.md",
                 parent / "caption.md"):
        if cand.is_file():
            return cand
    loose = sorted(parent.glob("caption_*.md"))
    return loose[0] if len(loose) == 1 else None


def _caption_lead(caption: Path) -> str:
    """The caption's finding sentence: its first BOLD lead line, trimmed to one sentence.

    A2MC captions follow `feedback_report_figure_empty_alt_text`: an `![](fig.png)` embed, then a
    `**Figure N. <the finding>.**` paragraph. So skip headings, blank lines and image embeds, and
    take the first line that opens in bold.
    """
    for raw in caption.read_text().splitlines():
        ln = raw.strip()
        if not ln or ln.startswith("#") or ln.startswith("!["):
            continue
        if ln.startswith("**"):
            end = ln.find("**", 2)
            return ln[2:end].strip() if end > 2 else ln
        return ln
    return ""


#: What `--report` ships from a report DIRECTORY: the document and the figures it embeds. Its build
#: machinery (a pdf build script, a LaTeX header, a figure-provenance tsv) stays behind -- a bundle
#: is for reading, not for rebuilding the document.
REPORT_SUFFIXES = {".md", ".pdf", ".docx", ".png", ".jpg", ".jpeg"}


def _how_to_predict(tier_cls: str, spec_d: Dict[str, Any]) -> List[str]:
    """The section a delivered bundle was missing: how to get a number out of it.

    An audit of a bundle already in a collaborator's repository found it could not produce a
    prediction as delivered -- it loaded, and then the recipient had to ask what to call and what
    to pass. The loader script pointed at "the bundle README for the call it needs", and the
    README had no such section. Written per architecture, because a scalar tier and a
    driver-conditioned sequence emulator need different arguments.
    """
    n_in = len(spec_d.get("input_names") or [])
    names = list(spec_d.get("input_names") or [])[:4]
    order = ", ".join("`%s`" % n for n in names) + (", ..." if n_in > len(names) else "")
    out = ["## How to predict", "",
           "Inputs are a 2-D array `X` of shape `(n_cases, %d)`, with the columns IN THE ORDER "
           "the spec declares: %s. `spec.input_names` is that order; do not reorder it." % (n_in, order),
           ""]
    if tier_cls in ("S0Surrogate", "S1Surrogate"):
        out += ["```python", "from load_surrogate import load_bundle",
                "model, spec = load_bundle()",
                "pred = model.predict_batch(X)        # .values -> (n_cases, n_targets)",
                "one  = model.simulated(X[0])         # {target: value} for a single case",
                "```", ""]
    elif tier_cls in ("KGMLEmulator", "S2Surrogate", "S3Surrogate"):
        out += ["This model emulates TRAJECTORIES, so it needs the per-step drivers as well as the "
                "parameter vector. The artifact declares the driver columns it was trained on and "
                "their order; read them from the model rather than guessing:", "",
                "```python", "from load_surrogate import load_bundle",
                "model, spec = load_bundle()",
                "print(model.driver_names)            # the driver columns, IN ORDER",
                "traj = model.predict_trajectories(X, drivers)   # drivers (T, n_drivers)",
                "                                                # -> (n_cases, n_targets, T)",
                "pred = model.predict_batch(X)        # the same trajectories, reduced to scalars",
                "```", "",
                "`drivers` must carry the same columns, in the same order and units, as the run "
                "the emulator was trained on. Feeding a different set silently produces a "
                "confident wrong answer, because nothing in the array says what its columns are.",
                ""]
    else:
        out += ["```python", "from load_surrogate import load_bundle",
                "model, spec = load_bundle()",
                "pred = model.predict_batch(X)",
                "```", "",
                "This architecture (`%s`) may expose a richer call (a field, a network or a "
                "trajectory) -- `help(type(model))` after loading lists what it takes." % tier_cls,
                ""]
    return out


def _report_verdict(acceptance: Optional[Dict[str, Any]]) -> Optional[bool]:
    """True / False / None, from the ONE derivation in models.surrogate.validate."""
    if not acceptance:
        return None
    try:
        from models.surrogate.validate import report_passed
    except Exception:                                      # pragma: no cover - packaging offline
        return acceptance.get("passed")
    return report_passed(acceptance)


def _use_mode_line(spec_d: Dict[str, Any], acceptance: Optional[Dict[str, Any]]) -> str:
    """One line pairing the DECLARED use mode with whether acceptance backs it."""
    mode = spec_d.get("use_mode")
    verdict = _report_verdict(acceptance)
    if verdict is True:
        return ("The use mode above is DECLARED and ACCEPTED: the acceptance battery for "
                "`%s` passed. See Verdicts below for the split it was measured on." % mode)
    if verdict is False:
        return ("**The use mode above is DECLARED, NOT EARNED.** `use_mode` records what this "
                "surrogate was BUILT FOR; its acceptance battery for `%s` FAILED. Read Verdicts "
                "below before using it as one." % mode)
    return ("**The use mode above is DECLARED, NOT EARNED.** `use_mode` records what this "
            "surrogate was built for, and this artifact carries no acceptance verdict, so "
            "nothing here says it meets the bar for `%s`." % mode)


def _architecture_line(tier_cls: str, spec_d: Dict[str, Any]) -> str:
    """Name the architecture, because a tier names a rung and several classes can sit on one."""
    known = {
        "KGMLEmulator": "a recurrent, driver-conditioned sequence emulator (after KGML / PyKGML) "
                        "-- NOT the latent ROM that `S3Surrogate` implements on the same rung",
        "S3Surrogate": "the latent ROM with composed targets",
        "S2Surrogate": "the trajectory tier: a latent reduced-order model over the time axis",
        "S1Surrogate": "the scalar tier: per-target regression with conformal intervals",
        "S0Surrogate": "the baseline tier: the training set itself, used as a lookup",
        "FieldEmulator": "a spatial field emulator over a fixed grid",
        "SpatioTemporalEmulator": "a space-and-time emulator",
        "GraphEmulator": "a network emulator over declared nodes and edges",
        "DeepONetEmulator": "an operator-learning emulator",
    }
    what = known.get(tier_cls)
    if what:
        return "Architecture: `%s` -- %s." % (tier_cls, what)
    return ("Architecture: `%s`. A tier names a RUNG rather than an implementation, so check this "
            "class against the methodology report before assuming which one you have." % tier_cls)


def _readme(artifact: Path, spec_d: Dict[str, Any], tier_cls: str,
            acceptance: Optional[Dict[str, Any]], promotion: Optional[Dict[str, Any]],
            env: Optional[Dict[str, Any]], files: List[Path], bundle: Path,
            figure_pairs: Optional[List[Tuple[Path, Optional[Path]]]] = None,
            report_files: Optional[List[Path]] = None) -> str:
    prov = spec_d.get("provenance") or {}
    lines = [
        f"# Packaged A2MC surrogate: `{spec_d.get('name')}`",
        "",
        f"Tier **{spec_d.get('tier')}** (`{tier_cls}`), use mode **{spec_d.get('use_mode')}**, "
        f"{len(spec_d.get('input_names') or [])} inputs, "
        f"{len(spec_d.get('targets') or [])} targets.",
        "",
        # THE USE MODE IS A DECLARATION, NOT AN ACHIEVEMENT, and a reader holding the methodology
        # report needs that said here rather than inferred three sections down. A bundle whose
        # acceptance FAILED still carries `use_mode: online_inference` in its spec, because the
        # field records what the surrogate was BUILT FOR; the audit of a delivered bundle read
        # that as a claim the artifact had met the bar. So the verdict travels with the mode.
        _use_mode_line(spec_d, acceptance),
        "",
        # A tier names a RUNG, not an implementation: S3 covers both the latent ROM in
        # `S3Surrogate` and the driver-conditioned recurrent emulator in `KGMLEmulator`, which is
        # why "tier S3" alone read as a mislabel to a recipient expecting the other one.
        _architecture_line(tier_cls, spec_d),
        "",
        "## What this is",
        "",
        "A trained statistical emulator of a process model, together with the code needed to load "
        "it. It is not the process model, and it is valid only against the setup it was trained "
        "against, recorded below. Changing the parameter list, the bounds, the base parameter file "
        "or the scoring convention invalidates it.",
        "",
        "## How to load it",
        "",
        "```bash",
        "python load_surrogate.py          # loads the artifact and prints what it is",
        "```",
        "",
        "```python",
        "from load_surrogate import load_bundle",
        "model, spec = load_bundle()",
        "```",
        "",
        "No installation step: `load_surrogate.py` puts this directory on `sys.path` so the "
        "`models.surrogate` package inside it resolves. You need the libraries listed under "
        "Environment below.",
        "",
    ] + _how_to_predict(tier_cls, spec_d) + [
        "## Provenance: what this artifact is bound to",
        "",
        "| field | value |",
        "|---|---|",
    ]
    for k, v in prov.items():
        lines.append(f"| `{k}` | {v if v else '_not recorded_'} |")
    unstamped = [k for k, v in prov.items() if not v]
    if unstamped:
        lines += ["", "**%d of these %d fields are not recorded** (%s). Each unrecorded field is "
                  "a binding this artifact cannot be checked against: nothing here can tell you "
                  "whether the model source, the parameter list or the scoring convention has "
                  "moved since it was fitted, so the artifact is UNPROTECTED against those "
                  "changes rather than verified against them."
                  % (len(unstamped), len(prov), ", ".join("`%s`" % k for k in unstamped))]

    lines += ["", "## Environment it was built with", ""]
    if env:
        lines.append(f"Python {env.get('python')} on `{env.get('platform')}`.")
        lines.append("")
        lines.append("| library | version |")
        lines.append("|---|---|")
        for k, v in (env.get("libraries") or {}).items():
            lines.append(f"| `{k}` | {v} |")
        lines += ["", "A MAJOR version difference in any of these refuses to load, because a "
                  "pickled estimator and a saved `state_dict` are not guaranteed across one. Pass "
                  "`load_bundle(strict=False)` to override once you have decided the change is safe."]
    else:
        lines.append("**Not recorded.** This artifact predates environment stamping, so the "
                     "library versions that produced it are unknown and a silent change in them "
                     "cannot be detected.")

    lines += ["", "## Verdicts", ""]
    if acceptance:
        # Derived, not read: `passed` is a property of AcceptanceReport, so a report serialized
        # from the dataclass has `verdicts` and no `passed` key and this section printed nothing
        # at all about a report that records a FAIL.
        passed = _report_verdict(acceptance)
        if passed is not None:
            lines.append(f"Acceptance: **{'PASSED' if passed else 'FAILED'}**.")
        else:
            lines.append("Acceptance: **NO VERDICT RECORDED.** The report in this artifact has "
                         "neither a `passed` field nor a non-empty `verdicts` block, so nothing "
                         "in it says the surrogate was accepted.")
        summary = acceptance.get("summary")
        if summary:
            lines.append("")
            lines.append(f"> {str(summary)[:600]}")
        split = acceptance.get("split_kind")
        if split:
            lines += ["", f"Split used to measure it: **{split}**"]
    else:
        lines.append("No acceptance report in the artifact.")

    lines.append("")
    if promotion and promotion.get("promoted") and not promotion.get("revoked"):
        lines.append(f"Promotion: **approved** {promotion.get('promoted_at')} by "
                     f"{promotion.get('reviewed_by') or 'unattributed'}.")
        if promotion.get("basis"):
            lines += ["", f"> Basis: {promotion['basis']}"]
        if promotion.get("forced"):
            lines.append("")
            lines.append("**This promotion was FORCED over a failing acceptance report.**")
    else:
        lines += ["", "Promotion: **NOT PROMOTED.** This bundle was built with "
                  "`--allow-unpromoted` and is for REVIEW. No human has authorised this surrogate "
                  "for use, so do not let it steer a decision until one has."]

    if report_files:
        docs = [f for f in report_files if f.suffix.lower() in (".pdf", ".docx", ".md")]
        imgs = [f for f in report_files if f.suffix.lower() in (".png", ".jpg", ".jpeg")]
        lines += ["", "## Report", "",
                  "**Read this first.** The methodology report for this surrogate: what it is, how "
                  "it was evaluated, and what may and may not be claimed from it. The Verdicts "
                  "section above is the summary; the reasoning is here.", ""]
        for f in docs:
            lines.append(f"- `report/{f.name}`")
        if imgs:
            lines.append(f"- {len(imgs)} embedded figure(s), numbered as the report numbers them")
        lines += ["", "`report/` and `figures/` overlap on purpose: `figures/` is the loose set "
                  "shipped for quick review, `report/` is the document's own numbered set.", ""]

    if figure_pairs:
        lines += ["", "## Figures", "",
                  "Shipped for review. Each is the rendered PNG from the phase-results folder that "
                  "produced it; the caption beside it, where one exists, states what it shows and "
                  "how to read it.", ""]
        for fig, cap in figure_pairs:
            lines.append(f"### `figures/{fig.name}`")
            lines.append("")
            lines.append(f"![](figures/{fig.name})")
            lines.append("")
            if cap is not None:
                # Quote the caption's own finding rather than paraphrasing it, so the bundle and the
                # phase folder cannot disagree. The line wanted is the bold `**Figure N. ...**`
                # lead, NOT the first non-heading line: an A2MC caption opens with its own `![](...)`
                # embed, which a naive first-line rule quotes as the finding (it did, on the first
                # real bundle, producing a README that quoted an image tag at the reader).
                first = _caption_lead(cap)
                if first:
                    lines.append(f"> {first}")
                    lines.append("")
                lines.append(f"Full caption: `figures/{cap.name}`.")
            else:
                lines.append("_No caption file accompanied this figure._")
            lines.append("")

    lines += ["", "## Contents", "", "| file | size | sha256 (first 16) |", "|---|---|---|"]
    for f in files:
        lines.append(f"| `{f.relative_to(bundle)}` | {_human_bytes(f.stat().st_size)} | "
                     f"`{_sha256(f)[:16]}` |")
    lines += ["", "`MANIFEST.sha256` carries the full digests; verify with "
              "`sha256sum -c MANIFEST.sha256`. It covers everything the packager wrote, "
              "this README included. **Anything added to the bundle afterwards is not in "
              "it**, and `sha256sum -c` will report success without checking it -- add "
              "files with `--report` / `--figure` / `--include` at package time, or "
              "regenerate the manifest over the whole bundle.", ""]
    return "\n".join(lines)


def package(artifact: Path, out: Path, allow_unpromoted: bool = False,
            include: Optional[List[str]] = None, figures: Optional[List[str]] = None,
            report: Optional[str] = None,
            make_tar: bool = False, force: bool = False) -> Path:
    """Build the bundle. Raises SystemExit with a stated reason rather than writing a broken one."""
    artifact = Path(artifact)
    if not artifact.is_dir():
        _refuse(f"{artifact} is not a directory.")

    spec_path, tier_path = artifact / "spec.json", artifact / "tier.json"
    if not spec_path.is_file():
        _refuse(f"{artifact} has no spec.json; it is not a saved surrogate.")
    if not tier_path.is_file():
        _refuse(f"{artifact} has no tier.json, so the class to rebuild is unknown.")

    spec_d = json.loads(spec_path.read_text())
    tier_cls = json.loads(tier_path.read_text()).get("class", "")
    if tier_cls not in WEIGHTS_BY_CLASS:
        _refuse(f"tier class {tier_cls!r} has no packaging recipe. Add it to WEIGHTS_BY_CLASS in "
                f"{Path(__file__).name} in the same commit that adds the tier, so a new tier "
                f"cannot ship a bundle with no weights in it.")

    missing = [w for w in WEIGHTS_BY_CLASS[tier_cls] if not (artifact / w).is_file()]
    if missing:
        _refuse(f"{artifact} is missing the weight file(s) {missing} that {tier_cls} saves. "
                "The artifact is incomplete; re-save it.")

    acceptance = _read_json(artifact / "acceptance.json")
    if acceptance is None:
        _refuse(f"{artifact} has no acceptance.json. An unmeasured surrogate must not be handed "
                "to anyone; measure it first.")

    from tools.promote_surrogate import check_promotion
    promoted, why = check_promotion(artifact)
    if not promoted and not allow_unpromoted:
        _refuse(f"{artifact} is {why}.\n"
                "  Packaging is the act of handing this to someone else, which is when the\n"
                "  promotion gate matters. Promote it with tools/promote_surrogate.py, or pass\n"
                "  --allow-unpromoted to ship it for REVIEW (the bundle README says so plainly).")

    out = Path(out)
    if out.exists():
        if not force:
            _refuse(f"{out} already exists. Pass --force to overwrite it, having checked it is not "
                    "a bundle someone else is using.")
        shutil.rmtree(out)
    (out / "artifact").mkdir(parents=True)

    written: List[Path] = []

    for name in DECLARATION_FILES:
        src = artifact / name
        if src.is_file():
            dst = out / "artifact" / name
            shutil.copy2(src, dst)
            written.append(dst)
    for name in WEIGHTS_BY_CLASS[tier_cls]:
        src = artifact / name
        if src.is_file():
            dst = out / "artifact" / name
            shutil.copy2(src, dst)
            written.append(dst)
    for name in include or []:
        src = artifact / name
        if not src.is_file():
            _refuse(f"--include {name}: no such file in {artifact}")
        dst = out / "artifact" / name
        shutil.copy2(src, dst)
        written.append(dst)

    # FIGURES, with their captions. A figure path is resolved against the CWD, not the artifact
    # directory, because the canonical home of a phase figure is its stem and a bundle is built
    # from the artifact directory one level in.
    figure_pairs: List[Tuple[Path, Optional[Path]]] = []
    if figures:
        (out / "figures").mkdir()
    _copy_figures(figures, out, written, figure_pairs)

    # THE REPORT. Separate from --figure and from --include, because neither could carry it:
    # --include resolves inside the artifact directory, and a methodology report lives in
    # use_cases/<Case>/reports/<stem>/; --figure copies one loose image into figures/. Both bundles
    # shipped before this existed had their report copied in BY HAND after packaging, which put it
    # outside the manifest -- see the note there. Resolved against the CWD, like --figure.
    report_files: List[Path] = []
    if report:
        src = Path(report)
        if not src.exists():
            _refuse(f"--report {report}: no such file or directory")
        if src.is_dir():
            # A report folder also holds its BUILD machinery -- a pdf build script, a LaTeX
            # header, a figure-provenance manifest. Those are for the author, not the reviewer,
            # and shipping them makes the bundle look like a source tree. Filter to what is read,
            # and SAY what was left behind rather than dropping it silently.
            srcs = sorted(f for f in src.iterdir()
                          if f.is_file() and f.suffix.lower() in REPORT_SUFFIXES)
            skipped = sorted(f.name for f in src.iterdir()
                             if f.is_file() and f.suffix.lower() not in REPORT_SUFFIXES)
            if skipped:
                print(f"report   : skipped {len(skipped)} non-report file(s): {', '.join(skipped)}")
        else:
            srcs = [src]
        if not srcs:
            _refuse(f"--report {report}: no readable report files "
                    f"({', '.join(sorted(REPORT_SUFFIXES))}) in {src}")
        (out / "report").mkdir()
        for f in srcs:
            dst = out / "report" / f.name
            shutil.copy2(f, dst)
            written.append(dst)                  # <- so the MANIFEST covers it
            report_files.append(dst)

    pkg = out / "models" / "surrogate"
    pkg.mkdir(parents=True)
    stub = out / "models" / "__init__.py"
    stub.write_text(MODELS_STUB)
    written.append(stub)
    for src in sorted((REPO / "models" / "surrogate").glob("*.py")):
        dst = pkg / src.name
        shutil.copy2(src, dst)
        written.append(dst)

    loader = out / "load_surrogate.py"
    loader.write_text(LOADER)
    written.append(loader)

    env = _read_json(out / "artifact" / "environment.json")
    promotion = _read_json(out / "artifact" / "promotion.json")
    readme = out / "README.md"
    readme.write_text(_readme(artifact, spec_d, tier_cls, acceptance, promotion, env,
                              sorted(written), out, figure_pairs, report_files))
    written.append(readme)

    manifest = out / "MANIFEST.sha256"
    manifest.write_text("".join(
        f"{_sha256(f)}  {f.relative_to(out)}\n" for f in sorted(written)))

    if make_tar:
        tar = out.with_suffix(out.suffix + ".tar.gz") if out.suffix else Path(str(out) + ".tar.gz")
        with tarfile.open(tar, "w:gz") as tf:
            tf.add(out, arcname=out.name)
        print(f"tarball  : {tar}  ({_human_bytes(tar.stat().st_size)})")

    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("artifact", help="a saved surrogate directory (holds spec.json + tier.json)")
    ap.add_argument("--out", required=True, help="bundle directory to create")
    ap.add_argument("--allow-unpromoted", action="store_true",
                    help="package an unpromoted artifact FOR REVIEW; stamped in the README")
    ap.add_argument("--include", action="append", default=[],
                    help="extra file from the artifact dir (repeatable), e.g. a held-out array")
    ap.add_argument("--figure", action="append", default=[],
                    help="a figure to ship for REVIEW (repeatable), path relative to the CWD. Its "
                         "caption is copied too when one sits beside it")
    ap.add_argument("--report", help="the methodology report to ship: a DIRECTORY (its .md/.pdf/.docx and "
                                     "figures are copied flat into report/, build machinery is "
                                     "skipped and named) or a single file; path relative to the "
                                     "CWD. Covered by MANIFEST.sha256, unlike anything added "
                                     "after packaging")
    ap.add_argument("--tar", action="store_true", help="also write <out>.tar.gz")
    ap.add_argument("--force", action="store_true", help="overwrite an existing bundle directory")
    a = ap.parse_args(argv)

    out = package(Path(a.artifact), Path(a.out), allow_unpromoted=a.allow_unpromoted,
                  include=a.include, figures=a.figure, report=a.report,
                  make_tar=a.tar, force=a.force)
    total = sum(f.stat().st_size for f in out.rglob("*") if f.is_file())
    print(f"bundle   : {out}  ({_human_bytes(total)})")
    print(f"verify   : cd {out} && python load_surrogate.py")
    return OK


if __name__ == "__main__":
    raise SystemExit(main())
