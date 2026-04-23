"""
tests/verification/verify_header_v105_offsets.py
=================================================
PURPOSE : Find the actual byte offsets of known header fields in v105 saves.
          The spec offsets (based on v97/v98) are WRONG for v105.
          This script uses KNOWN VALUES from the TC01 README to locate fields
          by their content, not by their assumed position.

          Known values from TC01/README.md:
            - Character name : "TestABC"
            - Class          : Barbarian (spec says ID=4, but verify!)
            - Level          : 42
            - "gf" marker    : confirmed at offset 833 by VER-003

STATUS  : [SPEC_ONLY] -> produces [BINARY_VERIFIED] offset evidence
COVERS  : VER-002 (name offset), VER-004 (class/level offsets)

USAGE   : python tests/verification/verify_header_v105_offsets.py <path.d2s>
          python tests/verification/verify_header_v105_offsets.py tests/cases/TC01/testABC.d2s

DATE    : 2026-03-24
"""

import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")


# ============================================================
# KNOWN VALUES FROM TC01/README.md - used to FIND offsets
# ============================================================

TC01_CHAR_NAME = "TestABC"  # Known character name
TC01_CHAR_NAME_BYTES = b"TestABC"
TC01_LEVEL = 42  # Known level (single byte, value 0x2A)
TC01_EXPERIENCE = 21_376_515  # Known XP (uint32 LE = 0x01461E03... let's compute)
TC01_GOLD_INV = 419_458  # Known inventory gold (uint32 LE)

# [BINARY_VERIFIED] from VER-003
GF_OFFSET = 833  # "gf" stats header confirmed at this offset


def hex_dump(data: bytes, start: int, length: int, label: str) -> None:
    chunk = data[start : start + length]
    hex_part = " ".join(f"{b:02X}" for b in chunk)
    ascii_part = "".join(chr(b) if 32 <= b < 127 else "." for b in chunk)
    print(f"  [{label:35s}] offset=0x{start:04X} ({start:4d}d)  {hex_part:<48s}  |{ascii_part}|")


def uint32_le(data: bytes, offset: int) -> int:
    return int.from_bytes(data[offset : offset + 4], "little")


def print_section(title: str) -> None:
    print(f"\n{'=' * 60}")
    print(f"  {title}")
    print(f"{'=' * 60}")


def search_byte_pattern(data: bytes, pattern: bytes, limit: int = 1024) -> list[int]:
    """Find all occurrences of a byte pattern in data[:limit]."""
    results = []
    search_area = data[:limit]
    start = 0
    while True:
        pos = search_area.find(pattern, start)
        if pos == -1:
            break
        results.append(pos)
        start = pos + 1
    return results


def show_context(data: bytes, offset: int, before: int = 4, after: int = 16) -> None:
    """Show bytes surrounding an offset for context."""
    start = max(0, offset - before)
    hex_dump(data, start, before + after, f"Context around 0x{offset:04X}")


