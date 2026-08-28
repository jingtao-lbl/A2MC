#!/usr/bin/env python3
"""Validate the git-synced Claude memory bucket (.claude_memory/).

Enforces the frontmatter schema from docs/29_Claude_Memory_Bucket_Adoption_Plan.md +
CLAUDE.md branch rule (every .claude_memory memory sets machine/visibility/scope/type).
No-ops if .claude_memory/ is absent (e.g. the public clone), so it is safe to ship in tools/.

ERRORS (exit 1): a memory file missing a required frontmatter field, an invalid enum
value, a `visibility: public` file that contains a personal host path, or a DEAD LINK in
MEMORY.md (an index line pointing to a deleted/renamed memory — the removal backstop).
WARNINGS (exit 0): a memory not linked from MEMORY.md; a memory added on/after
PROVENANCE_SINCE with no pointer to the log that produced it.
"""
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BUCKET = ROOT / ".claude_memory"

MACHINE = {"shared", "mac", "perlmutter"}
VISIBILITY = {"private", "public"}
# Model subjects first, then technique/meta. `ecosim` + `ats` added 2026-07-30: the
# vocabulary predated the adapter kit, so memories about the newer onboarded models
# had to land under the generic `modeling`/`a2mc`.
SCOPE = {"fates", "elm", "elm-fates", "ecosim", "ats", "modeling", "hpc", "a2mc", "process"}
TYPE = {"user", "feedback", "project", "reference"}
# Personal host paths that must never appear in a visibility: public memory.
PERSONAL = re.compile(r"~|/global/homes/|/global/cfs/cdirs/|/pscratch/|/dvs_ro/cfs/")

SKIP = {"MEMORY.md", "CLAUDE.md"}

# --- provenance (memory -> log) -----------------------------------------------------
# The link graph was one-directional: `check_log_conformance` REQUIRES a log to name the
# memories it used (L4/L6), but nothing ever asked a memory to name the log that produced
# it. Cause: the body template in `manage-auto-memory` came from the harness's generic
# auto-memory format, whose only link affordance is [[memory]] -> sideways, never back to a
# log. Measured 2026-08-03: 48/107 memories mentioned a log stem, all incidentally in prose;
# 0 had a structured pointer.
#
# Date-scoped like check_log_conformance's L4 so the 59 pre-existing memories are not
# retroactively flagged. A memory file carries no date, but GIT DOES — the add date comes
# from `git log --diff-filter=A`. A file with no add date is new/uncommitted, i.e. being
# written now, so it is in scope.
PROVENANCE_SINCE = "2026-08-03"
# NO trailing \b: a citation is usually the FULL filename (`20260803c_Log_Spec_...`), and `_` is a
# word char, so `[a-z]{1,3}\b` refuses to match there. That dropped 23 of 48 citing memories, found
# by cross-checking two independent counts rather than by reading the regex.
_LOG_STEM = re.compile(r"\b20\d{6}[a-z]{1,3}")            # a dated log stem, e.g. 20260803c
_PROVENANCE_EXEMPT = {"user"}                             # a fact about Jing has no originating log
# A citation that carries a PATH is unambiguous, unlike a bare stem (see _source_logs).
_SOURCE_PATH = re.compile(
    r"(?:memory/(?:dev_logs[a-z_]*|ana_logs)|use_cases/[A-Za-z0-9_.-]+/memory/logs)"
    r"(?:/[A-Za-z0-9_.-]+)*/20\d{6}[a-z]{1,3}_[A-Za-z0-9_.-]+\.md")
_SOURCE_LINE = re.compile(r"^\*\*Source:\*\*(.+?)(?:\n\n|\Z)", re.M | re.S)


