#!/usr/bin/env python
"""Bundle a trained surrogate into something a person who does not have A2MC can actually load.

THE GAP THIS CLOSES. A saved surrogate is a directory of `spec.json`, `tier.json` and a pickle or a
`state_dict`. None of it loads without `models.surrogate` importable AT THAT EXACT MODULE PATH,
because the joblib blobs hold references to classes by their dotted name. So the artifact directory,
on its own, is not the deliverable: handing it to a collaborator hands them a file they cannot open.
Nothing in the module bundled the code with the weights, and the tool to do it was proposed on
2026-09-12 and never written.

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
  out   training data, held-out arrays, logs. A `kgml_heldout.npz` is 110 MB and is evidence, not
        payload; `--include` takes it if a recipient needs to re-verify.

THE PROMOTION GATE APPLIES HERE TOO. Packaging is the act of handing the surrogate to someone else,
which is exactly when `promotion.json` matters, so an unpromoted artifact is refused by default.
`--allow-unpromoted` exists because an unpromoted artifact is legitimately shared for REVIEW, and
it stamps the bundle's README so the recipient cannot mistake one for the other.

Usage::

    python tools/package_surrogate.py <artifact_dir> --out <bundle_dir> [--tar]
    python tools/package_surrogate.py <artifact_dir> --out <bundle_dir> --allow-unpromoted
    python tools/package_surrogate.py <artifact_dir> --out <bundle_dir> --include kgml_heldout.npz
    python tools/package_surrogate.py <artifact_dir> --out <bundle_dir> --figure ../R1b_fig.png

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

import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))          # so `models.surrogate` resolves to the copy in here

ARTIFACT = HERE / "artifact"


def load_bundle(strict: bool = True):
    """Return (model, spec). `strict=False` downgrades an environment mismatch to a warning."""
    from models.surrogate.spec import SurrogateSpec

    spec = SurrogateSpec.read(ARTIFACT / "spec.json")
    cls = json.loads((ARTIFACT / "tier.json").read_text())["class"]
    if cls == "KGMLEmulator":
        from models.surrogate.sequence import load_kgml
        return load_kgml(ARTIFACT, spec, strict=strict), spec
    from models.surrogate.tiers import load
    return load(ARTIFACT, strict=strict), spec


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
        print("  this tier predicts trajectories; see the bundle README for the call it needs")
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

def _caption_for(figure: Path) -> Optional[Path]:
    """The caption file beside a figure, or None when there is no unambiguous one.

    MEASURED CONVENTION, not a guess. Across this repo's `phase_results/` folders the dominant
    form is a bare `caption.md` (54 of them), with `caption_<topic>.md` used where one folder
    holds several figures. The topic is named after the SUBJECT, not the figure's filename:
    `caption_kgml.md` sits beside `R1b_kgml_emulator.png`. A stem-matching rule alone therefore
    finds nothing in the common case, which is exactly what it did on the first real bundle.

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


def _readme(artifact: Path, spec_d: Dict[str, Any], tier_cls: str,
            acceptance: Optional[Dict[str, Any]], promotion: Optional[Dict[str, Any]],
            env: Optional[Dict[str, Any]], files: List[Path], bundle: Path,
            figure_pairs: Optional[List[Tuple[Path, Optional[Path]]]] = None) -> str:
    prov = spec_d.get("provenance") or {}
    lines = [
        f"# Packaged A2MC surrogate: `{spec_d.get('name')}`",
        "",
        f"Tier **{spec_d.get('tier')}** (`{tier_cls}`), use mode **{spec_d.get('use_mode')}**, "
        f"{len(spec_d.get('input_names') or [])} inputs, "
        f"{len(spec_d.get('targets') or [])} targets.",
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
        "## Provenance: what this artifact is bound to",
        "",
        "| field | value |",
        "|---|---|",
    ]
    for k, v in prov.items():
        lines.append(f"| `{k}` | {v if v else '_not recorded_'} |")

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
        passed = acceptance.get("passed")
        if passed is not None:
            lines.append(f"Acceptance: **{'PASSED' if passed else 'FAILED'}**.")
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
              "`sha256sum -c MANIFEST.sha256`.", ""]
    return "\n".join(lines)


def package(artifact: Path, out: Path, allow_unpromoted: bool = False,
            include: Optional[List[str]] = None, figures: Optional[List[str]] = None,
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
    for name in figures or []:
        src = Path(name)
        if not src.is_file():
            _refuse(f"--figure {name}: no such file")
        dst = out / "figures" / src.name
        shutil.copy2(src, dst)
        written.append(dst)
        cap = _caption_for(src)
        if cap is not None:
            cdst = out / "figures" / cap.name
            shutil.copy2(cap, cdst)
            written.append(cdst)
        figure_pairs.append((dst, (out / "figures" / cap.name) if cap else None))

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
                              sorted(written), out, figure_pairs))
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
    ap.add_argument("--tar", action="store_true", help="also write <out>.tar.gz")
    ap.add_argument("--force", action="store_true", help="overwrite an existing bundle directory")
    a = ap.parse_args(argv)

    out = package(Path(a.artifact), Path(a.out), allow_unpromoted=a.allow_unpromoted,
                  include=a.include, figures=a.figure, make_tar=a.tar, force=a.force)
    total = sum(f.stat().st_size for f in out.rglob("*") if f.is_file())
    print(f"bundle   : {out}  ({_human_bytes(total)})")
    print(f"verify   : cd {out} && python load_surrogate.py")
    return OK


if __name__ == "__main__":
    raise SystemExit(main())
