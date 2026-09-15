#!/usr/bin/env python3
"""Mechanical skill-registry + contract health check for A2MC (no LLM, no deps).

A2MC skills live at .claude/skills/<name>/SKILL.md and are auto-discovered by the
harness (functional registry). There are THREE human-facing registries that must stay in
sync with the disk, so the drift surface is tripled vs a single-catalog project:

  1. the "Current skills" table in  .claude/skills/README.md
  2. the per-skill entries (### `name`) in  docs/a2mc_reference/skills_catalog.md
  3. the "At a glance" capability table in  AGENTS.md  (the public, harness-neutral
     operating contract — an un-enforced registry here is exactly how AGENTS.md silently
     fell behind when 8 skills were added; see memory/dev_logs/ for the 2026-06-28 fix)

Checks:
  1. DRIFT      disk == README-table == catalog == AGENTS.md table  (4-way parity)
  2. NAME/DIR   each SKILL.md frontmatter `name:` matches its directory
  3. CHANGELOG  each SKILL.md carries a `## Changelog` section
  4. CONTRACT   (Tier-1 skill-contract validation) every backticked repo path / tool /
                script the skill cites EXISTS, and every `<name>` skill it references is a
                PROJECT skill (policy: all skills live in the repo's .claude/skills/). A ref
                that resolves only at user level → GLOBAL-SKILL-REF (move it in); an unknown
                one → DEAD-SKILL-REF. Catches skill rot (a renamed tool leaving a dead ref).
  5. MODES      each surface's MODES CELL agrees with the skill's own `modes:` frontmatter
                (added 2026-09-05, and the root CLAUDE.md table is a fourth surface here).
                Check 1 verifies that a ROW EXISTS; this verifies that the row is TRUE.
                Measured gap: two skills went `requires_fates: true` -> `false` so adapter
                models could use them, all four surfaces went on saying FATES for twelve
                days, and this script reported clean every run in between.

This is the STATIC (Tier-1) gate. Its runtime sibling is tools/smoke_test_skills.py
(Tier-2), which actually runs the read-only backing commands the skills document and
asserts exit 0 — catching runtime bugs a static check can't.

Exit 0 = clean, 1 = any problem. Run from the repo root:
    python3 tools/check_skill_registry.py

Author: Jing Tao with Claude
"""
import re
import sys
from pathlib import Path

import yaml  # strict frontmatter parse (available under both system py3 and a2mc_env)

ROOT = Path(__file__).resolve().parent.parent
SKILLS_DIR = ROOT / ".claude" / "skills"
README = SKILLS_DIR / "README.md"
CATALOG = ROOT / "docs" / "a2mc_reference" / "skills_catalog.md"
AGENTS = ROOT / "AGENTS.md"

# Files shipped to the public repo through the <!-- private --> block filter
# (filter_private in each sync leg). Unbalanced markers make the filter silently
# strip too much (or too little); a marker string appearing INLINE (not on its own line)
# is a landmine — the awk filter matches any line containing it, so it would strip
# everything after it. Both bit us (2026-07-01/02). Check mechanically.
FILTERED_FILES = [ROOT / "CLAUDE.md", ROOT / "README.md", AGENTS, README, CATALOG] \
    + sorted((ROOT / "phases").glob("**/CLAUDE.md"))
OPEN_MARK, CLOSE_MARK = "<!-- private -->", "<!-- /private -->"


def skills_on_disk():
    out = {}
    if SKILLS_DIR.is_dir():
        for d in sorted(SKILLS_DIR.iterdir()):
            sk = d / "SKILL.md"
            if d.is_dir() and sk.is_file():
                out[d.name] = sk.read_text(encoding="utf-8")
    return out


def readme_table_names():
    if not README.is_file():
        return None
    return set(re.findall(r"\[([a-z0-9-]+)\]\(\1/SKILL\.md\)", README.read_text(encoding="utf-8")))


def catalog_names():
    if not CATALOG.is_file():
        return None
    return set(re.findall(r"^###\s+`([a-z0-9-]+)`", CATALOG.read_text(encoding="utf-8"), re.M))


