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
import warnings
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

def _child_env() -> dict:
    """Environment for the load-the-bundle subprocess: no repo on the path, and no accelerator.

    PYTHONPATH is dropped because that is the point of the test -- a bundle that needs A2MC on the
    path is not a bundle.

    CUDA IS HIDDEN, and that is a HERMETICITY fix rather than a proven cure. On 2026-09-22 this
    file failed twice on the first of two identical runs on a Perlmutter login node, with the child
    raising an accelerator error while loading `libtorch_cpu.so`, and passed 33/33 when run alone;
    nothing in the bundle changed between the runs. The child never needed a GPU -- it loads a
    small artifact and prints a prediction -- so taking the accelerator out of its environment
    removes a dependency the test never meant to exercise, and with it a class of failure that
    reports as "the bundle does not load" when the bundle is fine. It is recorded as MITIGATION:
    the underlying loader race was not reproduced and is not understood.
    """
    env = dict(os.environ)
    env.pop("PYTHONPATH", None)
    env["CUDA_VISIBLE_DEVICES"] = ""
    return env


def test_the_bundle_loads_in_a_process_that_cannot_see_A2MC(tmp_path):
    """THE test. A bundle that needs the repo is not a bundle."""
    art = _artifact(tmp_path)
    out = package(art, tmp_path / "bundle")

    env = _child_env()
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


def _structured_artifact(tmp_path):
    """A FieldEmulator: a torch weight file, a class outside the four tiers, and modules (`fields`,
    `_nn`) that a bundle built before these architectures existed would not have carried.
    """
    pytest.importorskip("torch")
    from models.surrogate.fields import FieldEmulator
    rng = np.random.default_rng(0)
    X = rng.uniform(0, 1, size=(16, 2))
    x = np.linspace(0, 1, 12)
    F = (X[:, [0]] * np.sin(np.pi * x[None, :]))[:, None, :].astype("f4")
    spec = SurrogateSpec(
        name="field_pkg_fixture", tier="S2", use_mode="online_inference",
        input_names=("a", "b"), input_lower=(0.0,) * 2, input_upper=(1.0,) * 2,
        targets=[TargetSpec("u")],
        provenance=Provenance(model="test", model_commit="deadbeef",
                              scoring_convention="fixture", created="2026-09-16"))
    m = FieldEmulator(spec, grid_shape=(12,), arch="fno", width=8, depth=2, modes=3, epochs=2,
                      patience=5)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")               # a two-epoch fixture is not meant to converge
        m.fit(X, fields=F)
    d = tmp_path / "field_artifact"
    m.save(d)
    (d / "acceptance.json").write_text(json.dumps({"passed": False, "summary": "fixture"}))
    return d


def test_a_STRUCTURED_architecture_bundle_loads_in_a_process_that_cannot_see_A2MC(tmp_path):
    """The new families must ship their weights AND the modules that rebuild them, and load through
    the generic loader's class dispatch with the repo off the path.
    """
    art = _structured_artifact(tmp_path)
    out = package(art, tmp_path / "bundle", allow_unpromoted=True)
    assert (out / "artifact" / "field.pt").is_file()
    assert (out / "models" / "surrogate" / "fields.py").is_file()
    assert (out / "models" / "surrogate" / "_nn.py").is_file()
    r = subprocess.run([sys.executable, "load_surrogate.py"], cwd=out, env=_child_env(),
                       capture_output=True, text=True)
    assert r.returncode == 0, f"bundle failed to load:\nSTDOUT{r.stdout}\nSTDERR{r.stderr}"
    assert "field_pkg_fixture" in r.stdout and "tier=S2" in r.stdout


def _kgml_artifact(tmp_path):
    """A KGMLEmulator: its spec declares tier S3, so only the class name in `tier.json` separates it
    from an `S3Surrogate`, and its weights and module (`sequence`) differ from that class's.
    """
    pytest.importorskip("torch")
    from models.surrogate.sequence import KGMLEmulator
    rng = np.random.default_rng(0)
    X = rng.uniform(0, 1, size=(12, 2))
    drivers = rng.uniform(0, 1, size=(20, 1)).astype("f4")
    T = (X[:, [0]] * drivers[:, 0][None, :])[:, None, :].astype("f4")
    spec = SurrogateSpec(
        name="kgml_pkg_fixture", tier="S3", use_mode="online_inference",
        input_names=("a", "b"), input_lower=(0.0,) * 2, input_upper=(1.0,) * 2,
        targets=[TargetSpec("y")],
        provenance=Provenance(model="test", model_commit="deadbeef",
                              scoring_convention="fixture", created="2026-09-16"))
    m = KGMLEmulator(spec, driver_names=["q"], reduce="mean", hidden=8, layers=1, dropout=0.0,
                     epochs=1, chunk_days=10)
    m.fit(X, None, trajectories=T, drivers=drivers, verbose=False)
    d = tmp_path / "kgml_artifact"
    m.save(d)
    (d / "acceptance.json").write_text(json.dumps({"passed": False, "summary": "fixture"}))
    return d


