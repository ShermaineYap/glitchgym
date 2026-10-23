"""The AI side of GlitchGym: diagnose errors, inject verified bugs, coach.

Design rule: the model proposes, the sandbox disposes. Nothing the model writes
(a mutant, a test, a fix) reaches the student until it has been executed and
checked. That is what stops a confident-but-wrong LLM from teaching nonsense.
"""

from __future__ import annotations

import ast
import difflib
import json
import random
from dataclasses import dataclass, field

from . import llm
from .catalog import CATEGORIES, CATEGORY_IDS, SNIPPETS_BY_ID, offline_bugs_for
from .sandbox import RunReport, run_script, run_tests, syntax_error

CATEGORY_LIST = "\n".join(f"- {k}: {v['name']} ({v['blurb']})" for k, v in CATEGORIES.items())

# --------------------------------------------------------------------------- #
# Diagnose
# --------------------------------------------------------------------------- #

DIAGNOSE_SYSTEM = f"""You are GlitchGym, a patient debugging tutor for university students.
A student gives you Python code and the error or wrong behaviour they saw.
Explain WHY it broke, not just how to fix it. Write for a first- or second-year student:
plain English, short sentences, no jargon without a one-line explanation.

Return ONLY a JSON object with these keys:
{{
  "error_type": "e.g. IndexError, or 'Wrong output' if there is no exception",
  "plain_english": "1-2 sentences: what the error message literally means",
  "root_cause": "2-4 sentences: the underlying reason in THIS code, pointing at the exact line",
  "line": <integer line number in the student's code where the cause is, or null>,
  "walkthrough": ["3-5 short steps tracing what Python did, ending at the failure"],
  "fix_code": "the full corrected code, minimal change from the original",
  "why_fix_works": "1-2 sentences",
  "mental_model": "one memorable rule of thumb that prevents this whole class of bug",
  "category": "one id from the list below that best matches the bug",
  "quick_check": {{
     "question": "a one-line multiple-choice question testing the same concept on NEW code",
     "options": ["A", "B", "C"],
     "answer_index": 0,
     "why": "one sentence"
  }}
}}

Bug category ids:
{CATEGORY_LIST}
If none fits well, pick the closest."""


_OFFLINE_DIAG = {
    "IndexError": ("off_by_one",
                   "You asked a list (or string) for a position that doesn't exist.",
                   "An index went past the end (or before the start) of a sequence. Check loop ranges and any `i + 1` / `i - 1` lookups."),
    "KeyError": ("dict_key",
                 "You looked up a dictionary key that was never added.",
                 "The key isn't in the dictionary at that moment. Use `dict.get(key, default)` or check `if key in d` first."),
    "TypeError": ("type_mixup",
                  "An operation got a value of a type it can't handle (e.g. adding a str to an int, or calling None).",
                  "A value has a different type than you assumed. Print `type(x)` just before the failing line."),
    "UnboundLocalError": ("scope",
                          "A variable was used before it was given a value in this function.",
                          "The variable is only assigned inside a branch or loop that didn't run. Initialise it before the loop."),
    "NameError": ("scope",
                  "Python doesn't know a name you used, usually a typo or a variable defined elsewhere.",
                  "Check spelling and make sure the variable is defined before, and in the same scope as, where it's used."),
    "AttributeError": ("type_mixup",
                       "You used a method or attribute that this kind of object doesn't have.",
                       "The object isn't the type you think, often None returned by a function that forgot to `return`."),
    "ZeroDivisionError": ("boundary_compare",
                          "You divided by zero.",
                          "An edge case (empty list, zero count) reached a division. Guard it with an if before dividing."),
    "ValueError": ("type_mixup",
                   "A function got the right type but an unusable value, e.g. int('abc').",
                   "Check the exact string being converted; strip whitespace and handle empty input."),
    "RecursionError": ("missing_return",
                       "A function kept calling itself and never stopped.",
                       "The base case is missing, unreachable or never returned."),
    "SyntaxError": ("logic",
                    "Python couldn't even read the code: something is mistyped.",
                    "Look at the reported line and the one just before it for missing colons, brackets or quotes."),
    "IndentationError": ("logic",
                         "The indentation doesn't match the structure Python expects.",
                         "Use 4 spaces consistently and make sure every block after a colon is indented."),
    "TimeoutError": ("off_by_one",
                     "The program never finished: almost certainly an infinite loop.",
                     "A loop condition never becomes false. Check that the loop variable actually changes each pass."),
}


def _error_name(error_text: str) -> str:
    for line in reversed(error_text.strip().splitlines()):
        head = line.split(":", 1)[0].strip()
        if head.endswith(("Error", "Exception")) or head == "AssertionError":
            return head.split(".")[-1]
    return "Wrong output"


