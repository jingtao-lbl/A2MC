#!/usr/bin/env python3
"""check_calibration_log_conformance.py — assert a CALIBRATION log matches the `calibration-log`
skill's contract.

The sibling `check_log_conformance.py` governs the DEVELOPMENT streams (`memory/dev_logs*/`,
`memory/ana_logs/`) and its contract does not fit here: a calibration log has no
`Version`/`Branch` header and no `Summary`/`Files Changed`/`Verification` sections. Measured over
the 127 committed calibration logs before writing this, `check_log_conformance.py` would have
failed all 38 free-form ones on sections they are not supposed to have.

The `calibration-log` skill defines TWO types and this tool checks both:

  TYPE A — PHASE LOG (`PhaseLogger`-generated; stem carries `_phase{N}_`)
      Each phase has its own purpose in reaching the calibration goal, so each has its OWN
      required sections. Those live in `PhaseLogger._EXPECTED_SECTIONS` and are READ FROM THERE
      (via `ast`, below) rather than copied — a second copy of a contract is how the leak-token
      list and this repo's own log spec both drifted (see `20260814b`, `20260814e`).

  TYPE B — FREE-FORM SESSION LOG (exploratory work that does not map to a phase)
      Lighter: header + the shared "record what you CONSULTED" block + cross-references.

WHAT THIS DOES NOT DO. `check_offline_log_evidence.py` already covers the EVIDENCE dimension for
analysis phases (first-hand artifact vs restatement, confidence-without-a-test, orphan numbers,
a figure missing its caption/script). This tool is STRUCTURE only; the two are complementary and
neither subsumes the other. Run both.

Non-retroactive by construction, like its sibling: a rule is applied only to logs dated on or
after the day it entered the skill, and the boundary day is a WARNING (a date cannot express when
a rule reached this branch).

Exit: 0 clean · 1 warnings only · 2 any error.

Usage:
    python3 tools/check_calibration_log_conformance.py <log.md | logs_dir | --site use_cases/<site>>

Author: Jing Tao with Claude.
"""
import ast
import os
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent

# The day the `calibration-log` skill added "Skills and memory invoked" to BOTH log types
# (its changelog: "2026-08-01: Added **'Skills and memory invoked'** (both log types)").
CAPABILITY_SECTION_SINCE = "20260801"

# The day `PhaseLogger._EXPECTED_SECTIONS` entered the generator (`e3a1c427`, "Offline phase logs
# now carry the handshake, and name their own gaps"). Logs written before it had no per-phase
# section contract to meet. Measured before setting this: applied retroactively the rule produced
# 401 errors across 89 phase logs — i.e. it would have condemned nearly the whole calibration
# record for missing sections that did not exist when they were written, which is noise, not a
# gate. Same non-retroactivity discipline as CAPABILITY_SECTION_SINCE.
PHASE_SECTIONS_SINCE = "20260801"

# The day the PI required a phase log to NAME the skills it must have invoked (C11) and the chain
# to be checked for cumulativeness (C12).
MUST_INVOKE_SINCE = "20260822"
CHAIN_CUMULATIVE_SINCE = "20260822"

#: A Phase-6 log that ROUTES 6->3 must carry the rethink, not just the routing decision.
#: `phase6-refinement` Step 4 owns the protocol and `calibration-log`'s Enrichment contract states
#: the logging obligation; this is the enforcement, because the requirement was prose only.
#:
#: THE GAP THIS CLOSES, measured 2026-08-23: a Phase-6 log that routed `rethink_6to3` contained ZERO
#: occurrences of "Rethink" and passed this checker clean. The next cycle reads the LOG, not the
#: state enum, so a rethink recorded nowhere is a cycle that starts blind -- and three consecutive
#: rethinks in one round then carried the same base and target framing forward unexamined.
RETHINK_SECTION_SINCE = "20260823"

#: How a phase-6 log announces it is routing 6->3 rather than converging or redesigning.
#: `PhaseLogger.log_refinement(next_action=...)` emits this heading verbatim.
_ITERATE = re.compile(r"^##\s*Next Action:\s*iterate\s*$", re.M | re.I)
#: The section that must then be present. Accept any heading containing "Rethink" so a log may title
#: it "The Rethink (6->3)" or "Rethink protocol" without tripping a spelling gate.
_RETHINK_HDR = re.compile(r"^##+\s*.*\bRethink\b.*$", re.M | re.I)