def test_a_KGML_bundle_loads_through_the_generic_loader_in_a_process_that_cannot_see_A2MC(tmp_path):
    """The bundle's loader calls `tiers.load` for every class, so a sequence emulator must ship its
    module and reach it through the class dispatch with the repo off the path.
    """
    art = _kgml_artifact(tmp_path)
    out = package(art, tmp_path / "bundle", allow_unpromoted=True)
    assert (out / "artifact" / "kgml.pt").is_file()
    assert (out / "models" / "surrogate" / "sequence.py").is_file()
    r = subprocess.run([sys.executable, "load_surrogate.py"], cwd=out, env=_child_env(),
                       capture_output=True, text=True)
    assert r.returncode == 0, f"bundle failed to load:\nSTDOUT{r.stdout}\nSTDERR{r.stderr}"
    assert "kgml_pkg_fixture" in r.stdout and "tier=S3" in r.stdout


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


# ---------------------------------------------------------------------------
# --report: the methodology report travels WITH the bundle, and is manifested.
#
# The gap these guard, measured 2026-09-16 on two shipped bundles. Neither `--figure` (one loose
# image into figures/, resolved from the CWD) nor `--include` (a file from INSIDE the artifact
# directory) could carry a report, which lives in use_cases/<Case>/reports/<stem>/. So both bundles
# had their report copied in BY HAND after packaging, and the manifest is built from what the
# packager wrote -- leaving the EcoSIM bundle at 19 entries covering 0 of its 6 report files while
# `sha256sum -c` reported success over 19 of 25. A check that passes over a quarter of what it
# ships is the shape of [[feedback_a_check_that_cannot_fail]].
# ---------------------------------------------------------------------------

def _report_dir(tmp_path):
    """A report folder as they really are: the document, its figures, and its build machinery."""
    d = tmp_path / "reports" / "20260915a_Topic"
    d.mkdir(parents=True)
    (d / "Topic_Methodology.md").write_text("# Topic\n\n![](fig1_thing.png)\n")
    (d / "Topic_Methodology.pdf").write_bytes(b"%PDF-1.4 fake")
    (d / "Topic_Methodology.docx").write_bytes(b"PK\x03\x04 fake")
    (d / "fig1_thing.png").write_bytes(b"\x89PNG\r\n\x1a\n" + b"x" * 32)
    (d / "build_pdf.sh").write_text("#!/bin/bash\npandoc ...\n")
    (d / "pdf_header.tex").write_text("\\usepackage{booktabs}\n")
    (d / "figure_sources.tsv").write_text("fig1_thing.png\t../stem/R1_thing.png\n")
    return d


def _listed(out):
    return {line.split("  ", 1)[1].strip()
            for line in (out / "MANIFEST.sha256").read_text().splitlines() if line.strip()}


def test_the_report_is_shipped_AND_covered_by_the_manifest(tmp_path):
    """THE failure this closes: a hand-added report is outside the manifest by construction."""
    art = _artifact(tmp_path)
    out = package(art, tmp_path / "bundle", report=str(_report_dir(tmp_path)))
    listed = _listed(out)
    for name in ("Topic_Methodology.md", "Topic_Methodology.pdf",
                 "Topic_Methodology.docx", "fig1_thing.png"):
        assert (out / "report" / name).is_file(), name
        assert f"report/{name}" in listed, f"{name} shipped but NOT manifested"


def test_report_build_machinery_is_left_behind(tmp_path):
    """A bundle is for reading, not for rebuilding the document."""
    art = _artifact(tmp_path)
    out = package(art, tmp_path / "bundle", report=str(_report_dir(tmp_path)))
    for name in ("build_pdf.sh", "pdf_header.tex", "figure_sources.tsv"):
        assert not (out / "report" / name).exists(), f"{name} should not ship"


def test_what_was_skipped_is_NAMED_not_dropped_silently(tmp_path, capsys):
    """A silent filter is a hidden decision ([[feedback_no_buried_choices_in_a_menu]])."""
    art = _artifact(tmp_path)
    package(art, tmp_path / "bundle", report=str(_report_dir(tmp_path)))
    said = capsys.readouterr().out
    assert "skipped 3 non-report file(s)" in said
    for name in ("build_pdf.sh", "pdf_header.tex", "figure_sources.tsv"):
        assert name in said


def test_a_single_report_FILE_is_accepted(tmp_path):
    art = _artifact(tmp_path)
    doc = _report_dir(tmp_path) / "Topic_Methodology.pdf"
    out = package(art, tmp_path / "bundle", report=str(doc))
    assert (out / "report" / "Topic_Methodology.pdf").is_file()
    assert "report/Topic_Methodology.pdf" in _listed(out)