def agents_table_names():
    """Skill names from the 'At a glance' capability table(s) in AGENTS.md — the first
    backticked token of each table row (`| `name` | … |`). Header/separator rows have no
    backticks, so they don't match."""
    if not AGENTS.is_file():
        return None
    return set(re.findall(r"^\|\s*`([a-z0-9-]+)`", AGENTS.read_text(encoding="utf-8"), re.M))


def _frontmatter_block(text):
    m = re.match(r"^---\n(.*?)\n---\n", text, re.S)
    return m.group(1) if m else None


def frontmatter_name(text):
    fm = _frontmatter_block(text)
    if fm is None:
        return None
    nm = re.search(r"^name:\s*(.+)$", fm, re.M)
    return nm.group(1).strip() if nm else None


def frontmatter_field(text, key):
    """Value of a top-level `key: value` line in the SKILL.md frontmatter, or None."""
    fm = _frontmatter_block(text)
    if fm is None:
        return None
    m = re.search(rf"^{re.escape(key)}:\s*(.+)$", fm, re.M)
    return m.group(1).strip() if m else None


# Enforced skill-frontmatter enums (schema mirrors the memory-bucket schema idea):
# visibility drives the public sync; category groups the skills machine-readably.
VISIBILITY = {"public", "private"}
CATEGORY = {"phase", "calibration", "model-dev", "meta", "kb-build", "authoring"}


# ---------------- Tier-1 contract validation ----------------
_BACKTICK = re.compile(r"`([^`]+)`")
_PATHISH = re.compile(r"^[A-Za-z0-9._/-]+$")
_CODE_EXT = (".py", ".sh", ".md", ".yaml", ".yml", ".json", ".txt", ".cdl", ".nc")
_REJECT = set(" <>*{}$|()=\"'\\#;,:")           # command / placeholder / glob markers
# Real repo top-level dirs: a cited path must be ANCHORED in one of these, or it's a
# basename / a path relative to another tree (wiki subdir, source tree, another repo) —
# not a repo-relative path we can validate. This is the precision anchor.
_TOP_DIRS = {p.name for p in ROOT.iterdir() if p.is_dir()}
# A skill reference: `name` directly adjacent to the word "skill".
_SKILLREF = re.compile(r"`([a-z][a-z0-9-]+)`\s+skill\b|\bskill[s]?\s+`([a-z][a-z0-9-]+)`")


def cited_paths(text):
    """Backtick-delimited spans that are unambiguously repo-relative file/dir paths.

    Pairs backticks LINE BY LINE. Inline code never spans lines, and doing so avoids a
    ``` code fence (or any backtick imbalance) desynchronizing span pairing for the rest of
    the document — which silently dropped real path citations and let dead-refs slip past
    the contract check (see memory/dev_logs_offlineagenthardening/20260702f_*)."""
    out = set()
    for line in text.splitlines():
        for span in _BACKTICK.findall(line):
            s = span.strip()
            m = re.match(r"^(.+?):\d+(?:-\d+)?$", s)    # strip trailing :NNN / :NNN-MMM
            if m:
                s = m.group(1)
            if any(c in _REJECT for c in s):
                continue
            if "/" not in s:                            # bare word / flag / param name
                continue
            if not _PATHISH.match(s):
                continue
            if s.split("/")[0] not in _TOP_DIRS:        # not anchored in a real top-level dir
                continue
            if s.startswith(("memory/dev_logs", "memory/ana_logs")):  # informal pointers (may dangle)
                continue
            if not (s.endswith("/") or s.endswith(_CODE_EXT)):        # require a file ext or a dir
                continue
            out.add(s)
    return out


def cited_skills(text):
    # Line by line, same reason as cited_paths (fence-desync robustness).
    out = set()
    for line in text.splitlines():
        for a, b in _SKILLREF.findall(line):
            out.add(a or b)
    return out


def user_skills():
    """User-level skills at ~/.claude/skills/ — used only to give a better error message
    (policy: ALL skills live in the repo; a user-level one should be moved in)."""
    d = Path.home() / ".claude" / "skills"
    return {p.name for p in d.iterdir() if (p / "SKILL.md").is_file()} if d.is_dir() else set()