# C11 — the skills a phase log MUST have invoked, by phase. A phase log is produced BY
# `calibration-log` (it owns the PhaseLogger contract: the offline layout, the handshake, the
# living-record rule, the artifacts table) and BY that phase's own skill (which owns what the phase
# must actually do). Writing either from memory is the failure `check_skill_claims.py` exists for,
# one level down: that tool asks whether a claim is TRUE, this one asks whether the claim is THERE.
# **The pair is what has teeth.** Alone, C11 could be satisfied by naming a skill you never opened,
# and check_skill_claims alone permits naming nothing. Together: you must claim these, and the
# claim must be true against the session transcript.
_PHASE_SKILL = {0: "phase0-design", 1: "phase1-exploration", 2: "phase2-screening",
                3: "phase3-diagnosis", 4: "phase4-hypothesis", 5: "phase5-testing",
                6: "phase6-refinement"}
_ALWAYS_SKILL = "calibration-log"
#: Required only when the log actually has a figure. "Figures are always preferred" (PI), so the
#: absence of one is not itself an error here -- but a figure produced without `plotting` skips the
#: view-the-rendered-PNG check, which is the one thing that catches a broken figure.
_FIGURE_SKILL = "plotting"

# TYPE A ---------------------------------------------------------------------------------------
# `PhaseLogger` offline stem: YYYYMMDDx_phase{N}_{name}_r{RR}[_c{EE}[_iter{II}]]_{descriptor}
_PHASE_STEM = re.compile(
    r"^(?P<date>\d{8})(?P<letter>z*[a-z])_phase(?P<phase>[0-7])_(?P<name>[a-z0-9]+)"
    r"_r(?P<round>\d{2})(?:_c(?P<cycle>\d{2}))?(?:_iter(?P<iter>\d{2}))?_(?P<desc>.+)\.md$")
# Header fields PhaseLogger always emits (verified: 89/89 committed phase logs carry all four).
_PHASE_HEADER = ["Site", "Phase", "Round", "Date"]
# Emitted for every phase log (89/89).
_PHASE_ALWAYS = ["Iteration Context"]
# The offline trailer's placeholder for an unfilled handshake field.
_HANDSHAKE_MISS = "_(not provided"

# TYPE B ---------------------------------------------------------------------------------------
_FREE_STEM = re.compile(r"^(?P<date>\d{8})(?P<letter>z*[a-z])_(?P<topic>.+)\.md$")
# Measured across the 38 committed free-form logs: Date 38/38, Author 38/38, Site 37/38,
# Type 36/38. The first two are required; the other two are warnings, since a genuinely
# site-agnostic note legitimately has no Site.
_FREE_HEADER_REQUIRED = ["Date", "Author"]
_FREE_HEADER_EXPECTED = ["Site", "Type"]
_FREE_SECTIONS = ["Cross-references"]

_NOT_LOGS = {"CLAUDE.md", "README.md", "MEMORY.md", "index.md"}


# ------------------------------------------------------------------------------------------
# Read the per-phase contract from phase_logger.py WITHOUT importing it.
# ------------------------------------------------------------------------------------------
def _str_const(node):
    """A string literal, across AST vintages. Python 3.8 replaced `ast.Str` with `ast.Constant`;
    the pre-commit hook falls back to bare python3, which is 3.6 on this machine, so supporting
    only `Constant` made the parser return {} there — and a silently-empty contract means the
    per-phase check quietly does nothing on exactly the interpreter the hook may pick."""
    if isinstance(node, getattr(ast, "Constant", ())) and isinstance(node.value, str):
        return node.value
    if isinstance(node, getattr(ast, "Str", ())):          # <3.8
        return node.s
    raise ValueError("not a string literal")


def _int_const(node):
    if isinstance(node, getattr(ast, "Constant", ())) and isinstance(node.value, int):
        return node.value
    if isinstance(node, getattr(ast, "Num", ())):          # <3.8
        return node.n
    raise ValueError("not an int literal")


