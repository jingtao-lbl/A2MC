#!/usr/bin/env python3
"""Which SETUP STAGE is this clone in, and is that stage mechanically complete?

The executable half of the `setup-discipline` skill. It answers the question that comes
BEFORE `check_setup_ready.py`:

    check_stage_ready.py : which stage am I in, and is its checkable part done?
    check_setup_ready.py : is THIS SITE ready for Phase 0?  (requires sourced configs)

That ordering is the whole point. `check_setup_ready.py` hard-exits when `A2MC_USE_CASE_DIR`
is unset, which for a freshly cloned repo is a dead end -- it tells the user to source a site
config that does not exist yet. This script therefore requires NO sourced config and reads only
what is on disk, so it can run in a clone that has nothing set up at all.

It checks the MECHANICAL subset of each stage's checklist and says so: items that cannot be
verified by a machine (was the research plan approved? was the interview actually held?) are
reported as the human-confirmed remainder, pointing at `setup-discipline`. A checklist that
silently omits its unverifiable items would read as "stage complete" when it is not.

Exit 0 = no FAIL (NA/INFO never fail); exit 1 = at least one FAIL.

Usage:
    python3 tools/check_stage_ready.py                 # auto-detect the stage
    python3 tools/check_stage_ready.py --model ecosim  # audit one model's onboarding (stage 2)
    python3 tools/check_stage_ready.py --case EcoSIM_BioCON
    python3 tools/check_stage_ready.py --stage 2       # force a stage
"""
import argparse
import json
import os
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))

PASS, FAIL, NA, INFO = "PASS", "FAIL", "NA", "INFO"
_MARK = {PASS: "✓", FAIL: "✗", NA: "–", INFO: "ℹ"}

# Entries in models/ that are package machinery, not adapted models.
_NOT_A_MODEL = {"_template", "__pycache__", "base.py", "registry.py", "__init__.py"}
# Entries in use_cases/ that are scaffolding, not real cases.
_NOT_A_CASE = {"TEMPLATE", "README.md", "__pycache__"}


def _rows_out(rows, title):
    print(f"\n{title}\n" + "-" * len(title))
    for status, label, detail in rows:
        line = f"  {_MARK[status]} {label}"
        if detail:
            line += f" — {detail}"
        print(line)
    return sum(1 for s, _, _ in rows if s == FAIL)


def onboarded_models():
    """Models with a real adapter package, per the REGISTRY CONTRACT.

    The test is `register_model()` in `models/<name>/__init__.py`, not the presence of `spec.py`.
    Measured 2026-08-19 on this clone: `models/surrogate/` has a `spec.py` and would pass a
    spec.py heuristic, but its own docstring says "A surrogate is NOT a model adapter" -- it is a
    learned artifact *about* a model -- and it never registers. Counting it produced a phantom
    "incomplete onboarding" with 3 failures for something that was never being onboarded.
    """
    d = ROOT / "models"
    if not d.is_dir():
        return []
    out = []
    for p in sorted(d.iterdir()):
        if not p.is_dir() or p.name in _NOT_A_MODEL:
            continue
        init = p / "__init__.py"
        if init.is_file() and "register_model(" in init.read_text(encoding="utf-8", errors="replace"):
            out.append(p.name)
    return out


def real_cases():
    """Cases that are actual work, excluding TEMPLATE, the per-model `*_template/` seeds, and
    hidden directories such as a Jupyter `.ipynb_checkpoints/` (a case name never starts with `.`)."""
    d = ROOT / "use_cases"
    if not d.is_dir():
        return []
    return sorted(p.name for p in d.iterdir()
                  if p.is_dir() and p.name not in _NOT_A_CASE and not p.name.startswith(".")
                  and not p.name.endswith("_template"))


def milestones():
    f = ROOT / "rag" / "milestones.json"
    if not f.is_file():
        return {}
    try:
        return json.load(f.open()).get("milestones", {})
    except (OSError, ValueError):
        return {}


def case_has_state(case: str) -> bool:
    """Does this case carry workflow state, i.e. has it reached Phase 0?

    Offline (`workflow_state_offline_r*.json`, written from phase0-design on) OR online
    (`workflow_state.json`, the orchestrator's). Counting only the offline file sent every case run
    by the online agent back to case creation for ever (audit 20260923b, F84).
    """
    mem = ROOT / "use_cases" / case / "memory"
    # NOTE the inner any(): Path.glob() returns a GENERATOR, which is always truthy.
    return any(mem.glob("workflow_state_offline_r*.json")) or (mem / "workflow_state.json").is_file()


