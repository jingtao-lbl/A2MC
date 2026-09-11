#!/usr/bin/env python3
"""Goal-conditional 'is this site ready for Phase 0?' preflight for A2MC setup.

Runs the full preparation checklist AFTER the user has sourced a2mc_config.sh + the
site config. It is deliberately GOAL-AWARE, not a rigid list: checks that don't apply
to the user's goal report N/A instead of failing.

  - PFT inventory is required ONLY for PFT-level targets (a MODIS/tower GPP goal that
    calibrates ecosystem fluxes needs no per-PFT breakdown -> N/A).
  - The simulation protocol (ADSP/RGSP/TRANS spin-up) is READ from config and reported,
    not required -- a user who doesn't care about BGC may run no spin-up.
  - FATES base param file / RAG milestone apply only when FATES is enabled.

Universal checks (always required): model path + milestone, site config overrides the
machine config, targets.yaml valid AND its targets mapped to model output variables
with a cost function established, parameter list present, calibration_rounds.yaml
present + consistent with the config (via tools/check_calibration_rounds.py).

Exit 0 = no failures (N/A and INFO don't fail); exit 1 = at least one FAIL.

Usage:
    source a2mc_config.sh
    source use_cases/<site>/config/<site>_config.sh
    python tools/check_setup_ready.py

Companion doc for the milestone step: docs/a2mc_reference/version_association_howto.md.
Author: Jing Tao with Claude.
"""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

ROOT_GUESS = Path(__file__).resolve().parent.parent

PASS, FAIL, NA, INFO, WARN = "PASS", "FAIL", "NA", "INFO", "WARN"
_MARK = {PASS: "✓", FAIL: "✗", NA: "–", INFO: "ℹ", WARN: "!"}


def env(name: str, default: str = "") -> str:
    return os.environ.get(name, default) or default


def _root() -> Path:
    ucd = env("A2MC_USE_CASE_DIR")
    if not ucd:
        # A fresh clone cannot follow "source the site config" -- there is no site config yet.
        # Route instead of dead-ending; check_stage_ready.py answers the earlier question and
        # needs nothing sourced. (2026-08-19)
        uc = ROOT_GUESS / "use_cases"
        real = [p.name for p in uc.iterdir()
                if p.is_dir() and p.name not in ("TEMPLATE", "__pycache__")
                and not p.name.endswith("_template")] if uc.is_dir() else []
        if not real:
            sys.exit("ERROR: no configured use case in this clone yet — this is first-run setup.\n"
                     "       Start with the `a2mc-init` skill, or run:  "
                     "python3 tools/check_stage_ready.py")
        sys.exit("ERROR: A2MC_USE_CASE_DIR unset — source a2mc_config.sh + the site config first.\n"
                 "       Cases in this clone: " + ", ".join(sorted(real)))
    return Path(ucd).resolve().parent.parent


def _run(argv: list[str]) -> tuple[int, str]:
    try:
        out = subprocess.run(argv, capture_output=True, text=True, cwd=str(_root()))
        return out.returncode, (out.stdout or "") + (out.stderr or "")
    except Exception as e:  # pragma: no cover
        return 1, str(e)


def _load_targets() -> dict:
    tf = env("A2MC_VALIDATION_TARGETS")
    if not tf or not Path(tf).exists():
        return {}
    try:
        import yaml
        with open(tf) as f:
            doc = yaml.safe_load(f) or {}
        return doc.get("targets", {}) or {}
    except Exception:
        return {}


def rounds_tools_for(model):
    """(checker, generator) for the round record, dispatched by ACTIVE MODEL.

    The FATES pair is FATES-config-coupled -- it asserts CIME spin-up phases (`protocol.suplphos`,
    `protocol.suplnitro`) that an adapter round record correctly does not have. Run against
    EcoSIM/PFLOTRAN/ATS it reports a FALSE mismatch and points at the wrong generator. Measured
    2026-08-26 on EcoSIM_BioCON R3: "2 mismatch(es)" from the FATES checker on a round the adapter
    checker passes clean. Same dispatch the targets check already does; this gate was the one place
    that had not been.
    """
    if (model or "fates").strip().lower() == "fates":
        return "tools/check_calibration_rounds.py", "tools/generate_calibration_rounds.py"
    return ("scripts/check_adapter_calibration_rounds.py",
            "scripts/generate_adapter_calibration_rounds.py")


