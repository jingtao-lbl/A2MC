"""Each sync leg's case guard must be an ALLOWLIST: a case not named as shippable aborts the sync.

THE DEFECT THIS PINS (2026-09-10). Both adapter-kit legs guarded use_cases/ with PRIVATE_CASES,
a list of the cases that must NOT ship. That is the wrong polarity for a repo that keeps gaining
cases: each new case was unguarded until someone remembered to add it. By 2026-09-10 the public
leg's list was missing EcoSIM_TeRaCON, EcoSIM_PointReyes, EcoSIM_Lusignan and EcoSIM_Kougarok, and
the Saleska leg's named only EcoSIM_BioCON. Nothing had leaked, but only because no INCLUDE entry
happened to match an unguarded case, which is the kind of safety a new glob removes silently.

The guard is now SHIPPABLE_CASES, and a case not on it aborts. These tests EXECUTE the shipped
block lifted from each leg (between its begin/end markers), so they cannot pass against a script
that no longer contains the guard, and they derive the case list from the BRANCH rather than from
a copy kept here.

Author: Jing Tao with Claude.
"""
from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent

# Per leg: the case directories it may ship BEYOND the shared README.md / TEMPLATE / *_template.
LEGS = {
    "scripts/sync_adapterkit_to_public.sh": set(),
    "scripts/sync_adapterkit_forSaleska.sh": {"PFLOTRAN_miniLEO"},
}

_BEGIN = "# ---- CASE ALLOWLIST GUARD (begin) ----"
_END = "# ---- CASE ALLOWLIST GUARD (end) ----"


def _extract_guard(leg: Path) -> str:
    lines = leg.read_text().splitlines()
    try:
        start = next(i for i, ln in enumerate(lines) if ln.strip() == _BEGIN)
        end = next(i for i, ln in enumerate(lines) if ln.strip() == _END)
    except StopIteration:  # pragma: no cover - only when the guard is removed or rewritten
        pytest.fail(
            f"the case allowlist guard is gone from {leg.name} (looked for {_BEGIN!r} .. "
            f"{_END!r}). It is what stops a private case study reaching a shared repo. "
            "Do not delete this test to make it pass."
        )
    assert start < end, f"{leg.name}: guard markers out of order"
    return "\n".join(lines[start : end + 1])


def _run(leg_rel: str, entries: list[str], tmp_path: Path) -> subprocess.CompletedProcess:
    leg = REPO / leg_rel
    if not leg.is_file():
        pytest.skip(f"{leg_rel} not present in this clone")
    arr = " ".join(f'"{e}"' for e in entries)
    harness = tmp_path / f"guard_{leg.stem}.sh"
    harness.write_text(
        "set -e\n"
        f"INCLUDE_FILES=({arr})\n"
        f"{_extract_guard(leg)}\n"
        'echo "REACHED_THE_SYNC"\n'
    )
    return subprocess.run(["bash", str(harness)], capture_output=True, text=True)


def _branch_cases() -> list[str]:
    """Case directories as the BRANCH has them, not as this machine's disk happens to."""
    out = subprocess.run(
        ["git", "-C", str(REPO), "ls-files", "--cached", "--others", "--exclude-standard",
         "use_cases"],
        capture_output=True, text=True, check=True,
    ).stdout
    names = {p.split("/")[1] for p in out.splitlines() if p.count("/") >= 2}
    return sorted(names)


def _allowed(name: str, extra: set[str]) -> bool:
    return name == "TEMPLATE" or name.endswith("_template") or name in extra


@pytest.mark.parametrize("leg_rel", LEGS)
def test_shared_shippable_entries_pass(leg_rel: str, tmp_path: Path):
    """The inventory file, TEMPLATE, a *_template demo case, and non-use_cases paths all pass.
    `EcoSIM_template` passing is also what proves the pattern is matched UNQUOTED: quoted,
    `*_template` would match only a literal asterisk and this entry would abort."""
    r = _run(
        leg_rel,
        ["tools/", "README.md", "use_cases/README.md", "use_cases/TEMPLATE/",
         "use_cases/EcoSIM_template/", "use_cases/PFLOTRAN_template/"],
        tmp_path,
    )
    assert r.returncode == 0 and "REACHED_THE_SYNC" in r.stdout, r.stderr


@pytest.mark.parametrize("leg_rel", LEGS)
def test_a_case_nobody_has_named_yet_is_refused(leg_rel: str, tmp_path: Path):
    """THE POINT OF THE ALLOWLIST. A list of private cases passes this; an allowlist refuses it."""
    r = _run(leg_rel, ["use_cases/EcoSIM_SomeFutureCase/"], tmp_path)
    assert r.returncode == 1, f"{leg_rel}: an unnamed new case was NOT refused"
    assert "REACHED_THE_SYNC" not in r.stdout
    assert "SHIPPABLE_CASES" in r.stderr, "the refusal must name the list to edit"


@pytest.mark.parametrize("leg_rel", LEGS)
def test_every_case_in_the_branch_gets_its_legs_verdict(leg_rel: str, tmp_path: Path):
    """Every real case, taken from git: refused unless this leg explicitly allows it."""
    extra = LEGS[leg_rel]
    cases = _branch_cases()
    assert cases, "no use_cases/ directories found in the branch -- the enumeration went blind"
    wrong = []
    for name in cases:
        # A file inside the case, to exercise the `_case%%/*` reduction as well as a directory.
        r = _run(leg_rel, [f"use_cases/{name}/README.md"], tmp_path)
        refused = r.returncode == 1
        if refused == _allowed(name, extra):
            wrong.append((name, "refused" if refused else "passed"))
    assert not wrong, f"{leg_rel}: wrong verdicts {wrong}"


@pytest.mark.parametrize("leg_rel", LEGS)
def test_a_widened_glob_is_refused(leg_rel: str, tmp_path: Path):
    """The mutation the old guard was checked against on 2026-08-03: `use_cases/*/` expanded."""
    entries = [f"use_cases/{n}/" for n in _branch_cases()]
    r = _run(leg_rel, entries, tmp_path)
    assert r.returncode == 1, f"{leg_rel}: a use_cases/*/ glob would have shipped every case"


def test_the_project_case_ships_only_on_its_own_leg(tmp_path: Path):
    entry = ["use_cases/PFLOTRAN_miniLEO/config/"]
    assert _run("scripts/sync_adapterkit_forSaleska.sh", entry, tmp_path).returncode == 0
    assert _run("scripts/sync_adapterkit_to_public.sh", entry, tmp_path).returncode == 1
