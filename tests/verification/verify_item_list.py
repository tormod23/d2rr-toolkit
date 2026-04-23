"""
tests/verification/verify_item_list.py
=======================================
PURPOSE : Verify the Skills section and Item List header format in v105 saves.
          Specifically:
            1. Find the "if" skills section header after the stats section
            2. Find the first "JM" item list header
            3. Confirm the item COUNT (uint16 after "JM") against known TC values
            4. Confirm that individual items do NOT have their own "JM" prefix (D2R rule)

STATUS  : [SPEC_ONLY] -> produces [BINARY_VERIFIED] evidence
COVERS  : VER-005 (Item List JM header + item count)

KNOWN ANCHORS (all [BINARY_VERIFIED]):
  - "gf" stats header: offset 833 (0x341)
  - Stats data begins: offset 835 (0x343)

KNOWN SPEC (all [SPEC_ONLY] until this script confirms them):
  - Stats section terminated by 9-bit value 0x1FF (all ones)
  - Skills section header: "if" (0x69 0x66) - CAUTION: same bytes as version "i" and "f"!
    Actually: "if" = 0x69 0x66? No - 'i'=0x69, 'f'=0x66. Let me re-check.
    ASCII 'i' = 0x69, 'f' = 0x66. So "if" = bytes 69 66.
    CAUTION: 0x69 appears in version field too. Search only AFTER offset 835.
  - Skills section: 2-byte header + 30 bytes (one byte per skill, 0 = no points)
  - Skills total size: 32 bytes (2 header + 30 data)
  - Item list header: "JM" = bytes 0x4A 0x4D
  - Item list count: uint16 LE immediately after "JM"
  - Individual items in D2R do NOT have their own "JM" prefix

KNOWN ITEM COUNTS FROM TEST CASE READMEs:
  TC01: 2 inventory items + 4 belt potions = 6 root items total
  TC02: 5 studded leathers + 4 belt potions = 9 root items total
  TC03: 10 equipped + 4 inventory + stash items (stash is separate section)
        Root item count in character list: 10 equipped + 4 inventory = 14?
        NOTE: belt items may or may not be counted - UNKNOWN, verify!

USAGE   : python tests/verification/verify_item_list.py <path.d2s> [tc_number]
          python tests/verification/verify_item_list.py tests/cases/TC01/TestABC.d2s 1
          python tests/verification/verify_item_list.py tests/cases/TC02/TestABC.d2s 2
          python tests/verification/verify_item_list.py tests/cases/TC03/TestWarlock.d2s 3

DATE    : 2026-03-24
"""

import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")


# ============================================================
# VERIFIED CONSTANTS [BINARY_VERIFIED]
# ============================================================

GF_OFFSET = 833  # [BINARY_VERIFIED] "gf" stats header offset
STATS_DATA_START = 835  # [BINARY_VERIFIED] first stats byte (after 2-byte "gf" header)

# ============================================================
# SPEC CONSTANTS [SPEC_ONLY]
# ============================================================

SKILLS_HEADER = b"if"  # [SPEC_ONLY] 2-byte skills section marker
SKILLS_DATA_LEN = 30  # [SPEC_ONLY] one byte per skill slot
SKILLS_TOTAL_LEN = 32  # [SPEC_ONLY] 2 header + 30 data

ITEM_LIST_HEADER = b"JM"  # [SPEC_ONLY] item list marker (only on LIST, not per item)
STATS_TERMINATOR_BITS = 9  # [SPEC_ONLY] 9-bit IDs
STATS_TERMINATOR_VALUE = 0x1FF  # [SPEC_ONLY] all-ones = end of stats

# Known item counts per test case [from TC READMEs - ground truth]
KNOWN_ITEM_COUNTS = {
    1: {
        "description": "TC01: Superior Short Sword + Vicious Spear (inv) + 4x Minor HP Potion (belt)",
        "inventory_items": 2,
        "belt_items": 4,
        "equipped_items": 0,
        "total_expected": None,  # [UNKNOWN] - do belt items count in root list?
        "notes": "Are belt items counted in root JM list? VERIFY!",
    },
    2: {
        "description": "TC02: 5x Studded Leather (inv) + 4x Minor HP Potion (belt)",
        "inventory_items": 5,
        "belt_items": 4,
        "equipped_items": 0,
        "total_expected": None,  # [UNKNOWN]
        "notes": "Are belt items counted in root JM list? VERIFY!",
    },
    3: {
        "description": "TC03: 10 equipped + 4 inventory items (stash is separate)",
        "inventory_items": 4,
        "belt_items": 0,
        "equipped_items": 10,
        "total_expected": None,  # [UNKNOWN]
        "notes": "Does root JM count include equipped items? VERIFY!",
    },
}