def contract_check(disk):
    """Blocking problems. Every backticked repo PATH a skill cites must exist; every
    `<name>` skill it references must be a PROJECT skill (policy: all skills live in the
    repo's .claude/skills/). A ref that resolves only at user level → GLOBAL-SKILL-REF
    (move it into the repo); an unknown one → DEAD-SKILL-REF."""
    problems = []
    proj, usr = set(disk), user_skills()
    for name, text in disk.items():
        for p in sorted(cited_paths(text)):
            if not (ROOT / p.rstrip("/")).exists():
                problems.append(f"DEAD-REF: '{name}' cites `{p}` which does not exist in the repo")
        for s in sorted(cited_skills(text)):
            if s == name or s in proj:
                continue
            if s in usr:
                problems.append(f"GLOBAL-SKILL-REF: '{name}' references `{s}`, which exists only "
                                f"at user level (~/.claude/skills/) — copy it into the repo's "
                                f".claude/skills/ (all skills live in the repo)")
            else:
                problems.append(f"DEAD-SKILL-REF: '{name}' references skill `{s}` which has no dir")
    return problems


# phase skill -> the PhaseLogger phase number whose section list it documents.
_PHASE_SKILLS = {"phase0-design": 0, "phase1-exploration": 1, "phase2-screening": 2,
                 "phase3-diagnosis": 3, "phase4-hypothesis": 4, "phase5-testing": 5,
                 "phase6-refinement": 6}


def phase_section_check():
    """Each phase skill's 'expected sections' line must match PhaseLogger._EXPECTED_SECTIONS.

    The list is deliberately written in BOTH places: the emitter needs it to name the gaps,
    and the skill needs it because the skill is where an agent looks. Two copies means drift,
    and drift here is silent — a skill promising sections the emitter no longer names, or
    omitting ones it does, reads as correct either way.

    This is the same one-source -> mechanical-derivation -> gate-at-commit shape the 4-way
    registry parity above already enforces for skill NAMES. Added 2026-08-02 after the lists
    were introduced and drift-checked by hand, i.e. by a habit rather than a guarantee.
    """
    problems = []
    try:
        import sys
        sys.path.insert(0, str(ROOT))
        from tools.phase_logger import PhaseLogger
    except Exception as e:                       # never let this break the whole gate
        return [f"PHASE-SECTIONS: cannot import PhaseLogger to compare ({type(e).__name__}: {e})"]

    for skill, ph in sorted(_PHASE_SKILLS.items()):
        f = SKILLS_DIR / skill / "SKILL.md"
        if not f.is_file():
            continue
        text = f.read_text(encoding="utf-8")
        expected = PhaseLogger._EXPECTED_SECTIONS.get(ph)
        if not expected:
            continue
        want = " \u00b7 ".join(expected)
        if want not in text:
            problems.append(
                f"PHASE-SECTIONS: '{skill}' does not carry phase {ph}'s current section list. "
                f"Expected the line to contain: {want} \u2014 re-sync it with "
                f"PhaseLogger._EXPECTED_SECTIONS[{ph}] in tools/phase_logger.py")
    return problems


def marker_check():
    """Private-comment blocks in every filtered/shipped file must be balanced, and each
    marker must be on its own line (an inline marker is a filter landmine)."""
    problems = []
    for f in FILTERED_FILES:
        if not f.exists():
            continue
        rel = f.relative_to(ROOT)
        opens = closes = 0
        for i, line in enumerate(f.read_text().splitlines(), 1):
            s = line.strip()
            if OPEN_MARK in line:
                if s == OPEN_MARK:
                    opens += 1
                else:
                    problems.append(f"MARKER: {rel}:{i} inline '{OPEN_MARK}' (filter landmine — own line or rephrase)")
            if CLOSE_MARK in line:
                if s == CLOSE_MARK:
                    closes += 1
                else:
                    problems.append(f"MARKER: {rel}:{i} inline '{CLOSE_MARK}' (filter landmine)")
        if opens != closes:
            problems.append(f"MARKER: {rel} unbalanced private blocks ({opens} open != {closes} close)")
    return problems


