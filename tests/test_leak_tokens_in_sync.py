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


# ---------------------------------------------------------------------------
# The EXEMPTIONS (PI, 2026-09-15). The token list is only half the gate: what is subtracted
# from a line BEFORE the tokens are tested decides what may ship. `jingtao-lbl` is the GitHub
# ORG — the URL a public reader clones, and in README.md since the first release — so it is
# exempt, like the contact address. Everything else stays caught.
#
# Pinned here for the same reason the token list is: the exemption lives in THREE places
# (PUBLIC_ORG/PUBLIC_CONTACT in the checker, and a `sed` in each leg's scan pipeline). One of
# them relaxed alone gives the worst shape — text commits cleanly, then aborts the publish gate.
# ---------------------------------------------------------------------------

SALESKA_LEG = REPO / "scripts" / "sync_adapterkit_forSaleska.sh"
EXEMPT_STRINGS = ("jingtao-lbl", r"jingtao@lbl\.gov")


def _scan(line: str) -> bool:
    """Exactly what the checker applies: exemptions subtracted, then the tokens tested."""
    from tools.validate_agent_surface import LEAK_TOKENS, PUBLIC_CONTACT, PUBLIC_ORG
    return bool(LEAK_TOKENS.search(PUBLIC_ORG.sub("", PUBLIC_CONTACT.sub("", line))))


@pytest.mark.parametrize("exempt", [
    "clone https://github.com/jingtao-lbl/A2MC.git",
    "the public `jingtao-lbl/A2MC` repo",
    "https://github.com/jingtao-lbl/A2MC-Saleska/tree/A2MC-upstream",
    "questions to jingtao@lbl.gov",
])
def test_the_public_org_and_contact_ship(exempt):
    """A skill that tells you which repo to sync to has to be able to NAME it."""
    assert not _scan(exempt), f"public identifier wrongly flagged: {exempt}"


@pytest.mark.parametrize("leaky", [
    "~/A2MC-adapter",
    "~/EcoSIM",
    "~/run",
    "export A2MC_HPC_ACCOUNT=m2467",
    "the m4218 scratch allocation",
    "branch kougarok_fates_demo",
    "ssh jingtao@perlmutter.nersc.gov",
])
def test_the_exemption_did_not_open_the_gate(leaky):
    """THE HALF THAT MAKES IT ABLE TO FAIL. An exemption is the easiest way to silently disable a
    leak gate, so every real leak must still trip AFTER the subtraction — including a bare
    username, which the org exemption must not swallow."""
    assert _scan(leaky), f"leak went undetected after the exemptions: {leaky}"


@pytest.mark.parametrize("leg", [ADAPTER_LEG, SALESKA_LEG], ids=lambda p: p.name)
def test_both_legs_carry_the_same_exemptions(leg: Path):
    """The shell gates must subtract what the Python gate subtracts, or the two disagree."""
    assert leg.is_file(), f"missing: {leg}"
    text = leg.read_text()
    for s in EXEMPT_STRINGS:
        assert s in text, (
            f"{leg.name} does not exempt {s!r} before its leak scan, so it will abort on text "
            "that tools/validate_agent_surface.py passes."
        )


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
