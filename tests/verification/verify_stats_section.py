"""
tests/verification/verify_stats_section.py
==========================================
PURPOSE : Verify the Stats Section bit-level encoding in v105 saves.
          This is the most complex verification so far - we work at the bit level.

          The spec claims (all [SPEC_ONLY] until confirmed here):
            - Stats are encoded as: 9-bit ID + variable-width value
            - Bits are read LSB-first
            - Bits within each byte are REVERSED (nokka/d2s documents this)
            - Section is terminated by 9-bit value 0x1FF (all ones)
            - Bit widths come from ItemStatCost.txt "CSvBits" column

          This script tests BOTH approaches (reversed / not reversed) and
          compares results against known TC README values to determine which
          is correct. We do NOT assume - we verify.

STATUS  : [SPEC_ONLY] -> produces [BINARY_VERIFIED] evidence
COVERS  : VER-007

KNOWN ANCHORS [BINARY_VERIFIED]:
  - Stats data starts at offset 835 (byte after "gf" at 833)

KNOWN STAT VALUES (from TC READMEs - ground truth for verification):
  TC01 (Barbarian lv42): Str=30, Dex=20, Vit=25, Ene=10,
                          StatPts=205, SkillPts=41, Level=42,
                          Gold_inv=419458, Gold_stash=0
  TC02 (Barbarian lv42): same base stats, Gold_inv=415144, Gold_stash=4194
  TC03 (Warlock   lv12): Str=15, Dex=20, Vit=25, Ene=20,
                          StatPts=55, SkillPts=11, Level=12,
                          Gold_inv=67655, Gold_stash=14545

USAGE   : python tests/verification/verify_stats_section.py <path.d2s> [tc_number]
          python tests/verification/verify_stats_section.py tests/cases/TC01/TestABC.d2s 1
          python tests/verification/verify_stats_section.py tests/cases/TC02/TestABC.d2s 2
          python tests/verification/verify_stats_section.py tests/cases/TC03/TestWarlock.d2s 3

DATE    : 2026-03-24
"""

import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")


# ============================================================
# VERIFIED CONSTANTS [BINARY_VERIFIED]
# ============================================================

GF_OFFSET = 833  # [BINARY_VERIFIED] "gf" stats header
STATS_DATA_START = 835  # [BINARY_VERIFIED] first stats byte
STATS_TERMINATOR = 0x1FF  # [SPEC_ONLY] 9-bit all-ones = end of stats section

# ============================================================
# SPEC CONSTANTS [SPEC_ONLY] - from ItemStatCost.txt CSvBits column
# These are the stat IDs and their bit widths in the CHARACTER STATS section.
# NOTE: These differ from item property bit widths (Save Bits column).
# ============================================================

# Format: stat_id -> (name, csv_bits, save_add, is_fixed_point)
# is_fixed_point=True means divide by 256 for display value (HP/Mana/Stamina)
STAT_DEFS: dict[int, tuple[str, int, int, bool]] = {
    0: ("Strength", 10, 0, False),  # [SPEC_ONLY]
    1: ("Energy", 10, 0, False),  # [SPEC_ONLY]
    2: ("Dexterity", 10, 0, False),  # [SPEC_ONLY]
    3: ("Vitality", 10, 0, False),  # [SPEC_ONLY]
    4: ("Stat Points Remaining", 10, 0, False),  # [SPEC_ONLY]
    5: ("Skill Points Remaining", 8, 0, False),  # [SPEC_ONLY]
    6: ("Current HP", 21, 0, True),  # [SPEC_ONLY] /256
    7: ("Max HP", 21, 0, True),  # [SPEC_ONLY] /256
    8: ("Current Mana", 21, 0, True),  # [SPEC_ONLY] /256
    9: ("Max Mana", 21, 0, True),  # [SPEC_ONLY] /256
    10: ("Current Stamina", 21, 0, True),  # [SPEC_ONLY] /256
    11: ("Max Stamina", 21, 0, True),  # [SPEC_ONLY] /256
    12: ("Level", 7, 0, False),  # [SPEC_ONLY]
    13: ("Experience", 32, 0, False),  # [SPEC_ONLY]
    14: ("Gold (Inventory)", 25, 0, False),  # [SPEC_ONLY]
    15: ("Gold (Stash)", 25, 0, False),  # [SPEC_ONLY]
}