# A skill may declare that its cross-reference list is RECIPROCAL: every skill it names must
# name it back. The declaration is this exact bolded lead-in, on the bullet that carries the
# names. It is deliberately visible in the rendered doc rather than an HTML comment, so the
# prose a human reads and the string this checker matches are the same object and cannot drift
# apart silently.
RECIPROCAL_MARK = "**Reciprocal skills**"
# A DECLARATION is a bullet that BEGINS with the marker — not any line mentioning it. Without the
# anchor, prose that quotes the marker (a Changelog entry describing this very mechanism, which is
# exactly what happened) is parsed as a second declaration, and every skill name in that sentence
# becomes a claimed reciprocal. Caught immediately: the changelog line naming `markdown-to-pdf` and
# `write-report` produced two false RECIPROCITY problems.
_RECIPROCAL_DECL = re.compile(r"^\s*[-*]\s+" + re.escape(RECIPROCAL_MARK))


def _names_referenced(text):
    """Every skill name the text refers to, in PROSE or as a bare backticked name.

    The back-check cannot use `cited_skills()` alone. That helper is built on `_SKILLREF`, which
    matches only the PROSE forms ("the `x` skill", "skills `x`") — so a reciprocal bullet written
    as ``- **Reciprocal skills** — `write-report`: ...`` is invisible to it and the pair reports as
    one-directional while both halves plainly exist. Found 2026-08-17, the first time a SECOND
    skill used the reciprocity mechanism: `plotting`'s partners all happened to cite it in prose,
    so the gap could not show until then.

    This is the same defect as Defect 1 in `20260816d` — reusing `_SKILLREF` where a bare
    backticked list is what actually appears — fixed there in the DECLARATION parser and missed
    here in the BACK-CHECK. Requiring a specific prose form to satisfy a link is exactly the
    brittleness `feedback_exact_strings_are_contracts` warns about.
    """
    out = set(cited_skills(text))
    for m in re.finditer(r"`([a-z][a-z0-9-]+)`", text):
        out.add(m.group(1))
    return out


