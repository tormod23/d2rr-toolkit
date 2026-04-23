#!/usr/bin/env python3
"""Byte-level roundtrip safety net across ALL test fixtures.

For every known-good D2S and D2I file in tests/cases/ this test verifies:

  1. PASSIVE roundtrip (no modifications):
       parse -> write -> byte-identical to source
     Tests the "no-op rebuild" short-circuit in the writers.

  2. ACTIVE roundtrip (forced rebuild):
       parse -> _modified=True -> write -> equal to source
     Tests the FULL rebuild path - the one that actually runs when a
     caller modifies items. Tolerates ONLY these expected differences:
       * D2S checksum at offset 0x0C..0x0F (recomputed)
       * D2S timestamp at offset 0x20..0x23 (touched by writer)
     Everything else must be byte-identical. A single unexpected diff
     is a regression - it means the writer lost, shifted or mutated
     bytes somewhere in the rebuild pipeline.

Any failure here indicates a bit/byte-loss bug in parser or writer.
The test is resilient to known edge cases:
  * Files the parser cannot fully round-trip (e.g. TC31 known parse
    failure) are skipped with a WARN line but do not fail the suite.
  * File types that are GUI/GAME test artifacts (.GUI, .GAME, .GUI2,
    ".empty" etc.) are included - they MUST roundtrip too.

Run: python tests/test_roundtrip_all_fixtures.py
"""

from __future__ import annotations

import logging
import sys
import tempfile
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
SRC_DIR = PROJECT_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

# Suppress toolkit noise - we only want test output
logging.basicConfig(level=logging.ERROR)

# Offsets of bytes that SHOULD differ after a forced D2S rebuild:
D2S_CHECKSUM_OFFSET = 0x0C  # 4 bytes
D2S_TIMESTAMP_OFFSET = 0x20  # 4 bytes
D2S_TOLERATED_OFFSETS: set[int] = {D2S_CHECKSUM_OFFSET + i for i in range(4)} | {
    D2S_TIMESTAMP_OFFSET + i for i in range(4)
}

# Fixtures known to have parse-level issues - skip but warn
KNOWN_PARSE_FAILURES = {
    # TC31 carries a deliberately-corrupt item for parse-recovery testing
    "TC31/ModernSharedStashSoftCoreV2.d2i",
    # TC61 fixtures that intentionally contain duplicate Section 5 entries
    # to exercise the DuplicateSection5ItemError path. Writer rejects by
    # design - no regression.
    "TC61/MixedSection5_Modified.d2i",
}

# Files that fail the D2S ACTIVE roundtrip. Empty after the parser fix
# in _parse_jm_items that passes check_jm=True on the last JM item -
# previously 7 files lost 1-7 bytes of inter-item padding at the
# corpse-JM boundary because the Huffman probe alone could not detect
# padding when no next item followed. Kept as an explicit set so any
# future regression at that boundary can be tracked here without
# breaking CI.
KNOWN_D2S_ACTIVE_FAILURES: set[str] = set()


def _init_game_data() -> None:
    from d2rr_toolkit.cli import _load_game_data

    probe = next((PROJECT_ROOT / "tests" / "cases").rglob("*.d2s"), None)
    if probe is None:
        raise RuntimeError("No *.d2s under tests/cases - cannot init game data")
    if _load_game_data(probe) is None:
        raise RuntimeError("Reimagined excel base could not be resolved")


def _first_diff_summary(src: bytes, dst: bytes, tolerated: set[int] | None = None) -> str:
    """Return a short string describing the first unexpected byte diff."""
    tolerated = tolerated or set()
    if len(src) != len(dst):
        return f"size mismatch: src={len(src)} dst={len(dst)}"
    for i, (a, b) in enumerate(zip(src, dst)):
        if a == b:
            continue
        if i in tolerated:
            continue
        return f"first unexpected diff @ 0x{i:04x}: src=0x{a:02x} dst=0x{b:02x}"
    return "identical apart from tolerated offsets"


def _count_diffs(src: bytes, dst: bytes, tolerated: set[int] | None = None) -> int:
    """Count byte positions that differ outside the tolerated set."""
    tolerated = tolerated or set()
    n = 0
    for i, (a, b) in enumerate(zip(src, dst)):
        if a != b and i not in tolerated:
            n += 1
    n += abs(len(src) - len(dst))
    return n


# --------------------------------------------------------------------------- #
#  Per-file roundtrip
# --------------------------------------------------------------------------- #


