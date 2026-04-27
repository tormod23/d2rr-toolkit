"""
tests/verification/verify_extended_item_diagnostic.py
======================================================
PURPOSE : Diagnose the extended item structure after the Huffman code.
          Specifically resolves the cur_durability discrepancy found in TC08.

VERSION : 2 - Added TC09 (Short Sword, Durability 250/250)

KNOWN FROM PREVIOUS RUNS [BINARY_VERIFIED]:
  - Huffman code starts at item-relative bit 53
  - unique_item_id = 35 bits (NOT 32 as spec stated)
  - iLVL = 7 bits
  - quality = 4 bits
  - has_custom_graphics = 1 bit
  - has_class_specific_data = 1 bit
  - timestamp_unknown_bit = 1 bit
  - For Armor.txt items: armor_defense = 11 bits (raw, subtract Save Add=10)
  - max_durability = 9 bits
  - terminator 0x1FF = 9 bits (confirmed position)

OPEN QUESTION (TC08 discrepancy):
  TC08: Leather Gloves, max_dur=12 [OK], cur_dur=6 [NO] (expected 12)
  Hypothesis A: cur_durability has an extra bit before it (10 bits not 9)
  Hypothesis B: there is a 1-bit gap between max_dur and cur_dur
  Hypothesis C: cur_durability uses a different bit width
  TC09 (Short Sword, 250/250) will resolve this.

ADDITIONAL QUESTION (TC09):
  Short Sword is in Weapons.txt, NOT Armor.txt.
  Does it have a defense field? Probably not.
  Does it have min_damage/max_damage fields instead? Maybe.
  We use 250/250 as a distinctive binary pattern to find dur fields precisely.

USAGE   : python tests/verification/verify_extended_item_diagnostic.py <path.d2s> [tc]
          tc: 8 or 9
          python ... tests/cases/TC08/TestPaladin.d2s 8
          python ... tests/cases/TC09/TestPaladin.d2s 9

DATE    : 2026-03-24
"""

import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")


# ============================================================
# VERIFIED CONSTANTS [BINARY_VERIFIED]
# ============================================================

GF_OFFSET = 833  # [BINARY_VERIFIED]
HUFFMAN_BIT_OFFSET = 53  # [BINARY_VERIFIED]
UNIQUE_ID_BITS = 35  # [BINARY_VERIFIED] NOT 32!
ITEMS_START_BYTE = 907  # [BINARY_VERIFIED] for Level 1 chars (TC07/08/09)

# Field offsets from ext_start [BINARY_VERIFIED]
OFFSET_UNIQUE_ID = 0
OFFSET_ILVL = 35  # [BINARY_VERIFIED]
OFFSET_QUALITY = 42  # [BINARY_VERIFIED]
OFFSET_HAS_GFX = 46  # [BINARY_VERIFIED]
OFFSET_HAS_CLASS = 47  # [BINARY_VERIFIED]
OFFSET_TIMESTAMP = 48  # [BINARY_VERIFIED]
OFFSET_TYPE_FIELDS = 49  # [BINARY_VERIFIED] type-specific data starts here

