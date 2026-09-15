"""Packaging a surrogate into something loadable off the repo.

The contract has two halves and both are tested by asserting a REFUSAL:

  * the bundle must actually LOAD in a process that cannot see A2MC, which is the whole point and
    which the one non-obvious step (a stub `models/__init__.py`) exists to make true;
  * packaging is handing the artifact to someone, so the promotion gate applies here as it does in
    `tools/promote_surrogate.py`.

The load test runs a SUBPROCESS with the repo removed from the path. Testing it in-process would
pass on the repo's own `models.surrogate` and prove nothing.
"""
from __future__ import annotations

import ast
import json
import os
import subprocess
import sys
from pathlib import Path

import numpy as np
import pytest

REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from models.surrogate.spec import Provenance, SurrogateSpec, TargetSpec   # noqa: E402
from models.surrogate.tiers import S1Surrogate                            # noqa: E402
from tools.package_surrogate import WEIGHTS_BY_CLASS, package             # noqa: E402


def _artifact(tmp_path, promoted=True, acceptance=True):
    rng = np.random.default_rng(0)
    X = rng.uniform(0, 1, size=(80, 3))
    Y = (X @ np.array([2.0, -1.0, 0.5]))[:, None] + 0.3
    spec = SurrogateSpec(
        name="pkg_fixture", tier="S1", use_mode="offline_search",
        input_names=("a", "b", "c"), input_lower=(0.0,) * 3, input_upper=(1.0,) * 3,
        targets=[TargetSpec("y", observed=1.0)],
        provenance=Provenance(model="test", model_commit="deadbeef",
                              scoring_convention="fixture", created="2026-09-13"))
    m = S1Surrogate(spec, learner="ridge", alpha=0.1)
    m.fit(X, Y)
    d = tmp_path / "artifact"
    m.save(d)
    if acceptance:
        (d / "acceptance.json").write_text(json.dumps(
            {"passed": True, "summary": "fixture", "split_kind": "random hold-out"}))
    if promoted:
        raw = (d / "acceptance.json").read_bytes()
        import hashlib
        (d / "promotion.json").write_text(json.dumps(
            {"promoted": True, "promoted_at": "2026-09-13T00:00:00", "reviewed_by": "test",
             "basis": "fixture", "acceptance_sha": hashlib.sha256(raw).hexdigest()[:16],
             "metrics_passed": True, "forced": False, "use_mode": "offline_search"}))
    return d


# --------------------------------------------------------------------------------------------
# it produces something that LOADS
# --------------------------------------------------------------------------------------------

def test_the_bundle_loads_in_a_process_that_cannot_see_A2MC(tmp_path):
    """THE test. A bundle that needs the repo is not a bundle."""
    art = _artifact(tmp_path)
    out = package(art, tmp_path / "bundle")

    env = dict(os.environ)
    env.pop("PYTHONPATH", None)                     # nothing may point back at the repo
    r = subprocess.run([sys.executable, "load_surrogate.py"], cwd=out, env=env,
                       capture_output=True, text=True)
    assert r.returncode == 0, f"bundle failed to load:\nSTDOUT{r.stdout}\nSTDERR{r.stderr}"
    assert "pkg_fixture" in r.stdout
    assert "midpoint prediction" in r.stdout


def test_it_ships_a_STUB_models_init_not_the_repo_one(tmp_path):
    """The one non-obvious step. A2MC's `models/__init__.py` imports the adapter registry, which a
    surrogate does not need and the bundle does not contain, so copying it breaks the import."""
    art = _artifact(tmp_path)
    out = package(art, tmp_path / "bundle")
    text = (out / "models" / "__init__.py").read_text()
    # Assert on CODE, not prose. The stub's docstring EXPLAINS the registry, so a substring search
    # for "registry" fails on the explanation; parse it instead and require no imports at all.
    tree = ast.parse(text)
    imports = [n for n in ast.walk(tree) if isinstance(n, (ast.Import, ast.ImportFrom))]
    assert imports == [], f"the bundled models/__init__.py imports something: {imports}"
    assert text != (REPO / "models" / "__init__.py").read_text(), "it copied the repo's __init__"
    assert "Namespace stub" in text


def test_the_manifest_covers_every_file_it_wrote(tmp_path):
    art = _artifact(tmp_path)
    out = package(art, tmp_path / "bundle")
    listed = {line.split("  ", 1)[1].strip()
              for line in (out / "MANIFEST.sha256").read_text().splitlines() if line.strip()}
    on_disk = {str(f.relative_to(out)) for f in out.rglob("*")
               if f.is_file() and f.name != "MANIFEST.sha256"}
    assert on_disk == listed, f"manifest and bundle disagree: {on_disk ^ listed}"


