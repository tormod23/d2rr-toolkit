#!/usr/bin/env python3
"""Test suite for toolkit logging hygiene.

Verifies that d2rr_toolkit follows the "library logging" convention:

    AC1 - Silent by default (no stderr output without opt-in)
    AC2 - Fast even with a slow root-logger handler attached
    AC3 - enable_logging() opt-in works for INFO and DEBUG
    AC4 - No print() calls in library code
    AC5 - No basicConfig calls in library code
    AC6 - Performance regression guard (parse < 100 ms median)

Plus:
    AC7 - Top-level logger has NullHandler + propagate=False
    AC8 - disable_logging() restores the default silent state
    AC9 - d2rr_toolkit.logging namespace doesn't break stdlib logging
"""

from __future__ import annotations

import ast
import io
import logging
import sys
import time
from contextlib import redirect_stderr
from pathlib import Path

project_root = Path(__file__).parent.parent
src_dir = project_root / "src"
if str(src_dir) not in sys.path:
    sys.path.insert(0, str(src_dir))


# Reference D2S file used by AC2, AC3, AC6 for parse() benchmarks.
# ~100 items, typical endgame save.
_REFERENCE_D2S = project_root / "MrLockhart.d2s"
if not _REFERENCE_D2S.exists():
    _REFERENCE_D2S = project_root / "tests" / "cases" / "TC49" / "MrLockhart.d2s"


def _load_game_data_once() -> None:
    """Load game data exactly once for the test run."""
    from d2rr_toolkit.cli import _load_game_data

    _load_game_data(_REFERENCE_D2S)


