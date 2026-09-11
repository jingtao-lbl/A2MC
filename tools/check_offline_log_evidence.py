#!/usr/bin/env python3
"""Evidence gate for offline (interactive-agent) phase logs — docs/33 §3a (meta-validation
Phase 1). Targets failure mode FM-1 (verification laxity / over-claiming): a `phase3_diagnosis`
that RESTATES a prior log with no first-hand analysis this session, yet stamps high confidence.

For an offline topic-stem log (`logs/{stem}.md`, stem = YYYYMMDDx_phase{N}_{name}_r{RR}[...]) of
an ANALYSIS phase (3 diagnosis / 4 hypothesis / 6 refinement), this checks:

ERRORS (exit 1) — the restatement-blocker:
  - no resolvable FIRST-HAND ARTIFACT: the log must cite (or have produced) at least one non-`.md`
    artifact — a script (.py), figure (.png/.pdf), or data file (.csv/.txt/.nc/.json) — that EXISTS
    in the log's paired `phase_results/{stem}/`, a `phases/*/generated/` dir, or a relative path
    that resolves. A log that cites only prior `.md` logs is a restatement.

WARNINGS (exit 0) — softer nudges (kept out of ERROR to avoid false positives):
  - phase 3/4 log with Confidence >= 0.95 and no Phase-5 / experiment reference (a diagnosis /
    hypothesis is a hypothesis until a test confirms it — see feedback_no_kb_injection_before_verified_test).
  - an orphan number in a Recommendation / Conclusion / Decision sentence whose value does not appear
    in any cited artifact name or the evidence text.

Non-analysis phases (0/1/2/5/7) and non-offline files are skipped. Dependency-free (stdlib only).

Usage:
    python3 tools/check_offline_log_evidence.py <log.md | logs_dir | --site use_cases/<site>>
"""
import json
import os
import re
import sys
from pathlib import Path

# Offline topic-stem: YYYYMMDDx_phase{N}_{name}_r{RR}[...]_{descriptor}.md
STEM_RE = re.compile(r"^(\d{8}z*[a-z])_phase(\d+)_[a-z]+_r(\d+)")   # z*[a-z]: past the 26th
                                                                  # same-day log the letter is za, zb, ...
                                                                  # (CLAUDE.md; phase_logger._offline_letter)
ANALYSIS_PHASES = {3, 4, 6}

# First-hand artifact extensions (NOT .md — logs/notes are not first-hand computation).
ARTIFACT_EXT = {".py", ".png", ".pdf", ".csv", ".txt", ".nc", ".json", ".npy", ".npz"}
# Evidence-section headers we recognize (from templates/logging/ + the offline convention).
EVIDENCE_HEADERS = re.compile(
    r"^#{2,4}\s*(evidence|scripts?\s+(created|run|developed)|"
    r"diagnostic\s+script\s+development|output\s+figures?|"
    r"results?\s+produced|quantitative\s+evidence)\b", re.I | re.M)
DECISION_HDR = re.compile(r"^#{2,4}\s*(.*\b(recommendation|conclusion|decision)s?\b.*)$", re.I | re.M)
# A cited artifact: `name.ext` in backticks, or a bare path token ending in a known ext.
CITED_RE = re.compile(r"`([^`]+?\.(?:py|png|pdf|csv|txt|nc|json|npy|npz))`|"
                      r"(?<![\w`])([\w./\-]+\.(?:py|png|pdf|csv|txt|nc|json|npy|npz))")


#: Effective date for the phase-0/5 submit-script archive rule (PI, 2026-08-23). Earlier folders
#: predate it; the count of exempt folders is not printed here because this check reports per-log.
SUBMIT_ARCHIVE_SINCE = "20260823"
#: Since this date a phase-5 stem's cases must also appear in the case's RUN LEDGER
#: (`memory/run_records.json`, written by `tools/record_run_status.py`). Non-retroactive for the
#: same reason as the line above: a permanently-red check is one nobody reads.
RUN_LEDGER_SINCE = "20260908"

def cited_artifacts(text):
    out = set()
    for m in CITED_RE.finditer(text):
        out.add((m.group(1) or m.group(2)).strip())
    return out