def _d2s_passive(path: Path) -> tuple[bool, str]:
    """parse -> write (no mod) -> byte-identical."""
    from d2rr_toolkit.parsers.d2s_parser import D2SParser
    from d2rr_toolkit.writers.d2s_writer import D2SWriter

    src = path.read_bytes()
    char = D2SParser(path).parse()
    writer = D2SWriter(src, char)
    with tempfile.TemporaryDirectory() as td:
        out = Path(td) / path.name
        writer.write(out)
        dst = out.read_bytes()
    if dst == src:
        return True, f"{len(src)} bytes identical"
    return False, _first_diff_summary(src, dst)


def _d2s_active(path: Path) -> tuple[bool, str]:
    """parse -> _modified=True -> write -> tolerate checksum+timestamp only."""
    from d2rr_toolkit.parsers.d2s_parser import D2SParser
    from d2rr_toolkit.writers.d2s_writer import D2SWriter

    src = path.read_bytes()
    char = D2SParser(path).parse()
    writer = D2SWriter(src, char)
    writer._modified = True  # force full rebuild path  # noqa: SLF001
    with tempfile.TemporaryDirectory() as td:
        out = Path(td) / path.name
        writer.write(out)
        dst = out.read_bytes()
    n = _count_diffs(src, dst, D2S_TOLERATED_OFFSETS)
    if n == 0:
        return True, f"{len(src)} bytes (checksum+timestamp tolerated)"
    return False, (
        f"{n} unexpected diff(s) -- " + _first_diff_summary(src, dst, D2S_TOLERATED_OFFSETS)
    )


def _d2i_passive(path: Path) -> tuple[bool, str]:
    """parse -> write (no mod) -> byte-identical. D2I has no checksum/ts."""
    from d2rr_toolkit.parsers.d2i_parser import D2IParser
    from d2rr_toolkit.writers.d2i_writer import D2IWriter

    src = path.read_bytes()
    stash = D2IParser(path).parse()
    writer = D2IWriter.from_stash(src, stash)
    with tempfile.TemporaryDirectory() as td:
        out = Path(td) / path.name
        writer.write(out)
        dst = out.read_bytes()
    if dst == src:
        return True, f"{len(src)} bytes identical"
    return False, _first_diff_summary(src, dst)


# D2I has no forced-rebuild switch: the splice path is only triggered
# when an actual modification is present. We still want to verify the
# splice code, so the active test removes+readds an item to force the
# splice path and expects byte-identical output (modulo the restore).


def _d2i_active_reinsert(path: Path) -> tuple[bool, str]:
    """Force splice path: remove first item from tab 0 then re-add it.

    Since items are restored to their original list position with original
    source_data, the final output must be byte-identical to the source.
    If the splice path loses/corrupts bytes, this will catch it.
    """
    from d2rr_toolkit.parsers.d2i_parser import D2IParser
    from d2rr_toolkit.writers.d2i_writer import D2IWriter

    src = path.read_bytes()
    stash = D2IParser(path).parse()

    # Find a tab with at least one item to force the splice path
    target_tab = None
    for idx, tab in enumerate(stash.tabs):
        if tab.items:
            target_tab = idx
            break
    if target_tab is None:
        return True, "no items in any tab - passive path covers this file"

    writer = D2IWriter.from_stash(src, stash)
    # Mutate: pop first item then insert it back at same index
    # This triggers _tab_unchanged() == False -> _splice_section path
    first = writer._tab_items[target_tab].pop(0)  # noqa: SLF001
    writer._tab_items[target_tab].insert(0, first)  # noqa: SLF001

    with tempfile.TemporaryDirectory() as td:
        out = Path(td) / path.name
        writer.write(out)
        dst = out.read_bytes()
    if dst == src:
        return True, f"{len(src)} bytes identical (splice path)"
    return False, _first_diff_summary(src, dst)


# --------------------------------------------------------------------------- #
#  Fixture discovery
# --------------------------------------------------------------------------- #


def _is_known_failure(path: Path) -> bool:
    rel = path.relative_to(PROJECT_ROOT).as_posix()
    return any(rel.endswith(k) for k in KNOWN_PARSE_FAILURES)


def _classify(path: Path) -> str | None:
    """Return 'd2s', 'd2i', or None based on the file name.

    D2S and D2I share the same signature (0x55AA55AA) so we must rely on
    the file name. Variants like 'foo.d2s.GUI' are D2S; 'bar.d2i.GAME'
    is D2I. Plain 'minimal' (no suffix) is classified by probing the
    D2S header - if it looks like a valid v105 character, treat as D2S.
    """
    name = path.name.lower()
    # Strip trailing post-suffixes like .GUI .GUI2 .GAME .empty .backup
    # to expose the real file-format extension underneath.
    stem = name
    for _ in range(3):  # tolerate a few layered suffixes
        base, dot, suffix = stem.rpartition(".")
        if not dot:
            break
        if suffix in ("d2s", "d2i"):
            return suffix
        stem = base
    # No recognised extension - probe the header
    try:
        with path.open("rb") as fh:
            header = fh.read(0x20)
    except OSError:
        return None
    if len(header) < 0x10 or header[:4] != b"\x55\xaa\x55\xaa":
        return None
    # D2S has the version as uint32 at offset 4. For D2R Reimagined
    # that must be 105. D2I files put a section-header field there
    # (typically small integer != 105).
    version = int.from_bytes(header[4:8], "little")
    return "d2s" if version == 105 else "d2i"