def _offline_diagnosis(code: str, error_text: str) -> dict:
    name = _error_name(error_text)
    cat, plain, cause = _OFFLINE_DIAG.get(
        name, ("logic", "The program didn't behave as expected.",
               "Compare what you expected with what you got, then trace the values line by line."))
    line = None
    for ln in error_text.splitlines():
        if "line " in ln:
            try:
                line = int(ln.rsplit("line ", 1)[1].split(",")[0].split(")")[0])
            except ValueError:
                pass
    return {
        "error_type": name,
        "plain_english": plain,
        "root_cause": cause,
        "line": line,
        "walkthrough": ["Find the last line of the traceback: that's the error type and message.",
                        "Go up to the last frame that points at your own file: that's where it surfaced.",
                        "Print the variables used on that line just before it runs.",
                        "Ask: is any value empty, None, the wrong type, or one step too far?"],
        "fix_code": "",
        "why_fix_works": "",
        "mental_model": CATEGORIES[cat]["blurb"],
        "category": cat,
        "quick_check": None,
        "_offline": True,
    }


def diagnose(code: str, error_text: str = "", expected: str = "") -> dict:
    """Explain an error. If no error text is given, run the code to capture one."""
    ran = None
    if not error_text.strip():
        stx = syntax_error(code)
        if stx:
            error_text = stx
        else:
            out, err, timed_out = run_script(code)
            ran = {"stdout": out, "stderr": err}
            error_text = err if err else ""
            if not error_text and not expected:
                return {"no_error": True, "stdout": out}
    if not llm.any_available():
        result = _offline_diagnosis(code, error_text or "Wrong output")
        result["provider"] = "Offline rules (no API key set)"
        result["captured_error"] = error_text
        return result

    user = (f"Student code:\n```python\n{_number(code)}\n```\n\n"
            f"Error / behaviour they saw:\n```\n{error_text or '(no exception)'}\n```\n")
    if ran and ran.get("stdout"):
        user += f"\nProgram output when run:\n```\n{ran['stdout'][-1500:]}\n```\n"
    if expected:
        user += f"\nWhat they expected instead: {expected}\n"
    user += "\n(Line numbers are prefixed for reference only; do NOT include them in fix_code.)"
    try:
        result, provider = llm.ask_json(DIAGNOSE_SYSTEM, user, temperature=0.2)
    except llm.LLMError as e:
        result = _offline_diagnosis(code, error_text or "Wrong output")
        result["provider"] = f"Offline rules (AI unavailable: {str(e)[:120]})"
        result["captured_error"] = error_text
        return result

    result["provider"] = provider
    result["captured_error"] = error_text
    if result.get("category") not in CATEGORIES:
        result["category"] = "logic"
    # Ground the suggested fix: does it at least run cleanly now?
    fix = (result.get("fix_code") or "").strip()
    if fix:
        fix = _strip_line_numbers(fix)
        result["fix_code"] = fix
        stx = syntax_error(fix)
        if stx:
            result["fix_check"] = ("fail", f"Suggested fix has a {stx}; treat it with care.")
        else:
            out, err, timed_out = run_script(fix)
            if timed_out:
                result["fix_check"] = ("fail", "Suggested fix timed out when run.")
            elif err and _error_name(err) == _error_name(error_text or "x"):
                result["fix_check"] = ("fail", "Suggested fix still raises the same error when run.")
            elif err:
                result["fix_check"] = ("warn", f"Fix runs but raises: {err.splitlines()[-1][:160]}")
            else:
                result["fix_check"] = ("pass", "Verified: the suggested fix runs without errors in the sandbox.")
    return result


def _number(code: str) -> str:
    return "\n".join(f"{i:>3}| {line}" for i, line in enumerate(code.splitlines(), 1))


def _strip_line_numbers(code: str) -> str:
    lines = code.splitlines()
    if lines and all(len(l) > 4 and l[:3].strip().isdigit() and l[3] == "|" for l in lines if l.strip()):
        return "\n".join(l[5:] if len(l) > 4 else "" for l in lines)
    return code


# --------------------------------------------------------------------------- #
# Gym: inject a verified bug
# --------------------------------------------------------------------------- #