def _source_logs(text):
    """Yield (stem, [every log with that stem]) for each stem on a memory's `**Source:**` line.

    TWO properties of log stems make the naive form of this check wrong, and both were found
    by running it (2026-08-07):

    1. **Stems are NOT unique.** They are per-directory sequences, so one stem names several
       unrelated logs across branch dirs — `20260731b` matches FOUR (adapter-kit, PFLOTRAN,
       surrogate, ana_logs). Resolving to the first hit and stopping reported a PFLOTRAN
       memory against an EcoSIM log and called the link broken. Hence a LIST: the caller
       passes if ANY candidate names the memory.
    2. **A stem may resolve to nothing on this branch, legitimately.** `.claude_memory/` is
       branch-scoped content while logs live in per-branch directories, so a memory can cite a
       log on a sibling branch — `feedback_schedule_periodic_reviews_with_a_real_mechanism`
       cites `20260801p`, which exists only on `A2MC-adapter-kit-ATS`. An empty list means
       SKIP, never fail: failing it would make the verdict depend on which branch is checked
       out, the defect `feedback_a_gate_must_measure_the_branch_not_the_disk` names.

    3. **A stem is ambiguous even WITHIN one directory.** `memory/dev_logs_adapterkit/` holds two
       `20260731a` logs, two `20260818a`, two `20260818e` -- the sequential-letter convention has
       been broken three times. So a directory prefix is not sufficient either; only the full path
       identifies a log.

    Hence: **if the citation carries a path, that path wins** and no stem globbing happens. A bare
    stem keeps the legacy any-directory search. Measured 2026-08-19: bare-stem resolution produced
    TWO false "wrong pointer" verdicts in one audit -- `feedback_taskcreate_per_skill_step` cites
    `main`'s 20260810a and was matched against this branch's unrelated 20260810a, and
    `reference_ecosim_forc_periods_and_spinup` cites a CALIBRATION log under `use_cases/` that this
    function never searched at all. Both pointers were correct; the resolver was not.
    """
    m = _SOURCE_LINE.search(text)
    if not m:
        return
    body = m.group(1)
    # An explicit path is unambiguous -- honor it and skip the stem search entirely.
    explicit = _SOURCE_PATH.findall(body)
    for rel in dict.fromkeys(explicit):
        yield rel, [ROOT / rel] if (ROOT / rel).is_file() else []
    if explicit:
        return
    # Deliberately NOT widened to `use_cases/*/memory/logs`. A calibration log IS a legitimate
    # source (`reference_ecosim_forc_periods_and_spinup` has one), but it must be cited BY PATH:
    # adding those dirs to the bare-stem search was measured on 2026-08-19 to invent a fresh false
    # positive (a FATES upstream-contribution memory matched an EcoSIM probe log sharing stem
    # `20260811b`) while fixing nothing that the explicit-path branch above does not already fix.
    log_dirs = sorted(ROOT.glob("memory/dev_logs*")) + [ROOT / "memory" / "ana_logs"]
    for stem in dict.fromkeys(_LOG_STEM.findall(body)):           # de-duped, order-stable
        hits = []
        for d in log_dirs:
            if d.is_dir():
                hits += list(d.glob(f"{stem}_*.md")) + list(d.glob(f"*/{stem}_*.md"))
        yield stem, hits



def _retired_stems():
    """Memory stems that once existed in the bucket and were DELETED, per git history.

    A dead wiki-link is normally INFO — the convention deliberately allows forward-looking links to
    memories not yet written. But a link to a target that *used to exist* is not forward-looking, it
    is a retirement that left its citations behind. Measured 2026-08-19: the 2026-08-12 downstream-project
    retirement (546cce99) left THREE dangling citations for a week, invisible to every mechanical
    check because MEMORY.md stayed consistent. One git call, so dead links stay cheap to classify.
    """
    try:
        out = subprocess.run(["git", "log", "--diff-filter=D", "--name-only", "--format=",
                              "--", ".claude_memory/"],
                             cwd=ROOT, capture_output=True, text=True, timeout=20).stdout
    except (OSError, subprocess.SubprocessError):
        return set()
    stems = set()
    for line in out.split():
        name = Path(line).name
        if name.endswith(".md") and name not in ("MEMORY.md", "CLAUDE.md"):
            stems.add(name[:-3])
    # A stem that exists again today was renamed/restored, not retired.
    return {s for s in stems if not (BUCKET / f"{s}.md").exists()}