def _discover_all() -> tuple[list[Path], list[Path]]:
    """Return (d2s_files, d2i_files) under tests/cases.

    The repo root is intentionally NOT scanned - every fixture must live
    in a numbered TC directory (see tests/cases/TC*/README.md).
    """
    cases = PROJECT_ROOT / "tests" / "cases"
    candidates: set[Path] = set()
    for pat in ("*.d2s", "*.d2i", "*.GUI", "*.GUI2", "*.GAME", "*.empty"):
        candidates.update(cases.rglob(pat))
    # Include bare-name variants (no extension) the user creates for A/B
    for f in cases.rglob("*"):
        if f.is_file() and "." not in f.name:
            candidates.add(f)
    d2s: list[Path] = []
    d2i: list[Path] = []
    for f in candidates:
        if not f.is_file():
            continue
        kind = _classify(f)
        if kind == "d2s":
            d2s.append(f)
        elif kind == "d2i":
            d2i.append(f)
    return sorted(d2s), sorted(d2i)


# --------------------------------------------------------------------------- #
#  Main
# --------------------------------------------------------------------------- #


def main() -> int:
    print("=" * 70)
    print("ROUNDTRIP BYTE-IDENTITY SAFETY NET")
    print("=" * 70)

    _init_game_data()

    d2s_files, d2i_files = _discover_all()
    print(f"\nDiscovered: {len(d2s_files)} D2S files, {len(d2i_files)} D2I files\n")

    passed = 0
    failed = 0
    skipped = 0
    known = 0
    unexpected_pass = 0

    def _run(label: str, fn, path: Path) -> None:
        nonlocal passed, failed, skipped, known, unexpected_pass
        rel = path.relative_to(PROJECT_ROOT).as_posix()
        if _is_known_failure(path):
            print(f"  SKIP  {label} {rel} -- known parse failure")
            skipped += 1
            return
        is_known_active_fail = label.strip() == "d2s.active" and rel in KNOWN_D2S_ACTIVE_FAILURES
        try:
            ok, detail = fn(path)
        except Exception as e:  # noqa: BLE001
            ok, detail = False, f"exception: {type(e).__name__}: {e}"
        if ok:
            if is_known_active_fail:
                print(f"  UNEXPECTED PASS  {label} {rel} -- remove from KNOWN_D2S_ACTIVE_FAILURES")
                unexpected_pass += 1
            else:
                print(f"  PASS  {label} {rel}")
                passed += 1
        else:
            if is_known_active_fail:
                print(f"  KNOWN {label} {rel} -- {detail}")
                known += 1
            else:
                print(f"  FAIL  {label} {rel} -- {detail}")
                failed += 1

    # --- D2S passive + active ---
    print("--- D2S passive roundtrip (no modification) ---")
    for f in d2s_files:
        _run("d2s.passive", _d2s_passive, f)

    print("\n--- D2S active roundtrip (_modified=True, full rebuild) ---")
    for f in d2s_files:
        _run("d2s.active ", _d2s_active, f)

    # --- D2I passive + active ---
    print("\n--- D2I passive roundtrip (no modification) ---")
    for f in d2i_files:
        _run("d2i.passive", _d2i_passive, f)

    print("\n--- D2I active roundtrip (splice path via reinsert) ---")
    for f in d2i_files:
        _run("d2i.active ", _d2i_active_reinsert, f)

    total = passed + failed + known + unexpected_pass
    print()
    print("=" * 70)
    print(
        f"Total: {passed} PASS, {failed} FAIL, {known} KNOWN, "
        f"{unexpected_pass} UNEXPECTED PASS, {skipped} SKIP ({total} checks)"
    )
    print("=" * 70)
    # Exit code: non-zero only on unexpected regressions. KNOWN failures are
    # tracked defects and must not break CI. UNEXPECTED PASS means a KNOWN
    # entry can be removed - flag as failure so the maintainer notices.
    return 0 if (failed == 0 and unexpected_pass == 0) else 1


if __name__ == "__main__":
    sys.exit(main())