def main() -> int:
    # Game data load *before* the silence tests so its INFO records
    # (from game_data modules) cannot leak into AC1's stderr capture.
    _load_game_data_once()

    passed = 0
    failed = 0
    total = 0

    def check(condition: bool, name: str, detail: str = ""):
        nonlocal passed, failed, total
        total += 1
        if condition:
            passed += 1
            print(f"  PASS  {name}")
        else:
            failed += 1
            print(f"  FAIL  {name}")
            if detail:
                print(f"        {detail}")

    # ── AC7 - Default logger state ────────────────────────────────────
    print("\n=== AC7. Default logger state (NullHandler + propagate=False) ===")

    from d2rr_toolkit.logging import disable_logging

    # Clean slate at the start of the test run
    disable_logging()

    toolkit_log = logging.getLogger("d2rr_toolkit")
    check(
        toolkit_log.propagate is False,
        "d2rr_toolkit logger has propagate=False",
    )
    handler_types = [type(h).__name__ for h in toolkit_log.handlers]
    check(
        "NullHandler" in handler_types,
        f"d2rr_toolkit logger has a NullHandler ({handler_types})",
    )
    check(
        toolkit_log.level == logging.NOTSET,
        f"d2rr_toolkit level is NOTSET ({toolkit_log.level})",
    )

    # ── AC1 - Silent by default (no stderr output) ────────────────────
    print("\n=== AC1. Silent by default ===")

    from d2rr_toolkit.parsers.d2s_parser import D2SParser

    # Restore the default state
    disable_logging()

    stderr_buffer = io.StringIO()
    with redirect_stderr(stderr_buffer):
        parsed = D2SParser(_REFERENCE_D2S).parse()
    stderr_output = stderr_buffer.getvalue()

    check(
        stderr_output == "",
        "D2SParser.parse() produces ZERO stderr output without opt-in",
        f"Got: {stderr_output[:200]!r}",
    )
    check(parsed is not None, "parse() still returns a valid result")
    check(len(parsed.items) > 0, f"parse() found items ({len(parsed.items)})")

    # ── AC2 - Fast with a slow root handler ──────────────────────────
    print("\n=== AC2. Fast with a slow root-logger handler ===")

    class SlowSink(logging.Handler):
        def __init__(self) -> None:
            super().__init__()
            self.count = 0

        def emit(self, record: logging.LogRecord) -> None:
            self.count += 1
            time.sleep(0.001)  # 1 ms per record - GUI-sink cost class

    # Save current root state and install a slow DEBUG handler
    root = logging.getLogger()
    old_level = root.level
    old_handlers = list(root.handlers)
    slow = SlowSink()

    try:
        root.handlers = [slow]
        root.setLevel(logging.DEBUG)
        # Toolkit must still be in its default silent state.
        disable_logging()

        t0 = time.perf_counter()
        D2SParser(_REFERENCE_D2S).parse()
        elapsed_ms = (time.perf_counter() - t0) * 1000
    finally:
        root.handlers = old_handlers
        root.setLevel(old_level)

    check(
        slow.count == 0,
        f"slow root-handler received ZERO toolkit records ({slow.count})",
    )
    check(
        elapsed_ms < 200,
        f"parse() < 200 ms with slow root handler ({elapsed_ms:.1f} ms)",
    )

    # ── AC3 - Opt-in works ────────────────────────────────────────────
    print("\n=== AC3. enable_logging() opt-in ===")

    from d2rr_toolkit.logging import enable_logging

    class CaptureHandler(logging.Handler):
        def __init__(self) -> None:
            super().__init__()
            self.records: list[logging.LogRecord] = []

        def emit(self, record: logging.LogRecord) -> None:
            self.records.append(record)

    capture = CaptureHandler()
    # Attach directly to the toolkit logger so we don't depend on propagation
    # behaviour - we're testing opt-in, not propagation.
    toolkit_log.addHandler(capture)

    try:
        # 3a. Default (disabled) - no records captured
        disable_logging()
        capture.records.clear()
        D2SParser(_REFERENCE_D2S).parse()
        check(
            len(capture.records) == 0,
            f"default state -> 0 records ({len(capture.records)})",
        )

        # 3b. Opt-in INFO - only INFO/WARNING/ERROR records
        enable_logging(level=logging.INFO)
        capture.records.clear()
        D2SParser(_REFERENCE_D2S).parse()
        debug_count = sum(1 for r in capture.records if r.levelno == logging.DEBUG)
        info_plus = sum(1 for r in capture.records if r.levelno >= logging.INFO)
        check(debug_count == 0, f"INFO opt-in -> 0 DEBUG records ({debug_count})")
        check(info_plus > 0, f"INFO opt-in -> at least 1 INFO+ record ({info_plus})")

        # 3c. Opt-in DEBUG - DEBUG records flow
        enable_logging(level=logging.DEBUG)
        capture.records.clear()
        D2SParser(_REFERENCE_D2S).parse()
        debug_count = sum(1 for r in capture.records if r.levelno == logging.DEBUG)
        check(
            debug_count > 0,
            f"DEBUG opt-in -> many DEBUG records ({debug_count})",
        )
    finally:
        toolkit_log.removeHandler(capture)
        disable_logging()

    # ── AC4 - No print() calls in library code ────────────────────────
    print("\n=== AC4. No print() calls in library code ===")

    toolkit_root = project_root / "src" / "d2rr_toolkit"
    violations: list[str] = []
    for path in toolkit_root.rglob("*.py"):
        # Skip __pycache__ and anything under it
        if "__pycache__" in path.parts:
            continue
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"))
        except SyntaxError:
            continue
        for node in ast.walk(tree):
            if (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Name)
                and node.func.id == "print"
            ):
                rel = path.relative_to(toolkit_root)
                violations.append(f"{rel}:{node.lineno}")

    check(
        not violations,
        f"AST scan finds no print() calls in library code ({len(violations)} violations)",
        "Violations:\n          " + "\n          ".join(violations[:10]) if violations else "",
    )

    # ── AC5 - No basicConfig calls in library code ────────────────────
    print("\n=== AC5. No basicConfig / getLogger().setLevel in library code ===")

    violations.clear()
    for path in toolkit_root.rglob("*.py"):
        if "__pycache__" in path.parts:
            continue
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"))
        except SyntaxError:
            continue
        for node in ast.walk(tree):
            if (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Attribute)
                and node.func.attr == "basicConfig"
            ):
                rel = path.relative_to(toolkit_root)
                violations.append(f"basicConfig @ {rel}:{node.lineno}")

    check(
        not violations,
        f"AST scan finds no logging.basicConfig calls ({len(violations)} violations)",
        "Violations:\n          " + "\n          ".join(violations[:10]) if violations else "",
    )

    # Also scan for getLogger().setLevel and getLogger().addHandler
    # patterns that would touch the ROOT logger (empty-arg getLogger).
    # A named getLogger("d2rr_toolkit").* is fine.
    root_mutation_count = 0
    for path in toolkit_root.rglob("*.py"):
        if "__pycache__" in path.parts:
            continue
        src = path.read_text(encoding="utf-8")
        # Parse each line - we're looking for literal getLogger() with no arg
        try:
            tree = ast.parse(src)
        except SyntaxError:
            continue
        for node in ast.walk(tree):
            # We want: logging.getLogger().setLevel(...)
            # or logging.getLogger().addHandler(...)
            if not isinstance(node, ast.Call):
                continue
            if not isinstance(node.func, ast.Attribute):
                continue
            if node.func.attr not in ("setLevel", "addHandler"):
                continue
            value = node.func.value
            if not isinstance(value, ast.Call):
                continue
            if not isinstance(value.func, ast.Attribute):
                continue
            if value.func.attr != "getLogger":
                continue
            # Check if getLogger() was called with no arguments (=> root logger)
            if not value.args and not value.keywords:
                rel = path.relative_to(toolkit_root)
                root_mutation_count += 1
                violations.append(f"root logger mutation @ {rel}:{node.lineno}")

    check(
        root_mutation_count == 0,
        f"no logging.getLogger().setLevel/addHandler on the ROOT logger ({root_mutation_count})",
        "Violations:\n          " + "\n          ".join(violations[-5:]) if violations else "",
    )

    # ── AC6 - Performance regression test ────────────────────────────
    print("\n=== AC6. Performance regression (parse < 100 ms median) ===")

    disable_logging()

    # Warm-up
    D2SParser(_REFERENCE_D2S).parse()

    runs: list[float] = []
    for _ in range(5):
        t0 = time.perf_counter()
        D2SParser(_REFERENCE_D2S).parse()
        runs.append(time.perf_counter() - t0)
    runs.sort()
    median_ms = runs[len(runs) // 2] * 1000
    min_ms = runs[0] * 1000
    max_ms = runs[-1] * 1000
    print(f"  parse() runs (ms): min={min_ms:.1f}, median={median_ms:.1f}, max={max_ms:.1f}")
    check(
        median_ms < 100,
        f"parse() median < 100 ms ({median_ms:.1f} ms)",
    )

    # ── AC8 - disable_logging() restores silent state ────────────────
    print("\n=== AC8. disable_logging() restores silence ===")

    enable_logging(level=logging.DEBUG)
    check(toolkit_log.level == logging.DEBUG, "enable_logging sets DEBUG")
    check(toolkit_log.propagate is True, "enable_logging sets propagate=True")

    disable_logging()
    check(
        toolkit_log.level == logging.NOTSET,
        f"disable_logging restores NOTSET ({toolkit_log.level})",
    )
    check(
        toolkit_log.propagate is False,
        "disable_logging restores propagate=False",
    )

    # ── AC9 - d2rr_toolkit.logging doesn't shadow stdlib ─────────────
    print("\n=== AC9. d2rr_toolkit.logging namespace safety ===")

    import logging as stdlib_logging

    check(
        stdlib_logging.INFO == 20,
        "stdlib logging.INFO still accessible (20)",
    )
    check(
        stdlib_logging.getLogger is not None,
        "stdlib logging.getLogger still callable",
    )

    # And importing d2rr_toolkit.logging explicitly also works
    import d2rr_toolkit.logging as tk_log_module

    check(
        hasattr(tk_log_module, "enable_logging"),
        "d2rr_toolkit.logging.enable_logging is importable",
    )
    check(
        hasattr(tk_log_module, "disable_logging"),
        "d2rr_toolkit.logging.disable_logging is importable",
    )

    # Submodules can still import stdlib logging - sanity check by importing
    # a submodule that uses it.
    from d2rr_toolkit.parsers import d2s_parser as _parser_module

    check(
        hasattr(_parser_module, "logger"),
        "d2s_parser module-level logger still exists",
    )
    check(
        _parser_module.logger.name == "d2rr_toolkit.parsers.d2s_parser",
        f"parser logger has the correct name ({_parser_module.logger.name})",
    )

    # ── Summary ───────────────────────────────────────────────────────
    print(f"\n{'=' * 60}")
    print(f"Total: {passed} PASS, {failed} FAIL ({total} checks)")
    print(f"{'=' * 60}")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())