# --------------------------------------------------------------------------------------------
# it REFUSES
# --------------------------------------------------------------------------------------------

def test_it_refuses_an_UNPROMOTED_artifact_by_default(tmp_path):
    art = _artifact(tmp_path, promoted=False)
    with pytest.raises(SystemExit, match="not promoted"):
        package(art, tmp_path / "bundle")


def test_allow_unpromoted_ships_it_and_SAYS_SO_in_the_readme(tmp_path):
    art = _artifact(tmp_path, promoted=False)
    out = package(art, tmp_path / "bundle", allow_unpromoted=True)
    readme = (out / "README.md").read_text()
    assert "NOT PROMOTED" in readme
    assert "REVIEW" in readme


def test_it_refuses_an_artifact_with_no_acceptance_report(tmp_path):
    art = _artifact(tmp_path, promoted=False, acceptance=False)
    with pytest.raises(SystemExit, match="no acceptance.json"):
        package(art, tmp_path / "bundle", allow_unpromoted=True)


def test_it_refuses_a_directory_that_is_not_a_surrogate(tmp_path):
    d = tmp_path / "nope"
    d.mkdir()
    with pytest.raises(SystemExit, match="no spec.json"):
        package(d, tmp_path / "bundle")


def test_it_refuses_a_tier_with_no_packaging_recipe(tmp_path):
    """A new tier must fail here rather than ship a bundle with no weights in it."""
    art = _artifact(tmp_path)
    (art / "tier.json").write_text(json.dumps({"class": "S9Surrogate"}))
    with pytest.raises(SystemExit, match="no packaging recipe"):
        package(art, tmp_path / "bundle")


def test_it_refuses_an_artifact_whose_weights_are_missing(tmp_path):
    art = _artifact(tmp_path)
    (art / WEIGHTS_BY_CLASS["S1Surrogate"][0]).unlink()
    with pytest.raises(SystemExit, match="missing the weight file"):
        package(art, tmp_path / "bundle")


def test_it_refuses_to_overwrite_without_force_and_obeys_force(tmp_path):
    art = _artifact(tmp_path)
    out = package(art, tmp_path / "bundle")
    (out / "a_file_someone_added.txt").write_text("x")
    with pytest.raises(SystemExit, match="already exists"):
        package(art, out)
    again = package(art, out, force=True)
    assert not (again / "a_file_someone_added.txt").exists()


def test_include_refuses_a_file_that_is_not_there(tmp_path):
    art = _artifact(tmp_path)
    with pytest.raises(SystemExit, match="no such file"):
        package(art, tmp_path / "bundle", include=["not_here.npz"])


def test_large_evidence_is_EXCLUDED_unless_asked_for(tmp_path):
    """A held-out array is evidence, not payload; a 110 MB default would make bundles unusable."""
    art = _artifact(tmp_path)
    (art / "heldout.npz").write_bytes(b"0" * 4096)
    out = package(art, tmp_path / "bundle")
    assert not (out / "artifact" / "heldout.npz").exists()
    out2 = package(art, tmp_path / "bundle2", include=["heldout.npz"])
    assert (out2 / "artifact" / "heldout.npz").exists()


# --------------------------------------------------------------------------------------------
# figures — a REVIEW bundle that shows the reviewer nothing asks them to audit an unseen number
# --------------------------------------------------------------------------------------------

def _figure(tmp_path, name="R1b_thing.png", caption=True):
    """A figure in a phase-results-shaped folder, i.e. NOT inside the artifact directory."""
    stem = tmp_path / "stem"
    stem.mkdir(exist_ok=True)
    fig = stem / name
    fig.write_bytes(b"\x89PNG\r\n\x1a\n" + b"0" * 128)
    if caption:
        (stem / f"caption_{fig.stem}.md").write_text(
            "# Figure: the thing\n\n**Three of five meet the bar.** How to read it: bars are targets.\n")
    return fig


def test_a_named_figure_and_its_caption_are_shipped(tmp_path):
    art = _artifact(tmp_path)
    fig = _figure(tmp_path)
    out = package(art, tmp_path / "bundle", figures=[str(fig)])
    assert (out / "figures" / "R1b_thing.png").is_file()
    assert (out / "figures" / "caption_R1b_thing.md").is_file(), "the caption beside it was dropped"


def test_the_readme_EMBEDS_the_figure_and_quotes_its_finding(tmp_path):
    """A figure listed but not shown is a filename, which is what the bundle already had."""
    art = _artifact(tmp_path)
    fig = _figure(tmp_path)
    out = package(art, tmp_path / "bundle", figures=[str(fig)])
    readme = (out / "README.md").read_text()
    assert "![](figures/R1b_thing.png)" in readme
    assert "Three of five meet the bar" in readme, "the caption's finding is not quoted"


