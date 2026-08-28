"""Tests for the Tier-3 memory write gate (memory/manager.py, v2.90).

propose mode (the autonomous online agent) stages curated writes to
auto_discovered_pending.json; interactive mode (the human-in-the-loop agent) writes the
curated JSONs. See memory/dev_logs/20260612d_*. tmp_path stays under the repo tmp/ via
pytest.ini --basetemp."""
import json

from memory.manager import MemoryManager, PENDING_FILENAME


def _curated_exist(d):
    return [(d / f).exists() for f in
            ("discoveries.json", "experiments.json", "failed_approaches.json")]


def test_propose_mode_stages_not_curated(tmp_path):
    m = MemoryManager(str(tmp_path), write_mode="propose")
    m.add_discovery("x", "desc", "mech", ["leaf_pft7"], confidence=0.7)
    m.add_failed_approach("an approach", "exp1", "why", "catastrophic", [])
    m.record_experiment({"name": "exp1", "modifications": []},
                        {"targets_met": 0, "metrics": {}}, "FAILED")
    # nothing reached the curated KB
    assert _curated_exist(tmp_path) == [False, False, False]
    # all three proposals are staged
    pend = json.loads((tmp_path / PENDING_FILENAME).read_text())
    assert len(pend["pending"]) == 3
    assert {p["kind"] for p in pend["pending"]} == {"discovery", "failed_approach", "experiment"}


def test_interactive_mode_writes_curated(tmp_path):
    m = MemoryManager(str(tmp_path), write_mode="interactive")
    m.add_discovery("real", "desc", "mech", ["leaf_pft7"])
    assert (tmp_path / "discoveries.json").exists()
    assert not (tmp_path / PENDING_FILENAME).exists()
    data = json.loads((tmp_path / "discoveries.json").read_text())
    # default source is auto_discovered -> verified False; promotion (source=curated) sets it True
    assert "real" in data
    assert data["real"]["verified"] is False


def test_interactive_promote_marks_verified(tmp_path):
    m = MemoryManager(str(tmp_path), write_mode="interactive")
    m.add_discovery("curated_one", "d", "m", ["x"], source="curated")
    data = json.loads((tmp_path / "discoveries.json").read_text())
    assert data["curated_one"]["verified"] is True


def test_default_mode_is_interactive(tmp_path):
    assert MemoryManager(str(tmp_path)).write_mode == "interactive"


def test_env_overrides_mode(tmp_path, monkeypatch):
    monkeypatch.setenv("A2MC_MEMORY_WRITE_MODE", "propose")
    assert MemoryManager(str(tmp_path)).write_mode == "propose"


def test_unknown_mode_falls_back_to_interactive(tmp_path):
    assert MemoryManager(str(tmp_path), write_mode="bogus").write_mode == "interactive"


# --------------------------------------------------------------- the hole, closed 2026-08-25

def test_add_parameter_info_is_GATED(tmp_path):
    """REGRESSION. `parameters.json` was written UNCONDITIONALLY while discoveries,
    failed_approaches and experiments all routed to staging in propose mode.

    That is a hole in the write gate, not a cosmetic gap: `parameters` shapes diagnoses exactly
    the way the other three do (`get_parameter_cautions`, `check_do_not_repeat`), so an
    unattended online run could write curated parameter knowledge straight into the store the
    next cycle reasons from -- the contamination path the gate exists to close.
    """
    m = MemoryManager(str(tmp_path), write_mode="propose")
    m.add_parameter_info("CNRT", parameter_pft=[1], insight="a claim")
    assert not (tmp_path / "parameters.json").exists() or \
        json.loads((tmp_path / "parameters.json").read_text()).get("parameters", {}) == {}, \
        "propose mode must NOT write parameters.json"
    staged = json.loads((tmp_path / "auto_discovered_pending.json").read_text())["pending"]
    assert any(it["kind"] == "parameter" and it["key"] == "CNRT" for it in staged), staged


def test_add_parameter_knowledge_is_GATED(tmp_path):
    m = MemoryManager(str(tmp_path), write_mode="propose")
    m.add_parameter_knowledge("CNRT", "calibration_advice", "widen on a literature limit")
    staged = json.loads((tmp_path / "auto_discovered_pending.json").read_text())["pending"]
    assert any(it["kind"] == "parameter_knowledge" for it in staged), staged


def test_interactive_mode_still_writes_parameters_directly(tmp_path):
    """The gate must narrow the ONLINE agent, not break the interactive one. If this fails the
    fix has disabled the sanctioned write path instead of gating the unattended one."""
    m = MemoryManager(str(tmp_path), write_mode="interactive")
    m.add_parameter_info("CNRT", parameter_pft=[1], insight="a claim")
    data = json.loads((tmp_path / "parameters.json").read_text())
    assert "CNRT" in data["parameters"], data


def test_every_curated_store_is_now_behind_the_gate(tmp_path):
    """The invariant, stated once. If a FIFTH curated writer is added without the gate, this is
    the test that should catch it -- so it asserts on the staged KINDS rather than on a list of
    method names that would go stale silently."""
    m = MemoryManager(str(tmp_path), write_mode="propose")
    m.add_discovery("d", "desc", "mech", ["plant_C"])
    m.add_failed_approach("a", "e1", "why", "no_effect", ["alt"])
    m.record_experiment({"id": "e1", "modifications": []}, {}, outcome="success")
    m.add_parameter_info("p", insight="i")
    kinds = {it["kind"] for it in
             json.loads((tmp_path / "auto_discovered_pending.json").read_text())["pending"]}
    assert kinds == {"discovery", "failed_approach", "experiment", "parameter"}, kinds
    for curated in ("discoveries.json", "failed_approaches.json", "experiments.json",
                    "parameters.json"):
        f = tmp_path / curated
        if f.exists():
            payload = json.loads(f.read_text())
            inner = payload.get(curated[:-5], payload)
            n = len([k for k in inner if not str(k).startswith("_")]) if isinstance(inner, dict) \
                else len(inner)
            assert n == 0, f"{curated} was written in propose mode: {inner}"