def cases_in_setup():
    """Real cases with no workflow state yet: scaffolded, not yet at Phase 0."""
    return [c for c in real_cases() if not case_has_state(c)]


def detect_stage():
    """Return (stage:int, why:str). Reads disk, never the session's claims."""
    cases = real_cases()
    if not onboarded_models():
        return 2, "no adapted model in models/ (none calls register_model())"
    # A glob inside any() must itself be wrapped in any(): a generator object is always truthy, which
    # once reported "setup complete" for every clone with a case. case_has_state() does that.
    if any(case_has_state(c) for c in cases):
        return 4, "a case has offline workflow state — setup is done, this is onboard-session territory"
    if not cases:
        return 1, "models are adapted but use_cases/ holds only templates"
    return 3, f"{len(cases)} real case(s) exist; a new one is stage 3"


# --------------------------------------------------------------------------- stage 1
def stage1_rows():
    """The model-install half of a2mc-init that the disk can show, as INFO or FAIL rows.

    `A2MC_MODEL_PATH` is NOT a stage-1 requirement. For EcoSIM, PFLOTRAN and ATS the model checkout is
    set per case in the SITE config (onboard-case Step 2), and a2mc_noncime_config.sh deliberately sets
    none; this checker also reads only its own process's environment, so the row FAILed for every
    non-CIME user through all of stage 1 (audit 20260923b, F31). It is INFO when unset, and a set path
    that does not exist is still a FAIL.

    The fork guard is ADVISORY here, as in model_preflight: a2mc-init offers it, a user with no GitHub
    account cannot have one, and "origin already is my fork" is legitimate. A hard FAIL left stage 1
    unfinishable for those users for ever (F30). onboard-model Step 0b is where it is required.
    """
    rows = []
    mp = os.environ.get("A2MC_MODEL_PATH", "")
    if not mp:
        rows.append((INFO, "model checkout",
                     "not set in this shell: for EcoSIM/PFLOTRAN/ATS a case's site config sets it "
                     "(onboard-case Step 2); for ELM-FATES, A2MC_E3SM_ROOT in a2mc_config.sh "
                     "(a2mc-init Step 3)"))
    else:
        p = Path(mp)
        rows.append((PASS if p.is_dir() else FAIL, "model checkout exists", mp))
        if p.is_dir():
            rows.append(_fork_guard_row(p))
    for cfg in ("a2mc_config.sh", "a2mc_noncime_config.sh"):
        if (ROOT / cfg).is_file():
            rows.append((INFO, f"{cfg} present",
                         "CIME models" if "noncime" not in cfg else "non-CIME adapter models"))
    return rows


def _fork_guard_row(checkout: Path):
    """origin's PUSH url must be disabled and a `fork` remote must exist.

    Checked because its absence is the one setup omission that can damage something OUTSIDE
    A2MC (a push to the upstream model repo), and it is invisible until it happens.
    """
    try:
        # stdout=PIPE + universal_newlines, not capture_output/text: those are 3.7+, and this module
        # runs under the SYSTEM python3 (3.6 on Perlmutter) from the hooks (audit 20260923b, F103).
        out = subprocess.run(["git", "remote", "-v"], cwd=str(checkout), stdout=subprocess.PIPE,
                             stderr=subprocess.PIPE, universal_newlines=True, timeout=15).stdout
    except (OSError, subprocess.SubprocessError):
        return (NA, "fork-only push guard", "could not read git remotes")
    if not out.strip():
        return (NA, "fork-only push guard", "checkout is not a git repo")
    push = [l for l in out.splitlines() if "(push)" in l]
    origin_push = [l for l in push if l.split()[0] == "origin"]
    has_fork = any(l.split()[0] == "fork" for l in push)
    disabled = origin_push and "DISABLED" in origin_push[0].upper()
    if disabled and has_fork:
        return (PASS, "fork-only push guard", "origin push disabled, fork remote set")
    missing = []
    if not disabled:
        missing.append("origin push NOT disabled")
    if not has_fork:
        missing.append("no `fork` remote")
    # ADVISORY (see stage1_rows): INFO, never FAIL.
    return (INFO, "fork-only push guard",
            "; ".join(missing) + " — optional unless you will edit model source (onboard-model Step 0b)")