def test_a_figure_with_no_caption_is_shipped_and_SAID_to_have_none(tmp_path):
    art = _artifact(tmp_path)
    fig = _figure(tmp_path, caption=False)
    out = package(art, tmp_path / "bundle", figures=[str(fig)])
    assert (out / "figures" / "R1b_thing.png").is_file()
    assert "No caption file accompanied this figure" in (out / "README.md").read_text()


def test_a_missing_figure_is_REFUSED(tmp_path):
    """Silently skipping it would ship a bundle whose README promises evidence it lacks."""
    art = _artifact(tmp_path)
    with pytest.raises(SystemExit, match="no such file"):
        package(art, tmp_path / "bundle", figures=[str(tmp_path / "nope.png")])


def test_figures_are_covered_by_the_manifest(tmp_path):
    art = _artifact(tmp_path)
    fig = _figure(tmp_path)
    out = package(art, tmp_path / "bundle", figures=[str(fig)])
    listed = {line.split("  ", 1)[1].strip()
              for line in (out / "MANIFEST.sha256").read_text().splitlines() if line.strip()}
    assert "figures/R1b_thing.png" in listed
    assert "figures/caption_R1b_thing.md" in listed


def test_no_figures_means_no_figures_directory(tmp_path):
    """The default bundle is unchanged; figures are opt-in."""
    art = _artifact(tmp_path)
    out = package(art, tmp_path / "bundle")
    assert not (out / "figures").exists()
    assert "## Figures" not in (out / "README.md").read_text()


def test_the_BARE_caption_md_convention_is_found(tmp_path):
    """54 of this repo's phase_results folders use a bare `caption.md`; a stem-matching rule alone
    finds none of them, which is what happened on the first real bundle."""
    art = _artifact(tmp_path)
    fig = _figure(tmp_path, caption=False)
    (fig.parent / "caption.md").write_text("# Cap\n\n**The bare convention.** Axes are targets.\n")
    out = package(art, tmp_path / "bundle", figures=[str(fig)])
    assert (out / "figures" / "caption.md").is_file()
    assert "The bare convention" in (out / "README.md").read_text()


def test_a_SINGLE_topic_caption_is_matched_even_when_its_name_does_not_match_the_figure(tmp_path):
    """`caption_kgml.md` beside `R1b_kgml_emulator.png` is the real case."""
    art = _artifact(tmp_path)
    fig = _figure(tmp_path, name="R1b_kgml_emulator.png", caption=False)
    (fig.parent / "caption_kgml.md").write_text("# Cap\n\n**Named for the subject.** Not the file.\n")
    out = package(art, tmp_path / "bundle", figures=[str(fig)])
    assert (out / "figures" / "caption_kgml.md").is_file()


def test_AMBIGUOUS_captions_ship_NONE_rather_than_the_wrong_one(tmp_path):
    """A caption describing a different figure is worse than no caption, because the README
    presents it as describing what the reader is looking at."""
    art = _artifact(tmp_path)
    fig = _figure(tmp_path, name="R1b_kgml_emulator.png", caption=False)
    (fig.parent / "caption_alpha.md").write_text("# A\n\n**Alpha.**\n")
    (fig.parent / "caption_beta.md").write_text("# B\n\n**Beta.**\n")
    out = package(art, tmp_path / "bundle", figures=[str(fig)])
    assert not (out / "figures" / "caption_alpha.md").exists()
    assert not (out / "figures" / "caption_beta.md").exists()
    assert "No caption file accompanied this figure" in (out / "README.md").read_text()


def test_the_quoted_lead_is_the_FINDING_not_the_captions_own_image_embed(tmp_path):
    """An A2MC caption opens with `![](fig.png)` per the empty-alt-text convention. A naive
    first-non-heading-line rule quotes that image tag at the reader, which is what the first real
    bundle's README did."""
    art = _artifact(tmp_path)
    fig = _figure(tmp_path, name="R1b_kgml_emulator.png", caption=False)
    (fig.parent / "caption_kgml.md").write_text(
        "![](R1b_kgml_emulator.png)\n\n"
        "**Figure 1. Three of five targets meet the bar.** Panel (a) shows one held-out case.\n")
    out = package(art, tmp_path / "bundle", figures=[str(fig)])
    readme = (out / "README.md").read_text()
    assert "> Figure 1. Three of five targets meet the bar" in readme
    assert "> ![](" not in readme, "the README quotes an image embed as the finding"