def load_expected_sections():
    """Parse `PhaseLogger._EXPECTED_SECTIONS` out of the source.

    Deliberately `ast`, not `import`: this checker must stay stdlib-only and runnable under the
    pre-commit hook's interpreter, and `tools/phase_logger.py` does not import there (it needs
    `dataclasses`, absent on the bare python3 on this machine). Parsing keeps ONE source of truth
    for the per-phase contract while adding no runtime dependency — the alternative, a second
    hardcoded copy, is exactly the drift this repo has now been bitten by twice.

    Returns {phase:int -> [section, ...]}, or {} if the constant cannot be found (in which case
    the per-phase check is skipped rather than silently passing everything — see C4).
    """
    src = (REPO / "tools" / "phase_logger.py")
    if not src.is_file():
        return {}
    try:
        tree = ast.parse(src.read_text(errors="replace"))
    except SyntaxError:
        return {}

    consts = {}

    def value(node):
        """Evaluate list literals, names bound to lists, and `+` between them."""
        if isinstance(node, ast.List):
            out = []
            for e in node.elts:
                out.append(_str_const(e))
            return out
        if isinstance(node, ast.Name):
            return list(consts[node.id])
        if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Add):
            return value(node.left) + value(node.right)
        raise ValueError("unsupported node")

    for node in ast.walk(tree):
        if not isinstance(node, ast.Assign) or len(node.targets) != 1:
            continue
        tgt = node.targets[0]
        if not isinstance(tgt, ast.Name):
            continue
        if tgt.id == "_RUN_SPINE":
            try:
                consts["_RUN_SPINE"] = value(node.value)
            except Exception:
                pass
        elif tgt.id == "_EXPECTED_SECTIONS" and isinstance(node.value, ast.Dict):
            out = {}
            for k, v in zip(node.value.keys, node.value.values):
                try:
                    out[_int_const(k)] = value(v)
                except Exception:
                    return {}
            return out
    return {}


class Finding:
    __slots__ = ("path", "code", "level", "msg")

    def __init__(self, path, code, level, msg):
        self.path, self.code, self.level, self.msg = path, code, level, msg

    def __str__(self):
        tag = "ERROR" if self.level == "error" else "warn "
        return "  %s [%s] %s: %s" % (tag, self.code, self.path.name, self.msg)


def _headers(text):
    return set(re.findall(r"^\*\*([A-Za-z ]+):\*\*", text, re.M))


def _sections(text):
    """`## Foo` headings. PhaseLogger appends free text to some headings ('## Next Action: ...'),
    so the leading token before ':' is kept as well — otherwise every such section reads absent."""
    out = set()
    for ln in text.splitlines():
        # ANY heading level, not just `## `. PhaseLogger nests some contract sections one level
        # deeper -- `log_hypothesis` writes `### Mechanism` under `## Hypothesis: <name>` -- and the
        # contract is about the section being PRESENT, not about its depth in the outline. Anchoring
        # on `## ` exactly reported a phase-4 log as missing `## Mechanism` while the content sat
        # right there at h3 (2026-08-14, the checker's first run against a real phase log).
        m = re.match(r"^(#{2,4})\s+(.*)$", ln)
        if m:
            h = m.group(2).strip()
            out.add(h)
            if ":" in h:
                out.add(h.split(":", 1)[0].strip())
    return out


def wrong_stream(path):
    """Is this path unambiguously in a stream this tool does NOT govern?

    Fires only on a POSITIVE match for another stream, never on an ambiguous path, so a log in a
    scratch/tmp directory (tests, a draft) is still checkable. Verified 2026-08-14 that without
    this guard the two checkers silently mis-serve each other: pointing THIS tool at a dev log
    returned "0 errors, 1 warning" — a near-clean PASS against the wrong contract, which is more
    dangerous than a false failure because nobody re-examines a pass.
    """
    parts = path.parts
    if any(p.startswith("dev_logs") or p == "ana_logs" for p in parts):
        return ("a DEVELOPMENT log (memory/dev_logs*/ or memory/ana_logs/) — use "
                "`tools/check_log_conformance.py`, whose contract is different "
                "(Summary/Problem/Solution/Files Changed/Verification + Version/Branch header)")
    if "model_logs" in parts:
        return ("a MODEL-DEV log (memory/model_logs/) — that stream has its own header shape and "
                "is held by review, not by a checker (see memory/model_logs/CLAUDE.md)")
    return None


