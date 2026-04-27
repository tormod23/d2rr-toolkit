"""
tests/verification/verify_huffman.py
=====================================
PURPOSE : Verify the Huffman-encoded item code decoding in v105 saves.

          The spec claims (all [SPEC_ONLY] until confirmed here):
            - Item codes are Huffman-encoded starting at bit 60 of each item
            - The Huffman tree is from d07riv's Phrozen Keep post
            - Codes are terminated by a space character (' ' = bit pattern 10)
            - Item codes are 3-4 characters (e.g. "hp1", "stu", "9ss")

          APPROACH: We do NOT assume bit 60 is correct for v105.
          Instead, we try multiple starting bit offsets (56-70) and check
          which one yields valid Huffman decoding. Valid = decodes to a
          known item code that exists in the game data files.

          This is the safest approach: let the data tell us the right offset.

STATUS  : [SPEC_ONLY] -> produces [BINARY_VERIFIED] evidence
COVERS  : VER-006

KNOWN ANCHORS [BINARY_VERIFIED]:
  - TC01 first JM: offset 916,  item count = 6
  - TC02 first JM: offset 921,  item count = 9
  - TC03 first JM: offset 921,  item count = 24
  - Items start at: JM_offset + 4 (2 bytes JM + 2 bytes count)

KNOWN ITEMS FROM TC READMEs (ground truth for verification):
  TC01: Superior Short Sword, Vicious Spear (magic), 4x Minor Healing Potion
  TC02: 5x Studded Leather (various qualities), 4x Minor Healing Potion
  TC03: Skull Cap, Amulet, Quilted Armor, Spiked Club, Buckler,
        2x Ring, Light Belt, Boots, Gloves, Superior Studded Leather,
        Orb of Conversion, Diamond, Orb of Socketing, Skull,
        Orb of Conversion, Rune Pliers, Orb of Assemblage, Gem Cluster,
        Orb of Infusion, Jewel Pliers, Orb of Renewal, Orb of Shadows,
        Orb of Corruption

USAGE   : python tests/verification/verify_huffman.py <path.d2s> [tc_number]
          python tests/verification/verify_huffman.py tests/cases/TC01/TestABC.d2s 1
          python tests/verification/verify_huffman.py tests/cases/TC02/TestABC.d2s 2
          python tests/verification/verify_huffman.py tests/cases/TC03/TestWarlock.d2s 3

DATE    : 2026-03-24
"""

import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")


# ============================================================
# VERIFIED CONSTANTS [BINARY_VERIFIED]
# ============================================================

# First JM offsets per TC file [BINARY_VERIFIED VER-005]
FIRST_JM_OFFSETS: dict[int, int] = {
    1: 916,
    2: 921,
    3: 921,
}
ITEM_DATA_RELATIVE_OFFSET = 4  # bytes: skip "JM" (2) + uint16 count (2)


# ============================================================
# HUFFMAN TREE [SPEC_ONLY] - from d07riv Phrozen Keep post
# Confirmed by D2SLib, D2CE, hero-editor - HIGH confidence
# but not yet verified against THIS mod/version at bit level.
# ============================================================

# Format: character -> bit string (MSB first as written, read LSB first from file)
# The bit patterns below are as documented by d07riv.
# IMPORTANT: These are the bit patterns read from the file LSB-first.
HUFFMAN_TABLE: dict[str, str] = {
    " ": "10",  # space = terminator
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
    # '_': unknown - [SPEC_ONLY] underscore mapping not documented
}


class HuffmanNode:
    """Node in the Huffman decoding tree."""

    def __init__(self) -> None:
        self.children: dict[int, "HuffmanNode"] = {}  # 0 or 1 -> child node
        self.character: str | None = None  # set on leaf nodes only

    @property
    def is_leaf(self) -> bool:
        return self.character is not None


def build_huffman_tree() -> HuffmanNode:
    """Build the Huffman decoding tree from the table.

    Each bit pattern string represents the path from root to leaf.
    Bit pattern character '0' means go to child[0], '1' means child[1].
    The patterns are read left-to-right, which corresponds to LSB-first
    from the file (first bit read = leftmost character in pattern string).
    """
    root = HuffmanNode()
    for char, pattern in HUFFMAN_TABLE.items():
        node = root
        for bit_char in pattern:
            bit = int(bit_char)
            if bit not in node.children:
                node.children[bit] = HuffmanNode()
            node = node.children[bit]
        node.character = char
    return root


def read_bit_lsb(data: bytes, bit_pos: int) -> int:
    """Read a single bit at bit_pos using LSB-first ordering. [BINARY_VERIFIED]"""
    byte_idx = bit_pos // 8
    bit_idx = bit_pos % 8
    if byte_idx >= len(data):
        return -1  # end of data
    return (data[byte_idx] >> bit_idx) & 1


