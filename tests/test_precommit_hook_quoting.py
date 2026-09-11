"""The pre-commit hook must not command-substitute inside its own messages.

MEASURED 2026-09-09. Line 616 wrote a guidance message as:

    echo "  ^ not blocking. A cycle report is `calibration-discipline` item 7, and the" >&2

Inside a DOUBLE-quoted string, backticks are command substitution, so the shell ran
`calibration-discipline` as a command. Every commit that tripped the cycle-report warning printed

    .githooks/pre-commit: line 616: calibration-discipline: command not found
      ^ not blocking. A cycle report is  item 7, and the

The guidance lost the noun it was about and gained an error line that looks like the hook itself is
broken -- which is how a real message gets read as noise and tuned out. Seven sibling lines in the
same file escape their backticks correctly, so this was one slip rather than a convention.

The test is a lint over the hook's own text: no UNESCAPED backtick inside a double-quoted `echo`.
It is deliberately not a "the hook runs" test -- the hook ran fine, and printed nonsense.
"""
from __future__ import annotations

import pathlib
import re

import pytest

HOOK = pathlib.Path(__file__).resolve().parent.parent / ".githooks" / "pre-commit"

#: an echo of a double-quoted string; we then look for a backtick not preceded by a backslash
_ECHO = re.compile(r'echo\s+"((?:[^"\\]|\\.)*)"')


def _offending_lines(text: str):
    out = []
    for n, line in enumerate(text.splitlines(), 1):
        for m in _ECHO.finditer(line):
            body = m.group(1)
            if re.search(r'(?<!\\)`', body):
                out.append((n, line.strip()))
    return out


def test_hook_exists():
    assert HOOK.is_file(), f"{HOOK} missing -- this repo's hooks are per-clone (core.hooksPath)"


def test_no_unescaped_backtick_in_a_double_quoted_echo():
    bad = _offending_lines(HOOK.read_text())
    assert not bad, (
        "unescaped backtick inside a double-quoted echo -- the shell will run it as a command and "
        "the message loses that word:\n"
        + "\n".join(f"  line {n}: {s}" for n, s in bad))


def test_the_lint_actually_catches_the_measured_defect():
    """MUTATION GUARD. A regex that matches nothing passes silently on every input, which is the
    failure mode this whole file exists to prevent one level up. Feed it the exact line that
    shipped and require a hit."""
    shipped = 'echo "  ^ not blocking. A cycle report is `calibration-discipline` item 7." >&2'
    assert _offending_lines(shipped), "the lint does not catch the line that actually shipped"


def test_the_lint_accepts_the_escaped_form_its_siblings_use():
    ok = r'echo "pre-commit: log does not match the \`log\` skill contract -- see above." >&2'
    assert not _offending_lines(ok), "the lint rejects the correct escaped form"


@pytest.mark.parametrize("line", [
    'echo "no backticks at all" >&2',
    "echo 'single quotes make `this` literal' >&2",
])
def test_the_lint_does_not_fire_on_safe_lines(line):
    assert not _offending_lines(line)