def targets_check_verdict(model: str, rc: int):
    """(blocked, warned) for the targets check, from a validator's exit code.

    THE TWO VALIDATORS HAVE DIFFERENT EXIT-CODE CONTRACTS, and normalising them is half the fix:
      validate_targets_config.py (FATES)  : 0 = clean OR warnings, 1 = errors, 2 = no file
      validate_model_targets.py (adapter) : 0 = clean, 1 = WARNINGS ONLY, 2 = errors

    A bare `rc == 0` test fails an adapter case on warnings while passing a FATES case on warnings.
    EcoSIM_Lusignan has 0 errors and 3 warnings, so dispatching ALONE would have left it ✗ and the
    gate just as unreachable. The gate's contract is "errors block Phase 0, warnings do not".
    """
    if model == "fates":
        return rc != 0, False
    return rc >= 2, rc == 1


#: Env var holding the adopted binary, per non-CIME model. CIME models build per case and have no
#: single archived executable, so they are absent here and the check reports N/A. VERIFIED against
#: the shipped configs -- only these two exist. ATS is deliberately ABSENT rather than guessed:
#: inventing `A2MC_ATS_BINARY` here would create a second name for a quantity ATS does not yet
#: define, which is the "two names for one quantity" shape the config check exists to prevent.
_BINARY_ENV = {"ecosim": "A2MC_ECOSIM_BINARY",
               "pflotran": "A2MC_PFLOTRAN_BINARY"}


def _declared_switches(root: Path, model: str, binary: str):
    """(label, [(key, recommended_value)], note) for the adopted binary, from the case manifest.

    WHY THIS EXISTS. An archived binary's provenance records what is IN it -- commit, checksum,
    size. It records nothing about what must be SET to get the behaviour it was built for, and a
    compiled-in default-off switch is invisible in a run log: its absence from a namelist is
    byte-identical to a deliberate choice to leave it off. Measured 2026-09-04: EcoSIM's
    `guard_floor_dying_stand` shipped 2026-08-20, was compiled into every binary since, was
    enabled only by one round's per-cohort relaunch runbook, and reached no case template. It was
    therefore OFF for EcoSIM_TeRaCON R1, which lost 8 of its first 364 cases to an abort the
    binary already knew how to suppress. Nothing in the setup gate could have asked.
    """
    import json
    label = Path(binary).parent.name
    man = Path(env("A2MC_USE_CASE_DIR", "")) / "config" / "binary_archive_manifest.json"
    if not man.is_file():
        return label, None, f"no binary_archive_manifest.json beside this case's config"
    try:
        entries = json.loads(man.read_text())["archives"]
    except Exception as exc:                                    # pragma: no cover - malformed json
        return label, None, f"cannot read {man.name}: {exc}"
    entry = next((e for e in entries if e.get("label") == label), None)
    if entry is None:
        return label, None, (f"'{label}' is not in {man.name} -- run "
                             f"tools/binary_archive_manifest.py --generate")
    decl = (entry.get("runtime_switches") or "").strip()
    if not decl:
        return label, [], "the manifest records no runtime_switches for this binary"
    # "key=.true. RECOMMENDED ..." -- take each key=value pair, ignore the prose around it.
    import re
    pairs = re.findall(r"([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(\.\w+\.|[-\w.]+)", decl)
    return label, pairs, decl


def _namelist_sets(nml: Path, key: str):
    """The value `key` is set to in a namelist file, or None if it does not appear."""
    import re
    if not nml.is_file():
        return None
    for ln in nml.read_text(errors="replace").splitlines():
        ln = ln.split("!", 1)[0]                                # strip comments; ! is the marker
        m = re.match(r"\s*%s\s*=\s*(\S+?),?\s*$" % re.escape(key), ln, re.I)
        if m:
            return m.group(1)
    return None


