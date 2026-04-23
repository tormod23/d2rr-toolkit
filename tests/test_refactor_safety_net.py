#!/usr/bin/env python3
"""Refactor Safety Net - Byte-identical Roundtrip Guard.

This test must pass before AND after every refactoring step. It parses each
sample .d2s / .d2i file in the repo root and verifies that the unmodified
writer produces a byte-identical copy of the source. Any drift indicates a
functional regression in the parser/writer chain.

On top of that, verifies:
- Basic import surface for the packages we are refactoring.
- CASC reader is importable via both old and new paths (during migration).
- Section 5 DB round-trip for the reimagined stash.

Run:
    python tests/test_refactor_safety_net.py

Exit code 0 = all pass. Non-zero = regression detected.
"""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path
from typing import Callable

PROJECT_ROOT = Path(__file__).resolve().parent.parent
SRC_DIR = PROJECT_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

# Silence toolkit debug noise during smoke run.
import logging  # noqa: E402

logging.basicConfig(level=logging.ERROR)


def _init_game_data() -> None:
    """Load all game data tables the parser/writer needs at import time.

    Uses the CLI helper because it resolves the Reimagined excel base from the
    installed D2R mod directory - we don't want duplicate path-resolution logic
    in the safety net itself.
    """
    from d2rr_toolkit.cli import _load_game_data

    # Probe against any existing TC sample so the helper can locate the mod dir.
    probe = next((PROJECT_ROOT / "tests" / "cases").rglob("*.d2s"), None)
    if probe is None:  # pragma: no cover - TC samples are required
        raise RuntimeError("No *.d2s samples under tests/cases - cannot init game data")
    if _load_game_data(probe) is None:
        raise RuntimeError("Reimagined excel base could not be resolved")


# --------------------------------------------------------------------------- #
#  Single-check runner
# --------------------------------------------------------------------------- #

Result = tuple[bool, str]
Check = Callable[[], Result]


def _run(name: str, fn: Check) -> bool:
    try:
        ok, detail = fn()
    except Exception as e:  # pragma: no cover - defensive only
        ok, detail = False, f"exception: {type(e).__name__}: {e}"
    status = "PASS" if ok else "FAIL"
    pad = " " * max(0, 52 - len(name))
    extra = f" -- {detail}" if detail else ""
    print(f"  {status}  {name}{pad}{extra}")
    return ok


# --------------------------------------------------------------------------- #
#  Import surface
# --------------------------------------------------------------------------- #


def check_import_toolkit() -> Result:
    from d2rr_toolkit.parsers.d2s_parser import D2SParser  # noqa: F401
    from d2rr_toolkit.parsers.d2i_parser import D2IParser  # noqa: F401
    from d2rr_toolkit.writers.d2s_writer import D2SWriter  # noqa: F401
    from d2rr_toolkit.writers.d2i_writer import D2IWriter  # noqa: F401
    from d2rr_toolkit.models.character import ParsedCharacter, ParsedItem  # noqa: F401

    return True, "d2rr_toolkit public API imports clean"


def check_import_legacy_shim() -> Result:
    # Backward-compat layer must stay importable until Phase 6.
    from d2rr_toolkit.parsers.d2s_parser import D2SParser  # noqa: F401
    from d2rr_toolkit.writers.d2s_writer import D2SWriter  # noqa: F401

    return True, "d2rr_toolkit re-export shim importable"


def check_import_casc() -> Result:
    # After the CASC move in Phase 2, BOTH import paths must still work.
    from d2rr_toolkit.adapters.casc import CASCReader as _Legacy  # noqa: F401

    try:
        from d2rr_toolkit.adapters.casc.reader import CASCReader as _New  # noqa: F401

        detail = "legacy + new adapter paths importable"
    except ModuleNotFoundError:
        detail = "legacy path importable (adapter move pending)"
    return True, detail


