"""The orchestrator must load the ACTIVE MODEL's knowledge store, not always the FATES one.

THE DEFECT THIS PINS (2026-09-11). `orchestrator.py` loaded its model-layer ("generic") memory from
a hardcoded `memory/gained_knowledge/`. That directory is the FATES store: it is unprefixed because
FATES predates the per-model layout, while adapter models keep `memory/<model>/gained_knowledge/`.
So every online EcoSIM or PFLOTRAN run was given FATES discoveries as its model knowledge and never
read its own model's store.

Two properties are pinned, one per failure shape:
  * the resolver maps FATES to the UNPREFIXED store and every other model to its NAMED store;
  * a model with no store gets nothing -- no FATES fallback, and no empty store created in the
    repo (`MemoryManager.__init__` mkdirs its data_dir, so constructing one on a missing store
    would create it).

Path assertions run against the real branch. Loader tests run against a temporary copy of the
stores, so no test writes into the repository's knowledge base.

Author: Jing Tao with Claude.
"""
from __future__ import annotations

import logging
import shutil
import subprocess
from pathlib import Path

import pytest

from tools.model_knowledge_store import (
    UNPREFIXED_STORE_MODELS,
    load_model_memory,
    model_store_dir,
)

REPO = Path(__file__).resolve().parent.parent
LOG = logging.getLogger("test_model_knowledge_store")


def _branch_named_stores() -> list[str]:
    """Model names that have a `memory/<model>/gained_knowledge/` store in the BRANCH."""
    out = subprocess.run(
        ["git", "-C", str(REPO), "ls-files", "memory"], capture_output=True, text=True, check=True
    ).stdout
    names = set()
    for p in out.splitlines():
        parts = p.split("/")
        if len(parts) >= 4 and parts[0] == "memory" and parts[2] == "gained_knowledge":
            names.add(parts[1])
    return sorted(names)


# ---------------------------------------------------------------------------
# The resolver, against the real branch
# ---------------------------------------------------------------------------


def test_fates_resolves_to_the_unprefixed_store_it_always_used():
    """A FATES run must load exactly what it loaded before this change."""
    assert model_store_dir("fates", REPO) == REPO / "memory" / "gained_knowledge"
    assert (REPO / "memory" / "gained_knowledge" / "discoveries.json").is_file()


def test_premise_the_adapter_stores_exist():
    """If these disappear, the parametrized test below silently tests nothing."""
    assert {"ecosim", "pflotran"} <= set(_branch_named_stores())


@pytest.mark.parametrize("model", _branch_named_stores())
def test_every_named_store_in_the_branch_resolves_to_itself(model: str):
    assert model_store_dir(model, REPO) == REPO / "memory" / model / "gained_knowledge"


def test_no_named_store_shadows_an_unprefixed_model():
    """A `memory/fates/` directory would make FATES's store ambiguous; the mapping would need
    revisiting rather than silently ignoring it."""
    for model in UNPREFIXED_STORE_MODELS:
        assert not (REPO / "memory" / model).exists(), (
            f"memory/{model}/ now exists but {model!r} is mapped to the unprefixed store"
        )


def test_an_unset_model_means_fates(monkeypatch):
    monkeypatch.delenv("A2MC_MODEL", raising=False)
    from models.registry import active_model_name
    assert active_model_name() == "fates"


# ---------------------------------------------------------------------------
# The loader, against a temporary copy of the stores
# ---------------------------------------------------------------------------


@pytest.fixture
def fake_root(tmp_path: Path) -> Path:
    """A repo-shaped tree holding copies of the FATES and EcoSIM stores (no ATS store)."""
    root = tmp_path / "repo"
    shutil.copytree(REPO / "memory" / "gained_knowledge", root / "memory" / "gained_knowledge")
    shutil.copytree(REPO / "memory" / "ecosim" / "gained_knowledge",
                    root / "memory" / "ecosim" / "gained_knowledge")
    (tmp_path / "case").mkdir()
    return root


def test_an_adapter_run_loads_its_own_store_not_fates(fake_root: Path, tmp_path: Path, monkeypatch):
    """THE DEFECT. With A2MC_MODEL=ecosim the model layer is the EcoSIM store."""
    monkeypatch.setenv("A2MC_MODEL", "ecosim")
    mm = load_model_memory(tmp_path / "case", "propose", LOG, repo_root=fake_root)
    assert mm is not None
    assert mm.data_dir.resolve() == (fake_root / "memory" / "ecosim" / "gained_knowledge").resolve()


def test_a_fates_run_loads_the_unprefixed_store(fake_root: Path, tmp_path: Path, monkeypatch):
    monkeypatch.delenv("A2MC_MODEL", raising=False)
    mm = load_model_memory(tmp_path / "case", "propose", LOG, repo_root=fake_root)
    assert mm is not None
    assert mm.data_dir.resolve() == (fake_root / "memory" / "gained_knowledge").resolve()


