"""The active profile must decide the ChromaDB COLLECTION, not just the directory.

`_resolve_rag_paths_from_env` always resolved the persist DIRECTORY per profile, but nothing
resolved the collection NAME inside it — so every adapter model opened FATESVectorStore's
default `fates_knowledge`, ChromaDB's `get_or_create` MANUFACTURED an empty collection of
that name, and the reasoning layer received ZERO vector chunks while the real index sat right
beside it. The graph layer still answered, so it read as thin recall rather than a miss.

Measured before the fix (20260806b Problem 2): api-43-1 → fates_knowledge 6328 (matched, so
FATES worked and hid the bug) · ecosim-2dea74d9 → ecosim_knowledge 1904 · pflotran-157a26f7 →
pflotran_knowledge 1374, the last two both retrieving 0.

Run: ~/a2mc_env/bin/python -m pytest tests/test_rag_collection_routing.py -q
"""
from __future__ import annotations

import json
import os
import sys
from importlib import reload
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

MILESTONES = REPO / "rag" / "milestones.json"


def _registry() -> dict:
    return json.loads(MILESTONES.read_text())["milestones"]


# ---------------------------------------------------------------- the registry contract

def test_every_profile_declares_a_collection_name():
    """A profile without one falls back to the FATES default — the original bug."""
    missing = [p for p, m in _registry().items() if not m.get("collection_name")]
    assert not missing, (
        f"profiles with no collection_name: {missing}. Without it the retriever opens "
        f"`fates_knowledge` and an adapter silently gets an empty collection.")


def test_adapter_profiles_do_not_claim_the_fates_collection():
    """Two profiles sharing one collection name in DIFFERENT dirs is fine; an ADAPTER
    claiming `fates_knowledge` is the bug restated as configuration."""
    for prof, meta in _registry().items():
        if meta.get("adapter"):
            assert meta["collection_name"] != "fates_knowledge", (
                f"{prof} is an adapter profile but claims the FATES collection")


# ---------------------------------------------------------------- resolution

@pytest.mark.parametrize("profile", sorted(_registry()))
def test_resolver_returns_the_registered_name(profile, monkeypatch):
    monkeypatch.setenv("A2MC_RAG_ACTIVE", profile)
    import rag.hybrid_retriever as hr
    reload(hr)
    assert hr._resolve_collection_from_env() == _registry()[profile]["collection_name"]


def test_resolver_returns_none_for_an_unregistered_profile(monkeypatch):
    """None means 'keep FATESVectorStore's own default' — the historical behaviour, so an
    unknown profile degrades exactly as before rather than crashing."""
    monkeypatch.setenv("A2MC_RAG_ACTIVE", "not-a-registered-profile")
    import rag.hybrid_retriever as hr
    reload(hr)
    assert hr._resolve_collection_from_env() is None


# ---------------------------------------------------------------- the guard

def test_missing_collection_raises_instead_of_being_manufactured():
    """`get_or_create` is the wrong verb on the READ path: an auto-created empty collection
    answers every query with silence, which reads as 'no answer' rather than 'wrong name'."""
    pytest.importorskip("chromadb")
    from rag.vector_store import FATESVectorStore
    persist = REPO / "rag" / "chroma_db" / "pflotran-157a26f7"
    if not (persist / "chroma.sqlite3").exists():
        pytest.skip("pflotran index not present in this checkout")
    with pytest.raises(ValueError, match="does not exist"):
        FATESVectorStore(persist_dir=str(persist),
                         collection_name="definitely_not_a_real_collection",
                         require_existing=True)


def test_require_existing_defaults_off_so_builders_still_create():
    """Builders MUST keep create semantics; only the retriever opts in. A default of True
    would break every build script."""
    import inspect
    from rag.vector_store import FATESVectorStore
    assert inspect.signature(FATESVectorStore.__init__).parameters[
        "require_existing"].default is False


# ---------------------------------------------------------------- end to end

@pytest.mark.parametrize("profile", sorted(_registry()))
def test_retriever_opens_the_right_non_empty_collection(profile, monkeypatch):
    """The property that was actually broken: a DEFAULT-constructed HybridRetriever reaches
    the profile's real index. Before the fix both adapters returned 0 here."""
    pytest.importorskip("chromadb")
    persist = REPO / "rag" / "chroma_db" / profile
    if not (persist / "chroma.sqlite3").exists():
        pytest.skip(f"{profile} index not present in this checkout")
    monkeypatch.setenv("A2MC_RAG_ACTIVE", profile)
    monkeypatch.delenv("A2MC_RAG_DIR", raising=False)
    import rag.hybrid_retriever as hr
    reload(hr)
    r = hr.HybridRetriever(auto_build=False)
    assert r.collection_name == _registry()[profile]["collection_name"]
    assert r.vector_retriever.vector_store.collection.count() > 0, (
        f"{profile} resolved to an EMPTY collection — the manufactured-collection bug")