MUTATE_SYSTEM = f"""You are the bug-injection engine of GlitchGym, a debugging gym for students.
You receive WORKING Python code, its test cases, and a target bug category.
Inject exactly ONE realistic bug of that category - the kind a real student would write.

Hard rules:
- Change as little as possible: 1-3 lines. Keep every function name and signature callable the same way.
- The bug MUST make at least one of the given tests fail (wrong value or an exception).
- No infinite loops, no input(), no imports, no file or network access.
- Do NOT add comments that reveal the bug. Do not rename things to hint at it.
- The bug should be findable by a second-year student in under 5 minutes.

Return ONLY JSON:
{{
  "mutated_code": "the full code with the bug",
  "bug_line": <line number of the main change>,
  "hints": ["hint 1: where to look, a question not an answer",
            "hint 2: what to inspect or trace",
            "hint 3: nearly gives the fix"],
  "explanation": "3-4 sentences for AFTER they solve it: why this bug happens in general and a rule of thumb to avoid it"
}}

Categories:
{CATEGORY_LIST}"""

TESTGEN_SYSTEM = """You write unit tests for student Python code.
Return ONLY JSON: {"tests": ["assert f(...) == ...", ...]}
Rules: 4-6 tests, each ONE line of Python (use ';' if you need setup), each normally an assert.
Cover normal cases AND edge cases (empty input, zero, boundary values, repeated calls).
Only call functions that exist in the code. No imports, no printing, no randomness.
The tests must PASS on the code as given: describe what it currently does."""

NUDGE_SYSTEM = """You are a Socratic debugging coach. The student is fixing a bug that was injected
on purpose. You can see the original working code, the buggy version, the student's current
attempt and the test results. Give ONE short nudge (max 2 sentences) that moves them forward
from where THEY are now. Never paste the corrected line or the fix. Prefer a question.
If their attempt introduced a new problem, point that out gently.
Return ONLY JSON: {"nudge": "...", "on_track": true|false}"""


@dataclass
class Challenge:
    category: str
    original_code: str
    mutated_code: str
    tests: list[str]
    hints: list[str]
    explanation: str
    source: str
    snippet_id: str | None = None
    title: str = ""
    description: str = ""
    bug_line: int | None = None
    verification_log: list[str] = field(default_factory=list)
    baseline: RunReport | None = None

    def to_dict(self) -> dict:
        d = self.__dict__.copy()
        d.pop("baseline", None)
        return d


def _changed_lines(a: str, b: str) -> int:
    diff = difflib.unified_diff(a.strip().splitlines(), b.strip().splitlines(), lineterm="", n=0)
    return sum(1 for l in diff if l[:1] in "+-" and not l.startswith(("+++", "---")))


def _func_names(code: str) -> set[str]:
    try:
        return {n.name for n in ast.walk(ast.parse(code)) if isinstance(n, ast.FunctionDef)}
    except SyntaxError:
        return set()


def verify_mutant(original: str, mutant: str, tests: list[str]) -> tuple[bool, str, RunReport | None]:
    """Accept a mutant only if it is a small, valid, test-failing change."""
    if not mutant or mutant.strip() == original.strip():
        return False, "mutant identical to original", None
    stx = syntax_error(mutant)
    if stx:
        return False, f"mutant does not parse ({stx})", None
    if not _func_names(original) <= _func_names(mutant):
        return False, "mutant renamed or removed a function", None
    changed = _changed_lines(original, mutant)
    if changed > 8:  # 8 diff lines ~ 4 edited lines
        return False, f"too many lines changed ({changed} diff lines)", None
    report = run_tests(mutant, tests)
    if report.timed_out:
        return False, "mutant hangs (infinite loop)", report
    if report.load_error:
        return False, "mutant crashes on load", report
    if report.failed == 0:
        return False, "mutant still passes every test (bug not caught)", report
    return True, f"fails {report.failed}/{len(report.results)} tests, {changed // 2 or 1} line(s) changed", report


def generate_tests(code: str) -> tuple[list[str], list[str]]:
    """Ask the model for tests, keep only those the original code passes."""
    log: list[str] = []
    data, provider = llm.ask_json(TESTGEN_SYSTEM, f"```python\n{code}\n```", temperature=0.2)
    tests = [t for t in data.get("tests", []) if isinstance(t, str) and t.strip()]
    report = run_tests(code, tests)
    if report.load_error:
        raise ValueError("Your code doesn't run yet, so it can't be used as a gym workout:\n" + report.load_error)
    kept = [r.test for r in report.results if r.passed]
    dropped = len(tests) - len(kept)
    log.append(f"{provider} wrote {len(tests)} tests; kept {len(kept)} that your working code passes"
               + (f", dropped {dropped} that didn't" if dropped else ""))
    if len(kept) < 2:
        raise ValueError("Couldn't build enough reliable tests for this code. Try code that defines a function.")
    return kept, log