# ============================================================
# HELPERS
# ============================================================


def hex_dump(data: bytes, start: int, length: int, label: str = "") -> None:
    chunk = data[start : start + length]
    hex_part = " ".join(f"{b:02X}" for b in chunk)
    ascii_part = "".join(chr(b) if 32 <= b < 127 else "." for b in chunk)
    prefix = f"  [{label:35s}] " if label else "  "
    print(f"{prefix}offset=0x{start:04X} ({start:4d}d)  {hex_part:<48s}  |{ascii_part}|")


def uint16_le(data: bytes, offset: int) -> int:
    return int.from_bytes(data[offset : offset + 2], "little")


def print_section(title: str) -> None:
    print(f"\n{'=' * 60}")
    print(f"  {title}")
    print(f"{'=' * 60}")


def find_all(data: bytes, pattern: bytes, start: int = 0, limit: int | None = None) -> list[int]:
    """Find all occurrences of pattern in data[start:limit]."""
    results = []
    search_in = data[start:limit] if limit else data[start:]
    pos = 0
    while True:
        idx = search_in.find(pattern, pos)
        if idx == -1:
            break
        results.append(start + idx)
        pos = idx + 1
    return results


# ============================================================
# ANALYSIS FUNCTIONS
# ============================================================


def dump_post_gf_region(data: bytes) -> None:
    """Dump the region right after 'gf' for manual inspection."""
    print_section(f"RAW DUMP: 80 bytes after 'gf' (offset {STATS_DATA_START})")
    print("  This is the raw stats + skills data. Inspect for patterns.")
    print()
    for row in range(0, 80, 16):
        offset = STATS_DATA_START + row
        if offset >= len(data):
            break
        hex_dump(data, offset, 16)


def search_for_skills_header(data: bytes) -> list[int]:
    """Search for 'if' (skills section header) after stats data.

    [SPEC_ONLY] Skills header is 'if' = bytes 0x69 0x66.
    CAUTION: These bytes may appear in stats data as valid values.
    We search starting from STATS_DATA_START and report ALL occurrences
    up to offset 1200 (well past any reasonable stats section).
    """
    print_section("SEARCH: 'if' Skills Section Header (0x69 0x66) [SPEC_ONLY]")
    print(f"  Searching for bytes 69 66 ('if') from offset {STATS_DATA_START} to 1200...")
    print("  [SPEC_ONLY] Expected somewhere after stats section (which ends at unknown offset)")
    print()

    occurrences = find_all(data, SKILLS_HEADER, start=STATS_DATA_START, limit=1200)

    if not occurrences:
        print("  NOT FOUND between offset 835 and 1200.")
        print("  Possible causes:")
        print("    - Skills header uses different bytes in v105?")
        print("    - Stats section extends past offset 1200?")
    else:
        print(f"  Found {len(occurrences)} occurrence(s) of 'if':")
        for off in occurrences:
            print(f"  Offset {off} (0x{off:04X}):")
            hex_dump(data, off, 34, f"'if' + 32 bytes at {off}")
            # Show what follows as potential skill bytes
            skill_bytes = data[off + 2 : off + 32]
            non_zero = [(i, b) for i, b in enumerate(skill_bytes) if b != 0]
            print(
                f"    -> Non-zero skill bytes: {non_zero if non_zero else 'none (all skills = 0)'}"
            )
            print()

    return occurrences


def search_for_jm_headers(data: bytes) -> list[int]:
    """Search for all 'JM' item list headers in the file.

    [SPEC_ONLY] The item list starts with 'JM' = bytes 0x4A 0x4D.
    In D2R, only the LIST header has 'JM' - individual items do NOT.
    We expect exactly 2 'JM' markers in a character save:
      1. Player item list (after skills section)
      2. Corpse item list (usually empty = 0 items)
    """
    print_section("SEARCH: 'JM' Item List Headers (0x4A 0x4D) [SPEC_ONLY]")
    print("  Searching for all 'JM' occurrences in entire file...")
    print("  [SPEC_ONLY] Expect: 2 occurrences (player list + corpse list)")
    print("  [SPEC_ONLY] D2R rule: NO 'JM' on individual items, only on list headers")
    print()

    occurrences = find_all(data, ITEM_LIST_HEADER, start=STATS_DATA_START)

    if not occurrences:
        print("  NO 'JM' found! This is unexpected for a valid character save.")
    else:
        print(f"  Found {len(occurrences)} 'JM' occurrence(s):")
        print()
        for i, off in enumerate(occurrences):
            item_count = uint16_le(data, off + 2)
            print(f"  [{i+1}] Offset {off} (0x{off:04X}):")
            hex_dump(data, off, 8, f"JM header #{i+1}")
            print(f"       Item count (uint16 LE): {item_count}")
            print()

    return occurrences