def main() -> int:
    if len(sys.argv) < 2:
        print("Usage: python verify_header_v105_offsets.py <path_to_d2s>")
        return 1

    path = Path(sys.argv[1])
    if not path.exists():
        print(f"ERROR: File not found: {path}")
        return 1

    with open(path, "rb") as f:
        data = f.read()

    print()
    print("=" * 60)
    print("  D2RR Toolkit: v105 Header Offset Discovery")
    print("  Using known TC01 values to find actual field positions")
    print("=" * 60)
    print(f"  File: {path}  ({len(data)} bytes)")

    # --------------------------------------------------------
    # SEARCH 1: Find character name "TestABC"
    # --------------------------------------------------------
    print_section("SEARCH 1: Character Name 'TestABC'")
    print(f"  Searching for ASCII bytes: {TC01_CHAR_NAME_BYTES.hex(' ')}")
    print(f"  ('TestABC' = {' '.join(f'{b:02X}' for b in TC01_CHAR_NAME_BYTES)})")
    print()

    name_occurrences = search_byte_pattern(data, TC01_CHAR_NAME_BYTES, limit=len(data))
    if not name_occurrences:
        print("  NOT FOUND anywhere in file!")
        print("  Possible causes: UTF-16 encoding? Different encoding entirely?")
        # Try UTF-16 LE
        utf16_bytes = TC01_CHAR_NAME.encode("utf-16-le")
        utf16_occurrences = search_byte_pattern(data, utf16_bytes, limit=len(data))
        if utf16_occurrences:
            print(f"  HOWEVER: Found as UTF-16-LE at offset(s): {utf16_occurrences}")
            for off in utf16_occurrences:
                show_context(data, off, before=4, after=len(utf16_bytes) + 4)
        else:
            print("  Also NOT found as UTF-16-LE.")
            print("  *** MANUAL INSPECTION NEEDED - see full hex dump below ***")
    else:
        for off in name_occurrences:
            print(f"  FOUND at offset {off} (0x{off:04X}):")
            show_context(data, off, before=4, after=20)
            print(f"  --> Character name field starts at offset: {off}")
            print(f"  --> Spec said 0x14 (20d) - actual is {off} ({off:04X}h)")
            if off != 0x14:
                print(f"  --> DIFFERENCE from spec: {off - 0x14} bytes")

    # --------------------------------------------------------
    # SEARCH 2: Find level byte (value 42 = 0x2A)
    # --------------------------------------------------------
    print_section("SEARCH 2: Level Byte (value 42 = 0x2A)")
    print("  Searching for 0x2A in header region (first 900 bytes)...")
    print("  WARNING: 0x2A is common - we look for it near other known fields")
    print()

    level_candidates = []
    for i in range(min(GF_OFFSET, len(data))):
        if data[i] == TC01_LEVEL:
            level_candidates.append(i)

    if not level_candidates:
        print(f"  No 0x2A bytes found in first {GF_OFFSET} bytes!")
    else:
        print(f"  Found {len(level_candidates)} candidate offset(s) for level=42:")
        for off in level_candidates:
            show_context(data, off, before=4, after=8)
        print()
        print("  NOTE: Level appears twice in saves: once in header, once in stats.")
        print("  The header level byte should be between the name field and 'gf'.")

    # --------------------------------------------------------
    # SEARCH 3: Find experience value (uint32 LE)
    # --------------------------------------------------------
    print_section("SEARCH 3: Experience Value (21,376,515 = 0x01461E03)")
    xp_bytes = TC01_EXPERIENCE.to_bytes(4, "little")
    print(f"  Searching for bytes: {xp_bytes.hex(' ')}  ({TC01_EXPERIENCE:,})")
    print()

    xp_occurrences = search_byte_pattern(data, xp_bytes, limit=len(data))
    if not xp_occurrences:
        print("  NOT FOUND. XP may be stored differently, or TC01 value is wrong.")
    else:
        for off in xp_occurrences:
            print(f"  FOUND at offset {off} (0x{off:04X}):")
            show_context(data, off, before=4, after=8)

    # --------------------------------------------------------
    # SEARCH 4: Find gold inventory (uint32 LE)
    # --------------------------------------------------------
    print_section("SEARCH 4: Gold Inventory (419,458 = 0x000665C2)")
    gold_bytes = TC01_GOLD_INV.to_bytes(4, "little")
    print(f"  Searching for bytes: {gold_bytes.hex(' ')}  ({TC01_GOLD_INV:,})")
    print()

    gold_occurrences = search_byte_pattern(data, gold_bytes, limit=len(data))
    if not gold_occurrences:
        print("  NOT FOUND. Gold may be bit-packed in the stats section (after 'gf').")
        print("  This is expected - gold is stored as a stat, not a header field.")
    else:
        for off in gold_occurrences:
            print(f"  FOUND at offset {off} (0x{off:04X}):")
            show_context(data, off, before=4, after=8)

    # --------------------------------------------------------
    # FULL HEADER HEX DUMP (everything before "gf")
    # --------------------------------------------------------
    print_section(f"FULL HEADER HEX DUMP (bytes 0 to {GF_OFFSET + 4})")
    print("  This is the ENTIRE header region. Inspect manually for known patterns.")
    print()

    for row_start in range(0, GF_OFFSET + 4, 16):
        chunk = data[row_start : row_start + 16]
        if not chunk:
            break
        hex_part = " ".join(f"{b:02X}" for b in chunk)
        ascii_part = "".join(chr(b) if 32 <= b < 127 else "." for b in chunk)
        # Annotate known offsets
        note = ""
        if row_start == 0:
            note = " <- signature + version"
        elif row_start == 0x10:
            note = " <- spec says: name at 0x14 (UNVERIFIED for v105)"
        elif row_start == GF_OFFSET & ~0xF:
            note = " <- near 'gf' stats header"
        print(f"  0x{row_start:04X}:  {hex_part:<48s}  |{ascii_part}|{note}")

    print()
    print("=" * 60)
    print("  SUMMARY & NEXT STEPS")
    print("=" * 60)
    print()
    print("  After reviewing this output:")
    print("  1. Find 'TestABC' in the hex dump above")
    print("     -> Record its actual offset in VERIFICATION_LOG.md VER-002")
    print("  2. Find 0x2A (42) near the name -> that is the level byte")
    print("     -> Record its actual offset in VERIFICATION_LOG.md VER-004")
    print("  3. Look for a pattern of 0x04 (Barbarian class?) near name + level")
    print("     -> Record class byte offset in VERIFICATION_LOG.md VER-004")
    print("  4. Note the full header is 833 bytes -> update all spec constants")
    print()
    print("  *** COPY RELEVANT OFFSETS INTO VERIFICATION_LOG.md ***")

    return 0


if __name__ == "__main__":
    sys.exit(main())

