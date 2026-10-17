"""tools/check_kb_readme.py: a model's knowledge-base README records the commit its knowledge base describes.

visibility: public

The first two tests are positive controls: a README that omits the live knowledge-base commit, or a
patch in its history, must be reported, or every pass below is vacuous.
"""
import json
from pathlib import Path

from tools.check_kb_readme import check_readme, kb_models, touched_models

ROOT = Path(__file__).resolve().parent.parent

MS = {
    "m-aaaaaaaa": {"adapter": "m", "knowledge_base_dir": "docs/m-knowledge-base", "legacy": True,
                   "model_commit_built": "aaaaaaaa" + "0" * 32},
    "m-bbbbbbbb": {"adapter": "m", "knowledge_base_dir": "docs/m-knowledge-base",
                   "model_commit_built": "bbbbbbbb" + "0" * 32,
                   "patches": [{"commit": "cccccccc" + "0" * 32}]},
    "api-43-1": {"fates_commit_built": "e027a40"},
}
INFO = kb_models(MS)["m"]
GOOD = """# M

## Current working version of the model

Profile `m-bbbbbbbb`, knowledge base at `cccccccc`.

## Update history

| cccccccc | patch |
| bbbbbbbb | new profile |
| aaaaaaaa | first |
"""


def test_missing_live_kb_commit_is_reported():
    assert check_readme("m", INFO, GOOD.replace("knowledge base at `cccccccc`", "knowledge base at `bbbbbbbb`"))


def test_missing_patch_in_history_is_reported():
    errs = check_readme("m", INFO, GOOD.replace("| cccccccc | patch |\n", ""))
    assert any("cccccccc" in e and "patch" in e for e in errs)


def test_in_step_readme_passes():
    assert check_readme("m", INFO, GOOD) == []


def test_live_profile_name_and_sections_are_required():
    assert any("live profile" in e for e in check_readme("m", INFO, GOOD.replace("`m-bbbbbbbb`", "it")))
    assert any("Update history" in e for e in check_readme("m", INFO, GOOD.replace("## Update history", "## History")))


def test_legacy_profile_need_not_be_current():
    # the legacy base must be in the history, but not in the current-version section
    assert check_readme("m", INFO, GOOD) == []
    assert any("aaaaaaaa" in e for e in check_readme("m", INFO, GOOD.replace("| aaaaaaaa | first |\n", "")))


def test_fates_milestones_are_out_of_scope():
    assert set(kb_models(MS)) == {"m"}


def test_touched_models_by_path_and_by_registry_entry():
    models = kb_models(MS)
    assert touched_models(["docs/m-knowledge-base/wiki/page.md"], models, MS, MS) == {"m"}
    assert touched_models(["models/m/curated_seed.yaml"], models, MS, MS) == {"m"}
    assert touched_models(["rag/graphs/m-bbbbbbbb.json"], models, MS, MS) == {"m"}
    assert touched_models(["docs/m-knowledge-base/README.md"], models, MS, MS) == set()   # the record alone
    assert touched_models(["tools/x.py"], models, MS, MS) == set()
    new = json.loads(json.dumps(MS))
    new["m-bbbbbbbb"]["patches"].append({"commit": "dddddddd" + "0" * 32})
    assert touched_models(["rag/milestones.json"], models, MS, new) == {"m"}


def test_the_ecosim_readme_is_in_step_and_a_dropped_patch_fails():
    ms = json.loads((ROOT / "rag/milestones.json").read_text())["milestones"]
    info = kb_models(ms)["ecosim"]
    text = (ROOT / info["dir"] / "README.md").read_text()
    assert check_readme("ecosim", info, text) == []
    patch = [p["commit"][:8] for v in info["profiles"].values() for p in (v.get("patches") or [])]
    assert patch, "the live EcoSIM profile is expected to carry a patch"
    assert check_readme("ecosim", info, text.replace(patch[-1], "xxxxxxxx"))