def test_a_model_with_no_store_gets_nothing_and_creates_nothing(
    fake_root: Path, tmp_path: Path, caplog
):
    """No FATES fallback, a warning that says so, and no empty store created by MemoryManager."""
    with caplog.at_level(logging.WARNING, logger=LOG.name):
        mm = load_model_memory(tmp_path / "case", "propose", LOG, model="ats", repo_root=fake_root)
    assert mm is None, "a model with no store must not be handed another model's store"
    assert not (fake_root / "memory" / "ats").exists(), "the loader created an empty ATS store"
    assert "ats" in caplog.text and "not used as a fallback" in caplog.text


def test_the_case_store_is_not_loaded_twice(fake_root: Path):
    """When the case memory directory IS the model store, the model layer is skipped."""
    same = fake_root / "memory" / "ecosim" / "gained_knowledge"
    assert load_model_memory(same, "propose", LOG, model="ecosim", repo_root=fake_root) is None


# ---------------------------------------------------------------------------
# declared_case_model: which model a case runs, from its own configs (v2.411)
# ---------------------------------------------------------------------------

from tools.model_knowledge_store import _MODEL_DECLARATION, declared_case_model  # noqa: E402


@pytest.mark.parametrize("case, model", [
    ("ELM-FATES_Kougarok", "fates"),     # FATES configs declare nothing: the registry default
    ("EcoSIM_BioCON", "ecosim"),         # its round configs declare nothing and must be IGNORED
    ("PFLOTRAN_miniLEO", "pflotran"),
    ("ATS_template", "ats"),
])
def test_real_cases_resolve_to_the_model_they_run(case: str, model: str):
    d = REPO / "use_cases" / case
    if not d.is_dir():
        pytest.skip(f"use_cases/{case} not in this clone")
    assert declared_case_model(d) == model


def test_a_case_whose_configs_disagree_is_refused():
    """use_cases/TEMPLATE holds an EcoSIM and a PFLOTRAN config: there is no one answer."""
    with pytest.raises(ValueError, match="different models"):
        declared_case_model(REPO / "use_cases" / "TEMPLATE")


def test_a_non_literal_declaration_is_refused(tmp_path: Path):
    (tmp_path / "config").mkdir()
    (tmp_path / "config" / "c.sh").write_text('export A2MC_MODEL="${A2MC_MODEL:-ecosim}"\n')
    with pytest.raises(ValueError, match="not a literal"):
        declared_case_model(tmp_path)


def test_a_case_with_no_config_is_fates(tmp_path: Path):
    assert declared_case_model(tmp_path) == "fates"


@pytest.mark.parametrize("line, model", [
    ('export A2MC_MODEL="ecosim"', "ecosim"),
    ("A2MC_MODEL=ecosim", "ecosim"),                          # unquoted
    ("export A2MC_MODEL='pflotran'", "pflotran"),             # single-quoted
    ('  export A2MC_MODEL="ats"   # the ATS adapter', "ats"),  # indented, trailing comment
])
def test_every_literal_declaration_form_is_read(tmp_path: Path, line: str, model: str):
    """Pinned here because the tracked configs cannot pin it: every declaration under
    use_cases/*/config/ is double-quoted today, so `test_no_tracked_declaration_is_skipped_silently`
    stays green if the pattern stops accepting the other forms. A first unquoted declaration would
    then be ignored and its case read as FATES."""
    assert _MODEL_DECLARATION.match(line), f"pattern does not read: {line!r}"
    (tmp_path / "config").mkdir()
    (tmp_path / "config" / "c.sh").write_text(line + "\n")
    assert declared_case_model(tmp_path) == model


def test_no_tracked_declaration_is_skipped_silently():
    """Every tracked config line that ASSIGNS A2MC_MODEL must match the strict pattern.

    A line the pattern cannot read is ignored, and an ignored declaration turns an adapter case
    into a FATES case, which is the misroute this module exists to prevent."""
    out = subprocess.run(["git", "-C", str(REPO), "ls-files", "use_cases/*/config/*.sh"],
                         capture_output=True, text=True, check=True).stdout.split()
    assert out, "no case configs found -- the enumeration went blind"
    loose = __import__("re").compile(r"^\s*(?:export\s+)?A2MC_MODEL=")
    unread = []
    for rel in out:
        for n, line in enumerate((REPO / rel).read_text(errors="replace").splitlines(), 1):
            if loose.match(line) and not _MODEL_DECLARATION.match(line):
                unread.append(f"{rel}:{n}: {line.strip()}")
    assert not unread, f"declarations the strict pattern does not read: {unread}"