def check_binary_switches(add, root: Path, model: str):
    """Does this case SET the runtime switches its adopted binary declares?"""
    grp = "Binary provenance"
    var = _BINARY_ENV.get(model)
    if not var:
        add(grp, NA, "adopted-binary runtime switches",
            f"{model} builds per case (CIME) — no single archived binary")
        return
    binary = env(var)
    if not binary:
        add(grp, NA, "adopted-binary runtime switches", f"{var} unset")
        return
    if "/build/" in binary and "/build_archive/" not in binary:
        add(grp, FAIL, "binary is an ARCHIVE, not the live build tree",
            f"{binary} — one rebuild overwrites it in place and a queued job resolves its exe at "
            f"RUN time (feedback_bind_runs_to_archived_binaries)")
        return
    add(grp, PASS if Path(binary).exists() else FAIL, "adopted binary exists",
        binary)

    label, pairs, note = _declared_switches(root, model, binary)
    if pairs is None:
        add(grp, WARN, "binary declares its required runtime switches", note)
        return
    if not pairs:
        add(grp, INFO, "binary declares its required runtime switches", note)
        return

    # The namelist the ensemble is materialized FROM is the one that decides.
    # PER-MODEL form ONLY, verified against the shipped configs: EcoSIM exports
    # A2MC_ECOSIM_BASE_NAMELIST. A generic `A2MC_BASE_NAMELIST` fallback was written here first and
    # REMOVED -- it exists nowhere in the repo, so it would have been a second name for a quantity
    # that already has one, with zero readers to justify it.
    nml = Path(env(f"A2MC_{model.upper()}_BASE_NAMELIST"))
    if not nml.is_file():
        add(grp, WARN, f"{label} declares {len(pairs)} switch(es); cannot check the namelist",
            f"A2MC_{model.upper()}_BASE_NAMELIST is unset or does not point at a file")
        return
    for key, want in pairs:
        got = _namelist_sets(nml, key)
        if got is None:
            add(grp, WARN, f"{key} is NOT set in {nml.name}",
                f"{label} recommends {key}={want}. A namelist read does not require the key, so "
                f"its absence is SILENT and leaves the compiled-in default. Set it deliberately, "
                f"either way.")
        elif got.lower() != want.lower():
            add(grp, INFO, f"{key} = {got} in {nml.name}",
                f"deliberate: {label} recommends {want}")
        else:
            add(grp, PASS, f"{key} = {got} in {nml.name}", f"matches what {label} recommends")


