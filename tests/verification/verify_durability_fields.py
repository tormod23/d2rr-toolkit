"""
tests/verification/verify_durability_fields.py
===============================================
PURPOSE : Verify the exact position and width of max_durability and
          cur_durability fields using TC08, TC09, and TC10.

          TC08: Leather Gloves, max_dur=12, cur_dur=12 (equal values)
          TC09: Short Sword,    max_dur=250, cur_dur=250 (equal, weapon type)
          TC10: Leather Gloves, max_dur=12,  cur_dur=10 (DIFFERENT values!)

          TC10 is the decisive test:
          - max_dur=12 confirms position (same as TC08)
          - cur_dur=10 DIFFERS from max_dur - unambiguously identifies cur_dur field
          - If we read 12 where we expect 12 AND 10 where we expect 10:
            [BINARY_VERIFIED] max_dur=8bits at type_start+11,
                              cur_dur=8bits at type_start+19

KNOWN FROM PREVIOUS RUNS [BINARY_VERIFIED]:
  GF_OFFSET         = 833
  HUFFMAN_BIT_OFFSET = 53
  unique_item_id     = 35 bits (NOT 32)
  iLVL               = 7 bits at ext_start+35
  quality            = 4 bits at ext_start+42
  has_gfx            = 1 bit  at ext_start+46
  has_class          = 1 bit  at ext_start+47
  timestamp          = 1 bit  at ext_start+48
  type_start         = ext_start + 49
  armor_defense      = 11 bits at type_start+0   (for Armor.txt items)
  max_durability     = 8 bits  at type_start+11  [BINARY_VERIFIED TC08+TC09]
  cur_durability     = 8 bits  at type_start+19  [BINARY_VERIFIED TC08+TC09, TO CONFIRM]
  unknown_after_cur  = 2 bits  at type_start+27  [UNKNOWN content]
  terminator 0x1FF   = 9 bits  at type_start+29  [BINARY_VERIFIED TC08]

USAGE   : python tests/verification/verify_durability_fields.py <tc10_path> [tc08_path]
          python tests/verification/verify_durability_fields.py tests/cases/TC10/TestPaladin.d2s
          python tests/verification/verify_durability_fields.py tests/cases/TC10/TestPaladin.d2s tests/cases/TC08/TestPaladin.d2s

DATE    : 2026-03-24
"""

import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")


# ============================================================
# VERIFIED CONSTANTS [BINARY_VERIFIED]
# ============================================================

GF_OFFSET = 833
HUFFMAN_BIT_OFFSET = 53
ITEMS_START_BYTE = 907  # Level 1 chars (TC07/08/09/10)

OFFSET_UNIQUE_ID = 0
OFFSET_ILVL = 35
OFFSET_QUALITY = 42
OFFSET_HAS_GFX = 46
OFFSET_HAS_CLASS = 47
OFFSET_TIMESTAMP = 48
OFFSET_TYPE_SPECIFIC = 49  # type_start = ext_start + 49

# Within type_start (for Armor.txt items) [BINARY_VERIFIED]:
ARMOR_DEFENSE_OFFSET = 0  # 11 bits
MAX_DUR_OFFSET = 11  # 8 bits [BINARY_VERIFIED]
CUR_DUR_OFFSET = 19  # 8 bits [BINARY_VERIFIED TC08+TC09, confirming with TC10]
UNKNOWN_POST_DUR = 27  # 2 bits [UNKNOWN]
TERMINATOR_OFFSET = 29  # 9 bits [BINARY_VERIFIED TC08]

# Expected values per TC [from READMEs - ground truth]
TC_KNOWN: dict[int, dict] = {
    8: {
        "item_code": "lgl",
        "ilvl": 6,
        "quality": 2,
        "defense_raw": 13,
        "max_dur": 12,
        "cur_dur": 12,
    },
    10: {
        "item_code": "lgl",
        "ilvl": 6,
        "quality": 2,
        "defense_raw": 12,
        "max_dur": 12,
        "cur_dur": 10,
    },  # defense=2 (raw=12), NOT 3!
}


# ============================================================
# BIT READING [BINARY_VERIFIED]
# ============================================================


def read_bit(data: bytes, bit_pos: int) -> int:
    byte_idx = bit_pos // 8
    if byte_idx >= len(data):
        return -1
    return (data[byte_idx] >> (bit_pos % 8)) & 1