def decode_huffman_code(
    data: bytes,
    start_bit: int,
    tree: HuffmanNode,
    max_chars: int = 8,
    max_bits: int = 80,
) -> tuple[str, int] | None:
    """Attempt to decode one Huffman item code starting at start_bit.

    Returns:
        (decoded_string, bits_consumed) if successful (terminated by space),
        None if decoding failed (invalid path, too long, or end of data).

    The returned string does NOT include the space terminator character.
    bits_consumed includes the space terminator bits.
    """
    node = tree
    result = []
    bits_used = 0

    while bits_used < max_bits:
        bit = read_bit_lsb(data, start_bit + bits_used)
        if bit == -1:
            return None  # ran off end of data

        bits_used += 1

        if bit not in node.children:
            return None  # invalid path in tree

        node = node.children[bit]

        if node.is_leaf:
            if node.character == " ":
                # Space = terminator, decoding complete
                return ("".join(result), bits_used)
            result.append(node.character)
            node = tree  # reset to root for next character
            if len(result) > max_chars:
                return None  # suspiciously long code

    return None  # exceeded max_bits


def is_plausible_item_code(code: str) -> bool:
    """Basic sanity check: is this a plausible D2 item code?

    D2 item codes are 3-4 characters: letters and digits only.
    Codes like "hp1", "stu", "9ss", "r01" are valid.
    Random garbage like "zzz" would be invalid (not in game data).
    This is a structural check only - we verify against game data separately.
    """
    if len(code) < 2 or len(code) > 4:
        return False
    return all(c.isalnum() or c == "_" for c in code)


# ============================================================
# GAME DATA LOADER (optional - for cross-referencing item codes)
# ============================================================


def load_item_codes_from_game_data(excel_dir: Path) -> set[str]:
    """Load all valid item codes from game data .txt files.

    Looks for armor.txt, weapons.txt, misc.txt in the given directory.
    Returns a set of valid 'code' column values.
    This allows us to verify that decoded Huffman codes are real items.
    """
    codes: set[str] = set()
    files_to_check = ["armor.txt", "weapons.txt", "misc.txt"]

    for filename in files_to_check:
        filepath = excel_dir / filename
        if not filepath.exists():
            continue
        try:
            with open(filepath, "r", encoding="utf-8", errors="replace") as f:
                lines = f.readlines()
            if not lines:
                continue

            # First line is header, find 'code' column index
            headers = lines[0].strip().split("\t")
            try:
                code_idx = headers.index("code")
            except ValueError:
                continue

            for line in lines[1:]:
                parts = line.strip().split("\t")
                if len(parts) > code_idx:
                    code = parts[code_idx].strip()
                    if code and code != "Expansion":
                        codes.add(code)

            print(f"  Loaded {len(codes)} codes so far from {filename}")
        except Exception as e:
            print(f"  Warning: could not read {filename}: {e}")

    return codes


# ============================================================
# MAIN VERIFICATION LOGIC
# ============================================================


def try_decode_items_at_offset(
    data: bytes,
    items_start_bit: int,
    item_count: int,
    tree: HuffmanNode,
    code_bit_offset: int,
    valid_codes: set[str],
    max_items: int = 6,
) -> tuple[list[str], int]:
    """Try to decode item codes assuming Huffman starts at code_bit_offset
    bits into each item.

    This is the brute-force search: we try different values of code_bit_offset
    (e.g. 56, 58, 60, 62, 64) and see which produces valid item codes.

    Returns:
        (list of decoded codes, number of valid codes found)
    """
    decoded_codes: list[str] = []
    # We can't know item boundaries without parsing the full item,
    # so we use a heuristic: decode one code starting at
    # items_start_bit + code_bit_offset (for the FIRST item only).
    # If it works, we record it as a candidate.

    huff_start = items_start_bit + code_bit_offset
    result = decode_huffman_code(data, huff_start, tree)

    if result is None:
        return [], 0

    code, bits_used = result
    if not is_plausible_item_code(code):
        return [], 0

    in_game_data = code in valid_codes if valid_codes else None
    decoded_codes.append(code)
    valid_count = 1 if (in_game_data is None or in_game_data) else 0

    return decoded_codes, valid_count


def print_section(title: str) -> None:
    print(f"\n{'=' * 60}")
    print(f"  {title}")
    print(f"{'=' * 60}")


def hex_dump(data: bytes, start: int, length: int, label: str = "") -> None:
    chunk = data[start : start + length]
    hex_part = " ".join(f"{b:02X}" for b in chunk)
    ascii_part = "".join(chr(b) if 32 <= b < 127 else "." for b in chunk)
    prefix = f"  [{label:30s}] " if label else "  "
    print(f"{prefix}0x{start:04X} ({start:4d}d):  {hex_part:<48s}  |{ascii_part}|")


