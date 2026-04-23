"""
tests/verification/verify_item_bitstructure.py
===============================================
PURPOSE : Verify item bit structure in v105 D2R Reimagined saves.

          Covers three distinct verification goals depending on TC:
            TC01/02/03 - Flag bits 0-52 + Huffman code offset
            TC07       - Simple item EXACT BIT SIZE measurement
            TC08       - Extended item fields AFTER Huffman code

VERSION : 3 - Added TC07 (simple item size) and TC08 (extended item structure)

ITEM QUALITY NOTATION (Reimagined mod display - NOT stored in binary):
  [N] = Normal tier base item     (e.g. "Leather Gloves [N]")
  [X] = Exceptional tier base item
  [E] = Elite tier base item       *** [E] != Ethereal! ***
  (nn) = item level (iLVL)        (e.g. "(12)")
  These are display-only. Tier and iLVL have separate binary representations.
  Ethereal = separate bit flag (bit 22). NOT related to [E] notation.

VERIFIED ITEM BIT LAYOUT (v105) [BINARY_VERIFIED]:
  bits  0- 3:  unknown_flags_0_3    (always 0 in tests)
  bit      4:  identified
  bits  5-10:  unknown_5_10         (always 0)
  bit     11:  socketed
  bit     12:  unknown_12
  bit     13:  picked_up_since_save
  bits 14-15:  unknown_14_15
  bit     16:  is_ear
  bit     17:  starter_item         [BINARY_VERIFIED]
  bits 18-20:  unknown_18_20
  bit     21:  simple_item          [BINARY_VERIFIED]
  bit     22:  ethereal
  bit     23:  unknown_23           (always 1 in tests)
  bit     24:  personalized
  bit     25:  unknown_25
  bit     26:  runeword
  bits 27-31:  unknown_27_31
  bits 32-34:  unknown_32_34        (always 5 = 0b101 in tests)
  bits 35-37:  location_id          [BINARY_VERIFIED]
  bits 38-41:  equipped_slot        [BINARY_VERIFIED]
  bits 42-45:  position_x           [BINARY_VERIFIED]
  bits 46-49:  position_y           [BINARY_VERIFIED]
  bits 50-52:  panel_id             [BINARY_VERIFIED]
  bit     53+: Huffman item code    [BINARY_VERIFIED]

USAGE   : python tests/verification/verify_item_bitstructure.py <path.d2s> [tc_number]
          tc_number: 1, 2, 3, 7, or 8
DATE    : 2026-03-24
"""

import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")


# ============================================================
# VERIFIED CONSTANTS [BINARY_VERIFIED]
# ============================================================

HUFFMAN_BIT_OFFSET = 53
GF_OFFSET = 833

ITEMS_START_BYTE_KNOWN: dict[int, int] = {
    1: 920,
    2: 925,
    3: 925,
    # TC07, TC08: auto-detected (Level 1 chars have smaller stats sections)
}

LOCATION_NAMES = {0: "Stored", 1: "Equipped", 2: "Belt", 4: "Cursor", 6: "Socketed"}
PANEL_NAMES = {0: "None", 1: "Inventory", 4: "Cube", 5: "Stash"}
SLOT_NAMES = {
    0: "Not equipped",
    1: "Head",
    2: "Neck/Amulet",
    3: "Torso",
    4: "Right Hand",
    5: "Left Hand",
    6: "Right Ring",
    7: "Left Ring",
    8: "Waist/Belt",
    9: "Feet/Boots",
    10: "Hands/Gloves",
    11: "Alt Right Hand",
    12: "Alt Left Hand",
}
QUALITY_NAMES = {
    1: "Low Quality",
    2: "Normal",
    3: "Superior",
    4: "Magic",
    5: "Set",
    6: "Rare",
    7: "Unique",
    8: "Crafted",
}