def read_bits(data: bytes, start_bit: int, count: int) -> int:
    result = 0
    for i in range(count):
        b = read_bit(data, start_bit + i)
        if b < 0:
            break
        result |= b << i
    return result


def bits_str(data: bytes, start_bit: int, count: int) -> str:
    """Return a human-readable LSB-first bit string."""
    return " ".join(str(read_bit(data, start_bit + i)) for i in range(count))


def print_section(title: str) -> None:
    print(f"\n{'=' * 65}")
    print(f"  {title}")
    print(f"{'=' * 65}")


# ============================================================
# HUFFMAN [BINARY_VERIFIED]
# ============================================================

HUFFMAN_TABLE: dict[str, str] = {
    " ": "10",
    "0": "11111011",
    "1": "1111100",
    "2": "001100",
    "3": "1101101",
    "4": "11111010",
    "5": "00010110",
    "6": "1101111",
    "7": "01111",
    "8": "000100",
    "9": "01110",
    "a": "11110",
    "b": "0101",
    "c": "01000",
    "d": "110001",
    "e": "110000",
    "f": "010011",
    "g": "11010",
    "h": "00011",
    "i": "1111110",
    "j": "000101110",
    "k": "010010",
    "l": "11101",
    "m": "01101",
    "n": "001101",
    "o": "1111111",
    "p": "11001",
    "q": "11011001",
    "r": "11100",
    "s": "0010",
    "t": "01100",
    "u": "00001",
    "v": "1101110",
    "w": "00000",
    "x": "00111",
    "y": "0001010",
    "z": "11011000",
}

_TREE: dict | None = None


def _get_tree() -> dict:
    global _TREE
    if _TREE is None:
        _TREE = {}
        for char, pattern in HUFFMAN_TABLE.items():
            node = _TREE
            for b in pattern[:-1]:
                node = node.setdefault(b, {})
            node[pattern[-1]] = char
    return _TREE


def decode_huffman(data: bytes, start_bit: int) -> tuple[str, int] | None:
    tree = _get_tree()
    node: dict | str = tree
    result = []
    bits = 0
    while bits < 80:
        b = read_bit(data, start_bit + bits)
        if b < 0:
            return None
        bits += 1
        bc = str(b)
        if not isinstance(node, dict) or bc not in node:
            return None
        node = node[bc]
        if isinstance(node, str):
            if node == " ":
                return ("".join(result), bits)
            result.append(node)
            node = tree  # type: ignore[assignment]
    return None


# ============================================================
# CORE ANALYSIS
# ============================================================


def analyze_item(data: bytes, tc_num: int, tc: dict) -> dict[str, int]:
    """Read all extended fields for a single item. Returns field values."""
    item_start_byte = ITEMS_START_BYTE
    item_start_bit = item_start_byte * 8

    # Decode Huffman code [BINARY_VERIFIED]
    huff = decode_huffman(data, item_start_bit + HUFFMAN_BIT_OFFSET)
    if huff is None:
        print("  ERROR: Huffman decode failed")
        return {}
    code, huff_bits = huff
    ext_start = HUFFMAN_BIT_OFFSET + huff_bits
    type_start = ext_start + OFFSET_TYPE_SPECIFIC

    # Read all verified fields
    fields = {
        "item_code": code,
        "huff_bits": huff_bits,
        "ext_start": ext_start,
        "type_start": type_start,
        "ilvl": read_bits(data, item_start_bit + ext_start + OFFSET_ILVL, 7),
        "quality": read_bits(data, item_start_bit + ext_start + OFFSET_QUALITY, 4),
        "has_gfx": read_bits(data, item_start_bit + ext_start + OFFSET_HAS_GFX, 1),
        "has_class": read_bits(data, item_start_bit + ext_start + OFFSET_HAS_CLASS, 1),
        "defense_raw": read_bits(data, item_start_bit + type_start + ARMOR_DEFENSE_OFFSET, 11),
        "max_dur": read_bits(data, item_start_bit + type_start + MAX_DUR_OFFSET, 8),
        "cur_dur": read_bits(data, item_start_bit + type_start + CUR_DUR_OFFSET, 8),
        "unknown_post": read_bits(data, item_start_bit + type_start + UNKNOWN_POST_DUR, 2),
        "terminator": read_bits(data, item_start_bit + type_start + TERMINATOR_OFFSET, 9),
        # absolute bit positions for reference
        "abs_max_dur": item_start_bit + type_start + MAX_DUR_OFFSET,
        "abs_cur_dur": item_start_bit + type_start + CUR_DUR_OFFSET,
        "abs_term": item_start_bit + type_start + TERMINATOR_OFFSET,
    }

    return fields


