#!/usr/bin/env python3
"""PreToolUse(Bash) hook -- before a simulation is submitted: the model's run skill, its template run files, and an archived copy.

visibility: public

WHAT IT GATES. A submission of simulations for a case, in Phase 0 or Phase 5:
  * `tools/submit_run.py ... --case-dir use_cases/<Case> ... -- <script>`  (a gate, pilot, probe, rerun,
    V0 arm or experiment: every test run), and
  * `A2MC_UNTRACKED_JOB=... sbatch ... use_cases/<Case>/...`               (a full Phase-0 ensemble).
Anything else (a build, an extraction, a transfer, a command that only mentions sbatch) passes.

WHAT IT REQUIRES, all three:
  1. THE MODEL'S RUN SKILL was invoked in this session after its newest compaction:
     `ecosim-run-workflow`, `pflotran-run-workflow`, `ats-run-workflow`, or `offline-testing-workflow`
     for ELM-FATES, chosen from the case's `{Model}_{Case}` name. A compaction discards a skill's text,
     so an invocation from before it no longer counts (the same rule `tools/check_skill_claims.py`
     applies to logs).
  2. THE CASE'S TEMPLATE RUN FILES were checked: its `use_cases/<Case>/case_template/README.md`, the
     generated index of launchers and namelists, was read or printed in this session after the newest
     compaction, by a tool call other than this submission.
  3. THE RUN FILES ARE ARCHIVED before they run: a byte-identical copy of the submitted script, and of
     every namelist or input deck (`*.nml`, `*.in`, `*.xml`) in `--run-dir`, sits in the stem's
     `submit_scripts/` (Phase 5 and test runs, `phase_results/<stem>/submit_scripts/`) or its
     `run_tracking/submit_scripts/` (Phase 0, `phase0-design` Step 3). A `--run-root` submission
     needs the launcher and at least one run file there. A full ensemble needs its launcher in the
     newest Phase-0 stem's `run_tracking/submit_scripts/`.

WHY. The run skill owns staging, the namelist's limits and the binary binding; the template index is
where an existing launcher is found instead of written again; and the submit script is the only
record of which binary a run was bound to, while the run directory is scratch. Each was skipped at
least once by a run that was then audited after the fact (the dev log
`memory/dev_logs_adapterkit/20261016k_A_Submission_Requires_The_Run_Skill_Templates_And_An_Archive.md`).

OVERRIDE. `A2MC_RUN_GATE_OVERRIDE="<why>"` on the command (at least 10 characters) lets a submission
through; the reason lands in the transcript, which is the record. Use it for a case with no run skill
or no case_template, not to skip the work.

DEGRADES. With no transcript in the payload, checks 1 and 2 cannot be made and are skipped; check 3
still runs. A case whose model has no known run skill is not gated on 1. The hook never raises.

Schema: denies via {"hookSpecificOutput": {"hookEventName": "PreToolUse", "permissionDecision":
"deny", "permissionDecisionReason": ...}}.

Author: Jing Tao with Claude on Perlmutter
"""
import filecmp
import glob
import json
import os
import re
import shlex
import sys