def check_file(path, expected_sections=None):
    out = []
    if not path.is_file():
        return [Finding(path, "C0", "error", "file not found")]
    if path.name in _NOT_LOGS:
        return []
    other = wrong_stream(path)
    if other:
        return [Finding(path, "C00", "error", "wrong tool: this is %s" % other)]
    text = path.read_text(errors="replace")
    secs, hdrs = _sections(text), _headers(text)
    is_phase = "_phase" in path.name and _PHASE_STEM.match(path.name)

    if is_phase:
        out += _check_phase(path, text, secs, hdrs, expected_sections)
    else:
        out += _check_free(path, text, secs, hdrs)

    # A PHASE-6 log that routes 6->3 must carry the rethink. See RETHINK_SECTION_SINCE.
    if is_phase:
        m6 = _PHASE_STEM.match(path.name)
        d6 = m6.group("date") if m6 else None
        if (d6 and d6 >= RETHINK_SECTION_SINCE and "_phase6_" in path.name
                and _ITERATE.search(text)):
            hdr = _RETHINK_HDR.search(text)
            # Boundary-day softening, the same convention CAPABILITY_SECTION_SINCE and
            # PHASE_SECTIONS_SINCE use: a log written ON the day the rule landed may predate it by
            # hours, and erroring on those makes the rule look retroactive when it is not.
            boundary6 = d6 == RETHINK_SECTION_SINCE
            if not hdr:
                out.append(Finding(
                    path, "C9", "warn" if boundary6 else "error",
                    "phase 6 routes 6->3 ('Next Action: iterate') but carries no '## ...Rethink...' "
                    "section — required since %s. The next cycle reads the LOG, not the state enum, "
                    "so a rethink recorded nowhere is a cycle that starts blind. Record the five "
                    "questions and the NEW PATHWAYS (phase6-refinement Step 4)."
                    % RETHINK_SECTION_SINCE
                    + (" (boundary day, so it may predate the rule)" if boundary6 else "")))
            else:
                # Present but hollow. A placeholder is a finding, not a state.
                body = text[hdr.end():]
                nxt = re.search(r"^##\s", body, re.M)
                body = body[:nxt.start()] if nxt else body
                words = len(re.findall(r"\w+", body))
                if words < 60:
                    out.append(Finding(
                        path, "C9", "warn",
                        "the rethink section is present but thin (%d words) — it must carry the "
                        "six questions and the NEW PATHWAYS, each with its lever class and "
                        "falsifier" % words))
                elif not re.search(r"\bpathway", body, re.I):
                    out.append(Finding(
                        path, "C9", "warn",
                        "the rethink section names no PATHWAY — its deliverable is candidate "
                        "pathways handed to Phase 3, not a narrative of the cycle"))

    # Shared: the "record what you CONSULTED" block, both types, non-retroactive.
    m = _PHASE_STEM.match(path.name) or _FREE_STEM.match(path.name)
    date = m.group("date") if m else None
    if date and date >= CAPABILITY_SECTION_SINCE and "Skills and memory invoked" not in secs:
        boundary = date == CAPABILITY_SECTION_SINCE
        out.append(Finding(
            path, "C8", "warn" if boundary else "error",
            "missing '## Skills and memory invoked' — required for BOTH log types since "
            "%s ('None' is a valid answer)" % CAPABILITY_SECTION_SINCE
            + (" (boundary day, so it may predate the rule reaching this branch)"
               if boundary else "")))
    return out