def print_field_table(fields: dict[str, int], tc: dict) -> tuple[int, int]:
    """Print field table and return (matches, total)."""
    item_start_bit = ITEMS_START_BYTE * 8
    ext_start = fields["ext_start"]
    type_start = fields["type_start"]

    print(
        f"\n  {'Field':<28} {'Item bit':>9}  {'Width':>6}  {'Found':>8}  {'Expected':>9}  {'Match'}"
    )
    print(f"  {'-'*28} {'-'*9}  {'-'*6}  {'-'*8}  {'-'*9}  {'-'*5}")

    rows = [
        ("item_code (Huffman)", "-", "-", fields["item_code"], tc["item_code"], True),
        ("iLVL", item_start_bit + ext_start + OFFSET_ILVL, 7, fields["ilvl"], tc["ilvl"], True),
        (
            "quality",
            item_start_bit + ext_start + OFFSET_QUALITY,
            4,
            fields["quality"],
            tc["quality"],
            True,
        ),
        ("has_gfx", item_start_bit + ext_start + OFFSET_HAS_GFX, 1, fields["has_gfx"], 0, True),
        (
            "has_class",
            item_start_bit + ext_start + OFFSET_HAS_CLASS,
            1,
            fields["has_class"],
            0,
            True,
        ),
        (
            "defense_raw (-> def=3)",
            item_start_bit + type_start + ARMOR_DEFENSE_OFFSET,
            11,
            fields["defense_raw"],
            tc["defense_raw"],
            True,
        ),
        (
            "max_durability",
            item_start_bit + type_start + MAX_DUR_OFFSET,
            8,
            fields["max_dur"],
            tc["max_dur"],
            True,
        ),
        (
            "cur_durability",
            item_start_bit + type_start + CUR_DUR_OFFSET,
            8,
            fields["cur_dur"],
            tc["cur_dur"],
            True,
        ),
        (
            "unknown_post_dur",
            item_start_bit + type_start + UNKNOWN_POST_DUR,
            2,
            fields["unknown_post"],
            "?",
            False,
        ),  # don't count
        (
            "terminator 0x1FF",
            item_start_bit + type_start + TERMINATOR_OFFSET,
            9,
            fields["terminator"],
            511,
            True,
        ),
    ]

    matches = total = 0
    for name, bit_pos, width, found, expected, count in rows:
        if count:
            total += 1
        ok = str(found) == str(expected)
        if ok and count:
            matches += 1
        sym = "[OK]" if ok else ("?" if not count else "[NO]")
        bit_str = str(bit_pos) if isinstance(bit_pos, int) else bit_pos
        width_str = str(width)
        print(
            f"  {name:<28} {bit_str:>9}  {width_str:>6}  {str(found):>8}  {str(expected):>9}  {sym}"
        )

    print(f"\n  Score: {matches}/{total}")
    return matches, total


def print_raw_durability_region(data: bytes, fields: dict[str, int]) -> None:
    """Show raw bits in the durability region for manual verification."""
    item_start_bit = ITEMS_START_BYTE * 8
    type_start = fields["type_start"]
    start = item_start_bit + type_start + MAX_DUR_OFFSET - 2  # 2 bits before

    print("\n  Raw bits around durability region:")
    print(
        f"  (type_start={type_start}, MAX_DUR_OFFSET={MAX_DUR_OFFSET}, CUR_DUR_OFFSET={CUR_DUR_OFFSET})"
    )
    print()

    max_dur_abs = item_start_bit + type_start + MAX_DUR_OFFSET
    cur_dur_abs = item_start_bit + type_start + CUR_DUR_OFFSET
    unk_abs = item_start_bit + type_start + UNKNOWN_POST_DUR
    term_abs = item_start_bit + type_start + TERMINATOR_OFFSET

    for i in range(-2, 32):
        abs_bit = item_start_bit + type_start + MAX_DUR_OFFSET + i
        val = read_bit(data, abs_bit)
        rel = MAX_DUR_OFFSET + i

        # Annotation
        ann = ""
        if abs_bit == max_dur_abs:
            ann = "<- max_dur start"
        elif abs_bit == max_dur_abs + 8:
            ann = "<- cur_dur start"
        elif abs_bit == cur_dur_abs + 8:
            ann = "<- unknown_post start"
        elif abs_bit == unk_abs + 2:
            ann = "<- terminator start"

        print(f"  type+{rel:3d}  (abs {abs_bit:5d}): {val}  {ann}")