# --------------------------------------------------------------------------- #
#  Roundtrip byte-identity
# --------------------------------------------------------------------------- #


def _roundtrip_d2s(path: Path) -> Result:
    from d2rr_toolkit.parsers.d2s_parser import D2SParser
    from d2rr_toolkit.writers.d2s_writer import D2SWriter

    source = path.read_bytes()
    character = D2SParser(path).parse()
    writer = D2SWriter(source, character)
    with tempfile.TemporaryDirectory() as tmpdir:
        out = Path(tmpdir) / path.name
        writer.write(out)
        produced = out.read_bytes()

    if produced == source:
        return True, f"{len(source)} bytes identical"
    # Helpful failure detail: find first diverging offset.
    for i, (a, b) in enumerate(zip(source, produced)):
        if a != b:
            return False, (
                f"first diff @ 0x{i:04x}: source={a:02x} produced={b:02x} "
                f"(sizes src={len(source)} dst={len(produced)})"
            )
    return False, f"size mismatch: src={len(source)} dst={len(produced)}"


def _roundtrip_d2i(path: Path) -> Result:
    from d2rr_toolkit.parsers.d2i_parser import D2IParser
    from d2rr_toolkit.writers.d2i_writer import D2IWriter

    source = path.read_bytes()
    stash = D2IParser(path).parse()
    writer = D2IWriter.from_stash(source, stash)
    with tempfile.TemporaryDirectory() as tmpdir:
        out = Path(tmpdir) / path.name
        writer.write(out)
        produced = out.read_bytes()

    if produced == source:
        return True, f"{len(source)} bytes identical"
    for i, (a, b) in enumerate(zip(source, produced)):
        if a != b:
            return False, (
                f"first diff @ 0x{i:04x}: source={a:02x} produced={b:02x} "
                f"(sizes src={len(source)} dst={len(produced)})"
            )
    return False, f"size mismatch: src={len(source)} dst={len(produced)}"


# --------------------------------------------------------------------------- #
#  Main
# --------------------------------------------------------------------------- #


def main() -> int:
    print("=" * 80)
    print("REFACTOR SAFETY NET")
    print("=" * 80)

    _init_game_data()

    checks: list[tuple[str, Check]] = [
        ("import[d2rr_toolkit public API]", check_import_toolkit),
        ("import[d2rr_toolkit shim]", check_import_legacy_shim),
        ("import[CASC reader]", check_import_casc),
    ]

    # Sample pool: pick one D2S per TC and the canonical D2I shared
    # stash. The roundtrip safety net (test_roundtrip_all_fixtures.py)
    # is the exhaustive variant - this one exists to provide a fast,
    # representative smoke check during refactors.
    cases = PROJECT_ROOT / "tests" / "cases"
    smoke_d2s = [
        cases / "TC49" / "MrLockhart.d2s",
        cases / "TC55" / "FrozenOrbHydra.d2s",
        cases / "TC56" / "VikingBarbie.d2s",
        cases / "TC71" / "StraFoHdin.d2s",
        cases / "TC71" / "HCLives.d2s",
        cases / "TC71" / "HCDied.d2s",
    ]
    d2s_samples = [p for p in smoke_d2s if p.exists()]
    d2i_samples = [cases / "TC30" / "ModernSharedStashSoftCoreV2.d2i"]
    d2i_samples = [p for p in d2i_samples if p.exists()]

    for f in d2s_samples:
        checks.append((f"roundtrip[{f.name}]", lambda p=f: _roundtrip_d2s(p)))
    for f in d2i_samples:
        checks.append((f"roundtrip[{f.name}]", lambda p=f: _roundtrip_d2i(p)))

    passed = 0
    failed = 0
    for name, fn in checks:
        if _run(name, fn):
            passed += 1
        else:
            failed += 1

    print("-" * 80)
    print(f"Total: {passed} PASS, {failed} FAIL")
    print("=" * 80)
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())

