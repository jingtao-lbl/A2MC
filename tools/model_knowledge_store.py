"""Resolve and load the MODEL layer of A2MC's adaptive memory.

A2MC's calibration knowledge has two JSON layers: the CASE store
(`use_cases/{Model}_{Case}/memory/gained_knowledge/`) and the MODEL store, which holds what is true
of a model wherever it runs. The model store's path is NOT uniform across models:

    fates              memory/gained_knowledge/              (unprefixed: no model name in the path)
    ecosim, pflotran   memory/<model>/gained_knowledge/

FATES is A2MC's built-in path rather than an adapter under `models/`, and its store predates the
per-model layout, so its folder carries no model name. Every model onboarded since carries its
name. Two failure shapes follow, and this module exists to avoid both:

  * building `memory/<model>/gained_knowledge/` for every model misses the FATES store;
  * hardcoding the unprefixed store hands an EcoSIM or PFLOTRAN run, or an EcoSIM or PFLOTRAN
    promotion, the FATES knowledge base.

A model with no store of its own gets NO model layer (with a warning). The FATES store is never
substituted, because foreign-model discoveries in the reasoning context are worse than none.

Consumers: `orchestrator.py` (reads the active model's store, v2.410), `tools/promote_knowledge.py`
(writes a case's discovery into that case's model store) and `tools/check_stage_ready.py` (checks
a model's store is seeded), the last two since v2.411.

Author: Jing Tao with Claude.
"""
# No `from __future__ import annotations`: this module is loaded by check_stage_ready.py, which
# runs under the SYSTEM python3 (3.6 on Perlmutter) from hooks and the setup docs, and that
# import is a SyntaxError before 3.7 (audit 20260923b, finding F103). It annotates nothing that
# needs it.

import logging
import re
from pathlib import Path
from typing import Optional

REPO_ROOT = Path(__file__).resolve().parent.parent

# Models whose model-layer store is the UNPREFIXED `memory/gained_knowledge/`. FATES only. A model
# added here must have no `memory/<model>/` directory, or the two would be ambiguous
# (`tests/test_model_knowledge_store.py` guards that).
UNPREFIXED_STORE_MODELS = frozenset({"fates"})

# A case config's declaration of its model, as a LITERAL: `export A2MC_MODEL="ecosim"`,
# `A2MC_MODEL=ecosim`, an optional trailing comment. Anything else on the line (a `;`, a second
# command) does not match, and a test asserts every tracked declaration does match, so a
# declaration this pattern cannot read fails a test rather than being skipped silently.
_MODEL_DECLARATION = re.compile(r"""^\s*(?:export\s+)?A2MC_MODEL=(["']?)([^"'\s#]*)\1\s*(?:#.*)?$""")


def model_store_dir(model: str, repo_root: Path = REPO_ROOT) -> Path:
    """Return the model-layer knowledge-store directory for `model`. It may not exist."""
    if model in UNPREFIXED_STORE_MODELS:
        return repo_root / "memory" / "gained_knowledge"
    return repo_root / "memory" / model / "gained_knowledge"


def declared_case_model(case_dir) -> str:
    """Return the model a case runs, as its own `config/*.sh` files declare it.

    Mirrors what sourcing the case's config does: an adapter case's config exports `A2MC_MODEL`,
    while a FATES case's config sets none and relies on `models.registry.DEFAULT_MODEL`. A file
    that does not declare the variable is IGNORED, not read as fates: round configs such as
    `ecosim_biocon_config_r3.sh` set nothing and source the base config, which does.

    Raises `ValueError` when the case's configs declare different models (`use_cases/TEMPLATE/`
    holds both an EcoSIM and a PFLOTRAN config) or when a declaration is not a literal name.
    """
    cfg = Path(case_dir) / "config"
    found: dict = {}
    if cfg.is_dir():
        for f in sorted(cfg.glob("*.sh")):
            for line in f.read_text(encoding="utf-8", errors="replace").splitlines():
                m = _MODEL_DECLARATION.match(line)
                if m:
                    found.setdefault(m.group(2), set()).add(f.name)
    if not found:
        from models.registry import DEFAULT_MODEL
        return DEFAULT_MODEL
    if len(found) > 1:
        detail = "; ".join(f"{v or '<empty>'} in {', '.join(sorted(fs))}"
                           for v, fs in sorted(found.items()))
        raise ValueError(f"its config files declare different models ({detail})")
    (value,) = found
    if not value or "$" in value or "{" in value:
        raise ValueError(f"A2MC_MODEL is not a literal model name "
                         f"({value!r} in {', '.join(sorted(found[value]))})")
    return value


def load_model_memory(case_memory_dir, write_mode: str, logger: logging.Logger,
                      model: Optional[str] = None, repo_root: Path = REPO_ROOT):
    """Return a `MemoryManager` over the active model's knowledge store, or None.

    `model` defaults to `models.registry.active_model_name()` (`$A2MC_MODEL`, else fates).

    Returns None, loading nothing, when:
      * the model has no store -- warned, and the FATES store is NOT used as a fallback;
      * the store is the same directory as the case store (already loaded as the case layer).

    The directory is checked BEFORE a `MemoryManager` is constructed, because
    `MemoryManager.__init__` creates its `data_dir`: constructing one on a missing store would
    silently create an empty `memory/<model>/gained_knowledge/` in the repo.
    """
    if model is None:
        from models.registry import active_model_name
        model = active_model_name()

    store = model_store_dir(model, repo_root)
    try:
        shown = f"{store.relative_to(repo_root)}/"
    except ValueError:
        shown = f"{store}/"

    if not store.is_dir():
        logger.warning(
            f"No model-layer knowledge store for A2MC_MODEL={model!r} ({shown} absent); running "
            f"with case knowledge only. The FATES store is not used as a fallback."
        )
        return None
    if store.resolve() == Path(case_memory_dir).resolve():
        return None

    from memory import MemoryManager
    manager = MemoryManager(str(store), write_mode=write_mode)
    logger.info(f"Model memory loaded ({model}, {shown}): "
                f"{manager.stats()['discoveries']['total']} discoveries")
    return manager