def resolve(name, site_dir, stem, repo_root):
    """True if a cited artifact name/path resolves to an existing file produced by this work."""
    cands = []
    p = Path(name)
    # absolute or repo-relative path as written
    cands.append((repo_root / name).resolve() if not p.is_absolute() else p)
    base = p.name
    # paired topic-artifact folder
    cands.append(site_dir / "memory" / "phase_results" / stem / base)
    # generated diagnostic scripts (any phase)
    for g in (repo_root / "phases").glob("*/generated"):
        cands.append(g / base)
    for c in cands:
        try:
            if Path(c).is_file():
                return True
        except OSError:
            continue
    # last resort: basename match anywhere under the topic folder
    topic = site_dir / "memory" / "phase_results" / stem
    if topic.is_dir():
        for f in topic.rglob(base):
            if f.is_file():
                return True
    return False


def parse_confidence(text):
    m = re.search(r"confidence[:*\s]+\**\s*([0-9]*\.?[0-9]+)\s*(%?)", text, re.I)
    if not m:
        return None
    val = float(m.group(1))
    if m.group(2) == "%" or val > 1.5:  # a percentage
        val /= 100.0
    return val


#: A `phase_results/<stem>/...` path mentioned anywhere in a log. A stem can be renamed (the
#: offline letter allocator reassigns it), and PhaseLogger BAKES the reasoning chain into the file
#: at write time -- so a log written before its state was repointed freezes the superseded stem.
ARTIFACT_DIR_RE = re.compile(r"phase_results/(\d{8}[a-z]+_phase\d+_[A-Za-z0-9_]+)")

#: A CROSS-CASE artifact citation, repo-rooted: `use_cases/<Case>/memory/phase_results/<stem>`.
#: These are legitimate and are how a NEW case inherits evidence from an earlier one -- the whole
#: point of seeding a case from a prior campaign. Resolved against the case the path NAMES, not
#: against the log's own site_dir, which is what made a valid cross-case pointer indistinguishable
#: from a dead local one. It still ERRORs when the named case or stem does not exist; the fix
#: widens WHERE the checker looks, never WHETHER it can fail.
#: The case segment is `<Model>_<Case>`, NOT a free-form directory name (PI, 2026-09-01). The model
#: half may itself carry a hyphen (`ELM-FATES_Kougarok`, `EcoSIM-PFLOTRAN_LEO`), so the shape is
#: "one-or-more non-underscore chars, an underscore, then the case". Matching a bare name instead
#: would accept `use_cases/TEMPLATE/...` and any typo'd path as a well-formed citation and then
#: report it as merely missing, which hides a malformed reference behind a not-found message.
CROSS_CASE_DIR_RE = re.compile(
    r"use_cases/([A-Za-z0-9.-]+_[A-Za-z0-9_.-]+)/memory/phase_results/"
    r"(\d{8}[a-z]+_phase\d+_[A-Za-z0-9_]+)")

#: An embedded image: ![](path) or ![alt](path). The convention is EMPTY alt text plus a bold
#: **Figure N.** caption beneath (feedback_report_figure_embed / feedback_report_figure_empty_alt_text).
EMBED_RE = re.compile(r"!\[[^\]]*\]\(([^)]+)\)")

#: EFFECTIVE DATE of the embed-your-figures rule (PI, 2026-08-22). A log stamped BEFORE this is
#: grandfathered: the rule did not exist when it was written, and 45 of the site's 82 offline logs
#: predate it. Retro-warning them would mean a permanent wall of noise about work nobody is going
#: to revisit, and a checker whose output is always red is a checker nobody reads.
#:
#: The exemption is COUNTED AND REPORTED, never silent -- a backlog that vanishes from the output
#: is a backlog that stops being a decision. Only this WARN is dated; a dead artifact pointer is a
#: defect at any age and stays an ERROR regardless.
EMBED_RULE_EFFECTIVE = "20260822"


