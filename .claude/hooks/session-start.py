#!/usr/bin/env python3
"""SessionStart hook — surface a brief operating snapshot into context at session start
(also runs on resume / after compaction). Best-effort and read-only; never blocks.

Shows: current branch, uncommitted-file count, the most recently changed CALIBRATION
logs and round/cycle reports across the clone's cases, the latest Handoff/Session dev_log plus the latest dev_log
and ana_log of ANY type, the count of pending knowledge proposals awaiting curation, and
any live long-running A2MC processes. Helps the cold-start runbook (CLAUDE.md Rule 6) fire
reliably.

The calibration line is the one present in EVERY clone. The three dev_log/ana_log lines
describe framework-development history, which a clone without any `memory/dev_logs*/` simply
does not have -- their globs return nothing and the lines are omitted, so no reader is
pointed at a directory they lack.
"""
import sys, os, re, json, glob, subprocess


def sh(args):
    try:
        return subprocess.check_output(args, stderr=subprocess.DEVNULL).decode().strip()
    except Exception:
        return ""


def ensure_memory_symlink(root, lines):
    """Self-heal the .claude_memory bucket wiring (docs/29 machinery).

    The harness reads memory from ~/.claude/projects/<cwd-key>/memory/, which must be
    a symlink to the tracked <repo>/.claude_memory/. NON-DESTRUCTIVE: auto-wire only a
    fresh clone (harness path absent or holding no real memories); if the harness store
    holds its OWN memories, WARN loudly and leave it, never clobber/merge automatically.
    Best-effort; never raises. Manual fallback: scripts/setup_clone.sh.
    """
    try:
        bucket = os.path.join(root, ".claude_memory")
        if not os.path.isdir(bucket):
            return  # no tracked bucket on this branch (e.g. a public clone)
        harness = os.path.expanduser(
            "~/.claude/projects/%s/memory" % root.replace("/", "-"))
        if os.path.islink(harness):
            return  # already wired
        mems = [f for f in os.listdir(harness)
                if f.endswith(".md") and f != "MEMORY.md"] if os.path.isdir(harness) else []
        if not mems:
            # fresh clone (absent / empty): safe to auto-wire, back up any empty dir
            if os.path.isdir(harness):
                os.rename(harness, harness + ".pre-symlink-bak")
            os.makedirs(os.path.dirname(harness), exist_ok=True)
            os.symlink(bucket, harness)
            lines.append("✓ auto-wired Claude memory bucket (fresh clone) -> .claude_memory")
        else:
            stray = sorted(set(mems) - {f for f in os.listdir(bucket) if f.endswith(".md")})
            lines.append(
                "⚠ Claude memory bucket NOT wired: %d standalone file(s) in the harness "
                "store%s not under git. Reconcile into .claude_memory/, then run "
                "scripts/setup_clone.sh."
                % (len(mems), (" incl. %s" % ", ".join(stray[:3])) if stray else ""))
    except Exception:
        pass


def memory_checkup_due(root, lines):
    """Weekly memory/skills staleness checkup — a DURABLE trigger.

    CronCreate/Monitor timers are session-only and expire after 7 days, so they cannot carry a
    weekly cadence across session boundaries (see memory
    `feedback_schedule_periodic_reviews_with_a_real_mechanism`). This is stateless instead: a
    timestamp file plus an age check, so it fires the next time a session starts after the
    interval elapses, which for a weekly audit is exactly when it is useful.
    """
    import datetime
    # The checkup and the bucket it audits exist only in the private dev repo: both legs exclude
    # .claude_memory/ and the skill is visibility: private. Without this guard every public clone
    # was told at every session to run a skill it does not have and write into a directory it
    # lacks (audit 20260923b, finding F39) -- the same guard ensure_memory_symlink already has.
    if not os.path.isdir(os.path.join(root, ".claude_memory")) or \
            not os.path.isdir(os.path.join(root, ".claude", "skills", "memory-checkup")):
        return
    stamp = os.path.join(root, ".claude_memory", ".last_checkup")
    today = datetime.date.today()
    try:
        with open(stamp) as f:
            last = datetime.date.fromisoformat(f.read().strip())
        days = (today - last).days
    except Exception:
        days, last = None, None
    if days is None:
        lines.append("\u23f0 memory checkup: never run here \u2014 run the `memory-checkup` skill "
                     "(then: date -I > .claude_memory/.last_checkup)")
    elif days >= 7:
        lines.append("\u23f0 memory checkup DUE \u2014 %d days since %s. Run the `memory-checkup` "
                     "skill (then: date -I > .claude_memory/.last_checkup)" % (days, last))