def reciprocity_check(disk):
    """Every skill named in a RECIPROCAL_MARK bullet must name the declaring skill back.

    WHY: `plotting`'s cross-references claimed `phase0-design`, `phase3-diagnosis` and
    `scientific-analysis` applied its conventions while none of the three mentioned it. A
    one-directional claim is invisible from the side that matters — the skill that should have
    loaded it — so a whole case's figures were produced without the conventions ever being read
    (`memory/dev_logs_adapterkit/20260816c_*`). Fixing the instances is not enough; the invariant
    has to be enforced or it decays back.

    WHAT WOULD MAKE THIS FAIL (named first, per `feedback_a_check_that_cannot_fail`):
      1. a declared skill does not name the declarer back        -> RECIPROCITY problem
      2. a declared skill does not exist on disk                 -> RECIPROCITY problem
      3. NO skill anywhere declares reciprocity                  -> RECIPROCITY problem

    (3) is the anti-silent-pass guard and the reason this check is worth having. Without it,
    renaming or rewording the marker would make the loop iterate over nothing and report success —
    the exact failure mode of a check that matches a label another file writes
    (`feedback_exact_strings_are_contracts`). At least one skill is expected to declare
    reciprocity; if that stops being true the checker must be edited deliberately, not silently
    satisfied. No skill name is hardcoded here — the mechanism is open to any skill.
    """
    problems, declarers = [], []
    for name, text in sorted(disk.items()):
        lines = text.splitlines()
        for i, line in enumerate(lines):
            if not _RECIPROCAL_DECL.match(line):
                continue
            declarers.append(name)
            # The declaration is ONE bullet that may wrap over indented continuation lines.
            # Collect until the next top-level bullet, the next heading, or a blank line
            # followed by anything that is not an indented continuation.
            block = [line]
            for nxt in lines[i + 1:]:
                if nxt.startswith("## ") or re.match(r"^[-*] ", nxt):
                    break
                if not nxt.strip():
                    break
                block.append(nxt)
            # Collect BARE backticked tokens from the bullet and treat each as a CLAIMED
            # skill name.
            #
            # `_SKILLREF` is deliberately not used: it matches PROSE ("the `x` skill",
            # "skills `x`"), so a comma-separated list of backticked names matches nothing and
            # the check reported "names no skills" on a bullet that plainly named fourteen.
            #
            # And the tokens are NOT intersected with the known skill set, which was the first
            # attempt: intersecting silently discards a typo'd or renamed skill, making the
            # "declared skill does not exist" branch below unreachable — a check that cannot
            # fail (`feedback_a_check_that_cannot_fail`). Verified: with the intersection, the
            # missing-skill case produced no problem at all. A skill name is `[a-z0-9-]+` with
            # no dot, slash or underscore, so excluding those shapes keeps paths and code
            # identifiers out without hiding a real name.
            named = {tok for b in block
                     for tok in re.findall(r"`([a-z][a-z0-9._/-]*)`", b)
                     if re.fullmatch(r"[a-z][a-z0-9-]*", tok)}
            named.discard(name)                      # a self-reference is not a claim
            if not named:
                problems.append(
                    f"RECIPROCITY: '{name}' declares {RECIPROCAL_MARK} but the bullet names no "
                    f"skills (did the list move out of the bullet?)")
            for target in sorted(named):
                if target not in disk:
                    problems.append(
                        f"RECIPROCITY: '{name}' declares '{target}' reciprocal but no such skill exists")
                elif name not in _names_referenced(disk[target]):
                    problems.append(
                        f"RECIPROCITY: '{name}' names '{target}', but '{target}' never names "
                        f"'{name}' back — add the reciprocal pointer or drop it from the list")
    if not declarers:
        problems.append(
            f"RECIPROCITY: no skill declares '{RECIPROCAL_MARK}' anywhere. Either the marker was "
            f"reworded (this check then silently passes — fix the marker) or the last reciprocal "
            f"list was removed on purpose (then update this checker deliberately).")
    return problems


# ---------------------------------------------------------------- modes-column parity (2026-09-05)
#
# The four surfaces each carry a MODES cell beside every skill: the run configurations the skill
# applies to, mirroring its `modes:` frontmatter. Until now this check compared NAMES and COUNTS
# and never read that cell, so the cell could say anything. Measured: `summarize-calibration-round`
# and `compare-calibration-rounds` went `requires_fates: true` -> `false` on 2026-08-24 precisely so
# adapter models could use them, and for twelve days all four surfaces still said FATES -- the
# documentation telling an EcoSIM or PFLOTRAN user that the standardized round close did not apply
# to them, while this checker reported clean on every run.
#
# What it compares: FATES-ness only, which is the one modes fact the tables actually encode. A cell
# reading `any`, `any (HPC)` or `EcoSIM` is not-FATES; a cell naming FATES is FATES; and a cell
# spelling `requires_fates: false` is not-FATES even though the word appears in it, which is the
# trap a naive substring match falls into.
FATES_WORD = re.compile(r"\bFATES\b")


def _fates_from_cell(text):
    """FATES-ness a surface CLAIMS for a skill.

    Order matters. An explicit `requires_fates: <bool>` wins outright. Otherwise only the VALUE is
    read, never the commentary: a catalog line reads "`any` — ATS-specific, no FATES dependency",
    whose tail names FATES while asserting the opposite, so a bare word search over the whole cell
    reports five false drifts. The value is the first backticked token, or the text before the em
    dash when there is none.
    """
    m = re.search(r"requires_fates:\s*(true|false)", text, re.I)
    if m:
        return m.group(1).lower() == "true"
    head = text.split("—")[0]
    tok = re.search(r"`([^`]+)`", head)
    return bool(FATES_WORD.search(tok.group(1) if tok else head))


def _fates_on_disk(skill_text):
    """FATES-ness the SKILL.md declares, or None when it declares nothing."""
    fm = _frontmatter_block(skill_text)
    if fm is None:
        return None
    m = re.search(r"requires_fates:\s*(true|false)", fm, re.I)
    return None if not m else m.group(1).lower() == "true"