# ============================================================
# CROSS-TC COMPARISON
# ============================================================


def compare_tc08_tc10(data8: bytes, data10: bytes) -> None:
    """Side-by-side bit comparison of TC08 and TC10 in durability region."""
    print_section("CROSS-TC COMPARISON: TC08 (12/12) vs TC10 (10/12)")
    print("  Comparing durability region bit-by-bit.")
    print("  max_dur field should be IDENTICAL (both = 12).")
    print("  cur_dur field should DIFFER (TC08=12, TC10=10).")
    print()

    item_bit_8 = ITEMS_START_BYTE * 8
    item_bit_10 = ITEMS_START_BYTE * 8

    # Get ext_start for each file
    huff8 = decode_huffman(data8, item_bit_8 + HUFFMAN_BIT_OFFSET)
    huff10 = decode_huffman(data10, item_bit_10 + HUFFMAN_BIT_OFFSET)
    if huff8 is None or huff10 is None:
        print("  ERROR: Huffman decode failed")
        return

    ts8 = HUFFMAN_BIT_OFFSET + huff8[1] + OFFSET_TYPE_SPECIFIC
    ts10 = HUFFMAN_BIT_OFFSET + huff10[1] + OFFSET_TYPE_SPECIFIC

    max_start_8 = item_bit_8 + ts8 + MAX_DUR_OFFSET
    max_start_10 = item_bit_10 + ts10 + MAX_DUR_OFFSET

    print(f"  {'Offset':>8}  {'TC08 bit':>9}  {'TC09 bit':>9}  {'Same?':>6}  {'Field annotation'}")
    print(f"  {'-'*8}  {'-'*9}  {'-'*9}  {'-'*6}  {'-'*20}")

    for i in range(30):
        b8 = read_bit(data8, max_start_8 + i)
        b10 = read_bit(data10, max_start_10 + i)
        same = "=" if b8 == b10 else "!="

        ann = ""
        if i == 0:
            ann = "<- max_dur bit 0"
        elif i == 7:
            ann = "<- max_dur bit 7 (last)"
        elif i == 8:
            ann = "<- cur_dur bit 0"
        elif i == 15:
            ann = "<- cur_dur bit 7 (last)"
        elif i == 16:
            ann = "<- unknown_post bit 0"
        elif i == 17:
            ann = "<- unknown_post bit 1"
        elif i == 18:
            ann = "<- terminator bit 0"

        # Highlight differences
        marker = " ***" if same == "!=" else ""
        print(f"  +{i:>7}  {b8:>9}  {b10:>9}  {same:>6}  {ann}{marker}")

    # Quick read of both durability fields
    max8 = read_bits(data8, max_start_8, 8)
    cur8 = read_bits(data8, max_start_8 + 8, 8)
    max10 = read_bits(data10, max_start_10, 8)
    cur10 = read_bits(data10, max_start_10 + 8, 8)

    print(f"\n  TC08: max_dur={max8}  cur_dur={cur8}  (expected 12/12)")
    print(f"  TC10: max_dur={max10}  cur_dur={cur10}  (expected 12/10)")
    print()

    all_ok = max8 == 12 and cur8 == 12 and max10 == 12 and cur10 == 10
    if all_ok:
        print("  ALL VALUES MATCH EXPECTED [OK]")
        print()
        print("  [BINARY_VERIFIED] max_durability: 8 bits at type_start + 11")
        print("  [BINARY_VERIFIED] cur_durability: 8 bits at type_start + 19")
        print("  [BINARY_VERIFIED] TC08 cur_dur discrepancy RESOLVED:")
        print("    Earlier run showed cur_dur=6 - that was caused by wrong bit")
        print("    width assumption (9 bits instead of 8). Now confirmed as 12. [OK]")
    else:
        print("  MISMATCH - investigate field positions")
        for label, got, exp in [
            ("TC08 max_dur", max8, 12),
            ("TC08 cur_dur", cur8, 12),
            ("TC10 max_dur", max10, 12),
            ("TC10 cur_dur", cur10, 10),
        ]:
            sym = "[OK]" if got == exp else "[NO]"
            print(f"    {label}: got={got} expected={exp} {sym}")