def resource_headroom(root, lines, relay=None):
    """Filesystem quota and compute allocation, BEFORE anything is written or submitted.

    THE BLIND SPOT THIS CLOSES. Every other line in this snapshot describes work state -- what is
    running, what was logged, what is pending. None describes the RESOURCES that work consumes, so
    resource state only ever becomes visible by failing, and it fails as an error that reads nothing
    like a quota or allocation problem. The queries are sub-second, so the only reason they go
    unrun is that nothing prompts them. (The incident that prompted this is in the dev log named
    below, not here: a docstring asserting a filesystem's state is stale the moment it changes.)

    Why it belongs in the SNAPSHOT rather than in a pre-write check alone: by the time an agent is
    choosing where to put a 2 GB dump it has already designed the experiment around the assumption
    that space exists. The number has to arrive before the design, not during it.

    Only problems are printed. A clone with room says nothing, so this costs a line only when it
    matters. Full detail on demand: tools/check_resources.py

    Background: memory/dev_logs_adapterkit/reflection/20260923e_Reflection_I_Never_Measured_The_Resources_I_Was_Spending.md
    """
    script = os.path.join(root, "tools", "check_resources.py")
    if not os.path.isfile(script):
        return
    # NOT sh(): it uses check_output, which RAISES on a non-zero exit and is swallowed by its
    # try/except -- and check_resources.py signals "over threshold" with exit 1. Routed through
    # sh() this function printed nothing EXACTLY when it had something to say, which is the same
    # failure shape the tool exists to prevent. Read the output regardless of the exit code.
    try:
        proc = subprocess.run([sys.executable, script, "--quiet"],
                              stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                              universal_newlines=True, timeout=90)
        out = (proc.stdout or "").strip()
    except Exception:
        return
    if not out:
        return
    lines.append("RESOURCES -- headroom problems (tools/check_resources.py for the full table):")
    for row in out.splitlines():
        if row.strip():
            lines.append("  " + row.strip())
    lines.append("  A near-full quota breaks the agent's OWN diagnostics: tool output is captured "
                 "under the repo, so a full home degrades the ability to diagnose a full home.")
    lines.append("  Before any bulk write: python3 tools/check_resources.py --need-gb <N>  "
                 "(exit 1 = will not fit, 2 = could not confirm; both mean do not write).")
    # Relay only a CROSSED threshold. A machine without `myquota` prints "QUOTA UNREADABLE
    # [absent]" at every session, and telling a laptop user their disk is low every time would be
    # a false alarm that teaches them to ignore the real one.
    low = [" ".join(r.split()[1:]) for r in out.splitlines() if r.strip().startswith("!!")]
    if relay is not None and low:
        relay.append("Disk or allocation headroom is low: %s. Large writes (an ensemble, big "
                     "outputs) may fail until space is freed." % "; ".join(low))