VERIFIED_FIELDS: list[tuple[int, int, str]] = [
    (0, 4, "unknown_flags_0_3"),
    (4, 1, "identified"),
    (5, 6, "unknown_5_10"),
    (11, 1, "socketed"),
    (12, 1, "unknown_12"),
    (13, 1, "picked_up_since_save"),
    (14, 2, "unknown_14_15"),
    (16, 1, "is_ear"),
    (17, 1, "starter_item"),
    (18, 3, "unknown_18_20"),
    (21, 1, "simple_item"),
    (22, 1, "ethereal"),
    (23, 1, "unknown_23"),
    (24, 1, "personalized"),
    (25, 1, "unknown_25"),
    (26, 1, "runeword"),
    (27, 5, "unknown_27_31"),
    (32, 3, "unknown_32_34"),
    (35, 3, "location_id"),
    (38, 4, "equipped_slot"),
    (42, 4, "position_x"),
    (46, 4, "position_y"),
    (50, 3, "panel_id"),
]

KNOWN_ITEM1: dict[int, dict] = {
    1: {
        "description": "hp1 Minor Healing Potion - Belt, STARTER, SIMPLE",
        "identified": 1,
        "starter_item": 1,
        "simple_item": 1,
        "socketed": 0,
        "is_ear": 0,
        "ethereal": 0,
        "runeword": 0,
        "personalized": 0,
        "location_id": 2,
        "panel_id": 0,
        "equipped_slot": 0,
    },
    2: {
        "description": "stu Normal Studded Leather - Inventory (0,0), NOT starter",
        "identified": 1,
        "starter_item": 0,
        "simple_item": 0,
        "socketed": 0,
        "is_ear": 0,
        "ethereal": 0,
        "runeword": 0,
        "personalized": 0,
        "location_id": 0,
        "panel_id": 1,
        "equipped_slot": 0,
        "position_x": 0,
        "position_y": 0,
    },
    3: {
        "description": "qui Quilted Armor - Equipped, Torso slot 3",
        "identified": 1,
        "starter_item": 0,
        "simple_item": 0,
        "socketed": 0,
        "is_ear": 0,
        "ethereal": 0,
        "runeword": 0,
        "personalized": 0,
        "location_id": 1,
        "panel_id": 0,
        "equipped_slot": 3,
    },
    7: {
        # KEY: bought from Akara, NOT starter item - different from TC01!
        "description": "hp1 Minor Healing Potion - Belt Slot 0, BOUGHT (not starter), SIMPLE",
        "identified": 1,
        "starter_item": 0,  # BOUGHT not starter - critical test
        "simple_item": 1,
        "socketed": 0,
        "is_ear": 0,
        "ethereal": 0,
        "runeword": 0,
        "personalized": 0,
        "location_id": 2,
        "panel_id": 0,
        "equipped_slot": 0,
    },
    8: {
        "description": "lgl Leather Gloves [N] iLVL=6, Def=3, Dur=12/12 - Inventory (0,0), Normal quality",
        "identified": 1,
        "starter_item": 0,
        "simple_item": 0,
        "socketed": 0,
        "is_ear": 0,
        "ethereal": 0,
        "runeword": 0,
        "personalized": 0,
        "location_id": 0,
        "panel_id": 1,
        "equipped_slot": 0,
        "position_x": 0,
        "position_y": 0,
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
# AUTO-DETECT HELPERS
# ============================================================


def find_first_jm(data: bytes) -> int | None:
    pos = data.find(b"JM", GF_OFFSET)
    return pos if pos != -1 else None


def find_second_jm(data: bytes) -> int | None:
    first = find_first_jm(data)
    if first is None:
        return None
    second = data.find(b"JM", first + 2)
    return second if second != -1 else None


def get_item_count(data: bytes) -> int:
    jm = find_first_jm(data)
    if jm is None:
        return 0
    return int.from_bytes(data[jm + 2 : jm + 4], "little")


# ============================================================
# DISPLAY
# ============================================================


def print_section(title: str) -> None:
    print(f"\n{'=' * 65}")
    print(f"  {title}")
    print(f"{'=' * 65}")


# ============================================================
# FLAG BITS VERIFICATION (TC01/02/03/07/08)
# ============================================================


def verify_flag_bits(data: bytes, item_start_byte: int, tc_num: int) -> None:
    item_start_bit = item_start_byte * 8

    huff_result = decode_huffman(data, item_start_bit + HUFFMAN_BIT_OFFSET)
    if huff_result:
        code, huff_bits = huff_result
        print(f"\n  Huffman code: '{code}'  ({huff_bits} bits)  [BINARY_VERIFIED]")
    else:
        print("\n  ERROR: Huffman decode failed at bit 53")
        return

    print_section("Item flag fields (corrected v105 layout)")
    print(f"  {'Bit(s)':<10} {'W':>3}  {'Field':<24}  {'Val':>5}  Interpretation       Status")
    print(f"  {'-'*10} {'-'*3}  {'-'*24}  {'-'*5}  {'-'*20}  {'-'*6}")

    fields: dict[str, int] = {}
    for bit_offset, bit_count, name in VERIFIED_FIELDS:
        val = read_bits(data, item_start_bit + bit_offset, bit_count)
        fields[name] = val
        lbl = str(bit_offset) if bit_count == 1 else f"{bit_offset}-{bit_offset+bit_count-1}"
        interp = ""
        if name == "location_id":
            interp = LOCATION_NAMES.get(val, f"?({val})")
        elif name == "panel_id":
            interp = PANEL_NAMES.get(val, f"?({val})")
        elif name == "equipped_slot":
            interp = SLOT_NAMES.get(val, f"slot {val}")
        elif name in (
            "identified",
            "starter_item",
            "simple_item",
            "socketed",
            "runeword",
            "ethereal",
            "personalized",
            "is_ear",
        ):
            interp = "YES" if val else ""
        bv = (
            "[BV]"
            if name
            in (
                "identified",
                "starter_item",
                "simple_item",
                "socketed",
                "is_ear",
                "ethereal",
                "runeword",
                "personalized",
                "location_id",
                "equipped_slot",
                "position_x",
                "position_y",
                "panel_id",
            )
            else "[??]"
        )
        print(f"  {lbl:<10} {bit_count:>3}  {name:<24}  {val:>5}  {interp:<20}  {bv}")

    if tc_num in KNOWN_ITEM1:
        known = KNOWN_ITEM1[tc_num]
        print_section(f"Compare to TC{tc_num:02d} known values")
        print(f"  {known['description']}\n")
        print(f"  {'Field':<24} {'Expected':>9} {'Found':>7}  Match")
        print(f"  {'-'*24} {'-'*9} {'-'*7}  {'-'*5}")
        matches = total = 0
        for field, expected in known.items():
            if field == "description":
                continue
            total += 1
            found = fields.get(field, -1)
            ok = found == expected
            if ok:
                matches += 1
            print(f"  {field:<24} {str(expected):>9} {found:>7}  {'[OK]' if ok else '[NO]'}")
        print(f"\n  Score: {matches}/{total}")
        if matches == total:
            print("  ALL MATCH [OK]")
        else:
            print(f"  {total - matches} mismatch(es)")


# ============================================================
# TC07: SIMPLE ITEM SIZE MEASUREMENT
# ============================================================


def verify_simple_item_size(data: bytes, items_start_byte: int) -> None:
    print_section("TC07 PRIMARY: Simple Item Exact Size Measurement")

    second_jm = find_second_jm(data)
    if second_jm is None:
        print("  ERROR: Could not find second JM")
        return

    item_byte_count = second_jm - items_start_byte
    item_bit_count = item_byte_count * 8

    print(f"  Items start byte  : {items_start_byte}")
    print(f"  Second JM at byte : {second_jm}")
    print(f"  Item byte count   : {item_byte_count}")
    print(f"  Item bit count    : {item_bit_count}")

    huff_result = decode_huffman(data, items_start_byte * 8 + HUFFMAN_BIT_OFFSET)
    if huff_result is None:
        print("  ERROR: Huffman decode failed")
        return
    code, huff_bits = huff_result
    huff_end_bit = HUFFMAN_BIT_OFFSET + huff_bits

    print(f"\n  Huffman code '{code}': {huff_bits} bits, ends at item-relative bit {huff_end_bit}")

    # Spec: 1 socket bit then byte pad
    socket_val = read_bit(data, items_start_byte * 8 + huff_end_bit)
    after_socket = huff_end_bit + 1
    pad = (8 - after_socket % 8) % 8
    spec_total = after_socket + pad

    print(f"\n  [SPEC_ONLY] Socket bit at item bit {huff_end_bit}: {socket_val}")
    print(f"  [SPEC_ONLY] Bits before pad: {after_socket}")
    print(f"  [SPEC_ONLY] Padding: {pad} bits")
    print(f"  [SPEC_ONLY] Spec-predicted total: {spec_total} bits ({spec_total//8} bytes)")
    print(f"  File-measured total:              {item_bit_count} bits ({item_byte_count} bytes)")
    print()

    if spec_total == item_bit_count:
        print("  MATCH [OK]")
        print("  [BINARY_VERIFIED] simple item = flags(53) + Huffman + 1 socket bit + byte pad")
    else:
        diff = item_bit_count - spec_total
        print(f"  MISMATCH [NO]  difference: {diff} bits")
        print(f"  Showing bits {spec_total} to {item_bit_count-1} for diagnosis:")
        for i in range(abs(diff) + 4):
            b = read_bit(data, items_start_byte * 8 + spec_total + i)
            print(f"    item bit {spec_total+i}: {b}")

    print_section("TC07: Full item raw bytes")
    item_bytes = data[items_start_byte:second_jm]
    for row in range(0, len(item_bytes), 8):
        chunk = item_bytes[row : row + 8]
        h = " ".join(f"{b:02X}" for b in chunk)
        a = "".join(chr(b) if 32 <= b < 127 else "." for b in chunk)
        print(f"    [{row:2d}] {h:<24}  |{a}|")

    print("\n  Full item as bits:")
    bits_str = "".join(str(read_bit(data, items_start_byte * 8 + i)) for i in range(item_bit_count))
    for row in range(0, item_bit_count, 16):
        print(f"    bit {row:3d}: {bits_str[row:row+16]}")


# ============================================================
# TC08: EXTENDED ITEM STRUCTURE AFTER HUFFMAN CODE
# ============================================================


def verify_extended_item_structure(data: bytes, items_start_byte: int) -> None:
    print_section("TC08 PRIMARY: Extended Item Fields After Huffman Code")
    print("  [BINARY_VERIFIED] Simple items = 80 bits = 10 bytes (TC07 confirmed)")
    print("  Scanning items until first non-simple item...")
    print()

    SIMPLE_ITEM_BITS = 80  # [BINARY_VERIFIED] from TC07
    item_start_bit = items_start_byte * 8
    target_start_bit = None

    for item_num in range(1, 30):
        simple_flag = read_bits(data, item_start_bit + 21, 1)
        huff = decode_huffman(data, item_start_bit + HUFFMAN_BIT_OFFSET)
        code_peek = huff[0] if huff else "???"
        print(
            f"  Item #{item_num}: simple={simple_flag}, code='{code_peek}' at byte {item_start_bit // 8}"
        )
        if not simple_flag:
            target_start_bit = item_start_bit
            print("  -> Non-simple item found! This is our target.")
            break
        item_start_bit += SIMPLE_ITEM_BITS  # [BINARY_VERIFIED]
    else:
        print("  ERROR: No non-simple item found")
        return

    if target_start_bit is None:
        return

    print()
    item_start_bit = target_start_bit

    huff_result = decode_huffman(data, item_start_bit + HUFFMAN_BIT_OFFSET)
    if huff_result is None:
        print("  ERROR: Huffman decode failed on target item")
        return
    code, huff_bits = huff_result
    print(f"  Target Huffman code: '{code}'  ({huff_bits} bits)")
    if code != "lgl":
        print(f"  WARNING: Expected 'lgl' (Leather Gloves), got '{code}'")

    ext_start = HUFFMAN_BIT_OFFSET + huff_bits
    print(f"  Extended data starts at item-relative bit: {ext_start}")
    print()

    bit = ext_start

    def read_field(name: str, count: int, note: str = "") -> int:
        nonlocal bit
        val = read_bits(data, item_start_bit + bit, count)
        print(f"  bit {bit:3d}+{count:2d}: {name:<30} = {val:6d}  (0x{val:04X})  {note}")
        bit += count
        return val

    print(f"  {'Start':>7}  {'W':>3}  {'Field':<30}  {'Value':>8}  Notes")
    print(f"  {'-'*7}  {'-'*3}  {'-'*30}  {'-'*8}  {'-'*20}")

    unique_id = read_field("unique_item_id", 32, "[SPEC_ONLY] random")

    item_level = read_field("item_level (iLVL)", 7, "[SPEC_ONLY] expect 12")
    quality = read_field("quality", 4, "expect 2=Normal")
    has_gfx = read_field("has_custom_graphics", 1, "[SPEC_ONLY] expect 0")
    if has_gfx:
        read_field("  graphic_index", 3, "[SPEC_ONLY]")
    has_class = read_field("has_class_specific_data", 1, "[SPEC_ONLY] expect 0")
    if has_class:
        read_field("  class_specific_data", 11, "[SPEC_ONLY]")

    # Quality-specific data
    print(f"\n  Quality {quality} ({QUALITY_NAMES.get(quality,'?')}) specific data:")
    if quality == 1:
        read_field("  low_quality_type", 3, "[SPEC_ONLY]")
    elif quality == 3:
        read_field("  superior_type", 3, "[SPEC_ONLY]")
    elif quality == 4:
        read_field("  magic_prefix_id", 11, "[SPEC_ONLY]")
        read_field("  magic_suffix_id", 11, "[SPEC_ONLY]")
    elif quality == 5:
        read_field("  set_id", 12, "[SPEC_ONLY]")
    elif quality == 6 or quality == 8:
        read_field("  name_id_1", 8, "[SPEC_ONLY]")
        read_field("  name_id_2", 8, "[SPEC_ONLY]")
        for _ in range(6):
            has_affix = read_field("  has_affix", 1, "[SPEC_ONLY]")
            if has_affix:
                read_field("    affix_id", 11, "[SPEC_ONLY]")
    elif quality == 7:
        read_field("  unique_set_id", 12, "[SPEC_ONLY]")
    else:
        print("  -> Normal quality: no extra data [SPEC_ONLY]")

    print("\n  Optional fields from flag bits:")
    if read_bits(data, item_start_bit + 26, 1):  # runeword
        read_field("  runeword_str_index", 12, "[SPEC_ONLY]")
        read_field("  runeword_unknown", 4, "[SPEC_ONLY]")
    if read_bits(data, item_start_bit + 24, 1):  # personalized
        print("  -> personalized name field [SPEC_ONLY]")

    timestamp_bit = read_field("timestamp_unknown_bit", 1, "[SPEC_ONLY]")

    print("\n  Armor/weapon-specific data:")
    print("  [SPEC_ONLY] lgl (Leather Gloves) is in Armor.txt -> defense field present")
    defense_raw = read_field("  armor_defense (raw)", 11, "[SPEC_ONLY] display = raw - 10")
    print(f"             -> displayed defense = {defense_raw} - 10 = {defense_raw - 10}")

    max_dur = read_field("  max_durability", 9, "[SPEC_ONLY]")
    if max_dur > 0:
        cur_dur = read_field("  current_durability", 9, "[SPEC_ONLY]")
    else:
        print("  -> max_dur=0: indestructible")

    if read_bits(data, item_start_bit + 11, 1):  # socketed
        read_field("  num_sockets", 4, "[SPEC_ONLY]")

    print("\n  Magical properties (9-bit IDs until 0x1FF):")
    for i in range(20):
        stat_id = read_bits(data, item_start_bit + bit, 9)
        print(f"    bit {bit}: stat_id = {stat_id} (0x{stat_id:03X})", end="")
        bit += 9
        if stat_id == 0x1FF:
            print("  <- TERMINATOR [OK]")
            break
        else:
            print("  <- property (need ItemStatCost.txt to read width)")
            break  # stop safely

    print(f"\n  Total item bits consumed so far: {bit}")

    # Verification summary
    print_section("TC08: Verification of Known Values")
    # Re-read cleanly for comparison
    il = read_bits(data, item_start_bit + ext_start + 32, 7)
    qu = read_bits(data, item_start_bit + ext_start + 39, 4)
    gx = read_bits(data, item_start_bit + ext_start + 43, 1)
    cl = read_bits(data, item_start_bit + ext_start + 44, 1)

    checks = [
        ("item_level (iLVL)", 6, il),  # [CORRECTED] was 12, actual is 6
        ("quality", 2, qu),
        ("has_custom_graphics", 0, gx),
        ("has_class_data", 0, cl),
        ("max_dur > 0", 1, 1 if max_dur > 0 else 0),
        # defense displayed = raw - 10 = 3, so raw = 13
        # durability max = 12, current = 12
    ]
    all_ok = True
    print(f"  {'Field':<26} {'Expected':>9} {'Found':>9}  Match")
    print(f"  {'-'*26} {'-'*9} {'-'*9}  {'-'*5}")
    for name, exp, found in checks:
        ok = found == exp
        if not ok:
            all_ok = False
        print(f"  {name:<26} {exp:>9} {found:>9}  {'[OK]' if ok else '[NO]'}")
    print()
    if all_ok:
        print("  ALL MATCH [OK]  Extended item structure confirmed for Normal quality item!")
    else:
        print("  Mismatches detected - investigate before [BINARY_VERIFIED]")


# ============================================================
# MAIN
# ============================================================


def main() -> int:
    if len(sys.argv) < 2:
        print("Usage: python verify_item_bitstructure.py <path.d2s> [tc_number]")
        print("  tc_number: 1, 2, 3, 7, or 8")
        return 1

    path = Path(sys.argv[1])
    if not path.exists():
        print(f"ERROR: {path}")
        return 1

    tc_num: int | None = None
    if len(sys.argv) >= 3:
        try:
            tc_num = int(sys.argv[2])
        except ValueError:
            pass

    with open(path, "rb") as f:
        data = f.read()

    print()
    print("=" * 65)
    print("  D2RR Toolkit: Item Bit Structure Verification (VER-006b v3)")
    print(f"  File: {path}  ({len(data)} bytes)")
    if tc_num:
        print(f"  Test Case: TC{tc_num:02d}")
    print("=" * 65)

    if data[GF_OFFSET : GF_OFFSET + 2] != b"gf":
        print(f"\n  ERROR: 'gf' not at offset {GF_OFFSET}")
        return 1
    print(f"\n  [BINARY_VERIFIED] 'gf' at offset {GF_OFFSET} [OK]")
    print(f"  Item count: {get_item_count(data)}")

    # Determine items start byte
    if tc_num in ITEMS_START_BYTE_KNOWN:
        items_start_byte = ITEMS_START_BYTE_KNOWN[tc_num]
        print(f"  [BINARY_VERIFIED] Items start byte: {items_start_byte}")
    else:
        jm = find_first_jm(data)
        if jm is None:
            print("  ERROR: No JM found")
            return 1
        items_start_byte = jm + 4
        print(f"  [AUTO-DETECTED] JM at byte {jm}, items start at byte {items_start_byte}")
        print(f"  *** Record items_start_byte={items_start_byte} in VERIFICATION_LOG.md ***")

    print(f"  [BINARY_VERIFIED] Huffman at item-relative bit {HUFFMAN_BIT_OFFSET}")

    # Route by TC
    if tc_num == 7:
        verify_flag_bits(data, items_start_byte, 7)
        verify_simple_item_size(data, items_start_byte)
    elif tc_num == 8:
        verify_flag_bits(data, items_start_byte, 8)
        verify_extended_item_structure(data, items_start_byte)
    else:
        verify_flag_bits(data, items_start_byte, tc_num or 1)

    print_section("SUMMARY")
    if tc_num == 7:
        print("  Record in VERIFICATION_LOG.md:")
        print("  - items_start_byte for TC07")
        print("  - Exact simple item bit/byte count")
        print("  - starter_item=0 for bought potion (vs 1 for TC01 starter)")
        print("  - Socket bit value and position after Huffman code")
        print("  - Whether spec formula (53 + Huffman + 1 + pad) is correct")
    elif tc_num == 8:
        print("  Record in VERIFICATION_LOG.md:")
        print("  - items_start_byte for TC08")
        print("  - iLVL = 12 position and bit width")
        print("  - Quality = 2 (Normal) position and bit width")
        print("  - Durability field positions and values")
        print("  - 0x1FF terminator position")

    return 0


if __name__ == "__main__":
    sys.exit(main())

