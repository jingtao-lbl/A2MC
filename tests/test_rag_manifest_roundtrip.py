"""The RAG milestone registry must survive a load -> save cycle unchanged.

`rag/milestones.json` is the VERSION-ASSOCIATION registry: A2MC detects the user's model commits
and matches them against these entries to select a RAG profile. `Milestone` is a FATES-shaped
TYPED VIEW of one entry, and the registry stopped being FATES-only when the adapter profiles
(`ecosim-*`, `pflotran-*`) were added to the JSON without the dataclass being extended.

Before 2026-08-27 that made `load -> save` lossy in both directions: it dropped every key the class
does not model -- 10 per adapter profile, including `adapter`, `model_commit_built` and
`param_file`, plus `expected_counts` on EVERY profile, which is what
`tools/check_rag_index_committed.py` reads -- and it INVENTED ~14 empty `fates_*` keys on an
adapter entry, turning a PFLOTRAN milestone into a malformed FATES-looking one.

Nothing had fired only because both adapter builders bypass the class and read the JSON directly
(`build_ecosim_rag.py:59`, `build_pflotran_rag.py:67`). The workaround hid the defect rather than
avoiding it, while `rag_manifest.save_manifest` and `scripts/rag_bump.py` kept a live write path
through the class.

These tests are written against the COMMITTED registry, not a fixture, because the property that
matters is about the real file: a fixture would keep passing while the registry grew a key the
class cannot hold.
"""
import json
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from tools.rag_manifest import Milestone, load_manifest, save_manifest  # noqa: E402

MANIFEST = REPO / "rag" / "milestones.json"


def _bodies():
    if not MANIFEST.is_file():
        pytest.skip("rag/milestones.json absent")
    return json.loads(MANIFEST.read_text())["milestones"]


def test_every_committed_profile_round_trips_exactly():
    """THE property. Same keys, same order, same values, for every profile in the registry.

    Parameterised over the real file rather than a fixed list, so a newly registered model is
    covered the moment it lands instead of when someone remembers to add it here.
    """
    for name, body in _bodies().items():
        out = Milestone.from_dict(name, body).to_dict()
        assert set(out) == set(body), f"{name}: key set changed; lost={set(body)-set(out)}, added={set(out)-set(body)}"
        assert list(out) == list(body), f"{name}: key ORDER changed, which makes a save a huge spurious diff"
        assert out == body, f"{name}: values changed"


def test_an_adapter_profile_keeps_its_adapter_identity():
    """The specific loss that motivated this: which model, which commit, which parameter surface.

    Asserted by name rather than only through the generic round-trip, so a future refactor that
    silently drops exactly these reads as a failure about ADAPTER IDENTITY, not a diff.
    """
    bodies = _bodies()
    adapters = {n: b for n, b in bodies.items() if b.get("adapter")}
    if not adapters:
        pytest.skip("no adapter profile registered")
    for name, body in adapters.items():
        out = Milestone.from_dict(name, body).to_dict()
        for key in ("adapter", "model_commit_built", "model_wiki_subdir",
                    "param_file", "param_file_format", "knowledge_base_dir", "upstream_url"):
            if key in body:
                assert out.get(key) == body[key], f"{name}: lost or changed {key!r}"


def test_an_adapter_profile_does_not_GROW_fates_keys():
    """The other half, and the one a 'preserve unknown keys' fix alone does not give you.

    A naive fix keeps the extras and still emits every modelled field, so a PFLOTRAN entry
    acquires `fates_api_epoch`, `fates_tag_built`, `fates_param_file_format` and friends. That is
    corruption in the opposite direction: the entry starts to look like a FATES milestone.
    """
    bodies = _bodies()
    for name, body in bodies.items():
        if not body.get("adapter"):
            continue
        out = Milestone.from_dict(name, body).to_dict()
        grew = sorted(k for k in out if k.startswith(("fates_", "elm_")) and k not in body)
        assert not grew, f"{name} acquired FATES/ELM keys it never had: {grew}"


def test_expected_counts_survives_on_every_profile():
    """`check_rag_index_committed.py` reads this. Losing it disarms a committed guard silently."""
    for name, body in _bodies().items():
        if "expected_counts" not in body:
            continue
        out = Milestone.from_dict(name, body).to_dict()
        assert out.get("expected_counts") == body["expected_counts"], \
            f"{name}: expected_counts lost -- check_rag_index_committed would stop checking"


def test_a_full_load_then_save_leaves_the_file_unchanged(tmp_path):
    """End to end through the real save path, which is what `rag_bump.py` reaches."""
    if not MANIFEST.is_file():
        pytest.skip("rag/milestones.json absent")
    before = MANIFEST.read_text()
    p = tmp_path / "milestones.json"
    p.write_text(before)
    save_manifest(load_manifest(p), p)
    assert json.loads(p.read_text())["milestones"] == json.loads(before)["milestones"]


def test_a_milestone_built_in_code_still_emits_its_modelled_fields():
    """The non-loaded path must keep working: no `_source_keys`, so emit the full modelled set."""
    m = Milestone(profile_name="new-1", description="d", fates_api_epoch="43.1")
    out = m.to_dict()
    assert out["description"] == "d" and out["fates_api_epoch"] == "43.1"
    assert "covers_sci_tags" in out and "canonical" in out


def test_a_modelled_field_CHANGED_in_code_is_written_back():
    """Preserving the source must not freeze it. An edit through the typed view has to persist,
    or `rag_bump` would silently no-op."""
    bodies = _bodies()
    name, body = next(iter(bodies.items()))
    ms = Milestone.from_dict(name, body)
    ms.notes = "edited-by-test"
    assert ms.to_dict()["notes"] == "edited-by-test"


def test_a_modelled_field_ADDED_in_code_is_written_back():
    """A field absent from the source but SET in code must appear -- distinguished from a field
    merely sitting at its default, which must not."""
    bodies = _bodies()
    adapters = [b for b in bodies.values() if b.get("adapter")]
    if not adapters:
        pytest.skip("no adapter profile registered")
    body = adapters[0]
    ms = Milestone.from_dict("x", body)
    assert "fates_tag_built" not in ms.to_dict(), "a default must not be emitted"
    ms.fates_tag_built = "sci.1.2.3_api.43.1.0"
    assert ms.to_dict()["fates_tag_built"] == "sci.1.2.3_api.43.1.0"