def _dead_artifact_pointers(name, text, site_dir):
    """ERROR on a cited phase_results/<stem> directory that does not exist.

    A dead pointer is worse than a missing one: it reads as a citation, so a reader chases it
    instead of disbelieving it. Real instance 2026-08-22 -- a phase-1 log cited a superseded
    stem in 14 places and only the PI noticed.
    """
    out, seen = [], set()
    pr = site_dir / "memory" / "phase_results"
    # A cross-case citation matches ARTIFACT_DIR_RE too (the repo-rooted path CONTAINS the local
    # shape), so resolve those first and exempt their stems from the local check below -- otherwise
    # a valid pointer into another case reports as a dead local one.
    use_cases_root = site_dir.parent
    cross_ok = set()
    for case, stem in CROSS_CASE_DIR_RE.findall(text):
        if (use_cases_root / case / "memory" / "phase_results" / stem).is_dir():
            cross_ok.add(stem)
        elif stem not in seen:
            seen.add(stem)
            out.append(
                f"{name}: cites `use_cases/{case}/memory/phase_results/{stem}/` which does not "
                f"exist — a dead CROSS-CASE artifact pointer. Check the case name and the stem.")
    for stem in ARTIFACT_DIR_RE.findall(text):
        if stem in seen or stem in cross_ok:
            continue
        seen.add(stem)
        if not (pr / stem).is_dir():
            out.append(
                f"{name}: cites `phase_results/{stem}/` which does not exist — a dead artifact "
                f"pointer. If the stem was renamed, the log must be REGENERATED after the state "
                f"is repointed: PhaseLogger bakes the reasoning chain in at write time, so state "
                f"first, log second.")
    return out


def _unembedded_figures(name, text, site_dir, stem):
    """WARN when the paired folder has figures the log never shows.

    A phase log and its artifact folder are meant to be read as ONE document. Naming a folder is
    not showing a figure: `phase_results/{stem}/foo.png` in prose renders as text, and the reader
    has to go hunting. Embed with `![](../phase_results/{stem}/foo.png)`.
    """
    if stem[:8] < EMBED_RULE_EFFECTIVE:
        return []          # grandfathered -- written before the rule existed
    topic = site_dir / "memory" / "phase_results" / stem
    if not topic.is_dir():
        return []
    figs = sorted(f.name for f in topic.iterdir()
                  if f.is_file() and f.suffix.lower() in (".png", ".pdf"))
    if not figs:
        return []
    embedded = {Path(m).name for m in EMBED_RE.findall(text)}
    missing = [f for f in figs if f not in embedded]
    if not missing:
        return []
    return [f"{name}: {len(missing)} of {len(figs)} figure(s) in phase_results/{stem}/ are not "
            f"EMBEDDED in the log ({', '.join(missing[:3])}"
            f"{'…' if len(missing) > 3 else ''}) — embed each as "
            f"`![](../phase_results/{stem}/<file>.png)` with a bold **Figure N.** caption, so the "
            f"log and its evidence review as one document. Naming the folder in prose is not "
            f"showing the figure."]