ROOT = os.environ.get("CLAUDE_PROJECT_DIR") or os.path.dirname(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

RUN_SKILL = {"EcoSIM": "ecosim-run-workflow", "PFLOTRAN": "pflotran-run-workflow",
             "ATS": "ats-run-workflow", "ELM-FATES": "offline-testing-workflow"}
RUN_FILE = re.compile(r"\.(nml|in|xml)$")
SUBMIT_RUN = re.compile(r"\btools/submit_run\.py\b")
UNTRACKED = re.compile(r"\bA2MC_UNTRACKED_JOB=")
SBATCH = re.compile(r"(?:^|[;&|(\n`]|\$\()\s*(?:[A-Za-z_][A-Za-z0-9_]*=(?:\"[^\"]*\"|'[^']*'|\S*)\s+)*sbatch(?=\s)")
OVERRIDE = re.compile(r"""\bA2MC_RUN_GATE_OVERRIDE=(?:"([^"]*)"|'([^']*)'|(\S+))""")
CASE_PATH = re.compile(r"use_cases/([A-Za-z0-9][A-Za-z0-9_.\-]*)/")


def deny(reason):
    print(json.dumps({"hookSpecificOutput": {"hookEventName": "PreToolUse",
                                             "permissionDecision": "deny",
                                             "permissionDecisionReason": reason}}))


def model_prefix(case):
    for p in sorted(RUN_SKILL, key=len, reverse=True):
        if case.startswith(p + "_"):
            return p
    return None


def transcript_evidence(path, case, own_id):
    """(skills invoked after the newest compaction, whether case_template/README.md was read after it)."""
    needle = "use_cases/%s/case_template/README.md" % case
    boundary, skills, readme = -1, {}, []
    try:
        fh = open(path, errors="ignore")
    except (OSError, TypeError):
        return None, None
    with fh:
        for lineno, line in enumerate(fh):
            if '"compact_boundary"' in line:
                try:
                    if json.loads(line).get("subtype") == "compact_boundary":
                        boundary = lineno
                except Exception:
                    pass
                continue
            if '"Skill"' not in line and needle not in line:
                continue
            try:
                rec = json.loads(line)
            except Exception:
                continue
            content = (rec.get("message") or {}).get("content") or []
            if not isinstance(content, list):
                continue
            for blk in content:
                if not (isinstance(blk, dict) and blk.get("type") == "tool_use"):
                    continue
                if blk.get("id") == own_id:
                    continue
                inp = blk.get("input") or {}
                if blk.get("name") == "Skill" and inp.get("skill"):
                    skills[inp["skill"].strip().lstrip("/")] = lineno
                elif needle in json.dumps(inp):
                    readme.append(lineno)
    after = {s for s, ln in skills.items() if ln > boundary}
    return after, any(ln > boundary for ln in readme)


def archive_dirs(case, stem):
    base = os.path.join(ROOT, "use_cases", case, "memory", "phase_results", stem)
    return [d for d in (os.path.join(base, "submit_scripts"),
                        os.path.join(base, "run_tracking", "submit_scripts")) if os.path.isdir(d)]


def archived(path, dirs):
    """Is a byte-identical copy of `path` in any of `dirs`?"""
    if not os.path.isfile(path):
        return True                     # cannot compare what is not there; the submission fails anyway
    for d in dirs:
        for cand in glob.glob(os.path.join(d, "**", "*"), recursive=True):
            if os.path.isfile(cand) and os.path.getsize(cand) == os.path.getsize(path) \
                    and filecmp.cmp(cand, path, shallow=False):
                return True
    return False


ASSIGN = re.compile(r"""(?:^|[;&|\s(])([A-Za-z_][A-Za-z0-9_]*)=("[^"]*"|'[^']*'|[^\s;&|)]+)""")


def expander(cmd):
    """Expand $NAME / ${NAME} from assignments made in the command itself, then from the environment."""
    env = {}
    for k, v in ASSIGN.findall(cmd):
        env[k] = v.strip("'\"")
    def expand(t):
        if t is None:
            return t
        for _ in range(3):
            t2 = re.sub(r"\$\{([A-Za-z_][A-Za-z0-9_]*)\}|\$([A-Za-z_][A-Za-z0-9_]*)",
                        lambda m: env.get(m.group(1) or m.group(2), os.environ.get(m.group(1) or m.group(2), m.group(0))), t)
            if t2 == t:
                break
            t = t2
        return t
    return expand


def abspath(p):
    return p if os.path.isabs(p) else os.path.join(ROOT, p)


def opt(tokens, name):
    for i, t in enumerate(tokens):
        if t == name and i + 1 < len(tokens):
            return tokens[i + 1]
        if t.startswith(name + "="):
            return t.split("=", 1)[1]
    return None


def main():
    payload = json.load(sys.stdin)
    if payload.get("tool_name") != "Bash":
        return
    cmd = (payload.get("tool_input") or {}).get("command") or ""
    is_test = bool(SUBMIT_RUN.search(cmd))
    is_ensemble = bool(UNTRACKED.search(cmd) and SBATCH.search(cmd) and "--test-only" not in cmd)
    if not (is_test or is_ensemble):
        return
    m = OVERRIDE.search(cmd)
    if m and len((m.group(1) or m.group(2) or m.group(3) or "").strip()) >= 10:
        return
    try:
        tokens = shlex.split(cmd, comments=False)
    except ValueError:
        tokens = cmd.split()
    expand = expander(cmd)
    tokens = [expand(t) for t in tokens]

    if is_test:
        cd = opt(tokens, "--case-dir")
        case = os.path.basename(os.path.normpath(cd)) if cd else None
    else:
        hits = CASE_PATH.findall(cmd)
        case = hits[0] if hits else None
    if not case or not os.path.isdir(os.path.join(ROOT, "use_cases", case)):
        return

    problems = []
    prefix = model_prefix(case)
    skills, readme = transcript_evidence(payload.get("transcript_path"), case, payload.get("tool_use_id"))
    if skills is not None:
        need = RUN_SKILL.get(prefix)
        if need and need not in skills:
            problems.append("1. invoke the `%s` skill first (not since this session's newest compaction): "
                            "it owns staging, the namelist's limits and the binary binding for this model"
                            % need)
        tmpl = os.path.join(ROOT, "use_cases", case, "case_template", "README.md")
        if os.path.isfile(tmpl) and not readme:
            problems.append("2. read the case's template run-file index first: use_cases/%s/case_template/README.md "
                            "(an existing launcher or namelist there is adapted, not written again; an adapted "
                            "one names its source with `Template: case_template/<name>`)" % case)

    if is_test:
        stem = opt(tokens, "--stem")
        rest = tokens[tokens.index("--") + 1:] if "--" in tokens else []
        script = next((t for t in rest if t.endswith(".sh")), None) or next(
            (t for t in reversed(rest) if not t.startswith("-")), None)
        if script and "$" in script:
            problems.append("3. give the submitted script as a resolvable path (%s did not resolve), so its "
                            "archived copy can be checked" % script)
            script = None
        files = [abspath(script)] if script else []
        run_dir, run_root = opt(tokens, "--run-dir"), opt(tokens, "--run-root")
        if run_dir and os.path.isdir(abspath(run_dir)):
            files += sorted(os.path.join(abspath(run_dir), f) for f in os.listdir(abspath(run_dir))
                            if RUN_FILE.search(f) and os.path.getsize(os.path.join(abspath(run_dir), f)) < 2 ** 20)
        dirs = archive_dirs(case, stem) if stem else []
        where = ("use_cases/%s/memory/phase_results/%s/submit_scripts/ (or run_tracking/submit_scripts/ "
                 "for a Phase-0 stem)" % (case, stem or "<stem>"))
        if not stem:
            problems.append("3. give --stem, so the run's files have an archive to go to")
        else:
            missing = [f for f in files if not archived(f, dirs)]
            if missing:
                problems.append("3. archive these into %s before submitting, byte-identical: %s"
                                % (where, ", ".join(missing)))
            if run_root and not any(RUN_FILE.search(c) for d in dirs
                                    for c in glob.glob(os.path.join(d, "**", "*"), recursive=True)):
                problems.append("3. archive at least one representative run file (namelist or deck) into %s"
                                % where)
    else:
        stems = sorted(glob.glob(os.path.join(ROOT, "use_cases", case, "memory", "phase_results",
                                              "*_phase0_design_r*")))
        launchers = [abspath(t) for t in tokens if t.endswith(".sh") and os.path.isfile(abspath(t))]
        if stems and launchers:
            dirs = [d for d in [os.path.join(stems[-1], "run_tracking", "submit_scripts")] if os.path.isdir(d)]
            missing = [f for f in launchers if not archived(f, dirs)]
            if missing:
                problems.append("3. archive the launcher into %s/run_tracking/submit_scripts/ before submitting "
                                "(phase0-design Step 3): %s" % (os.path.relpath(stems[-1], ROOT), ", ".join(missing)))

    if problems:
        deny("Submission held for %s: the run skill, the template run files and an archived copy come first.\n%s\n"
             "If this case genuinely has no run skill or template, declare it on the command: "
             "A2MC_RUN_GATE_OVERRIDE=\"<why>\"." % (case, "\n".join(problems)))


if __name__ == "__main__":
    try:
        main()
    except Exception:
        pass