def analyze_item_counts(jm_offsets: list[int], data: bytes, tc_num: int | None) -> None:
    """Compare found item counts against known TC values."""
    print_section("ITEM COUNT ANALYSIS")

    if not jm_offsets:
        print("  No JM headers found - cannot analyze item counts.")
        return

    first_jm = jm_offsets[0]
    first_count = uint16_le(data, first_jm + 2)

    print(f"  First 'JM' at offset {first_jm}: item count = {first_count}")
    print()

    if tc_num and tc_num in KNOWN_ITEM_COUNTS:
        tc = KNOWN_ITEM_COUNTS[tc_num]
        print(f"  TC{tc_num} expected: {tc['description']}")
        print(f"    Inventory items : {tc['inventory_items']}")
        print(f"    Belt items      : {tc['belt_items']}")
        print(f"    Equipped items  : {tc['equipped_items']}")
        print(f"    Total expected  : {tc['total_expected'] or '[UNKNOWN - verify!]'}")
        print(f"    Found in file   : {first_count}")
        print()

        # Try to deduce if belt items are included
        inv_only = tc["inventory_items"] + tc["equipped_items"]
        inv_plus_belt = inv_only + tc["belt_items"]

        if first_count == inv_only:
            print(f"  MATCH: count={first_count} == inventory+equipped only ({inv_only})")
            print("  -> Belt items are NOT counted in root JM list")
        elif first_count == inv_plus_belt:
            print(f"  MATCH: count={first_count} == inventory+equipped+belt ({inv_plus_belt})")
            print("  -> Belt items ARE counted in root JM list")
        else:
            print(f"  NO MATCH: count={first_count} does not match either hypothesis")
            print(f"    inv+equip only     = {inv_only}")
            print(f"    inv+equip+belt     = {inv_plus_belt}")
            print("  -> Item counting logic differs from expectation. Manual inspection needed.")

        print()
        print(f"  NOTE: {tc['notes']}")

    if len(jm_offsets) >= 2:
        second_jm = jm_offsets[1]
        second_count = uint16_le(data, second_jm + 2)
        print()
        print(f"  Second 'JM' at offset {second_jm}: count = {second_count}")
        if second_count == 0:
            print("  -> Count=0 as expected for corpse list (character is alive)")
        else:
            print(f"  -> Count={second_count} unexpected for corpse list!")
            print("     Either character was dead when saved, or this is not the corpse list.")

    if len(jm_offsets) > 2:
        print()
        print(f"  UNEXPECTED: {len(jm_offsets)} 'JM' markers found (expected 2).")
        print(f"  Additional offsets: {jm_offsets[2:]}")
        print("  These may be: mercenary items, iron golem, or unknown sections.")


def check_no_per_item_jm(data: bytes, jm_offsets: list[int]) -> None:
    """Verify the D2R rule: individual items must NOT have 'JM' prefix.

    [SPEC_ONLY] In D2R (v97+), only list headers have 'JM'.
    This is a critical difference from classic D2.
    If we find MORE 'JM' markers than expected, the format may differ.
    """
    print_section("VERIFY: No Per-Item 'JM' Prefix (D2R Rule) [SPEC_ONLY]")
    print("  [SPEC_ONLY] In D2R, individual items have NO 'JM' prefix.")
    print("  Classic D2 (<= v96) had 'JM' on every item.")
    print()

    if len(jm_offsets) == 0:
        print("  Cannot verify - no 'JM' found at all.")
    elif len(jm_offsets) == 2:
        print(f"  Found exactly 2 'JM' markers (offsets: {jm_offsets})")
        print("  This matches the expected D2R pattern:")
        print("    JM #1 -> player item list header")
        print("    JM #2 -> corpse item list header (usually count=0)")
        print("  -> D2R 'no per-item JM' rule: LIKELY CONFIRMED")
        print("     (Cannot be 100% certain without parsing item boundaries)")
    elif len(jm_offsets) > 2:
        print(f"  Found {len(jm_offsets)} 'JM' markers.")
        print("  Extra markers beyond 2 could indicate:")
        print("    a) Per-item 'JM' (classic behavior - would be wrong for D2R)")
        print("    b) Mercenary item list")
        print("    c) Other section headers that happen to contain 4A 4D")
        print("  -> Manual inspection required for markers beyond #2")


