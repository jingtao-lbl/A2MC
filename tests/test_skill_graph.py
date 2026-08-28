"""`tools/skill_graph.py` — the inverse question the reciprocity check cannot ask.

`check_skill_registry.py::reciprocity_check` walks edges a skill CHOSE to declare, so it cannot
see an edge that should exist and never was declared — which is what every gap in the 2026-08-24
round-boundary audit turned out to be. This tool reads the edges already present in prose and
reports the shape, including the INBOUND list a skill's own author never sees.

Deliberately not a gate, so these tests assert it INFORMS correctly rather than that it fails.
The one thing it must never do is report a clean graph because it parsed nothing —
`test_it_finds_the_real_graph` is the anti-silent-pass guard.
"""
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TOOL = ROOT / "tools" / "skill_graph.py"

sys.path.insert(0, str(ROOT))
from tools.skill_graph import build, inbound, skills_on_disk  # noqa: E402


def run(*args):
    r = subprocess.run([sys.executable, str(TOOL), *args], capture_output=True, text=True, cwd=ROOT)
    return r.returncode, r.stdout + r.stderr


# ------------------------------------------------------------------ the graph itself

def test_it_finds_the_real_graph():
    """ANTI-SILENT-PASS. If the reference regexes stopped matching — a link style changed, the
    directory moved — every other query would return an empty, cheerful answer. A graph over 47
    skills is not sparse; assert it is substantial before trusting anything else."""
    g = build(skills_on_disk())
    assert len(g) > 40, f"only {len(g)} skills parsed"
    edges = sum(len(e["out"]) for e in g.values())
    assert edges > 100, f"only {edges} edges parsed — the reference patterns likely stopped matching"


def test_edges_are_directional_and_inbound_is_computed():
    g = build(skills_on_disk())
    # round-housekeeping was authored to point at these; the relationship must read both ways
    assert "curate-knowledge" in g["round-housekeeping"]["out"]
    assert "round-housekeeping" in inbound(g, "curate-knowledge")


def test_a_skill_never_references_itself():
    """Self-edges would inflate every count and make 'referenced by' meaningless."""
    g = build(skills_on_disk())
    for name, e in g.items():
        assert name not in e["out"], f"{name} references itself"


def test_declared_reciprocity_is_a_subset_of_prose_edges():
    """A skill cannot declare a reciprocal partner it never mentions — if it could, the declared
    set and the real graph would describe different things."""
    g = build(skills_on_disk())
    for name, e in g.items():
        assert e["declared"] <= e["out"], f"{name} declares {e['declared'] - e['out']} unreferenced"


# ------------------------------------------------------------------ the queries

def test_skill_query_shows_both_directions():
    code, out = run("--skill", "round-housekeeping")
    assert code == 0, out
    assert "REFERENCES" in out and "REFERENCED BY" in out
    assert "curate-knowledge" in out


def test_an_unknown_skill_is_an_error_not_an_empty_answer():
    code, out = run("--skill", "no-such-skill")
    assert code == 2 and "no such skill" in out


def test_asymmetric_reports_one_way_edges_without_failing():
    """One-way references are NORMAL — a phase skill routes to `plotting` and `plotting` should
    not name all nine back. Exiting non-zero here would produce a checker that must be silenced
    to be used, which is why this is an instrument and not a gate."""
    code, out = run("--asymmetric", "--limit", "5")
    assert code == 0, out
    assert "NOT errors" in out


def test_orphans_names_skills_nothing_references():
    code, out = run("--orphans")
    assert code == 0, out
    assert "NOTHING references" in out


def test_stats_reports_both_coverage_numbers():
    """The gap between the prose graph and the declared mechanism is the measurement WP8 needed
    to answer whether a graph is a new artifact or the existing check applied more widely."""
    code, out = run("--stats")
    assert code == 0, out
    assert "prose reference edges" in out and "declaring **Reciprocal**" in out