def _table_modes(path, row_re):
    if not path.is_file():
        return {}
    out = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        m = row_re.match(line)
        if m:
            out[m.group(1)] = m.group(2)
    return out


def _catalog_modes():
    if not CATALOG.is_file():
        return {}, []
    parts = re.split(r"^###\s+`([a-z0-9-]+)`", CATALOG.read_text(encoding="utf-8"), flags=re.M)
    out, missing = {}, []
    for i in range(1, len(parts), 2):
        name, body = parts[i], parts[i + 1]
        m = re.search(r"^-\s*\*\*Modes:\*\*\s*(.+)$", body, re.M)
        (out.__setitem__(name, m.group(1)) if m else missing.append(name))
    return out, missing


def modes_check(disk):
    """Every surface's modes cell must agree with the skill's own frontmatter."""
    problems = []
    truth = {n: _fates_on_disk(t) for n, t in disk.items()}
    cat, cat_missing = _catalog_modes()
    surfaces = {
        ".claude/skills/README.md": _table_modes(
            README, re.compile(r"^\|\s*\[([a-z0-9-]+)\]\([^)]*\)\s*\|([^|]*)\|")),
        "AGENTS.md": _table_modes(
            AGENTS, re.compile(r"^\|\s*`([a-z0-9-]+)`\s*\|([^|]*)\|")),
        "CLAUDE.md": _table_modes(
            ROOT / "CLAUDE.md", re.compile(r"^\|\s*`([a-z0-9-]+)`\s*\|([^|]*)\|")),
        "docs/a2mc_reference/skills_catalog.md": cat,
    }
    for surface, rows in surfaces.items():
        for name, cell in sorted(rows.items()):
            want = truth.get(name)
            if want is None:          # not on disk, or declares no requires_fates
                continue
            if _fates_from_cell(cell) != want:
                problems.append(
                    f"MODES DRIFT: {surface} marks '{name}' as "
                    f"{'FATES' if not want else 'not FATES'} but its SKILL.md declares "
                    f"requires_fates: {str(want).lower()} — the cell reads {cell.strip()!r}. "
                    f"A modes cell nobody checks is how two skills stayed documented as "
                    f"FATES-only for twelve days after they were made generic")
    for name in sorted(cat_missing):
        if name in truth:
            problems.append(
                f"MODES MISSING: docs/a2mc_reference/skills_catalog.md entry '{name}' has no "
                f"'- **Modes:**' line, so its modes cell cannot be checked at all")
    return problems


