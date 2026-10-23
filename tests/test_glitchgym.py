"""Tests for the sandbox, the bug bank and the verify-and-retry loop.

The LLM is mocked, so these run offline and deterministically.
"""

import pytest

from glitchgym import coach, llm, progress
from glitchgym.catalog import CATEGORIES, OFFLINE_BUGS, SNIPPETS, SNIPPETS_BY_ID
from glitchgym.sandbox import run_script, run_tests


# ---------------------------------------------------------------- sandbox
def test_passing_code():
    r = run_tests("def f(x):\n    return x * 2\n", ["assert f(2) == 4", "assert f(0) == 0"])
    assert r.ok and r.passed == 2


def test_failure_reports_actual_value_without_rerunning():
    code = "calls = []\ndef f(x):\n    calls.append(x)\n    return len(calls)\n"
    r = run_tests(code, ["assert f(1) == 99"])
    assert not r.ok
    assert r.results[0].error == "AssertionError: got 1"  # evaluated once, not twice


def test_runtime_error_points_at_student_line():
    r = run_tests("def f(xs):\n    return xs[10]\n", ["assert f([1]) == 1"])
    assert "IndexError" in r.results[0].error and "line 2" in r.results[0].error


def test_syntax_error_is_load_error():
    r = run_tests("def f(:\n  pass", ["assert True"])
    assert r.load_error and "SyntaxError" in r.load_error


def test_infinite_loop_times_out():
    r = run_tests("def f():\n    while True:\n        pass\n", ["f()"], timeout=1.5)
    assert r.timed_out and not r.ok


def test_run_script_captures_traceback():
    out, err, timed_out = run_script("print('hi')\n1/0\n")
    assert "hi" in out and "ZeroDivisionError" in err and not timed_out


# ---------------------------------------------------------------- catalog
@pytest.mark.parametrize("snip", SNIPPETS, ids=lambda s: s.id)
def test_every_snippet_passes_its_tests(snip):
    assert run_tests(snip.code, snip.tests).ok


@pytest.mark.parametrize("bug", OFFLINE_BUGS, ids=lambda b: f"{b.snippet_id}-{b.category}")
def test_every_offline_bug_is_valid(bug):
    snip = SNIPPETS_BY_ID[bug.snippet_id]
    ok, why, _ = coach.verify_mutant(snip.code, bug.mutated_code, snip.tests)
    assert ok, why
    assert bug.category in CATEGORIES and len(bug.hints) == 3


def test_every_category_has_an_offline_bug():
    assert {b.category for b in OFFLINE_BUGS} == set(CATEGORIES)


# ---------------------------------------------------------------- verifier
SNIP = SNIPPETS_BY_ID["sum_evens"]


def test_verifier_rejects_mutant_that_still_passes():
    same_behaviour = SNIP.code.replace("total += n", "total = total + n")
    ok, why, _ = coach.verify_mutant(SNIP.code, same_behaviour, SNIP.tests)
    assert not ok and "passes every test" in why


def test_verifier_rejects_renamed_function():
    ok, why, _ = coach.verify_mutant(SNIP.code, SNIP.code.replace("sum_evens", "add_evens"), SNIP.tests)
    assert not ok and "renamed" in why


def test_verifier_rejects_unparseable():
    ok, why, _ = coach.verify_mutant(SNIP.code, "def sum_evens(nums)\n    return 0\n", SNIP.tests)
    assert not ok and "parse" in why


def test_verifier_rejects_hang():
    hang = "def sum_evens(nums):\n    total = 0\n    while True:\n        pass\n    return total\n"
    ok, why, _ = coach.verify_mutant(SNIP.code, hang, SNIP.tests)
    assert not ok and "hang" in why


# ---------------------------------------------------------------- AI loop (mocked)
def _mock_llm(monkeypatch, replies):
    calls = []

    def fake(system, user, temperature=0.4, timeout=45):
        calls.append(user)
        return replies[len(calls) - 1], "MockModel"

    monkeypatch.setattr(llm, "any_available", lambda: True)
    monkeypatch.setattr(llm, "ask_json", fake)
    return calls


def test_retry_until_a_mutant_verifies(monkeypatch):
    bad = {"mutated_code": SNIP.code.replace("total += n", "total = total + n"), "hints": ["a", "b", "c"],
           "explanation": "x"}
    good = {"mutated_code": SNIP.code.replace("n % 2 == 0", "n % 2 == 1"), "hints": ["h1", "h2", "h3"],
            "explanation": "parity flipped"}
    calls = _mock_llm(monkeypatch, [bad, good])
    ch = coach.make_challenge("logic", snippet_id="sum_evens")
    assert ch.source == "MockModel" and "n % 2 == 1" in ch.mutated_code
    assert "rejected" in ch.verification_log[0] and "ACCEPTED" in ch.verification_log[1]
    assert "rejected by the test runner" in calls[1]  # feedback sent back to the model


def test_falls_back_to_offline_bank_after_three_failures(monkeypatch):
    bad = {"mutated_code": SNIP.code, "hints": [], "explanation": ""}
    _mock_llm(monkeypatch, [bad, bad, bad])
    ch = coach.make_challenge("scope", snippet_id="sum_evens")
    assert ch.source.startswith("Offline")
    assert run_tests(ch.mutated_code, ch.tests).failed > 0


def test_custom_code_keeps_only_tests_the_original_passes(monkeypatch):
    code = "def double(x):\n    return x * 2\n"
    tests = {"tests": ["assert double(2) == 4", "assert double(3) == 7", "assert double(0) == 0"]}
    mutant = {"mutated_code": "def double(x):\n    return x + 2\n", "hints": ["a", "b", "c"], "explanation": "e"}
    _mock_llm(monkeypatch, [tests, mutant])
    ch = coach.make_challenge("type_mixup", custom_code=code)
    assert ch.tests == ["assert double(2) == 4", "assert double(0) == 0"]
    assert "dropped 1" in ch.verification_log[0]


def test_offline_mode_without_keys(monkeypatch):
    monkeypatch.setattr(llm, "any_available", lambda: False)
    ch = coach.make_challenge("aliasing", snippet_id="make_grid")
    assert ch.source.startswith("Offline")
    d = coach.diagnose("xs = [1]\nprint(xs[3])\n")
    assert d["error_type"] == "IndexError" and d["category"] == "off_by_one"


# ---------------------------------------------------------------- progress
def test_adaptive_picks_weakest_and_own_bugs():
    st = progress.new_state()
    for c in CATEGORIES:
        progress.log_attempt(st, category=c, snippet_id=None, score=90, solved=True, hints_used=0,
                             nudges_used=0, checks=1, seconds=30, source="t")
    progress.log_attempt(st, category="aliasing", snippet_id=None, score=10, solved=True, hints_used=3,
                         nudges_used=1, checks=4, seconds=300, source="t")
    assert progress.next_category(st)[0] == "aliasing"
    for _ in range(4):
        progress.log_encounter(st, "type_mixup", "TypeError")
    assert progress.next_category(st)[0] == "type_mixup"


def test_score():
    assert coach.score_attempt(0, 0, 1, True, False) == 100
    assert coach.score_attempt(2, 1, 3, True, False) == 40
    assert coach.score_attempt(0, 0, 1, False, True) == 0
