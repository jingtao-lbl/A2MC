"""`tools/check_stage_ready.py` must route correctly and be able to FAIL.

Two properties matter and are asserted separately:

1. **Routing** — the stage is read from DISK, not from what a session claims. Each of the four
   routes is driven from a synthetic clone, so a wrong route is a test failure rather than a
   surprise in someone's first session.
2. **The checks can fail.** A stage checker that reports complete on an incomplete clone is worse
   than none, because "✓ no failures" is exactly what a user reads before moving on. Every stage
   therefore has a paired complete/incomplete fixture.

Author: Jing Tao with Claude.
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
TOOL = REPO / "tools" / "check_stage_ready.py"


def run(root: Path, *args, env_extra: dict | None = None):
    """Run the checker against a synthetic clone by importing it with a patched ROOT."""
    import os
    code = (
        "import importlib.util,sys,pathlib;"
        f"spec=importlib.util.spec_from_file_location('csr',r'{TOOL}');"
        "m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);"
        f"m.ROOT=pathlib.Path(r'{root}');"
        f"sys.argv=['csr']+{list(args)!r};"
        "sys.exit(m.main())"
    )
    env = {**os.environ, **(env_extra or {})}
    env.pop("A2MC_MODEL_PATH", None) if env_extra is None else None
    r = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, timeout=60, env=env)
    return r.returncode, r.stdout + r.stderr


def make_clone(tmp: Path, *, models=(), cases=(), offline_state=False, milestones=None) -> Path:
    """Build a synthetic A2MC clone. `models` register properly; `cases` are real cases."""
    (tmp / "models").mkdir(parents=True, exist_ok=True)
    for m in models:
        d = tmp / "models" / m
        d.mkdir(parents=True, exist_ok=True)
        # the registry contract is what marks a directory as an adapted model
        (d / "__init__.py").write_text("register_model(object())\n")
        for f in ("spec.py", "parameter_parser.py", "output_parser.py"):
            (d / f).write_text("# stub\n")
        (d / "runtemplates").mkdir(exist_ok=True)
        (d / "runtemplates" / "run.tmpl").write_text("x\n")
        gk = tmp / "memory" / m / "gained_knowledge"
        gk.mkdir(parents=True, exist_ok=True)
        (gk / "discoveries.json").write_text(json.dumps({"discoveries": [{"id": "x"}]}))
    (tmp / "use_cases").mkdir(parents=True, exist_ok=True)
    (tmp / "use_cases" / "TEMPLATE").mkdir(exist_ok=True)
    (tmp / "use_cases" / "EcoSIM_template").mkdir(exist_ok=True)   # a per-model seed, NOT a real case
    for c in cases:
        d = tmp / "use_cases" / c
        (d / "config").mkdir(parents=True, exist_ok=True)
        (d / "config" / "site_config.sh").write_text("# cfg\n")
        (d / "config" / "calibration_rounds.yaml").write_text("rounds: []\n")
        (d / "validation").mkdir(exist_ok=True)
        (d / "validation" / "targets.yaml").write_text("targets:\n  - name: gpp\n")
        (d / "parameters").mkdir(exist_ok=True)
        (d / "parameters" / "list.csv").write_text("name,lower_bound,upper_bound\n")
        (d / "memory").mkdir(exist_ok=True)
        if offline_state:
            (d / "memory" / "workflow_state_offline_r01.json").write_text("{}")
    (tmp / "rag").mkdir(parents=True, exist_ok=True)
    ms = milestones if milestones is not None else {
        m: {"adapter": m, "knowledge_base_dir": f"docs/{m}-kb", "curated_yaml_path": f"models/{m}/curated_seed.yaml"}
        for m in models}
    (tmp / "rag" / "milestones.json").write_text(json.dumps({"milestones": ms}))
    for prof, e in ms.items():
        (tmp / (e.get("knowledge_base_dir") or f"docs/{prof}-kb")).mkdir(parents=True, exist_ok=True)
        cy = tmp / (e.get("curated_yaml_path") or f"models/{prof}/curated_seed.yaml")
        cy.parent.mkdir(parents=True, exist_ok=True); cy.write_text("seed: {}\n")
        (tmp / "rag" / "chroma_db" / prof).mkdir(parents=True, exist_ok=True)
        (tmp / "rag" / "graphs").mkdir(parents=True, exist_ok=True)
        (tmp / "rag" / "graphs" / f"{prof}.json").write_text("{}")
    return tmp


# --------------------------------------------------------------------- routing
def test_no_adapted_model_routes_to_stage_2(tmp_path):
    rc, out = run(make_clone(tmp_path))
    assert "stage: 2" in out and "onboard-model" in out, out


def test_model_but_no_case_routes_to_stage_1(tmp_path):
    rc, out = run(make_clone(tmp_path, models=("ecosim",)))
    assert "stage: 1" in out and "a2mc-init" in out, out


def test_real_case_routes_to_stage_3(tmp_path):
    rc, out = run(make_clone(tmp_path, models=("ecosim",), cases=("EcoSIM_BioCON",)))
    assert "stage: 3" in out and "onboard-case" in out, out


def test_offline_state_means_setup_is_over(tmp_path):
    rc, out = run(make_clone(tmp_path, models=("ecosim",), cases=("EcoSIM_BioCON",), offline_state=True))
    assert "stage: 4" in out and "onboard-session" in out, out


def test_template_dirs_are_not_counted_as_cases(tmp_path):
    """`TEMPLATE/` and `<Model>_template/` are scaffolding. Counting either would route a fresh
    clone to stage 3 and skip a2mc-init entirely."""
    rc, out = run(make_clone(tmp_path, models=("ecosim",)))
    assert "stage: 1" in out, out
    assert "real cases:     (none)" in out, out


def test_a_directory_that_does_not_register_is_not_a_model(tmp_path):
    """models/surrogate/ has a spec.py but is explicitly NOT an adapter and never registers.
    A spec.py heuristic counted it and invented a 3-failure onboarding for it."""
    root = make_clone(tmp_path)
    d = root / "models" / "surrogate"
    d.mkdir(parents=True)
    (d / "spec.py").write_text("# a surrogate is NOT a model adapter\n")
    (d / "__init__.py").write_text("# no register_model call\n")
    rc, out = run(root)
    assert "surrogate" not in out.split("real cases")[0], out
    assert "stage: 2" in out, out


# --------------------------------------------------------------------- the checks can FAIL
def test_stage2_complete_model_passes(tmp_path):
    rc, out = run(make_clone(tmp_path, models=("ecosim",)), "--model", "ecosim")
    assert rc == 0, out
    assert "✗" not in out, out


def test_stage2_unregistered_milestone_fails(tmp_path):
    """The item whose omission breaks every LATER clone rather than this one."""
    root = make_clone(tmp_path, models=("ecosim",), milestones={})
    rc, out = run(root, "--model", "ecosim")
    assert rc == 1, out
    assert "milestone registered" in out and "unsupported" in out, out


def test_stage2_missing_rag_index_fails(tmp_path):
    """chroma.sqlite3 carries skip-worktree, so an unstaged rebuild looks identical to this."""
    root = make_clone(tmp_path, models=("ecosim",))
    import shutil
    shutil.rmtree(root / "rag" / "chroma_db" / "ecosim")
    rc, out = run(root, "--model", "ecosim")
    assert rc == 1 and "RAG index committed" in out, out


def test_stage2_missing_parser_fails(tmp_path):
    root = make_clone(tmp_path, models=("ecosim",))
    (root / "models" / "ecosim" / "output_parser.py").unlink()
    rc, out = run(root, "--model", "ecosim")
    assert rc == 1 and "output_parser.py" in out, out


def test_stage3_complete_case_passes(tmp_path):
    root = make_clone(tmp_path, models=("ecosim",), cases=("EcoSIM_BioCON",))
    rc, out = run(root, "--case", "EcoSIM_BioCON")
    assert rc == 0, out


def test_stage3_empty_targets_fails(tmp_path):
    """A targets.yaml that exists but holds nothing is the silent case: Phase 2 scores nothing."""
    root = make_clone(tmp_path, models=("ecosim",), cases=("EcoSIM_BioCON",))
    (root / "use_cases" / "EcoSIM_BioCON" / "validation" / "targets.yaml").write_text("# only a comment\n")
    rc, out = run(root, "--case", "EcoSIM_BioCON")
    assert rc == 1 and "EMPTY" in out, out


def test_stage3_missing_rounds_fails(tmp_path):
    root = make_clone(tmp_path, models=("ecosim",), cases=("EcoSIM_BioCON",))
    (root / "use_cases" / "EcoSIM_BioCON" / "config" / "calibration_rounds.yaml").unlink()
    rc, out = run(root, "--case", "EcoSIM_BioCON")
    assert rc == 1 and "calibration_rounds.yaml" in out, out


# --------------------------------------------------------------------- contract
def test_unverifiable_items_are_reported_not_hidden(tmp_path):
    """The gate must state what it CANNOT check. A checklist that silently drops its
    unverifiable items reads as 'stage complete' when it is not."""
    rc, out = run(make_clone(tmp_path, models=("ecosim",), cases=("EcoSIM_BioCON",)), "--case", "EcoSIM_BioCON")
    assert "Not mechanically checkable" in out, out
    assert "GATE 1" in out and "GATE 2" in out, out
    assert "still yours to confirm" in out, out


def test_runs_with_no_sourced_config(tmp_path):
    """The reason this tool exists: check_setup_ready.py hard-exits without A2MC_USE_CASE_DIR,
    which is a dead end in a fresh clone."""
    rc, out = run(make_clone(tmp_path), env_extra={"A2MC_USE_CASE_DIR": ""})
    assert "stage:" in out, out
    assert "A2MC_USE_CASE_DIR" not in out, out


def test_a_structural_failure_does_not_hide_later_checks(tmp_path):
    """An early return on the milestone failure hid every row below it, so a reader saw a short
    clean tail and reasonably read it as 'the rest is fine'. Measured on ATS: its missing
    milestone masked a missing adaptive-memory seed entirely."""
    root = make_clone(tmp_path, models=("ecosim",), milestones={})
    import shutil
    shutil.rmtree(root / "memory" / "ecosim" / "gained_knowledge")
    rc, out = run(root, "--model", "ecosim")
    assert rc == 1, out
    assert "milestone registered" in out, out
    assert "adaptive memory seeded" in out, "the rows after the milestone failure were hidden"


def test_check_setup_ready_routes_a_fresh_clone_instead_of_dead_ending(tmp_path):
    """The reason this tool exists, pinned. check_setup_ready.py used to tell a brand-new user to
    'source the site config first' -- impossible advice when no site config exists yet."""
    (tmp_path / "use_cases" / "TEMPLATE").mkdir(parents=True)
    (tmp_path / "use_cases" / "EcoSIM_template").mkdir(parents=True)
    code = (
        "import importlib.util,pathlib,sys;"
        f"spec=importlib.util.spec_from_file_location('csr',r'{REPO / 'tools' / 'check_setup_ready.py'}');"
        "m=importlib.util.module_from_spec(spec);\n"
        "try:\n spec.loader.exec_module(m)\nexcept SystemExit:\n pass\n"
        f"m.ROOT_GUESS=pathlib.Path(r'{tmp_path}')\n"
        "try:\n m._root()\nexcept SystemExit as e:\n print(e)\n"
    )
    import os
    env = {k: v for k, v in os.environ.items() if k != "A2MC_USE_CASE_DIR"}
    r = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, timeout=60, env=env)
    assert "first-run setup" in r.stdout, r.stdout + r.stderr
    assert "a2mc-init" in r.stdout and "check_stage_ready" in r.stdout, r.stdout


def test_an_empty_knowledge_scaffold_is_not_a_seeded_store(tmp_path):
    """Four empty scaffolds is the half-done state, and no caller can see it: MemoryManager returns
    0 chars for a MISSING store and for an EMPTY one, raising nothing either way. That silent
    equivalence is why step 10 went unnoticed on PFLOTRAN for three weeks."""
    root = make_clone(tmp_path, models=("ecosim",))
    (root / "memory" / "ecosim" / "gained_knowledge" / "discoveries.json").write_text(
        json.dumps({"_comment": "scaffold", "discoveries": []}))
    rc, out = run(root, "--model", "ecosim")
    assert rc == 1, out
    assert "EMPTY scaffold" in out, out


def test_a_missing_knowledge_store_says_what_it_costs(tmp_path):
    """The message has to teach the consequence: silent degradation is the whole defect."""
    root = make_clone(tmp_path, models=("ecosim",))
    import shutil
    shutil.rmtree(root / "memory" / "ecosim" / "gained_knowledge")
    rc, out = run(root, "--model", "ecosim")
    assert rc == 1 and "NO model knowledge" in out, out


def test_fates_is_checked_against_its_unprefixed_store(tmp_path):
    """FATES keeps `memory/gained_knowledge/`, with no model name in the path. Until v2.411 the row
    built `memory/fates/gained_knowledge/`, which never exists, so a seeded FATES store read as
    absent. The adapter-model rows above still pass through the same resolver."""
    root = make_clone(tmp_path)
    gk = root / "memory" / "gained_knowledge"
    gk.mkdir(parents=True, exist_ok=True)
    (gk / "discoveries.json").write_text(json.dumps({"discoveries": [{"id": "x"}]}))
    rc, out = run(root, "--model", "fates")
    assert "adaptive memory seeded — 1 discovery record(s)" in out, out
    assert "memory/fates" not in out, out


# --------------------------------------------------------------------- the SessionStart branch
def _hook_lines(root):
    """Call the hook's setup_stage() against a synthetic clone, out of process.

    Out of process to keep the clone's `tools/` on the import path without disturbing this
    process. It is no longer out of process because importing the hook runs anything: the bare
    module-level `main()` gained a `__main__` guard on 2026-08-25. Before that, `exec_module`
    ran the ENTIRE session snapshot -- `squeue`, `ps`, git reads -- so on a loaded login node the
    import alone blew the 60-second budget below and these three tests failed with
    TimeoutExpired. This docstring previously described that as the reason for the workaround;
    the workaround was fine, the unguarded `main()` was the defect.
    """
    code = (
        "import importlib.util,sys,json;"
        f"spec=importlib.util.spec_from_file_location('h',r'{REPO / '.claude' / 'hooks' / 'session-start.py'}');"
        "m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);"
        f"L=[];m.setup_stage(r'{root}',L);sys.stderr.write(json.dumps(L))"
    )
    r = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, timeout=60)
    return json.loads(r.stderr or "[]")


def test_hook_is_silent_on_a_configured_clone(tmp_path):
    """A regular session must pay nothing for this. Stage 4 = setup done = say nothing."""
    root = make_clone(tmp_path, models=("ecosim",), cases=("EcoSIM_BioCON",), offline_state=True)
    (root / "tools").mkdir(exist_ok=True)
    import shutil; shutil.copy(REPO / "tools" / "check_stage_ready.py", root / "tools")
    assert _hook_lines(root) == []


def test_hook_names_the_skill_for_an_unconfigured_clone(tmp_path):
    """The gap this closes: every other snapshot line presumes a configured clone, so a new user
    got a near-empty snapshot and no hint that a2mc-init exists."""
    root = make_clone(tmp_path)                      # no adapted model -> stage 2
    (root / "tools").mkdir(exist_ok=True)
    import shutil; shutil.copy(REPO / "tools" / "check_stage_ready.py", root / "tools")
    out = " ".join(_hook_lines(root))
    assert "SETUP STAGE 2" in out and "onboard-model" in out, out
    assert "setup-discipline" in out and "check_stage_ready.py" in out, out


def test_hook_never_breaks_a_session(tmp_path):
    """A hook that raises costs every session. Missing tool -> silent, not an exception."""
    assert _hook_lines(tmp_path) == []               # no tools/ at all
