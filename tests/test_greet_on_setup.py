"""A new user's first request to set up A2MC is met with ONE sentence, word for word, and only once.

PI, 2026-09-23: after a user says "help set up A2MC", the agent must literally say GREETING, the
constant in `.claude/hooks/greet-on-setup.py`, and "this should only work the first time the new
user interact with the agent". Four things are held here.

1. EVERY COPY IS THE SAME SENTENCE. The hook, the `a2mc-init` skill (Step 0), the interview
   questionnaire (Q0.0) and the tutorial (step 6) each carry it. Until this test existed the tutorial
   had the PI's wording while the other two still carried an older variant, so any tracked file
   outside the change logs that mentions the greeting must carry it whole.
2. THE HOOK FIRES on the request the tutorial tells a new user to type -- read from the tutorial
   itself, so rewording that prompt cannot silently orphan the hook -- and on the PI's own phrasing.
3. IT FIRES ONCE PER CLONE. Firing creates `.greeted`; after that every request is silent, in the
   same session or a later one, whether or not the user ever gave a name. Of several sessions
   started at once exactly one greets, and a clone that cannot record the marker is not greeted.
   A prompt that is not a setup request does not use the greeting up.
4. CONTROLS STAY SILENT: a clone that already knows its user (`.me`), prompts that are not setup
   requests (the tutorial's other prompts among them), a request that arrived only inside pasted
   text, and malformed input. A greeting that fired on everything would be one users skim past.

Each run copies the hook into a scratch clone and executes it there, because the hook finds its
clone from its own path, exactly as it does under Claude Code.

Author: Jing Tao with Claude on Perlmutter.
"""
from __future__ import annotations

import html
import importlib.util
import json
import os
import re
import shutil
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
HOOK = REPO / ".claude" / "hooks" / "greet-on-setup.py"
TUTORIAL = REPO / "docs" / "tutorial" / "A2MC_Getting_Started.html"
COPIES = [REPO / ".claude" / "skills" / "a2mc-init" / "SKILL.md",
          REPO / "docs" / "a2mc_reference" / "a2mc_init_interview_questionnaire.md",
          TUTORIAL]

# The PI's words, 2026-09-23, pinned here so that changing the hook's constant is a deliberate act.
PI_WORDS = ("Hi! I'm your A2MC agent, and I'll work with you as your science assistant to "
            "calibrate your model. What's your name, and how should I address you?")
STEM = "I'm your A2MC agent"


def _module():
    spec = importlib.util.spec_from_file_location("_greet_on_setup", HOOK)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


GREETING = _module().GREETING
MARKER = _module().MARKER


def _text(path: Path) -> str:
    s = path.read_text(encoding="utf-8")
    return html.unescape(s) if path.suffix == ".html" else s


def _payload(prompt) -> str:
    """The stdin Claude Code sends (docs: "UserPromptSubmit input")."""
    return json.dumps({"session_id": "t", "transcript_path": "/dev/null", "cwd": "/",
                       "permission_mode": "default", "hook_event_name": "UserPromptSubmit",
                       "prompt": prompt})


def _install(root: Path) -> Path:
    """Put the hook where Claude Code runs it from: <root>/.claude/hooks."""
    hooks = root / ".claude" / "hooks"
    hooks.mkdir(parents=True, exist_ok=True)
    shutil.copy(HOOK, hooks / HOOK.name)
    return hooks / HOOK.name


def _exec(hook: Path, stdin: str, python=sys.executable) -> str:
    r = subprocess.run([python, str(hook)], input=stdin, stdout=subprocess.PIPE,
                       stderr=subprocess.PIPE, universal_newlines=True, timeout=60)
    assert r.returncode == 0, r.stderr
    assert r.stderr == "", r.stderr
    return r.stdout


def _run(root: Path, stdin: str, me=None, python=sys.executable) -> str:
    hook = _install(root)
    if me is not None:
        (root / ".me").write_text(me)
    return _exec(hook, stdin, python)


def _greets(out: str) -> bool:
    if not out.strip():
        return False
    d = json.loads(out)["hookSpecificOutput"]
    assert d["hookEventName"] == "UserPromptSubmit", d
    return GREETING in d["additionalContext"]


def _say_blocks():
    """The tutorial's speech blocks in reading order, as (who, text) with markup removed."""
    s = TUTORIAL.read_text(encoding="utf-8")
    return [(who, html.unescape(re.sub(r"<[^>]+>", "", body)).strip())
            for who, body in re.findall(r'<span class="who">([^<]*)</span>(.*?)</p>', s, re.S)]