def test_a_missing_report_is_REFUSED(tmp_path):
    art = _artifact(tmp_path)
    with pytest.raises(SystemExit):
        package(art, tmp_path / "bundle", report=str(tmp_path / "nope"))


def test_a_report_dir_with_NO_readable_document_is_REFUSED(tmp_path):
    """Not silently an empty report/: a directory of build scripts is a mistaken path."""
    d = tmp_path / "machinery"; d.mkdir()
    (d / "build_pdf.sh").write_text("#!/bin/bash\n")
    art = _artifact(tmp_path)
    with pytest.raises(SystemExit):
        package(art, tmp_path / "bundle", report=str(d))


def test_the_readme_leads_with_the_report_and_places_it_ABOVE_figures(tmp_path):
    art = _artifact(tmp_path)
    out = package(art, tmp_path / "bundle", report=str(_report_dir(tmp_path)),
                  figures=[str(_figure(tmp_path))])
    txt = (out / "README.md").read_text()
    assert "## Report" in txt and "Read this first" in txt
    assert txt.index("## Report") < txt.index("## Figures"), "the document comes before the figures"


def test_no_report_means_no_report_directory(tmp_path):
    """The default bundle is unchanged; the report is opt-in like the figures."""
    art = _artifact(tmp_path)
    out = package(art, tmp_path / "bundle")
    assert not (out / "report").exists()
    assert "## Report" not in (out / "README.md").read_text()


def test_the_readme_WARNS_that_later_additions_escape_the_manifest(tmp_path):
    """The rule that makes the whole gap visible to a recipient, not just to us."""
    art = _artifact(tmp_path)
    out = package(art, tmp_path / "bundle")
    assert "not in it" in (out / "README.md").read_text()


# --------------------------------------------------------------------------------------------
# What a RECIPIENT reads. Every case here came from auditing a bundle already delivered
# (memory/dev_logs_adapterkit/20260913g), where the documents disagreed with each other.
# --------------------------------------------------------------------------------------------

def _readme_of(tmp_path, **kw):
    art = _artifact(tmp_path, **kw)
    out = package(art, tmp_path / "bundle", allow_unpromoted=True)
    return (out / "README.md").read_text()


def test_the_README_says_the_use_mode_is_DECLARED_not_earned_when_acceptance_failed(tmp_path):
    """`use_mode` records what a surrogate was BUILT FOR, not what it achieved.

    The delivered bundle carried `use mode online_inference` in its header while its own
    acceptance report recorded a FAIL, and the audit read the header as a claim.
    """
    art = _artifact(tmp_path, promoted=False)
    (art / "acceptance.json").write_text(json.dumps({"passed": False, "summary": "below bar"}))
    out = package(art, tmp_path / "bundle", allow_unpromoted=True)
    text = (out / "README.md").read_text()
    assert "DECLARED, NOT EARNED" in text
    assert "FAILED" in text


def test_the_README_reads_a_VERDICTS_ONLY_report(tmp_path):
    """A report serialized from the dataclass has no `passed` key, and this section printed
    nothing about it at all -- so a FAIL rendered as silence."""
    art = _artifact(tmp_path, promoted=False)
    (art / "acceptance.json").write_text(json.dumps(
        {"verdicts": {"ranking": True, "coverage": False}, "per_target": {}, "overall": {}}))
    out = package(art, tmp_path / "bundle", allow_unpromoted=True)
    assert "Acceptance: **FAILED**" in (out / "README.md").read_text()


def test_the_README_says_plainly_when_there_is_NO_verdict(tmp_path):
    art = _artifact(tmp_path, promoted=False)
    (art / "acceptance.json").write_text(json.dumps({"architecture": "kgml", "n_train": 10}))
    out = package(art, tmp_path / "bundle", allow_unpromoted=True)
    assert "NO VERDICT RECORDED" in (out / "README.md").read_text()


def test_the_README_NAMES_THE_ARCHITECTURE_not_only_the_tier(tmp_path):
    """A tier names a rung; two classes can sit on one. "Tier S3" alone read as a mislabel to a
    recipient holding a methodology report about the other S3."""
    text = _readme_of(tmp_path)
    assert "Architecture: `S1Surrogate`" in text
    assert "scalar tier" in text


def test_the_README_TELLS_THE_RECIPIENT_HOW_TO_PREDICT(tmp_path):
    """The delivered bundle loaded and then could not be used: the loader pointed at a README
    section that did not exist."""
    text = _readme_of(tmp_path)
    assert "## How to predict" in text
    assert "predict_batch" in text
    assert "input_names" in text, "the column order must be stated, not assumed"


def test_the_README_FLAGS_unstamped_provenance_fields(tmp_path):
    """The delivered bundle's provenance block was empty and the table said `_not recorded_` in
    each row, which reads as a formatting detail rather than as a missing binding."""
    text = _readme_of(tmp_path)
    assert "not recorded" in text
    assert "UNPROTECTED" in text