def _check_phase(path, text, secs, hdrs, expected_sections):
    out = []
    m = _PHASE_STEM.match(path.name)

    for f in _PHASE_HEADER:
        if f not in hdrs:
            out.append(Finding(path, "C2", "error", "header missing '**%s:**'" % f))

    # The filename's phase number must agree with the header — a mismatch means the log was
    # written by one phase method and renamed, or hand-edited, and every downstream tool that
    # keys off the stem (workflow_state, the reasoning chain) will disagree with the body.
    hm = re.search(r"^\*\*Phase:\*\*\s*(\d)", text, re.M)
    if hm and hm.group(1) != m.group("phase"):
        out.append(Finding(path, "C3", "error",
                           "filename says phase %s but header says phase %s"
                           % (m.group("phase"), hm.group(1))))

    for s in _PHASE_ALWAYS:
        if s not in secs:
            out.append(Finding(path, "C5", "error", "missing '## %s'" % s))

    # C4 — the phase's OWN required sections. Each phase exists to move the calibration toward
    # the goal in a specific way, so its section list is its contract, not decoration.
    phase = int(m.group("phase"))
    if expected_sections is None:
        expected_sections = load_expected_sections()
    date = m.group("date")
    if not expected_sections:
        out.append(Finding(path, "C4", "warn",
                           "could not read PhaseLogger._EXPECTED_SECTIONS — per-phase section "
                           "check SKIPPED (fix the parser rather than trusting this pass)"))
    elif date >= PHASE_SECTIONS_SINCE:
        # Sections the GENERATOR already named as absent are C7's business, not C4's. Reporting
        # both would double-count the same gap and bury the ones nobody has acknowledged.
        declared = set()
        blk = re.search(r"^## Sections not provided\s*$(.*?)(?=^## |\Z)", text, re.S | re.M)
        if blk:
            declared = {ln[2:].split("—")[0].split(" - ")[0].strip().strip("*").strip()
                        for ln in blk.group(1).splitlines() if ln.startswith("- ")}
        boundary = date == PHASE_SECTIONS_SINCE
        for s in expected_sections.get(phase, []):
            if s in secs or s in declared:
                continue
            out.append(Finding(
                path, "C4", "warn" if boundary else "error",
                "phase %d log missing '## %s' — this phase's own contract "
                "(PhaseLogger._EXPECTED_SECTIONS); required for logs dated after %s"
                % (phase, s, PHASE_SECTIONS_SINCE)))

    # C6 — the offline handshake must be FILLED, not left as the generated placeholder. An
    # unfilled field is worse than an absent one: it looks like a chain and resolves to nothing.
    if "Phase Handshake" in secs:
        blk = re.search(r"^## Phase Handshake\s*$(.*?)(?=^## |\Z)", text, re.S | re.M)
        if blk:
            for label in ("Inherited from the previous phase", "Handed to the next phase",
                          "Next action"):
                fm = re.search(r"\*\*%s:\*\*\s*(.*)" % re.escape(label), blk.group(1))
                if fm and _HANDSHAKE_MISS in fm.group(1):
                    out.append(Finding(path, "C6", "error",
                                       "Phase Handshake '%s' left as the generated placeholder"
                                       % label))

    # C11 — the skills this phase log MUST have invoked, named on the Skills line.
    if date >= MUST_INVOKE_SINCE:
        boundary = date == MUST_INVOKE_SINCE
        lvl = "warn" if boundary else "error"
        claimed = _claimed_skills(text)
        need = [_ALWAYS_SKILL]
        ps = _PHASE_SKILL.get(phase)
        if ps:
            need.append(ps)
        if _has_figure(path, text):
            need.append(_FIGURE_SKILL)
        for s in need:
            if s not in claimed:
                out.append(Finding(
                    path, "C11", lvl,
                    "phase %d log does not name `%s` under '**Skills:**' — a phase log is produced "
                    "BY that skill, and writing it from memory of the format is the failure "
                    "check_skill_claims.py exists for one level down (that tool asks if a claim is "
                    "TRUE; this asks if it is THERE). Invoke it, then name it%s"
                    % (phase, s,
                       " (boundary day: may predate the rule reaching this branch)" if boundary
                       else "")))

    # C12 — the reasoning chain must be CUMULATIVE. PhaseLogger rebuilds it from
    # workflow_state_offline_r{RR}.json at write time, so every decision a log stands on must still
    # be in that state. An entry present in a log and absent from the state means the state LOST it
    # (or the block was hand-edited), and the next phase then builds on something the chain no
    # longer carries -- the exact re-derivation the loop exists to prevent.
    #
    # ORDERING IS DELIBERATELY NOT USED. Measured 2026-08-22 across one round's 19 logs: ordering by
    # mtime reported 3 false violations (every one a log edited retroactively), and ordering by
    # (cycle, phase) reported 1 (a probe cycle c00 that ran BEFORE the round's Phase 0 was re-run).
    # Subset-of-state needs no order, so neither artifact can arise.
    if date >= CHAIN_CUMULATIVE_SINCE and "Reasoning chain" in " ".join(secs):
        missing = _chain_not_in_state(path, text, m.group("round"))
        for k in missing[:3]:
            out.append(Finding(path, "C12", "error",
                               "reasoning-chain decision is NOT in workflow_state_offline_r%s.json: "
                               "`%s` — the chain is rebuilt FROM that state, so an entry it no "
                               "longer carries means the state lost it or the block was hand-edited"
                               % (m.group("round"), k)))
        if len(missing) > 3:
            out.append(Finding(path, "C12", "error",
                               "... and %d more chain decision(s) absent from the state"
                               % (len(missing) - 3)))

    # C7 — PhaseLogger names the sections it emitted empty. That list is a to-do the writer left
    # behind, not a state to ship: it is the generator telling you the log is incomplete.
    if "Sections not provided" in secs:
        blk = re.search(r"^## Sections not provided\s*$(.*?)(?=^## |\Z)", text, re.S | re.M)
        n = len(re.findall(r"^- ", blk.group(1), re.M)) if blk else 0
        # Warn only when something is ACTUALLY outstanding. This previously fired on n == 0 too,
        # so a log whose author had filled every section and replaced the generated list with a
        # statement to that effect still got told to "fill them" -- a check that cannot pass, which
        # is how a warning channel gets tuned out along with the warnings that mean something.
        if n:
            out.append(Finding(path, "C7", "warn",
                               "PhaseLogger flagged %d section(s) as not provided — fill them or "
                               "state why they do not apply" % n))
    return out


