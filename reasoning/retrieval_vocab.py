"""Model-aware RAG retrieval vocabulary for reasoning/methods.py.

Every phase method that queries RAG (`diagnose`, `generate_hypothesis`,
`interpret_results`, `extract_lesson`, `analyze_screening_results`,
`analyze_sensitivity_results`) needs three things to ask a useful question:
which output/column name a target maps to, which mechanism names to look up
in the knowledge graph, and (for `generate_hypothesis`) how to scan free text
for mechanism mentions. Before this module existed, all three were hardcoded
FATES vocabulary (`f"FATES_{t.upper()...}"`, `['PID_Controller', ...]`), so a
correctly-opened PFLOTRAN or EcoSIM RAG index was asked FATES's questions.

FATES has no `models/fates/` adapter package -- it predates the adapter-kit
architecture and is not registered in `models.registry`. "No active adapter
resolves" therefore IS the FATES case, and every function below returns its
caller's own literal pre-existing default in that case, so `main`'s live FATES
campaign sees byte-identical behavior. An adapter model (EcoSIM, PFLOTRAN,
ATS, ...) is asked through its own `ModelSpec` instead of guessed at with
FATES-shaped string surgery.

Root-cause finding this fixes:
memory/dev_logs_adapterkitpflotran/20260807k_Step13_Reasoning_Half_The_Retriever_Is_Right_The_Query_Is_FATES.md
-- PFLOTRAN's `diagnose()` call retrieved noise because its RAG query was built
from FATES output names / mechanism names that appear in no PFLOTRAN corpus.
"""

from __future__ import annotations

from typing import Callable, Dict, Iterable, List, Optional

_FATES_LEGACY_MECHANISMS = ("PID_Controller", "ECA_Competition", "Storage_Allocation")

_FATES_LEGACY_KEYWORD_RULES = (
    (("pid", "allocation"), "PID_Controller"),
    (("nutrient", "phosphorus", "nitrogen"), "ECA_Competition"),
    (("storage",), "Storage_Allocation"),
    (("mortality", "starvation"), "Carbon_Starvation"),
)


def active_adapter_spec():
    """Return the active model's `ModelSpec`, or `None`.

    `None` means either FATES (no `models/fates/` package is registered) or
    resolution failed for any reason (`A2MC_MODEL` unset/unknown, import
    error). Never raises -- a reasoning call must degrade to FATES's legacy
    behavior, not hard-fail, because the active model couldn't be resolved.
    """
    try:
        from models.registry import get_active_model
        backend, _ = get_active_model()
        return backend.spec
    except Exception:
        return None


def resolve_output_names(
    keys: Iterable[str],
    targets: Optional[Dict] = None,
    legacy_fmt: Optional[Callable[[str], str]] = None,
) -> List[str]:
    """Resolve target/result KEYS to real output/column names for RAG retrieval.

    Priority:
      1. ``targets[key]['variable']`` if given -- exact, and already the same
         name `tools/validate_model_targets.py` checks against the model's own
         output registry (a list value takes its first element).
      2. the active adapter's ``ModelSpec.retrieval_output_name_map``.
      3. the key unchanged -- the right default for an adapter whose targets
         already ARE real column names (e.g. PFLOTRAN's ``outflow_Ca``).
      4. ``legacy_fmt(key)``, used only when no adapter is registered (FATES)
         -- preserves each call site's exact original FATES-only heuristic for
         a target with no ``variable`` field.
    """
    spec = active_adapter_spec()
    out = []
    for k in keys:
        variable = None
        if targets is not None:
            entry = targets.get(k)
            if isinstance(entry, dict):
                v = entry.get("variable")
                if isinstance(v, list) and v:
                    variable = v[0]
                elif isinstance(v, str) and v:
                    variable = v
        if variable:
            out.append(variable)
        elif spec is not None:
            out.append(spec.retrieval_output_name_map.get(k, k))
        elif legacy_fmt is not None:
            out.append(legacy_fmt(k))
        else:
            out.append(k)
    return out


def retrieval_mechanisms(legacy: Iterable[str] = _FATES_LEGACY_MECHANISMS) -> List[str]:
    """This model's mechanism vocabulary for RAG mechanism-context lookup.

    An adapter declares it via ``ModelSpec.mechanism_keyword_map`` (already
    curated for the YAML overlay -- see e.g. `models/pflotran/spec.py`); FATES
    (no adapter) keeps a caller-supplied literal default so each call site's
    original hardcoded list is preserved unchanged.
    """
    spec = active_adapter_spec()
    if spec is not None and spec.mechanism_keyword_map:
        seen = []
        for name in spec.mechanism_keyword_map.values():
            if name not in seen:
                seen.append(name)
        return seen
    return list(legacy)


def infer_mechanisms_from_text(text: str) -> List[str]:
    """Scan free text (e.g. a diagnosis's ``likely_causes``) for mechanism mentions.

    An adapter model is scanned against its own
    ``ModelSpec.mechanism_keyword_map`` (keyword -> mechanism name); FATES (no
    adapter) keeps its literal 4-rule keyword scan unchanged.
    """
    lowered = (text or "").lower()
    spec = active_adapter_spec()
    if spec is not None and spec.mechanism_keyword_map:
        found = []
        for kw, name in spec.mechanism_keyword_map.items():
            if kw in lowered and name not in found:
                found.append(name)
        return found
    found = []
    for keywords, mechanism in _FATES_LEGACY_KEYWORD_RULES:
        if any(kw in lowered for kw in keywords) and mechanism not in found:
            found.append(mechanism)
    return found


def domain_flavored_query(task_phrase: str, legacy: str) -> str:
    """Build the natural-language RAG query for a phase-method call.

    An adapter model appends the first sentence of its own ``domain_summary``
    (already-written, onboarding-reviewed prose) to ``task_phrase``, instead of
    FATES's literal task+domain phrase; FATES (no adapter) keeps ``legacy``
    unchanged.
    """
    spec = active_adapter_spec()
    if spec is not None and spec.domain_summary:
        first_sentence = spec.domain_summary.strip().split(". ")[0].rstrip(".")
        return f"{task_phrase} {first_sentence}".strip()
    return legacy