# --------------------------------------------------------------------------- stage 2
def stage2_rows(model: str):
    rows = []
    md = ROOT / "models" / model
    for f in ("spec.py", "parameter_parser.py", "output_parser.py"):
        rows.append((PASS if (md / f).is_file() else FAIL, f"models/{model}/{f}", ""))

    ms = milestones()
    mine = {k: v for k, v in ms.items() if v.get("adapter") == model}
    # Report EVERY row, never return early on a structural failure. An early return hides the
    # checks below it, so you fix one item, re-run, and meet the next -- and a reader reasonably
    # reads a short clean tail as "the rest is fine". Measured 2026-08-19: ATS's missing milestone
    # masked its missing adaptive-memory seed entirely.
    prof, entry = (sorted(mine.items())[0] if mine else (None, {}))
    if prof is None:
        rows.append((FAIL, "milestone registered",
                     f"no rag/milestones.json entry with adapter: {model} — every future clone "
                     f"will report this model as unsupported"))
    else:
        rows.append((PASS, "milestone registered", prof))

    for label, key in (("knowledge base (wiki)", "knowledge_base_dir"),
                       ("curated seed", "curated_yaml_path")):
        if prof is None:
            rows.append((NA, label, "no milestone to read the path from"))
            continue
        rel = entry.get(key)
        if not rel:
            rows.append((FAIL, label, f"milestone has no `{key}`"))
        else:
            rows.append((PASS if (ROOT / rel).exists() else FAIL, label, rel))

    if prof is None:
        rows.append((NA, "RAG index committed", "no milestone profile to locate the index"))
        rows.append((NA, "knowledge graph", "no milestone profile"))
    else:
        chroma = ROOT / "rag" / "chroma_db" / prof
        rows.append((PASS if chroma.is_dir() else FAIL, "RAG index committed",
                     str(chroma.relative_to(ROOT)) if chroma.is_dir()
                     else f"{chroma.relative_to(ROOT)} absent — note chroma.sqlite3 carries "
                          f"skip-worktree, so a rebuild that was never staged looks identical to this"))
        graph = ROOT / "rag" / "graphs" / f"{prof}.json"
        rows.append((PASS if graph.is_file() else FAIL, "knowledge graph", f"rag/graphs/{prof}.json"))

    # Not just "the directory exists": four EMPTY scaffolds is exactly the half-done state, and the
    # consumer cannot tell you -- MemoryManager returns 0 chars for a missing store AND for an empty
    # one, raising nothing either way. So check that discoveries.json actually carries entries; the
    # other three stores are legitimately empty on a fresh onboarding (calibration fills them).
    #
    # WHERE the store is depends on the model: FATES keeps the unprefixed memory/gained_knowledge/
    # (it predates the per-model layout), adapter models memory/<model>/gained_knowledge/. Building
    # memory/<model>/ here, as this did until v2.411, looked for a memory/fates/ that never exists.
    # The one resolver is tools/model_knowledge_store.py, loaded by FILE PATH rather than through
    # the `tools` package: importing the package pulls in its FATES utilities and numpy, and this
    # checker runs with no sourced config and inside session hooks that must stay cheap.
    import importlib.util
    _spec = importlib.util.spec_from_file_location(
        "_a2mc_model_knowledge_store", Path(__file__).resolve().parent / "model_knowledge_store.py")
    _mks = importlib.util.module_from_spec(_spec)
    _spec.loader.exec_module(_mks)
    kb = _mks.model_store_dir(model, ROOT)
    disc = kb / "discoveries.json"
    if not kb.is_dir():
        rows.append((FAIL, "adaptive memory seeded", f"{kb.relative_to(ROOT)}/ absent — "
                     f"the reasoning loop would run with NO model knowledge and never error"))
    elif not disc.is_file():
        rows.append((FAIL, "adaptive memory seeded", f"{disc.relative_to(ROOT)} absent"))
    else:
        try:
            n = len(json.loads(disc.read_text(encoding="utf-8")).get("discoveries", []))
        except ValueError:
            n = -1
        if n > 0:
            rows.append((PASS, "adaptive memory seeded", f"{n} discovery record(s)"))
        elif n == 0:
            rows.append((FAIL, "adaptive memory seeded",
                         "discoveries.json is an EMPTY scaffold — the store exists but carries no "
                         "knowledge, which reads identically to a missing one at every call site"))
        else:
            rows.append((FAIL, "adaptive memory seeded", f"{disc.relative_to(ROOT)} is not valid JSON"))
    rt = md / "runtemplates"
    rows.append((PASS if rt.is_dir() and any(rt.iterdir()) else FAIL, "run template", f"models/{model}/runtemplates/"))
    # The build recipe onboard-model Step 0d records, and a2mc-init Step 2 sends every later user to.
    # Without a row, a model counted as onboarded with no way for its next user to build it (P3).
    bg = md / "BUILD.md"
    rows.append((PASS if bg.is_file() else FAIL, "build guide",
                 f"models/{model}/BUILD.md" if bg.is_file()
                 else f"models/{model}/BUILD.md absent — onboard-model Step 0d records the build there"))
    return rows