# Known TC values [from READMEs - ground truth]
TC_KNOWN: dict[int, dict] = {
    8: {
        "description": "Leather Gloves [N] iLVL=6, Def=3, Dur=12/12",
        "item_code": "lgl",
        "ilvl": 6,
        "quality": 2,
        "item_type": "armor",  # in Armor.txt
        "defense_raw": 13,  # 3 displayed + 10 Save Add
        "max_dur": 12,
        "cur_dur": 12,  # TC08 showed 6 - DISCREPANCY TO RESOLVE
    },
    9: {
        "description": "Short Sword [N] iLVL=6, Dur=250/250",
        "item_code": "9ss",
        "ilvl": 6,
        "quality": 2,
        "item_type": "weapon",  # in Weapons.txt - NO defense field!
        "defense_raw": None,  # weapons don't have armor defense
        "max_dur": 250,
        "cur_dur": 250,  # distinctive value for easy identification
    },
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


def print_section(title: str) -> None:
    print(f"\n{'=' * 65}")
    print(f"  {title}")
    print(f"{'=' * 65}")


# ============================================================
# HUFFMAN DECODER [BINARY_VERIFIED]
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
# CORE ANALYSIS FUNCTIONS
# ============================================================


def dump_region(
    data: bytes, item_start_bit: int, from_bit: int, to_bit: int, label: str = ""
) -> None:
    """Dump a region of bits relative to item_start_bit."""
    if label:
        print(f"  {label}")
    for row_start in range(from_bit, to_bit, 8):
        chunk_end = min(row_start + 8, to_bit)
        bits = [
            read_bit(data, item_start_bit + row_start + i) for i in range(chunk_end - row_start)
        ]
        bits_str = " ".join(str(b) for b in bits)
        uint_val = sum(b << i for i, b in enumerate(bits))
        print(f"  item bit {row_start:3d}-{chunk_end-1:3d}: {bits_str:<24}  (uint={uint_val:3d})")


def search_value(
    data: bytes,
    item_start_bit: int,
    value: int,
    bit_width: int,
    search_from: int,
    search_to: int,
    label: str,
) -> list[int]:
    """Search for a specific value in a bit range. Returns list of matching positions."""
    matches = []
    print(
        f"\n  Searching for {label}={value} ({bit_width}-bit) in item bits {search_from}-{search_to}:"
    )
    for pos in range(search_from, search_to - bit_width + 1):
        val = read_bits(data, item_start_bit + pos, bit_width)
        if val == value:
            print(f"    Found at item-relative bit {pos}  [OK]")
            matches.append(pos)
    if not matches:
        print(f"    NOT FOUND in range {search_from}-{search_to}")
    return matches


def find_terminator(
    data: bytes, item_start_bit: int, search_from: int, search_to: int
) -> list[int]:
    """Find 0x1FF (9-bit all-ones) terminator positions."""
    matches = []
    print(f"\n  Searching for 0x1FF terminator (9-bit=511) in item bits {search_from}-{search_to}:")
    for pos in range(search_from, search_to):
        val = read_bits(data, item_start_bit + pos, 9)
        if val == 0x1FF:
            print(f"    Terminator at item-relative bit {pos}  [OK]")
            matches.append(pos)
    return matches


# ============================================================
# TC08 ANALYSIS: Durability discrepancy investigation
# ============================================================


def analyze_tc08_durability(data: bytes, item_start_bit: int, ext_start: int, tc: dict) -> None:
    """Investigate why cur_dur=6 instead of 12 in TC08."""
    print_section("TC08 Durability Discrepancy Investigation")
    print("  Known from TC08 [BINARY_VERIFIED]:")
    print(f"    max_dur=12 at item bit {ext_start + OFFSET_TYPE_FIELDS + 11}")
    print(f"    terminator at item bit {ext_start + OFFSET_TYPE_FIELDS + 11 + 9 + 9}")
    print()

    # defense field end: ext_start + 49 + 11 = ext_start + 60
    # max_dur: ext_start + 60, 9 bits
    # cur_dur: should be ext_start + 69, 9 bits
    # terminator: should be ext_start + 78, 9 bits

    type_start = ext_start + OFFSET_TYPE_FIELDS  # [BINARY_VERIFIED]

    # For TC08 (armor): defense is 11 bits first
    defense_end = type_start + 11  # after 11-bit defense
    max_dur_start = defense_end  # immediately after

    max_dur_val = read_bits(data, item_start_bit + max_dur_start, 9)
    print(
        f"  max_durability at item bit {max_dur_start}: {max_dur_val}  "
        f"{'[OK]' if max_dur_val == tc['max_dur'] else '[NO]'}"
    )

    print("\n  Testing cur_durability with various widths and gaps:")
    print(
        f"  {'Gap':>5}  {'Width':>6}  {'Start bit':>10}  {'Value':>8}  {'= 12?':>6}  {'Terminator?':>12}"
    )
    print(f"  {'-'*5}  {'-'*6}  {'-'*10}  {'-'*8}  {'-'*6}  {'-'*12}")

    for gap in range(0, 4):
        for width in range(8, 11):
            cur_start = max_dur_start + 9 + gap
            cur_val = read_bits(data, item_start_bit + cur_start, width)
            term_start = cur_start + width
            term_val = read_bits(data, item_start_bit + term_start, 9)
            ok = cur_val == tc["cur_dur"]
            term_ok = term_val == 0x1FF
            print(
                f"  {gap:>5}  {width:>6}  {cur_start:>10}  {cur_val:>8}  "
                f"{'[OK]' if ok else '[NO]':>6}  {'[OK] 0x1FF' if term_ok else str(term_val):>12}"
            )

    # Also: raw bit dump of the durability region
    print()
    print(f"  Raw bits around durability region (max_dur_start={max_dur_start}):")
    dump_region(data, item_start_bit, max_dur_start, max_dur_start + 30)


# ============================================================
# TC09 ANALYSIS: Short Sword with Durability 250/250
# ============================================================


def analyze_tc09(data: bytes, item_start_bit: int, ext_start: int, tc: dict) -> None:
    """Use 250/250 durability to precisely locate durability fields."""
    print_section("TC09 PRIMARY: Durability Field Location with value 250")
    print("  Expected: max_dur=250, cur_dur=250")
    print(
        f"  250 in binary (9-bit LSB-first): " f"{''.join(str((250 >> i) & 1) for i in range(9))}"
    )
    print("  250 = 0xFA = 0b11111010")
    print()

    # First: search for 250 as a 9-bit value in a wide range
    matches_250 = search_value(
        data,
        item_start_bit,
        250,
        9,
        search_from=ext_start + 35,  # after unique_id
        search_to=ext_start + 120,
        label="dur=250",
    )

    if matches_250:
        print(f"\n  Found {len(matches_250)} occurrence(s) of value 250 (9-bit):")
        for pos in matches_250:
            # Check if the next 9 bits are also 250
            next_val = read_bits(data, item_start_bit + pos + 9, 9)
            print(
                f"    item bit {pos}: val=250, next-9-bits={next_val} "
                f"{'<- BOTH 250! max+cur found!' if next_val == 250 else ''}"
            )

    # Search for terminator near expected location
    find_terminator(data, item_start_bit, search_from=ext_start + 60, search_to=ext_start + 130)

    # Now: since Short Sword is in Weapons.txt (NOT Armor.txt),
    # it should NOT have a defense field.
    # Structure after timestamp bit should be:
    #   [SPEC_ONLY] max_durability (9 bits)
    #   [SPEC_ONLY] cur_durability (9 bits)
    #   [SPEC_ONLY] terminator 0x1FF (if no magical properties)

    print_section("TC09: Testing Weapons.txt item structure (no defense field)")
    print("  [SPEC_ONLY] Weapons have no armor_defense field.")
    print(
        f"  Type-specific fields start at ext_start + {OFFSET_TYPE_FIELDS} = "
        f"item bit {ext_start + OFFSET_TYPE_FIELDS}"
    )
    print()

    type_start = ext_start + OFFSET_TYPE_FIELDS

    print(f"  {'Description':<40} {'Bit':>5}  {'Value':>8}  {'= 250?':>7}")
    print(f"  {'-'*40} {'-'*5}  {'-'*8}  {'-'*7}")

    # Hypothesis 1: max_dur immediately at type_start (no defense for weapons)
    for offset in range(0, 20):
        max_d = read_bits(data, item_start_bit + type_start + offset, 9)
        cur_d = read_bits(data, item_start_bit + type_start + offset + 9, 9)
        term = read_bits(data, item_start_bit + type_start + offset + 18, 9)
        if max_d == 250:
            print(
                f"  max_dur at type_start+{offset:<3}                       "
                f"{type_start+offset:>5}  {max_d:>8}  {'[OK]' if max_d==250 else '[NO]':>7}"
            )
            print(
                f"    cur_dur (+9):                              "
                f"{type_start+offset+9:>5}  {cur_d:>8}  {'[OK]' if cur_d==250 else '[NO]':>7}"
            )
            print(
                f"    terminator (+18):                          "
                f"{type_start+offset+18:>5}  {term:>8}  "
                f"{'[OK] 0x1FF' if term==0x1FF else '[NO]':>7}"
            )
            print()

    # Wide raw dump of type-specific region
    print(f"  Raw bits of type-specific region (type_start={type_start} to +40):")
    dump_region(data, item_start_bit, type_start, type_start + 40)


# ============================================================
# CROSS-TC COMPARISON
# ============================================================


def cross_tc_comparison(
    data8: bytes,
    data9: bytes,
    item_start_bit_8: int,
    item_start_bit_9: int,
    ext_start_8: int,
    ext_start_9: int,
) -> None:
    """Compare TC08 and TC09 bit-by-bit in the type-specific region."""
    print_section("CROSS-TC COMPARISON: Durability region TC08 vs TC09")
    print(f"  Comparing item bits from ext_start + {OFFSET_TYPE_FIELDS} onward.")
    print("  TC08: Leather Gloves (Armor) - max_dur=12, cur_dur=12")
    print("  TC09: Short Sword (Weapon)   - max_dur=250, cur_dur=250")
    print()
    print(f"  {'offset':>8}  {'TC08 bit':>9}  {'TC09 bit':>9}  {'same?':>6}")
    print(f"  {'-'*8}  {'-'*9}  {'-'*9}  {'-'*6}")

    type_start_8 = ext_start_8 + OFFSET_TYPE_FIELDS
    type_start_9 = ext_start_9 + OFFSET_TYPE_FIELDS

    for i in range(60):
        b8 = read_bit(data8, item_start_bit_8 + type_start_8 + i)
        b9 = read_bit(data9, item_start_bit_9 + type_start_9 + i)
        same = "=" if b8 == b9 else "!="
        print(f"  +{i:>7}  {b8:>9}  {b9:>9}  {same:>6}")


# ============================================================
# MAIN
# ============================================================


def main() -> int:
    if len(sys.argv) < 2:
        print("Usage: python verify_extended_item_diagnostic.py <path.d2s> [tc]")
        print("  tc: 8 or 9")
        print("  For cross-TC comparison: provide TC08 path as first arg and TC09 as second")
        return 1

    paths = [Path(sys.argv[1])]
    if len(sys.argv) >= 3 and sys.argv[2] not in ("8", "9"):
        # Second arg might be a second file path
        paths.append(Path(sys.argv[2]))
        tc_num = int(sys.argv[3]) if len(sys.argv) >= 4 else None
    else:
        tc_num = int(sys.argv[2]) if len(sys.argv) >= 3 else None

    print()
    print("=" * 65)
    print("  TC08/TC09 Extended Item Diagnostic v2 - Durability Investigation")
    print("=" * 65)

    # Load files
    all_data: dict[int, bytes] = {}
    if len(paths) == 1:
        with open(paths[0], "rb") as f:
            data = f.read()
        print(f"\n  File: {paths[0]}  ({len(data)} bytes)")
        if tc_num:
            all_data[tc_num] = data
        else:
            print("  ERROR: please specify tc number (8 or 9)")
            return 1
    else:
        # Two files: assume TC08 and TC09
        with open(paths[0], "rb") as f:
            all_data[8] = f.read()
        with open(paths[1], "rb") as f:
            all_data[9] = f.read()
        print(f"\n  TC08 file: {paths[0]}  ({len(all_data[8])} bytes)")
        print(f"  TC09 file: {paths[1]}  ({len(all_data[9])} bytes)")

    # Process each TC
    ext_starts: dict[int, int] = {}
    item_start_bits: dict[int, int] = {}

    for tc, data in all_data.items():
        tc_info = TC_KNOWN[tc]
        print_section(f"TC{tc:02d}: {tc_info['description']}")

        # Verify gf anchor
        if data[GF_OFFSET : GF_OFFSET + 2] != b"gf":
            print(f"  ERROR: 'gf' not at offset {GF_OFFSET}")
            continue
        print(f"  [BINARY_VERIFIED] 'gf' at offset {GF_OFFSET} [OK]")

        item_start_byte = ITEMS_START_BYTE
        item_start_bit = item_start_byte * 8
        item_start_bits[tc] = item_start_bit

        # Decode Huffman
        huff = decode_huffman(data, item_start_bit + HUFFMAN_BIT_OFFSET)
        if huff is None:
            print("  ERROR: Huffman decode failed")
            continue
        code, huff_bits = huff
        print(f"  Item code: '{code}'  ({huff_bits} bits)")
        if code != tc_info["item_code"]:
            print(f"  WARNING: Expected '{tc_info['item_code']}', got '{code}'")

        ext_start = HUFFMAN_BIT_OFFSET + huff_bits
        ext_starts[tc] = ext_start
        print(f"  ext_start: item-relative bit {ext_start}")

        # Verify known extended fields [BINARY_VERIFIED]
        ilvl = read_bits(data, item_start_bit + ext_start + OFFSET_ILVL, 7)
        qual = read_bits(data, item_start_bit + ext_start + OFFSET_QUALITY, 4)
        print(f"  iLVL={ilvl} (expect {tc_info['ilvl']}) {'[OK]' if ilvl==tc_info['ilvl'] else '[NO]'}")
        print(
            f"  quality={qual} (expect {tc_info['quality']}) {'[OK]' if qual==tc_info['quality'] else '[NO]'}"
        )

        # TC-specific analysis
        if tc == 8:
            analyze_tc08_durability(data, item_start_bit, ext_start, tc_info)
        elif tc == 9:
            analyze_tc09(data, item_start_bit, ext_start, tc_info)

    # Cross-TC comparison if both available
    if 8 in all_data and 9 in all_data:
        cross_tc_comparison(
            all_data[8],
            all_data[9],
            item_start_bits[8],
            item_start_bits[9],
            ext_starts[8],
            ext_starts[9],
        )

    print_section("SUMMARY")
    print("  Questions to answer from this output:")
    print("  Q1: Where exactly is max_dur=250 in TC09? (search results in STEP 1)")
    print("  Q2: Is cur_dur=250 immediately after max_dur? (consecutive 250s)")
    print("  Q3: Does TC09 (Weapon) have a defense field? (compare to TC08 Armor)")
    print("  Q4: With 250/250 known position, does TC08 field layout now make sense?")
    print("  Q5: Is there an extra bit between max_dur and cur_dur?")
    print()
    print("  *** After analysis, update VERIFICATION_LOG.md with correct durability layout ***")

    return 0


if __name__ == "__main__":
    sys.exit(main())