# Known values per test case [from TC READMEs - GROUND TRUTH]
KNOWN_VALUES: dict[int, dict[str, int]] = {
    1: {
        "Strength": 30,
        "Dexterity": 20,
        "Vitality": 25,
        "Energy": 10,
        "Stat Points Remaining": 205,
        "Skill Points Remaining": 41,
        "Level": 42,
        "Gold (Inventory)": 419_458,
        "Gold (Stash)": 0,
    },
    2: {
        "Strength": 30,
        "Dexterity": 20,
        "Vitality": 25,
        "Energy": 10,
        "Stat Points Remaining": 205,
        "Skill Points Remaining": 41,
        "Level": 42,
        "Gold (Inventory)": 415_144,
        "Gold (Stash)": 4_194,
    },
    3: {
        "Strength": 15,
        "Dexterity": 20,
        "Vitality": 25,
        "Energy": 20,
        "Stat Points Remaining": 55,
        "Skill Points Remaining": 11,
        "Level": 12,
        "Gold (Inventory)": 67_655,
        "Gold (Stash)": 14_545,
    },
}


# ============================================================
# BIT READER - two variants to test both hypotheses
# ============================================================


def reverse_bits_in_byte(b: int) -> int:
    """Reverse the 8 bits within a single byte.

    Example: 0b10110001 -> 0b10001101
    This is the operation nokka/d2s applies to the stats section.
    """
    result = 0
    for i in range(8):
        if b & (1 << i):
            result |= 1 << (7 - i)
    return result


def preprocess_reversed(data: bytes) -> bytes:
    """Return a copy of data with bits reversed in every byte.

    [SPEC_ONLY] nokka/d2s says the stats section needs this transformation
    before reading as a normal LSB-first bit stream.
    """
    return bytes(reverse_bits_in_byte(b) for b in data)


def read_bits_lsb(data: bytes, bit_offset: int, count: int) -> int:
    """Read 'count' bits starting at 'bit_offset', LSB-first.

    This is the standard D2 bit reading method.
    Bit 0 of byte 0 is the first bit, bit 7 of byte 0 is the 8th bit,
    bit 0 of byte 1 is the 9th bit, etc.
    """
    result = 0
    for i in range(count):
        byte_idx = (bit_offset + i) // 8
        bit_idx = (bit_offset + i) % 8
        if byte_idx < len(data) and (data[byte_idx] >> bit_idx) & 1:
            result |= 1 << i
    return result


class BitReader:
    """Simple LSB-first bit reader with position tracking."""

    def __init__(self, data: bytes, start_byte: int = 0) -> None:
        self.data = data
        self.bit_pos = start_byte * 8

    def read(self, count: int) -> int:
        value = read_bits_lsb(self.data, self.bit_pos, count)
        self.bit_pos += count
        return value

    @property
    def byte_pos(self) -> int:
        return self.bit_pos // 8

    @property
    def bit_offset_in_byte(self) -> int:
        return self.bit_pos % 8


# ============================================================
# STAT DECODER
# ============================================================


def decode_stats(
    raw_data: bytes,
    start_byte: int,
    use_bit_reversal: bool,
    label: str,
    max_stats: int = 30,
) -> tuple[dict[str, int | float], bool, int]:
    """Attempt to decode the stats section.

    Args:
        raw_data:         Full file bytes.
        start_byte:       Byte offset where stats data begins (835).
        use_bit_reversal: If True, reverse bits in each byte before reading.
        label:            Description for output ("reversed" or "normal").
        max_stats:        Safety limit to prevent infinite loops.

    Returns:
        Tuple of:
          - dict of stat_name -> value (raw integer, not fixed-point divided)
          - bool: True if terminated cleanly by 0x1FF
          - int: bit position where terminator was found (or -1)
    """
    # Extract just the stats region (generous slice)
    region = raw_data[start_byte : start_byte + 200]

    if use_bit_reversal:
        region = preprocess_reversed(region)

    reader = BitReader(region, start_byte=0)
    results: dict[str, int | float] = {}
    terminated_cleanly = False
    terminator_bit_pos = -1

    for _ in range(max_stats):
        # Read 9-bit stat ID
        stat_id = reader.read(9)

        if stat_id == STATS_TERMINATOR:
            terminated_cleanly = True
            terminator_bit_pos = reader.bit_pos - 9
            break

        if stat_id not in STAT_DEFS:
            # Unknown stat ID - record and continue reading minimum bits
            # to try to stay aligned. This indicates something is wrong.
            results[f"UNKNOWN_ID_{stat_id}"] = -1
            # We cannot continue reliably without knowing the bit width
            break

        name, csv_bits, save_add, is_fixed_point = STAT_DEFS[stat_id]
        raw_value = reader.read(csv_bits)
        display_value: int | float = raw_value - save_add

        if is_fixed_point:
            display_value = raw_value / 256.0

        results[name] = display_value

    return results, terminated_cleanly, terminator_bit_pos