def check_log(path, repo_root):
    """Return (errors, warnings) for one offline log file."""
    errors, warnings = [], []
    name = path.name
    m = STEM_RE.match(name)
    if not m:
        return errors, warnings  # not an offline topic-stem log
    stem = name[:-3] if name.endswith(".md") else name
    phase = int(m.group(2))
    # site dir = parent of the logs/ dir the file lives in
    logs_dir = path.parent
    site_dir = logs_dir.parent.parent  # .../{site}/memory/logs/file -> .../{site}
    text = path.read_text(encoding="utf-8", errors="replace")

    # --- EVERY offline phase log: is its evidence actually PRESENTED and does it RESOLVE? ---
    # These two run for all phases, not only 3/4/6. The restatement checks below are specific to
    # analysis phases, but "the log must show its figures" and "its pointers must not be dead"
    # are universal -- and both were missed here on a phase-1 log, by a human reader rather than
    # by this tool, because the analysis-phase early return used to skip the whole function.
    errors += _dead_artifact_pointers(name, text, site_dir)
    warnings += _unembedded_figures(name, text, site_dir, stem)

    # --- WARN: a PHASE 0 or 5 folder must archive the JOB SCRIPTS it ran ---
    # Those two phases put simulations on a scheduler, and the run directory they submit from is
    # untracked scratch that gets cleaned. The submit script is the only record of which BINARY
    # the run was bound to and of its run-time hash assertion, so a log claiming a passed V0 gate
    # with no archived submit script cannot show which executable produced the number. On
    # 2026-08-23 a cycle nearly ran against the wrong binary because the materializer emits the
    # LIVE build path by default ([[feedback_bind_runs_to_archived_binaries]]).
    #
    # SITED ABOVE THE ANALYSIS-PHASE EARLY RETURN. Phases 0 and 5 are NOT analysis phases, so a
    # check placed after that return can never fire for the only two phases it targets -- which is
    # exactly how it was first written, and the same defect the comment on that return already
    # records having happened once before.
    # Non-retroactive: earlier phase-0/5 folders predate the rule and a permanently-red check is
    # one nobody reads. WARN not ERROR -- a launch can legitimately be mid-flight when the folder
    # is first written.
    # PHASE 5 ONLY. Phase 0 also puts simulations on a scheduler, but its job scripts are
    # GENERATED from the machine + round config by the materializer and an ensemble is
    # thousands of cases (one R3 round is 59,393), so archiving them would be enormous and
    # redundant -- the config plus the generator reproduces them exactly. Phase 5's handful
    # of variants are hand-designed and hand-repointed onto a specific binary, so nothing
    # else records what actually ran. Corrected by the PI the day the rule landed.
    m_ph = re.search(r"_phase(5)_", stem)
    if m_ph and stem[:8] >= SUBMIT_ARCHIVE_SINCE:
        sub = (site_dir / "memory" / "phase_results" / stem) / "submit_scripts"
        has = sub.is_dir() and any(sub.iterdir())
        if not has:
            warnings.append(
                f"{name}: phase 5 ran hand-designed variants but "
                f"phase_results/{stem}/submit_scripts/ is empty or absent — COPY the per-case "
                f"submit script(s) and a representative runfile there (copy, do not move: the "
                f"scheduler reads the operative copy). The run root is untracked scratch, and the "
                f"submit script is the only record of which BINARY this run was bound to.")
        elif stem[:8] >= RUN_LEDGER_SINCE:
            # --- WARN: every case this phase SUBMITTED must appear in the RUN LEDGER ---
            # The archive above records what was submitted; the ledger records what BECAME of it.
            # Without this pairing the ledger is optional in practice, and an optional record is
            # the one that stops being written: the same content lived in a hand-written caption
            # section for cycles c00-c08 of one round and then silently vanished for ten
            # consecutive cycles, because nothing checked it.
            # The submit_scripts archive is the right authority to check against precisely
            # BECAUSE it is checked above -- it cannot be quietly skipped to dodge this.
            # Both separators are in use for the filenames ([[feedback_exact_strings_are_contracts]]).
            submitted = sorted({f.name[:-len("_submit.sh")] if f.name.endswith("_submit.sh")
                                else f.name[:-len(".submit.sh")]
                                for f in sub.glob("*submit.sh")})
            ledger = site_dir / "memory" / "run_records.json"
            if not submitted:
                pass  # nothing named a case; the archive check above already spoke
            elif not ledger.exists():
                warnings.append(
                    f"{name}: phase 5 submitted {len(submitted)} case(s) but "
                    f"{ledger.parent.name}/run_records.json does not exist — record them with "
                    f"`python tools/record_run_status.py`. The ledger is a RECORD, not curated "
                    f"knowledge: it is ungated and Phase 5 fills it as the runs progress.")
            else:
                try:
                    recorded = {r.get("case") for r in
                                json.loads(ledger.read_text()).get("records", [])}
                except (ValueError, OSError) as exc:
                    warnings.append(f"{name}: could not read run_records.json ({exc})")
                    recorded = None
                if recorded is not None:
                    missing = [c for c in submitted if c not in recorded]
                    if missing:
                        warnings.append(
                            f"{name}: {len(missing)} of {len(submitted)} submitted case(s) are "
                            f"absent from memory/run_records.json — "
                            f"{', '.join(missing[:4])}{' ...' if len(missing) > 4 else ''}. "
                            f"Record them with `python tools/record_run_status.py from-ladder "
                            f"--case-dir <case> --round <R> --cycle <C> --data <scoring .json> "
                            f"--stem {stem}` (or `from-submits` if the cycle has no scoring JSON).")

    if phase not in ANALYSIS_PHASES:
        return errors, warnings

    # --- ERROR: at least one resolvable first-hand artifact ---
    arts = cited_artifacts(text)
    resolved = [a for a in arts if resolve(a, site_dir, stem, repo_root)]
    if not resolved:
        # also accept a non-empty paired topic folder as produced evidence
        topic = site_dir / "memory" / "phase_results" / stem
        produced = topic.is_dir() and any(
            f.suffix in ARTIFACT_EXT for f in topic.rglob("*") if f.is_file())
        if not produced:
            errors.append(
                f"{name}: no resolvable first-hand artifact — a phase{phase} (analysis) log must "
                f"cite a script/figure/data file produced THIS session (in phase_results/{stem}/ or "
                f"a phases/*/generated/ dir). Citing only prior .md logs is a restatement "
                f"(feedback_offline_logs_need_first_hand_analysis).")

    # --- WARN: high confidence for a pre-test phase, no Phase-5/experiment link ---
    if phase in (3, 4):
        conf = parse_confidence(text)
        has_test_link = bool(re.search(r"phase[_ ]?5|_c\d+_|experiment[_ ]id|verified_by", text, re.I))
        if conf is not None and conf >= 0.95 and not has_test_link:
            warnings.append(
                f"{name}: Confidence {conf:.2f} on a phase{phase} log with no Phase-5/experiment "
                f"link — a diagnosis/hypothesis is a hypothesis until a test confirms it; do not "
                f"promote to the curated KB yet (feedback_no_kb_injection_before_verified_test).")

    # --- WARN: orphan number in a recommendation/conclusion/decision sentence ---
    art_blob = " ".join(arts) + " " + " ".join(
        # numbers appearing in evidence sections
        EVIDENCE_HEADERS.split(text)[-1:] if EVIDENCE_HEADERS.search(text) else [])
    for hm in DECISION_HDR.finditer(text):
        seg = text[hm.end(): hm.end() + 600]
        # PhaseLogger appends its own `## Iteration Context` JSON right after the Next Action
        # heading, carrying a wall-clock timestamp. Scanning it made the check fire on the
        # generator's own output ("57" out of 03:57:25) rather than on anything the author wrote,
        # which is a check reporting a defect it created. Stop the segment at the next heading.
        nxt = re.search(r"\n#{1,6} ", seg)
        if nxt:
            seg = seg[: nxt.start()]
        # A `File.F90:1009` or `path/to/x.py:88-93` citation IS a source citation, so its LINE
        # NUMBER is not an orphan quantity. Strip those spans before scanning, or the check fires
        # on the very act of citing -- measured 2026-09-07, when adding `RootMod.F90:1009` to
        # source a percentage silently replaced that warning with a warning about `1009`.
        scan = re.sub(r"[\w./-]+\.(?:F90|f90|py|sh|nml|yaml|yml|json|md|cdl|nc|xml)"
                      r"(?::\d+(?:\s*[-,]\s*:?\d+)*)?", " ", seg)
        for num in re.findall(r"(?<![\w.])(\d{2,}(?:\.\d+)?)", scan):
            if num not in art_blob and num not in "".join(resolved):
                warnings.append(
                    f"{name}: load-bearing number `{num}` appears in a "
                    f"{hm.group(1).strip().lower()} but is not traceable to a cited artifact — "
                    f"verify it first-hand (feedback_performance_experiment_is_the_objective).")
                break  # one nudge per decision section is enough

    # --- WARN: the paired artifact folder should be SELF-DOCUMENTING (figure + caption + script + data) ---
    # A figure with no caption / no generating script / no data is under-documented: a future reader can't
    # tell what it shows, how it was made, or from what. Mirror the write-report self-contained folder.
    topic = site_dir / "memory" / "phase_results" / stem
    if topic.is_dir():
        exts = {f.suffix.lower() for f in topic.rglob("*") if f.is_file()}
        if exts & {".png", ".pdf"}:  # there is a figure to document
            missing = []
            if ".md" not in exts:
                missing.append("a caption/NOTES .md (what it shows + how-to-read + provenance)")
            if ".py" not in exts:
                missing.append("the generating .py script (saved, reproducible — not an inline heredoc)")
            if not (exts & {".csv", ".txt", ".nc", ".json", ".npz", ".npy"}):
                missing.append("the underlying data file")
            if missing:
                warnings.append(
                    f"{name}: phase_results/{stem}/ has a figure but is not self-documenting — add "
                    f"{'; '.join(missing)} (figures>tables>words + the write-report self-contained-folder "
                    f"discipline). The log/{{stem}}.md carries the analysis; the folder must let a future "
                    f"reader regenerate + interpret the figure without you.")

    return errors, warnings