def _staged_memories() -> set:
    """Memory filenames staged in THIS commit — the nudge window for provenance.

    Scoped to staged rather than "modified since the cutoff" deliberately. Measured 2026-08-05: the
    modified-since form would raise 14 standing warnings, because bulk edits (the 19 `name:` fixes)
    touched legacy memories that predate the rule. 14 permanent warnings train you to ignore the gate.
    Staged-only fires exactly when someone is editing the file — the moment they can act on it — and
    goes quiet again afterwards. Empty outside a commit, so a manual run adds nothing.
    """
    try:
        out = subprocess.run(["git", "diff", "--cached", "--name-only"],
                             cwd=ROOT, capture_output=True, text=True, timeout=10).stdout
        return {Path(l).name for l in out.split() if l.startswith(".claude_memory/")}
    except (OSError, subprocess.SubprocessError):
        return set()


def _added_date(path: Path) -> str:
    """YYYY-MM-DD this file was first committed; '' if untracked/new or git is unavailable."""
    try:
        out = subprocess.run(
            ["git", "log", "--diff-filter=A", "--format=%ad", "--date=short", "--", str(path)],
            cwd=ROOT, capture_output=True, text=True, timeout=10,
        ).stdout.strip().splitlines()
        return out[-1] if out else ""       # last line = the ORIGINAL add, not a later re-add
    except (OSError, subprocess.SubprocessError):
        return ""


def frontmatter(text):
    """Return the frontmatter block (between the first two --- lines) or None."""
    lines = text.split("\n")
    if not lines or lines[0].strip() != "---":
        return None
    end = next((i for i in range(1, len(lines)) if lines[i].strip() == "---"), None)
    return None if end is None else "\n".join(lines[1:end])


def top_level(fm, key):
    """Value of a top-level `key: value` line in the frontmatter, or None."""
    m = re.search(rf"^{key}:\s*(.+?)\s*$", fm, re.M)
    return m.group(1).strip() if m else None