def main():
    disk = skills_on_disk()
    if not disk:
        print(f"ERROR: no skills under {SKILLS_DIR}"); return 1
    readme, catalog, agents = readme_table_names(), catalog_names(), agents_table_names()
    if readme is None:
        print(f"ERROR: {README} not found"); return 1
    if catalog is None:
        print(f"ERROR: {CATALOG} not found"); return 1
    if agents is None:
        print(f"ERROR: {AGENTS} not found"); return 1

    disk_names = set(disk)
    problems = []
    for n in sorted(disk_names - readme):
        problems.append(f"DRIFT: '{n}' on disk but missing from the README 'Current skills' table")
    for n in sorted(readme - disk_names):
        problems.append(f"DRIFT: README table lists '{n}' but no skill dir exists")
    for n in sorted(disk_names - catalog):
        problems.append(f"DRIFT: '{n}' on disk but missing from docs/a2mc_reference/skills_catalog.md")
    for n in sorted(catalog - disk_names):
        problems.append(f"DRIFT: catalog lists '{n}' but no skill dir exists")
    for n in sorted(disk_names - agents):
        problems.append(f"DRIFT: '{n}' on disk but missing from the AGENTS.md 'At a glance' table")
    for n in sorted(agents - disk_names):
        problems.append(f"DRIFT: AGENTS.md table lists '{n}' but no skill dir exists")

    for name, text in disk.items():
        # Strict YAML parse of the frontmatter block. The field-reads below are regex-based
        # (lenient) and miss real YAML breakage — e.g. an unquoted ": " in the description —
        # that fails the pytest frontmatter parse (tests/test_offline_agent_mode.py). Parse
        # strictly here, in the enforced pre-commit gate, so the checker and the pytest agree.
        fm_block = _frontmatter_block(text)
        if fm_block is None:
            problems.append(f"FRONTMATTER: '{name}' SKILL.md has no `---`-delimited frontmatter block")
        else:
            try:
                yaml.safe_load(fm_block)
            except yaml.YAMLError as e:
                mark = getattr(e, "problem_mark", None)
                loc = f" (line {mark.line + 1}, col {mark.column + 1})" if mark is not None else ""
                problems.append(
                    f"FRONTMATTER-YAML: '{name}' frontmatter is not valid YAML{loc}: "
                    f"{getattr(e, 'problem', str(e))} — commonly an unquoted ': ' in the description")
        fm = frontmatter_name(text)
        if fm is None:
            problems.append(f"NAME: '{name}' SKILL.md has no `name:` in frontmatter")
        elif fm != name:
            problems.append(f"NAME: '{name}' frontmatter name is '{fm}' (must match dir)")
        # CHANGELOG-LAST exists because the PUBLIC sync strips a skill's changelog: it is
        # development history (dated entries naming dev logs, versions, the defects behind each
        # edit), the same class of content as memory/dev_logs*/ and a <!-- private --> block. The
        # strip runs from the `## Changelog` heading to the next `## ` heading, and a section sitting
        # AFTER the changelog is what makes that rule delicate. Measured 2026-09-15 on a staged sync:
        # `phase5-testing` kept `## Log it as a LIVING record` after its changelog, holding phase 5's
        # expected-section line, and a truncate-to-EOF strip deleted it -- caught only because the
        # staged destination then failed PHASE-SECTIONS. Requiring the changelog to be LAST makes the
        # strip trivially exact and stops a new skill from reintroducing the hazard. A stripped copy
        # (heading + pointer line, nothing after) satisfies both rules, which it must: this checker
        # ships and runs in the public repo.
        cl = re.search(r"^## Changelog\s*$", text, re.M)
        if cl is None:
            problems.append(f"CHANGELOG: '{name}' SKILL.md has no `## Changelog` section")
        else:
            after = [ln for ln in text[cl.end():].splitlines() if ln.startswith("## ")]
            if after:
                problems.append(
                    f"CHANGELOG-LAST: '{name}' SKILL.md has {len(after)} section(s) after "
                    f"`## Changelog` ({', '.join(a.strip() for a in after[:3])}). The changelog must "
                    f"be the LAST section: the public sync strips it, and content after it is what "
                    f"a strip can silently take with it. Move those sections above the changelog.")
        vis = frontmatter_field(text, "visibility")
        if vis is None:
            problems.append(f"FRONTMATTER: '{name}' SKILL.md missing `visibility:` (one of {sorted(VISIBILITY)})")
        elif vis not in VISIBILITY:
            problems.append(f"FRONTMATTER: '{name}' visibility '{vis}' invalid (must be one of {sorted(VISIBILITY)})")
        cat = frontmatter_field(text, "category")
        if cat is None:
            problems.append(f"FRONTMATTER: '{name}' SKILL.md missing `category:` (one of {sorted(CATEGORY)})")
        elif cat not in CATEGORY:
            problems.append(f"FRONTMATTER: '{name}' category '{cat}' invalid (must be one of {sorted(CATEGORY)})")

    problems += contract_check(disk)
    problems += reciprocity_check(disk)
    problems += marker_check()
    problems += phase_section_check()
    problems += modes_check(disk)

    print(f"Skills on disk : {len(disk_names)}")
    print(f"README table   : {len(readme)}")
    print(f"Catalog        : {len(catalog)}")
    print(f"AGENTS.md table: {len(agents)}")
    print()
    if problems:
        print(f"✘ {len(problems)} problem(s):")
        for p in problems:
            print(f"  - {p}")
        return 1
    print("✔ registry + contracts clean — in sync, names match, versioned, cited paths/skills exist, private markers balanced")
    return 0


if __name__ == "__main__":
    sys.exit(main())