def _claimed_skills(text):
    """Backticked names on the '**Skills:**' bullet, including its wrapped continuation lines.

    Capturing only the first line is silent UNDER-detection, the worst failure for a check: the
    same bug was found and fixed in check_skill_claims.py, where a skill named on line two of a
    wrapped bullet was missed while its siblings were caught.
    """
    out = set()
    for m in re.finditer(r"^[ \t]*[-*][ \t]*\*\*Skills?:?\*\*(.*?)(?=\n[ \t]*[-*][ \t]*\*\*|\n[ \t]*\n|\Z)",
                         text, re.M | re.S):
        out.update(re.findall(r"`([A-Za-z0-9][A-Za-z0-9._-]*)`", m.group(1)))
    return out


def _has_figure(path, text):
    """Does this log have a figure at all -- embedded, or sitting in its paired artifact folder?

    Both, because they fail differently: a figure embedded but produced without `plotting` skipped
    the view-the-PNG check, and a figure in the folder but not embedded is ALSO a `plotting`
    product (the evidence gate separately warns that it is unshown).
    """
    if re.search(r"^!\[\]\(", text, re.M):
        return True
    d = path.parent.parent / "phase_results" / path.stem
    try:
        return any(d.glob("*.png"))
    except OSError:
        return False


def _chain_not_in_state(path, text, rr):
    """Chain DECISION entries that the round's state file no longer carries.

    Returns [] when the state cannot be read -- absence of the file is not evidence of a lost
    decision, and inventing an error from a missing input is how a check earns distrust.
    """
    m = re.search(r"^## Reasoning chain.*?$(.*?)(?=^## |\Z)", text, re.S | re.M)
    if not m:
        return []
    state = path.parent.parent / ("workflow_state_offline_r%s.json" % rr)
    if not state.is_file():
        return []
    try:
        import json
        data = json.loads(state.read_text(errors="replace"))
    except Exception:
        return []
    have = {str(d.get("decision", ""))[:60] for d in (data.get("decisions") or [])}
    missing = []
    for ln in m.group(1).splitlines():
        if not ln.startswith("- "):
            continue
        body = ln[2:].strip()
        dm = re.match(r"\d{4}-\d{2}-\d{2}\s*[\u2014-]\s*(.+)", body)
        if not dm:                      # a stem-keyed evidence entry, not a decision
            continue
        key = dm.group(1).split(" \u2014 *")[0].strip()[:60]
        if key not in have:
            missing.append(key[:55])
    return missing