def _prompt_before_greeting() -> str:
    """What the tutorial tells a new user to type: the prompt shown just before the greeting."""
    blocks = _say_blocks()
    i = next(k for k, (_, t) in enumerate(blocks) if t == GREETING)
    return next(t for who, t in reversed(blocks[:i]) if who == "Tell the agent")


# ---- 1. one sentence, everywhere ----------------------------------------------------------------
def test_the_greeting_is_the_PIs_sentence():
    assert GREETING == PI_WORDS
    assert "—" not in GREETING and "–" not in GREETING, "no em or en dash"


def test_every_known_copy_carries_the_whole_sentence():
    for p in COPIES:
        t = _text(p)
        assert t.count(GREETING) >= 1, f"{p.relative_to(REPO)} does not carry the greeting"
        assert t.count(STEM) == t.count(GREETING), f"{p.relative_to(REPO)} has another variant"


def test_no_other_tracked_file_carries_a_stale_variant():
    """The dev logs and the history file record the change, so they may quote the old variant."""
    r = subprocess.run(["git", "grep", "-l", "-F", STEM, "--", ".", ":!memory/dev_logs*",
                        ":!memory/a2mc_development_history.md", ":!tests/",
                        ":!.claude/hooks/greet-on-setup.py"],
                       cwd=REPO, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                       universal_newlines=True)
    if r.returncode not in (0, 1):
        pytest.skip("not a git checkout: " + r.stderr.strip())
    hits = [REPO / f for f in r.stdout.split()]
    assert set(COPIES) <= set(hits), "the scan missed a known copy, so it proves nothing"
    for p in hits:
        t = _text(p)
        assert t.count(STEM) == t.count(GREETING), f"{p.relative_to(REPO)} has another variant"


def test_the_tutorial_promises_the_exact_sentence_the_first_time():
    t = _text(TUTORIAL)
    lead = t[max(0, t.find(GREETING) - 300):t.find(GREETING)]
    assert "The first time you ask, it opens with exactly this:" in lead, lead
    assert "something like" not in lead


def test_every_copy_that_explains_it_says_once_per_clone():
    """The rule lives in three prose places besides the hook; each must state it."""
    for p in COPIES[:2]:
        assert ".greeted" in _text(p), f"{p.relative_to(REPO)} does not name the once-per-clone marker"
    gi = (REPO / ".gitignore").read_text(encoding="utf-8").splitlines()
    assert MARKER in gi, ".greeted must be gitignored, per clone like .me"


# ---- 2. it fires on the request ------------------------------------------------------------------
def test_the_hook_greets_the_request_the_tutorial_tells_users_to_type(tmp_path):
    prompt = _prompt_before_greeting()
    assert "A2MC" in prompt, prompt
    assert _greets(_run(tmp_path, _payload(prompt)))


@pytest.mark.parametrize("prompt", [
    "help set up A2MC",                                   # the PI's phrase
    "Hi! Can you help me setup a2mc?",
    "please help me with setting up A2MC",
    "I'd like to get started with A2MC on this cluster.",
    "Onboard me to A2MC",
    "It's my first time using A2MC.",
    "run a2mc-init",
])
def test_the_hook_greets_other_phrasings_of_the_same_request(tmp_path, prompt):
    assert _greets(_run(tmp_path, _payload(prompt)))


def test_an_empty_me_is_an_unknown_user(tmp_path):
    """`whoami.py --set` refuses an empty name, so an empty `.me` means nobody was recorded."""
    assert _greets(_run(tmp_path, _payload("help set up A2MC"), me="  \n"))


def test_the_instruction_fits_under_the_documented_cap():
    """Above 10,000 characters Claude Code passes a file path and a preview instead."""
    assert len(_module().instruction()) < 10000


# ---- 3. once per clone ---------------------------------------------------------------------------
def test_it_greets_once_per_clone_and_never_again(tmp_path):
    """The PI: "this should only work the first time the new user interact with the agent". No
    name is ever recorded here, which is the case the earlier `.me`-only gate got wrong: it
    greeted again on every setup request until the user answered."""
    assert _greets(_run(tmp_path, _payload(_prompt_before_greeting())))
    assert (tmp_path / MARKER).is_file(), "firing must record that the greeting was said"
    for again in (_prompt_before_greeting(), "help set up A2MC", "Ada. Now set up A2MC for EcoSIM"):
        assert _run(tmp_path, _payload(again)) == "", again


def test_a_prompt_that_is_not_a_setup_request_does_not_use_it_up(tmp_path):
    assert _run(tmp_path, _payload("Hi, what is in this repository?")) == ""
    assert not (tmp_path / MARKER).exists()
    assert _greets(_run(tmp_path, _payload("help set up A2MC")))