def show_region_between_gf_and_jm(data: bytes, jm_offsets: list[int]) -> None:
    """Show everything between 'gf' stats and first 'JM' item list."""
    if not jm_offsets:
        return

    first_jm = jm_offsets[0]
    region_size = first_jm - STATS_DATA_START

    print_section(f"REGION: Between 'gf' data and first 'JM' ({STATS_DATA_START} to {first_jm})")
    print(f"  Size: {region_size} bytes")
    print("  Contains: stats section + skills section")
    print("  [SPEC_ONLY] Skills section = 'if' header + 30 bytes = 32 bytes total")
    print("  [SPEC_ONLY] Stats section  = region_size - 32 bytes")
    estimated_stats_size = region_size - 32
    print(f"  -> Estimated stats section size: {estimated_stats_size} bytes (if skills=32)")
    print()

    # Dump the last 40 bytes before JM to find the skills/JM boundary
    dump_start = max(STATS_DATA_START, first_jm - 40)
    print("  Last 40 bytes before first 'JM' (finding skills section end):")
    hex_dump(data, dump_start, first_jm - dump_start + 4, "pre-JM region")


# ============================================================
# MAIN
# ============================================================


def main() -> int:
    if len(sys.argv) < 2:
        print("Usage: python verify_item_list.py <path_to_d2s> [tc_number]")
        print("  tc_number: 1, 2, or 3 (enables comparison against known item counts)")
        return 1

    path = Path(sys.argv[1])
    if not path.exists():
        print(f"ERROR: File not found: {path}")
        return 1

    tc_num: int | None = None
    if len(sys.argv) >= 3:
        try:
            tc_num = int(sys.argv[2])
        except ValueError:
            print(f"WARNING: Invalid tc_number '{sys.argv[2]}' - ignoring")

    with open(path, "rb") as f:
        data = f.read()

    print()
    print("=" * 60)
    print("  D2RR Toolkit: Item List Header Verification (VER-005)")
    print(f"  File: {path}  ({len(data)} bytes)")
    if tc_num:
        print(f"  Test Case: TC{tc_num:02d}")
    print("=" * 60)

    # Sanity check: confirm "gf" is where we expect it
    if data[GF_OFFSET : GF_OFFSET + 2] == b"gf":
        print(f"\n  [BINARY_VERIFIED] 'gf' confirmed at offset {GF_OFFSET} - anchor OK")
    else:
        actual = data[GF_OFFSET : GF_OFFSET + 2].hex()
        print(f"\n  ERROR: 'gf' NOT at offset {GF_OFFSET}! Found: {actual}")
        print("  This file may not be the expected version. Aborting.")
        return 1

    # Run all searches
    dump_post_gf_region(data)
    skills_offsets = search_for_skills_header(data)
    jm_offsets = search_for_jm_headers(data)
    analyze_item_counts(jm_offsets, data, tc_num)
    check_no_per_item_jm(data, jm_offsets)
    show_region_between_gf_and_jm(data, jm_offsets)

    print_section("SUMMARY")
    print("  Record in VERIFICATION_LOG.md VER-005:")
    print()
    if jm_offsets:
        print(f"  1. First 'JM' offset    : {jm_offsets[0]} (0x{jm_offsets[0]:04X})")
        print(f"     Item count (uint16)  : {uint16_le(data, jm_offsets[0] + 2)}")
    if len(jm_offsets) >= 2:
        print(f"  2. Second 'JM' offset   : {jm_offsets[1]} (0x{jm_offsets[1]:04X})")
        print(f"     Item count (uint16)  : {uint16_le(data, jm_offsets[1] + 2)}")
    if skills_offsets:
        print(f"  3. 'if' skills offset   : {skills_offsets[0]} (0x{skills_offsets[0]:04X})")
    print()
    print("  Questions to answer from this output:")
    print("  Q1: Does 'if' appear exactly once between 'gf' and 'JM'?")
    print("  Q2: Is the JM item count correct for this test case?")
    print("  Q3: Are belt items counted in the root JM item count?")
    print("  Q4: Are there exactly 2 'JM' markers (player + corpse)?")

    return 0


if __name__ == "__main__":
    sys.exit(main())