def make_challenge(category: str, snippet_id: str | None = None, custom_code: str | None = None,
                   custom_tests: list[str] | None = None, max_tries: int = 3) -> Challenge:
    """Create a verified bug-hunt. Uses the AI when available, else the offline bank."""
    log: list[str] = []
    if custom_code:
        original = custom_code.strip() + "\n"
        title, description = "Your own code", "Code you pasted in."
        if custom_tests:
            tests = custom_tests
        else:
            if not llm.any_available():
                raise ValueError("Custom code needs an API key so the AI can write tests for it.")
            tests, tlog = generate_tests(original)
            log += tlog
    else:
        snip = SNIPPETS_BY_ID[snippet_id]
        original, tests, title, description = snip.code, snip.tests, snip.title, snip.description

    baseline = run_tests(original, tests)
    if not baseline.ok:
        raise ValueError("The starting code must pass all its tests first. " + baseline.summary())

    if llm.any_available():
        feedback = ""
        for attempt in range(1, max_tries + 1):
            user = (f"Target bug category: {category} ({CATEGORIES[category]['name']})\n\n"
                    f"Working code:\n```python\n{original}\n```\n\nTests (all currently pass):\n"
                    + "\n".join(tests) + feedback)
            try:
                data, provider = llm.ask_json(MUTATE_SYSTEM, user, temperature=0.8)
            except llm.LLMError as e:
                log.append(f"AI call failed: {str(e)[:120]}")
                break
            mutant = _strip_line_numbers(str(data.get("mutated_code", ""))).rstrip() + "\n"
            ok, why, _ = verify_mutant(original, mutant, tests)
            log.append(f"Attempt {attempt} ({provider}): {'ACCEPTED' if ok else 'rejected'} - {why}")
            if ok:
                hints = [str(h) for h in data.get("hints", [])][:3]
                while len(hints) < 3:
                    hints.append("Run the failing test in your head, line by line, and write down each variable.")
                return Challenge(category, original, mutant, tests, hints,
                                 str(data.get("explanation", "")), provider, snippet_id,
                                 title, description, data.get("bug_line"), log, baseline)
            feedback = (f"\n\nYour previous attempt was rejected by the test runner: {why}. "
                        "Try a different, still-realistic bug of the same category.")

    # Offline fallback (only possible for seed snippets)
    if custom_code:
        raise ValueError("The AI couldn't produce a verified bug for this code. " + " | ".join(log))
    pool = offline_bugs_for(snippet_id, category) or offline_bugs_for(snippet_id)
    bug = random.choice(pool)
    ok, why, _ = verify_mutant(original, bug.mutated_code, tests)
    log.append(f"Offline bug bank: {why}")
    return Challenge(bug.category, original, bug.mutated_code, tests, bug.hints, bug.explanation,
                     "Offline bug bank (pre-verified)", snippet_id, title, description, None, log, baseline)


def pick_snippet_for(category: str) -> str:
    """Pick a seed snippet that suits a category (offline bank knows which fit)."""
    fits = [b.snippet_id for b in offline_bugs_for(category=category)]
    if fits:
        return random.choice(fits)
    return random.choice(list(SNIPPETS_BY_ID))


# --------------------------------------------------------------------------- #
# Coaching while they work
# --------------------------------------------------------------------------- #

def nudge(ch: Challenge, attempt_code: str, report: RunReport, hints_used: int) -> tuple[str, str]:
    """A live, personalised Socratic nudge. Falls back to the next static hint."""
    fallback = ch.hints[min(hints_used, len(ch.hints) - 1)]
    if not llm.any_available():
        return fallback, "static hint"
    results = "\n".join(f"{'PASS' if r.passed else 'FAIL'}: {r.test}" + (f"  -> {r.error}" if r.error else "")
                        for r in report.results) or (report.load_error or report.summary())
    user = (f"Original (correct) code:\n```python\n{ch.original_code}\n```\n"
            f"Buggy version given to student:\n```python\n{ch.mutated_code}\n```\n"
            f"Bug category: {CATEGORIES[ch.category]['name']}\n"
            f"Student's current attempt:\n```python\n{attempt_code}\n```\n"
            f"Test results of their attempt:\n{results}\n")
    try:
        data, provider = llm.ask_json(NUDGE_SYSTEM, user, temperature=0.5, timeout=30)
        text = str(data.get("nudge", "")).strip()
        return (text or fallback), provider
    except llm.LLMError:
        return fallback, "static hint"


def score_attempt(hints_used: int, nudges_used: int, checks: int, solved: bool, gave_up: bool) -> int:
    """0-100 mastery points for one drill."""
    if gave_up or not solved:
        return 0
    s = 100 - 20 * hints_used - 10 * nudges_used - 5 * max(0, checks - 1)
    return max(10, min(100, s))