def _check_free(path, text, secs, hdrs):
    out = []
    if not _FREE_STEM.match(path.name):
        out.append(Finding(path, "C1", "error",
                           "filename is not YYYYMMDDx_Topic.md (x = same-day letter; past z use "
                           "za, zb — never aa, it sorts before b)"))
    for f in _FREE_HEADER_REQUIRED:
        if f not in hdrs:
            out.append(Finding(path, "C2", "error", "header missing '**%s:**'" % f))
    for f in _FREE_HEADER_EXPECTED:
        if f not in hdrs:
            out.append(Finding(path, "C2", "warn",
                               "header missing '**%s:**' (expected for a calibration session log; "
                               "omit only if genuinely not applicable)" % f))
    for s in _FREE_SECTIONS:
        if s not in secs:
            out.append(Finding(path, "C9", "error", "missing '## %s'" % s))
    if "Next" not in secs:
        out.append(Finding(path, "C10", "warn",
                           "no '## Next' — say what this leaves open, even if 'nothing'"))
    return out


def _pure_rename_paths(repo):
    """Staged paths whose CONTENT did not change: a rename at 100% similarity.

    WHY (2026-08-25): the staged-file gates use `--diff-filter=ACMR`, and R includes renames, so a
    DIRECTORY rename re-gates every file it moved even though not one byte changed. Measured:
    renaming `use_cases/Kougarok` to `use_cases/ELM-FATES_Kougarok` staged 36 files, and this gate
    failed the commit on a PRE-EXISTING defect in a log the rename merely relocated. That is
    exactly the "block unrelated work you did not touch" failure the staged-only design exists to
    prevent, arriving through a door that design did not cover.

    A rename WITH edits (R0xx, similarity below 100) is NOT in this set and is still checked, which
    is what makes this a narrowing rather than a hole.
    """
    import subprocess
    try:
        out = subprocess.check_output(
            ["git", "diff", "--cached", "-M", "--name-status", "--diff-filter=R"],
            cwd=str(repo)).decode("utf-8", "replace")
    except Exception:
        return set()
    pure = set()
    for ln in out.splitlines():
        f = ln.split("\t")
        if len(f) >= 3 and f[0].strip() == "R100":
            pure.add(f[2].strip())
    return pure


def _staged():
    """Calibration logs staged in THIS commit.

    Staged-only on purpose, mirroring the sibling: the gate covers what you are writing now and
    never blocks a commit over pre-existing drift in logs you did not touch. That matters more
    here than for dev logs — this corpus has 127 files with 4 known errors, and a whole-corpus
    gate would block unrelated work by other sessions until someone else's log is fixed.
    """
    import subprocess
    try:
        out = subprocess.check_output(
            ["git", "diff", "--cached", "--name-only", "--diff-filter=ACMR"],
            cwd=str(REPO)).decode("utf-8", "replace")
    except Exception:
        return []
    keep = []
    _pure = _pure_rename_paths(REPO)
    for line in out.splitlines():
        if line.strip() in _pure:          # pure rename: nothing new to gate
            continue
        p = Path(line.strip())
        if not line.strip() or p.suffix != ".md":
            continue
        parts = p.parts
        if "use_cases" in parts and "logs" in parts and "memory" in parts:
            keep.append(REPO / p)
    return [p for p in keep if p.is_file()]


def _collect(args):
    if args == ["--staged"]:
        return _staged()
    paths = []
    it = iter(args)
    for a in it:
        if a == "--site":
            site = Path(next(it, ""))
            d = site / "memory" / "logs"
            paths += sorted(p for p in d.glob("*.md")) if d.is_dir() else []
        else:
            p = Path(a)
            paths += sorted(p.glob("*.md")) if p.is_dir() else [p]
    return [p for p in paths if p.name not in _NOT_LOGS]


def main():
    args = sys.argv[1:]
    if not args:
        print(__doc__.strip().splitlines()[-3])
        return 2
    paths = _collect(args)
    if not paths:
        print("no calibration logs found in: %s" % " ".join(args))
        return 0

    expected = load_expected_sections()
    findings = []
    for p in paths:
        findings += check_file(p, expected)

    print("calibration-log conformance — %d file(s) checked" % len(paths))
    if not findings:
        print("\n\u2714 all logs conform to the `calibration-log` skill contract")
        return 0
    errs = [f for f in findings if f.level == "error"]
    for f in findings:
        print(f)
    print("\n%d error(s), %d warning(s)" % (len(errs), len(findings) - len(errs)))
    print("Fix per .claude/skills/calibration-log/SKILL.md — and RE-READ it rather than "
          "recalling it; it changes.")
    return 2 if errs else 1


if __name__ == "__main__":
    sys.exit(main())