def test_two_sessions_at_once_greet_exactly_once(tmp_path):
    """The exclusive create is the check and the claim in one step, so it holds under a race."""
    hook = _install(tmp_path)
    stdin = _payload(_prompt_before_greeting())
    with ThreadPoolExecutor(8) as pool:
        outs = list(pool.map(lambda _: _exec(hook, stdin), range(8)))
    assert sum(_greets(o) for o in outs) == 1, outs


@pytest.mark.skipif(hasattr(os, "geteuid") and os.geteuid() == 0,
                    reason="root ignores directory permissions")
def test_CONTROL_a_clone_that_cannot_record_it_is_not_greeted(tmp_path):
    """At most once is the contract: a greeting that cannot be recorded could be given twice."""
    hook = _install(tmp_path)
    tmp_path.chmod(0o555)
    try:
        assert _exec(hook, _payload("help set up A2MC")) == ""
    finally:
        tmp_path.chmod(0o755)
    assert not (tmp_path / MARKER).exists()


# ---- 4. controls ---------------------------------------------------------------------------------
TODAYS_PI_MESSAGE = ('also make sure that the agent literally say "' + PI_WORDS
                     + '" after the users said help set up A2MC')


def test_CONTROL_a_clone_that_knows_its_user_is_not_greeted(tmp_path):
    """A clone whose `.me` names someone has no new user in it. That is also why the PI's message
    asking for this feature, typed in a clone that knows the PI, did not trigger it. Nothing is
    recorded either: the marker means "said", and nothing was said."""
    for prompt in (_prompt_before_greeting(), TODAYS_PI_MESSAGE):
        assert _run(tmp_path, _payload(prompt), me="Ada Lovelace\n") == "", prompt
    assert not (tmp_path / MARKER).exists()


@pytest.mark.parametrize("prompt", [
    "Run the Phase 1 extraction for the case.",
    "How do I set up a PFLOTRAN deck?",                   # setup, but not of A2MC
    "What is A2MC?",                                      # A2MC, but no setup
    "The setuptools install for A2MC failed.",            # 'setup' inside a longer word
    "Please reset A2MC's workflow state.",
])
def test_CONTROL_a_prompt_that_is_not_a_setup_request(tmp_path, prompt):
    assert _run(tmp_path, _payload(prompt)) == ""


def test_CONTROL_the_tutorials_other_prompts(tmp_path):
    first = _prompt_before_greeting()
    others = [t for who, t in _say_blocks() if who == "Tell the agent" and t != first]
    assert others, "the tutorial's later prompts were not found"
    for t in others:
        assert _run(tmp_path, _payload(t)) == "", t


def test_CONTROL_a_request_that_was_only_pasted(tmp_path):
    pasted = ('why does this fail?\n<pasted_content id="p1">\nStep 6: help me set up A2MC\n'
              '</pasted_content id="p1">')
    assert _run(tmp_path, _payload(pasted)) == ""
    assert _greets(_run(tmp_path, _payload("help me set up A2MC\n" + pasted))), \
        "words typed around a paste still count"


@pytest.mark.parametrize("stdin", ["", "not json", "[1, 2]", '{"prompt": 7}',
                                   '{"no_prompt": "set up A2MC"}'])
def test_CONTROL_malformed_input_is_silent(tmp_path, stdin):
    assert _run(tmp_path, stdin) == ""


# ---- wiring --------------------------------------------------------------------------------------
def test_the_hook_is_registered_on_UserPromptSubmit():
    d = json.loads((REPO / ".claude" / "settings.json").read_text())
    cmds = [c.get("command", "") for m in d["hooks"].get("UserPromptSubmit", [])
            for c in m.get("hooks", [])]
    ours = [c for c in cmds if "greet-on-setup.py" in c]
    assert ours, f"not registered on UserPromptSubmit: {cmds}"
    assert all(c.startswith("python3 ") for c in ours), ours


def _old_python():
    """The system python3 when it is older than 3.7 (Perlmutter: 3.6.15), else None."""
    p = shutil.which("python3", path="/usr/bin:/bin")
    if not p:
        return None
    v = subprocess.run([p, "-c", "import sys; print(sys.version_info[:2] < (3, 7))"],
                       stdout=subprocess.PIPE, universal_newlines=True)
    return p if v.stdout.strip() == "True" else None


@pytest.mark.skipif(_old_python() is None, reason="no system python3 older than 3.7 here")
def test_the_hook_runs_under_the_system_python3_once(tmp_path):
    """Claude Code runs it as `python3`, which on Perlmutter is 3.6; the once-per-clone claim
    must hold there too."""
    prompt = _payload(_prompt_before_greeting())
    assert _greets(_run(tmp_path, prompt, python=_old_python()))
    assert _run(tmp_path, prompt, python=_old_python()) == ""