def hpc_jobs_in_flight(root, lines):
    """Jobs already on the scheduler at session start => `arm-hpc-monitoring` applies NOW.

    THE BLIND SPOT THIS CLOSES. The sibling hook `remind-arm-monitoring.py` is PostToolUse
    on a SUBMISSION, so it can only fire in the session that submits. A session that
    INHERITS running jobs -- the normal case after a compaction, a resume, or simply the
    next day -- never triggers it. That is not a corner case: a multi-day ensemble is
    inherited by every session except the first.

    Why "jobs in flight" is sufficient evidence that nothing is watching them: a Claude
    `Monitor` is session-scoped and does not survive a session boundary, so a starting
    session has zero armed monitors BY CONSTRUCTION. No state file is needed to detect the
    gap -- queued/running jobs at session start always mean "unwatched, so far".

    Motivated by, but NOT demonstrated by, the 2026-08-09 miss: three restarted TRANS chains
    ran ~25 h with a correctly nohup'd watcher writing events no Monitor was reading. The
    submission-time hook did not catch that for the mundane reason that it did not yet exist
    (jobs submitted 08-08 07:36; hook written 08-09 08:11). The inherited-session gap above is
    a property of the TRIGGER, reasoned from where it fires, not an inference from that
    incident. Stated this way deliberately: the first draft of this docstring claimed the jobs
    were inherited from an earlier session, which two timestamps disprove. See
    memory/dev_logs/reflection/20260809a_Reflection_Why_Reading_The_Skill_Was_Not_Enough.md.

    `timeout` is not optional: a busy or degraded SLURM controller makes squeue HANG rather
    than fail, and a session-start hook must never wedge the session.
    """
    out = sh(["bash", "-lc",
              "timeout 15 squeue -u \"$USER\" -h -o '%T' 2>/dev/null "
              "| sort | uniq -c | sort -rn"])
    if not out:
        return                      # no jobs, squeue absent, or the query timed out
    counts, total = [], 0
    for ln in out.splitlines():
        parts = ln.split()
        if len(parts) == 2 and parts[0].isdigit():
            total += int(parts[0])
            counts.append("%s %s" % (parts[0], parts[1].lower()))
    if not total:
        return

    # ADAPTER-KIT ADAPTATION of main's version. `squeue -u $USER` is ACCOUNT-scoped, and this
    # account runs THREE lanes in parallel (main/api-43 Kougarok, adapter-kit/EcoSIM, the demo
    # clone). Main's wording -- "`arm-hpc-monitoring` applies now" -- is right where one lane
    # dominates, but here it routinely reports ANOTHER session's jobs: verified 2026-08-14, this
    # hook fired on 8 in-flight `Kougarok_ELM-FATES_...p169v6rffix...` jobs belonging to the main
    # session, and told this branch to arm monitors on them. That is precisely what
    # `feedback_monitor_only_own_session_launches` forbids ("never monitor simulations not
    # launched by you in this session"), and acting on it once nearly restarted another lane's
    # jobs. So: report the jobs (situational awareness is the point), name a few so the reader can
    # tell whose they are, and make ownership the gate rather than mere presence.
    sample = sh(["bash", "-lc",
                 "timeout 15 squeue -u \"$USER\" -h -o '%j' 2>/dev/null | sort -u | head -3"])
    names = ", ".join(sample.split()) if sample else "(names unavailable)"
    lines.append(
        "⚠ %d HPC job%s IN FLIGHT (%s). A Monitor is session-scoped, so this session starts with "
        "none armed. NOTE this is `squeue -u $USER` — ACCOUNT-scoped, and this account runs "
        "several lanes, so some or all of these may belong to another session. Sample: %s. "
        "Arm `arm-hpc-monitoring` ONLY for jobs THIS session launched; leave the rest to their "
        "owner and never restart them (feedback_monitor_only_own_session_launches)."
        % (total, "" if total == 1 else "s", ", ".join(counts), names))
    # Reuse the sibling hook's wording verbatim so the two can never drift apart.
    try:
        import importlib.util
        _sp = importlib.util.spec_from_file_location(
            "_ram", os.path.join(root, ".claude", "hooks", "remind-arm-monitoring.py"))
        _ram = importlib.util.module_from_spec(_sp)
        _sp.loader.exec_module(_ram)
        body = _ram.MESSAGE.split("\n", 1)[1]      # drop its submission-specific first line
        lines.append("  " + body.replace("\n", "\n  "))
    except Exception:
        lines.append("  Two layers (nohup the watcher, arm Monitor on its LOG); a PROGRESS "
                     "signal, not only state transitions; terminal is an ALLOW-LIST "
                     "cross-checked against filesystem liveness.")