# --------------------------------------------------------------------------- stage 3
def stage3_rows(case: str):
    rows = []
    cd = ROOT / "use_cases" / case
    if not cd.is_dir():
        return [(FAIL, f"use_cases/{case}", "no such case")]

    cfgs = list((cd / "config").glob("*.sh")) if (cd / "config").is_dir() else []
    rows.append((PASS if cfgs else FAIL, "site config",
                 ", ".join(p.name for p in cfgs) if cfgs else "no *.sh in config/"))

    tgt = cd / "validation" / "targets.yaml"
    if not tgt.is_file():
        rows.append((FAIL, "validation/targets.yaml", "absent"))
    else:
        body = [l for l in tgt.read_text(encoding="utf-8", errors="replace").splitlines()
                if l.strip() and not l.lstrip().startswith("#")]
        rows.append((PASS if body else FAIL, "validation/targets.yaml",
                     f"{len(body)} non-comment line(s)" if body else "present but EMPTY"))

    params = [p for p in (cd / "parameters").iterdir()
              if p.is_file() and p.suffix in (".txt", ".csv", ".yaml", ".json")] \
        if (cd / "parameters").is_dir() else []
    rows.append((PASS if params else FAIL, "parameter list",
                 ", ".join(p.name for p in params[:3]) if params else "no list in parameters/"))

    rounds = cd / "config" / "calibration_rounds.yaml"
    rows.append((PASS if rounds.is_file() else FAIL, "calibration_rounds.yaml", ""))

    if not case_has_state(case):
        # The plan row comes first so "resume at the first failing row" stops at GATE 1 rather than
        # skipping past an unwritten plan to the parameter list (audit 20260923b, persona P6). A
        # file cannot show the user APPROVED it; that stays a human item below.
        plan = cd / "research_plan.md"
        rows.insert(0, (PASS if plan.is_file() else FAIL, "research_plan.md drafted",
                        "" if plan.is_file() else "not yet — onboard-case Step 4 (GATE 1) comes before any value"))
        rows.append(_placeholder_row(cd))

    rows.append((INFO, "goal-conditional preflight",
                 "run `check_setup_ready.py` AFTER sourcing the configs — it owns the "
                 "targets-mapped-to-outputs and cost-function checks this script cannot reach"))
    return rows


# A template value still in place: `<UPPER_SNAKE>` on the value side of a non-comment line, or the
# EcoSIM/PFLOTRAN template's `observed: X.X` / `site: MySite`. Every stage-3 row used to be an
# existence check, so an unedited copy of the model template passed them all and the hook announced
# "No mechanical items outstanding" (audit 20260923b, F32).
# The ELM-FATES template writes its placeholders differently (`"MySite"`, `/path/to/your/...`,
# `site: YourSite`), so a `<...>`-only pattern passed it untouched (persona P7).
_PLACEHOLDER = re.compile(r"<[A-Za-z][A-Za-z0-9_]{2,}>|:\s*X\.X\b|\bMySite\b|\bYourSite\b|/path/to/")


def _placeholder_row(cd: Path):
    hits = {}
    files = list((cd / "config").glob("*.sh")) + [cd / "validation" / "targets.yaml",
                                                   cd / "config" / "calibration_rounds.yaml"]
    for f in files:
        if not f.is_file():
            continue
        n = 0
        for line in f.read_text(encoding="utf-8", errors="replace").splitlines():
            code = line.split("#", 1)[0]
            if _PLACEHOLDER.search(code):
                n += 1
        if n:
            hits[str(f.relative_to(cd))] = n
    if not hits:
        return (PASS, "template placeholders replaced", "")
    return (FAIL, "template placeholders replaced",
            "; ".join("%s: %d line(s)" % kv for kv in sorted(hits.items()))
            + " — onboard-case Step 4(b) fills them after GATE 1")


# --------------------------------------------------------------------------- next skill
def next_skill(stage: int, clone_ok: bool) -> str:
    """The skill a user at this stage should run next, in words. Shared by both hooks and main()."""
    if not clone_ok:
        return "`a2mc-init` (Step 1: this clone is not wired yet)"
    if stage == 1:
        return ("`onboard-case` for a model A2MC has (its Step 2 checks the model install; "
                "`a2mc-init` Step 2 builds one if there is none), or `onboard-model` for one it does not")
    if stage == 2:
        return "`onboard-model`"
    if stage == 3:
        return "`onboard-case`, resuming at the first failing row of each case below"
    return "`onboard-session`"