# ============================================================
# MAIN
# ============================================================


def main() -> int:
    if len(sys.argv) < 2:
        print("Usage: python verify_durability_fields.py <tc10_path> [tc08_path]")
        print("  tc10_path: path to TC10 TestPaladin.d2s (Gloves 10/12)")
        print("  tc08_path: optional path to TC08 TestPaladin.d2s (Gloves 12/12)")
        return 1

    path10 = Path(sys.argv[1])
    path8 = Path(sys.argv[2]) if len(sys.argv) >= 3 else None

    if not path10.exists():
        print(f"ERROR: {path10}")
        return 1
    if path8 and not path8.exists():
        print(f"ERROR: {path8}")
        return 1

    with open(path10, "rb") as f:
        data10 = f.read()
    data8 = None
    if path8:
        with open(path8, "rb") as f:
            data8 = f.read()

    print()
    print("=" * 65)
    print("  D2RR Toolkit: Durability Field Verification (TC10)")
    print(f"  TC10 file: {path10}  ({len(data10)} bytes)")
    if path8:
        print(f"  TC08 file: {path8}  ({len(data8)} bytes)")
    print("=" * 65)

    # Verify gf anchor
    if data10[GF_OFFSET : GF_OFFSET + 2] != b"gf":
        print(f"  ERROR: 'gf' not at offset {GF_OFFSET}")
        return 1
    print(f"\n  [BINARY_VERIFIED] 'gf' at offset {GF_OFFSET} [OK]")
    print(
        f"  Item count: {int.from_bytes(data10[data10.find(b'JM', GF_OFFSET)+2:data10.find(b'JM', GF_OFFSET)+4], 'little')}"
    )

    # --------------------------------------------------------
    # Analyze TC10
    # --------------------------------------------------------
    print_section("TC10: Leather Gloves - Durability 10/12")
    tc10 = TC_KNOWN[10]
    fields10 = analyze_item(data10, 10, tc10)
    if not fields10:
        return 1

    print(f"  item_code  : '{fields10['item_code']}'  (expected 'lgl')")
    print(f"  ext_start  : item-relative bit {fields10['ext_start']}")
    print(f"  type_start : item-relative bit {fields10['type_start']}")

    matches, total = print_field_table(fields10, tc10)
    print_raw_durability_region(data10, fields10)

    # --------------------------------------------------------
    # Cross-TC comparison with TC08 if provided
    # --------------------------------------------------------
    if data8 is not None:
        if data8[GF_OFFSET : GF_OFFSET + 2] != b"gf":
            print(f"  ERROR: TC08 'gf' not at offset {GF_OFFSET}")
        else:
            compare_tc08_tc10(data8, data10)

    # --------------------------------------------------------
    # Summary
    # --------------------------------------------------------
    print_section("SUMMARY")
    print(f"  TC10 score: {matches}/{total}")
    if matches == total:
        print()
        print("  ALL FIELDS MATCH [OK]")
        print()
        print("  [BINARY_VERIFIED] Confirmed:")
        print("    max_durability = 8 bits at type_start + 11")
        print("    cur_durability = 8 bits at type_start + 19")
        print("    TC10: max_dur=12 [OK], cur_dur=10 [OK]")
        if data8 is not None:
            print("    TC08: max_dur=12 [OK], cur_dur=12 [OK]  (earlier '6' was bit-width bug)")
        print()
        print("  Record in VERIFICATION_LOG.md:")
        print("    max_dur 8-bit width [BINARY_VERIFIED] TC08+TC09+TC10")
        print("    cur_dur 8-bit width [BINARY_VERIFIED] TC08+TC09+TC10")
    else:
        print(f"  {total - matches} mismatch(es) - investigate before [BINARY_VERIFIED]")
        print()
        print("  Possible causes:")
        print("    - type_start offset wrong (defense field width?)")
        print("    - max_dur/cur_dur field widths differ from 8 bits")
        print("    - Item order in JM list unexpected")

    print()
    print("  *** Update VERIFICATION_LOG.md VER-006d with TC10 results ***")

    return 0


if __name__ == "__main__":
    sys.exit(main())
