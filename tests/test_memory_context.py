"""Tests for the read-side gate: MemoryManager.get_relevant_context(verified_only=...)
(G6). With verified_only=True, only verified discoveries reach the formatted context —
the read-side complement to the write gate. See memory/dev_logs/20260617b_* and Q4 in
20260519f."""
from memory.manager import MemoryManager


def test_get_relevant_context_verified_only_filters_discoveries(tmp_path):
    m = MemoryManager(str(tmp_path), write_mode="interactive")
    # curated -> verified True; auto_discovered -> verified False
    m.add_discovery("curated_one", "desc", "mech", ["leaf_pft7"], source="curated")
    m.add_discovery("auto_one", "desc", "mech", ["leaf_pft7"], source="auto_discovered")

    both = m.get_relevant_context(targets=["leaf_pft7"], verified_only=False)
    only = m.get_relevant_context(targets=["leaf_pft7"], verified_only=True)

    # default: both surface
    assert "curated_one" in both
    assert "auto_one" in both
    # verified_only: only the verified discovery survives
    assert "curated_one" in only
    assert "auto_one" not in only


def test_get_relevant_context_default_is_unfiltered(tmp_path):
    m = MemoryManager(str(tmp_path), write_mode="interactive")
    m.add_discovery("auto_one", "desc", "mech", ["leaf_pft7"], source="auto_discovered")
    # default call (no verified_only) keeps the unverified discovery — backward compatible
    assert "auto_one" in m.get_relevant_context(targets=["leaf_pft7"])


# ---------------------------------------------------------------------------
# The renderer must emit the ACTIONABLE half of a discovery (2026-08-15)
# ---------------------------------------------------------------------------
def test_action_field_is_rendered_into_the_context(tmp_path):
    """A discovery's `action` says what to DO about it, and the renderer dropped it.

    Not an edge case: every discovery in every populated store carries `action` (25 of 25
    across memory/gained_knowledge, memory/ecosim and the BioCON case) and none carries the
    `implications`/`do_not_repeat` pair that add_discovery() writes and the renderer expected.
    So the stores and the retrieval path were on different schemas and the actionable half of
    the knowledge base was unreachable: curated lessons arrived as statements of fact with
    their instructions silently removed.
    """
    import json, pathlib
    store = tmp_path / "discoveries.json"
    store.write_text(json.dumps({"discoveries": [{
        "id": "d1", "description": "desc", "mechanism": "mech", "affects": ["Fs"],
        "action": "SCORE-IT-THIS-EXACT-WAY", "source": "logs/some_log.md",
        "confidence": 1.0, "verified": "2026-08-15"}]}))
    out = MemoryManager(str(tmp_path)).get_relevant_context(targets=["Fs"])
    assert "SCORE-IT-THIS-EXACT-WAY" in out, (
        f"the instruction must reach the agent, not just the description:\n{out}")
    assert "logs/some_log.md" in out, f"provenance must travel with the claim:\n{out}"


def test_every_curated_store_uses_a_schema_the_renderer_can_emit():
    """Binds the STORES to the RENDERER, so the two cannot drift apart again silently.

    The previous drift was invisible because both halves worked in isolation: the stores were
    valid JSON and the renderer produced valid output. Only the join was broken.
    """
    import json, pathlib
    repo = pathlib.Path(__file__).resolve().parents[1]
    renderable = {"description", "mechanism", "affects", "affects_pfts",
                  "implications", "do_not_repeat", "action", "source"}
    checked = 0
    for rel in ("memory/gained_knowledge/discoveries.json",
                "memory/ecosim/gained_knowledge/discoveries.json",
                "use_cases/EcoSIM_BioCON/memory/gained_knowledge/discoveries.json"):
        p = repo / rel
        if not p.is_file():
            continue
        ds = json.loads(p.read_text()).get("discoveries", [])
        ds = list(ds.values()) if isinstance(ds, dict) else ds
        for d in [x for x in ds if isinstance(x, dict)]:
            checked += 1
            assert renderable & set(d), (
                f"{rel}: discovery {d.get('id')} carries no field the renderer emits "
                f"({sorted(d)}), so it would retrieve as an empty entry")
    assert checked >= 20, f"expected the populated stores; only inspected {checked}"