# ============================================================
# DISPLAY HELPERS
# ============================================================


def print_section(title: str) -> None:
    print(f"\n{'=' * 60}")
    print(f"  {title}")
    print(f"{'=' * 60}")


def hex_dump_region(data: bytes, start: int, length: int) -> None:
    for row in range(0, length, 16):
        offset = start + row
        if offset >= len(data):
            break
        chunk = data[offset : offset + 16]
        hex_part = " ".join(f"{b:02X}" for b in chunk)
        ascii_part = "".join(chr(b) if 32 <= b < 127 else "." for b in chunk)
        print(f"  0x{offset:04X} ({offset:4d}d):  {hex_part:<48s}  |{ascii_part}|")


def compare_against_known(
    decoded: dict[str, int | float],
    tc_num: int,
    label: str,
) -> tuple[int, int]:
    """Compare decoded values against known TC values. Returns (matches, total)."""
    known = KNOWN_VALUES.get(tc_num, {})
    if not known:
        return 0, 0

    matches = 0
    total = 0

    print(f"\n  Comparison [{label}] vs TC{tc_num:02d} known values:")
    print(f"  {'Stat':<28} {'Expected':>10} {'Found':>12} {'Match'}")
    print(f"  {'-'*28} {'-'*10} {'-'*12} {'-'*5}")

    for stat_name, expected in known.items():
        total += 1
        found = decoded.get(stat_name)
        if found is None:
            print(f"  {stat_name:<28} {expected:>10} {'NOT FOUND':>12} [NO]")
        elif isinstance(found, float):
            # Fixed-point: compare integer part
            match = int(found) == expected
            symbol = "[OK]" if match else "[NO]"
            if match:
                matches += 1
            print(f"  {stat_name:<28} {expected:>10} {found:>12.3f} {symbol}")
        else:
            match = int(found) == expected
            symbol = "[OK]" if match else "[NO]"
            if match:
                matches += 1
            print(f"  {stat_name:<28} {expected:>10} {int(found):>12} {symbol}")

    print(f"\n  Score: {matches}/{total} correct")
    return matches, total


# ============================================================
# MAIN
# ============================================================


