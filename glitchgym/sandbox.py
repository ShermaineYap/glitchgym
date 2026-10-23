"""Run student code and test assertions in an isolated Python subprocess.

Every test is a single Python statement, normally an ``assert``. Each test runs
in its own try/except so one failure doesn't hide the others, and the harness
reports structured JSON back to the parent process.

This is a hackathon-grade sandbox: separate process, isolated interpreter
(``-I``), empty environment, throwaway working directory, wall-clock timeout
and (on Linux/macOS) CPU and memory limits. It is not a security boundary for
hostile code on a shared server; see README "Limitations".
"""

from __future__ import annotations

import ast
import json
import os
import subprocess
import sys
import tempfile
import textwrap
from dataclasses import dataclass, field

DEFAULT_TIMEOUT = 4.0
_MARKER = "@@GLITCHGYM_RESULT@@"

_HARNESS = r'''
import json, sys, traceback, io, contextlib
_MARKER = {marker!r}
_SRC = {src!r}
_TESTS = {tests!r}
_out = {{"load_error": None, "results": []}}
_ns = {{"__name__": "__glitchgym__"}}
try:
    with contextlib.redirect_stdout(io.StringIO()):
        exec(compile(_SRC, "student_code.py", "exec"), _ns)
except BaseException as e:
    _out["load_error"] = "".join(traceback.format_exception(type(e), e, e.__traceback__)).strip()
import ast as _ast

def _instrument(src):
    # Turn `assert LEFT == RIGHT` into `__gg_left = LEFT; assert __gg_left == RIGHT`
    # so a failure can report what LEFT evaluated to without calling it twice.
    tree = _ast.parse(src)
    body = []
    for node in tree.body:
        if isinstance(node, _ast.Assert) and isinstance(node.test, _ast.Compare):
            tgt = _ast.Name(id="__gg_left", ctx=_ast.Store())
            body.append(_ast.Assign(targets=[tgt], value=node.test.left))
            node.test.left = _ast.Name(id="__gg_left", ctx=_ast.Load())
        body.append(node)
    tree.body = body
    return compile(_ast.fix_missing_locations(tree), "test", "exec")

if _out["load_error"] is None:
    for _t in _TESTS:
        _r = {{"test": _t, "passed": False, "error": None}}
        _g = dict(_ns)
        try:
            _code = _instrument(_t)
            with contextlib.redirect_stdout(io.StringIO()):
                exec(_code, _g)
            _r["passed"] = True
        except AssertionError as e:
            _msg = str(e)
            if not _msg and "__gg_left" in _g:
                _msg = "got " + repr(_g["__gg_left"])[:300]
            _r["error"] = "AssertionError: " + _msg if _msg else "AssertionError"
        except BaseException as e:
            _tb = traceback.extract_tb(e.__traceback__)
            _line = ""
            for _fr in _tb:
                if _fr.filename == "student_code.py":
                    _line = " (student_code.py, line %d)" % _fr.lineno
            _r["error"] = type(e).__name__ + ": " + str(e) + _line
        _out["results"].append(_r)
sys.stdout.write(_MARKER + json.dumps(_out))
'''

_RUN_HARNESS = r'''
import sys, traceback, io, contextlib
_SRC = {src!r}
_ns = {{"__name__": "__main__"}}
try:
    exec(compile(_SRC, "student_code.py", "exec"), _ns)
except BaseException:
    traceback.print_exc()
    sys.exit(1)
'''


@dataclass
class TestResult:
    test: str
    passed: bool
    error: str | None = None


@dataclass
class RunReport:
    ok: bool                       # every test passed and code loaded
    load_error: str | None = None  # syntax/import/top-level error
    timed_out: bool = False
    results: list[TestResult] = field(default_factory=list)

    @property
    def passed(self) -> int:
        return sum(r.passed for r in self.results)

    @property
    def failed(self) -> int:
        return len(self.results) - self.passed

    def summary(self) -> str:
        if self.timed_out:
            return "Timed out (infinite loop?)"
        if self.load_error:
            return "Code failed to load"
        return f"{self.passed}/{len(self.results)} tests passing"


def _limits():  # pragma: no cover - only on POSIX
    try:
        import resource
        resource.setrlimit(resource.RLIMIT_CPU, (5, 5))
        resource.setrlimit(resource.RLIMIT_AS, (512 * 1024 * 1024, 512 * 1024 * 1024))
    except Exception:
        pass


def _spawn(script: str, timeout: float) -> subprocess.CompletedProcess:
    with tempfile.TemporaryDirectory(prefix="glitchgym_") as tmp:
        path = os.path.join(tmp, "harness.py")
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(script)
        env = {"PYTHONIOENCODING": "utf-8", "PATH": os.environ.get("PATH", "")}
        if os.name == "nt":
            env["SYSTEMROOT"] = os.environ.get("SYSTEMROOT", "")
        return subprocess.run(
            [sys.executable, "-I", path],
            cwd=tmp,
            env=env,
            capture_output=True,
            text=True,
            timeout=timeout,
            preexec_fn=_limits if os.name == "posix" else None,
        )


def syntax_error(code: str) -> str | None:
    """Return a readable syntax error message, or None if the code parses."""
    try:
        ast.parse(code)
        return None
    except SyntaxError as e:
        return f"SyntaxError: {e.msg} (line {e.lineno})"


def run_tests(code: str, tests: list[str], timeout: float = DEFAULT_TIMEOUT) -> RunReport:
    """Execute ``code`` then each test statement; return a structured report."""
    code = textwrap.dedent(code)
    script = _HARNESS.format(marker=_MARKER, src=code, tests=list(tests))
    try:
        proc = _spawn(script, timeout)
    except subprocess.TimeoutExpired:
        return RunReport(ok=False, timed_out=True,
                         results=[TestResult(t, False, "Timed out") for t in tests])
    out = proc.stdout or ""
    if _MARKER not in out:
        err = (proc.stderr or "").strip() or "Sandbox crashed (memory or CPU limit?)"
        return RunReport(ok=False, load_error=err[-1500:])
    data = json.loads(out.split(_MARKER, 1)[1])
    results = [TestResult(**r) for r in data["results"]]
    load_error = data["load_error"]
    ok = load_error is None and bool(results) and all(r.passed for r in results)
    return RunReport(ok=ok, load_error=load_error, results=results)


def run_script(code: str, timeout: float = DEFAULT_TIMEOUT) -> tuple[str, str, bool]:
    """Run code as a script. Returns (stdout, stderr/traceback, timed_out)."""
    script = _RUN_HARNESS.format(src=textwrap.dedent(code))
    try:
        proc = _spawn(script, timeout)
    except subprocess.TimeoutExpired:
        return "", "TimeoutError: the program ran longer than %.0f s (infinite loop?)" % timeout, True
    return (proc.stdout or "")[-4000:], (proc.stderr or "").strip()[-4000:], False