def clone_setup(root, lines, relay=None):
    """Report per-clone wiring that has not happened, AT EVERY STAGE.

    `setup_stage()` below returns silently at stage 4 -- correct for its own question, and exactly
    wrong for this one. A case is DELIVERED: emailed as a folder and unpacked under use_cases/. So
    the first session in a clone wired to nothing reports stage 4 and says nothing, which is the
    one session where saying something matters most.

    Reuses check_clone_setup.clone_rows() rather than restating the checks, the same way
    setup_stage() reuses check_stage_ready.detect_stage(); a second copy would drift from the first.
    """
    try:
        import importlib.util
        path = os.path.join(root, "tools", "check_clone_setup.py")
        if not os.path.isfile(path):
            return
        spec = importlib.util.spec_from_file_location("_ccs", path)
        if spec is None or spec.loader is None:
            return
        m = importlib.util.module_from_spec(spec)
        sys.modules["_ccs"] = m
        spec.loader.exec_module(m)
        bad = [r for r in m.clone_rows() if r[0] == m.FAIL]
        if not bad:
            return
        lines.append("\u26a0 THIS CLONE IS NOT FULLY SET UP (%d item%s). git cannot carry these, so"
                     % (len(bad), "" if len(bad) == 1 else "s"))
        lines.append("  every fresh clone starts without them and nothing else will mention it:")
        for _, label, detail in bad:
            lines.append("    \u2717 %s \u2014 %s" % (label, detail))
        lines.append("  Full report: python3 tools/check_clone_setup.py")
        lines.append("  This is the per-clone half of the `a2mc-init` skill (its Step 1); "
                     "run that skill to")
        lines.append("  work through it, and record the user's name rather than inferring it.")
        if relay is not None:
            relay.append("This A2MC clone is not fully set up (%s). The `a2mc-init` skill, Step 1, "
                         "finishes it." % "; ".join(label for _, label, _ in bad))
    except Exception:
        return                          # a hook must never break a session


def setup_stage(root, lines, relay=None):
    """Surface the SETUP stage when this clone is not yet configured.

    Every other line in this snapshot presumes a configured clone -- handoff, offline state,
    pending knowledge, live jobs. A brand-new user therefore gets a near-empty snapshot and no
    hint that `a2mc-init` exists, which is the discoverability gap `setup-discipline` was written
    to close and could not, being pull-based. Silent on a configured clone (stage 4), so this
    costs a regular session nothing.

    Reuses check_stage_ready.py's own detection rather than restating it -- a second copy of the
    routing rule would drift from the first.
    """
    try:
        import importlib.util
        spec = importlib.util.spec_from_file_location(
            "_csr", os.path.join(root, "tools", "check_stage_ready.py"))
        if spec is None or spec.loader is None:
            return
        m = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(m)
        stage, why = m.detect_stage()
        if stage == 4:
            return                      # setup is done; say nothing
        names = {1: "a2mc-init", 2: "onboard-model", 3: "onboard-case"}
        lines.append("\u25ba SETUP STAGE %d: start with the `%s` skill (%s)."
                     % (stage, names[stage], why))
        lines.append("  Definition of done: the `setup-discipline` skill. "
                     "Audit it now: python3 tools/check_stage_ready.py")
        if relay is not None:
            relay.append("Setup is not finished: it is at stage %d, and the next step is the `%s` "
                         "skill (%s)." % (stage, names[stage], why))
    except Exception:
        return                          # a hook must never break a session


RELAY_HEADER = ("TELL THE USER, briefly, in your first reply: they cannot see this snapshot. "
                "Claude Code gives a start-up hook's output to you, not to them, so what they need "
                "to know reaches them only if you say it:")


def render(lines, relay):
    """The snapshot text. What the USER needs to know comes first, as an instruction to relay it.

    WHY. Claude Code puts SessionStart output (plain stdout, `additionalContext` and `systemMessage`
    alike) into the MODEL's context; the person at the terminal sees at most a collapsed hook line
    (code.claude.com/docs/en/hooks, SessionStart). Until 2026-09-23 this snapshot told a user nothing
    at all: its "THIS CLONE IS NOT FULLY SET UP" line even said "nothing else will mention it", and
    nothing did. `relay` holds the few items that are the USER's business -- an unfinished clone or
    setup, low disk, an invalid calibration state -- each added where it is detected. Empty `relay`
    means no header, so a session with nothing to report stays silent.
    """
    head = []
    if relay:
        head = [RELAY_HEADER] + ["  - " + r for r in relay] + [""]
    return "A2MC session snapshot \u2014\n" + "\n".join(head + lines)