def main() -> int:
    if len(sys.argv) < 2:
        print("Usage: python verify_stats_section.py <path_to_d2s> [tc_number]")
        print("  tc_number: 1, 2, or 3 (enables comparison against known values)")
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
    print("  D2RR Toolkit: Stats Section Verification (VER-007)")
    print(f"  File: {path}  ({len(data)} bytes)")
    if tc_num:
        print(f"  Test Case: TC{tc_num:02d}")
    print("=" * 60)

    # Sanity check anchor
    if data[GF_OFFSET : GF_OFFSET + 2] != b"gf":
        print(f"\n  ERROR: 'gf' NOT at offset {GF_OFFSET}. Wrong file or version?")
        return 1
    print(f"\n  [BINARY_VERIFIED] 'gf' confirmed at offset {GF_OFFSET} - anchor OK")

    # --------------------------------------------------------
    # Raw bytes dump
    # --------------------------------------------------------
    print_section(f"RAW STATS BYTES (offset {STATS_DATA_START}, first 60 bytes)")
    hex_dump_region(data, STATS_DATA_START, 60)

    # --------------------------------------------------------
    # Show bit representation of first few bytes
    # --------------------------------------------------------
    print_section("BIT VIEW: First 6 bytes of stats data (two representations)")
    raw_slice = data[STATS_DATA_START : STATS_DATA_START + 6]
    rev_slice = preprocess_reversed(raw_slice)
    print("  Normal   (as-is):  ", end="")
    print(" ".join(f"{b:08b}" for b in raw_slice))
    print("  Reversed (flipped):", end="")
    print(" ".join(f"{b:08b}" for b in rev_slice))
    print()
    print(
        "  First 9 bits (normal,   LSB-first) = stat ID candidate: "
        f"{read_bits_lsb(bytes(raw_slice), 0, 9):3d}  (0x{read_bits_lsb(bytes(raw_slice), 0, 9):03X})"
    )
    print(
        "  First 9 bits (reversed, LSB-first) = stat ID candidate: "
        f"{read_bits_lsb(bytes(rev_slice), 0, 9):3d}  (0x{read_bits_lsb(bytes(rev_slice), 0, 9):03X})"
    )

    # --------------------------------------------------------
    # Attempt 1: WITH bit reversal (nokka/d2s method)
    # --------------------------------------------------------
    print_section("ATTEMPT 1: WITH bit-reversal per byte (nokka/d2s method) [SPEC_ONLY]")
    decoded_rev, clean_rev, term_pos_rev = decode_stats(
        data, STATS_DATA_START, use_bit_reversal=True, label="reversed"
    )
    print(f"  Terminated cleanly by 0x1FF: {'YES' if clean_rev else 'NO'}")
    if term_pos_rev >= 0:
        byte_pos = STATS_DATA_START + term_pos_rev // 8
        print(f"  Terminator at bit {term_pos_rev} " f"(byte offset in file: ~{byte_pos})")
    print(f"  Stats decoded: {len(decoded_rev)}")
    for name, val in decoded_rev.items():
        if isinstance(val, float):
            print(f"    {name:<28}: {val:.3f}  (raw*256={int(val*256)})")
        else:
            print(f"    {name:<28}: {val}")

    score_rev = (0, 0)
    if tc_num:
        score_rev = compare_against_known(decoded_rev, tc_num, "reversed")

    # --------------------------------------------------------
    # Attempt 2: WITHOUT bit reversal (plain LSB-first)
    # --------------------------------------------------------
    print_section("ATTEMPT 2: WITHOUT bit-reversal (plain LSB-first)")
    decoded_plain, clean_plain, term_pos_plain = decode_stats(
        data, STATS_DATA_START, use_bit_reversal=False, label="normal"
    )
    print(f"  Terminated cleanly by 0x1FF: {'YES' if clean_plain else 'NO'}")
    if term_pos_plain >= 0:
        byte_pos = STATS_DATA_START + term_pos_plain // 8
        print(f"  Terminator at bit {term_pos_plain} " f"(byte offset in file: ~{byte_pos})")
    print(f"  Stats decoded: {len(decoded_plain)}")
    for name, val in decoded_plain.items():
        if isinstance(val, float):
            print(f"    {name:<28}: {val:.3f}  (raw*256={int(val*256)})")
        else:
            print(f"    {name:<28}: {val}")

    score_plain = (0, 0)
    if tc_num:
        score_plain = compare_against_known(decoded_plain, tc_num, "normal")

    # --------------------------------------------------------
    # Verdict
    # --------------------------------------------------------
    print_section("VERDICT")
    if tc_num:
        rev_m, rev_t = score_rev
        plain_m, plain_t = score_plain
        print(f"  WITH reversal  : {rev_m}/{rev_t} matches, " f"clean terminator: {clean_rev}")
        print(
            f"  WITHOUT reversal: {plain_m}/{plain_t} matches, " f"clean terminator: {clean_plain}"
        )
        print()

        if rev_m > plain_m and clean_rev:
            print("  RESULT: Bit-reversal IS required. nokka/d2s is correct.")
            print("  -> Tag: [BINARY_VERIFIED] bit-reversal required for stats section")
        elif plain_m > rev_m and clean_plain:
            print("  RESULT: Bit-reversal is NOT required. Plain LSB-first works.")
            print("  -> Tag: [BINARY_VERIFIED] no bit-reversal needed for stats section")
        elif rev_m == plain_m:
            print("  RESULT: INCONCLUSIVE - both approaches give same score.")
            print("  -> Check clean terminator and individual values manually.")
            print("  -> Try running on other TC files for more data points.")
        else:
            print("  RESULT: NEITHER approach decoded cleanly.")
            print("  -> Stat bit widths in STAT_DEFS may be wrong for v105.")
            print("  -> Check ItemStatCost.txt CSvBits column for Reimagined mod.")
    else:
        print("  No TC number provided - cannot compare against known values.")
        print("  Re-run with tc_number argument: python ... <file> 1")

    print()
    print("  *** RECORD RESULT IN VERIFICATION_LOG.md VER-007 ***")
    print("  *** Include: which approach works, terminator position, ***")
    print("  ***          and the score from the comparison above    ***")

    return 0


if __name__ == "__main__":
    sys.exit(main())