# --------------------------------------------------------------------------- human remainder
_HUMAN = {
    1: ["the user was greeted, their name recorded with whoami.py, and their experience gauged (Step 0)",
        "the GitHub question was asked, and the answer taken (Step 1)",
        "the model install on this machine was built if needed and verified (Step 2)",
        "the two no-match cases were distinguished (drift vs unsupported model)",
        "the session was routed onward EXPLICITLY, not left trailing off"],
    2: ["a filled questionnaire was supplied, not assumed",
        "the codebase was characterized BEFORE scaffolding (Step 0c)",
        "V1/V2/V3/V4/V5 verdicts were read — a Yellow is a decision, not a pass",
        "the smoke test actually ran the reasoning phases"],
    3: ["target granularity was established FIRST, in the MODEL's own terms",
        "GATE 1: research_plan.md approved by the user",
        "GATE 2: parameter list + ensemble design agreed, with bound_source per parameter",
        "no auto-memory was written about this case"],
    4: [],
}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--model", help="audit this model's onboarding (stage 2)")
    ap.add_argument("--case", help="audit this case (stage 3)")
    ap.add_argument("--stage", type=int, choices=(1, 2, 3), help="force a stage")
    a = ap.parse_args()

    stage, why = detect_stage()
    if a.model:
        stage, why = 2, f"--model {a.model}"
    elif a.case:
        stage, why = 3, f"--case {a.case}"
    elif a.stage:
        stage, why = a.stage, f"--stage {a.stage}"

    names = {1: "a2mc-init", 2: "onboard-model", 3: "onboard-case", 4: "onboard-session (setup done)"}
    print(f"A2MC setup stage: {stage} — {names[stage]}\n  detected because: {why}")
    print(f"  models adapted: {onboarded_models() or '(none)'}")
    print(f"  real cases:     {real_cases() or '(none)'}")

    # THE PER-CLONE ROWS RUN AT EVERY STAGE, and that is a bug fix rather than a nicety.
    # `detect_stage()` returns 4 as soon as any case carries offline workflow state, and a case
    # is DELIVERED -- emailed and unpacked under use_cases/. So a clone wired to nothing reports
    # "setup is done" the moment a finished case lands in it, and these rows, which used to live
    # only in the stage-1 branch below, were never reached by the one person who most needed
    # them. The clone's wiring and the case's maturity are independent facts.
    fails = 0
    clone_ok = True
    try:
        from check_clone_setup import clone_rows
        crow = clone_rows()
        clone_ok = not any(r[0] == FAIL for r in crow)
        fails += _rows_out(crow, "Per-clone setup (every stage)")
    except Exception as exc:                      # never let this break the stage report
        print(f"\n  (per-clone check unavailable: {exc})")
    print(f"\nNEXT: {next_skill(stage, clone_ok)}")

    if stage == 1:
        fails += _rows_out(stage1_rows(), "Stage 1 — a2mc-init (mechanical subset)")
    elif stage == 2:
        targets = [a.model] if a.model else onboarded_models()
        if not targets:
            print("\n  No adapted model yet — this IS stage 2. Start with the `onboard-model` skill.")
        for m in targets:
            fails += _rows_out(stage2_rows(m), f"Stage 2 — onboard-model: {m}")
    elif stage == 3:
        targets = [a.case] if a.case else real_cases()
        for c in targets:
            fails += _rows_out(stage3_rows(c), f"Stage 3 — onboard-case: {c}")
    else:
        print("\n  A case has workflow state, so that case is past setup — `onboard-session` resumes it.")
        print("  The per-clone rows above are a separate question; a delivered case does not wire a clone.")
        pending = cases_in_setup()
        if pending:
            # Stage 4 is repo-wide, so a second case still in setup was invisible here (F93).
            print("  Cases with no workflow state yet (still in setup — `onboard-case` resumes each):")
            for c in pending:
                print(f"    - {c}   (audit: python3 tools/check_stage_ready.py --case {c})")

    human = _HUMAN.get(stage, [])
    if human:
        print(f"\nNot mechanically checkable ({len(human)}) — confirm by hand, `setup-discipline` Stage {stage}:")
        for h in human:
            print(f"  ? {h}")

    print()
    if fails:
        print(f"✗ {fails} FAIL(s) — this stage is NOT complete.")
        return 1
    print("✓ no failures in the mechanical checks. The '?' items above are still yours to confirm.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
