"""The leak-token list lives in more than one file — pin them together.

The pattern that decides what may ship publicly existed in FOUR places on 2026-08-14
(`tools/validate_agent_surface.py`, both sync legs, and a hardcoded copy inside
`tests/test_offline_agent_mode.py`). Relaxing one of them left the others enforcing the old
policy, which is the worst possible failure shape: text commits cleanly through the pre-commit
checker and then **aborts the fatal publish gate** in the sync script, or a test fails on wording
the PI explicitly asked for.

The test copy was removed (it now imports the tool's pattern). The shell copies cannot import, so
they are pinned here instead.

Author: Jing Tao with Claude.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent

PY_SOURCE = REPO / "tools" / "validate_agent_surface.py"
# The adapter-kit leg is THIS branch's publish gate. `scripts/sync_to_public.sh` is main's leg
# (its PRIVATE_REPO points at the main clone), so it is main's to keep in step — asserted
# separately below with an explicit skip rather than silently ignored.
ADAPTER_LEG = REPO / "scripts" / "sync_adapterkit_to_public.sh"
MAIN_LEG = REPO / "scripts" / "sync_to_public.sh"

_PY_RE = re.compile(r'^LEAK_TOKENS\s*=\s*re\.compile\(r"([^"]+)"\)', re.M)
_SH_RE = re.compile(r"^LEAK_TOKENS='([^']+)'", re.M)


def _extract(path: Path, pattern: re.Pattern) -> str:
    assert path.is_file(), f"missing: {path}"
    m = pattern.search(path.read_text())
    assert m, f"could not locate a LEAK_TOKENS assignment in {path.name}"
    return m.group(1)


def test_adapter_publish_gate_matches_the_precommit_checker():
    """The gate that BLOCKS a publish must agree with the gate that blocks a commit."""
    py = _extract(PY_SOURCE, _PY_RE)
    sh = _extract(ADAPTER_LEG, _SH_RE)
    assert py == sh, (
        "leak-token drift between the pre-commit checker and the adapter-kit publish gate:\n"
        f"  tools/validate_agent_surface.py : {py}\n"
        f"  scripts/sync_adapterkit_to_public.sh : {sh}\n"
        "Text that commits cleanly would abort the sync (or vice versa). Update both."
    )


def test_tokens_are_identity_not_path_shape():
    """Policy assertion (PI, 2026-08-14): public text carries real path SHAPES with the
    identifying segments templated, so structural path tokens must NOT come back."""
    py = _extract(PY_SOURCE, _PY_RE)
    for structural in ("/global/", "/pscratch/", "/Users/", "/cfs/cdirs"):
        assert structural not in py, (
            f"{structural!r} is back in LEAK_TOKENS. Path SHAPE is public and is what makes the "
            "docs usable; only the identifying segments (<user>, <project>) are private. See "
            ".claude_memory/feedback_scrub_paths_keep_the_example.md"
        )


@pytest.mark.parametrize("leaky", [
    "~/E3SM_FATES_api43",
    "~/EcoSIM",
    "~/.claude",
    "~/run",
    "~/A2MC-main",
    "the m4218 scratch allocation",
    "branch kougarok_fates_demo",
])
def test_real_personal_paths_are_still_caught(leaky):
    """Relaxing structure must not stop a REAL path being caught — a real one always carries
    an identifying segment. This is the half that makes the check able to fail."""
    from tools.validate_agent_surface import LEAK_TOKENS
    assert LEAK_TOKENS.search(leaky), f"leak went undetected: {leaky}"


@pytest.mark.parametrize("safe", [
    "/global/cfs/cdirs/<project>/<user>/E3SM_FATES_api43",
    "shared NERSC scratch (such as `/global/cfs`)",
    "$A2MC_MODEL_PATH",
    "/global/homes/j/<user>",
    "/pscratch/sd/j/$USER/run",
    "<PATH_TO_ECOSIM_CHECKOUT>",
])
def test_templated_paths_are_publishable(safe):
    """The whole point of the relaxation: a real path shape with templated identity must ship."""
    from tools.validate_agent_surface import LEAK_TOKENS
    m = LEAK_TOKENS.search(safe)
    assert not m, f"templated path wrongly flagged: {safe} (matched {m.group(0)!r} if m)"


def test_main_leg_drift_is_reported():
    """`scripts/sync_to_public.sh` is MAIN's leg; this branch does not own it. Skip rather than
    fail, but make the drift visible instead of letting it sit silently."""
    if not MAIN_LEG.is_file():
        pytest.skip("main's sync leg not present in this clone")
    py = _extract(PY_SOURCE, _PY_RE)
    sh = _extract(MAIN_LEG, _SH_RE)
    if py != sh:
        pytest.skip(
            "KNOWN: main's sync leg carries a different leak-token list "
            f"({sh!r} vs {py!r}). main owns that file — carry the change over via "
            "main's adopt-from-adapter-kit skill."
        )