def gather(target):
    p = Path(target)
    if p.is_file():
        return [p]
    if p.is_dir():
        # a site dir or a logs dir
        logs = p / "memory" / "logs" if (p / "memory" / "logs").is_dir() else p
        return sorted(f for f in logs.glob("*.md") if STEM_RE.match(f.name))
    return []


def main(argv):
    if not argv:
        print("usage: check_offline_log_evidence.py <log.md | logs_dir | --site use_cases/<site>>")
        return 2
    if argv[0] == "--site":
        target = argv[1]
    else:
        target = argv[0]
    repo_root = Path(__file__).resolve().parent.parent

    # A TARGET THAT RESOLVES TO NOTHING IS AN ERROR, NOT A PASS.
    # Until 2026-08-28 a mistyped path -- `--site PFLOTRAN_miniLEO` instead of
    # `--site use_cases/PFLOTRAN_miniLEO`, or any typo'd case name -- returned exit 0 and printed
    # the same green tick as a clean run, differing only in a "0 offline log(s) scanned" the reader
    # has no reason to distrust. That is the vacuous-green-tick failure this file already warns
    # about further down for SKIPPED files; the same hole was open one level up for a target that
    # was never found at all. Found by the 3-hourly self-review quoting its own green tick.
    # An existing path holding no matching logs stays a PASS: a young case legitimately has none.
    if not Path(target).exists():
        print(f"\n✘ target does not exist: {target}")
        print("  A non-existent target is a FAILED check, not an empty one -- otherwise a typo")
        print("  reads as a clean gate. Did you mean `--site use_cases/<Site>`?")
        return 1
    files = gather(target)
    if not files:
        print(f"  [note] {target} exists but holds no offline logs matching the stem pattern "
              f"(YYYYMMDDx_phase{{N}}_{{name}}_r{{RR}}...). Passing: a case with no offline logs yet "
              f"is legitimate. If you expected logs here, the STEM is what did not match.")
    all_err, all_warn = [], []
    for f in files:
        e, w = check_log(f, repo_root)
        all_err += e
        all_warn += w
    for w in all_warn:
        print(f"  [warn] {w}")
    if all_err:
        print(f"\n✘ {len(all_err)} evidence problem(s):")
        for e in all_err:
            print(f"  - {e}")
        return 1
    # Say what was checked, not what was scanned: the restatement checks apply only to the
    # analysis phases, and a summary that counts skipped files as "checked" is how a vacuous
    # green tick gets quoted as evidence (it was, twice, on 2026-08-22).
    n_analysis = sum(1 for f in files
                     if (mm := STEM_RE.match(f.name)) and int(mm.group(2)) in ANALYSIS_PHASES)
    n_grandfathered = sum(1 for f in files if f.name[:8] < EMBED_RULE_EFFECTIVE)
    if n_grandfathered:
        print(f"  [note] {n_grandfathered} log(s) predate the embed-your-figures rule "
              f"({EMBED_RULE_EFFECTIVE}) and are exempt from that WARN. Reported so the backlog "
              f"stays visible; dead artifact pointers are still checked in them.")
    print(f"✔ offline log evidence gate: {len(files)} offline log(s) scanned "
          f"({n_analysis} analysis-phase, full restatement checks; the rest checked for dead "
          f"artifact pointers + unembedded figures only), {len(all_warn)} warning(s), 0 errors")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