def main():
    if not BUCKET.is_dir():
        print("check_memory_bucket: no .claude_memory/ (skip)")
        return 0

    files = sorted(f for f in BUCKET.glob("*.md") if f.name not in SKIP)
    staged = _staged_memories()
    RETIRED = _retired_stems()          # one git call, reused for every file's wiki-links
    index = (BUCKET / "MEMORY.md").read_text(encoding="utf-8") if (BUCKET / "MEMORY.md").exists() else ""

    errors, warnings = [], []
    for f in files:
        rel = f.name
        text = f.read_text(encoding="utf-8")
        fm = frontmatter(text)
        if fm is None:
            errors.append(f"{rel}: no YAML frontmatter block")
            continue

        machine = top_level(fm, "machine")
        visibility = top_level(fm, "visibility")
        scope = top_level(fm, "scope")
        # `type` may be top-level or nested under a `metadata:` block — accept either.
        tmatch = re.search(r"^\s*type:\s*(.+?)\s*$", fm, re.M)
        typ = tmatch.group(1).strip() if tmatch else None

        for name, val, allowed in (
            ("machine", machine, MACHINE),
            ("visibility", visibility, VISIBILITY),
            ("scope", scope, SCOPE),
            ("type", typ, TYPE),
        ):
            if val is None:
                errors.append(f"{rel}: missing frontmatter field `{name}`")
            elif val not in allowed:
                errors.append(f"{rel}: invalid `{name}: {val}` (allowed: {', '.join(sorted(allowed))})")

        if "-" in f.stem:
            # Hyphens are reserved for MODEL names (ELM-FATES, api-31-0, elm-fates in `scope:`).
            # Keeping them out of memory filenames means a hyphen anywhere in a memory identifier
            # unambiguously separates a model name, never words. Skills use hyphens (`a2mc-init`);
            # memories deliberately do not (PI, 2026-08-03).
            errors.append(f"{rel}: memory filenames use snake_case — no hyphens. Hyphens are "
                          f"reserved for model names (ELM-FATES); rename to `{f.stem.replace('-', '_')}.md` "
                          f"and update its MEMORY.md pointer + any [[links]]")

        # A [[link]] whose HYPHENATED form has an existing UNDERSCORE twin is a typo, never a
        # forward-looking link — so this catches the defect class without touching the convention that
        # allows links to memories not yet written. Mechanism (main's 20260805e): a divergent `name:`
        # induces an author to write [[that-value]]; the name==stem gate below removes the GENERATOR,
        # this removes the ARTIFACTS it already produced.
        for link in set(re.findall(r"\[\[([A-Za-z0-9_-]+)\]\]", text)):
            # A link to a RETIRED memory is a citation the retirement forgot to resolve — distinct
            # from a forward-looking link, which stays legitimate. See _retired_stems().
            if not (BUCKET / f"{link}.md").exists() and link in RETIRED:
                errors.append(f"{rel}: dead wiki-link [[{link}]] — that memory was RETIRED, so this "
                              f"is a citation the retirement left behind, not a forward-looking link. "
                              f"Demote it to plain prose naming where the content went.")
            if "-" in link and (BUCKET / f"{link.replace('-', '_')}.md").exists():
                errors.append(f"{rel}: dead wiki-link [[{link}]] — hyphenated twin of the existing "
                              f"`{link.replace('-', '_')}.md`; links resolve by FILENAME, so use underscores")

        nm = top_level(fm, "name")
        if not nm:
            errors.append(f"{rel}: missing frontmatter field `name`")
        elif nm.strip().strip("\"'") != f.stem:
            # `name:` IS the filename stem (manage-auto-memory §1). Nothing was checking it, so
            # 19 of 107 had drifted by 2026-08-03 — 5 to a hyphenated slug, 14 to a prose title.
            # It matters because [[wiki-links]] resolve by STEM: a memory whose `name:` says
            # something else is unfindable by the identity it declares.
            errors.append(f"{rel}: `name: {nm}` must equal the filename stem `{f.stem}` "
                          f"(wiki-links resolve by stem, so a divergent name is unreachable)")
        if not top_level(fm, "description"):
            errors.append(f"{rel}: missing frontmatter field `description`")

        if visibility == "public":
            hit = PERSONAL.search(text)
            if hit:
                errors.append(f"{rel}: visibility: public but contains a personal host path "
                              f"('{hit.group(0)}') — genericize or make it private")

        if f"({rel})" not in index:
            warnings.append(f"{rel}: not linked from MEMORY.md")

        # Provenance: name the log that produced this memory, so the graph is bidirectional.
        if typ not in _PROVENANCE_EXEMPT and not _LOG_STEM.search(text):
            added = _added_date(f)
            # In scope if NEW since the rule, or being EDITED right now (the nudge window).
            is_staged = rel in staged
            if not added or added >= PROVENANCE_SINCE or is_staged:
                when = ("edited in this commit" if is_staged and added and added < PROVENANCE_SINCE
                        else f"added {added}" if added else "new/uncommitted")
                warnings.append(
                    f"{rel}: no log reference ({when}) — add a `**Source:**` line naming the "
                    f"dev/ana log this came from (e.g. `20260803c`), so a reader can find the "
                    f"reasoning. See the `manage-auto-memory` skill.")

        # The OTHER half of the bidirectional link: a Source pointer must land somewhere
        # that CLAIMS this memory. Existence alone is not enough and was never the failure
        # mode — on 2026-08-07 two memories cited 20260807c, a real log that contains none
        # of their content, and every gate stayed green. A pointer that resolves but lies
        # is worse than an absent one, because a reader follows it and is misled.
        for stem, logs in _source_logs(text):
            if not logs:
                continue          # cross-branch reference — legitimate, see _source_logs
            if any(f.stem in p.read_text(encoding="utf-8", errors="replace") for p in logs):
                continue          # some log with that stem claims it — link satisfied
            where = logs[0].relative_to(ROOT) if len(logs) == 1 else f"{len(logs)} logs share this stem"
            warnings.append(
                f"{rel}: `**Source:** {stem}` points at a log that never names this memory "
                f"({where}). Either the pointer is wrong, or that log needs "
                f"`**Memory written:** {f.stem}` in its 'Skills and memory invoked' section.")

    # Removal backstop: every bare (<slug>.md) link in MEMORY.md must resolve to a real
    # memory file. A dead link means a memory was deleted without pruning its index line
    # — the symmetric-removal gap (mirrors check_skill_registry.py's DRIFT check for skills).
    existing = {f.name for f in files}
    for target in re.findall(r"\(([A-Za-z0-9_][A-Za-z0-9_.-]*\.md)\)", index):
        if target in SKIP or target in existing:
            continue
        errors.append(f"MEMORY.md: dead link to `{target}` — file does not exist; prune the "
                      f"index line (or restore the memory)")

    # CONTRACT: a memory that cites a concrete CODE artifact must cite one that exists.
    # Deliberately narrow, because the first cut produced 6/6 false positives on real data:
    #   - `tools/fates_utils.get_szpf_range`  -> module.function, not a path
    #   - `docs/39`                           -> doc shorthand, real file is docs/39_*.md
    #   - `docs/23_..._Plan.md`               -> a DEMO-branch doc, legitimately absent here
    # So: code dirs only (docs are exempt per `feedback_dead_refs_to_internal_docs_ok`), and
    # only tokens ending in a real source extension — that alone excludes module.function.
    # [[wiki-links]] and prose skill names stay OUT (forward-looking links are allowed, and
    # external skills are legitimately cited); those remain the `memory-checkup` judgment pass.
    CITED = re.compile(r"`((?:tools|scripts|phases|models)/[A-Za-z0-9_./-]+\.(?:py|sh|yaml|json))`")
    # NB anchored so it does not match an EXTERNAL kit path such as
    # `${A2MC_MODEL_PATH}/python_tools/.claude/skills/<name>` (the EcoSIM developer's
    # own skills, referenced in place by design).
    CITED_SKILL = re.compile(r"(?<![/\w.])\.claude/skills/([a-z0-9-]+)")
    for f in files:
        text = f.read_text(encoding="utf-8")
        for tgt in sorted(set(CITED.findall(text))):
            if any(ch in tgt for ch in "*{<"):          # globs/placeholders are not paths
                continue
            if not (ROOT / tgt).exists():
                errors.append(f"{f.name}: cites `{tgt}` which does not exist")
        for s in sorted(set(CITED_SKILL.findall(text))):
            if not (ROOT / ".claude" / "skills" / s).is_dir():
                errors.append(f"{f.name}: cites skill `{s}` which does not exist")

    for w in warnings:
        print(f"  [warn] {w}")
    if errors:
        print(f"\n✘ {len(errors)} problem(s):")
        for e in errors:
            print(f"  - {e}")
        return 1
    print(f"✔ .claude_memory/: {len(files)} memories, frontmatter valid"
          # NB "warning(s)", not "unindexed": this counter is EVERY warning above (a missing
          # `**Source:**` line, an unindexed file, ...). Labelling them all "unindexed" sent a
          # reader looking for a MEMORY.md gap that did not exist (2026-08-06).
          + (f" ({len(warnings)} warning(s) — see above)" if warnings else ""))
    return 0


if __name__ == "__main__":
    sys.exit(main())