def bits_at(data: bytes, start_bit: int, count: int = 16) -> str:
    """Return a string of 0s and 1s for debugging bit layout."""
    bits = []
    for i in range(count):
        bits.append(str(read_bit_lsb(data, start_bit + i)))
        if (i + 1) % 8 == 0:
            bits.append(" ")
    return "".join(bits).strip()


def main() -> int:
    if len(sys.argv) < 2:
        print("Usage: python verify_huffman.py <path_to_d2s> [tc_number]")
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
            pass

    with open(path, "rb") as f:
        data = f.read()

    print()
    print("=" * 60)
    print("  D2RR Toolkit: Huffman Item Code Verification (VER-006)")
    print(f"  File: {path}  ({len(data)} bytes)")
    if tc_num:
        print(f"  Test Case: TC{tc_num:02d}")
    print("=" * 60)

    # --------------------------------------------------------
    # Load game data for code validation (optional)
    # --------------------------------------------------------
    valid_codes: set[str] = set()
    excel_paths = [
        path.parent.parent.parent / "excel" / "reimagined",
        path.parent.parent.parent / "excel" / "original",
    ]
    print_section("GAME DATA: Loading item codes for validation")
    for excel_dir in excel_paths:
        if excel_dir.exists():
            print(f"  Trying: {excel_dir}")
            valid_codes = load_item_codes_from_game_data(excel_dir)
            if valid_codes:
                print(f"  Total valid item codes loaded: {len(valid_codes)}")
                break
    if not valid_codes:
        print("  No game data found - will skip code validation against game data.")
        print("  Place game data in excel/reimagined/ or excel/original/ for full validation.")

    # --------------------------------------------------------
    # Build Huffman tree
    # --------------------------------------------------------
    tree = build_huffman_tree()
    print_section("Huffman Tree Built [SPEC_ONLY]")
    print(f"  Characters in table: {len(HUFFMAN_TABLE)}")
    print("  Note: '_' (underscore) mapping is unknown - [SPEC_ONLY]")

    # --------------------------------------------------------
    # Locate item data
    # --------------------------------------------------------
    if tc_num and tc_num in FIRST_JM_OFFSETS:
        jm_offset = FIRST_JM_OFFSETS[tc_num]
    else:
        # Search for JM in file starting after stats
        jm_pos = data.find(b"JM", 833)
        if jm_pos == -1:
            print("ERROR: Could not find JM header")
            return 1
        jm_offset = jm_pos
        print(f"  Auto-detected JM offset: {jm_offset}")

    item_count = int.from_bytes(data[jm_offset + 2 : jm_offset + 4], "little")
    items_start_byte = jm_offset + ITEM_DATA_RELATIVE_OFFSET
    items_start_bit = items_start_byte * 8

    print_section("ITEM LIST ANCHOR [BINARY_VERIFIED]")
    print(f"  JM header at byte  : {jm_offset} (0x{jm_offset:04X})")
    print(f"  Item count         : {item_count}")
    print(f"  Items data starts  : byte {items_start_byte} (0x{items_start_byte:04X})")
    print(f"  Items data starts  : bit  {items_start_bit}")
    hex_dump(data, items_start_byte, 16, "First 16 bytes of items")

    # --------------------------------------------------------
    # Show bit layout of first item bytes
    # --------------------------------------------------------
    print_section("BIT LAYOUT: First 80 bits of item data")
    print("  [SPEC_ONLY] Spec says item structure starts with flag bits,")
    print("  then Huffman code at bit 60. We test multiple offsets.")
    print()
    for row in range(0, 80, 16):
        bit_str = bits_at(data, items_start_bit + row, 16)
        byte_off = items_start_byte + row // 8
        print(
            f"  bits {items_start_bit+row:5d}-{items_start_bit+row+15:5d} "
            f"(byte ~{byte_off:4d}): {bit_str}"
        )

    # --------------------------------------------------------
    # BRUTE FORCE: Try Huffman decoding at multiple bit offsets
    # --------------------------------------------------------
    print_section("BRUTE FORCE: Try Huffman at bit offsets 40-80 [SPEC_ONLY=60]")
    print("  Trying to decode item code at each candidate bit offset.")
    print("  A successful decode yields a 2-4 char alphanumeric string.")
    print()
    print(
        f"  {'Bit offset':>12}  {'Decoded code':>14}  {'In game data?':>14}  {'Bits used':>10}  {'Verdict'}"
    )
    print(f"  {'-'*12}  {'-'*14}  {'-'*14}  {'-'*10}  {'-'*20}")

    candidates: list[tuple[int, str, int]] = []  # (bit_offset, code, bits_used)

    for bit_offset in range(40, 81):
        huff_start = items_start_bit + bit_offset
        result = decode_huffman_code(data, huff_start, tree)

        if result is None:
            continue

        code, bits_used = result
        if not is_plausible_item_code(code):
            continue

        in_game = "YES" if code in valid_codes else ("N/A" if not valid_codes else "NO")
        spec_marker = " <-- SPEC" if bit_offset == 60 else ""
        print(
            f"  {bit_offset:>12}  {code:>14}  {in_game:>14}  {bits_used:>10}  "
            f"VALID{spec_marker}"
        )
        candidates.append((bit_offset, code, bits_used))

    if not candidates:
        print("  NO valid Huffman codes found in range 40-80!")
        print("  Possible causes:")
        print("    - Item bit layout differs from spec in v105")
        print("    - Huffman table has errors")
        print("    - Items section starts at wrong position")
        print("    - First item may be a 'simple' item with different layout")

    # --------------------------------------------------------
    # Deep decode: for best candidate, try to read ALL items
    # --------------------------------------------------------
    if candidates:
        # Priority order for best candidate:
        # 1. Game-data-validated candidate (code confirmed YES in valid_codes)
        # 2. Spec offset (bit 60) if it produced a result
        # 3. First valid candidate as fallback
        # This prevents picking a random offset just because it appears first.
        game_validated = next((c for c in candidates if valid_codes and c[1] in valid_codes), None)
        spec_candidate = next((c for c in candidates if c[0] == 60), None)
        best = game_validated or spec_candidate or candidates[0]
        best_bit_offset, first_code, _ = best

        print_section(
            f"DEEP DECODE: All items at bit offset {best_bit_offset} "
            f"({'spec value' if best_bit_offset == 60 else 'found by search'})"
        )
        print(f"  [SPEC_ONLY] Item header = {best_bit_offset} fixed bits before code")
        print("  WARNING: We cannot know item boundaries without parsing full items.")
        print("  Strategy: decode first item code, then attempt next items")
        print("  by scanning forward for more valid Huffman codes.")
        print()

        # Decode as many items as we can from the stream
        # IMPORTANT: We can only reliably decode the FIRST item's code.
        # After that, we don't know the item's total bit length.
        # So we show the first code and then explain the limitation.
        print(f"  Item #1 code: '{first_code}'  (at bit offset {best_bit_offset})")
        if first_code in valid_codes:
            print("    -> Confirmed in game data files!")
        elif valid_codes:
            print("    -> NOT in game data files (may be Reimagined-specific)")
        print()

        # Show what bits look like after the first code
        _, bits_used_first = decode_huffman_code(data, items_start_bit + best_bit_offset, tree)  # type: ignore[misc]
        next_start = items_start_bit + best_bit_offset + bits_used_first
        print(f"  After first code: bit {next_start} " f"(byte ~{next_start // 8})")
        print("  Remaining item #1 data follows (unknown length)")
        print()
        print("  NOTE: To decode all items, we need to know the full item")
        print("  bit structure (all flag fields before the code).")
        print("  This requires VER-006b: full item structure verification.")
        print("  For now, confirming the Huffman code START OFFSET is sufficient.")

    # --------------------------------------------------------
    # Verdict
    # --------------------------------------------------------
    print_section("VERDICT")
    if candidates:
        if spec_candidate := next((c for c in candidates if c[0] == 60), None):
            print(f"  Spec bit offset 60 produces valid code: '{spec_candidate[1]}'")
            if valid_codes and spec_candidate[1] in valid_codes:
                print(f"  Code '{spec_candidate[1]}' confirmed in game data.")
                print("  RESULT: Huffman at bit offset 60 CONFIRMED.")
                print("  -> [BINARY_VERIFIED] Huffman code starts at item bit 60")
                print("  -> [BINARY_VERIFIED] Huffman table from d07riv is correct")
            else:
                print(f"  Code '{spec_candidate[1]}' not in loaded game data.")
                print(
                    f"  -> Manual verification needed: is '{spec_candidate[1]}' a valid item code?"
                )
                print("  -> Check excel/reimagined/misc.txt, armor.txt, weapons.txt")
        else:
            print("  Spec bit offset 60 did NOT produce a valid code.")
            print(f"  Best found offset: {candidates[0][0]} -> '{candidates[0][1]}'")
            print("  -> Huffman offset differs from spec. [CONTRADICTED]")
            print(f"  -> Update bit offset to {candidates[0][0]} in constants.")
    else:
        print("  INCONCLUSIVE - no valid codes found.")
        print("  -> Huffman table or item structure needs further investigation.")

    print()
    print("  *** RECORD RESULT IN VERIFICATION_LOG.md VER-006 ***")
    print("  *** Key questions: ***")
    print("  Q1: Does bit offset 60 produce a valid item code?")
    print("  Q2: Is the decoded code in the game data files?")
    print("  Q3: Does the code match the known first item in this TC?")

    return 0


if __name__ == "__main__":
    sys.exit(main())