def main():
    root = os.environ.get("CLAUDE_PROJECT_DIR") or os.getcwd()
    lines = []
    relay = []
    ensure_memory_symlink(root, lines)
    clone_setup(root, lines, relay)
    setup_stage(root, lines, relay)
    resource_headroom(root, lines, relay)

    branch = sh(["git", "-C", root, "branch", "--show-current"])
    if branch:
        lines.append("Branch: %s" % branch)

    dirty = sh(["git", "-C", root, "status", "--porcelain"])
    n_dirty = len([l for l in dirty.splitlines() if l.strip()])
    lines.append("Uncommitted files: %d" % n_dirty)

    def latest(pattern, with_stream=False):
        # Newest by the YYYYMMDDx naming convention (basename lexical sort).
        hits = glob.glob(pattern)
        if not hits:
            return ""
        best = sorted(hits, key=os.path.basename)[-1]
        if with_stream:
            return "%s / %s" % (os.path.basename(os.path.dirname(best)),
                                os.path.basename(best))
        return os.path.basename(best)

    # Calibration logs AND round/cycle reports — the application-agent record, and the only
    # such stream that exists in every clone. Reports are included because a round or cycle
    # report is often the fastest read for "where does this stand", while the phase logs carry
    # the finer-grained trail. READMEs are excluded: a template case carries one.
    #
    # NEWEST PER CASE, not newest overall: a flat mtime sort is dominated by whichever case is
    # busiest, which answers "what did I touch last" rather than "where does each case stand".
    # Ordering the per-case rows newest-first still answers the first question with row one. The
    # date is printed so a stale case is visible as stale rather than merely present.
    by_case = {}
    for f in (glob.glob(os.path.join(root, "use_cases", "*", "memory", "logs", "*.md"))
              + glob.glob(os.path.join(root, "use_cases", "*", "reports", "*", "*.md"))):
        if os.path.basename(f) == "README.md":
            continue
        case = f.split(os.sep + "use_cases" + os.sep)[-1].split(os.sep)[0]
        try:
            mt = os.path.getmtime(f)
        except OSError:
            continue
        if case not in by_case or mt > by_case[case][0]:
            by_case[case] = (mt, f)
    if by_case:
        rows = sorted(by_case.items(), key=lambda kv: kv[1][0], reverse=True)
        lines.append("Calibration logs + reports, newest per case:")
        for case, (mt, f) in rows[:8]:
            kind = "report" if (os.sep + "reports" + os.sep) in f else "log"
            day = __import__("datetime").date.fromtimestamp(mt).isoformat()
            lines.append("  %-22s (%-6s) %s  %s" % (case, kind, day, os.path.basename(f)))
        if len(rows) > 8:
            lines.append("  ... and %d more case(s)" % (len(rows) - 8))

    # Narrow cold-start pointer: latest Handoff/Session log specifically.
    # `dev_logs*` — NOT `dev_logs`. Every feature branch keeps its own stream
    # (`memory/dev_logs_<branchname>/`) and writes only there, so globbing the bare
    # directory reports main's newest file and silently misses the branch's own. Measured
    # 2026-08-28 on adapter-kit: it named a 2026-07-14 log while the branch's latest was
    # 2026-08-28, six weeks stale, and nothing looked wrong. The stream is named in the
    # output for the same reason — with 13 directories, the filename alone is ambiguous.
    hs = (glob.glob(os.path.join(root, "memory", "dev_logs*", "*Handoff*")) +
          glob.glob(os.path.join(root, "memory", "dev_logs*", "*Session_Log*")))
    if hs:
        _h = sorted(hs, key=os.path.basename)[-1]
        lines.append("Latest handoff/session log: %s / %s"
                     % (os.path.basename(os.path.dirname(_h)), os.path.basename(_h)))

    # Latest of ANY type in each LIVE stream, so no recent work is missed.
    #
    # `memory/ana_logs/` is deliberately NOT here: that stream is retired, and a stream that
    # receives no new log has a "latest" that can only get staler. The live streams are
    # `memory/dev_logs*/` and `use_cases/<Case>/memory/model_evolution/`; the authority for which
    # is which is `.claude/skills/log/SKILL.md`.
    dev = latest(os.path.join(root, "memory", "dev_logs*", "20*.md"), with_stream=True)
    if dev:
        lines.append("Latest dev_log (any type): %s" % dev)
    # These two are NOT `latest()`: that helper sorts by BASENAME, which is correct only for a
    # stream whose filenames start with YYYYMMDDx. A report basename carries no date, so it needs
    # mtime. Both live under `use_cases/<Case>/...`, so the useful label is the CASE rather than
    # the immediate parent directory, which for one of them is the constant "model_evolution".
    def newest_by_case(pattern, skip_readme=False):
        hits = [f for f in glob.glob(pattern)
                if not (skip_readme and os.path.basename(f) == "README.md")]
        if not hits:
            return ""
        try:
            best = max(hits, key=os.path.getmtime)
        except OSError:
            return ""
        case = best.split(os.sep + "use_cases" + os.sep)[-1].split(os.sep)[0]
        return "%s / %s" % (case, os.path.basename(best))

    mev = newest_by_case(os.path.join(root, "use_cases", "*", "memory",
                                      "model_evolution", "20*.md"))
    if mev:
        lines.append("Latest model_evolution record: %s" % mev)
    rep = newest_by_case(os.path.join(root, "use_cases", "*", "reports", "*", "*.md"),
                         skip_readme=True)
    if rep:
        lines.append("Latest report (any case): %s" % rep)

    # Offline-agent resume state (docs/31): each case's HIGHEST-round
    # workflow_state_offline_r{RR}.json, the most recently TOUCHED case first.
    #
    # NOT the highest round across all cases. A round number is per case -- one case is at R3
    # because it has been calibrated three times, another at R1 because it is newer -- so the two
    # numbers do not share a scale and ranking by them ranks nothing. mtime is what "active"
    # means, and this block carries the `► NEXT: execute it` line, so naming the wrong case here
    # misdirects the whole session.
    #
    # The detail lines (NEXT, objective, validity) are rendered for the ACTIVE case only; every
    # other campaign gets one line, so a second one is visible without burying the first.
    per_case = {}
    for p in glob.glob(os.path.join(root, "use_cases", "*", "memory",
                                    "workflow_state_offline_r*.json")):
        m = re.search(r"_r(\d+)\.json$", p)
        if not m:
            continue
        case = p.split(os.sep + "use_cases" + os.sep)[-1].split(os.sep)[0]
        rnd = int(m.group(1))
        if case not in per_case or rnd > per_case[case][0]:
            try:
                per_case[case] = (rnd, p, os.path.getmtime(p))
            except OSError:
                continue
    ordered = sorted(per_case.items(), key=lambda kv: kv[1][2], reverse=True)
    # Labelled by the CASE DIRECTORY, not the state file's `site` field: the two can disagree,
    # and a round label always carries its case, since every case has its own R1
    # ([[feedback_prefix_round_labels_with_the_case]]).
    also_lines = []
    for _case, (_rnd, _p, _mt) in ordered[1:]:
        try:
            with open(_p) as f:
                _st = json.load(f)
            _nt = len(_st.get("open_threads", []))
            also_lines.append(
                "  (also) %s R%s %s | cycle %s | %d open thread%s | last touched %s"
                % (_case, _st.get("calibration_round"), _st.get("current_phase"),
                   _st.get("experiment_count"), _nt, "" if _nt == 1 else "s",
                   __import__("datetime").date.fromtimestamp(_mt).isoformat()))
        except (OSError, ValueError):
            continue
    best = (ordered[0][1][0], ordered[0][1][1], ordered[0][0]) if ordered else None
    if best:
        try:
            with open(best[1]) as f:
                st = json.load(f)
            nt = len(st.get("open_threads", []))
            lines.append("Offline state (ACTIVE): %s R%s %s | cycle %s | %d open thread%s"
                         % (best[2], st.get("calibration_round"),
                            st.get("current_phase"), st.get("experiment_count"),
                            nt, "" if nt == 1 else "s"))
            # docs/35: the next action is the most salient cold-start line — DRIVE it, don't wait.
            if st.get("open_threads"):
                na = st["open_threads"][0].get("next_action", "")
                if na:
                    lines.append("  ► NEXT: %s  (execute it; pause only at a fork/hard stop)" % na)
            # Phase-6 objective gate (docs/34): surface the binding target + next experiment.
            pd = st.get("phase6_decision")
            if pd and (pd.get("binding_target") or pd.get("next_targeted_experiment")):
                lines.append("  objective: binding target '%s' | next experiment: %s"
                             % (pd.get("binding_target", "?"),
                                pd.get("next_targeted_experiment", "?")))
            # Invariant check — surface a corrupt/misdriving state loudly (non-blocking).
            try:
                import importlib.util
                _sp = importlib.util.spec_from_file_location(
                    "_cwso", os.path.join(root, "tools", "check_workflow_state_offline.py"))
                _cwso = importlib.util.module_from_spec(_sp)
                _sp.loader.exec_module(_cwso)
                _errs, _ = _cwso.check_one(best[1])
                if _errs:
                    lines.append("⚠ Offline state INVALID (%d error%s) — run "
                                 "tools/check_workflow_state_offline.py before driving: %s"
                                 % (len(_errs), "" if len(_errs) == 1 else "s", _errs[0]))
                    relay.append("The offline calibration state for %s is invalid (%s), so the "
                                 "calibration cannot safely resume until it is fixed."
                                 % (st.get("site", "?"), _errs[0]))
            except Exception:
                pass
        except Exception:
            pass

    lines.extend(also_lines)

    open_props = 0
    for p in glob.glob(os.path.join(root, "use_cases", "*", "memory",
                                    "gained_knowledge", "auto_discovered_pending.json")):
        try:
            with open(p) as f:
                d = json.load(f)
            open_props += sum(1 for it in d.get("pending", [])
                              if not it.get("promoted") and not it.get("discarded"))
        except Exception:
            pass
    if open_props:
        lines.append("Pending knowledge proposals to curate: %d "
                     "(run the curate-knowledge skill)" % open_props)

    try:
        memory_checkup_due(root, lines)
    except Exception:
        pass

    ps = sh(["bash", "-lc",
             "ps -ef | grep \"$USER\" | grep -E 'monitor|submit|extract' "
             "| grep -v grep | head -5"])
    if ps:
        lines.append("Live A2MC processes:\n" + ps)

    # Ask the scheduler directly. The `ps` check above sees only THIS login node, so it
    # misses an ensemble whose driver has exited or was launched from another node --
    # while its jobs keep running. Last, so the reminder lands closest to the prompt.
    try:
        hpc_jobs_in_flight(root, lines)
    except Exception:
        pass

    ctx = render(lines, relay)
    print(json.dumps({"hookSpecificOutput": {
        "hookEventName": "SessionStart",
        "additionalContext": ctx}}))

# GUARDED, 2026-08-25. This used to be a bare `main()` at module level. The hook is invoked as a
# SCRIPT (settings.json: `python3 .../session-start.py`), so the guard is behaviour-identical
# there -- but it also stopped `import` from running the ENTIRE snapshot, including `squeue`,
# `ps` and git reads against the real repo.
#
# Measured cost: `tests/test_check_stage_ready.py` imports this module to call `setup_stage()`
# and gives the subprocess 60 seconds. On a login node with 46 jobs queued the import alone
# exceeded that, so three tests failed with TimeoutExpired -- a test that passes on an idle node
# and fails under load, which is the worst shape a test can have because it trains the reader to
# discount failures. Its own helper's docstring had documented the workaround ("importing it
# in-process would emit a full snapshot") rather than the fix.
if __name__ == "__main__":
    main()