def main() -> None:
    root = _root()
    py = sys.executable
    fates_on = "fates" in env("A2MC_ELM_OPTIONS").lower() or bool(env("A2MC_FATES_PARTEH_MODE"))
    targets = _load_targets()
    pft_targets = {k: v for k, v in targets.items()
                   if isinstance(k, str) and k[:3] == "PFT" and "_" in k and k[3].isdigit()}
    pft_level = bool(pft_targets)

    results: list[tuple[str, str, str, str]] = []  # (group, status, label, detail)

    def add(group: str, status: str, label: str, detail: str = ""):
        results.append((group, status, label, detail))

    # ---- Universal ----
    mp = env("A2MC_MODEL_PATH")
    add("Model + milestone", PASS if mp and Path(mp).exists() else FAIL,
        "A2MC_MODEL_PATH set and exists", mp or "<unset>")

    if fates_on:
        rc, out = _run([py, "scripts/rag_match.py"])
        sel = next((ln.strip() for ln in out.splitlines() if "Selection:" in ln), "")
        matched = rc == 0 and "no_match" not in out.lower()
        add("Model + milestone", PASS if matched else FAIL,
            "checkout matches a registered RAG milestone",
            sel or "see: python scripts/rag_match.py (docs/a2mc_reference/version_association_howto.md)")
    else:
        add("Model + milestone", NA, "RAG milestone match", "FATES off — RAG milestone N/A")

    # site config overrides machine config
    sc = env("A2MC_SITE_CONFIG")
    site_ok = bool(sc) and Path(sc).exists() and bool(env("A2MC_ENSEMBLE_NAME")) and bool(env("A2MC_USE_CASE_DIR"))
    add("Config layering", PASS if site_ok else FAIL,
        "site config sourced + overrides a2mc_config.sh",
        f"A2MC_SITE_CONFIG={Path(sc).name if sc else '<unset>'}, ENSEMBLE_NAME={env('A2MC_ENSEMBLE_NAME') or '<unset>'}")

    # targets.yaml valid -- DISPATCHED BY MODEL.
    #
    # There are two target validators and they are not interchangeable.
    # `validate_targets_config.py` is FATES-shaped (rule R1 wants `PFT<id>_<var>` names, S3 wants a
    # `time_year`/`time_month` anchor); `validate_model_targets.py` is the model-generic one that
    # understands `variable`/`reduce`/`window_years`. Running the FATES one on an adapter case
    # produced exactly 2 spurious errors PER TARGET -- measured 2026-08-16: EcoSIM_BioCON 6,
    # EcoSIM_Lusignan 6, PFLOTRAN_miniLEO 22 -- so this gate could NEVER pass for two thirds of the
    # onboarded models, and never had. Audit: memory/dev_logs_adapterkit/20260816b.
    #
    # FATES keeps the previous behaviour byte-for-byte: it is the only validator that understands
    # SZPF resolution and the PFT<id>_<var> contract.
    active_model = (os.environ.get("A2MC_MODEL", "") or "fates").strip().lower()
    if active_model == "fates":
        rc, out = _run([py, "tools/validate_targets_config.py"])
        _which = "validate_targets_config.py"
    else:
        _tgt = env("A2MC_VALIDATION_TARGETS") or str(
            Path(env("A2MC_USE_CASE_DIR") or ".") / "validation" / "targets.yaml")
        rc, out = _run([py, "tools/validate_model_targets.py",
                        "--model", active_model, "--targets", _tgt])
        _which = f"validate_model_targets.py --model {active_model}"

    # THE TWO VALIDATORS HAVE DIFFERENT EXIT-CODE CONTRACTS. Normalise here, or dispatching
    # alone would leave the gate just as unreachable:
    #   validate_targets_config.py (FATES) : 0 = clean OR warnings, 1 = errors, 2 = no file
    #   validate_model_targets.py (adapter): 0 = clean, 1 = WARNINGS ONLY, 2 = errors
    # A bare `rc == 0` test therefore FAILS an adapter case on warnings while PASSING a FATES case
    # on warnings. EcoSIM_Lusignan has 0 errors and 3 warnings, so it would still have been ✗.
    # The gate's contract is "errors block Phase 0, warnings do not" -- apply it to both.
    _blocked, _warned = targets_check_verdict(active_model, rc)
    add("Targets + cost fn", FAIL if _blocked else PASS, _which,
        "run it directly for details" if _blocked
        else ("warnings only (do not block Phase 0) — run it directly to review" if _warned else ""))

    # targets mapped to model output variables + cost function established
    if not targets:
        add("Targets + cost fn", FAIL, "targets present + mapped to output variables",
            "no targets found in targets.yaml")
    else:
        missing_var = [k for k, v in targets.items()
                       if not (isinstance(v, dict) and str(v.get("variable", "")).strip()
                               and "TODO" not in str(v.get("variable", "")))]
        def _has_obs(v):
            # valid if a scalar snapshot `observed`, OR a non-empty time-series `observations:` list
            if isinstance(v.get("observed"), (int, float)):
                return True
            obs = v.get("observations")
            return isinstance(obs, list) and len(obs) > 0
        missing_obs = [k for k, v in targets.items() if not (isinstance(v, dict) and _has_obs(v))]
        add("Targets + cost fn", PASS if not missing_var else FAIL,
            "every target mapped to a model output variable",
            "" if not missing_var else f"missing/placeholder `variable`: {missing_var}")
        add("Targets + cost fn", PASS if not missing_obs else FAIL,
            "every target has an observed value + uncertainty",
            "" if not missing_obs else f"missing numeric `observed`: {missing_obs}")
        # cost function established
        try:
            import yaml
            cc = (yaml.safe_load(open(env("A2MC_VALIDATION_TARGETS"))) or {}).get("cost_config", {}) or {}
        except Exception:
            cc = {}
        cost_ok = bool(cc.get("error_method")) and bool(cc.get("aggregation_method"))
        add("Targets + cost fn", PASS if cost_ok else FAIL, "cost function established (cost_config)",
            f"error_method={cc.get('error_method')}, aggregation={cc.get('aggregation_method')}"
            if cost_ok else "cost_config missing error_method/aggregation_method (confirm with user)")

    # parameter list + salib
    pl = env("A2MC_PARAM_LIST_FILE")
    add("Parameters", PASS if pl and Path(pl).exists() else FAIL,
        "parameter list file exists", Path(pl).name if pl else "<unset>")
    sp = env("A2MC_SALIB_PROBLEM_FILE")
    add("Parameters", PASS if sp and Path(sp).exists() else NA,
        "SALib problem file", (Path(sp).name if sp and Path(sp).exists()
                               else "not yet generated — Phase 0 create_parameter_sample.py writes it"))

    # calibration_rounds.yaml present + consistent
    cr = root / "use_cases" / Path(env("A2MC_USE_CASE_DIR")).name / "config" / "calibration_rounds.yaml"
    # DISPATCH BY MODEL, like the targets check above. The FATES generator/checker pair is
    # FATES-config-coupled: it asserts CIME spin-up phases (protocol.suplphos / suplnitro) that an
    # adapter round record correctly does not have, so running it against EcoSIM/PFLOTRAN/ATS
    # reported a FALSE mismatch and told the user to regenerate with the wrong generator. Measured
    # 2026-08-26 on EcoSIM_BioCON R3: the FATES checker reported "2 mismatch(es)" on a round the
    # adapter checker passes clean. `onboard-case` already warns the two are not interchangeable;
    # this gate was the one place that had not been dispatched.
    _checker, _generator = rounds_tools_for(active_model)
    if not cr.exists():
        add("Round record", FAIL, "calibration_rounds.yaml exists",
            f"missing — generate: python {_generator} --round 1 --write")
    else:
        rc, out = _run([py, _checker])
        add("Round record", PASS if rc == 0 else FAIL,
            f"calibration_rounds.yaml consistent with config ({Path(_checker).name})",
            "" if rc == 0 else f"mismatch — run {_checker} for the diff")

    # ---- Conditional ----
    if pft_level:
        pfts = env("A2MC_PFTS")
        base = env("A2MC_BASE_PARAM_FILE")
        valid_ids: set[int] = set()
        try:
            sys.path.insert(0, str(root))
            from tools.fates_utils import get_pft_names_from_file  # type: ignore
            valid_ids = set(get_pft_names_from_file(base).keys()) if base and Path(base).exists() else set()
        except Exception:
            pass
        want = {int(x) for x in pfts.split(",") if x.strip().isdigit()} if pfts else set()
        tgt_pfts = {int(v.get("pft")) for v in pft_targets.values() if isinstance(v, dict) and v.get("pft")}
        problems = []
        if not want:
            problems.append("A2MC_PFTS unset")
        if valid_ids and not want <= valid_ids:
            problems.append(f"A2MC_PFTS {sorted(want - valid_ids)} not in base file PFTs {sorted(valid_ids)}")
        if valid_ids and not tgt_pfts <= valid_ids:
            problems.append(f"target PFTs {sorted(tgt_pfts - valid_ids)} not in base file")
        add("PFT inventory (PFT-level goal)", PASS if not problems else FAIL,
            "A2MC_PFTS set + PFT ids valid in the base param file",
            f"A2MC_PFTS={pfts}" if not problems else "; ".join(problems))
    else:
        add("PFT inventory", NA, "PFT inventory / A2MC_PFTS",
            "ecosystem-level goal (no PFT-level targets) — PFT inventory not required")

    if fates_on:
        base = env("A2MC_BASE_PARAM_FILE")
        add("FATES base file", PASS if base and Path(base).exists() else FAIL,
            "FATES base parameter file exists", base or "<unset>")
    else:
        add("FATES base file", NA, "FATES base parameter file", "FATES off — N/A")

    # protocol is INFORMATIONAL (read from config, not required)
    def yr(p):
        return env(f"A2MC_{p}_YEARS", "0")
    proto = "; ".join(
        f"{p}: {yr(p)}yr suplP={env(f'A2MC_{p}_SUPLPHOS','NONE')}/suplN={env(f'A2MC_{p}_SUPLNITRO','NONE')}"
        for p in ("ADSP", "RGSP", "TRANS"))
    add("Simulation protocol", INFO, "configured protocol (confirm it matches the goal)", proto)

    check_binary_switches(add, root, env("A2MC_MODEL", "fates").lower())

    # ---- report ----
    order = ["Model + milestone", "Config layering", "Targets + cost fn", "Parameters",
             "Round record", "PFT inventory (PFT-level goal)", "PFT inventory", "FATES base file",
             "Simulation protocol", "Binary provenance"]
    seen_groups = [g for g in order if any(r[0] == g for r in results)]
    print(f"A2MC setup readiness — site '{Path(env('A2MC_USE_CASE_DIR')).name}' "
          f"({'FATES' if fates_on else 'ELM-only'}, "
          f"{'PFT-level' if pft_level else 'ecosystem-level'} targets)\n")
    for g in seen_groups:
        print(f"  {g}:")
        for grp, status, label, detail in results:
            if grp != g:
                continue
            line = f"    [{_MARK[status]}] {label}"
            if detail:
                line += f"   {detail}"
            print(line)
    n_fail = sum(1 for _, s, _, _ in results if s == FAIL)
    print()
    if n_fail:
        print(f"✗ {n_fail} check(s) FAILED — not ready for Phase 0. Resolve the ✗ items above.")
        sys.exit(1)
    print("✓ setup is ready for Phase 0 (all applicable checks pass; N/A items don't apply to this goal).")


if __name__ == "__main__":
    main()
